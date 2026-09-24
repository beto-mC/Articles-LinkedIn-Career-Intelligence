#!/usr/bin/env python3
"""mAInCharacter audio site builder.

Reads site.yml and every articles/<slug>/audio.yml, then writes a static site to _site/:
  index.html                    audio registry (newest first)
  <slug>/index.html             one page per publication
  <slug>/audio/*.mp3|m4a|wav    downloads, tagged with title, owner and license
  <slug>/transcripts/*.md|txt   branded transcripts, speakers labeled "Character N"
  registry.json                 machine feed for the master registry on main-character.me
  feed.xml                      podcast RSS (MP3 enclosures, transcript links)
  sitemap.xml, robots.txt, llms.txt, .nojekyll, CNAME (if custom_domain)

Skip rules: any folder whose name starts with "_" (e.g. articles/_template, _archive),
and any audio.yml with status: archived. status: draft builds the page (noindex) but
keeps it out of the registry, feed, sitemap and llms.txt.

Usage: python tools/audio-site/build.py [--out _site] [--brand-local DIR] [--site-url URL] [--no-audio]
"""
import argparse, datetime as dt, hashlib, html, json, os, re, shutil, subprocess, sys
from pathlib import Path
from urllib.parse import quote
import yaml

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
FMT = {
    "mp3": {"label": "MP3", "note": "Plays everywhere", "mime": "audio/mpeg"},
    "m4a": {"label": "M4A", "note": "Original quality (AAC)", "mime": "audio/mp4"},
    "wav": {"label": "WAV", "note": "Uncompressed, for editing", "mime": "audio/wav"},
}
e = lambda s: html.escape(str(s or ""), quote=True)
BRAND = '<span class="mcw"><span class="mcw-g">mAIn</span>Character</span>'


def md_inline(s):
    """**bold** only; everything else escaped."""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", e(s))


def iso_dur(sec):
    sec = int(round(sec)); return f"PT{sec//60}M{sec%60}S"


def clock(sec):
    sec = int(round(sec)); return f"{sec//60}:{sec%60:02d}"


def mb(n):
    return f"{n/1_000_000:.1f} MB"


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def transcode(src, dst, fmt, tags):
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    codec = {"mp3": ["-c:a", "libmp3lame", "-b:a", "192k", "-id3v2_version", "3"],
             "m4a": ["-c:a", "copy", "-movflags", "+faststart"] if src.suffix.lower() in (".m4a", ".mp4", ".aac")
                    else ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"],
             "wav": ["-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2"]}[fmt]
    meta = []
    for k, v in tags.items():
        meta += ["-metadata", f"{k}={v}"]
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-map_metadata", "-1", *codec, *meta, str(dst)], check=True)


def read_transcript(path, corrections=None):
    lines = []
    text = path.read_text(encoding="utf-8")
    for wrong, right in (corrections or {}).items():
        text = re.sub(r"\b" + re.escape(wrong) + r"(?=['’]?s?\b)", right, text)
    # Zero-based tools (speaker_0 / SPEAKER_00) shift up by one; one-based labels stay as they are.
    zero_based = re.search(r"^(?:Speaker|Character|SPEAKER)[ _]?0+\s*[:\-]", text, re.M | re.I) is not None
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        m = re.match(r"^(?:Speaker|Character)[ _]?(\d+)\s*[:\-]\s*(.*)$", raw, re.I)
        if m:
            lines.append((f"Character {int(m.group(1)) + (1 if zero_based else 0)}", m.group(2)))
        elif lines:
            lines[-1] = (lines[-1][0], lines[-1][1] + " " + raw)
        else:
            lines.append(("Character 1", raw))
    return lines


def transcript_files(site, pub, a, lines, url):
    head = [f"{a['title']} — transcript", "",
            f"Publication: {pub['title']} ({pub['date']})",
            f"Audio: {a['generator']}, {a.get('generator_format','')} format. AI-generated voices.",
            f"Transcript: {a.get('transcript_source', 'machine transcription')}, unedited. "
            + ("Single narrator, labeled Character 1." if a.get("voices") == 1 else
               "Speakers labeled Character 1, Character 2" + (" (turns assigned from the dialogue, not voice analysis)." if a.get("speaker_labels") == "text" else ".")),
            f"Source page: {url}"]
    for n in a.get("caveats", []) + a.get("notes", []):
        head.append(f"Note: {n}")
    if site.get("name_corrections"):
        head.append("Note: names misheard by the transcription tool were corrected to their proper spelling.")
    lic = [f"— {site['publisher']} · {site['publisher_url']}",
           f"Licensed {site['license_name']} ({site['license_plain']}) · {site['rights_url']}"]
    txt = "\n".join(["mAInCharacter", "=" * 13, ""] + head + ["", "-" * 60, ""] +
                    [f"{who}: {said}\n" for who, said in lines] + ["-" * 60] + lic) + "\n"
    md = "\n".join([f"# {a['title']}", "", f"**mAInCharacter** · transcript", ""] +
                   [f"> {h}  " for h in head[2:]] + ["", "---", ""] +
                   [f"**{who}:** {said}\n" for who, said in lines] + ["---", "", lic[0].replace(site['publisher_url'], f"<{site['publisher_url']}>"),
                   "", f"Licensed [{site['license_name']}]({site['license_url']}) ({site['license_plain']}) · <{site['rights_url']}>"]) + "\n"
    return txt, md


