#!/usr/bin/env python3
# M2-3/M2-5: Delphi 固有観点 (strategy §5.7) に対応する関数候補の自動抽出 (win64 DLL)。
#
# 入力:  PE32+ x64 DLL + pescan.py の出力 json (.pdata / IAT slot / unwind flags)
# 依存:  pip capstone (x86-64 個別関数 disasm)。
#
# 観点 → 自動候補の抽出基準 (sizes を確認し 人手チェックの前提):
#   SEH_try_finally : .pdata unwind flags に UHANDLER/EHANDLER が立ち、関数内に
#                     実 protect 対象の call を含む小さめ (<=0x100B) 関数。
#                     → Delphi x64 table-based SEH (strategy §5.7 #1)
#   VMT_indirect    : call [reg(+off)] を含み、Delphi VMT class pointer
#                     (P-112 に vmtClassName) を即値/lea で参照する小 (<0x180B) 関数。
#                     → §5.7 #2 (VMT)
#   RTTI_ref        : P-112 (= vmtClassName 保管先) の rip 相対 load など、
#                     RTTI 名面に到達する小 (<0x100B) 関数。 → §5.7 #3
#   FastMM_allocator: 全 .pdata 関数中で caller xref 数が上位かつ小 (<0x60B) の関数。
#                     Delphi RTL のホット内部 entry (アロケータ喉部想定) → §5.7 #4
#                     (この観点のみ「参照数少」の例外を明示して採用している)
#   calling_conv    : 中サイズ (0x40-0x180B)・xref 少 (1-4)・multi-afe 形。 → §5.7 #5
#
# python3 delphi_scan.py --input FLEngine_x64.dll --scan-json work/pe_scan_dll.json \
#   --out work/delphi_candidates.json

import argparse
import json
import re
import struct
import sys

import capstone

BASE = 0x400000  # PE データディレクトリの既定 ImageBase


