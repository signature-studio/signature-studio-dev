#!/usr/bin/env bash
# C++ module (MSVC) の全 .pdata 関数を RetDec+pass 鎖で lift → emcc -c (到達性のみ; 正しさは別)
#   bash tools/plugins/pitch_time/cpp_lift.sh <block> [timeout_sec_per_chunk] [chunk_chars]
#   例: 19222 (Pitcher 本体) / 19072 (Scratcher engine) / 19216 (Newtone engine)
# range 文字列が chunk_chars (既定 40000 字 = 約 1,600 関数。 retdec の引数 1 個は 131072 B が上限) を超える module は chunk に分けて別々に lift する
# (chunk 間の呼出は declare になる = リンク時に未解決。 chunk 数が 1 なら全関数が同一 module)。
# 出力: work/pitch_time/cpp<block>/ と stdout 末尾に集計 1 行:
#   block,pdata_funcs,chunks,lift_rc_max,defines,f80_funcs,unimpl_helpers,emcc_c_fail_chunks,fixcmp_patched,emcc_c_fail_after_fixcmp,lift_s,missing_define,missing_bytes,missing_ref,extra_inside
# unimpl_helpers / defines は chunk 合計 (chunk 数 1 なら module 全体の値)。 emcc_c_fail* = emcc -c が失敗した chunk 数。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
cd "$HERE/.."
B="$1"; TMO="${2:-1500}"; CH="${3:-40000}"
OUT="work/pitch_time/cpp$B"; rm -rf "$OUT"; mkdir -p "$OUT"
python3 pitch_time/cpp_ranges.py "$B" "$OUT/ranges" "$CH" 2> "$OUT/ranges.info"
NCH=$(ls "$OUT"/ranges.*.txt | wc -l)
emcc_c() { ( source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; TMPDIR="$1/tmp" emcc -c "$2" -o "$1/e.o" -w -O0 -msimd128 > "$3" 2>&1 ); echo $?; }
: > "$OUT/chunks.csv"
for ((k = 0; k < NCH; k++)); do
  C="$OUT/c$k"; mkdir -p "$C/tmp"; cp "$OUT/ranges.$k.txt" "$C/ranges.txt"
  t0=$(date +%s)
  bash lift/lift_ranges.sh "$FL_WIN64_DIR/extracted/block$(printf %05d "$B")_PE.bin" "$C/ranges.txt" "$C" e "$TMO" > "$C/lift.log" 2>&1
  rc=$?
  t1=$(date +%s)
  DEF=$(grep -c '^define' "$C/e.final.ll" 2>/dev/null || echo 0)
  UNI=$(grep -o 'unimplemented [0-9]*' "$C/e.simd.log" 2>/dev/null | awk '{print $2}' | head -1)
  F80=$(python3 - "$C/e.final.ll" <<'PY'
import re, sys
try:
    s = open(sys.argv[1]).read()
except Exception:
    print(-1); sys.exit()
print(sum(1 for f in re.split(r'\n(?=define )', s) if f.startswith('define') and 'x86_fp80' in f))
PY
)
  erc=-1; erc2=-1; NP=-1
  if [ -f "$C/e.final.ll" ]; then
    erc=$(emcc_c "$C" "$C/e.final.ll" "$C/emcc.log")
    # 局所修復 (icmp ptr/i64 型不整合) を当てた後の再試行。 clang は最初の型エラーで止まるため、次に露見する類型を記録する
    NP=$(python3 pitch_time/cpp_fixcmp.py "$C/e.final.ll" "$C/e.fixcmp.ll" 2>&1 | sed 's/.*= //')
    erc2=$(emcc_c "$C" "$C/e.fixcmp.ll" "$C/emcc_fixcmp.log")
    { echo "[final.ll]"; grep -m1 'error' "$C/emcc.log" || true; echo "[fixcmp.ll]"; grep -m1 'error' "$C/emcc_fixcmp.log" || true; } > "$C/first_errors.txt"
  fi
  DEFS=$(python3 pitch_time/cpp_defs.py "$C" 2>/dev/null || echo "-1,-1,-1,-1,-1")
  echo "$k,$rc,$DEF,$F80,${UNI:--1},$erc,$NP,$erc2,$((t1-t0)),$DEFS" >> "$OUT/chunks.csv"
done
python3 - "$B" "$OUT" <<'PY' | tee "$OUT/summary.csv"
import sys
b, d = sys.argv[1:3]
R = [list(map(int, l.split(','))) for l in open(d + '/chunks.csv').read().split('\n') if l]
nf = int(open(d + '/ranges.info').read().split()[0])
s = lambda i: sum(r[i] for r in R)
# chunks.csv: k,rc,def,f80,uni,erc,NP,erc2,sec,missing,missing_bytes,missing_ref,extra,function_defines
fail = lambda i: sum(1 for r in R if r[i] != 0)
print(','.join(map(str, [b, nf, len(R), max(r[1] for r in R), s(2), s(3), s(4), fail(5), s(6), fail(7), s(8), s(9), s(10), s(11), s(12)])))
PY