ICON_FILE = '<svg class="dl-i" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 2.5h8l4.5 4.5v14.5H6z"/><path d="M14 2.5V7h4.5"/><path d="M9 16v-3M11.5 17.5v-6M14 16v-3"/></svg>'
ICON_DOC = '<svg class="dl-i" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 2.5h8l4.5 4.5v14.5H6z"/><path d="M14 2.5V7h4.5"/><path d="M9 12h6M9 15h6M9 18h4"/></svg>'


def head_block(site, title, desc, canon, og_image, brand, jsonld, noindex, css_href, keywords=(), sonic=""):
    kw = f'<meta name="keywords" content="{e(", ".join(keywords))}">' if keywords else ""
    robots = '<meta name="robots" content="noindex">' if noindex else '<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">'
    return f"""<!doctype html>
<html lang="{e(site['language'])}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
{kw}
{robots}
<link rel="canonical" href="{e(canon)}">
<meta name="author" content="{e(site['author'])}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{e(site['site_name'])}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(canon)}">
<meta property="og:image" content="{e(og_image)}">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" type="image/svg+xml" href="{brand}/icon/mc-icon-stacked-gold.svg">
<link rel="apple-touch-icon" href="{brand}/icon/png/mc-icon-stacked-gold-on-black-1024.png">
<link rel="alternate" type="application/rss+xml" title="{e(site['site_name'])}" href="{e(site['site_url'])}/feed.xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,500;0,600;1,500&family=DM+Sans:wght@400;500;700&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{css_href}">
<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>
</head>
<body data-ga="{e(site.get('ga_measurement_id') or '')}" data-sonic="{e(sonic or '')}"{' data-sonic-auto="1"' if site.get('sonic_autoplay') else ''}>
<a class="skip-link" href="#main">Skip to content</a>
<div class="diplomatic-rule" aria-hidden="true"></div>
<div class="read-progress" id="readProgress" aria-hidden="true"></div>"""


def logo(brand, variant, cls, alt="mAInCharacter"):
    b = f"{brand}/header/mc-header-{variant}"
    return (f'<img class="{cls}" src="{b}-720.png" srcset="{b}-360.png 360w, {b}-720.png 720w, {b}-1200.png 1200w" '
            f'sizes="(max-width: 640px) 160px, 220px" width="720" height="250" alt="{alt}">')


def site_head(site, brand, home, nav):
    links = "".join(f'<a href="{e(h)}">{e(t)}</a>' for t, h in nav)
    return f"""
<header class="site-head" id="siteHead">
  <div class="sh-inner">
    <a class="sh-logo" href="{e(site['publisher_url'])}" aria-label="mAInCharacter — main-character.me">{logo(brand, 'dark', 'sh-lockup')}</a>
    <nav aria-label="Section navigation">{links}</nav>
    <div class="sh-cta"><a href="{e(site['calendly'])}" target="_blank" rel="noopener">Start the Conversation</a></div>
  </div>
</header>"""


def license_block(site):
    return (f'<p class="license">— {e(site["publisher"])} · <a href="{e(site["publisher_url"])}">{e(site["publisher_url"])}</a><br>'
            f'Licensed <a href="{e(site["license_url"])}" rel="license">{e(site["license_name"])}</a> ({e(site["license_plain"])}) · '
            f'<a href="{e(site["rights_url"])}">{e(site["rights_url"])}</a></p>')


def consent_bar(site):
    if not site.get("ga_measurement_id"):
        return ""
    return ('<div class="consent" id="consent" role="region" aria-label="Analytics choice" hidden>'
            '<p>This page can count plays and downloads with Google Analytics. No ads, no sale of data. '
            f'<a href="{e(site["rights_url"])}">Rights &amp; use</a>.</p>'
            '<div class="consent-btns"><button type="button" class="btn" data-consent="yes">Count me</button>'
            '<button type="button" class="btn ghost" data-consent="no">No thanks</button></div></div>')


def footer(site, brand, extra_links):
    row = '<span aria-hidden="true">·</span>'.join(f'<a href="{e(h)}" class="mcf-link">{e(t)}</a>' for t, h in extra_links)
    return f"""
<footer class="mc-footer" aria-label="Site footer">
  <div class="mcf-brand">
    <a href="{e(site['publisher_url'])}" class="mcf-logo-link" aria-label="mAInCharacter home">{logo(brand, 'light', 'mcf-logo')}</a>
    <p class="mcf-tagline">Career Intelligence · Advisory Services</p>
  </div>
  <nav class="mcf-nav" aria-label="Footer navigation">
    <a href="{e(site['publisher_url'])}" class="mcf-link">main-character.me</a>
    <div class="mcf-row">{row}</div>
    <p class="mcf-rights">© {dt.date.today().year} <a href="{e(site['publisher_url'])}" class="mcf-link">{e(site['publisher'])}</a>. Licensed <a href="{e(site['license_url'])}" class="mcf-link" rel="license">{e(site['license_name'])}</a>. <a href="{e(site['rights_url'])}" class="mcf-link">Rights &amp; use</a>.</p>
  </nav>
</footer>
{consent_bar(site)}
<button type="button" class="to-top" id="toTop" aria-label="Back to top" hidden><svg viewBox="0 0 15 25" aria-hidden="true"><path d="M7.5 2 L7.5 23 M2 8 L7.5 2 L13 8" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>"""


