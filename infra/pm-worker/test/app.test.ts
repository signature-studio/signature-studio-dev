import { test } from "node:test";
import assert from "node:assert/strict";
import { PmApp, buildManifest, APP_NAME } from "../src/app.ts";
import { loadConfig } from "../src/config.ts";
import { MemoryStore } from "../src/kvstore.ts";
import { openText, sealText } from "../src/crypto.ts";
import { signBody } from "../src/hmac.ts";
import { WEBHOOK_EVENTS } from "../src/webhook.ts";
import { STORE_KEY, WH_SECRET, T0, configuredApp, issuePayload, j, mockFetch, send } from "./helpers.ts";

test("manifest: App 名・権限・購読イベントが指定どおり (org 所有の App として作る)", async () => {
  const m = buildManifest("https://pm.example") as any;
  assert.equal(m.name, "oc-pm-for-signature-studio");
  assert.equal(m.name, APP_NAME);
  assert.equal(m.hook_attributes.url, "https://pm.example/webhook");
  assert.equal(m.redirect_url, "https://pm.example/setup/callback");
  assert.deepEqual(m.default_permissions, { issues: "write", pull_requests: "write", contents: "write", actions: "read", metadata: "read" });
  assert.deepEqual(m.default_events, [...WEBHOOK_EVENTS]);
  assert.ok(m.default_events.includes("workflow_run") && m.default_events.includes("issue_dependencies"));
  const app = new PmApp({ store: new MemoryStore(), cfg: loadConfig({}), storeKey: STORE_KEY, now: () => T0, fetch: mockFetch([]).f, scheduleSoon: async () => {} });
  const html = await (await app.handle(new Request("https://pm.example/setup"))).text();
  assert.match(html, /https:\/\/github\.com\/organizations\/signature-studio\/settings\/apps\/new\?state=/);
  assert.match(html, /method="post"/);
});

test("manifest callback: id/pem/webhook_secret は封印して保管し、応答・ログ・ストアの平文に出ない", async () => {
  const logs: string[] = [];
  const orig = console.log;
  console.log = (...a: unknown[]) => void logs.push(a.join(" "));
  try {
    const ctx = await configuredApp();
    const body = await ctx.cb.text();
    assert.equal(ctx.cb.status, 200);
    assert.match(body, /installations\/new/);
    const rec = ctx.store.get<any>("meta", "app");
    assert.equal(rec.appId, 4242);
    const dump = JSON.stringify([...ctx.store.data].map(([b, m]) => [b, [...m]]));
    const pemBody = ctx.pems.pkcs1.split("\n")[1];
    for (const secret of [WH_SECRET, pemBody, "BEGIN RSA PRIVATE KEY"]) {
      assert.ok(!dump.includes(secret), "ストアに平文が無い");
      assert.ok(!body.includes(secret), "応答に平文が無い");
      assert.ok(!logs.join("\n").includes(secret), "ログに平文が無い");
    }
    assert.ok(rec.pemSealed.startsWith("v1.") && rec.whSealed.startsWith("v1."));
    assert.equal(await openText(STORE_KEY, rec.whSealed), WH_SECRET);
    assert.match(await openText(STORE_KEY, rec.pemSealed), /BEGIN RSA PRIVATE KEY/);
    await assert.rejects(openText(b64(1), rec.whSealed));
  } finally {
    console.log = orig;
  }
});

const b64 = (n: number) => Buffer.alloc(32, n).toString("base64url");

