#!/usr/bin/env python3
"""liftdiff — 関数単位 native-vs-wasm 差分ハーネス CLI

  liftdiff.py build  TARGET.json
  liftdiff.py run    TARGET.json --fn 0x4133f0[,name,...] [--pattern p01,pall] [--json out.json]
  liftdiff.py batch  TARGET.json --set closure|sample:N|file:PATH [--shards 8] --out work/m11/batch.jsonl
  liftdiff.py summary BATCH.jsonl [--md out.md]
"""
import argparse, json, os, random, sys, time, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ldlib import build_wasm, cases, classify, irtool
from ldlib.session import Session

FORMAT_VERSION = 1
KEEP_RAW_ALL = False
TRACE_HEAD = 12


def parse_fn(s, sess):
    out = []
    for tok in s.split(','):
        tok = tok.strip()
        if not tok:
            continue
        if tok.startswith(sess.prefix):
            out.append(int(tok[len(sess.prefix):], 16))
        else:
            out.append(int(tok, 16))
    return out


def trim_case(c, keep_raw):
    d = {k: v for k, v in c.items() if not k.startswith('_')}
    if keep_raw:
        n, w = c.get('_n', {}), c.get('_w', {})
        d['raw'] = {'native': {k: n.get(k) for k in ('rax', 'rdx', 'x0', 'fault', 'detail', 'calls', 'mem_blocks', 'heap_used') if k in n},
                    'wasm': {k: w.get(k) for k in ('rax', 'rdx', 'x0', 'detail', 'calls', 'mem_blocks', 'heap_used', 'rtype') if k in w}}
        d['raw']['native']['trace_head'] = n.get('trace', [])[:TRACE_HEAD]
        d['raw']['wasm']['trace_head'] = w.get('trace', [])[:TRACE_HEAD]
        d['raw']['native']['trace_len'] = len(n.get('trace', []))
        d['raw']['wasm']['trace_len'] = len(w.get('trace', []))
        d['raw']['native']['status'] = n.get('status'); d['raw']['wasm']['status'] = w.get('status')
        d['raw']['wasm']['blk'] = w.get('blk', [])   # LD-64: blk=1 の case のみ (IR block 入口 VA の列)
        d['raw']['wasm']['blk_over'] = w.get('blk_over', 0)
    return d


def make_record(sess, rec, irfeats):
    va = int(rec['va'], 16)
    mach = None
    try:
        mach = sess.static_info(va)
    except Exception:
        mach = None
    irf = irfeats.get(rec['name'])
    irf_s = irf and {k: v for k, v in irf.items() if k != 'callees'}
    route = 'clift' if sess.t.get('clift') else 'ir'
    out = {'liftdiff_version': FORMAT_VERSION, 'target': sess.t['name'],
           'function': {'va': rec['va'], 'name': rec['name'], 'sig': rec.get('sig')}}
    if 'cases' not in rec:
        out['verdict'] = rec['verdict']
        out['unexec_reason'] = rec.get('reason')
        out['cases'] = []
        out['static'] = {'machine': mach, 'ir': irf_s}
        return out
    v = classify.verdict(rec)
    out['verdict'] = v
    if v == 'unexec':
        out['unexec_reason'] = classify.unexec_reason(rec)
    if v == 'mismatch':
        out['tags'] = [{'tag': t, 'confidence': c, 'evidence': e} for t, c, e in classify.classify(rec, mach, irf, rec['sig'], route=route)]
    out['cases'] = [trim_case(c, KEEP_RAW_ALL or c['outcome'] in ('diff', 'wasm_trap')) for c in rec['cases']]
    out['static'] = {'machine': mach, 'ir': irf_s}
    return out


def order_key(sess, name, irfeats):
    sig = sess.sigs[name]
    nptr = sum(1 for t in sig['params'] if t == 'ptr' or t == 'i64')
    f = irfeats.get(name, {})
    return (nptr, f.get('lines', 0))


def state_path(a):
    if not getattr(a, 'state', None):
        return None
    if a.state == 'auto':
        t = build_wasm.load_target(a.target)
        return os.path.join(t['work'], 'boot_state.json')
    return a.state


