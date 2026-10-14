# 942 unit の kind / shim_calls を unit 番号で突き合わせる独立検算 (survey_trace.mjs の集計とは別経路)。
#   python3 check_survey_vs_1255.py <new.survey.json> <old.survey.json>
import collections, json, sys
N = {u['unit']: u for u in json.load(open(sys.argv[1]))['per_unit']}
O = {u['unit']: u for u in json.load(open(sys.argv[2]))['per_unit']}
kd = [k for k in N if N[k]['kind'] != O[k]['kind']]
sd = [k for k in N if N[k].get('shim_calls') != O[k].get('shim_calls')]
print('units', len(N), len(O), 'kind diff', len(kd), 'shim_calls diff', len(sd))
print('kinds', dict(collections.Counter(u['kind'] for u in N.values())))
