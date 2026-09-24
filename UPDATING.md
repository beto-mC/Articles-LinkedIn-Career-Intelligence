# Updating the audio site

For Beto and the mC team. Not published on the site.

**The rule:** one article folder = one page. Add a folder, commit, and GitHub builds and publishes it. You never edit HTML.

## Add a new publication (about 10 minutes)

1. **Make the audio** in Gemini Notebook. Download it (`.m4a`).
2. **Make a folder** named for the date and topic: `articles/2026-10-05-your-topic/`
3. **Put the audio in it.** Any name works. Upload with GitHub's *Add file → Upload files*.
4. **Copy the form.** Copy `articles/_template/audio.yml` into your folder and fill it in.
   - `slug` must match the folder name exactly.
   - Keep `status: draft` while you check it. Change to `published` when ready.
   - Write the summary yourself or ask Claude. Every claim must come from the article, the audio, or a linked source.
   - Put anything wrong or unverified in the audio under `caveats:` (a figure you cannot source, an invented persona). Misspelled names go in `name_corrections` in site.yml.
   - `title` is what the audio is *about*, written from its opening minute — not the export file name. Keep the file name in `file_title`.
   - `quotes`: up to three short lines said in the audio, verbatim. They show as Key Quotes.
   - `caveats`: unverified figures or invented personas. These go in the transcript header, not on the page.
   - `questions[].source`: the anchor in the article the answer comes from (e.g. `#wedge`), so Short answers link back.
   - `hero_art`: leave empty for the mC Arc Box, or give a repo path or URL for an image in the title card's top-right corner.
5. **Add the transcript (optional but recommended).** Save it as `transcripts/<audio id>.txt` in the same folder. Each line starts with `Speaker 1:` or `Character 1:`. The build renames Speaker to Character and makes the branded `.md` and `.txt` downloads.
6. **Commit.** The *Publish audio site* action runs (Actions tab, about 2–4 minutes). Green check = live.

## What the build does for you

| You add | The site gets |
|---|---|
| One `.m4a` | MP3, M4A and WAV downloads, each tagged with title, owner and license |
| `audio.yml` | The page, the player, the summary, notes, references, short-answer block |
| A transcript `.txt` | On-page transcript plus branded `.md` and `.txt` downloads |
| Any of the above | The audio registry page, `registry.json`, `feed.xml` (podcast RSS), `sitemap.xml`, `llms.txt`, search and AI metadata |

## The claim check (TypeSafe Jev)

Every build checks the page against its sources and writes a table to the run's summary (Actions tab → the run → Summary).

| Check | How | Verdict |
|---|---|---|
| Key Quotes | Matched word for word in the transcript | verified / not in audio |
| Summaries, Listen for | Jev judges each sentence against the transcript | verified / contradicted / unsupported |
| Short answers | Jev judges each answer against the article section in its `source` link | same, or source missing if the link is dead |

Below 0.8 confidence a verdict is marked "needs a person". The check never blocks publishing.
Jev turns on when the repo has the secret `TYPESAFE_API_KEY` (Settings → Secrets and variables → Actions). Without it, only the quote match runs.

## Status and archive

| Want to… | Do this |
|---|---|
| Preview without listing it | `status: draft` (page builds, marked noindex, left out of registry and feeds) |
| Take a page down | `status: archived`, or move the folder into `_archive/` |
| Keep a file out of the build | Put it in any folder whose name starts with `_` |

## The audio pills

The title-card pill carries the gold mC icon, linked to main-character.me. Episode pills leave it off. Every pill has a speed dial (75% to 225%, in 25% steps); the choice is remembered for the visitor. Narrow pills move the seek bar to a second row.

## Where the master registry lives

The master table of contents for all mAInCharacter publications stays on
**main-character.me/intelligence.html#index** (mC-website repo, Tom's lane).
This site publishes `registry.json` so that page can list audio automatically
instead of anyone copying entries by hand. Wiring that in is a change to mC-website
and needs Tom's sign-off.

## Site-wide switches (site.yml)

| Key | What it does |
|---|---|
| `ga_measurement_id` | GA4 ID (`G-…`). Set to the mC Web stream, `G-80FW775JMB`. Empty = no analytics at all. When set, a consent bar appears; Google Analytics loads only after "Count me", and records plays, downloads and transcript copies. |
| `sonic_log` / `sonic_source` | The sonic logo. The workflow renders `sonic_log` (an MP3) on each build from the *mC Sonic Constellation* export named in `sonic_source` (`assets/mC_Sonic_Constellation_standalone.html`), using its own audio engine. To change the sound, replace that export with a new one of the same name. Commit an MP3 at the `sonic_log` path to override. On the page it is a small gold dot, bottom left: hover shows the arcs and waveform, pressing plays it, pressing again stops it. An episode starting silences it. |
| `sonic_autoplay` | `false` (default) = the sonic logo plays only when pressed. `true` = it also plays once on a visitor's first tap or click, unless that tap is on an audio player. |
| `arcbox` | The *mC Arc Box* export (`assets/mC_Arc_Box_-_Embed_standalone.html`). The build unpacks it and shows it top-right on every title card. To change it, replace that export with a new one of the same name. A publication can set `hero_art` to show an image instead, or `arcbox: false` to hide it. |
| `name_corrections` | Spellings the transcription tool gets wrong → the right spelling. Applied to transcripts at build time; the transcript header says so. |
| `size_budget_mb` | Build fails above this total. |

## One-time settings

- **GitHub Pages:** Settings → Pages → Source: *GitHub Actions*.
- **Custom domain (when ready):** add DNS record `CNAME audio → beto-mc.github.io`, then in `site.yml` set
  `custom_domain: audio.main-character.me` and `site_url: https://audio.main-character.me`, commit.
- **Transcripts without ElevenLabs:** any tool that exports speaker-labeled text works
  (e.g. Otter, Descript). The build does not call ElevenLabs or any paid service.
- **Size watch:** WAV adds about 10 MB per minute. GitHub Pages sites should stay under 1 GB.
  If you pass ~60 minutes of total audio, remove `wav` from `formats` in `site.yml`.

## Check before you publish

- [ ] `slug` matches the folder name
- [ ] Summary says what the listener gets, with nothing invented
- [ ] Wrong or unsourced claims in the audio are listed under `notes`
- [ ] Illustrative people (e.g. Amara) are labeled as illustrative
- [ ] `generator` and `generator_format` are right (Deep Dive, The Brief, The Critique, The Debate)
