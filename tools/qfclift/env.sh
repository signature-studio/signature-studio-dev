# qfclift 環境 (e2e が source する)。FL_WIN64_DIR は `tar --zstd -xf fl-win64.tar.zst -C <dir>` の <dir>。
QFC="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$QFC/../shared/env.sh"
[ -d /opt/emsdk ] && source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
QFC_PE="${QFC_PE:-$FL_WIN64_DIR/extracted/block24350_PE.bin}"   # QuickFontCache_x64.dll (block24350)
QFC_PY="${QFC_PY:-python3}"                                      # capstone + pefile が入った python
export QFC QFC_PE QFC_PY
