---
name: screencast-tutorial
description: Turn a screencast or how-to video (a local .webm/.mp4/.mov, often a yt-dlp download) into a blog-quality written tutorial. The video is transcribed locally with free Whisper (whisper.cpp), the speech becomes timed, numbered steps, and screenshots plus code typed from the screen fill in what the audio leaves out. Output is Markdown with images and, on request, a self-contained HTML page in the Zysys Admin design system. Use this whenever the user attaches or names a video and wants a transcript, written instructions, step-by-step notes, a tutorial, a blog post, a "companion doc", or "the commands/config from this video", even if they only say "transcribe this" or "turn this into instructions".
---

# Screencast → written tutorial

A screencast teaches through two channels. The narration says _why_. The screen shows _what_: file contents, commands, the result of each step. A good written companion needs both. The transcript is a **reference** for writing the article. It is not the article. The screen is the source of truth for anything exact: file names, values, commands.

The scripts in `scripts/` do the mechanical parts. Every path below is relative to this skill directory.

## 0. Confirm the ask (one short message)

Before running anything, restate the deliverable in a few lines and pin down the one thing that changes the work most. Usually that's one of:

- a transcript only;
- timed instructions with `[VISUAL @ mm:ss]` placeholders;
- a full article with screenshots;
- an HTML page.

Also ask whether the user substitutes any tool shown in the video with their own. For example, "I use kitty, not WezTerm" means that section gets rewritten for kitty.

Get the video facts first by `read`ing the video path (duration, resolution), so the summary is concrete. If the user has already said what they want, skip the question and start.

## 1. Transcribe locally (free)

```sh
scripts/transcribe.sh "<video>" <workdir> "Nix, nix-darwin, home-manager, Neovim, …"
```

The third argument is a glossary prompt: the tool and product names the video is likely to mention. The script:

- extracts 16 kHz mono audio;
- picks the best local Whisper model in this order: `$WHISPER_MODEL`, then Superwhisper's downloaded models (`~/Library/Application Support/superwhisper/ggml-*.bin`), then `~/.cache/whisper.cpp/`, and downloads `large-v3-turbo` only if none exist;
- fetches the Silero VAD model, which stops long silent typing stretches from producing invented text;
- writes `transcript.{srt,vtt,txt,json}` to the work directory.

A 45-minute video takes about 5 minutes on Apple Silicon.

**Runner timeouts matter more than speed.** Background jobs often have a default deadline (agentmux `run_command` background jobs stop at 600 s). A killed run leaves a partial log and no output files. Give the job an explicit timeout of 3600 s. If the outputs are missing, look at the last timestamp in `whisper.log` before suspecting Whisper itself.

## 2. Read the transcript and fix misheard terms against the screen

Read all of `transcript.txt`. Whisper mishears product names even with a glossary: "Western" for WezTerm, "rosepie" for Rosé Pine, ".files" for dotfiles, "Herder" for herdr, "cloud" for Claude.

**Settle every correction by looking at a frame, not by reasoning about it.** The obvious-looking fix can be wrong in either direction. In one run, a reviewer claimed the repo was literally named `.files`; the frame showed `mkdir dotfiles`. Use `read "<video>:2m55s"` to look at the exact moment.

Keep the raw transcript files as they are. Apply corrections in the article.

## 3. Map sections to timestamps

Draft the outline from the transcript: one section per real step (install X, configure Y, verify Z). Then find each step's start time:

```sh
python3 scripts/find_moments.py <workdir>/transcript.json "DeterminateNix" "rebuild.sh" "home manager as an input" …
```

The script prints `phrase → mm:ss` for the first three matches of each phrase. A step's on-screen result usually appears **10–40 s after** the sentence that introduces it, because the speaker talks first and then pastes or types.

## 4. Grab and read the frames

Pull every candidate frame in one batch:

```sh
python3 scripts/grab_frames.py "<video>" <workdir>/images 04-flake=4:40 08-defaults=7:35 …
```

Then `read` the frames that should hold exact content: config files, terminal output, before/after views. A frame is usable only if it shows the finished state.

- If the frame shows the file half-edited, another file, or an empty buffer, re-extract it 5–30 s later.
- Scrolled-off content ("12 more lines") may need a second frame.

Screen-only details to capture:

- full file contents and file paths (the editor's status line usually shows the path);
- exact commands, which the narration often skips;
- package names (a Homebrew `brews` vs `casks` entry, an exact cask name);
- the keystroke overlay, if the video has one.

## 5. Write the article in your own words

Use `references/article-shape.md` for the structure. The rules that matter:

- **Write the prose fresh. Never lightly edit the transcript.** The narration is the reference for intent and reasoning. If the speaker has authored opinions (rule lists, philosophy), paraphrase them as a short summary, and don't copy them out.
- **Type the config from the screen** as short code blocks, and put the screenshot it came from right below. Copy only what the reader needs to reproduce the step.
- **Label anything the screen never showed.** If a file's contents never appear, write the most likely version, and say in the text that it is reconstructed from the narration or from an earlier command. Don't present a guess as a transcription.
- **Apply the user's substitutions properly.** Rewrite the section for their tool. Map each setting from the video's tool to the new one, in a table when there are several. Keep one video frame as a labelled reference.
- Start each section with a `[Watch at m:ss](https://www.youtube.com/watch?v=<id>&t=<seconds>s)` link. The YouTube id is usually in the yt-dlp filename (`… [5N-okeDdIuI].webm`).
- Add a short "adapting this to your machine" closer with placeholders and any destructive settings. For example, Homebrew `cleanup = "zap"` removes every unlisted app.

Then check the image links and remove frames you didn't use:

```sh
python3 scripts/check_links.py <workdir>/tutorial.md --prune
```

The script exits 1 if any image link points to a missing file.

## 6. Optional: a self-contained web page

```sh
python3 scripts/build_html.py <workdir>/tutorial.md ~/Downloads/tut.html \
  --tokens ~/Dropbox/Zysys/zysys-admin-design-system.zip \
  --meta "Written companion to <author>'s video · 13 steps · 44 min video"
```

The output is one file with:

- the design tokens inlined (`tokens.css` from a design-system zip or a `.css` file);
- screenshots embedded as JPEG data URIs, about 4 MB for 22 images;
- a sticky table of contents with the current section highlighted, and one card per `##` section;
- a Copy button on every code block, and click-to-zoom screenshots;
- "Watch at m:ss" timestamp labels.

It needs `pandoc` and Pillow. **Verify it in a real browser before reporting it done.** Serve the directory with `python3 -m http.server`, open the page, and confirm `tab.errors()` is empty. Then click one TOC entry and screenshot one table and one code block. Headless file:// pages are often blocked, so serve over HTTP.

## 7. Report

Give the output paths and the counts (sections, images, links checked). Then list, by name, everything the screen didn't show and you reconstructed, plus anything you didn't test, such as a substituted tool's config or a mobile layout. The user decides what to double-check from that list.

## Files

- `scripts/transcribe.sh`: audio extraction plus whisper.cpp with VAD and model discovery.
- `scripts/find_moments.py`: phrase → timestamp lookup in `transcript.json`.
- `scripts/grab_frames.py`: batch frame extraction, `name=mm:ss` pairs.
- `scripts/check_links.py`: image-link check, with `--prune` for unused frames.
- `scripts/build_html.py`: Markdown → self-contained HTML page in the Zysys Admin design system.
- `references/article-shape.md`: section template and an example section.
