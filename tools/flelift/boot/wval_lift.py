#!/usr/bin/env python3
"""wval_lift.py — 書込み値の監視 (#3771・診断用・boot/ 内だけ)。

lift 生成 C の store 文 (ST8..ST64・STF32/STF64・STX・STY) を、guest VA を添えた監視版マクロ
(WV_ST64(va, a, v) 等) に書き換えた copy を作る。書込み値 (4/8 byte、16 byte は下位・上位 8 byte) が
`--value` に一致した store だけ、stderr に `[wval] va=... a=... n=... v=... R0..R7 ret=...` を出す (件数上限あり)。
ret は store 時点の [RSP] (push の無い関数の中では呼出元の戻り番地)。
間接呼出し (ott_dispatch) の target が `--value` に一致したときは `[wval-call] va=... target=... R1 R3 R5` を出す。

rt/ (fle_cpu.h・fle_cpu.c) と x64c.py は変えない。書き換えは出力先 (--out) の copy だけ。
既存の FLE_WWATCH (#3028) は監視 slot が 0x15e1c78・0x15e4790 に固定のため、任意の値・任意のアドレスには使えない。

使い方:
    python3 boot/wval_lift.py --src work/boot/lift --out work/boot/lift_wv --value 0x6bbc20
"""
import argparse
import os
import re
import shutil
import sys

HOOK = r'''
/* wval (#3771・診断用): boot/wval_lift.py が挿入。書込み値が監視値に一致した store を出す */
#include <stdio.h>
#define WV_VAL @VALUE@
static int wv_n_ = 0;
static int wv_n12_ = 0;
static void wv_chk_(uint64_t va, uint64_t a, uint32_t n, const void* p) {
    uint64_t q[2] = { 0, 0 };
    int hit;
    int *cnt = n < 4 ? &wv_n12_ : &wv_n_;
    if (*cnt >= @CAP@) return;
    memcpy(q, p, n < 16 ? n : 16);
    if (n < 4) {
        uint64_t m = (1ULL << (8 * n)) - 1;
        hit = ((q[0] & m) == (WV_VAL & m));
    } else {
        hit = (n == 4) ? ((uint32_t)q[0] == (uint32_t)WV_VAL) : (q[0] == WV_VAL || (n == 16 && q[1] == WV_VAL));
    }
    if (!hit) return;
    (*cnt)++;
    fprintf(stderr, "[wval] va=%#llx a=%#llx n=%u v=%#llx R0=%#llx R1=%#llx R2=%#llx R3=%#llx R5=%#llx R6=%#llx R7=%#llx ret=%#llx\n",
            (unsigned long long)va, (unsigned long long)a, n, (unsigned long long)q[0],
            (unsigned long long)R[0], (unsigned long long)R[1], (unsigned long long)R[2], (unsigned long long)R[3],
            (unsigned long long)R[5], (unsigned long long)R[6], (unsigned long long)R[7], (unsigned long long)LD64(R[RSP]));
}
static void wv_call_(uint64_t va, uint64_t t) {
    if (t != WV_VAL || wv_n_ >= @CAP@) return;
    wv_n_++;
    fprintf(stderr, "[wval-call] va=%#llx target=%#llx R1=%#llx R3=%#llx R5=%#llx\n", (unsigned long long)va,
            (unsigned long long)t, (unsigned long long)R[1], (unsigned long long)R[3], (unsigned long long)R[5]);
}
static int wv_e_n_ = 0;
static void wv_enter_(uint64_t fn) {
    if (wv_e_n_ >= 2000) return;
    wv_e_n_++;
    fprintf(stderr, "[wval-enter] fn=%#llx ret=%#llx R1=%#llx R2=%#llx R3=%#llx\n", (unsigned long long)fn,
            (unsigned long long)LD64(R[RSP]), (unsigned long long)R[1], (unsigned long long)R[2], (unsigned long long)R[3]);
    if (fn == 0x6bc010ULL)
        fprintf(stderr, "[wval-mode] obj=%#llx dl=%#llx [obj+0x70]=%#x [obj+0xc4]=%#x\n", (unsigned long long)R[1],
                (unsigned long long)(R[2] & 0xff), (unsigned)LD32(R[1] + 0x70ULL), (unsigned)LD8(R[1] + 0xc4ULL));
}
#define WV_ST8(va, a, v) ({ uint8_t wv_ = (uint8_t)(v); wv_chk_((va), (a), 1, &wv_); ST8(a, wv_); })
#define WV_ST16(va, a, v) ({ uint16_t wv_ = (uint16_t)(v); wv_chk_((va), (a), 2, &wv_); ST16(a, wv_); })
#define WV_ST32(va, a, v) ({ uint32_t wv_ = (uint32_t)(v); wv_chk_((va), (a), 4, &wv_); ST32(a, wv_); })
#define WV_ST64(va, a, v) ({ uint64_t wv_ = (uint64_t)(v); wv_chk_((va), (a), 8, &wv_); ST64(a, wv_); })
#define WV_STF32(va, a, v) ({ float wv_ = (float)(v); wv_chk_((va), (a), 4, &wv_); STF32(a, wv_); })
#define WV_STF64(va, a, v) ({ double wv_ = (double)(v); wv_chk_((va), (a), 8, &wv_); STF64(a, wv_); })
#define WV_STX(va, a, x) ({ X128 wv_ = (x); wv_chk_((va), (a), 16, &wv_); STX((a), wv_); })
#define WV_STY(va, a, lo, hi) ({ X128 wvl_ = (lo), wvh_ = (hi); wv_chk_((va), (a), 16, &wvl_); STY((a), wvl_, wvh_); })
'''

