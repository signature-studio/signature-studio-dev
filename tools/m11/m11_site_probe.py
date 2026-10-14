#!/usr/bin/env python3
"""#1847: _CopyArray (function_416db0) の呼出し元 site 別計測 probe (計測専用, M11_INSTR_K12=1 の build でのみ使う).

使い方:
  python3 m11_site_probe.py work/boot_final3.ll work/boot_final3.probe.ll --sites work/s1847/sites.json
  (= 入力 IR の function_416db0 呼出しの直前に `store volatile i32 <site>, ptr @m11_site_cur` を入れる)
  python3 m11_site_probe.py work/boot_final3.ll /dev/null --reach work/s1847/out.json --sites work/s1847/sites.json
  (= survey 結果 (out.json) を入力に、site を含む関数から直接 call で辿れる unit を静的に数える)

site 番号は IR 上の出現順 (1..N)。m11_ov.c の `[CA_KIND] site=<n>` と対応する。
静的到達は直接 call のみ (indirect call は辿らない) なので上界。
"""
import json, re, sys, collections, argparse

TARGET = 'function_416db0'
CALL_RE = re.compile(r'call [^@]*@' + TARGET + r'\(')
DEF_RE = re.compile(r'^define .*@(\w+)\(')
IMAGE_BASE = 0x400000


def insert_probes(src, dst):
    lines = open(src).read().split('\n')
    out, sites, fn = [], {}, None
    n = 0
    for line in lines:
        m = DEF_RE.match(line)
        if m:
            fn = m.group(1)
        elif line.startswith('}'):
            fn = None
        if fn is not None and CALL_RE.search(line):
            n += 1
            ind = re.match(r'^ *', line).group(0)
            out.append('%sstore volatile i32 %d, ptr @m11_site_cur' % (ind, n))
            sites[n] = fn
        out.append(line)
    text = '\n'.join(out)
    text = re.sub(r'(?m)^(target datalayout = .*)$', r'\1\n@m11_site_cur = external global i32', text, count=1)
    if dst != '/dev/null':
        open(dst, 'w').write(text)
    return sites


def static_reach(ir_path, sites, units):
    calls = collections.defaultdict(set)
    fn = None
    for line in open(ir_path).read().split('\n'):
        m = DEF_RE.match(line)
        if m:
            fn = m.group(1); continue
        if line.startswith('}'):
            fn = None; continue
        if fn is None:
            continue
        for c in re.findall(r'call [^@]*@(\w+)\(', line):
            calls[fn].add(c)
    res = collections.defaultdict(list)
    for u in units:
        if u['kind'] == 'noproc':
            continue
        entry = 'function_%x' % (int(u['va'], 16) + IMAGE_BASE)
        seen, st = {entry}, [entry]
        while st:
            f = st.pop()
            for c in calls.get(f, ()):
                if c not in seen:
                    seen.add(c); st.append(c)
        for s, f in sites.items():
            if f in seen:
                res[s].append(u['unit'])
    return res


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('dst')
    ap.add_argument('--sites', required=True, help='site 表 (json) の出力先')
    ap.add_argument('--reach', help='survey 結果 json (指定時は静的到達も出す)')
    a = ap.parse_args()
    sites = insert_probes(a.src, a.dst)
    json.dump({str(k): v for k, v in sites.items()}, open(a.sites, 'w'), indent=1)
    print('sites:', len(sites), json.dumps(sites))
    if a.reach:
        res = static_reach(a.src, sites, json.load(open(a.reach)))
        for s in sorted(sites):
            print('site', s, sites[s], 'static-reachable units:', len(res[s]), sorted(res[s])[:12])
