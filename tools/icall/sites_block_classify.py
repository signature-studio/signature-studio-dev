#!/usr/bin/env python3
"""sites_block_classify.py RW_PE RANGES MAP_JSON SITES_JSON OUTDIR [DUMP] : #1014 (ICALL-15) の受入条件 2。

RetDec の --print-after-all 全段 dump を段 (= dump 1 本) に分け、関数ごとに基本ブロック (label) と
書換え stub 呼出し (function_1cd3f30 / function_1cd3fe0) を段ごとに追う。
DUMP を渡すと RetDec を呼ばない (RETDEC_BIN 不要)。RetDec を呼ぶときは RETDEC_BIN に retdec-decompiler を指定する。
stub 呼出しの VA は、全 stub に !insn.addr が付く段 (タグ段) から取る。
VA の対応は「stub の !insn.addr の直前にある sites[].new」 (差は +78 〜 +81 バイト)。
出力 OUTDIR/site_block.tsv (site 1 行)、OUTDIR/summary.txt (集計とネガティブコントロール 2 件)。
"""
import bisect, collections, json, os, re, subprocess, sys, tempfile

RETDEC = os.environ.get('RETDEC_BIN', '')
HDR = re.compile(rb'^\*\*\* IR Dump After (.*) \*\*\*$')
DEF = re.compile(r'^define\b.*@(function_\w+)\(')
LAB = re.compile(r'^([A-Za-z_.$][\w.$-]*):')
META = re.compile(r'^!(\d+) = !\{i64 (\d+)\}\s*$')
STUB = re.compile(r'@(function_1cd3f30|function_1cd3fe0)\(\)')
INSN = re.compile(r'!insn\.addr !(\d+)')
MAXLAG = 100  # stub の insn.addr は sites[].new の直後 (+78〜+81) にある


def run_retdec(pe, ranges, outdir):
    if not RETDEC:
        sys.exit('RETDEC_BIN に retdec-decompiler を指定する (docs/REFERENCES.md [RETDEC])。段 dump を渡すなら DUMP 引数')
    dump = os.path.join(outdir, 'print_after_all.txt')
    with tempfile.TemporaryDirectory(prefix='sbc_', dir=outdir) as tmp, open(dump, 'wb') as err:
        rc = subprocess.run([RETDEC, pe, '-o', os.path.join(tmp, 'x.c'), '--select-ranges', ranges,
                             '--select-decode-only', '--print-after-all'],
                            stdout=subprocess.DEVNULL, stderr=err, env=dict(os.environ, TMPDIR=tmp),
                            check=False).returncode
    if rc != 0:
        sys.exit('RetDec が終了コード %d で失敗 (途中までの段 dump では集計しない): %s' % (rc, dump))
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
    """関数ごとの {blocks: {label: stub 数}, tags: {label: [insn.addr の VA]}, nstub: stub 総数}"""
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
                fns[fn] = {'blocks': collections.OrderedDict(), 'tags': collections.defaultdict(list), 'nstub': 0}
            continue
        if ln == '}':
            inbody = False
            continue
        lb = LAB.match(ln)
        if lb:
            label = lb.group(1)
            fns[fn]['blocks'][label] = 0
            continue
        if label is None:
            continue
        if STUB.search(ln):
            fns[fn]['blocks'][label] += 1
            fns[fn]['nstub'] += 1
            im = INSN.search(ln)
            va = meta.get(im.group(1)) if im else None
            if va is not None:
                fns[fn]['tags'][label].append(va)
    return fns


def stub_sum(blocks):
    return sum(blocks.values())


def tag_map(fns):
    return {v: (fn, label) for fn, d in fns.items() for label, vas in d['tags'].items() for v in vas}


def map_sites(tag_va, news):
    """stub VA → 直前の sites[].new。戻り値: (new → (fn, label), lag の度数, 未対応 [(VA, (fn, label))], 重複数)"""
    site_blk, lags, unmatched, dup = {}, collections.Counter(), [], 0
    for t, blk in sorted(tag_va.items()):
        i = bisect.bisect_right(news, t) - 1
        if i < 0 or t - news[i] > MAXLAG:
            unmatched.append((t, blk))
            continue
        lags[t - news[i]] += 1
        if news[i] in site_blk:
            dup += 1
        else:
            site_blk[news[i]] = blk
    return site_blk, lags, unmatched, dup


