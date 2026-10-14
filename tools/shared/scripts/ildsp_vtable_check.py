#!/usr/bin/env python3
"""ildsp_vtable.py の出力 (JSON) を、生バイトだけで読み直して照合する検算。

usage: ildsp_vtable_check.py <json> [--pe <PE>]
  既定 PE: JSON の "pe" フィールド。
方式が別: pefile / capstone を使わず、PE ヘッダを struct で読み、命令は固定バイト列
(lea rip / mov rcx,[rcx+8]; jmp rel32 / xor eax,eax; ret / call rel32 / call [rip+disp32]) で照合する。
全件一致で ALL OK (exit 0)。1 件でも不一致なら FAIL を列挙して exit 1。
"""
import sys, os, json, struct, hashlib, argparse

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json")
    ap.add_argument("--pe", default=None)
    a = ap.parse_args()
    J = json.load(open(a.json))
    pe_path = a.pe or J["pe"]
    raw = open(pe_path, "rb").read()

    check(hashlib.sha256(raw).hexdigest() == J["pe_sha256"], "pe_sha256 が一致しない (別ファイルの JSON)")

    # --- PE ヘッダを生バイトで読む
    lfanew = struct.unpack_from("<I", raw, 0x3C)[0]
    check(raw[lfanew:lfanew + 4] == b"PE\0\0", "PE signature")
    nsec = struct.unpack_from("<H", raw, lfanew + 6)[0]
    optsz = struct.unpack_from("<H", raw, lfanew + 20)[0]
    opt = lfanew + 24
    base = struct.unpack_from("<Q", raw, opt + 24)[0]
    check(hex(base) == J["image_base"], f"image_base {hex(base)} != {J['image_base']}")
    secs = []
    for k in range(nsec):
        o = opt + optsz + 40 * k
        name = raw[o:o + 8].rstrip(b"\0").decode()
        vsz, va, rsz, rptr = struct.unpack_from("<IIII", raw, o + 8)
        secs.append((name, va, max(vsz, rsz), rptr, vsz))
    text = [s for s in secs if s[0] == ".text"][0]
    t_lo, t_hi = text[1], text[1] + text[4]
    check(hex(t_lo) == J["text"]["lo"] and hex(t_hi) == J["text"]["hi"], ".text 範囲が一致しない")

    def off(rva):
        for _, va, sz, ptr, _ in secs:
            if va <= rva < va + sz:
                return rva - va + ptr
        raise KeyError(hex(rva))

    def u64(rva):
        return struct.unpack_from("<Q", raw, off(rva))[0]

    def bytes_at(rva, n):
        return raw[off(rva):off(rva) + n]

    def rel_target(site, n_prefix, n_total):
        """site から n_prefix バイト後の rel32 の宛先 (次命令は site+n_total)。"""
        rel = struct.unpack_from("<i", raw, off(site + n_prefix))[0]
        return site + n_total + rel

    # --- 1. CreateInstance の vptr 格納 lea
    ci = J["create_instance"]
    lea = int(ci["vptr_lea_at"], 16)
    b = bytes_at(lea, 7)
    check(b[:3] == bytes.fromhex("488d05"), f"CreateInstance の lea 命令でない: {b.hex()}")
    check(b.hex() == ci["vptr_lea_bytes"], "vptr_lea_bytes が生バイトと一致しない")
    check(rel_target(lea, 3, 7) == int(ci["vptr_target_rva"], 16), "lea の RIP 相対先が vptr_target_rva と一致しない")
    check(bytes_at(lea + 7, 3) == bytes.fromhex("488907"), "lea の直後が mov [rdi],rax でない (vptr 格納でない)")

    # --- 2. vtable
    V = J["vtable"]
    VT = int(V["rva"], 16)
    check(V["rva"] == ci["vptr_target_rva"], "vtable.rva と vptr_target_rva が不一致")
    n = V["slot_count"]
    check(n == len(V["slots"]) == 6, f"slot 数 {n} (期待 6)")
    for k in range(n):
        v = u64(VT + 8 * k)
        check(v - base == int(V["slots"][k]["target_rva"], 16), f"slot {k}: 生バイトの値 {hex(v)} が JSON と不一致")
        check(t_lo <= v - base < t_hi, f"slot {k}: .text を指さない")
    end_v = u64(VT + 8 * n)
    check(hex(end_v) == V["end_value_va"], "slot 終端の値が JSON と不一致")
    check(not (t_lo <= end_v - base < t_hi), "slot 終端が .text を指す (vtable 長が 6 で終わらない)")
    check(V["end_in_text"] is False, "end_in_text フラグ不一致")

    # --- 3. slot 種別ごとの生バイト照合
    for s in V["slots"]:
        t = int(s["target_rva"], 16)
        k = s["index"]
        if s["kind"] == "thunk_inner":
            b = bytes_at(t, 9)
            check(b[:4] == bytes.fromhex("488b4908") and b[4] == 0xE9,
                  f"slot {k}: thunk の生バイトが mov rcx,[rcx+8]; jmp rel32 でない: {b.hex()}")
            check(hex(rel_target(t, 5, 9)) == s["thunk_target"], f"slot {k}: thunk の jmp 先が JSON と不一致")
        elif s["kind"] == "const_ret0":
            check(bytes_at(t, 3) in (bytes.fromhex("31c0c3"), bytes.fromhex("33c0c3")),
                  f"slot {k}: 定数返しの生バイトが xor eax,eax; ret でない")
        elif s["kind"] == "function":
            # 範囲内の全 e8 を生バイトで走査し、JSON の call 箇所と照合する (走査の偽陽性は lea 等の変位に E8 が入る場合のみ)
            lo, hi = int(s["ranges"][0][0], 16), int(s["ranges"][-1][1], 16)
            scan = set()
            for x in range(lo, hi - 4):
                if raw[off(x)] == 0xE8:
                    tgt = rel_target(x, 1, 5)
                    if t_lo <= tgt < t_hi:
                        scan.add((hex(x), hex(tgt)))
            js = {(c["site"], c["target"]) for c in s["calls"] if c["target"]}
            check(js <= scan, f"slot {k}: JSON の call 箇所が生バイト走査で見つからない {sorted(js - scan)[:3]}")
            check(len(scan) == len(js), f"slot {k}: 生バイト走査の call 数 {len(scan)} と JSON {len(js)} が不一致")
            if s["stores_vptr"]:
                # dtor の指紋: 解放 helper 0x1ac9b0 へ rdx=0x2f8 (内部オブジェクト) と rdx=0x10 (ラッパ) の 2 回の sized 呼出し
                for sz in ("0x2f8", "0x10"):
                    imm = struct.pack("<I", int(sz, 16))
                    found = False
                    for x in range(lo, hi - 5):
                        if raw[off(x):off(x) + 5] == b"\xba" + imm:
                            found = any(raw[off(y)] == 0xE8 and rel_target(y, 1, 5) == 0x1AC9B0
                                        for y in range(x + 5, min(hi, x + 16)))
                            if found:
                                break
                    check(found, f"slot {k}: mov edx,{sz} の直後に 0x1ac9b0 への call が無い")
                for ref in s["stores_vptr"]:
                    x = int(ref, 16)
                    check(bytes_at(x, 3) == bytes.fromhex("488d05") and rel_target(x, 3, 7) == VT,
                          f"slot {k}: stores_vptr {ref} が vtable への lea でない")
        else:
            fails.append(f"slot {k}: 未知の kind {s['kind']}")

    # --- 4. closure: JSON が挙げた直接 call を生バイトで再確認し、closure 集合に閉じているかを見る
    for key in ("closure_create_only", "closure_with_slots"):
        cl = J[key]
        starts = {int(f["start"], 16) for f in cl["function_starts"]}
        check(len(starts) == cl["functions"], f"{key}: 関数数の不一致")
        for site, tgt in cl["direct_call_sites"]:
            x = int(site, 16)
            check(raw[off(x)] == 0xE8 and rel_target(x, 1, 5) == int(tgt, 16),
                  f"{key}: 直接 call {site} の生バイトが {tgt} を指さない")
            check(int(tgt, 16) in starts or any(
                int(r[0], 16) <= int(tgt, 16) < int(r[1], 16) for f in cl["function_starts"] for r in f["ranges"]),
                f"{key}: 直接 call {site} -> {tgt} が closure に無い")
        # 参考値: 関数範囲内の生バイト e8 のうち宛先が closure 外の .text 関数 (逆アセンブル由来の JSON と突き合わせる。偽陽性を含みうる)
        ext = []
        for f in cl["function_starts"]:
            for r in f["ranges"]:
                lo, hi = int(r[0], 16), int(r[1], 16)
                for x in range(lo, hi - 4):
                    if raw[off(x)] == 0xE8:
                        tgt = rel_target(x, 1, 5)
                        if t_lo <= tgt < t_hi and tgt not in starts:
                            ext.append((hex(x), hex(tgt)))
        print(f"[{key}] 参考: 生バイト e8 の closure 外宛先 = {len(ext)} 件 {ext[:4]}")

    # --- 5. 間接 call / jmp の宛先スロット (rip 相対) を生バイトで確認
    for key in ("closure_create_only", "closure_with_slots"):
        for c in J[key]["indirect_calls"]:
            x = int(c["site"], 16)
            check(raw[off(x):off(x) + 2] == b"\xff\x15", f"{key}: 間接 call {c['site']} が call [rip+disp] でない")
            slot = rel_target(x, 2, 6)
            check(hex(slot) == c["slot_rva"], f"{key}: 間接 call {c['site']} のスロット RVA 不一致")
            check(hex(u64(slot)) == c["slot_file_value"], f"{key}: 間接 call {c['site']} のスロット値不一致")

    if fails:
        for m in fails:
            print("FAIL", m)
        print(f"ildsp_vtable_check: FAIL {len(fails)} 件")
        sys.exit(1)
    print("ildsp_vtable_check: ALL OK")


if __name__ == "__main__":
    main()
