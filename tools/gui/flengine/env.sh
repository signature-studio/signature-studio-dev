# GUI-3 (#174) 環境: 他スクリプトが source する。値は環境変数で上書き可。
# FL_WIN64_DIR: fl-win64 展開先 (tools/shared/env.sh と同名)。capstone/pefile/mingw は PATH 上にあること。
GF_HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
GF_GUI="$(cd "$GF_HERE/.." && pwd)"
GF_M11="${GF_M11:-$(cd "$GF_GUI/../m11" && pwd)}"   # 読取専用の素材元。e2e.sh は複製先 ($GF_W/tree/m11) を入れる
GF_W="${GF_W:-$GF_GUI/work/flengine}"
export GF_M11 PATH="${GF_EXTRA_PATH:+$GF_EXTRA_PATH:}$PATH"
set +u; . "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1 || true; set -u