EXT = {"image/webp": ".webp", "image/png": ".png", "image/jpeg": ".jpg", "image/svg+xml": ".svg",
       "font/woff2": ".woff2", "font/woff": ".woff", "audio/mpeg": ".mp3"}


def unbundle(src, dest, note):
    """Unpack a standalone HTML export (manifest + template) into index.html plus its asset files."""
    import base64, gzip, json
    text = src.read_text(encoding="utf-8")
    def block(name):
        m = re.search(r'<script type="__bundler/' + name + r'"[^>]*>(.*?)</script>', text, re.S)
        if not m:
            sys.exit(f"{src.name}: not a standalone export (no {name} block)")
        return json.loads(m.group(1))
    manifest, html = block("manifest"), block("template")
    dest.mkdir(parents=True, exist_ok=True)
    for i, (uid, meta) in enumerate(manifest.items()):
        data = base64.b64decode(meta["data"])
        if meta.get("compressed"):
            data = gzip.decompress(data)
        name = f"asset-{i + 1}{EXT.get(meta['mime'], '.bin')}"
        (dest / name).write_bytes(data)
        html = html.replace(uid, name)
    html = html.replace("<title>", "<!-- " + note + " -->\n<title>", 1)
    (dest / "index.html").write_text(html, encoding="utf-8")


RATES = [0.75, 1, 1.25, 1.5, 1.75, 2, 2.25]
RATE_TICKS = "".join(f'<i data-r="{r}"></i>' for r in RATES)


def player(a, src_rel, label="Listen", brand="", home="https://main-character.me/", mark=False):
    """The audio pill. mark=True adds the gold mC icon (title card only; episode pills stay clean)."""
    mark_html = (f'\n  <a class="ao-mark" href="{e(home)}" aria-label="mAInCharacter — main-character.me"><img src="{brand}/icon/png/mc-icon-stacked-gold-transparent-2048.png" width="2048" height="2048" alt="" loading="lazy"></a>') if mark else ""
    return f"""<div class="ao-wrap"><div class="ao" role="group" aria-label="Audio: {e(a['title'])}" data-title="{e(a['title'])}">
  <button type="button" class="ao-play" aria-pressed="false" aria-label="Play {e(a['title'])}"><svg class="ao-i-play" viewBox="0 0 24 24" aria-hidden="true"><polygon points="7 4 20 12 7 20 7 4"/></svg><svg class="ao-i-pause" viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="4" width="4.5" height="16" rx="1"/><rect x="13.5" y="4" width="4.5" height="16" rx="1"/></svg></button>
  <span class="ao-wave" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></span>
  <span class="ao-meta"><span class="ao-k">{e(label)}</span><span class="ao-t"><span class="ao-time-current">0:00</span><span class="ao-sep">/</span><span class="ao-time-duration">{clock(a['_dur'])}</span></span></span>
  <input type="range" class="ao-seek" min="0" max="{a['_dur']:.1f}" value="0" step="0.1" aria-label="Seek">
  <div class="ao-dial" role="group" aria-label="Playback speed">
    <button type="button" class="ao-step" data-dir="-1" aria-label="Slower">&#8211;</button>
    <span class="ao-dial-box"><output class="ao-rate-v" aria-live="polite">1.00×</output><span class="ao-ticks" aria-hidden="true">{RATE_TICKS}</span></span>
    <button type="button" class="ao-step" data-dir="1" aria-label="Faster">+</button>
  </div>{mark_html}
  <audio preload="none"><source src="{e(src_rel)}" type="audio/mpeg"></audio>
</div></div>"""


