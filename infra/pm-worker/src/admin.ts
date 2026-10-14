// 管理用 endpoint (POST /admin/resync) の認証。新しい API token は作らず、呼び出し側が自分の GitHub token (Bearer) で
// repo の push 権限を示せたときだけ通す (/status?detail=1 と同じ方式)。token は保存せず、GitHub への確認に 1 回使うだけ。
// 入口 (index.ts) と DO (app.ts) の両方で使う。未認証・不明な token は呼び出し元で 404 にする (存在を示さない)。
import type { FetchFn } from "./github.ts";

export function bearerToken(h: string | null): string | null {
  const m = /^Bearer (\S{10,255})$/.exec(h ?? "");
  return m ? m[1] : null;
}

export async function canPushRepo(token: string, repo: string, f: FetchFn): Promise<boolean> {
  const r = await f(`https://api.github.com/repos/${repo}`, {
    headers: { authorization: `Bearer ${token}`, accept: "application/vnd.github+json", "user-agent": "signature-studio-pm-worker" },
  });
  if (!r.ok) {
    void r.body?.cancel();
    return false;
  }
  const j = (await r.json().catch(() => null)) as { permissions?: { push?: boolean; admin?: boolean } } | null;
  return !!(j?.permissions?.push || j?.permissions?.admin);
}
