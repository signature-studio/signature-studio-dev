#!/usr/bin/env bash
# assettrace 1 コマンド検証: 単体 (ネガコン含む) → fixture trace の CLI 実行 → 期待件数照合。
#   bash tools/startup/assettrace/e2e.sh
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
OUT="$(mktemp -d)"; trap 'rm -rf "$OUT"' EXIT

node --test "$HERE/test/assettrace.test.mjs" 2>&1 | grep -E "^# (pass|fail)"

# fixture は RO 違反 (w=true で /fl 書込) を含まないので exit 0 が期待
node "$HERE/assettrace.mjs" --trace "$HERE/test/fixtures/boot.trace.jsonl" --inv "$HERE/test/fixtures/inv.jsonl" \
  --out "$OUT/r.json" --tiers-out "$OUT/tiers.json"

node -e '
const r = JSON.parse(require("fs").readFileSync(process.argv[1]));
const t = JSON.parse(require("fs").readFileSync(process.argv[2]));
const exp = { files: 5, unknown: 1, missing: 1, roWrites: 0 };
for (const k of Object.keys(exp)) if (r[k].length !== exp[k]) { console.error(`FAIL ${k}: ${r[k].length} != ${exp[k]}`); process.exit(1); }
if (Object.values(t).some((v) => v !== "T0") || Object.keys(t).length !== 5) { console.error("FAIL tiers-out"); process.exit(1); }
console.log("[assettrace] e2e PASS (files 5 / unknown 1 / missing 1 / roWrites 0 / tiers-out T0x5)");
' "$OUT/r.json" "$OUT/tiers.json"

# CLI の RO 違反検出 (ネガコン): /fl への書込み open があると exit 1
echo '{"op":"open","path":"/fl/Artwork/x.png","ok":true,"w":true}' > "$OUT/bad.jsonl"
if node "$HERE/assettrace.mjs" --trace "$OUT/bad.jsonl" --inv "$HERE/test/fixtures/inv.jsonl" --out "$OUT/b.json" 2>/dev/null; then
  echo "FAIL: RO 書込みで exit 0" >&2; exit 1
fi
echo "[assettrace] NC (RO write -> exit 1) PASS"
