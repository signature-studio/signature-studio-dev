#!/usr/bin/env python3
"""shimx_link の実測結果を集約して results/*.md|json を作る (CAB-166)。

  analyze.py            # tools/m11/work/shimx_link の run/survey/classes から results/ を生成
入力: work/shimx_link/gen557 (boot_final2 分類) / gen_fix (boot_final3 分類) / *.run.json / *.survey.json / baseline/*.survey.json
"""
import csv, json, os, re, sys, collections

HERE = os.path.dirname(os.path.abspath(__file__))
M11 = os.path.abspath(os.path.join(HERE, '..'))
W = os.path.join(M11, 'work', 'shimx_link')
SX = os.path.abspath(os.path.join(M11, '..', 'shimx'))
OUT = os.path.join(HERE, 'results')
os.makedirs(OUT, exist_ok=True)


def jl(p):
    return json.load(open(p)) if os.path.exists(p) else None


inv = {}
for r in csv.DictReader(open(os.path.join(SX, 'data', 'inventory.csv'))):
    inv.setdefault(r['api'], r)
STUB = {a for a, r in inv.items() if r['status'] == 'S'}


def status(a):
    r = inv.get(a)
    return {'F': '機能', 'S': 'スタブ', 'L': 'libc'}.get(r['status'], r['status']) if r else '-'


# ---------------- 1. 外部参照の解決状況 ----------------
def res_table(c, label):
    n = c['counts']
    sh = c['names']['shimx']
    sh_stub = [a for a in sh if a in STUB]
    lift_c = c['names']['lift_c']
    kinds = collections.Counter('simd helper (__asm_*)' if x.startswith('__asm') else 'function_* fail-fast stub (m11_fnstubs)' if x.startswith('function_') else 'm11 runtime' for x in lift_c)
    return {
        'label': label, 'ir': c['ir'], 'total_external': c['total_external'],
        'shimx': len(sh), 'shimx_functional': len(sh) - len(sh_stub), 'shimx_stub': len(sh_stub), 'shimx_stub_names': sh_stub,
        'gui': n['gui'], 'audio': n['audio'], 'gui_audio_total': n['gui'] + n['audio'], 'gui_audio_by_dll': c['gui_audio_by_dll'],
        'lift_total': n['lift_c'] + n['lift_unresolved'] + n['intrinsic'],
        'lift_provided_by_m11_c': n['lift_c'], 'lift_provided_breakdown': dict(kinds),
        'lift_unresolved': n['lift_unresolved'], 'llvm_intrinsic': n['intrinsic'], 'unknown': n['unknown'], 'unknown_names': c['names']['unknown'],
    }


c557 = jl(os.path.join(W, 'gen557', 'classes.json'))
c570 = jl(os.path.join(W, 'gen_fix', 'classes.json')) or jl(os.path.join(W, 'gen', 'classes.json'))
tabs = []
if c557: tabs.append(res_table(c557, 'boot_final2.ll (shimx REPORT の 557)'))
if c570: tabs.append(res_table(c570, '現行リンク対象 boot_final3.ll'))
json.dump(tabs, open(os.path.join(OUT, 'resolution.json'), 'w'), indent=1, ensure_ascii=False)
md = ['# 外部参照の解決状況 (gen_link.py 分類; shimx は nm 実測)', '']
md.append('| 区分 | ' + ' | '.join(t['label'] for t in tabs) + ' |')
md.append('|---|' + '---|' * len(tabs))
rows = [('外部参照 総数', 'total_external'), ('shimx 解決', 'shimx'), ('  うち機能実装', 'shimx_functional'), ('  うちスタブ (常時エラー/0 台)', 'shimx_stub'),
        ('GUI/audio 対象外 (fail-fast or 0 返却スタブを生成)', 'gui_audio_total'), ('  user32/gdi32/他 GUI', 'gui'), ('  dsound (audio)', 'audio'),
        ('lift 由来 (shimx の対象外)', 'lift_total'), ('  m11 側 C が提供 (SIMD helper / fnstub / rt)', 'lift_provided_by_m11_c'),
        ('  どこも未提供 (lift_unresolved)', 'lift_unresolved'), ('  LLVM intrinsic', 'llvm_intrinsic'), ('未分類 (shimx 署名ずれ declare 等)', 'unknown')]
