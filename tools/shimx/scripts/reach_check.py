#!/usr/bin/env python3
"""R8 進捗チェッカー: M11 の「静的到達するが動的呼出が無い shimx API」(未実機検証 133 名) のうち、
純リンク実行トレースで新たに呼ばれた名を算出する。

  python3 scripts/reach_check.py --run <m11_sx_*.run.json> [--reach <reach.json>] [--out <md>]

入力:
  --run   : tools/m11/shimx_link/run_trace.mjs の出力 (run.json; trace.calls に shim 名・回数)
  --reach : tools/m11/shimx_link/results/reach.json (静的到達解析。既定はリポジトリ内の物を使用)
出力:
  stdout に集計 (units 完走数 / shimx 呼出種数 / 133 名の消化状況)。--out があれば markdown も保存。
"""
import argparse, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, '..', '..'))
DEFAULT_REACH = os.path.join(REPO, 'm11', 'shimx_link', 'results', 'reach.json')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', required=True)
    ap.add_argument('--reach', default=DEFAULT_REACH)
    ap.add_argument('--out')
    a = ap.parse_args()
    run = json.load(open(a.run))
    reach = json.load(open(a.reach))
    never = reach.get('static_reach_but_never_called', [])
    calls = (run.get('trace') or {}).get('calls') or []
    sx = {c['name']: c['count'] for c in calls if not c.get('gui')}
    units_run = run.get('units_run')
    units_total = run.get('units_total')
    boot_ok = units_run is not None and units_total is not None and units_run >= 17
    newly = sorted(n for n in never if n in sx)
    remaining = sorted(n for n in never if n not in sx)
    lines = []
    lines.append('# R8 未検証 shimx API の実機検証進捗 (reach_check)')
    lines.append('')
    lines.append('- 入力: %s / %s' % (os.path.relpath(a.run, REPO), os.path.relpath(a.reach, REPO)))
    lines.append('- units: %s/%s 完走 (17 unit 完走 = %s)' % (units_run, units_total, 'YES' if boot_ok else 'NO'))
    lines.append('- トレース内 shimx 呼出: %d 種 (計 %d 回)' % (len(sx), sum(sx.values())))
    lines.append('- 未実機検証 %d 名のうち **本実行で呼出 %d 名 / 残 %d 名**' % (len(never), len(newly), len(remaining)))
    lines.append('')
    if newly:
        lines.append('## 本実行で検証できた名 (%d)' % len(newly))
        lines.append('')
        lines.append(' | 名前 | 呼出回数 |')
        lines.append(' |---|---|')
        for n in newly:
            lines.append(' | %s | %d |' % (n, sx[n]))
        lines.append('')
    if remaining:
        lines.append('## 未達 (呼出無し, %d 名)' % len(remaining))
        lines.append('')
        for i in range(0, len(remaining), 6):
            lines.append('- ' + ' '.join(remaining[i:i + 6]))
    text = '\n'.join(lines) + '\n'
    print('\n'.join(lines[2:6]))
    if a.out:
        os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
        open(a.out, 'w').write(text)
        print('  -> %s' % a.out)


if __name__ == '__main__':
    main()