def build(args):
    site = yaml.safe_load((ROOT / "site.yml").read_text(encoding="utf-8"))
    if args.site_url:
        site["site_url"] = args.site_url
    site["site_url"] = site["site_url"].rstrip("/")
    cd = (site.get("custom_domain") or "").strip()
    if cd and site["site_url"] != f"https://{cd}" and not args.site_url:
        sys.exit(f"site.yml: custom_domain is {cd} but site_url is {site['site_url']}. Set site_url: https://{cd} in the same commit.")
    brand = (args.brand_local or site["brand_base"]).rstrip("/")
    out = ROOT / args.out
    def place_media(ref, dest_dir, rel_prefix):
        """A URL passes through; a repo path is copied into the site and returned as a relative URL."""
        if not ref:
            return ""
        if re.match(r"^https?://", ref):
            return ref
        src = ROOT / ref
        if not src.exists():
            sys.exit(f"Media file not found: {ref}")
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dest_dir / src.name)
        return f"{rel_prefix}{src.name}"
    if out.exists():
        # keep transcoded audio between local runs; rebuild everything else
        for p in out.iterdir():
            if p.is_dir() and (p / "audio").exists():
                for q in p.iterdir():
                    if q.name != "audio":
                        shutil.rmtree(q) if q.is_dir() else q.unlink()
            elif p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
    out.mkdir(parents=True, exist_ok=True)
    (out / "assets").mkdir(exist_ok=True)
    for f in ("styles.css", "script.js"):
        shutil.copy(HERE / f, out / "assets" / f)
    sref = site.get("sonic_log")
    if sref and not re.match(r"^https?://", sref) and not (ROOT / sref).exists():
        print(f"Warning: sonic logo {sref} not found (the workflow renders it from tools/audio-site/sonic). Building without it.")
        sref = ""
    site["_sonic_root"] = place_media(sref, out / "assets", "assets/")   # from the index
    arc = (site.get("arcbox") or "").strip()
    site["_arcbox"] = False
    if arc:
        if not (ROOT / arc).exists():
            sys.exit(f"site.yml: arcbox export not found: {arc}")
        unbundle(ROOT / arc, out / "assets" / "arcbox",
                 "Built from " + Path(arc).name + " (the canonical mC Arc Box export) by tools/audio-site/build.py. "
                 "Only the packaging changed: its image and fonts are separate files. Change the Arc Box in its master and re-export.")
        site["_arcbox"] = True
    site["_sonic_sub"] = ("../" + site["_sonic_root"]) if site["_sonic_root"] and not site["_sonic_root"].startswith("http") else site["_sonic_root"]

    pubs = []
    for yml in sorted((ROOT / "articles").glob("*/audio.yml")):
        if any(part.startswith("_") for part in yml.relative_to(ROOT).parts):
            continue
        pub = yaml.safe_load(yml.read_text(encoding="utf-8"))
        pub["date"] = str(pub["date"])
        if pub.get("status") not in ("published", "draft", "archived"):
            sys.exit(f"{yml.relative_to(ROOT)}: status must be published, draft or archived (got {pub.get('status')!r})")
        if pub["status"] == "archived":
            continue
        pub["_dir"] = yml.parent
        missing = [k for k in ("slug", "date", "title", "description", "badge", "audio") if not pub.get(k)]
        for i, a in enumerate(pub.get("audio") or []):
            missing += [f"audio[{i}].{k}" for k in ("id", "title", "master", "generator", "summary") if not a.get(k)]
        if missing:
            sys.exit(f"{yml.relative_to(ROOT)}: missing required field(s): {', '.join(missing)}")
        if pub["slug"] != yml.parent.name:
            sys.exit(f"{yml.relative_to(ROOT)}: slug '{pub['slug']}' must match its folder name '{yml.parent.name}'")
        pubs.append(pub)
    pubs.sort(key=lambda p: p["date"], reverse=True)
    keep = {p["slug"] for p in pubs} | {"assets"}
    for d in list(out.iterdir()):
        if d.is_dir() and d.name not in keep:
            shutil.rmtree(d)   # archived or removed publications leave the site, including cached audio

    registry, feed_items, sitemap = [], [], [f"{site['site_url']}/"]
    llms = [f"# {site['site_name']}", "", f"> {site['tagline']} Audio companions by {site['author']}, {site['publisher']}. "
            f"Each page has a listener summary, corrections, references and a full transcript. Licensed {site['license_name']}.", "",
            f"Master registry of all mAInCharacter publications: {site['registry_url']}", "", "## Publications", ""]

    for pub in pubs:
        slug, pdir = pub["slug"], out / pub["slug"]
        url = f"{site['site_url']}/{slug}/"
        draft = pub.get("status") == "draft"
        expected = {f"mC_{slug}_{a['id']}.{fmt}" for a in pub["audio"] for fmt in site["formats"]}
        if (pdir / "audio").exists():
            for f in (pdir / "audio").iterdir():
                if f.name not in expected:
                    f.unlink()   # removed format, renamed or deleted episode
        shutil.rmtree(pdir / "transcripts", ignore_errors=True)
        (pdir / "transcripts").mkdir(parents=True, exist_ok=True)
        shutil.rmtree(pdir / "media", ignore_errors=True)
        pub["_hero_art"] = place_media(pub.get("hero_art"), pdir / "media", "media/")
        for a in pub["audio"]:
            src = ROOT / a["master"]
            if not src.exists():
                sys.exit(f"Missing master audio for {slug}/{a['id']}: {a['master']}")
            a["_dur"] = probe(src)
            base = f"mC_{slug}_{a['id']}"
            tags = {"title": a["title"], "artist": "mAInCharacter", "album": pub.get("series") or pub["title"],
                    "date": pub["date"][:4],
                    "copyright": f"© {pub['date'][:4]} {site['publisher']} · {site['license_name']} · {site['rights_url']}",
                    "comment": f"AI-generated audio ({a['generator']}, {a.get('generator_format','')}). Source and license: {url}"}
            a["_files"] = {}
            for fmt in site["formats"]:
                dst = pdir / "audio" / f"{base}.{fmt}"
                if not args.no_audio:
                    transcode(src, dst, fmt, tags)
                a["_files"][fmt] = (f"audio/{base}.{fmt}", dst.stat().st_size if dst.exists() else 0)
            tpath = pub["_dir"] / "transcripts" / f"{a['id']}.txt"
            a["_transcript"] = read_transcript(tpath, site.get("name_corrections")) if tpath.exists() else []
            if a["_transcript"]:
                txt, md = transcript_files(site, pub, a, a["_transcript"], url)
                (pdir / "transcripts" / f"{base}_transcript.txt").write_text(txt, encoding="utf-8")
                (pdir / "transcripts" / f"{base}_transcript.md").write_text(md, encoding="utf-8")
                a["_tfiles"] = {"md": f"transcripts/{base}_transcript.md", "txt": f"transcripts/{base}_transcript.txt"}
        render_publication(site, brand, pub, pdir, url, draft)
        if draft:
            continue
        sitemap.append(url)
        registry.append({"slug": slug, "date": pub["date"], "title": pub["title"], "series": pub.get("series"),
                         "description": pub["description"], "url": url, "article": pub.get("canonical_article"),
                         "audio": [{"id": a["id"], "title": a["title"], "kind": a.get("kind"), "duration": clock(a["_dur"]),
                                    "generator": a["generator"], "format": a.get("generator_format"),
                                    "summary": a["summary"], "url": f"{url}#{a['id']}",
                                    "downloads": {k: f"{url}{v[0]}" for k, v in a["_files"].items()},
                                    "transcripts": {k: f"{url}{v}" for k, v in a.get("_tfiles", {}).items()}} for a in pub["audio"]]})
        llms.append(f"- [{pub['title']}]({url}) ({pub['date']}): {pub['description']}")
        for a in pub["audio"]:
            llms.append(f"  - [{a['title']}]({url}#{a['id']}): {a['summary']}"
                        + (f" Transcript: {url}{a['_tfiles']['md']}" if a.get("_tfiles") else ""))
            feed_items.append((pub, a, url))

    render_index(site, brand, pubs, out)
    write_feeds(site, brand, out, registry, feed_items, sitemap, llms)
    if site.get("custom_domain"):
        (out / "CNAME").write_text(site["custom_domain"].strip() + "\n")
    (out / ".nojekyll").write_text("")
    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    budget = int(site.get("size_budget_mb", 750)) * 1_000_000
    print(f"Site size: {total/1e6:.0f} MB of {budget/1e6:.0f} MB budget")
    if total > budget:
        sys.exit("Site is over its size budget. Remove wav from formats in site.yml, or archive old publications.")
    print(f"Built {len(pubs)} publication(s), {sum(len(p['audio']) for p in pubs)} audio item(s) -> {out}")