for lab, k in rows:
    md.append('| %s | %s |' % (lab, ' | '.join(str(t[k]) for t in tabs)))
md += ['', 'GUI/audio の DLL 内訳: ' + '; '.join('%s: %s' % (t['label'], ', '.join('%s %d' % kv for kv in t['gui_audio_by_dll'].items())) for t in tabs), '']
md.append('shimx 解決のうちスタブ (inventory status=S): ' + (', '.join(tabs[-1]['shimx_stub_names']) if tabs else ''))
md.append('未分類: ' + ', '.join('%s=%s' % (t['label'], t['unknown_names']) for t in tabs))
open(os.path.join(OUT, 'resolution.md'), 'w').write('\n'.join(md) + '\n')

# ---------------- 2. 実行結果一覧 ----------------
runs = []
KNOWN = ['plain_failfast', 'plain_soft', 'plain_soft_fix', 'trace_failfast_fix', 'trace_soft_fix']
for f in ['m11_sx_%s.run.json' % k for k in KNOWN]:
    if os.path.exists(os.path.join(W, f)):
        d = jl(os.path.join(W, f))
        st = (d.get('stack') or '').split('\n')
        top = [re.sub(r'^\s*at wasm://wasm/\w+:', '', l).strip() for l in st[1:8]]
        runs.append({'variant': d['variant'], 'units_run': d['units_run'], 'init_count_var': d['init_count_var'], 'dllmain_done': d['dllmain_done'],
                     'threw': d['threw'], 'icall_miss': d['icall_miss'], 'va_calls': d['va_calls'], 'top_frames': top,
                     'last_stderr': [l for l in d['last_stderr'] if 'FAIL-FAST' in l or 'MessageBox' in l]})
json.dump(runs, open(os.path.join(OUT, 'runs.json'), 'w'), indent=1, ensure_ascii=False)

# ---------------- 3. トレース (trace_soft_fix) ----------------
d = jl(os.path.join(W, 'm11_sx_trace_soft_fix.run.json'))
if d and d.get('trace'):
    t = d['trace']
    ev = t['events']
    stop_unit = d['init_count_var']
    seg = collections.defaultdict(lambda: collections.Counter())
    for unit, name in ev:
        seg['done' if unit < stop_unit else 'stop'][name] += 1
    first = {c['name']: c for c in t['calls']}
    lines = ['# shimx 呼出トレース (lifted コード → shim; 計数ラッパ経由, SHIMX_TRACE=1, soft+fix ビルド)', '',
             '停止: init_count_var=%d (InitUnits が unit #%d の init 実行中に %s)' % (stop_unit, stop_unit, d['threw']), '',
             '## A. 17 unit 完走区間 (unit 0=InitUnits 前 〜 unit %d)' % (stop_unit - 1), '',
             '| shim | 区分 | 状態 | 回数 | 初回 unit | 初回 unit の init LVA |', '|---|---|---|---|---|---|']
    for c in t['calls']:
        if seg['done'][c['name']] == 0: continue
        lines.append('| %s | %s | %s | %d | %s | %s |' % (c['name'], 'GUI/audio stub' if c['gui'] else 'shimx', '-' if c['gui'] else status(c['name']),
                                                         seg['done'][c['name']], c['first_unit'] if c['first_unit'] else '0 (InitUnits 前)', c['first_unit_va'] or '-'))
    lines += ['', '合計 %d 呼出 / %d 種 (うち GUI/audio stub %d 種)' % (sum(seg['done'].values()), sum(1 for k in seg['done'] if seg['done'][k]), sum(1 for k in seg['done'] if first[k]['gui'])), '',
              '## B. unit #%d (停止 unit) の呼出と停止時点' % stop_unit, '', '| shim | 区分 | 状態 | 回数 |', '|---|---|---|---|']
    for nm, n in sorted(seg['stop'].items(), key=lambda kv: first[kv[0]]['first_seq']):
        lines.append('| %s | %s | %s | %d |' % (nm, 'GUI/audio stub' if first[nm]['gui'] else 'shimx', '-' if first[nm]['gui'] else status(nm), n))
    lines += ['', '合計 %d 呼出 / %d 種' % (sum(seg['stop'].values()), len(seg['stop'])), '', '停止直前の呼出列 (末尾 40):', '```']
    rl = []
    for e in t['tail']:
        k = 'unit=%d %s' % (e['unit'], e['name'])
        if rl and rl[-1][0] == k: rl[-1][1] += 1
        else: rl.append([k, 1])
    lines += [k + (' x%d' % n if n > 1 else '') for k, n in rl]
    lines += ['```', '', '停止スタック (wasm):', '```'] + (d.get('stack') or '').split('\n')[:10] + ['```']
    open(os.path.join(OUT, 'trace_units.md'), 'w').write('\n'.join(lines) + '\n')
    json.dump({'units_1_17': dict(seg['done']), 'unit_18': dict(seg['stop']), 'calls': t['calls'], 'new_per_unit': t['new_per_unit'], 'per_unit': t['per_unit'], 'tail': t['tail'], 'stack': d.get('stack')},
              open(os.path.join(OUT, 'trace_units.json'), 'w'), indent=1, ensure_ascii=False)
    called = {c['name'] for c in t['calls']}
