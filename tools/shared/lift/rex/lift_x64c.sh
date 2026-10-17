#!/usr/bin/env bash
# REX (win `REX Shared Library.dll` = block24351_PE.bin) の REXGetCreatorInfo / REXGetInfo 閉包を x64c で lift → C → wasm。
# 元の機械語 (native_ref.c: RWX に VA 0x30000000 へ敷設して直接実行) と同一入力で、戻り値・import 呼出回数・arena・.data を全バイト比較する (T-SH-44 / #2733)。
# RetDec は使わない (D5)。所有者限定 tier の side module (D20)。
# usage: FL_WIN64_DIR=<fl-win64 展開先> bash tools/shared/lift/rex/lift_x64c.sh [ok|neg-cmp|neg-ctx|neg-owner|dllmain|all]
#   dllmain (#4834): DllMain(0x1fd78, reason=1) を root に加え、両側で DllMain を 1 回実行した後の .data を基準にして全バイト比較する。all には含めない。
#   REX_SIDE (既定 1): 1 = 所有者限定 tier の配信物 ($W/owner/) に REX side module (rex_side.wasm) を組み込む。0 = 組み込まない (除外)。0/1 以外は exit 2。
#   ok (既定): 本検査。exit 0 = 全 case 一致 + カバレッジ充足 + 配信物の一覧が REX_SIDE と一致。
#   neg-cmp : 比較器のネガティブコントロール (wasm 結果の 1 バイトを反転)。
#   neg-ctx : 入力のネガティブコントロール (wasm 側だけ ctx 大域を 0 にする)。
#   neg-owner: 配信物一覧の突合のネガティブコントロール (owner/rex_glue.c を追加してから突合する)。
#   movnti  : movnti (閉包内 24 箇所) を含む経路への到達の実測 (gen_movnti.py・movnti_check.py。T-SH-90 / #3589)。
#             実装判定 = movnti の ott_unsup が 0 件 (#3893)。reach 16 件は arena 0x80000 で完了することを判定 (#4324)。
#   neg-*   : FAIL を検出したら exit 0 / PASS してしまったら exit 1。all = ok + 全 neg-* + movnti。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$HERE/../.."
FLE="$ROOT/../flelift"
source "$ROOT/env.sh"
MODE="${1:-ok}"
REX_SIDE="${REX_SIDE:-1}"
case "$REX_SIDE" in 0|1) ;; *) echo "[rex] REX_SIDE は 0 か 1 (got: $REX_SIDE)"; exit 2 ;; esac
if [ "$MODE" = all ]; then
  for m in ok neg-cmp neg-ctx neg-owner movnti; do bash "$0" "$m" || exit 1; done
  echo "[rex] ALL OK (本検査 PASS + ネガコン 3 件 (neg-cmp・neg-ctx・neg-owner) が期待通り FAIL + movnti 到達の判定 PASS)"; exit 0
fi
DLL="${REX_DLL:-$FL_WIN64_DIR/extracted/block24351_PE.bin}"
[ -f "$DLL" ] || { echo "[rex] DLL not found: $DLL (FL_WIN64_DIR=${FL_WIN64_DIR:-})"; exit 2; }
W="$ROOT/work/lift/rex"; mkdir -p "$W"
source "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1
L0="$(cut -d' ' -f1-3 /proc/loadavg)"; T0=$(date +%s)

if [ "$MODE" = dllmain ]; then ROOTS="0x1800011c0, 0x180001130, 0x180001fd78"; else ROOTS="0x1800011c0, 0x180001130"; fi
python3 -c "import json; json.dump({'roots': [$ROOTS], 'calltgt': []}, open('$W/entries.json', 'w'))"
rm -rf "$W/lift"
python3 "$FLE/x64c.py" --pe "$DLL" --entries "$W/entries.json" --out "$W/lift" --closure 99 \
  --img 0x180000000 --shift 0x150000000 --img-size 0x6a000 --impbase 0x1D80000
if [ "$MODE" = movnti ]; then export REX_ARENA_SZ=0x80000; fi   # reach (a1 < 0x80000) を arena 内で完了させる (#4324)。他モードは 0x10000 のまま
python3 "$HERE/rex_image.py" "$DLL" "$W"
if [ "$MODE" = movnti ]; then python3 "$HERE/gen_movnti.py" "$W/cases.bin"; else python3 "$HERE/gen_cases.py" "$W/cases.bin" 200; fi

# dllmain: fle_cpu.c の同名 imp_* を -D で退け、rex 専用 no-op 表 (rex_imp_noop.c) を唯一の定義にする。
# fle_cpu.c 本体は変えない (既定モードのビルドは従来どおり)。
FLE_CPU_SRC="$FLE/rt/fle_cpu.c"; EXTRA_SRC=""
if [ "$MODE" = dllmain ]; then
  # -D は指定したファイルすべてに効くため、fle_cpu.c だけを別翻訳単位にして -D を掛ける。
  emcc -c -O1 -ffp-contract=off -fno-fast-math -w -I "$FLE/rt" -I "$W" $(cat "$W/fle_cpu_rename.flags") \
    "$FLE/rt/fle_cpu.c" -o "$W/fle_cpu_renamed.o"
  FLE_CPU_SRC="$W/fle_cpu_renamed.o"; EXTRA_SRC="$W/rex_imp_noop.c"
