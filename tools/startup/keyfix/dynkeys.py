#!/usr/bin/env python3
"""dynkeys.py — 動的キー ('prefix' + [globalobj+field]) の構成を抽出し、field への書込 site を全走査。

CAB-213: LoadSettings/SaveSettings 等の key=None op を解決するための道具。
  1) op site 直前の UStrCat3(prefix_lit, [G+off]) を検出
  2) `mov [rax+off], reg` (rax==[G] chain) の全 site を列挙し、reg に流込む文字列定数を取得
"""
import re, collections
import feparse as F
import fnindex
from xref import str_at

RE_RIP = re.compile(r'\[rip ([+-]) (0x[0-9a-f]+)\]')
USTR_ASG = 0x413480
USTR_CAT3 = 0x414c70

_text = None
_ins_cache = {}


def all_ins():
    global _text
    if _text is None:
        F.load()
        tva, tsize = F.text_range()
        off = F.va2off(tva)
        _text = list(F.md().disasm(F._RAW[off:off + tsize], tva))
    return _text


def func_ins(fva):
    if fva not in _ins_cache:
        f = fnindex.func_of(fva)
        _ins_cache[fva] = F.disasm_func(f[0], f[1] - f[0] + 0x10) if f else []
    return _ins_cache[fva]


def cat_sites():
    """全 UStrCat3 呼出: [(site, dest_desc, s1, s2_desc)] — s2_desc は ('glob', G, off) / ('str', s) / None"""
    out = []
    for i, x in enumerate(all_ins()):
        if x.mnemonic != 'call' or x.op_str != hex(USTR_CAT3):
            continue
        # 逆方向に lea rcx / lea rdx / (r8 の由来) を探す
        window = all_ins()[max(0, i - 12):i]
        dest = s1 = None
        r8 = None
        for y in window:
            if y.op_str.startswith('rcx, '):
                dest = y.op_str.split('rcx, ')[1]
            if y.op_str.startswith('rdx, '):
                v = y.op_str.split('rdx, ')[1]
                m = RE_RIP.search(v)
                if m:
                    disp = int(m.group(2), 16) * (1 if m.group(1) == '+' else -1)
                    s1 = str_at(y.address + y.size + disp)
            if y.op_str.startswith('r8, '):
                r8 = y.op_str.split('r8, ')[1]
        if dest and s1 and r8:
            out.append((x.address, dest, s1, r8))
    return out


def parse_r8(desc):
    """'qword ptr [rax + 0x10]' のように、rax が [rip+G] 由来の想定で (G, off) を推定"""
    m = re.match(r'qword ptr \[(\w+) \+ (0x[0-9a-f]+)\]$', desc)
    if not m:
        m2 = re.match(r'qword ptr \[(\w+)\]$', desc)
        if m2:
            return (m2.group(1), 0)
        return None
    return (m.group(1), int(m.group(2), 16))


def glob_origin(ins_list, idx, reg):
    """idx までに reg が [rip+G] から来たか探索 (後方 12 命令)"""
    for y in ins_list[max(0, idx - 12):idx]:
        if y.op_str.startswith(reg + ', qword ptr [rip'):
            m = RE_RIP.search(y.op_str)
            disp = int(m.group(2), 16) * (1 if m.group(1) == '+' else -1)
            return y.address + y.size + disp
        if y.op_str.startswith(reg + ', '):
            src = y.op_str.split(', ')[1]
            m = re.match(r'qword ptr \[(\w+)\]$', src)
            if m and m.group(1) != reg:
                r = glob_origin(ins_list, idx, m.group(1))
                if r:
                    return r
            if m and m.group(1) == reg:
                continue
    return None


if __name__ == '__main__':
    cs = cat_sites()
    print('UStrCat3 sites:', len(cs))
    for site, dest, s1, r8 in cs:
        if not s1 or 'General\\' not in s1[:16]:
            continue
        f = fnindex.func_of(site)
        ins_list = func_ins(f[0]) if f else []
        idx = next((i for i, x in enumerate(ins_list) if x.address == site), None)
        g = None
        pr = parse_r8(r8)
        if pr:
            g = glob_origin(ins_list, idx, pr[0])
        print('0x%x in 0x%x: %s := %r + [%s+%s] (G=%s)' % (
            site, f[0] if f else 0, dest.strip(), s1[:24], pr[0] if pr else '?', hex(pr[1]) if pr else '?', hex(g) if g else '?'))
