#!/usr/bin/env python3
"""lift 準備度の合否判定 (gate)。 batch_lift.sh の status.csv を読み、targets.py の 28 本すべてが合格のときだけ exit 0。
  usage: judge.py <status.csv>
合格条件 (行ごと。 同一 block が複数行なら最後の行): 28 本すべての行が存在し、名前が targets.py と一致し、
  closure_funcs > 0 / lift_rc == 0 / emcc_c_rc == 0 / f80_funcs == 0 / declares_unimpl == 0 / defines >= closure_funcs。
  (defines > closure_funcs は正常: RetDec が 1 range を複数 define に切る。 個々の関数の脱落は closure_defs.py が見る)
  (-1 は「final.ll や simd.log が生成されなかった」の印なので、f80 / declares_unimpl の == 0 条件で不合格になる)
不合格条件の追加: header 不一致 / targets に無い block の行 / 数値でない欄。
exit: 0 = 全合格 / 1 = 1 件以上の不合格 / 2 = 入力が読めない。 不合格でも表示だけで終わらせない。
"""
import csv, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from targets import TARGETS  # noqa: E402

HDR = ['block', 'name', 'closure_funcs', 'closure_bytes', 'lift_rc', 'defines', 'declares_unimpl', 'f80_funcs', 'emcc_c_rc', 'seconds']
NUM = [h for h in HDR if h != 'name']


def judge(rows):
    """rows: csv.reader の行 (header 込み)。 戻り値: (失敗の説明リスト, 合格した本数)"""
    fails = []
    if not rows or rows[0] != HDR:
        return ['header 不一致: %r' % (rows[0] if rows else None)], 0
    want = {b: n for n, b, _, _ in TARGETS}
    last = {}
    for r in rows[1:]:
        if len(r) != len(HDR):
            fails.append('列数 %d != %d: %r' % (len(r), len(HDR), r))
            continue
        try:
            last[int(r[0])] = r
        except ValueError:
            fails.append('block が整数でない: %r' % (r,))
    for b in sorted(set(last) - set(want)):
        fails.append('block %d: targets.py に無い行' % b)
    ok = 0
    for name, b, _, _ in TARGETS:
        r = last.get(b)
        if r is None:
            fails.append('%s (%d): status に行が無い' % (name, b))
            continue
        d = dict(zip(HDR, r))
        try:
            v = {k: int(d[k]) for k in NUM}
        except ValueError:
            fails.append('%s (%d): 数値でない欄 %r' % (name, b, r))
            continue
        why = []
        if d['name'] != name:
            why.append('name=%r' % d['name'])
        if v['closure_funcs'] <= 0:
            why.append('closure_funcs=%d' % v['closure_funcs'])
        for k in ('lift_rc', 'emcc_c_rc', 'f80_funcs', 'declares_unimpl'):
            if v[k] != 0:
                why.append('%s=%d' % (k, v[k]))
        if v['defines'] < v['closure_funcs']:
            why.append('defines=%d < closure_funcs=%d' % (v['defines'], v['closure_funcs']))
        if why:
            fails.append('%s (%d): %s' % (name, b, ', '.join(why)))
        else:
            ok += 1
    return fails, ok


def main():
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        rows = list(csv.reader(open(sys.argv[1])))
    except OSError as e:
        print('judge: 入力が読めない: %s' % e, file=sys.stderr)
        return 2
    fails, ok = judge(rows)
    for f in fails:
        print('  FAIL', f)
    print('judge: %s %d/%d 本合格 (不合格の説明 %d 件)' % ('PASS' if not fails else 'FAIL', ok, len(TARGETS), len(fails)))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
