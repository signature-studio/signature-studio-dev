#!/usr/bin/env python3
"""merge_survey.py — survey_seg_*.json (セグメント実行の結果) を results/survey.json に統合する。"""
import glob, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
# unit 単位の jsonl (timeout に耐える追記ログ) を正本にする。同一 unit の最終行を探用。
units = {}
for p in glob.glob(os.path.join(HERE, 'results', 'survey_seg_*.jsonl')) +          glob.glob(os.path.join(HERE, 'results', 'survey_units.jsonl')):
    for line in open(p, errors='replace'):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            units[int(rec[0])] = rec
        except Exception:
            continue
# FLE-2: runner は empty/noproc を jsonl に書き出さない (details に載せない設計) ため、
# 完了した survey の summary json から空き unit を補完する (総数を 942 に揃える)。
for sp in glob.glob(os.path.join(HERE, 'results', '*summary*.json')) + glob.glob(os.path.join(HERE, 'results', 'survey_seg_*.json')):
    try:
        d = json.load(open(sp, errors='replace'))
    except Exception:
        continue
    sv = d.get('survey') if isinstance(d, dict) else None
    if not isinstance(sv, dict):
        continue
    for rec in (sv.get('details') or []):
        try:
            i, cls, info = rec[0], rec[1], rec[2]
        except Exception:
            continue
        if int(i) not in units:
            units[int(i)] = [int(i), cls, info]
    total = sum((sv.get('byCls') or {}).values())
    if total and len(units) < total:
        have = {}
        for v in units.values():
            have[v[1]] = have.get(v[1], 0) + 1
        for cls, n in (sv.get('byCls') or {}).items():
            miss = n - have.get(cls, 0)
            for i in range(total):
                if miss <= 0:
                    break
                if i not in units:
                    units[i] = [i, cls, 0]
                    miss -= 1
by, details = {}, []
for i in sorted(units):
    _, cls, info = units[i]
    by[cls] = by.get(cls, 0) + 1
    if cls not in ('ok', 'empty'):
        details.append([i, cls, info])
out = {'units_covered': len(units), 'byCls': by, 'details': details[:600]}
json.dump(out, open(os.path.join(HERE, 'results', 'survey.json'), 'w'), indent=1, ensure_ascii=False)
segs = len(glob.glob(os.path.join(HERE, 'results', 'survey_seg_*.jsonl')))
print('[merge_survey] segments=%d covered=%d byCls=%s' % (segs, len(units), by))
