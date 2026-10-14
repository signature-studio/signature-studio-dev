#!/usr/bin/env python3
"""hs_disp_emu.py — FLE TFruityHost.Dispatcher (0x13173a0) を ID ごとに unicorn で実行し、
応答値・到達経路・外部呼出 (関数外への call) を実測する (#986 / PLG-P0b-2)。

既存の hs_disp_tree.py は一直線の追跡で、Dispatcher が使う cmp/jcc 二分木を正しく辿れない
(間接 jmp 無し・case 本体が窓外) ため、case 確定にはこちらを使う。

方式:
  * block00031_PE.bin を ImageBase に全セクション展開してマップする。
  * 引数 (Win64): rcx=Host, rdx=HostTag, r8=ID, r9=Index, [caller rsp+0x20]=Value。
  * 関数範囲 [FN_LO, FN_HI) の外へ入る命令 (= call 先) は実行せず、戻り値 0 として
    呼出元へ戻す (外部呼出の記録のみ)。
  * 戻り先が SENT に達した時点の rax を応答値とする。

依存: unicorn (pip install unicorn)。
使い方: FL_WIN64_DIR=<展開先> python3 hs_disp_emu.py [IDs...]   (既定 0..255)
        HS_DISP_OUT=<path.json> を付けると全 ID の結果を JSON に出す。
        HS_DISP_STACK_FILL=<バイト値> で実行前のスタック内容を指定する (未指定は 0 埋め・#2782)。
"""
import os
import sys
import json
from collections import Counter

import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE, UC_HOOK_MEM_UNMAPPED, UC_HOOK_MEM_WRITE, UC_PROT_ALL
from unicorn import UC_MEM_READ_UNMAPPED, UC_MEM_WRITE_UNMAPPED, UC_MEM_FETCH_UNMAPPED
from unicorn.x86_const import UC_X86_REG_RAX, UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_RSP, UC_X86_REG_RBP, UC_X86_REG_R8, UC_X86_REG_R9, UC_X86_REG_RIP

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'shared'))
from paths import FL_WIN64_DIR

PE_PATH = os.path.join(FL_WIN64_DIR, 'extracted', 'block00031_PE.bin')
DISP = 0x13173a0
FN_LO, FN_HI = 0x13173a0, 0x1330000
HOST = 0x40000000
TAG = 0x54534154
STACK_BASE, STACK_SIZE = 0x7000000, 0x200000
STACK_TOP = STACK_BASE + 0x100000
SENT = 0x7F000000
MAX_STEPS = 400000
PAGE = 0x1000
# 経路上の判定用 VA (hostshim.c / hs_disp_tree.py の主張の検証点)
WATCH = {0x131bb5c, 0x13281af, 0x1320dd9, 0x1322b53, 0x131b8dd, 0x1320840}
# HS_DISP_RET_ARG=1 のとき、機械語で rax=第1引数 と確定した callee は rcx を返す (#1222 §7)
RET_ARG = os.environ.get('HS_DISP_RET_ARG') == '1'
RET_ARG_VA = {0x412d60, 0x416230}
# HS_DISP_PATH=1 のとき結果に実行経路 (path) と callout の位置 (callout_at: (path 上の位置, 呼出先)) を含める (#2886 の格納元解析用)
KEEP_PATH = os.environ.get('HS_DISP_PATH') == '1'
# HS_DISP_RET_SPEC="VA:rcx,VA:host,VA:one,..." で callee ごとの戻り値を指定する (#1222 §8・#2782 §10)。
# rcx = 第1引数を返す / host = HOST 領域 (有効ポインタ) を返す / one = 整数 1 を返す。未指定の callee は従来どおり 0。
RET_SPEC = {}
for _item in filter(None, os.environ.get('HS_DISP_RET_SPEC', '').split(',')):
    _va, _mode = _item.split(':')
    RET_SPEC[int(_va, 0)] = _mode
