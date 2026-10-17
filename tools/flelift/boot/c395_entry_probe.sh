#!/usr/bin/env bash
# c395_entry_probe.sh — PY-4877 (#5168): 変換スロット 0x16b8298 を書く束縛関数 f_c395a0 が、
# FLEngine boot (既定経路 = FLE_IPP 未指定 = fle_boot.mjs の既定 mode 3) で実行されるかを観測する。
# 観測点 (lift 生成 C に fprintf を挿入):
#   c3b3a2 : f_c395a0 の唯一の直接呼出し元 (呼出し回数)
#   c395a0 : f_c395a0 入口 (呼出し回数)
#   4235f0 : resolver (GetProcAddress 系) 入口 (呼出し回数と戻り番地)
#   c396c5 : 0x16b8298 への格納直前 (R[0] = resolver の戻り値、[0x16b8298] の現在値)
# 判定: c395a0 が 0 件なら、既定経路では束縛関数が走らず 0x16b8298 は 0 のまま。
#   c395a0 が >=1 件で c396c5 が 0 件なら、格納前に別経路で戻る (分岐を要確認)。
#   c396c5 が出れば R[0] が格納される値そのもの。
#
#   bash tools/flelift/boot/c395_entry_probe.sh   # 前提: 先に fle6_measure.sh (FLE_BOOT_RUNS=default) で work/boot/lift を作る
#
# 前提: FL_WIN64_DIR / SS_EMSDK_ENV (必須) / node / python3 (capstone, pefile)。出力は work/boot/ (gitignore)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
FLE="$(cd "$HERE/.." && pwd)"
source "$HERE/../../shared/env.sh"
W="${FLE_BOOT_WORK:-$FLE/work/boot}"
LIFT="$W/lift"
DBG="$W/lift_dbg5168"
SS_EMSDK_ENV="${SS_EMSDK_ENV:?SS_EMSDK_ENV に emsdk_env.sh のパスを指定する}"
[ -f "$LIFT/fle_lifted_s0.c" ] || { echo "[c395] $LIFT が無い。先に bash tools/flelift/boot/fle6_measure.sh を実行する"; exit 2; }

mk_probe() { echo '{ static int n_; if (n_++ < 16) fprintf(stderr, "[C395-'"$1"'] n=%d ret=%llx\n", n_, (unsigned long long)LD64(R[4])); }'; }
STORE_PROBE='{ static int s_; if (s_++ < 4) fprintf(stderr, "[C395-STORE] n=%d R0=%llx slot=%llx\n", s_, (unsigned long long)R[0], (unsigned long long)LD64(0x16b8298ULL)); }'

rm -rf "$DBG" && cp -r "$LIFT" "$DBG"
# 各 VA は 1 つの shard にしか無い。shard ごとに dbg_lift を呼び、どこか 1 shard で必ず 1 回だけ解決されることを確かめる
# (0 件・2 件以上は挿入失敗として exit 2)。shard に無いときの unresolved は正常なので握りつぶす。
insert_probe() {
  local name="$1" va="$2" c="$3" n=0 k out
  for k in 0 1 2 3 4 5 6 7; do
    out="$(python3 "$HERE/dbg_lift.py" --src "$DBG/fle_lifted_s$k.c" --out "$DBG/fle_lifted_s$k.c" --at "$va" --c "$c" 2>&1 || true)"
    if grep -q -- '-> line' <<<"$out"; then
      n=$((n + 1)); echo "[c395] $name $(grep -- '-> line' <<<"$out" | head -1) (shard $k)"
    fi
  done
  if [ "$n" -ne 1 ]; then echo "[c395] $name ($va) の挿入先が $n 件 (1 件であること)。挿入失敗のため中止" >&2; exit 2; fi
}
insert_probe callsite 0xc3b3a2 "$(mk_probe callsite)"
insert_probe entry 0xc395a0 "$(mk_probe entry)"
insert_probe resolver 0x4235f0 "$(mk_probe resolver)"
insert_probe STORE 0xc396c5 "$STORE_PROBE"
echo "[c395] probe 挿入行数: $(grep -c 'C395-' "$DBG"/fle_lifted_s*.c | awk -F: '{s+=$2} END {print s}')"

FLE_LIFT_DIR="$DBG" FLE_LABEL=c395 FLE_SHARDS=8 SS_EMSDK_ENV="$SS_EMSDK_ENV" bash "$HERE/build.sh" plain

LOG="$W/run_c395_probe.log"
FLE_DIAG_NULLFILL=0 FLE_BOOT_VARIANT=plain FLE_BOOT_LOG_CAP=268435456 FLE_BOOT_TIME_CAP=300 FLE_BOOT_QUIET_BIN=1 timeout "${FLE_BOOT_TIMEOUT:-600}" node "$HERE/fle_boot.mjs" "$W/fleboot_c395.cjs" "$W/c395_probe.json" --boot-only > "$LOG" 2>&1 || true
echo "[c395] C395 行:"
grep -E '\[C395|FLEBOOT_RESULT' "$LOG" | cut -c1-300 | head -100
