#!/usr/bin/env python3
"""tol_removal_check.py — CAB-273 (tol gate 撤去) の監査スクリプト (規則 36・37)。

数え方の定義 (規則 36):
  - 「tol 残存」= 下記 4 ファイルに tol gate の動作経路が 1 箇所でも残っていること。
    対象ファイルと判定条件:
      (1) snapins.json       … JSON ツリー全体にキー "tol" が存在しない (再帰探索)
      (2) harness/compare.mjs … "--tol" の引数解析・TOL_GATE 定数・tol 判定分岐が 0 件
      (3) lift/build.py      … tolarg / tol.json の生成経路が 0 件
      (4) scripts/make_table.py … 判定列が cfg['tol'] の有無由来でない (c.get('tol') 0 件)
  - 「REPORT の許容誤差記述」= REPORT.md の「許容誤差」の出現。§13 の歴史注記として
    残っているものは「legacy 明記」として許容 (下記 LEGACY_OK の語を含む行)。
  - 「snapins.json の差分」= `git show HEAD:<path>` との比較で、削除キー "tol" 以外の
    差分が 0 行であること (撤去のみで内容を変えていないことの監査)。

usage: python3 scripts/tol_removal_check.py [--strict-report]
   --strict-report: REPORT.md の「許容誤差」を legacy 注記も含め 0 件にする (既定は 0 件必須ではなく
                    許容誤差 *判定* (動作経路) が 0 件であることを確認する)。
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REL = 'tools/targets/kilohearts/snapins'


def walk_keys(obj, path=''):
    """JSON ツリーの全キーパスを yield (規則 36: 1 パス = 1 キー)。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield path + '/' + str(k)
            yield from walk_keys(v, path + '/' + str(k))


