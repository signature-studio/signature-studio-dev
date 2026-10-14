import { test } from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { rmSync } from "node:fs";
import { signBody } from "../src/hmac.ts";
import { receiveWebhook, type WebhookEnv } from "../src/route.ts";
import type { SqlCursor, StorageLike } from "../src/store.ts";

const SECRET = "test-secret";
const BOT = "opencode-for-signature-studio[bot]";
const ENV: WebhookEnv = { webhookSecret: SECRET, botLogin: BOT };

// DO の ctx.storage 相当。node:sqlite を使い、実行された書き込み SQL を数える。
function openStorage(file: string) {
  const db = new DatabaseSync(file);
  const writes = { count: 0 };
  const storage: StorageLike = {
    sql: {
      exec(query, ...bindings) {
        const isRead = /^\s*SELECT/i.test(query);
        if (!isRead) writes.count++;
        const stmt = db.prepare(query);
        const rows = isRead ? (stmt.all(...(bindings as never[])) as Record<string, unknown>[]) : (stmt.run(...(bindings as never[])), []);
        const cursor: SqlCursor = { toArray: () => rows };
        return cursor;
      },
    },
    transactionSync(fn) {
      db.exec("BEGIN");
      try {
        const r = fn();
        db.exec("COMMIT");
        return r;
      } catch (e) {
        db.exec("ROLLBACK");
        throw e;
      }
    },
  };
  return { storage, writes, close: () => db.close() };
}

function req(event: string, payload: unknown, sig?: string | null) {
  const body = JSON.stringify(payload);
  const headers = new Headers({ "X-GitHub-Event": event });
  const s = sig === undefined ? signBody(SECRET, body) : sig;
  if (s !== null) headers.set("X-Hub-Signature-256", s);
  return { headers, body };
}

const issue = (number: number, updatedAt: string, title = `[CI-${number}] t`) => ({
  action: "edited",
  issue: { number, title, body: "b", state: "open", updated_at: updatedAt, labels: [] },
});

test("401 のとき storage に一切書き込まない (DDL も含む)", () => {
  const { storage, writes, close } = openStorage(":memory:");
  try {
    const r = req("issues", issue(1, "2026-10-14T10:00:00Z"), "sha256=00");
    const res = receiveWebhook(storage, ENV, r.headers, r.body);
    assert.equal(res.status, 401);
    assert.equal(writes.count, 0);
    const none = req("issues", issue(1, "2026-10-14T10:00:00Z"), null);
    assert.equal(receiveWebhook(storage, ENV, none.headers, none.body).status, 401);
    const wrong = req("issues", issue(1, "2026-10-14T10:00:00Z"));
    assert.equal(receiveWebhook(storage, { ...ENV, webhookSecret: "other" }, wrong.headers, wrong.body).status, 401);
    assert.equal(writes.count, 0);
  } finally {
    close();
  }
});

test("検証済みの配送を増分保存し、再起動 (新しい接続) 後も同じ状態を読める", () => {
  const dir = process.env.TMPDIR ?? "/tmp";
  const file = `${dir}/pm-worker-route-${process.pid}-${Date.now()}.db`;
  const a = openStorage(file);
  try {
    const r1 = req("issues", issue(1, "2026-10-14T10:00:00Z"));
    assert.equal(receiveWebhook(a.storage, ENV, r1.headers, r1.body).status, 202);
    const c = { action: "created", issue: { number: 1 }, comment: { user: { login: BOT }, created_at: "2026-10-14T11:00:00Z", body: "着手" } };
    const r2 = req("issue_comment", c);
    receiveWebhook(a.storage, ENV, r2.headers, r2.body);
    const pr = { action: "opened", pull_request: { number: 9, state: "open", merged_at: null, draft: false, head: { ref: "1-x" }, title: "t", body: "Closes #1", updated_at: "2026-10-14T12:00:00Z" } };
    const r3 = req("pull_request", pr);
    receiveWebhook(a.storage, ENV, r3.headers, r3.body);
  } finally {
    a.close();
  }
  const b = openStorage(file);
  try {
    const rows = b.storage.sql.exec("SELECT kind, key FROM pm_entities ORDER BY kind, key").toArray();
    assert.deepEqual(
      rows.map((r) => `${r.kind}:${r.key}`),
      ["bot_last:1", "issue:1", "pr:9"],
    );
    const bl = b.storage.sql.exec("SELECT json FROM pm_entities WHERE kind = 'bot_last'").toArray()[0];
    assert.equal(JSON.parse(String(bl.json)).body, "着手");
    const noop = req("issues", issue(1, "2026-10-14T10:00:00Z"));
    assert.equal(receiveWebhook(b.storage, ENV, noop.headers, noop.body).status, 202);
  } finally {
    b.close();
    rmSync(file, { force: true });
  }
});

test("同じ配送を 2 回受けても状態・保存内容が変わらない (冪等)", () => {
  const { storage, writes, close } = openStorage(":memory:");
  try {
    const r = req("issues", issue(2, "2026-10-14T10:00:00Z", "[CI-2] once"));
    receiveWebhook(storage, ENV, r.headers, r.body);
    const first = storage.sql.exec("SELECT kind, key, json FROM pm_entities ORDER BY kind, key").toArray();
    const before = writes.count;
    const again = receiveWebhook(storage, ENV, r.headers, r.body);
    const second = storage.sql.exec("SELECT kind, key, json FROM pm_entities ORDER BY kind, key").toArray();
    assert.deepEqual(second, first);
    assert.equal(again.status, 202);
    // 2 回目は差分 0 なので書き込み SQL は DDL (CREATE TABLE IF NOT EXISTS) のみ
    assert.equal(writes.count - before, 1);
  } finally {
    close();
  }
});
