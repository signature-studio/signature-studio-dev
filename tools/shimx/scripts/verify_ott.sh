#!/usr/bin/env bash
# OTT (M8) の undefined symbol 47 種に対する shimx の解決数を実測する。
#   m8_build.sh の emcc コマンドを再現 (M4 shim の heap.c/failfast.c を shimx の全ソースに置換)し、
#   wasm-ld の "undefined symbol" を集計する。 tools/m6..m8 は読取のみ (成果物は tools/shimx/work/ott/)。
#   使い方: bash scripts/verify_ott.sh        → work/ott/result.json
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"
M6="$HERE/../m6"; M8="$HERE/../m8"
OUT="$HERE/work/ott"; mkdir -p "$OUT"
set +u; . /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; set -u
if [ ! -f "$M8/work/ott_m8.ll" ] || [ ! -f "$M6/work/m6_stubs.c" ]; then
    echo "[verify_ott] SKIP: tools/m8/work/ott_m8.ll または tools/m6/work が無い (M8 成果物の再生成が必要)"; exit 0
fi
EXPORTS=$(python3 - <<PYEOF
import re
src=open("$M6/m6_build.sh").read()
print(re.search(r'-sEXPORTED_FUNCTIONS=(\S+)', src).group(1))
PYEOF
)
cd "$M6"
# shim 差し替え: ベースライン (M4 の 2 ファイル) と shimx (全ソース) の 2 通りを実測
build() {  # $1=tag  $2...=shim ソース  (EXTRA_LD でリンカ追加オプション)
    local tag="$1"; shift
    emcc "$@" msimd6.c work/m6_stubs.c work/m6_data.c m6_rt.c work/m6_stubs_hand.c work/m6_stubs_hand2.c \
      "$M8/m8_rt.c" "$M8/work/ott_m8.ll" \
      -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAP32,HEAPF64 \
      -o "$OUT/ott_$tag.cjs" \
      -w -Wno-error=int-conversion -Wno-implicit-function-declaration \
      -O0 -g1 -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB -sGLOBAL_BASE=268435456 \
      -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule \
      -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=1 -sEXPORTED_FUNCTIONS="$EXPORTS" \
      -Wl,--no-gc-sections ${EXTRA_LD:-} -Wl,--initial-memory=$((0x36000000)) -Wl,--max-memory=$((0x36000000)) \
      > "$OUT/build_$tag.log" 2>&1 || { echo "[verify_ott] $tag: emcc 失敗 (build_$tag.log)"; tail -5 "$OUT/build_$tag.log"; return 1; }
}
build base "$HERE/../shim/src/heap.c" "$HERE/../shim/src/failfast.c"
# (1) 厳密リンク: 既存下流スタブ (m6_stubs_hand 等) との重複シンボルを収集 (失敗が期待動作)
build shimx_strict "$HERE"/src/*.c >/dev/null 2>&1 || true
# (2) 重複許容 (shimx が先勝ち) で undefined を集計
EXTRA_LD="-Wl,--allow-multiple-definition" build shimx "$HERE"/src/*.c
python3 - <<PYEOF
import json, re
def undef(tag):
    s = open("$OUT/build_%s.log" % tag, errors='replace').read()
    return sorted(set(re.findall(r'undefined symbol: ([A-Za-z_0-9.]+)', s)))
b, x = undef('base'), undef('shimx')
fn = lambda L: [n for n in L if n.startswith('function_18')]
r = {
  'baseline_undefined': len(b), 'baseline_fn18': len(fn(b)), 'baseline_api': len(b) - len(fn(b)),
  'shimx_undefined': len(x), 'shimx_fn18': len(fn(x)), 'shimx_api': len(x) - len(fn(x)),
  'resolved_by_shimx': sorted(set(b) - set(x)), 'still_undefined_api': [n for n in x if not n.startswith('function_18')],
  'new_undefined_vs_baseline': sorted(set(x) - set(b)),
  'duplicate_with_downstream_stubs': sorted(set(re.findall(r'duplicate symbol: ([A-Za-z_0-9.]+)', open("$OUT/build_shimx_strict.log", errors='replace').read()))),
}
json.dump(r, open("$OUT/result.json", 'w'), indent=1)
print("[verify_ott] baseline: %d (fn18 %d + API %d) -> shimx: %d (fn18 %d + API %d); API 解決 %d 種" % (
  r['baseline_undefined'], r['baseline_fn18'], r['baseline_api'], r['shimx_undefined'], r['shimx_fn18'], r['shimx_api'], len(r['resolved_by_shimx'])))
print("[verify_ott] shimx で解決:", ' '.join(r['resolved_by_shimx']))
print("[verify_ott] 下流スタブと重複 (shimx 採用時に退役すべき定義):", r['duplicate_with_downstream_stubs'])
print("[verify_ott] 残 API:", r['still_undefined_api'], " 新規 undefined:", r['new_undefined_vs_baseline'])
PYEOF

# 実行回帰: M8 の t1 (param 全零 sweep) 出力が baseline と bit 一致するか
if [ -f "$M8/t1_sel8.mjs" ]; then
    cd "$M8"
    for tag in base shimx; do
        M8MOD="$OUT/ott_$tag.cjs" T1VAL=0 T1OUT="$OUT/t1_$tag.hex" T1Z=19 T1SET=0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19 \
            node t1_sel8.mjs > "$OUT/t1_$tag.log" 2>&1 || true
    done
    A=$(sha256sum "$OUT/t1_base.hex" | cut -c1-16); B=$(sha256sum "$OUT/t1_shimx.hex" | cut -c1-16)
    echo "[verify_ott] t1 出力 SHA baseline=$A shimx=$B ($( [ "$A" = "$B" ] && echo 一致 || echo 不一致 )) lines=$(wc -l < "$OUT/t1_shimx.hex")"
    [ "$A" = "$B" ] || exit 1
fi
