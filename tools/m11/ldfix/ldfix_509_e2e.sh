#!/usr/bin/env bash
# ldfix_509_e2e.sh — #509 (LD-9) 1 コマンド再現。work-m11 の
#   work/{boot*.lift.ll, boot*.drc.config.json, m11_image.bin, boot_final.ll, boot_final3.ll} と [EMSDK], node に加え、
#   6/7 の修復後 IR 生成 (ldfix.py --pe) のために fl-win64 の PE (FL_WIN64_DIR) が要る (#1290)。
#   1/7 修復前 IR を再生成 (audit_lsf_e2e.sh と同じ)
#   2/7 ldfix 旧版 ($PREV_REF) / 新版 (HEAD) を同じ修復前 IR に適用 → 出力が異なる関数の一覧 (他の関数は byte 一致)
#   3/7 audit_lsf.py (store 形 + 消費者形) を 修復前 / 旧版 / 新版 に実行
#   4/7 既に ldfix 済みの work/boot_final.ll へ F3c だけを重ねた IR (--passes f3c) と新版出力の突合
#   5/7 ネガティブコントロール (旧版 = 修復を外す / 新版の store 1 本・消費者 1 関数を戻す)
#   6/7 修復前後の wasm を作り survey 942 unit を unit ごとに突合 + 修復した関数の動的到達 (reach_509.sh)
#        修復前 wasm: step 1 の ldfix=disabled 記録 + M11_ALLOW_LDFIX_DISABLED=1 (明示 opt-in)。
#        修復後 wasm: 修復前 IR を ldfix.py --pe で正規適用 → ldfix=applied → ld108=disabled (#2402: fix_ld108 は適用しない。REPORT_1290 の測定条件を保つ) → --bind → M11_ALLOW_LD108_DISABLED=1 で build (#1290)。
#   7/7 修復前後の wasm で 5 関数を直接呼んで期待値と突き合わせ (dyn_509.mjs)
# 使い方: EMSDK_ENV=<[EMSDK] の emsdk_env.sh> bash tools/m11/ldfix/ldfix_509_e2e.sh      環境変数: EMSDK_ENV (必須、[EMSDK] の emsdk_env.sh) / M11_WORK (既定 tools/m11/work) / PY (capstone+pefile 入り python) / PREV_REF (既定 009e823)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../../.." && pwd)"
W="${M11_WORK:-$REPO/tools/m11/work}"
PREV_REF="${PREV_REF:-009e823}"
OUT="${RUNNER_TEMP:-/tmp}/ldfix_509_e2e"; rm -rf "$OUT"; mkdir -p "$OUT"
export PATH="$HOME/.local/share/pnpm/bin:$PATH"
if [ -z "${PY:-}" ]; then
  if python3 -c 'import capstone, pefile' 2>/dev/null; then PY=python3
  else uv venv "$OUT/venv" -q && uv pip install -q --python "$OUT/venv/bin/python" capstone pefile && PY="$OUT/venv/bin/python"; fi
fi
CFG="$W/boot*.drc.config.json"; IMG="$W/m11_image.bin"
PE_QS="${PE:-${FL_WIN64_DIR:?FL_WIN64_DIR (fl-win64 の展開先) を指定してください}/extracted/block00031_PE.bin}"
: "${EMSDK_ENV:?EMSDK_ENV (<[EMSDK]> の emsdk_env.sh) を指定してください}"   # reach_509.sh が要る (未指定だと 6/7 の reach だけ失敗して rc 0 になっていた)
step() { echo "[ldfix_509_e2e] $*"; }
FNS="5c0270,41a670,66e080,7e5240,806740,c62780,417b70,409c80,666a60,1062c50,1063090,12cb4f0,12f9730,4087a0,40ffe0,447ee0,44f110,44f1d0,44f2c0,44f740,6074b0,7763d0,8239d0,86a7c0,8c7710,f3dd20"

step "1/7 修復前 IR を再生成"
mkdir -p "$OUT/gen/tools"; cp -r "$REPO/tools/m11" "$REPO/tools/shared" "$OUT/gen/tools/"; rm -rf "$OUT/gen/tools/m11/work"; mkdir -p "$OUT/gen/tools/m11/work"
for f in boot0 boot1 boot2 boot3 boot4; do cp "$W/$f.lift.ll" "$OUT/gen/tools/m11/work/"; done
find "$W" -maxdepth 1 -type f -size -3M -exec cp {} "$OUT/gen/tools/m11/work/" \;
( cd "$OUT/gen/tools/m11" && M11_LDFIX=0 bash m11_gen_ir2.sh > "$OUT/gen_ir2.log" 2>&1 ) || { echo "gen_ir2 失敗: $OUT/gen_ir2.log"; exit 1; }
PRE="$OUT/gen/tools/m11/work/boot_final.ll"

