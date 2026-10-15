# #2770: 監視付き run と監視なし run の boot 状態 (img・heap) を比べる。使い方: python3 cmp_img_2770.py <state_a.json> <state_b.json>
# 出力: entry rsp の一致、img の要素数・byte 数、片方にしか無い要素 (開始 RVA で比較) の数、heap の一致、byte 差の一覧。
import json, re, sys

def load(p):
    d = json.load(open(p))
    st = d['state']
    m = re.search(r'0x7fff[0-9a-f]+', d.get('detail', {}).get('entry_detail', ''))
    mem, starts, nbytes = {}, set(), 0
    for rva, hx in st['img']:
        a = int(rva, 16); b = bytes.fromhex(hx)
        starts.add(a); nbytes += len(b)
        for i, v in enumerate(b):
            mem[a + i] = v
    return st, mem, starts, nbytes, (m.group(0) if m else None)

def main():
    a_path, b_path = sys.argv[1], sys.argv[2]
    sa, ma, ea, na, ra = load(a_path)
    sb, mb, eb, nb, rb = load(b_path)
    keys = sorted(set(ma) | set(mb))
    diff = [k for k in keys if ma.get(k) != mb.get(k)]
    heap_eq = sa.get('heap') == sb.get('heap')
    if ra is None or rb is None:
        rsp_note = 'UNKNOWN: not comparable'
    elif ra == rb:
        rsp_note = 'same'
    else:
        rsp_note = 'DIFFERENT: not comparable'
    print('%s vs %s: entry_rsp %s/%s (%s)' % (a_path.split('/')[-1], b_path.split('/')[-1], ra, rb, rsp_note))
    print('img elements %d/%d, bytes %d/%d, only_in_a=%d only_in_b=%d' % (
        len(sa['img']), len(sb['img']), na, nb, len(ea - eb), len(eb - ea)))
    print('byte_diff=%d heap_eq=%s heap_used=%s/%s hw=%s/%s' % (
        len(diff), heap_eq, sa.get('heap_used'), sb.get('heap_used'), sa.get('hw'), sb.get('hw')))
    for k in diff[:40]:
        print('  rva=%#x a=%s b=%s' % (k, '%02x' % ma[k] if k in ma else '--', '%02x' % mb[k] if k in mb else '--'))

main()
