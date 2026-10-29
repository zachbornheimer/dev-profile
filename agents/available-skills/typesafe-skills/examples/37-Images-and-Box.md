---
name: 37 Images and Box
description: Attach still PNG/JPEG to System One requests; use Noul/Choice/Score on photos and Box to locate a target. Opt-in, experimental.
---

ORIGINAL SOURCE: <https://docs.typesafe.ai/images>
ALSO: <https://docs.typesafe.ai/primitives/box>
ALSO: <https://typesafe.ai/blog/jev-1-14>
VIDEO: none
Use the original source primarily. This skill below is a summary in our own words. View details at this link.

## When to use

The next line of code needs a typed judgment about pixels that already exist: a screenshot vs a design, a scanned form, a camera frame, a signature pad capture. Do not add an image to a text-only picker or summarizer.

## What it demonstrates

Images can go anywhere text can go in a System One request: `state`, a question's `instructions`, or its `criteria`. Each file is listed once in `assets` under a unique reference (a UUID is safest). Jev 1.13 already accepts images; Box needs Jev 1.14 (`jev-preview` or `jev-1.14.0`). Both images and Box are off by default. Every request that contains an image or a Box must send `TypeSafe-Danger-Zone-Images: true` or the API returns 400. TypeSafe does not vouch for production reliability yet; decompose questions.

Box returns `top`/`bottom`/`left`/`right` as fractions of the image size, plus `confidence`. There is no "not found": pair Box with a Noul for presence and ignore the box when the Noul is low. One target per Box question.

## Steps / call shape

Prepare each image first: PNG or still JPEG, pixels rotated upright (EXIF is stripped and ignored), longest side at most 1568, each side at least 280. Prefer multipart over base64.

```python
from pathlib import Path
from typesafe_sdk import Box, Image, Noul, TypeSafeClient

with TypeSafeClient() as client:
    result = client.system_one(
        model="jev-preview",
        state={"photo": Image(Path("door-camera.jpg"))},
        questions={
            "person_present": Noul(instructions="Is there a person in `photo`?"),
            "person": Box(instructions="the person in `photo`"),
        },
        extra_headers={"TypeSafe-Danger-Zone-Images": "true"},
    )
```

Put a shared photo in `state` once. Put a one-off comparison picture in that question only. Define Choice/Score options with example pictures when the label is visual. For a small target in a large image, tile or crop first, then Box.

## Results / numbers

Image tokens are billed as ordinary input tokens. Limits (rejected, never resized): 16 MiB per file, 280–1568 px per side, 32 MiB request body. A 402 is billing, not a missing header; a missing header is 400.

## Pitfalls

- Short asset keys such as `id` also match inside `identity`. Use a new UUID per image.
- Box always returns four edges. Do not treat a box as proof the target is present.
- Do not send GIF/WebP/HEIC/video. Export one still frame as PNG or JPEG.
- Text-only workflows (skill-pick, quality-guard, summarize-a-file) do not get cheaper by attaching a photo.

## Related cookbooks

- `04-Choosing-Primitives.md` — Box is the fourth primitive.
- `03-Atomic-Questions.md` — decompose visual questions the same way as text.
- `10-Smart-Home-Assistant.md` — camera frames as state; ask what changed.
