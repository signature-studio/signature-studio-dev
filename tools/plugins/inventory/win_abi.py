#!/usr/bin/env python3
"""全 Delphi プラグイン DLL (win64) の FruityPlug ABI 実測: CreatePlugInstance → クラス → vtable → Info。

 - CreatePlugInstance(Host, Tag) を逆アセンブルし、`mov rcx,[rip+disp]` (クラスref) と最後の call (ctor) を得る
 - クラス ref の中身 = vtable 先頭 (Image-Line 版 Delphi は TObject 仮想を負 index に置く C++ 互換配置)
 - vtable[0..19] = TFruityPlug 20 スロット。抽象 stub (最頻出アドレス) か override かを判定
 - ctor 内の `lea rcx,[rip+d]; mov [rax+0x10],rcx` から TFruityPlugInfo (packed) を読む
出力: work/win_abi.json
"""
import os, sys, json, struct, re, collections
from multiprocessing import Pool
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, '..', 'work')
EXT = '/home/ubuntu/work/analysis/win64/extracted'
SLOTS = ['DestroyObject', 'Dispatcher', 'Idle_Public', 'SaveRestoreState', 'GetName', 'ProcessEvent',
         'ProcessParam', 'Eff_Render', 'Gen_Render', 'TriggerVoice', 'Voice_Release', 'Voice_Kill',
         'Voice_ProcessEvent', 'Voice_Render', 'NewTick', 'MIDITick', 'MIDIIn', 'MsgIn',
         'OutputVoice_ProcessEvent', 'OutputVoice_Kill']


class Img:
    def __init__(self, d):
        self.d = d
        self.pe = pefile.PE(data=d, fast_load=True)
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.size = self.pe.OPTIONAL_HEADER.SizeOfImage

    def rd(self, va, n):
        o = self.pe.get_offset_from_rva(va - self.base)
        return self.d[o:o + n]

    def q(self, va):
        return struct.unpack('<Q', self.rd(va, 8))[0]

    def inimg(self, va):
        return self.base <= va < self.base + self.size

    def cstr(self, va, n=96):
        try:
            return self.rd(va, n).split(b'\0')[0].decode('latin1')
        except Exception:
            return None

    def pstr(self, va):
        try:
            b = self.rd(va, 64)
            return b[1:1 + b[0]].decode('latin1')
        except Exception:
            return None


def scan(fn):
    d = open(os.path.join(EXT, fn), 'rb').read()
    img = Img(d)
    pe = img.pe
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT']])
    cpi = None
    for s in pe.DIRECTORY_ENTRY_EXPORT.symbols:
        if s.name == b'CreatePlugInstance':
            cpi = img.base + s.address
    r = {'file': fn, 'cpi': hex(cpi) if cpi else None}
    if not cpi:
        return r
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    code = img.rd(cpi, 0x100)
    classref = None
    ctor = None
    calls = []
    for i in md.disasm(code, cpi):
        if i.mnemonic == 'mov' and i.op_str.startswith('rcx, qword ptr [rip') and classref is None and calls:
            classref = i.address + i.size + i.operands[1].mem.disp
        if i.mnemonic == 'call' and i.operands[0].type == 2:
            calls.append(i.operands[0].imm)
            if classref is not None and ctor is None:
                ctor = i.operands[0].imm
        if i.mnemonic == 'ret':
            break
    r['calls'] = [hex(c) for c in calls]
    if classref is None:
        return r
    cp = img.q(classref)
    r['classref'] = hex(classref)
    r['vtable'] = hex(cp)
    hdr = cp - 0x70
    r['class_name'] = img.pstr(img.q(hdr - 24))
    r['instance_size'] = img.q(hdr - 16)
    par = img.q(hdr - 8)
    if img.inimg(par):
        try:
            r['parent'] = img.pstr(img.q(par - 0x70 - 24))
        except Exception:
            pass
    slots = []
    for k in range(64):
        x = img.q(cp + 8 * k)
        if not (img.base + 0x1000 <= x < img.base + img.size):
            break
        slots.append(x)
    r['nslots'] = len(slots)
    first20 = slots[:20]
    # abstract stub = 最頻出アドレス (仮想 20 スロットのうち複数回出現するもの)
    c = collections.Counter(first20)
    abstract = c.most_common(1)[0][0] if c.most_common(1)[0][1] >= 3 else None
    r['abstract'] = hex(abstract) if abstract else None
    r['slots'] = [hex(x) for x in slots]
    r['impl'] = {SLOTS[k]: hex(first20[k]) for k in range(len(first20)) if first20[k] != abstract}
    # Info
    info = None
    if ctor:
        code = img.rd(ctor, 0x120)
        leas = {}
        for i in md.disasm(code, ctor):
            m = re.match(r'(r[a-z0-9]+), \[rip', i.op_str) if i.mnemonic == 'lea' else None
            if m:
                leas[m.group(1)] = i.address + i.size + i.operands[1].mem.disp
            m = re.match(r'qword ptr \[r[a-z0-9]+ \+ 0x10\], (r[a-z0-9]+)$', i.op_str) if i.mnemonic == 'mov' else None
            if m and m.group(1) in leas:
                info = leas[m.group(1)]
                break
            if i.mnemonic == 'ret':
                break
    if info:
        b = img.rd(info, 44)
        sdk, ln, sn, fl, npar, dpoly, noc, nov = struct.unpack('<iQQiiiii', b[:40])
        r['info'] = {'va': hex(info), 'sdk': sdk, 'long': img.cstr(ln), 'short': img.cstr(sn),
                     'flags': hex(fl & 0xffffffff), 'nparams': npar, 'defpoly': dpoly, 'noutctrl': noc, 'noutvoice': nov}
    return r


def main():
    S = {r['file']: r for r in json.load(open(os.path.join(WORK, 'win_pe_scan.json')))}
    files = sorted(f for f, r in S.items() if 'FP_DelphiPlug' in r['hints'] and 'CreatePlugInstance' in r['exports'])
    with Pool(14) as p:
        res = p.map(scan, files)
    json.dump(res, open(os.path.join(WORK, 'win_abi.json'), 'w'), indent=0)
    ok = [r for r in res if 'info' in r]
    print('delphi plugin DLLs', len(res), 'with vtable', sum(1 for r in res if 'vtable' in r), 'with info', len(ok))
    cl = collections.Counter(r.get('class_name') for r in res)
    print(cl.most_common(12))
    imp = collections.Counter()
    for r in res:
        for k in r.get('impl', {}):
            imp[k] += 1
    print(sorted(imp.items(), key=lambda kv: -kv[1]))


if __name__ == '__main__':
    main()
