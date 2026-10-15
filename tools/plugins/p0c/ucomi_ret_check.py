#!/usr/bin/env python3
"""ucomi_ret_check.py — 0x5e12b0 の戻り値 (xmm0) を native と IR で bit 比較する (#3439 / P0c-21)。

  python3 ucomi_ret_check.py <IR.ll> [--cases N]

census (p0c4_abi_e2e.py) の buf_diff は出力バッファしか比べない。0x5e12b0 は書き込みを持たず、
戻り値は xmm0 (= a>b ? a : b) なので、flags (CF|ZF) の誤りは buf_diff に現れない。
本試験は関数を単独のモジュールに取り出し、戻り値を比べる:
  native : 機械語 (PE の 0x5e12b0 から ret まで) を mmap(RWX) に置き ctypes で呼ぶ
  IR     : 修復後の IR (引数 %in.xmm0.bits / %in.xmm1.bits) を lli で実行。戻り値は
           `select i1 CF|ZF, xmm1, xmm0` で取り出す (ret i64 の代わり)
ucomiss / movaps は同じ意味の定義を付ける (ucomiss は no-op。flags は IR 側の fcmp が担う)。
"""
import argparse
import ctypes
import mmap
import os
import re
import struct
import subprocess
import sys
import tempfile
import random

import capstone
import pefile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import FL_WIN64_DIR  # noqa: E402

FN = 'function_5e12b0'
VA = 0x5e12b0
SPECIAL = [0x00000000, 0x80000000, 0x3f800000, 0xbf800000, 0x7fc00000, 0xffc00000,
           0x7f800000, 0xff800000, 0x00000001, 0x3f000000, 0x40000000]


def load_fn(ir_text):
    m = re.search(r'(?ms)^define [^\n]*@%s\(([^)]*)\)[^\n]*\{\n.*?^\}\n' % FN, ir_text)
    if not m:
        raise SystemExit('[FAIL] %s の定義が IR に無い' % FN)
    body = m.group(0)
    params = re.findall(r'i64 (%[\w.$-]+)', m.group(1))
    if len(params) != 2 or not all('xmm' in p for p in params):
        raise SystemExit('[FAIL] %s の引数が xmm0/xmm1 の 2 本になっていない: %s' % (FN, params))
    ret = re.search(r'^\s*ret i64 (%[\w.$-]+)\s*$', body, re.M)
    if not ret:
        raise SystemExit('[FAIL] ret 行が無い')
    cu = re.search(r'call void @__asm_ucomiss\(i128 (%[\w.$-]+), i128 (%[\w.$-]+)\)', body)
    br = re.search(r'br i1 (%[\w.$-]+), label %(\S+), label %', body)
    if not cu or not br:
        raise SystemExit('[FAIL] ucomiss 呼出し / 分岐の条件が見つからない (flags が未接続?)')
    a, b = cu.group(1), cu.group(2)
    body = body.replace('@%s(' % FN, '@t_fn(', 1)
    body = body.replace(ret.group(0), '\n'.join([
        '  %%t.sel = select i1 %s, i128 %s, i128 %s' % (br.group(1), b, a),
        '  %t.bits = trunc i128 %t.sel to i32',
        '  %t.r = zext i32 %t.bits to i64',
        '  ret i64 %t.r']), 1)
    order = ['xmm0' if p == '%in.xmm0.bits' else 'xmm1' for p in params]
    return body, order, params


def module_text(body):
    return '\n'.join([
        'target datalayout = "e-m:e-p:32:32-p10:8:8-p20:8:8-i64:64-i128:128-f128:64-n32:64-S128-ni:1:10:20"',
        'declare i32 @printf(ptr, ...)',
        '@fmt = private constant [6 x i8] c"%llu\\0A\\00"',
        '',
        'define void @__asm_ucomiss(i128 %a, i128 %b) {\n  ret void\n}',
        'define i128 @__asm_movaps(i128 %x) {\n  ret i128 %x\n}',
        body,
    ])


