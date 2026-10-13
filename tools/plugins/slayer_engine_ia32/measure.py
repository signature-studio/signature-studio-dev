#!/usr/bin/env python3
"""FL Slayer x86 engine (block22434 = Slayer_Engine.dll) の ia32 decode 基準値 (#674 / 親 #536)。

  measure.py         実測 + 期待値 gate (C1〜C4)。 gate 不合格で exit 1。
  measure.py --nega  ネガティブコントロール (壊した入力は必ず FAIL)。 miss > 0 で exit 1。
  --seed / --bytes   --nega の N2 (乱数破壊) の seed と先頭バイト数 (既定 674 / 300)。
  --dump             全命令の逆アセンブルを work/ に書く (gitignore 対象)。

素材: $FL_WIN64_DIR/extracted/block22434_PE.bin (既定 $RUNNER_TEMP/fl-win64)。
入力の SHA-256 と capstone の版は固定値で検証し、不一致は gate より前に exit 1。 依存: capstone==5.0.7。
"""
import argparse, collections, hashlib, os, random, re, struct, sys, time

try:
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32, CS_MODE_64
    from capstone import x86 as cx
except ImportError:
    sys.exit('capstone が無い: uv pip install --python <python> capstone')

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, 'work')
X64C = os.path.normpath(os.path.join(HERE, '..', '..', 'ott', 'lift', 'x64c.py'))

EXPECT_MACHINE = 0x14C          # IMAGE_FILE_MACHINE_I386 (#536 C1)
EXPECT_TEXT_VSIZE = 73002       # .text VirtualSize (#536 C7 の 73,002 B)
UNDEC_MAX = 0.001               # gate C3: 線形掃引のデコード不能バイト率の上限 (粗い gate)
EXPECT_PRIV_MAX = 15            # gate C4: 特権命令 (ring0 専用) の件数の上限 = 実測 baseline
EXPECT_CAPSTONE = '5.0.7'       # 件数は capstone の版に依存するため版を固定する
EXPECT_SHA256 = '84b64c43cc6528401e1c4e84074785e100e8453c4db4c8322a5d5f608de724a9'  # block22434_PE.bin (179,512 B)
PRIV_MNEM = frozenset(['in', 'ins', 'insb', 'insw', 'insd', 'out', 'outs', 'outsb', 'outsw', 'outsd',
                       'hlt', 'cli', 'sti', 'iret', 'iretd', 'iretw', 'lgdt', 'lidt', 'lldt', 'ltr', 'lmsw',
                       'sgdt', 'sidt', 'sldt', 'clts', 'invd', 'wbinvd', 'invlpg', 'rdmsr', 'wrmsr', 'rsm',
                       'sysexit', 'swapgs', 'xsetbv'])
NEGA_SEED = 674
NEGA_CORRUPT_BYTES = 300

LEGACY_PREFIX = {0x66, 0x67, 0xF0, 0xF2, 0xF3, 0x2E, 0x36, 0x3E, 0x26, 0x64, 0x65}
SIMD_REG_PREFIX = ('xmm', 'ymm', 'mm')
SIMD_GROUPS = ['MMX', 'SSE1', 'SSE2', 'SSE3', 'SSSE3', 'SSE41', 'SSE42', 'SSE4A', 'AVX', 'AVX2', 'FMA', 'FMA4', 'F16C', 'XOP']
FPU_NON_X87 = {'fxsave', 'fxrstor', 'fxsave64', 'fxrstor64', 'femms'}
X87_CTRL = ('fldcw', 'fnstcw', 'fstcw', 'fnstenv', 'fldenv')
IA32_FOCUS = ('cdq', 'cwde', 'cbw', 'cwd', 'movzx', 'movsx', 'lea', 'push', 'pop', 'pushad', 'popad',
              'pushfd', 'popfd', 'xchg', 'cmpxchg', 'xadd', 'bswap', 'bt', 'bts', 'btr', 'btc', 'bsf', 'bsr',
              'shld', 'shrd', 'leave', 'enter', 'into', 'sahf', 'lahf', 'loop', 'jecxz', 'cpuid', 'rdtsc',
              'int', 'iret', 'ret', 'retf', 'call', 'jmp', 'cmpxchg8b', 'imul', 'mul', 'div', 'idiv')