COMMENT_VA = re.compile(r'^\s*/\* ([0-9a-f]+): ')
STORE = re.compile(r'\b(ST(?:8|16|32|64|F32|F64|X|Y))\(')
INCLUDE_RT = re.compile(r'^#include "fle_cpu\.h"\s*$')
ENTER_FN = re.compile(r'^void f_(6ba1f0|6bc010|6cd520|6c9280)\(void\) \{$')
LABEL = re.compile(r'^L_[0-9a-f]+:;$')

# --objwatch (#4287・診断用): obj = [f_6ba1f0 の rbp+0xe0] (f_6cd520 の rbx = rcx = obj) の mode 字段 [obj+0xc4] への
# 全幅 (1/2/4/8/16 byte) の store を、宛先アドレス一致で記録する。値の比較はしない。
# obj は f_6ba1f0 の入口 (rcx) と、obj の確定後 (ラベル L_6ba25b の直後) で更新する。
OBJ_HOOK = r'''
/* wobj (#4287・診断用): boot/wval_lift.py --objwatch が挿入 */
static uint64_t wo_obj_ = 0;
static int wo_n_ = 0;
static void wo_enter_(uint64_t va, uint64_t rcx, uint64_t dl) {
    fprintf(stderr, "[wobj-enter] va=%#llx rcx=%#llx dl=%#llx ret=%#llx\n", (unsigned long long)va,
            (unsigned long long)rcx, (unsigned long long)dl, (unsigned long long)LD64(R[RSP]));
    if (va == 0x6cd520ULL) {
        wo_obj_ = rcx;
        fprintf(stderr, "[wobj-read] va=%#llx obj=%#llx mode(+0xc4)=%#llx 0x70=%#llx\n", (unsigned long long)va,
                (unsigned long long)rcx, (unsigned long long)LD32(rcx + 0xc4ULL), (unsigned long long)LD32(rcx + 0x70ULL));
    }
}
static void wo_set_(uint64_t va, uint64_t obj) {
    wo_obj_ = obj;
    fprintf(stderr, "[wobj-set] va=%#llx obj=%#llx\n", (unsigned long long)va, (unsigned long long)obj);
}
static void wo_chk_(uint64_t va, uint64_t a, uint32_t n, const void* p) {
    uint64_t q[2] = { 0, 0 };
    uint64_t tgt = wo_obj_ ? wo_obj_ + 0xc4ULL : @FIXOBJ@ + 0xc4ULL;
    if (!(a <= tgt && tgt < a + n) || wo_n_ >= @CAP@) return;
    memcpy(q, p, n < 16 ? n : 16);
    wo_n_++;
    fprintf(stderr, "[wobj] va=%#llx a=%#llx n=%u v=%#llx obj=%#llx R0=%#llx R1=%#llx R2=%#llx R3=%#llx R5=%#llx ret=%#llx\n",
            (unsigned long long)va, (unsigned long long)a, n, (unsigned long long)q[0], (unsigned long long)wo_obj_,
            (unsigned long long)R[0], (unsigned long long)R[1], (unsigned long long)R[2], (unsigned long long)R[3],
            (unsigned long long)R[5], (unsigned long long)LD64(R[RSP]));
}
#define WO_ST8(va, a, v) ({ uint8_t wo_ = (uint8_t)(v); wo_chk_((va), (a), 1, &wo_); ST8(a, wo_); })
#define WO_ST16(va, a, v) ({ uint16_t wo_ = (uint16_t)(v); wo_chk_((va), (a), 2, &wo_); ST16(a, wo_); })
#define WO_ST32(va, a, v) ({ uint32_t wo_ = (uint32_t)(v); wo_chk_((va), (a), 4, &wo_); ST32(a, wo_); })
#define WO_ST64(va, a, v) ({ uint64_t wo_ = (uint64_t)(v); wo_chk_((va), (a), 8, &wo_); ST64(a, wo_); })
#define WO_STF32(va, a, v) ({ float wo_ = (float)(v); wo_chk_((va), (a), 4, &wo_); STF32(a, wo_); })
#define WO_STF64(va, a, v) ({ double wo_ = (double)(v); wo_chk_((va), (a), 8, &wo_); STF64(a, wo_); })
#define WO_STX(va, a, x) ({ X128 wo_ = (x); wo_chk_((va), (a), 16, &wo_); STX((a), wo_); })
#define WO_STY(va, a, lo, hi) ({ X128 wol_ = (lo), woh_ = (hi); wo_chk_((va), (a), 16, &wol_); STY((a), wol_, woh_); })
'''

