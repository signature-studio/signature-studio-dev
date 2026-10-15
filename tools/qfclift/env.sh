# qfclift 環境 (e2e が source する)。FL_WIN64_DIR は `tar --zstd -xf fl-win64.tar.zst -C <dir>` の <dir>。
QFC="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$QFC/../shared/env.sh"
[ -d /opt/emsdk ] && source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
QFC_PE="${QFC_PE:-$FL_WIN64_DIR/extracted/block24350_PE.bin}"   # QuickFontCache_x64.dll (block24350)
QFC_PY="${QFC_PY:-python3}"                                      # capstone + pefile が入った python
FT_SRC_INC="$QFC/../shared/work/src/freetype-2.7/include"        # FreeType 2.7 ヘッダ (build.sh が展開)
FT_WASM32_LIB="$QFC/../shared/work/build/freetype/wasm32/src/objs/.libs/libfreetype.a"   # build.sh の wasm32 成果物
export QFC QFC_PE QFC_PY FT_SRC_INC FT_WASM32_LIB