step "2/7 ldfix 旧版 ($PREV_REF) / 新版 (HEAD)"
mkdir -p "$OUT/prev/ldfix"; cp "$HERE"/ldmach.py "$HERE"/ldmach_img.py "$HERE"/ldfix_img.py "$OUT/prev/ldfix/"; cp "$REPO/tools/m11/lb_base.py" "$OUT/prev/"
git -C "$REPO" show "$PREV_REF:tools/m11/ldfix/ldfix.py" > "$OUT/prev/ldfix/ldfix.py"
"$PY" "$OUT/prev/ldfix/ldfix_img.py" "$PRE" "$OUT/prev.ll" "$IMG" "$CFG" --report "$OUT/prev_report.json" 2>&1 | tail -1
"$PY" "$HERE/ldfix_img.py" "$PRE" "$OUT/new.ll" "$IMG" "$CFG" --report "$OUT/new_report.json" 2>&1 | tail -1
"$PY" - "$OUT/prev.ll" "$OUT/new.ll" "$OUT/prev_report.json" "$OUT/new_report.json" <<'PYEOF'
import json, re, sys
def fns(f):
    t = open(f, errors='replace').read()
    d = {m.group(1): m.group(0) for m in re.finditer(r'^define [^\n]*@(function_[0-9a-f]+)\(.*?\n}\n', t, re.M | re.S)}
    return d, re.sub(r'^define [^\n]*@function_[0-9a-f]+\(.*?\n}\n', '', t, flags=re.M | re.S)
(A, ra), (B, rb) = fns(sys.argv[1]), fns(sys.argv[2])
diff = [k[9:] for k in A if A[k] != B.get(k)]
print('[diff] 旧版/新版で本体が異なる関数: %d / %d  %s' % (len(diff), len(A), ' '.join(diff)))
print('[diff] 関数外のテキストは一致: %s' % (ra == rb))
a, b = json.load(open(sys.argv[3])), json.load(open(sys.argv[4]))
print('[diff] report キーの差 (f3c 以外): %s' % [k for k in sorted(set(a) | set(b)) if not k.startswith('f3c') and a.get(k) != b.get(k)])
print('[diff] F3c 関数: 旧 %d → 新 %d (旧の全てを含む: %s)' % (a['f3c_fns'], b['f3c_fns'], set(a['f3c_vas']) <= set(b['f3c_vas'])))
print('[diff] f3c_no_store (block-local 門): 旧 %s 新 %s / F3c-fn 門 stores %s / F3c-use 置換行 %s' % (a.get('f3c_no_store'), b.get('f3c_no_store'), b.get('f3c_fn_stores'), b.get('f3c_use_replaced')))
PYEOF

step "3/7 audit_lsf.py (store 形 + 消費者形): 修復前 / 旧版 / 新版"
for k in pre prev new; do
  case $k in pre) F="$PRE";; prev) F="$OUT/prev.ll";; new) F="$OUT/new.ll";; esac
  "$PY" "$HERE/audit_lsf.py" "$F" "$IMG" "$CFG" --json "$OUT/audit_$k.json" | sed "s/^/[$k] /" | cut -c1-700
done

step "4/7 既に ldfix 済みの work/boot_final.ll へ F3c だけ重ねる (--passes f3c)"
"$PY" "$HERE/ldfix_img.py" "$W/boot_final.ll" "$OUT/bf_f3c.ll" "$IMG" "$CFG" --passes f3c --report "$OUT/bf_f3c_report.json" 2>&1 | tail -1
"$PY" - "$W/boot_final.ll" "$OUT/bf_f3c.ll" "$OUT/new.ll" <<'PYEOF'
import re, sys
def fns(f):
    t = open(f, errors='replace').read()
    return {m.group(1): m.group(0) for m in re.finditer(r'^define [^\n]*@(function_[0-9a-f]+)\(.*?\n}\n', t, re.M | re.S)}
orig, ov, new = fns(sys.argv[1]), fns(sys.argv[2]), fns(sys.argv[3])
ch = [k for k in orig if orig[k] != ov[k]]
strip = lambda b: [l for l in b.split('\n') if ' = alloca ' not in l]
same = [k for k in ch if strip(ov[k]) == strip(new[k])]
print('[overlay] boot_final.ll から変わった関数 %d、うち 新版出力と alloca 行を除いて同一 %d' % (len(ch), len(same)))
PYEOF

