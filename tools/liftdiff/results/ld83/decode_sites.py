#!/usr/bin/env python3
"""LD-83 (#2192): run の --json 出力の raw.wasm.blk を block 入口 (B) と site (J = br・C = import call) に分解する。

使い方 (REPORT_APPENDIX_LD83.md §1 の run の出力 <run.json> を渡す):
  python3 tools/liftdiff/results/ld83/decode_sites.py <run.json> [--seq N]
出力: 関数 × pattern ごとに blocks / J / C / sites (=J+C) / 計、ord 連番の検査 (ok/NG)、blk_over。
      --seq N を付けると各 case の先頭 N 要素の列 (B<VA> J<VA>.<ord>=<cond> C<VA>.<ord>, VA は 16 進) も出す。

符号化 (tools/liftdiff/ldlib/irtool.py の instrument・sites=True と一致させること):
  block 入口 = VA そのもの (bit 62 無し)
  site      = 1<<62 | kind<<56 | ord<<40 | cond<<39 (br のみ) | VA & 0xffffffff   (kind 1 = br・2 = import call)
ord は同じ block 内の site の通し番号 (block 入口で 0 に戻る)。呼び出し先の block 記録を挟んでも、site の VA で戻り先を解決して検査する
(ord_ok の docstring)。解決できない site・連番から外れた ord は NG (記録の欠落・VA の帰属誤りを示す)。
"""
import json, sys

BIT62 = 1 << 62


def vals(blk):
    return [int(x, 16) if isinstance(x, str) else int(x) for x in blk]


def decode(v):
    if not v & BIT62:
        return ('B', v, None, None)
    kind = (v >> 56) & 0x3f
    ord_ = (v >> 40) & 0xff
    va = v & 0xffffffff
    if kind == 1:
        return ('J', va, ord_, (v >> 39) & 1)
    if kind == 2:
        return ('C', va, ord_, None)
    return ('?', va, ord_, None)


def ord_ok(items):
    """site の ord が block ごとに 0,1,2… と連番かを検査する。
    呼び出し先の block 記録は呼び出し元の site の間に挟まり、戻りの印が無い。そこで site の VA (下位 32 bit) で
    戻り先を解決する: 積まれた block のうち同じ VA の最も新しいものに属し、それより上の block は呼び出し先として閉じる。
    VA が積まれていない site は NG (記録の欠落・ring の切れ目)。同じ VA の再帰呼出しは解決を誤りうる (REPORT §1)。"""
    frames = []
    by_va = {}
    for tag, va, o, _ in items:
        if tag == 'B':
            key = va & 0xffffffff
            frames.append([key, 0])
            by_va.setdefault(key, []).append(len(frames) - 1)
        elif tag in 'JC':
            lst = by_va.get(va)
            if not lst:
                return False
            idx = lst[-1]
            while len(frames) - 1 > idx:
                by_va[frames.pop()[0]].pop()
            if o != frames[idx][1]:
                return False
            frames[idx][1] += 1
    return True


def seq_str(items, n):
    out = []
    for tag, va, o, c in items[:n]:
        if tag == 'B':
            out.append('B%x' % va)
        elif tag == 'J':
            out.append('J%x.%d=%d' % (va, o, c))
        else:
            out.append('%s%x.%d' % (tag, va, o))
    return ' '.join(out)


def main():
    args = sys.argv[1:]
    seq_n = 0
    if '--seq' in args:
        i = args.index('--seq')
        seq_n = int(args[i + 1])
        del args[i:i + 2]
    with open(args[0]) as fh:
        recs = json.load(fh)
    print('fn\tpattern\toutcome\tblocks\tJ\tC\tsites\ttotal\tord\tblk_over')
    for f in recs:
        va = f['function']['va']
        for c in f['cases']:
            w = c.get('raw', {}).get('wasm', {})
            items = [decode(v) for v in vals(w.get('blk') or [])]
            nb = sum(1 for t in items if t[0] == 'B')
            nj = sum(1 for t in items if t[0] == 'J')
            nc = sum(1 for t in items if t[0] == 'C')
            print('%s\t%s\t%s\t%d\t%d\t%d\t%d\t%d\t%s\t%s' % (
                va, c['pattern'], c.get('outcome'), nb, nj, nc, nj + nc, nb + nj + nc,
                'ok' if ord_ok(items) else 'NG', w.get('blk_over', 0)))
            if seq_n:
                print('  seq: ' + seq_str(items, seq_n))


if __name__ == '__main__':
    main()
