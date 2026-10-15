#!/usr/bin/env bash
# #3801 (KH-65): Delay の型不一致 (`_DAT_<va>` のグローバル型) の規則 `--fix gtype` を census し、Gain/Haas/Gate の .o 不変を見る。
#   bash tools/targets/kilohearts/ghidra_route/gtype_census.sh <work>
# <work> は repo 外 (例: $RUNNER_TEMP/kh)。下に次を置く前提:
#   <work>/win/HeartCore.core_64   plugins-kilohearts の Installer zip → payload.dat → windows.zip/1ccb1df8c8f10745 → HeartCore.core_64
#   <work>/emsdk                   toolchain-emsdk (emsdk_env.sh を source する)
#   <work>/ghidra/ghidra_12.1.4_PUBLIC   Ghidra 12.1.4 (zip sha256 ddac49f9…d2db)。JAVA_HOME 既定は temurin-21
# 出力: <work>/gtype/ 配下。stdout に delay の census と gain/haas/gate の .o の cmp 結果。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; KH="$(cd -- "$HERE/.." && pwd)"
W=${1:?usage: gtype_census.sh <work>}
CORE="$W/win/HeartCore.core_64"; O="$W/gtype"
GHIDRA="$W/ghidra/ghidra_12.1.4_PUBLIC"; export JAVA_HOME=${JAVA_HOME:-/usr/lib/jvm/temurin-21-jdk-amd64}; export PATH="$JAVA_HOME/bin:$PATH"
FX=bitcast,intload,stackpair,assoc,concat,gtype
rm -rf "$O"; mkdir -p "$O/out" "$W/proj"
# lift 集合 = delay・stereo の lift 一意アドレス ∪ gain・haas・gate (昇順・10 進。0x 付きの引数は使わない)
VAS=$(cd "$KH" && python3 -c "
import json
d=json.load(open('snapins/snapins.json')); s=set()
for k in ['delay','stereo']:
    s.update(int(v,16) for v in d[k]['lift'].values() if isinstance(v,str))
s.update(int(x,16) for x in ['0x1804b0380','0x1804d0280','0x1804d0180','0x1804cff00','0x1804cff90','0x1804d0720','0x1804c2f50','0x180295f20','0x180020e70'])
print(' '.join(str(x) for x in sorted(s)))")
JAVA_TOOL_OPTIONS="-Xmx10g" timeout 900 "$GHIDRA/support/analyzeHeadless" "$W/proj" kh -import "$CORE" -noanalysis \
  -scriptPath "$KH/scripts/ghidra" -postScript DecompEach.java "$O/out" $VAS -deleteProject > "$O/ghidra.log" 2>&1
awk -F'\t' 'NR>1{print $5}' "$O/out/summary.tsv" | sort | uniq -c
source "$W/emsdk/emsdk_env.sh" >/dev/null 2>&1
python3 "$HERE/ghidra_to_c.py" delay "$O/delay" "$O/out" "$CORE" --fix $FX >/dev/null
emcc -c -ferror-limit=0 -I "$HERE" "$O/delay/delay.c" -o "$O/delay/delay.o" 2> "$O/delay/emcc.log" || true
echo "delay emcc error 行: $(grep -c 'error:' "$O/delay/emcc.log" || true)"
python3 "$HERE/emcc_census.py" "$O/delay/emcc.log"
F="-w -O1 -Wno-error=int-conversion -Wno-error=incompatible-pointer-types -Wno-error=incompatible-pointer-types-discards-qualifiers"
# 第 2 引数 (任意) = 比較する旧 ghidra_route dir (例: git archive で展開した origin/main の tools/targets/kilohearts/ghidra_route)
for n in gain haas gate; do
  python3 "$HERE/ghidra_to_c.py" $n "$O/$n" "$O/out" "$CORE" --fix $FX >/dev/null
  emcc $F -I "$HERE" -c "$O/$n/$n.c" -o "$O/$n/$n.o" 2>/dev/null
  echo "$n .o: $(stat -c %s "$O/$n/$n.o") B"
  if [ -n "${2:-}" ]; then
    python3 "$2/ghidra_to_c.py" $n "$O/base/$n" "$O/out" "$CORE" --fix bitcast,intload,stackpair,assoc,concat >/dev/null
    emcc $F -I "$HERE" -c "$O/base/$n/$n.c" -o "$O/base/$n/$n.o" 2>/dev/null
    cmp "$O/base/$n/$n.o" "$O/$n/$n.o" && echo "$n .o: 旧規則と一致"
  fi
done
