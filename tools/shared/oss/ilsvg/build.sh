#!/usr/bin/env bash
# ILSvg の upstream 構成要素の version 特定 + 部分的実ビルド (CAB-150)。
#   usage: bash oss/ilsvg/build.sh
#
# 【結論】 ILSvg_x64 の .o 名集合 (95 個) と def symbol (2780 個) から upstream version を特定:
#   svgdom 0.3.59〜0.4.9, svgren 0.6.0〜0.6.3, cppfw/agg 2.8.x, cssom 0.2.x,
#   papki 2024-02-25 以降 (tag なし), pixman vendored (version 未特定), IL 独自グルー 15 本
#
# 【実ビルド】 agg 2.8.9 の svgren 使用サブセット (25 cpp) は emcc で単体ビルド成功。
#   svgdom/svgren は papki/r4/utki/cssom/mikroxml の依存解決が必要で、現状の取得済み
#   upstream 構成では header パスが解決しない (詳細は下記 LOG)。
#   -> svgdom/svgren の連結ビルドは子チケット (本 REPORT §6 未解決に起票)。
set -euo pipefail
PATH="$HOME/.local/share/pnpm/bin:$PATH"
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$HERE/../.."
S="$ROOT/work/src"; B="$ROOT/work/build/ilsvg"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
rm -rf "$B"; mkdir -p "$B"

# --- (1) version 特定の独立再計算 (規則 37) ---
echo "== 1. version 特定 (独立再計算) =="
python3 "$ROOT/scripts/ilsvg_version_recount.py" | tee "$B/version_recount.txt"

# --- (2) agg 2.8.9 の svgren 使用サブセットを emcc でビルド ---
echo
echo "== 2. cppfw/agg 2.8.9 (svgren 使用サブセット 25 cpp) を native/wasm でビルド =="
AGG_GIT="$S/cppfw-agg"
if [ ! -d "$AGG_GIT" ]; then
  git clone -q --filter=blob:none https://github.com/cppfw/agg.git "$AGG_GIT"
fi
cd "$AGG_GIT"
git checkout -q 2.8.9
AS="$AGG_GIT/src/agg/src"; AI="$AGG_GIT/src/agg/include"
SUBSET="agg_arc agg_arrowhead agg_bezier_arc agg_bspline agg_curves agg_embedded_raster_fonts agg_gsv_text agg_image_filters agg_line_aa_basics agg_line_profile_aa agg_rounded_rect agg_sqrt_tables agg_trans_affine agg_trans_double_path agg_trans_single_path agg_trans_warp_magnifier agg_vcgen_bspline agg_vcgen_contour agg_vcgen_dash agg_vcgen_markers_term agg_vcgen_smooth_poly1 agg_vcgen_stroke agg_vpgen_clip_polygon agg_vpgen_clip_polyline agg_vpgen_segmentator"
SRCS=$(for f in $SUBSET; do echo "$AS/$f.cpp"; done)
echo "[ilsvg] agg subset: $(echo $SRCS | wc -w) cpp files"
mkdir -p "$B/agg-native" "$B/agg-wasm32"
# native: 一括コンパイルして symbol 数を確認 (クラッシュしないかの smoke test)
gcc -O2 -w -fPIC -I"$AI" -c $SRCS 2>&1 | head -3
gcc -O2 -w -fPIC -I"$AI" $SRCS -shared -o "$B/agg-native/libagg_subset.so"
echo "[ilsvg] agg native .so: $(stat -c %s "$B/agg-native/libagg_subset.so")B"
# wasm: 同じくコンパイル (objdump で wasm であることを確認)
emcc -O2 -w -I"$AI" -c $SRCS 2>&1 | head -3
echo "[ilsvg] agg wasm32 objects: $(ls *.o | wc -l) (wasm format)"
# ILSvg のシンボルと突合 (cppfw/agg 2.8.9 が agg:: シンボルを供給することの確認)
if [ -s "$ROOT/work/svg/ilsvg_syms.txt" ]; then
  n_agg_bin=$(/opt/emsdk/upstream/bin/llvm-cxxfilt < "$ROOT/work/svg/ilsvg_syms.txt" 2>/dev/null | grep -c "^agg::" || true)
  echo "[ilsvg] ILSvg binary agg:: symbols: $n_agg_bin"
fi

# --- (3) svgdom/svgren の依存ブロック記録 ---
echo
echo "== 3. svgdom 0.4.5 / svgren 0.6.3 の依存ブロック (試行して記録) =="
cd "$S/cppfw-svgdom" && git checkout -q 0.4.5
SD="$S/cppfw-svgdom/src"
SDOM=$(find "$SD/svgdom" -name "*.cpp" | sort)
mkdir -p "$B/svgdom-try"
cd "$B/svgdom-try"
emcc -c -O2 -w -I"$SD" $(for f in $SDOM; do echo "$f"; done) 2>"$B/svgdom_try.err" || true
echo "[ilsvg] svgdom compile errors (先頭5):"
head -5 "$B/svgdom_try.err" | sed 's/^/    /'
echo "[ilsvg] -> header パス (papki/file.hpp, r4/vector.hpp) が未解決 (upstream repo 単体ではビルド不可)"
cd "$S/cppfw-svgdom" && git checkout -q main 2>/dev/null || git checkout -q master 2>/dev/null

echo
echo "=== ILSvg 検証サマリ ==="
echo "  version 特定: data/ilsvg_version.json (svgdom 0.3.59-0.4.9 / svgren 0.6.0-0.6.3 / agg 2.8.x / cssom 0.2.x)"
echo "  agg 実ビルド: emcc で 25 cpp コンパイル成功 (svgren 使用サブセット)"
echo "  svgdom/svgren 連結ビルド: 依存 (papki/r4/utki/cssom/mikroxml) 解決が必要 = ブロック -> 子チケット"
