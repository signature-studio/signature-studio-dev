#!/usr/bin/env python3
"""dynamics 7 閉包への間接呼出到達先の追加 (#200 PM 指示。 sampler/closure_indirect.py (#537) の定義を流用)。

  python3 dynamics/closure_indirect.py [--out-dir DIR]     前提: dynamics_e2e.sh 実行済み (work/closure, work/winfuncs, work/fw_hash_counts.json) + `source dynamics/env.sh`

定義・BFS・検査 C1/C3/C4 は sampler/closure_indirect.py の Pe クラス・bfs を import して使う (sampler 側は変更しない)。
C2 は sampler/unreached_unique.py と同じ定義 (非共通 ∧ base 外 ∧ データ参照) を本ファイル内で再計算し、Pe.dataref の結果と照合する
(dynamics には sampler の unreached.json が無いため、照合先は再計算値)。
出力: <out-dir>/indirect/block<B>.ranges.txt (total の ranges、lift 入力)、<out-dir>/indirect.json、stdout の表
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, '..')
sys.path.insert(0, os.path.join(P, 'sampler'))
import closure_indirect as ci  # noqa: E402

BLOCKS = [('Fruity Limiter', 19021), ('Fruity Compressor', 18990), ('Maximus', 19148), ('Soundgoodizer', 19245),
          ('Emphasis', 18974), ('Fruity Multiband Compressor', 19047), ('Transient Processor', 19251)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out-dir', default=os.path.join(ci.WORK, 'dynamics'))
    a = ap.parse_args()
    cnt = json.load(open(os.path.join(ci.WORK, 'fw_hash_counts.json')))
    os.makedirs(os.path.join(a.out_dir, 'indirect'), exist_ok=True)
    out, bad = {}, []
    print('| プラグイン | base 関数 / B | root (データ参照あり) 関数 / B | callee 関数 / B | **total 関数 / B** | 非共通に占める total (関数 % / B %) | frontier 関数 / B | lea 残 関数 / B | 非共通のうち未到達 関数 / B |')
    print('|---|--:|--:|--:|--:|--:|--:|--:|--:|')
    for name, blk in BLOCKS:
        x = ci.Pe(blk, cnt)
        clo = json.load(open(os.path.join(ci.WORK, 'closure', 'block%05d.json' % blk)))
        entries = [int(v, 16) - x.base for v in clo['entries'].values()]
        base_ref = {int(r.split('-')[0], 16) - x.base for r in clo['ranges']}
        base, _ = x.bfs(entries, lambda f: x.edges(f)[0])
        c1 = base == base_ref and len(base) > 0
        cand = sorted(x.nonfw - base)
        roots = x.dataref()(cand) if cand else set()
        # C2: unreached_unique.py と同じ定義の再計算 (非共通 ∧ 閉包外 (ranges 由来) ∧ データ参照)
        rest0 = sorted(x.nonfw - base_ref)
        c2 = bool(rest0) and x.dataref()(rest0) == roots
        total, front = x.bfs(list(base) + sorted(roots), lambda f: x.edges(f)[0])
        callee = total - base - roots
        leas = set()
        for f in total:
            leas |= x.edges(f)[1]
        lea_res = {f for f in leas if f in x.nonfw and f not in total}
        rest = x.nonfw - total
        c3 = total <= x.nonfw and base <= total and roots <= total
        over, _ = x.bfs(list(base | roots), x.edges_bytescan)
        c4 = total <= over
        for tag, ok in (('C1 base 再現', c1), ('C2 root 再計算一致', c2), ('C3 total ⊆ 非共通 / base ⊆ total', c3), ('C4 capstone ⊆ byte 走査', c4)):
            if not ok:
                bad.append('%s: %s' % (name, tag))
        open(os.path.join(a.out_dir, 'indirect', 'block%05d.ranges.txt' % blk), 'w').write(','.join(x.ranges(total)))
        out[name] = {'block': blk, 'nonfw_funcs': len(x.nonfw), 'nonfw_bytes': x.size(x.nonfw),
                     'base_funcs': len(base), 'base_bytes': x.size(base), 'root_funcs': len(roots), 'root_bytes': x.size(roots),
                     'callee_funcs': len(callee), 'callee_bytes': x.size(callee), 'total_funcs': len(total), 'total_bytes': x.size(total),
                     'frontier_funcs': len(front), 'frontier_bytes': x.size(front), 'lea_residual_funcs': len(lea_res), 'lea_residual_bytes': x.size(lea_res),
                     'unreached_funcs': len(rest), 'unreached_bytes': x.size(rest),
                     'bytescan_total_funcs': len(over), 'bytescan_total_bytes': x.size(over), 'checks': {'C1': c1, 'C2': c2, 'C3': c3, 'C4': c4}}
        o = out[name]
        f = lambda k: '%s / %s' % (format(o[k + '_funcs'], ','), format(o[k + '_bytes'], ','))
        print('| %s | %s | %s | %s | **%s** | %.1f / %.1f | %s | %s | %s |' % (
            name, f('base'), f('root'), f('callee'), f('total'), 100.0 * o['total_funcs'] / o['nonfw_funcs'], 100.0 * o['total_bytes'] / o['nonfw_bytes'],
            f('frontier'), f('lea_residual'), f('unreached')))
    tot = {k: sum(v[k] for v in out.values()) for k in ('base_funcs', 'base_bytes', 'root_funcs', 'root_bytes', 'callee_funcs', 'callee_bytes', 'total_funcs', 'total_bytes')}
    out['_sum'] = tot
    print('| 計 | %s / %s | %s / %s | %s / %s | **%s / %s** | | | | |' % tuple(format(tot[k], ',') for k in (
        'base_funcs', 'base_bytes', 'root_funcs', 'root_bytes', 'callee_funcs', 'callee_bytes', 'total_funcs', 'total_bytes')))
    json.dump(out, open(os.path.join(a.out_dir, 'indirect.json'), 'w'), indent=1)
    for b in bad:
        print('FAIL', b, file=sys.stderr)
    print('dynamics closure_indirect: %s' % ('FAIL %d' % len(bad) if bad else 'PASS 4 checks x %d plugins' % len(BLOCKS)))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
