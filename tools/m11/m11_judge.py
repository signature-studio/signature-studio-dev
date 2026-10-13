#!/usr/bin/env python3
"""m11_judge.py: m11_e2e.sh の実測出力 (work/e2e_full.out, work/e2e_survey.out) を機械判定して要約を印字する.
既定は報告のみで exit 0 (未達でも現在の到達点を再現して数値を出す).
`--require-stage N` を付けた時だけ, 到達 stage < N なら exit 1 (機械判定ゲート; e2e からは呼ばない).
stage 6 は「全 942 unit が Halt0 を経由せず完走し, DllMain が TRUE (=1) を正常 return」の時だけ (#134).
Halt0 → longjmp 経由の巻き戻し (早期終了) は stage 6 にしない."""
import json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
W = os.environ.get('M11_JUDGE_WORK') or os.path.join(HERE, 'work')
REQUIRE = None
if '--require-stage' in sys.argv:
    try:
        REQUIRE = int(sys.argv[sys.argv.index('--require-stage') + 1])
    except (IndexError, ValueError):
        REQUIRE = None
    if REQUIRE not in range(1, 7):
        sys.stderr.write('usage: m11_judge.py [--require-stage N]  (N は 1〜6 の整数)\n')
        sys.exit(2)


def read(p):
    try:
        return open(p, errors='replace').read()
    except OSError:
        return ''


def names():
    wasm = os.path.join(W, 'm11_boot.cjs.wasm')
    n = {}
    try:
        ex = subprocess.run(['wasm-objdump', '-x', '-j', 'Export', wasm], capture_output=True, text=True).stdout
        for m in re.finditer(r'- func\[(\d+)\] <([^>]*)>', ex):
            n[int(m.group(1))] = m.group(2)
    except OSError:
        sys.path.insert(0, HERE)  # wabt 無し: m11_wasmnames (export/name section) で代用
        try:
            from m11_wasmnames import func_names
            n = func_names(wasm)
        except Exception:
            pass
    return n


def jline(text, tag):
    m = re.search(r'^%s (\{.*\})\s*$' % tag, text, re.M)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


full_txt = read(os.path.join(W, 'e2e_full.out'))
sv_txt = read(os.path.join(W, 'e2e_survey.out'))
F = jline(full_txt, 'M11_RESULT')
S = jline(sv_txt, 'M11_SURVEY')
N = names()
try:
    COND = json.loads(read(os.path.join(W, 'ir_conditions.json')) or '{}')
except ValueError:
    COND = {}

STAGES = [
    (1, 'PE image (.text/.data/.rdata, LVA) を linear memory に敷設'),
    (2, 'entry_point(DllMain) → _StartLib → _InitLib 到達 (TLS hook を間接 call 表経由で実行)'),
    (3, 'System.InitUnits 開始 (InitTable 942 unit を読出し)'),
    (4, 'FastMM4 実行: GetMem が VirtualAlloc でプールを確保'),
    (5, '全 942 unit 初期化が trap 無しで完走 (survey: 隔離実行)'),
    (6, 'DllMain attach が Halt0 無しで全 unit 完走し TRUE を正常 return (longjmp 早期終了は含めない)'),
]
reached = 0
if F:
    if F.get('image_bytes'):
        reached = 1
    if (F.get('icall_ok') or 0) >= 1:
        reached = 2
    if (F.get('units_total') or 0) >= 1 or (S and S.get('units')):
        reached = 3
    pr = F.get('probes') or {}
    if (F.get('va_calls') or 0) >= 1 and (pr.get('GetMem') or 0) >= 1:
        reached = max(reached, 4) if reached >= 3 else reached
    if S and S.get('ok') == 942 - (S.get('noproc') or 0) and not S.get('trap') and not S.get('miss') and not S.get('clobber'):
        reached = 5
    # #134: stage 6 = 全 unit が Halt0 を経ずに完走し, DllMain が TRUE (=1) を正常 return した時だけ.
    # Halt0 → longjmp (RestoreContext) の巻き戻しは早期終了であり, DllMain 完走ではない.
    halt0 = (F.get('longjmp_hit') or 0) > 0 or ((F.get('probes') or {}).get('Halt0') or 0) > 0
    complete6 = (not halt0 and not F.get('dllmain_done') and not F.get('threw')
                 and (F.get('units_total') or 0) > 0 and F.get('units_run') == F.get('units_total')
                 and not F.get('units_skipped') and str(F.get('boot_rc')) == '1')
    if complete6 and reached >= 5:
        reached = 6

