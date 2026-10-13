#!/usr/bin/env python3
"""xcheck414.py [N] : #764 function_414ad0 の C 版 / IR 版 / LStr 版の同一入力突合 (機械語 oracle = unicorn)。

oracle: PE (block00031_PE.bin) の 0x414ad0..0x414ba9 の実バイト列を unicorn で実行する。
callee (412d60 / 409470 / 414850 / 412c20 / 409c80 / 40f560) は Python スタブに置換する。
スタブの仕様は xcheck414_harness.c と同一。各 case: var 引数 s = ARENA+0x80, n = edx。
結果行 = fault ret fnv1a64(arena) bump。成果物は tools/m11/work/xcheck414/ (gitignore 対象)。
要 env: FL_WIN64_DIR (または LD_M11_PE)。
"""
import os, sys, random, struct, subprocess, importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / 'tools' / 'shared'))
sys.path.insert(0, str(REPO / 'tools' / 'm11' / 'ldfix'))
from paths import FL_WIN64_DIR  # docs/REFERENCES.md [WIN64]
import unicorn as uc
from unicorn.x86_const import (UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8,
                               UC_X86_REG_RAX, UC_X86_REG_RSP, UC_X86_REG_RIP)
import ldmach

ARENA = 0x20000000
ARENA_SIZE = 0x8000
HEAP0 = ARENA + 0x3000
EMPTY = ARENA + 0x2010
STACK = 0x10000000
STACK_SIZE = 0x10000
SENT = 0x50000000
FN = 0x414ad0
FN_END = 0x414ba9 + 1
G_WORD = 2  # 412c20 が [rip+..] から読む 16bit 値の代用 (実値は未確認。C/IR/機械語で同じ値を使う)
NS = [-2, -1, 0, 1, 2, 3, 4, 7, 8, 15, 16, 100]
M64 = (1 << 64) - 1


class Fault(Exception):
    pass


def fnv(b):
    h = 1469598103934665603
    for c in b:
        h = ((h ^ c) * 1099511628211) & M64
    return h


def make_cases(seed, count):
    rnd = random.Random(seed)
    cases = []
    for _ in range(count):
        arena = bytearray(rnd.getrandbits(8) for _ in range(ARENA_SIZE))
        n = rnd.choice(NS)
        h = ARENA + rnd.choice([0x1000, 0x1100, 0x1200, 0x2000, 0x2200])
        data = h + 16
        rc = rnd.choice([0, 1, 1, 1, 2, -1])
        ln = rnd.choice([n, n, n + 1, n - 1, 0, 5, -1])
        struct.pack_into('<i', arena, h + 8 - ARENA, rc)
        struct.pack_into('<i', arena, data - 4 - ARENA, ln)
        kind = rnd.choice(['hdr', 'hdr', 'zero', 'wild'])
        if kind == 'zero':
            p = 0
        elif kind == 'wild':
            p = rnd.choice([0x1000, 0x18, ARENA + ARENA_SIZE - 4, 0x7fff0000])
        else:
            p = data
        struct.pack_into('<Q', arena, 0x80, p)
        cases.append((n, bytes(arena)))
    return cases


def write_cases(path, cases):
    with open(path, 'wb') as f:
        f.write(struct.pack('<I', len(cases)))
        for n, arena in cases:
            f.write(struct.pack('<i', n))
            f.write(arena)


class Heap:
    def __init__(self):
        self.bump = HEAP0
        self.sz = {}

    def alloc(self, n):
        if self.bump + n > ARENA + ARENA_SIZE:
            raise Fault()
        p = self.bump
        self.bump += (n + 15) & ~15
        self.sz[p] = n
        return p


