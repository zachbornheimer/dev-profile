-- plugins/ui/render-markdown.lua
return {
  {
    "MeanderingProgrammer/render-markdown.nvim",
    ft = { "markdown" },
    dependencies = {
      "nvim-treesitter/nvim-treesitter",
      "nvim-mini/mini.icons",
    },
    opts = {},
    keys = {
      {
        "<leader>mt",
        "<cmd>RenderMarkdown toggle<cr>",
        desc = "Toggle Markdown rendering",
      },
    },
  },
}
