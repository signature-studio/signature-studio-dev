#!/usr/bin/env python3
"""win64 プラグイン PE の関数単位解析。

.pdata から関数境界を取り、各関数を capstone で逆アセンブルして
 - 位置非依存ハッシュ (RIP 相対 disp / 外部への call・jmp rel32 をマスク)
 - 浮動小数点演算命令数 (SSE/AVX 算術)
 - 呼んでいる Win32 import 名 (call [IAT] / jmp thunk 経由)
を求める。結果は work/winfuncs/<block>.json。
cross-plugin 集計 (framework か plugin 固有か) は win_unique.py。
"""
import os, sys, json, struct, hashlib, re, collections
from multiprocessing import Pool
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_REG_RIP

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'icall', 'disp_size'))
import dispfix as DF
WORK = os.path.join(HERE, '..', 'work')
OUTD = os.path.join(WORK, 'winfuncs')
EXT = '/home/ubuntu/work/analysis/win64/extracted'
# CAB-229 (D9): capstone の disp_size は 66 prefix 付き disp32 で 2 を返す。補正は opt-in (WINFUNCS_DISPFIX=1)。
# 既定 OFF の理由: ここで出すハッシュは framework/fw_prep.py (CAB-194 稼働中・編集禁止) が同一規約で再計算して
# work/fw_hash_counts.json と突合するため、片側だけ規約を変えると framework 判定が静かに縮む。移行手順は icall/disp_size/REPORT.md §5。
DISPFIX = os.environ.get('WINFUNCS_DISPFIX') == '1'


def disp_of(ins):
    """(offset, size) | None"""
    if DISPFIX:
        return DF.disp_span(ins)
    return (ins.disp_offset, ins.disp_size) if ins.disp_size else None

FP_RE = re.compile(r'^v?(add|sub|mul|div|sqrt|min|max|rcp|rsqrt|fmadd|fmsub|fnmadd|fnmsub|hadd|dp)(ss|sd|ps|pd)$')
CVT_RE = re.compile(r'^v?cvt')
X87 = {'fld', 'fstp', 'fmul', 'fadd', 'fsub', 'fdiv', 'fild', 'fistp', 'fmulp', 'faddp', 'fsubp', 'fdivp', 'fsin', 'fcos', 'fsqrt', 'fxch', 'fst', 'fld1', 'fldz', 'fchs', 'fabs'}
BRANCH_REL = {'call', 'jmp'}


