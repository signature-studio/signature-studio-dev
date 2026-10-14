#!/usr/bin/env python3
"""sites_block_classify.py RW_PE RANGES MAP_JSON SITES_JSON OUTDIR : #1014 (ICALL-15) の受入条件 2。

RetDec の --print-after-all 全段 dump (OUTDIR/print_after_all.txt) を段 (= dump 1 本) に分け、
関数ごとに基本ブロック (label) と書換え stub 呼出し (function_1cd3f30 / function_1cd3fe0) を段ごとに追う。
stub 呼出しの VA は、全 stub に !insn.addr が付く段 (MAP の sites[].new に対応する VA が出る段) から取る。
VA の対応は「stub の !insn.addr の直前にある sites[].new」 (差は +78 〜 +81 バイト)。
出力 OUTDIR/site_block.tsv (site 1 行: VA・ir・関数・ブロック label・前後段の状態・最終状態)、
OUTDIR/summary.txt (集計)。
"""
import bisect, collections, json, os, re, subprocess, sys, tempfile

RETDEC = os.environ.get('RETDEC_BIN', '/opt/retdec/bin/retdec-decompiler')
HDR = re.compile(rb'^\*\*\* IR Dump After (.*) \*\*\*$')
DEF = re.compile(r'^define\b.*@(function_\w+)\(')
LAB = re.compile(r'^([A-Za-z_.$][\w.$-]*):')
META = re.compile(r'^!(\d+) = !\{i64 (\d+)\}\s*$')
STUB = re.compile(r'@(function_1cd3f30|function_1cd3fe0)\(\)')
INSN = re.compile(r'!insn\.addr !(\d+)')
REF = re.compile(r'label %([A-Za-z_.$][\w.$-]*)')
MAXLAG = 100  # stub の insn.addr は sites[].new の直後 (+78〜+81) にある


def run_retdec(pe, ranges, outdir):
    tmp = tempfile.mkdtemp(prefix='sbc_', dir=outdir)
    dump = os.path.join(outdir, 'print_after_all.txt')
    with open(dump, 'wb') as err:
        subprocess.run([RETDEC, pe, '-o', os.path.join(tmp, 'x.c'), '--select-ranges', ranges,
                        '--select-decode-only', '--print-after-all'],
                       stdout=subprocess.DEVNULL, stderr=err, env=dict(os.environ, TMPDIR=tmp), check=False)
    return dump


def split_segments(path):
    segs, cur, buf = [], None, []
    with open(path, 'rb') as f:
        for raw in f:
            line = raw.rstrip(b'\n')
            m = HDR.match(line)
            if m:
                if cur is not None:
                    segs.append((cur, buf))
                cur, buf = m.group(1).decode(errors='replace'), []
                continue
            if cur is not None:
                buf.append(line.decode(errors='replace'))
    if cur is not None:
        segs.append((cur, buf))
    return segs


def parse_segment(lines):
    """関数ごとの {blocks: {label: {stub, succ}}, entry, tags: {label: [insn.addr]}}"""
    meta = {}
    for ln in lines:
        mm = META.match(ln)
        if mm:
            meta[mm.group(1)] = int(mm.group(2))
    fns, fn, label, inbody = {}, None, None, False
    for ln in lines:
        if not inbody:
            d = DEF.match(ln)
            if d:
                fn, label, inbody = d.group(1), None, True
                fns[fn] = {'blocks': collections.OrderedDict(), 'entry': None, 'tags': collections.defaultdict(list),
                           'stubs': []}
            continue
        if ln == '}':
            inbody = False
            continue
        lb = LAB.match(ln)
        if lb:
            label = lb.group(1)
            fns[fn]['blocks'][label] = {'stub': 0, 'succ': set()}
            if fns[fn]['entry'] is None:
                fns[fn]['entry'] = label
            continue
        if label is None:
            continue
        for r in REF.findall(ln):
            fns[fn]['blocks'][label]['succ'].add(r)
        sm = STUB.search(ln)
        if sm:
            fns[fn]['blocks'][label]['stub'] += 1
            im = INSN.search(ln)
            va = meta.get(im.group(1)) if im else None
            fns[fn]['stubs'].append((label, sm.group(1), va))
            if va is not None:
                fns[fn]['tags'][label].append(va)
    return fns


def reachable(blocks, entry):
    seen, st = set(), ([entry] if entry else [])
    while st:
        b = st.pop()
        if b in seen or b not in blocks:
            continue
        seen.add(b)
        st.extend(blocks[b]['succ'])
    return seen


