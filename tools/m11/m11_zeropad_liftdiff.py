#!/usr/bin/env python3
"""#955 [M11-N55]: sigfix 0 詰め site を liftdiff 差分ハーネスの採点結果と突合する。

入力:
  tools/m11/results/sigfix_zeropad_remaining.tsv (sigfix 0 詰め site 1,049 行)
  OUT_JSONL (liftdiff batch の出力。callee の関数単位採点)
出力:
  tools/m11/results/sigfix_zeropad_liftdiff.tsv (site 別の判定, 優先順)
  標準出力に集計

判定 (site = caller→callee の 0 詰め k 番目引数):
  一致   = callee の採点が match (0 詰め引数を含む全 pattern で native と wasm が一致)
  不一致 = callee の採点が mismatch
  未到達 = callee が採点されない (unexec: 実行不能) または batch に無い
  tag   = callee の不一致 tag の evidence が引数 k を指すか (`arg<k>` / `arg <k>`)

使い方: python3 tools/m11/m11_zeropad_liftdiff.py OUT_JSONL
"""
import csv, json, os, re, sys, collections

HERE = os.path.dirname(os.path.abspath(__file__))
TSV_IN = os.path.join(HERE, 'results', 'sigfix_zeropad_remaining.tsv')
TSV_OUT = os.path.join(HERE, 'results', 'sigfix_zeropad_liftdiff.tsv')


def load(path):
    recs = {}
    for line in open(path):
        r = json.loads(line)
        recs[r['function']['name']] = r
    return recs


def arg_mentioned(rec, k):
    pat = re.compile(r'arg\s?%d\b' % k)
    return any(pat.search(t.get('evidence', '')) for t in rec.get('tags', []))


def main():
    recs = load(sys.argv[1])
    rows = list(csv.DictReader(open(TSV_IN), delimiter='\t'))
    out = []
    for r in rows:
        callee = r['callee']
        k = int(r['k'])
        rec = recs.get(callee)
        if rec is None:
            verdict, tag = 'unreached', 'not_in_batch'
        elif rec['verdict'] == 'match':
            verdict, tag = 'match', ''
        elif rec['verdict'] == 'mismatch':
            verdict = 'mismatch'
            tag = 'arg%d' % k if arg_mentioned(rec, k) else ''
        else:
            verdict, tag = 'unreached', rec.get('unexec_reason', rec['verdict'])
        out.append((r['caller'], callee, k, r['status'], verdict, tag))

    # 優先順: 判定が確定している (match/mismatch) → 未到達 の順, 同順位内は callee ごとの site 数の多い順
    cnt = collections.Counter(o[1] for o in out)
    rank = {'mismatch': 0, 'match': 1, 'unreached': 2}
    out.sort(key=lambda o: (rank[o[4]], -cnt[o[1]], o[1], o[0], o[2]))

    with open(TSV_OUT, 'w') as f:
        f.write('# priority\tcaller\tcallee\tk\tstatus\tverdict\ttag\n')
        for i, o in enumerate(out, 1):
            f.write('%d\t%s\n' % (i, '\t'.join(str(x) for x in o)))

    total = len(out)
    c = collections.Counter(o[4] for o in out)
    print('sites %d: 一致 %d / 不一致 %d / 未到達 %d' % (total, c['match'], c['mismatch'], c['unreached']))
    print('不一致 site の内訳 (arg k を tag が指すもの): %d' % sum(1 for o in out if o[4] == 'mismatch' and o[5]))
    ur = collections.Counter(o[5] for o in out if o[4] == 'unreached')
    for k_, v in ur.most_common():
        print('  未到達 理由 %s: %d' % (k_, v))
    print('callee 数: 一致 %d / 不一致 %d / 未到達 %d' % (
        len({o[1] for o in out if o[4] == 'match'}),
        len({o[1] for o in out if o[4] == 'mismatch'}),
        len({o[1] for o in out if o[4] == 'unreached'})))


if __name__ == '__main__':
    main()
