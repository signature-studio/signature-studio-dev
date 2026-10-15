#!/usr/bin/env python3
"""hs_val_probe.py — Dispatcher (0x13173a0) の格納元 call 先 (#3652 / PLG-P0b-36) の実値を unicorn で測る。

方式 (hs_disp_emu.py と同じ写像・同じ stub 規則。違いは観測点の追加だけ):
  * 観測 (probe): 指定 VA の命令を実行する直前に、レジスタ・[rbp+off]・[reg+off] を読む。
  * 分離実行 (isolate): 1 関数を引数を与えて単独で実行する。許可範囲 [lo,hi) の外への call は
    実行せず戻り値 (既定 0・RET 指定で変更) として戻す (hs_disp_emu.py と同じ stub)。
  * 格納元 call 先の実行を許可したいときは ALLOW で範囲を足す (そのなかの外部 call は stub)。

依存: unicorn 2.1.4 / pefile (hs_disp_emu.py と同じ)。
使い方: FL_WIN64_DIR=<展開先> PYTHONPATH=<unicorn,pefile,capstone> python3 hs_val_probe.py <mode> [args]
  mode=disp          : 全 256 ID (または指定 ID) の Dispatcher 実行で、観測点の引数値と到達を出す
                       (HS_DISP_STACK_FILL=<値> でスタック初期内容を指定できる)
  mode=fn ENTRY HI 'rcx=..,r8=..' : 1 関数を引数を与えて単独実行する (許可範囲 [ENTRY,HI))
  mode=sweep11ffde0  : 0x11ffde0 (受入 1) を ecx の値ごとに単独実行し、戻り値と末尾 VA を出す
  mode=verify        : 0xe4e970 (受入 3) を実行し、オブジェクトのフィールドを変えて予測式と照合する
  mode=word41        : 0x11d06e0 (受入 4) を出力 word の初期値 0/0x60/0x5 で単独実行する
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hs_disp_emu as E
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE, UC_HOOK_MEM_UNMAPPED, UC_PROT_ALL
from unicorn.x86_const import (UC_X86_REG_RAX, UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_RSP,
                               UC_X86_REG_RBP, UC_X86_REG_R8, UC_X86_REG_R9, UC_X86_REG_RIP)

PAGE = 0x1000
MAX_STEPS = 400000
_IMG = {}
FILL = int(os.environ['HS_DISP_STACK_FILL'], 0) if os.environ.get('HS_DISP_STACK_FILL') else None
REG = {'rax': UC_X86_REG_RAX, 'rcx': UC_X86_REG_RCX, 'rdx': UC_X86_REG_RDX, 'r8': UC_X86_REG_R8,
       'r9': UC_X86_REG_R9, 'rbp': UC_X86_REG_RBP, 'rsp': UC_X86_REG_RSP}

# Dispatcher 内の観測点 (#3652 の受入 1〜4 の call 直前)。rbp 基準のスロットと引数レジスタを読む。
DISP_PROBES = {
    0x1318730: ['rbp+0x1880:8'],
    0x132178c: ['rbp+0x1880:8'],                                          # [rbp+0x1880] の初期値 (受入 1 の ecx の供給元)
    0x1318e3e: ['ecx', 'r8d', 'rbp+0x1880:4', 'rbp+0x119c:4'],           # call 0x11ffde0 (受入 1)
    0x1319f66: ['rcx', 'rdx', 'r8', 'r9'],                                # call 0x9636a0 (受入 2)
    0x131c40c: ['rcx', 'rdx', 'r8', 'r9', 'rdx*:4', 'r8*:4'],            # call 0xe4e970 (受入 3)
    0x1321be8: ['rcx', 'rdx', 'r8', 'r9'],                                # call 0xed6780 (受入 3)
    0x1321a1b: ['rcx', 'rdx', 'r8', 'r9', 'rbp+0x111c:2', 'rbp+0x111a:2'],  # call 0x11d06e0 (受入 4)
    # #3986: REPORT_DISPATCHER_APPENDIX_3673.md §2 の書込み元 VA (書込み直前の値)
    0x41d919: ['rdi', 'r8', 'rbp+0x30:8'],                                 # G18 = rdi (0x18)
    0x11fc2b3: ['rax', 'rbp+0x170:8'],                                     # P45 = rax (0x45)
    0x9dec3f: ['rax', 'rcx', 'rdx'],                                       # P56 = rax (0x56)
    0x13226dd: ['rbp+0x1880:4'],                                           # 0x54 の index
    0x1322a07: ['rbp+0x1880:4'],                                           # 0x65 の経路 (値の観測)
    0x1322b47: ['rbp+0x109c:4', 'rbp+0x1168:8'],                           # 0x65 の movsxd 直前
}


def _read(uc, spec, regs_only=False):
    """spec: 'rcx' / 'ecx' / 'r8d' (32bit 下位) / 'rbp+0x1880:4' (rbp 相対メモリ) / 'rdx*:4' (rdx の指す先)。"""
    if '+' in spec and ':' in spec:
        base, rest = spec.split('+', 1)
        off, size = rest.split(':')
        addr = uc.reg_read(REG[base]) + int(off, 16)
        return int.from_bytes(uc.mem_read(addr, int(size)), 'little')
    if '*' in spec:
        base = spec.split('*')[0]
        size = int(spec.split(':')[1]) if ':' in spec else 4
        return int.from_bytes(uc.mem_read(uc.reg_read(REG[base]), size), 'little')
    if spec in ('ecx', 'edx', 'r8d', 'r9d'):
        full = {'ecx': 'rcx', 'edx': 'rdx', 'r8d': 'r8', 'r9d': 'r9'}[spec]
        return uc.reg_read(REG[full]) & 0xffffffff
    return uc.reg_read(REG[spec])


def emulate(entry, regs, allowed, probes=None, ret_spec=None, stop_at=None, mem_init=None, sent_ret=E.SENT, fill=None):
    """entry から実行し sent_ret (戻り番地) に達するまで。allowed は [(lo,hi)] の実行許可範囲。
    範囲外への入りは stub (戻り値 ret_spec.get(va, 0)) として戻す。probes: {va: [spec,...]}。"""
    probes = probes or {}
    ret_spec = ret_spec or {}
    if not _IMG:
        data = open(E.PE_PATH, 'rb').read()
        pe, base, size = E.load_image(data)
        _IMG.update(data=data, pe=pe, base=base, size=size)
    data, pe, base, size = _IMG['data'], _IMG['pe'], _IMG['base'], _IMG['size']
    uc = Uc(UC_ARCH_X86, UC_MODE_64)
    uc.mem_map(base, size, UC_PROT_ALL)
    uc.mem_write(base, data[:pe.OPTIONAL_HEADER.SizeOfHeaders])
    for s in pe.sections:
        uc.mem_write(base + s.VirtualAddress, s.get_data())
    uc.mem_map(E.HOST, 0x10000, UC_PROT_ALL)
    uc.mem_map(E.STACK_BASE, E.STACK_SIZE, UC_PROT_ALL)
    uc.mem_map(E.SENT & ~(PAGE - 1), PAGE, UC_PROT_ALL)
    uc.mem_write(E.SENT, b'\xf4')
    if fill is not None:
        uc.mem_write(E.STACK_BASE, bytes([fill]) * E.STACK_SIZE)
    for va, raw in (mem_init or []):
        uc.mem_write(va, raw)

    st = {'steps': 0, 'stop': None, 'path': [], 'callouts': [], 'probe': [], 'unmapped': 0}

    def on_code(uc_, addr, sz, _):
        st['steps'] += 1
        if st['steps'] > MAX_STEPS:
            st['stop'] = 'step上限'
            uc_.emu_stop()
            return
        if addr == sent_ret:
            st['stop'] = 'return'
            uc_.emu_stop()
            return
        if addr in probes:
            st['probe'].append((addr, {s: _read(uc_, s) for s in probes[addr]}))
        if stop_at is not None and addr == stop_at:
            st['stop'] = 'stop_at'
            uc_.emu_stop()
            return
        if not any(lo <= addr < hi for lo, hi in allowed):
            sp = uc_.reg_read(UC_X86_REG_RSP)
            ret = int.from_bytes(uc_.mem_read(sp, 8), 'little')
            st['callouts'].append('0x%x' % addr)
            uc_.reg_write(UC_X86_REG_RAX, ret_spec.get(addr, 0))
            uc_.reg_write(UC_X86_REG_RSP, sp + 8)
            uc_.reg_write(UC_X86_REG_RIP, ret)
            return
        st['path'].append(addr)

    def on_unmapped(uc_, access, addr, sz, val, _):
        st['unmapped'] += 1
        if st['unmapped'] > 2000:
            return False
        page = addr & ~(PAGE - 1)
        try:
            uc_.mem_map(page, PAGE, UC_PROT_ALL)
            uc_.mem_write(page, b'\x00' * PAGE)
        except Exception:
            return False
        return True

    uc.hook_add(UC_HOOK_CODE, on_code, begin=base, end=base + size - 1)
    uc.hook_add(UC_HOOK_MEM_UNMAPPED, on_unmapped)
    sp = E.STACK_TOP
    sp -= 8
    uc.mem_write(sp, sent_ret.to_bytes(8, 'little'))
    uc.reg_write(UC_X86_REG_RSP, sp)
    uc.reg_write(UC_X86_REG_RBP, sp)
    for name, val in regs.items():
        uc.reg_write(REG[name], val)
    uc.reg_write(UC_X86_REG_RAX, 0)
    try:
        uc.emu_start(entry, sent_ret, timeout=0, count=MAX_STEPS + 10)
    except Exception as e:
        st['stop'] = 'exception: %s' % e
    return {'rax': uc.reg_read(UC_X86_REG_RAX), 'stop': st['stop'] or 'ended', 'path': st['path'],
            'callouts': st['callouts'], 'probe': st['probe'], 'unmapped': st['unmapped'], 'uc': uc}


def disp_probe(ids):
    """Dispatcher を ID ごとに実行し、観測点の値と到達を出す。"""
    rows = {}
    lo, hi = E.FN_LO, E.FN_HI
    if os.environ.get('HS_ALLOW_LO') and os.environ.get('HS_ALLOW_HI'):
        lo, hi = int(os.environ['HS_ALLOW_LO'], 0), int(os.environ['HS_ALLOW_HI'], 0)
    for ident in ids:
        r = emulate(E.DISP, {'rcx': E.HOST, 'rdx': E.TAG, 'r8': ident, 'r9': 0}, [(lo, hi)],
                    probes=DISP_PROBES, sent_ret=E.SENT, fill=FILL)
        rows[ident] = r
        hits = [(va, vals) for va, vals in r['probe']]
        print('ID=0x%02x rax=0x%x stop=%s path=%d hits=%s' % (
            ident, r['rax'], r['stop'], len(r['path']),
            ' '.join('0x%x%s' % (va, '' if not vals else '{' + ','.join('%s=0x%x' % kv for kv in vals.items()) + '}')
                     for va, vals in hits) or '-'))
    return rows


def isolate(entry, args, allowed, probes=None, ret_spec=None, mem_init=None):
    r = emulate(entry, args, allowed, probes=probes, ret_spec=ret_spec, mem_init=mem_init)
    return r


def _parse_args(s):
    out = {}
    for item in filter(None, s.split(',')):
        k, v = item.split('=')
        out[k] = int(v, 0)
    return out


def sweep_11ffde0(ecxs, r8d=0x8000):
    """0x1318e3e の call 0x11ffde0 を ecx (switch 値) ごとに単独実行する (受入 1)。戻り値と最後に通った 3 VA を出す。"""
    lo, hi = 0x11ffde0, 0x120010a
    out = []
    for v in ecxs:
        r = isolate(lo, {'rcx': v, 'r8': r8d}, [(lo, hi)])
        out.append((v, r['rax'] & 0xffffffff, r['path'][-3:], r['callouts']))
        print('ecx=0x%x r8d=0x%x -> eax=0x%x (signed %d) last=%s callouts=%s' % (
            v, r8d, r['rax'] & 0xffffffff, (r['rax'] & 0xffffffff) - (1 << 32) if r['rax'] & 0x80000000 else r['rax'] & 0xffffffff,
            ','.join('0x%x' % a for a in r['path'][-3:]) or '-', ','.join(r['callouts']) or '-'))
    return out


def verify_e4e970():
    """0xe4e970 を実際に実行し (0xe4ed50 も許可)、オブジェクトのフィールドを変えて戻り値と出力を予測式と照合する (受入 3)。
    予測: bool = (a78!=5 かつ a18!=5 (= e4ed50 が 0)) かつ d78>=0 (flags=1 の場合)。出力は d74/d78 の書き込みのみ。"""
    lo, hi = 0xe4e970, 0xe4e9ef
    lo2, hi2 = 0xe4ed50, 0xe4ed69
    obj = E.HOST + 0x1000
    out_p, out_q = E.HOST + 0x2000, E.HOST + 0x2010
    mism = 0
    rows = []
    for a78 in (5, 0):
        for a18 in (5, 0):
            for d78 in (-1, 0, 1):
                fields = {0xa78: a78, 0xa18: a18, 0xd78: d78 & 0xffffffff, 0xd74: 0x1234, 0xb1c: 0x77}
                mem = []
                for off, val in fields.items():
                    mem.append((obj + off, (val & 0xffffffff).to_bytes(4, 'little')))
                mem.append((out_p, (0xdead).to_bytes(4, 'little')))
                mem.append((out_q, (0xbeef).to_bytes(4, 'little')))
                for flags in (1, 2, 4):
                    mem2 = mem + [(out_p, (0xdead).to_bytes(4, 'little')), (out_q, (0xbeef).to_bytes(4, 'little'))]
                    r = isolate(lo, {'rcx': obj, 'rdx': out_p, 'r8': out_q, 'r9': flags}, [(lo, hi), (lo2, hi2)], mem_init=mem2)
                    p = int.from_bytes(r['uc'].mem_read(out_p, 4), 'little')
                    q = int.from_bytes(r['uc'].mem_read(out_q, 4), 'little')
                    pred_true = (a78 != 5 and a18 != 5 and d78 >= 0)
                    pred_bool = 1 if pred_true else (0 if flags not in (2, 4) else None)
                    got = r['rax'] & 0xff
                    rows.append((a78, a18, d78, flags, got, p, q, r['callouts']))
                    print('a78=%d a18=%d d78=%d flags=%d -> al=%d out_p=0x%x out_q=0x%x (expect %s) callouts=%s' % (
                        a78, a18, d78, flags, got, p, q & 0xffffffff, ('al=%d' % pred_bool) if pred_bool is not None else 'al=(e4ed50==0)', ','.join(r['callouts']) or '-'))
                    if flags == 1 and got != (1 if pred_true else 0):
                        mism += 1
    print('verify flags=1 mismatches = %d' % mism)
    return rows


def verify_11d06e0():
    """0x11d06e0 (out word = [rbx]) を単独実行する。callee (0x11cf880・0x11c8ba0・0x11829e0) は stub (戻り値 0)。
    出力 word の初期値 0 / 0x60 / 0x5 で最終値を見る (受入 4)。書込みは word を 0 にする分岐だけのはず。"""
    lo, hi = 0x11d06e0, 0x11d073b
    word_addr = E.HOST + 0x3000
    rows = []
    for w in (0x0, 0x60, 0x5):
        r = isolate(lo, {'rcx': E.HOST, 'rdx': 0, 'r8': word_addr, 'r9': 0},
                    [(lo, hi)], mem_init=[(word_addr, w.to_bytes(2, 'little'))])
        final = int.from_bytes(r['uc'].mem_read(word_addr, 2), 'little')
        rows.append((w, final))
        print('word_in=0x%x -> word_out=0x%x (judge sete=%d) last=%s callouts=%s' % (
            w, final, 1 if final == 0 else 0, ','.join('0x%x' % a for a in r['path'][-3:]), ','.join(r['callouts']) or '-'))
    return rows


def g18_caller():
    """0x41d8f0 (G18 の書込み関数) を r9=1・r9=0 で単独実行し、0x41d919 (mov [G18], rdi) の到達と書込み直前の値を出す (受入 1)。
    rdi は 0x41d8ff で r8 から複写されるため、観測は r8 (= ID) で行う。"""
    rows = []
    for r9 in (1, 0):
        for ident in (0x18, 0x45, 0x54, 0x56, 0x64, 0x65):
            r = emulate(0x41d8f0, {'rcx': E.HOST, 'rdx': E.TAG, 'r8': ident, 'r9': r9}, [(0x41d8f0, 0x41d8f0 + 0x200)],
                        probes={0x41d919: ['r8', 'rcx']}, sent_ret=E.SENT)
            hit = [vals for va, vals in r['probe'] if va == 0x41d919]
            print('G18 caller: r9=%d ID=0x%02x 0x41d919 %s rax=0x%x stop=%s' % (
                r9, ident, ('reached r8=0x%x' % hit[0]['r8']) if hit else 'NOT reached', r['rax'], r['stop']))
            rows.append((r9, ident, bool(hit)))
    return rows


def p45_caller():
    """0x11fba90 (P45 の書込み関数) を this=HOST・[this+0x34a8]=0 で単独実行する (受入 1)。
    0x11fbb4f の分岐 (eax==0xb) に届くには [[rbp+0x140]+0x10] の前提が要る。現状は 0x11fbaef までしか届かず未確定。"""
    this = E.HOST
    r = emulate(0x11fba90, {'rcx': this, 'rdx': 0, 'r8': 0x45, 'r9': 0}, [(0x11fba90, 0x11fba90 + 0x1000)],
                probes={0x11fbaef: ['rcx'], 0x11fbb4f: ['rbp+0x140:8'], 0x11fc2b3: ['rax', 'rbp+0x170:8']},
                sent_ret=E.SENT, mem_init=[(this + 0x34a8, (0).to_bytes(4, 'little'))])
    print('P45 caller: rax=0x%x stop=%s 0x11fbaef=%s 0x11fbb4f=%s 0x11fc2b3=%s' % (
        r['rax'], r['stop'],
        any(va == 0x11fbaef for va, _ in r['probe']),
        any(va == 0x11fbb4f for va, _ in r['probe']),
        any(va == 0x11fc2b3 for va, _ in r['probe'])))
    return r


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'disp'
    if mode == 'disp':
        ids = [int(a, 0) for a in sys.argv[2:]] or list(range(256))
        disp_probe(ids)
    elif mode == 'fn':
        entry = int(sys.argv[2], 0)
        hi = int(sys.argv[3], 0)
        args = _parse_args(sys.argv[4])
        r = isolate(entry, args, [(entry, hi)])
        print('rax=0x%x stop=%s steps=%d last=%s callouts=%s' % (r['rax'], r['stop'], len(r['path']),
              ','.join('0x%x' % a for a in r['path'][-3:]), ','.join(r['callouts']) or '-'))
    elif mode == 'sweep11ffde0':
        sweep_11ffde0([int(a, 0) for a in sys.argv[2:]] or [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 0x7fff, 0xffffffff])
    elif mode == 'verify':
        verify_e4e970()
    elif mode == 'word41':
        verify_11d06e0()
    elif mode == 'g18caller':
        g18_caller()
    elif mode == 'p45caller':
        p45_caller()
    else:
        raise SystemExit('unknown mode %s' % mode)
