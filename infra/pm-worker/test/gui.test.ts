import { test } from "node:test";
import assert from "node:assert/strict";
import { GUI_HTML, GUI_MAX_BYTES, guiResponse } from "../src/gui.ts";

const NONCE_RE = /nonce-([A-Za-z0-9_-]+)/;

test("GET /: HTML と既定のヘッダ・nonce が応答ごとに異なる", async () => {
  const a = guiResponse("GET");
  const b = guiResponse("GET");
  assert.equal(a.status, 200);
  assert.equal(a.headers.get("content-type"), "text/html; charset=utf-8");
  const csp = a.headers.get("content-security-policy") ?? "";
  const nonce = NONCE_RE.exec(csp)?.[1] ?? "";
  assert.ok(nonce.length >= 16, "nonce が付く");
  assert.equal(csp, `default-src 'none'; script-src 'nonce-${nonce}'; style-src 'nonce-${nonce}'; connect-src 'self'; img-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`);
  assert.equal(a.headers.get("x-content-type-options"), "nosniff");
  assert.equal(a.headers.get("referrer-policy"), "no-referrer");
  assert.equal(a.headers.get("cache-control"), "no-store");
  const body = await a.text();
  assert.equal(body.split(`nonce="${nonce}"`).length - 1, 2, "style と script の 2 か所に同じ nonce");
  assert.ok(!body.includes("__NONCE__"));
  assert.ok(new TextEncoder().encode(body).length <= GUI_MAX_BYTES, "40KB 以内");
  const csp2 = NONCE_RE.exec(b.headers.get("content-security-policy") ?? "")?.[1];
  assert.notEqual(csp2, nonce, "nonce は応答ごとに変わる");
  assert.notEqual(NONCE_RE.exec(csp)?.[1], csp2);
});

