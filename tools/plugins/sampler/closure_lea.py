#!/usr/bin/env python3
"""#537 の推移閉包 (total) に、`lea reg,[rip+X]` で開始 VA を取られている非共通関数を root として足した閉包 (#627)。 lift/plugin_closure.py は変更しない。

  closure_lea.py [--out-dir DIR]    前提: indirect_e2e.sh の前半 (closure_indirect.py 実行済み = work/sampler/indirect.json) + `source sampler/env.sh`

定義 (closure_indirect.py と同じ語彙):
  total      = #537 の推移閉包 (base ∪ データ参照 root から `call/jmp rel32` で到達する非共通関数)
  lea root   = 閉包の関数が `lea reg,[rip+X]` で開始 VA を取っている非共通関数のうち閉包に無いもの。 root を足して `call/jmp rel32` で広げ、
               新しく入った関数の lea 先がもう無くなるまで繰り返す (固定点)。 1 巡目 (total の関数だけが取る lea 先) が #537 の「lea 残」。
  total2     = 固定点に達した閉包。 callee = total2 − total − lea root
検査 (全て満たさなければ exit 1):
  L1 total の関数数・バイトが work/sampler/indirect.json と一致 (#537 の再現。 base / root も同様)
  L2 1 巡目の lea root が indirect.json の lea_residual と一致 (issue #627 の 153 関数 / 38,656 B の再現)
  L3 固定点の独立検証: total2 の全関数について、`call/jmp rel32` 先と `lea [rip+X]` 先の非共通関数が全て total2 に入っている
  L4 total ⊆ total2 ⊆ 非共通関数 (framework を lift 対象に混ぜない)
  L5 別算法 (命令境界を見ない E8/E9 rel32 の全オフセット走査) の過大近似閉包に total2 が含まれる
  L6 反例入力 (C4 の識別力): 関数本体に「命令内の即値 (mov rax, imm64) に E8 rel32 が埋まる」偽の呼出を注入し、byte 走査だけが偽の到達先を拾い capstone 版は拾わないこと
  L7 実データの偽到達先: 命令境界に無い E8/E9 のうち、到達先が total2 外の非共通関数の開始になるもの (= 閉包を偽に広げうる) が 0 であること。 機会数・関数開始を指す数 (total2 内を含む) を併記
出力: work/sampler/lea/block<B>.ranges.txt (total2 の ranges、lift 入力) / .total.ranges.txt (#537 total) / .frontier.json (total・total2 から呼ぶ framework 関数の VA)、work/sampler/lea.json、stdout の表
"""
import argparse, json, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import closure_indirect as CI  # noqa: E402
import targets  # noqa: E402

WORK = CI.WORK


def lea_fixpoint(x, total, calls):
    """total を出発点に、lea 先 (非共通) を root に足して call/jmp で広げる固定点。 返り値 (total2, lea_roots(巡目別), frontier)"""
    cur, front = set(total), set()
    rounds = []
    while True:
        leas = set()
        for f in cur:
            leas |= x.edges(f)[1]
        new = {f for f in leas if f in x.nonfw and f not in cur}
        if not new:
            return cur, rounds, front
        rounds.append(new)
        cur, front = x.bfs(sorted(cur) + sorted(new), calls)


def verify_fixpoint(x, total2):
    """L3: 閉包の性質を BFS とは別に全関数について確かめる。 返り値 = 閉包から漏れた (関数, 先) の数"""
    miss = 0
    for f in total2:
        c, l = x.edges(f)
        for t in (c | l):
            if t in x.nonfw and t not in total2:
                miss += 1
    return miss


def decoy_selftest(x, total2):
    """L6: 閉包内の関数 f0 の本体を `mov rax, imm64` (imm64 の中に E8 rel32 を埋める) に差し替え、
    その E8 が total2 外の非共通関数 t を指すようにする。 命令境界を見る capstone 版は t を拾わず、byte 走査版だけが t を拾うことを確かめる。
    返り値 (ok, 詳細)"""
    outside = sorted(x.nonfw - total2)
    if not outside:
        return False, 'total2 外の非共通関数が無く偽の到達先を作れない'
    t = outside[0]
    f0 = max(total2)
    o = 2
    rel = t - (f0 + o + 5)
    body = b'\x48\xb8' + b'\xe8' + struct.pack('<i', rel) + b'\x00\x00\x00' + b'\xc3'
    orig = x.body
    x._code.pop(f0, None)
    x.body = lambda f: body if f == f0 else orig(f)
    try:
        cap = x.edges(f0)[0]
        byt = x.edges_bytescan(f0)
    finally:
        x.body = orig
        x._code.pop(f0, None)
    ok = (t not in cap) and (t in byt)
    return ok, 'f0=0x%x → 偽の到達先 t=0x%x: capstone 版 %s / byte 走査版 %s' % (f0, t, 'なし' if t not in cap else '拾う', '拾う' if t in byt else 'なし')


