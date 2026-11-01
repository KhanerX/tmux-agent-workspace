// Server half of the tmux-agent-status plugin. The v2 background service is shared
// across terminals and has no tmux pane of its own, so the real work lives in tui.ts,
// which runs inside each TUI process. The loader requires a server entrypoint.
import { Plugin } from "@opencode/plugin"

export default Plugin.define({
  id: "tmux-agent-status",
  setup() {},
})
