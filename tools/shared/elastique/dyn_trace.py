#!/usr/bin/env python3
"""élastique_x64.dll を unicorn で実行し、call/jmp の実行時の宛先を記録する (T-SH-42 / #2643)。

入力 (既定):
  ELASTIQUE_DLL = tools/shared/work/win/elastique_x64.dll (FL 素材 block24357_PE.bin の複製)
  entries.csv   = tools/shared/elastique/data/entries.csv (IPPCODE の入口 197)
実行: DllMain (DLL_PROCESS_ATTACH) → ElAllocator_SetFunctions → export 15 件を、合成引数 2 通りで呼ぶ。
  kernel32 の Heap 系は bump 割当で実装し、他の import は戻り値 0 の stub。実 FL のホスト構造体・音声入力は使わない。
記録: 分岐元が call/jmp (直接・間接とも) の命令の次に実行された命令番地を宛先とし、(分岐元, 宛先) を数える。
  宛先の分類: ipp_entry (入口 197) / ipp_other (IPPCODE の他) / text / iat_stub / host_stub / unmapped / other。
出力: tools/shared/work/elastique/dyn/ (gitignore) に全 edge・run 一覧・サマリ。
  tools/shared/elastique/data/runtime_indirect.csv に間接 edge のみ (コミット対象)。
依存: pefile・unicorn・capstone (tools/shared/work/venv)。
"""
import csv
import json
import os
import struct
import sys
import time

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM
from unicorn import (Uc, UcError, UC_ARCH_X86, UC_MODE_64, UC_PROT_ALL, UC_PROT_READ, UC_PROT_WRITE,
                     UC_HOOK_CODE, UC_HOOK_MEM_READ)
from unicorn.x86_const import (UC_X86_REG_RAX, UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8,
                               UC_X86_REG_R9, UC_X86_REG_RSP, UC_X86_REG_RIP)

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, '..', 'work', 'elastique', 'dyn')
DLL = os.environ.get('ELASTIQUE_DLL', os.path.join(HERE, '..', 'work', 'win', 'elastique_x64.dll'))
ENTRIES = os.environ.get('DYN_ENTRIES', os.path.join(HERE, 'data', 'entries.csv'))
OUT_CSV = os.path.join(HERE, 'data', 'runtime_indirect.csv')
PAGE = 0x1000
STUB = 0x10000000
STUB_SIZE = 0x100000
STACK_TOP = 0x30100000
STACK_SIZE = 0x100000
SENT = 0x20000000
SCRATCH = 0x40000000
SCRATCH_SIZE = 0x100000
POOL = 0x50000000
POOL_SIZE = 0x4000000
COUNT = int(os.environ.get('DYN_COUNT', '3000000'))
COUNT_EXTRA = int(os.environ.get('DYN_COUNT_EXTRA', '1000000'))
ENTRY_INIT = 0x1803E71B0


def align(x):
    return (x + PAGE - 1) & ~(PAGE - 1)


