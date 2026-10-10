#!/usr/bin/env python3
"""impact_hash.py — D9 が関数 fingerprint (正規化ハッシュ) に与える実害の定量 (CAB-229 要件2/4)

2 つの規約を legacy (capstone disp_size を信用) と fixed (dispfix) で再計算し、stored 成果物で legacy の再現性を確認した上で差を出す:
  (1) fw_overlap 規約 (md5[:16]; 全 disp32 + 分岐 imm32 をゼロ化)  — inventory/fw_overlap.py, p0c/kernel_matrix.py
      legacy 再現性: work/fw_overlap.json と集計値が一致すること。 fixed = 修正後の fw_overlap.funcs_of そのもの
  (2) win_funcs 規約 (sha1[:12]; rip 相対 disp32 + 範囲外 call/jmp をゼロ化) — inventory/win_funcs.py, framework/fw_prep.py
      legacy 再現性: work/winfuncs/*.json の hash と全関数一致すること。 fixed = WINFUNCS_DISPFIX=1 の win_funcs.analyze
出力: results/impact_hash.json   usage: impact_hash.py [--jobs 14]
"""
import argparse, collections, hashlib, json, os, re, statistics, struct, sys
from multiprocessing import Pool
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

HERE = os.path.dirname(os.path.abspath(__file__))
PLUG = os.path.abspath(os.path.join(HERE, '..', '..', 'plugins'))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(PLUG, 'inventory'))
import fw_overlap as FO
import win_funcs as WF
WORK = os.path.join(PLUG, 'work')
TMP = os.path.join(HERE, 'work')
EXT = FO.EXT


def fo_legacy(i):
    """fw_overlap.funcs_of の修正前コピー (disp_size == 4 を信用)"""
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
            if ins.disp_size == 4:
                nm[o + ins.disp_offset:o + ins.disp_offset + 4] = b'\0\0\0\0'
            if ins.imm_size == 4 and (ins.group(1) or ins.group(2) or ins.group(7) or ins.mnemonic in ('call', 'jmp')):
                nm[o + ins.imm_offset:o + ins.imm_offset + 4] = b'\0\0\0\0'
        out.append((e - b, hashlib.md5(bytes(nm)).hexdigest()[:16]))
    return i, out


def fo_aggregate(R):
    cnt = collections.Counter()
    for o in R.values():
        for h in {x[1] for x in o}:
            cnt[h] += 1
    res = {'delphi_dlls': len(R), 'distinct_hashes': len(cnt)}
    for th in (130, 100, 66, 13):
        res['distinct_hash_in_ge_%d_dlls' % th] = sum(1 for v in cnt.values() if v >= th)
    fw = [(sum(s for s, h in o if cnt[h] >= 13), sum(s for s, h in o), sum(1 for s, h in o if cnt[h] >= 13)) for o in R.values()]
    res['fw_bytes_per_dll'] = {'min': min(f[0] for f in fw), 'median': statistics.median(f[0] for f in fw), 'max': max(f[0] for f in fw)}
    res['fw_funcs_per_dll_median'] = statistics.median(f[2] for f in fw)
    res['fw_fraction_median'] = round(statistics.median(f[0] / f[1] for f in fw), 3)
    res['nonfw_bytes_median'] = statistics.median(f[1] - f[0] for f in fw)
    bal = R[FO.BALANCE]
    sz = {h: s for s, h in bal}
    tot = sum(sz.values())
    hs = {i: {x[1] for x in o} for i, o in R.items()}
    cov = sorted((sum(sz[h] for h in sz if h in hs[i]) / tot, i) for i in R)
    res['balance_func_bytes_covered_by_other_dll'] = {
        'min': round(cov[0][0], 3), 'median': round(statistics.median(c[0] for c in cov), 3),
        'ge_0.9': sum(1 for c in cov if c[0] >= 0.9), 'ge_0.8': sum(1 for c in cov if c[0] >= 0.8)}
    return res, cnt


