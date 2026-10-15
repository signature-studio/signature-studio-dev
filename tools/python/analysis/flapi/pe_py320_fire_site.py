#!/usr/bin/env python3
"""PY-320 (#4346): 公開表 0x12acb70 (MoveLeftMenuClick) を TMethod(Code, Data) として呼ぶ呼出し箇所 (関数と VA) と、rdx (第 2 引数 = Sender) の出どころを PE 上で確定する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py320_fire_site.py

展開: tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin' (<展開先>/extracted/block00031_PE.bin に展開される)
Delphi x64 の VMT 配置: 自己ポインタ VMT-0xc8、動的メソッド表ポインタ以外の仮想スロットは VMT+8*k。
終了 0 = 全 PASS。1 件でも FAIL なら終了 1。負の対照は検出できれば PASS。
前段: pe_py268_rdx.py (VMT 0x1277f38・公開表 0x12793f3 の照合)。
"""
import os
import re
import struct
import sys

import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pe_callgraph as pc  # noqa: E402

RAW = open(os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin"), "rb").read()
TEXT_VA = 0x401000
TEXT_FO = 0x400
TEXT_SIZE = 0xFA34B0
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print("PASS" if ok else "FAIL", name, detail)


def control(name, detected, detail=""):
    check("負の対照: " + name, detected, detail)


def is_text(va):
    return TEXT_VA <= va < TEXT_VA + TEXT_SIZE


def u64(va):
    return struct.unpack_from("<Q", RAW, va - TEXT_VA + TEXT_FO)[0]


def shortstr(va):
    o = va - TEXT_VA + TEXT_FO
    n = RAW[o]
    return RAW[o + 1:o + 1 + n].decode("latin1")


def find_vmt(name):
    qw = memoryview(RAW)[TEXT_FO:TEXT_FO + TEXT_SIZE].cast("Q")
    selfs = [TEXT_VA + 8 * i + 0xC8 for i, v in enumerate(qw) if v == TEXT_VA + 8 * i + 0xC8]
    return [v for v in selfs if is_text(v - 0x88) and is_text(u64(v - 0x88))
            and shortstr(u64(v - 0x88)) == name]


def slot(vmt, off):
    return u64(vmt + off)


INS = pc.load()
MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
LOAD = re.compile(r"^qword ptr \[(\w+) \+ (0x[0-9a-f]+)\]$")


def dispatch_sites(insns, code_off):
    """call qword ptr [R + code_off] の直前 (8 命令以内) に rcx = [R + code_off+8] と rdx = <Self> があり、Self が R と同じ reg の箇所。"""
    out = []
    for i, (a, m, o) in enumerate(insns):
        if m != "call":
            continue
        mm = LOAD.match(o)
        if not mm or int(mm.group(2), 16) != code_off:
            continue
        base = mm.group(1)
        win = insns[max(0, i - 8):i]
        data = [x for x in win if x[1] == "mov" and x[2] == "rcx, qword ptr [%s + %s]" % (base, hex(code_off + 8))]
        self_ = [x for x in win if x[1] == "mov" and x[2] == "rdx, %s" % base]
        if data and self_:
            out.append((a, base))
    return out


TMENU = find_vmt("TMenuItem")
TQUICK = find_vmt("TQuickMenuItem")
check("TMenuItem の VMT: 自己ポインタと classname の照合で 1 件・VMT=0x838c10",
      TMENU == [0x838C10], f"found={[hex(x) for x in TMENU]}")
check("TQuickMenuItem の VMT: 自己ポインタと classname の照合で 1 件・VMT=0x725a58",
      TQUICK == [0x725A58], f"found={[hex(x) for x in TQUICK]}")
VM_T = TMENU[0] if len(TMENU) == 1 else 0
VM_Q = TQUICK[0] if len(TQUICK) == 1 else 0

DISP = 0x840B50
check("TMenuItem の仮想スロット 0xd0 は 0x840b50 (Click 系ディスパッチャ)",
      slot(VM_T, 0xD0) == DISP, f"slot={hex(slot(VM_T, 0xD0))}")
OVR = 0x72DB20
check("TQuickMenuItem の仮想スロット 0xd0 は 0x72db20 (TMenuItem のスロットを上書き)",
      slot(VM_Q, 0xD0) == OVR, f"slot={hex(slot(VM_Q, 0xD0))}")

direct = [a for a, m, o in INS if m == "call" and o == hex(DISP)]
check("0x840b50 への直接 call は 1 箇所 (0x72db3d・0x72db20 の内側)",
      len(direct) == 1 and 0x72DB20 <= direct[0] < 0x72DB4F,
      f"sites={[hex(x) for x in direct]}")

def in_func(va, start, end):
    return start <= va < end


sites_all = dispatch_sites(INS, 0x100)
sites = [(a, b) for a, b in sites_all if in_func(a, DISP, 0x840C3A)]
check("0x840b50 の関数内に Code=[R+0x100]・Data=[R+0x108] を rcx/rdx=R で call する箇所が 2 件",
      len(sites) == 2 and all(b == "rbx" for _, b in sites),
      f"sites={[(hex(a), b) for a, b in sites]} (関数外の同型箇所 {len(sites_all) - len(sites)} 件は対象外)")
check("呼出し箇所の VA は 0x840be8 と 0x840c2e",
      sorted(a for a, _ in sites) == [0x840BE8, 0x840C2E],
      f"sites={[hex(a) for a, _ in sites]}")

idx = [i for i, (a, m, o) in enumerate(INS) if a == DISP][0]
check("0x840b50 の入口で rbx = rcx (Self を保持し、rdx の出どころにする)",
      any(x[1] == "mov" and x[2] == "rbx, rcx" for x in INS[idx:idx + 4]),
      f"insns={[x[2] for x in INS[idx:idx + 4]]}")
check("呼出し直前の rdx 設定は mov rdx, rbx (Self) のみ",
      all(any(x[1] == "mov" and x[2] == "rdx, rbx" for x in INS[max(0, i - 8):i])
          for i, (a, m, o) in enumerate(INS) if a in (0x840BE8, 0x840C2E)),
      "")

sites_q = [(a, b) for a, b in dispatch_sites(INS, 0xF0) if in_func(a, 0x840CD0, 0x840D28)]
control("0x840cd0 は +0xf0 の Code を rdx=Self で呼ぶ別経路で、+0x100 の検出は 0 件",
        len([x for x in sites_all if in_func(x[0], 0x840CD0, 0x840D28)]) == 0 and len(sites_q) == 1,
        f"+0xf0 sites={[hex(a) for a, _ in sites_q]}")

LOAD_VA = 0x12ACB70
hits4 = [i for i in range(len(RAW) - 3) if RAW[i:i + 4] == struct.pack("<I", LOAD_VA)]
check("0x12acb70 の即値・絶対値としての出現は公開表の 1 件のみ (呼出し箇所は値を即値で持たない)",
      len(hits4) == 1, f"fileoffs={[hex(x) for x in hits4]}")

sys.exit(0 if all(RESULTS) else 1)
