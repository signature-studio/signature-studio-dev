"""LD-67 (#1906): 既定 build (ott_old) と計装 build (ott_old_blk) の 6 関数 × vm0/u16 の case を比較する。
使い方: python3 compare_blk.py <def.json> <blk.json>
判定: outcome・diffs・wasm_status・wasm の rax/x0 が case ごとに一致するか (差 0 で PASS)。"""
import json, sys

def load(p):
    return {f['function']['va']: f for f in json.load(open(p))}

def key(c):
    w = c.get('raw', {}).get('wasm', {})
    return (c.get('outcome'), c.get('wasm_status'), json.dumps(c.get('diffs'), sort_keys=True), w.get('rax'), w.get('x0'))

def main():
    d, b = load(sys.argv[1]), load(sys.argv[2])
    n = bad = 0
    for va in d:
        for cd, cb in zip(d[va]['cases'], b[va]['cases']):
            n += 1
            same = key(cd) == key(cb)
            bad += not same
            print('%s %-5s %-10s %-10s %s blk=%d' % (va, cd['pattern'], cd['outcome'], cb['outcome'],
                  'SAME' if same else 'DIFF', len(cb.get('raw', {}).get('wasm', {}).get('blk') or [])))
    print('cases=%d diff=%d' % (n, bad))
    sys.exit(1 if bad else 0)

if __name__ == '__main__':
    main()
