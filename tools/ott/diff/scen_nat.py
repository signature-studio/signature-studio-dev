"""scen_nat.py: 標準シナリオを native (実機械語) で実行。wasm の alloc log を再生して heap アドレスを一致させる。
   usage: scen_nat.py wasm_stages.json out_nat.json  [env: F248=]"""
import sys, os, json, zlib, base64, struct, ctypes
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'native'))
import ottnat as N
W = json.load(open(sys.argv[1]))
n = W['N']; PVAL = W['PVAL']
N.load()
N._lib.ott_map_range.argtypes = [ctypes.c_uint64, ctypes.c_uint64]
al = W['alog']
lo = min(a[0] for a in al) & ~0xfffff; hi = (max(a[0] + a[1] for a in al) + 0xfffff) & ~0xfffff
assert N._lib.ott_map_range(lo, hi) == 0, 'heap range map'
assert N._lib.ott_map_range(0x30300000, 0x30400000) == 0, 'obj/io range map'
P = (ctypes.c_uint64 * len(al))(*[a[0] for a in al]); S = (ctypes.c_uint64 * len(al))(*[a[1] for a in al])
N._lib.ott_replay_set(P, S, len(al))
OBJ, IN_A, OU_A, BUF = 0x30310000, 0x30320000, 0x30330000, 0x30340000
inp = zlib.decompress(base64.b64decode(W['inp']))
N.wr(BUF, inp)
N.wr(IN_A, struct.pack('<QQ', BUF, BUF + n * 4)); N.wr(OU_A, struct.pack('<QQ', BUF + n * 8, BUF + n * 12))
z = lambda b: base64.b64encode(zlib.compress(b)).decode()
stages = {}
def regions():
    r = [('obj', OBJ, 0x1000)]
    for i in range(N._lib.ott_alog_count()):
        p = ctypes.c_uint64(); s = ctypes.c_uint64(); N._lib.ott_alog_get(i, ctypes.byref(p), ctypes.byref(s))
        r.append(('h%d' % i, p.value, s.value))
    r.append(('io', BUF, n * 16))
    return r
def snap(nm): stages[nm] = [{'k': k, 'p': p, 's': s, 'z': z(N.rd(p, s))} for k, p, s in regions()]
N.call(0x18011d400, (OBJ, 0)); snap('ctor')
for i in range(19):
    v = float(os.environ['P4']) if (i == 4 and os.environ.get('P4')) else PVAL
    N.call(0x180120af0, (OBJ, i), (0, 0, N.f32b(v)))
snap('setp')
N.call(0x180120800, (OBJ,)); snap('resume')
if os.environ.get('F248', '') != '': N.wr(OBJ + 0x248, bytes([int(os.environ['F248'])]))
N.call(0x18011ec20, (OBJ, IN_A, OU_A, n)); snap('proc')
print('[scen_nat] replay mismatch', N._lib.ott_replay_mismatch(), 'pos', N._lib.ott_replay_pos(), '/', len(al))
json.dump({'N': n, 'stages': stages}, open(sys.argv[2], 'w'))
