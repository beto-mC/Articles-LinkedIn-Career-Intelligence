// Renders the mAInCharacter sonic logo from the canonical mC Sonic Constellation export,
// then encodes the MP3 the site plays. The audio engine and score are read from the export
// itself (nothing is copied by hand), rendered offline in headless Chrome with a seeded
// Math.random so every build sounds the same.
// Usage: node tools/audio-site/sonic/render.mjs <chrome> <export.html> <out.mp3>
// Needs playwright-core (the workflow installs it) and ffmpeg.
import { chromium } from 'playwright-core';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { dirname, resolve, join } from 'node:path';
import { tmpdir } from 'node:os';

const [chrome, source, out] = process.argv.slice(2);
if (!chrome || !source || !out) { console.error('usage: render.mjs <chrome> <export.html> <out.mp3>'); process.exit(2); }

const bundle = readFileSync(source, 'utf8');
const tm = bundle.match(/<script type="__bundler\/template"[^>]*>([\s\S]*?)<\/script>/);
if (!tm) throw new Error(`${source}: not a standalone export`);
const tpl = JSON.parse(tm[1]);
const js = (tpl.match(/<script>\(function\(\)\{([\s\S]*)\}\)\(\);<\/script>/) || [])[1] || '';
function cut(from, to) {
  const a = js.indexOf(from), b = js.indexOf(to, a);
  if (a < 0 || b < 0) throw new Error(`sonic export changed: cannot find "${from}" … "${to}"`);
  return js.slice(a, b);
}
const engine = cut('function makeIR', '/* ===== Sky');                    // audio engine
const score = cut('var t0 = ctx.currentTime + 0.1;', 'var base = (t0');     // the timeline in play()

const page = `<!doctype html><meta charset="utf-8"><script>
(function(){var x=20260921;Math.random=function(){x^=x<<13;x^=x>>>17;x^=x<<5;return ((x>>>0)%1e9)/1e9;};})();
var ctx=null,master=null,rev=null,SR=48000;
${engine}
async function render(){
  ctx=new OfflineAudioContext(2, SR*13, SR);
  /* same master chain as initAudio() in the export */
  var lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 9500; lp.Q.value = 0.4;
  var comp = ctx.createDynamicsCompressor();
  comp.threshold.value = -20; comp.knee.value = 24; comp.ratio.value = 4; comp.attack.value = 0.01; comp.release.value = 0.32;
  master = ctx.createGain(); master.gain.value = 0.9; master.connect(lp); lp.connect(comp); comp.connect(ctx.destination);
  rev = ctx.createConvolver(); rev.buffer = makeIR(3.4, 2.6);
  var rg = ctx.createGain(); rg.gain.value = 0.55; rev.connect(rg); rg.connect(master);
  ${score}
  var buf = await ctx.startRendering(), n = buf.length, L = buf.getChannelData(0), R = buf.getChannelData(1);
  var dv = new DataView(new ArrayBuffer(44 + n * 4));
  function ws(o, s){ for (var i = 0; i < s.length; i++) dv.setUint8(o + i, s.charCodeAt(i)); }
  ws(0,'RIFF'); dv.setUint32(4, 36 + n * 4, true); ws(8,'WAVE'); ws(12,'fmt '); dv.setUint32(16,16,true); dv.setUint16(20,1,true);
  dv.setUint16(22,2,true); dv.setUint32(24,SR,true); dv.setUint32(28,SR*4,true); dv.setUint16(32,4,true); dv.setUint16(34,16,true);
  ws(36,'data'); dv.setUint32(40, n * 4, true);
  for (var i = 0; i < n; i++){ dv.setInt16(44+i*4, Math.max(-1,Math.min(1,L[i]))*32767, true); dv.setInt16(46+i*4, Math.max(-1,Math.min(1,R[i]))*32767, true); }
  var b = new Uint8Array(dv.buffer), s = ''; for (var j = 0; j < b.length; j += 32768) s += String.fromCharCode.apply(null, b.subarray(j, j + 32768));
  return btoa(s);
}
</script>`;

const browser = await chromium.launch({ executablePath: chrome, args: ['--no-sandbox'] });
const p = await browser.newPage();
await p.setContent(page);
const b64 = await p.evaluate(() => render());
await browser.close();
const wav = join(tmpdir(), 'mc-sonic.wav');
writeFileSync(wav, Buffer.from(b64, 'base64'));
mkdirSync(dirname(resolve(out)), { recursive: true });
execFileSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-i', wav,
  '-af', 'afade=t=out:st=12.2:d=0.8', '-c:a', 'libmp3lame', '-b:a', '128k',
  '-metadata', 'title=mAInCharacter sonic logo — Constellation', '-metadata', 'artist=mAInCharacter',
  '-metadata', 'copyright=© mAInCharacter Advisory LLC', resolve(out)]);
console.log('Sonic logo rendered:', out);
