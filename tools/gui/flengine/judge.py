#!/usr/bin/env python3
"""GUI-3 (#174) 判定: 実測 JSON を baseline (GUI shim 無しの m11 同一 IR) と突き合わせ、gate ごとに PASS/FAIL。
FAIL が 1 つでもあれば exit 1 (e2e.sh はこの終了コードをそのまま返す)。
  judge.py --dir DIR [--expect-units N] [--boot BOOT.json] ...   (既定のファイル名は e2e.sh が DIR に置く)
ネガティブコントロールは e2e.sh が「壊した入力」でこの judge を呼び、**exit 1 になること**を要求する。"""
import argparse, json, os, re, sys

ap = argparse.ArgumentParser()
ap.add_argument('--dir', required=True)
ap.add_argument('--boot', default='boot_ff.json')
ap.add_argument('--survey-ff', default='survey_ff.json')
ap.add_argument('--survey-soft', default='survey_soft.json')
ap.add_argument('--survey-soft-chain', default='survey_soft_chain.json')
ap.add_argument('--probe', default='probe.json')
ap.add_argument('--wndscan', default='wndclass.json', help='m11_wndclass_scan.py --json-out の出力 (e2e.sh が DIR に置く)')
ap.add_argument('--expected', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results', 'reach_expected.json'))
ap.add_argument('--expect-units', type=int, default=None, help='baseline の units_run を上書き (ネガコン用)')
ap.add_argument('--quiet', action='store_true')
a = ap.parse_args()
D = a.dir
J = lambda f: json.load(open(f if os.path.isabs(f) else os.path.join(D, f)))
T = lambda f: open(os.path.join(D, f)).read()

base_boot, base_sv = J('baseline_boot.json'), J('baseline_survey.json')
boot, svf, svs, probe = J(a.boot), J(a.survey_ff), J(a.survey_soft), J(a.probe)
chain = J(a.survey_soft_chain)
expected = set(json.load(open(a.expected))['names'])
res = []
def gate(name, ok, detail):
    res.append((name, bool(ok), detail))

for v in ('ff', 'soft'):
    line = [l for l in T('build_%s.log' % v).splitlines() if '[gf] OK:' in l]
    m = re.search(r'signature mismatch: (\d+), undefined symbol: (\d+), duplicate symbol: (\d+)', line[-1] if line else '')
    gate('L1 link[%s]' % v, m and m.groups() == ('0', '0', '0'), 'sigmismatch/undefined/duplicate = %s' % (m.groups() if m else 'build failed',))
ad = re.search(r'declares\(GUI\)=(\d+) adapters=(\d+) \(impl (\d+) / stub (\d+)\) c=(\d+) d=(\d+)', T('build_ff.log'))
gate('A1 adapters', ad and ad.group(1) == ad.group(2) and ad.group(5) == '0' and ad.group(6) == '0',
     'declare=%s adapter=%s impl=%s stub=%s (c=%s d=%s)' % ad.groups() if ad else 'no adapter line')

bu = a.expect_units if a.expect_units is not None else base_boot['units_run']
gate('B1 boot parity', boot['units_run'] == bu and boot['dllmain_done'] == base_boot['dllmain_done'] and boot['init_count'] == base_boot['init_count']
     and boot['probes'].get('GetMem') == base_boot['probes'].get('GetMem') and boot['probes'].get('FreeMem') == base_boot['probes'].get('FreeMem')
     and boot['icall_miss'] == base_boot['icall_miss'] and boot['boot_failfast'] is None and boot['boot_threw'] == base_boot.get('threw'),
     'units_run %s (base %s) / dllmain_done %s / GetMem %s FreeMem %s / icall_miss %s / threw %s (base %s)' % (boot['units_run'], bu, boot['dllmain_done'], boot['probes'].get('GetMem'), boot['probes'].get('FreeMem'), boot['icall_miss'], boot['boot_threw'], base_boot.get('threw')))
first = boot['reach'][0] if boot['reach'] else None
gate('R1 first GUI API reaches shim (boot)', first and first['kind'] == 'IMPL' and first['calls'] > 0,
     'first=%s calls=%s kind=%s; reached=%d' % (first and first['name'], first and first['calls'], first and first['kind'], len(boot['reach'])))
names_soft = {r['name'] for r in chain['reach']}   # 到達は前 unit の状態を引き継ぐ chain 実行で見る (隔離版は到達が減る)
gate('R2 survey reach floor', expected <= names_soft, 'reached %d (expected floor %d); missing=%s' % (len(names_soft), len(expected), sorted(expected - names_soft)))
sv, bs = svs['survey'], base_sv
gate('S1 survey parity (soft)', all(sv.get(k, 0) == bs.get(k, 0) for k in ('ok', 'noproc', 'miss', 'trap', 'clobber')),
     'ok/noproc/miss/trap/clobber = %s/%s/%s/%s/%s (base %s/%s/%s/%s/%s)' % (sv['ok'], sv['noproc'], sv['miss'], sv['trap'], sv.get('clobber', 0), bs['ok'], bs['noproc'], bs['miss'], bs['trap'], bs.get('clobber', 0)))
ffu = set(svf['survey']['failfast_units'])
stub_soft = set(svs['softstub_apis'])
sfu = set(svs['survey']['failfast_units'])
gate('S2 soft adds no fail-fast beyond ff (ff fail-fast APIs stay STUB or fail-fast in soft)', sfu <= ffu and ffu <= (stub_soft | sfu),
     'ff fail-fast APIs=%s (units %s); soft fail-fast=%s; soft STUB APIs=%s' % (sorted(ffu), svf['survey']['kinds'].get('gui_failfast', 0), sorted(sfu), sorted(stub_soft)))
cl = probe['classes']
pr = {r['name']: r['calls'] for r in probe['reach']}
gate('P1 RegisterClassW/CreateWindowExW reach shim (directed)', len(cl) >= 2 and all(c['atom'] not in (None, 0) for c in cl) and pr.get('RegisterClassW', 0) >= 2 and pr.get('CreateWindowExW', 0) >= 2,
     'atoms=%s RegisterClassW=%s CreateWindowExW=%s' % ([c['atom'] for c in cl], pr.get('RegisterClassW'), pr.get('CreateWindowExW')))
gate('P2 ABI (GLOBAL_BASE / 31bit handle)', probe['abi']['gui_shared_ptr_ge_0x10000'] and probe['abi']['screen_dc_in_31bit'],
     'gui_shared_ptr=%s screen_dc=%s' % (probe['abi']['gui_shared_ptr'], probe['abi']['screen_dc']))
gate('P3 WNDPROC 4-arg via m11_icall hook', all(w['wndproc_icall_calls'] > 0 for w in probe['windows']),
     'hook calls per CreateWindowExW=%s' % [w['wndproc_icall_calls'] for w in probe['windows']])

tapp = [w for w in probe['windows'] if w['name'] == 'TApplication']
h = int(tapp[0]['hwnd'], 16) if tapp and tapp[0]['hwnd'] else 0
gate('P4 TApplication window (WNDPROC = DefWindowProcW import thunk) created', h > 0 and h < 0x80000000 and tapp[0]['wndproc_icall_calls'] > 0,
     'hwnd=%s icall=%s' % (tapp[0]['hwnd'] if tapp else None, tapp[0]['wndproc_icall_calls'] if tapp else None))
ws = J(a.wndscan)['summary']
gate('W1 WNDCLASS scan: every fn WNDPROC is defined in the final IR', ws['wndclass_instances'] >= 11 and ws['wndproc_fn_instances'] >= 8 and ws['wndproc_outside_final_ir'] == 0,
     'WNDCLASS %d (fn WNDPROC %d, import thunk %d) / outside final IR %d / outside base closure %d (floor: 11 / 8)' % (ws['wndclass_instances'], ws['wndproc_fn_instances'], ws['wndproc_import_thunk_instances'], ws['wndproc_outside_final_ir'], ws['wndproc_outside_closure']))
tl = [w for w in probe['windows'] if w['name'] == 'TLightweightLayeredControl']
hl = int(tl[0]['hwnd'], 16) if tl and tl[0]['hwnd'] else 0
gate('P5 TLightweightLayeredControl (WNDPROC 0x31dd10, formerly outside closure) window created', 0 < hl < 0x80000000 and tl[0]['m11_icall_ok_delta'] > 0,
     'hwnd=%s m11_icall ok=%s miss=%s' % (tl[0]['hwnd'] if tl else None, tl[0]['m11_icall_ok_delta'] if tl else None, tl[0]['m11_icall_miss_delta'] if tl else None))
ok_all = all(r[1] for r in res)
if not a.quiet:
    for n, ok, d in res: print('%-52s %s  %s' % (n, 'PASS' if ok else 'FAIL', d))
    nat = [r['name'] for r in boot['reach'] + svs['reach'] if r['name'].startswith(('RegisterClass', 'CreateWindowEx'))]
    print('INFO natural (boot+survey) RegisterClass*/CreateWindowEx* reach: %s' % (sorted(set(nat)) or 'NOT REACHED (acceptance criterion 1 unmet by natural flow; see REPORT)'))
    for w in probe['windows']:
        if not w['hwnd'] or w['hwnd'] == '0x0':
            print('OPEN directed CreateWindowExW(%s) returned NULL: WNDPROC 4-arg call reached m11_icall x%d, miss +%d' % (w['name'], w['wndproc_icall_calls'], w['m11_icall_miss_delta']))
    print('INFO m11_icall miss targets after probe: %s (0x6c6f = WNDPROC swapped in by WM_NCCREATE (SetWindowLongPtr), not yet attributed; see REPORT)' % probe.get('icall_miss_targets'))
    uw = probe.get('util_window') or {}
    if uw.get('ret') in (None, '0x0'):
        print('OPEN directed function_52a7f0 (AllocateHWnd) returned NULL: RegisterClassW skipped by a lift defect (cmp [TempClass.lpfnWndProc] folded to constant 0)')
    print('JUDGE %s (%d/%d gates)' % ('PASS' if ok_all else 'FAIL', sum(1 for r in res if r[1]), len(res)))
sys.exit(0 if ok_all else 1)
