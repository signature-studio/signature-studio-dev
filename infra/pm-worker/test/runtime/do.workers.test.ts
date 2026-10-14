import { describe, it, expect } from "vitest";
import { env, runInDurableObject, SELF } from "cloudflare:test";
import { signBody } from "../../src/hmac.ts";
import { sealText } from "../../src/crypto.ts";
import { PmDO } from "../../src/do.ts";

// 実 workerd の Durable Object (ctx.storage.sql) で、webhook の増分保存・再起動後の読み出し・401 時の無書き込みを確認する。
const STORE_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
const SECRET = "runtime-test-secret";
const REPO = "signature-studio/signature-studio-dev";

const pmStub = () => env.PM.get(env.PM.idFromName("main"));

// App の webhook secret を DO と同じ形式 (kv の meta/app) で封じて置く。setup フローは通さない。
async function seedApp(state: any): Promise<void> {
  const whSealed = await sealText(STORE_KEY, SECRET);
  const rec = { appId: 1, slug: "oc-pm-test", pemSealed: "v1.x.y", whSealed, installationId: 1 };
  state.storage.sql.exec("CREATE TABLE IF NOT EXISTS kv (bucket TEXT NOT NULL, k TEXT NOT NULL, v TEXT NOT NULL, PRIMARY KEY (bucket, k))");
  state.storage.sql.exec("INSERT INTO kv (bucket, k, v) VALUES ('meta', 'app', ?)", JSON.stringify(rec));
}

function kvRows(state: any): Array<{ bucket: string; k: string; v: string }> {
  return [...state.storage.sql.exec("SELECT bucket, k, v FROM kv ORDER BY bucket, k")];
}

const issue = (number: number, title: string) => ({
  action: "edited",
  repository: { full_name: REPO },
  issue: { number, title, body: "b", state: "open", updated_at: "2026-10-14T10:00:00Z", labels: [] },
});

async function post(payload: unknown, sig?: string): Promise<Response> {
  const body = JSON.stringify(payload);
  const headers: Record<string, string> = { "X-GitHub-Event": "issues", "Content-Type": "application/json" };
  headers["X-Hub-Signature-256"] = sig ?? signBody(SECRET, body);
  return SELF.fetch("https://pm.test/webhook", { method: "POST", headers, body });
}

describe("PmDO (実 Durable Object ランタイム)", () => {
  it("POST /webhook が検証済みの配送を増分保存し、再起動 (新しいインスタンス) 後も読める", async () => {
    await runInDurableObject(pmStub(), async (instance, state: any) => {
      await seedApp(state);
    });

    const res = await post(issue(4242, "[CI-4242] runtime"));
    expect(res.status).toBe(202);
    expect(await res.json()).toMatchObject({ ok: true, result: "applied" });

    await runInDurableObject(pmStub(), async (_instance, state: any) => {
      const rows = kvRows(state).filter((r) => r.bucket === "issues");
      expect(rows.map((r) => r.k)).toContain("4242");
      expect(JSON.parse(rows.find((r) => r.k === "4242")!.v).title).toBe("[CI-4242] runtime");

      // 再起動相当: 同じ storage 上に新しい PmDO を作り、保存済みの状態を読み出す。
      const restarted = new PmDO(state, env as any) as any;
      expect(restarted.app.engine.s.issues["4242"]?.title).toBe("[CI-4242] runtime");
    });
  });

  it("署名が不正なら 401 で、DO の storage に新しい行を書かない", async () => {
    const before = await runInDurableObject(pmStub(), async (_i, state: any) => kvRows(state));

    const bad = await post(issue(5555, "[CI-5555] forged"), "sha256=00");
    expect(bad.status).toBe(401);
    const none = await SELF.fetch("https://pm.test/webhook", {
      method: "POST",
      headers: { "X-GitHub-Event": "issues" },
      body: JSON.stringify(issue(5555, "[CI-5555] nosig")),
    });
    expect(none.status).toBe(401);

    await runInDurableObject(pmStub(), async (_i, state: any) => {
      expect(kvRows(state)).toEqual(before);
      expect(kvRows(state).some((r) => r.k === "5555")).toBe(false);
    });
  });
  it("/status: 観測のキーを返し、last_webhook_at は検証済みの配送だけで進む。webhook の自由文に混ぜた secret は出さない", async () => {
    await runInDurableObject(pmStub(), async (_i, state: any) => {
      if (!kvRows(state).some((r) => r.bucket === "meta" && r.k === "app")) await seedApp(state);
    });
    const status = async () => (await SELF.fetch("https://pm.test/status")).text();
    const evil = "-----BEGIN RSA PRIVATE KEY-----\nMIIEdummyKEYmaterial\n-----END RSA PRIVATE KEY----- ghp_DUMMYtokenDUMMYtoken0123456789abcdef whsec_dummy";
    const before = JSON.parse(await status());
    for (const k of ["last_webhook_at", "last_dispatch_at", "running", "dry_run_skipped_posts", "reconcile_diff", "rest_remaining", "rest_used", "rest_reset_at"]) {
      expect(before).toHaveProperty(k);
    }
    expect(before.rest_remaining).toBeNull();
    expect(before.mode).toBe("dry-run");

    expect((await post(issue(6001, evil), "sha256=00")).status).toBe(401);
    expect(JSON.parse(await status()).last_webhook_at).toBe(before.last_webhook_at);

    expect((await post(issue(6002, evil))).status).toBe(202);
    const text = await status();
    expect(Date.parse(JSON.parse(text).last_webhook_at)).toBeGreaterThan(0);
    for (const needle of ["BEGIN RSA PRIVATE KEY", "MIIEdummyKEYmaterial", "ghp_DUMMY", "whsec_dummy", SECRET, STORE_KEY]) expect(text).not.toContain(needle);
  });
});
