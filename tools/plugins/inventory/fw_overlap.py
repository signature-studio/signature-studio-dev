#!/usr/bin/env python3
"""Delphi プラグイン 133 DLL の framework 共有度を、win_funcs.py とは独立の正規化ハッシュで再計測する (検収で追加)。

関数 (.pdata 境界) ごとに disp32 / rel32 分岐先をゼロ化したバイト列を md5 化し、
 (a) ≥N DLL に現れる distinct ハッシュ数, (b) DLL ごとの framework 関数バイト・関数数, (c) Fruity Balance の関数バイトが
 他 DLL にどれだけ含まれるか (framework 同一性の直接指標) を出力する。
出力: work/fw_overlap.json (集計のみ)。 要: pefile, capstone。 ~1 分 (14 proc)。
"""
import json, os, re, struct, sys, collections, hashlib, statistics
from multiprocessing import Pool
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'icall', 'disp_size'))
import dispfix as DF      # CAB-229: capstone の disp_size は 66 prefix 付き disp32 で 2 を返す (D9)
WORK = os.path.join(HERE, '..', 'work')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared'))
from paths import FL_WIN64_DIR  # noqa: E402
EXT = os.path.join(FL_WIN64_DIR, 'extracted')
BALANCE = 18983


def delphi_blocks():
    B = json.load(open(os.path.join(WORK, 'nsis_blockmap.json')))
    ids = sorted({r['idx'] for r in B if r['kind'] == 'PE' and re.match(r'^\$V31\\Plugins\\Fruity\\(Effects|Generators)\\', r['outdir'])})
    out = []
    for i in ids:
        d = open('%s/block%05d_PE.bin' % (EXT, i), 'rb').read()
        if pefile.PE(data=d, fast_load=True).FILE_HEADER.Machine == 0x8664 and b'FP_DelphiPlug' in d:
            out.append(i)
    return out


def funcs_of(i):
    d = open('%s/block%05d_PE.bin' % (EXT, i), 'rb').read()
    pe = pefile.PE(data=d, fast_load=True)
    pdata = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0].get_data()
    fs = sorted({(b, e) for b, e, u in (struct.unpack_from('<III', pdata, 12 * k) for k in range(len(pdata) // 12)) if b and not u & 1})
    code = {s.VirtualAddress: s.get_data()[:s.Misc_VirtualSize] for s in pe.sections if s.Characteristics & 0x20000000}
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    out = []
    for b, e in fs:
        raw = next((c[b - va:e - va] for va, c in code.items() if va <= b < va + len(c)), b'')
        if len(raw) != e - b:
            continue
        nm = bytearray(raw)
        for ins in md.disasm(raw, b):
            o = ins.address - b
            DF.zero_disp32(nm, o, ins)
            if ins.imm_size == 4 and (ins.group(1) or ins.group(2) or ins.group(7) or ins.mnemonic in ('call', 'jmp')):
                nm[o + ins.imm_offset:o + ins.imm_offset + 4] = b'\0\0\0\0'
        out.append((e - b, hashlib.md5(bytes(nm)).hexdigest()[:16]))
    return i, out


if __name__ == '__main__':
    ids = delphi_blocks()
    with Pool(14) as p:
        R = dict(p.map(funcs_of, ids))
    cnt = collections.Counter()
    for o in R.values():
        for h in {x[1] for x in o}:
            cnt[h] += 1
    res = {'delphi_dlls': len(ids), 'distinct_hashes': len(cnt)}
    for th in (130, 100, 66, 13):
        res['distinct_hash_in_ge_%d_dlls' % th] = sum(1 for v in cnt.values() if v >= th)
    fw = [(sum(s for s, h in o if cnt[h] >= 13), sum(s for s, h in o), sum(1 for s, h in o if cnt[h] >= 13)) for o in R.values()]
    res['fw_bytes_per_dll'] = {'min': min(f[0] for f in fw), 'median': statistics.median(f[0] for f in fw), 'max': max(f[0] for f in fw)}
    res['fw_funcs_per_dll_median'] = statistics.median(f[2] for f in fw)
    res['fw_fraction_median'] = round(statistics.median(f[0] / f[1] for f in fw), 3)
    res['nonfw_bytes_median'] = statistics.median(f[1] - f[0] for f in fw)
    bal = R[BALANCE]
    sz = {h: s for s, h in bal}
    tot = sum(sz.values())
    hs = {i: {x[1] for x in o} for i, o in R.items()}
    cov = sorted((sum(sz[h] for h in sz if h in hs[i]) / tot, i) for i in R)
    res['balance_func_bytes_covered_by_other_dll'] = {
        'min': round(cov[0][0], 3), 'median': round(statistics.median(c[0] for c in cov), 3),
        'ge_0.9': sum(1 for c in cov if c[0] >= 0.9), 'ge_0.8': sum(1 for c in cov if c[0] >= 0.8),
        'lt_0.8': [(i, round(c, 3)) for c, i in cov if c < 0.8]}
    os.makedirs(WORK, exist_ok=True)
    json.dump(res, open(os.path.join(WORK, 'fw_overlap.json'), 'w'), indent=1)
    print(json.dumps(res, indent=1))
