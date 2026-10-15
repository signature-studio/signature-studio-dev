#!/usr/bin/env python3
"""merge_survey.py の covered 集計を固定する (#4931)。
empty / noproc の unit も jsonl に 1 行ずつ残り、0〜941 の 942 件が covered になることを見る。
実行: python3 tools/flelift/tests/merge_survey_test.py
一時ディレクトリに boot/merge_survey.py を複製して、合成の survey_seg_0.jsonl で走らせる (実 results/ は触らない)。"""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'boot', 'merge_survey.py')
TOTAL = 942


def rows():
    out = []
    for i in range(TOTAL):
        if i == 941:
            out.append([i, 'noproc', 0])
        elif i in (29, 38, 39):
            out.append([i, 'empty', 0x1000 + i])
        elif i >= 900 and i % 2 == 0:
            out.append([i, 'empty', 0x2000 + i])
        else:
            out.append([i, 'ok', 0])
    return out


def run(lines):
    with tempfile.TemporaryDirectory() as td:
        boot = os.path.join(td, 'boot')
        os.makedirs(os.path.join(boot, 'results'))
        shutil.copy(SRC, os.path.join(boot, 'merge_survey.py'))
        with open(os.path.join(boot, 'results', 'survey_seg_0.jsonl'), 'w') as f:
            for r in lines:
                f.write(json.dumps(r) + '\n')
        p = subprocess.run([sys.executable, os.path.join(boot, 'merge_survey.py')],
                           capture_output=True, text=True, check=True)
        with open(os.path.join(boot, 'results', 'survey.json')) as f:
            return json.load(f), p.stdout


def main():
    data = rows()
    d, out = run(data)
    want_by = {'ok': 0, 'empty': 0, 'noproc': 0}
    for r in data:
        want_by[r[1]] += 1
    assert d['units_covered'] == TOTAL, (d['units_covered'], out)
    assert d['byCls'] == want_by, d['byCls']
    assert 'covered=942' in out, out
    print('PASS covered=%d byCls=%s' % (d['units_covered'], d['byCls']))

    d2, _ = run([r for r in data if r[1] == 'ok' or r[1] == 'unlifted'])
    assert d2['units_covered'] < TOTAL, d2
    print('PASS empty/noproc を落とすと covered < 942 (%d)' % d2['units_covered'])


if __name__ == '__main__':
    main()
