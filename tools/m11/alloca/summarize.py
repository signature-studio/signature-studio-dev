#!/usr/bin/env python3
"""CAB-129 alloca 縮退修正の検収集計: baseline (修正前) vs 修正後を実測値で比較する.

入力: results/run/, results/survey/, results/baseline/, work/alloca_report.json
出力: results/summary.json + 標準出力の比較表
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))


def rd(p):
    try:
        return open(os.path.join(HERE, p), errors='replace').read()
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


def kinds_of(survey_json_path):
    try:
        d = json.load(open(os.path.join(HERE, survey_json_path)))
        return d.get('summary', {}).get('kinds', {})
    except (OSError, ValueError):
        return {}


def main():
    F = jline(rd('results/run/e2e_full.out'), 'M11_RESULT')
    S = jline(rd('results/run/e2e_survey.out'), 'M11_SURVEY')
    FB = jline(rd('results/baseline/e2e_full.out'), 'M11_RESULT')
    SB = jline(rd('results/baseline/e2e_survey.out'), 'M11_SURVEY')
    def stage_of(txt, dflt=None):
        m = re.search(r'reached_stage: (\d)/6', txt)
        return int(m.group(1)) if m else dflt
    ST = stage_of(rd('work/judge.out'), F and F.get('boot_stage'))
    STB = stage_of(rd('results/baseline/judge.out'), FB and FB.get('boot_stage'))
    SX = jline(rd('results/run/sx_plain_soft.out'), 'SXL_RESULT')
    SXB = jline(rd('results/baseline/sx_plain_soft.run.json'), 'SXL_RESULT')
    KB = kinds_of('results/baseline/m11_sx_trace_soft_fix.survey.json')      # shimx survey (fix 付き) 修正前
    KB_main = kinds_of('results/baseline/m11_boot_surveytrace.json')         # mainline を同手順で 修正前
    KP = kinds_of('results/baseline/m11_sx_plain_soft.survey.json')          # 純リンク survey 修正前 (ab_baseline.sh)
    K_fix = kinds_of('results/survey/m11_sx_trace_soft_fix.survey.json')     # 修正後 shimx (--fix; ほぼ no-op)
    K_pure = kinds_of('results/survey/m11_sx_plain_soft.survey.json')        # 修正後 shimx 純リンク
    K_main = kinds_of('results/survey/m11_boot.survey.json')                 # 修正後 mainline 同手順
    SXB_pure = jline(rd('results/run/sx_plain_soft_BASE.out'), 'SXL_RESULT')  # 純リンク起動 修正前
    rep = {}
    try:
        rep = json.load(open(os.path.join(HERE, 'work/alloca_report.json')))
    except (OSError, ValueError):
        pass

    def trap(k):
        return sum(v for kk, v in k.items() if kk not in ('ok', 'noproc', 'closure_outside'))

    rows = [
        ('mainline stage (judge)', '-', '-'),
        ('  reached_stage (judge)', STB, ST),
        ('  units_run (通常起動)', FB and FB.get('units_run'), F and F.get('units_run')),
        ('  survey.ok (m11_survey)', SB and SB.get('ok'), S and S.get('ok')),
        ('  survey.trap', SB and SB.get('trap'), S and S.get('trap')),
        ('  survey.oob', (SB and SB.get('trap_kinds', {}).get('memory access out of bounds')),
         (S and S.get('trap_kinds', {}).get('memory access out of bounds'))),
        ('shimx survey (survey_trace 手順)', '-', '-'),
        ('  shimx--fix: ok', KB.get('ok'), K_fix.get('ok')),
        ('  shimx--fix: oob', KB.get('oob'), K_fix.get('oob')),
        ('  shimx--fix: halt0', KB.get('halt0'), K_fix.get('halt0')),
        ('  shimx--fix: trap 計', trap(KB), trap(K_fix)),
        ('  mainline: ok', KB_main.get('ok'), K_main.get('ok')),
        ('  mainline: oob', KB_main.get('oob'), K_main.get('oob')),
        ('  mainline: trap 計', trap(KB_main), trap(K_main)),
        ('shimx 純リンク起動 (run_trace, --fix 無し)', '-', '-'),
        ('  units_run', SXB and SXB.get('units_run'), SX and SX.get('units_run')),
        ('  init_count', SXB and SXB.get('init_count'), SX and SX.get('init_count')),
        ('  init_count_var', SXB and SXB.get('init_count_var'), SX and SX.get('init_count_var')),
        ('  dllmain_done (longjmp)', SXB and SXB.get('dllmain_done'), SX and SX.get('dllmain_done')),
        ('  threw', SXB and SXB.get('threw'), SX and SX.get('threw')),
        ('shimx 純リンク survey 942 (A/B)', '-', '-'),
        ('  純リンク: ok', KP.get('ok'), K_pure.get('ok')),
        ('  純リンク: oob', KP.get('oob'), K_pure.get('oob')),
        ('  純リンク: halt0', KP.get('halt0'), K_pure.get('halt0')),
        ('  純リンク: trap 計', trap(KP), trap(K_pure)),
    ]
    w0 = max(len(r[0]) for r in rows) + 2
    print('=' * 78)
    print('CAB-129 alloca 縮退修正 — 検収集計 (修正前 → 修正後, 実測)')
    print('=' * 78)
    if rep:
        print('pass: 拡幅 %d alloca / %d 関数 (追加 stack %d B), 証拠サイト %s' % (
            rep.get('widened_count', 0), rep.get('functions_patched', 0), rep.get('total_added_bytes', 0),
            json.dumps(rep.get('detector_counts', {}))))
    for r in rows:
        if r[1] == '-' and r[2] == '-':
            print('-- %s' % r[0])
        else:
            print('%-*s %s → %s' % (w0, r[0], r[1], r[2]))
    out = {'baseline': {'mainline_units_run': FB and FB.get('units_run'), 'mainline_survey': SB,
                        'sx_pure_startup': SXB_pure or SXB, 'sx_pure_kinds': KP, 'sx_fix_kinds': KB,
                        'mainline_trace_kinds': KB_main},
           'after': {'mainline_units_run': F and F.get('units_run'), 'mainline_survey': S,
                     'sx_pure': SX, 'sx_fix_kinds': K_fix, 'sx_pure_kinds': K_pure, 'mainline_trace_kinds': K_main},
           'pass': rep}
    with open(os.path.join(HERE, 'results/summary.json'), 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('results/summary.json に保存')


if __name__ == '__main__':
    main()