# 関数の入口ラベル (VA → 行の直後に挿入する呼出し)
OBJ_ENTRY = {'L_6ba1f0:;': 0x6ba1f0, 'L_6cd520:;': 0x6cd520}
# obj が f_6ba1f0 内で確定する位置 (VA 0x6ba25b のラベルの直後)
OBJ_SET = {'L_6ba25b:;': 0x6ba25b}


def patch(lines, value, cap, objwatch=False, fixobj=0x12d7a090):
    out = []
    va = 0
    hooked = False
    sites = 0
    entry_pending = None
    for line in lines:
        if not hooked and INCLUDE_RT.match(line):
            out.append(line)
            out.append(HOOK.replace('@VALUE@', hex(value) + 'ULL').replace('@CAP@', str(cap)))
            if objwatch:
                out.append(OBJ_HOOK.replace('@CAP@', str(cap)).replace('@FIXOBJ@', hex(fixobj) + 'ULL'))
            hooked = True
            continue
        m = COMMENT_VA.match(line)
        if m:
            va = int(m.group(1), 16)
        fm = ENTER_FN.match(line)
        if fm:
            entry_pending = int(fm.group(1), 16)
        elif entry_pending is not None and LABEL.match(line):
            out.append(line)
            out.append('  wv_enter_(%#xULL);' % entry_pending)
            entry_pending = None
            continue
        if STORE.search(line) and not line.lstrip().startswith('/*'):
            prefix = 'WO_%s(' if objwatch else 'WV_%s('
            line, k = STORE.subn(lambda s: (prefix % s.group(1)) + '%#xULL, ' % va, line)
            sites += k
        if 'ott_dispatch(t_);' in line:
            line = line.replace('ott_dispatch(t_);', 'wv_call_(%#xULL, t_); ott_dispatch(t_);' % va)
        out.append(line)
        if objwatch:
            s = line.strip()
            if s in OBJ_ENTRY:
                out.append('  wo_enter_(%#xULL, R[1], R[2]);' % OBJ_ENTRY[s])
            elif s in OBJ_SET:
                out.append('  wo_set_(%#xULL, LD64(R[5] + 0xe0ULL));' % OBJ_SET[s])
    return out, hooked, sites


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True, help='lift 出力ディレクトリ (fle_lifted_s*.c を含む)')
    ap.add_argument('--out', required=True, help='書換え後の出力ディレクトリ')
    ap.add_argument('--value', default='0x6bbc20', help='監視する書込み値 (既定 0x6bbc20)')
    ap.add_argument('--cap', type=int, default=400, help='1 TU あたりの出力上限')
    ap.add_argument('--objwatch', action='store_true', help='obj+0xc4 (mode) への全幅 store を宛先一致で監視する (--value は使わない)')
    ap.add_argument('--fixobj', default='0x12d7a090', help='確保前から監視する obj の既定値 (確保内の store を拾う。前回実測の obj)')
    a = ap.parse_args()
    value = int(a.value, 16)
    os.makedirs(a.out, exist_ok=True)
    n_files = 0
    n_stores = 0
    for name in sorted(os.listdir(a.src)):
        src = os.path.join(a.src, name)
        dst = os.path.join(a.out, name)
        if re.match(r'^fle_lifted(_s\d+)?\.c$', name):
            lines = open(src, errors='replace').read().split('\n')
            new, hooked, sites = patch(lines, value, a.cap, a.objwatch, int(a.fixobj, 16))
            if not hooked:
                print('[wval] %s: #include "fle_cpu.h" が無い' % name, file=sys.stderr)
                sys.exit(1)
            n_stores += sites
            open(dst, 'w').write('\n'.join(new))
            n_files += 1
        elif os.path.isfile(src):
            shutil.copy2(src, dst)
    print('[wval] patched %d lifted files, %d store sites -> %s (value %#x)' % (n_files, n_stores, a.out, value))


if __name__ == '__main__':
    main()