def jsonld_publication(site, brand, pub, url):
    org = {"@type": "Organization", "@id": f"{site['publisher_url']}#org", "name": site["publisher"], "url": site["publisher_url"],
           "logo": f"{brand}/icon/png/mc-icon-stacked-gold-on-black-1024.png", "sameAs": site.get("same_as", [])}
    person = {"@type": "Person", "@id": f"{site['publisher_url']}#beto", "name": site["author"], "worksFor": {"@id": org["@id"]}}
    eps = []
    for a in pub["audio"]:
        eps.append({"@type": "PodcastEpisode", "@id": f"{url}#{a['id']}", "url": f"{url}#{a['id']}", "name": a["title"], "alternateName": a.get("file_title"),
                    "description": a["summary"], "datePublished": pub["date"], "inLanguage": site["language"],
                    "timeRequired": iso_dur(a["_dur"]), "author": {"@id": person["@id"]}, "publisher": {"@id": org["@id"]},
                    "copyrightHolder": {"@id": org["@id"]}, "license": site["license_url"],
                    "creditText": f"{site['publisher']}, {site['publisher_url']}",
                    "isBasedOn": pub.get("canonical_article"),
                    "partOfSeries": {"@type": "PodcastSeries", "name": site["site_name"], "url": site["site_url"] + "/"},
                    "associatedMedia": [{"@type": "AudioObject", "name": f"{a['title']} ({FMT[k]['label']})",
                                         "contentUrl": f"{url}{v[0]}", "encodingFormat": FMT[k]["mime"],
                                         "duration": iso_dur(a["_dur"]), "contentSize": mb(v[1])} for k, v in a["_files"].items()],
                    "transcript": " ".join(f"{w}: {s}" for w, s in a["_transcript"])[:5000] if a["_transcript"] else None,
                    "sdPublisher": {"@id": org["@id"]},
                    "abstract": f"AI-generated audio made with {a['generator']} ({a.get('generator_format','')})."})
    graph = [org, person,
             {"@type": "WebPage", "@id": url, "url": url, "name": pub["title"], "description": pub["description"],
              "inLanguage": site["language"], "datePublished": pub["date"], "isPartOf": {"@type": "WebSite", "name": site["site_name"], "url": site["site_url"] + "/"},
              "about": pub.get("keywords", []), "license": site["license_url"], "publisher": {"@id": org["@id"]},
              "primaryImageOfPage": f"{brand}/favicon/og-image-1200x630.png",
              "breadcrumb": {"@type": "BreadcrumbList", "itemListElement": [
                  {"@type": "ListItem", "position": 1, "name": "Audio", "item": site["site_url"] + "/"},
                  {"@type": "ListItem", "position": 2, "name": pub["title"], "item": url}]}},
             *eps]
    if pub.get("questions"):
        graph.append({"@type": "FAQPage", "@id": f"{url}#questions", "mainEntity": [
            {"@type": "Question", "name": q["q"], "acceptedAnswer": {"@type": "Answer", "text": q["a"]}} for q in pub["questions"]]})
    return {"@context": "https://schema.org", "@graph": graph}


def title_html(pub):
    t, acc = pub["title"], pub.get("title_accent")
    if acc and t.endswith(acc):
        return f'{e(t[:-len(acc)].rstrip())} <span class="accent">{e(acc)}</span>'
    return e(t)


def hero_art(site, pub):
    """Top-right of the title card: a publication image if set, else the site's Arc Box."""
    if pub.get("_hero_art"):
        return (f'<figure class="hero-art"><img src="{e(pub["_hero_art"])}" alt="{e(pub.get("hero_art_alt") or "")}" '
                'loading="eager" decoding="async"></figure>')
    if site.get("_arcbox") and pub.get("arcbox", True) is not False:
        return ('<div class="hero-art hero-arc" aria-hidden="true"><iframe src="../assets/arcbox/index.html" '
                'title="mAInCharacter Arc Box" tabindex="-1" loading="lazy"></iframe></div>')
    return ""


