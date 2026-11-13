---
name: nvim-leader-prefix-timeout
description: "Use when a Zach nvim leader key (comma) \"doesn't work\" or feels laggy: a map that is a prefix of other maps only fires after timeoutlen."
---

Zach's nvim: mapleader is `,` (lua/zach/core/keymaps.lua). A map like `<leader>t` that is a prefix of other maps (`,to ,tx ,tn ,tp ,tf ,tw ,tt`) only fires after `timeoutlen`, so it looks broken. Fix by binding to a key that prefixes nothing, not by tuning timeoutlen. Before adding any `<leader>X` map, grep `"<leader>X` across ~/.config/nvim for longer maps.

Explorer (snacks.nvim) layout: toggle owner is lua/zach/core/explorer.lua (`toggle`, `reveal`); keys live in lua/zach/plugins/ui/snacks.lua `keys`. Toggle is `,T`, reveal is `,E` (moved from `,t` on 2026-11-10). Lazy `keys` load at startup, so restart nvim after changing them.