def fl_dir():
    d = os.environ.get('FL_WIN64_DIR')
    if d:
        return d
    rt = os.environ.get('RUNNER_TEMP')
    if rt:
        return os.path.join(rt, 'fl-win64')
    sys.exit('FL_WIN64_DIR も RUNNER_TEMP も未設定 (素材の展開先が不明)')


def parse_pe(d):
    if d[:2] != b'MZ':
        raise ValueError('MZ 無し')
    lfa = struct.unpack_from('<I', d, 0x3C)[0]
    if d[lfa:lfa + 4] != b'PE\0\0':
        raise ValueError('PE シグネチャ無し')
    machine, nsec, _, _, _, optsz, chars = struct.unpack_from('<HHIIIHH', d, lfa + 4)
    opt = lfa + 24
    magic = struct.unpack_from('<H', d, opt)[0]
    ibase = struct.unpack_from('<I', d, opt + 28)[0] if magic == 0x10B else None
    secs = []
    for i in range(nsec):
        off = opt + optsz + 40 * i
        name, vsz, va, rsz, rptr = struct.unpack_from('<8sIIII', d, off)
        secs.append({'name': name.rstrip(b'\0').decode('ascii', 'replace'), 'vsize': vsz, 'va': va,
                     'rawsize': rsz, 'rawptr': rptr, 'hdr_off': off})
    text = next((s for s in secs if s['name'] == '.text'), None)
    if text is None:
        raise ValueError('.text 無し')
    return {'lfa': lfa, 'machine': machine, 'magic': magic, 'chars': chars, 'ibase': ibase,
            'sections': secs, 'text': text}


BASE_PREFIX = ('lock ', 'bnd ')


def key_of(ins):
    mn = ins.mnemonic
    for p in BASE_PREFIX:
        if mn.startswith(p):
            mn = mn[len(p):]
    return mn


def is_simd(ins, simd_ids):
    for op in ins.operands:
        if op.type == cx.X86_OP_REG and ins.reg_name(op.reg).startswith(SIMD_REG_PREFIX):
            return True
    return any(g in simd_ids for g in ins.groups)


class Stats:
    def __init__(self):
        self.n = 0
        self.undec = 0
        self.max_run = 0
        self.mnem = collections.Counter()
        self.f_raw = 0
        self.f_ctrl = collections.Counter()
        self.simd = 0
        self.ind_call = 0
        self.ind_jmp = 0
        self.dir_call = 0
        self.mem = collections.Counter()
        self.p66 = 0
        self.p67 = 0
        self.fs = 0
        self.mode_diff = 0
        self.mode_diff_mn = collections.Counter()
        self.x64_undec = 0
        self.priv = 0


def sweep(md32, md64, code, base, simd_ids, dump=None):
    st = Stats()
    run = 0
    pos = 0
    n = len(code)
    while pos < n:
        buf = bytes(code[pos:pos + 15])
        r = list(md32.disasm(buf, base + pos, 1))
        if not r:
            st.undec += 1
            run += 1
            st.max_run = max(st.max_run, run)
            pos += 1
            continue
        run = 0
        ins = r[0]
        st.n += 1
        k = key_of(ins)
        st.mnem[k] += 1
        if k in PRIV_MNEM:
            st.priv += 1
        if dump is not None:
            dump.write('%08x: %-24s %s %s\n' % (ins.address, ins.bytes.hex(), ins.mnemonic, ins.op_str))
        if k.startswith('f'):
            st.f_raw += 1
            if k in X87_CTRL:
                st.f_ctrl[k] += 1
        if is_simd(ins, simd_ids):
            st.simd += 1
        if ins.mnemonic in ('call', 'jmp') and ins.operands:
            t = ins.operands[0].type
            if t in (cx.X86_OP_REG, cx.X86_OP_MEM):
                if ins.mnemonic == 'call':
                    st.ind_call += 1
                else:
                    st.ind_jmp += 1
            elif ins.mnemonic == 'call':
                st.dir_call += 1
        for b in ins.bytes:
            if b not in LEGACY_PREFIX:
                break
            if b == 0x66:
                st.p66 += 1
            elif b == 0x67:
                st.p67 += 1
        seg_fs = False
        for op in ins.operands:
            if op.type != cx.X86_OP_MEM:
                continue
            m = op.mem
            if m.segment == cx.X86_REG_FS:
                seg_fs = True
            if m.index != 0:
                st.mem['sib'] += 1
            elif m.base == 0:
                st.mem['abs'] += 1
            else:
                st.mem['base'] += 1
        if seg_fs:
            st.fs += 1
        r64 = list(md64.disasm(buf, base + pos, 1))
        if not r64:
            st.x64_undec += 1
        if not r64 or r64[0].size != ins.size or r64[0].mnemonic != ins.mnemonic:
            st.mode_diff += 1
            st.mode_diff_mn[k] += 1
        pos += ins.size
    return st