def driver(pairs, order):
    lines = ['define i32 @main() {', 'entry:']
    for i, (a, b) in enumerate(pairs):
        arg = {'xmm0': a, 'xmm1': b}
        args = ', '.join('i64 %d' % arg[o] for o in order)
        lines.append('  %%r%d = call i64 @t_fn(%s)' % (i, args))
        lines.append('  call i32 (ptr, ...) @printf(ptr @fmt, i64 %%r%d)' % i)
    lines += ['  ret i32 0', '}']
    return '\n'.join(lines)


def native_results(pe_path, pairs):
    pe = pefile.PE(pe_path, fast_load=True)
    mem = pe.get_memory_mapped_image()
    ib = pe.OPTIONAL_HEADER.ImageBase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    code = b''
    for ins in md.disasm(mem[VA - ib:VA - ib + 64], VA):
        code += ins.bytes
        if ins.mnemonic == 'ret':
            break
    buf = mmap.mmap(-1, 4096, prot=mmap.PROT_READ | mmap.PROT_WRITE | mmap.PROT_EXEC)
    buf.write(code)
    addr = ctypes.addressof(ctypes.c_char.from_buffer(buf))
    f = ctypes.CFUNCTYPE(ctypes.c_float, ctypes.c_float, ctypes.c_float)(addr)
    out = []
    for a, b in pairs:
        fa = struct.unpack('<f', struct.pack('<I', a))[0]
        fb = struct.unpack('<f', struct.pack('<I', b))[0]
        r = f(fa, fb)
        out.append(struct.unpack('<I', struct.pack('<f', r))[0])
    return code.hex(), out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ir')
    ap.add_argument('--cases', type=int, default=2000)
    ap.add_argument('--pe', default=os.path.join(FL_WIN64_DIR, 'extracted', 'block18983_PE.bin'))
    a = ap.parse_args()
    body, order, params = load_fn(open(a.ir, errors='replace').read())
    rnd = random.Random(3439)
    pairs = []
    for x in SPECIAL:
        for y in SPECIAL:
            pairs.append((x, y))
    while len(pairs) < a.cases:
        ra = struct.unpack('<I', struct.pack('<f', rnd.uniform(-10, 10)))[0]
        rb = struct.unpack('<I', struct.pack('<f', rnd.uniform(-10, 10)))[0]
        pairs.append((ra, rb))
    pairs.append((0x3f800000, 0x3f800000))
    with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR') or None) as td:
        ll = os.path.join(td, 'ucomi.ll')
        open(ll, 'w').write(module_text(body) + '\n' + driver(pairs, order) + '\n')
        exe = os.path.join(td, 'ucomi')
        c = subprocess.run(['clang', '-w', ll, '-o', exe], capture_output=True, text=True, timeout=600)
        if c.returncode != 0:
            sys.stderr.write(c.stderr[-2000:])
            raise SystemExit('[FAIL] clang rc=%d' % c.returncode)
        r = subprocess.run([exe], capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            raise SystemExit('[FAIL] IR 実行 rc=%d' % r.returncode)
        ir_out = [int(x) for x in r.stdout.split()]
    code_hex, nat = native_results(a.pe, pairs)
    if len(ir_out) != len(pairs) or len(nat) != len(pairs):
        raise SystemExit('[FAIL] 出力件数 native=%d IR=%d 期待 %d' % (len(nat), len(ir_out), len(pairs)))
    bad = [(pairs[i], nat[i], ir_out[i]) for i in range(len(pairs)) if nat[i] != ir_out[i]]
    print('[ucomi_ret] %s native=%s cases=%d args=%s mismatch=%d' % (FN, code_hex, len(pairs), order, len(bad)))
    for (a_, b_), n, i in bad[:5]:
        print('  [FAIL] a=0x%08x b=0x%08x native=0x%08x IR=0x%08x' % (a_, b_, n, i))
    if bad:
        raise SystemExit('[FAIL] 戻り値が native と不一致 (%d / %d)' % (len(bad), len(pairs)))
    print('   戻り値 bit 一致 %d / %d' % (len(pairs), len(pairs)))


if __name__ == '__main__':
    main()
