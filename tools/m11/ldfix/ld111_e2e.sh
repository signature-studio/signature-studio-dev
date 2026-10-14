#!/usr/bin/env bash
# ld111_e2e.sh — #2396 (LD-111) 1 コマンド再現。PE (fl-win64) 無しで、work-m11 の
#   work/{boot_final.ll, boot_final3.ll, boot*.drc.config.json, m11_image.bin} だけで走る。
#   1/4 既存判定への影響: 統合前 (BASE の audit_lsf.py) と統合後 (--no-disp) の出力が byte 一致、既定 (変位形あり) は既存 3 行が一致
#   2/4 変位形 SUSPECT_DISP_VAS: 文字列転送 (movs) の列挙あり / なし (--no-strmov = #2316 時点) × boot_final.ll / boot_final3.ll
#   2b/4 fix_ld108.py (#2316 の検証用パッチ) 適用後の boot_final.ll の全関数監査 (既存判定と変位形)
#   2c/4 ldfix (ldfix_img.py) 適用後の boot_final.ll の全関数監査 (修復後 IR で変位形だけが 41a670 を拾うか)
#   3/4 残 SUSPECT 3 件 (6677a0 / d237e0 / de1da0) と 41a670 を機械語から突合 (triage_ld111.py。audit とは別算法)
#   4/4 ネガティブコントロール (NC1〜NC5。1 件ずつ壊して判定が動くことを示す)
# 使い方: bash tools/m11/ldfix/ld111_e2e.sh      環境変数: M11_WORK (既定 tools/m11/work) / PY (capstone+pefile 入り python)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../../.." && pwd)"
W="${M11_WORK:-$REPO/tools/m11/work}"
BASE=14150b46b03f8aeb40568854a0c291ae48713f23   # 統合前の main (audit_lsf.py が変位形を持たない最後の commit)
OUT="${RUNNER_TEMP:-/tmp}/ld111_e2e"; mkdir -p "$OUT"
if [ -z "${PY:-}" ]; then
  if python3 -c 'import capstone, pefile' 2>/dev/null; then PY=python3
  else uv venv "$OUT/venv" -q && uv pip install -q --python "$OUT/venv/bin/python" capstone pefile && PY="$OUT/venv/bin/python"; fi
fi
CFG="$W/boot*.drc.config.json"; IMG="$W/m11_image.bin"
ONLY=41a670,6677a0,d237e0,de1da0
step() { echo "[ld111_e2e] $*"; }
for f in "$W/boot_final.ll" "$W/boot_final3.ll" "$IMG"; do [ -f "$f" ] || { echo "[ld111_e2e] $f 無し (work-m11 を tools/m11/work に展開)"; exit 1; }; done

step "0/4 BASE=$BASE の audit_lsf.py (と ldmach*.py / lb_base.py) を取り出す"
rm -rf "$OUT/base"; mkdir -p "$OUT/base/ldfix"
for f in audit_lsf.py ldmach.py ldmach_img.py; do git -C "$REPO" show "$BASE:tools/m11/ldfix/$f" > "$OUT/base/ldfix/$f" || exit 1; done
git -C "$REPO" show "$BASE:tools/m11/lb_base.py" > "$OUT/base/lb_base.py" || exit 1

step "1/4 既存判定への影響 (SUSPECT_VAS / SUSPECT_USE_VAS / SUSPECT_MIXED_VAS と JSON 集計)"
for ir in boot_final boot_final3; do
  s=$(date +%s)
  "$PY" "$OUT/base/ldfix/audit_lsf.py" "$W/$ir.ll" "$IMG" "$CFG" > "$OUT/$ir.base.txt"
  "$PY" "$HERE/audit_lsf.py" "$W/$ir.ll" "$IMG" "$CFG" --no-disp > "$OUT/$ir.nodisp.txt"
  "$PY" "$HERE/audit_lsf.py" "$W/$ir.ll" "$IMG" "$CFG" --json "$OUT/$ir.new.json" > "$OUT/$ir.new.txt"
  e=$(date +%s)
  cmp -s "$OUT/$ir.base.txt" "$OUT/$ir.nodisp.txt" && echo "[$ir] --no-disp == 統合前: byte 一致" || echo "[$ir] --no-disp != 統合前: 不一致 (FAIL)"
  "$PY" - "$OUT/$ir.base.txt" "$OUT/$ir.new.txt" <<'EOF'
