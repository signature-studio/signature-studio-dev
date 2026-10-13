#!/usr/bin/env bash
# P0c-15 (#1253 指摘 2): f80_lower --ext の書換え行で !insn.addr が消える挙動の A/B 再現
#   bash tools/plugins/p0c/p0c15_meta_ab.sh
# 前提: python3, llvm-as (llvm-as-18 か PATH の llvm-as)。素材不要。
# 判定: [A] 書換え無し入力は旧 (origin/main) と新で byte 一致 / [B] 書換え行のメタデータは新で落ちる (旧は素通し)
#       / [C] 書換え行のメタデータ有無で ir5_patch の出力が byte 一致 (後段で insn.addr を読まない根拠)
#       / [D] 落とした後の IR が llvm-as を通る。いずれかが外れたら exit 1。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(cd -- "$HERE/../../.." && pwd)"
W="${P0C15_WORK:-$HERE/work/p0c15}"
mkdir -p "$W"
LLVM_AS="$(command -v llvm-as || command -v llvm-as-18)"
OLD="$W/f80_lower_old.py"
git -C "$ROOT" show "${P0C15_OLD_REV:-origin/main}:tools/plugins/p0c/f80_lower.py" > "$OLD"
NEW="$HERE/f80_lower.py"
F=function_5dfd30

cat > "$W/in.ll" <<'EOF'
target datalayout = "e-m:e-p:32:32-i64:64-n32:64-S128"
define void @function_5dfd30(double %a, double %b, ptr %o) {
entry:
  %1 = fmul double %a, %b, !insn.addr !1
  %2 = fadd double %1, %a, !insn.addr !2
  %3 = fptosi double %2 to i32, !insn.addr !3
  store i32 %3, ptr %o, !insn.addr !4
  ret void, !insn.addr !5
}
!1 = !{i64 4198400}
!2 = !{i64 4198404}
!3 = !{i64 4198408}
!4 = !{i64 4198412}
!5 = !{i64 4198416}
EOF
sed -E 's/, !insn\.addr !-?[0-9]+//g' "$W/in.ll" > "$W/in_nomd.ll"
# 書換え無し入力 (x87 演算なし): 旧と新で一致すること
printf 'target datalayout = "e-m:e-p:32:32-i64:64-n32:64-S128"\ndefine double @function_5dfd30(double %%a, double %%b) {\nentry:\n  %%1 = fadd double %%a, %%b\n  ret double %%1\n}\n' > "$W/noop.ll"

run() { python3 "$1" "$2" "$3" --ext --ext-funcs $F --report "$4" > /dev/null 2>&1; }
status() { python3 -c "import json,sys;print([(f['status'],f.get('rewritten')) for f in json.load(open(sys.argv[1]))['ext_functions']])" "$1"; }

run "$OLD" "$W/in.ll" "$W/old.ll" "$W/old.json"
run "$NEW" "$W/in.ll" "$W/new.ll" "$W/new.json"
run "$NEW" "$W/in_nomd.ll" "$W/new_nomd.ll" "$W/new_nomd.json"
run "$OLD" "$W/in_nomd.ll" "$W/old_nomd.ll" "$W/old_nomd.json"
echo "[B] 書換え行 (メタデータ付き) old: $(status "$W/old.json")"
echo "[B] 書換え行 (メタデータ付き) new: $(status "$W/new.json")"
echo "[B] 書換え行 new の insn.addr 残存行 (fmul/fadd/fptosi が消えていれば 2 = store/ret のみ):"
grep -c 'insn.addr' "$W/new.ll" || true

fail=0
if cmp -s "$W/old_nomd.ll" "$W/new_nomd.ll"; then echo "[A] 書換え無し (メタデータ無し) old==new: PASS"; else echo "[A] FAIL"; fail=1; fi
python3 "$ROOT/tools/m5/ir5_patch.py" "$W/new.ll" "$W/ir5_md.ll" --keep-all > /dev/null 2>&1
python3 "$ROOT/tools/m5/ir5_patch.py" "$W/new_nomd.ll" "$W/ir5_nomd.ll" --keep-all > /dev/null 2>&1
if cmp -s "$W/ir5_md.ll" "$W/ir5_nomd.ll"; then echo "[C] ir5_patch 出力 (メタデータ有無) byte 一致: PASS"; else echo "[C] FAIL"; fail=1; fi
for f in new.ll new_nomd.ll ir5_md.ll ir5_nomd.ll; do
  if "$LLVM_AS" "$W/$f" -o /dev/null 2>/dev/null; then echo "[D] llvm-as $f: PASS"; else echo "[D] llvm-as $f: FAIL"; fail=1; fi
done
exit $fail