def get_funcs(pe):
    pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata']
    if not pd:
        return []
    data = pd[0].get_data()[:pd[0].Misc_VirtualSize]
    out = []
    for i in range(len(data) // 12):
        b, e, u = struct.unpack_from('<III', data, 12 * i)
        if b == 0 and e == 0:
            continue
        if u & 1:  # chained/indirect unwind
            continue
        out.append((b, e))
    return sorted(set(out))


def analyze(fn):
    path = os.path.join(EXT, fn)
    d = open(path, 'rb').read()
    pe = pefile.PE(data=d, fast_load=True)
    D = pefile.DIRECTORY_ENTRY
    pe.parse_data_directories(directories=[D['IMAGE_DIRECTORY_ENTRY_IMPORT'], D['IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT']])
    base = pe.OPTIONAL_HEADER.ImageBase
    iat = {}
    for ent in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
        dll = ent.dll.decode('latin1').lower()
        for im in ent.imports:
            nm = im.name.decode('latin1') if im.name else '#%d' % im.ordinal
            iat[im.address - base] = (dll, nm)
    for ent in getattr(pe, 'DIRECTORY_ENTRY_DELAY_IMPORT', []):
        dll = ent.dll.decode('latin1').lower()
        for im in ent.imports:
            nm = im.name.decode('latin1') if im.name else '#%d' % im.ordinal
            a = getattr(im, 'address', None)
            if a:
                iat[a - base] = (dll + '(delay)', nm)
    execs = [s for s in pe.sections if s.Characteristics & 0x20000000]
    code = {}
    for s in execs:
        code[s.VirtualAddress] = s.get_data()[:s.Misc_VirtualSize]

    def read(rva, n):
        for va, b in code.items():
            if va <= rva < va + len(b):
                return b[rva - va: rva - va + n]
        return b''

    thunks = {}
    for va, b in code.items():
        i = b.find(b'\xff\x25')
        while i != -1:
            if i + 6 <= len(b):
                disp = struct.unpack_from('<i', b, i + 2)[0]
                tgt = va + i + 6 + disp
                if tgt in iat:
                    thunks[va + i] = iat[tgt]
            i = b.find(b'\xff\x25', i + 1)
    funcs = get_funcs(pe)
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    res = []
    for (b, e) in funcs:
        raw = read(b, e - b)
        if len(raw) != e - b:
            continue
        norm = bytearray(raw)
        nfp = ncvt = nx87 = ninsn = 0
        imps = set()
        for ins in md.disasm(raw, b):
            ninsn += 1
            mn = ins.mnemonic
            off = ins.address - b
            if FP_RE.match(mn):
                nfp += 1
            elif CVT_RE.match(mn):
                ncvt += 1
            elif mn in X87:
                nx87 += 1
            if mn in BRANCH_REL and ins.imm_size == 4:
                tgt = ins.operands[0].imm if ins.operands else 0
                if not (b <= tgt < e):
                    for k in range(ins.imm_offset, ins.imm_offset + 4):
                        norm[off + k] = 0
                    if tgt in thunks:
                        imps.add(thunks[tgt])
                continue
            if mn.startswith('j') and ins.imm_size == 4:
                tgt = ins.operands[0].imm
                if not (b <= tgt < e):
                    for k in range(ins.imm_offset, ins.imm_offset + 4):
                        norm[off + k] = 0
                continue
            dsp = disp_of(ins)
            if dsp and dsp[1] == 4:
                for o in ins.operands:
                    if o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP:
                        for k in range(dsp[0], dsp[0] + 4):
                            norm[off + k] = 0
                        tgt = ins.address + ins.size + o.mem.disp
                        if tgt in iat and mn in ('call', 'jmp'):
                            imps.add(iat[tgt])
                        break
        h = hashlib.sha1(bytes(norm)).hexdigest()[:12]
        res.append([b, e - b, h, ninsn, nfp, ncvt, nx87, sorted('%s!%s' % x for x in imps)])
    strs = set()
    for m in re.finditer(rb'([A-Za-z0-9_\-\. ]{3,40}\.(?:dll|DLL|dylib))', d):
        strs.add(m.group(1).decode('latin1'))
    for m in re.finditer(rb'((?:[A-Za-z0-9_\-\. ]\x00){3,40}\.\x00[dD]\x00[lL]\x00[lL]\x00)', d):
        strs.add(m.group(1).decode('utf-16le', 'ignore'))
    out = {'file': fn, 'nfunc': len(res), 'funcs': res, 'dll_strings': sorted(strs)[:80],
           'thunks': len(thunks), 'iat': len(iat)}
    os.makedirs(OUTD, exist_ok=True)
    json.dump(out, open(os.path.join(OUTD, fn.replace('_PE.bin', '.json')), 'w'))
    return fn, len(res)


def main():
    B = json.load(open(os.path.join(WORK, 'nsis_blockmap.json')))
    ids = set()
    for r in B:
        if r['kind'] == 'PE' and re.match(r'^\$V31\\Plugins\\Fruity\\(Effects|Generators)\\', r['outdir']):
            ids.add(r['idx'])
    S = {r['file']: r for r in json.load(open(os.path.join(WORK, 'win_pe_scan.json')))}
    files = sorted('block%05d_PE.bin' % i for i in ids if S['block%05d_PE.bin' % i]['machine'] == 'x64')
    if len(sys.argv) > 1:
        files = [f for f in files if f[5:10] in sys.argv[1:]]
    with Pool(14) as p:
        for fn, n in p.imap_unordered(analyze, files):
            pass
    print('analyzed', len(files), 'PEs ->', os.path.normpath(OUTD))


if __name__ == '__main__':
    main()
