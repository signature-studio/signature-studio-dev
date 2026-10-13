#!/usr/bin/env python3
"""PLG-F2-3 (#515) ネガティブコントロール: 差分試験が「既知の脱落」を入れた IR で不一致を出すことを実測する。

  python3 tools/plugins/f2/nc_leaf.py [--kinds store_drop,load_drop,fp_swap]

前提: leaf_diff.sh 実行済み (work/f2/leaf/*.jsonl, work/f2/targets/*.json)。
手順: ベースラインで verdict=match の関数だけを対象に、block ごと・変異 kind ごとに IR を 1 つ複製し、対象関数それぞれに
      変異を 1 箇所だけ入れる (他の関数は無変更)。同じ liftdiff で再採点し、match → mismatch になった割合を報告する。
変異 kind (docs/DEFECTS.md の既知類型を模す):
  store_drop : alloca (レジスタ退避) 以外へ書く最初の `store` を削除        (DEFECTS.md D3 = メモリ宛 store 脱落)
  load_drop  : alloca 以外から読む最初の整数/浮動小数 `load` を 0 に置換     (DEFECTS.md D4 = deref 脱落)
  fp_swap    : 最初の `fadd` を `fsub` に (fadd が無ければ `fmul` を `fadd` に)  (浮動小数演算の取り違え)
出力: work/f2/nc/<kind><block>.{ll,json}, work/f2/nc/<kind>_<block>.jsonl, stdout に kind 別の 検出数/変異数 と未検出関数
"""
import collections, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGINS = os.path.abspath(os.path.join(HERE, '..'))
REPO = os.path.abspath(os.path.join(PLUGINS, '..', '..'))
LD = os.path.join(REPO, 'tools', 'liftdiff')
W = os.path.join(PLUGINS, 'work', 'f2')

ALLOCA = re.compile(r'^\s*(%[\w.$-]+)\s*=\s*alloca\b')
STORE = re.compile(r'^\s*store\s+(?:volatile\s+)?(.+),\s*ptr\s+([^\s,]+)')
LOAD = re.compile(r'^(\s*)(%[\w.$-]+)\s*=\s*load\s+(?:volatile\s+)?(i\d+|float|double|ptr),\s*ptr\s+(%[\w.$-]+|@[\w.$-]+|[^\s,]+)')


def mutate(lines, kind):
    """lines: 1 関数の本文行 (define 行と } を除く)。 戻り: (new_lines, 説明) | None"""
    allocas = {m.group(1) for l in lines for m in [ALLOCA.match(l)] if m}
    for i, l in enumerate(lines):
        if kind == 'store_drop':
            m = STORE.match(l)
            if m and m.group(2) not in allocas:
                return lines[:i] + lines[i + 1:], 'line %d 削除: %s' % (i, l.strip()[:80])
        elif kind == 'load_drop':
            m = LOAD.match(l)
            if m and m.group(4) not in allocas:
                ind, dst, ty = m.group(1), m.group(2), m.group(3)
                z = {'float': 'fadd float 0.0, 0.0', 'double': 'fadd double 0.0, 0.0', 'ptr': 'inttoptr i64 0 to ptr'}.get(ty, 'add %s 0, 0' % ty)
                return lines[:i] + ['%s%s = %s' % (ind, dst, z)] + lines[i + 1:], 'line %d: %s -> 0' % (i, l.strip()[:80])
    if kind == 'fp_swap':
        for a, b in (('fadd', 'fsub'), ('fsub', 'fadd'), ('fmul', 'fadd')):
            for i, l in enumerate(lines):
                m = re.match(r'^(\s*%[\w.$-]+\s*=\s*)%s\b(.*)$' % a, l)
                if m:
                    return lines[:i] + [m.group(1) + b + m.group(2)] + lines[i + 1:], 'line %d: %s -> %s' % (i, a, b)
    return None


