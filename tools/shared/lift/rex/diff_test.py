#!/usr/bin/env python3
"""native (元の機械語) と wasm (x64c lift) の差分判定。case ごとに RAX・import 呼出回数・arena・.data のバイト列を全比較する。
カバレッジ gate: 戻り値の種類 >= 2, import 経路を通った case >= 1, ctx=NULL の case >= 1, 両 export の case >= 1 (欠ければ exit 1)。
usage: diff_test.py WORKDIR [--mutate-wasm]   (--mutate-wasm: wasm 結果の 1 バイトを反転 = ネガティブコントロール)
exit 0: 全 case 一致かつカバレッジ充足。exit 1: 不一致 / カバレッジ不足。
"""
import json, struct, sys, collections

W = sys.argv[1]
MUTATE = '--mutate-wasm' in sys.argv
L = json.load(open(W + '/layout.json'))
ARENA_SZ, DATA_SZ = L['arena_sz'], L['data_sz']
REC = 16 + ARENA_SZ + DATA_SZ
nat = open(W + '/res_native.bin', 'rb').read()
was = bytearray(open(W + '/res_wasm.bin', 'rb').read())
assert len(nat) % REC == 0 and len(was) % REC == 0, (len(nat), len(was), REC)
n = len(nat) // REC
assert len(was) // REC == n, 'case 数不一致 native=%d wasm=%d' % (n, len(was) // REC)
CRASH = 0xC2A5C2A5C2A5C2A5
if MUTATE:
    first = next(i for i in range(n) if struct.unpack_from('<Q', nat, i * REC)[0] != CRASH)
    was[first * REC + 16 + 5] ^= 0x01   # 比較対象の最初の case の arena の 5 バイト目を 1 bit 反転 (比較器が検出するか)

cases = open(W + '/cases.bin', 'rb').read()
fns = []
a0s = []
arenas = []
ctxnull = 0
p = 4
for _ in range(n):
    fn = struct.unpack_from('<I', cases, p)[0]
    ctx = struct.unpack_from('<Q', cases, p + 8 + 32)[0]
    fns.append(fn)
    a0s.append(struct.unpack_from('<Q', cases, p + 8)[0])
    arenas.append(cases[p + 48:p + 48 + ARENA_SZ])
    ctxnull += (ctx == 0)
    p += 8 + 32 + 8 + ARENA_SZ

# 書込の有無: 入力 arena・初期 .data と比べて変化した case 数。ctx 大域 (.data 内) は各 case で書き換えるので除く。
ARENA_LO = L['arena']
d0 = open(W + '/image_native.bin', 'rb').read()[L['data_rva']:L['data_rva'] + DATA_SZ]   # 初期 .data (DllMain 前) = 書込の有無の基準
CTX_OFF = L['ctx_rva'] - L['data_rva']
def data_wo_ctx(d):
    return d[:CTX_OFF] + d[CTX_OFF + 8:]

bad = []
rax_hist = collections.Counter()
hit_cases = 0
crashed = []
w_arena = w_data = w_any = 0
for i in range(n):
    a = nat[i * REC:(i + 1) * REC]
    b = bytes(was[i * REC:(i + 1) * REC])
    if struct.unpack_from('<Q', a, 0)[0] == CRASH:
        crashed.append(i)
        continue
    rax_hist[struct.unpack_from('<Q', a, 0)[0]] += 1
    hit_cases += struct.unpack_from('<Q', a, 8)[0] > 0
    wa = a[16:16 + ARENA_SZ] != arenas[i]
    wd = data_wo_ctx(a[16 + ARENA_SZ:]) != data_wo_ctx(d0)   # 書込の有無 (初期 .data 基準)
    w_arena += wa
    w_data += wd
    w_any += (wa or wd)
    if a != b:
        off = next(k for k in range(REC) if a[k] != b[k])
        bad.append((i, off))
compared = n - len(crashed)

cov = {'compared': compared, 'native_crash_excluded': len(crashed), 'distinct_rax': len(rax_hist),
       'import_cases': hit_cases, 'ctx_null': ctxnull, 'fn0': fns.count(0), 'fn1': fns.count(1),
       'rax1_success': rax_hist[1], 'rax3': rax_hist[3], 'write_cases': w_any}
cov_ok = (compared >= n // 2 and cov['distinct_rax'] >= 2 and cov['import_cases'] >= 1 and cov['ctx_null'] >= 1
          and cov['fn0'] >= 1 and cov['fn1'] >= 1 and cov['rax1_success'] >= 1 and cov['rax3'] >= 1
          and cov['write_cases'] >= 1)
print('[diff] cases=%d compared=%d match=%d mismatch=%d native_crash_excluded=%d' % (n, compared, compared - len(bad), len(bad), len(crashed)))
print('[diff] first mismatches (case, byte offset in record): %s' % bad[:5])
print('[diff] writes (入力 arena・初期 .data から変化した case, ctx 除く): any=%d arena=%d data=%d / compared=%d' % (w_any, w_arena, w_data, compared))
a0_ext = [not (ARENA_LO <= a0s[i] < ARENA_LO + ARENA_SZ) for i in range(n)]
ext_n, ext_c = sum(a0_ext), sum(a0_ext[i] for i in crashed)
int_n, int_c = n - ext_n, len(crashed) - ext_c
print('[diff] native crash と a0 の範囲: a0 arena 外 %d / %d (%.0f%%), a0 arena 内 %d / %d (%.0f%%)' % (
    ext_c, ext_n, 100.0 * ext_c / max(ext_n, 1), int_c, int_n, 100.0 * int_c / max(int_n, 1)))
print('[diff] coverage %s ok=%s' % (cov, cov_ok))
print('[diff] rax top: %s' % [('%#x' % k, v) for k, v in rax_hist.most_common(4)])
ok = not bad and cov_ok
print('[diff] RESULT %s' % ('PASS' if ok else 'FAIL'))
sys.exit(0 if ok else 1)
