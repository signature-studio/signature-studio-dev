#!/usr/bin/env python3
"""playlist の未確定点 (PY-105 / #2908・REPORT_PY105.md §5〜§8) の VMT・クラス名・呼出し元を抽出する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/playlist_class_facts.py

記法: [X] = X 番地の qword (ファイル内の値。.bss は実行時値なので 0 として扱わない: 読めなければ未確定)。
出力:
- T1: getLiveBlockColor (0x100c030) の owner 変数 (slot 0x15e35c8 → .bss 変数) の書込み元と、
  owner の +0xd2c (theme) の書込み箇所・直前の呼出し・class-ref (rcx に入る slot) → VMT → vmtClassName、
  VMT+0x218 の関数 VA と冒頭 30 命令。
- T2: 0x666780 の obj 変数 (0x16b6e00) の書込み元 (allocation の class-ref → vmtClassName)、
  0xbd68e0 の呼出し元 (mov ecx, 0x26 の直後のもの)、各呼出し元の VMT 逆引き (推定)。
- T3: 0x12e3a60 の G1 (0x15e2218)・G2 (0x15e22d8) の指す .bss 変数の書込み元 → vmtClassName、
  0x128f9e0 の VMT 逆引き (仮想メソッドかどうか)、0x12e3a60 内の 0x258 参照と呼出し行。
- T4: 0x12e7f80 の `*(*(0x15e13b8))` (.bss 変数) の書込み元 → vmtClassName、cfg を格納する [X+0xd98] の書込み元、
  cfg+0x49e を読み書きする関数の先頭 VA。

VMT 逆引き (推定): 関数 VA を値として持つ qword の直前 0x1000 バイト以内で、vmtClassName (VMT-0x88) が識別子の
ShortString を指す最も近い VMT を出す。確定ではない。
値は逆アセンブルと VMT の読取りのみ。意味づけは REPORT_PY105.md を見ること。
"""
import os
import re
import struct
from collections import deque

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
raw = open(PE, "rb").read()
pe = pefile.PE(data=raw, fast_load=True)
BASE = pe.OPTIONAL_HEADER.ImageBase
MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
TEXT = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
TEXT_LO = BASE + TEXT.VirtualAddress
RIP = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")
STORE_RIP = re.compile(r"^qword ptr \[rip [+-] 0x[0-9a-f]+\], r\w+$")
STORE_DISP = re.compile(r"^qword ptr \[(r\w+) \+ (0x(?:d2c|d98))\], (r\w+)$")
BYTE_49E = re.compile(r"byte ptr \[(r\w+) \+ 0x49e\]")
IDENT = re.compile(rb"^[A-Za-z_][A-Za-z0-9_]*$")
VOLATILE = {"rax", "rcx", "rdx", "r8", "r9", "r10", "r11"}
REGS = {"rax", "rbx", "rcx", "rdx", "rsi", "rdi", "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15"}

SLOT_OWNER = 0x15E35C8
SLOT_G1 = 0x15E2218
SLOT_G2 = 0x15E22D8
SLOT_CFG = 0x15E13B8
SLOT_CLASS_E2E9F8 = 0xE2E9F8
OBJ_0x666780 = 0x16B6E00
FN_BD68E0 = 0xBD68E0
FN_128F9E0 = 0x128F9E0
FN_12E3A60 = 0x12E3A60
FN_E9C770 = 0xE9C770
CALL_TARGETS = {FN_BD68E0, FN_128F9E0, FN_E9C770}


def fo(va):
    rva = va - BASE
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + s.SizeOfRawData:
            off = s.PointerToRawData + rva - s.VirtualAddress
            return off if off < len(raw) else None
    return None


def qword(va):
    off = fo(va)
    return struct.unpack_from("<Q", raw, off)[0] if off is not None else None


def va_of_file(pos):
    for s in pe.sections:
        if s.PointerToRawData <= pos < s.PointerToRawData + s.SizeOfRawData:
            return BASE + s.VirtualAddress + pos - s.PointerToRawData
    return None


def shortstr(ptr):
    off = fo(ptr) if ptr is not None else None
    if off is None:
        return None
    n = raw[off]
    body = raw[off + 1:off + 1 + n]
    return body if 0 < n < 64 and IDENT.match(body) else None


def vmt_name(vmt):
    ptr = qword(vmt - 0x88)
    s = shortstr(ptr)
    return s.decode() if s else None


def rip_target(addr, size, op):
    m = RIP.search(op)
    if not m:
        return None
    return addr + size + int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)


def func_start(va):
    off = fo(va)
    p = off
    for _ in range(0x8000):
        if raw[p - 1] == 0xCC and raw[p - 2] == 0xCC:
            return va_of_file(p)
        p -= 1
    return None