def false_target_census(x, total2):
    """L7: total2 の関数本体の E8/E9 全オフセットのうち、capstone が命令として復号した `call/jmp rel32` の先頭でないもの (= 命令境界に無い) の数と、
    そのうち rel32 の到達先が別 .pdata 関数の開始になるものの数 (hit) と、さらに total2 外の非共通関数であるもの (hit_out = 閉包を偽に広げうる到達先) の数を返す。"""
    opp = hit = hit_out = 0
    for f in total2:
        b = x.body(f)
        starts = set()
        for ins in x.md.disasm(b, x.base + f):
            if ins.size == 5 and ins.bytes[0] in (0xe8, 0xe9):
                starts.add(ins.address - x.base - f)
        for m in CI.JMPCALL.finditer(b):
            o = m.start()
            if o + 5 > len(b) or o in starts:
                continue
            opp += 1
            t = f + o + 5 + struct.unpack_from('<i', b, o + 1)[0]
            if t in x.ends and not (f <= t < x.ends[f]):
                hit += 1
                if t in x.nonfw and t not in total2:
                    hit_out += 1
    return opp, hit, hit_out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out-dir', default=os.path.join(WORK, 'sampler'))
    ap.add_argument('--indirect-json', default=os.path.join(WORK, 'sampler', 'indirect.json'))
    a = ap.parse_args()
    cnt = json.load(open(os.path.join(WORK, 'fw_hash_counts.json')))
    prev = json.load(open(a.indirect_json))
    os.makedirs(os.path.join(a.out_dir, 'lea'), exist_ok=True)
    out, bad = {}, []
    print('| プラグイン | total (#537) 関数 / B | lea root 1 巡目 関数 / B | lea root 全巡 (巡数) 関数 / B | callee 関数 / B | **total2 関数 / B** | total2 が非共通に占める割合 (関数 % / B %) | frontier 関数 | 非共通のうち total2 外 関数 / B |')
    print('|---|--:|--:|--:|--:|--:|--:|--:|--:|')
    calls = lambda f: x.edges(f)[0]
    for name, blk, _ in targets.SHELLS:
        x = CI.Pe(blk, cnt)
        clo = json.load(open(os.path.join(WORK, 'closure', 'block%05d.json' % blk)))
        entries = [int(v, 16) - x.base for v in clo['entries'].values()]
        base, _ = x.bfs(entries, calls)
        cand = sorted(x.nonfw - base)
        roots = x.dataref()(cand) if cand else set()
        total, front1 = x.bfs(list(base) + sorted(roots), calls)
        total2, rounds, front = lea_fixpoint(x, total, calls)
        if not rounds:
            front = front1
        lea_all = set().union(*rounds) if rounds else set()
        callee = total2 - total - lea_all
        p = prev[name]
        l1 = (len(base), x.size(base), len(roots), x.size(roots), len(total), x.size(total)) == (
            p['base_funcs'], p['base_bytes'], p['root_funcs'], p['root_bytes'], p['total_funcs'], p['total_bytes'])
        first = rounds[0] if rounds else set()
        l2 = (len(first), x.size(first)) == (p['lea_residual_funcs'], p['lea_residual_bytes'])
        l3miss = verify_fixpoint(x, total2)
        l3 = l3miss == 0
        l4 = total <= total2 <= x.nonfw
        over, _ = x.bfs(sorted(base | roots | lea_all), x.edges_bytescan)
        l5 = total2 <= over
        l6, l6msg = decoy_selftest(x, total2)
        opp, hit, hit_out = false_target_census(x, total2)
        l7 = hit_out == 0
        for tag, ok in (('L1 total が indirect.json と一致', l1), ('L2 lea 1 巡目が indirect.json の lea 残と一致', l2), ('L3 固定点 (漏れ %d)' % l3miss, l3),
                        ('L4 total ⊆ total2 ⊆ 非共通', l4), ('L5 total2 ⊆ byte 走査', l5), ('L6 反例注入 (%s)' % l6msg, l6),
                        ('L7 命令境界外 E8/E9 のうち閉包外の非共通関数を指す %d (関数開始を指す %d) / 機会 %d' % (hit_out, hit, opp), l7)):
            if not ok:
                bad.append('%s: %s' % (name, tag))
        open(os.path.join(a.out_dir, 'lea', 'block%05d.ranges.txt' % blk), 'w').write(','.join(x.ranges(total2)))
        open(os.path.join(a.out_dir, 'lea', 'block%05d.total.ranges.txt' % blk), 'w').write(','.join(x.ranges(total)))
        json.dump({'total': sorted(x.base + f for f in front1), 'total2': sorted(x.base + f for f in front)},
                  open(os.path.join(a.out_dir, 'lea', 'block%05d.frontier.json' % blk), 'w'))
        rest = x.nonfw - total2
        out[name] = {'block': blk, 'nonfw_funcs': len(x.nonfw), 'nonfw_bytes': x.size(x.nonfw),
                     'total_funcs': len(total), 'total_bytes': x.size(total),
                     'lea_first_funcs': len(first), 'lea_first_bytes': x.size(first), 'lea_rounds': len(rounds),
                     'lea_all_funcs': len(lea_all), 'lea_all_bytes': x.size(lea_all),
                     'callee_funcs': len(callee), 'callee_bytes': x.size(callee),
                     'total2_funcs': len(total2), 'total2_bytes': x.size(total2),
                     'frontier_funcs': len(front), 'frontier_bytes': x.size(front),
                     'unreached_funcs': len(rest), 'unreached_bytes': x.size(rest),
                     'bytescan_total2_funcs': len(over), 'bytescan_total2_bytes': x.size(over),
                     'nonboundary_e8e9': opp, 'nonboundary_e8e9_hit_funcstart': hit, 'nonboundary_e8e9_hit_outside': hit_out, 'decoy': l6msg,
                     'checks': {'L1': l1, 'L2': l2, 'L3': l3, 'L4': l4, 'L5': l5, 'L6': l6, 'L7': l7}}
        o = out[name]
        f = lambda k: '%s / %s' % (format(o[k + '_funcs'], ','), format(o[k + '_bytes'], ','))
        print('| %s | %s | %s | %s (%d) | %s | **%s** | %.1f / %.1f | %d | %s |' % (
            name, f('total'), f('lea_first'), f('lea_all'), o['lea_rounds'], f('callee'), f('total2'),
            100.0 * o['total2_funcs'] / o['nonfw_funcs'], 100.0 * o['total2_bytes'] / o['nonfw_bytes'], o['frontier_funcs'], f('unreached')))
    keys = ('nonfw', 'total', 'lea_first', 'lea_all', 'callee', 'total2', 'unreached')
    tot = {k + s: sum(v[k + s] for v in out.values()) for k in keys for s in ('_funcs', '_bytes')}
    out['_sum'] = tot
    print('| 計 | %s / %s | %s / %s | %s / %s | %s / %s | **%s / %s** | %.1f / %.1f | | %s / %s |' % (
        format(tot['total_funcs'], ','), format(tot['total_bytes'], ','), format(tot['lea_first_funcs'], ','), format(tot['lea_first_bytes'], ','),
        format(tot['lea_all_funcs'], ','), format(tot['lea_all_bytes'], ','), format(tot['callee_funcs'], ','), format(tot['callee_bytes'], ','),
        format(tot['total2_funcs'], ','), format(tot['total2_bytes'], ','), 100.0 * tot['total2_funcs'] / tot['nonfw_funcs'], 100.0 * tot['total2_bytes'] / tot['nonfw_bytes'],
        format(tot['unreached_funcs'], ','), format(tot['unreached_bytes'], ',')))
    print('\nL7 命令境界外 E8/E9 (機会 / 到達先が関数開始 / うち total2 外の非共通): ' + ' / '.join(
        '%s %s / %d / %d' % (n, format(out[n]['nonboundary_e8e9'], ','), out[n]['nonboundary_e8e9_hit_funcstart'], out[n]['nonboundary_e8e9_hit_outside']) for n, _, _ in targets.SHELLS))
    json.dump(out, open(os.path.join(a.out_dir, 'lea.json'), 'w'), indent=1)
    for b in bad:
        print('FAIL', b, file=sys.stderr)
    print('closure_lea: %s' % ('FAIL %d' % len(bad) if bad else 'PASS 7 checks x %d plugins' % len(targets.SHELLS)))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