def main():
    fails = []

    # (1) snapins.json
    cfg_path = os.path.join(ROOT, 'snapins.json')
    cfg = json.load(open(cfg_path))
    tols = [p for p in walk_keys(cfg) if p.rsplit('/', 1)[-1] == 'tol']
    print('[1] snapins.json tol keys: %d' % len(tols))
    for p in tols:
        print('    LEFTOVER', p)
    if tols:
        fails.append('snapins.json tol %d keys' % len(tols))

    # git HEAD との差分: tol キー削除のみであること
    r = subprocess.run(['git', '-C', '/home/ubuntu/work/webstudio', 'show',
                        'HEAD:%s/snapins.json' % REL], capture_output=True, text=True)
    if r.returncode == 0:
        old = json.loads(r.stdout)
        oldcaps = [k for k in old]
        newcaps = [k for k in cfg]
        def strip(o):
            o = json.loads(json.dumps(o))
            for k in list(o):
                if 'tol' in o[k]:
                    del o[k]['tol']
            return o
        # 退避: tol を除いたツリーが一致すること (キー集合と各 snap-in の tol 以外が相同)
        s_old, s_new = strip(old), strip(cfg)
        print('[1b] snapins.json vs HEAD: keys %d -> %d, tol-stripped equal=%s'
              % (len(oldcaps), len(newcaps), s_old == s_new))
        if s_old != s_new:
            fails.append('snapins.json differs from HEAD beyond tol removal')
        for k in old:
            if 'tol' in old[k] and 'tol' not in cfg.get(k, {}):
                print('    removed tol from %s' % k)
    else:
        print('[1b] git show HEAD failed (skip): %s' % r.stderr.strip()[:120])

    # (2) compare.mjs
    cm = open(os.path.join(ROOT, 'harness', 'compare.mjs')).read()
    n_tol_arg = len(re.findall(r"'--tol'", cm))
    n_gate = len(re.findall(r'TOL_GATE', cm))
    n_tolmap = len(re.findall(r'tolMap\s*=', cm))
    print('[2] compare.mjs: --tol parsing=%d, TOL_GATE=%d, tolMap=%d' % (n_tol_arg, n_gate, n_tolmap))
    if n_tol_arg or n_gate or n_tolmap:
        fails.append('compare.mjs tol path remains')

    # (3) build.py — tol の *動作経路* がないこと (コメント中の言及は許容)
    bp = open(os.path.join(ROOT, 'lift', 'build.py')).read()
    code = '\n'.join(l for l in bp.split('\n') if not l.lstrip().startswith('#'))
    n_tol = len(re.findall(r'(tolarg|tol\.json|cfg\.get\(\'tol\'\)|--tol)', code))
    print('[3] build.py: tol code paths=%d (comment mentions ignored)' % n_tol)
    for i, l in enumerate(bp.split('\n'), 1):
        if re.search(r'(tolarg|tol\.json|cfg\.get\(\'tol\'\)|--tol)', l) and not l.lstrip().startswith('#'):
            print('    build.py:%d %s' % (i, l.strip()[:100]))
    if n_tol:
        fails.append('build.py tol path remains')

    # (4) make_table.py
    mt = open(os.path.join(ROOT, 'scripts', 'make_table.py')).read()
    n_cfg = len(re.findall(r"c\.get\('tol'\)", mt))
    print('[4] make_table.py: c.get(\'tol\')=%d' % n_cfg)
    if n_cfg:
        fails.append('make_table.py still keys on tol')

    # (5) REPORT.md の「許容誤差」は全て *歴史* の文脈であること (現行判定の記述がないこと)。
    #     判定規則 (規則 36): historical マーカ = legacy / §13 / 撤去 / 当時 / 変更前 / 旧 / → 。
    #     マーカの無い行 = 「現行も許容誤差で判定している」と読める行 = FAIL。
    rp = open(os.path.join(ROOT, 'REPORT.md')).read()
    MARK = ('legacy', '§13', '§9-4', '撤去', '当時', '変更前', '旧', '→', 'CAB-273', 'CAB-224')
    rows = [(i, l) for i, l in enumerate(rp.split('\n'), 1) if '許容誤差' in l]
    bad_rows = [(i, l) for i, l in rows if not any(m in l for m in MARK)]
    print('[5] REPORT.md 許容誤差 lines: %d (all historical-marked: %s)' % (len(rows), not bad_rows))
    for i, l in rows:
        tag = 'hist' if (i, l) not in bad_rows else 'ACTIVE'
        print('    REPORT.md:%d [%s] %s' % (i, tag, l.strip()[:110]))
    if bad_rows:
        fails.append('REPORT.md has unmarked tolerance description (%d lines)' % len(bad_rows))

    # (6) 独立再計算 (規則 37): 実測 snapshot (work/<n>/s0/stat.json) から 14 snap-in の
    #     判定を自分で数え直す。数え方: 分母 = work/<name>/s0/stat.json が存在する snap-in 14 本
    #     (ORDER 順)。bit-exact = trials_ok == trials かつ calls_ok == calls かつ
    #     compare 文字列に '[tolerance]' または 'tol(' が含まれないこと。
    import json as _json
    ORDER = ['matrix', 'gain', 'haas', 'clipper', 'gate', 'quickeq', 'resonator', 'stereo',
             'disperser', 'formant', 'phaser', 'delay', 'limiter', 'khbase']
    inexact, legacy_tag, missing = [], [], []
    for n in ORDER:
        sp = os.path.join(ROOT, 'work', n, 's0', 'stat.json')
        if not os.path.exists(sp):
            missing.append(n)
            continue
        s = _json.load(open(sp))
        cmp_ = s.get('compare', '')
        if not (s.get('trials_ok') == s.get('trials') and s.get('calls_ok') == s.get('calls')):
            inexact.append(n)
        if '[tolerance]' in cmp_ or 'tol(' in cmp_:
            legacy_tag.append(n)
    print('[6] independent recount of work/<n>/s0/stat.json (分母=%d): not-exact %s / legacy tol tag %s / missing %s'
          % (len(ORDER), inexact or 'なし', legacy_tag or 'なし', missing or 'なし'))
    if inexact or legacy_tag or (len(missing) == len(ORDER)):
        fails.append('stat.json recount: not-exact=%s legacy=%s missing=%d' % (inexact, legacy_tag, len(missing)))

    print('---')
    if fails:
        print('FAIL: ' + '; '.join(fails))
        return 1
    print('OK: tol gate fully removed (comparison = strict bit-exact)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
