"""scen2_nat.py wasm.json out.json: scen2_wasm の spec/入力/alog を再生して native (実機械語) で同一 scenario を実行"""
import sys, os, json, zlib, base64, struct, ctypes
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'ott', 'native'))
import ottnat as N
W = json.load(open(sys.argv[1])); spec = W['spec']; n = W['n']; nproc = spec.get('nproc', 1)
N.load()
N._lib.ott_map_range.argtypes = [ctypes.c_uint64, ctypes.c_uint64]
# native の python は低位 VA (0x400000..) を占有するので、wasm 低位 heap/arena と同一 VA には置けない。
# 全 heap/arena を一様に +OFF 平行移動した位置に敷設して再生し (matrix.py の nq が逆変換して照合)、アドレス差は定数オフセットに限定する。
OFF = int(os.environ.get('LB_NAT_OFF', 0x40000000))
al = [[p + OFF, s] for p, s in W['alog']]
if al:
    lo = min(a[0] for a in al) & ~0xfffff; hi = (max(a[0] + a[1] for a in al) + 0xfffff) & ~0xfffff
    assert N._lib.ott_map_range(lo, hi) == 0
    P = (ctypes.c_uint64 * len(al))(*[a[0] for a in al]); S = (ctypes.c_uint64 * len(al))(*[a[1] for a in al])
    N._lib.ott_replay_set(P, S, len(al))
ARENA = int(os.environ['LB_ARENA']); ARENA_SIZE = int(os.environ.get('LB_ARENA_SIZE', 0x100000))
assert N._lib.ott_map_range(ARENA + OFF, ARENA + OFF + ARENA_SIZE) == 0
ARENA += OFF
OBJ, IN_A, OU_A, BUF = ARENA + 0x10000, ARENA + 0x20000, ARENA + 0x30000, ARENA + 0x40000
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
