#!/usr/bin/env python3
"""arrangement の選択範囲読出し 4 件 (REPORT_PY96・PY-96 #2832) の PE 根拠を再計算して検査する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_selection_check.py

入力は block00031_PE.bin のみ。各 handler の先頭 (ret まで) の RIP 相対参照先・状態 field の offset・
共通ヘルパ (0xd77e20・0xe43e80) の呼出しを検査し、外れたら rc 1。
"""
import os
import re
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
CONV = 0x15E4280  # 戻り値の変換スロット (int と bool で共通。REPORT_PY87 と同じ)
OBJ = 0xD77E20  # 状態オブジェクトを返す共通ヘルパ
ACTIVE = 0xE43E80  # start >= 0 かつ end >= 0 を al に返す
FNS = {  # 名前: (handler 先頭 VA, 読む field の offset (int 系), 期待する呼出し先)
    "selectionStart": (0xD786E0, 0xD74, None),
    "selectionEnd": (0xD78700, 0xD78, None),
    "liveSelectionStart": (0xD78500, 0xD74, None),
    "selectionIsActive": (0xD78720, None, ACTIVE),
}


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=False)
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = pe.sections

    def v2o(va):
        rva = va - base
        for s in secs:
            if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
                return s.PointerToRawData + (rva - s.VirtualAddress)
        raise SystemExit(f"VA {va:#x} が無い")

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    ok = True
    for name, (fn, field, callee) in FNS.items():
        body = []
        for ins in md.disasm(raw[v2o(fn):v2o(fn) + 0x60], fn):
            body.append(ins)
            if ins.mnemonic == "ret":
                break
        rip = []
        for ins in body:
            if "rip" in ins.op_str:
                d = int(ins.op_str.split("rip")[1].split("]")[0].replace(" ", ""), 0)
                rip.append(ins.address + ins.size + d)
        calls = [int(ins.op_str, 16) for ins in body if ins.mnemonic == "call" and ins.op_str.startswith("0x")]
        fields = [int(m.group(1), 16) for ins in body for m in [re.search(r"dword ptr \[rax \+ (0x[0-9a-f]+)\]", ins.op_str)] if m]
        checks = [OBJ in calls, CONV in rip]
        if field is not None:
            checks.append(field in fields)
        if callee is not None:
            checks.append(callee in calls)
        print(f"{name:20s} fn={fn:#x} calls={[hex(c) for c in calls]} conv_slot={CONV in rip} "
              f"field={hex(field) if field is not None else '-'} ok={all(checks)}")
        ok = ok and all(checks)
    act = [ins for ins in md.disasm(raw[v2o(ACTIVE):v2o(ACTIVE) + 0x30], ACTIVE)][:8]
    cmp_ok = [i for i in act if i.mnemonic == "cmp" and "dword ptr [rcx" in i.op_str]
    print(f"active_helper {ACTIVE:#x} cmp_count={len(cmp_ok)} (期待 2: +0xd74 と +0xd78)")
    ok = ok and len(cmp_ok) == 2
    if not ok:
        print("FAIL")
        sys.exit(1)
    print("PASS")


if __name__ == "__main__":
    main()
