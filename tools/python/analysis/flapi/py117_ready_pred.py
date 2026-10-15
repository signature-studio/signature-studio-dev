#!/usr/bin/env python3
"""playlist.muteTrackLock の準備判定 (core 0xd56510 の call [rax+0x98] @0xd56535) の呼出し先を PE から確定する (PY-117 / #2959)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/py117_ready_pred.py

連鎖 (静的に確認できた範囲。各段は assert で検査する):
  this = [[[G]]+8]  G = 0x15e4790 (global)            (0xd56521〜0xd56532)
  C = [B+8] は 0x1263540 / 0x1264100 が 0x125da90(class=[0x125b0f8], dl=1) の戻り値を格納する (lazy 生成)
  C の VMT = [0x125b0f8] = 0x125b1c0 (NewInstance = VMT[-0x30] = 0x40f960)
  準備判定の呼出し先 = VMT[0x98] = 0x1262b80 (general.safeToEdit と同じ式・REPORT_PY94)
  0x1262b80 の真偽: byte[*g1]==0 && byte[*g2]==0 && !C.VMT[0x48]() && dword[*g3 + 0x168] <= 0
値は逆アセンブルの事実のみ。実行時の値 (.bss) は PE の静的内容に無いので、ここでは読まない。
"""
import os
import struct

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
raw = open(PE, "rb").read()
pe = pefile.PE(data=raw, fast_load=True)
BASE = pe.OPTIONAL_HEADER.ImageBase
MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
G = 0x15E4790
CORE, CALLSITE, STORE_C_1, STORE_C_2 = 0xD56510, 0xD56535, 0x1263540, 0x1264100
CLASS_GLOBAL, PRED = 0x125B0F8, 0x1262B80


def fo_of(va):
    rva = va - BASE
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.PointerToRawData + (rva - s.VirtualAddress), s.Name.rstrip(b"\0").decode()
    raise SystemExit(f"VA {va:#x} is outside sections")


def u64(va):
    return struct.unpack_from("<Q", raw, fo_of(va)[0])[0]


def ins_at(va, n=1):
    f, _ = fo_of(va)
    return list(MD.disasm(raw[f:f + 16 * n], va))[:n]


def rip_target(x):
    import re
    m = re.search(r"\[rip ([+-]) (0x[0-9a-f]+)\]", x.op_str)
    if not m:
        return None
    d = int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
    return x.address + x.size + d


def main():
    # 1. 呼出し元: G 経由で this を作り、vtbl[0x98] を呼ぶ
    chain = []
    for x in MD.disasm(raw[fo_of(CORE)[0] + 0x11:fo_of(CORE)[0] + 0x25], CORE + 0x11):
        chain.append(x)
    loads = [x for x in chain if x.mnemonic == "mov" and "rip" in x.op_str]
    assert rip_target(loads[0]) == G, hex(rip_target(loads[0]))
    call = ins_at(CALLSITE)[0]
    assert call.mnemonic == "call" and call.op_str == "qword ptr [rax + 0x98]", call.op_str
    print(f"[1] 呼出し元 {CALLSITE:#x}: {call.mnemonic} {call.op_str}。this の源 = [{G:#x}] 経由 (rip 先 {rip_target(loads[0]):#x})")

    # 2. C = [B+8] の生成 (lazy): 0x976a90 (B の生成) の後に 0x125da90 の戻り値を [B+8] へ格納
    for site in (STORE_C_1, STORE_C_2):
        seq = ins_at(site, 1)
        assert seq
    for site, callee in ((STORE_C_1, 0x976A90), (STORE_C_2, 0x125DA90)):
        blk = list(MD.disasm(raw[fo_of(site)[0]:fo_of(site)[0] + 160], site))
        calls = [x for x in blk if x.mnemonic == "call"]
        assert any(int(x.op_str, 16) == callee for x in calls if x.op_str.startswith("0x")), (hex(site), [x.op_str for x in calls])
        stores = [x for x in blk if x.mnemonic == "mov" and x.op_str.endswith("], rax") and "+ 8]" in x.op_str]
        assert stores, hex(site)
        print(f"[2] 生成 {site:#x}: call {[x.op_str for x in calls][:3]} ; 格納 {stores[0].op_str}")

    # 3. C のクラス (VMT): 0x125da90 の class 引数 = [CLASS_GLOBAL]。NewInstance = VMT[-0x30]
    vmt = u64(CLASS_GLOBAL)
    new_inst = u64(vmt - 0x30)
    assert new_inst == 0x40F960, hex(new_inst)
    slot98 = u64(vmt + 0x98)
    assert slot98 == PRED, hex(slot98)
    print(f"[3] C の VMT = [{CLASS_GLOBAL:#x}] = {vmt:#x} / NewInstance = {new_inst:#x} / 準備判定の呼出し先 VMT[0x98] = {slot98:#x}")

    # 4. 述語 0x1262b80 の真偽条件 (ガードの global とその参照先)
    body = []
    for x in MD.disasm(raw[fo_of(PRED)[0]:fo_of(PRED)[0] + 96], PRED):
        body.append(x)
        if x.mnemonic == "ret":
            break
    globs = [rip_target(x) for x in body if x.mnemonic == "mov" and "rip" in x.op_str]
    assert len(globs) == 3, globs
    g1, g2, g3 = globs
    p1, p2, p3 = u64(g1), u64(g2), u64(g3)
    vt48 = u64(vmt + 0x48)
    print(f"[4] 述語 {PRED:#x}: 真 ⇔ byte[*{g1:#x}]==0 && byte[*{g2:#x}]==0 && !C.VMT[0x48]()={vt48:#x} && dword[*{g3:#x}+0x168] <= 0")
    print(f"    静的内容: *{g1:#x}={p1:#x}, *{g2:#x}={p2:#x}, *{g3:#x}={p3:#x} (.bss 側は実行時に設定。PE の静的内容は未設定)")


if __name__ == "__main__":
    main()
