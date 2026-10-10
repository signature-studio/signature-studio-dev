#!/usr/bin/env bash
# 既存リソースの一覧スナップショット (Worker 名 / Access app id+名 / service token 名 / R2 バケット名 / zone 名)。読取のみ。
#   bash deploy/probe/snapshot.sh <out.json>        probe 前後で diff を取り「残存 0・既存無変更」を確認する
set -euo pipefail
export PATH="$HOME/.local/share/pnpm/bin:$HOME/.bun/bin:$PATH"
OUT="${1:?out.json}"
mkdir -p "$(dirname "$OUT")"
node -e '
const { execFileSync } = require("node:child_process");
const j = (a) => JSON.parse(execFileSync("cf", a, { encoding: "utf8", maxBuffer: 1 << 28 }));
const arr = (x) => (Array.isArray(x) ? x : x?.result ?? []);
const snap = {
  workers: arr(j(["workers", "scripts", "search", "--name", "", "--per-page", "100"])).map((s) => s.script_name).sort(),
  accessApps: arr(j(["zero-trust", "access", "applications", "list", "--per-page", "100"])).map((a) => `${a.id} ${a.name}`).sort(),
  serviceTokens: arr(j(["zero-trust", "access", "service-tokens", "list"])).map((t) => t.name).sort(),
  r2Buckets: (j(["r2", "buckets", "list"]).buckets ?? []).map((b) => b.name).sort(),
  zones: arr(j(["zones", "list"])).map((z) => z.name).sort(),
};
require("node:fs").writeFileSync(process.argv[1], JSON.stringify(snap, null, 1));
console.log(JSON.stringify(Object.fromEntries(Object.entries(snap).map(([k, v]) => [k, v.length]))));
' "$OUT"
