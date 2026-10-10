#!/usr/bin/env python3
"""HeartCore.core_64 のライセンス層静的解析ツール (CAB-59)。

phase strings : .rdata/.data (raw) から ASCII / UTF-16LE 文字列を全抽出し VA 付きで JSON 化
phase sweep   : .text を capstone sweep (並列) し rip 相対 operand 先 target → (insn, func) の逆引きを pickle 化
                + call [rip+X] (IAT) site も記録
phase query   : キーワードで文字列を引き、xref (参照元関数) と callgraph 情報を表示

usage:
  lic_scan.py strings <pe> <out_strings.json>
  lic_scan.py sweep   <pe> <callgraph.pkl> <out_xrefs.pkl> [nproc]
  lic_scan.py query   <pe> <strings.json> <xrefs.pkl> <callgraph.pkl> <keyword...> [--utf16|--ascii]
"""
import sys, os, re, json, pickle, collections
import pefile
from multiprocessing import Pool

PE_PATH = None


def load_pe(path):
    pe = pefile.PE(path, fast_load=True)
    return pe, open(path, 'rb').read()


def rva2off(pe, rva):
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            d = rva - s.VirtualAddress
            if d < s.SizeOfRawData:
                return s.PointerToRawData + d
    return None


# ---------------------------------------------------------------- strings
def phase_strings(path, outp):
    pe, data = load_pe(path)
    base = pe.OPTIONAL_HEADER.ImageBase
    out = {}
    for s in pe.sections:
        name = s.Name.rstrip(b'\0').decode()
        if name not in ('.rdata', '.data'):
            continue
        raw = data[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
        # ascii runs >=4
        for m in re.finditer(rb'[\x20-\x7e]{4,}', raw):
            va = base + s.VirtualAddress + m.start()
            out.setdefault(va, {'s': m.group().decode('ascii'), 'enc': 'a', 'sec': name})
        # utf16le runs >=4 chars
        for m in re.finditer(rb'(?:[\x20-\x7e]\x00){4,}', raw):
            va = base + s.VirtualAddress + m.start()
            out.setdefault(va, {'s': m.group().decode('utf-16le'), 'enc': 'w', 'sec': name})
    json.dump({hex(k): v for k, v in sorted(out.items())}, open(outp, 'w'), ensure_ascii=False)
    print('strings', len(out), '->', outp)


# ---------------------------------------------------------------- sweep
_PE = None
_DATA = None


def _init(path):
    global _PE, _DATA
    _PE = pefile.PE(path, fast_load=True)
    _DATA = open(path, 'rb').read()


def _sweep_chunk(ranges):
    import capstone
    from capstone import CS_ARCH_X86, CS_MODE_64
    base = _PE.OPTIONAL_HEADER.ImageBase
    t = _PE.sections[0]
    t_lo, t_hi = t.VirtualAddress, t.VirtualAddress + t.Misc_VirtualSize

    def off(rva):
        return t.PointerToRawData + (rva - t.VirtualAddress)

    md = capstone.Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = False
    rip = {}   # target_rva -> [(insn_va, func_va)]
    iat = {}   # iat_rva    -> [(insn_va, func_va)]
    for start, end in ranges:
        lim = min(end, t_hi)
        buf = _DATA[off(start):off(lim)]
        for addr, size, mn, ops in md.disasm_lite(buf, base + start):
            if '[rip' in ops:
                m = re.search(r'\[rip \+ (0x[0-9a-f]+)\]|\[rip - (0x[0-9a-f]+)\]', ops)
                if not m:
                    continue
                disp = int(m.group(1), 16) if m.group(1) else -int(m.group(2), 16)
                tgt = addr + size + disp - base
                iscall = mn == 'call' or (mn == 'jmp' and '0x' not in ops.split(',')[0])
                d = iat if (iscall and tgt < t_lo or iscall and tgt >= t_hi) else rip
                if iscall:
                    # call [rip+x] / jmp [rip+x] → IAT slot (target outside .text)
                    if tgt < t_lo or tgt >= t_hi:
                        d = iat
                    else:
                        d = rip
                d.setdefault(tgt, []).append((addr - base + base, start + base))
    return rip, iat


def phase_sweep(path, cgp, outp, nproc=16):
    cg = pickle.load(open(cgp, 'rb'))
    funcs = cg['funcs']
    res = cg['res']
    # sweep 既知関数 (pdata+leaf)。leaf は res から size を使う
    ranges = []
    for start, r in res.items():
        end = start + max(r['size'], 16)
        ranges.append((start, end))
    ranges.sort()
    chunks = [ranges[i::nproc * 8] for i in range(nproc * 8)]
    rip_all, iat_all = {}, {}
    with Pool(nproc, initializer=_init, initargs=(path,)) as p:
        for rip, iat in p.imap_unordered(_sweep_chunk, chunks):
            for k, v in rip.items():
                rip_all.setdefault(k, []).extend(v)
            for k, v in iat.items():
                iat_all.setdefault(k, []).extend(v)
    pickle.dump({'rip': rip_all, 'iat': iat_all}, open(outp, 'wb'), protocol=4)
    print('sweep: rip targets', len(rip_all), 'iat slots', len(iat_all), '->', outp)


# ---------------------------------------------------------------- query
def _func_callers(cg, base, fnva):
    """fn を直接 call する関数一覧"""
    out = []
    for s, r in cg['res'].items():
        if (fnva - base) in r['calls'] or (fnva - base) in r['jmps']:
            out.append(s + base)
    return out


def phase_query(path, strp, xrp, cgp, keywords, enc=None):
    pe, _ = load_pe(path)
    base = pe.OPTIONAL_HEADER.ImageBase
    strings = {int(k, 16): v for k, v in json.load(open(strp)).items()}
    x = pickle.load(open(xrp, 'rb'))
    rip, iat = x['rip'], x['iat']
    cg = pickle.load(open(cgp, 'rb'))
    res = cg['res']

    kw = [k.lower() for k in keywords]
    hits = {}
    for va, info in strings.items():
        s = info['s'].lower()
        if any(k in s for k in kw):
            if enc and info['enc'] != enc:
                continue
            hits[va] = info
    print(f'=== {len(hits)} strings match {keywords} (enc={enc or "any"}) ===')
    for va in sorted(hits):
        info = hits[va]
        refs = rip.get(va - base, [])
        print(f'\n[{va:#x}] {info["enc"]} {info["sec"]} {info["s"][:120]!r}')
        for insn, fn in refs[:12]:
            r = res.get(fn - base)
            sz = r['size'] if r else '?'
            print(f'    <- insn {insn:#x} func {fn:#x} (size {sz})')
        if len(refs) > 12:
            print(f'    ... +{len(refs)-12} more refs')


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'strings':
        phase_strings(sys.argv[2], sys.argv[3])
    elif cmd == 'sweep':
        phase_sweep(sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]) if len(sys.argv) > 5 else 16)
    elif cmd == 'query':
        enc = None
        args = sys.argv[2:]
        if '--utf16' in args:
            enc = 'w'; args.remove('--utf16')
        if '--ascii' in args:
            enc = 'a'; args.remove('--ascii')
        phase_query(args[0], args[1], args[2], args[3], args[4:], enc)
