#!/usr/bin/env bash
# KH-51 (#3306) §3-3: module A/B/E/F の lowered.ll と mod.wasm が、比較元 commit の kh_lower と現在の kh_lower で一致することを確かめる。
#   usage: bash scripts/lowered_identity.sh [比較元 commit (既定 64fd760)]   (license/ で実行。素材 = work/winpkg/HeartCore.core_64)
# 比較元は git worktree (license/work/wt_before) に展開する。RetDec の stage-0 キャッシュ (work/retdec0) と HeartCore は共有する。
# 不一致が 1 件でもあれば rc 1。
set -euo pipefail
LIC="$(cd -- "$(dirname -- "$0")/.." && pwd)"
KILO="$(dirname -- "$LIC")"
BASE="${1:-64fd760}"
REPO="$(git -C "$LIC" rev-parse --show-toplevel)"
WT="$LIC/work/wt_before"
WLIC="$WT/tools/targets/kilohearts/license"
[ -f "$KILO/work/winpkg/HeartCore.core_64" ] || { echo "HeartCore.core_64 が無い: KH_UI_WORK=$KILO/work bash $KILO/ui_eval/extract_core.sh" >&2; exit 2; }
mkdir -p "$LIC/work"
git -C "$REPO" worktree add --detach "$WT" "$BASE" >/dev/null
trap 'git -C "$REPO" worktree remove --force "$WT" >/dev/null 2>&1 || true' EXIT
mkdir -p "$WLIC/work"
ln -sfn "$KILO/work" "$WT/tools/targets/kilohearts/work"
for m in A B E F; do
  (cd "$LIC" && python3 lic_build.py --module "$m" > "$LIC/work/identity_now_$m.json")
done
ln -sfn "$LIC/work/retdec0" "$WLIC/work/retdec0"
for m in A B E F; do
  (cd "$WLIC" && python3 lic_build.py --module "$m" > "$LIC/work/identity_base_$m.json")
done
rc=0
for m in A B E F; do
  a="$LIC/work/lic$m"; b="$WLIC/work/lic$m"
  if cmp -s "$a/lowered.ll" "$b/lowered.ll"; then l=IDENTICAL; else l=DIFF; rc=1; fi
  if cmp -s "$a/mod.wasm" "$b/mod.wasm"; then w=IDENTICAL; else w=DIFF; rc=1; fi
  echo "module=$m lowered.ll=$l ($(grep -c '@ymm' "$a/lowered.ll" || true) ymm refs) mod.wasm=$w sha256=$(sha256sum "$a/mod.wasm" | cut -c1-64) bytes=$(stat -c %s "$a/mod.wasm")"
done
echo "base=$BASE rc=$rc"
exit $rc