def run_unicorn(img, cases):
    out = []
    for n, arena in cases:
        m = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_64)
        m.mem_map(0x414000, 0x2000, uc.UC_PROT_ALL)
        m.mem_write(FN, img)
        m.mem_map(0x409000, 0x1000, uc.UC_PROT_ALL)
        m.mem_map(0x412000, 0x1000, uc.UC_PROT_ALL)
        m.mem_map(0x40f000, 0x1000, uc.UC_PROT_ALL)
        m.mem_map(SENT & ~0xfff, 0x1000, uc.UC_PROT_ALL)
        m.mem_map(ARENA, ARENA_SIZE, uc.UC_PROT_ALL)
        m.mem_write(ARENA, arena)
        m.mem_map(STACK, STACK_SIZE, uc.UC_PROT_ALL)
        heap = Heap()

        def ret_from_stub(mu):
            rsp = mu.reg_read(UC_X86_REG_RSP)
            mu.reg_write(UC_X86_REG_RIP, struct.unpack('<Q', bytes(mu.mem_read(rsp, 8)))[0])
            mu.reg_write(UC_X86_REG_RSP, rsp + 8)

        def stub_412d60(mu, addr, size, _):
            dest = mu.reg_read(UC_X86_REG_RCX)
            old = struct.unpack('<Q', bytes(mu.mem_read(dest, 8)))[0]
            if old:
                hdr = old - 0x10
                mu.mem_write(dest, struct.pack('<Q', 0))
                rc = struct.unpack('<i', bytes(mu.mem_read(hdr + 8, 4)))[0]
                if rc > 0:
                    mu.mem_write(hdr + 8, struct.pack('<I', rc - 1))
            mu.reg_write(UC_X86_REG_RAX, dest)
            ret_from_stub(mu)

        def stub_409470(mu, addr, size, _):
            ptr = mu.reg_read(UC_X86_REG_RCX)
            newsize = mu.reg_read(UC_X86_REG_RDX)
            signed = newsize - (1 << 64) if newsize >> 63 else newsize
            cur = struct.unpack('<Q', bytes(mu.mem_read(ptr, 8)))[0]
            nw = 0
            if cur:
                if signed > 0:
                    nw = heap.alloc(newsize)
                    mm = min(heap.sz.get(cur, 0), newsize)
                    if mm:
                        mu.mem_write(nw, bytes(mu.mem_read(cur, mm)))
            elif signed > 0:
                nw = heap.alloc(newsize)
            mu.mem_write(ptr, struct.pack('<Q', nw))
            mu.reg_write(UC_X86_REG_RAX, nw)
            ret_from_stub(mu)

        def stub_414850(mu, addr, size, _):
            p = mu.reg_read(UC_X86_REG_RCX)
            mu.reg_write(UC_X86_REG_RAX, p if p else EMPTY)
            ret_from_stub(mu)

        def stub_412c20(mu, addr, size, _):
            ni = mu.reg_read(UC_X86_REG_RCX) & 0xffffffff
            ni = ni - (1 << 32) if ni >> 31 else ni
            if ni <= 0:
                mu.reg_write(UC_X86_REG_RAX, 0)
            else:
                c = heap.alloc((ni + 1) * 2 + 16)
                mu.mem_write(c + 0xc, struct.pack('<I', ni & 0xffffffff))
                mu.mem_write(c + 8, struct.pack('<I', 1))
                mu.mem_write(c + 6, struct.pack('<H', 2))
                mu.mem_write(c + 4, struct.pack('<H', G_WORD))
                mu.mem_write(c + 16 + ni * 2, b'\x00\x00')
                mu.reg_write(UC_X86_REG_RAX, c + 16)
            ret_from_stub(mu)

        def stub_409c80(mu, addr, size, _):
            src = mu.reg_read(UC_X86_REG_RCX)
            dst = mu.reg_read(UC_X86_REG_RDX)
            k = mu.reg_read(UC_X86_REG_R8)
            k = k - (1 << 64) if k >> 63 else k
            if k > 0:
                mu.mem_write(dst, bytes(mu.mem_read(src, k)))
            ret_from_stub(mu)

        def stub_40f560(mu, addr, size, _):
            raise Fault()

        stubs = {0x412d60: stub_412d60, 0x409470: stub_409470, 0x414850: stub_414850,
                 0x412c20: stub_412c20, 0x409c80: stub_409c80, 0x40f560: stub_40f560}
        for a, fn in stubs.items():
            m.hook_add(uc.UC_HOOK_CODE, fn, begin=a, end=a)
        m.reg_write(UC_X86_REG_RCX, ARENA + 0x80)
        m.reg_write(UC_X86_REG_RDX, n & 0xffffffff)
        top = STACK + STACK_SIZE - 0x100
        m.mem_write(top - 8, struct.pack('<Q', SENT))
        m.reg_write(UC_X86_REG_RSP, top - 8)
        fault, ret = 0, 0
        try:
            m.emu_start(FN, SENT)
            ret = m.reg_read(UC_X86_REG_RAX)
        except (uc.UcError, Fault):
            fault = 1
        ar = bytes(m.mem_read(ARENA, ARENA_SIZE))
        out.append('%d %d %016x %d' % (fault, 0 if fault else ret, fnv(ar), heap.bump))
    return out