def cmd_bootstate(a):
    from ldlib import boot
    sess = Session(a.target, shards=1, build=not a.nobuild)
    r, res = boot.build_state(sess, a.upto, mode=a.mode)
    out = os.path.join(sess.t['work'], 'boot_state.json' if a.mode == 'units' else 'boot_state_%s.json' % a.mode)
    json.dump(res, open(out, 'w'))
    st = res['state']
    print('[boot] units_run=%s/%s first_fail=%s mode=%s img_runs=%d heap_used=%s hw=%s -> %s' % (
        res['units_run'], res['units_total'], res['first_fail'], res.get('mode'), len(st['img']), st['heap_used'], st['hw'], out))
    pc = boot.precondition(st)
    print('[boot] precondition InitTable=%#x InitCount=%d TLS_set=%d ok=%s' % (pc['table_ptr'], pc['init_count'], pc['tls_set'], pc['ok']))
    if r:
        r.close()


def cmd_run(a):
    sess = Session(a.target, shards=1, build=not a.nobuild, trace=not a.notrace, state=state_path(a))
    irfeats = {} if sess.t.get('clift') else irtool.ir_features(sess.t['ir'], sess.prefix)
    global KEEP_RAW_ALL, TRACE_HEAD
    if a.verbose:
        KEEP_RAW_ALL = True; TRACE_HEAD = 200
    vas = parse_fn(a.fn, sess)
    pats = a.pattern.split(',') if a.pattern else None
    if a.args:
        cases.CUSTOM['custom'] = (a.args.split(','), a.blob or '-', a.patch)
        pats = ['custom']
    res = sess.run_functions(vas, pats)
    outs = []
    for va in vas:
        r = make_record(sess, res[va], irfeats)
        outs.append(r)
        print_record(r, a.verbose)
    if a.json:
        json.dump(outs if len(outs) > 1 else outs[0], open(a.json, 'w'), indent=1)
        print('wrote', a.json)


def print_record(r, verbose=False):
    f = r['function']
    print('%s %s verdict=%s%s' % (f['va'], f['name'], r['verdict'], (' reason=' + r['unexec_reason']) if r.get('unexec_reason') else ''))
    for t in r.get('tags', []):
        print('   tag %-22s [%s] %s' % (t['tag'], t['confidence'], t['evidence'][:200]))
    for c in r['cases']:
        print('   case %-6s %-12s native=%s wasm=%s' % (c['pattern'], c['outcome'], c.get('native_status'), c.get('wasm_status')))
        if verbose or c['outcome'] in ('diff', 'wasm_trap'):
            for k, v in c.get('diffs', {}).items():
                print('        %s: %s' % (k, json.dumps(v)[:300]))
            if c['outcome'] == 'wasm_trap':
                print('        wasm: %s' % (c.get('wasm_detail') or '')[:300])


def select_set(sess, spec, irfeats):
    allv = sess.closure_vas()
    if spec == 'closure':
        vas = allv
    elif spec.startswith('sample:'):
        n = int(spec.split(':')[1])
        rnd = random.Random(1)
        vas = sorted(rnd.sample(allv, min(n, len(allv))))
    elif spec.startswith('file:'):
        vas = [int(l.split()[0], 16) for l in open(spec[5:]) if l.strip() and not l.startswith('#')]
    else:
        raise SystemExit('bad --set')
    vas.sort(key=lambda v: order_key(sess, sess.fn_name(v), irfeats))
    return vas


def cmd_batch(a):
    sess = Session(a.target, shards=a.shards, build=not a.nobuild, trace=not a.notrace, timeout=a.timeout, state=state_path(a))
    irfeats = {} if sess.t.get('clift') else irtool.ir_features(sess.t['ir'], sess.prefix)
    vas = select_set(sess, a.set, irfeats)
    if a.limit:
        vas = vas[:a.limit]
    for tok in (a.add or '').split(','):
        if tok.strip():
            for v in parse_fn(tok, sess):
                if v not in vas:
                    vas.append(v)
    print('[batch] %d functions, shards=%d' % (len(vas), a.shards), flush=True)
    t0 = time.time()
    out = open(a.out, 'w')
    chunk = 400
    for i in range(0, len(vas), chunk):
        part = vas[i:i + chunk]
        res = sess.run_functions(part, None, with_refine=True)
        for va in part:
            out.write(json.dumps(make_record(sess, res[va], irfeats)) + '\n')
        out.flush()
        print('[batch] %d/%d  %.0fs' % (min(i + chunk, len(vas)), len(vas), time.time() - t0), flush=True)
    out.close()
    print('[batch] done %.0fs -> %s' % (time.time() - t0, a.out))
    cmd_summary(argparse.Namespace(file=a.out, md=None))


def load_jsonl(p):
    return [json.loads(l) for l in open(p) if l.strip()]


