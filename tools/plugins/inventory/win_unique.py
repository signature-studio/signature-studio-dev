#!/usr/bin/env python3
"""win_funcs の出力を cross-plugin 集計し、framework / 共有 / plugin 固有 に分類する。

出力: work/win_unique.json  {block: {nfunc, bytes, fw_bytes, shared_bytes, uniq_bytes, uniq_funcs,
        uniq_fp, uniq_cvt, uniq_x87, uniq_imports{...}}}
Delphi プラグイン DLL (FP_DelphiPlug を含むもの) 同士で比較した framework = ハッシュが 10% 以上の DLL に出現。
engine 等の非 Delphi PE は「固有」とみなす (比較対象が無いため全関数が固有)。
"""
import os, json, collections, sys, re

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, '..', 'work')
FD = os.path.join(WORK, 'winfuncs')


def main():
    S = {r['file']: r for r in json.load(open(os.path.join(WORK, 'win_pe_scan.json')))}
    D = {}
    for f in sorted(os.listdir(FD)):
        D[f[:-5]] = json.load(open(os.path.join(FD, f)))
    delphi = [k for k in D if 'FP_DelphiPlug' in S[k + '_PE.bin']['hints']]
    print('delphi plugin DLLs', len(delphi), 'of', len(D))
    cnt = collections.Counter()
    for k in delphi:
        for h in {x[2] for x in D[k]['funcs']}:
            cnt[h] += 1
    n = len(delphi)
    FW = max(10, int(0.10 * n))
    print('framework threshold >=', FW)
    out = {}
    for k, d in D.items():
        is_d = k in delphi
        fw = sh = un = 0
        ufn = ufp = ucvt = ux87 = 0
        uimps = collections.Counter()
        fwimps = collections.Counter()
        tot = 0
        ulist = []
        for (rva, sz, h, ni, nfp, ncvt, nx87, imps) in d['funcs']:
            tot += sz
            c = cnt.get(h, 0) if is_d else 0
            if is_d and c >= FW:
                fw += sz
                for i in imps:
                    fwimps[i] += 1
            elif is_d and c > 2:
                sh += sz
            else:
                un += sz
                ufn += 1
                ufp += nfp
                ucvt += ncvt
                ux87 += nx87
                for i in imps:
                    uimps[i] += 1
                ulist.append((rva, sz, nfp))
        out[k] = {'delphi': is_d, 'nfunc': d['nfunc'], 'bytes': tot, 'fw_bytes': fw, 'shared_bytes': sh,
                  'uniq_bytes': un, 'uniq_funcs': ufn, 'uniq_fp': ufp, 'uniq_cvt': ucvt, 'uniq_x87': ux87,
                  'uniq_imports': dict(uimps), 'dll_strings': d['dll_strings']}
    json.dump(out, open(os.path.join(WORK, 'win_unique.json'), 'w'))
    # preview
    rows = sorted(out.items(), key=lambda kv: kv[1]['uniq_bytes'])
    for k, v in rows[:25]:
        print(k, v['delphi'], v['nfunc'], v['bytes'], 'fw', v['fw_bytes'], 'sh', v['shared_bytes'], 'uniq', v['uniq_bytes'], v['uniq_funcs'], 'fp', v['uniq_fp'])


if __name__ == '__main__':
    main()
