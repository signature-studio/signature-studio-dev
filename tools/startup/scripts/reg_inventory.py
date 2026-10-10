#!/usr/bin/env python3
"""reg_inventory.py — CallSiteStrings.java の出力 (reg_sites.tsv) から FLEngine の TRegistry 利用 (key/value) 表を再構成。
usage: reg_inventory.py reg_sites.tsv func_index.tsv > reg_raw.csv
"""
import csv, sys, collections
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from fidx import Idx
M = {'005b1820': 'ReadStr', '005b1920': 'WriteStr', '005b19f0': 'ReadInt', '005b1b00': 'WriteInt', '005b1c10': 'ReadBool',
     '005b1c50': 'WriteBool', '005af5e0': 'OpenKey', '005af7c0': 'OpenKeyRO', '005af470': 'CreateKey', '005b03a0': 'ReadStrCur',
     '005b0350': 'WriteStrCur', '005afd50': 'DeleteValue', '005afa50': 'DeleteKey', '005af3d0': 'SetRoot', '005b0cb0': 'ValueExists',
     '005af120': 'Create', '005b19f0b': 'x'}
def lit(s):
    if not s: return None
    if s[:2] in ('A:', 'W:'): return s[2:]
    return s   # '#imm'
def main():
    ix = Idx(sys.argv[2] if len(sys.argv) > 2 else 'func_index.tsv')
    by = collections.defaultdict(list)
    with open(sys.argv[1]) as f:
        for x in csv.DictReader(f, delimiter='\t', quoting=csv.QUOTE_NONE):
            c = int(x['caller'], 16)
            if 0x5ae000 <= c < 0x5b4000: continue
            if x['callee'] in M: by[x['caller']].append(x)
    w = csv.writer(sys.stdout)
    w.writerow(['func', 'size', 'call', 'root', 'op', 'key', 'value', 'arg3', 'note'])
    for fn in sorted(by):
        root = 'HKCU?'; cur = ''
        for s in sorted(by[fn], key=lambda z: z['call']):
            op = M[s['callee']]
            rcx, rdx, r8, r9 = (lit(s[k]) for k in ('rcx', 'rdx', 'r8', 'r9'))
            key = value = arg3 = ''
            if op == 'Create': root = 'HKCU(default)'; cur = ''
            elif op == 'SetRoot':
                root = {'#80000001': 'HKCU', '#80000002': 'HKLM', '#ffffffff80000001': 'HKCU', '#ffffffff80000002': 'HKLM'}.get((rdx or '').lower(), rdx or '<dyn>'); cur = ''
            elif op in ('OpenKey', 'OpenKeyRO', 'CreateKey'): cur = rdx or '<dyn>'; key = cur
            elif op in ('ReadStrCur', 'WriteStrCur'): value = (r8 if op == 'ReadStrCur' else rdx) or '<dyn>'; key = cur
            elif op in ('ValueExists', 'DeleteValue'): value = rdx or '<dyn>'; key = cur
            elif op == 'DeleteKey': key = rdx or '<dyn>'
            elif op == 'ReadStr': key = r8 or ('' if s['r8'] == '' and False else '<cur/dyn>'); value = r9 or '<dyn>'
            elif op in ('WriteStr', 'ReadInt', 'WriteInt', 'ReadBool', 'WriteBool'):
                key = rdx or '<cur/dyn>'; value = r8 or '<dyn>'; arg3 = r9 or ''
            note = ''
            w.writerow([fn, ix.by_addr[fn]['size'], s['call'], root, op, key, value, arg3, note])
main()