def x64c_names():
    if not os.path.exists(X64C):
        return None
    src = open(X64C, encoding='utf-8').read()
    return set(re.findall(r'def i_([a-z0-9_]+)\(', src)) | set(re.findall(r'^\s*i_([a-z0-9_]+)\s*=', src, re.M))


def x64c_covers(k, names):
    if k.startswith('rep '):
        rest = k[4:]
        return rest.startswith(('movs', 'stos')) and rest[-1] in 'bwdq'
    if k in names:
        return True
    if k.startswith(('cmov', 'set')):
        return True
    if k.startswith('j') and k not in ('jmp', 'jecxz', 'jcxz'):
        return True
    if k.startswith('cmp') and k.endswith(('ss', 'sd')) and k not in ('cmpss', 'cmpsd'):
        return True
    if k.startswith('vcmp') and k.endswith(('sd', 'ss')):
        return True
    if k[:2] == 'vf' and k.endswith(('sd', 'ss')):
        return True
    return False


def analyze(data, log, dump_path=None):
    t0 = time.time()
    load0 = os.getloadavg()[0]
    pe = parse_pe(data)
    text = pe['text']
    base = (pe['ibase'] or 0) + text['va']
    code = data[text['rawptr']:text['rawptr'] + text['vsize']]
    md32 = Cs(CS_ARCH_X86, CS_MODE_32)
    md32.detail = True
    md64 = Cs(CS_ARCH_X86, CS_MODE_64)
    md64.detail = True
    simd_ids = {getattr(cx, 'X86_GRP_' + g) for g in SIMD_GROUPS if hasattr(cx, 'X86_GRP_' + g)}
    dump = open(dump_path, 'w', encoding='utf-8') if dump_path else None
    try:
        st = sweep(md32, md64, code, base, simd_ids, dump)
    finally:
        if dump:
            dump.close()
    elapsed = time.time() - t0
    total = len(code)
    ratio = st.undec / total if total else 1.0
    gates = [
        ('C1', 'PE machine == 0x14c (i386)', pe['machine'] == EXPECT_MACHINE,
         'machine=0x%x' % pe['machine']),
        ('C2', '.text VirtualSize == 73002', text['vsize'] == EXPECT_TEXT_VSIZE,
         '.text VirtualSize=%d (SizeOfRawData=%d, file off=0x%x)' % (text['vsize'], text['rawsize'], text['rawptr'])),
        ('C3', 'linear sweep undecoded ratio <= %.3f%%' % (UNDEC_MAX * 100), ratio <= UNDEC_MAX,
         'undecoded=%d B / %d B = %.4f%% (max run %d B)' % (st.undec, total, ratio * 100, st.max_run)),
        ('C4', 'privileged (ring0) insn count <= %d' % EXPECT_PRIV_MAX, st.priv <= EXPECT_PRIV_MAX,
         'priv=%d (in/out/ins/outs/iret/hlt/cli/sti/lgdt 等)' % st.priv),
    ]
    return {'pe': pe, 'text': text, 'base': base, 'total': total, 'st': st, 'ratio': ratio,
            'gates': gates, 'elapsed': elapsed, 'load0': load0, 'load1': os.getloadavg()[0], 'log': log}


