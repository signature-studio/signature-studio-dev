#!/usr/bin/env python3
"""FL Slayer x64 殻 (block 22433) と x86 engine (Slayer_Engine.dll, block 22434) の結合方式の静的検証 (#536)。

usage: slayer_x86.py [--nega] [--probe-retdec WORKDIR]
  (無印)   検査 C1〜C7 を実行。 1 つでも不合格なら exit 1。 全て合格のときだけ最後に `[slayer_x86] OK` を出す。
  --nega   各検査の入力を 1 箇所壊して実行し、その検査が FAIL することを確認 (外れたら exit 1)。
  --probe-retdec DIR   RetDec を x86 engine に当てた計測 (情報のみ。 合否に含めない)。
前提: FL_WIN64_DIR/extracted/ に block22433/22434/24765/24766 (docs/WORKFLOW.md §11)。 pefile + capstone。
"""
import bisect, collections, json, os, re, struct, subprocess, sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32, CS_OP_IMM

HERE = os.path.dirname(os.path.abspath(__file__))
FL = os.environ.get('FL_WIN64_DIR') or os.path.join(os.environ.get('RUNNER_TEMP', '/tmp'), 'fl-win64')
EXT = os.path.join(FL, 'extracted')
BR32, BR64 = 24765, 24766           # ilbridge.exe の x86 / x64 (TBridgeCommandLineParams を持つ PE は全 block 中この 2 本のみ)
CTOR_FN = 0x4521e0                  # FL Slayer の生成関数 (Slayer_Engine.dll 文字列を参照する唯一の関数)
LOAD_FN = 0x4529c0                  # engine ロード関数 (「plugin engine couldn't be loaded」を出す)


def ws(s):
    return s.encode('utf-16le')


def load(block):
    return open(os.path.join(EXT, 'block%05d_PE.bin' % block), 'rb').read()


def slayer_blocks():
    m = json.load(open(os.path.join(HERE, '..', 'PLUGIN_MATRIX.json')))
    p = [x for x in m['plugins'] if x['name'] == 'FL Slayer' and x['kind'] == 'Generators'][0]
    mods = {x['file']: x['block'] for x in p['win']['modules']}
    shell = [b for f, b in mods.items() if f.startswith('FL Slayer')][0]
    return shell, mods['Slayer_Engine.dll']


class Shell:
    """x64 殻の関数表 (.pdata) と byte-scan 呼出グラフ。 近似: `e8/e9 rel32` と `ff 25` を byte 走査 (命令境界は見ない)。"""
    def __init__(self, data):
        self.pe = pe = pefile.PE(data=data)
        self.base = pe.OPTIONAL_HEADER.ImageBase
        t = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
        self.tv, self.td = t.VirtualAddress, t.get_data()
        dd = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
        pd = pe.get_data(dd.VirtualAddress, dd.Size)
        self.fs = sorted((struct.unpack_from('<I', pd, i)[0], struct.unpack_from('<I', pd, i + 4)[0]) for i in range(0, len(pd), 12))
        self.st = [f[0] for f in self.fs]
        self.imp = {}
        for d in pe.DIRECTORY_ENTRY_IMPORT:
            for i in d.imports:
                self.imp[i.address - self.base] = d.dll.decode() + '!' + (i.name.decode() if i.name else str(i.ordinal))
        self._graph()

    def fn(self, a):
        j = bisect.bisect_right(self.st, a) - 1
        return self.st[j] if j >= 0 and a < self.fs[j][1] else None

    def _graph(self):
        td, tv = self.td, self.tv
        self.thunk, self.callees, self.api = {}, collections.defaultdict(set), collections.defaultdict(set)
        for i in range(len(td) - 6):
            if td[i] == 0xff and td[i + 1] == 0x25:
                tg = tv + i + 6 + struct.unpack_from('<i', td, i + 2)[0]
                if tg in self.imp:
                    self.thunk[tv + i] = self.imp[tg]
        for i in range(len(td) - 5):
            if td[i] in (0xe8, 0xe9):
                tg = tv + i + 5 + struct.unpack_from('<i', td, i + 1)[0]
                f = self.fn(tv + i)
                if f is None:
                    continue
                if tg in self.thunk:
                    self.api[f].add(self.thunk[tg])
                elif self.fn(tg) == tg:
                    self.callees[f].add(tg)

    def reach(self, root, maxd):
        seen, par, q = {root: 0}, {}, collections.deque([root])
        while q:
            f = q.popleft()
            for c in self.callees.get(f, ()):
                if c not in seen and seen[f] < maxd:
                    seen[c] = seen[f] + 1
                    par[c] = f
                    q.append(c)
        return seen, par

    def rip_refs(self, rva):
        """`lea/mov reg,[rip+d]` が rva を指す site の (site, 所属関数) 一覧。"""
        out = []
        for i in range(len(self.td) - 4):
            if self.td[i - 2] in (0x8d, 0x8b) and self.tv + i + 4 + struct.unpack_from('<i', self.td, i)[0] == rva:
                out.append((self.tv + i, self.fn(self.tv + i)))
        return out

    def ustr_rva(self, text):
        raw = self.pe.__data__
        return [self.pe.get_rva_from_offset(m.start()) for m in re.finditer(re.escape(ws(text)), raw)]