test("manifest callback: state 不一致・期限切れ・再利用・設定済みでは拒否する", async () => {
  const ctx = await configuredApp();
  // 設定済み: /setup も callback も閉じる
  assert.equal((await ctx.app.handle(new Request("https://pm.example/setup"))).status, 409);
  assert.equal((await ctx.app.handle(new Request(`https://pm.example/setup/callback?code=${"b".repeat(40)}&state=${ctx.state}`))).status, 409);

  const fresh = () => {
    const clock = { t: T0 };
    const m = mockFetch([]);
    const app = new PmApp({ store: new MemoryStore(), cfg: loadConfig({}), storeKey: STORE_KEY, now: () => clock.t, fetch: m.f, scheduleSoon: async () => {} });
    return { app, m, clock };
  };
  const a = fresh();
  const st = /state=([^"&]+)/.exec(await (await a.app.handle(new Request("https://pm.example/setup"))).text())?.[1] as string;
  const bad = await a.app.handle(new Request(`https://pm.example/setup/callback?code=${"c".repeat(40)}&state=WRONG`));
  assert.equal(bad.status, 400);
  assert.equal(a.m.calls.length, 0, "state 不一致では GitHub を呼ばない");
  a.clock.t += 61 * 60_000;
  const late = await a.app.handle(new Request(`https://pm.example/setup/callback?code=${"c".repeat(40)}&state=${st}`));
  assert.equal(late.status, 400);
  assert.equal(a.m.calls.length, 0);
  const b = fresh();
  const bad2 = await b.app.handle(new Request(`https://pm.example/setup/callback?code=zzz&state=x`));
  assert.equal(bad2.status, 400, "setup を開いていなければ state が無く拒否");
});

const stateOf = async (app: PmApp): Promise<string> =>
  /state=([^"&]+)/.exec(await (await app.handle(new Request("https://pm.example/setup"))).text())?.[1] as string;

test("/setup: 有効な state があれば何度開いても同じ state を返す (第三者が叩いても変わらない)", async () => {
  const clock = { t: T0 };
  const m = mockFetch([]);
  const store = new MemoryStore();
  const app = new PmApp({ store, cfg: loadConfig({}), storeKey: STORE_KEY, now: () => clock.t, fetch: m.f, scheduleSoon: async () => {} });
  const first = await stateOf(app);
  assert.ok(first && first.length >= 24);
  clock.t += 30 * 60_000;
  assert.equal(await stateOf(app), first, "PM が開いた後に第三者が /setup を叩いても同じ state");
  assert.equal(await stateOf(app), first, "PM がもう一度開いても同じ state");
  assert.equal(store.get<any>("meta", "setupState").exp, T0 + 60 * 60_000, "期限は延ばさない");
  // 進行中の state で callback は通る (正)
  const ok = mockFetch([(c) => (c.url.includes("/app-manifests/") ? j({ id: 1, slug: "oc-pm-for-signature-studio", pem: "p", webhook_secret: "w", owner: { login: "signature-studio" } }, 201) : undefined)]);
  const app2 = new PmApp({ store, cfg: loadConfig({}), storeKey: STORE_KEY, now: () => clock.t, fetch: ok.f, scheduleSoon: async () => {} });
  assert.equal((await app2.handle(new Request(`https://pm.example/setup/callback?code=${"a".repeat(40)}&state=${first}`))).status, 200);
  assert.equal(store.get("meta", "setupState"), undefined, "成功したら state を消費する");
});

test("/setup: 期限切れの state は新しく発行し、古い state は受け付けない", async () => {
  const clock = { t: T0 };
  const m = mockFetch([]);
  const app = new PmApp({ store: new MemoryStore(), cfg: loadConfig({}), storeKey: STORE_KEY, now: () => clock.t, fetch: m.f, scheduleSoon: async () => {} });
  const old = await stateOf(app);
  clock.t += 61 * 60_000;
  const fresh = await stateOf(app);
  assert.notEqual(fresh, old);
  assert.equal((await app.handle(new Request(`https://pm.example/setup/callback?code=${"a".repeat(40)}&state=${old}`))).status, 400);
  assert.equal(m.calls.length, 0);
});

test("callback: 第三者が不正な code / 不一致の state で叩いても、進行中の state は失効しない", async () => {
  const m = mockFetch([(c) => (c.url.includes("/app-manifests/") ? j({ message: "Not Found" }, 404) : undefined)]);
  const store = new MemoryStore();
  const app = new PmApp({ store, cfg: loadConfig({}), storeKey: STORE_KEY, now: () => T0, fetch: m.f, scheduleSoon: async () => {} });
  const st = await stateOf(app);
  const before = JSON.stringify(store.get("meta", "setupState"));
  assert.equal((await app.handle(new Request(`https://pm.example/setup/callback?code=zzz&state=${st}`))).status, 400, "形式不正の code");
  assert.equal((await app.handle(new Request(`https://pm.example/setup/callback?code=${"f".repeat(40)}&state=WRONG`))).status, 400, "state 不一致");
  assert.equal((await app.handle(new Request(`https://pm.example/setup/callback?code=${"f".repeat(40)}&state=${st}`))).status, 502, "GitHub が拒否する code");
  assert.equal(JSON.stringify(store.get("meta", "setupState")), before, "進行中の state は変わらない");
  assert.equal(store.get("meta", "app"), undefined);
  assert.equal(await stateOf(app), st, "その後も同じ state で手順を続けられる");
});

test("manifest callback: GitHub の変換が失敗したら保存しない", async () => {
  const m = mockFetch([(c) => (c.url.includes("/app-manifests/") ? j({ message: "x" }, 404) : undefined)]);
  const store = new MemoryStore();
  const app = new PmApp({ store, cfg: loadConfig({}), storeKey: STORE_KEY, now: () => T0, fetch: m.f, scheduleSoon: async () => {} });
  const st = /state=([^"&]+)/.exec(await (await app.handle(new Request("https://pm.example/setup"))).text())?.[1] as string;
  const r = await app.handle(new Request(`https://pm.example/setup/callback?code=${"d".repeat(40)}&state=${st}`));
  assert.equal(r.status, 502);
  assert.equal(store.get("meta", "app"), undefined);
});

test("manifest callback: owner が org でない App (第三者が持ち込んだ code) は保存しない", async () => {
  const m = mockFetch([(c) => (c.url.includes("/app-manifests/") ? j({ id: 1, slug: "evil", pem: "x", webhook_secret: "y", owner: { login: "attacker" } }, 201) : undefined)]);
  const store = new MemoryStore();
  const app = new PmApp({ store, cfg: loadConfig({}), storeKey: STORE_KEY, now: () => T0, fetch: m.f, scheduleSoon: async () => {} });
  const st = /state=([^"&]+)/.exec(await (await app.handle(new Request("https://pm.example/setup"))).text())?.[1] as string;
  const r = await app.handle(new Request(`https://pm.example/setup/callback?code=${"e".repeat(40)}&state=${st}`));
  assert.equal(r.status, 403);
  assert.equal(store.get("meta", "app"), undefined);
});

test("POST /webhook: 署名なし・不一致・改ざんは 401 で、ストアに一切書かない", async () => {
  const ctx = await configuredApp();
  const before = ctx.store.writes;
  const payload = issuePayload(10);
  for (const sig of [null, "sha256=00", "sha1=abc", signBody("other-secret", JSON.stringify(payload))]) {
    const r = await send(ctx.app, "issues", payload, sig);
    assert.equal(r.status, 401);
  }
  const body = JSON.stringify(payload);
  const tampered = await ctx.app.handle(
    new Request("https://pm.example/webhook", { method: "POST", body: body.replace("t10", "evil"), headers: { "x-github-event": "issues", "x-hub-signature-256": signBody(WH_SECRET, body) } }),
  );
  assert.equal(tampered.status, 401);
  assert.equal(ctx.store.writes, before, "未検証の入力ではストアが変わらない");
  assert.equal(ctx.soon(), 0, "alarm も早めない");
  assert.equal(ctx.m.calls.filter((c) => c.method === "POST" && c.url.includes("/comments")).length, 0);
});

test("POST /webhook: 署名が正しければ反映し 202、alarm を早める。別 repo の配送は無視する", async () => {
  const ctx = await configuredApp();
  const r = await send(ctx.app, "issues", issuePayload(10, { title: "[CI-10] x" }));
  assert.equal(r.status, 202);
  assert.equal(ctx.soon(), 1);
  assert.equal(ctx.store.get<any>("issues", "10").title, "[CI-10] x");
  const other = issuePayload(11);
  (other as any).repository = { full_name: "someone/else" };
  await send(ctx.app, "issues", other);
  assert.equal(ctx.store.get("issues", "11"), undefined);
});

test("webhook 未設定 (App 作成前) は 503 で何もしない", async () => {
  const app = new PmApp({ store: new MemoryStore(), cfg: loadConfig({}), storeKey: STORE_KEY, now: () => T0, fetch: mockFetch([]).f, scheduleSoon: async () => {} });
  assert.equal((await send(app, "issues", issuePayload(1))).status, 503);
});

test("GET /status: 既定は集計だけ (log・would_launch_now・last_error を含まない)。detail は push 権限の token が要る", async () => {
  const ctx = await configuredApp({
    handlers: [
      (c) => (c.url.endsWith("/repos/signature-studio/signature-studio-dev") && c.auth === "Bearer ghp_valid_push_token_x" ? j({ permissions: { push: true } }) : undefined),
      (c) => (c.url.endsWith("/repos/signature-studio/signature-studio-dev") && c.auth === "Bearer ghp_valid_read_token_xx" ? j({ permissions: { push: false } }) : undefined),
    ],
  });
  await send(ctx.app, "issues", issuePayload(10));
  const s = (await (await ctx.app.handle(new Request("https://pm.example/status"))).json()) as any;
  assert.equal(s.mode, "dry-run");
  assert.equal(s.open_issues, 1);
  for (const k of ["log", "would_launch_now", "last_error"]) assert.ok(!(k in s), k);
  assert.ok(!JSON.stringify(s).includes("t10"), "タイトルを含まない");
  const noTok = await ctx.app.handle(new Request("https://pm.example/status?detail=1"));
  assert.equal(noTok.status, 401);
  const readTok = await ctx.app.handle(new Request("https://pm.example/status?detail=1", { headers: { authorization: "Bearer ghp_valid_read_token_xx" } }));
  assert.equal(readTok.status, 401);
  const ok = await ctx.app.handle(new Request("https://pm.example/status?detail=1", { headers: { authorization: "Bearer ghp_valid_push_token_x" } }));
  assert.equal(ok.status, 200);
  assert.ok("log" in ((await ok.json()) as any));
});

test("封印: 同じ平文でも毎回違う暗号文になり、改ざんは復号できない", async () => {
  const a = await sealText(STORE_KEY, "x");
  const b = await sealText(STORE_KEY, "x");
  assert.notEqual(a, b);
  const t = a.slice(0, -2) + (a.endsWith("AA") ? "BB" : "AA");
  await assert.rejects(openText(STORE_KEY, t));
});

test("不明なパスは 404", async () => {
  const ctx = await configuredApp();
  assert.equal((await ctx.app.handle(new Request("https://pm.example/admin"))).status, 404);
});