def report(res, sha, path, names):
    pe, st, text = res['pe'], res['st'], res['text']
    log = res['log']
    log('[input] file=%s size=%d sha256=%s' % (path, os.path.getsize(path), sha))
    log('[pe] machine=0x%x magic=0x%x ImageBase=0x%x .text VA=0x%x file_off=0x%x VirtualSize=%d SizeOfRawData=%d' % (
        pe['machine'], pe['magic'], pe['ibase'] or 0, text['va'], text['rawptr'], text['vsize'], text['rawsize']))
    log('[sweep ia32 CS_MODE_32] capstone=%s insn=%d undecoded_bytes=%d (%.4f%%) max_run=%d B' % (
        CAP_VER, st.n, st.undec, res['ratio'] * 100, st.max_run))
    log('[timing] elapsed=%.2f s load_avg_1m start=%.2f end=%.2f parallelism=1 cpu=%d' % (
        res['elapsed'], res['load0'], res['load1'], os.cpu_count() or 0))
    log('[ops] x87(f*)=%d (exact, fxsave/fxrstor/femms 除外)=%d ctrl=%s simd=%d ind_call=%d ind_jmp=%d dir_call=%d priv=%d' % (
        st.f_raw, st.f_raw - sum(v for k, v in st.mnem.items() if k in FPU_NON_X87),
        ' '.join('%s=%d' % (k, st.f_ctrl.get(k, 0)) for k in X87_CTRL), st.simd, st.ind_call, st.ind_jmp, st.dir_call, st.priv))
    log('[mem] abs(disp only)=%d sib(index)=%d base_only=%d fs_seg=%d p66=%d p67=%d rep=%d' % (
        st.mem['abs'], st.mem['sib'], st.mem['base'], st.fs, st.p66, st.p67,
        sum(v for k, v in st.mnem.items() if k.startswith('rep '))))
    log('[mnem top 30] ' + ' '.join('%s=%d' % kv for kv in st.mnem.most_common(30)))
    log('[ia32-focus] ' + ' '.join('%s=%d' % (k, sum(v for m, v in st.mnem.items() if m == k or m.startswith(k + ' '))) for k in IA32_FOCUS))
    log('[x64c mode-diff] same bytes under CS_MODE_64: mismatch=%d (%.2f%%) x64_undecoded=%d top=%s' % (
        st.mode_diff, 100.0 * st.mode_diff / max(st.n, 1), st.x64_undec,
        ' '.join('%s=%d' % kv for kv in st.mode_diff_mn.most_common(15))))
    if names is None:
        log('[x64c coverage] x64c.py 不在 (省略)')
    else:
        unc = [(k, v) for k, v in st.mnem.most_common() if not x64c_covers(k, names)]
        cov_n = sum(v for k, v in st.mnem.items() if x64c_covers(k, names))
        log('[x64c coverage] mnemonic 単位で x64c が扱う insn=%d / %d (%.2f%%)。扱わない mnemonic 種=%d 件、上位: %s' % (
            cov_n, st.n, 100.0 * cov_n / max(st.n, 1), len(unc), ' '.join('%s=%d' % kv for kv in unc[:40])))
    for gid, desc, ok, detail in res['gates']:
        log('[gate %s] %s: %s — %s' % (gid, desc, 'PASS' if ok else 'FAIL', detail))


CAP_VER = None


def load_input(args, log):
    global CAP_VER
    import capstone
    CAP_VER = capstone.__version__
    if CAP_VER != EXPECT_CAPSTONE:
        log('[pin] FAIL capstone=%s (期待 %s)' % (CAP_VER, EXPECT_CAPSTONE))
        return None
    path = args.dll or os.path.join(fl_dir(), 'extracted', 'block22434_PE.bin')
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        log('[input] FAIL 素材が無い/空: %s' % path)
        return None
    data = open(path, 'rb').read()
    sha = hashlib.sha256(data).hexdigest()
    if sha != EXPECT_SHA256:
        log('[input] FAIL sha256=%s (期待 %s)' % (sha, EXPECT_SHA256))
        return None
    return path, data, sha


