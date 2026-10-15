#!/usr/bin/env bash
# py301_undo_obj_probe.sh — PY-201 後続 (#3028): 安全判定の obj ([0x141d6c0] = [[0x15e4790]+8]) を設定する経路が
# unit 209 の停止までに実行されるかを観測する。観測点 2 つ: 0x976a95 (obj と [0x141d6b8] を読み、非 0 なら
# [0x141d6c0] の関数を呼んで 0 にする関数の入口) と 0x976b60 (その作成呼出し先の入口)。書込み監視 (FLE_WWATCH) は
# obj 周りの 4 slot (0x141d6c0・0x141d6b8・0x15e4790・0x15e1c78) で、値が変わる書込みだけ出す。
#
#   bash tools/flelift/boot/py301_undo_obj_probe.sh      # 前提: 先に fle6_measure.sh で work/boot/lift を作る
#
# 前提: FL_WIN64_DIR (fl-win64 展開先) / SS_EMSDK_ENV (emsdk_env.sh。エントリ ID は docs/REFERENCES.md の [EMSDK]) / node。出力は work/boot/ (gitignore)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
FLE="$(cd "$HERE/.." && pwd)"
W="$FLE/work/boot"
LIFT="$W/lift"
DBG="$W/lift_py301"
SS_EMSDK_ENV="${SS_EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}"
[ -f "$LIFT/fle_lifted_s0.c" ] || { echo "[py301] $LIFT が無い。先に bash tools/flelift/boot/fle6_measure.sh を実行する"; exit 2; }

# 観測 C 文: 入口で [0x141d6b8]・[0x141d6c0] を読む (最初の 32 回まで)。
PROBE_A='{ static int n_; if (n_++ < 32) fprintf(stderr, "[PY301-a] 0x976a95 n=%d b6b8=%llx obj=%llx\n", n_, (unsigned long long)LD64(0x141d6b8), (unsigned long long)LD64(0x141d6c0)); }'
# 作成呼出し先 (0x976b60) の入口: 引数 rcx・dl と [0x141d6b8]。
PROBE_B='{ static int n_; if (n_++ < 32) fprintf(stderr, "[PY301-b] 0x976b60 n=%d rcx=%llx dl=%llx b6b8=%llx\n", n_, (unsigned long long)R[RCX], (unsigned long long)(R[RDX] & 0xff), (unsigned long long)LD64(0x141d6b8)); }'
# 陽性対照: boot の末尾 (MessageBoxA → exit の call site) は必ず通る。ここで発火しなければ観測の仕組みが効いていない。
PROBE_C='{ static int n_; if (n_++ < 4) fprintf(stderr, "[PY301-c] 0x412a0d n=%d (control)\n", n_); }'

rm -rf "$DBG" && cp -r "$LIFT" "$DBG"
for k in 0 1 2 3 4 5 6 7; do
  # 0x976a95・0x976b60・0x412a0d がどの shard にあるかは事前に決めない。他 shard では解決されず 0 hit になる。
  python3 "$HERE/dbg_lift.py" --src "$DBG/fle_lifted_s$k.c" --out "$DBG/fle_lifted_s$k.c" --at 0x976a95 --c "$PROBE_A" || true
  python3 "$HERE/dbg_lift.py" --src "$DBG/fle_lifted_s$k.c" --out "$DBG/fle_lifted_s$k.c" --at 0x976b60 --c "$PROBE_B" || true
  python3 "$HERE/dbg_lift.py" --src "$DBG/fle_lifted_s$k.c" --out "$DBG/fle_lifted_s$k.c" --at 0x412a0d --c "$PROBE_C" || true
done
echo "[py301] probes: $(grep -c 'PY301' "$DBG"/fle_lifted_s*.c | awk -F: '{s+=$2} END {print s}') (expect 3)"

rm -f "$W"/obj/py301_*.o
FLE_LIFT_DIR="$DBG" FLE_LABEL=py301 FLE_SHARDS=8 \
  FLE_EXTRA_CCF="-DFLE_WWATCH -DFLE_WWATCH_SLOTS=0x141d6c0ull,0x141d6b8ull,0x15e4790ull,0x15e1c78ull" \
  SS_EMSDK_ENV="$SS_EMSDK_ENV" bash "$HERE/build.sh" plain

LOG="$W/run_py301_probe.log"
FLE_IPP=1 FLE_DIAG_NULLFILL=0 FLE_BOOT_VARIANT=plain node "$HERE/fle_boot.mjs" "$W/fleboot_py301.cjs" "$W/py301_probe.json" --boot-only > "$LOG" 2>&1 || true
echo "[py301] PY301 行: $(grep -c '\[PY301' "$LOG" || true) (0 件なら入口に未到達)"
grep -E '\[PY301|fle_wwatch\]|FLEBOOT_RESULT' "$LOG" | cut -c1-300
