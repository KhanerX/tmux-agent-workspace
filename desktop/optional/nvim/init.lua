-- Basic editor behavior
vim.opt.number = true
vim.opt.relativenumber = true
vim.opt.expandtab = true
vim.opt.shiftwidth = 2
vim.opt.tabstop = 2
vim.opt.smartindent = true
vim.opt.clipboard = "unnamedplus"
vim.opt.completeopt = { "menuone", "noinsert", "noselect" }
vim.opt.signcolumn = "yes"
vim.opt.hlsearch = true

vim.keymap.set("i", "kj", "<Esc>", { desc = "Exit insert mode" })
vim.keymap.set("n", "<Esc>", "<cmd>nohlsearch<CR><Esc>", { desc = "Clear search highlight" })

-- Treat SICP files as Racket/Scheme
vim.filetype.add({
  extension = {
    rkt = "racket",
    scm = "scheme",
    ss = "scheme",
  },
})

-- Bootstrap lazy.nvim if missing
local lazypath = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"
if not vim.loop.fs_stat(lazypath) then
  vim.fn.system({
    "git", "clone", "--filter=blob:none",
    "https://github.com/folke/lazy.nvim.git",
    "--branch=stable",
    lazypath,
  })
end
vim.opt.rtp:prepend(lazypath)

require("lazy").setup({
  -- Treesitter syntax highlighting
  {
    "nvim-treesitter/nvim-treesitter",
    build = ":TSUpdate",
    config = function()
      local ok, treesitter = pcall(require, "nvim-treesitter.configs")
      if not ok then
        return
      end

      treesitter.setup({
        ensure_installed = { "scheme", "c", "cpp" },
        highlight = { enable = true },
        indent = { enable = true },
      })
    end,
  },

  {
    "hrsh7th/nvim-cmp",
    dependencies = {
      "hrsh7th/cmp-nvim-lsp",
    },
    config = function()
      local cmp = require("cmp")

      cmp.setup({
        preselect = cmp.PreselectMode.Item,
        completion = {
          autocomplete = false,
          completeopt = "menuone,noinsert,noselect",
        },
        snippet = {
          expand = function()
          end,
        },
        window = {
          completion = cmp.config.disable,
          documentation = cmp.config.disable,
        },
        view = {
          docs = {
            auto_open = false,
          },
        },
        mapping = cmp.mapping.preset.insert({
          ["<C-Space>"] = cmp.mapping.complete(),
          ["<C-e>"] = cmp.mapping.abort(),
          ["<Tab>"] = cmp.mapping(function(fallback)
            if cmp.visible() then
              cmp.confirm({ select = true, behavior = cmp.ConfirmBehavior.Replace })
            else
              cmp.complete()
            end
          end, { "i" }),
          ["<S-Tab>"] = cmp.mapping(function(fallback)
            if cmp.visible() then
              cmp.abort()
            else
              fallback()
            end
          end, { "i" }),
        }),
        experimental = {
          ghost_text = true,
        },
        sources = {
          {
            name = "nvim_lsp",
            keyword_length = 2,
            max_item_count = 8,
          },
        },
      })
    end,
  },

})

local lsp_capabilities = vim.lsp.protocol.make_client_capabilities()
do
  local ok, cmp_nvim_lsp = pcall(require, "cmp_nvim_lsp")
  if ok then
    lsp_capabilities = cmp_nvim_lsp.default_capabilities(lsp_capabilities)
    lsp_capabilities.textDocument.completion.completionItem.snippetSupport = false
  end
end

local function lsp_root(bufnr)
  local path = vim.api.nvim_buf_get_name(bufnr)
  if path == "" then
    return vim.fn.getcwd()
  end

  local root = vim.fs.find({ ".git", "compile_commands.json", "compile_flags.txt", "Makefile" }, {
    upward = true,
    path = vim.fs.dirname(path),
  })[1]

  return root and vim.fs.dirname(root) or vim.fs.dirname(path)
end

vim.api.nvim_create_autocmd("FileType", {
  pattern = { "c", "cpp" },
  callback = function(args)
    vim.lsp.start({
      name = "clangd",
      cmd = { "clangd" },
      root_dir = lsp_root(args.buf),
      capabilities = lsp_capabilities,
    })
  end,
})

vim.api.nvim_create_autocmd("FileType", {
  pattern = { "racket", "scheme" },
  callback = function(args)
    vim.lsp.start({
      name = "racket_langserver",
      cmd = { "racket", "-l", "racket-langserver" },
      root_dir = lsp_root(args.buf),
      capabilities = lsp_capabilities,
    })
  end,
})

vim.keymap.set("n", "gd", vim.lsp.buf.definition)
vim.keymap.set("n", "K", vim.lsp.buf.hover)
vim.keymap.set("n", "<leader>rn", vim.lsp.buf.rename)
vim.keymap.set("n", "<leader>ca", vim.lsp.buf.code_action)

-- Run current Racket/Scheme file
vim.keymap.set("n", "<leader>r", function()
  vim.cmd("w")
  vim.cmd("botright split")
  vim.fn.termopen({ "racket", vim.fn.expand("%:p") })
end)

-- Open plain Racket REPL
vim.keymap.set("n", "<leader>R", function()
  vim.cmd("botright split | terminal racket")
end)

local function run_competitive_programming_target(target)
  local directory
  if vim.bo.buftype == "" then
    vim.cmd("write")
    directory = vim.fn.expand("%:p:h")
    vim.g.competitive_programming_directory = directory
  else
    directory = vim.g.competitive_programming_directory
  end

  if not directory or directory == "" then
    vim.notify("Open main.cpp or input.txt first", vim.log.levels.WARN)
    return
  end

  local command = "make --no-print-directory -s -C " .. vim.fn.shellescape(directory) .. " " .. target

  if vim.g.competitive_programming_terminal_buf then
    for _, win in ipairs(vim.fn.win_findbuf(vim.g.competitive_programming_terminal_buf)) do
      if vim.api.nvim_win_is_valid(win) then
        vim.api.nvim_win_close(win, true)
      end
    end

    if vim.api.nvim_buf_is_valid(vim.g.competitive_programming_terminal_buf) then
      pcall(vim.api.nvim_buf_delete, vim.g.competitive_programming_terminal_buf, { force = true })
    end
  end

  vim.cmd("botright 12split")
  vim.cmd("terminal " .. command)
  vim.g.competitive_programming_terminal_buf = vim.api.nvim_get_current_buf()
end

vim.keymap.set("n", "<F5>", function()
  run_competitive_programming_target("run")
end, {
  desc = "Compile and run competitive programming solution",
})

vim.keymap.set("n", "<F6>", function()
  run_competitive_programming_target("debug")
end, {
  desc = "Run competitive programming solution with sanitizers",
})
