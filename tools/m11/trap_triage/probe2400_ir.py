#!/usr/bin/env python3
# #2400 計測専用 (M11_PROBE_2400=1 のとき m11_build.sh から呼ぶ): function_e3ef60 の 60a270 呼出し 9 箇所の直前で
#   m11_e3ef60_obs(site, arg1, this, edx) を呼ぶ. site は呼出し番地順の 1..9 (1: e3f0b4 ... 9: e3f215; C 側の表と対応).
#   this は IR 上 [arg1+off] のロード値そのもの (off = 0x778・0x7d8・0x810・0x840・0x808・0x7f0・0x838・0x8e8・0x9c8).
# 既定 off では呼ばない (m11_build.sh が M11_PROBE_2400=1 のときだけ通す)。冪等: 既に入っていれば何もしない。
# 使い方: python3 trap_triage/probe2400_ir.py work/boot_final3.ll   (in-place)
import re
import sys

src = sys.argv[1]
s = open(src).read()
if 'm11_e3ef60_obs' in s:
    print('[probe2400_ir] already patched: ' + src)
    sys.exit(0)

m = re.search(r'^define [^\n]*@function_e3ef60\(.*?^}\n', s, re.S | re.M)
if not m:
    sys.exit('[probe2400_ir] function_e3ef60 が無い: %s' % src)
body = m.group(0)
pat = re.compile(r'^  (%[\w.]+) = call i64 @function_60a270\(i64 (%[\w.]+), i32 (%[\w.]+)\)\n', re.M)
n = len(pat.findall(body))
if n != 9:
    sys.exit('[probe2400_ir] 60a270 呼出しは 9 箇所のはず (%d 箇所): %s' % (n, src))

cnt = [0]


def ins(mm):
    cnt[0] += 1
    return '  call void @m11_e3ef60_obs(i32 %d, i64 %%arg1, i64 %s, i32 %s)\n' % (cnt[0], mm.group(2), mm.group(3)) + mm.group(0)


body = pat.sub(ins, body)
s = s[:m.start()] + body + s[m.end():]
s = s.rstrip('\n') + '\ndeclare void @m11_e3ef60_obs(i32, i64, i64, i32)\n'
open(src, 'w').write(s)
print('[probe2400_ir] patched function_e3ef60 (60a270 呼出し %d 箇所): %s' % (cnt[0], src))
