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
static void wv_chk_(uint64_t va, uint64_t a, uint32_t n, const void* p) {
    uint64_t q[2] = { 0, 0 };
    int hit;
    if (n < 4 || wv_n_ >= @CAP@) return;
    memcpy(q, p, n < 16 ? n : 16);
    hit = (n == 4) ? ((uint32_t)q[0] == (uint32_t)WV_VAL) : (q[0] == WV_VAL || (n == 16 && q[1] == WV_VAL));
    if (!hit) return;
    wv_n_++;
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
#define WV_ST8(va, a, v) ST8(a, v)
#define WV_ST16(va, a, v) ST16(a, v)
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


def patch(lines, value, cap):
    out = []
    va = 0
    hooked = False
    sites = 0
    for line in lines:
        if not hooked and INCLUDE_RT.match(line):
            out.append(line)
            out.append(HOOK.replace('@VALUE@', hex(value) + 'ULL').replace('@CAP@', str(cap)))
            hooked = True
            continue
        m = COMMENT_VA.match(line)
        if m:
            va = int(m.group(1), 16)
        if STORE.search(line) and not line.lstrip().startswith('/*'):
            line, k = STORE.subn(lambda s: 'WV_%s(%#xULL, ' % (s.group(1), va), line)
            sites += k
        if 'ott_dispatch(t_);' in line:
            line = line.replace('ott_dispatch(t_);', 'wv_call_(%#xULL, t_); ott_dispatch(t_);' % va)
        out.append(line)
    return out, hooked, sites


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True, help='lift 出力ディレクトリ (fle_lifted_s*.c を含む)')
    ap.add_argument('--out', required=True, help='書換え後の出力ディレクトリ')
    ap.add_argument('--value', default='0x6bbc20', help='監視する書込み値 (既定 0x6bbc20)')
    ap.add_argument('--cap', type=int, default=400, help='1 TU あたりの出力上限')
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
            new, hooked, sites = patch(lines, value, a.cap)
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
