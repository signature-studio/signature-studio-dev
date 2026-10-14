#!/usr/bin/env python3
# #2839 (SHX-T31): import 呼出しの引数幅が IR で i64 になる根本の突合。
# 機械語 (PE の IAT → thunk → 呼出し元) ・ RetDec の lift (該当関数 + thunk だけ) ・ RetDec 署名 DB を並べる。
# 使い方: python3 tools/m11/shimx_link/hmo_rootcause.py [--dll winmm.dll --name midiOutShortMsg]
# 素材: FL_WIN64_DIR (既定 block00031_PE.bin) / RETDEC_ROOT (既定 /opt/retdec)。出力は work/shimx_link/rootcause/ (gitignore)。
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

HERE = Path(__file__).resolve().parent
WORK = HERE.parent / "work" / "shimx_link" / "rootcause"
IMAGE_SCN_MEM_EXECUTE = 0x20000000
RIP_RE = re.compile(r"rip ([+-]) 0x([0-9a-f]+)")


def load_pe(path):
    pe = pefile.PE(path)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    return pe


def find_iat(pe, dll, name):
    for ent in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
        if ent.dll.decode(errors="replace").lower() != dll.lower():
            continue
        for imp in ent.imports:
            if imp.name and imp.name.decode() == name:
                return imp.address
    return None


def disasm_exec(pe):
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.skipdata = True
    base = pe.OPTIONAL_HEADER.ImageBase
    for s in pe.sections:
        if s.Characteristics & IMAGE_SCN_MEM_EXECUTE:
            yield list(md.disasm(s.get_data(), base + s.VirtualAddress))


def rip_target(x):
    m = RIP_RE.search(x.op_str)
    if not m:
        return None
    d = int(m.group(2), 16)
    return x.address + x.size + (d if m.group(1) == "+" else -d)


def find_thunks(pe, iat):
    out = []
    for ins in disasm_exec(pe):
        for x in ins:
            if x.mnemonic == "jmp" and rip_target(x) == iat:
                out.append(x)
    return out


def find_callers(pe, thunk_addrs):
    res = []
    for ins in disasm_exec(pe):
        for i, x in enumerate(ins):
            if x.mnemonic == "call" and x.op_str.startswith("0x") and int(x.op_str, 16) in thunk_addrs:
                lo = i
                while lo > 0 and ins[lo - 1].mnemonic not in ("ret", "int3"):
                    lo -= 1
                hi = i
                while hi < len(ins) - 1 and ins[hi].mnemonic != "ret":
                    hi += 1
                res.append((x, ins[lo:hi + 1]))
    return res


def resolve_type(types, tid):
    seen = []
    cur = str(tid)
    while True:
        ent = types.get(cur)
        if ent is None:
            return seen + ["<missing %s>" % cur]
        seen.append(ent.get("name", ent.get("type", "?")))
        if ent.get("type") != "typedef":
            return seen
        nxt = ent.get("typedefed_type")
        if nxt == "unknown":
            return seen + ["unknown"]
        cur = nxt


def show_db(retdec_root, name):
    p = retdec_root / "share/retdec/support/generic/types/windows.json"
    d = json.load(open(p))
    types = d["types"]
    fn = d["functions"].get(name)
    print("[db] %s" % p.relative_to(retdec_root))
    print("[db] unknown typedef 総数: %d" % sum(1 for v in types.values() if v.get("typedefed_type") == "unknown"))
    if fn is None:
        print("[db] %s: 署名無し" % name)
        return
    print("[db] decl: %s" % fn["decl"])
    for prm in fn["params"]:
        print("[db]   param %-10s type_id=%-6s chain=%s" % (prm["name"], prm["type"], " -> ".join(resolve_type(types, prm["type"]))))


def run_retdec(retdec_bin, pe_path, ranges, tag):
    WORK.mkdir(parents=True, exist_ok=True)
    tmp = WORK / "tmp"
    tmp.mkdir(exist_ok=True)
    env = dict(os.environ, TMPDIR=str(tmp))
    out_c = WORK / ("%s.drc.c" % tag)
    subprocess.run([retdec_bin, pe_path, "-o", str(out_c), "--select-ranges", ranges,
                    "--select-decode-only", "--timeout", "600"],
                   check=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900)
    return WORK / ("%s.drc.ll" % tag)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default="winmm.dll")
    ap.add_argument("--name", default="midiOutShortMsg")
    args = ap.parse_args()
    fl = Path(os.environ.get("FL_WIN64_DIR", "")) / "extracted/block00031_PE.bin"
    fl = Path(os.environ.get("M11_PE", fl))
    retdec_root = Path(os.environ.get("RETDEC_ROOT", "/opt/retdec"))
    retdec_bin = os.environ.get("RETDEC") or str(retdec_root / "bin/retdec-decompiler")
    print("[pe] %s" % fl)
    pe = load_pe(str(fl))
    iat = find_iat(pe, args.dll, args.name)
    if iat is None:
        print("[pe] %s!%s は import 表に無い" % (args.dll, args.name))
        return 1
    print("[pe] IAT %s!%s = VA 0x%x" % (args.dll, args.name, iat))
    thunks = find_thunks(pe, iat)
    print("[pe] thunk (jmp [IAT]) %d 件: %s" % (len(thunks), ", ".join("0x%x" % t.address for t in thunks)))
    if not thunks:
        return 1
    callers = find_callers(pe, {t.address for t in thunks})
    print("[pe] 呼出し元 %d 件" % len(callers))
    if not callers:
        return 1
    call, body = callers[0]
    print("[pe] 呼出し元 (先頭 1 件) の関数本体 0x%x-0x%x:" % (body[0].address, body[-1].address + body[-1].size))
    for y in body:
        mark = ">>" if y.address == call.address else "  "
        print("   %s %x: %s %s" % (mark, y.address, y.mnemonic, y.op_str))
    thunk = thunks[0]
    fstart, fend = body[0].address, body[-1].address + body[-1].size
    ranges = "0x%x-0x%x,0x%x-0x%x" % (fstart, fend, thunk.address, thunk.address + thunk.size)
    print("[lift] RetDec select-ranges: %s" % ranges)
    ll = run_retdec(retdec_bin, str(fl), ranges, args.name)
    text = ll.read_text()
    print("[lift] IR (%s):" % ll.name)
    for line in text.splitlines():
        if line.startswith("declare") or ("@%s(" % args.name) in line or line.startswith("define"):
            print("   " + line)
    show_db(retdec_root, args.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
