#!/usr/bin/env python3
"""playlist 未読 26 関数 (PY-61 / #2026) の逆アセンブル事実を抽出する (PY-57 の解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/playlist_undecided_facts.py

出力 (関数ごと): PyArg 書式文字列 (取れたもの)・範囲 code 経路 (cmp 0x1f4 と -4 の VA)・
track 要素のフィールド読み (imul rcx,0x45 の後の [rax+rcx*4+off])・コア呼び出し (lea r8 の先)・
戻り値の変換 (call qword ptr [rax] の数)。末尾に 0xd82c20 の status → 文言表を出す。
値は逆アセンブルの事実のみ。意味づけ (実装の戻り値) は REPORT_PY61.md を見ること。
"""
import os
import re

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
FUNCS = {
    "getTrackColor": 0xD55EA0, "isTrackMuteLock": 0xD56490, "muteTrackLock": 0xD565C0,
    "soloTrack": 0xD56830, "isTrackSelected": 0xD56A40, "selectAll": 0xD56D00,
    "deselectAll": 0xD56DD0, "getTrackActivityLevelVis": 0xD56F10, "getDisplayZone": 0xD56F80,
    "lockDisplayZone": 0xD57030, "liveDisplayZone": 0xD57200, "getLiveLoopMode": 0xD57370,
    "getLiveTriggerMode": 0xD573E0, "getLivePosSnap": 0xD57450, "getLiveTrigSnap": 0xD574C0,
    "getLiveBlockStatus": 0xD57550, "getLiveStatus": 0xD57670, "getLiveBlockColor": 0xD57740,
    "triggerLiveClip": 0xD57860, "refreshLiveClips": 0xD57A20, "incLivePosSnap": 0xD57B50,
    "incLiveTrigSnap": 0xD57CD0, "incLiveLoopMode": 0xD57E50, "incLiveTrigMode": 0xD57FD0,
    "liveTimeToBlockNum": 0xD58150, "liveBlockNumToTime": 0xD581A0,
}
STATUS_CALLER = 0xD82C20
DISPATCH = "0xd843d0"

raw = open(PE, "rb").read()
pe = pefile.PE(data=raw, fast_load=True)
BASE = pe.OPTIONAL_HEADER.ImageBase
MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)


def fo_of(va):
    rva = va - BASE
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.PointerToRawData + (rva - s.VirtualAddress)
    raise SystemExit(f"VA {va:#x} is outside sections")


def cstr(va):
    fo = fo_of(va)
    return raw[fo:raw.find(b"\0", fo, fo + 400)].decode("latin1")


CORES = [0xD56510, 0xD56770, 0xD56990, 0xD56AB0, 0xD56C90, 0xD56FC0, 0xD57150, 0xD577E0,
         0xD579D0, 0xD57AF0, 0xD57C70, 0xD57DF0, 0xD57F70, 0xD85210, 0xD55F30]
READ8 = [0xD56160, 0xD56330, 0xD566F0, 0xD56B60, 0xD56EA0, 0xD580F0, 0xD581F0, 0xD585D0]
STARTS = sorted(set(FUNCS.values()) | set(CORES) | set(READ8))


def body(va):
    out, after_ret = [], None
    end = min((b for b in STARTS if b > va), default=va + 1500)
    for x in MD.disasm(raw[fo_of(va):fo_of(va) + 1500], va):
        if x.address >= end or (after_ret is not None and x.mnemonic == "int3" and x.address - after_ret <= 4):
            break
        if x.mnemonic == "ret":
            after_ret = x.address
        out.append(x)
    return out


def rip_target(x):
    m = re.search(r"\[rip ([+-]) (0x[0-9a-f]+)\]", x.op_str)
    if not m:
        return None
    d = int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
    return x.address + x.size + d


def main():
    for name, va in FUNCS.items():
        ins = body(va)
        fmt = next((cstr(t) for x in ins[:60] if x.mnemonic == "lea" and x.op_str.startswith("rdx,")
                    for t in [rip_target(x)] if t and x.address < va + 0x200), None)
        core, last_r8 = None, None
        for x in ins:
            if x.mnemonic == "lea" and x.op_str.startswith("r8,") and "rip" in x.op_str:
                last_r8 = rip_target(x)
            if x.mnemonic == "call" and x.op_str == DISPATCH and core is None:
                core = hex(last_r8) if last_r8 else None
        fields = sorted({re.search(r"\+ (0x[0-9a-f]+)\]", x.op_str).group(1)
                         for x in ins if "rcx*4" in x.op_str and re.search(r"\+ (0x[0-9a-f]+)\]", x.op_str)})
        ranges = sum(1 for x in ins if x.mnemonic == "cmp" and "0x1f4" in x.op_str)
        neg4 = sum(1 for x in ins if "0xfffffffffffffffc" in x.op_str)
        vcalls = sum(1 for x in ins if x.mnemonic == "call" and "qword ptr [rax]" in x.op_str)
        to_status = sum(1 for x in ins if x.mnemonic == "call" and x.op_str == hex(STATUS_CALLER))
        print(f"{name:26s} {va:#x} fmt={fmt!r} core={core} fields={fields} "
              f"cmp1f4={ranges} neg4={neg4} vcall={vcalls} status_call={to_status}")
    print("-- status -> text (0xd82c20 の分岐先の lea rdx)")
    for x in body(STATUS_CALLER):
        if x.mnemonic == "lea" and x.op_str.startswith("rdx,"):
            t = rip_target(x)
            print(f"{x.address:#x} -> {t:#x} {cstr(t)!r}")


if __name__ == "__main__":
    main()