import json, sys
b = open(sys.argv[1]).read().splitlines(); n = open(sys.argv[2]).read().splitlines()
jb, jn = json.loads(b[0]), json.loads(n[0])
same_json = all(jn.get(k) == v for k, v in jb.items())
same_lines = b[1:4] == n[1:4]
print('  既定 (変位形あり) の既存 3 行: %s / 既存 JSON 集計 %d キー: %s' % ('一致' if same_lines else '不一致 (FAIL)', len(jb), '一致' if same_json else '不一致 (FAIL)'))
cnt = lambda l: len(l.split()) - 1
print('  既存: SUSPECT_VAS %d 関数 / SUSPECT_USE_VAS %d 関数 / SUSPECT_MIXED_VAS %s 関数' % (cnt(n[1]), cnt(n[2]), n[3].split()[1]))
print('  変位形: ' + n[4])
print('  ' + n[5])
print('  ' + json.dumps({k: v for k, v in jn.items() if k not in jb}, ensure_ascii=False))
EOF
  echo "  所要 (base + no-disp + 既定 の 3 回) $((e-s)) 秒 / load $(cut -d' ' -f1-3 /proc/loadavg)"
done

step "2/4 変位形 SUSPECT_DISP_VAS: 文字列転送 (movs) の列挙 なし (--no-strmov = #2316 時点) / あり (既定)"
for ir in boot_final boot_final3; do
  for opt in --no-strmov ""; do
    "$PY" "$HERE/audit_lsf.py" "$W/$ir.ll" "$IMG" "$CFG" $opt | grep -E '^(\{|SUSPECT_DISP_VAS)' | "$PY" -c "
import json, sys
l = sys.stdin.read().splitlines()
j = json.loads(l[0])
print('[$ir ${opt:-既定}] disp_mach_fns=%d suspect_disp_fns=%d / %s' % (j['disp_mach_fns'], j['suspect_disp_fns'], l[1]))"
  done
done

step "2b/4 修復後 IR (fix_ld108.py = #2316 の検証用パッチを boot_final.ll に適用) の全関数監査: 既存判定と変位形"
"$PY" "$HERE/fix_ld108.py" "$W/boot_final.ll" "$OUT/boot_final.fix108.ll" > /dev/null || exit 1
"$PY" "$HERE/audit_lsf.py" "$OUT/boot_final.fix108.ll" "$IMG" "$CFG" > "$OUT/fix108.new.txt"
echo "[boot_final+fix_ld108] $(grep '^SUSPECT_VAS' "$OUT/fix108.new.txt" | cut -c1-80) / SUSPECT_USE_VAS $(grep '^SUSPECT_USE_VAS' "$OUT/fix108.new.txt" | awk '{print NF-1}') 関数 (41a670 を含む: $(grep '^SUSPECT_USE_VAS' "$OUT/fix108.new.txt" | grep -c ' 41a670')) / $(grep '^SUSPECT_DISP_VAS' "$OUT/fix108.new.txt")"
"$PY" "$HERE/audit_lsf.py" "$OUT/boot_final.fix108.ll" "$IMG" "$CFG" --no-strmov | grep '^SUSPECT_DISP_VAS' | sed 's/^/[boot_final+fix_ld108 --no-strmov] /'

