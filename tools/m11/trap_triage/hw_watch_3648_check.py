# #3648 (LD-171): hw_watch_3648.sh の出力 (work/probe3648/) を判定する。使い方: python3 hw_watch_3648_check.py [work/probe3648 のパス]
# 判定: (1) 同じ CPU・同じ環境長 (env -i 固定) の組で boot 状態 (img・heap・detail) が一致するか (cmp_img_2770.py と同じ比較)
#       (2) 陽性対照 C (15eac98) の hw 記録 (DR) と page 方式の wp 記録の 1:1 対応 (値・chg・枠・RIP 差)
#       (3) 監視 F (5ac308) の hw 記録が 0 件か
import json, re, sys, os
from collections import Counter

D = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', '..', 'liftdiff', 'work', 'probe3648')
VA = 0x15eac98


def state(tag):
    d = json.load(open(os.path.join(D, tag + '.json')))
    st = d['state']
    mem = {}
    for rva, hx in st['img']:
        a = int(rva, 16)
        for i, v in enumerate(bytes.fromhex(hx)):
            mem[a + i] = v
    m = re.search(r'0x7fff[0-9a-f]+', d.get('detail', {}).get('entry_detail', ''))
    return dict(mem=mem, heap=st.get('heap'), detail=d.get('detail'), state=st, rsp=m.group(0) if m else None, img=len(st['img']), units=d.get('units_run'), n_img_bytes=sum(len(bytes.fromhex(h)) for _, h in st['img']))


def cmp(a, b):
    A, B = state(a), state(b)
    keys = set(A['mem']) | set(B['mem'])
    diff = sum(1 for k in keys if A['mem'].get(k) != B['mem'].get(k))
    return dict(pair='%s-%s' % (a, b), rsp=(A['rsp'], B['rsp']), byte_diff=diff, heap_eq=A['heap'] == B['heap'],
                state_eq=A['state'] == B['state'], detail_eq=A['detail'] == B['detail'], units=(A['units'], B['units']),
                img=(A['img'], B['img']), img_bytes=A['n_img_bytes'])


def hw_lines(tag):
    out = []
    for l in open(os.path.join(D, tag + '.out')):
        m = re.match(r'hw rip=(0x[0-9a-f]+) dr6=(\w+) a0=(0x[0-9a-f]+) old0=(\w+) new0=(\w+) chg0=(\d) a1=(0x[0-9a-f]+) old1=(\w+) new1=(\w+) chg1=(\d)', l)
        if m:
            out.append(dict(rip=int(m.group(1), 16), dr6=int(m.group(2), 16), new0=m.group(5), chg0=int(m.group(6))))
    return out


def wp_lines(tag):
    out = []
    for l in open(os.path.join(D, tag + '.out')):
        m = re.match(r'wp case=\S+ call=\d+ rip_rva=\S+ rip=(0x[0-9a-f]+) addr=(0x[0-9a-f]+) old=\w+ new=(\w+) chg=(\d)', l)
        if m:
            out.append(dict(rip=int(m.group(1), 16), addr=int(m.group(2), 16), new=m.group(3), chg=int(m.group(4))))
    return out


def summary(tag):
    lines = open(os.path.join(D, tag + '.out')).read().splitlines()
    return [l for l in lines if l.startswith('hwsum') or l.startswith('wpsum')]


print('== (1) boot 状態の比較 (env -i 固定。rsp・img・heap・detail)')
for a, b in [('X6e1', 'X6e2'), ('X6e1', 'F6e1'), ('X6e2', 'F6e2'), ('F6e1', 'F6e2'),
             ('X7e', 'C7e'), ('X7e', 'C7e2'), ('X7e', 'Cp7e'), ('C7e', 'Cp7e'),
             ('X6c2', 'F6c2'), ('X7c2', 'C7c2'), ('X6e1', 'X6c2')]:
    r = cmp(a, b)
    print('%-16s rsp=%s/%s byte_diff=%d heap_eq=%s state_eq=%s detail_eq=%s units=%s/%s img=%s/%s bytes=%d' % (
        r['pair'], r['rsp'][0], r['rsp'][1], r['byte_diff'], r['heap_eq'], r['state_eq'], r['detail_eq'],
        r['units'][0], r['units'][1], r['img'][0], r['img'][1], r['img_bytes']))

print('== (2) 陽性対照 C (15eac98): hw 記録と page 記録の 1:1 対応')
hw, pg = hw_lines('C7e'), wp_lines('Cp7e')
print('hw=%d page=%d' % (len(hw), len(pg)))
ok, bad = 0, []
for h, p in zip(hw, pg):
    slot_ok = (p['addr'] == VA and h['dr6'] & 1) or (p['addr'] == VA - 8 and h['dr6'] & 2 and not h['dr6'] & 1)
    d = h['rip'] - p['rip']
    if slot_ok and h['new0'] == p['new'] and h['chg0'] == p['chg'] and 0 < d <= 15:
        ok += 1
    else:
        bad.append((hex(p['rip']), hex(p['addr']), hex(h['rip']), h['dr6']))
print('1:1 一致 %d/%d (枠・値・chg・0<RIP差<=15)  不一致 %s' % (ok, len(pg), bad[:3]))
print('dr6 内訳 %s' % dict(Counter(h['dr6'] for h in hw)))
print('page addr-VA 内訳 %s' % dict(Counter(p['addr'] - VA for p in pg)))
print('RIP 差 (hw - page) 内訳 %s' % dict(Counter(h['rip'] - p['rip'] for h, p in zip(hw, pg))))
print('hwsum C7e: %s | C7e2: %s | Cp7e: %s' % (summary('C7e'), summary('C7e2'), summary('Cp7e')))

print('== (3) 監視 F (5ac308) の記録')
for t in ['F6e1', 'F6e2', 'F6c2']:
    print('%s hw 行 %d | %s' % (t, len(hw_lines(t)), summary(t)))
