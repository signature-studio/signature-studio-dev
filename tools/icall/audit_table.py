#!/usr/bin/env python3
"""audit_table.py — work/rt_*/audit_{before,after}.json から 監査表 (Markdown) を出力."""
import json, os, sys
W = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'work')
rows = [('OTT (F 282 関数)', 'rt_ott-F'), ('Fruity Balance (Delphi framework 67 関数)', 'rt_fruity-balance'), ('Fresh Air SlateCore (131 関数)', 'rt_freshair-core'),
        ('Kilohearts HeartCore (gain+infra 196 関数)', 'rt_kilohearts-gain'), ('FLEngine_x64.dll (7,421 関数)', 'rt_flengine')]
print('| 対象 | 非IAT間接call (全数) | RetDec 素通し 落ち | 復元後 落ち | tail-jmp 落ち before→after | jump table (RetDec 未解決/全数 → cmp/je 列へ展開) | gap(landing pad等) site |')
print('|---|--:|--:|--:|--:|--:|--:|')
for name, d in rows:
    try:
        b = json.load(open(os.path.join(W, d, 'audit_before.json'))); a = json.load(open(os.path.join(W, d, 'audit_after.json')))
        mp = json.load(open(os.path.join(W, d, 'map.json')))
    except Exception:
        continue
    print('| %s | %d | %d (%.1f%%) | %d (%.1f%%) | %d/%d → %d | %d/%d → %d | %d |' % (
        name, b['call_non_iat'], b['call_lost_non_iat'], 100.0 * b['call_lost_non_iat'] / max(b['call_non_iat'], 1),
        a['call_lost_non_iat'], 100.0 * a['call_lost_non_iat'] / max(a['call_non_iat'], 1),
        b['jmp_tail_lost'], b['jmp_tail_sites'], a['jmp_tail_lost'], b['jmptable_dropped'], b['jmptable_sites'], mp.get('njt', 0), b.get('gap_sites', 0)))