else:
    called = set()

# ---------------- 4. survey ----------------
sv = jl(os.path.join(W, 'm11_sx_trace_soft_fix.survey.json'))
bs = jl(os.path.join(W, 'baseline', 'm11_boot.survey.json'))
if sv:
    s = sv['summary']
    api = s['api_units']
    called_s = set(api) | called
    lines = ['# unit 隔離 survey (942 unit を 1 本ずつ実行; soft+fix ビルド, 計数ラッパ経由)', '',
             '| 結果 | shimx リンク (soft+fix) | M11 既存ビルド (同じ手順で再測) |', '|---|---|---|']
    keys = sorted(set(s['kinds']) | set(bs['summary']['kinds'] if bs else []))
    for k in keys:
        lines.append('| %s | %d | %s |' % (k, s['kinds'].get(k, 0), bs['summary']['kinds'].get(k, 0) if bs else '-'))
    if bs:
        ka = {u['unit']: u['kind'] for u in bs['per_unit']}; kb = {u['unit']: u['kind'] for u in sv['per_unit']}
        diff = collections.Counter((ka[k], kb[k]) for k in ka if ka[k] != kb[k])
        lines += ['', '既存ビルドとの unit 別差: ' + (', '.join('%s→%s %d unit' % (a, b, n) for (a, b), n in diff.items()) or 'なし'),
                  '(注: runtime が abort した unit の後は新インスタンスで継続するため、M11 REPORT の survey 数値 ok 812/OOB 34/Halt0 48 とは unit 間状態の引継ぎが異なり一致しない)']
    lines += ['', '## SHIMX_TRACE=1 の [shimx] 出力 (survey 全体; GetProcAddress miss / LoadLibrary 失敗 / ShellExecute 等)', '']
    for l, v in s.get('shimx_trace_msgs', {}).items():
        lines.append('- `%s` x%d (最初 unit %d)' % (l, v['count'], v['first_unit']))
    lines += ['', '## fail-fast (abort) した unit', '']
    for a in s['aborts']:
        lines.append('- unit %d (init LVA %s): %s' % (a['unit'], a['lva'], a['detail']))
    lines += ['', '## survey で呼ばれた shim API (unit 数 / 呼出数 / 最初の unit / 区分 / 状態)', '', '| API | unit 数 | 呼出数 | 最初 unit | 状態 |', '|---|---|---|---|---|']
    for nm, v in api.items():
        lines.append('| %s | %d | %d | %d | %s |' % (nm, v['units'], v['calls'], v['first_unit'], status(nm) if nm in inv else 'GUI/audio'))
    open(os.path.join(OUT, 'survey.md'), 'w').write('\n'.join(lines) + '\n')

    # スタブ起動経路使用
    stub_called = sorted(a for a in called_s if a in STUB)
    ff_names = {'RtlUnwind', 'RtlUnwindEx', 'RaiseException'}
    lines = ['# shimx スタブ (inventory status=S) のうち起動経路で呼ばれたもの', '',
             '- FLEngine 静的 import に対するスタブ: %d 本 (inventory S, 全 scope 重複除く: %d)' % (len({a for a in STUB if inv[a]['scope'] == 'static' and inv[a]['dll'] and not inv[a]['status'].startswith('X')}), len(STUB)),
             '- 17 unit 通常起動 + #18 で呼ばれたスタブ: %s' % (', '.join(sorted(a for a in called if a in STUB)) or 'なし'),
             '- 942 unit survey (隔離実行) で呼ばれたスタブ: %s' % (', '.join(stub_called) or 'なし'),
             '- fail-fast 系 (RtlUnwind/RtlUnwindEx/RaiseException) の closure declare 数: %d / 到達: %s' % (len(ff_names & set(c570['names']['shimx'])), ', '.join(sorted(called_s & ff_names)) or 'なし'),
             '- shimx 解決 %d 名のうちスタブ %d 名: %s' % (len(c570['names']['shimx']), len([a for a in c570['names']['shimx'] if a in STUB]), ', '.join(a for a in c570['names']['shimx'] if a in STUB)),
             '- shimx 内部の fail-fast (shim_unimplemented) に当たったもの: ' + ('; '.join('unit %d: %s' % (a['unit'], a['detail']) for a in s['aborts']) or 'なし')]
    open(os.path.join(OUT, 'stub_usage.md'), 'w').write('\n'.join(lines) + '\n')

