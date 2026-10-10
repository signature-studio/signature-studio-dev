"""scen2_nat.py wasm.json out.json: scen2_wasm の spec/入力/alog を再生して native (実機械語) で同一 scenario を実行"""
import sys, os, json, zlib, base64, struct, ctypes
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'native'))
import ottnat as N
W = json.load(open(sys.argv[1])); spec = W['spec']; n = W['n']; nproc = spec.get('nproc', 1)
N.load()
N._lib.ott_map_range.argtypes = [ctypes.c_uint64, ctypes.c_uint64]
al = W['alog']
if al:
    lo = min(a[0] for a in al) & ~0xfffff; hi = (max(a[0] + a[1] for a in al) + 0xfffff) & ~0xfffff
    assert N._lib.ott_map_range(lo, hi) == 0
    P = (ctypes.c_uint64 * len(al))(*[a[0] for a in al]); S = (ctypes.c_uint64 * len(al))(*[a[1] for a in al])
    N._lib.ott_replay_set(P, S, len(al))
assert N._lib.ott_map_range(0x30300000, 0x30400000) == 0
OBJ, IN_A, OU_A, BUF = 0x30310000, 0x30320000, 0x30330000, 0x30340000
inp = zlib.decompress(base64.b64decode(W['inp']))
N.wr(IN_A, struct.pack('<QQ', BUF, BUF + n * 4)); N.wr(OU_A, struct.pack('<QQ', BUF + n * 8, BUF + n * 12))
N.call(0x18011d400, (OBJ, 0))
if spec.get('sr'): N.wr(OBJ + 0x18, struct.pack('<f', spec['sr']))
for i, v in enumerate(spec.get('params', [])):
    if v is not None: N.call(0x180120af0, (OBJ, i), (0, 0, N.f32b(v)))
if spec.get('p19') is not None: N.call(0x180120af0, (OBJ, 19), (0, 0, N.f32b(spec['p19'])))
N.call(0x180120800, (OBJ,))
if spec.get('f248') is not None: N.wr(OBJ + 0x248, bytes([spec['f248']]))
outs = []
for b in range(nproc):
    N.wr(BUF, inp[b * 2 * n * 4:(b + 1) * 2 * n * 4])
    N.call(0x18011ec20, (OBJ, IN_A, OU_A, n))
    outs.append(list(struct.unpack('<%dI' % (2 * n), N.rd(BUF + n * 8, n * 8))))
z = lambda b: base64.b64encode(zlib.compress(b)).decode()
regs = [('obj', OBJ, 0x1000)] + [('h%d' % i, p, s) for i, (p, s) in enumerate(al)]
final = [{'k': k, 'p': p, 's': s, 'z': z(N.rd(p, s))} for k, p, s in regs]
json.dump({'outs': outs, 'final': final, 'mismatch': N._lib.ott_replay_mismatch()}, open(sys.argv[2], 'w'))
print('[scen2_nat] ok blocks', nproc, 'replay mismatch', N._lib.ott_replay_mismatch())
