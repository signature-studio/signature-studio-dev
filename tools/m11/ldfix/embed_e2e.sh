#!/usr/bin/env bash
# embed_e2e.sh — CAB-131 ldfix 常設化 (m11_gen_ir2.sh 組込) の A/B 検収 (tools/m11/ldfix 内で完結)。
#
#   bash tools/m11/ldfix/embed_e2e.sh [--batch]
#
# 比較する 2 本の IR (どちらも m11_gen_ir2.sh の素出力 = m11_post 前・alloca 適用前):
#   base = ldfix 適用前 (常設化前の committed pipeline 出力と byte 同一であることを確認済)
#   fix  = ldfix 適用後 (常設化後の pipeline が生成する実 IR; F1v 変種 4 関数追加修復を含む)
# 比較軸:
#   (1) stage4 回帰 (mainline 相当): ldfix/stage4.sh — 共有 work/obj や work/boot_final3.ll を
#       使わない自完結 build (CAB-231 の ldfix_e2e.sh と同一方式) → reached_stage / units_run /
#       init_count / GetMem / icall_ok / wasm-ld mismatch/undefined
#   (2) 942 unit survey (stage4 build 上, survey_stage4.mjs) → ok/trap/kinds
#   (3) --batch: liftdiff closure 全数 batch (fix IR) → load_dropped 残数 (目標 0) と verdict 遷移
#
# base IR の再生成: ir_base_noldfix.ll が無ければ git HEAD (7dc07f4) 版の m11_gen_ir2.sh を
#   一時 dir で実行して作る (常設化前の素 pipeline)。
# 中断再開: 各 step の完了マーカーを ldfix/work/embed_*.done に置く (サーバ再起動対策)。
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO="$(cd -- "$HERE/../../.." && pwd)"
cd "$REPO"
export PATH="$HOME/.local/share/pnpm/bin:$PATH"
PE=/home/ubuntu/work/analysis/win64/extracted/block00031_PE.bin
BATCH=0
for a in "$@"; do case "$a" in --batch) BATCH=1 ;; esac; done

step() { echo "[embed_e2e] $(date +%H:%M:%S) $*"; }
mark() { touch "$HERE/work/embed_$1.done"; }
done_p() { [ -f "$HERE/work/embed_$1.done" ]; }

mkdir -p "$HERE/work"

# 0. IR の確保 --------------------------------------------------------------------
BASE_IR="$HERE/work/ir_base_noldfix.ll"
FIX_IR="$HERE/work/ir_fix_embedded.ll"
if [ ! -f "$FIX_IR" ]; then
  step "fix IR 無し → 常設化後 gen_ir2.sh を実行"
  (cd tools/m11 && bash m11_gen_ir2.sh) > "$HERE/work/embed_genir2.log" 2>&1 \
    && cp tools/m11/work/boot_final.ll "$FIX_IR" \
    && cp tools/m11/work/ldfix_report.json "$HERE/work/ldfix_report_embedded.json" \
    || { step "FAILED: gen_ir2"; exit 1; }
fi
if [ ! -f "$BASE_IR" ]; then
  step "base IR 無し → git HEAD 版 gen_ir2.sh (ldfix 無し) を一時 dir で実行"
  T="$HERE/work/basegen"; rm -rf "$T"; mkdir -p "$T"
  git show 'HEAD:tools/m11/m11_gen_ir2.sh' > "$T/gen_ir2_head.sh"
  (cd tools/m11 && bash "$T/gen_ir2_head.sh") > "$HERE/work/embed_basegen.log" 2>&1 \
    && cp tools/m11/work/boot_final.ll "$BASE_IR" \
    && cp tools/m11/work/boot_final.ll "$T/boot_final_base.ll" \
    || { step "FAILED: base gen_ir2"; exit 1; }
  # fix IR を再生成して元に戻す (boot_final.ll を fix 状態に)
  (cd tools/m11 && bash m11_gen_ir2.sh) >> "$HERE/work/embed_basegen.log" 2>&1 || true
fi
step "IR 確認: base=$(wc -c < "$BASE_IR")B fix=$(wc -c < "$FIX_IR")B"

