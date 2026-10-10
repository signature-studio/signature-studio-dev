import struct, math

def b2d(b): return struct.unpack('<d', struct.pack('<Q', b))[0]
PI = b2d(0x4009249249249243); PI2 = b2d(0x4019249249249243)

def dsm_band_setup(f0, SR):
    """function_180126670 の register-exact dsm 忠実転記 (m10 FIX1-4 反映)。
    定数: pi=0x4009249249249243@0x1802056e8, pi2=0x4019249249249243@0x1802056f8,
    2.0@0x1801ee848, 4.0@0x1801fde58, 8.0@0x1801f70d8, 6.0@0x1802056f0, -4.0@0x180205700。
    tan は native poly(0x1801a9be0) の代置 libm tan (python math.tan == wasm libm 系)。"""
    W = f0 * PI; W2 = f0 * PI2
    v11 = W2 * W2                     # 0x1801266f8  (xmm11)
    v14 = v11 * v11                   # 0x180126701  (xmm14 = W2^4)
    T = math.tan(W / SR)              # 0x1801266ec div + 0x180126706 call 1801a9be0
    v10 = 4.0                         # 0x18012670b  (xmm10)
    v1 = W2 / T                       # 0x180126717  (C1)
    v8 = v11                          # 0x18012671b
    v2 = v14 * 6.0                    # 0x18012671f/723 FIX3
    v7 = v1 * v1                      # 0x18012672e  (C1^2)
    v8 = v8 * W2                      # 0x180126732  (W2^3)
    v6 = W2 * math.sqrt(2.0)          # 0x180126737  (sqrtpd 2.0 @0x1801266bf)
    v13 = v7                          # 0x18012673c
    v5 = v7 * v1                      # 0x180126740/743 (C1^3)
    v8 = v8 * math.sqrt(2.0)          # 0x180126747
    v9 = v11                          # 0x18012674c  (xmm11 未破壊 -> W2^2)
    v11 = v11 * 8.0                   # 0x180126750
    v5 = v5 * v6                      # 0x180126759  (P)
    v8 = v8 * v1                      # 0x18012675d  (Q)
    v1 = v14                          # 0x180126762
    v13 = v13 * v7                    # 0x180126766 FIX1 (C1^4)
    v9 = v9 * v10                     # 0x18012676b FIX2 (4W2^2)
    v4 = v5                           # 0x180126770
    v3 = v8                           # 0x180126773
    v11 = v11 * v7                    # 0x180126777  (U)
    v3 = v3 + v8                      # 0x18012677c  (2Q)
    v0 = v8 + v14                     # 0x180126781/785
    v9 = v9 * v7                      # 0x18012678a  (S2)
    v4 = v4 + v5                      # 0x18012678f  (2P)
    v6 = v13 * 6.0                    # 0x180126793/797
    v1 = v1 - v8                      # 0x18012679f
    v0 = v0 - v13                     # 0x1801267a4
    v12 = v3                          # 0x1801267a9
    v12 = v12 + v9                    # 0x1801267ad
    v1 = v1 + v5                      # 0x1801267b2
    v0 = v0 - v5                      # 0x1801267b6
    v12 = v12 + v13                   # 0x1801267ba
    v1 = v1 - v13                     # 0x1801267bf
    v0 = v0 * v10                     # 0x1801267c4
    v12 = v12 + v4                    # 0x1801267c9
    v1 = v1 * v10                     # 0x1801267ce
    v12 = v12 + v14                   # 0x1801267d3  (K)
    A16 = v0 / v12                    # 0x1801267d8/7e2 [st+0x98]
    B16 = v1 / v12                    # 0x1801267dd/7f2 [st+0xa8]
    _A16 = v2 - v11                   # 0x1801267ea/7ed (6W2^4 - U)
    C16 = v2 / v12                    # 0x1801267fa/803 FIX3 [st+0x78]
    A32 = (_A16 + v6) / v12           # 0x1801267ff/808 [st+0xa0]
    _n = v13 - v3                     # 0x180126815/819
    _n = _n + v14                     # 0x18012681d
    _n = _n - v4                      # 0x180126822
    _n = _n + v9                      # 0x180126826
    B32 = _n / v12                    # 0x18012682b/830 [st+0xb0]
    D1 = v14 / v12                    # 0x180126838/83c [st+0x68],[0xc8]
    C1c = v14 * 4.0 / v12             # 0x180126841/857 [st+0x70],[0xc0]
    D2 = v13 * (-4.0) / v12           # 0x18012686b/89d [st+0x88],[0xd0]
    E2 = v6 / v12                     # 0x1801268d2 [st+0x90]
    F2 = v13 / v12                    # 0x1801268d7 [st+0x80],[0xd8]
    return dict(A16=A16, A32=A32, B16=B16, B32=B32, D1=D1, C1c=C1c, C16=C16, D2=D2, E2=E2, F2=F2)

def poly_roots(a16, a32, b16, b32):
    import cmath
    D = 1 + a16 + a32 + b16 + b32
    return D

if __name__ == '__main__':
    import json, sys
    fn = sys.argv[1]                     # node probe の JSON (m10_coefdump.json)
    rec = json.load(open(fn))
    offs = {'A16': 0x98, 'A32': 0xa0, 'B16': 0xa8, 'B32': 0xb0, 'D1': 0x68, 'C1c': 0x70, 'C16': 0x78, 'D2': 0x88, 'E2': 0x90, 'F2': 0x80}
    maxdev = 0.0; nbad = 0
    for k in range(8):
        st = rec[k]
        f0 = 88.30000305175781 if k < 4 else 2500.0
        ex = dsm_band_setup(f0, 44100.0)
        row = {}
        for nm, off in offs.items():
            got = st['cells'][str(off)] if str(off) in st['cells'] else st['cells'][off]
            base = abs(ex[nm])
            dev = 0.0 if (got == ex[nm] or base == 0 and got == ex[nm]) else (abs(got - ex[nm]) / base if base > 1e-300 else abs(got - ex[nm]))
            row[nm] = dev
            maxdev = max(maxdev, dev)
            if dev > 1e-9:
                nbad += 1
    print(json.dumps({'maxdev': maxdev, 'nbad': nbad}))