step "5/7 ネガティブコントロール"
"$PY" - "$OUT/new.ll" "$OUT" <<'PYEOF'
import re, sys
t = open(sys.argv[1], errors='replace').read()
# NC-store: 806740 の修復 store (load 経由) を %arg3 に戻す
m = re.search(r'^define [^\n]*@function_806740\(.*?\n}\n', t, re.M | re.S)
b = m.group(0)
b2 = re.sub(r'(store i64 )%ldfxn\d+(, ptr %17, align 8)', r'\1%arg3\2', b)
assert b2 != b
open(sys.argv[2] + '/nc_store.ll', 'w').write(t.replace(b, b2))
# NC-use: 1063090 の消費者置換を戻す (挿入した load 2 行を消し、%ldfxu* を %arg1 に戻す)
m = re.search(r'^define [^\n]*@function_1063090\(.*?\n}\n', t, re.M | re.S)
b = m.group(0)
b2 = re.sub(r'^  %ldfxu\d+_p = .*\n  %ldfxu\d+ = load .*\n', '', b, flags=re.M)
b2 = re.sub(r'%ldfxu\d+(?![\w.$-])', '%arg1', b2)
assert b2 != b and 'ldfxu' not in b2
open(sys.argv[2] + '/nc_use.ll', 'w').write(t.replace(b, b2))
PYEOF
for k in prev nc_store nc_use; do
  F="$OUT/$k.ll"
  "$PY" "$HERE/audit_lsf.py" "$F" "$IMG" "$CFG" > "$OUT/nc_$k.txt"
  echo "[NC:$k] $(grep -o '"suspect_fns": [0-9]*, "suspect_sites": [0-9]*' "$OUT/nc_$k.txt" || echo 'store 形 SUSPECT 0') / $(grep '^SUSPECT_VAS' "$OUT/nc_$k.txt" | cut -c1-120) / use 形(pure): $(grep '^SUSPECT_USE_VAS' "$OUT/nc_$k.txt" | awk '{print NF-1}') 関数 (1063090 を含む: $(grep '^SUSPECT_USE_VAS' "$OUT/nc_$k.txt" | grep -c ' 1063090'))"
done

step "6/7 survey 前後 (wasm 再ビルド) と動的到達"
B="$OUT/build"; mkdir -p "$B/tools"; cp -a "$REPO/tools/shim" "$REPO/tools/shared" "$B/tools/"; cp -a "$REPO/tools/m11" "$B/tools/m11_src"; rm -rf "$B/tools/m11_src/work"; mv "$B/tools/m11_src" "$B/tools/m11"; cp -a "$W" "$B/tools/m11/work"
mkdir -p "$OUT/basewasm"
FAIL=0
( cd "$B/tools/m11" && cp "$OUT/gen/tools/m11/work/ir_conditions.json" work/ && cp "$PRE" work/boot_final.ll && rm -f work/boot_final3.ll \
  && M11_ALLOW_LDFIX_DISABLED=1 bash m11_build.sh > "$OUT/build_base.log" 2>&1 \
  && cp work/m11_boot.cjs work/m11_boot.cjs.wasm "$OUT/basewasm/" && node trap_triage/survey_units.mjs "$OUT/sv_base.json" | tail -1 ) || { echo "[ldfix_509_e2e] 修復前 wasm の build/survey 失敗: $OUT/build_base.log"; FAIL=1; }
( cd "$B/tools/m11" && cp "$PRE" work/boot_final.ll && "$PY" ldfix/ldfix.py work/boot_final.ll work/boot_final.ldfix.ll --pe "$PE_QS" --report work/ldfix_report.json > "$OUT/ldfix_new.log" 2>&1 \
  && mv work/boot_final.ldfix.ll work/boot_final.ll && python3 m11_cond.py ldfix=applied && python3 m11_cond.py ld108=disabled && python3 m11_cond.py --bind work/boot_final.ll \
  && rm -f work/boot_final3.ll && M11_ALLOW_LD108_DISABLED=1 bash m11_build.sh > "$OUT/build_new.log" 2>&1 \
  && node trap_triage/survey_units.mjs "$OUT/sv_new.json" | tail -1 ) || { echo "[ldfix_509_e2e] 修復後 wasm の build/survey 失敗: $OUT/build_new.log"; FAIL=1; }
( cd "$B/tools/m11" && python3 trap_triage/survey_diff.py "$OUT/sv_base.json" "$OUT/sv_new.json" )
"$PY" - "$OUT/sv_base.json" "$OUT/sv_new.json" <<'PYEOF'
import json, re, sys
def norm(r):
    r = dict(r)
    if 'frames' in r:
        r['frames'] = [re.sub(r'wasm://wasm/[0-9a-f]+:|:0x[0-9a-f]+$', '', f) for f in r['frames']]
    return r
a = [norm(x) for x in json.load(open(sys.argv[1]))]; b = [norm(x) for x in json.load(open(sys.argv[2]))]
d = [x['unit'] for x, y in zip(a, b) if x != y]
print('[survey] 正規化後 (wasm hash / offset を除く) に unit 記録 (kind・msg・frame・stub 呼出・va_mb) が異なる unit: %d %s' % (len(d), d[:20]))
PYEOF
M11_WORK="$B/tools/m11/work" bash "$HERE/reach_509.sh" "$FNS" "$OUT/reach.json" || FAIL=1

step "7/7 動的確認 (修復前 wasm / 修復後 wasm を直接呼ぶ)"
if [ "$FAIL" = 0 ]; then
  node "$HERE/dyn_509.mjs" "$OUT/basewasm/m11_boot.cjs" "$B/tools/m11/work/m11_boot.cjs" "$IMG" || FAIL=1
else
  echo "[ldfix_509_e2e] 6/7 で修復前 wasm が作れていないため 7/7 は未実行"
fi
if [ "$FAIL" = 0 ]; then echo "[ldfix_509_e2e] 完了 (成果物: $OUT)"; else echo "[ldfix_509_e2e] 失敗 (成果物: $OUT)" >&2; fi
exit "$FAIL"
