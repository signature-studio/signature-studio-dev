#!/usr/bin/env python3
"""census.py — 実バイナリでの capstone disp_size 誤報告の実測 (CAB-229 要件2)

各サンプル (PE の関数範囲集合 / 全 .pdata / mac x86_64 slice の LC_FUNCTION_STARTS 関数) を線形 disasm し、
dispfix の補正 layout を真値として capstone の (disp_size, disp_offset) を突合する。ほか:
  - capstone mem.disp が rip 相対で raw の disp32 と一致するか (値側の健全性。誤りなら全 rip 利用コードに波及)
  - imm_offset == size - imm_size か (imm 側の健全性)
出力: results/census.json と stdout 表。 usage: census.py [--jobs 14] [--only NAME,NAME] [--json results/census.json]
"""
import argparse, collections, json, os, re, struct, sys
from multiprocessing import Pool
from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OP_MEM
from capstone.x86 import X86_REG_RIP

HERE = os.path.dirname(os.path.abspath(__file__))
ICALL = os.path.join(HERE, '..')
T = os.path.join(ICALL, '..')
sys.path.insert(0, HERE)
sys.path.insert(0, ICALL)
sys.path.insert(0, os.path.join(T, 'shared'))
from paths import FL_MAC_DIR, FL_WIN64_DIR, PLUGINS_DIR
import dispfix as D

EXT = os.path.join(FL_WIN64_DIR, 'extracted')
OTT = os.path.join(PLUGINS_DIR, 'ott', 'binaries', 'OTT_vst2_win64.dll')
FA = os.path.join(T, 'targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64')
KH = os.path.join(T, 'targets/kilohearts/work/winpkg/HeartCore.core_64')
SERUM = os.path.join(T, 'targets/serum2/work/Serum2_win64.vst3')
MACROOT = os.path.join(FL_MAC_DIR, 'pkg_extract', 'payload_out', 'Applications', 'FL Studio 2026.app', 'Contents', 'Resources', 'FL', 'Plugins', 'Fruity')
W = os.path.join(ICALL, 'work')


def parse_ranges(path, img):
    toks = [t for t in open(path).read().replace(',', '\n').split() if t]
    vas = [int(t.split('-')[0], 16) for t in toks]
    img.set_extra_starts(vas)
    out = []
    for t in toks:
        if '-' in t:
            lo, hi = t.split('-')
            out.append((int(lo, 16), int(hi, 16)))
        else:
            r = img.func_range(int(t, 16))
            if r:
                out.append(r)
    return sorted(set(out))


def pe_units(name, pe, ranges_file=None, nchunk=1):
    import audit_icall as A
    img = A.Image(pe)
    if ranges_file:
        rs = parse_ranges(ranges_file, img)
    else:
        rs = sorted((a, b) for a, b in img.pdata.items())
    k = max(1, nchunk)
    return [dict(sample=name, kind='pe', pe=pe, ranges=rs[i::k], rd=bool(ranges_file)) for i in range(k)]


def mac_funcs_of(path):
    sys.path.insert(0, os.path.join(T, 'plugins', 'inventory'))
    import mac_funcs as M
    d = open(path, 'rb').read()
    sl = M.x86_slice(d)
    if sl is None:
        return None
    ncmds = struct.unpack_from('<I', sl, 16)[0]
    off = 32
    text_seg = fs = None
    secs = []
    for _ in range(ncmds):
        cmd, csz = struct.unpack_from('<II', sl, off)
        if cmd == 0x19:
            segname = sl[off + 8: off + 24].rstrip(b'\0').decode()
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from('<QQQQ', sl, off + 24)
            nsect = struct.unpack_from('<I', sl, off + 64)[0]
            if segname == '__TEXT':
                text_seg = (vmaddr, fileoff)
            so = off + 72
            for _s in range(nsect):
                sn = sl[so: so + 16].rstrip(b'\0').decode()
                sg = sl[so + 16: so + 32].rstrip(b'\0').decode()
                addr, sz, foff = struct.unpack_from('<QQI', sl, so + 32)
                secs.append((sg, sn, addr, sz, foff))
                so += 80
        elif cmd == 0x26:
            fs = struct.unpack_from('<II', sl, off + 8)
        off += csz
    if not fs or not text_seg:
        return None
    tsec = [s for s in secs if s[0] == '__TEXT' and s[1] == '__text'][0]
    tva, tsz, tfo = tsec[2], tsec[3], tsec[4]
    blob = sl[fs[0]: fs[0] + fs[1]]
    i = 0
    addr = text_seg[0]
    starts = []
    while i < len(blob):
        v, i = M.uleb(blob, i)
        if v == 0:
            break
        addr += v
        starts.append(addr)
    starts = sorted(s for s in starts if tva <= s < tva + tsz)
    out = []
    for k, b in enumerate(starts):
        e = starts[k + 1] if k + 1 < len(starts) else tva + tsz
        out.append((b, sl[tfo + (b - tva): tfo + (e - tva)]))
    return out


