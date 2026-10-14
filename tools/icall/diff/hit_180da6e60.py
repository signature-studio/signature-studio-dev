#!/usr/bin/env python3
"""hit_180da6e60.py [FN_VA] — native 1 回実行で、候補命令 (CANDS) が実行されたかを int3 トレース (ott_trace_install) で記録して表示する。
初期化は fa_cmp.init_native (件数は FA_LOOP_N)。判定は候補 VA の hit の有無のみ (値は見ない)。
FA_ELEM_STATE=S (件数 >0 のとき) は要素 0 の state (+0x100108) を S にする。state 0 は 0x180da41a0 を呼ぶ。
ott_call_cov の単歩 coverage は窓 (IMG_BASE + 0x308000) 外の VA を記録しないため使わない。
用法: FA_CORE=... FA_LOOP_N=0 python3 tools/icall/diff/hit_180da6e60.py [180da6e60]
      FA_CORE=... FA_LOOP_N=1 FA_ELEM_STATE=2 python3 tools/icall/diff/hit_180da6e60.py [180da6e60]"""
import sys, os, ctypes, struct
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fa_cmp as F
import ottnat as N

CANDS = [(0x180da6e8e, 'No1 cookie store'), (0x180da6f4d, 'No2'), (0x180da7278, 'No3'), (0x180da7280, 'No4'),
         (0x180da7293, 'No5 (IR 有)'), (0x180da7297, 'No6'), (0x180da729b, 'No7'), (0x180da7308, 'No8 (IR 有)'),
         (0x180da730c, 'No9'), (0x180da7310, 'No10'), (0x180da6e99, 'SIGSEGV 点'),
         (0x180da6ece, 'loop 先頭'), (0x180da7373, '出口 (cookie 検査)'), (0x180da41a0, '41a0 entry (state 0)')]


def main():
    va = int(sys.argv[1] if len(sys.argv) > 1 else '180da6e60', 16)
    N.load(F.FA)
    gpr = F.init_native(va)
    if os.environ.get('FA_ELEM_STATE') and F.LOOP_CNT > 0:
        B = N.u64(gpr[0] + 0xb8)
        N.wr(B + 0x100108, struct.pack('<I', int(os.environ['FA_ELEM_STATE'])))
    vas = [a for a, _ in CANDS]
    N._lib.ott_trace_install(ctypes.cast((ctypes.c_uint64 * len(vas))(*vas), ctypes.c_void_p), len(vas))
    N._lib.ott_trace_enable(1)
    _, x0 = N.call(va, gpr=gpr, xmm=(N.f64b(1.5),))
    N._lib.ott_trace_enable(0)
    n = N._lib.ott_trace_count()
    N._lib.ott_trace_buf.restype = ctypes.c_void_p
    buf = ctypes.string_at(N._lib.ott_trace_buf(), n * 88)
    hits = {}
    for i in range(n):
        rec = struct.unpack_from('<11Q', buf, i * 88)
        hits[rec[0]] = hits.get(rec[0], 0) + 1
    print('fn %#x xmm0 %016x (件数 FA_LOOP_N=%d・要素 0 state=%s) trace records %d' % (
        va, x0, F.LOOP_CNT, os.environ.get('FA_ELEM_STATE', 'zero'), n))
    for a, name in CANDS:
        print('%#x %-20s hits %d' % (a, name, hits.get(a, 0)))


if __name__ == '__main__':
    main()
