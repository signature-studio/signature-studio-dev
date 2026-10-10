"""fma_sens.py: native 機械語で CRT の __use_fma3 相当 flag (0x18026c50c) を 0 / 1 に変えた出力差 (tolerance 設計用)。
   usage: fma_sens.py  → JSON を stdout"""
import sys, os, json, math, struct
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'native'))
import ottnat as N
N.load()
FLAG = 0x18026c50c
def run(flag, params, n=256, f248=None, nproc=3, sig=0.0):
    N.wr(FLAG, struct.pack('<I', flag))
    OBJ = N.alloc(0x10000); buf = N.alloc(n * 16 + 0x100); inA = N.alloc(64); ouA = N.alloc(64)
    N.call(0x18011d400, (OBJ, 0))
    for i, v in enumerate(params): N.call(0x180120af0, (OBJ, i), (0, 0, N.f32b(v)))
    N.call(0x180120800, (OBJ,))
    if f248 is not None: N.wr(OBJ + 0x248, bytes([f248]))
    N.wr(inA, struct.pack('<QQ', buf, buf + n * 4)); N.wr(ouA, struct.pack('<QQ', buf + n * 8, buf + n * 12))
    out = []
    for b in range(nproc):
        N.wr(buf, b''.join(struct.pack('<f', math.sin((b*n+i)*0.05)*0.7 + math.sin((b*n+i)*0.011)*0.3 + sig) for i in range(n)) + b''.join(struct.pack('<f', math.cos((b*n+i)*0.13)*0.5 + sig) for i in range(n)))
        N.call(0x18011ec20, (OBJ, inA, ouA, n))
        out += list(struct.unpack('<%dI' % (2 * n), N.rd(buf + n * 8, n * 8)))
    return out
def ulp(a, b):
    fa = struct.unpack('<f', struct.pack('<I', a))[0]; fb = struct.unpack('<f', struct.pack('<I', b))[0]
    if fa == fb: return 0
    ia = a if a < 0x80000000 else -(a & 0x7fffffff); ib = b if b < 0x80000000 else -(b & 0x7fffffff)
    return abs(ia - ib)
import random
random.seed(11)
res = []
CASES = [('std', [0.5]*19, None), ('std_f248_0', [0.5]*19, 0), ('p0.25', [0.25]*19, None), ('p0.75', [0.75]*19, 0)]
CASES += [('rnd%d' % k, [round(random.random(), 3) for _ in range(19)], random.choice([None, 0, 1])) for k in range(8)]
for name, params, f248 in CASES:
    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(r)
        a = run(0, params, f248=f248); 
        b = run(1, params, f248=f248)
        data = memoryview(json.dumps([a, b]).encode())
        while len(data): data = data[os.write(w, data):]
        os._exit(0)
    os.close(w); data = b''
    while True:
        ch = os.read(r, 1 << 20)
        if not ch: break
        data += ch
    os.waitpid(pid, 0)
    a, b = json.loads(data)
    fl = lambda u: struct.unpack('<f', struct.pack('<I', u))[0]
    us = [ulp(x, y) for x, y in zip(a, b)]
    ad = [abs(fl(x) - fl(y)) for x, y in zip(a, b)]
    peak = max(abs(fl(x)) for x in a)
    res.append(dict(name=name, cells=len(a), diff_cells=sum(1 for u in us if u), max_ulp=max(us), max_abs=max(ad), peak=peak, max_abs_over_peak=max(ad)/peak if peak else 0))
print(json.dumps(res))
print('[fma_sens] cases %d, cells %d, differing cells %d, max_ulp %d, max_abs_over_peak %.3g' % (len(res), sum(r['cells'] for r in res), sum(r['diff_cells'] for r in res), max(r['max_ulp'] for r in res), max(r['max_abs_over_peak'] for r in res)))
