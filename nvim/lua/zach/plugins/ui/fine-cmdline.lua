-- `;` opens ex-commands in a floating input. `:` stays the native command
-- line on purpose: the float has no live :s preview (inccommand), no range
-- from visual mode, and no command-line window.
return {
  "VonHeikemen/fine-cmdline.nvim",
  dependencies = { "MunifTanjim/nui.nvim" },
  cmd = "FineCmdline",
  keys = { { ";", "<cmd>FineCmdline<CR>", desc = "Floating command line" } },
  opts = {},
}
