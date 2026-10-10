#!/usr/bin/env node
// Cloudflare Access: R2 カスタムドメインのホスト名に対する Self-hosted App (Worker 不要)。
//   - 人間: メール allow ポリシー (ACCESS_ALLOW_EMAILS もしくは ACCESS_ALLOW_EMAIL_DOMAIN)
//   - E2E/CI: service token + non_identity ポリシー (CF-Access-Client-Id/Secret ヘッダ)
//
// 重要: カスタムドメインを R2 に接続する *前* に Access App を作ること
//       (先に接続すると bucket が一時的に公開される。deploy.sh は順序を保証する)。
//
//   node deploy/scripts/40-access.mjs --host studio.example.com [mode]
//   mode: (既定) 作成予定の JSON を表示 | --dry-run (cf --dry-run, 既存は読取) | --apply
import { chmodSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { cf } from "../lib/cf.mjs";

const args = process.argv.slice(2);
const opt = (n, d) => {
  const i = args.indexOf(`--${n}`);
  return i >= 0 ? args[i + 1] : d;
};
const has = (n) => args.includes(`--${n}`);
const host = opt("host", process.env.CF_HOSTNAME);
if (!host) throw new Error("--host (または CF_HOSTNAME) が必要");
const mode = has("apply") ? "apply" : has("dry-run") ? "dry-run" : "print";
const emails = (opt("emails", process.env.ACCESS_ALLOW_EMAILS) ?? "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);
const emailDomain = process.env.ACCESS_ALLOW_EMAIL_DOMAIN;
const tokenName = opt("service-token", process.env.ACCESS_SERVICE_TOKEN_NAME ?? "webstudio-e2e");
const appName = opt("app-name", process.env.ACCESS_APP_NAME ?? `webstudio (${host})`);
const sessionDuration = process.env.ACCESS_SESSION_DURATION ?? "24h";

const include = [
  ...emails.map((email) => ({ email: { email } })),
  ...(emailDomain ? [{ email_domain: { domain: emailDomain } }] : []),
];
if (!include.length) {
  throw new Error(
    "人間用 allow 対象が無い: ACCESS_ALLOW_EMAILS=a@x,b@y もしくは ACCESS_ALLOW_EMAIL_DOMAIN=example.com",
  );
}

const policyHuman = {
  name: `webstudio-allow (${host})`,
  decision: "allow",
  include,
  exclude: [],
  require: [],
};
const policyToken = (tokenId) => ({
  name: `webstudio-e2e-token (${host})`,
  decision: "non_identity",
  include: [{ service_token: { token_id: tokenId } }],
  exclude: [],
  require: [],
});
const appBody = (policyIds) => ({
  name: appName,
  type: "self_hosted",
  destinations: [{ type: "public", uri: host }],
  session_duration: sessionDuration,
  app_launcher_visible: false,
  http_only_cookie_attribute: true,
  policies: policyIds.map((id, i) => ({ id, precedence: i + 1 })),
});

if (mode === "print") {
  console.log(
    JSON.stringify(
      {
        policyHuman,
        policyToken: policyToken("<token-id>"),
        app: appBody(["<human-policy-id>", "<token-policy-id>"]),
      },
      null,
      2,
    ),
  );
  process.exit(0);
}
const dry = mode === "dry-run" ? ["--dry-run"] : [];
const listOf = (r) => (Array.isArray(r) ? r : r?.result ?? []);

async function upsert(kind, listCmd, createCmd, updateCmd, finder, body) {
  const cur = finder(listOf(await cf(listCmd)));
  if (cur) {
    const r = await cf([...updateCmd, cur.id, "--body", JSON.stringify(body), ...dry]);
    console.log(`  ${kind}: 更新 (${cur.id.slice(0, 8)}…)${mode === "dry-run" ? " (dry-run)" : ""}`);
    return mode === "dry-run" ? cur : r;
  }
  const r = await cf([...createCmd, "--body", JSON.stringify(body), ...dry]);
  console.log(`  ${kind}: 新規作成${mode === "dry-run" ? " (dry-run)" : ""}`);
  return mode === "dry-run" ? { id: `<${kind}-id>` } : r;
}

console.log(`## Access [${mode}] host=${host}`);

// service token (client secret は作成時の 1 回のみ返る -> 0600 ファイルへ)
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
    writeFileSync(f, JSON.stringify({ client_id: r.client_id, client_secret: r.client_secret }), {
      mode: 0o600,
    });
    chmodSync(f, 0o600);
    console.log(
      `  service-token: 新規作成。secret は ${f} (0600, gitignore 済み)。E2E_ACCESS_CLIENT_ID/SECRET へ`,
    );
  }
} else {
  console.log(`  service-token: 既存 (${tok.id.slice(0, 8)}…) — secret は再取得不可。紛失時は rotate`);
}

const P = ["zero-trust", "access", "policies"];
const human = await upsert(
  "policy-human", [...P, "list"], [...P, "create"], [...P, "update"],
  (l) => l.find((p) => p.name === policyHuman.name), policyHuman,
);
const token = await upsert(
  "policy-token", [...P, "list"], [...P, "create"], [...P, "update"],
  (l) => l.find((p) => p.name === policyToken("").name), policyToken(tok.id),
);
const A = ["zero-trust", "access", "applications"];
await upsert(
  "application", [...A, "list"], [...A, "create"], [...A, "update"],
  (l) => l.find((a) => (a.destinations ?? []).some((d) => d.uri === host) || a.domain === host),
  appBody([human.id, token.id]),
);
console.log("完了。次: R2 カスタムドメイン接続 (50-domain.sh) — Access が先に存在すること");