def c1_engine(eng):
    """engine は x86 DLL・.pdata 無し・export は main のみ・import は KERNEL32 のみ。"""
    pe = pefile.PE(data=eng)
    exp = [e.name for e in pe.DIRECTORY_ENTRY_EXPORT.symbols]
    dlls = sorted({d.dll.decode() for d in pe.DIRECTORY_ENTRY_IMPORT})
    ok = (pe.FILE_HEADER.Machine == 0x14c and pe.OPTIONAL_HEADER.DATA_DIRECTORY[3].Size == 0
          and exp == [b'main'] and dlls == ['KERNEL32.dll'])
    return ok, 'machine=%#x pdata=%d exports=%s imports=%s(%d fn)' % (
        pe.FILE_HEADER.Machine, pe.OPTIONAL_HEADER.DATA_DIRECTORY[3].Size, exp, dlls,
        sum(len(d.imports) for d in pe.DIRECTORY_ENTRY_IMPORT))


def c2_shell_names_engine(sh):
    """殻は 'Slayer_Engine.dll' (UTF-16 Delphi 文字列) を CTOR_FN 内の 1 箇所だけで参照し、同じ関数が 'System\\Tools\\Bridge\\' も参照する。"""
    r_eng = sh.ustr_rva('Slayer_Engine.dll')
    r_br = sh.ustr_rva('System\\Tools\\Bridge\\')
    refs = [x for r in r_eng for x in sh.rip_refs(r)]
    refs_br = [x for r in r_br for x in sh.rip_refs(r)]
    ok = len(r_eng) == 1 and [f for _, f in refs] == [CTOR_FN] and CTOR_FN in [f for _, f in refs_br]
    return ok, 'Slayer_Engine.dll strings=%d refs=%s; Bridge\\ refs in ctor=%d' % (
        len(r_eng), [(hex(a), hex(f or 0)) for a, f in refs], sum(1 for _, f in refs_br if f == CTOR_FN))


def c3_spawn_chain(sh):
    """CTOR_FN → LOAD_FN → … → CreateProcessW を呼ぶ関数 (深さ込みの経路) が実在する。"""
    seen, par = sh.reach(CTOR_FN, 8)
    hit = [f for f in seen if any('CreateProcessW' in a for a in sh.api.get(f, ()))]
    if not hit or LOAD_FN not in seen:
        return False, 'LOAD_FN reached=%s CreateProcessW callers=%s' % (LOAD_FN in seen, hit)
    f = hit[0]
    path = [f]
    while path[-1] in par:
        path.append(par[path[-1]])
    path = [hex(p) for p in reversed(path)]
    return path[1] == hex(LOAD_FN), 'path=%s' % ' -> '.join(path)


def c4_bridge_names(sh):
    """殻は '32bit\\ilbridge.exe' / '64bit\\ilbridge.exe' と起動引数 -wrapper/-address/-processid の文字列 (UTF-16) をそれぞれちょうど 1 つ持つ (存在のみの検査。 参照関係は見ない)。"""
    names = ['32bit\\ilbridge.exe', '64bit\\ilbridge.exe', '-wrapper', '-address', '-processid']
    cnt = {n: len(sh.ustr_rva(n)) for n in names}
    return all(v == 1 for v in cnt.values()), str(cnt)


def c5_bridge_exe(br32, br64):
    """ilbridge.exe 実体: x86 EXE と x64 EXE が存在し、ともに TBridgeCommandLineParams と共有メモリ/プロセス API を持つ。"""
    res = []
    for b, mach in ((br32, 0x14c), (br64, 0x8664)):
        pe = pefile.PE(data=b)
        names = {i.name.decode() for d in pe.DIRECTORY_ENTRY_IMPORT for i in d.imports if i.name}
        need = {'OpenFileMappingW', 'MapViewOfFile', 'CreateFileMappingW', 'LoadLibraryW', 'GetProcAddress', 'OpenProcess'}
        res.append(pe.FILE_HEADER.Machine == mach and not pe.FILE_HEADER.Characteristics & 0x2000
                   and b'TBridgeCommandLineParams' in b and need <= names)
    return all(res), 'x86 exe ok=%s, x64 exe ok=%s' % tuple(res)


