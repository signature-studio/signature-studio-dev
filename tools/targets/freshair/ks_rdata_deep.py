#!/usr/bin/env python3
"""value 17 関数の差分語を、指す先の window まで辿って 3 分類する (FA-35 #2743)。

入口: ks_rdata_class.py の cls == value の関数について、rip 参照 (32 B) を 8 B 語の位置ごとに SC/KH で対にし、
内容が違う語を判定する。語 p (SC) と q (KH) の判定 judge(p, q, depth):
  const  : 両側とも非ポインタ。定数値の差 (kind = text / dbl / int)
  ポインタ対 (両側とも sec_of が解決し、同じ .rdata 内): 指す先の window (既定 64 B = 8 語) を語単位で比べる。
           差の語は judge を再帰 (深さ上限 depth)。全語が same / placement なら placement、どれかが content なら content。
  undet  : 分類不能 (ptr_vs_const / sec_* 不一致・.rdata 外 / depth 上限 / oob)
top-level の対応: const → 定数値の差、placement → 配置差、content → 参照先の内容差 (葉の理由を記録)、undet → 分類不能。
関数の用途: ident.json の process 対応 (process 本体)・vtable slot・closure (4 root) の所属・直接呼び出し元 (union closure 内) から照合する。
usage: ks_rdata_deep.py <HeartCore.core_64> <SlateCore.core_64> <ks_rdata_class.json> <ident.json> <out.json> [window=64] [depth=3]
注: 指す先の 8 B 語の RVA 候補判定は ks_rdata_value.sec_of と同じ (RVA か定数かは未判定)。
"""
import sys, os, json, struct, collections, tempfile, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ks_identity import Pe, vtables
from ks_closure_share import rip_data, closure, ROOTS
from ks_rdata_value import sec_of, is_text


def u64(b):
    return struct.unpack('<Q', b)[0]


def as_dbl(v):
    return struct.unpack('<d', struct.pack('<Q', v))[0]


def printable_run(v, n=3):
    """8 B 語に印字可能 ASCII の連続 n 文字以上を含むか (制御バイトの混在を含む文字列断片)。"""
    run = best = 0
    for c in struct.pack('<Q', v):
        run = run + 1 if 32 <= c < 127 else 0
        best = max(best, run)
    return best >= n


def const_kind(p, q):
    if is_text(p) or is_text(q):
        return 'text'
    if printable_run(p) or printable_run(q):
        return 'text_mixed'
    dp, dq = as_dbl(p), as_dbl(q)
    ok = all(v == v and abs(v) != float('inf') and v != 0 for v in (dp, dq))
    return 'dbl' if ok and dp * dq > 0 else 'int'


def judge(sc, kh, p, q, d, win):
    """(label, info, p, q)。label は same / placement / content / const / undet。
    content の info は最深の葉 (label, 理由, 葉の SC 語, KH 語)。const の info は kind、undet の info は理由。"""
    if p == q:
        return 'same', None, p, q
    P, Q = sec_of(sc, p), sec_of(kh, q)
    if P is not None and Q is not None:
        if P[0] != Q[0] or P[0] != '.rdata':
            return 'undet', 'sec_%s/%s' % (P[0], Q[0]), p, q
        if d == 0:
            return 'undet', 'depth', p, q
        ts, tk = sc.rva_bytes(P[2], win), kh.rva_bytes(Q[2], win)
        if len(ts) < win or len(tk) < win:
            return 'undet', 'oob', p, q
        leaf = None
        for i in range(0, win, 8):
            x, y = u64(ts[i:i + 8]), u64(tk[i:i + 8])
            if x == y:
                continue
            lab, info, _, _ = judge(sc, kh, x, y, d - 1, win)
            if lab in ('same', 'placement'):
                continue
            if leaf is None:
                leaf = info if lab == 'content' else (lab, info, x, y)
        return ('placement', None, p, q) if leaf is None else ('content', leaf, p, q)
    if printable_run(p) or printable_run(q):
        return 'const', const_kind(p, q), p, q
    if P is not None or Q is not None:
        return 'undet', 'ptr_vs_const', p, q
    return 'const', const_kind(p, q), p, q


def pos_kind(sc, kh, p, q):
    """ks_rdata_value_pos.py と同じ 5 区分 (突き合わせ用)。"""
    sx, sy = sec_of(sc, p), sec_of(kh, q)
    sx = sx if sx and sx[0] == '.rdata' else None
    sy = sy if sy and sy[0] == '.rdata' else None
    if sx and sy and not sx[3] and not sy[3]:
        return 'rva_pair'
    if is_text(p) or is_text(q):
        return 'text'
    dp, dq = as_dbl(p), as_dbl(q)
    ok = all(v == v and abs(v) != float('inf') and v != 0 for v in (dp, dq))
    return 'dbl_pair' if ok and dp * dq > 0 else 'other'


def strs(blob):
    return [m.decode('latin1') for m in re.findall(rb'[\x20-\x7e]{3,}', blob)]


def content_strings(sc, kh, allw, win):
    """content 語の指す先 (win B) の印字可能文字列の集合を SC/KH で比べる。"""
    c = collections.Counter()
    for w in allw:
        if w['label'] != 'content':
            continue
        P, Q = sec_of(sc, int(w['sc'], 16)), sec_of(kh, int(w['kh'], 16))
        a, b = strs(sc.rva_bytes(P[2], win)), strs(kh.rva_bytes(Q[2], win))
        c['set_equal' if set(a) == set(b) else 'set_differ'] += 1
    return dict(c)


def short(root):
    m = re.match(r'\.\?AV(\w+?)Dsp', root)
    return m.group(1) if m else root