def mutate_ir(src, dst, vas, kind):
    out, cur, body, head, done = [], None, [], None, {}
    for ln in open(src, errors='replace'):
        if cur is None:
            if ln.startswith('define '):
                m = re.search(r'@function_([0-9a-f]+)\(', ln)
                if m and int(m.group(1), 16) in vas and ln.rstrip().endswith('{'):
                    cur, head, body = int(m.group(1), 16), ln, []
                    continue
            out.append(ln)
        else:
            if ln.startswith('}'):
                r = mutate([x.rstrip('\n') for x in body], kind)
                if r:
                    done[cur] = r[1]
                    body = [x + '\n' for x in r[0]]
                out.append(head); out += body; out.append(ln)
                cur = None
            else:
                body.append(ln)
    open(dst, 'w').writelines(out)
    return done


def main():
    a = sys.argv[1:]
    kinds = ['store_drop', 'load_drop', 'fp_swap']
    if a[:1] == ['--kinds']:
        kinds = a[1].split(',')
    base = {}
    for p in sorted(os.listdir(os.path.join(W, 'leaf'))):
        for l in open(os.path.join(W, 'leaf', p)):
            r = json.loads(l)
            base[(r['target'], int(r['function']['va'], 16))] = r['verdict']
    os.makedirs(os.path.join(W, 'nc'), exist_ok=True)
    res = collections.defaultdict(list)
    for kind in kinds:
        for tgt in sorted({t for t, _ in base}):
            vas = {va for (t, va), v in base.items() if t == tgt and v == 'match'}
            if not vas:
                continue
            t = json.load(open(os.path.join(W, 'targets', tgt + '.json')))
            block = tgt[len('eqf'):]
            ir_src = os.path.join(REPO, t['ir'])
            ir_dst = os.path.join(W, 'nc', '%s%s.ll' % (kind, block))
            done = mutate_ir(ir_src, ir_dst, vas, kind)
            if not done:
                continue
            t['name'] = 'nc_%s%s' % (kind, block)
            t['ir'] = os.path.relpath(ir_dst, REPO)
            t['simd']['ir'] = t['ir']
            tp = os.path.join(W, 'nc', t['name'] + '.json')
            json.dump(t, open(tp, 'w'), indent=1)
            vf = os.path.join(W, 'nc', t['name'] + '.vas')
            open(vf, 'w').write('\n'.join('%x' % v for v in sorted(done)) + '\n')
            out = os.path.join(W, 'nc', '%s_%s.jsonl' % (kind, block))
            subprocess.run([sys.executable, 'liftdiff.py', 'batch', tp, '--set', 'file:' + vf, '--shards', '2', '--out', out],
                           cwd=LD, stdout=subprocess.DEVNULL, check=True)
            for l in open(out):
                r = json.loads(l)
                va = int(r['function']['va'], 16)
                res[kind].append((block, hex(va), r['verdict'], done[va]))
            print('[nc] %s block %s: 変異 %d 関数 -> 不一致 %d' % (kind, block, len(done), sum(1 for x in res[kind] if x[0] == block and x[2] == 'mismatch')), flush=True)
    print()
    print('| kind | ベースライン match のうち変異できた関数 | 変異後 mismatch (検出) | match のまま (未検出) | unexec |')
    print('|---|--:|--:|--:|--:|')
    rc = 0
    for kind in kinds:
        R = res[kind]
        c = collections.Counter(x[2] for x in R)
        print('| %s | %d | %d | %d | %d |' % (kind, len(R), c['mismatch'], c['match'], c['unexec']))
        for b, va, v, d in R:
            if v != 'mismatch':
                print('  未検出 %s block %s %s: %s' % (kind, b, va, d))
        if not c['mismatch']:
            rc = 1
    json.dump(res, open(os.path.join(W, 'nc', 'nc_result.json'), 'w'), indent=1)
    sys.exit(rc)


if __name__ == '__main__':
    main()