# ---------------- 5. 静的到達 (unit 初期化 proc を根とする直接呼出し/参照グラフ) ----------------
ir = os.path.join(M11, 'work', 'boot_final.ll')
if sv and os.path.exists(ir) and c570:
    src = open(ir, errors='replace').read()
    funcs = {}
    for m in re.finditer(r'^define [^\n]*@([\w.$-]+)\([^\n]*\{\n(.*?)^\}\n', src, re.S | re.M):
        funcs[m.group(1)] = set(re.findall(r'@([\w.$-]+)', m.group(2)))
    roots = ['entry_point'] + ['function_%x' % (int(u['lva'], 16) + 0x400000 - int(os.environ.get('M11_LB_BASE', '0'), 0)) for u in sv['per_unit'] if u['kind'] != 'noproc']
    seen, stack = set(), [r for r in roots if r in funcs]
    ext = set()
    while stack:
        f = stack.pop()
        if f in seen: continue
        seen.add(f)
        for r in funcs.get(f, ()):
            if r in funcs:
                if r not in seen: stack.append(r)
            else:
                ext.add(r)
    N = c570['names']
    reach = {k: sorted(set(N[k]) & ext) for k in ('shimx', 'gui', 'audio')}
    allsx = N['shimx']
    never = sorted(set(allsx) - set(api) - called)
    R = {'roots': len(roots), 'defined_functions': len(funcs), 'reachable_functions': len(seen),
         'reach_shimx': len(reach['shimx']), 'shimx_total': len(allsx), 'reach_gui': len(reach['gui']), 'gui_total': len(N['gui']),
         'reach_audio': len(reach['audio']), 'dynamic_shimx_called': len([a for a in set(api) | called if a in set(allsx)]),
         'dynamic_gui_called': len([a for a in set(api) | called if a in set(N['gui'] + N['audio'])]),
         'static_reach_but_never_called': sorted(set(reach['shimx']) - set(api) - called)}
    json.dump(R, open(os.path.join(OUT, 'reach.json'), 'w'), indent=1, ensure_ascii=False)
    print('[analyze] reach:', {k: v for k, v in R.items() if k != 'static_reach_but_never_called'})
print('[analyze] results ->', OUT)
