#!/usr/bin/env python3
"""hit_180da6e60.py [FN_VA] — native 1 回実行で、候補命令 (CANDS) が実行されたかを int3 トレース (ott_trace_install) で記録して表示する。
初期化は fa_cmp.init_native (件数は FA_LOOP_N)。判定は候補 VA の hit の有無のみ (値は見ない)。
FA_ELEM_STATE=S (件数 >0 のとき) は要素 0 の state (+0x100108) を S にする。state 0 は 0x180da41a0 を呼ぶ。
FA_ELEM_SPEC=S0,S1,... (件数と同数。接尾辞 n は state 8 の pair を 0 にする) は要素ごとの state と pair を置く (setup_elems)。
ott_call_cov の単歩 coverage は窓 (IMG_BASE + 0x308000) 外の VA を記録しないため使わない。
用法: FA_CORE=... FA_LOOP_N=0 python3 tools/icall/diff/hit_180da6e60.py [180da6e60]
      FA_CORE=... FA_LOOP_N=1 FA_ELEM_STATE=2 python3 tools/icall/diff/hit_180da6e60.py [180da6e60]
      FA_CORE=... FA_LOOP_N=3 FA_ELEM_SPEC=2,8,8n python3 tools/icall/diff/hit_180da6e60.py [180da6e60]"""
import sys, os, ctypes, struct
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fa_cmp as F
import ottnat as N

CANDS = [(0x180da6e8e, 'No1 cookie store'), (0x180da6f4d, 'No2'), (0x180da7278, 'No3'), (0x180da7280, 'No4'),
         (0x180da7293, 'No5 (IR 有)'), (0x180da7297, 'No6'), (0x180da729b, 'No7'), (0x180da7308, 'No8 (IR 有)'),
         (0x180da730c, 'No9'), (0x180da7310, 'No10'), (0x180da6e99, 'SIGSEGV 点'),
         (0x180da6ece, 'loop 先頭'), (0x180da7373, '出口 (cookie 検査)'), (0x180da41a0, '41a0 entry (state 0)')]
# ICALL-81 (#2695) 2 回目: A の vtable を ret 系の機械語 (image 内の実在 VA) で作る。
# [A+8]・[A+0x30] は rax=rcx (= A) を返す stub、[VT+0x10] は何もしない ret。仮想 callee は読まない (未確定の判定材料)。
RET_SELF = 0x1803b3d2d   # mov rax, rcx; ret
RET = 0x1803ba143        # ret


def setup_elems(gpr, spec):
    # FA_ELEM_SPEC="2,8,8n": 要素 i の state を指定する。n は +0x100130 (state 8 の pair) を 0 にする。
    # state 2 は +0x100120 に pair を置く。全要素の 64 B 節点 node[0] を nil にする (41a0 の spin 回避)。
    A = N.u64(gpr[0] + 0x10); B = N.u64(gpr[0] + 0xb8)
    VT = N.alloc(0x100)
    N.wr(VT + 0x08, struct.pack('<Q', RET_SELF)); N.wr(VT + 0x10, struct.pack('<Q', RET))
    N.wr(VT + 0x30, struct.pack('<Q', RET_SELF)); N.wr(A, struct.pack('<Q', VT))
    for i, tok in enumerate(spec):
        E = B + i * F.LOOP_STRIDE
        N.wr((E + 0xbf) & ~63, struct.pack('<I', F.NIL_NODE))
        N.wr(E + 0x100108, struct.pack('<I', int(tok.rstrip('n'))))
        if tok.startswith('2'):
            N.wr(E + 0x100120, struct.pack('<Q', N.alloc(0x10)))
        if tok.startswith('8') and not tok.endswith('n'):
            N.wr(E + 0x100130, struct.pack('<Q', N.alloc(0x10)))


def main():
    va = int(sys.argv[1] if len(sys.argv) > 1 else '180da6e60', 16)
    N.load(F.FA)
    gpr = F.init_native(va)
    st0 = 'zero'
    if os.environ.get('FA_ELEM_SPEC') and F.LOOP_CNT > 0:
        spec = os.environ['FA_ELEM_SPEC'].split(',')
        assert len(spec) == F.LOOP_CNT, 'FA_ELEM_SPEC の要素数は FA_LOOP_N と一致させる'
        setup_elems(gpr, spec)
        st0 = spec[0]
    if os.environ.get('FA_ELEM_STATE') and F.LOOP_CNT > 0:
        B = N.u64(gpr[0] + 0xb8)
        N.wr(B + 0x100108, struct.pack('<I', int(os.environ['FA_ELEM_STATE'])))
        st0 = os.environ['FA_ELEM_STATE']
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
    print('fn %#x xmm0 %016x (件数 FA_LOOP_N=%d・要素 0 state=%s・FA_ELEM_SPEC=%s) trace records %d' % (
        va, x0, F.LOOP_CNT, st0, os.environ.get('FA_ELEM_SPEC', '-'), n))
    for a, name in CANDS:
        print('%#x %-20s hits %d' % (a, name, hits.get(a, 0)))


if __name__ == '__main__':
    main()
