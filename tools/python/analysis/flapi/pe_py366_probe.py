#!/usr/bin/env python3
"""PY-366 (#4543): 0x4096d0 の範囲外 (bl > 0x1c) の経路と 0x459ef0 の役割の確認 (解析補助)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py366_probe.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'
  (<展開先>/extracted/block00031_PE.bin が存在すること)
終了 0 = 全 PASS。1 件でも FAIL なら終了 1。
"""
import os
import sys

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


def main():
    raw = open(PE, "rb").read()
    pe = pefile.PE(data=raw, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    text = [s for s in pe.sections if s.Name.startswith(b".text")][0]

    def fo_of(va):
        return text.PointerToRawData + (va - base - text.VirtualAddress)

    def decode(start, end):
        return list(md.disasm(raw[fo_of(start):fo_of(start) + (end - start)], start))

    def rip_ea(ins):
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                return ins.address + ins.size + op.mem.disp
        return None

    imports = {}
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    for entry in pe.DIRECTORY_ENTRY_IMPORT:
        for imp in entry.imports:
            if imp.address is not None and imp.name:
                imports[imp.address] = f"{entry.dll.decode()}!{imp.name.decode()}"

    def thunk_target(va):
        ins = decode(va, va + 6)[0]
        ea = rip_ea(ins)
        return imports.get(ea) if ea is not None and ins.mnemonic == "jmp" else None

    def calls(start, end):
        out = []
        for i in decode(start, end):
            if i.mnemonic == "call" and i.op_str.startswith("0x"):
                out.append((i.address, int(i.op_str, 16)))
        return out

    # 1. 0x4096d0: bl > 0x1c の分岐 (表引きを飛ばす) と、そのまま 0x4096b0 へ渡すこと
    f = {i.address: i for i in decode(0x4096D0, 0x409730)}
    check("0x409709: cmp bl,0x1c の後に ja 0x40971b", f[0x409709].mnemonic == "ja" and f[0x409709].op_str == "0x40971b")
    check("0x40971b: rcx = bl を 0x4096b0 へ渡す", f[0x40971B].mnemonic == "movzx" and f[0x409722].op_str == "0x4096b0")

    # 2. 0x4096b0 → 0x412a40 → 0x4128b0 の連鎖
    check("0x4096b0 は 0x412a40 を呼ぶ", (0x4096BB, 0x412A40) in calls(0x4096B0, 0x4096C5))
    check("0x412a40 は 0x4128b0 を呼ぶ", (0x412A4A, 0x4128B0) in calls(0x412A40, 0x412A54))

    # 3. 0x412a40 の ecx 保存先 G と、0x4128b0 末尾で読む先が同じ G (exit code)
    store = decode(0x412A44, 0x412A4A)[0]
    g_store = rip_ea(store)
    load = [i for i in decode(0x412A07, 0x412A0D) if i.mnemonic == "mov"][0]
    g_load = rip_ea(load)
    check("0x412a44: ecx を大域 G に保存", store.mnemonic == "mov" and "ecx" in store.op_str and g_store is not None,
          f"G={g_store:#x}" if g_store else "")
    check("0x412a07: 大域 G を ecx へ読む (exit code)", g_load == g_store, f"load={g_load:#x} store={g_store:#x}")

    # 4. その後の ExitProcess 呼び出し
    check("0x406fc0 は kernel32!ExitProcess の thunk", thunk_target(0x406FC0) == "kernel32.dll!ExitProcess")
    check("0x412a0d: ExitProcess(thunk 0x406fc0) を呼ぶ", (0x412A0D, 0x406FC0) in calls(0x4128B0, 0x412A35))

    # 5. 0x4129ed の条件: 大域 G2 != 0 なら exit を飛ばす (無条件ではない)
    jne = decode(0x4129ED, 0x4129F7)[1]
    check("0x4129f5: [G2]!=0 なら 0x412a12 へ飛ぶ (exit を飛ばす)", jne.mnemonic == "jne" and jne.op_str == "0x412a12")

    # 6. 0x4128b0 の範囲内に RaiseException thunk (0x406fd0) の直接 call は無い
    check("0x4128b0: RaiseException thunk (0x406fd0) の直接 call なし",
          all(t != 0x406FD0 for _, t in calls(0x4128B0, 0x412A35)))

    # 7. エピローグ ret (0x412a34) へ入る分岐は 0x4128b0 の範囲内に無い (戻り辺なし)
    jumps_to_epi = [i.address for i in decode(0x4128B0, 0x412A35)
                    if i.mnemonic.startswith("j") and i.op_str.startswith("0x")
                    and 0x412A2D <= int(i.op_str, 16) <= 0x412A34]
    check("0x4128b0: エピローグ 0x412a2d-0x412a34 へ入る分岐なし", not jumps_to_epi, str(jumps_to_epi))

    # 8. 0x459ef0 の呼び出し順 (0x41c820 → 0x448d40 → 0x411e80 → 0x412d60)。戻り値を 0x45c1c0 が使わないことは probe 318 で確認済み
    order = [t for _, t in calls(0x459EF0, 0x459F3B)]
    check("0x459ef0: 呼び出し順 0x41c820→0x448d40→0x411e80→0x412d60",
          order == [0x41C820, 0x448D40, 0x411E80, 0x412D60], " ".join(hex(t) for t in order))

    # 9. 0x41c820 は LoadStringW (user32 thunk 0x407030) を呼ぶ (文字列リソースを作る)
    check("0x407030 は user32!LoadStringW の thunk", thunk_target(0x407030) == "user32.dll!LoadStringW")
    check("0x41c820 は 0x407030 を呼ぶ", (0x41C88A, 0x407030) in calls(0x41C820, 0x41C8B9))

    ok = all(RESULTS)
    print(f"{sum(RESULTS)}/{len(RESULTS)} PASS")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