def analyze(segs, mp, sites, fixed=None):
    """segs = [(si, pn, fns)] (段ごとの parse 結果)。集計 dict を返す。
    fixed = {関数: (pre 段, drop 段)} を渡すと落ちの段を自動判定せず固定する (ネガティブコントロール用)。"""
    tagged = [sum(len(v) for d in fns.values() for v in d['tags'].values()) for _, _, fns in segs]
    tag_si = len(tagged) - 1 - tagged[::-1].index(max(tagged))
    new_of = {s['va']: s['new'] for s in mp['sites']}
    news = sorted(set(new_of.values()))
    site_blk, lags, unmatched, dup = map_sites(tag_map(segs[tag_si][2]), news)
    cands = []
    for si, pn, fns in segs:
        if tagged[si]:
            sb = map_sites(tag_map(fns), news)[0]
            cands.append((si, pn, tagged[si], sum(1 for n in news if sb.get(n) != site_blk.get(n))))
    pname = {si: pn for si, pn, _ in segs}
    fns_all = sorted({f for _, _, fns in segs for f, d in fns.items() if d['nstub']})
    seq = {f: [(si, pn, fns[f]) for si, pn, fns in segs if f in fns] for f in fns_all}
    bl = {f: {si: d['blocks'] for si, _, d in seq[f]} for f in fns_all}

    # 段ごとの関数の状態。落ちの段 = stub 数が初期値を下回る最初の段 (seq の添字 ds)。
    # pre = 落ちの直前の段 (GVN)、jt = ブロック数が最初に減る段
    info = {}
    for f in fns_all:
        s0 = seq[f]
        init = stub_sum(s0[0][2]['blocks'])
        if fixed and f in fixed:
            ds = next(i for i, (si, _, _) in enumerate(s0) if si == fixed[f][1])
        else:
            ds = next((i for i, (si, pn, d) in enumerate(s0) if stub_sum(d['blocks']) < init), None)
        if ds is None:
            info[f] = {'init': init, 'ds': None, 'pre': None, 'drop': None, 'jt': None}
            continue
        n0 = len(s0[ds][2]['blocks'])
        info[f] = {'init': init, 'ds': ds, 'pre': s0[ds - 1][0] if ds else None, 'drop': s0[ds][0],
                   'jt': next((si for si, pn, d in s0[ds:] if len(d['blocks']) < n0), None)}

    def state(f, si, lab):
        b = bl[f].get(si) if si is not None else None
        return None if b is None else b.get(lab)

    rows = []
    for s in sites:
        fn, lab = site_blk.get(new_of[s['va']], (None, None))
        r = {'va': s['va'], 'ir': s['ir'], 'fn': fn or '-', 'lab': lab or '-',
             'pre': None, 'post': None, 'fin': None, 'gone': None, 'drop_pass': '-'}
        if fn is not None and info[fn]['ds'] is not None:
            i = info[fn]
            r.update(pre=state(fn, i['pre'], lab), post=state(fn, i['drop'], lab),
                     fin=state(fn, seq[fn][-1][0], lab), drop_pass=pname[i['drop']])
            r['gone'] = next(((si, pn) for si, pn, d in seq[fn][i['ds']:] if lab not in d['blocks']), None)
        rows.append(r)

    blk_n = collections.Counter((r['fn'], r['lab']) for r in rows if r['fn'] != '-')
    pre_of = {b: state(b[0], info[b[0]]['pre'], b[1]) for b in blk_n}
    post_of = {b: state(b[0], info[b[0]]['drop'], b[1]) for b in blk_n}
    mism = sorted(b for b in blk_n if pre_of[b] != blk_n[b])
    moved = sum(1 for r in rows if r['post'] == 0 and
                any(r['lab'] in d['blocks'] for f2 in fns_all if f2 != r['fn'] for _, _, d in seq[f2]))

    per = {}
    for f in fns_all:
        i = info[f]
        st = {'init': i['init']}
        if i['ds'] is not None:
            pre, drop = bl[f][i['pre']], bl[f][i['drop']]
            fb = [b for b in blk_n if b[0] == f]
            kept_b = [b for b in fb if post_of[b] > 0]
            st.update(
                pre_seg=i['pre'], pre_stub=stub_sum(pre), pre_stub_blocks=sum(1 for v in pre.values() if v),
                pre_blocks=len(pre), drop_seg=i['drop'], drop_stub=stub_sum(drop), drop_blocks=len(drop),
                jt_seg=i['jt'], jt_blocks=len(bl[f][i['jt']]) if i['jt'] is not None else None,
                site_blocks=len(fb), dropped_blocks=len(fb) - len(kept_b), kept_blocks=len(kept_b),
                sites=sum(blk_n[b] for b in fb),
                dropped_sites=sum(1 for r in rows if r['fn'] == f and r['post'] == 0),
                kept_sites=sum(1 for r in rows if r['fn'] == f and r['post'] not in (None, 0)),
                gvn_site_stub=sum(pre_of[b] for b in fb),
                kept_stub=sum(post_of[b] for b in kept_b),
            )
            st['nonsite_stub'] = st['drop_stub'] - st['kept_stub']
        per[f] = st

    gone = collections.Counter(
        (r['ir'], r['fn'], 'label_gone_at=%s' % ('never' if r['gone'] is None else '%d %s' % r['gone']))
        for r in rows if r['post'] == 0)
    return {'tag_si': tag_si, 'tag_n': len(tag_map(segs[tag_si][2])), 'sites_n': len(sites), 'lags': lags,
            'unmatched': unmatched, 'dup': dup, 'cands': cands, 'pname': pname, 'fns_all': fns_all,
            'info': info, 'per': per, 'rows': rows, 'mism': mism, 'blk_n': blk_n, 'moved': moved,
            'gone': gone, 'bl': bl, 'seq': seq}