def render_publication(site, brand, pub, pdir, url, draft):
    first = pub["audio"][0]
    art = hero_art(site, pub)
    th = pub.get("thesis") or {}
    nav = ([("Thesis", "#thesis")] if th else []) + [(a.get("nav") or a.get("generator_format") or a["title"], f"#{a['id']}") for a in pub["audio"]] + [("All audio", "../")]
    parts = [head_block(site, f"{pub['title']} — {site['site_name']} | mAInCharacter", pub["description"], url,
                        f"{brand}/favicon/og-image-1200x630.png", brand, jsonld_publication(site, brand, pub, url), draft,
                        "../assets/styles.css", pub.get("keywords", []), site["_sonic_sub"]),
             site_head(site, brand, "../", nav), '<main class="wrap" id="main">',
             f"""<div class="hero{' has-art' if art else ''}">
  {art}
  <div class="hero-text">
    <div class="hero-logo"><a href="{e(site['publisher_url'])}" aria-label="mAInCharacter home">{logo(brand, 'dark', 'mc-lockup')}</a></div>
    <nav class="crumbs" aria-label="Breadcrumb"><a href="../">Audio</a> <span aria-hidden="true">/</span> <span>{e(pub.get('series') or pub['title'])}</span></nav>
    <span class="badge">{e(pub['badge'])}</span>
    <h1>{title_html(pub)}</h1>
    <p class="deck">{e(pub.get('deck'))}</p>
    {f'<p class="deck define">{md_inline(pub["define"])}</p>' if pub.get('define') else ''}
    {player(first, first['_files']['mp3'][0], 'Listen · ' + first.get('generator_format', ''), brand, site['publisher_url'], mark=True)}
    <div class="byline"><span>By<strong>{e(site['author'])} · {BRAND}</strong></span><span>Published<strong><time datetime="{e(pub['date'])}">{dt.date.fromisoformat(pub['date']).strftime('%B %-d, %Y')}</time></strong></span><span>Form<strong>Audio · {len(pub['audio'])} episode{'s' if len(pub['audio']) != 1 else ''}</strong></span></div>
    {f'<a class="back" href="{e(pub["canonical_article"])}">Read the full article →</a>' if pub.get('canonical_article') else ''}
  </div>
</div>"""]
    n = 0
    if th:
        n += 1
        steps = "".join(f'<div><p class="k">{e(s["k"])}</p><h3>{e(s["h"])}</h3><p>{e(s["p"])}</p></div>' for s in th.get("steps", []))
        ideas = "".join(f'<li><div><strong>{e(i["t"])}</strong> {e(i["p"])}</div></li>' for i in th.get("ideas", []))
        parts.append(f"""<section class="episode episode--featured" id="thesis">
  <div class="section-header"><div class="section-number">{n:02d}</div><div><span class="sh-eyebrow">{e(th.get('eyebrow'))}</span><h2>{e(th.get('heading'))}</h2></div></div>
  <div class="prose"><p class="lead">{e(th.get('lead'))}</p><p>{e(th.get('body'))}</p></div>
  {f'<div class="wedge">{steps}</div>' if steps else ''}
  {f'<div class="idea-panel"><p class="eyebrow">{e(th.get("ideas_label"))}</p><ol>{ideas}</ol></div>' if ideas else ''}
  {f'<blockquote class="pull"><p>{e(th["pull"])}</p><cite>{e(th.get("pull_cite"))}</cite></blockquote>' if th.get('pull') else ''}
  {f'<div class="path-note"><span class="rule" aria-hidden="true"></span><p><em>{e(th["closing_line"])}</em></p></div>' if th.get('closing_line') else ''}
</section>""")
    for a in pub["audio"]:
        n += 1
        dls = "".join(f'<a class="dl" href="{e(rel)}" download data-track="download" data-format="{k}" data-title="{e(a["title"])}"><span class="dl-badge">{ICON_FILE}<b>{FMT[k]["label"]}</b></span><span class="dl-size">{mb(size)}</span><span class="sr">{FMT[k]["note"]}</span></a>'
                      for k, (rel, size) in a["_files"].items())
        tdl = "".join(f'<a class="dl dl--doc" href="{e(rel)}" download data-track="transcript_download" data-format="{k}" data-title="{e(a["title"])}"><span class="dl-badge">{ICON_DOC}<b>{k.upper()}</b></span><span class="dl-size">{"Markdown" if k == "md" else "Plain text"}</span></a>'
                      for k, rel in a.get("_tfiles", {}).items())
        quotes = "".join(f'<li><span class="q-mark" aria-hidden="true">“</span>{e(q)}</li>' for q in (a.get("quotes") or [])[:3])
        refs = "".join(f'<li><a href="{e(r["url"])}">{e(r["label"])}</a></li>' for r in a.get("references", []))
        tnote = e(a.get("transcript_source", "machine transcription")) + " · " + ("single narrator" if a.get("voices") == 1 else "speakers labeled Character 1, Character 2")
        lines = "".join(f'<p><b class="who w{w.split()[-1]}">{e(w)}</b> {e(s_)}</p>' for w, s_ in a["_transcript"])
        parts.append(f"""<section class="episode" id="{e(a['id'])}">
  <div class="section-header"><div class="section-number">{n:02d}</div><div><span class="sh-eyebrow">{e(a.get('kind'))} · {clock(a['_dur'])}</span><h2>{e(a['title'])}</h2></div></div>
  <p class="summary-p">{e(a['summary'])}</p>
  <div class="ep-grid">
    <div class="ep-main">
      {player(a, a['_files']['mp3'][0], 'Listen', brand, site['publisher_url'])}
      {f'<p class="listen-for"><span>Listen for</span>{e(a["listen_for"])}</p>' if a.get('listen_for') else ''}
      {f'<div class="quotes"><p class="eyebrow">Key quotes</p><ul>{quotes}</ul></div>' if quotes else ''}
    </div>
    <aside class="ep-side" aria-label="Downloads">
      <p class="eyebrow">Audio</p><div class="dl-list">{dls}</div>
      {f'<p class="eyebrow">Transcript</p><div class="dl-list">{tdl}</div>' if tdl else ''}
      <dl class="ep-meta"><div><dt>Made with</dt><dd>{e(a['generator'])}</dd></div><div><dt>Voices</dt><dd>{a.get('voices', '')} AI</dd></div></dl>
    </aside>
  </div>
  {f'<div class="t-reveal" data-reveal="transcript"><div class="t-head-row"><button type="button" class="t-head" aria-expanded="false" aria-controls="t-{e(a["id"])}"><span class="t-label">Transcript</span><span class="t-sub">{tnote}</span><span class="dn-cue" aria-hidden="true">+</span><span class="t-cue-l">Full transcript</span></button><button type="button" class="t-copy" data-copy="t-{e(a["id"])}" data-title="{e(a["title"])}" aria-label="Copy the full transcript">Copy</button></div><div class="t-body" id="t-{e(a["id"])}">{lines}</div></div>' if lines else ''}
  {f'<div class="refs"><p class="eyebrow">References</p><ul>{refs}</ul></div>' if refs else ''}
  <p class="attrib">AI-generated audio: {e(a['generator'])}, {e(a.get('generator_format'))} format. Voices are synthetic and may contain errors. Written summary, title and notes by {BRAND}.</p>
</section>""")
    if pub.get("questions"):
        def qa_item(q):
            src = f' <a class="qa-src" href="{e(q["source"])}">In the article →</a>' if q.get("source") else ""
            return f'<div class="qa-item"><dt>{e(q["q"])}</dt><dd>{e(q["a"])}{src}</dd></div>'
        qa = "".join(qa_item(q) for q in pub["questions"])
        parts.append(f'<section class="qa" id="questions"><p class="eyebrow">Short answers</p><h2>Questions this publication answers</h2><dl>{qa}</dl></section>')
    parts.append(closing(site))
    parts.append(f'<div class="colophon">{e(site["author"])} · {BRAND} · {e(pub.get("series") or "")} · {dt.date.fromisoformat(pub["date"]).strftime("%B %Y")}{license_block(site)}</div></main>')
    parts.append(footer(site, brand, [("All audio", "../"), ("Master registry", site["registry_url"]), ("Book a Briefing", site["calendly"])]))
    parts.append('<script src="../assets/script.js"></script>\n</body>\n</html>')
    (pdir / "index.html").write_text("\n".join(parts), encoding="utf-8")


