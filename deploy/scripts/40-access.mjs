#!/usr/bin/env node
// Cloudflare Access: Worker 単位 (destination.type="worker") の Self-hosted App + E2E 用 service token (冪等 upsert)。
//   - worker 型は workers.dev の本番 URL / version preview URL / 将来追加するカスタムドメインを全て保護する (tools/hosting 実測)。
//     hostname 型は <ver>-<name>.<sub>.workers.dev の preview が 200 素通しになるため使わない。
//   - 人間: メール allow (ACCESS_ALLOW_EMAILS / ACCESS_ALLOW_EMAIL_DOMAIN)。E2E/CI: service token + non_identity ポリシー。
//   - **Worker が存在してから**作る (worker_id が必要)。deploy は 20-worker.mjs --phase closed -> 本スクリプト -> --phase open の順。
//
//   node deploy/scripts/40-access.mjs [--name signature-studio] [--emails a@x,b@y] [mode]
//   mode: (既定) 作成予定 JSON を表示 | --dry-run (cf --dry-run、既存は読取のみ) | --apply
import { chmodSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { cf } from "../lib/cf.mjs";

const args = process.argv.slice(2);
const opt = (n, d) => {
  const i = args.indexOf(`--${n}`);
  return i >= 0 ? args[i + 1] : d;
};
const has = (n) => args.includes(`--${n}`);
const name = opt("name", process.env.WORKER_NAME ?? "signature-studio");
const mode = has("apply") ? "apply" : has("dry-run") ? "dry-run" : "print";
const emails = (opt("emails", process.env.ACCESS_ALLOW_EMAILS) ?? "").split(",").map((s) => s.trim()).filter(Boolean);
const emailDomain = process.env.ACCESS_ALLOW_EMAIL_DOMAIN;
const tokenName = opt("service-token", process.env.ACCESS_SERVICE_TOKEN_NAME ?? `${name}-e2e`);
const sessionDuration = process.env.ACCESS_SESSION_DURATION ?? "24h";

// 人間用 allow: メール指定 (ACCESS_ALLOW_EMAILS / ACCESS_ALLOW_EMAIL_DOMAIN) が無ければ
// include: Everyone =「ログイン必須・この Zero Trust 組織のユーザならログイン可」(ユーザ決定 2026-10-10)。
// ログイン必須は Access 自体の挙動 (未認証リクエストは IdP ログインへ 302)。service token (non_identity) のみ認証を省略する。
// ACCESS_ALLOW_EVERYONE=1 でメール指定と Everyone の併用可 (組織ユーザ + 特定外部メール)。
// 後日メール許可リストに絞る手順は RUNBOOK.md §4 (メール許可リストの追加)。
let include = [
  ...emails.map((email) => ({ email: { email } })),
  ...(emailDomain ? [{ email_domain: { domain: emailDomain } }] : []),
];
if (!include.length || process.env.ACCESS_ALLOW_EVERYONE === "1") include.push({ everyone: {} });
const listOf = (r) => (Array.isArray(r) ? r : r?.result ?? []);
const dry = mode === "dry-run" ? ["--dry-run"] : [];

const appBody = (workerId, tokenId) => ({
  name,
  type: "self_hosted",
  destinations: [{ type: "worker", worker_id: workerId }],
  session_duration: sessionDuration,
  app_launcher_visible: false,
  policies: [
    { name: `${name}-allow`, decision: "allow", include },
    { name: `${name}-e2e-token`, decision: "non_identity", include: [{ service_token: { token_id: tokenId } }] },
  ],
});

if (mode === "print") {
  console.log(JSON.stringify(appBody("<worker-id: cf workers scripts search --name " + name + ">", "<service-token-id>"), null, 2));
  process.exit(0);
}

console.log(`## Access [${mode}] worker=${name}`);
console.log(`  人間 allow: ${[emails.length ? `email ${emails.length} 件` : "", emailDomain ? `email_domain ${emailDomain}` : "", (process.env.ACCESS_ALLOW_EVERYONE === "1" || (!emails.length && !emailDomain)) ? "everyone" : ""].filter(Boolean).join(" + ") || "なし"} / service token: ${tokenName}`);
const workers = listOf(await cf(["workers", "scripts", "search", "--name", name, "--per-page", "100"]));
const worker = workers.find((w) => w.script_name === name);
if (!worker && mode === "apply") throw new Error(`Worker ${name} が無い: 先に 20-worker.mjs --phase closed を実行する`);
const workerId = worker?.id ?? "<worker-id>";
console.log(`  worker: ${worker ? `${name} (${worker.id.slice(0, 8)}…)` : "未作成 (dry-run: placeholder)"}`);

// service token: client secret は作成時の 1 回しか返らない -> 0600 ファイル (deploy/work/secrets, gitignore 済み)
const toks = listOf(await cf(["zero-trust", "access", "service-tokens", "list"]));
let tok = toks.find((t) => t.name === tokenName);
if (!tok) {
  const r = await cf([
    "zero-trust", "access", "service-tokens", "create",
    "--name", tokenName,
    "--duration", process.env.ACCESS_SERVICE_TOKEN_DURATION ?? "8760h",
    ...dry,
  ]);
  if (mode === "dry-run") {
    tok = { id: "<token-id>" };
    console.log(`  service-token: 新規作成 (dry-run) name=${tokenName}`);
  } else {
    tok = r;
    const dir = path.resolve(import.meta.dirname, "../work/secrets");
    mkdirSync(dir, { recursive: true, mode: 0o700 });
    const f = path.join(dir, `${tokenName}.json`);
    writeFileSync(f, JSON.stringify({ client_id: r.client_id, client_secret: r.client_secret }), { mode: 0o600 });
    chmodSync(f, 0o600);
    console.log(`  service-token: 新規作成。secret は ${f} (0600, gitignore 済み)`);
  }
} else {
  console.log(`  service-token: 既存 (${tok.id.slice(0, 8)}…) — secret は再取得不可。紛失時は rotate/再作成`);
}

const A = ["zero-trust", "access", "applications"];
const apps = listOf(await cf([...A, "list", "--per-page", "100"]));
const cur = apps.find((a) => a.name === name || (a.destinations ?? []).some((d) => d.type === "worker" && d.worker_id === workerId));
const body = appBody(workerId, tok.id);
if (cur) {
  await cf([...A, "update", cur.id, "--body", JSON.stringify(body), ...dry]);
  console.log(`  application: 更新 (${cur.id.slice(0, 8)}…)${dry.length ? " (dry-run)" : ""}`);
} else {
  const r = await cf([...A, "create", "--body", JSON.stringify(body), ...dry]);
  console.log(`  application: 新規作成${dry.length ? " (dry-run)" : ` (${String(r?.id).slice(0, 8)}…)`}`);
}
console.log("完了。次: 20-worker.mjs --phase open (公開 URL を出す) -> 90-verify.sh");
