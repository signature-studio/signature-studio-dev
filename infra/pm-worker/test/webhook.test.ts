import { test } from "node:test";
import assert from "node:assert/strict";
import { signBody } from "../src/hmac.ts";
import { EMPTY_STATE, handleWebhook, type PmState } from "../src/webhook.ts";

const SECRET = "test-secret";
const BOT = "opencode-for-signature-studio[bot]";

function send(s: PmState, event: string, payload: unknown, opts: { sig?: string | null; secret?: string } = {}) {
  const body = JSON.stringify(payload);
  const sig = opts.sig === undefined ? signBody(SECRET, body) : opts.sig;
  return handleWebhook(s, { secret: opts.secret ?? SECRET, event, signature: sig, body, botLogin: BOT });
}

const issuePayload = (number: number, updatedAt: string, state = "open", title = `[CI-${number}] t`) => ({
  action: "edited",
  issue: { number, title, body: "b", state, updated_at: updatedAt, labels: [{ name: "x" }] },
});

test("署名が無い・違う・形式違いの入力は 401 で、状態を一切変えない", () => {
  const before = send(EMPTY_STATE, "issues", issuePayload(1, "2026-10-14T10:00:00Z")).state;
  const cases: Array<string | null> = [null, "", "sha256=00", "sha1=abc"];
  for (const sig of cases) {
    const r = send(before, "issues", issuePayload(2, "2026-10-14T11:00:00Z"), { sig });
    assert.equal(r.status, 401);
    assert.equal(r.state, before);
  }
  const body = JSON.stringify(issuePayload(2, "2026-10-14T11:00:00Z"));
  const noHeader = handleWebhook(before, { secret: SECRET, event: "issues", signature: undefined, body, botLogin: BOT });
  assert.equal(noHeader.status, 401);
  assert.equal(noHeader.state, before);
  const wrongKey = send(before, "issues", issuePayload(2, "2026-10-14T11:00:00Z"), { secret: "other" });
  assert.equal(wrongKey.status, 401);
  assert.equal(wrongKey.state, before);
});

test("秘密鍵が空なら、正しく見える署名でも拒否する", () => {
  const r = send(EMPTY_STATE, "issues", issuePayload(1, "2026-10-14T10:00:00Z"), { secret: "" });
  assert.equal(r.status, 401);
});

test("未知のイベントは検証後に無視し、状態を変えない", () => {
  const r = send(EMPTY_STATE, "push", { any: 1 });
  assert.equal(r.status, 202);
  assert.equal(r.reason, "ignored");
  assert.equal(r.state, EMPTY_STATE);
});

test("issues: 増分に反映し、古い更新は無視する", () => {
  let s = send(EMPTY_STATE, "issues", issuePayload(1, "2026-10-14T10:00:00Z", "open", "[CI-1] new")).state;
  assert.equal(s.issues["1"]?.title, "[CI-1] new");
  s = send(s, "issues", issuePayload(1, "2026-10-14T09:00:00Z", "closed", "[CI-1] old")).state;
  assert.equal(s.issues["1"]?.title, "[CI-1] new");
  assert.equal(s.issues["1"]?.state, "open");
  s = send(s, "issues", issuePayload(1, "2026-10-14T11:00:00Z", "closed")).state;
  assert.equal(s.issues["1"]?.state, "closed");
});

test("issues: PR を issues イベントで受けても issue として登録しない", () => {
  const p = { action: "edited", issue: { number: 5, title: "pr", body: "", state: "open", updated_at: "2026-10-14T10:00:00Z", labels: [], pull_request: {} } };
  const s = send(EMPTY_STATE, "issues", p).state;
  assert.equal(s.issues["5"], undefined);
});

test("issue_comment: bot の最後のコメントだけを botLast に反映する", () => {
  const c = (login: string, at: string, body: string) => ({
    action: "created",
    issue: { number: 7 },
    comment: { user: { login }, created_at: at, body },
  });
  let s = send(EMPTY_STATE, "issue_comment", c(BOT, "2026-10-14T10:00:00Z", "着手")).state;
  s = send(s, "issue_comment", c("pycabbage", "2026-10-14T11:00:00Z", "人間のコメント")).state;
  assert.equal(s.botLast["7"]?.body, "着手");
  s = send(s, "issue_comment", c(BOT, "2026-10-14T12:00:00Z", "停止します")).state;
  assert.equal(s.botLast["7"]?.body, "停止します");
  s = send(s, "issue_comment", c(BOT, "2026-10-14T09:00:00Z", "古い")).state;
  assert.equal(s.botLast["7"]?.body, "停止します");
});

test("pull_request / pull_request_review: PR を増分に反映する", () => {
  const pr = (number: number, updatedAt: string, state: string, merged: boolean) => ({
    action: "synchronize",
    pull_request: {
      number,
      state,
      merged_at: merged ? "2026-10-14T10:00:00Z" : null,
      draft: false,
      head: { ref: "9-x" },
      title: "t",
      body: "Closes #9",
      updated_at: updatedAt,
    },
  });
  let s = send(EMPTY_STATE, "pull_request", pr(20, "2026-10-14T10:00:00Z", "open", false)).state;
  assert.equal(s.prs["20"]?.ref, "9-x");
  s = send(s, "pull_request_review", { action: "submitted", pull_request: pr(20, "2026-10-14T11:00:00Z", "closed", true).pull_request }).state;
  assert.equal(s.prs["20"]?.state, "closed");
  assert.equal(s.prs["20"]?.merged, true);
});

test("workflow_run: run を増分に反映する", () => {
  const run = (id: number, updatedAt: string, status: string, conclusion: string | null) => ({
    action: "completed",
    workflow_run: { id, event: "issue_comment", display_title: "[CI-1] t", status, conclusion, updated_at: updatedAt },
  });
  let s = send(EMPTY_STATE, "workflow_run", run(555, "2026-10-14T10:00:00Z", "in_progress", null)).state;
  assert.equal(s.runs["555"]?.status, "in_progress");
  s = send(s, "workflow_run", run(555, "2026-10-14T11:00:00Z", "completed", "success")).state;
  assert.equal(s.runs["555"]?.conclusion, "success");
  s = send(s, "workflow_run", run(555, "2026-10-14T09:00:00Z", "queued", null)).state;
  assert.equal(s.runs["555"]?.status, "completed");
});

test("検証済みの入力は 202 applied", () => {
  const r = send(EMPTY_STATE, "issues", issuePayload(3, "2026-10-14T10:00:00Z"));
  assert.equal(r.status, 202);
  assert.equal(r.reason, "applied");
});
