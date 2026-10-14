import type { Env } from "./config.ts";
import { PmDO } from "./do.ts";

export { PmDO };

const FORWARD = new Set(["issues", "issue_comment", "issue_dependencies", "pull_request", "pull_request_review", "workflow_run"]);
const PUBLIC_PATHS = new Set(["/webhook", "/setup", "/setup/callback", "/status"]);

function stub(env: Env) {
  return env.PM.get(env.PM.idFromName("main"));
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const u = new URL(req.url);
    if (!PUBLIC_PATHS.has(u.pathname)) return new Response("not found", { status: 404 });
    if (u.pathname === "/webhook") {
      if (req.method !== "POST") return new Response("method not allowed", { status: 405 });
      // 対象外のイベント (ping・push など) は DO を起こさず捨てる。未検証の入力は何も実行しない。
      const ev = req.headers.get("x-github-event");
      if (!ev || !FORWARD.has(ev)) return new Response(JSON.stringify({ ok: true, result: "ignored" }), { status: 202 });
    }
    return stub(env).fetch(req);
  },

  // Cron Trigger (毎分)。alarm の保険と、watchdog dispatch の起点。
  async scheduled(_c: unknown, env: Env, ctx: { waitUntil(p: Promise<unknown>): void }): Promise<void> {
    ctx.waitUntil(stub(env).fetch(new Request("https://do/tick", { method: "POST" })).then((r) => r.body?.cancel()));
  },
};