def wf_run(args):
    fn, fixed = args
    WF.DISPFIX = fixed
    WF.OUTD = os.path.join(TMP, 'winfuncs_fixed' if fixed else 'winfuncs_legacy')
    os.makedirs(WF.OUTD, exist_ok=True)
    WF.analyze(fn)
    return fn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--jobs', type=int, default=14)
    a = ap.parse_args()
    os.makedirs(TMP, exist_ok=True)
    os.makedirs(os.path.join(HERE, 'results'), exist_ok=True)
    ids = FO.delphi_blocks()
    out = {}
    with Pool(a.jobs) as p:
        L = dict(p.map(fo_legacy, ids))
        F = dict(p.map(FO.funcs_of, ids))
    agg_l, cnt_l = fo_aggregate(L)
    agg_f, cnt_f = fo_aggregate(F)
    stored = json.load(open(os.path.join(WORK, 'fw_overlap.json')))
    keys = [k for k in stored if k != 'balance_func_bytes_covered_by_other_dll']
    repro = all(stored[k] == agg_l[k] for k in keys)
    print('[fw_overlap 規約] legacy 再現 (stored fw_overlap.json と一致):', repro)
    nfun = sum(len(o) for o in L.values())
    chg = sum(1 for i in L for (s1, h1), (s2, h2) in zip(L[i], F[i]) if h1 != h2)
    chgb = sum(s1 for i in L for (s1, h1), (s2, h2) in zip(L[i], F[i]) if h1 != h2)
    nplug = sum(1 for i in L if any(h1 != h2 for (s1, h1), (s2, h2) in zip(L[i], F[i])))
    print('  関数 %d 中 hash が変わる %d (%.2f%%, %d bytes), 影響 DLL %d/%d' % (nfun, chg, 100.0 * chg / nfun, chgb, nplug, len(L)))
    for k in agg_l:
        if agg_l[k] != agg_f[k]:
            print('  %-42s legacy=%s fixed=%s' % (k, agg_l[k], agg_f[k]))
    out['fw_overlap_convention'] = dict(legacy_reproduces_stored=repro, funcs=nfun, funcs_hash_changed=chg, bytes_changed=chgb, dlls_affected=nplug,
                                        legacy=agg_l, fixed=agg_f)
    # (2) win_funcs 規約
    S = {r['file']: r for r in json.load(open(os.path.join(WORK, 'win_pe_scan.json')))}
    B = json.load(open(os.path.join(WORK, 'nsis_blockmap.json')))
    bids = {r['idx'] for r in B if r['kind'] == 'PE' and re.match(r'^\$V31\\Plugins\\Fruity\\(Effects|Generators)\\', r['outdir'])}
    files = sorted('block%05d_PE.bin' % i for i in bids if S['block%05d_PE.bin' % i]['machine'] == 'x64')
    with Pool(a.jobs) as p:
        p.map(wf_run, [(f, False) for f in files])
        p.map(wf_run, [(f, True) for f in files])
    diff_fn = tot = 0
    legacy_ne_stored = 0
    cl, cf = collections.Counter(), collections.Counter()
    hl, hf = {}, {}
    for f in files:
        k = f[:-7]
        st = json.load(open(os.path.join(WORK, 'winfuncs', k + '.json')))['funcs']
        lg = json.load(open(os.path.join(TMP, 'winfuncs_legacy', k + '.json')))['funcs']
        fx = json.load(open(os.path.join(TMP, 'winfuncs_fixed', k + '.json')))['funcs']
        if [x[2] for x in st] != [x[2] for x in lg]:
            legacy_ne_stored += 1
        for x, y in zip(lg, fx):
            tot += 1
            if x[2] != y[2]:
                diff_fn += 1
        hl[k] = lg
        hf[k] = fx
        if 'FP_DelphiPlug' in S[f]['hints']:
            for h in {x[2] for x in lg}:
                cl[h] += 1
            for h in {x[2] for x in fx}:
                cf[h] += 1
    print('[win_funcs 規約] legacy 再現 (stored winfuncs/*.json と全関数 hash 一致): %d/%d PE' % (len(files) - legacy_ne_stored, len(files)))
    print('  関数 %d 中 hash が変わる %d (%.2f%%)' % (tot, diff_fn, 100.0 * diff_fn / tot))
    fwl = sum(1 for h, c in cl.items() if c >= 13)
    fwf = sum(1 for h, c in cf.items() if c >= 13)
    flip_in = flip_out = 0
    fw_funcs_l = fw_funcs_f = fw_bytes_l = fw_bytes_f = 0
    for k in hl:
        for x, y in zip(hl[k], hf[k]):
            a_ = cl.get(x[2], 0) >= 13
            b_ = cf.get(y[2], 0) >= 13
            fw_funcs_l += a_
            fw_funcs_f += b_
            fw_bytes_l += x[1] * a_
            fw_bytes_f += y[1] * b_
            if not a_ and b_:
                flip_in += 1
            if a_ and not b_:
                flip_out += 1
    print('  distinct hash (Delphi): legacy=%d fixed=%d / count>=13: legacy=%d fixed=%d' % (len(cl), len(cf), fwl, fwf))
    print('  framework 判定 (>=13 DLL) の関数: legacy=%d fixed=%d (非fw→fw %d, fw→非fw %d), bytes legacy=%d fixed=%d' % (fw_funcs_l, fw_funcs_f, flip_in, flip_out, fw_bytes_l, fw_bytes_f))
    out['win_funcs_convention'] = dict(files=len(files), legacy_reproduces_stored_pe=len(files) - legacy_ne_stored, funcs=tot, funcs_hash_changed=diff_fn,
                                       distinct_hash_legacy=len(cl), distinct_hash_fixed=len(cf), ge13_legacy=fwl, ge13_fixed=fwf,
                                       fw_funcs_legacy=fw_funcs_l, fw_funcs_fixed=fw_funcs_f, flip_nonfw_to_fw=flip_in, flip_fw_to_nonfw=flip_out,
                                       fw_bytes_legacy=fw_bytes_l, fw_bytes_fixed=fw_bytes_f)
    json.dump(out, open(os.path.join(HERE, 'results', 'impact_hash.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
