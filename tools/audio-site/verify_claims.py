#!/usr/bin/env python3
"""Check every claim on the audio pages against its source before it goes out.

Pattern: TypeSafe citation check (docs.typesafe.ai/cookbooks/citation_check).
  1. Key Quotes are matched word for word against the episode transcript. No model.
     Not found = "not in audio".
  2. Summaries, "Listen for" lines and short answers are judged by TypeSafe Jev with one
     Choice question: does the source support, contradict, or say nothing about the claim?
     Summaries and "Listen for" are checked against the transcript; short answers against
     the article section their `source` link points to.
  3. Verdicts at or above AUTO_ACCEPT confidence stand; lower ones are flagged for a person.

Jev runs only when TYPESAFE_API_KEY is set (a GitHub Actions secret). Without it, step 1 still
runs and step 2 is reported as skipped. The report goes to the Actions run summary.
By default it never blocks publishing; `--strict` fails the run on "not in audio",
"contradicted" or an unreachable source.

Usage: python tools/audio-site/verify_claims.py [--strict]
"""
import html, json, os, re, sys, urllib.request, urllib.error
from pathlib import Path
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
API = "https://api.typesafe.ai/v1/systemone"
AUTO_ACCEPT = 0.8
QUESTION = {
    "relation": {
        "type": "choice",
        "instructions": "How does the section relate to the claim?",
        "criteria": {
            "supports": "The section states the claim or directly implies that it is true",
            "contradicts": "The section states the opposite of the claim or implies it is false",
            "says_nothing": "The section does not address what the claim asserts, either way",
        },
    }
}
VERDICT = {"supports": "verified", "contradicts": "contradicted", "says_nothing": "unsupported"}


def norm(t):
    t = html.unescape(t or "")
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = t.replace("—", "-").replace("–", "-")
    return re.sub(r"\s+", " ", t).strip().lower()


def transcript_text(path):
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = re.sub(r"^\s*(Speaker|Character)\s*\d+\s*:\s*", "", line)
        if line.strip():
            lines.append(line.strip())
    return " ".join(lines)


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"“])", text or "") if len(s.strip()) > 20]


_pages = {}


def section_text(url):
    """Fetch an article page once and return the text under the #anchor (or the whole page)."""
    base, _, anchor = url.partition("#")
    if base not in _pages:
        try:
            req = urllib.request.Request(base, headers={"User-Agent": "mC-audio-verify/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                _pages[base] = r.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            _pages[base] = e
    page = _pages[base]
    if isinstance(page, Exception):
        return None, f"source unreachable ({getattr(page, 'code', '') or type(page).__name__})"
    chunk = page
    if anchor:
        m = re.search(r'id=["\']' + re.escape(anchor) + r'["\']', page)
        if not m:
            return None, f"anchor #{anchor} not found"
        chunk = page[m.start():]
        nxt = re.search(r"<(section|article)\b|<h[12]\b", chunk[200:])
        chunk = chunk[: 200 + nxt.start()] if nxt else chunk[:20000]
    chunk = re.sub(r"(?is)<(script|style).*?</\1>", " ", chunk)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", chunk))).strip()[:60000], ""


def jev(claim, section, key):
    body = json.dumps({"model": "jev-latest", "state": {"claim": claim, "section": section},
                       "questions": QUESTION}).encode()
    req = urllib.request.Request(API, data=body, method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        a = json.load(r)["answers"]["relation"]
    return a["choice"], float(a.get("confidence", 0))


def main():
    strict = "--strict" in sys.argv
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    rows = []
    for yml in sorted((ROOT / "articles").glob("*/audio.yml")):
        if any(p.startswith("_") for p in yml.relative_to(ROOT).parts):
            continue
        pub = yaml.safe_load(yml.read_text(encoding="utf-8"))
        if pub.get("status") == "archived":
            continue
        checks = []   # (where, kind, claim, source_text or None, note)
        for a in pub.get("audio", []):
            tp = yml.parent / "transcripts" / f"{a['id']}.txt"
            tx = transcript_text(tp) if tp.exists() else None
            for q in a.get("quotes") or []:
                found = tx is not None and norm(q) in norm(tx)
                verdict = "verified" if found else ("no transcript" if tx is None else "not in audio")
                rows.append((pub["slug"], a["id"], "quote", q, verdict, "", "word-for-word match"))
            items = [("summary", s) for s in sentences(a.get("summary"))]
            items += [("listen for", a["listen_for"])] if a.get("listen_for") else []
            for kind, s in items:
                checks.append((a["id"], kind, s, tx, "" if tx else "no transcript"))
        for q in pub.get("questions") or []:
            src, note = section_text(q["source"]) if q.get("source") else (None, "no source link")
            checks.append(("short answers", "answer", f"{q['q']} {q['a']}", src, note))
        for where, kind, claim, src, note in checks:
            if src is None:
                rows.append((pub["slug"], where, kind, claim, "source missing", "", note))
            elif not key:
                rows.append((pub["slug"], where, kind, claim, "skipped", "", "no TYPESAFE_API_KEY"))
            else:
                try:
                    choice, conf = jev(claim, src, key)
                    v = VERDICT.get(choice, choice)
                    flag = "" if conf >= AUTO_ACCEPT else "needs a person"
                    rows.append((pub["slug"], where, kind, claim, v, f"{conf:.2f}", flag))
                except Exception as e:  # service or network failure: report, never guess
                    rows.append((pub["slug"], where, kind, claim, "check failed", "", type(e).__name__))
    out = ["## Claim check (TypeSafe Jev)", "",
           f"Jev: {'on' if key else 'off — add the TYPESAFE_API_KEY secret to turn it on'}. "
           f"Auto-accept at confidence {AUTO_ACCEPT}.", "",
           "| Page | Item | Kind | Claim | Verdict | Confidence | Note |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        claim = r[3] if len(r[3]) <= 110 else r[3][:107] + "…"
        out.append("| " + " | ".join([r[0], r[1], r[2], claim.replace("|", "/"), r[4], r[5], r[6]]) + " |")
    report = "\n".join(out) + "\n"
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(report)
    print(report)
    bad = [r for r in rows if r[4] in ("not in audio", "contradicted", "source missing")]
    print(f"{len(rows)} checks, {len(bad)} to fix.")
    sys.exit(1 if strict and bad else 0)


if __name__ == "__main__":
    main()