def summarize(recs):
    S = collections.Counter(r['verdict'] for r in recs)
    tags = collections.Counter()
    first_tag = collections.Counter()
    reasons = collections.Counter(r.get('unexec_reason') for r in recs if r['verdict'] == 'unexec')
    for r in recs:
        if r['verdict'] == 'mismatch':
            ts = [t['tag'] for t in r.get('tags', [])]
            for t in ts:
                tags[t] += 1
            for p in classify.PRIORITY:
                if p in ts:
                    first_tag[p] += 1
                    break
            else:
                first_tag[ts[0] if ts else 'other'] += 1
    return S, tags, first_tag, reasons


def cmd_summary(a):
    recs = load_jsonl(a.file)
    S, tags, first_tag, reasons = summarize(recs)
    n = len(recs)
    lines = ['関数数 %d: 一致 %d / 不一致 %d / 実行不能 %d' % (n, S['match'], S['mismatch'], S['unexec']), '',
             '不一致の類型 (主因 = 優先順位最上位の1つ / 該当数 = 複数タグ重複あり):']
    for p, c in first_tag.most_common():
        lines.append('  %-24s 主因 %5d   該当 %5d' % (p, c, tags[p]))
    leaf = sum(1 for r in recs if r['verdict'] == 'mismatch' and any(c.get('leaf') and c['outcome'] == 'diff' for c in r['cases']))
    trapl = sum(1 for r in recs if r['verdict'] == 'mismatch' and any(c['outcome'] == 'wasm_trap' for c in r['cases']))
    lines.append('')
    lines.append('不一致のうち callee を一切呼ばずに差分が出た (= その関数自身の欠陥と確定) : %d / wasm trap を含む : %d' % (leaf, trapl))
    lines.append('')
    lines.append('実行不能の内訳:')
    for k, c in reasons.most_common():
        lines.append('  %-34s %5d' % (k, c))
    print('\n'.join(lines))
    if a.md:
        open(a.md, 'w').write('\n'.join(lines) + '\n')


def cmd_export(a):
    recs = load_jsonl(a.file)
    with open(a.out, 'w') as f:
        f.write('# va\tname\tverdict\tprimary_tag\ttags\tunexec_reason\tpatterns(ok/total)\n')
        for r in recs:
            ts = [t['tag'] for t in r.get('tags', [])]
            prim = next((p for p in classify.PRIORITY if p in ts), ts[0] if ts else '')
            cs = r.get('cases', [])
            nok = sum(1 for c in cs if c.get('native_status') == 'ok')
            f.write('%s\t%s\t%s\t%s\t%s\t%s\t%d/%d\n' % (r['function']['va'], r['function']['name'], r['verdict'], prim, ','.join(ts), r.get('unexec_reason') or '', nok, len(cs)))
    print('wrote', a.out, len(recs))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='cmd', required=True)
    p = sp.add_parser('build'); p.add_argument('target')
    p = sp.add_parser('run'); p.add_argument('target'); p.add_argument('--fn', required=True); p.add_argument('--pattern'); p.add_argument('--json')
    p.add_argument('--state'); p.add_argument('--args'); p.add_argument('--blob'); p.add_argument('--patch'); p.add_argument('-v', '--verbose', action='store_true'); p.add_argument('--nobuild', action='store_true'); p.add_argument('--notrace', action='store_true')
    p = sp.add_parser('batch'); p.add_argument('target'); p.add_argument('--set', default='closure'); p.add_argument('--shards', type=int, default=8)
    p.add_argument('--out', required=True); p.add_argument('--limit', type=int); p.add_argument('--add'); p.add_argument('--nobuild', action='store_true')
    p.add_argument('--notrace', action='store_true'); p.add_argument('--state'); p.add_argument('--timeout', type=float, default=10.0)
    p = sp.add_parser('bootstate'); p.add_argument('target'); p.add_argument('--upto', type=int); p.add_argument('--mode', default='units', choices=['units', 'entry', 'hybrid']); p.add_argument('--nobuild', action='store_true')
    p = sp.add_parser('summary'); p.add_argument('file'); p.add_argument('--md')
    p = sp.add_parser('export'); p.add_argument('file'); p.add_argument('--out', required=True)
    a = ap.parse_args()
    if a.cmd == 'build':
        build_wasm.build(build_wasm.load_target(a.target), True)
    elif a.cmd == 'run':
        cmd_run(a)
    elif a.cmd == 'batch':
        cmd_batch(a)
    elif a.cmd == 'bootstate':
        cmd_bootstate(a)
    elif a.cmd == 'summary':
        cmd_summary(a)
    elif a.cmd == 'export':
        cmd_export(a)


if __name__ == '__main__':
    main()