def c6_engine_vst2(eng):
    """export `main` は audioMaster(0, audioMasterVersion=1, 0, 0, 0, 0) を呼び、AEffect に magic 'VstP' (0x56737450) を書く (VST2 規約)。"""
    pe = pefile.PE(data=eng)
    main = [e.address for e in pe.DIRECTORY_ENTRY_EXPORT.symbols if e.name == b'main'][0]
    code = pe.get_data(main, 20)
    call_ok = code[5:].startswith(bytes.fromhex('6a006a006a006a006a016a00ffd6'))   # push 0 x4; push 1; push 0; call esi
    magic = [pe.get_rva_from_offset(m.start()) for m in re.finditer(re.escape(struct.pack('<I', 0x56737450)), eng)]
    text = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
    magic_in_text = [r for r in magic if text.VirtualAddress <= r < text.VirtualAddress + text.Misc_VirtualSize]
    return call_ok and len(magic_in_text) == 1, 'main=%#x audioMaster(opcode=1) call=%s VstP-imm sites in .text=%d' % (main, call_ok, len(magic_in_text))


def engine_stats(eng):
    pe = pefile.PE(data=eng)
    t = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
    d = t.get_data()[:t.Misc_VirtualSize]
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    c, off = collections.Counter(), 0
    base = pe.OPTIONAL_HEADER.ImageBase + t.VirtualAddress
    while off < len(d):
        ok = False
        for i in md.disasm(d[off:], base + off):
            ok = True
            off = i.address - base + i.size
            c['ins'] += 1
            m = i.mnemonic
            if m.startswith('f') and m not in ('fs',):
                c['x87'] += 1
            if m in ('fldcw', 'fnstcw', 'fstcw'):
                c['cw'] += 1
            gn = {md.group_name(g) for g in i.groups}
            if gn & {'sse1', 'sse2', 'sse3', 'ssse3', 'sse41', 'sse42', 'avx', 'mmx', '3dnow'}:
                c['simd'] += 1
            if m == 'call' and i.operands and i.operands[0].type != CS_OP_IMM:
                c['icall'] += 1
        if not ok:
            off += 1
    c['text_bytes'] = t.Misc_VirtualSize
    return c


def c7_engine_profile(eng):
    """engine の命令構成 (線形掃引。 .text 内データも命令に化けるため近似): SIMD 命令 0 / x87 あり。"""
    c = engine_stats(eng)
    return c['simd'] == 0 and c['x87'] > 0 and c['ins'] > 0, dict(c)


def run(shell, eng, br32, br64, verbose=True):
    sh = Shell(shell)
    res = [('C1 engine は x86 DLL / .pdata 無し / export main のみ / import KERNEL32 のみ', *c1_engine(eng)),
           ('C2 殻が Slayer_Engine.dll を CTOR 内 1 箇所で参照', *c2_shell_names_engine(sh)),
           ('C3 CTOR → LOAD → CreateProcessW の呼出経路', *c3_spawn_chain(sh)),
           ('C4 殻が 32bit/64bit ilbridge.exe 名と起動引数を持つ', *c4_bridge_names(sh)),
           ('C5 ilbridge.exe (x86/x64) 実体', *c5_bridge_exe(br32, br64)),
           ('C6 engine は VST2 plugin (main + audioMaster + VstP)', *c6_engine_vst2(eng)),
           ('C7 engine は SIMD 0 / x87 あり', *c7_engine_profile(eng))]
    if verbose:
        for n, ok, info in res:
            print('%s %s: %s' % ('PASS' if ok else 'FAIL', n, info))
    return [ok for _, ok, _ in res]


def mutate(b, old, new, count=1):
    assert b.count(old) >= 1, old
    return b.replace(old, new, count)