def closing(site):
    return f"""<section class="closing">
  <div><p class="eyebrow">Next step</p><h2>Make the next <span class="accent">step</span> yours.</h2>
  <p>{BRAND} helps experienced professionals turn expertise into a clearer next move.</p><p class="sig">— Beto</p></div>
  <aside><p class="k">The Briefing</p><h3>30 minutes, free</h3><p>A first conversation about where you are and what comes next.</p>
  <a class="btn" href="{e(site['calendly'])}" target="_blank" rel="noopener">Start the Conversation</a></aside>
</section>"""


def render_index(site, brand, pubs, out):
    listed = [p for p in pubs if p.get("status") != "draft"]
    url = site["site_url"] + "/"
    items = []
    for p in listed:
        eps = "".join(f'<li><a href="{e(p["slug"])}/#{e(a["id"])}">{e(a["title"])}</a><span>{e(a.get("generator_format"))} · {clock(a["_dur"])}</span></li>' for a in p["audio"])
        items.append(f"""<article class="reg">
  <p class="reg-date"><time datetime="{e(p['date'])}">{e(p['date'])}</time> · {e(p.get('series') or '')}</p>
  <h2><a href="{e(p['slug'])}/">{e(p['title'])}</a></h2>
  <p>{e(p['description'])}</p>
  <ul class="reg-eps">{eps}</ul>
  <a class="btn" href="{e(p['slug'])}/">Open the episodes</a>
</article>""")
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": site["site_name"], "url": url, "description": site["tagline"],
          "publisher": {"@type": "Organization", "name": site["publisher"], "url": site["publisher_url"]}, "license": site["license_url"],
          "mainEntity": {"@type": "ItemList", "itemListElement": [{"@type": "ListItem", "position": i + 1, "url": f"{url}{p['slug']}/", "name": p["title"]} for i, p in enumerate(listed)]}}
    html_ = [head_block(site, f"{site['site_name']} | mAInCharacter", site["tagline"] + " Audio companions by Beto Cruz.", url,
                        f"{brand}/favicon/og-image-1200x630.png", brand, ld, False, "assets/styles.css", (), site["_sonic_root"]),
             site_head(site, brand, "./", [("Episodes", "#registry"), ("main-character.me", site["publisher_url"])]),
             f"""<main class="wrap" id="main">
<div class="hero"><div class="hero-text">
  <div class="hero-logo"><a href="{e(site['publisher_url'])}" aria-label="mAInCharacter home">{logo(brand, 'dark', 'mc-lockup')}</a></div>
  <span class="badge">Audio</span>
  <h1>Audio <span class="accent">companions</span></h1>
  <p class="deck">{e(site['tagline'])}</p>
  <div class="byline"><span>By<strong>{e(site['author'])}</strong></span><span>Publications<strong>{len(listed)}</strong></span><span>Episodes<strong>{sum(len(p['audio']) for p in listed)}</strong></span></div>
  <a class="back" href="{e(site['registry_url'])}">Every publication, in the master registry →</a>
</div></div>
<section id="registry" class="registry"><div class="section-header"><div class="section-number">≡</div><div><span class="sh-eyebrow">Newest first</span><h2>All audio</h2></div></div>{''.join(items)}</section>
{closing(site)}
<div class="colophon">{e(site['author'])} · {BRAND} · Audio{license_block(site)}</div>
</main>""",
             footer(site, brand, [("Master registry", site["registry_url"]), ("RSS feed", "feed.xml"), ("Book a Briefing", site["calendly"])]),
             '<script src="assets/script.js"></script>\n</body>\n</html>']
    (out / "index.html").write_text("\n".join(html_), encoding="utf-8")