def measure(args, log):
    loaded = load_input(args, log)
    if loaded is None:
        log('[measure] FAIL 入力検証不合格 (gate は実行しない)')
        return 1
    path, data, sha = loaded
    dump_path = None
    if args.dump:
        os.makedirs(WORK, exist_ok=True)
        dump_path = os.path.join(WORK, 'block22434.ia32.disasm.txt')
    res = analyze(data, log, dump_path)
    report(res, sha, path, x64c_names())
    if dump_path:
        log('[dump] %s' % os.path.relpath(dump_path, HERE))
    fails = [g for g in res['gates'] if not g[2]]
    if fails:
        log('[measure] FAIL (%d/%d gate 不合格: %s)' % (len(fails), len(res['gates']), ' '.join(g[0] for g in fails)))
        return 1
    log('[measure] OK (%d/%d)' % (len(res['gates']), len(res['gates'])))
    return 0


def mut_machine(d, pe):
    b = bytearray(d)
    struct.pack_into('<H', b, pe['lfa'] + 4, 0x8664)
    return bytes(b)


def mut_text_random(d, pe):
    b = bytearray(d)
    off = pe['text']['rawptr']
    rng = random.Random(NEGA_SEED)
    for i in range(NEGA_CORRUPT_BYTES):
        b[off + i] = rng.randrange(256)
    return bytes(b)


def mut_text_vsize(d, pe):
    b = bytearray(d)
    struct.pack_into('<I', b, pe['text']['hdr_off'] + 8, EXPECT_TEXT_VSIZE + 1)
    return bytes(b)


NEGA = [
    ('N1', 'machine 0x14c -> 0x8664 (x86-64 のつもり)', mut_machine, {'C1'}),
    ('N2', '.text 先頭を乱数化 (seed / bytes は [nega params] 行)', mut_text_random, {'C4'}),
    ('N3', '.text VirtualSize 73002 -> 73003', mut_text_vsize, {'C2'}),
]


def nega(args, log):
    loaded = load_input(args, log)
    if loaded is None:
        log('nega: FAIL 入力検証不合格 (ネガコンは実行しない)')
        return 1
    _, data, _ = loaded
    pe = parse_pe(data)
    log('[nega params] N2 seed=%d corrupt_bytes=%d' % (NEGA_SEED, NEGA_CORRUPT_BYTES))
    os.makedirs(os.path.join(WORK, 'nega'), exist_ok=True)
    miss = 0
    for nid, desc, mut, expect in NEGA:
        d2 = mut(data, pe)
        out = os.path.join(WORK, 'nega', nid + '.dll')
        with open(out, 'wb') as f:
            f.write(d2)
        res = analyze(d2, lambda s: None)
        got = {g[0] for g in res['gates'] if not g[2]}
        hit = got == expect
        miss += 0 if hit else 1
        log('[nega %s] %s: expect FAIL=%s got FAIL=%s %s' % (nid, desc, sorted(expect), sorted(got),
                                                           'HIT' if hit else 'MISS'))
        for gid, gdesc, ok, detail in res['gates']:
            log('    [%s] %s: %s — %s' % (gid, gdesc, 'PASS' if ok else 'FAIL', detail))
    log('nega: %d/%d miss' % (miss, len(NEGA)))
    return 1 if miss else 0


def main():
    global NEGA_SEED, NEGA_CORRUPT_BYTES
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dll', help='対象 PE (既定: $FL_WIN64_DIR/extracted/block22434_PE.bin)')
    ap.add_argument('--nega', action='store_true', help='ネガティブコントロールを実行')
    ap.add_argument('--seed', type=int, default=NEGA_SEED, help='--nega の N2 の乱数 seed (既定 %d)' % NEGA_SEED)
    ap.add_argument('--bytes', type=int, default=NEGA_CORRUPT_BYTES,
                    help='--nega の N2 で乱数化する先頭バイト数 (既定 %d)' % NEGA_CORRUPT_BYTES)
    ap.add_argument('--dump', action='store_true', help='全命令の逆アセンブルを work/ に書く')
    args = ap.parse_args()
    NEGA_SEED, NEGA_CORRUPT_BYTES = args.seed, args.bytes
    log = lambda s: print(s, flush=True)
    rc = nega(args, log) if args.nega else measure(args, log)
    sys.exit(rc)


if __name__ == '__main__':
    main()
