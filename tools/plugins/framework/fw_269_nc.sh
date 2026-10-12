#!/usr/bin/env bash
# fw_269_nc.sh — CAB-269 のネガティブコントロール (規則 41: 主要検査を 1 つ壊して FAIL を確認)。
#
#   bash fw_269_nc.sh [SRC_W]
#     SRC_W: fw_stage2.sh が完走した W (既定 work/verify_269/fw)。成果物をハードリンクして
#            canon 段以降だけを作り直すので、SRC_W は書換わらない。
#
# 5 件 (NC1-NC4 = S1-S4 の修正を個別に外す / NC5 = entry export 名破壊):
#   NC1 S1: fw_boot.c を W に置かない → emcc `fw_boot.c: No such file or directory`
#   NC2 S2: fw_canon.py の ceclone 採番を 0 からにして canon 段と衝突させる
#           → llvm-as `multiple definition of local value named 'ceclone1'`
#   NC3 S3: fldenv の declare を置き換えず削除 → llvm-as `use of undefined value '@fw_fldenv'`
#   NC4 S4: fw_ovpass.py を trunc に戻す → llvm-as `invalid cast opcode for cast from 'i64' to 'i128'`
#   NC5 entry: `_function_6c13a0` を存在しない export 名に → smoke `SMOKE FAIL: ... export されていない`
# 判定: 全件が期待するエラー文字列で FAIL すること (PASS しか出ない検査は判別力なし)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/../../shared/env.sh"
T="$REPO_ROOT"
SRCW="${1:-$HERE/work/verify_269/fw}"
N="$HERE/work/nc269"
FW="$HERE"
export PATH="$PATH:/opt/emsdk/node/24.19.0_64bit/bin"
export TMPDIR="$N/tmp"; mkdir -p "$N/tmp"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1

# canon 段以降だけ作り直す (canon2/canon3/route/table/image は作らない)
EXCL="fw_route.cjs fw_route.wasm smoke.log fw_flat4.ll fw_simd.c fw_flat4_canon.ll fw_flat4_canon2.ll \
fw_flat4_canon3.ll fw_table.c fw_image.bin fw_imports.json fw_canon_flat4.json fw_canon_canon.json emcc.log"

pass=0; fail=0
report() { # $1=名前 $2=期待文字列 $3=ログ $4=exit
  if [ $4 != 0 ] && grep -q "$2" "$3"; then echo "  [NC] OK   期待どおり FAIL: $1"; pass=$((pass+1));
  else echo "  [NC] **NG** 期待外 (exit=$4): $1 → $3"; fail=$((fail+1)); fi
}

