#!/usr/bin/env bash
# check_versions.sh — D9 が capstone のどの版で再現するか (PyPI wheel を work/wheels に取得して repro_min.py を実行)
#   bash tools/icall/disp_size/check_versions.sh [version...]    既定: 5.0.5 5.0.6 5.0.7 5.0.8 5.0.9 6.0.0a11
#   env: CAPSTONE_NEXT=<capstone ソースを cmake build した dir> を指定すると upstream HEAD (next) も検査 (既定 work/capnext)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$HERE"; mkdir -p work/wheels results
VERS=("$@"); [ ${#VERS[@]} -eq 0 ] && VERS=(5.0.5 5.0.6 5.0.7 5.0.8 5.0.9 6.0.0a11)
OUT=results/capstone_versions.txt; : > "$OUT"
printf '%-12s %-14s %s\n' "pypi版" ".so sha256[:12]" "repro_min (D9 誤報告 / 13 case)" | tee -a "$OUT"
for v in "${VERS[@]}"; do
  d="work/wheels/x-$v"
  if [ ! -d "$d/capstone" ]; then
    pip download "capstone==$v" --pre --no-deps -d work/wheels -q >/dev/null 2>&1 || { echo "$v: download 失敗" | tee -a "$OUT"; continue; }
    w=$(ls work/wheels/capstone-$v-*.whl | head -1); mkdir -p "$d"; unzip -qo "$w" -d "$d"
  fi
  sha=$(sha256sum "$d"/capstone/lib/libcapstone.so | cut -c1-12)
  r=$(PYTHONPATH="$d" python3 repro_min.py 2>&1 | tail -1)
  printf '%-12s %-14s %s\n' "$v" "$sha" "$r" | tee -a "$OUT"
done
NEXT="${CAPSTONE_NEXT:-$HERE/work/capnext}"
if [ -f "$NEXT/build/libcapstone.so" ]; then
  rev=$(cut -c1-60 "$HERE/work/capnext.rev" 2>/dev/null)
  sha=$(sha256sum "$NEXT/build/libcapstone.so.6.0.0" 2>/dev/null | cut -c1-12)
  r=$(PYTHONPATH="$NEXT/bindings/python" LIBCAPSTONE_PATH="$NEXT/build" python3 repro_min.py 2>&1 | tail -1)
  printf '%-12s %-14s %s  [%s]\n' "next(HEAD)" "$sha" "$r" "$rev" | tee -a "$OUT"
fi
echo "(参考) 現環境 pip: $(pip show capstone 2>/dev/null | grep ^Version) / capstone.__version__: $(python3 -c 'import capstone;print(capstone.__version__)')" | tee -a "$OUT"
