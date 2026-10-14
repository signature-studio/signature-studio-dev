#!/usr/bin/env python3
"""gain_manual_dump.py の出力 (人手判定の材料) を、TSV と RTTI の値だけで独立に照合する (KH-35, #2176)。

判定 (行ごと):
  root 行: root_class の vtable のいずれかの slot が 0x180000000 + func_rva (rtti_walk.py の出力)
  非 root 行: parent_rva が TSV 内、call_site が親の [parent, parent+size) 内、
              dump の `>>` 行の命令が call/jmp で遷移先が 0x180000000 + func_rva
usage: gain_manual_check.py <gain_manual_dump.txt> <gain_before_160.tsv> <rtti_vtables.json>
出力: 1 行 JSON。bad が空なら全行 OK。
"""
import csv, json, re, sys

IMAGE_BASE = 0x180000000


def parse_dump(path):
    blocks, cur = [], None
    for line in open(path):
        m = re.match(r'#(\d+) (0x[0-9a-f]+) size=(\d+) root=(\S+)', line)
        if m:
            cur = {'i': int(m.group(1)), 'f': int(m.group(2), 16), 'lines': []}
            blocks.append(cur)
        elif cur is not None:
            cur['lines'].append(line.rstrip('\n'))
    return blocks


def main(dumpp, tsvp, rttip):
    rows = list(csv.DictReader(open(tsvp), delimiter='\t'))
    by_rva = {int(r['func_rva'], 16): r for r in rows}
    rtti = json.load(open(rttip))
    blocks = parse_dump(dumpp)
    res = {'rows': len(blocks), 'roots': 0, 'root_slot_ok': 0, 'nonroot': 0, 'edge_ok': 0, 'bad': []}
    for b in blocks:
        r = rows[b['i'] - 1]
        f = int(r['func_rva'], 16)
        if b['f'] != f:
            res['bad'].append(b['i'])
            continue
        if not r['parent_rva']:
            res['roots'] += 1
            va = '0x%x' % (IMAGE_BASE + f)
            ok = any(s == va for ent in rtti.get(r['root_class'], []) for s in ent['slots'])
            res['root_slot_ok'] += ok
            if not ok:
                res['bad'].append(b['i'])
            continue
        res['nonroot'] += 1
        p, c = int(r['parent_rva'], 16), int(r['call_site_rva'], 16)
        prow = by_rva.get(p)
        ok = prow is not None and p <= c < p + int(prow['size'])
        hit = [re.match(r'\s*>> (0x[0-9a-f]+): (\w+) (0x[0-9a-f]+)$', x) for x in b['lines']]
        hit = [m for m in hit if m]
        ok = ok and len(hit) == 1 and int(hit[0].group(1), 16) == c \
            and hit[0].group(2) in ('call', 'jmp') and int(hit[0].group(3), 16) == IMAGE_BASE + f
        res['edge_ok'] += ok
        if not ok:
            res['bad'].append(b['i'])
    print(json.dumps(res))


if __name__ == '__main__':
    main(*sys.argv[1:4])
