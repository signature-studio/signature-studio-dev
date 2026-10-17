#!/usr/bin/env bash
# py301_obj_writer_probe.sh — PY-301 後続 (#4135): 安全判定の obj ([0x141d6c0] = [[0x15e4790]+8]) に書く 2 経路を
# 既定経路 (FLE_IPP 未指定・units 895 まで進む経路) で観測する。PE 逆アセンブル (第 31 波) で、obj への書込みは
#   0x1264050 (関数入口。obj が 0 のときだけ作成関数 0x125da90 を呼ぶ) の 0x1264145 (mov [rcx+8], rax)
#   0x1263540 の 0x1263571 (mov [rcx+8], rax・作成関数 0x125da90 の戻り値)
# の 2 本と分かった。本 probe は各入口の到達と、書込み直前の戻り値 (rax) と obj の値を見る。
#   bash tools/flelift/boot/py301_obj_writer_probe.sh      # 前提: 先に fle6_measure.sh で work/boot/lift を作る
#
# 陽性対照: 0x412a0d (boot 末尾) は必ず通る。ここで発火しなければ観測の仕組みが効いていない。
# 前提: FL_WIN64_DIR / SS_EMSDK_ENV / node。出力は work/boot/ (gitignore)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
FLE="$(cd "$HERE/.." && pwd)"
W="$FLE/work/boot"
LIFT="$W/lift"
SS_EMSDK_ENV="${SS_EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}"
[ -f "$LIFT/fle_lifted_s0.c" ] || { echo "[py301o] $LIFT が無い。先に bash tools/flelift/boot/fle6_measure.sh を実行する"; exit 2; }

# 入口: S = [0x15e4790] (Q スロット)・P = [S] (書込み先の基底)・P+8 (書込み先の値) を読む (最初の 16 回)。
PROBE_E1='{ static int n_; if (n_++ < 16) fprintf(stderr, "[PY301o-e] 0x1264050 n=%d S=%llx P=%llx P8=%llx\n", n_, (unsigned long long)LD64(0x15e4790), (unsigned long long)LD64(LD64(0x15e4790)), (unsigned long long)LD64(LD64(LD64(0x15e4790))+8)); }'
PROBE_E2='{ static int n_; if (n_++ < 16) fprintf(stderr, "[PY301o-f] 0x1263540 n=%d S=%llx P=%llx P8=%llx\n", n_, (unsigned long long)LD64(0x15e4790), (unsigned long long)LD64(LD64(0x15e4790)), (unsigned long long)LD64(LD64(LD64(0x15e4790))+8)); }'
# 書込み直前: rax (作成関数の戻り値) と書込み先 [rcx+8]。
PROBE_W1='{ static int n_; if (n_++ < 16) fprintf(stderr, "[PY301o-w1] 0x1264145 n=%d rax=%llx dst=%llx\n", n_, (unsigned long long)R[RAX], (unsigned long long)R[RCX]); }'
PROBE_W2='{ static int n_; if (n_++ < 16) fprintf(stderr, "[PY301o-w2] 0x1263571 n=%d rax=%llx dst=%llx\n", n_, (unsigned long long)R[RAX], (unsigned long long)R[RCX]); }'
# 陽性対照: boot 末尾の exit call site。
PROBE_C='{ static int n_; if (n_++ < 4) fprintf(stderr, "[PY301o-c] 0x412a0d n=%d (control)\n", n_); }'

rm -rf "$W/lift_py301o" && cp -r "$LIFT" "$W/lift_py301o"
DBG="$W/lift_py301o"
# dbg_lift.py は「そのシャードに VA が無い」ときも非 0 を返すので、rc は見ない。挿入の成否は下の番地ごとの数で判定する。
for k in 0 1 2 3 4 5 6 7; do
  F="$DBG/fle_lifted_s$k.c"
  python3 "$HERE/dbg_lift.py" --src "$F" --out "$F" --at 0x1264050 --c "$PROBE_E1" > /dev/null 2>&1 || true
  python3 "$HERE/dbg_lift.py" --src "$F" --out "$F" --at 0x1263540 --c "$PROBE_E2" > /dev/null 2>&1 || true
  python3 "$HERE/dbg_lift.py" --src "$F" --out "$F" --at 0x1264145 --c "$PROBE_W1" > /dev/null 2>&1 || true
  python3 "$HERE/dbg_lift.py" --src "$F" --out "$F" --at 0x1263571 --c "$PROBE_W2" > /dev/null 2>&1 || true
  python3 "$HERE/dbg_lift.py" --src "$F" --out "$F" --at 0x412a0d --c "$PROBE_C" > /dev/null 2>&1 || true
done
# 番地ごとに、全シャードでちょうど 1 回挿入されたことを確かめる (1 本でも欠ければ止める)。
PROBE_OK=1
for pair in e:0x1264050 f:0x1263540 w1:0x1264145 w2:0x1263571 c:0x412a0d; do
  tag="${pair%%:*}"; va="${pair#*:}"
  n=$(cat "$DBG"/fle_lifted_s*.c | grep -c "\[PY301o-$tag\]" || true)
  [ "$n" = 1 ] || { echo "[py301o] MISS $va (tag $tag): 挿入 $n 回 (expect 1)"; PROBE_OK=0; }
done
echo "[py301o] probes: $(grep -c 'PY301o' "$DBG"/fle_lifted_s*.c | awk -F: '{s+=$2} END {print s}') (expect 5)"
[ "$PROBE_OK" = 1 ] || { echo "[py301o] probe 挿入が 5 本揃わないため停止 (測定しない)"; exit 3; }

rm -f "$W"/obj/py301o_*.o
FLE_LIFT_DIR="$DBG" FLE_LABEL=py301o FLE_SHARDS=8 \
  SS_EMSDK_ENV="$SS_EMSDK_ENV" bash "$HERE/build.sh" plain

LOG="$W/run_py301o_probe.log"
FLE_IPP= FLE_DIAG_NULLFILL=0 FLE_BOOT_VARIANT=plain node "$HERE/fle_boot.mjs" "$W/fleboot_py301o.cjs" "$W/py301o_probe.json" --boot-only > "$LOG" 2>&1 || true
echo "[py301o] PY301o 行: $(grep -c '\[PY301o' "$LOG" || true) (0 件なら入口に未到達)"
grep -E '\[PY301o|FLEBOOT_RESULT' "$LOG" | cut -c1-300
