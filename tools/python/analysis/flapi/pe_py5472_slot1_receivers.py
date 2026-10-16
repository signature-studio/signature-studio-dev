#!/usr/bin/env python3
"""PY-5472 (#5472): 格納配列 [map+8] の読出しと slot 1 呼出しの receiver 経路を、逆アセ行の完全一致で固定する
(解析補助。REPORT_PY275.md §7)。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py5472_slot1_receivers.py

展開: tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'

本 probe が確定するのは「slot 1 の receiver が読出し値と別の式で取られている」という静的事実だけ。
読出し値と receiver が実行時に同じオブジェクトかは確定しない (REPORT §7 の未解決表)。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pe_callgraph as pc  # noqa: E402

# (VA, 期待する逆アセ文字列 (capstone の mnemonic + op_str))
EXPECT = [
    # 0xc3b930: 読出し 0xc3b9fd -> [rbp+0x78]。slot 1 の receiver は [rbp+0x98] = [[rbp+0xd0]+0x10]
    (0xC3B9FD, "mov rax, qword ptr [rcx + rax*8 + 8]"),
    (0xC3BA02, "mov qword ptr [rbp + 0x78], rax"),
    (0xC3BB16, "mov qword ptr [rbp + 0x98], rax"),
    (0xC3BB2B, "mov rbx, qword ptr [rax]"),
    (0xC3BB2E, "call qword ptr [rbx + 8]"),
    # 0xc3bc00: 読出し 0xc3bcb4 -> [rbp+0x60]。slot 1 の receiver は [rbp+0x78] = [[rbp+0xa0]+0x10]
    (0xC3BCB4, "mov rax, qword ptr [rcx + rax*8 + 8]"),
    (0xC3BCB9, "mov qword ptr [rbp + 0x60], rax"),
    (0xC3BD89, "mov qword ptr [rbp + 0x78], rax"),
    (0xC3BD95, "mov rbx, qword ptr [rax]"),
    (0xC3BD98, "call qword ptr [rbx + 8]"),
    (0xC3BDD4, "mov qword ptr [rdx + 0x78], rax"),
    (0xC3BDE0, "mov rbx, qword ptr [rax]"),
    (0xC3BDE3, "call qword ptr [rbx + 8]"),
    # 0xd328f0: 読出し 0xd329b2 (rcx) / 0xd32a32 / 0xd32a94 / 0xd32b50。slot 1 の receiver は [rbp+0x78] = [[rbp+0xe0]+0xb0]
    (0xD32B6C, "mov rax, qword ptr [rbp + 0xe0]"),
    (0xD32B73, "mov rax, qword ptr [rax + 0xb0]"),
    (0xD32B7A, "mov qword ptr [rbp + 0x78], rax"),
    (0xD32B86, "mov rbx, qword ptr [rax]"),
    (0xD32B89, "call qword ptr [rbx + 8]"),
    # 0x1046a30: 読出し 0x104ab4a -> [rbp+0x508]。slot 1 の receiver は [rip+x] 由来のグローバル
    (0x104AB4A, "mov rax, qword ptr [rax + rcx*8 + 8]"),
    (0x104AB4F, "mov qword ptr [rbp + 0x508], rax"),
    (0x104861E, "mov rax, qword ptr [rax]"),
    (0x1048621, "mov rax, qword ptr [rax + 0x5c]"),
    (0x1048633, "mov rbx, qword ptr [rax]"),
    (0x1048636, "call qword ptr [rbx + 8]"),
    (0x104B56E, "mov rax, qword ptr [rax + 0x5c]"),
    (0x104B580, "mov rbx, qword ptr [rax]"),
    (0x104B583, "call qword ptr [rbx + 8]"),
    # 0x1046a30: [rbp+0x508] を receiver とする間接 call は offset 0x1f0 (slot 1 ではない)
    (0x104AD81, "call qword ptr [rbx + 0x1f0]"),
]
FAILS = []


def main():
    insns = pc.load()
    got = {a: f"{m} {o}".strip() for a, m, o in insns}
    for va, want in EXPECT:
        have = got.get(va)
        ok = have == want
        print(("PASS " if ok else "FAIL ") + f"{hex(va)} :: {have}")
        if not ok:
            FAILS.append(hex(va))
    stores_508 = [hex(a) for a, m, o in insns
                  if 0x1046A30 <= a < 0x104CF90 and m == "mov" and o.startswith("qword ptr [rbp + 0x508],")]
    ok = stores_508 == ["0x104ab4f"]
    print(("PASS " if ok else "FAIL ") + f"0x1046a30 内の [rbp+0x508] への格納は 0x104ab4f の 1 件 :: {stores_508}")
    if not ok:
        FAILS.append("508")
    print(f"\nsummary: {'ALL PASS' if not FAILS else 'FAIL: ' + ', '.join(FAILS)}")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
