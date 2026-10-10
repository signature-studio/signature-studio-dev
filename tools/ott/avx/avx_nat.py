#!/usr/bin/env python3
"""avx_nat.py — CAB-135: crt_nat.py (CRT init 入り native runner) + AVX/FMA flag 強制書き込み。

env AVX_FORCE="fma,isa" の flag 群を DLL .data に直接書く (fma_sens.py の 0x18026c50c 書き込み方式):
  fma : 0x18026c50c = 1 (__use_fma3 — CRT 数学 11 kernel の内部 dispatch を FMA 経路へ)
        0x18026c508 = 1 (同一値対)
  isa : 0x180260cc0 = 3 (__isa_available = AVX — memmove 大块 ymm 経路)
        0x18026b890 = 0 (feature byte bit1=0 — rep movsb でなく ymm loop を選ばせる)
書き込みは load_lib() 後・fork 前なので全 scenario child に引き継がれる。

usage: avx_nat.py --out RESULT.json [--scen SCEN.json] [--replay ALOG.json] [--cov COV.json] [--only NAME]...
"""
import sys, os, struct

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'crtinit'))
sys.path.insert(0, os.path.join(HERE, '..', 'native'))
import crt_nat                       # runner 本体 (load_lib を差し替える)
import ottnat as N

FLAG_FMA_PAIR = (0x18026c508, 0x18026c50c)
FLAG_ISA = 0x180260cc0
FLAG_FEAT = 0x18026b890

_orig_load_lib = crt_nat.load_lib


def load_lib():
    lib = _orig_load_lib()
    force = os.environ.get('AVX_FORCE', '')
    if 'fma' in force:
        for f in FLAG_FMA_PAIR:
            N.wr(f, struct.pack('<I', 1))
    if 'isa' in force:
        N.wr(FLAG_ISA, struct.pack('<I', 3))
        N.wr(FLAG_FEAT, bytes([0]))
    if os.environ.get('AVX_DEBUG'):
        rb = lambda a: struct.unpack('<I', N.rd(a, 4))[0]
        print('[avx_nat] force=%s readback fma=%d isa=%d feat=%d' % (
            force, rb(0x18026c50c), rb(0x180260cc0), N.rd(0x18026b890, 1)[0]), file=sys.stderr)
    return lib


crt_nat.load_lib = load_lib

if __name__ == '__main__':
    crt_nat.main()
