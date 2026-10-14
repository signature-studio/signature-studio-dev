#!/usr/bin/env python3
"""MX-13 round 推移の独立検算 (規則 37 / §5)。

mx_closure.py の round ループ (入口を増やしながら callees を計算する反復) とは別の
アルゴリズムで、同じ出力 (<prefix>_sets.pkl) から閉包を再計算する:
  1. 閉包 = seeds から callees 辺を辿る BFS (到達可能な入口の集合)。
  2. BFS 深さ = 「何 hop 目で初めて入るか」。hop ごとの件数を round 推移の別表示とする。
  3. round ループの最終 entries と一致するか、round ごとの added 合計が
     閉包サイズ - seeds 数 と一致するかを確認する。
"""
import sys, json, pickle, collections


def main(sets_pkl, rounds_json):
    s = pickle.load(open(sets_pkl, 'rb'))
    callees, seeds, entries = s['callees'], set(s['seeds']), set(s['entries'])
    depth = {x: 0 for x in seeds}
    q = collections.deque(seeds)
    while q:
        f = q.popleft()
        for g in callees.get(f, ()):
            if g not in depth:
                depth[g] = depth[f] + 1
                q.append(g)
    reach = set(depth)
    hop = collections.Counter(depth.values())
    rl = json.load(open(rounds_json))['rounds_log']
    added_sum = sum(r['added'] for r in rl)
    print('seeds=%d bfs_closure=%d loop_entries=%d' % (len(seeds), len(reach), len(entries)))
    print('bfs == loop: %s' % (reach == entries))
    print('loop added 合計=%d, closure-seeds=%d, 一致=%s' % (added_sum, len(reach) - len(seeds),
                                                      added_sum == len(reach) - len(seeds)))
    print('hop 別 (初到達の深さ): ' + ' '.join('%d:%d' % (k, hop[k]) for k in sorted(hop)))
    print('最終 round entries == %d, rounds=%d' % (rl[-1]['entries'], len(rl)))
    ok = reach == entries and added_sum == len(reach) - len(seeds) and rl[-1]['entries'] == len(entries)
    print('RESULT=%s' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1], sys.argv[2]))
