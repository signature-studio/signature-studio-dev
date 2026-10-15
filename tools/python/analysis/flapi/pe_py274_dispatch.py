#!/usr/bin/env python3
"""PY-274 (#3937): DMT を引く動的ディスパッチ関数 0x410090 の経路 (rdx の受け渡し) を逆アセンブルで照合する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py274_dispatch.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin' (<展開先>/extracted/block00031_PE.bin に展開される)
終了 0 = 全 PASS。1 件でも FAIL なら終了 1。
発火側の上流 (0x410090 を呼ぶ箇所) は本スクリプトの対象外 (REPORT_PY274.md)。
"""
import os
import sys

import capstone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pe_callgraph as pc  # noqa: E402

INS = pc.load()
BY_VA = {a: (m, o) for a, m, o in INS}
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print("PASS" if ok else "FAIL", name, detail)


def at(va, n):
    return [BY_VA.get(va + k) for k in range(n)]


DISPATCH = 0x410090
LOOKUP = 0x40FF70

# 0x410090 の入口: rcx = Self (受信オブジェクト)、rdx = TMessage* を退避する (rsi = rdx)。
check("0x410090 で rsi = rdx (TMessage* の退避)", BY_VA.get(0x41009E) == ("mov", "rsi, rdx"),
      f"got={BY_VA.get(0x41009E)}")
# Msg (word [rsi]) を msgid とし、0 と 0xc000 以上を既定経路へ回す。
check("0x410090 で msgid = word [rsi] を読む", BY_VA.get(0x4100A1) == ("movzx", "rax, word ptr [rsi]"),
      f"got={BY_VA.get(0x4100A1)}")
check("0x410090 で DMT 検索 0x40ff70 を呼ぶ", BY_VA.get(0x4100B8) == ("call", hex(LOOKUP)),
      f"got={BY_VA.get(0x4100B8)}")
# 見つかった handler を call [rbp+0x20] で呼ぶ。第 2 引数 rdx は rsi (TMessage*) のまま。
check("0x410090 で handler 呼出しの直前に rdx = rsi (TMessage*)",
      BY_VA.get(0x4100CE) == ("mov", "rdx, rsi") and BY_VA.get(0x4100D1) == ("call", "qword ptr [rbp + 0x20]"),
      f"got={BY_VA.get(0x4100CE)},{BY_VA.get(0x4100D1)}")
# 見つからないときは DefaultHandler (call [vmt-0x38]) へ同じ rdx を渡す。
check("0x410090 の既定経路も rdx = rsi を渡す",
      BY_VA.get(0x4100E7) == ("mov", "rdx, rsi") and BY_VA.get(0x4100ED) == ("call", "qword ptr [rbx - 0x38]"),
      f"got={BY_VA.get(0x4100E7)},{BY_VA.get(0x4100ED)}")
# 0x40ff70 (DMT 検索): rcx = VMT、edx = msgid。見つからなければ親 VMT (vmt-0x78) へ進む。
check("0x40ff70 で DMT は [VMT-0x90] から読む", BY_VA.get(0x40FF73) == ("mov", "rcx, qword ptr [rax - 0x90]"),
      f"got={BY_VA.get(0x40FF73)}")
check("0x40ff70 で祖先鎖は [VMT-0x78] から辿る", BY_VA.get(0x40FFCB) == ("mov", "rax, qword ptr [rax - 0x78]"),
      f"got={BY_VA.get(0x40FFCB)}")

# 0x410090 を呼ぶ direct call 箇所は無い (間接経路)。
dcalls = [a for a, m, o in INS if m == "call" and o.startswith("0x") and int(o, 16) == DISPATCH]
check("0x410090 への direct call は 0 件 (呼出し元は関数ポインタ経由)", dcalls == [], f"sites={[hex(x) for x in dcalls]}")

print()
print("PASS 件数", sum(RESULTS), "/", len(RESULTS))
sys.exit(0 if all(RESULTS) else 1)
