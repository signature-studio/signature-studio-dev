#!/usr/bin/env python3
"""sampler の lift 判定 (gate)。 不合格が 1 件でもあれば exit 1、入力不正は exit 2、全件合格のみ exit 0。

  judge.py shells  STATUS_CSV --blocks B1,B2,... [--allow-unimpl B=N,...] [--allow-names N1,N2] [--out OUT_CSV]
  judge.py engines ENGINES_CSV --blocks B1,B2,...

shells: batch_lift.sh の status.csv (header: block,name,closure_funcs,closure_bytes,lift_rc,defines,declares_unimpl,f80_funcs,emcc_c_rc,seconds)。
  同一 block の行が複数あれば最後の行を採る。 --blocks の全 block に行があること (欠落は不合格)。
  各行の合格条件: lift_rc==0 / emcc_c_rc==0 / f80_funcs==0 / 0<=declares_unimpl<=許容上限 (既定 0) / defines>0。
  列 unimpl_names (任意) があれば、名前が --allow-names に含まれることも要求する。 数値が整数でない・負 (-1 = 計測不能) は不合格。
engines: engine_lift.sh の 1 行サマリ。 合格条件: lift_rc==0 / defines>0 / pdata_funcs>0 / 行が揃う /
  emcc_c_rc_after_f80==0 (#540 受入条件 1: 全 .pdata lift の最終 IR が emcc -c を通る) / missing_ref==0。 整数でない値・-1 (未計測) は不合格。
"""
import csv, sys, argparse

SHELL_COLS = ['block', 'name', 'closure_funcs', 'closure_bytes', 'lift_rc', 'defines', 'declares_unimpl', 'f80_funcs', 'emcc_c_rc', 'seconds']
ENGINE_COLS = ['block', 'pdata_funcs', 'lift_rc', 'defines', 'f80_funcs', 'unimpl_helpers', 'emcc_c_rc', 'fixcmp_patched',
               'emcc_c_rc_after_fixcmp', 'lift_s', 'missing_define', 'missing_bytes', 'missing_ref', 'extra_inside', 'function_defines', 'emcc_c_rc_after_f80']


def load(path, cols):
    try:
        rows = list(csv.reader(open(path)))
    except OSError as e:
        sys.exit('judge: 入力を読めない: %s' % e)
    if not rows or rows[0][:len(cols)] != cols:
        print('judge: header 不一致 (期待 %s)' % ','.join(cols), file=sys.stderr)
        sys.exit(2)
    return rows[0], rows[1:]


def to_int(row, hdr, col):
    try:
        return int(row[hdr.index(col)])
    except (ValueError, IndexError):
        return None


def judge_shells(a):
    want = [int(x) for x in a.blocks.split(',') if x]
    allow = {int(k): int(v) for k, v in (kv.split('=') for kv in a.allow_unimpl.split(',') if kv)}
    names_ok = set(x for x in a.allow_names.split(',') if x)
    hdr, body = load(a.csv, SHELL_COLS)
    last = {}
    for r in body:
        if r and r[0].isdigit():
            last[int(r[0])] = r
    fails, kept = [], []
    for b in want:
        r = last.get(b)
        if r is None:
            fails.append((b, '?', '行が無い'))
            continue
        kept.append(r)
        v = {c: to_int(r, hdr, c) for c in ('lift_rc', 'defines', 'declares_unimpl', 'f80_funcs', 'emcc_c_rc')}
        why = []
        for c, x in v.items():
            if x is None:
                why.append('%s が整数でない' % c)
        if not why:
            if v['lift_rc'] != 0: why.append('lift_rc=%d' % v['lift_rc'])
            if v['emcc_c_rc'] != 0: why.append('emcc_c_rc=%d' % v['emcc_c_rc'])
            if v['f80_funcs'] != 0: why.append('f80_funcs=%d' % v['f80_funcs'])
            if v['defines'] <= 0: why.append('defines=%d' % v['defines'])
            lim = allow.get(b, 0)
            if not 0 <= v['declares_unimpl'] <= lim: why.append('declares_unimpl=%d (許容 0..%d)' % (v['declares_unimpl'], lim))
        if 'unimpl_names' in hdr:
            names = [x for x in r[hdr.index('unimpl_names')].split('|') if x]
            bad = [x for x in names if x not in names_ok]
            if bad: why.append('許可外の未実装 helper: %s' % ','.join(bad))
        if why:
            fails.append((b, r[1] if len(r) > 1 else '?', '; '.join(why)))
    if a.out and not fails:
        csv.writer(open(a.out, 'w')).writerows([hdr] + kept)
    for b, n, w in fails:
        print('  FAIL block %s (%s): %s' % (b, n, w))
    if 'lowered' in hdr:
        low = [r[0] for r in kept if to_int(r, hdr, 'lowered') == 1]
        print('  lowering 後の値で判定した block: %d/%d (%s) — この block の f80 / emcc -c の判定は lowering 後の値による (raw は f80_raw / emcc_c_rc_raw)'
              % (len(low), len(want), ','.join(low) or '-'))
    if fails:
        print('judge shells: FAIL %d/%d' % (len(fails), len(want)))
        return 1
    print('judge shells: PASS %d/%d (lift_rc / emcc_c_rc / f80 全 0, declares_unimpl は許容内)' % (len(want), len(want)))
    return 0


def judge_engines(a):
    want = [int(x) for x in a.blocks.split(',') if x]
    hdr, body = load(a.csv, ENGINE_COLS)
    last = {int(r[0]): r for r in body if r and r[0].isdigit()}
    fails = []
    for b in want:
        r = last.get(b)
        if r is None:
            fails.append((b, '行が無い'))
            continue
        v = {c: to_int(r, hdr, c) for c in ('pdata_funcs', 'lift_rc', 'defines', 'emcc_c_rc_after_f80', 'missing_ref')}
        why = ['%s が整数でない' % c for c, x in v.items() if x is None]
        if not why:
            if v['lift_rc'] != 0: why.append('lift_rc=%d' % v['lift_rc'])
            if v['defines'] <= 0: why.append('defines=%d' % v['defines'])
            if v['pdata_funcs'] <= 0: why.append('pdata_funcs=%d' % v['pdata_funcs'])
            if v['emcc_c_rc_after_f80'] != 0: why.append('emcc_c_rc_after_f80=%d (最終 IR が emcc -c を通らない)' % v['emcc_c_rc_after_f80'])
            if v['missing_ref'] != 0: why.append('missing_ref=%d (参照されるのに define が無い関数)' % v['missing_ref'])
        if why:
            fails.append((b, '; '.join(why)))
    for b, w in fails:
        print('  FAIL engine block %s: %s' % (b, w))
    if fails:
        print('judge engines: FAIL %d/%d' % (len(fails), len(want)))
        return 1
    print('judge engines: PASS %d/%d (lift_rc 0 / define>0 / 最終 IR の emcc -c rc 0 / missing_ref 0)' % (len(want), len(want)))
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['shells', 'engines'])
    p.add_argument('csv')
    p.add_argument('--blocks', required=True)
    p.add_argument('--allow-unimpl', default='')
    p.add_argument('--allow-names', default='')
    p.add_argument('--out', default='')
    a = p.parse_args()
    sys.exit(judge_shells(a) if a.mode == 'shells' else judge_engines(a))