print('=' * 72)
print('M11 e2e: FLEngine_x64.dll 部分起動 PoC (audio/GUI なし; RetDec lift → emcc → wasm → node)')
print('=' * 72)
print('IR 生成条件 (work/ir_conditions.json): ldfix=%s qstore=%s pe=%s' % (COND.get('ldfix', '-'), COND.get('qstore', '-'), COND.get('pe', '-')))
if not F:
    print('reached_stage: 0 (実行出力なし: m11_boot.cjs が未生成か node 起動失敗)')
    print('stop_reason: e2e_full.out に M11_RESULT 無し')
    print(full_txt[-800:])
    sys.exit(1 if REQUIRE is not None else 0)

stage_name = dict(STAGES).get(reached, '未達')
print('reached_stage: %d/6  (%s)' % (reached, stage_name))
for k, v in STAGES:
    print('  [%s] stage %d: %s' % ('x' if k <= reached else ' ', k, v))

# stop reason (full run)
stop = None
if halt0:
    stop = 'Halt0 経由の早期終了 (longjmp で巻き戻し; DllMain 完走ではない) units_run=%s/%s' % (F.get('units_run'), F.get('units_total'))
elif F.get('dllmain_done'):
    stop = 'longjmp 経路 (Halt0 無しで巻き戻し) — 判定外'
elif F.get('threw'):
    _tail = full_txt[full_txt.find('boot threw:'):] if 'boot threw:' in full_txt else full_txt
    frames = re.findall(r'wasm-function\[(\d+)\]', _tail)
    chain = ' <- '.join(N.get(int(i), '?') for i in frames[:5])
    stop = 'trap "%s" @ %s' % (F['threw'], chain)
elif complete6:
    stop = 'DllMain attach 正常完走 (全 %s unit を Halt0 無しで実行, DllMain=TRUE)' % F.get('units_total')
else:
    stop = 'boot_enter が戻った (rc=%s, units_run=%s/%s, skipped=%s)' % (
        F.get('boot_rc'), F.get('units_run'), F.get('units_total'), F.get('units_skipped'))
print('stop_reason (full InitUnits run): %s' % stop)
print('  units: run=%s / total=%s, init_count(prologue)=%s, icall ok=%s miss=%s' % (
    F.get('units_run'), F.get('units_total'), F.get('init_count'), F.get('icall_ok'), F.get('icall_miss')))

# FastMM state
pr = F.get('probes') or {}
va0 = re.search(r'\[m11\]\[VA\] #0 addr=\S+ size=(\d+) \(0x([0-9a-f]+)\) type=(0x[0-9a-f]+)', full_txt)
print('FastMM4 state (full run): GetMem=%s FreeMem=%s FastMM_GetMem_impl=%s FastMM_FreeMem_impl=%s' % (
    pr.get('GetMem'), pr.get('FreeMem'), pr.get('FastMM_GetMem(407a50)'), pr.get('FastMM_FreeMem(407e20)')))
print('  VirtualAlloc calls=%s total=%.1f MB' % (F.get('va_calls'), (F.get('va_used') or 0) / 1e6))
if va0:
    sz = int(va0.group(1))
    print('  first VirtualAlloc size=%d (0x%x)%s' % (sz, sz, '  == FastMM4 MediumBlockPoolSize (1.25MB-16)' if sz == 0x13fff0 else ''))
print('  fastmm_initialized: %s' % ('yes (GetMem->medium pool VirtualAlloc 実行済)' if (pr.get('GetMem') or 0) > 0 and (F.get('va_calls') or 0) > 0 else 'no'))

print('stubs/dispatch: Win32 stub uniq=%s hits=%s / indirect-call table entries=%s' % (F.get('stub_uniq'), F.get('stub_total'), F.get('disp_entries')))
print('image: %s bytes, wasm: %s bytes' % (F.get('image_bytes'), F.get('wasm_size')))

