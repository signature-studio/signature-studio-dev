#!/usr/bin/env python3
"""distortion (PLG-F6 / #203) の合否判定。 不合格が 1 行でもあれば exit 1 (表示だけで終わらせない)。

  judge.py STATUS.csv --blocks B1,B2,... --audit AUDIT.csv [--allow-unimpl BLOCK=N ...]
      Delphi DLL の閉包 lift (lift/batch_lift.sh の status.csv 形式; 列名で参照)。 各 block に付き
        行がちょうど 1 本 / 全列が整数 / lift_rc=0 / f80_funcs=0 / emcc_c_rc=0 /
        0 <= declares_unimpl <= 許容値 (既定 0; -1 = 集計不能は不合格) / defines>=1 / closure_funcs>=1
      に加え、AUDIT.csv (engine_defs.py の欠落監査: block,missing_define,missing_bytes,missing_ref,extra_inside,function_defines) から
        missing_define=0 (閉包の全 range の開始 VA に define がある) /
        defines == function_defines == closure_funcs + extra_inside (RetDec が range 内部に切り出した関数の分だけ増える)
      を要求する。 要求外の block の行があっても不合格。
  judge.py ENGINES.csv --engines --blocks B1,B2,...
      engine_lift.sh の 1 行サマリ形式。 行 1 本 / 整数 / lift_rc=0 / defines>=1 / pdata_funcs>=1 / 集計不能 (-1) 無し、に加え
      emcc_c_rc=0 / missing_define=0 / f80_funcs=0 (f80 lowering 後) を合格条件とする (PLG-F6-2 #545)。
      未実装 helper の数 / lowering 前の f80・emcc は合否に使わず表示する。

exit: 0 = 全 block 合格, 1 = 不合格あり, 2 = 入力不正 (引数 / ファイル / ヘッダ)。
"""
import argparse, csv, sys

SHELL_COLS = ['block', 'name', 'closure_funcs', 'closure_bytes', 'lift_rc', 'defines', 'declares_unimpl',
              'f80_funcs', 'emcc_c_rc', 'seconds']
AUDIT_COLS = ['block', 'missing_define', 'missing_bytes', 'missing_ref', 'extra_inside', 'function_defines']
ENGINE_COLS = ['block', 'pdata_funcs', 'lift_rc', 'defines', 'f80_funcs', 'unimpl_helpers', 'emcc_c_rc',
               'f80_funcs_pre', 'emcc_c_rc_pre_f80', 'lift_s', 'missing_define', 'missing_bytes',
               'missing_ref', 'extra_inside', 'function_defines']


def usage_error(msg):
    print('judge: 入力不正: %s' % msg, file=sys.stderr)
    sys.exit(2)


def load(path, cols):
    try:
        rows = list(csv.reader(open(path)))
    except OSError as e:
        usage_error(str(e))
    if not rows:
        usage_error('%s が空' % path)
    if rows[0] != cols:
        usage_error('ヘッダ不一致 %s (期待 %s)' % (rows[0], cols))
    out = []
    for i, r in enumerate(rows[1:], 2):
        if len(r) != len(cols):
            usage_error('%s:%d 列数 %d (期待 %d)' % (path, i, len(r), len(cols)))
        out.append(dict(zip(cols, r)))
    return out


def to_int(v):
    try:
        return int(v)
    except ValueError:
        return None


def judge_shell(rows, blocks, allow, audit):
    fails = 0
    seen = {r['block'] for r in rows}
    for r in rows:
        if r['block'] not in {str(b) for b in blocks}:
            fails += 1
            print('FAIL  block %s: 対象外の行 (name=%s)' % (r['block'], r['name']))
    for b in blocks:
        mine = [r for r in rows if r['block'] == str(b)]
        if len(mine) != 1:
            fails += 1
            print('FAIL  block %d: 行数 %d (期待 1)' % (b, len(mine)))
            continue
        r = mine[0]
        v = {k: to_int(r[k]) for k in SHELL_COLS if k not in ('block', 'name')}
        bad = [k for k, x in v.items() if x is None]
        if bad:
            fails += 1
            print('FAIL  block %d %s: 非整数の列 %s' % (b, r['name'], bad))
            continue
        why = []
        if v['lift_rc'] != 0:
            why.append('lift_rc=%d' % v['lift_rc'])
        if v['f80_funcs'] != 0:
            why.append('f80_funcs=%d' % v['f80_funcs'])
        if v['emcc_c_rc'] != 0:
            why.append('emcc_c_rc=%d' % v['emcc_c_rc'])
        lim = allow.get(b, 0)
        if not 0 <= v['declares_unimpl'] <= lim:
            why.append('declares_unimpl=%d (許容 0..%d)' % (v['declares_unimpl'], lim))
        if v['defines'] < 1:
            why.append('defines=%d' % v['defines'])
        if v['closure_funcs'] < 1:
            why.append('closure_funcs=%d' % v['closure_funcs'])
        am = [x for x in audit if x['block'] == str(b)]
        if len(am) != 1:
            why.append('audit 行数 %d (期待 1)' % len(am))
        else:
            av = {k: to_int(x) for k, x in am[0].items()}
            if any(x is None for x in av.values()):
                why.append('audit に非整数')
            else:
                if av['missing_define'] != 0:
                    why.append('missing_define=%d' % av['missing_define'])
                if not v['defines'] == av['function_defines'] == v['closure_funcs'] + av['extra_inside']:
                    why.append('defines=%d function_defines=%d closure_funcs+extra_inside=%d' % (
                        v['defines'], av['function_defines'], v['closure_funcs'] + av['extra_inside']))
        if why:
            fails += 1
        print('%s  block %d %-24s lift_rc=%d defines=%d closure_funcs=%d f80=%d unimpl=%d emcc_c=%d%s' % (
            'FAIL' if why else 'PASS', b, r['name'], v['lift_rc'], v['defines'], v['closure_funcs'], v['f80_funcs'],
            v['declares_unimpl'], v['emcc_c_rc'], ('  <- ' + '; '.join(why)) if why else ''))
    return fails


