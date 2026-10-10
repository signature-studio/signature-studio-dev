"""trace_nat.py wasm_trace.json out.json : native 側 entry trace (hook 対象 = ott.ll の define 全関数)"""
import sys, os, json, zlib, base64, struct, ctypes, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'native'))
import ottnat as N
W = json.load(open(sys.argv[1])); n = W['N']; PVAL = W['PVAL']
LL = os.environ.get('OTT_LL', os.path.join(os.path.dirname(__file__), '..', 'work', 'ott.ll'))
vas = sorted({int(m.group(1), 16) for m in re.finditer(r'^define \S+ @function_([0-9a-f]+)\(', open(LL).read(), re.M)})
N.load()
N._lib.ott_map_range.argtypes = [ctypes.c_uint64, ctypes.c_uint64]
al = W['alog']
lo = min(a[0] for a in al) & ~0xfffff; hi = (max(a[0] + a[1] for a in al) + 0xfffff) & ~0xfffff
assert N._lib.ott_map_range(lo, hi) == 0 and N._lib.ott_map_range(0x30300000, 0x30400000) == 0
P = (ctypes.c_uint64 * len(al))(*[a[0] for a in al]); S = (ctypes.c_uint64 * len(al))(*[a[1] for a in al])
N._lib.ott_replay_set(P, S, len(al))
OBJ, IN_A, OU_A, BUF = 0x30310000, 0x30320000, 0x30330000, 0x30340000
N.wr(BUF, zlib.decompress(base64.b64decode(W['inp'])))
N.wr(IN_A, struct.pack('<QQ', BUF, BUF + n * 4)); N.wr(OU_A, struct.pack('<QQ', BUF + n * 8, BUF + n * 12))
arr = (ctypes.c_uint64 * len(vas))(*vas)
N._lib.ott_trace_install(arr, len(vas))
N._lib.ott_trace_enable(1)
marks = {}
def mk(nm): marks[nm] = N._lib.ott_trace_count()
N.call(0x18011d400, (OBJ, 0)); mk('ctor')
for i in range(19):
    v = float(os.environ['P4']) if (i == 4 and os.environ.get('P4')) else PVAL
    N.call(0x180120af0, (OBJ, i), (0, 0, N.f32b(v)))
mk('setp')
N.call(0x180120800, (OBJ,)); mk('resume')
if os.environ.get('F248', '') != '': N.wr(OBJ + 0x248, bytes([int(os.environ['F248'])]))
N.call(0x18011ec20, (OBJ, IN_A, OU_A, n)); mk('proc')
cnt = N._lib.ott_trace_count()
N._lib.ott_trace_buf.restype = ctypes.c_void_p
base = N._lib.ott_trace_buf()
raw = ctypes.string_at(base, cnt * 88)   # TrRec = 11*8
tr = []
for i in range(cnt):
    f = struct.unpack_from('<11Q', raw, i * 88)
    tr.append([format(f[0], 'x')] + [format(x, 'x') for x in f[1:5]] + [format(x, 'x') for x in f[5:9]])
outv = list(struct.unpack('<%dI' % (2 * n), N.rd(BUF + n * 8, n * 8)))
json.dump({'trace': tr, 'marks': marks, 'out': outv, 'mismatch': N._lib.ott_replay_mismatch()}, open(sys.argv[2], 'w'))
print('[trace_nat] records', cnt, marks, 'mismatch', N._lib.ott_replay_mismatch())
