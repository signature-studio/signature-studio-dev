"""case 生成: 引数パターン × メモリ blob (ptr-rich random)。"""
import numpy as np

ARENA_SIZE = 1 << 20
PTR_SLOTS = [0x1000, 0x5000, 0x9000, 0xd000, 0x11000, 0x15000, 0x19000, 0x1d000]
SMALL = [3, 5, 7, 9, 11, 13, 15, 17]
BLOB_SIZE = 0x40000
FP_D = [0x3ff8000000000000, 0x4004000000000000, 0x400c000000000000, 0x4012000000000000]   # 1.5 2.5 3.5 4.5
FP_F = [0x3fc00000, 0x40200000, 0x40600000, 0x40900000]


def make_blob(seed, size=BLOB_SIZE, pfrac=0.30):
    """ポインタ豊富なランダム領域. 戻り (bytes, [fixup byte offsets]). ポインタは arena 先頭相対 offset で格納し、ランナ側が arena base を加算する。"""
    rng = np.random.default_rng(seed)
    n = size // 8
    k = rng.random(n)
    vals = np.zeros(n, dtype=np.uint64)
    offs = (rng.integers(0x1000 // 8, size // 8, n) * 8).astype(np.uint64)
    ptr = k < pfrac
    small = (k >= pfrac) & (k < pfrac + 0.20)
    mid = (k >= pfrac + 0.20) & (k < pfrac + 0.35)
    vals[ptr] = offs[ptr]
    vals[small] = rng.integers(0, 256, n).astype(np.uint64)[small]
    vals[mid] = rng.integers(0, 1 << 12, n).astype(np.uint64)[mid]
    fix = [int(i) * 8 for i in np.nonzero(ptr)[0]]
    return vals.tobytes(), fix


BLOBS = {'r1': (101, 0.30), 'r2': (202, 0.30), 'r3': (303, 0.30), 'r4': (404, 0.85)}


VMT_SLOTS = 8
LD_VMT_IDX0 = 256  # rt/ld_core.h LD_VMT_IDX0 (GetProcAddress の index 0..255 と別域)
LD_FAKEPROC_BASE = 0x50010000
LD_FAKEPROC_SZ = 32


def make_blob_vm(size=BLOB_SIZE):
    """this 疑似オブジェクト: arena+0x1000 に VMT (arena+0x2000) への fixup ptr。VMT 本体は 0 埋め (未解決 slot は native で fault し比較外)。既存 pattern vm0 が使うため内容を変えない。"""
    buf = bytearray(size)
    buf[0x1000:0x1008] = (0x2000).to_bytes(8, 'little')
    return bytes(buf), [0x1000]


def make_blob_vmt(size=BLOB_SIZE):
    """fvm 専用 this 疑似オブジェクト: make_blob_vm と同じ配置で、VMT slot k (arena+0x2000+8k) に仮 proc 番地 LD_FAKEPROC_BASE+(LD_VMT_IDX0+k)*SZ を置く (rt/ld_core.h の静的 index 域。native/wasm 同一解決)。"""
    buf = bytearray(size)
    buf[0x1000:0x1008] = (0x2000).to_bytes(8, 'little')
    for k in range(VMT_SLOTS):
        buf[0x2000 + 8 * k:0x2000 + 8 * k + 8] = (LD_FAKEPROC_BASE + (LD_VMT_IDX0 + k) * LD_FAKEPROC_SZ).to_bytes(8, 'little')
    return bytes(buf), [0x1000]


def make_blob_u16(size=BLOB_SIZE):
    """UTF-16 文字列: arena+0x1000 に Delphi UnicodeString ヘッダ (refcnt=1, length)、本文 UTF-16LE は +8 (arena+0x1008) に置く。引数はヘッダ先頭 (arena+0x1000) を渡す。"""
    import struct
    buf = bytearray(size)
    text = 'FL Studio 26.1.7 ABC'.encode('utf-16-le')
    buf[0x1000:0x1008] = struct.pack('<ii', 1, len(text) // 2)
    buf[0x1008:0x1008 + len(text)] = text
    return bytes(buf), []


SPECIAL_BLOBS = {'vm': make_blob_vm, 'vmt': make_blob_vmt, 'u16': make_blob_u16}

# (name, ptr 位置集合, blob, ptr オフセット加算)
PATTERNS = [
    ('z', set(), '-', 0, 'zero'),
    ('s', set(), '-', 0, 'small'),
    ('p0', {0}, 'r1', 0, 'small'),
    ('p1', {1}, 'r1', 0, 'small'),
    ('p01', {0, 1}, 'r2', 0, 'small'),
    ('pall', {0, 1, 2, 3}, 'r1', 0, 'small'),
    ('pall2', {0, 1, 2, 3}, 'r3', 0x40, 'small'),
    ('q0', {0}, 'r4', 0x80, 'small'),
    ('qall', {0, 1, 2, 3}, 'r4', 0x100, 'small'),
    ('vm0', {0}, 'vm', 0, 'small'),
    ('u16', {0}, 'u16', 0, 'small'),
]
PATTERN_NAMES = [p[0] for p in PATTERNS]


def kinds_of(sig_params, n=8):
    ks = []
    for i in range(n):
        ty = sig_params[i] if i < len(sig_params) else 'i64'
        ks.append('d' if ty == 'double' else 'f' if ty == 'float' else 'i')
    return ks


def build_args(pattern, kinds):
    name, ptrs, blob, add, base = next(p for p in PATTERNS if p[0] == pattern)
    toks = []
    for i, k in enumerate(kinds):
        if k == 'd':
            toks.append('d:0x%x' % FP_D[i % 4])
        elif k == 'f':
            toks.append('f:0x%x' % FP_F[i % 4])
        elif i in ptrs:
            toks.append('i:a:0x%x' % (PTR_SLOTS[i] + add))
        else:
            toks.append('i:0x%x' % (0 if base == 'zero' else SMALL[i]))
    return toks, blob


FVM_OFF = 0x40


def fvm_candidates(fault, kinds):
    """'s' pattern の native fault addr から this 候補の引数 index を返す (LD-23 / #975)。
    引数 i が整数 SMALL[i] で、fault addr が SMALL[i]+off (off < FVM_OFF) なら、その引数は deref されたポインタ候補。"""
    if not fault or 'addr' not in fault:
        return []
    a = int(fault['addr'], 16)
    return [i for i in range(min(len(kinds), len(SMALL))) if kinds[i] == 'i' and 0 <= a - SMALL[i] < FVM_OFF]


def fvm_line(va, name_prefix, arg, sig, trace=True, xfill=True):
    """引数 arg だけを this 疑似オブジェクト (vmt blob・arena+0x1000) へのポインタにした case。他の引数は small。"""
    kinds = kinds_of(sig['params'])
    toks = []
    for i, k in enumerate(kinds):
        if k == 'd':
            toks.append('d:0x%x' % FP_D[i % 4])
        elif k == 'f':
            toks.append('f:0x%x' % FP_F[i % 4])
        elif i == arg:
            toks.append('i:a:0x%x' % PTR_SLOTS[0])
        else:
            toks.append('i:0x%x' % SMALL[i])
    return 'id=%x:fvm%d fn=%x blob=vmt args=%s trace=%d xfill=%d sig=%s rt=%s' % (
        va, arg, va, ','.join(toks), 1 if trace else 0, 1 if xfill else 0, ','.join(sig['params']), sig['ret'])


def supported_sig(sig):
    ok = {'i1', 'i8', 'i16', 'i32', 'i64', 'ptr', 'float', 'double'}
    return all(t in ok for t in sig['params']) and (sig['ret'] in ok or sig['ret'] == 'void')


CUSTOM = {}


def case_line(va, name_prefix, pattern, sig, trace=True, xfill=True, stkfill=None, extra=''):
    kinds = kinds_of(sig['params'])
    if pattern in CUSTOM:
        toks, blob = CUSTOM[pattern][:2]
        if len(CUSTOM[pattern]) > 2 and CUSTOM[pattern][2]:
            extra = (extra + ' ' if extra else '') + 'p=' + CUSTOM[pattern][2]
    else:
        toks, blob = build_args(pattern, kinds)
    rt = sig['ret']
    s = 'id=%x:%s fn=%x blob=%s args=%s trace=%d xfill=%d sig=%s rt=%s' % (
        va, pattern, va, blob, ','.join(toks), 1 if trace else 0, 1 if xfill else 0, ','.join(sig['params']), rt)
    if stkfill is not None:
        s += ' stkfill=%x' % stkfill
    if extra:
        s += ' ' + extra
    return s
