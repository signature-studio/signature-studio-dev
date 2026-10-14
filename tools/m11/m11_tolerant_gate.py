#!/usr/bin/env python3
"""m11_tolerant_gate.py (#2714 WIN-3): 寛容起動 (m11_tolerant.mjs) と既存経路の回帰を機械判定する.
  - 寛容起動: work/e2e_tolerant.out の M11_TOLERANT 行で, 試行 unit 数 = 期待値 (既定 942), ok + noproc + skipped = 試行, JS へ InitUnits が渡った, を見る.
  - 回帰 (strict・survey): work/e2e_full.out の M11_RESULT で units_run + units_skipped = --strict-done (通常起動の完了数),
    work/e2e_survey.out の M11_SURVEY で ok = --survey-ok. 外れたら exit 1.
  --negctl: 試行 unit を 1 つ減らした合成入力を判定し, ゲートが非 0 で止めることを確かめる (ネガコン). 止めなければ exit 1.
M11_JUDGE_WORK で work/ を変えられる (ネガコン・検証用)."""
import argparse, copy, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
W = os.environ.get('M11_JUDGE_WORK') or os.path.join(HERE, 'work')


def jline(path, tag):
    try:
        text = open(path, errors='replace').read()
    except OSError:
        return None
    m = re.search(r'^%s (\{.*\})\s*$' % tag, text, re.M)
    return json.loads(m.group(1)) if m else None


def check_tolerant(t, expect):
    errs = []
    if t is None:
        return ['M11_TOLERANT 行が無い (寛容起動が実行されていない)']
    if not t.get('hook_ran'):
        errs.append('hook_ran=false (InitUnits が寛容ループに渡らなかった)')
    if t.get('attempted') != expect:
        errs.append('attempted=%s != 期待 %d (942 unit を最後まで試行していない)' % (t.get('attempted'), expect))
    if t.get('units_total') != expect:
        errs.append('units_total=%s != 期待 %d' % (t.get('units_total'), expect))
    sk = sum((t.get('skipped_kinds') or {}).values())
    if t.get('skipped') != sk:
        errs.append('skipped=%s と種類別の和 %d が合わない' % (t.get('skipped'), sk))
    if (t.get('ok') or 0) + (t.get('noproc') or 0) + sk != (t.get('attempted') or 0):
        errs.append('ok+noproc+skipped != attempted (集計が合わない)')
    return errs


def check_regression(full, survey, strict_done, survey_ok):
    errs = []
    if full is None:
        errs.append('M11_RESULT 行が無い (通常起動が実行されていない)')
    elif strict_done is not None and (full.get('units_run') or 0) + (full.get('units_skipped') or 0) != strict_done:
        errs.append('通常起動の完了数 %s != 期待 %d (strict の挙動が変わった)' % (
            (full.get('units_run') or 0) + (full.get('units_skipped') or 0), strict_done))
    if survey is None:
        errs.append('M11_SURVEY 行が無い (survey が実行されていない)')
    elif survey_ok is not None and survey.get('ok') != survey_ok:
        errs.append('survey ok=%s != 期待 %d (survey の数値が変わった)' % (survey.get('ok'), survey_ok))
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--expect-attempted', type=int, default=942)
    ap.add_argument('--strict-done', type=int)
    ap.add_argument('--survey-ok', type=int)
    ap.add_argument('--negctl', action='store_true')
    a = ap.parse_args()
    t = jline(os.path.join(W, 'e2e_tolerant.out'), 'M11_TOLERANT')
    if a.negctl:
        if t is None:
            print('NEGCTL: 寛容起動の出力が無いためネガコンを作れない')
            return 1
        bad = copy.deepcopy(t)
        bad['attempted'] = a.expect_attempted - 1   # 退行: 1 unit 試行されずに止まった想定
        errs = check_tolerant(bad, a.expect_attempted)
        if not errs:
            print('NEGCTL_FAILED: 試行 %d の退行入力を検出できなかった (ゲートが効いていない)' % bad['attempted'])
            return 1
        print('NEGCTL_OK: 退行入力を検出 (%s)' % errs[0])
        return 0
    errs = check_tolerant(t, a.expect_attempted)
    errs += check_regression(jline(os.path.join(W, 'e2e_full.out'), 'M11_RESULT'),
                             jline(os.path.join(W, 'e2e_survey.out'), 'M11_SURVEY'), a.strict_done, a.survey_ok)
    if t is not None:
        print('M11_TOLERANT gate: attempted=%s ok=%s noproc=%s skipped=%s %s clobber=%s boot_rc=%s dllmain_done=%s' % (
            t.get('attempted'), t.get('ok'), t.get('noproc'), t.get('skipped'), json.dumps(t.get('skipped_kinds'), ensure_ascii=False),
            t.get('clobber'), t.get('boot_rc'), t.get('dllmain_done')))
    for e in errs:
        print('TOLERANT_GATE_FAILED: ' + e)
    return 1 if errs else 0


if __name__ == '__main__':
    sys.exit(main())
