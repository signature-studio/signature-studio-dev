#!/usr/bin/env bash
# fle6_measure.sh — FLE-6: dsp_ippv2 ローダ shim 後に 0x6a7b70 を root 化して unit 進行を実測する
# 最小経路 (boot_e2e.sh の 4 variant clang を 1 variant=plain に絞った版)。
#
#   bash tools/flelift/boot/fle6_measure.sh            # gen → lift → plain clang → boot → ネガコン
#
# 工程: gen_boot (phase A) → x64c lift (closure 2) → fle_data_gen → gen_boot (phase B: imp bridge)
#       → build.sh plain (lifted C の clang -O0 1 本) → boot 実行 (--boot-only)
#       → ネガコン FLE_IPP=0 (dsp_ippv2 shim 無効) で同じ boot を再実行。
#       dsp_ippv2 shim は既定で無効 (FLE_IPP=1 のときだけ有効)。本スクリプトは shim 有 = FLE_IPP=1 で測る。
# 0x6a7b70 は boot_roots.json には入れず、本スクリプトだけが FLE_EXTRA_ROOTS で一時的に root 化する
# (iterate_roots.sh の blocklist 不変条件を崩さないため)。
# 前提: FL_WIN64_DIR (fl-win64 展開先) / python3 (capstone, pefile) / SS_EMSDK_ENV (emsdk_env.sh, 既定 /opt/emsdk) / node。
# 出力: results/boot_summary_fle6.json (shim 有), results/boot_summary_fle6_negctl.json (shim 無)。
# 生成物は work/boot/ (gitignore)。判定に失敗したら非 0 で終了する。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
FLE="$(cd "$HERE/.." && pwd)"
source "$HERE/../../shared/env.sh"
W="${FLE_BOOT_WORK:-$FLE/work/boot}"   # route ごとに分ける (#2702: 既定経路は別 work で lift する)
LIFT="$W/lift"
PE="${FLE_PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}"
SS_EMSDK_ENV="${SS_EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}"  # emsdk_env.sh は EMSDK_ENV を unset するので別名にする
[ -f "$SS_EMSDK_ENV" ] || { echo "[fle6] emsdk_env.sh not found: $SS_EMSDK_ENV (SS_EMSDK_ENV で指定)"; exit 2; }
# `-` (`:-` ではない): FLE_EXTRA_ROOTS= と空を渡すと root を足さない既定経路になる (#2702)
export FLE_EXTRA_ROOTS="${FLE_EXTRA_ROOTS-0x6a7b70}"
TAG="${FLE_BOOT_TAG:-fle6}"   # results/ の出力名の接頭 (既定 fle6 = 従来の名前)
RUNS="${FLE_BOOT_RUNS:-shim negctl ipp2}"   # shim=FLE_IPP=1 / negctl=FLE_IPP=0 / ipp2=FLE_IPP=2 / default=FLE_IPP 未指定
# diag_shim / diag_negctl (#672): FLE_DIAG_NULLFILL=1 (buf=0 の fill を戻す診断)。lift 条件は FLE_EXTRA_ROOTS で指定する (未指定は既定 root 0x6a7b70)。
#   付録 672 §1 の測定は FLE_EXTRA_ROOTS= (root 無し)、付録 3770 §2 の測定は FLE_EXTRA_ROOTS=0x6bbc20。
# lifted C は N 本 (fle_lifted_s<k>.c) に分けて並列 clang する (FLE-9, #2700)。1 にすると単一 TU (cap 11000MB で打ち切り)。
# FLE_TRAP_VA (例 0xd76c90・PY-5388 #5771): その VA を lift せず trap stub にする (x64c --trap)。呼ばれると ott_unsup で
#   boot_threw=unsup になるので、boot 経路でその関数に到達したかを観測できる。未指定は従来どおり (trap を足さない)。
export FLE_SHARDS="${FLE_SHARDS:-8}"
export TMPDIR="$W/tmp"
mkdir -p "$W/tmp" "$W/obj" "$HERE/results"
set +u; source "$SS_EMSDK_ENV" > /dev/null 2>&1; set -u
NODE="$(command -v node)"

stage() { echo "[fle6] $1 start $(date -u +%H:%M:%S) load=$(cut -d' ' -f1-3 /proc/loadavg)"; }
elapsed() { echo "[fle6] $1 done in $(( $(date +%s) - $2 ))s load=$(cut -d' ' -f1-3 /proc/loadavg)"; }

T=$(date +%s); stage "gen-A"
python3 "$HERE/gen_boot.py" --pe "$PE" --out "$W" > /dev/null
elapsed "gen-A" "$T"

T=$(date +%s); stage "lift"
# lift は RSS 上限 (FLE_RSS_CAP_MB, 既定 13800MB) を rss_cap.py で監視する。超過時は子 PID だけ kill され rc=143 で止まる。
python3 "$HERE/rss_cap.py" --cap-mb "${FLE_RSS_CAP_MB:-13800}" --log "$W/rss_lift.log" -- \
  python3 "$FLE/x64c.py" --pe "$PE" --entries "$W/fle_entries_boot.json" --out "$LIFT" --closure "${FLE_LIFT_CLOSURE:-2}" \
  --img 0x400000 --shift 0 --img-size 0x18c0000 --impbase 0x1D80000 \
  --override 0x4126f0=fle_ov_longjmp --override 0x409410=fle_ov_getmem \
  --override 0x409440=fle_ov_freemem --override 0x4120c0=fle_ov_initunits --shards "$FLE_SHARDS" ${FLE_TRAP_VA:+--trap "$FLE_TRAP_VA"} | tail -3
