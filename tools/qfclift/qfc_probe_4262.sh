#!/usr/bin/env bash
# qfc_probe_4262.sh — DllMain の ExitProcess(0) 停止の呼出元と longjmp 継続後の進行を実測する (T-SH-106 / #4262)。
#   qfc_boot.sh で作られた work/boot/lift (soft 版の lift C) に計測用の fprintf を入れ、work/probe/ に別ビルドする。
#   lift C は work/ (gitignore) のみ。repo の lift 出力・e2e・boot の entries は変えない。
# 前提: qfc_boot.sh を 1 回実行済み (work/boot/lift があること)。FL_WIN64_DIR 必須。
set -euo pipefail
source "$(cd -- "$(dirname -- "$0")" && pwd)/env.sh"
cd "$QFC"
[ -f work/boot/lift/fle_lifted.c ] || { echo "[probe4262] work/boot/lift が無い (先に qfc_boot.sh)"; exit 2; }
rm -rf work/probe && mkdir -p work/probe && cp work/boot/lift/*.c work/boot/lift/*.json work/probe/
python3 - <<'PY'
src = open('work/probe/fle_lifted.c').read()
def rep(before, after):
    global src
    assert src.count(before) == 1, before[:60]
    src = src.replace(before, after)
rep('void f_40fb80(void) {\nL_40fb80:;\n', 'void f_40fb80(void) {\nL_40fb80:;\n  fprintf(stderr, "[probe] enter 40fb80 ret@rsp=%llx\\n", (unsigned long long)LD64(R[4]));\n')
rep('  R[RSP] -= 8; ST64(R[RSP], 0x40fcbdULL); f_40fa40();', '  fprintf(stderr, "[probe] longjmp site=40fcb8\\n");\n  R[RSP] -= 8; ST64(R[RSP], 0x40fcbdULL); f_40fa40();')
rep('void f_59c210(void) {\nL_59c210:;\n', 'void f_59c210(void) {\nL_59c210:;\n  fprintf(stderr, "[probe] enter 59c210 eax=%x\\n", (unsigned)R[0]);\n')
rep('  R[RSP] -= 8; ST64(R[RSP], 0x40fce2ULL); imp_ExitProcess();', '  fprintf(stderr, "[probe] pre-ExitProcess site=40fcdd 5aa000=%u\\n", (unsigned)LD32(0x5aa000ULL));\n  R[RSP] -= 8; ST64(R[RSP], 0x40fce2ULL); imp_ExitProcess();')
open('work/probe/fle_lifted.c', 'w').write(src)
PY
source qfc_lift.sh
wasm_build "$QFC/work/probe" "$QFC/work/probe/qfcl_soft.cjs" "$QFC/work/probe/soft_imp.c" "$QFC/qfc_imp.c" "$QFC/qfc_ov.c"
sed "s/printErr: (s) => errs.push(String(s))/printErr: (s) => { errs.push(String(s)); console.error(String(s)); }/" qfc_boot.mjs > work/probe/qfc_boot_probe.mjs
QFC_CJS="$QFC/work/probe/qfcl_soft.cjs" QFC_OUT="$QFC/work/probe/boot_soft.json" timeout 300 node work/probe/qfc_boot_probe.mjs 2>&1 | grep -E "probe|\[fle\]" || true
