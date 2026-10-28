# Article shape

The reader is following along at a keyboard, not watching. Every section has to work without the video. The video link is there for anyone who wants to see a step happen.

## Skeleton

````markdown
# <Outcome-first title: what the reader ends up with>

_A written companion to <author>'s video ["<title>"](url), <adaptation note if any>. Timestamps link back to the matching part of the video._

<2–3 sentences: what you'll have at the end, and why it's worth doing.>

## Contents

1. [Step name](#1-step-name)
   …

<optional: the finished file tree in a ```text block>

---

## 1. <Step name: an imperative or noun phrase>

[▶ m:ss](https://www.youtube.com/watch?v=<id>&t=<seconds>s)

<Why this step exists, in 1–3 sentences of your own words.>

<Commands or config in fenced blocks with a language tag (sh, nix, lua, toml, conf, json).>

![<What the frame proves>](images/NN-name.png)

<What changes after the step and how to check it worked.>

…

---

### Adapting this to your machine

- placeholders to replace (`<you>`, paths)
- platform variants (Intel vs Apple Silicon)
- anything destructive the config does on the first run
````

## Conventions

- **Number the `##` steps.** `build_html.py` turns each one into a card with an entry in the sidebar.
- **Use the `▶ m:ss` link text exactly.** The HTML build renames it to "Watch at m:ss".
- **Screenshot alt text is a caption.** Say what the frame shows, such as "flake.nix with home-manager and nix-homebrew", not "screenshot".
- **One screenshot per idea.** Put the code block first, then the frame that proves it. Leave out frames that only show the speaker talking.
- **Label reconstructions where they appear.** For example: "The video doesn't show this spec on screen; rebuilt from the narration."
- **Use `>` blockquotes only for warnings.** They render as an amber callout. Example: "The `cc` alias skips permission prompts."
- **For a substituted tool,** add a two-column mapping table with the original setting and the replacement, then the original frame labelled "for comparison".

## Example section (from the Nix dev-env run)

````markdown
## 4. macOS preferences as code

[▶ 7:15](https://www.youtube.com/watch?v=5N-okeDdIuI&t=435s)

This is the first rebuild that visibly changes something. The `system.defaults` block replaces the clicking you'd normally do in System Settings:

    ```nix
      system.defaults = {
        NSGlobalDomain.KeyRepeat = 2;   # fast key repeat
        dock.autohide = true;
        …
      };
    ```

![system.defaults in configuration.nix](images/08-system-defaults.png)

Run `./rebuild.sh` and the Dock starts hiding itself.
````
