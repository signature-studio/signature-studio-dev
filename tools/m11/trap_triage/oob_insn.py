#!/usr/bin/env python3
"""oob_insn.py <m11_boot.cjs.wasm> <wasm-function index> <module offset (hex)> [before=24]
V8 の生 stack (`wasm-function[N]:0xOFF`) の OFF (モジュール先頭からのバイト位置) が指す命令を, MVP + bulk
の命令デコードで特定し, その直前 before 命令を列挙する (#684)。関数名は export 名 (survey と同じ解決)。"""
import sys, re

def leb(b, i, signed=False, bits=32):
    r = s = 0
    while True:
        x = b[i]; i += 1
        r |= (x & 0x7f) << s; s += 7
        if not x & 0x80:
            break
    if signed and (x & 0x40):
        r -= 1 << s
    return r, i

def sections(b):
    i = 8; out = {}
    while i < len(b):
        sid = b[i]; sz, j = leb(b, i + 1); out.setdefault(sid, []).append((j, j + sz)); i = j + sz
    return out

def names_and_imports(b, secs):
    nimp = 0; exp = {}
    for (s, e) in secs.get(2, []):
        n, j = leb(b, s)
        for _ in range(n):
            for _k in range(2):
                l, j = leb(b, j); j += l
            kind = b[j]; j += 1
            if kind == 0:
                nimp += 1; _, j = leb(b, j)
            elif kind == 1:
                j += 1; fl, j = leb(b, j); _, j = leb(b, j)
                if fl & 1: _, j = leb(b, j)
            elif kind == 2:
                fl, j = leb(b, j); _, j = leb(b, j)
                if fl & 1: _, j = leb(b, j)
            else:
                j += 1; fl, j = leb(b, j); _, j = leb(b, j)
                if fl & 1: _, j = leb(b, j)
    for (s, e) in secs.get(7, []):
        n, j = leb(b, s)
        for _ in range(n):
            l, j = leb(b, j); nm = b[j:j + l].decode(); j += l
            kind = b[j]; idx, j = leb(b, j + 1)
            if kind == 0: exp.setdefault(idx, nm)
    return nimp, exp

NOIMM = set(range(0x45, 0xc5)) | {0x00, 0x01, 0x0b, 0x0f, 0x1a, 0x1b, 0xd1}
MEM = {0x28: 'i32.load', 0x29: 'i64.load', 0x2a: 'f32.load', 0x2b: 'f64.load', 0x2c: 'i32.load8_s', 0x2d: 'i32.load8_u',
       0x2e: 'i32.load16_s', 0x2f: 'i32.load16_u', 0x30: 'i64.load8_s', 0x31: 'i64.load8_u', 0x32: 'i64.load16_s',
       0x33: 'i64.load16_u', 0x34: 'i64.load32_s', 0x35: 'i64.load32_u', 0x36: 'i32.store', 0x37: 'i64.store',
       0x38: 'f32.store', 0x39: 'f64.store', 0x3a: 'i32.store8', 0x3b: 'i32.store16', 0x3c: 'i64.store8',
       0x3d: 'i64.store16', 0x3e: 'i64.store32'}
CTL = {0x02: 'block', 0x03: 'loop', 0x04: 'if', 0x05: 'else', 0x0b: 'end', 0x0c: 'br', 0x0d: 'br_if',
       0x0f: 'return', 0x10: 'call', 0x11: 'call_indirect', 0x1a: 'drop', 0x1b: 'select', 0x20: 'local.get',
       0x21: 'local.set', 0x22: 'local.tee', 0x23: 'global.get', 0x24: 'global.set', 0x00: 'unreachable',
       0x01: 'nop', 0x0e: 'br_table', 0x3f: 'memory.size', 0x40: 'memory.grow', 0x41: 'i32.const', 0x42: 'i64.const',
       0x43: 'f32.const', 0x44: 'f64.const', 0xd0: 'ref.null', 0xd2: 'ref.func'}

