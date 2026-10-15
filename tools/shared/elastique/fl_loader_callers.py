#!/usr/bin/env python3
"""FL 本体 PE の中で LoadSharedElastiqueDll を解決するローダと、その呼出元を静的に同定する (T-SH-123 / #4396)。

入力: FL_WIN64_DIR = 素材の展開先 (既定 $RUNNER_TEMP/fl-win64。extracted/ を含む)
手順:
  1. block00031_PE.bin (FL 本体) の .text を線形走査し、UTF-16LE "LoadSharedElastiqueDll" を指す lea を探す。
     その lea を含む関数をローダとする。
  2. ローダの直接 call/jmp (rel32) の呼出元を数え、各呼出元を含む関数 (wrap) を求める。
  3. wrap の中で、élastique の *_CreateInstance の UTF-16 名を指す lea の有無を数える。
  4. wrap の直接呼出元 (1 段上) を求める。
出力: 標準出力のみ。線形走査は命令境界を (逆アセンブルの size で) 進める。
"""
import bisect
import os
import re
import time

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

FL_DIR = os.environ.get('FL_WIN64_DIR', os.path.join(os.environ.get('RUNNER_TEMP', '/tmp'), 'fl-win64'))
PE_NAME = 'block00031_PE.bin'
LOADER_NAME = 'LoadSharedElastiqueDll'
CREATE_NAMES = ['ElPro_CreateInstance', 'ElProDirect_CreateInstance', 'ElProV3_CreateInstance',
                'ElProV3Direct_CreateInstance', 'ElResampleSource_CreateInstance',
                'Auftakt_CreateInstance', 'SolPitchAn_CreateInstance']
RIP_RE = re.compile(r'\[rip \+ (0x[0-9a-f]+)\]')


def main():
    t0 = time.time()
    path = os.path.join(FL_DIR, 'extracted', PE_NAME)
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXCEPTION']])
    ib = pe.OPTIONAL_HEADER.ImageBase
    data = open(path, 'rb').read()
    text = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.text'][0]
    base = ib + text.VirtualAddress
    code = data[text.PointerToRawData:text.PointerToRawData + text.Misc_VirtualSize]
    funcs = sorted((ib + e.struct.BeginAddress, ib + e.struct.EndAddress) for e in pe.DIRECTORY_ENTRY_EXCEPTION)
    starts = [a for a, _ in funcs]

    def fn_of(va):
        i = bisect.bisect_right(starts, va) - 1
        return funcs[i][0] if i >= 0 and funcs[i][0] <= va < funcs[i][1] else None

    def utf16_str_va(s):
        off = data.find(s.encode('utf-16le'))
        for sec in pe.sections:
            if sec.PointerToRawData <= off < sec.PointerToRawData + sec.SizeOfRawData:
                return ib + sec.VirtualAddress + (off - sec.PointerToRawData)
        return None

    names = {utf16_str_va(LOADER_NAME): LOADER_NAME}
    for n in CREATE_NAMES:
        names[utf16_str_va(n)] = n
    names.pop(None, None)

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    lea_refs = {}
    call_refs = {}
    slot_name = {}
    slot_calls = {}
    last_name = {}
    o = 0
    while o < len(code):
        ins = next(md.disasm(code[o:o + 16], base + o), None)
        if ins is None:
            o += 1
            continue
        m = RIP_RE.search(ins.op_str) if 'rip' in ins.op_str else None
        if m:
            t = ins.address + ins.size + int(m.group(1), 16)
            if ins.mnemonic == 'lea' and t in names:
                lea_refs.setdefault(names[t], []).append(ins.address)
                last_name[fn_of(ins.address)] = names[t]
            elif ins.mnemonic == 'mov' and ins.op_str.startswith('qword ptr [rip') and ins.op_str.endswith(', rax'):
                n = last_name.get(fn_of(ins.address))
                if n and n != LOADER_NAME:
                    slot_name[t] = n
            elif ins.mnemonic == 'call':
                slot_calls.setdefault(t, []).append(ins.address)
        if ins.mnemonic in ('call', 'jmp') and ins.op_str.startswith('0x'):
            call_refs.setdefault(int(ins.op_str, 16), []).append(ins.address)
        o += ins.size

    loader_fns = sorted({fn_of(a) for a in lea_refs.get(LOADER_NAME, [])} - {None})
    print(f'PE: {PE_NAME} (.text {hex(base)}・{len(code)} B・関数 {len(funcs)})')
    print(f'{LOADER_NAME} を指す lea: {[hex(a) for a in lea_refs.get(LOADER_NAME, [])]} → 関数 {[hex(f) for f in loader_fns]}')
    print('ローダが格納するスロット → export 名: ' + ', '.join(f'{hex(s)}={n}' for s, n in sorted(slot_name.items())))
    for ld in loader_fns:
        callers = call_refs.get(ld, [])
        print(f'ローダ {hex(ld)} の直接呼出元: {len(callers)} 件')
        for c in callers:
            wrap = fn_of(c)
            print(f'  call {hex(c)} → wrap {hex(wrap)}')
            for s in sorted(slot_calls):
                if any(fn_of(a) == wrap for a in slot_calls[s]):
                    print(f'    wrap が call [{hex(s)}] = {slot_name.get(s, "同一関数内の名前解決 (未対応)")}')
            up = call_refs.get(wrap, [])
            print(f'    wrap の直接呼出元: {len(up)} 件 {[hex(u) + " in " + hex(fn_of(u)) for u in up]}')
    print(f'経過 {time.time() - t0:.1f} s')


if __name__ == '__main__':
    main()