def main():
    pe, ranges, map_json, sites_json, outdir = sys.argv[1:6]
    os.makedirs(outdir, exist_ok=True)
    dump = run_retdec(pe, open(ranges).read().strip(), outdir)
    segs = [(si, pn, parse_segment(lines)) for si, (pn, lines) in enumerate(split_segments(dump))]

    # VA 付き stub 数が最大の最後の段 (タグ段)。モジュール全体の段は後段ほど block が組み直されるため、
    # GVN (SCCP の直前) に最も近い段を使う。以後の関数別の段は insn.addr が付かないので使えない
    tagged = [sum(len(v) for g in fns.values() for v in g['tags'].values()) for _, _, fns in segs]
    tag_seg = len(tagged) - 1 - tagged[::-1].index(max(tagged)) if tagged else None
    tag_va = {}
    for fn, d in segs[tag_seg][2].items():
        for label, vas in d['tags'].items():
            for v in vas:
                tag_va[v] = (fn, label)

    mp = json.load(open(map_json))
    sites = json.load(open(sites_json))
    new_of = {s['va']: s['new'] for s in mp['sites']}
    news = sorted(new_of.values())
    site_blk, unmatched = {}, []
    for t, blk in tag_va.items():
        i = bisect.bisect_right(news, t) - 1
        if i >= 0 and 0 <= t - news[i] <= MAXLAG and news[i] not in site_blk:
            site_blk[news[i]] = blk
        else:
            unmatched.append((t, blk))

    fns_all = sorted(set(f for _, _, fns in segs for f in fns if fns[f]['stubs']))
    # 段ごとの関数の状態 (stub 数が初期値を下回る最初の段 = 落ちの段)
    seq = {f: [(si, pn, fns[f]) for si, pn, fns in segs if f in fns] for f in fns_all}
    init = {f: sum(b['stub'] for b in seq[f][0][2]['blocks'].values()) for f in fns_all}
    drop_seg = {}
    for f in fns_all:
        drop_seg[f] = next((i for i, (si, pn, d) in enumerate(seq[f])
                            if sum(b['stub'] for b in d['blocks'].values()) < init[f]), None)
    pos = {f: {si: i for i, (si, pn, d) in enumerate(seq[f])} for f in fns_all}

    def state(f, si, label):
        if si is None or f not in pos or si not in pos[f]:
            return None
        b = seq[f][pos[f][si]][2]['blocks']
        return b[label]['stub'] if label in b else None

    rows = []
    for s in sites:
        v = s['va']
        n = new_of[v]
        fn, lab = site_blk.get(n, (None, None))
        if fn is None:
            rows.append((v, s['ir'], '-', '-', None, None, None, None))
            continue
        ds = drop_seg.get(fn)
        if ds is None:
            pre_si = post_si = None
        else:
            post_si = seq[fn][ds][0]
            pre_si = seq[fn][ds - 1][0] if ds else None
        fin_si = seq[fn][-1][0]
        pre = state(fn, pre_si, lab)
        post = state(fn, post_si, lab)
        fin = state(fn, fin_si, lab)
        rows.append((v, s['ir'], fn, lab, pre, post, fin, seq[fn][ds][1] if ds is not None else None))
        # ラベルが最初に消えた段
    gone = collections.Counter()
    for v, ir, fn, lab, pre, post, fin, dpass in rows:
        if fn == '-' or drop_seg.get(fn) is None:
            continue
        first = next((pn for si, pn, d in seq[fn][drop_seg[fn]:] if lab not in d['blocks']), None)
        gone[(ir, fn, 'label_gone_at=' + (first or 'never'))] += 1
    with open(os.path.join(outdir, 'site_block.tsv'), 'w') as f:
        f.write('va\tir\tfn\tlabel\tstub_in_label_pre\tstub_in_label_post\tstub_in_label_final\tdrop_pass\n')
        for r in rows:
            f.write('%d\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' % (r[0], r[1], r[2], r[3],
                                                          '-' if r[4] is None else r[4],
                                                          '-' if r[5] is None else r[5],
                                                          '-' if r[6] is None else r[6],
                                                          r[7] or '-'))
    with open(os.path.join(outdir, 'summary.txt'), 'w') as f:
        f.write('segments %d / tag segment %s (stub VA %d) / sites %d / unmatched tags %d\n' % (
            len(segs), tag_seg, len(tag_va), len(sites), len(unmatched)))
        for fn in fns_all:
            f.write('%s: 初期 stub %d, 落ちの段 %s\n' % (fn, init[fn], seq[fn][drop_seg[fn]][1] if drop_seg[fn] is not None else '-'))
        for k, c in sorted(collections.Counter((r[1], r[2]) for r in rows).items()):
            f.write('site %s %s: %d\n' % (k[0], k[1], c))
        for k, c in sorted(gone.items()):
            f.write('block (%s, %s, %s): %d sites\n' % (k[0], k[1], k[2], c))
        moved = 0
        for r in rows:
            if r[2] == '-' or r[3] == '-' or r[4] is None:
                continue
            for f2 in fns_all:
                if f2 != r[2] and any(r[3] in d['blocks'] for _, _, d in seq[f2]):
                    moved += 1
        f.write('dropped/kept block label found in another function: %d\n' % moved)
    print(open(os.path.join(outdir, 'summary.txt')).read())


if __name__ == '__main__':
    main()
