#!/usr/bin/env python3
"""fidx.py — func_index.tsv (CallTree.java 出力) の索引ヘルパ。thunk(API名)→caller 逆引き、文字列→関数検索。"""
import csv, sys, collections, re
def load(path='func_index.tsv'):
    rows = []
    with open(path) as f:
        r = csv.reader(f, delimiter='\t', quoting=csv.QUOTE_NONE)
        hdr = next(r)
        for x in r:
            if len(x) < 7: x += [''] * (7 - len(x))
            d = dict(zip(hdr, x)); d['callees'] = [c for c in d['callees'].split(',') if c]
            d['strs'] = [s for s in d['strings'].split(' | ') if s]
            rows.append(d)
    return rows
class Idx:
    def __init__(self, path='func_index.tsv'):
        self.rows = load(path)
        self.by_addr = {r['addr']: r for r in self.rows}
        self.thunk = collections.defaultdict(list)   # api name -> [thunk addr]
        for r in self.rows:
            if int(r['size']) <= 8 and not r['name'].startswith('FUN_'):
                self.thunk[r['name']].append(r['addr'])
        self.callers = collections.defaultdict(list)
        for r in self.rows:
            for c in r['callees']: self.callers[c].append(r['addr'])
    def api_callers(self, api):
        out = []
        for a in self.thunk.get(api, []): out += self.callers.get(a, [])
        return sorted(set(out))
    def find_str(self, pat, flags=re.I):
        rx = re.compile(pat, flags)
        out = []
        for r in self.rows:
            for s in r['strs']:
                if rx.search(s): out.append((r['addr'], r['name'], int(r['size']), s))
        return out
if __name__ == '__main__':
    ix = Idx()
    cmd = sys.argv[1]
    if cmd == 'api':
        for a in sys.argv[2:]:
            print(a, [(c, ix.by_addr[c]['size']) for c in ix.api_callers(a)])
    elif cmd == 'str':
        for t in ix.find_str(sys.argv[2]): print('%s\t%s\t%d\t%s' % t)
