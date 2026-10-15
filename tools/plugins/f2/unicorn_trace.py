#!/usr/bin/env python3
# PLG-F3-21 (#1807 子 A): block PE を preferred base に展開し、関数を unicorn で実行して
# 呼出し後の値と、監視範囲への書込み元 (rip) を記録する。
# IAT の各 slot は ret だけの stub に向け、呼ばれた import 名を数える (戻り値 rax=0)。
# gs:[0x58] は TLS 配列 (0x1000 の zero 配列) を指す。
# 依存: pefile・unicorn (pip install unicorn)。未解決の間接 call で止まる場合は fault 行に戻り番地を出す。
# usage: python3 unicorn_trace.py <block_PE.bin> <entry_hex> [-r reg=hex ...] [-a hex ...]
#                                 [-w lo:hi ...] [-q hex ...] [-m MAX_INSN]
#                                 [-d addr=val ...] [-t hex ...] [-p hex[:reg=val,...] ...] [-H] [-V] [-z]
#   -p: 本体の前に同じメモリ上で順に実行する関数 (arena 初期化・DllMain)。-V: VirtualAlloc を合成メモリで返す。
#   -d: 実行前に qword を書く (ホスト構造体の合成用)。-t: 番地に入るたびに rcx/rdx/r8/r9 を出す。
import argparse
import collections
import struct

import pefile
import unicorn
from unicorn import (Uc, UcError, UC_ARCH_X86, UC_MODE_64, UC_PROT_ALL, UC_PROT_READ,
                     UC_PROT_WRITE, UC_HOOK_CODE, UC_HOOK_MEM_WRITE, UC_HOOK_MEM_READ)
from unicorn.x86_const import (UC_X86_REG_RAX, UC_X86_REG_RBP, UC_X86_REG_RCX, UC_X86_REG_RDX,
                               UC_X86_REG_RSP, UC_X86_REG_RIP)

PAGE = 0x1000
STUB = 0x10000000
STUB_SIZE = 0x100000
STACK_TOP = 0x30100000
STACK_SIZE = 0x100000
SENT = 0x20000000
SCRATCH = 0x40000000
SCRATCH_SIZE = 0x100000
POOL = 0x50000000
POOL_SIZE = 0x8000000
LOG_LIMIT = 200


def align(x):
    return (x + PAGE - 1) & ~(PAGE - 1)


