/* mc-audio-ga v1 — one Google Analytics 4 schema for every mAInCharacter audio player.
   Source of truth: beto-mC/Articles-LinkedIn-Career-Intelligence, tools/audio-site/audio-ga.js.
   The article pages on main-character.me carry an inline copy. Keep every copy identical,
   so the same episode reports the same way wherever it plays.

   What it tracks: any element with data-audio-id that contains an <audio> element.
     audio_play      first play of an episode in a page view
     audio_progress  25, 50 and 75 percent listened (audio_percent)
     audio_complete  played to the end (audio_percent 100)
     audio_download  a click on [data-audio-download="mp3|m4a|wav"] (audio_format), every click
     transcript_download  a click on [data-audio-transcript="md|txt"] (audio_format), every click
   Links point at their episode with data-audio-ref="<audio_id>".

   Parameters, identical for the same episode on every page:
     audio_id        <publication>/<episode>, e.g. 2026-09-21-ai-quotient/speedboats-vs-cargo-ships
                     (the same id as the episode's RSS guid)
     audio_title     the episode title, as tagged inside the MP3
     audio_file      the MP3 file name
     audio_kind      e.g. "Debate · two hosts"
     audio_duration  length in seconds
     publication     the publication slug
     surface         where it played: article | audio_site

   Events go through window.mcTrack, so each site keeps its own consent rules.
   Nothing is sent, and nothing is marked as sent, until Google Analytics is loaded. */
(function () {
  if (window.mcAudioGA) return;
  var sent = {};
  var ATTR = { audio_id: 'data-audio-id', audio_title: 'data-audio-title', audio_file: 'data-audio-file',
               audio_kind: 'data-audio-kind', audio_duration: 'data-audio-duration',
               publication: 'data-publication', surface: 'data-surface' };
  function source(ref) {
    var all = document.querySelectorAll('[data-audio-id]');
    for (var i = 0; i < all.length; i++) if (all[i].getAttribute('data-audio-id') === ref) return all[i];
    return null;
  }
  function params(el) {
    var p = {};
    for (var k in ATTR) p[k] = el.getAttribute(ATTR[k]) || '';
    p.audio_duration = parseInt(p.audio_duration, 10) || 0;
    return p;
  }
  function live() { return typeof window.mcTrack === 'function' && typeof window.gtag === 'function'; }
  /* once: a key that makes the event count once per episode per page view; omit to count every call */
  function track(name, el, extra, once) {
    if (!el || !el.getAttribute('data-audio-id') || !live()) return;
    var p = params(el);
    if (once) { var key = p.audio_id + '|' + name + '|' + once; if (sent[key]) return; sent[key] = 1; }
    if (extra) for (var x in extra) p[x] = extra[x];
    window.mcTrack(name, p);
  }
  function watch(el) {
    var a = el.querySelector('audio');
    if (!a || a.getAttribute('data-mc-ga')) return;
    a.setAttribute('data-mc-ga', '1');
    a.addEventListener('play', function () { track('audio_play', el, null, 'play'); });
    a.addEventListener('timeupdate', function () {
      var d = isFinite(a.duration) && a.duration > 0 ? a.duration : params(el).audio_duration;
      if (!d) return;
      var pct = a.currentTime / d * 100;
      [25, 50, 75].forEach(function (m) { if (pct >= m) track('audio_progress', el, { audio_percent: m }, m); });
    });
    a.addEventListener('ended', function () { track('audio_complete', el, { audio_percent: 100 }, 'end'); });
  }
  function init() { Array.prototype.forEach.call(document.querySelectorAll('[data-audio-id]'), watch); }
  document.addEventListener('click', function (ev) {
    var t = ev.target && ev.target.closest ? ev.target.closest('[data-audio-download],[data-audio-transcript]') : null;
    if (!t) return;
    var dl = t.hasAttribute('data-audio-download');
    track(dl ? 'audio_download' : 'transcript_download', source(t.getAttribute('data-audio-ref')),
          { audio_format: t.getAttribute(dl ? 'data-audio-download' : 'data-audio-transcript') });
  }, true);
  window.mcAudioGA = {
    version: 1,
    watch: init,
    /* for other listeners on the page, e.g. a transcript copy button */
    track: function (name, ref, extra) { track(name, source(ref), extra); }
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