test("HEAD /: 同じヘッダで本文なし", async () => {
  const g = guiResponse("GET");
  const h = guiResponse("HEAD");
  assert.equal(h.status, 200);
  assert.equal(await h.text(), "");
  assert.equal(h.headers.get("content-type"), g.headers.get("content-type"));
  assert.match(h.headers.get("content-security-policy") ?? "", /script-src 'nonce-/);
  await g.text();
});

test("POST / などは 405 と Allow", async () => {
  for (const m of ["POST", "PUT", "DELETE", "PATCH"]) {
    const r = guiResponse(m);
    assert.equal(r.status, 405, m);
    assert.equal(r.headers.get("allow"), "GET, HEAD", m);
    await r.text();
  }
});

test("外部参照が無い: http(s)://・// は GitHub のリンク 1 件だけ、外部の読み込み要素が無い", () => {
  const allowed = "https://github.com/signature-studio/signature-studio-dev";
  assert.equal(GUI_HTML.split("http://").length - 1, 0, "http:// は無い");
  assert.equal(GUI_HTML.split(allowed).length - 1, 1, "GitHub のリンクは 1 件");
  assert.equal(GUI_HTML.split("//").length - 1, 1, "// は GitHub のリンクの中だけ");
  assert.doesNotMatch(GUI_HTML, /<(img|link|iframe|object|embed|base|form|source|video|audio|svg)\b/i);
  assert.doesNotMatch(GUI_HTML, /<script\b[^>]*\bsrc=/i);
  assert.doesNotMatch(GUI_HTML, /@import|url\(|@font-face/);
  assert.doesNotMatch(GUI_HTML, /\son[a-z]+\s*=/i, "インラインのイベント属性が無い");
  assert.doesNotMatch(GUI_HTML, /\sstyle\s*=/i, "style 属性は使わない (nonce の style-src と両立させるため CSSOM で設定)");
});

test("描画に危険な API を使わない (静的検査)", () => {
  const script = /<script nonce="[^"]+">([\s\S]*?)<\/script>/.exec(GUI_HTML)?.[1] ?? "";
  assert.ok(script.length > 0, "script がある");
  assert.doesNotMatch(script, /innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\b|new Function|setAttribute|srcdoc/);
  assert.doesNotMatch(script, /`/, "テンプレート文字列を使わない");
});

// 偽 DOM: textContent と子要素だけを持つ。innerHTML への代入は違反として記録する。
// 値が要素として解釈される (img や script が生える) ことが無いこと、値が textContent として出ることを確かめる。
function fakeDom(html: string) {
  const violations: string[] = [];
  const created: FakeEl[] = [];
  class FakeEl {
    tagName: string;
    className = "";
    style: Record<string, string> = {};
    hidden = false;
    children: FakeEl[] = [];
    private text = "";
    constructor(tag: string) {
      this.tagName = tag.toLowerCase();
      created.push(this);
    }
    get textContent(): string {
      return this.text + this.children.map((c) => c.textContent).join("");
    }
    set textContent(v: string) {
      this.text = String(v);
      this.children = [];
    }
    set innerHTML(_v: string) {
      violations.push("innerHTML");
      throw new Error("innerHTML is not allowed");
    }
    appendChild(c: FakeEl): FakeEl {
      this.children.push(c);
      return c;
    }
    addEventListener(): void {}
  }
  const byId = new Map<string, FakeEl>();
  for (const m of html.matchAll(/ id="([^"]+)"/g)) byId.set(m[1], new FakeEl("span"));
  const listeners: Array<() => void> = [];
  const doc = {
    visibilityState: "visible",
    getElementById: (id: string) => byId.get(id) ?? null,
    createElement: (tag: string) => new FakeEl(tag),
    addEventListener: (_t: string, f: () => void) => listeners.push(f),
  };
  return { doc, byId, created, violations, FakeEl };
}

async function runPage(payload: unknown, status = 200) {
  const html = GUI_HTML.split("__NONCE__").join("nonce0123456789abcd");
  const script = /<script nonce="[^"]+">([\s\S]*?)<\/script>/.exec(html)?.[1] ?? "";
  const dom = fakeDom(html);
  const timers: Array<() => void> = [];
  const f = async () => ({ ok: status === 200, status, json: async () => payload });
  const run = new Function("document", "fetch", "setInterval", "clearInterval", "navigator", script);
  run(dom.doc, f, (fn: () => void) => (timers.push(fn), timers.length), () => {}, {});
  for (let i = 0; i < 5; i++) await new Promise((r) => setImmediate(r));
  return dom;
}

const EVIL = `<img src=x onerror="alert(1)"><script>alert(2)</script>"><b>`;

test("悪意のある値は DOM の要素にならず textContent として出る (偽 DOM で描画を実行)", async () => {
  const payload = {
    mode: "live",
    mode_launch: "live",
    mode_dispatch: "live",
    configured: true,
    pm_bot_login: EVIL,
    fresh: true,
    phase: EVIL,
    launch_stop: EVIL,
    last_tick: new Date().toISOString(),
    last_dispatch_at: null,
    last_webhook_at: null,
    last_full_sync: null,
    last_reconcile: null,
    last_watchdog: null,
    active_all: 3,
    target: 58,
    room: 55,
    ready: 0,
    started: 1,
    blocked: 0,
    user: 2,
    stopped: 4,
    recent: 0,
    counters: { launched: 5, dispatched: 6, pmDispatched: 0, wouldLaunch: 0, wouldDispatch: 0, reconciles: 9 },
    rest_remaining: 4000,
    rest_used: 1000,
    rest_reset_at: null,
    sync_truncated: [{ name: EVIL, pages: 150, at: "x" }],
    pm_detected: { [EVIL]: 1 },
    running: { in_progress: 3 },
    [EVIL]: EVIL,
  };
  const dom = await runPage(payload);
  assert.equal(dom.violations.length, 0, "innerHTML は使われていない");
  assert.equal(dom.byId.get("band")?.hidden, true, "描画が例外で止まっていない (取得失敗の帯が出ない)");
  for (const el of dom.created) assert.ok(["div", "span"].includes(el.tagName), `作られた要素は div/span だけ (実際: ${el.tagName})`);
  assert.equal(dom.byId.get("v-pm_bot_login")?.textContent, EVIL);
  assert.equal(dom.byId.get("b-phase")?.textContent, `phase: ${EVIL}`);
  assert.equal(dom.byId.get("b-stop")?.textContent, `launch_stop: ${EVIL}`);
  assert.match(dom.byId.get("v-sync_truncated")?.textContent ?? "", /<img src=x/);
  assert.equal(dom.byId.get("cfg")?.hidden, true, "configured=true なら未設定の案内は出ない");
  assert.match(dom.byId.get("unknown")?.textContent ?? "", /未表示のキー: /);
  assert.equal(dom.byId.get("cap-n")?.textContent, "3 / 60");
  assert.equal(dom.byId.get("b-fresh")?.className, "badge ok");
  assert.equal(dom.byId.get("b-stop")?.className, "badge bad");
  assert.equal(dom.byId.get("v-c-reconciles")?.textContent, "9");
  assert.equal(dom.byId.get("rest-n")?.textContent, "4000 / 5000");
});

test("未設定 (configured=false) は案内を出す。取得失敗は帯で示す", async () => {
  const unconfigured = await runPage({ configured: false, mode: "dry-run" });
  assert.equal(unconfigured.byId.get("cfg")?.hidden, false);
  const failed = await runPage({}, 500);
  assert.equal(failed.byId.get("band")?.hidden, false);
  assert.equal(failed.byId.get("band-msg")?.textContent.startsWith("取得失敗 (HTTP 500)"), true);
});
