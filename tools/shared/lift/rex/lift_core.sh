#!/usr/bin/env bash
# REX 中核閉包 (REXCreate / REXGetInfoFromBuffer / REXRenderSlice) を x64c で lift → C → wasm (コンパイル確認まで)。T-SH-45 (#2734)。
# 差分テスト (元の機械語との比較) は REX 入力素材が無いため未実施 (REPORT §8.5)。RetDec は使わない (D5)。
# 出力は所有者限定 tier 専用 (D20)。生成物は tools/shared/work/lift/rex-core/ (gitignore・commit しない)。
# usage: FL_WIN64_DIR=<fl-win64 展開先> bash tools/shared/lift/rex/lift_core.sh [ok|neg-owner|all]
#   REX_SIDE (既定 1): 1 = 所有者限定 tier の配信物 ($W/owner/) に rex_core_side.wasm (rex_core.wasm の複製) を組み込む。0 = 組み込まない (除外)。0/1 以外は exit 2。
#   ok (既定): 配信物の一覧が REX_SIDE と一致し、REX の wasm と同じ内容の配信物の数が REX_SIDE と一致することを確認する。
#   neg-owner: 配信物一覧の突合のネガティブコントロール (owner/rex_glue.c を追加してから突合する)。FAIL を検出すれば期待通り。
#   all = ok + neg-owner。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$HERE/../.."
FLE="$ROOT/../flelift"
source "$ROOT/env.sh"
MODE="${1:-ok}"
REX_SIDE="${REX_SIDE:-1}"
case "$REX_SIDE" in 0|1) ;; *) echo "[rex-core] REX_SIDE は 0 か 1 (got: $REX_SIDE)"; exit 2 ;; esac
case "$MODE" in ok|neg-owner|all) ;; *) echo "[rex-core] mode は ok|neg-owner|all (got: $MODE)"; exit 2 ;; esac
if [ "$MODE" = all ]; then
  for m in ok neg-owner; do bash "$0" "$m" || exit 1; done
  echo "[rex-core] ALL OK (ok PASS + neg-owner が期待通り FAIL)"; exit 0
fi
DLL="${REX_DLL:-$FL_WIN64_DIR/extracted/block24351_PE.bin}"
[ -f "$DLL" ] || { echo "[rex-core] DLL not found: $DLL (FL_WIN64_DIR=${FL_WIN64_DIR:-})"; exit 2; }
W="$ROOT/work/lift/rex-core"; mkdir -p "$W"
source "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1
L0="$(cut -d' ' -f1-3 /proc/loadavg)"; T0=$(date +%s)

# REXCreate 0x1800010b0 / REXGetInfoFromBuffer 0x180001170 / REXRenderSlice 0x180001280 (export RVA 0x10b0 / 0x1170 / 0x1280)
python3 -c "import json; json.dump({'roots': [0x1800010b0, 0x180001170, 0x180001280], 'calltgt': []}, open('$W/entries.json', 'w'))"
rm -rf "$W/lift"
python3 "$FLE/x64c.py" --pe "$DLL" --entries "$W/entries.json" --out "$W/lift" --closure 99 \
  --img 0x180000000 --shift 0x150000000 --img-size 0x6a000 --impbase 0x1D80000 | tee "$W/x64c.log"
echo "[rex-core] indirect register dispatch sites (ott_dispatch): $(grep -c 'ott_dispatch(t_)' "$W/lift/fle_lifted.c")"
echo "[rex-core] unsup sites (lift_meta.json): $(python3 -c "import json; print(len(json.load(open('$W/lift/lift_meta.json'))['unsup_sites']))")"

emcc -O1 -ffp-contract=off -fno-fast-math -w -I "$FLE/rt" \
  "$W/lift/fle_lifted.c" "$FLE/rt/fle_cpu.c" "$HERE/rex_glue.c" \
  -sSTANDALONE_WASM=1 -sALLOW_MEMORY_GROWTH=0 -sINITIAL_MEMORY=$((0x31000000)) -sSTACK_SIZE=65536 -sGLOBAL_BASE=268435456 \
  --no-entry -Wl,--no-gc-sections -Wl,--export=rex_run -Wl,--export=rex_reset -Wl,--export=rex_hits_get \
  -o "$W/rex_core.wasm"
echo "[rex-core] wasm: $(stat -c %s "$W/rex_core.wasm") bytes"

rm -rf "$W/owner"; mkdir -p "$W/owner"
if [ "$REX_SIDE" = 1 ]; then cp "$W/rex_core.wasm" "$W/owner/rex_core_side.wasm"; fi
if [ "$MODE" = neg-owner ]; then echo "dummy" > "$W/owner/rex_glue.c"; fi
OWN_LIST="$(cd "$W" && find owner -type f | sort)"
if [ "$REX_SIDE" = 1 ]; then EXP_OWN="owner/rex_core_side.wasm"; EXP_REX_N=1; else EXP_OWN=""; EXP_REX_N=0; fi
OWN_RC=0
[ "$OWN_LIST" = "$EXP_OWN" ] || OWN_RC=1
REX_SHA="$(sha256sum "$W/rex_core.wasm" | cut -d' ' -f1)"
OWN_REX_N="$(cd "$W" && find owner -type f -exec sha256sum {} + | grep -cF "$REX_SHA" || true)"
[ "$OWN_REX_N" = "$EXP_REX_N" ] || OWN_RC=1
echo "[rex-core] owner tier REX_SIDE=$REX_SIDE: 一覧=[$(echo "$OWN_LIST" | tr '\n' ' ' | sed 's/ $//')] 期待=[$EXP_OWN] REX の wasm と同内容の配信物 $OWN_REX_N (期待 $EXP_REX_N) sha256=$REX_SHA rc=$OWN_RC"
if [ "$MODE" = neg-owner ]; then rm -f "$W/owner/rex_glue.c"; fi

T1=$(date +%s)
echo "[rex-core] elapsed=$((T1-T0))s load start=[$L0] end=[$(cut -d' ' -f1-3 /proc/loadavg)]"
if [ "$MODE" = ok ]; then
  [ $OWN_RC -eq 0 ] || { echo "[rex-core] ok: 配信物の確認 FAIL rc=$OWN_RC"; exit $OWN_RC; }
  exit 0
fi
if [ $OWN_RC -ne 0 ]; then echo "[rex-core] neg-owner: FAIL を検出 (期待通り) rc=$OWN_RC"; exit 0; else echo "[rex-core] neg-owner: PASS してしまった = ゲートが効いていない"; exit 1; fi
