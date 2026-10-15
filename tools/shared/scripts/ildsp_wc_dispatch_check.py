#!/usr/bin/env python3
"""ildsp_wc_dispatch.py の結果 (JSON) を、別アルゴリズムで検算する。

usage: ildsp_wc_dispatch_check.py <json> [PE]
  検算の方法 (ildsp_wc_dispatch.py と共有するのは JSON と PE のパスだけ):
  1. GNU objdump で、vptr 格納 (0x1ac4b4)・vcall (0x1a9e2b)・vcall 直前の this 読み (0x1a9e16) の命令文字列を読む。
  2. PE ヘッダ・セクション表・基底再配置 (.reloc) を struct で生バイト読みし、
     vtable の各 slot の値 (VA - ImageBase) と DIR64 reloc の有無を照合する。
  3. JSON の vcall の target が、生バイトで読んだ slot の値と一致することを確認する。
  出力: ALL OK で exit 0。不一致は MISMATCH を出して exit 1。
"""
import sys, os, re, json, struct, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
from paths import FL_WIN64_DIR

EXPECT_STORE = (0x1ac4b4, "mov", "%rax,(%rcx)")
EXPECT_THIS = (0x1a9e16, "mov", "(%rcx),%rax")
EXPECT_VCALL = (0x1a9e2b, "call", "*0x18(%rax)")
EXPECT_SLOT_FN = (0x1a9de0, "lea", "0x20(%rcx),%rax")


def objdump_at(pe, va):
    out = subprocess.run(["objdump", "-d", "--no-show-raw-insn", f"--start-address={hex(va)}",
                          f"--stop-address={hex(va + 16)}", pe], capture_output=True, text=True).stdout
    for line in out.splitlines():
        m = re.match(r"\s*([0-9a-f]+):\t(\S+)\s*(.*)$", line)
        if m and int(m.group(1), 16) == va:
            return m.group(2), m.group(3).strip()
    return None, None


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    js = json.load(open(sys.argv[1]))
    pe = sys.argv[2] if len(sys.argv) > 2 else os.path.join(FL_WIN64_DIR, "extracted", "block24360_PE.bin")
    raw = open(pe, "rb").read()

    pe_off = struct.unpack_from("<I", raw, 0x3c)[0]
    assert raw[pe_off:pe_off + 4] == b"PE\0\0"
    n_sec, = struct.unpack_from("<H", raw, pe_off + 6)
    opt_size, = struct.unpack_from("<H", raw, pe_off + 20)
    opt = pe_off + 24
    assert struct.unpack_from("<H", raw, opt)[0] == 0x20B, "PE32+ 前提"
    image_base, = struct.unpack_from("<Q", raw, opt + 24)
    dd_base = opt + 112
    reloc_rva, reloc_size = struct.unpack_from("<II", raw, dd_base + 5 * 8)
    secs = []
    for i in range(n_sec):
        o = opt + opt_size + 40 * i
        vsize, va, rsize, rptr = struct.unpack_from("<IIII", raw, o + 8)
        secs.append((va, max(vsize, rsize), rptr))

    def off_of(rva):
        for va, sz, ptr in secs:
            if va <= rva < va + sz:
                return ptr + (rva - va)
        raise ValueError(hex(rva))

    def reloc_has(rva):
        page_rva = rva & ~0xFFF
        o = off_of(reloc_rva)
        end = o + reloc_size
        while o < end:
            pg, bsz = struct.unpack_from("<II", raw, o)
            for k in range(8, bsz, 2):
                e, = struct.unpack_from("<H", raw, o + k)
                if pg == page_rva and (e >> 12) == 10 and (e & 0xFFF) == (rva & 0xFFF):
                    return True
            o += bsz
        return False

    bad = []
    vc = js["vcalls"][0]
    vt = int(js["vt_rva"], 16)
    slot_rva = int(vc["slot_rva"], 16)
    target = int(vc["target_rva"], 16)

    for va, want in ((EXPECT_STORE[0], EXPECT_STORE), (EXPECT_THIS[0], EXPECT_THIS),
                     (EXPECT_VCALL[0], EXPECT_VCALL), (EXPECT_SLOT_FN[0], EXPECT_SLOT_FN)):
        mn, ops = objdump_at(pe, image_base + va)
        ok = mn == want[1] and ops.startswith(want[2])
        print(f"[objdump] {hex(va)}: {mn} {ops} -> {'OK' if ok else 'MISMATCH'}")
        if not ok:
            bad.append(hex(va))

    raw_slot_va, = struct.unpack_from("<Q", raw, off_of(slot_rva))
    raw_target = raw_slot_va - image_base
    ok_t = raw_target == target == 0x1A9DE0
    print(f"[raw] vtable {hex(vt)} slot {vc['slot']} (RVA {hex(slot_rva)}) = {hex(raw_target)} / JSON {hex(target)} -> {'OK' if ok_t else 'MISMATCH'}")
    if not ok_t:
        bad.append("slot")

    ok_r = reloc_has(slot_rva)
    print(f"[reloc] DIR64 reloc at slot RVA {hex(slot_rva)}: {'present' if ok_r else 'absent'} -> {'OK' if ok_r else 'MISMATCH'}")
    if not ok_r:
        bad.append("reloc")

    ok_store = len(js["stores"]) == 1 and js["stores"][0]["vtable"] == hex(vt)
    print(f"[store] WC vtable を書く箇所 = {len(js['stores'])} (JSON) / vtable {js['stores'][0]['vtable'] if js['stores'] else None} -> {'OK' if ok_store else 'MISMATCH'}")
    if not ok_store:
        bad.append("store")

    if bad:
        print("MISMATCH:", ", ".join(bad))
        sys.exit(1)
    print("ALL OK")


if __name__ == "__main__":
    main()