def delphi_units():
    sys.path.insert(0, os.path.join(T, 'plugins', 'inventory'))
    import fw_overlap as F
    ids = F.delphi_blocks()
    return [dict(sample='Delphi plugin 133 DLL (全 .pdata)', kind='pe', pe='%s/block%05d_PE.bin' % (EXT, i), ranges=None) for i in ids]


def mac_units():
    out = []
    for dp, dn, fn in os.walk(MACROOT):
        for f in fn:
            p = os.path.join(dp, f)
            if os.path.islink(p) or os.path.getsize(p) < 4096:
                continue
            with open(p, 'rb') as fh:
                m = fh.read(4)
            if m in (b'\xca\xfe\xba\xbe', b'\xcf\xfa\xed\xfe'):
                out.append(dict(sample='mac Fruity Mach-O x86_64 slice (LC_FUNCTION_STARTS)', kind='mac', path=p))
    return out


def sample_units(only=None):
    U = []
    spec = [
        ('OTT F (icall closure 282 関数)', lambda: pe_units('OTT F (icall closure 282 関数)', OTT, os.path.join(W, 'route/F.txt'))),
        ('OTT F 線形 sweep', lambda: [dict(u, sample='OTT F 線形 sweep (参考)', rd=False) for u in pe_units('x', OTT, os.path.join(W, 'route/F.txt'))]),
        ('FLEngine M11 closure (7,421 関数)', lambda: pe_units('FLEngine M11 closure (7,421 関数)', EXT + '/block00031_PE.bin', os.path.join(W, 'fle_F.txt'), 4)),
        ('Fruity Balance closure (67 関数)', lambda: pe_units('Fruity Balance closure (67 関数)', EXT + '/block18983_PE.bin', os.path.join(W, 'bal_ranges.txt'))),
        ('Fresh Air SlateCore closure (131 関数)', lambda: pe_units('Fresh Air SlateCore closure (131 関数)', FA, os.path.join(W, 'fa_ranges.txt'))),
        ('KH HeartCore gain+infra (196 関数)', lambda: pe_units('KH HeartCore gain+infra (196 関数)', KH, os.path.join(W, 'kh_gain_ranges.txt'))),
        ('FLEngine_x64.dll (全 .pdata)', lambda: pe_units('FLEngine_x64.dll (全 .pdata)', EXT + '/block00031_PE.bin', None, 12)),
        ('Fresh Air SlateCore (全 .pdata)', lambda: pe_units('Fresh Air SlateCore (全 .pdata)', FA, None, 4)),
        ('KH HeartCore (全 .pdata)', lambda: pe_units('KH HeartCore (全 .pdata)', KH, None, 4)),
        ('Serum2 win64 vst3 (全 .pdata)', lambda: pe_units('Serum2 win64 vst3 (全 .pdata)', SERUM, None, 8)),
        ('Delphi plugin 133 DLL (全 .pdata)', delphi_units),
        ('mac Fruity Mach-O x86_64 slice (LC_FUNCTION_STARTS)', mac_units),
    ]
    for name, f in spec:
        if only and not any(o in name for o in only):
            continue
        U += f()
    return U


def tally(insns, C, mn_err, err_cls):
    """命令列を C に加算。"""
    nerr_here = nerr_nonnop = 0
    for ins in insns:
        C['n_ins'] += 1
        mo = ins.modrm_offset
        raw = bytes(ins.bytes)
        lay = D.layout(raw, bool(mo))
        isz = ins.imm_size
        if isz and ins.imm_offset != ins.size - isz:
            C['imm_offset_mismatch'] += 1
        if not lay.disp_size:
            if ins.disp_size:
                C['phantom_disp'] += 1
                PH.append((hex(ins.address), raw.hex(), '%s %s' % (ins.mnemonic, ins.op_str), ins.disp_size, ins.modrm_offset))
            continue
        C['disp'] += 1
        kind = 'rip' if lay.rip else ('disp32' if lay.disp_size == 4 else 'disp8' if lay.disp_size == 1 else 'moffs')
        C['n_' + kind] += 1
        if lay.rip and lay.addr32:
            C['n_addr32_rip'] += 1              # 67 prefix 付き rip 相対 (eip 相対): capstone は base=EIP になり `base == RIP` 判定を素通りする
        if lay.rip:
            for op in ins.operands:
                if op.type == CS_OP_MEM and op.mem.base == X86_REG_RIP:
                    C['rip_val_checked'] += 1
                    if op.mem.disp != struct.unpack_from('<i', raw, lay.disp_offset)[0]:
                        C['rip_val_mismatch'] += 1
                    break
        if ins.disp_size != lay.disp_size or ins.disp_offset != lay.disp_offset:
            nerr_here += 1
            C['err'] += 1
            if not ins.mnemonic.startswith('nop'):
                nerr_nonnop += 1
                C['err_nonnop'] += 1
                C['err_nonnop_' + kind] += 1
            C['err_' + kind] += 1
            cls = 'legacy66' if (0x66 in lay.prefixes and not lay.rexw) else ('vex2pp66' if lay.enc == 'vex2' and (raw[1] & 3) == 1 else 'other')
            C['cls_' + cls] += 1
            mn_err[ins.mnemonic] += 1
            err_cls[(cls, kind, lay.map if lay.enc == 'legacy' else lay.enc)] += 1
    if nerr_nonnop:
        C['funcs_with_err_nonnop'] += 1
    return nerr_here


