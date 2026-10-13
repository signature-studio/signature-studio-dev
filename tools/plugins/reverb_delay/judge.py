#!/usr/bin/env python3
"""reverb_delay e2e の合否判定 (gate)。 不合格が 1 件でもあれば exit 1。

usage: judge.py <status.csv> <block> [<block> ...] [--closure-dir DIR]

status.csv は lift/batch_lift.sh の出力。 列は**名前で読む**: 必須 10 列 (block,name,closure_funcs,closure_bytes,lift_rc,defines,declares_unimpl,f80_funcs,emcc_c_rc,seconds) が
ヘッダに全部あることを要求し、余分な列 (既定鎖の icall,dispatch_calls など) は許容する。 列の位置には依存しない。
block ごとの合格条件 (すべて満たすこと):
  lift_rc == 0 / emcc_c_rc == 0 / f80_funcs == 0 / declares_unimpl == 0 / defines == closure_funcs / defines > 0
  (defines == closure_funcs は DEFECT 検出用: 閉包 ranges を RetDec が取りこぼすと define が減る。 DIR/block*.json があればその unique_funcs とも一致を要求)
行の過不足もすべて不合格: 指定 block の行が無い / 数値でない列 / 行の列数がヘッダと違う (不足・過剰) / 必須列の欠落。 指定外 block の行は無視する。
同一 block が複数行ある場合は最後の行を採用するが、複数行あったこと自体を警告する (batch_lift.sh は追記式)。
"""
import csv, json, os, sys

COLS = ['block', 'name', 'closure_funcs', 'closure_bytes', 'lift_rc', 'defines', 'declares_unimpl', 'f80_funcs', 'emcc_c_rc', 'seconds']
INT_COLS = [c for c in COLS if c != 'name']


def judge(hdr, rows, want, closure_dir=None):
    """returns (fail_messages, per_block_lines)"""
    fails, lines = [], []
    by = {}
    for i, r in enumerate(rows):
        if len(r) != len(hdr):
            fails.append('row %d: 列数 %d (ヘッダ %d): %r' % (i + 2, len(r), len(hdr), r))
            continue
        by.setdefault(r[hdr.index('block')], []).append(r)
    for b in want:
        rs = by.get(b)
        if not rs:
            fails.append('block %s: status.csv に行が無い' % b)
            lines.append('%s MISSING' % b)
            continue
        if len(rs) > 1:
            lines.append('%s warn: %d 行 (最後の行を採用)' % (b, len(rs)))
        r = dict(zip(hdr, rs[-1]))
        try:
            v = {c: int(r[c]) for c in INT_COLS}
        except ValueError:
            fails.append('block %s: 数値でない列: %r' % (b, rs[-1]))
            lines.append('%s BADROW' % b)
            continue
        why = []
        if v['lift_rc'] != 0:
            why.append('lift_rc=%d' % v['lift_rc'])
        if v['emcc_c_rc'] != 0:
            why.append('emcc_c_rc=%d' % v['emcc_c_rc'])
        if v['f80_funcs'] != 0:
            why.append('f80_funcs=%d' % v['f80_funcs'])
        if v['declares_unimpl'] != 0:
            why.append('declares_unimpl=%d' % v['declares_unimpl'])
        if v['defines'] <= 0:
            why.append('defines=%d' % v['defines'])
        if v['defines'] != v['closure_funcs']:
            why.append('defines=%d != closure_funcs=%d' % (v['defines'], v['closure_funcs']))
        if closure_dir:
            p = os.path.join(closure_dir, 'block%05d.json' % int(b))
            try:
                uf = json.load(open(p))['unique_funcs']
                if uf != v['closure_funcs']:
                    why.append('closure_funcs=%d != %s unique_funcs=%d' % (v['closure_funcs'], os.path.basename(p), uf))
            except (OSError, KeyError, ValueError) as e:
                why.append('closure json 読めず: %s' % e)
        lines.append('%s %-24s %s%s' % (b, r['name'], 'PASS' if not why else 'FAIL ', '; '.join(why)))
        if why:
            fails.append('block %s %s: %s' % (b, r['name'], '; '.join(why)))
    return fails, lines


def main(argv):
    cdir = None
    if '--closure-dir' in argv:
        i = argv.index('--closure-dir')
        cdir = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    path, want = argv[0], argv[1:]
    with open(path) as f:
        rows = list(csv.reader(f))
    if not rows or any(c not in rows[0] for c in COLS):
        print('judge: FAIL ヘッダに必須列が無い (必須: %s): %r' % (','.join(COLS), rows[:1]), file=sys.stderr)
        return 1
    fails, lines = judge(rows[0], rows[1:], want, cdir)
    print('\n'.join(lines))
    if fails:
        print('judge: FAIL %d 件 / %d block' % (len(fails), len(want)), file=sys.stderr)
        for m in fails:
            print('  ' + m, file=sys.stderr)
        return 1
    print('judge: PASS %d/%d block (lift_rc / emcc -c / f80 / declares_unimpl が全 0, defines == closure_funcs)' % (len(want), len(want)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