def reg_id(name):
    return getattr(unicorn.x86_const, 'UC_X86_REG_' + name.upper())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pe')
    ap.add_argument('entry', type=lambda s: int(s, 0))
    ap.add_argument('-r', action='append', default=[], help='初期レジスタ reg=hex')
    ap.add_argument('-a', action='append', default=[], type=lambda s: int(s, 0),
                    help='5 番目以降の引数 (stack)')
    ap.add_argument('-w', action='append', default=[], help='書込み監視範囲 lo:hi (hex)')
    ap.add_argument('-q', action='append', default=[], type=lambda s: int(s, 0),
                    help='実行前後に表示する qword アドレス')
    ap.add_argument('-R', action='append', default=[], help='読取り監視範囲 lo:hi (hex)。読んだ命令 (rip) ごとに件数を出す')
    ap.add_argument('-S', action='store_true',
                    help='user32!LoadStringW を PE の .rsrc (RT_STRING) から返す (uID の block は (uID>>4)+1、16 件ずつ。戻り値は文字数。無いと 0)。kernel32!GetLocalTime は 2026-10-14 を書く (全 0 だと Delphi が時刻の例外を投げる)')
    ap.add_argument('-m', type=int, default=2000000, help='最大命令数')
    ap.add_argument('-d', action='append', default=[], help='実行前に書く qword addr=val (hex)')
    ap.add_argument('-t', action='append', default=[], type=lambda s: int(s, 0),
                    help='この VA に入ったとき rcx/rdx の値と [rcx]・[rcx+0x28]・[[rcx]+0x28]・rax・rbp・[rax+0x28] を出す (最初の 20 回)')
    ap.add_argument('-p', action='append', default=[],
                    help='本体の前に同じメモリ上で順に実行する関数 hex (arena 初期化等。rcx/rdx は -H の host)。'
                         'hex:reg=val,... で、その前処理だけ初期レジスタを与える (DllMain の reason=rdx=1 等)')
    ap.add_argument('-V', action='store_true',
                    help='kernel32!VirtualAlloc と kernel32!LocalAlloc が 64KB 境界で POOL (0x50000000〜) の領域を返す (size=rdx。pool 超過は error を出して 0)。LocalAlloc を 0 で返すと DllMain の attach が 0xe2 の致命エラーで longjmp する (#2574)')
    ap.add_argument('-H', action='store_true',
                    help='合成 host: rcx を SCRATCH+0x10000 の host に向け、[host]=vtable (0x40 スロット、全て ret stub)')
    ap.add_argument('-z', action='store_true',
                    help='page 0 (NULL 付近) を読取専用にする。NULL this への書込みを UC_ERR_WRITE_PROT で止める (既定は RW のまま)')
    a = ap.parse_args()

    data = open(a.pe, 'rb').read()
    pe = pefile.PE(a.pe)
    ib = pe.OPTIONAL_HEADER.ImageBase
    uc = Uc(UC_ARCH_X86, UC_MODE_64)
    uc.mem_map(ib, align(pe.OPTIONAL_HEADER.SizeOfImage), UC_PROT_ALL)
    uc.mem_write(ib, data[:pe.OPTIONAL_HEADER.SizeOfHeaders])
    for s in pe.sections:
        n = min(s.SizeOfRawData, s.Misc_VirtualSize)
        if n:
            uc.mem_write(ib + s.VirtualAddress, data[s.PointerToRawData:s.PointerToRawData + n])

    # gs:[0x58] -> TLS 配列 (gs base = 0 のため、アドレス 0x58 を直接読む)
    uc.mem_map(0, 0x2000, UC_PROT_READ | UC_PROT_WRITE)
    uc.mem_write(0x58, struct.pack('<Q', 0x1000))
    if a.z:
        uc.mem_protect(0, PAGE, UC_PROT_READ)

    names = {}
    k = 0
    uc.mem_map(STUB, STUB_SIZE, UC_PROT_ALL)
    for ent in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []) + getattr(pe, 'DIRECTORY_ENTRY_DELAY_IMPORT', []):
        for imp in ent.imports:
            nm = imp.name.decode() if imp.name else 'ord%d' % imp.ordinal
            sva = STUB + 16 * k
            k += 1
            uc.mem_write(sva, b'\xc3')
            names[sva] = '%s!%s' % (ent.dll.decode(), nm)
            uc.mem_write(imp.address, struct.pack('<Q', sva))

    uc.mem_map(SCRATCH, SCRATCH_SIZE, UC_PROT_READ | UC_PROT_WRITE)
    uc.mem_map(STACK_TOP - STACK_SIZE, STACK_SIZE, UC_PROT_READ | UC_PROT_WRITE)
    RET_STUB = STUB + STUB_SIZE - 0x10
    uc.mem_write(RET_STUB, b'\xc3')
    print('ret stub %#x (-d の vtable 先に使える)' % RET_STUB)
    for item in a.d:
        ad, val = item.split('=')
        uc.mem_write(int(ad, 0), struct.pack('<Q', int(val, 0)))
    uc.mem_map(SENT & ~(PAGE - 1), PAGE, UC_PROT_READ)
    pool = [POOL]
    if a.V:
        uc.mem_map(POOL, POOL_SIZE, UC_PROT_ALL)
    host = SCRATCH + 0x10000
    rets = {}
    if a.H:
        vtab = SCRATCH + 0x11000
        obj = SCRATCH + 0x12000
        otab = SCRATCH + 0x13000
        uc.mem_write(host, struct.pack('<Q', vtab))
        uc.mem_write(obj, struct.pack('<Q', otab))
        for base, tab, nm in ((host, vtab, 'host'), (obj, otab, 'obj')):
            for i in range(0x40):
                sva = STUB + 16 * (k + i + (0 if nm == 'host' else 0x40))
                uc.mem_write(sva, b'\xc3')
                names[sva] = '%s.vtable[%#x]' % (nm, 8 * i)
                uc.mem_write(tab + 8 * i, struct.pack('<Q', sva))
                if nm == 'host' and i == 0:
                    rets[sva] = obj

    strings = {}
    if a.S:
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_RESOURCE']])
        for t in pe.DIRECTORY_ENTRY_RESOURCE.entries:
            if t.id != 6:
                continue
            for b in t.directory.entries:
                ent = b.directory.entries[0].data.struct
                d = pe.get_data(ent.OffsetToData, ent.Size)
                pos = 0
                for i in range(16):
                    n = struct.unpack_from('<H', d, pos)[0]
                    pos += 2
                    if n:
                        strings[(b.id - 1) * 16 + i] = d[pos:pos + 2 * n].decode('utf-16-le')
                        pos += 2 * n
        print('rsrc strings: %d' % len(strings))

    hits = {}
    log = []

    tail = collections.deque(maxlen=12)

    tcount = collections.Counter()

    def on_code(uc_, addr, size, ud):
        tail.append(addr)
        if addr in a.t and tcount[addr] < 20:
            tcount[addr] += 1
            rcx = uc_.reg_read(UC_X86_REG_RCX)
            info = 'trace %#x #%d rcx=%#x rdx=%#x' % (addr, tcount[addr], rcx, uc_.reg_read(UC_X86_REG_RDX))
            try:
                info += ' [rcx]=%#x [rcx+0x28]=%#x' % (
                    struct.unpack('<Q', uc_.mem_read(rcx, 8))[0],
                    struct.unpack('<Q', uc_.mem_read(rcx + 0x28, 8))[0])
            except UcError:
                info += ' (rcx 未マップ)'
            try:
                info += ' [[rcx]+0x28]=%#x' % struct.unpack('<Q', uc_.mem_read(
                    struct.unpack('<Q', uc_.mem_read(rcx, 8))[0] + 0x28, 8))[0]
            except UcError:
                info += ' ([[rcx]+0x28] 未マップ)'
            rax = uc_.reg_read(UC_X86_REG_RAX)
            info += ' rax=%#x rbp=%#x' % (rax, uc_.reg_read(UC_X86_REG_RBP))
            try:
                info += ' [rax+0x28]=%#x' % struct.unpack('<Q', uc_.mem_read(rax + 0x28, 8))[0]
            except UcError:
                info += ' ([rax+0x28] 未マップ)'
            print(info)
        if addr in names:
            hits[names[addr]] = hits.get(names[addr], 0) + 1
            if a.V and names[addr].lower() in ('kernel32.dll!virtualalloc', 'kernel32.dll!localalloc'):
                size = uc_.reg_read(UC_X86_REG_RDX)
                need = (size + 0xffff) & ~0xffff
                if pool[0] + need > POOL + POOL_SIZE:
                    print('error: %s size=%#x は pool の残り %#x を超える (戻り 0)' % (
                        names[addr], size, POOL + POOL_SIZE - pool[0]))
                    uc_.reg_write(UC_X86_REG_RAX, 0)
                else:
                    uc_.reg_write(UC_X86_REG_RAX, pool[0])
                    pool[0] += need
            elif a.S and names[addr].lower() == 'kernel32.dll!getlocaltime':
                uc_.mem_write(uc_.reg_read(UC_X86_REG_RCX), struct.pack('<8H', 2026, 10, 3, 14, 0, 0, 0, 0))
            elif a.S and names[addr].lower() == 'user32.dll!loadstringw':
                uid = uc_.reg_read(UC_X86_REG_RDX)
                buf = uc_.reg_read(unicorn.x86_const.UC_X86_REG_R8)
                cch = uc_.reg_read(unicorn.x86_const.UC_X86_REG_R9)
                s = strings.get(uid, '')
                w = s[:max(cch - 1, 0)]
                if s and cch:
                    uc_.mem_write(buf, w.encode('utf-16-le') + b'\0\0')
                uc_.reg_write(UC_X86_REG_RAX, len(w) if s else 0)
            else:
                uc_.reg_write(UC_X86_REG_RAX, rets.get(addr, 0))

    def on_write(uc_, access, addr, size, value, ud):
        if len(log) < LOG_LIMIT:
            rip = uc_.reg_read(UC_X86_REG_RIP)
            log.append('  write %#x size=%d val=%#x rip=%#x' % (addr, size, value, rip))

    rreads = collections.Counter()
    rfirst = {}

    def on_read(uc_, access, addr, size, value, ud):
        rip = uc_.reg_read(UC_X86_REG_RIP)
        rreads[rip] += 1
        rfirst.setdefault(rip, addr)

    uc.hook_add(UC_HOOK_CODE, on_code)
    for item in a.w:
        lo, hi = item.split(':')
        uc.hook_add(UC_HOOK_MEM_WRITE, on_write, begin=int(lo, 16), end=int(hi, 16) - 1)
    for item in a.R:
        lo, hi = item.split(':')
        uc.hook_add(UC_HOOK_MEM_READ, on_read, begin=int(lo, 16), end=int(hi, 16) - 1)

    for q in a.q:
        print('before [%#x] = %#x' % (q, struct.unpack('<Q', uc.mem_read(q, 8))[0]))

    def enter(fn, final, regs=()):
        rsp = STACK_TOP - 0x208
        uc.mem_write(rsp, struct.pack('<Q', SENT))
        if final:
            for i, v in enumerate(a.a):
                uc.mem_write(rsp + 0x28 + 8 * i, struct.pack('<Q', v))
        uc.reg_write(UC_X86_REG_RSP, rsp)
        if a.H:
            uc.reg_write(UC_X86_REG_RCX, host)
            uc.reg_write(UC_X86_REG_RDX, host)
        for item in (a.r if final else regs):
            name, val = item.split('=')
            uc.reg_write(reg_id(name), int(val, 0))
        st = 'returned to sentinel'
        try:
            uc.emu_start(fn, SENT, count=a.m)
        except UcError as e:
            st = 'UcError %s' % e
        return st

    for item in a.p:
        p, _, regs = item.partition(':')
        p = int(p, 0)
        st = enter(p, False, [r for r in regs.split(',') if r])
        print('prelude %#x: %s rip=%#x rax=%#x' % (p, st, uc.reg_read(UC_X86_REG_RIP),
                                                  uc.reg_read(UC_X86_REG_RAX)))
    status = enter(a.entry, True)
    rip = uc.reg_read(UC_X86_REG_RIP)
    print('status: %s rip=%#x rax=%#x' % (status, rip, uc.reg_read(UC_X86_REG_RAX)))
    if rip != SENT:
        ret = struct.unpack('<Q', uc.mem_read(uc.reg_read(UC_X86_REG_RSP), 8))[0]
        print('fault: [rsp]=%#x (呼出し元の戻り番地。間接 call なら呼出し先が 0 の可能性)' % ret)
        print('last executed: ' + ' '.join('%#x' % x for x in tail))
    for q in a.q:
        print('after  [%#x] = %#x' % (q, struct.unpack('<Q', uc.mem_read(q, 8))[0]))
    print('stub hits (%d distinct):' % len(hits))
    for nm, c in sorted(hits.items(), key=lambda kv: -kv[1]):
        print('  %6d %s' % (c, nm))
    print('watch writes (%d shown):' % len(log))
    for line in log:
        print(line)
    if a.R:
        print('watch reads (%d rip, %d reads):' % (len(rreads), sum(rreads.values())))
        for rip, c in sorted(rreads.items()):
            print('  rip=%#x reads=%d first addr=%#x' % (rip, c, rfirst[rip]))


if __name__ == '__main__':
    main()
