# GUI-3 (#174) 環境: 他スクリプトが source する。値は環境変数で上書き可。
# FL_WIN64_DIR: fl-win64 展開先 (tools/shared/env.sh と同名)。capstone/pefile/mingw は PATH 上にあること。
GF_HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
GF_GUI="$(cd "$GF_HERE/.." && pwd)"
GF_M11="$(cd "$GF_GUI/../m11" && pwd)"
GF_W="${GF_W:-$GF_GUI/work/flengine}"
export PATH="${GF_EXTRA_PATH:+$GF_EXTRA_PATH:}$PATH"
# SS_EMSDK_ENV: docs/REFERENCES.md [EMSDK] の emsdk_env.sh (必須)。emsdk_env.sh は EMSDK_ENV を unset するため別名にする。
: "${SS_EMSDK_ENV:?SS_EMSDK_ENV に docs/REFERENCES.md [EMSDK] の emsdk_env.sh を指定してください}"
set +u; . "$SS_EMSDK_ENV" >/dev/null 2>&1 || true; set -u