def usage_map(sc, sp, ident, fns):
    td = tempfile.mkdtemp()
    sv = vtables(sp, os.path.join(td, 's.json'))
    slots = {r: set(int(x, 16) for x in sv[r][0]['slots']) for r in ROOTS}
    cl = {r: closure(sc, [int(x, 16) for x in sv[r][0]['slots']]) for r in ROOTS}
    union = set()
    for r in ROOTS:
        union |= set(cl[r])
    callers = collections.defaultdict(set)
    for g in union:
        ins, _ = sc.disasm(g)
        for i in ins:
            if i.mnemonic in ('call', 'jmp') and re.fullmatch(r'0x[0-9a-f]+', i.op_str):
                t = int(i.op_str, 16)
                if t != g and t in union:
                    callers[t].add(g)
    proc_sc = {v['process_pair']['sc_va']: c for c, v in ident.items()}
    proc_kh = {v['process_pair']['kh_va']: c for c, v in ident.items()}
    res = {}
    for f in fns:
        roots_in = [short(r) for r in ROOTS if f in cl[r]]
        slot_of = [short(r) for r in ROOTS if f in slots[r]]
        pc = proc_sc.get(hex(f))
        cs = sorted(callers.get(f, ()))
        pcall = sorted({proc_sc[hex(g)] for g in cs if hex(g) in proc_sc})
        if pc:
            lab = 'process 本体 (%s)' % pc
        elif slot_of:
            lab = 'vtable 直接 (%s)' % ','.join(slot_of)
        elif len(roots_in) >= 2:
            lab = 'closure 共有 (%s)' % ','.join(roots_in)
        elif roots_in:
            lab = 'closure 単独 (%s)' % roots_in[0]
        else:
            lab = 'closure 外'
        res[hex(f)] = dict(label=lab, roots=roots_in, direct_callers=len(cs),
                           caller_process=pcall, caller_vas=[hex(g) for g in cs][:8])
    return res


def classify_fn(sc, kh, sva, kva, depth, win):
    a, b = rip_data(sc, sva, 32), rip_data(kh, kva, 32)
    words = []
    for ri, (x, y) in enumerate(zip(a, b)):
        if x == y:
            continue
        xs, ys = struct.unpack('<4Q', x), struct.unpack('<4Q', y)
        for wi, (p, q) in enumerate(zip(xs, ys)):
            if p == q:
                continue
            lab, info, _, _ = judge(sc, kh, p, q, depth, win)
            words.append(dict(ref=ri, word=wi, sc=hex(p), kh=hex(q), pos=pos_kind(sc, kh, p, q),
                              label=lab, info=info, leaf=info if lab == 'content' else None))
    return words


def tally(words):
    c = collections.Counter()
    for w in words:
        lab, info = w['label'], w['info']
        if lab == 'const':
            c['const_' + info] += 1
        elif lab == 'content':
            c['content'] += 1
            c['content_leaf_%s_%s' % info[:2]] += 1
        elif lab == 'undet':
            c['undet_' + info] += 1
        else:
            c[lab] += 1
    return c


def main(kp, sp, cls_json, ident_json, out, win=64, depth=3):
    kh, sc = Pe(kp), Pe(sp)
    rc = json.load(open(cls_json))
    ident = json.load(open(ident_json))
    fns = []
    allw = []
    per = {}
    for s, info in sorted(rc.items()):
        if info['cls'] != 'value':
            continue
        words = classify_fn(sc, kh, int(s, 16), int(info['kh_va'], 16), depth, win)
        fns.append(int(s, 16))
        per[s] = dict(kh_va=info['kh_va'], words=words, tally=dict(tally(words)))
        allw.extend(dict(w, fn=s) for w in words)
    use = usage_map(sc, sp, ident, fns)
    total = dict(tally(allw))
    cstr = content_strings(sc, kh, allw, win)
    print('content_strings', json.dumps(cstr, sort_keys=True))
    def key(w):
        i = w['info']
        return w['label'] + (':' + (i if isinstance(i, str) else i[0]) if i else '')
    cross = collections.Counter((w['pos'], key(w)) for w in allw)
    sens = {}
    for wv in (16, 32, 64, 128):
        ws = []
        for s, info in rc.items():
            if info['cls'] == 'value':
                ws += classify_fn(sc, kh, int(s, 16), int(info['kh_va'], 16), depth, wv)
        sens['win%d_d%d' % (wv, depth)] = dict(tally(ws))
    for dv in (1, 2, 3, 4):
        ws = []
        for s, info in rc.items():
            if info['cls'] == 'value':
                ws += classify_fn(sc, kh, int(s, 16), int(info['kh_va'], 16), dv, win)
        sens['win%d_d%d' % (win, dv)] = dict(tally(ws))
    print('differing words', len(allw), 'pos_kind', dict(collections.Counter(w['pos'] for w in allw)))
    print('label', json.dumps(total, sort_keys=True))
    print('cross', json.dumps({'%s|%s' % k: v for k, v in sorted(cross.items())}, sort_keys=True))
    for s, v in per.items():
        u = use.get(hex(int(s, 16)))
        print(s, v['kh_va'], len(v['words']), json.dumps(v['tally'], sort_keys=True), '|', u['label'] if u else '')
    for k, v in sens.items():
        print('sens', k, json.dumps(v, sort_keys=True))
    json.dump(dict(win=win, depth=depth, total=total, content_strings=cstr, cross={'%s|%s' % k: v for k, v in cross.items()},
                   funcs=per, usage=use, sensitivity=sens), open(out, 'w'), indent=1, sort_keys=True,
              default=str)


if __name__ == '__main__':
    a = sys.argv[1:]
    main(a[0], a[1], a[2], a[3], a[4], int(a[5]) if len(a) > 5 else 64, int(a[6]) if len(a) > 6 else 3)
