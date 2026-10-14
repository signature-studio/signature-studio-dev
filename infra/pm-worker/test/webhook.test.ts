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

test("botReport: run-outcome と PM のマーカーを含む bot コメントは報告にせず、botLast だけが更新される", () => {
  const c = (at: string, body: string) => ({ action: "created", issue: { number: 7 }, comment: { user: { login: BOT }, created_at: at, body } });
  let s = send(EMPTY_STATE, "issue_comment", c("2026-10-14T10:00:00Z", "停止します。素材不足: toolchain-emsdk が無い")).state;
  s = send(s, "issue_comment", c("2026-10-14T11:00:00Z", "<!-- oc-run-outcome: no-pr reason=artifact run=1 -->\n素材不足")).state;
  assert.match(s.botLast["7"]?.body ?? "", /oc-run-outcome/);
  assert.equal(s.botReport["7"]?.body, "停止します。素材不足: toolchain-emsdk が無い");
  s = send(s, "issue_comment", c("2026-10-14T12:00:00Z", "<!-- oc-pm-decision: rule=R1 reversible=yes -->")).state;
  assert.equal(s.botReport["7"]?.body, "停止します。素材不足: toolchain-emsdk が無い");
  s = send(s, "issue_comment", c("2026-10-14T13:00:00Z", "報告 2")).state;
  assert.equal(s.botReport["7"]?.body, "報告 2");
});

test("停止印 (oc-fix-limit): 作者は型 Bot かつ github-actions[bot] (markLogin) だけ。実装 App・reviewer・型 User の偽印は信じない (#2639)", () => {
  const c = (login: string, type: string, at = "2026-10-14T10:00:00Z") => ({
    action: "created",
    issue: { number: 7, pull_request: {} },
    comment: { user: { login, type }, created_at: at, body: "上限 <!-- oc-fix-limit --> <!-- oc-pm-intent: stuck pr=7 reason=ceiling -->" },
  });
  const stopOf = (s: PmState) => s.sig["7"]?.stop;
  assert.equal(stopOf(send(EMPTY_STATE, "issue_comment", c(BOT, "Bot")).state), undefined, "実装 App 名義の偽印は信じない");
  assert.equal(stopOf(send(EMPTY_STATE, "issue_comment", c("oc-reviewer-for-signature-studio[bot]", "Bot")).state), undefined, "reviewer 名義の印は信じない");
  assert.equal(stopOf(send(EMPTY_STATE, "issue_comment", c("github-actions[bot]", "User")).state), undefined, "型 User は信じない");
  assert.deepEqual(stopOf(send(EMPTY_STATE, "issue_comment", c("github-actions[bot]", "Bot")).state), { at: "2026-10-14T10:00:00Z", intent: "ceiling" });
  const withMark = (payload: unknown, markLogin: string) => {
    const body = JSON.stringify(payload);
    return handleWebhook(EMPTY_STATE, { secret: SECRET, event: "issue_comment", signature: signBody(SECRET, body), body, botLogin: BOT, markLogin }).state;
  };
  assert.equal(stopOf(withMark(c("github-actions[bot]", "Bot"), "oc-mark-test[bot]")), undefined, "markLogin を変えたら既定の作者は信じない");
  assert.deepEqual(stopOf(withMark(c("oc-mark-test[bot]", "Bot"), "oc-mark-test[bot]")), { at: "2026-10-14T10:00:00Z", intent: "ceiling" });
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