def sweep(store_targets, slot_set):
    data = raw[TEXT.PointerToRawData:TEXT.PointerToRawData + TEXT.SizeOfRawData]
    win = deque(maxlen=12)
    rec = {"store": [], "call": [], "disp": [], "b49e": [], "indirect": [], "frame228": []}
    pending = []
    pos = 0
    while pos < len(data):
        chunk = data[pos:pos + 0x10000 + 32]
        last = None
        for ins in MD.disasm(chunk, TEXT_LO + pos):
            if ins.address - TEXT_LO - pos >= 0x10000:
                break
            last = ins
            op = ins.op_str
            tgt = rip_target(ins.address, ins.size, op) if "[rip" in op else None
            dest = op.split(",")[0].strip()
            for pd in pending:
                if pd[0] == ins.address:
                    continue
                m = re.match(r"^qword ptr \[(r\w+)\], (r\w+)$", op)
                if ins.mnemonic == "mov" and m and m.group(1) == pd[1]:
                    rec["indirect"].append((pd[2], ins.address, op, list(win)))
            pending = [(a, r, sl, n - 1) for (a, r, sl, n) in pending
                       if n > 1 and not (dest == r and ins.mnemonic not in ("cmp", "test")) and not (ins.mnemonic == "call" and r in VOLATILE)]
            if ins.mnemonic == "mov" and tgt in slot_set and op.startswith(("r", "e")) and op.split(",")[0].strip() in REGS:
                pending.append((ins.address, op.split(",")[0].strip(), tgt, 10))
            if tgt in store_targets and STORE_RIP.match(op):
                rec["store"].append((tgt, ins.address, op, list(win)))
            elif ins.mnemonic == "call" and op.startswith("0x") and int(op, 16) in CALL_TARGETS:
                rec["call"].append((int(op, 16), ins.address, list(win)))
            elif ("0xd2c" in op or "0xd98" in op) and STORE_DISP.match(op):
                rec["disp"].append((ins.address, op, list(win)))
            elif op.startswith("qword ptr [rbp + 0x228], "):
                rec["frame228"].append((ins.address, op, list(win)))
            elif "0x49e" in op and BYTE_49E.search(op):
                rec["b49e"].append((ins.address, ins.mnemonic, op))
            win.append((ins.address, ins.size, ins.mnemonic, op))
        pos = last.address - TEXT_LO + last.size if last else pos + 1
    return rec


def alloc_of(window):
    """window 末尾の call の直前 (前の call まで) で rcx に渡す class-ref を探す。
    rcx = [slot] (slot の値が VMT) か、rcx = lea [rip+VMT] (VMT 自身) のどちらか。"""
    calls = [i for i, w in enumerate(window) if w[2] == "call"]
    if not calls:
        return None
    ci = calls[-1]
    call_va, call_tgt = window[ci][0], int(window[ci][3], 16) if window[ci][3].startswith("0x") else None
    for w in reversed(window[:ci]):
        if w[2] == "call":
            break
        if w[2] == "mov" and w[3].startswith("rcx, qword ptr [rip"):
            slot = rip_target(*w[:2], w[3])
            vmt = qword(slot)
            return (call_va, call_tgt, slot, vmt, vmt_name(vmt) if vmt else None)
        if w[2] == "lea" and w[3].startswith("rcx, [rip"):
            vmt = rip_target(*w[:2], w[3])
            return (call_va, call_tgt, None, vmt, vmt_name(vmt))
    return (call_va, call_tgt, None, None, None)


