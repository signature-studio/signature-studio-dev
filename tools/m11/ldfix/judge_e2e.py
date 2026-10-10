#!/usr/bin/env python3
"""judge_e2e.py — ldfix_e2e.sh の stage4/survey 結果を機械判定する。
base (修復前 IR) と fix (修復後 IR) の stage4 到達・probe 数・survey 件数を比較し、
fix が base に逆行していないこと (stage4 到達同一、probe 減無し、survey ok 減無し) を検証する。"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.join(HERE, 'work', 'stage4')


def read(p):
    try:
        return open(p, errors='replace').read()
    except OSError:
        return ''


def jline(text, tag):
    m = re.search(r'^%s (\{.*\})\s*$' % tag, text, re.M)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


def load(name):
    d = {}
    txt = read(os.path.join(W, name, 'e2e_full.out'))
    d['full'] = jline(txt, 'M11_RESULT') or {}
    txt = read(os.path.join(W, name, 'e2e_survey.out'))
    d['survey'] = jline(txt, 'M11_SURVEY') or {}
    return d


def stage_of(F):
    st = 0
    if F.get('image_bytes'):
        st = 1
    if (F.get('icall_ok') or 0) >= 1:
        st = 2
    if (F.get('units_total') or 0) >= 1:
        st = 3
    pr = F.get('probes') or {}
    if (F.get('va_calls') or 0) >= 1 and (pr.get('GetMem') or 0) >= 1:
        st = 4
    return st


base = load('base')
fix = load('fix')
sb, sf = stage_of(base['full']), stage_of(fix['full'])
prb, prf = base['full'].get('probes') or {}, fix['full'].get('probes') or {}
ok = True
lines = []
lines.append('stage4 到達: base=%d/6 fix=%d/6 %s' % (sb, sf, 'OK' if sf >= sb else 'REGRESS'))
ok &= sf >= sb
for k in ('GetMem', 'FreeMem', 'FastMM_GetMem(407a50)'):
    lines.append('probe %-22s base=%-5s fix=%-5s %s' % (k, prb.get(k), prf.get(k),
                 'OK' if (prf.get(k) or 0) >= (prb.get(k) or 0) else 'REGRESS'))
    ok &= (prf.get(k) or 0) >= (prb.get(k) or 0)
for k in ('units_run', 'units_total', 'init_count', 'icall_ok'):
    vb, vf = base['full'].get(k), fix['full'].get(k)
    lines.append('%-12s base=%-5s fix=%-5s %s' % (k, vb, vf, 'OK' if (vf or 0) >= (vb or 0) else 'REGRESS'))
    ok &= (vf or 0) >= (vb or 0)
sob, sof = base['survey'].get('ok'), fix['survey'].get('ok')
trb, trf = base['survey'].get('trap'), fix['survey'].get('trap')
lines.append('survey ok: base=%s fix=%s %s (trap %s -> %s)' % (sob, sof, 'OK' if (sof or 0) >= (sob or 0) else 'REGRESS', trb, trf))
ok &= (sof or 0) >= (sob or 0)
print('\n'.join(lines))
print('STAGE4_JUDGE ' + json.dumps({'pass': bool(ok), 'stage_base': sb, 'stage_fix': sf,
                                    'getmem_base': prb.get('GetMem'), 'getmem_fix': prf.get('GetMem'),
                                    'survey_ok_base': sob, 'survey_ok_fix': sof}, ensure_ascii=False))
sys.exit(0 if ok else 1)
