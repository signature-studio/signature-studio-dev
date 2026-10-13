#!/usr/bin/env bash
# terms-watch の定期実行 (Web 4 文書。素材不要)。terms-watch.yaml (tools/legal/terms-watch/workflow/ → .github/workflows/) から呼ぶ。
#   bash tools/legal/terms-watch/ci.sh [--tamper <id>]
# 終了コード: 0 全件 UNCHANGED / 1 差分あり / 2 引数不正 / 3 取得失敗・検証不能 / 4 exit 0 だが UNCHANGED 以外が混じる・結果 JSON 不正
# (0 以外は全て job を失敗させる。0 を返すのは「4 件すべてが台帳と一致」を結果 JSON で確認できた時だけ)
# --tamper <id>: 台帳の当該文書の SHA-256 先頭 1 文字を変えた複製で比較する (ネガティブコントロール。台帳本体は書き換えない)
# 環境変数: TW_OUT (出力 dir。既定 $RUNNER_TEMP/terms-watch)・TW_SOURCES / TW_LEDGER (sources.json / 台帳の差替え。ネガコン用)
set -uo pipefail
ROOT="$(git rev-parse --show-toplevel)"
CLI="$ROOT/tools/legal/terms-watch/cli.mjs"
ONLY="fl-tou-web,kilohearts-eula,slate-audiotonix-terms,ni-eula"
OUT="${TW_OUT:-${RUNNER_TEMP:-${TMPDIR:-/tmp}}/terms-watch}"
LEDGER="${TW_LEDGER:-$ROOT/docs/LEGAL_TERMS_LEDGER.json}"
TAMPER=""
case "${1:-}" in
  "") ;;
  --tamper) TAMPER="${2:-}"; [ -n "$TAMPER" ] || { echo "ci.sh: --tamper に id が要る" >&2; exit 2; } ;;
  *) echo "usage: ci.sh [--tamper <id>]" >&2; exit 2 ;;
esac
rm -rf "$OUT"; mkdir -p "$OUT"
finish() { # finish <code>: exit_code を記録して終了 (notify.sh が読む)
  echo "$1" > "$OUT/exit_code"
  [ -n "${GITHUB_OUTPUT:-}" ] && echo "code=$1" >> "$GITHUB_OUTPUT"
  exit "$1"
}

if [ -n "$TAMPER" ]; then
  node -e '
    const fs = require("fs"); const [src, dst, id] = process.argv.slice(1);
    const l = JSON.parse(fs.readFileSync(src, "utf8")); const c = l.docs[id]?.current;
    if (!c) { console.error(`ci.sh: 台帳に ${id} が無い`); process.exit(2); }
    c.sha256 = (c.sha256[0] !== "0" ? "0" : "1") + c.sha256.slice(1);
    fs.writeFileSync(dst, JSON.stringify(l));
  ' "$LEDGER" "$OUT/ledger.tampered.json" "$TAMPER" || finish 2
  LEDGER="$OUT/ledger.tampered.json"
  echo "ci.sh: ネガティブコントロール — 台帳の $TAMPER の SHA-256 先頭 1 文字を改変した複製で比較する"
fi

args=(check --only "$ONLY" --strict --no-write --ledger "$LEDGER" --md "$OUT/unused.md" --snapshots "$OUT/snap" --json "$OUT/result.json")
[ -n "${TW_SOURCES:-}" ] && args+=(--sources "$TW_SOURCES")
node "$CLI" "${args[@]}" 2>&1 | tee "$OUT/log.txt"
code="${PIPESTATUS[0]}"
[ "$code" = 0 ] || finish "$code"

# exit 0 でも、結果 JSON で「対象 4 件すべてが UNCHANGED」を確認できなければ失敗にする (NEW = 台帳に無い、SKIP 等の見逃し防止)
node -e '
  const r = JSON.parse(require("fs").readFileSync(process.argv[1], "utf8")).results;
  const want = process.argv[2].split(",");
  const bad = want.filter((id) => r.find((x) => x.id === id)?.status !== "UNCHANGED");
  if (r.length !== want.length || bad.length) { console.error(`ci.sh: UNCHANGED でない/欠けた文書: ${bad.join(",") || "(件数不一致 " + r.length + ")"}`); process.exit(1); }
' "$OUT/result.json" "$ONLY" || { echo "ci.sh: exit 0 だが結果 JSON が全件 UNCHANGED でない → 失敗扱い (4)" >&2; finish 4; }
finish 0
