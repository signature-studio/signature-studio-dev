# 環境前提 (CAB-101)。e2e スクリプト自身が source する (呼出し側の export に依存しない・規則 43)。
#   source tools/startup/glue/env.sh
#   bash tools/startup/glue/glue.sh
#
# 見つけた落とし穴 (全て本 dir の e2e で踏んだもの):
#  1. PATH: node が既定 PATH に無い (pnpm の node を使う) → ~/.local/share/pnpm/bin を追加。
#  2. TMPDIR 未設定だと /tmp (tmpfs 3.7GB)。emcc の一時ファイルが溢れたので <dir>/work/tmp を使う。
#  3. emcc は EXPORTED_FUNCTIONS を **明示すると callMain を落とす** (実測: callMain 2→0)。
#     unit リンクでは _main を EXPORTED_FUNCTIONS に足す (host/build.sh 参照)。
#  4. Emscripten の EXPORT("name") 付き関数 (pump の *_e 群) は export_name が JS 名を決める。
#     C 内部シンボルと export_name が衝突する組 (pump_calibrate / pump_clock_offset /
#     pump_clock_calibrated) は C シンボル名側 (_e 付き) を EXPORTED_FUNCTIONS に書く。
#  5. TypeScript 直実行は node >= 24 (本repo は node 26)。wvfs/regbridge/pathmap は .ts/.mjs を直接 import。
export PATH="$HOME/.local/share/pnpm/bin:$PATH"
GLUE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" && pwd)"
export TMPDIR="$GLUE_DIR/work/tmp"
mkdir -p "$TMPDIR"
echo "[glue] env: PATH+=~/local/share/pnpm/bin TMPDIR=$TMPDIR (実ディスク)"
