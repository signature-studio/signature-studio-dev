#!/usr/bin/env bash
# full lift in N chunks (argv limit 回避) — 完了を work/boot.N*.lift.ll + work/boot_all.DONE マーカで示す
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$HERE"
PER=1900
src=work/boot_ranges.txt
rm -f work/boot.N*.lift.DONE work/boot_all.DONE work/chunk_*.txt
python3 - <<'PY'
rs = open('/home/ubuntu/work/webstudio/tools/m11/work/boot_ranges.txt').read().split(',')
per = 1900
n = 0
for i in range(0, len(rs), per):
    open('/home/ubuntu/work/webstudio/tools/m11/work/chunk_%d.txt' % n, 'w').write(','.join(rs[i:i + per]))
    n += 1
print('chunks:', n)
PY
CH=$(ls work/chunk_*.txt | wc -l)
for i in $(seq 0 $((CH - 1))); do
  echo "[chunk $i] start $(date +%T)"
  bash m11_lift.sh work/chunk_$i.txt boot$i 1800 > work/boot_lift_i$i.out 2>&1
  rc=$?
  touch "work/boot$i.lift.DONE"
  echo "[chunk $i] rc=$rc end $(date +%T)"
done
touch work/boot_all.DONE
echo "[boot lift all] done $(date +%T)"
