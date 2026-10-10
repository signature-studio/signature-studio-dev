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