def decode_body(b, start, end):
    """(offset, text) の列. start は命令列の先頭 (locals の後)."""
    i = start; out = []; depth = 0
    while i < end:
        at = i; op = b[i]; i += 1
        if op in (0x02, 0x03, 0x04):
            bt = b[i]
            if bt == 0x40 or bt in (0x7f, 0x7e, 0x7d, 0x7c, 0x70, 0x6f):
                i += 1
            else:
                _, i = leb(b, i, signed=True)
            txt = CTL[op]
        elif op in MEM:
            _, i = leb(b, i); off, i = leb(b, i); txt = '%s offset=%d' % (MEM[op], off)
        elif op in (0x0c, 0x0d, 0x10, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0xd2):
            v, i = leb(b, i); txt = '%s %d' % (CTL.get(op, '0x%02x' % op), v)
        elif op == 0x11:
            t, i = leb(b, i); tb, i = leb(b, i); txt = 'call_indirect type=%d table=%d' % (t, tb)
        elif op == 0x0e:
            n, i = leb(b, i)
            for _k in range(n + 1): _, i = leb(b, i)
            txt = 'br_table'
        elif op == 0x1c:
            n, i = leb(b, i); i += n; txt = 'select'
        elif op == 0x41:
            v, i = leb(b, i, signed=True); txt = 'i32.const %d' % v
        elif op == 0x42:
            v, i = leb(b, i, signed=True); txt = 'i64.const %d' % v
        elif op == 0x43:
            i += 4; txt = 'f32.const'
        elif op == 0x44:
            i += 8; txt = 'f64.const'
        elif op in (0x3f, 0x40):
            i += 1; txt = CTL[op]
        elif op == 0xd0:
            i += 1; txt = 'ref.null'
        elif op == 0xfc:
            sub, i = leb(b, i)
            if sub == 8: _, i = leb(b, i); i += 1; txt = 'memory.init'
            elif sub == 9: _, i = leb(b, i); txt = 'data.drop'
            elif sub == 10: i += 2; txt = 'memory.copy'
            elif sub == 11: i += 1; txt = 'memory.fill'
            elif sub in (12, 14): _, i = leb(b, i); _, i = leb(b, i); txt = 'table.init/copy 0x%x' % sub
            else: txt = 'fc.%d' % sub; _, i = leb(b, i) if sub in (13, 15, 16, 17) else (0, i)
        elif op in NOIMM or op in CTL or 0x45 <= op <= 0xc4:
            txt = CTL.get(op, '0x%02x' % op)
        else:
            txt = '?0x%02x' % op
        out.append((at, txt))
    return out

def main():
    wasm = sys.argv[1]; fidx = int(sys.argv[2]); target = int(sys.argv[3], 16)
    before = int(sys.argv[4]) if len(sys.argv) > 4 else 24
    b = open(wasm, 'rb').read(); secs = sections(b)
    nimp, exp = names_and_imports(b, secs)
    bodies = []
    for (s, e) in secs.get(10, []):
        n, j = leb(b, s)
        for _ in range(n):
            sz, j2 = leb(b, j); bodies.append((j2, j2 + sz)); j = j2 + sz
    k = fidx - nimp
    if not (0 <= k < len(bodies)):
        sys.exit('function index %d out of code range (imports=%d)' % (fidx, nimp))
    bs, be = bodies[k]
    if not (bs <= target < be):
        sys.exit('offset 0x%x is outside function %d body [0x%x,0x%x)' % (target, fidx, bs, be))
    # body: locals vec のあと命令列
    nl, j = leb(b, bs)
    for _ in range(nl):
        _, j = leb(b, j); j += 1
    insns = decode_body(b, j, be)
    pos = [x for x, _ in insns].index(target) if target in [x for x, _ in insns] else None
    print('function[%d] %s  body=[0x%x,0x%x)  nimports=%d' % (fidx, exp.get(fidx, '?'), bs, be, nimp))
    if pos is None:
        sys.exit('offset 0x%x is not an instruction boundary (decoder mismatch?)' % target)
    for x, t in insns[max(0, pos - before):pos + 4]:
        print(('>> ' if x == target else '   ') + '0x%x  %s' % (x, t))

main()
