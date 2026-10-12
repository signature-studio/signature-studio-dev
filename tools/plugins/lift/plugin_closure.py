#!/usr/bin/env python3
"""プラグイン DSP エントリ (vtable override) からの直接呼出クロージャを求め、RetDec --select-ranges 用 ranges を出力する。

  - エントリ = win_abi.json の impl スロット (framework 既定実装 = 全 DLL 共通ハッシュは除外)
  - BFS: `call/jmp rel32` で到達する .pdata 関数を辿る。ハッシュが framework 共通 (13 DLL 以上) の関数は
    **frontier** として記録するのみ (P0 で 1 回だけ lift する共有 lib 側)
  - 間接呼出: `call [reg+disp]` (仮想/関数ポインタ), `call [rip+IAT]` (Win32) を件数のみ記録
出力: work/closure/<block>.json と ranges (<block>.ranges.txt)、work/closure_summary.json。
使い方: plugin_closure.py <block番号> ...   |  --all
"""
import os, sys, json, struct, re, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared'))
from paths import FL_WIN64_DIR
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_REG_RIP

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
WORK = os.path.join(ROOT, 'work')
EXT = os.path.join(FL_WIN64_DIR, 'extracted')
FWTHR = 13


def fw_counts():
    cache = os.path.join(WORK, 'fw_hash_counts.json')
    if os.path.exists(cache):
        return json.load(open(cache))
    S = {r['file']: r for r in json.load(open(os.path.join(WORK, 'win_pe_scan.json')))}
    cnt = collections.Counter()
    FD = os.path.join(WORK, 'winfuncs')
    for f in os.listdir(FD):
        k = f[:-5]
        if 'FP_DelphiPlug' not in S[k + '_PE.bin']['hints']:
            continue
        j = json.load(open(os.path.join(FD, f)))
        for h in {x[2] for x in j['funcs']}:
            cnt[h] += 1
    json.dump(cnt, open(cache, 'w'))
    return cnt


def closure(block, cnt, abi_all):
    k = 'block%05d' % block
    fn = k + '_PE.bin'
    d = open(os.path.join(EXT, fn), 'rb').read()
    pe = pefile.PE(data=d, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0].get_data()
    ends = {}
    for i in range(len(pd) // 12):
        b, e, u = struct.unpack_from('<III', pd, 12 * i)
        if b and not (u & 1):
            ends[b] = e
    text = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
    tb, tv = text.get_data(), text.VirtualAddress
    fj = json.load(open(os.path.join(WORK, 'winfuncs', k + '.json')))
    hmap = {x[0]: x[2] for x in fj['funcs']}
    abi = abi_all[fn]
    entries = []
    for slot, va in abi.get('impl', {}).items():
        rva = int(va, 16) - base
        h = hmap.get(rva)
        if h is not None and cnt.get(h, 0) >= FWTHR:
            continue  # framework 既定実装
        entries.append((slot, rva))
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    seen, fw_front = {}, {}
    ind_virtual = ind_ptr = iat_calls = 0
    q = [rva for _, rva in entries]
    while q:
        f = q.pop()
        if f in seen or f not in ends:
            continue
        h = hmap.get(f)
        if h is not None and cnt.get(h, 0) >= FWTHR:
            fw_front[f] = ends[f] - f
            continue
        seen[f] = ends[f] - f
        for ins in md.disasm(tb[f - tv: ends[f] - tv], base + f):
            mn = ins.mnemonic
            if mn in ('call', 'jmp') and ins.operands:
                o = ins.operands[0]
                if o.type == 2:  # IMM
                    t = o.imm - base
                    if t in ends and not (f <= t < ends[f]):
                        q.append(t)
                elif o.type == X86_OP_MEM:
                    if o.mem.base == X86_REG_RIP:
                        iat_calls += 1
                    elif mn == 'call':
                        if o.mem.disp == 0 and o.mem.index == 0:
                            ind_ptr += 1
                        else:
                            ind_virtual += 1
                elif mn == 'call':
                    ind_ptr += 1
    ranges = ['0x%x-0x%x' % (base + f, base + f + seen[f] - 1) for f in sorted(seen)]
    return {'block': block, 'entries': {s: hex(base + r) for s, r in entries},
            'unique_funcs': len(seen), 'unique_bytes': sum(seen.values()),
            'framework_frontier_funcs': len(fw_front), 'framework_frontier_bytes': sum(fw_front.values()),
            'indirect_vcall': ind_virtual, 'indirect_ptr_or_vt0': ind_ptr, 'iat_calls': iat_calls,
            'ranges': ranges, 'frontier': sorted(hex(base + r) for r in fw_front)}


def main():
    cnt = fw_counts()
    abi_all = {r['file']: r for r in json.load(open(os.path.join(WORK, 'win_abi.json')))}
    blocks = [int(f[5:10]) for f, a in abi_all.items() if 'impl' in a]
    want = [int(a) for a in sys.argv[1:] if a.isdigit()]
    if want:
        blocks = want
    os.makedirs(os.path.join(WORK, 'closure'), exist_ok=True)
    out = {}
    for b in blocks:
        try:
            r = closure(b, cnt, abi_all)
        except Exception as e:
            print('block', b, 'ERR', e)
            continue
        out[b] = {k: v for k, v in r.items() if k not in ('ranges', 'frontier')}
        json.dump(r, open(os.path.join(WORK, 'closure', 'block%05d.json' % b), 'w'))
        open(os.path.join(WORK, 'closure', 'block%05d.ranges.txt' % b), 'w').write(','.join(r['ranges']))
    if not want:
        json.dump(out, open(os.path.join(WORK, 'closure_summary.json'), 'w'))
    print('closures', len(out))
    for b in blocks[:3]:
        if b in out:
            print(b, out[b])


if __name__ == '__main__':
    main()