python3 "$FLE/fle_data_gen.py" "$PE" "$LIFT/fle_data.c" "$LIFT/lift_meta.json" > /dev/null
python3 "$HERE/gen_boot.py" --pe "$PE" --meta "$LIFT/lift_meta.json" --out "$W" > /dev/null
elapsed "lift" "$T"

T=$(date +%s); stage "clang-plain"
bash "$HERE/build.sh" plain
elapsed "clang-plain" "$T"

# 判定は exit code で行う (|| true で握り潰さない)。結果 JSON・判定行が無い、または判定 NG なら即失敗する。
# $1=label  $2=out.json  $3=FLE_IPP (1: shim 有 / 0: ネガコン / 2: shim 有 + ippsZero_8u 以外で停止 / 空: 既定)
run_boot() {
  local log="$W/run_${TAG}_$1.log"
  local rc=0
  # FLE-15 (#3770): FLE_BOOT_TIMEOUT 秒で打ち切る (時間上限・rc=124)。ログ上限は FLE_BOOT_LOG_CAP (bytes・fle_boot.mjs が JSON に残す)。
  FLE_IPP="$3" FLE_TOLERANT="${4:-0}" FLE_DIAG_NULLFILL="${5:-0}" FLE_BOOT_LOG_CAP="${6:-${FLE_BOOT_LOG_CAP:-0}}" FLE_BOOT_VARIANT=plain timeout "${FLE_BOOT_TIMEOUT:-900}" "$NODE" "$HERE/fle_boot.mjs" "$W/fleboot_plain.cjs" "$2" --boot-only > "$log" 2>&1 || rc=$?
  if [ "$rc" = 124 ]; then echo "[fle6] $1: 時間上限 ${FLE_BOOT_TIMEOUT:-900}s で打ち切り ($log・ログ $(stat -c%s "$log") B)"; FAIL_RC=124; return 0; fi
  grep 'FLEBOOT_RESULT' "$log" || true
  grep 'FLEBOOT_IPP_CHECK' "$log" || { echo "[fle6] $1: FLEBOOT_IPP_CHECK 行が無い ($log)"; exit 4; }
  [ -s "$2" ] || { echo "[fle6] $1: 結果 JSON が無い ($2)"; exit 4; }
  # 判定 NG (rc=3) でも shim 有・ネガコンの両方を採取してから最後に非 0 で終わる (片方の数値を欠かさない)。
  [ "$rc" = 0 ] || { echo "[fle6] $1: fle_boot.mjs が rc=$rc で終了 (IPP 判定 NG なら 3) ($log)"; FAIL_RC="$rc"; }
}

for r in $RUNS; do
  T=$(date +%s); stage "boot $r"
  case "$r" in
    shim)    run_boot shim    "$HERE/results/boot_summary_${TAG}.json"        1 ;;
    negctl)  run_boot negctl  "$HERE/results/boot_summary_${TAG}_negctl.json" 0 ;;
    ipp2)    run_boot ipp2    "$HERE/results/boot_summary_${TAG}_ipp2.json"   2 ;;
    default) run_boot default "$HERE/results/boot_summary_${TAG}_default.json" "" 0 0 "${FLE_BOOT_LOG_CAP:-0}" ;;   # FLE-39 (#5013): 既定経路の log cap は環境変数で渡す (既定 0 = 無効・従来どおり)
    tol)     run_boot tol     "$HERE/results/boot_summary_${TAG}_tol.json"    1 1 ;;   # 寛容起動 (#2719): shim 有 + 逐次 unit 寛容 + CreateFruityInstance 観測
    tol2)    run_boot tol2    "$HERE/results/boot_summary_${TAG}_tol2.json"   1 2 ;;   # 診断: 失敗 unit の後で InitTable を起動時の値へ戻す (補修。既定ではない)
    # #672 診断: shim 有 + buf=0 の fill を戻す。FLE-15 (#3770): ログ上限 FLE_BOOT_LOG_CAP (既定 256MiB) で有界にする
    diag_shim)   run_boot diag_shim   "$HERE/results/boot_summary_${TAG}_diag_shim.json"   1 0 1 "${FLE_BOOT_LOG_CAP:-268435456}" ;;
    diag_negctl) run_boot diag_negctl "$HERE/results/boot_summary_${TAG}_diag_negctl.json" 0 0 1 "${FLE_BOOT_LOG_CAP:-268435456}" ;;   # #672 診断: ネガコン + buf=0 の fill を戻す
    ilt)         run_boot ilt         "$HERE/results/boot_summary_${TAG}_ilt.json"         3 0 0 "${FLE_BOOT_LOG_CAP:-268435456}" ;;   # #672 分岐入力実験: shim 有 + ILTools 擬似モジュール (FLE_IPP=3)
    *) echo "[fle6] unknown run: $r"; exit 2 ;;
  esac
  elapsed "boot $r" "$T"
done
echo "[fle6] end $(date -u +%H:%M:%S)"
[ -z "${FAIL_RC:-}" ] || exit "$FAIL_RC"
