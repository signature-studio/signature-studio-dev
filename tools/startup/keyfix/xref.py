#!/usr/bin/env python3
"""xref.py — callee への call site と、site 直前の引数積み (lea/mov rip-rel) の文字列抽出"""
import re, collections
import feparse as F
import fnindex

RE_RIP = re.compile(r'\[rip ([+-]) (0x[0-9a-f]+)\]')


def disasm_func_at(va, max_bytes=0x6000):
    """VA を含む関数を逆アセンブル (fnindex で範囲を得る; 無ければ前後 0x1000)"""
    f = fnindex.func_of(va)
    if f:
        s, e = f
        return F.disasm_func(s, min(e - s + 0x10, max_bytes)), s, e
    return F.disasm_func(va - 0x400, max_bytes), va - 0x400, None


def str_at(va):
    """Delphi 文字列: lea 先 VA から utf-8/utf-16 を試す (header 越しも探索)"""
    st = F.StrTab()
    e = st.exact(va)
    if e is not None:
        return e
    # header 経由: VA が data-16 の可能性
    for delta in (0x10, 0x0c, 8, 0x14, 0x18):
        e = st.exact(va + delta) if delta else None
        if e:
            return e
    k = st.at(va)
    if k:
        kind, text, off, sva = k
        return text[off:] if off < len(text) else None
    return None


def arg_strings_for_sites(callee, window=40):
    """callee への各 call site について、site 直前の rip 相対 lea/mov で積まれた文字列候補を返す
    returns [(site_va, {reg: str_or_None, imms: [...]}), ...]
    """
    g = F.build_call_graph()
    sites = sorted(g.get(callee, []))
    out = []
    cache = {}
    for site in sites:
        f = fnindex.func_of(site)
        if not f:
            out.append((site, {}))
            continue
        fs = f[0]
        if fs not in cache:
            cache[fs] = disasm_func_at(fs)[0]
        ins_list = cache[fs]
        idx = next((i for i, x in enumerate(ins_list) if x.address == site), None)
        if idx is None:
            out.append((site, {}))
            continue
        lo = max(0, idx - window)
        found = {}
        for x in ins_list[lo:idx]:
            m = RE_RIP.search(x.op_str)
            if m and x.mnemonic in ('lea', 'mov'):
                disp = int(m.group(2), 16) * (1 if m.group(1) == '+' else -1)
                tgt = x.address + x.size + disp
                s = str_at(tgt)
                if s:
                    # 対象レジスタ
                    mm = re.match(r'(\w+),', x.op_str)
                    reg = mm.group(1) if mm else '?'
                    found[reg] = s
        out.append((site, found))
    return out


if __name__ == '__main__':
    import sys
    callee = int(sys.argv[1], 16)
    for site, strs in arg_strings_for_sites(callee):
        print(hex(site), strs)
