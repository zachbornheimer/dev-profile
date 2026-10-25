-- Godot 4 as an external-editor workflow: class docs in a float, scene
-- helpers, health checks. C# intelligence itself is csharp-ls in mason.lua.
return {
  "Mathijs-Bakker/godotdev.nvim",
  -- C# LSP is mason csharp-ls. Do not FileType-load here: setup() warns
  -- about nvim-dap and that hit-enter blocked Coin.cs on open.
  ft = { "gd", "gdscript", "gdshader" },
  dependencies = {
    "mfussenegger/nvim-dap",
  },
  cmd = {
    "GodotDocs",
    "GodotDocsFloat",
    "GodotDocsBuffer",
    "GodotDocsBrowser",
    "GodotDocsCursor",
    "GodotRunProject",
    "GodotRunCurrentScene",
    "GodotRunScene",
    "GodotSceneTree",
  },
  keys = {
    { "gK", "<cmd>GodotDocs<cr>", desc = "Godot class docs" },
  },
  opts = {
    csharp = true,
    godot_path = "godot-mono",
    formatter = false,
    treesitter = { auto_setup = false },
    docs = {
      renderer = "float",
      version = "stable",
    },
  },
}