if S:
    print('-' * 72)
    print('unit survey (InitUnits 抑止 → 942 unit を 1 本ずつ try/catch 隔離; DllMain done=%s):' % S.get('dllmain_done'))
    print('  ok=%s noproc=%s miss(closure外)=%s trap=%s clobber=%s  (合計 %s)' % (S.get('ok'), S.get('noproc'), S.get('miss'), S.get('trap'), S.get('clobber', 0), S.get('units')))
    print('  trap kinds: %s' % json.dumps(S.get('trap_kinds'), ensure_ascii=False))
    if S.get('trap_oom') is not None:   # #513: OOM (VirtualAlloc が NULL を返した unit) 起因の trap を分離
        print('  oom 分離: trap=%s = oom %s (unit 実行中に VirtualAlloc が NULL) + その他 %s / ok のうち OOM を踏んだ unit %s / 非 OOM trap kinds: %s' % (
            S.get('trap'), S.get('trap_oom'), S.get('trap_other'), S.get('ok_with_oom'), json.dumps(S.get('trap_kinds_nonoom'), ensure_ascii=False)))
        print('  clobber (unit が image の InitTable を壊した → 実行前の image を戻した): %s' % (S.get('clobber_units') or []))
        print('  VirtualAlloc (survey): live=%.1f MB peak=%.1f MB oom=%s 実解放 %s 回 (%.1f MB) 表に無い解放 %s 見送り(NC) %s decommit %s 64MB 以上の要求 %s 回%s' % (
            (S.get('va_live') or 0) / 1e6, (S.get('va_peak') or 0) / 1e6, S.get('va_oom'), S.get('va_freed'), (S.get('va_freed_bytes') or 0) / 1e6,
            S.get('va_free_unknown'), S.get('va_free_skipped'), S.get('va_decommit'), S.get('va_big'), '  [NC: VirtualFree 無効]' if S.get('vfree_noop') else ''))
    tf = S.get('top_frame_idx') or {}
    top = sorted(tf.items(), key=lambda kv: -kv[1])[:8]
    print('  top trap frames: %s' % ', '.join('%s x%d' % (N.get(int(k), 'fn#' + k), v) for k, v in top))
    print('  FastMM (survey 通算): GetMem=%s FreeMem=%s VirtualAlloc calls=%s %.1f MB' % (
        S.get('getmem'), S.get('freemem'), S.get('va_calls'), (S.get('va_bytes') or 0) / 1e6))
    print('  unresolved function_* (fail-fast): %s' % json.dumps(S.get('failfast_functions')))
    print('  Win32 stub hits (uniq=%s total=%s): %s' % (S.get('stub_uniq'), S.get('stub_total'), ', '.join((S.get('stub_hits') or [])[:12])))
    mb = re.findall(r'\[m11\]\[MessageBox[AW]\][^\n]*', sv_txt)
    print('  MessageBox 呼出し: %d 件%s' % (len(mb), (' 例: ' + mb[0][:160]) if mb else ''))

print('-' * 72)
print('M11_SUMMARY ' + json.dumps({
    'reached_stage': reached, 'stop_reason': stop, 'ir_conditions': COND,
    'units_run_full': F.get('units_run'), 'units_total': F.get('units_total'),
    'survey_ok': S.get('ok') if S else None, 'survey_trap': S.get('trap') if S else None, 'survey_trap_oom': S.get('trap_oom') if S else None, 'survey_clobber': S.get('clobber') if S else None, 'survey_miss': S.get('miss') if S else None,
    'getmem': pr.get('GetMem'), 'freemem': pr.get('FreeMem'), 'va_calls': F.get('va_calls'), 'va_mb': round((F.get('va_used') or 0) / 1e6, 1),
    'wasm_bytes': F.get('wasm_size'), 'trampolines': F.get('disp_entries'),
    'halt0_early': halt0, 'dllmain_normal_true': complete6,
}, ensure_ascii=False))
if REQUIRE is not None and reached < REQUIRE:
    print('REQUIRE_STAGE_FAILED: reached_stage=%d < required=%d' % (reached, REQUIRE))
    sys.exit(1)
sys.exit(0)