def summary_lines(segs, res):
    pn = res['pname']
    L = ['segments %d / タグ段 %d (%s) / stub VA %d / sites %d' % (
        len(segs), res['tag_si'], pn[res['tag_si']], res['tag_n'], res['sites_n']),
        'stub VA − sites[].new の差 (度数): %s / 対応 %d / 未対応 %d / 同一 site への重複 %d' % (
            ', '.join('%d: %d' % kv for kv in sorted(res['lags'].items())), sum(res['lags'].values()),
            len(res['unmatched']), res['dup'])]
    L += ['  未対応 stub VA 0x%x (%s %s)' % (t, b[0], b[1]) for t, b in res['unmatched']]
    L.append('タグ段の候補 (段, pass, stub VA 数, 基準段と所属 label が違う site 数):')
    L += ['  段 %d %s: %d / %d' % c for c in res['cands']]
    for f in res['fns_all']:
        i, s = res['info'][f], res['per'][f]
        L.append('%s: 初期 stub %d' % (f, i['init']))
        if i['ds'] is None:
            L.append('  落ちの段なし')
            continue
        L.append('  GVN 段 %d (%s): stub %d / stub を含むブロック %d / ブロック %d' % (
            s['pre_seg'], pn[s['pre_seg']], s['pre_stub'], s['pre_stub_blocks'], s['pre_blocks']))
        L.append('  SCCP 段 %d (%s): stub %d (kept site ブロック %d + 非 site %d) / ブロック %d' % (
            s['drop_seg'], pn[s['drop_seg']], s['drop_stub'], s['kept_stub'], s['nonsite_stub'], s['drop_blocks']))
        L.append('  ブロック数が最初に減る段 %d (%s): ブロック %d' % (s['jt_seg'], pn[s['jt_seg']], s['jt_blocks']))
        L.append('  site ブロック %d (落ち %d / kept %d) / site %d (落ち %d / kept %d) / GVN 段の site ブロック stub 合計 %d' % (
            s['site_blocks'], s['dropped_blocks'], s['kept_blocks'], s['sites'], s['dropped_sites'],
            s['kept_sites'], s['gvn_site_stub']))
    dfs = [f for f in res['fns_all'] if res['info'][f]['ds'] is not None]
    pre_tot = sum(res['per'][f]['pre_stub'] for f in dfs)
    site_tot = sum(res['per'][f]['gvn_site_stub'] for f in dfs)
    L.append('GVN 段の stub 合計 %d = site ブロックの stub 合計 %d + 非 site %d' % (pre_tot, site_tot, pre_tot - site_tot))
    L.append('1:1 検証 (GVN 段の stub 数 = site 数): 検査 %d ブロック / 不一致 %d %s' % (
        len(res['blk_n']), len(res['mism']), res['mism'][:5]))
    for k, c in sorted(res['gone'].items()):
        L.append('block (%s, %s, %s): %d sites' % (k[0], k[1], k[2], c))
    L.append('落ちた site の label が別関数の段に現れる数 (moved): %d' % res['moved'])
    return L


