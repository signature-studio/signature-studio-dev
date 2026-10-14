import { bearerToken, canPushRepo } from "./admin.ts";
import { DEFAULT_REPO, type Env } from "./config.ts";
import { PmDO } from "./do.ts";
import { guiResponse } from "./gui.ts";

export { PmDO };

const FORWARD = new Set(["issues", "issue_comment", "issue_dependencies", "pull_request", "pull_request_review", "workflow_run"]);
const PUBLIC_PATHS = new Set(["/webhook", "/setup", "/setup/callback", "/status"]);
// 管理用の経路と、その HTTP メソッド (#2339 resync・#2343 import/export)。
const ADMIN_METHOD: Record<string, string> = { "/admin/resync": "POST", "/admin/import": "POST", "/admin/export": "GET" };

function stub(env: Env) {
  return env.PM.get(env.PM.idFromName("main"));
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const u = new URL(req.url);
    // 管理用 (#2339・#2343)。認証は入口で行い、通らなければ 404 を返して DO を呼ばない (存在を示さない)。通ったら DO で実行する。
    if (Object.hasOwn(ADMIN_METHOD, u.pathname)) {
      const token = bearerToken(req.headers.get("authorization"));
      const ok = req.method === ADMIN_METHOD[u.pathname] && !!token && (await canPushRepo(token, env.REPO ?? DEFAULT_REPO, (i, init) => fetch(i, init)));
      if (!ok) return new Response("not found", { status: 404 });
      return stub(env).fetch(req);
    }
    // 状態の簡易 GUI (#2658)。静的な HTML だけで、DO は呼ばない (値は同じ Worker の GET /status から読む)。
    if (u.pathname === "/") return guiResponse(req.method);
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