fi
emcc -O1 -ffp-contract=off -fno-fast-math -w -I "$FLE/rt" -I "$W" \
  "$W/lift/fle_lifted.c" "$FLE_CPU_SRC" "$HERE/rex_glue.c" $EXTRA_SRC \
  -sSTANDALONE_WASM=1 -sALLOW_MEMORY_GROWTH=0 -sINITIAL_MEMORY=$((0x31000000)) -sSTACK_SIZE=65536 -sGLOBAL_BASE=268435456 \
  --no-entry -Wl,--no-gc-sections -Wl,--export=rex_run -Wl,--export=rex_reset -Wl,--export=rex_hits_get -Wl,--export=rex_unsup_get \
  --profiling-funcs -o "$W/rex.wasm"
echo "[rex] wasm: $(stat -c %s "$W/rex.wasm") bytes"

gcc -O1 -w -I "$W" -o "$W/native_ref" "$HERE/native_ref.c"
if [ "$MODE" = dllmain ]; then export REX_DLLMAIN=1 REX_IAT_SLOTS="$W/iat_slots.txt" REX_DATA_BASE_OUT="$W/data_base.bin"; else unset REX_DLLMAIN; fi
timeout 300 "$W/native_ref" "$W/image_native.bin" "$W/cases.bin" "$W/res_native.bin" 2> "$W/native_stderr.txt"; cat "$W/native_stderr.txt" >&2

if [ "$MODE" = neg-ctx ]; then REX_NEG=ctx timeout 300 node "$HERE/run_wasm.mjs" "$W"; elif [ "$MODE" = movnti ]; then REX_RUN_CRASHED=1 timeout 300 node "$HERE/run_wasm.mjs" "$W"; else timeout 300 node "$HERE/run_wasm.mjs" "$W"; fi
if [ "$MODE" = movnti ]; then
  set +e; python3 "$HERE/movnti_check.py" "$W"; RC=$?; set -e
  echo "[rex] movnti elapsed=$(( $(date +%s) - T0 ))s load start=[$L0] end=[$(cut -d' ' -f1-3 /proc/loadavg)]"
  exit $RC
fi
set +e
if [ "$MODE" = neg-cmp ]; then python3 "$HERE/diff_test.py" "$W" --mutate-wasm; RC=$?; else python3 "$HERE/diff_test.py" "$W"; RC=$?; fi
set -e
if [ "$MODE" = dllmain ]; then
  T1=$(date +%s)
  echo "[rex] dllmain elapsed=$((T1-T0))s load start=[$L0] end=[$(cut -d' ' -f1-3 /proc/loadavg)]"
  exit $RC
fi
python3 "$HERE/crash_class.py" "$W" "$W/native_stderr.txt"
python3 "$HERE/crash_insn.py" "$W"
T1=$(date +%s)
echo "[rex] $MODE elapsed=$((T1-T0))s load start=[$L0] end=[$(cut -d' ' -f1-3 /proc/loadavg)]"
if [ "$MODE" = ok ] || [ "$MODE" = neg-owner ]; then
  [ $RC -eq 0 ] || { echo "[rex] $MODE: 本検査 FAIL rc=$RC"; exit $RC; }
  rm -rf "$W/owner"; mkdir -p "$W/owner"
  if [ "$REX_SIDE" = 1 ]; then cp "$W/rex.wasm" "$W/owner/rex_side.wasm"; fi
  if [ "$MODE" = neg-owner ]; then echo "dummy" > "$W/owner/rex_glue.c"; fi
  OWN_LIST="$(cd "$W" && find owner -type f | sort)"
  if [ "$REX_SIDE" = 1 ]; then EXP_OWN="owner/rex_side.wasm"; else EXP_OWN=""; fi
  OWN_RC=0
  [ "$OWN_LIST" = "$EXP_OWN" ] || OWN_RC=1
  if [ "$REX_SIDE" = 1 ]; then
    cmp "$W/rex.wasm" "$W/owner/rex_side.wasm" || OWN_RC=1
  else
    [ -z "$(find "$W/owner" -type f \( -name '*rex*' -o -name '*glue*' -o -name '*.c' \))" ] || OWN_RC=1
  fi
  echo "[rex] owner tier REX_SIDE=$REX_SIDE: 一覧=[$(echo "$OWN_LIST" | tr '\n' ' ' | sed 's/ $//')] 期待=[$EXP_OWN] rc=$OWN_RC"
  if [ "$MODE" = neg-owner ]; then rm -f "$W/owner/rex_glue.c"; fi
  (cd "$W" && find owner -type f | sort) > "$W/owner_list.txt"
  if [ "$MODE" = ok ]; then exit $OWN_RC; fi
  if [ $OWN_RC -ne 0 ]; then echo "[rex] neg-owner: FAIL を検出 (期待通り) rc=$OWN_RC"; exit 0; else echo "[rex] neg-owner: PASS してしまった = ゲートが効いていない"; exit 1; fi
fi
if [[ "$MODE" == neg-* ]]; then
  if [ $RC -ne 0 ]; then echo "[rex] $MODE: FAIL を検出 (期待通り) rc=$RC"; exit 0; else echo "[rex] $MODE: PASS してしまった = ゲートが効いていない"; exit 1; fi
fi
exit $RC
