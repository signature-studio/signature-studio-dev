#!/usr/bin/env python3
"""OTT 旧 RetDec chain の既知欠陥 D1〜D6 を liftdiff のバッチ結果から機械的に突合する (work/ott_old/batch.jsonl)。"""
import json, os, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
recs = [json.loads(l) for l in open(os.path.join(ROOT, 'work/ott_old/batch.jsonl'))]
byfn = {r['function']['name'][len('function_'):]: r for r in recs}
tags = collections.defaultdict(list)
for r in recs:
    for t in r.get('tags', []):
        tags[t['tag']].append(r['function']['name'][len('function_'):])
cnt = collections.Counter(r['verdict'] for r in recs)
d = {
    'D1_indirect_call_drop': {'tags': ['icall_drop'], 'functions': tags['icall_drop']},
    'D2_short_global': {'tags': ['short_global'], 'functions': tags['short_global']},
    'D3_callsite_arg_drop': {'tags': ['callsite_arg_drop', 'arg_drop'], 'functions': sorted(set(tags['callsite_arg_drop'] + tags['arg_drop']))},
    'D4_D5_c_defined_ports': {'note': 'C 定義 (libm 置換 CRT 数学 / hand port) vs native 実機械語', 'functions': [n for n, r in byfn.items() if (r['function']['sig'] or {}).get('c') and r['verdict'] == 'mismatch']},
    'D6_body_layer': {'tags': ['xmm_arg_drop', 'zero_init_drop', 'fp_flag_unreflected', 'spill_slot_deref'],
                      'functions': sorted(set(tags['xmm_arg_drop'] + tags['zero_init_drop'] + tags['fp_flag_unreflected'] + tags['spill_slot_deref']))},
}
for k, v in d.items():
    v['count'] = len(v['functions'])
summary = {'functions': len(recs), 'match': cnt['match'], 'mismatch': cnt['mismatch'], 'unexec': cnt['unexec'], 'defects': {k: v['count'] for k, v in d.items()},
           'ctor_18011d400': {'verdict': byfn.get('18011d400', {}).get('verdict'), 'tags': [t['tag'] for t in byfn.get('18011d400', {}).get('tags', [])]}}
print('OTT_SUMMARY ' + json.dumps(summary))
json.dump(d, open(os.path.join(ROOT, 'work/ott_old/defects.json'), 'w'), indent=1)
ok = d['D1_indirect_call_drop']['count'] > 0 and d['D2_short_global']['count'] > 0 and d['D3_callsite_arg_drop']['count'] > 0 and d['D6_body_layer']['count'] > 0
sys.exit(0 if ok else 1)