def write_feeds(site, brand, out, registry, feed_items, sitemap, llms):
    (out / "registry.json").write_text(json.dumps({"generated": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "site": site["site_url"] + "/", "publisher": site["publisher"], "license": site["license_url"], "publications": registry},
        indent=2, ensure_ascii=False), encoding="utf-8")
    x = lambda s: html.escape(str(s or ""), quote=False)
    items = []
    for pub, a, url in feed_items:
        mp3, size = a["_files"]["mp3"]
        d = dt.datetime.fromisoformat(pub["date"] + "T12:00:00+00:00").strftime("%a, %d %b %Y %H:%M:%S +0000")
        tr = f'<podcast:transcript url="{x(url + a["_tfiles"]["txt"])}" type="text/plain"/>' if a.get("_tfiles") else ""
        items.append(f"""<item><title>{x(a['title'])}</title><link>{x(url)}#{x(a['id'])}</link><guid isPermaLink="false">{x(pub['slug'])}/{x(a['id'])}</guid>
<pubDate>{d}</pubDate><description>{x(a['summary'] + ' AI-generated audio: ' + a['generator'] + '.')}</description>
<enclosure url="{x(url + mp3)}" length="{size}" type="audio/mpeg"/><itunes:duration>{int(a['_dur'])}</itunes:duration><itunes:explicit>false</itunes:explicit>{tr}</item>""")
    (out / "feed.xml").write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:podcast="https://podcastindex.org/namespace/1.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel><title>{x(site['site_name'])}</title><link>{x(site['site_url'])}/</link><atom:link href="{x(site['site_url'])}/feed.xml" rel="self" type="application/rss+xml"/>
<description>{x(site['tagline'])}</description><language>{x(site['language'])}</language><copyright>{x(site['publisher'] + ' · ' + site['license_name'])}</copyright>
<itunes:author>{x(site['author'])}</itunes:author><itunes:explicit>false</itunes:explicit><itunes:image href="{x(brand)}/icon/png/mc-icon-stacked-gold-on-black-1024.png"/><image><url>{x(brand)}/icon/png/mc-icon-stacked-gold-on-black-1024.png</url><title>{x(site["site_name"])}</title><link>{x(site["site_url"])}/</link></image>
{''.join(items)}
</channel></rss>
""", encoding="utf-8")
    today = dt.date.today().isoformat()
    (out / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"<url><loc>{x(u)}</loc><lastmod>{today}</lastmod></url>\n" for u in sitemap) + "</urlset>\n", encoding="utf-8")
    search_bots = ["OAI-SearchBot", "ChatGPT-User", "PerplexityBot", "Perplexity-User", "Claude-SearchBot", "Claude-User", "Bingbot", "Googlebot", "DuckAssistBot"]
    training_bots = ["GPTBot", "Google-Extended", "ClaudeBot", "CCBot", "Applebot-Extended", "Meta-ExternalAgent", "Bytespider"]
    rules = ["# mAInCharacter Audio. Answer and search engines welcome; see llms.txt."]
    rules += [f"User-agent: {b}\nAllow: /\n" for b in search_bots]
    if site.get("ai_training_crawlers", "block") == "block":
        rules += [f"User-agent: {b}\nDisallow: /\n" for b in training_bots]
    rules += ["User-agent: *\nAllow: /\n", f"Sitemap: {site['site_url']}/sitemap.xml"]
    (out / "robots.txt").write_text("\n".join(rules) + "\n", encoding="utf-8")
    llms += ["", "## Machine-readable", "", f"- Registry feed: {site['site_url']}/registry.json", f"- Podcast RSS: {site['site_url']}/feed.xml", "",
             "## License", "", f"— {site['publisher']} · {site['publisher_url']}",
             f"Licensed {site['license_name']} ({site['license_plain']}) · {site['rights_url']}", ""]
    (out / "llms.txt").write_text("\n".join(llms), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="_site")
    ap.add_argument("--brand-local", help="serve brand files from a local folder (preview/QA only)")
    ap.add_argument("--site-url")
    ap.add_argument("--no-audio", action="store_true", help="skip transcoding (fast preview)")
    build(ap.parse_args())
