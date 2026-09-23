# Updating the audio site

For Beto and the mC team. Not published on the site.

**The rule:** one article folder = one page. Add a folder, commit, and GitHub builds and publishes it. You never edit HTML.

## Add a new publication (about 10 minutes)

1. **Make the audio** in Gemini Notebook (formerly NotebookLM). Download it (`.m4a`).
2. **Make a folder** named for the date and topic: `articles/2026-10-05-your-topic/`
3. **Put the audio in it.** Any name works. Upload with GitHub's *Add file → Upload files*.
4. **Copy the form.** Copy `articles/_template/audio.yml` into your folder and fill it in.
   - `slug` must match the folder name exactly.
   - Keep `status: draft` while you check it. Change to `published` when ready.
   - Write the summary yourself or ask Claude. Every claim must come from the article, the audio, or a linked source.
   - Put anything wrong or unverified in the audio under `notes:` (e.g. a mispronounced name, a figure you can't source).
5. **Add the transcript (optional but recommended).** Save it as `transcripts/<audio id>.txt` in the same folder. Each line starts with `Speaker 1:` or `Character 1:`. The build renames Speaker to Character and makes the branded `.md` and `.txt` downloads.
6. **Commit.** The *Publish audio site* action runs (Actions tab, about 2–4 minutes). Green check = live.

## What the build does for you

| You add | The site gets |
|---|---|
| One `.m4a` | MP3, M4A and WAV downloads, each tagged with title, owner and license |
| `audio.yml` | The page, the player, the summary, notes, references, short-answer block |
| A transcript `.txt` | On-page transcript plus branded `.md` and `.txt` downloads |
| Any of the above | The audio registry page, `registry.json`, `feed.xml` (podcast RSS), `sitemap.xml`, `llms.txt`, search and AI metadata |

## Status and archive

| Want to… | Do this |
|---|---|
| Preview without listing it | `status: draft` (page builds, marked noindex, left out of registry and feeds) |
| Take a page down | `status: archived`, or move the folder into `_archive/` |
| Keep a file out of the build | Put it in any folder whose name starts with `_` |

## Where the master registry lives

The master table of contents for all mAInCharacter publications stays on
**main-character.me/intelligence.html#index** (mC-website repo, Tom's lane).
This site publishes `registry.json` so that page can list audio automatically
instead of anyone copying entries by hand. Wiring that in is a change to mC-website
and needs Tom's sign-off.

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
