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


VMT_SLOTS = 24  # rt/ld_core.h LD_VMT_SLOTS と一致させる (LD-238: 784520 の slot 23 まで)
LD_VMT_IDX0 = 1024  # rt/ld_core.h LD_VMT_IDX0 (GetProcAddress の index 0..1023 と別域)
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


def make_blob_vmt2(size=BLOB_SIZE):
    """LD-238 (#4423): 2 段の this 疑似オブジェクト。arena+0x1000 の this の +8 に内部オブジェクト (arena+0x3000) を置き、その先頭に VMT (arena+0x2000) を置く。
    668390 / 6683d0 は [this+8] の先頭 qword を VMT として [VMT+0x20] を間接呼出しするため、this+8 が要る。VMT slot は make_blob_vmt と同じ仮 proc。"""
    buf = bytearray(size)
    buf[0x1000:0x1008] = (0x2000).to_bytes(8, 'little')
    buf[0x1008:0x1010] = (0x3000).to_bytes(8, 'little')
    buf[0x3000:0x3008] = (0x2000).to_bytes(8, 'little')
    for k in range(VMT_SLOTS):
        buf[0x2000 + 8 * k:0x2000 + 8 * k + 8] = (LD_FAKEPROC_BASE + (LD_VMT_IDX0 + k) * LD_FAKEPROC_SZ).to_bytes(8, 'little')
    return bytes(buf), [0x1000, 0x1008, 0x3000]


def make_blob_u16(size=BLOB_SIZE):
    """UTF-16 文字列: arena+0x1000 に Delphi UnicodeString ヘッダ (refcnt=1, length)、本文 UTF-16LE は +8 (arena+0x1008) に置く。引数はヘッダ先頭 (arena+0x1000) を渡す。"""
    import struct
    buf = bytearray(size)
    text = 'FL Studio 26.1.7 ABC'.encode('utf-16-le')
    buf[0x1000:0x1008] = struct.pack('<ii', 1, len(text) // 2)
    buf[0x1008:0x1008 + len(text)] = text
    return bytes(buf), []


SPECIAL_BLOBS = {'vm': make_blob_vm, 'vmt': make_blob_vmt, 'vmt2': make_blob_vmt2, 'u16': make_blob_u16}

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

# LD-207 (#4264): 691dd0 は rcx が有効オブジェクト (vtable・ビン表が boot 状態) でないと、小サイズ確保のビン読みで segv する。
# 既定の pattern では rcx が blob の値を指すため入らない。vmt blob (VMT 付き疑似オブジェクト) を rcx に渡す pattern を、その VA だけに足す。
# r8 (1 byte flag) は 0 にする。0 以外だと 691e65 の判定で segv する (実測)。
OBJ_PATTERNS = {
    0x691dd0: [('vmo', {0}, 'vmt', 0, 'zero')],
}


def kinds_of(sig_params, n=8):
    ks = []
    for i in range(n):
        ty = sig_params[i] if i < len(sig_params) else 'i64'
        ks.append('d' if ty == 'double' else 'f' if ty == 'float' else 'i')
    return ks


def build_args(pattern, kinds):
    allp = PATTERNS + [p for ps in OBJ_PATTERNS.values() for p in ps]
    name, ptrs, blob, add, base = next(p for p in allp if p[0] == pattern)
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
    ext = (' tr=1 wsig=' + ','.join(sig['wsig'])) if sig.get('wsig') else ''
    return 'id=%x:fvm%d fn=%x blob=vmt args=%s trace=%d xfill=%d sig=%s rt=%s%s' % (
        va, arg, va, ','.join(toks), 1 if trace else 0, 1 if xfill else 0, ','.join(sig['params']), sig['ret'], ext)


def supported_sig(sig):
    ok = {'i1', 'i8', 'i16', 'i32', 'i64', 'ptr', 'float', 'double'}
    return all(t in ok for t in sig['params']) and (sig['ret'] in ok or sig['ret'] == 'void')


# LD-52 (#1528): IR の i128 引数は機械語では xmm0 (double) か整数レジスタ 1 本。入口型は REPORT_APPENDIX_LD53.md §7.1。
# 投入は native が sig の型どおりに行い、wasm は m11_tr_<fn> (i64×8 → IR 引数へ zext) に raw 64bit を wsig で渡す。
MACHINE_ENTRY = {
    0x40c660: ['double'],               # xmm0 (IR は i128 の型誤り)
    0x40c750: ['double'],               # xmm0
    0x40c420: ['double'],               # xmm0 (LD-288 / #5888: 入力 xmm0 を IR が落とし 0 固定になっていた)
    0x653c80: ['i64', 'i64', 'i64'],    # r8 の整数 (rcx・rdx は未使用)
    0x691dd0: ['i64', 'i64', 'i64'],    # rcx: オブジェクトのポインタ / rdx: i64 / r8: 1 byte flag
    0x442a50: ['double', 'i64', 'i64', 'i64'],  # xmm0 (4428c0 経由で 40c660)。rdx/r8/r9 は出力 word*
    0x442b90: ['double'],               # xmm0 (442420 → 40c660)
    0x664890: ['double'],               # xmm0 (476930 → 40c1d0)
    0x6649b0: ['double', 'i64', 'i64'], # xmm0 (476500 → 40bf40)。rdx/r8 は出力 ptr
    0x6649c0: ['float', 'i64', 'i64'],  # xmm0 は float (4764c0 が cvtss2sd)。rdx/r8 は出力 float*
    0x664a80: ['double', 'double'],     # xmm0・xmm1 (476020)
    0x4256c0: ['i64'],                  # rcx: POINT の値 (x = 下位 32bit, y = 上位 32bit)
}


# LD-203 (#4200): 653c80 の間接 call slot (VA 0x15f3480 = RVA 0x11f3480)。boot 状態では null で、call で segv する。
# 仮 proc の番地 (VMT slot 0 = LD_FAKEPROC_BASE + LD_VMT_IDX0 * LD_FAKEPROC_SZ) を入れると、native / wasm が同じ仮 proc を見る。根拠は REPORT_APPENDIX_LD203.md。
PATCH_BY_VA = {
    0x653c80: f'i:0x11f3480:q={LD_FAKEPROC_BASE + LD_VMT_IDX0 * LD_FAKEPROC_SZ:#x}',
}


def machine_sig(va, sig):
    ps = MACHINE_ENTRY.get(va)
    if ps is None:
        return sig
    return dict(sig, params=ps, wsig=['i64'] * len(ps), tr=True, ir_params=sig['params'])


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
    if sig.get('tr'):
        s += ' tr=1'
    if sig.get('wsig'):
        s += ' wsig=' + ','.join(sig['wsig'])
    if stkfill is not None:
        s += ' stkfill=%x' % stkfill
    if va in PATCH_BY_VA:
        extra = (extra + ' ' if extra else '') + 'p=' + PATCH_BY_VA[va]
    if extra:
        s += ' ' + extra
    return s
