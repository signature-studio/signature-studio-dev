#!/usr/bin/env python3
"""regapi.py — TRegistry メソッド実装 (0x5ae000-0x5b4000) の意味分類。

各メソッドが呼ぶ Reg* thunk と、全引数 (Delphi register ABI: Self=rcx, s1=rdx, s2=r8, s3=r9) を
逆アセンブルから抽出する。CAB-213 の key 解析の前提 (どの引数がキー文字列か) を確定する。
"""
import re, collections
import feparse as F
from regcalls import reg_iat_map, RE_RIP, build

WORK = __file__.rsplit('/', 1)[0] + '/work'


def method_semantics():
    """{method_va: {'apis': {api: n}, 'nargs': int, 'calls': [...]}}"""
    fb = build()
    apis_by_func = collections.defaultdict(collections.Counter)
    for fs, d in fb.items():
        for api, sites in d.items():
            apis_by_func[int(fs, 16)] += collections.Counter({api: len(sites)})
    # thunk → api
    F.load()
    reg_iat = reg_iat_map()
    tva, tsize = F.text_range()
    off = F.va2off(tva)
    data = F._RAW[off:off + tsize]
    thunk = {}
    for ins in F.md().disasm(data, tva):
        m = RE_RIP.search(ins.op_str)
        if not m or ins.mnemonic != 'jmp':
            continue
        disp = int(m.group(2), 16) * (1 if m.group(1) == '+' else -1)
        tgt = ins.address + ins.size + disp
        api = reg_iat.get(tgt)
        if api:
            thunk[ins.address] = api
    g = F.build_call_graph()
    out = {}
    for mva in range(0x5ae000, 0x5b4000):
        sites = g.get(mva, [])
        if not sites:
            continue
        apis = collections.Counter()
        calls = []
        for site in sites:
            f = fnindex.func_of(site)
            if not f or f[0] != mva:
                continue
            calls.append(site)
        for site in calls:
            pass
        # 逆アセンブル本体から call 先を分類
        f = fnindex.func_of(mva)
        if not f:
            continue
        ins_list = F.disasm_func(f[0], f[1] - f[0] + 0x10)
        for x in ins_list:
            if x.mnemonic == 'call' and x.op_str.startswith('0x'):
                t = int(x.op_str, 16)
                api = thunk.get(t)
                if api:
                    apis[api] += 1
        out[mva] = {'apis': dict(apis), 'size': f[1] - f[0], 'ncallsites': len(calls)}
    return out


if __name__ == '__main__':
    import fnindex, json, os, sys
    out = method_semantics()
    jf = os.path.join(WORK, 'treg_methods.json')
    json.dump({hex(k): v for k, v in out.items()}, open(jf, 'w'), indent=0)
    for k in sorted(out):
        v = out[k]
        print('%x size=%-5d apis=%s' % (k, v['size'], v['apis']))