def judge_engine(rows, blocks):
    fails = 0
    for r in rows:
        if r['block'] not in {str(b) for b in blocks}:
            fails += 1
            print('FAIL  engine %s: 対象外の行' % r['block'])
    for b in blocks:
        mine = [r for r in rows if r['block'] == str(b)]
        if len(mine) != 1:
            fails += 1
            print('FAIL  engine %d: 行数 %d (期待 1)' % (b, len(mine)))
            continue
        r = mine[0]
        v = {k: to_int(r[k]) for k in ENGINE_COLS}
        bad = [k for k, x in v.items() if x is None]
        if bad:
            fails += 1
            print('FAIL  engine %d: 非整数の列 %s' % (b, bad))
            continue
        why = []
        if v['lift_rc'] != 0:
            why.append('lift_rc=%d' % v['lift_rc'])
        if v['defines'] < 1:
            why.append('defines=%d' % v['defines'])
        if v['pdata_funcs'] < 1:
            why.append('pdata_funcs=%d' % v['pdata_funcs'])
        neg = [k for k in ('f80_funcs', 'unimpl_helpers', 'emcc_c_rc', 'missing_define') if v[k] < 0]
        if neg:
            why.append('集計不能 (-1) の列 %s' % neg)
        # PLG-F6-2 (#545) の受入条件: final.ll が emcc -c を通る / .pdata の全 range に define がある / f80 が残らない
        for k in ('emcc_c_rc', 'missing_define', 'f80_funcs'):
            if v[k] > 0:
                why.append('%s=%d' % (k, v[k]))
        if v['defines'] != v['function_defines'] + 1 and v['defines'] != v['function_defines']:
            why.append('defines=%d function_defines=%d (差は entry_point の 0 か 1 のみ許容)' % (v['defines'], v['function_defines']))
        if why:
            fails += 1
        print('%s  engine %d pdata=%d lift_rc=%d defines=%d emcc_c=%d missing_define=%d f80=%d | 参考(合否外): unimpl=%d f80_pre=%d emcc_c_pre_f80=%d%s' % (
            'FAIL' if why else 'PASS', b, v['pdata_funcs'], v['lift_rc'], v['defines'], v['emcc_c_rc'], v['missing_define'],
            v['f80_funcs'], v['unimpl_helpers'], v['f80_funcs_pre'], v['emcc_c_rc_pre_f80'], ('  <- ' + '; '.join(why)) if why else ''))
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('csv')
    ap.add_argument('--blocks', required=True)
    ap.add_argument('--engines', action='store_true')
    ap.add_argument('--allow-unimpl', action='append', default=[], metavar='BLOCK=N')
    ap.add_argument('--audit')
    a = ap.parse_args()
    try:
        blocks = [int(x) for x in a.blocks.split(',')]
        allow = {int(k): int(n) for k, n in (s.split('=') for s in a.allow_unimpl)}
    except ValueError:
        usage_error('--blocks / --allow-unimpl の書式')
    if a.engines:
        fails = judge_engine(load(a.csv, ENGINE_COLS), blocks)
    else:
        if not a.audit:
            usage_error('--audit が必要')
        fails = judge_shell(load(a.csv, SHELL_COLS), blocks, allow, load(a.audit, AUDIT_COLS))
    print('judge: %d/%d block 合格' % (len(blocks) - min(fails, len(blocks)), len(blocks)) if fails else
          'judge: %d/%d block 合格' % (len(blocks), len(blocks)))
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