setup_nc() { # $1 = NC 用 W
  local d="$1" f b
  rm -rf "$d"; mkdir -p "$d"
  for f in "$SRCW"/*; do
    [ -f "$f" ] || continue
    b=$(basename "$f")
    case " $EXCL " in *" $b "*) continue ;; esac
    ln -f "$f" "$d/$b"
  done
  # stage_inputs が $HERE からコピーするので W 側のコピーは外す
  rm -f "$d/fw_boot.c" "$d/fw_rt.c" "$d/fw_rt.h"
}

# 破損した script 1 本だけ差し替えた「偽 HERE」を作る ($2 = 差し替えファイル, $3 = ファイル名)
make_fake_here() { # $1 = 出力dir $2 = 破損ファイル(省略可) $3 = その名前
  local d="$1" e
  rm -rf "$d"; mkdir -p "$d"
  for e in "$FW"/*; do ln -s "$e" "$d/$(basename "$e")"; done
  [ -n "${2:-}" ] && ln -sf "$2" "$d/$3"
  return 0
}

# 偽 HERE に sed で壊した fw_stage2.sh を置く ($1 = 出力dir $2 = sed 式)
make_fake_stage2() { # $1 = 出力dir $2 = sed 式
  make_fake_here "$1"
  rm -f "$1/fw_stage2.sh"
  sed "$2" "$FW/fw_stage2.sh" > "$1/fw_stage2.sh"
}

echo "[nc269] SRC_W=$SRCW"
[ -f "$SRCW/fw_route.cjs" ] || { echo "[nc269] SRC_W に fw_route.cjs が無い" >&2; exit 1; }

# ---------------- NC1 (S1): fw_boot.c をコピーしない旧挙動 ----------------
echo "== NC1 (S1): stage_inputs に fw_boot.c を含めない =="
W1="$N/fw_s1"; setup_nc "$W1"
make_fake_stage2 "$N/here_s1" 's/for f in fw_rt.h fw_rt.c fw_boot.c; do/for f in fw_rt.h fw_rt.c; do/'
grep -q "fw_boot.c" "$N/here_s1/fw_stage2.sh"
FW_W="$W1" bash "$N/here_s1/fw_stage2.sh" > "$N/nc1.log" 2>&1 && rc=0 || rc=$?
report "S1 fw_boot.c 未コピー" "fw_boot.c: No such file or directory" "$N/nc1.log" $rc

# ---------------- NC2 (S2): ceclone 採番を 0 から (canon 段で衝突) ----------------
echo "== NC2 (S2): uid 採番を衝突させる =="
W2="$N/fw_s2"; setup_nc "$W2"
python3 - "$FW/fw_canon.py" "$N/fw_canon_bad.py" <<'PY'
import sys
src = open(sys.argv[1]).read()
src = src.replace('UID_BASE = 10000', 'UID_BASE = 0')
src = src.replace('return max([UID_BASE] + nums) if nums else UID_BASE', 'return 0')  # 継続採番も外す
open(sys.argv[2], 'w').write(src)
assert 'return 0' in src and 'UID_BASE = 0' in src
PY
make_fake_here "$N/here_s2" "$N/fw_canon_bad.py" "fw_canon.py"
FW_W="$W2" bash "$N/here_s2/fw_stage2.sh" > "$N/nc2.log" 2>&1 && rc=0 || rc=$?
report "S2 ceclone 二重定義" "multiple definition of local value named 'ceclone1'" "$N/nc2.log" $rc

# ---------------- NC3 (S3): fldenv declare を置き換えず削除 ----------------
echo "== NC3 (S3): fw_fldenv の declare を欠落させる =="
W3="$N/fw_s3"; setup_nc "$W3"
python3 - "$FW/fw_canon.py" "$N/fw_canon_s3.py" <<'PY'
import sys
src = open(sys.argv[1]).read()
old = "FLDENV_DECL_RE.subn('declare void @fw_fldenv(ptr) local_unnamed_addr', text)"
assert old in src
src = src.replace(old, "FLDENV_DECL_RE.subn('', text)")
open(sys.argv[2], 'w').write(src)
PY
make_fake_here "$N/here_s3" "$N/fw_canon_s3.py" "fw_canon.py"
FW_W="$W3" bash "$N/here_s3/fw_stage2.sh" > "$N/nc3.log" 2>&1 && rc=0 || rc=$?
report "S3 fw_fldenv declare 欠落" "use of undefined value '@fw_fldenv'" "$N/nc3.log" $rc

# ---------------- NC4 (S4): ovpass を trunc に戻す ----------------
echo "== NC4 (S4): i128 戻りを trunc に戻す =="
W4="$N/fw_s4"; setup_nc "$W4"
python3 - "$FW/fw_ovpass.py" "$N/fw_ovpass_bad.py" <<'PY'
import sys
src = open(sys.argv[1]).read()
old = "%%t = zext i64 %s to %s' % (r, rt)"
assert old in src, 'zext 行が見つからない'
src = src.replace(old, "%%t = trunc i64 %s to %s' % (r, rt)")
open(sys.argv[2], 'w').write(src)
PY
make_fake_here "$N/here_s4" "$N/fw_ovpass_bad.py" "fw_ovpass.py"
FW_W="$W4" bash "$N/here_s4/fw_stage2.sh" > "$N/nc4.log" 2>&1 && rc=0 || rc=$?
report "S4 trunc i64 → i128" "invalid cast opcode for cast from 'i64' to 'i128'" "$N/nc4.log" $rc

# ---------------- NC5: entry export 名破壊 ----------------
echo "== NC5: entry export 名を壊す =="
W5="$N/fw_s5"; setup_nc "$W5"
make_fake_stage2 "$N/here_s5" 's/_function_6c13a0,_function_4189c0/_function_6c13a1,_function_4189c0/'
grep -q "_function_6c13a1" "$N/here_s5/fw_stage2.sh" || { echo "[nc269] NC5 の sed が不発" >&2; exit 1; }
FW_W="$W5" bash "$N/here_s5/fw_stage2.sh" > "$N/nc5.log" 2>&1 && rc=0 || rc=$?
# 注意: fw_run.mjs のメッセージは `entry function_6c13a0` と export 名をハードコードしている
# (実 export 名を 6c13a1 に壊しても 6c13a0 と出る)。FAIL したことを期待文字列で確認する。
report "entry export 名破壊" "SMOKE FAIL: entry function_6c13a0 が export されていない" "$N/nc5.log" $rc

echo "[nc269] 結果: OK=$pass NG=$fail (5 件期待)"
[ $fail = 0 ]
