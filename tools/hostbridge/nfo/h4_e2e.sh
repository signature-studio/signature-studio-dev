#!/usr/bin/env bash
# CAB-216 (HB-H4') 1 コマンド e2e: generateDb() → pathreg → wvfs 仮想 FS 結線の実行検証。
#   bash tools/hostbridge/nfo/h4_e2e.sh [--fresh] [--keep] [--no-chrome]
#
# 検証 5 段 (チケット要件):
#   ① 生成 (OTT + Serum 2 gen/FX + Massive X + Kilohearts 45 + Fresh Air = 50 entry / 102 ファイル)
#   ② 仮想 FS 書込 (createPathRouter().route() → /c/home 配下 mkdirp + writeFileSync)
#   ③ nfo reader (fle:0x910cd0 準拠) + tools/flp 独立パーサ round-trip (831/831 は nfo_e2e.sh と共有 work/metrics.json)
#   ④ 仮想 FS 再読込一致 (sha256 + 大文字小文字変え読み + 余剰 0)
#   ⑤ kill/reload 永続 (別プロセス + SIGKILL、flush 点契約 onYield/onPageHide)
#   ⑥ vreg seed (HKCU Software\Image-Line\Shared\Paths\Shared data) との整合
#   ⑦ Chrome (OPFS, 実ディスクプロファイル) での SIGKILL 越え永続 + flush 点陰性対照
#   ⑧ 独立再計算 (h4_recount.mjs — 別アルゴリズム)
#
# 規約: 書込は tools/hostbridge/nfo のみ。tools/assets・tools/shimx・tools/startup は読取専用。
set -euo pipefail
cd "$(dirname "$0")"
ARGS=()
for a in "$@"; do case "$a" in
  --fresh|--keep|--no-chrome) ARGS+=("$a") ;;
  *) echo "usage: $0 [--fresh] [--keep] [--no-chrome]" >&2; exit 2 ;;
esac; done
export PATH="$HOME/.local/share/pnpm/bin:$HOME/.bun/bin:$PATH"
command -v node >/dev/null || { echo "node not found"; exit 2; }
mkdir -p work/tmp
export TMPDIR="$PWD/work/tmp"
command -v google-chrome >/dev/null || CHROME=:
echo "== h4_e2e (Chrome: ${CHROME:-google-chrome})"
node h4/h4_e2e.ts "${ARGS[@]+"${ARGS[@]}"}"