def find_stub_line(lines, fn, lab):
    inside, label = False, None
    for i, ln in enumerate(lines):
        if not inside:
            d = DEF.match(ln)
            if d and d.group(1) == fn:
                inside = True
            continue
        if ln == '}':
            break
        lb = LAB.match(ln)
        if lb:
            label = lb.group(1)
            continue
        if label == lab and STUB.search(ln):
            return i
    return None


def negctl(segs_raw, segs, mp, sites, res):
    """同じ段 dump を壊して、検出器が反応することを確かめる。段の選び方は本番の結果から固定する
    (stub を消すと落ちの段の自動判定が動いてしまい、判定自体を検査できないため)。"""
    fixed = {f: (i['pre'], i['drop']) for f, i in res['info'].items() if i['ds'] is not None}
    base = analyze(segs, mp, sites, fixed)
    L = ['negctl 基準: 段を固定して再解析 → 1:1 不一致 %d / moved %d (本番 %d / %d)' % (
        len(base['mism']), base['moved'], len(res['mism']), res['moved'])]
    for r in res['rows']:
        if r['post'] != 0:
            continue
        dst = next(f for f in res['fns_all'] if f != r['fn'])
        si = res['info'][dst]['pre']
        if r['lab'] in res['bl'][dst][si]:
            continue
        lines = list(segs_raw[si][1])
        di = next(i for i, ln in enumerate(lines) if DEF.match(ln) and DEF.match(ln).group(1) == dst)
        lines.insert(di + 1, r['lab'] + ':')
        segs2 = list(segs)
        segs2[si] = (si, segs[si][1], parse_segment(lines))
        res2 = analyze(segs2, mp, sites, fixed)
        L.append('negctl N1 (別関数への label 注入): 段 %d (%s) の %s に label %s を 1 つ注入 → moved %d → %d' % (
            si, segs[si][1], dst, r['lab'], res['moved'], res2['moved']))
        break
    for r in res['rows']:
        if r['fn'] == '-' or not r['pre']:
            continue
        si = res['info'][r['fn']]['pre']
        lines = list(segs_raw[si][1])
        k = find_stub_line(lines, r['fn'], r['lab'])
        if k is None:
            continue
        del lines[k]
        segs2 = list(segs)
        segs2[si] = (si, segs[si][1], parse_segment(lines))
        res2 = analyze(segs2, mp, sites, fixed)
        L.append('negctl N2 (stub 1 本削除): 段 %d (%s) の %s %s の stub 1 本を削除 → 1:1 不一致 %d → %d' % (
            si, segs[si][1], r['fn'], r['lab'], len(res['mism']), len(res2['mism'])))
        break
    return L


def main():
    pe, ranges, map_json, sites_json, outdir = sys.argv[1:6]
    os.makedirs(outdir, exist_ok=True)
    dump = sys.argv[6] if len(sys.argv) > 6 else run_retdec(pe, open(ranges).read().strip(), outdir)
    segs_raw = split_segments(dump)
    segs = [(si, pn, parse_segment(lines)) for si, (pn, lines) in enumerate(segs_raw)]
    mp = json.load(open(map_json))
    sites = json.load(open(sites_json))
    res = analyze(segs, mp, sites)
    with open(os.path.join(outdir, 'site_block.tsv'), 'w') as f:
        f.write('va\tir\tfn\tlabel\tstub_in_label_pre\tstub_in_label_post\tstub_in_label_final\tdrop_pass\tlabel_gone_at\n')
        for r in res['rows']:
            gone = '-' if r['gone'] is None else '%d %s' % r['gone']
            vals = ['-' if r[k] is None else str(r[k]) for k in ('pre', 'post', 'fin')]
            f.write('%d\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' % (r['va'], r['ir'], r['fn'], r['lab'],
                                                             vals[0], vals[1], vals[2], r['drop_pass'], gone))
    lines = summary_lines(segs, res) + negctl(segs_raw, segs, mp, sites, res)
    text = '\n'.join(lines) + '\n'
    with open(os.path.join(outdir, 'summary.txt'), 'w') as f:
        f.write(text)
    print(text)


if __name__ == '__main__':
    main()
