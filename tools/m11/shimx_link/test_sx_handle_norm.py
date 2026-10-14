#!/usr/bin/env python3
"""sx_handle_norm.py の合成 IR 検査 (#1628)。全ケース PASS で終了 0、FAIL があれば終了 1。

  python3 tools/m11/shimx_link/test_sx_handle_norm.py

素の declare 形 (measured IR と同じ形) の正規化・冪等性と、想定外の参照 (invoke) での停止を確かめる。
宣言の形が崩れた入力 (属性付き宣言・宣言無し) の fail-closed は測定していないため検査しない (SHX-T32)。
実 IR (boot_final3.ll) は使わない (生成には emsdk・work-m11 が要る)。
"""
import os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS = os.path.join(HERE, 'sx_handle_norm.py')

BODY = """define i32 @f(i64 %%hmo) {
entry:
  %%r = call i32 @midiOutShortMsg(%s)
  ret i32 %%r
}
"""
STRICT = 'declare i32 @midiOutShortMsg(i64, i32)\n\n' + BODY % 'i64 %hmo, i32 0'


def run(text):
    d = tempfile.mkdtemp()
    src, dst = os.path.join(d, 'in.ll'), os.path.join(d, 'out.ll')
    with open(src, 'w') as f:
        f.write(text)
    p = subprocess.run([sys.executable, PASS, src, dst], capture_output=True, text=True)
    out = open(dst).read() if p.returncode == 0 else None
    return p.returncode, out


cases = []

rc, out = run(STRICT)
cases.append(('strict: 正規化 (宣言 i32・呼出し trunc)', rc == 0
              and 'declare i32 @midiOutShortMsg(i32, i32)' in out
              and 'trunc i64 %hmo to i32' in out
              and 'call i32 @midiOutShortMsg(i32 %sxh_' in out
              and 'i64' not in out.split('define')[0].split('declare')[1]))

rc2, out2 = run(out)
cases.append(('冪等: 2 回目は無変更', rc2 == 0 and out2 == out))

rc, _ = run(STRICT.replace('call i32 @midiOutShortMsg(i64 %hmo, i32 0)',
                           'invoke i32 @midiOutShortMsg(i64 %hmo, i32 0) to label %a unwind label %b'))
cases.append(('invoke: 想定外参照で停止 (rc != 0)', rc != 0))

rc, out = run('declare i32 @other(i64, i32)\n\n' + BODY.replace('midiOutShortMsg', 'other') % 'i64 %hmo, i32 0')
cases.append(('無関係な関数のみ: 変更無し・rc 0', rc == 0 and out is not None and 'declare i32 @other(i64, i32)' in out))

bad = 0
for name, ok in cases:
    print(('PASS ' if ok else 'FAIL ') + name)
    bad += 0 if ok else 1
print('test_sx_handle_norm: cases=%d fail=%d' % (len(cases), bad))
sys.exit(1 if bad else 0)
