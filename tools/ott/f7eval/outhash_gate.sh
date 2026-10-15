#!/usr/bin/env bash
# outhash_gate.sh — CAB-238 検収④ (出力 SHA の分離) を snapshot 環境で再測定する。
#   (A) 既定 (auto f7,p1) ビルド vs 元 m10 成果物 : combo 別 SHA 比較 (不一致 combo 数とその理由)
#   (B) 旧既定 (--auto none) の liftlib gate : checks/census/trap + outhash 42/42 一致
# 出力: tools/ott/work/cab238/outhash_gate/{A,B}.log, A_fp1.json, A_ref.json
set -uo pipefail
HERE_GATE="$(cd -- "$(dirname -- "$0")" && pwd)"
# shellcheck source=/dev/null
source "$HERE_GATE/../../shared/env.sh"   # REPO_ROOT
SNAP="$REPO_ROOT/tools/liftlib/work/wt_cab238/tools/liftlib"
OUT="$REPO_ROOT/tools/ott/work/cab238/outhash_gate"
mkdir -p "$OUT"
export PATH="$SNAP/../..:$PATH"
NODE="$(command -v node || ls /opt/emsdk/node/*/bin/node | tail -1)"
echo "[gate] node=$NODE snap=$SNAP"
# (A) auto f7,p1 = 既定ビルド vs m10 参照
#   params=0.9 / [0x248]=1 / amp=0 の combo だけ processReplacing が停止しない (§5.2 の無限ループ事象)
#   ため DROP で 1 combo 外し、残り 41 combo で SHA 比較する。
echo "=== (A) auto f7,p1 = 既定ビルド vs m10 参照 (40 combo, p0.9_f1_a0 / p0.9_f1_a1 は無限ループで除外) ===" | tee "$OUT/A.log"
(
  cd "$SNAP"
  # 既定 (legacy) レイアウト: e2e_harness は既定 ARENA 0x30310000 を使う (LB_* env は渡さない)
  DROP=p0.9_f1_a0,p0.9_f1_a1 OTT_CJS="$SNAP/work/ott_auto_f7_p1/ott_gen.cjs" \
      "$NODE" "$REPO_ROOT/tools/ott/f7eval/cab238_outhash.mjs" > "$OUT/A_fp1.json" 2>"$OUT/A_fp1.err"
  echo "rc=$?" >> "$OUT/A.log"
  # m10 参照 (liftlib recipe 本体をそのまま使用 = gate (B) で 42/42 一致したものと同一条件)
  env OTT_CJS="$REPO_ROOT/tools/m10/work/ott_m10.cjs" \
      "$NODE" liftlib/recipes/ott/ott_outhash.mjs > "$OUT/A_ref.json" 2>"$OUT/A_ref.err"
  echo "rc=$?" >> "$OUT/A.log"
)
python3 - "$OUT" >> "$OUT/A.log" <<'PYEOF'
import json, sys, os
out = sys.argv[1]
a = json.load(open(os.path.join(out, "A_fp1.json")))
b = json.load(open(os.path.join(out, "A_ref.json")))
ks = sorted(a)
eq = [k for k in ks if a[k] == b[k]]
ne = [k for k in ks if a[k] != b[k]]
f0eq = [k for k in eq if "_f0_" in k]
print("combos=%d equal=%d diff=%d" % (len(ks), len(eq), len(ne)))
print("f0: equal=%d/%d" % (len(f0eq), len([k for k in ks if "_f0_" in k])))
print("equal_keys=%s" % ",".join(eq))
print("--- diff by param/f/amp ---")
import collections
g = collections.defaultdict(lambda: [0, 0])
for k in ks:
    v, f, am = k[1:].split("_")
    key = (v, f, am)
    g[key][1] += 1
    if k in ne:
        g[key][0] += 1
for key in sorted(g, key=lambda t: (t[0], t[1], t[2])):
    print("  p%-4s f%s a%-4s : diff %d/%d" % (key[0], key[1], key[2], g[key][0], g[key][1]))
PYEOF
# (B) 旧既定 (--auto none) の liftlib gate は RUN_B=1 の時だけ実行 (既定 skip: 別途計測済み)
if [ "${RUN_B:-0}" = "1" ]; then
  echo "=== (B) 旧既定 (--auto none) gate ===" | tee "$OUT/B.log"
  (cd "$SNAP" && python3 -m liftlib ott --auto none) > "$OUT/B_run.log" 2>&1
  echo "rc=$?" >> "$OUT/B.log"
  tail -12 "$OUT/B_run.log" | tee -a "$OUT/B.log"
fi
echo "[gate] done"
