#!/usr/bin/env python3
"""gen_mixed.py — FLE-3: verdict_boot.jsonl を liftdiff の関数級 verdict と混在させて採点する。

tools/liftdiff の `summary` は「FORMAT v1 JSONL を 1 ファイル」入力で、
`function.va` が同じ PE VA 空間 (恒等写像) なら target が違っても集計できる。
本スクリプトは
  (a) tools/liftdiff/work/flelift/batch_closure.jsonl  (関数級 7,421 行、target=flelift)
  (b) tools/flelift/boot/results/verdict_boot.jsonl    (unit 級 943 行、target=flelift-boot)
を結合して `work/boot/verdict_mixed.jsonl` (gitignore) を書き、さらに
`tools/liftdiff/liftdiff.py summary` を呼んで results/mixed_summary.md に採点結果を残す。

使い方:
  python3 tools/flelift/boot/gen_mixed.py [--fn-jsonl PATH] [--boot-jsonl PATH] [--no-summary]

boot 行は unit 初期化の順次/隔離実行結果であり「関数の bit 一致」とは意味が違うため、
`tags` に `x-route_diff` (survey 単位の差分) / `x-boot_chain` (連鎖全体) を付けている。
`first_tag` の `x-route_diff 149` は「native baseline が fault / x64c が ok」=
x64c 優位の unit 数 (native_fault) として読む。
"""
import argparse, json, os, subprocess, sys, collections

HERE = os.path.dirname(os.path.abspath(__file__))
FLE = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(FLE))          # tools/ の親 = リポジトリルート
DEF_FN = os.path.join(REPO, 'tools', 'liftdiff', 'work', 'flelift', 'batch_closure.jsonl')
DEF_BOOT = os.path.join(HERE, 'results', 'verdict_boot.jsonl')
# 巨大な混在 JSONL (約 32MB) は results/ に入れず work/boot/ に書く (20MB 超 blob 禁止)。
# --md の採 intellect結果 (数 KB) は results/ に残す。
OUT = os.path.join(FLE, 'work', 'boot', 'verdict_mixed.jsonl')
MD = os.path.join(HERE, 'results', 'mixed_summary.md')


def load(p):
    recs = []
    for line in open(p, errors='replace'):
        line = line.strip()
        if not line:
            continue
        try:
            recs.append(json.loads(line))
        except Exception:
            pass
    return recs


