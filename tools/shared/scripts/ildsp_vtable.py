#!/usr/bin/env python3
"""ildsp (block24360_PE.bin, win64 PE) の GeneralPitchShifter_CreateInstance が返す instance の vtable を静的に抽出する。

usage: ildsp_vtable.py [PE] [--out <json>]
  既定 PE: $FL_WIN64_DIR/extracted/block24360_PE.bin (tools/shared/paths.py)
  既定 out: tools/shared/work/raw/ildsp_vtable.json (gitignore)
  検算: ildsp_vtable_check.py <json> (生バイトだけで読み直す別実装)
  --seed: 追加で、指定した RVA (16 進、カンマ区切り) だけから辿った closure を出す (例: 0x161fc0)

出力 (事実のみ。各 slot の役割の判定は tools/shared/lift/ildsp/REPORT.md §4):
  1. CreateInstance (RVA 0x1aa290) の vptr 格納 lea の RIP 相対先 = vtable RVA
  2. vtable の slot 列。値が .text を指す間を数え、最初の非 .text 値で止める
  3. 各 slot の分類 (thunk: `mov rcx,[rcx+8]` + 直接 jmp / 定数返し: `xor eax,eax; ret` / 他は関数)
  4. closure: CreateInstance 単独と、CreateInstance + 全 slot の先 の 2 種。
     直接 call・関数外への直接 jmp を辿る。関数範囲は .pdata。.pdata に無い葉関数は
     「int3 の並びまでの線形走査」で範囲を決める (mode=scan)。間接 call / jmp の箇所を全件列挙する。
"""
import sys, os, json, argparse, struct, bisect, hashlib, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
from paths import FL_WIN64_DIR
import pefile, capstone
ROOT = os.path.dirname(HERE)

