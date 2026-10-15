#!/usr/bin/env python3
"""fw_smoke_check の RunError 判定と stage-2 の emcc 設定 (素材不要)。python3 tests/test_fw_smoke_check.py"""
import contextlib
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FW = os.path.join(HERE, '..')
sys.path.insert(0, FW)
import fw_smoke_check as S

fails = []


def check(name, cond, info=''):
    print(('PASS ' if cond else 'FAIL ') + name + (' ' + str(info) if info and not cond else ''))
    if not cond:
        fails.append(name)


PASS_LINE = '[fw] SMOKE PASS (Halt0/RestoreContext 到達): dispatch=38 units_done=0 va=1 heap=1 ff=0'
RUNERR_203 = '[fw][MessageBoxA] Error: Runtime error 203 at 0000000000000001'  # REPORT_3150 §2 (smoke.log 27 行目)
RUNERR_OLD = '[fw][MessageBoxA] Error: Runtime 268436792 at 0000000010000710'  # 150a83fa の baseline (smoke.log 29 行目)


def run_main(lines, expect):
    with tempfile.TemporaryDirectory() as d:
        log = os.path.join(d, 'smoke.log')
        with open(log, 'w') as f:
            f.write('\n'.join(lines) + '\n')
        with contextlib.redirect_stdout(io.StringIO()):
            return S.main(['--log', log, '--image', os.path.join(d, 'none.bin'), '--expect'] + expect)


check('Runtime error N at ADDR を数える (#3150 の再現行)', S.RUNERR_RE.match(RUNERR_203) is not None)
check('Runtime N at ADDR (error なし) も数える', S.RUNERR_RE.match(RUNERR_OLD) is not None)
check('RunError 以外の行は数えない', S.RUNERR_RE.match('[fw][MessageBoxA] Info: Runtime error 203 at 1') is None)
check('再現ログ 1 行で runerr=1 (ff=0 init_reach=-1)',
      run_main([RUNERR_203, PASS_LINE], ['runerr=1', 'ff=0', 'init_reach=-1']) == 0)
check('再現ログを runerr=0 と期待すると FAIL を返す',
      run_main([RUNERR_203, PASS_LINE], ['runerr=0', 'ff=0', 'init_reach=-1']) == 1)
check('RunError が無ければ runerr=0', run_main([PASS_LINE], ['runerr=0', 'ff=0', 'init_reach=-1']) == 0)

with open(os.path.join(FW, 'fw_stage2.sh')) as f:
    STAGE2 = f.read()
check('emcc は EXIT_RUNTIME=0 (exit 後も情報関数を呼べる)',
      '-sEXIT_RUNTIME=0 ' in STAGE2 and '-sEXIT_RUNTIME=1' not in STAGE2)

if fails:
    print('FAILED: %d' % len(fails))
    sys.exit(1)
print('ALL PASS')