# 応答値の格納先 [rbp+0x11a0] (#2782)。Dispatcher 末尾 0x1328a38 の `mov rax,[rbp+0x11a0]` が応答になる。
# rbp = STACK_TOP-40-0x1838 (entry rsp=STACK_TOP-8・push 4 本・sub 0x1838)。
RESP_SLOT = STACK_TOP - 40 - 0x1838 + 0x11a0
RESP_READ_VA = 0x1328a38  # mov rax,[rbp+0x11a0] (応答の読み出し)
# HS_DISP_STACK_FILL=<バイト値> でスタック領域を指定値で埋める (未指定は従来どおり 0 埋め)。
# 応答スロットが全 ID で書かれない経路の値が、スタックの初期内容に依存するかを試す (#2782)。
_FILL = os.environ.get('HS_DISP_STACK_FILL')
STACK_FILL = int(_FILL, 0) if _FILL else None
ACCESS_NAME = {UC_MEM_READ_UNMAPPED: 'read', UC_MEM_WRITE_UNMAPPED: 'write', UC_MEM_FETCH_UNMAPPED: 'fetch'}


def load_image(pe_data):
    pe = pefile.PE(data=pe_data)
    base = pe.OPTIONAL_HEADER.ImageBase
    size = (pe.OPTIONAL_HEADER.SizeOfImage + PAGE - 1) & ~(PAGE - 1)
    return pe, base, size


def run_one(ident, image, base, size, pe_data_sections):
    uc = Uc(UC_ARCH_X86, UC_MODE_64)
    uc.mem_map(base, size, UC_PROT_ALL)
    for va, raw in pe_data_sections:
        uc.mem_write(va, raw)
    uc.mem_map(HOST, 0x10000, UC_PROT_ALL)
    uc.mem_map(STACK_BASE, STACK_SIZE, UC_PROT_ALL)
    uc.mem_map(SENT & ~(PAGE - 1), PAGE, UC_PROT_ALL)
    uc.mem_write(SENT, b'\xf4')  # hlt (SENT 到達の検出用)
    if STACK_FILL is not None:
        uc.mem_write(STACK_BASE, bytes([STACK_FILL]) * STACK_SIZE)

    st = {'steps': 0, 'stop': None, 'callouts': [], 'callout_at': [], 'path': [], 'unmapped': 0, 'trail': [], 'hit': [], 'pages': Counter(),
          'slot_writes': []}
    fn_range = (FN_LO, FN_HI)

    def on_code(uc_, addr, sz, _):
        st['steps'] += 1
        if st['steps'] > MAX_STEPS:
            st['stop'] = 'step上限'
            uc_.emu_stop()
            return
        if addr == SENT:
            st['stop'] = 'return'
            uc_.emu_stop()
            return
        if addr == RESP_READ_VA:
            st['rbp_ok'] = uc_.reg_read(UC_X86_REG_RBP) == RESP_SLOT - 0x11a0
        if not (fn_range[0] <= addr < fn_range[1]):
            # 関数外へ入った = call 先 (外部 / 他関数)。戻り先を pop して rax=0 で戻す
            sp = uc_.reg_read(UC_X86_REG_RSP)
            ret = int.from_bytes(uc_.mem_read(sp, 8), 'little')
            st['callouts'].append('0x%x' % addr)
            st['callout_at'].append((len(st['path']), addr))
            ret_rax = 0
            if RET_ARG and addr in RET_ARG_VA:
                ret_rax = uc_.reg_read(UC_X86_REG_RCX)
            if addr in RET_SPEC:
                ret_rax = {'rcx': uc_.reg_read(UC_X86_REG_RCX), 'host': HOST, 'one': 1}[RET_SPEC[addr]]
            uc_.reg_write(UC_X86_REG_RAX, ret_rax)
            uc_.reg_write(UC_X86_REG_RSP, sp + 8)
            uc_.reg_write(UC_X86_REG_RIP, ret)
            return
        st['path'].append(addr)
        if addr in WATCH:
            st['hit'].append('0x%x' % addr)
        st['trail'].append(addr)
        if len(st['trail']) > 8:
            del st['trail'][0]

    def on_unmapped(uc_, access, addr, sz, val, _):
        st['unmapped'] += 1
        if st['unmapped'] > 2000:
            return False
        page = addr & ~(PAGE - 1)
        st['pages'][(page, ACCESS_NAME.get(access, str(access)))] += 1
        try:
            uc_.mem_map(page, PAGE, UC_PROT_ALL)
            uc_.mem_write(page, b'\x00' * PAGE)
        except Exception:
            return False
        return True

    def on_slot_write(uc_, access, addr, sz, val, _):
        st['slot_writes'].append('0x%x=0x%x' % (uc_.reg_read(UC_X86_REG_RIP), val))

    uc.hook_add(UC_HOOK_CODE, on_code, begin=base, end=base + size - 1)
    uc.hook_add(UC_HOOK_MEM_UNMAPPED, on_unmapped)
    uc.hook_add(UC_HOOK_MEM_WRITE, on_slot_write, begin=RESP_SLOT, end=RESP_SLOT + 7)

    sp = STACK_TOP
    uc.mem_write(sp + 0x20, (0).to_bytes(8, 'little'))       # Value (caller [rsp+0x20])
    sp -= 8
    uc.mem_write(sp, SENT.to_bytes(8, 'little'))             # 戻り先
    uc.reg_write(UC_X86_REG_RSP, sp)
    uc.reg_write(UC_X86_REG_RBP, sp)
    uc.reg_write(UC_X86_REG_RCX, HOST)
    uc.reg_write(UC_X86_REG_RDX, TAG)
    uc.reg_write(UC_X86_REG_R8, ident)
    uc.reg_write(UC_X86_REG_R9, 0)
    uc.reg_write(UC_X86_REG_RAX, 0)
    try:
        uc.emu_start(DISP, SENT, timeout=0, count=MAX_STEPS + 10)
    except Exception as e:
        st['stop'] = 'exception: %s' % e
    rax = uc.reg_read(UC_X86_REG_RAX)
    return {
        'rax': rax,
        'stop': st['stop'] or 'ended',
        'steps': st['steps'],
        'callouts': st['callouts'],
        'path_len': len(st['path']),
        'path_hash': '%08x' % (hash(tuple(st['path'])) & 0xffffffff),
        'trail': ['0x%x' % a for a in st['trail']],
        'unmapped': st['unmapped'],
        'unmapped_pages': {'0x%x/%s' % (p, a): n for (p, a), n in st['pages'].items()},
        'hit': st['hit'],
        'path': st['path'] if KEEP_PATH else None,
        'callout_at': st['callout_at'] if KEEP_PATH else None,
        'slot_writes': st['slot_writes'],
        'rbp_ok': st.get('rbp_ok'),
    }