# 1. stage4 回帰 (base/fix) — stage4.sh は m11_post 後の IR を要求する
#    (post が override 対象 6 関数の define を weak 化するため。CAB-231 も boot_final3.ll = post 後で実施)
#    注: 生成 m11_simd.c の `#include "../msimd11_core.h"` は work/stage4/ 基準で解決されるため
#        そこに実体を置く (CAB-231 実施時も同様の状態だった; stage4.sh 本体は既存のまま変更しない)。
mkdir -p "$HERE/work/stage4"
cp "$REPO/tools/m11/msimd11_core.h" "$HERE/work/stage4/msimd11_core.h" 2>/dev/null || true
for V in base fix; do
  if done_p "s4_$V"; then step "stage4/$V: done マーカーあり skip"; continue; fi
  IR="$BASE_IR"; [ $V = fix ] && IR="$FIX_IR"
  POST_OUT="$HERE/work/boot_final3_${V}_emb.ll"
  step "m11_post + stage4/$V build+run ($(basename "$IR"))"
  python3 tools/m11/m11_post.py "$IR" "$POST_OUT" --report "$HERE/work/post_${V}_emb.json" > /dev/null \
    || { step "FAILED: m11_post/$V"; exit 1; }
  bash "$HERE/stage4.sh" "$POST_OUT" "${V}_emb" > "$HERE/work/embed_stage4_$V.log" 2>&1
  rc=$?
  grep STAGE4_RESULT "$HERE/work/embed_stage4_$V.log" | tail -1
  [ $rc = 0 ] || step "WARNING: stage4/$V rc=$rc"
  mark "s4_$V"
done

# 2. 942 unit survey (base/fix, 並列) ---------------------------------------------
if ! done_p "survey"; then
  step "survey (base_emb / fix_emb 並列)"
  for V in base fix; do
    (export S4_NAME="${V}_emb"; export S4_IMAGE=tools/m11/work/m11_image.bin; \
     timeout 900 node "$HERE/survey_stage4.mjs" \
       > "$HERE/work/stage4/${V}_emb/e2e_survey.out" 2> "$HERE/work/stage4/${V}_emb/e2e_survey.err" || true) &
  done
  wait
  for V in base fix; do
    grep -o 'M11_SURVEY {.*}' "$HERE/work/stage4/${V}_emb/e2e_survey.out" | head -c 220; echo " <- $V"
  done
  mark "survey"
fi

# 3. 判定 (base/fix の stage4 + survey 数値比較) -----------------------------------
python3 - "$HERE/work" <<'PYEOF'
import json, re, sys, os
W = sys.argv[1]
def result(name):
    p = os.path.join(W, 'stage4', name, 'result.jsonline')
    if not os.path.exists(p): return {}
    try:
        t = open(p).read().strip()
        for pre in ('STAGE4_RESULT ', 'M11_RESULT '):
            if t.startswith(pre):
                t = t[len(pre):]
                break
        return json.loads(t)
    except Exception: return {}
def survey(name):
    p = os.path.join(W, 'stage4', name, 'e2e_survey.out')
    if not os.path.exists(p): return {}
    t = open(p, errors='replace').read()
    m = re.search(r'M11_SURVEY (\{.*\})', t)
    return json.loads(m.group(1)) if m else {}
b, f = result('base_emb'), result('fix_emb')
sb, sf = survey('base_emb'), survey('fix_emb')
keys = ['reached_stage_probe', 'units_run', 'units_total', 'init_count', 'getmem', 'freemem',
        'fastmm_getmem_impl', 'icall_ok', 'icall_miss', 'dllmain_done', 'threw', 'boot_rc']
print('EMBED_AB stage4 (base_emb -> fix_emb):')
for k in keys:
    print('  %-22s %s -> %s %s' % (k, b.get(k), f.get(k), '' if b.get(k) == f.get(k) else '  <-- CHANGED'))
print('EMBED_AB survey:')
for k in ['ok', 'trap', 'noproc', 'miss']:
    print('  %-8s %s -> %s %s' % (k, sb.get(k), sf.get(k), '' if sb.get(k) == sf.get(k) else '  <-- CHANGED'))
kb, kf = sb.get('kinds') or {}, sf.get('kinds') or {}
for k in sorted(set(kb) | set(kf)):
    if kb.get(k) != kf.get(k):
        print('  kinds[%s] %s -> %s  <-- CHANGED' % (k[:40], kb.get(k), kf.get(k)))
PYEOF

# 4. liftdiff batch (fix IR, --batch 時) -------------------------------------------
if [ $BATCH = 1 ] && ! done_p "batch"; then
  step "liftdiff batch (fix_emb IR, shards 12, 約 11 分)"
  # boot_state (native unit 0..16 実行済み状態) は target 非依存 (m11/m11_ldfix と同一実測) → 共用
  mkdir -p tools/liftdiff/work/m11_ldfix_embedded
  cmp -s tools/liftdiff/work/m11_ldfix/boot_state.json tools/liftdiff/work/m11_ldfix_embedded/boot_state.json || \
    cp tools/liftdiff/work/m11_ldfix/boot_state.json tools/liftdiff/work/m11_ldfix_embedded/boot_state.json
  python3 tools/liftdiff/liftdiff.py batch "$HERE/targets/m11_ldfix_embedded.json" --set closure --shards 12 --state auto \
    --out "$HERE/work/batch_embed.jsonl" > "$HERE/work/batch_embed.log" 2>&1 || step "WARNING: batch rc=$?"
  python3 tools/liftdiff/liftdiff.py summary "$HERE/work/batch_embed.jsonl" | head -8 || true
  mark "batch"
fi
step "done"
exit 0