def run_native(exe, case_file):
    r = subprocess.run([exe, case_file, str(G_WORD)], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        sys.exit('%s rc=%d %s' % (exe, r.returncode, r.stderr[:300]))
    return [x for x in r.stdout.split('\n') if x]


def build(name, flags, srcs, outdir):
    exe = str(outdir / name)
    r = subprocess.run(['clang', '-O0', '-g0', '-w', '-I', str(outdir)] + flags + srcs + ['-o', exe],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit('build %s failed: %s' % (name, r.stderr[:1500]))
    return exe


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    out = HERE.parent / 'work' / 'xcheck414'
    out.mkdir(parents=True, exist_ok=True)
    pe = os.environ.get('LD_M11_PE', f'{FL_WIN64_DIR}/extracted/block00031_PE.bin')
    mach = ldmach.Machine(pe)
    rva, size = mach.fns[FN]
    img = bytes(mach.read(rva, size))
    assert len(img) == FN_END - FN, (len(img), FN_END - FN)

    m11 = (HERE.parent / 'm11_ov.c').read_text().split('\n')
    (out / 'body_c.c').write_text('\n'.join(m11[658:683]) + '\n')
    (out / 'body_lstr.c').write_text('\n'.join(m11[688:720]) + '\n')
    h = str(HERE / 'xcheck414_harness.c')

    spec = importlib.util.spec_from_file_location('ir414_fix', str(HERE / 'ir414_fix.py'))
    ir = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ir)
    (out / 'ir_only.ll').write_text(
        'declare i64 @function_412d60(i64, i64)\n'
        'declare i64 @function_409470(ptr, i64)\n'
        'declare i64 @function_414850(i64)\n'
        'declare i64 @function_412c20(i64)\n'
        'declare void @function_409c80(i64, i64, i64)\n' + ir.BODY + '\n')
    r = subprocess.run(['clang', '-x', 'ir', '-c', '-O0', '-w', '-o', str(out / 'ir_only.o'),
                        str(out / 'ir_only.ll')], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit('ir compile failed: ' + r.stderr[:1500])

    exe_c = build('h_c', ['-DBODY_C'], [h], out)
    exe_l = build('h_lstr', ['-DBODY_LSTR'], [h], out)
    exe_i = build('h_ir', [], [h, str(out / 'ir_only.o')], out)

    cases = make_cases(0x764, count)
    cf = str(out / 'cases.bin')
    write_cases(cf, cases)
    expect = run_unicorn(img, cases)
    got = {'C(UStr #if)': run_native(exe_c, cf), 'LStr(#else)': run_native(exe_l, cf),
           'IR(ir414_fix)': run_native(exe_i, cf)}
    print('cases=%d G_WORD=%d fn_bytes=%d' % (len(cases), G_WORD, len(img)))
    print('mc(unicorn): fault=%d ok=%d' % (sum(e.startswith('1 ') for e in expect),
                                          sum(e.startswith('0 ') for e in expect)))
    for name, lines in got.items():
        bad = [i for i, (a, b) in enumerate(zip(expect, lines)) if a != b]
        bad += list(range(min(len(expect), len(lines)), max(len(expect), len(lines))))
        print('%-14s diff=%d / %d' % (name, len(bad), len(cases)))
        for i in bad[:3]:
            print('   case %d n=%d mc=[%s] %s=[%s]' % (i, cases[i][0], expect[i], name,
                                                       lines[i] if i < len(lines) else '-'))


if __name__ == '__main__':
    main()