PH = []


def run_unit(u):
    del PH[:]
    cs = Cs(CS_ARCH_X86, CS_MODE_64)
    cs.detail = True
    C = collections.Counter()
    mn_err = collections.Counter()
    err_cls = collections.Counter()
    if u['kind'] == 'pe':
        import audit_icall as A
        img = A.Image(u['pe'])
        rs = u['ranges'] if u['ranges'] is not None else sorted(img.pdata.items())
        dis = A.Disasm(img) if u.get('rd') else None
        for lo, hi in rs:
            if dis is not None:                      # 到達可能命令 (recursive descent + jump table) — audit_icall / icall_rewrite と同じ集合
                insns = [i for _, i in sorted(dis.scan_function(lo, hi, {}).items())]
            else:                                    # 線形 sweep
                code = img.read(lo, hi - lo)
                if not code:
                    continue
                insns = cs.disasm(code, lo)
            C['n_funcs'] += 1
            if tally(insns, C, mn_err, err_cls):
                C['funcs_with_err'] += 1
    else:
        fl = mac_funcs_of(u['path'])
        if fl:
            for va, code in fl:
                C['n_funcs'] += 1
                if tally(cs.disasm(code, va), C, mn_err, err_cls):
                    C['funcs_with_err'] += 1
    return u['sample'], dict(C), dict(mn_err), {'|'.join(map(str, k)): v for k, v in err_cls.items()}, PH[:5]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--jobs', type=int, default=14)
    ap.add_argument('--only', default='')
    ap.add_argument('--json', default=os.path.join(HERE, 'results', 'census.json'))
    a = ap.parse_args()
    units = sample_units([x for x in a.only.split(',') if x])
    R = collections.OrderedDict()
    PHX = {}
    MN = collections.defaultdict(collections.Counter)
    CL = collections.defaultdict(collections.Counter)
    with Pool(a.jobs) as p:
        for name, C, mn, cl, ph in p.imap_unordered(run_unit, units, chunksize=1):
            if ph:
                PHX.setdefault(name, []).extend(ph)
            R.setdefault(name, collections.Counter()).update(C)
            MN[name].update(mn)
            CL[name].update(cl)
    names = [u['sample'] for u in units]
    order = list(dict.fromkeys(names))
    print('%-52s %9s %9s %8s %8s %8s %7s %7s %9s %6s' % ('sample', 'insns', 'disp有', 'rip相対', 'rip誤り', '誤りnop除', '誤り計', '誤り率*', 'funcs誤り', 'val/imm'))
    out = {}
    for name in order:
        c = R[name]
        rate = 100.0 * c['err'] / c['disp'] if c['disp'] else 0
        print('%-52s %9d %9d %8d %8d %8d %7d %6.2f%% %4d/%-5d %d/%d' % (name, c['n_ins'], c['disp'], c['n_rip'], c['err_rip'], c['err_nonnop'], c['err'], rate,
              c['funcs_with_err'], c['n_funcs'], c['rip_val_mismatch'], c['imm_offset_mismatch']))
        out[name] = dict(counts=dict(c), error_rate_of_disp_insns=round(rate, 3),
                         rip_error_rate=round(100.0 * c['err_rip'] / c['n_rip'], 3) if c['n_rip'] else 0,
                         nonnop_error_rate=round(100.0 * c['err_nonnop'] / c['disp'], 3) if c['disp'] else 0,
                         top_mnemonics=MN[name].most_common(8), classes=dict(CL[name].most_common(12)), phantom_examples=PHX.get(name, [])[:3])
    print('* 誤り率 = (disp を持つ命令のうち capstone disp_size/offset が真値と異なる) / (disp を持つ命令)。val/imm = rip 相対 mem.disp 値誤り / imm_offset 不整合 (どちらも 0 が期待)')
    os.makedirs(os.path.dirname(a.json), exist_ok=True)
    json.dump(out, open(a.json, 'w'), indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