def nega(shell, eng, br32, br64):
    """検査 Ck 1 つを壊した入力で Ck だけが FAIL になることを確認。"""
    mach = struct.pack('<H', 0x14c)
    pe_off = struct.unpack_from('<I', eng, 0x3c)[0]
    eng_n1 = bytearray(eng); struct.pack_into('<H', eng_n1, pe_off + 4, 0x8664)                      # C1: machine
    eng_n6 = mutate(eng, bytes.fromhex('6a006a006a006a006a016a00ffd6'), bytes.fromhex('6a006a006a006a006a026a00ffd6'))   # C6: opcode 1→2
    cases = [
        ('N1 engine machine を 0x8664 に', 0, (shell, bytes(eng_n1), br32, br64)),
        ('N2 殻の Slayer_Engine.dll 文字列を改名', 1, (mutate(shell, ws('Slayer_Engine.dll'), ws('Slayer_Engine.dlX')), eng, br32, br64)),
        ('N3 殻の CreateProcessW import 名を CreateProcessX に', 2, (mutate(shell, b'CreateProcessW\0', b'CreateProcessX\0'), eng, br32, br64)),
        ('N4 殻の 64bit\\ilbridge.exe 文字列を改名', 3, (mutate(shell, ws('64bit\\ilbridge.exe'), ws('64bit\\ilbridgX.exe')), eng, br32, br64)),
        ('N5 x86 ilbridge の TBridgeCommandLineParams を改名', 4, (shell, eng, mutate(br32, b'TBridgeCommandLineParams', b'TBridgeCommandLineParamX'), br64)),
        ('N6 engine main の audioMaster opcode を 2 に', 5, (shell, eng_n6, br32, br64)),
        ('N7 engine の .text 先頭に SSE 命令 (xorps) を 1 つ書込', 6, None),
    ]
    pe = pefile.PE(data=eng)
    t = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
    e7 = bytearray(eng)
    # .text 内の最初の int3/nop パディング 3 byte (cc cc cc) を xorps xmm0,xmm0 (0f 57 c0) に置換
    pad = bytes(eng[t.PointerToRawData:t.PointerToRawData + t.SizeOfRawData]).find(b'\xcc\xcc\xcc')
    if pad < 0:
        pad = bytes(eng[t.PointerToRawData:t.PointerToRawData + t.SizeOfRawData]).find(b'\x90\x90\x90')
    e7[t.PointerToRawData + pad:t.PointerToRawData + pad + 3] = b'\x0f\x57\xc0'
    cases[-1] = (cases[-1][0], 6, (shell, bytes(e7), br32, br64))
    bad = 0
    for name, k, args in cases:
        r = run(*args, verbose=False)
        others = [i for i, ok in enumerate(r) if not ok and i != k]
        good = (not r[k]) and not others
        print('%s %s -> C%d=%s others_failed=%s' % ('OK  ' if good else 'MISS', name, k + 1, 'FAIL' if not r[k] else 'PASS', [o + 1 for o in others]))
        bad += 0 if good else 1
    return bad


def probe_retdec(eng_path, work):
    os.makedirs(work, exist_ok=True)
    dll = os.path.join(work, 'slayer_engine_x86.dll')
    open(dll, 'wb').write(open(eng_path, 'rb').read())
    log = subprocess.run(['/opt/retdec/bin/retdec-decompiler', dll, '-o', os.path.join(work, 'se.c'), '--timeout', '250'],
                         capture_output=True, text=True)
    ll = open(os.path.join(work, 'se.ll')).read()
    defs = re.split(r'\n(?=define )', ll)[1:]
    f80 = [f for f in defs if 'x86_fp80' in f.split('\n}\n')[0]]
    em = subprocess.run(['bash', '-c', 'source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; emcc -c %s -o %s -w -O0' % (
        os.path.join(work, 'se.ll'), os.path.join(work, 'se.o'))], capture_output=True, text=True)
    first = (em.stderr.strip().splitlines() or [''])[0]
    print('[probe] retdec rc=%d defines=%d defines_with_x86_fp80=%d emcc_rc=%d first_error=%s' % (
        log.returncode, len(defs), len(f80), em.returncode, first))
    # 1 件目の誤り (関数局所名 %wide-string の定数化) だけを機械的に除いて再度 emcc。 2 件目以降の阻害要因の有無を見る
    s2 = re.sub(r'(?m)^(@\S+ = [a-z ]*constant \[\d+ x i16\]) %wide-string', r'\1 zeroinitializer', ll)
    open(os.path.join(work, 'se2.ll'), 'w').write(s2)
    em2 = subprocess.run(['bash', '-c', 'source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; emcc -c %s -o %s -w -O0' % (
        os.path.join(work, 'se2.ll'), os.path.join(work, 'se2.o'))], capture_output=True, text=True)
    print('[probe] after stubbing wide-string: emcc_rc=%d first_error=%s' % (
        em2.returncode, (em2.stderr.strip().splitlines() or [''])[0].replace(work, '<work>')))


def main():
    shell_b, eng_b = slayer_blocks()
    assert (shell_b, eng_b) == (22433, 22434), (shell_b, eng_b)
    shell, eng, br32, br64 = load(shell_b), load(eng_b), load(BR32), load(BR64)
    rc = 0
    if '--probe-retdec' in sys.argv:
        probe_retdec(os.path.join(EXT, 'block%05d_PE.bin' % eng_b), sys.argv[sys.argv.index('--probe-retdec') + 1])
        return 0
    if '--nega' in sys.argv:
        bad = nega(shell, eng, br32, br64)
        print('[slayer_x86] nega: %d/7 miss' % bad)
        return 1 if bad else 0
    r = run(shell, eng, br32, br64)
    if all(r):
        print('[slayer_x86] OK (%d/%d)' % (sum(r), len(r)))
        return 0
    print('[slayer_x86] FAIL (%d/%d)' % (sum(r), len(r)), file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