def build_report(recs):
    """target 別内訳つきの liftdiff レポートを Markdown で返す。

    unit 級 (target=flelift-boot) の差分は x-route_diff タグ、native 側が fault のものは
    native_fault outcome として数える。関数級 (target=flelift) と分離して集計しないと
    unit 級の寄与が関数級に埋もれるため、target 別に出す。
    """
    L = []
    by_target = collections.defaultdict(list)
    for r in recs:
        by_target[r.get('target', '?')].append(r)
    L.append('## verdict 混在採算 (boot unit 級 + liftdiff 関数級)')
    L.append('')
    L.append('| target | 行数 | match | mismatch | unexec |')
    L.append('|---|---:|---:|---:|---:|')
    for t in sorted(by_target):
        c = collections.Counter(r['verdict'] for r in by_target[t])
        L.append('| %s | %d | %d | %d | %d |' % (t, len(by_target[t]), c['match'], c['mismatch'], c['unexec']))
    c = collections.Counter(r['verdict'] for r in recs)
    L.append('| **合計** | **%d** | **%d** | **%d** | **%d** |' % (
        len(recs), c['match'], c['mismatch'], c['unexec']))
    L.append('')
    unit_recs = by_target.get('flelift-boot', [])
    xdiff = [r for r in unit_recs if any(t['tag'] == 'x-route_diff' for t in r.get('tags', []))]
    xchain = [r for r in unit_recs if any(t['tag'] == 'x-boot_chain' for t in r.get('tags', []))]
    nf = sum(1 for r in xdiff
             for cc in r.get('cases', []) if cc.get('outcome') == 'native_fault')
    match_n = len(unit_recs) - len(xdiff) - len(xchain)
    L.append('### unit 級 (target=flelift-boot) の寄与')
    L.append('')
    L.append('| 分類 | unit 数 | 説明 |')
    L.append('|---|---:|---|')
    L.append('| match (x64c = RetDec baseline) | %d | 両 route で同じ結果 |' % match_n)
    L.append('| **x-route_diff** | %d | survey unit 単位の差分。うち **native_fault (native 側 fault / x64c ok = x64c 優位) = %d** |' % (len(xdiff), nf))
    L.append('| x-boot_chain | %d | boot 連鎖全体 (sequential init) の比較行 |' % len(xchain))
    L.append('')
    fn_recs = by_target.get('flelift', [])
    tags = collections.Counter()
    for r in fn_recs:
        if r['verdict'] != 'mismatch':
            continue
        for t in r.get('tags', []):
            tags[t['tag']] += 1
    L.append('### 関数級 (target=flelift) の mismatch タグ上位')
    L.append('')
    for tag, n in tags.most_common(10):
        L.append('- %s: %d' % (tag, n))
    L.append('')
    L.append('`liftdiff.py summary` は両 target を同じ PE VA 空間 (恒等写像) で集計するため、')
    L.append('unit 級 row と関数級 row を 1 ファイルに混在させても `function.va` で衝突しない。')
    L.append('')
    return '\n'.join(L) + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fn-jsonl', default=DEF_FN)
    ap.add_argument('--boot-jsonl', default=DEF_BOOT)
    ap.add_argument('--out', default=OUT)
    ap.add_argument('--md', default=MD)
    ap.add_argument('--no-summary', action='store_true')
    a = ap.parse_args()

    fn_recs = load(a.fn_jsonl) if os.path.exists(a.fn_jsonl) else []
    boot_recs = load(a.boot_jsonl) if os.path.exists(a.boot_jsonl) else []
    if not boot_recs:
        print('[gen_mixed] %s が無い (boot/survey 未実行?)' % a.boot_jsonl, file=sys.stderr)
        return 1

    # boot 行は unit 初期化の意味を持つので、tags に route 差分タグを補う
    # (既に x-route_diff / x-boot_chain が付いている場合はそのまま)。
    by_target = collections.Counter()
    for r in boot_recs:
        by_target[r.get('target', '?')] += 1

    merged = fn_recs + boot_recs
    with open(a.out, 'w') as f:
        for r in merged:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print('[gen_mixed] 関数級 %d (target=%s) + unit 級 %d (target=%s) -> %d 行: %s' % (
        len(fn_recs), sorted({r.get("target") for r in fn_recs}), len(boot_recs),
        sorted(by_target), len(merged), a.out))

    # target 別内訳レポートを results/ に書く (liftdiff summary の通常レポートに統合)
    md_text = build_report(merged)
    open(a.md, 'w').write(md_text)
    print('[gen_mixed] report: %s' % a.md)
    if a.no_summary:
        return 0
    # liftdiff.py summary を呼ぶ (読み取り専用ツールの実行)
    ld = os.path.join(REPO, 'tools', 'liftdiff', 'liftdiff.py')
    if not os.path.exists(ld):
        print('[gen_mixed] %s が無い — summary はスキップ' % ld, file=sys.stderr)
        return 0
    raw_md = a.md + '.raw'
    r = subprocess.run([sys.executable, ld, 'summary', a.out, '--md', raw_md],
                       capture_output=True, text=True)
    print(r.stdout.rstrip() or r.stderr.rstrip()[-800:])
    # 生の summary と target 別レポートを連結して 1 ファイルにする
    raw = open(raw_md).read() if os.path.exists(raw_md) else ''
    try:
        os.remove(raw_md)
    except OSError:
        pass
    open(a.md, 'w').write(raw + '\n' + md_text)
    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
