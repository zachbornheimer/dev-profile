# Accessibility

**Check:** No mounted capability measures this yet: report it as unmeasured, never healthy. Intended scope (axe-core on key templates, keyboard traversal, contrast, forms).

## Facts

- Automated axe testing finds roughly 57% of issues. A manual keyboard and screen-reader pass is needed on the money pages (donate, register, checkout, login) at least quarterly.
- ADA Title II (public entities) does not cover private nonprofits. The exposure is Title III lawsuits (3,117 filed in 2025), so the goal is a documented good-faith effort.

## Checks

- axe on home, donate, register, a post, a form page: serious and critical violations are findings.
- Keyboard: tab order, visible focus, no traps, skip link, forms operable, modals closable.
- Screen reader spot check (VoiceOver): landmarks, headings, form labels, error messages, image alt text.
- Contrast: text at least 4.5:1, large text 3:1, UI components 3:1. Zoom to 200% without loss.
- Motion, autoplay, captions on video.

**Triage:** fix issues on money pages first; ticket per template, not per instance. Theme fixes are code changes and follow the backup rule.

**Needs Zach:** publishing an accessibility statement; any promise of conformance.

**Common misses:** passing axe while the donate form cannot be used with a keyboard; alt text present but useless; focus lost after a modal or a payment iframe.

**Cadence:** axe monthly; manual pass on money pages quarterly.

**Browser tests:** when writing or changing Playwright tests for this (synthetic login/checkout, visual regression, axe), load the `world-class-playwright` skill.
