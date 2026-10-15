# #2770: 監視付き run と監視なし run の boot 状態 (img・heap) を比べる。使い方: python3 cmp_img_2770.py <state_a.json> <state_b.json>
import json, sys

def load(p):
    st = json.load(open(p))['state']
    mem = {}
    for rva, hx in st['img']:
        a = int(rva, 16)
        b = bytes.fromhex(hx)
        for i, v in enumerate(b):
            mem[a + i] = v
    return st, mem

def main():
    a_path, b_path = sys.argv[1], sys.argv[2]
    sa, ma = load(a_path)
    sb, mb = load(b_path)
    keys = sorted(set(ma) | set(mb))
    diff = [k for k in keys if ma.get(k) != mb.get(k)]
    heap_eq = sa.get('heap') == sb.get('heap')
    print('%s vs %s: img_runs=%d/%d img_bytes=%d/%d byte_diff=%d heap_eq=%s heap_used=%s/%s hw=%s/%s' % (
        a_path.split('/')[-1], b_path.split('/')[-1], len(sa['img']), len(sb['img']), len(ma), len(mb), len(diff),
        heap_eq, sa.get('heap_used'), sb.get('heap_used'), sa.get('hw'), sb.get('hw')))
    for k in diff[:40]:
        print('  rva=%#x a=%s b=%s' % (k, '%02x' % ma[k] if k in ma else '--', '%02x' % mb[k] if k in mb else '--'))

main()