step "2c/4 ldfix (F3c ほか。ldfix_img.py = PE 無し版) 適用後の boot_final.ll の全関数監査: 修復後の IR で既存判定と変位形がどう出るか"
"$PY" "$HERE/ldfix_img.py" "$W/boot_final.ll" "$OUT/boot_final.ldfix.ll" "$IMG" "$CFG" --report "$OUT/ldfix.report.json" 2>&1 | tail -1 | cut -c1-200
"$PY" "$HERE/audit_lsf.py" "$OUT/boot_final.ldfix.ll" "$IMG" "$CFG" > "$OUT/ldfix.new.txt"
echo "[boot_final+ldfix] SUSPECT_VAS $(grep '^SUSPECT_VAS' "$OUT/ldfix.new.txt" | awk '{print NF-1}') 関数 / SUSPECT_USE_VAS $(grep '^SUSPECT_USE_VAS' "$OUT/ldfix.new.txt" | awk '{print NF-1}') 関数 / $(grep '^SUSPECT_DISP_VAS' "$OUT/ldfix.new.txt") / $(grep '^SUSPECT_DISP_ONLY_VAS' "$OUT/ldfix.new.txt" | cut -d' ' -f1-2)"

step "3/4 機械語との突合 (VA:argN:c)。LSF = 列挙漏れ (誤検出) / READ・NONE = wrong-value"
"$PY" "$HERE/triage_ld111.py" "$IMG" "$CFG" 41a670:1:8 6677a0:2:36 d237e0:2:36 de1da0:1:244

step "4/4 ネガティブコントロール (--only $ONLY。期待は各行の末尾)"
nc() { "$PY" "$HERE/audit_lsf.py" "$1" "${2:-$IMG}" "$CFG" --only "$ONLY" ${3:-} | grep '^SUSPECT_DISP_VAS' | sed "s/^/  /"; }
echo "[NC0] 無改変 (boot_final.ll)                              期待: 41a670"; nc "$W/boot_final.ll"
echo "[NC1] 文字列転送の列挙を外す (--no-strmov)                 期待: 41a670 6677a0 d237e0 de1da0"; nc "$W/boot_final.ll" "$IMG" --no-strmov
echo "[NC2] 6677a0 の machine code の movs 5 命令 (6677d1..6677da) を nop   期待: 41a670 6677a0"
"$PY" - "$IMG" "$OUT/nc2.bin" <<'EOF'
import sys
d = bytearray(open(sys.argv[1], 'rb').read())
lo, hi = 0x6677d1 - 0x400000, 0x6677da - 0x400000
assert d[lo:hi] == bytes.fromhex('48a548a548a548a5a5'), d[lo:hi].hex()
d[lo:hi] = b'\x90' * (hi - lo)
open(sys.argv[2], 'wb').write(d)
EOF
nc "$W/boot_final.ll" "$OUT/nc2.bin"
echo "[NC3] 6677a0 の IR の load 変位を 36 → 40 に変える           期待: 41a670 6677a0"
"$PY" - "$W/boot_final.ll" "$OUT/nc3.ll" <<'EOF'
import re, sys
t = open(sys.argv[1], errors='replace').read()
m = re.search(r'^define [^@]*@function_6677a0\(', t, re.M); e = t.index('\n}', m.end())
b2, n = re.subn(r'(%17 = add i64 %arg2, )36$', r'\g<1>40', t[m.start():e], flags=re.M)
assert n == 1, n
open(sys.argv[2], 'w').write(t[:m.start()] + b2 + t[e:])
EOF
nc "$OUT/nc3.ll"
echo "[NC4] 41a670 を fix_ld108.py で修復した IR (head 解除 store = [arg1+0] の load)   期待: 検出なし"
nc "$OUT/boot_final.fix108.ll"
echo "[NC5] 41a670 の machine code の arg1 zero-disp load 2 site (41a69c..41a6aa と 41a6d3..41a6d6) を nop   期待: 検出なし (IR だけでは判定しない)"
"$PY" - "$IMG" "$OUT/nc5.bin" <<'EOF'
import sys
d = bytearray(open(sys.argv[1], 'rb').read())
for lo, hi in ((0x41a69c, 0x41a6aa), (0x41a6d3, 0x41a6d6)):
    d[lo - 0x400000:hi - 0x400000] = b'\x90' * (hi - lo)
open(sys.argv[2], 'wb').write(d)
EOF
nc "$W/boot_final.ll" "$OUT/nc5.bin"
