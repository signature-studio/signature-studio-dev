#!/usr/bin/env bash
# dispatch_calls.py の識別力を確認するネガティブコントロール (対照 = golden 一致で rc 0、壊したものが rc 1)。
#   NC1: golden の selector 1 件を改変 (sel 2 → 3) → rc 1
#   NC2: golden から 1 件落とす (件数不足) → rc 1
#   NC3: golden に存在しない呼出し先を足す (件数超過) → rc 1
# exit 0 = 全て期待通り
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/env.sh"
PE="$FL_WIN64_DIR/extracted/block23663_PE.bin"
GOLD=0x846ab0:2,0x846af4:4,0x846b3c:3,0x846b8f:5,0x8439d1:10,0x847220:11,0x8473c8:13,0x8474ad:14,0x847547:12
FAIL=0
run() { # run <label> <期待 rc> <golden>
  set +e; python3 "$HERE/dispatch_calls.py" "$PE" --expect="$3" > /dev/null 2>&1; rc=$?; set -e
  if [ "$rc" = "$2" ]; then echo "ok   $1 rc=$rc"; else echo "!!   $1: rc=$rc 期待 $2" >&2; FAIL=1; fi
}
run "対照 (golden 一致)" 0 "$GOLD"
run "NC1 selector 改変" 1 "${GOLD/0x846ab0:2/0x846ab0:3}"
run "NC2 件数不足" 1 "${GOLD%,0x847547:12}"
run "NC3 件数超過" 1 "$GOLD,0x847600:1"
exit $FAIL