def main():
    pe = pefile.PE(DLL)
    ib = pe.OPTIONAL_HEADER.ImageBase
    isz = align(pe.OPTIONAL_HEADER.SizeOfImage)
    secs = {s.Name.rstrip(b'\0').decode(errors='replace'): s for s in pe.sections}
    ranges = {}
    for k, n in (('ipp', 'IPPCODE'), ('text', '.text')):
        lo = ib + secs[n].VirtualAddress
        ranges[k] = (lo, lo + secs[n].Misc_VirtualSize)
    entries = set()
    with open(ENTRIES) as f:
        for row in csv.DictReader(f):
            entries.add(int(row['entry_va'], 16))
    data = open(DLL, 'rb').read()

    uc = Uc(UC_ARCH_X86, UC_MODE_64)
    uc.mem_map(ib, isz, UC_PROT_ALL)
    uc.mem_write(ib, data[:pe.OPTIONAL_HEADER.SizeOfHeaders])
    for s in pe.sections:
        n = min(s.SizeOfRawData, s.Misc_VirtualSize)
        if n:
            uc.mem_write(ib + s.VirtualAddress, data[s.PointerToRawData:s.PointerToRawData + n])
    uc.mem_map(0, 0x2000, UC_PROT_READ | UC_PROT_WRITE)
    uc.mem_write(0x58, struct.pack('<Q', 0x1000))
    uc.mem_map(STUB, STUB_SIZE, UC_PROT_ALL)
    uc.mem_map(SENT & ~(PAGE - 1), PAGE, UC_PROT_ALL)
    uc.mem_map(SCRATCH, SCRATCH_SIZE, UC_PROT_READ | UC_PROT_WRITE)
    uc.mem_map(POOL, POOL_SIZE, UC_PROT_READ | UC_PROT_WRITE)
    uc.mem_map(STACK_TOP - STACK_SIZE, STACK_SIZE, UC_PROT_READ | UC_PROT_WRITE)

    bump = [POOL]
    sizes = {}

    def alloc(size):
        size = max(size, 16)
        p = bump[0]
        if p + size > POOL + POOL_SIZE:
            return 0
        bump[0] += (size + 15) & ~15
        sizes[p] = size
        return p

    def rax(v):
        uc.reg_write(UC_X86_REG_RAX, v & 0xFFFFFFFFFFFFFFFF)

    def h_alloc(u):
        rax(alloc(u.reg_read(UC_X86_REG_RCX)))

    def h_free(u):
        rax(0)

    def h_heap_alloc(u):
        rax(alloc(u.reg_read(UC_X86_REG_R8)))

    def h_heap_realloc(u):
        old = u.reg_read(UC_X86_REG_R8)
        size = u.reg_read(UC_X86_REG_R9)
        p = alloc(size)
        if old and p:
            n = min(sizes.get(old, 0), size)
            if n:
                u.mem_write(p, bytes(u.mem_read(old, n)))
        rax(p)

    def h_heap_size(u):
        rax(sizes.get(u.reg_read(UC_X86_REG_R8), 0))

    def h_ret1(u):
        rax(1)

    def h_ntohl(u):
        v = u.reg_read(UC_X86_REG_RCX) & 0xFFFFFFFF
        rax(int.from_bytes(v.to_bytes(4, 'little'), 'big'))

    def h_module(u):
        rax(ib)

    def h_heap(u):
        rax(0x7000)

    by_name = {
        'HeapAlloc': h_heap_alloc, 'HeapReAlloc': h_heap_realloc, 'HeapSize': h_heap_size,
        'HeapFree': h_ret1, 'GetProcessHeap': h_heap, 'ntohl': h_ntohl, 'htonl': h_ntohl,
        'GetModuleHandleW': h_module,
    }
    handlers = {}
    names = {}
    k = 0
    for ent in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
        for imp in ent.imports:
            nm = imp.name.decode() if imp.name else 'ord%d' % imp.ordinal
            sva = STUB + 16 * k
            k += 1
            uc.mem_write(sva, b'\xc3')
            names[sva] = '%s!%s' % (ent.dll.decode(), nm)
            if nm in by_name:
                handlers[sva] = by_name[nm]
            uc.mem_write(imp.address, struct.pack('<Q', sva))
    host = {}
    for nm, fn in (('host.malloc', h_alloc), ('host.free', h_free)):
        sva = STUB + 16 * k
        k += 1
        uc.mem_write(sva, b'\xc3')
        names[sva] = nm
        handlers[sva] = fn
        host[nm] = sva

    seen_runs = []
    kcache = {}
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    edges = {}
    last = [None]
    run_label = ['-']
    ins_total = [0]
    cur_src = set()
    group_src = {}

    def decode(addr):
        code = bytes(uc.mem_read(addr, 16))
        ins = next(md.disasm(code, addr), None)
        if ins is not None and ins.mnemonic in ('call', 'jmp'):
            ind = ins.operands[0].type != X86_OP_IMM
            k_ = (True, ind, '%s %s' % (ins.mnemonic, ins.op_str))
        else:
            k_ = (False, False, '')
        kcache[addr] = k_
        return k_

    def on_insn(u, addr, size, ud):
        ins_total[0] += 1
        p = last[0]
        if p is not None:
            last[0] = None
            if kcache[p][1]:
                cur_src.add(p)
            e = edges.get((p, addr))
            if e is None:
                e = edges[(p, addr)] = [0, kcache[p][1], kcache[p][2], run_label[0]]
            e[0] += 1
        h = handlers.get(addr)
        if h is not None:
            h(u)
        k_ = kcache.get(addr)
        if k_ is None:
            k_ = decode(addr)
        if k_[0]:
            last[0] = addr

    uc.hook_add(UC_HOOK_CODE, on_insn, begin=ib, end=ib + isz - 1)
    uc.hook_add(UC_HOOK_CODE, on_insn, begin=STUB, end=STUB + STUB_SIZE - 1)

    def classify(dst):
        if dst in entries:
            return 'ipp_entry'
        if ranges['ipp'][0] <= dst < ranges['ipp'][1]:
            return 'ipp_other'
        if ranges['text'][0] <= dst < ranges['text'][1]:
            return 'text'
        if STUB <= dst < STUB + STUB_SIZE:
            return 'stub:' + names.get(dst, '?')
        return 'other'

    runs = []

    def run(label, entry, args, group='base', count=COUNT):
        run_label[0] = label
        rsp = STACK_TOP - 0x208
        uc.mem_write(rsp, struct.pack('<Q', SENT))
        uc.reg_write(UC_X86_REG_RSP, rsp)
        for r, v in zip((UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8, UC_X86_REG_R9), args):
            uc.reg_write(r, v)
        last[0] = None
        cur_src.clear()
        t0 = time.time()
        before = ins_total[0]
        status = 'returned'
        try:
            uc.emu_start(entry, SENT, count=count)
        except UcError as e:
            rip = uc.reg_read(UC_X86_REG_RIP)
            status = 'uc_error:%s' % e
            if last[0] is not None:
                p = last[0]
                last[0] = None
                ek = (p, rip)
                e2 = edges.setdefault(ek, [0, kcache[p][1], kcache[p][2], label])
                e2[0] += 1
                status += ' fault_target=%#x class=%s' % (rip, 'unmapped')
                if kcache[p][1]:
                    cur_src.add(p)
        if status == 'returned' and uc.reg_read(UC_X86_REG_RIP) != SENT:
            status = 'count_limit'
        rv = uc.reg_read(UC_X86_REG_RAX)
        group_src.setdefault(group, set()).update(cur_src)
        runs.append({'run': label, 'group': group, 'entry': '%#x' % entry,
                     'args': ' '.join('%#x' % a for a in args),
                     'status': status, 'rax': '%#x' % rv, 'insns': ins_total[0] - before,
                     'sec': round(time.time() - t0, 2)})
        print('run %-28s %-14s insns=%-9d rax=%#x sec=%.1f %s' % (
            label, status[:14], ins_total[0] - before, rv, time.time() - t0, status if len(status) > 14 else ''),
            flush=True)
        return rv

    exports = [(e.name.decode(), ib + e.address) for e in pe.DIRECTORY_ENTRY_EXPORT.symbols]
    export_va = dict(exports)
    run('DllMain', ib + pe.OPTIONAL_HEADER.AddressOfEntryPoint, (ib, 1, 0, 0))
    run('ElAllocator_SetFunctions', export_va['ElAllocator_SetFunctions'],
        (host['host.malloc'], host['host.free'], 0, 0))
    obj = SCRATCH + 0x1000
    objs = []
    for nm, va in exports:
        if nm == 'ElAllocator_SetFunctions':
            continue
        run(nm + ':zero', va, (0, 0, 0, 0))
        rv = run(nm + ':scratch', va, (obj, obj + 0x1000, 44100, 2))
        if 'CreateInstance' in nm and POOL <= rv < POOL + POOL_SIZE:
            objs.append((nm, rv))

    thunks = []
    slots = {}
    for s in pe.sections:
        if s.Name.rstrip(b'\0') not in (b'.data', b'.rdata'):
            continue
        raw = data[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
        for off in range(0, len(raw) - 7, 8):
            v = struct.unpack_from('<Q', raw, off)[0]
            if ranges['text'][0] <= v < ranges['text'][1]:
                ins = next(md.disasm(bytes(uc.mem_read(v, 16)), v), None)
                if ins is not None and ins.mnemonic == 'call' and ins.op_str == '%#x' % ENTRY_INIT:
                    thunks.append(v)
                    slots[ib + s.VirtualAddress + off] = v
    thunks = sorted(set(thunks))
    slot_readers = {}

    def on_slot_read(u, access, addr, size, value, ud):
        rip = u.reg_read(UC_X86_REG_RIP)
        for s in slots:
            if addr < s + 8 and s < addr + size:
                key = (rip, s, run_label[0])
                slot_readers[key] = slot_readers.get(key, 0) + 1

    if slots:
        uc.hook_add(UC_HOOK_MEM_READ, on_slot_read, begin=min(slots) - 16, end=max(slots) + 23)
    print('thunk heads (.data/.rdata の 8 byte 値 → call %#x で始まる): %d' % (ENTRY_INIT, len(thunks)), flush=True)
    for v in thunks:
        run('thunk:%#x' % v, v, (0, 0, 0, 0))
        run('thunk:%#x:scratch' % v, v, (obj, obj + 0x1000, 44100, 2))

    targets = [(nm, va) for nm, va in exports if nm != 'ElAllocator_SetFunctions']
    targets += [('thunk:%#x' % v, v) for v in thunks]
    for nm, va in targets:
        run(nm + ':rate48k', va, (obj, obj + 0x1000, 48000, 1), 'rate48k', COUNT_EXTRA)
    for i, (cnm, o) in enumerate(objs[:3]):
        for nm, va in targets:
            run('%s:obj%d(%s)' % (nm, i, cnm), va, (o, obj, 44100, 2), 'obj', COUNT_EXTRA)

    os.makedirs(WORK, exist_ok=True)
    with open(os.path.join(WORK, 'slot_readers.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['reader_rip', 'slot_va', 'thunk_head', 'run', 'count'])
        for (rip, addr, rl), cnt in sorted(slot_readers.items()):
            w.writerow(['%#x' % rip, '%#x' % addr, '%#x' % slots[addr], rl, cnt])
    with open(os.path.join(WORK, 'edges.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['src', 'src_insn', 'dst', 'dst_class', 'indirect', 'count', 'first_run'])
        for (src, dst), (cnt, ind, txt, rl) in sorted(edges.items()):
            w.writerow(['%#x' % src, txt, '%#x' % dst, classify(dst), int(ind), cnt, rl])
    with open(os.path.join(WORK, 'runs.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(runs[0].keys()))
        w.writeheader()
        w.writerows(runs)

    ind_edges = [(s, d, v) for (s, d), v in edges.items() if v[1]]
    ind_src = {s for s, _, _ in ind_edges}
    cls_cnt = {}
    for s, d, v in ind_edges:
        c = classify(d)
        cls_cnt[c] = cls_cnt.get(c, 0) + 1
    entries_hit = {d for _, d, _ in ind_edges if d in entries}
    all_entries_hit = {d for (s, d) in edges if d in entries}
    summary = {
        'insns_total': ins_total[0],
        'branch_edges_distinct': len(edges),
        'indirect_edges_distinct': len(ind_edges),
        'indirect_sites_executed': len(ind_src),
        'indirect_targets_distinct': len({d for _, d, _ in ind_edges}),
        'indirect_edges_by_class': cls_cnt,
        'indirect_hits_on_ipp_entries': len(entries_hit),
        'entries_hit_by_any_branch': len(all_entries_hit),
        'entries_total': len(entries),
        'thunk_heads': len(thunks),
        'thunk_slot_readers_distinct_rip': len({r for r, _, _ in slot_readers}),
        'indirect_edges_to_thunk_heads': sum(v[0] for (s_, d, v) in ind_edges if d in set(thunks)),
        'indirect_sites_by_group': {g: len(s) for g, s in sorted(group_src.items())},
        'create_instances_chained': len(objs),
    }
    with open(os.path.join(WORK, 'summary.json'), 'w') as f:
        json.dump(summary, f, indent=1)
    with open(OUT_CSV, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['src_va', 'src_insn', 'dst_va', 'dst_class', 'count', 'first_run'])
        for s, d, v in sorted(ind_edges):
            w.writerow(['%#x' % s, v[2], '%#x' % d, classify(d), v[0], v[3]])
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    sys.exit(main())