CREATE_RVA = 0x1aa290
MAX_SLOTS = 16


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pe", nargs="?", default=os.path.join(FL_WIN64_DIR, "extracted", "block24360_PE.bin"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work", "raw", "ildsp_vtable.json"))
    ap.add_argument("--seed", default="")
    a = ap.parse_args()

    raw = open(a.pe, "rb").read()
    pe = pefile.PE(a.pe, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    img = pe.get_memory_mapped_image()
    base = pe.OPTIONAL_HEADER.ImageBase
    secs = {s.Name.rstrip(b"\0").decode(errors="replace"): s for s in pe.sections}
    text = secs[".text"]
    t_lo, t_hi = text.VirtualAddress, text.VirtualAddress + text.Misc_VirtualSize

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = False

    exc = pe.OPTIONAL_HEADER.DATA_DIRECTORY[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXCEPTION"]]
    funcs = {}
    for i in range(exc.Size // 12):
        b, e, u = struct.unpack_from("<III", img, exc.VirtualAddress + i * 12)
        funcs[b] = (e, u)
    fn_sorted = sorted(funcs)

    # chained な .pdata (UNWIND_INFO の CHAININFO) は親 (primary) の範囲に束ねる。1 関数 = 複数チャンク
    def primary_of(b):
        e, u = funcs[b]
        flags, codes = img[u] >> 3, img[u + 2]
        if flags & 4:
            return struct.unpack_from("<III", img, u + 4 + 2 * ((codes + 1) & ~1))[0]
        return b

    groups = collections.defaultdict(list)
    for b in fn_sorted:
        groups[primary_of(b)].append((b, funcs[b][0]))

    iat = {}
    for imp_dll in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
        for imp in imp_dll.imports:
            iat[imp.address - base] = f"{imp_dll.dll.decode()}!{(imp.name or b'').decode() or '#' + str(imp.ordinal)}"

    def ind_info(ins):
        """`call/jmp qword ptr [rip + disp32]` の IAT スロット RVA と import 名。"""
        if "[rip" not in ins.op_str:
            return {}
        disp = struct.unpack_from("<i", bytes(ins.bytes), len(ins.bytes) - 4)[0]
        slot = ins.address + ins.size + disp
        return {"slot_rva": hex(slot), "slot_file_value": hex(struct.unpack_from("<Q", img, slot)[0]),
                "import": iat.get(slot)}

    def owner(t):
        """t を含む .pdata チャンクの primary (無ければ None)。"""
        i = bisect.bisect_right(fn_sorted, t) - 1
        if i >= 0 and fn_sorted[i] <= t < funcs[fn_sorted[i]][0]:
            return primary_of(fn_sorted[i])
        return None

    def sweep_until(lo, hi):
        """[lo, hi) の線形走査。hi 指定が None なら int3 並びの直前 (ret / 無条件 jmp の直後が int3) まで。"""
        out, off = [], lo
        while off < (hi if hi is not None else t_hi):
            ins = next(md.disasm(bytes(img[off:off + 16]), off), None)
            if ins is None:
                off += 1
                continue
            out.append(ins)
            off += ins.size
            if hi is None and ins.mnemonic in ("ret", "jmp") and img[off] == 0xCC:
                break
        return out

    def body(entry):
        """(開始, 範囲リスト, 命令列, mode)。.pdata 内なら primary の全チャンク、無ければ scan (int3 境界まで)。"""
        p = owner(entry)
        if p is not None:
            ranges = sorted(groups[p])
            ins = []
            for b, e in ranges:
                ins += sweep_until(b, e)
            return p, ranges, ins, "pdata"
        ins = sweep_until(entry, None)
        return entry, [(entry, entry + sum(i.size for i in ins))], ins, "scan"

    def direct(ins):
        return ins.op_str.startswith("0x")

    def classify(ins):
        return "simd" if any(r in ins.op_str for r in ("xmm", "ymm", "zmm")) else "scalar"

    def rdx_before(insns, k):
        """k 番目の call の直前 3 命令内にある `mov edx|rdx, imm` の値 (無ければ None)。"""
        for j in range(k - 1, max(-1, k - 4), -1):
            m = insns[j]
            if m.mnemonic == "mov" and m.op_str.split(",")[0].strip() in ("edx", "rdx"):
                try:
                    return int(m.op_str.split(",")[1].strip(), 16)
                except ValueError:
                    return None
        return None

    def rip_target(ins):
        if ins.mnemonic == "lea" and "[rip" in ins.op_str:
            disp = struct.unpack_from("<i", bytes(ins.bytes), len(ins.bytes) - 4)[0]
            return ins.address + ins.size + disp
        return None

    # 1. CreateInstance の vptr 格納 lea
    ci = sweep_until(CREATE_RVA, CREATE_RVA + 0x40)
    vt_lea = next(i for i in ci if rip_target(i) is not None)
    VT = rip_target(vt_lea)
    create_info = {
        "rva": hex(CREATE_RVA),
        "vptr_lea_at": hex(vt_lea.address),
        "vptr_lea_bytes": bytes(vt_lea.bytes).hex(),
        "vptr_target_rva": hex(VT),
        "const_mov": [f"{hex(i.address)} {i.mnemonic} {i.op_str}" for i in body(CREATE_RVA)[2]
                      if i.mnemonic == "mov" and i.op_str.split(",")[0].strip() in ("ecx", "edx", "r8d") and i.op_str.split(",")[1].strip().startswith("0x")],
    }

    # 2. vtable slot 列 (.text を指す間)
    slots = []
    while len(slots) < MAX_SLOTS:
        v = struct.unpack_from("<Q", img, VT + 8 * len(slots))[0]
        rva = v - base
        if not (t_lo <= rva < t_hi):
            break
        slots.append(rva)
    end_v = struct.unpack_from("<Q", img, VT + 8 * len(slots))[0]

    slot_out = []
    for k, rva in enumerate(slots):
        b, ranges, ins, mode = body(rva)
        head = ins[:4]
        rec = {"index": k, "value_va": hex(base + rva), "target_rva": hex(rva), "mode": mode,
               "ranges": [[hex(x), hex(y)] for x, y in ranges],
               "head": [f"{hex(i.address)} {i.mnemonic} {i.op_str}" for i in head]}
        if len(ins) >= 2 and ins[0].mnemonic == "mov" and ins[0].op_str == "rcx, qword ptr [rcx + 8]" \
                and ins[1].mnemonic == "jmp" and direct(ins[1]):
            rec["kind"] = "thunk_inner"
            rec["thunk_target"] = hex(int(ins[1].op_str, 16))
        elif len(ins) >= 2 and ins[0].mnemonic == "xor" and ins[0].op_str == "eax, eax" and ins[1].mnemonic == "ret":
            rec["kind"] = "const_ret0"
        else:
            rec["kind"] = "function"
        calls = []
        for j, i in enumerate(ins):
            if i.mnemonic == "call":
                rdx = rdx_before(ins, j)
                calls.append({"site": hex(i.address), "target": (hex(int(i.op_str, 16)) if direct(i) else None),
                              "op": i.op_str, "rdx": (hex(rdx) if rdx is not None else None)})
        rec["calls"] = calls
        rec["stores_vptr"] = [hex(i.address) for i in ins if rip_target(i) == VT]
        slot_out.append(rec)

    # 3. closure
    def closure(entries):
        seen, order, stack = {}, [], list(entries)
        n_ins = simd = dcalls = 0
        ind_calls, ind_jmps, dsites, djsites, franges = [], [], [], [], {}
        while stack:
            ent = stack.pop()
            b, ranges, ins, mode = body(ent)
            if b in seen:
                continue
            seen[b] = mode
            order.append(b)
            franges[b] = ranges
            n_ins += len(ins)
            own = {i.address for i in ins}
            for k, i in enumerate(ins):
                if classify(i) == "simd":
                    simd += 1
                if i.mnemonic == "call":
                    if direct(i):
                        dcalls += 1
                        dsites.append([hex(i.address), hex(int(i.op_str, 16))])
                        stack.append(int(i.op_str, 16))
                    else:
                        ind_calls.append({"site": hex(i.address), "in_func": hex(b), "op": i.op_str, **ind_info(i)})
                elif i.mnemonic == "jmp":
                    if direct(i):
                        t = int(i.op_str, 16)
                        if t not in own:
                            djsites.append([hex(i.address), hex(t)])
                            stack.append(t)
                    else:
                        ind_jmps.append({"site": hex(i.address), "in_func": hex(b), "op": i.op_str, **ind_info(i)})
        return {
            "entries": [hex(x) for x in entries],
            "functions": len(order),
            "function_starts": [{"start": hex(x), "mode": seen[x],
                                 "ranges": [[hex(p), hex(q)] for p, q in franges[x]]} for x in sorted(order)],
            "direct_call_sites": sorted(dsites),
            "direct_jmp_sites": sorted(djsites),
            "instructions": n_ins, "simd": simd, "direct_calls": dcalls,
            "indirect_calls": sorted(ind_calls, key=lambda d: int(d["site"], 16)),
            "indirect_jmps": sorted(ind_jmps, key=lambda d: int(d["site"], 16)),
        }

    cl_ci = closure([CREATE_RVA])
    cl_all = closure([CREATE_RVA] + [int(s["target_rva"], 16) for s in slot_out])
    seeds = [int(x, 16) for x in a.seed.split(",") if x]
    cl_seed = closure(seeds) if seeds else None

    res = {
        "pe": a.pe,
        "pe_sha256": hashlib.sha256(raw).hexdigest(),
        "image_base": hex(base),
        "text": {"lo": hex(t_lo), "hi": hex(t_hi)},
        "create_instance": create_info,
        "vtable": {"rva": hex(VT), "slot_count": len(slots), "slots": slot_out,
                   "end_value_va": hex(end_v), "end_in_text": bool(t_lo <= end_v - base < t_hi)},
        "closure_create_only": cl_ci,
        "closure_with_slots": cl_all,
        "closure_seed": cl_seed,
    }
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(res, open(a.out, "w"), ensure_ascii=False, indent=1)

    print(f"# ildsp vtable: {os.path.basename(a.pe)} sha256={res['pe_sha256'][:12]}")
    print(f"vtable rva={hex(VT)} slots={len(slots)} end_value={hex(end_v)} end_in_text={res['vtable']['end_in_text']}")
    for s in slot_out:
        extra = f" -> {s['thunk_target']}" if s["kind"] == "thunk_inner" else ""
        print(f"slot {s['index']}: {s['target_rva']} {s['kind']}{extra} mode={s['mode']} ranges={s['ranges']} "
              f"calls={[(c['target'], c['rdx']) for c in s['calls']]} stores_vptr={s['stores_vptr']}")
    named = [("CreateInstance 単独", cl_ci), ("CreateInstance + 全 slot", cl_all)]
    if cl_seed is not None:
        named.append((f"seed {a.seed}", cl_seed))
    for name, cl in named:
        print(f"closure[{name}]: functions={cl['functions']} instructions={cl['instructions']} simd={cl['simd']} "
              f"direct_calls={cl['direct_calls']} indirect_calls={len(cl['indirect_calls'])} indirect_jmps={len(cl['indirect_jmps'])}")
        for c in cl["indirect_calls"]:
            print(f"  indirect call {c['site']} in {c['in_func']}: {c['op']} slot={c.get('slot_rva')} import={c.get('import')}")
        for c in cl["indirect_jmps"]:
            print(f"  indirect jmp {c['site']} in {c['in_func']}: {c['op']} slot={c.get('slot_rva')} import={c.get('import')}")


if __name__ == "__main__":
    main()