def method_owner(fva):
    """関数 VA を値に持つ qword の近くの VMT を推定する (推定・nearest header)。"""
    pat = struct.pack("<Q", fva)
    pos = raw.find(pat)
    while pos != -1:
        L = va_of_file(pos)
        if L is not None:
            for k in range(0, 0x1000 // 8):
                V = L - 8 * k
                name = vmt_name(V)
                if name:
                    return V, name, k
        pos = raw.find(pat, pos + 1)
    return None


def show_alloc(window, site):
    a = alloc_of(window)
    if a is None:
        print(f"    直前 call なし (store {site:#x})")
        return
    call_va, call_tgt, slot, vmt, name = a
    print(f"    直前 call={call_va:#x} (target {call_tgt and hex(call_tgt)})  class-ref slot={slot and hex(slot)}  VMT={vmt and hex(vmt)}  vmtClassName={name!r}")


def print_store(tag, site, op, w):
    print(f"  {tag} {site:#x}: {op}  func={hex(func_start(site)) if func_start(site) else None}")
    show_alloc(w, site)


def main():
    owner_var = qword(SLOT_OWNER)
    g1_var = qword(SLOT_G1)
    g2_var = qword(SLOT_G2)
    cfg_var = qword(SLOT_CFG)
    rec = sweep({OBJ_0x666780, owner_var}, {SLOT_OWNER, SLOT_G1, SLOT_G2, SLOT_CFG})

    print("-- T1 getLiveBlockColor 0x100c030 の theme 経路")
    print(f"  slot {SLOT_OWNER:#x} → 変数 {owner_var:#x} (.bss。owner = [{owner_var:#x}] は実行時値)")
    for tgt, site, op, w in rec["store"]:
        if tgt == owner_var:
            print_store("owner 変数への書込み", site, op, w)
    t1_func = func_start(0xE34933)
    for site, op, w in rec["frame228"]:
        if func_start(site) == t1_func:
            print(f"  [rbp+0x228] への書込み (theme 生成と同一関数) {site:#x}: {op}  直前 call={[hex(x[0]) for x in w if x[2] == 'call'][-1:]}")
    for site, op, w in rec["disp"]:
        if "0xd2c" in op:
            print_store("[reg+0xd2c] への書込み", site, op, w)
            for ww in w[-3:]:
                print(f"      直前: {ww[0]:#x} {ww[2]} {ww[3]}")
    vmt = qword(SLOT_CLASS_E2E9F8)
    print(f"  (参考) 0xe9c770 の rcx 候補 slot {SLOT_CLASS_E2E9F8:#x} = {vmt:#x}  vmtClassName={vmt_name(vmt)!r}")
    f218 = qword(vmt + 0x218)
    print(f"  VMT {vmt:#x} +0x218 の関数 = {f218:#x}")
    for x in MD.disasm(raw[fo(f218):fo(f218) + 30 * 16], f218):
        print(f"      {x.address:#x} {x.mnemonic} {x.op_str}")
        if x.mnemonic == "ret":
            break

    print("-- T2 0x666780 の obj 変数 (0x16b6e00) と 0xbd68e0 の k=0x26 呼出し元")
    for tgt, site, op, w in rec["store"]:
        if tgt == OBJ_0x666780:
            print_store("obj 変数への書込み", site, op, w)
    n_bd68 = 0
    for call_tgt, site, w in rec["call"]:
        if call_tgt != FN_BD68E0:
            continue
        n_bd68 += 1
        if any(t[2] == "mov" and t[3] == "ecx, 0x26" for t in w[-8:]):
            caller = func_start(site)
            mo = method_owner(caller) if caller else None
            print(f"  call 0xbd68e0 (k=0x26) {site:#x}  caller={hex(caller) if caller else None}  VMT逆引き(推定)={mo and (hex(mo[0]), mo[1], mo[2])}")
    print(f"  0xbd68e0 の全呼出し箇所数 = {n_bd68}")

    print("-- T3 0x12e3a60 の G1・G2 (間接参照) と 0x128f9e0")
    for name, slot, var in (("G1", SLOT_G1, g1_var), ("G2", SLOT_G2, g2_var)):
        print(f"  {name} slot {slot:#x} → 変数 {var:#x}")
        for sl, site, op, w in rec["indirect"]:
            if sl == slot:
                print_store(f"{name} 経由の書込み", site, op, w)
    mo = method_owner(FN_128F9E0)
    print(f"  0x128f9e0 の VMT 逆引き(推定) = {mo and (hex(mo[0]), mo[1], mo[2])} (None なら仮想メソッドの候補なし)")
    for x in MD.disasm(raw[fo(FN_12E3A60):fo(FN_12E3A60) + 320 * 16], FN_12E3A60):
        if x.address > FN_12E3A60 + 0x400:
            break
        if x.mnemonic == "call" or "0x258" in x.op_str:
            print(f"  0x12e3a60 内 {x.address:#x} {x.mnemonic} {x.op_str}")

    print("-- T4 0x12e7f80 の cfg (slot 0x15e13b8 → 変数 → 客体) と [X+0xd98]")
    print(f"  slot {SLOT_CFG:#x} → 変数 {cfg_var:#x}")
    for tgt, site, op, w in rec["store"]:
        if tgt == cfg_var:
            print_store("変数への書込み", site, op, w)
    for sl, site, op, w in rec["indirect"]:
        if sl == SLOT_CFG:
            print_store("slot 経由の書込み", site, op, w)
    for site, op, w in rec["disp"]:
        if "0xd98" in op and not re.search(r"\[(rbp|rsp) \+", op):
            print_store("[X+0xd98] への書込み", site, op, w)
    writers = []
    readers = set()
    for site, mn, op in rec["b49e"]:
        f = func_start(site)
        if mn == "mov" and op.startswith("byte ptr [") and f:
            writers.append((f, site, op))
        if f:
            readers.add(f)
    print(f"  [reg+0x49e] を読む関数 {len(readers)} 件 (汎用。cfg 特定不能)、そのうち mov で書く関数 {len({w[0] for w in writers})} 件")
    for f, site, op in sorted(writers)[:10]:
        print(f"    writer func {f:#x}  at {site:#x}  {op}")


if __name__ == "__main__":
    main()
