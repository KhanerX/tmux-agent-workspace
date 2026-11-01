// TUI half of the tmux-agent-status plugin. Runs inside the TUI process, so
// process.env.TMUX_PANE is the pane this OpenCode instance lives in. Mirrors agent
// state into tmux via ~/.local/bin/tmux-agent-status (waiting | active).
import { Plugin } from "@opencode/plugin/tui"
import { homedir } from "node:os"
import { join } from "node:path"

const SCRIPT = join(homedir(), ".local", "bin", "tmux-agent-status")

async function setStatus(state: "waiting" | "active") {
  try {
    const proc = Bun.spawn([SCRIPT, state], { stdout: "ignore", stderr: "ignore" })
    await proc.exited
  } catch {
    // tmux helper missing or failing must never break the TUI
  }
}

export default Plugin.define({
  id: "tmux-agent-status",
  setup(ctx) {
    if (!process.env.TMUX_PANE) return

    // Only react to sessions this TUI is showing. The v2 server is shared, so events
    // from other panes/projects also arrive here.
    const mine = (sessionID: string | undefined) => {
      if (!sessionID) return true
      let root = sessionID
      try {
        root = ctx.data.session.root(sessionID) ?? sessionID
      } catch {}
      const route = ctx.ui.router.current()
      if (route.type === "session" && route.sessionID === root) return true
      try {
        if (ctx.ui.tabs.list().some((t) => t.sessionID === root)) return true
      } catch {}
      return route.type !== "session"
    }

    const payload = (event: any) => event?.data ?? event?.properties ?? {}

    const offs = [
      ctx.data.on("session.status", (event: any) => {
        const p = payload(event)
        if (!mine(p.sessionID)) return
        if (p.status?.type === "busy") void setStatus("active")
        if (p.status?.type === "idle") void setStatus("waiting")
      }),
      ctx.data.on("session.idle", (event: any) => {
        if (mine(payload(event).sessionID)) void setStatus("waiting")
      }),
      ctx.data.on("permission.asked", (event: any) => {
        if (mine(payload(event).sessionID)) void setStatus("waiting")
      }),
      ctx.data.on("question.asked", (event: any) => {
        if (mine(payload(event).sessionID)) void setStatus("waiting")
      }),
    ]

    return () => {
      for (const off of offs) off()
    }
  },
})