def die(msg: str):
    print(f"[delphi_scan] FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def cstr(data, off, limit=256):
    if off is None or off <= 0 or off >= len(data):
        return ""
    end = data.find(b"\0", off, off + limit)
    return data[off:end].decode("latin1", "replace")


class PEScan:
    """pescan.py の json に依存する PE primitive 集合。"""

    def __init__(self, path, scan_json):
        self.data = open(path, "rb").read()
        self.scan = json.load(open(scan_json))
        self.sections = self.scan["sections"]
        if not self.scan.get("pdata"):
            die("pescan json に pdata がありません (pescan.py を先に走らせてください)")
        self.pdata = self.scan["pdata"]
        self.iat = self._load_slots("iat_slots")
        self.iat_delay = self._load_slots("iat_delay_slots")
        self.vmts, self.class_of = self._scan_vmts()
        self.name_storage = self._scan_name_storage()
        # class pointer P は RVA. コード即値 (mov reg, imm64) は VA (RVA+BASE)
        # で入るため、VA 側辞書も併設する (参照窓出しの呼出 hv)。
        self.class_of_va = {P + BASE: nm for P, nm in self.class_of.items()}
        self.name_storage_va = {k + BASE: v for k, v in self.name_storage.items()}

    def file_off(self, rva):
        for s in self.sections:
            if s["raw_size"] and s["vaddr"] <= rva < s["vaddr"] + s["vsize"]:
                o = rva - s["vaddr"]
                if o < s["raw_size"]:
                    return s["raw_ptr"] + o
        return None

    def _load_slots(self, key):
        out = {}
        for k, v in self.scan.get(key, {}).items():
            out[int(k, 16)] = (v[0], v[1])
        return out

    def _scan_vmts(self):
        """Delphi VMT: vmtClassName (-112, x64) を P-112 に検出し、
        class pointer P を採取する (P の集合)。 routine は .data 上 raw 値を scan。"""
        data = self.data
        pat = re.compile(rb"\x00([\x01-\x30])([A-Z][A-Za-z0-9_]{2,63})\x00")
        name_by_rva = {}
        for m in pat.finditer(data):
            L = m.group(1)[0]
            nm = m.group(2).decode("latin1")
            if L == len(nm):
                fo = m.start(2) - 1
                r = self.rva_of(fo)
                if r is not None:
                    name_by_rva[r] = nm
        dsecs = [s for s in self.sections if s["name"] in (".data", ".text")]
        vmts = []
        class_of = {}
        seen = set()
        for dsec in dsecs:
            raw = data[dsec["raw_ptr"]: dsec["raw_ptr"] + dsec["raw_size"]]
            for o in range(0, len(raw) - 8, 4):
                v = struct.unpack("<Q", raw[o:o + 8])[0]
                if v - BASE in name_by_rva:
                    a = dsec["vaddr"] + o           # vmtClassName を保管するアドレス (P-112)
                    P = a + 112                     # class pointer (Delphi x64 定数 -112 相対)
                    if P not in seen:
                        seen.add(P)
                        nm = name_by_rva[v - BASE]
                        vmts.append((P, nm))
                        class_of[P] = nm
        return vmts, class_of

    def _scan_name_storage(self):
        """vmtClassName の「保管先アドレス」(P-112) を採取 (rip 相対 load 判定用)。"""
        return {P - 112: nm for P, nm in self.vmts}

    def rva_of(self, off):
        for s in self.sections:
            if s["raw_ptr"] <= off < s["raw_ptr"] + s["raw_size"]:
                return s["vaddr"] + (off - s["raw_ptr"])
        return None


def rip_target(ins, operand):
    """capstone operand (mem, base==RIP) → target RVA (RVA 座標で disasm 済)。"""
    return ins.address + ins.size + operand.mem.disp


def disassemble(pe, pdata):
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    funcs = []
    for e in pdata:
        b, en = e["begin"], e["end"]
        size = en - b
        if size <= 0 or size > 0x10000:
            continue
        off = pe.file_off(b)
        if off is None:
            continue
        code = pe.data[off: off + size]
        insns = list(md.disasm(code, b))
        funcs.append({
            "begin": b, "end": en, "size": size, "unwind": e["unwind"],
            "flag": e.get("flag", "none"), "insns": insns,
        })
    return funcs


def feature_pass(pe, funcs):
    entry_set = {f["begin"] for f in funcs}
    xref = {}
    feat = {}
    for f in funcs:
        ft = {
            "indirect_calls": 0,   # call [reg] / call [mem]
            "direct_calls": 0,
            "target_calls": [],    # (target rva, internal/external label)
            "import_calls": [],    # (dll, name)
            "vmt_refs": [],        # class pointer を参照する場所 (rodata 相対)
            "name_storage_refs": [],
            "n_insns": len(f["insns"]),
        }
        for ins in f["insns"]:
            ops = ins.operands
            if ins.mnemonic in ("call", "jmp") and ops and ops[0].type == capstone.x86.X86_OP_IMM:
                tgt = ops[0].imm
                if tgt in entry_set:
                    xref[tgt] = xref.get(tgt, 0) + 1
                    ft["target_calls"].append(hex(tgt))
                ft["direct_calls"] += 1
            elif ins.mnemonic in ("call",) and ops and ops[0].type == capstone.x86.X86_OP_MEM:
                mem = ops[0].mem
                if mem.base == capstone.x86.X86_REG_RIP:
                    t = rip_target(ins, ops[0])
                    if t in pe.iat:
                        ft["import_calls"].append(list(pe.iat[t]))
                    elif t in pe.iat_delay:
                        ft["import_calls"].append(list(pe.iat_delay[t]))
                else:
                    ft["indirect_calls"] += 1
            elif ins.mnemonic in ("call",) and ops and ops[0].type == capstone.x86.X86_OP_REG:
                # register 経由の間接 call (VMT / function pointer 型)
                ft["indirect_calls"] += 1
            elif ins.mnemonic in ("mov", "movabs", "lea", "cmp", "test", "movzx",
                                  "add", "or", "and"):
                for op in ops:
                    if op.type == capstone.x86.X86_OP_IMM and (
                            op.imm in pe.class_of or op.imm in pe.class_of_va):
                        ft["vmt_refs"].append(hex(op.imm if op.imm in pe.class_of
                                                  else op.imm - BASE))
                    elif op.type == capstone.x86.X86_OP_MEM and \
                            op.mem.base == capstone.x86.X86_REG_RIP:
                        t = rip_target(ins, op)
                        if t in pe.class_of:
                            ft["vmt_refs"].append(hex(t))
                        if t in pe.name_storage:
                            ft["name_storage_refs"].append(hex(t))
        feat[f["begin"]] = ft
    return feat, xref


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--scan-json", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    pe = PEScan(args.input, args.scan_json)
    print(f"[delphi_scan] exports are Delphi 定形: {len(pe.scan.get('exports', {}))}")
    print(f"[delphi_scan] VMT class pointers: {len(pe.vmts)}")

    funcs = disassemble(pe, pe.pdata)
    print(f"[delphi_scan] functions disassembled: {len(funcs)}")
    feat, xref = feature_pass(pe, funcs)

    by = {f["begin"]: f for f in funcs}
    cands = {}

    # ---- 1) SEH / try-finally ------------------------------------
    seh = []
    for f in funcs:
        if f["flag"] in ("UHANDLER", "EHANDLER,UHANDLER", "EHANDLER"):
            ft = feat[f["begin"]]
            if f["size"] <= 0x100 and ft["direct_calls"] >= 1 and \
                    len(ft["target_calls"]) >= 1 and xref.get(f["begin"], 0) <= 6:
                seh.append(f["begin"])
        if len(seh) >= 6:
            break
    cands["SEH_try_finally"] = sorted(seh, key=lambda b: by[b]["size"])[:5]

    # ---- 2) VMT 間接 call ----------------------------------------
    # Delphi 仮想 dispatch: instance → [reg] で VMT ロード → call [reg+off]。
    # 「VMT ロード相当 ([reg]) load」と「call [reg+disp] (disp>0)」の両方を含む小関数。
    vmt_c = []
    for f in funcs:
        if f["size"] <= 0x180:
            has_call_disp = any(
                i.mnemonic == "call" and i.operands and
                i.operands[0].type == capstone.x86.X86_OP_MEM and
                i.operands[0].mem.base not in (capstone.x86.X86_REG_RIP,) and
                i.operands[0].mem.disp != 0
                for i in f["insns"])
            has_vmt_load = any(
                i.mnemonic in ("mov", "movzx") and i.operands and
                i.operands[0].type == capstone.x86.X86_OP_MEM and
                i.operands[0].mem.base not in (capstone.x86.X86_REG_RIP,) and
                i.operands[0].mem.disp == 0
                for i in f["insns"])
            if has_call_disp and has_vmt_load:
                n_x = xref.get(f["begin"], 0)
                vmt_c.append((f["begin"], f["size"], n_x))
    vmt_c.sort(key=lambda t: (t[1], t[2], t[0]))
    cands["VMT_indirect"] = [b for b, _s, _x in vmt_c[:5]]

    # ---- 3) RTTI / VMT fixed field 参照 --------------------------
    # Delphi x64 VMT fixed 部は class pointer からの負固定 offset
    # (vmtClassName = -112 (0x70) 等, mac/REPORT.md §2 記載値)。
    # コード側は [reg-0x??] 形でこれらを読む → 負 disp mem read を含む小関数。
    rtti_c = []
    RTTI_DISPS = {-0x70, -0x78, -0x80, -0x88, -0x90, -0x98, -0xa0, -0xa8}
    rtti_hits = {}
    for f in funcs:
        if 0x18 <= f["size"] <= 0x100:
            hit = None
            for i in f["insns"]:
                if i.mnemonic in ("mov", "movzx", "cmp", "test", "lea") and i.operands:
                    for op in i.operands:
                        if op.type == capstone.x86.X86_OP_MEM and \
                                op.mem.base not in (capstone.x86.X86_REG_RIP,) and \
                                op.mem.disp in RTTI_DISPS:
                            hit = (i.mnemonic, i.op_str)
                            break
                if hit:
                    break
            if hit and xref.get(f["begin"], 0) <= 6:
                rtti_c.append((f["begin"], f["size"], hit))
        if len(rtti_c) > 400:
            break
    rtti_c.sort(key=lambda t: (t[1], t[0]))
    for b, _s, h in rtti_c[:5]:
        rtti_hits[hex(b)] = h
    cands["RTTI_VMTfield"] = [b for b, _s, _h in rtti_c[:5]]

    # ---- 4) FastMM / RTL ホット entry ----------------------------
    # (呼出元多数 = FastMM/RTL 内部 entry; 「参照数少」の例外を明示して採用)
    top = sorted(xref.items(), key=lambda kv: -kv[1])
    fast = [(b, by[b]["size"], n) for b, n in top
            if b in by and by[b]["size"] <= 0x60]
    fast.sort(key=lambda t: (-t[2], t[1]))
    cands["FastMM_allocator"] = [b for b, _s, _n in fast[:5]]

    # ---- 5) calling convention / multi-arg -----------------------
    cconv = []
    for f in funcs:
        if 0x50 <= f["size"] <= 0x180:
            n_x = xref.get(f["begin"], 0)
            if 1 <= n_x <= 4:
                fp = None
                for ins in f["insns"][:10]:
                    if ins.mnemonic in ("mov", "lea", "cmp", "test", "add", "movzx") and \
                            ins.op_str.startswith(("qword ptr", "r")):
                        pass
                cconv.append((f["begin"], f["size"], n_x))
        if len(cconv) > 200:
            break
    cconv.sort(key=lambda t: (t[1], t[2], t[0]))
    cands["calling_convention"] = [b for b, _s, _x in cconv[:5]]

    detail = {}
    for k, lst in cands.items():
        detail[k] = []
        for b in lst:
            f = by[b]
            ft = feat[b]
            detail[k].append({
                "begin": hex(b), "end": hex(f["end"]), "size": f["size"],
                "unwind_flag": f["flag"],
                "n_insns": ft["n_insns"],
                "direct_calls": ft["direct_calls"],
                "indirect_calls": ft["indirect_calls"],
                "target_calls": ft["target_calls"][:8],
                "import_calls": ft["import_calls"][:8],
                "vmt_refs": ft["vmt_refs"][:8],
                "name_storage_refs": ft["name_storage_refs"][:8],
                "caller_xrefs": xref.get(b, 0),
            })

    # vmt_refs のアドレスから class 名も併記する (RTTI/VMT 候補の妥当性記録用)
    for k, lst in detail.items():
        for d in lst:
            cn = []
            for r in d.get("vmt_refs", [])[:8]:
                p = int(r, 16)
                if p in pe.class_of:
                    cn.append(pe.class_of[p])
            d["class_names"] = cn[:8]

    out = {
        "input": args.input,
        "functions": len(funcs),
        "vmt_class_pointers": len(pe.vmts),
        "vmt_examples": [{"class_ptr": hex(P), "name": nm}
                         for P, nm in pe.vmts[:40]],
        "unwind_flag_summary": pe.scan.get("unwind_flag_summary"),
        "xref_top": [{"target": hex(t), "count": n, "size": by[t]["size"]
                      if t in by else None}
                     for t, n in sorted(xref.items(), key=lambda kv: -kv[1])[:30]],
        "candidates": {k: [hex(b) for b in v] for k, v in cands.items()},
        "rtti_hits": rtti_hits,
        "candidates_detail": detail,
    }
    with open(args.out, "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print("[delphi_scan] candidates:", {k: [hex(x) for x in v] for k, v in cands.items()})
    print(f"[delphi_scan] wrote {args.out}")


if __name__ == "__main__":
    main()