def main():
    ids = [int(a, 0) for a in sys.argv[1:]] or list(range(256))
    pe_data = open(PE_PATH, 'rb').read()
    pe, base, size = load_image(pe_data)
    sections = [(base + s.VirtualAddress, s.get_data()) for s in pe.sections]
    sections.insert(0, (base, pe_data[:pe.OPTIONAL_HEADER.SizeOfHeaders]))
    res = {}
    for ident in ids:
        r = run_one(ident, pe, base, size, sections)
        res[ident] = r
        print('ID=0x%02x rax=0x%x stop=%s steps=%d path=%d leaf=%s hash=%s callouts=%s' % (
            ident, r['rax'], r['stop'], r['steps'], r['path_len'], r['trail'][-1] if r['trail'] else '-',
            r['path_hash'], ','.join(r['callouts'][:6]) or '-'))
    keys = Counter((r['rax'], r['path_hash']) for r in res.values())
    print('distinct (rax, path) = %d / IDs = %d' % (len(keys), len(res)))
    pages = Counter()
    for r in res.values():
        for k, n in r['unmapped_pages'].items():
            pages[k] += n
    print('unmapped: IDs with access = %d / total access = %d / (page,access) pairs = %d / pages = %d' % (
        sum(1 for r in res.values() if r['unmapped']), sum(pages.values()), len(pages),
        len(set(k.split('/')[0] for k in pages))))
    print('unmapped top (page/access, count over all IDs): %s' % ', '.join('%s=%d' % kv for kv in pages.most_common(5)))
    no_write = sorted(k for k, r in res.items() if not r['slot_writes'])
    print('slot [rbp+0x11a0]: IDs with no write = %d (stack_fill=%s) rbp_ok=%d / mismatch=%d / unreached=%d' % (
        len(no_write), 'none' if STACK_FILL is None else '0x%02x' % STACK_FILL,
        sum(1 for r in res.values() if r['rbp_ok'] is True), sum(1 for r in res.values() if r['rbp_ok'] is False),
        sum(1 for r in res.values() if r['rbp_ok'] is None)))
    print('slot no-write IDs: %s' % ' '.join('0x%02x' % k for k in no_write))
    out = os.environ.get('HS_DISP_OUT')
    if out:
        json.dump({'%d' % k: v for k, v in res.items()}, open(out, 'w'), indent=1)


if __name__ == '__main__':
    main()
