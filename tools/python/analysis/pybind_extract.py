#!/usr/bin/env python3
"""FLEngine (win64 PE) の Python C API 動的束縛 (InitSharedPython 周辺, 既定 0xc395a0) を機械抽出し、
静的リンク対象 libpython3.12.a の定義済みシンボルと突き合わせて対応表を出す (#83 / #115)。

  python3 analysis/pybind_extract.py --pe <block00031_PE.bin> --lib work/build-wasm/libpython3.12.a \
      [--func 0xc395a0] [--out analysis/pybind] [--expect 110] [--inject NAME] [--check]

方式: 関数範囲 (ret まで) の `lea reg,[rip+rel32]` の参照先を UTF-16LE の NUL 終端文字列として読み、
`_?Py` で始まるものを束縛名とする (名前は ASCII ではなく UTF-16 で PE に入っている)。各 lea の直後の
`call <resolver>` と、結果を保存する `mov [rip+rel32],rax` のスロット VA も取る。
gate (--check): 抽出件数が --expect と一致、全名が lib に存在 (ALLOW_ABSENT を除く)、ALLOW_ABSENT の根拠が
実際に成立 (lib に無い) していること。不合格は exit 1。--inject は存在しない名前を 1 件足すネガコン用。
"""
import argparse, json, os, re, struct, subprocess, sys

# lib に無くても許容する名前と根拠 (根拠が成立しなくなったら gate が落ちる)
ALLOW_ABSENT = {
    "_PyInterpreterState_GetRefTotal": "CPython 3.12 の Objects/object.c で #ifdef Py_REF_DEBUG 内のみ定義 (release build に無い)",
}
MUST_HAVE = {"Py_InitializeEx", "Py_NewInterpreterFromConfig", "PyRun_SimpleString", "PyEval_SaveThread", "PyImport_AppendInittab"}


def load_pe(path):
    d = open(path, "rb").read()
    e = struct.unpack_from("<I", d, 0x3C)[0]
    assert d[e:e + 4] == b"PE\0\0", "not a PE"
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    osz = struct.unpack_from("<H", d, e + 20)[0]
    base = struct.unpack_from("<Q", d, e + 24 + 24)[0]
    secs = []
    for i in range(nsec):
        n, vs, va, rs, rp = struct.unpack_from("<8sIIII", d, e + 24 + osz + i * 40)
        secs.append((n.rstrip(b"\0").decode(), va, max(vs, rs), rp, rs))
    return d, base, secs


def va2off(base, secs, va):
    rva = va - base
    for _, sva, sz, rp, rs in secs:
        if sva <= rva < sva + min(sz, rs) and rp:
            return rp + rva - sva
    return None


def utf16z(d, off, limit=96):
    out = []
    for i in range(limit):
        c = struct.unpack_from("<H", d, off + 2 * i)[0]
        if c == 0:
            break
        if not 0x20 <= c < 0x7F:
            return None
        out.append(chr(c))
    return "".join(out)


def extract(pe, func_va):
    d, base, secs = load_pe(pe)
    start = va2off(base, secs, func_va)
    # 関数範囲: 先頭から最初の epilogue (`add rsp,imm8; ret`) まで。早期 return は epilogue への jmp なので 1 つ目が関数末尾
    code = d[start:start + 0x1000]
    m_end = re.search(rb"\x48\x83\xc4[\x20-\x7f]\xc3", code)
    if not m_end:
        sys.exit("epilogue not found")
    end = m_end.end()
    code = code[:end]
    names = []
    for m in re.finditer(rb"[\x48\x4c]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]", code):
        i = m.start()
        rel = struct.unpack_from("<i", code, i + 3)[0]
        site = func_va + i
        tgt = site + 7 + rel
        off = va2off(base, secs, tgt)
        if off is None:
            continue
        s = utf16z(d, off)
        if not s or not re.match(r"_?Py[A-Z_]", s):
            continue
        # `lea rdx,[name]; call <resolver>; mov [slot],rax` の固定並びだけ解釈する (他形は resolver/slot を None)
        rest = code[i + 7:i + 7 + 12]
        callee = slot = None
        if len(rest) >= 12 and rest[0] == 0xE8:
            callee = site + 7 + 5 + struct.unpack_from("<i", rest, 1)[0]
            if rest[5] in (0x48, 0x4C) and rest[6] == 0x89 and rest[7] in (0x05, 0x0D, 0x15, 0x1D, 0x25, 0x2D, 0x35, 0x3D):
                slot = site + 7 + 12 + struct.unpack_from("<i", rest, 8)[0]
        names.append({"name": s, "lea_va": hex(site), "resolver_va": hex(callee) if callee else None,
                      "slot_va": hex(slot) if slot else None})
    return names, hex(func_va + end), base


def lib_syms(lib):
    nm = os.environ.get("LLVM_NM", "llvm-nm")
    out = subprocess.run([nm, "--defined-only", lib], capture_output=True, text=True, check=True).stdout
    syms = {}
    for l in out.splitlines():
        p = l.split()
        if len(p) == 3:
            syms.setdefault(p[2], set()).add(p[1])
    return syms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pe", required=True)
    ap.add_argument("--lib", required=True)
    ap.add_argument("--func", default="0xc395a0")
    ap.add_argument("--out", default=None)
    ap.add_argument("--expect", type=int, default=None)
    ap.add_argument("--inject", action="append", default=[])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    names, end, base = extract(a.pe, int(a.func, 16))
    for n in a.inject:
        names.append({"name": n, "lea_va": None, "resolver_va": None, "slot_va": None, "injected": True})
    syms = lib_syms(a.lib)
    rows = []
    for n in names:
        t = syms.get(n["name"])
        kind = None if not t else ("data" if t & {"D", "B", "R", "d", "b", "r"} else "func")
        n.update({"kind": kind, "lib": bool(t), "lib_type": "".join(sorted(t)) if t else None})
        if not t and n["name"] in ALLOW_ABSENT:
            n["absent_reason"] = ALLOW_ABSENT[n["name"]]
        rows.append(n)
    present = [r for r in rows if r["lib"]]
    missing = [r["name"] for r in rows if not r["lib"] and r["name"] not in ALLOW_ABSENT]
    allowed = [r["name"] for r in rows if not r["lib"] and r["name"] in ALLOW_ABSENT]
    summary = {"function_va": a.func, "scan_end_va": end, "names": len(rows), "unique": len({r["name"] for r in rows}),
               "in_lib": len(present), "funcs": sum(r["kind"] == "func" for r in rows), "data": sum(r["kind"] == "data" for r in rows),
               "absent_allowed": allowed, "missing": missing,
               "with_slot": sum(bool(r["slot_va"]) for r in rows), "resolvers": sorted({r["resolver_va"] for r in rows if r["resolver_va"]})}
    if a.out:
        os.makedirs(a.out, exist_ok=True)
        json.dump({"summary": summary, "bindings": rows}, open(os.path.join(a.out, "pybind_map.json"), "w"), indent=1)
        with open(os.path.join(a.out, "pybind_map.tsv"), "w") as f:
            f.write("name\tkind\tlib_type\tlea_va\tresolver_va\tslot_va\tnote\n")
            for r in rows:
                f.write("\t".join(str(x) if x is not None else "-" for x in (r["name"], r["kind"], r["lib_type"], r["lea_va"], r["resolver_va"], r["slot_va"], r.get("absent_reason", ""))) + "\n")
        with open(os.path.join(a.out, "pybind_refs.inc"), "w") as f:
            f.write("/* 生成物: analysis/pybind_extract.py。FL が動的束縛する Py* のうち libpython3.12.a に存在する名前 */\n")
            for r in present:
                f.write(("extern void %s(void);\n" if r["kind"] == "func" else "extern char %s[];\n") % r["name"])
            f.write("static const struct { const char *name; const void *addr; } pybind_refs[] = {\n")
            for r in present:
                f.write('    {"%s", (const void *)&%s},\n' % (r["name"], r["name"]))
            f.write("};\n")
    print(json.dumps(summary))
    if a.check:
        bad = []
        if a.expect is not None and len(rows) - len(a.inject) != a.expect:
            bad.append(f"extracted {len(rows) - len(a.inject)} != expect {a.expect}")
        if missing:
            bad.append(f"not in libpython: {missing}")
        for n in allowed:
            if n in syms:
                bad.append(f"ALLOW_ABSENT {n} が lib に存在する (根拠が不成立)")
        absent_must = MUST_HAVE - {r["name"] for r in rows}
        if absent_must:
            bad.append(f"must-have names not extracted: {sorted(absent_must)}")
        if len({r['name'] for r in rows}) != len(rows):
            bad.append("duplicate names")
        if summary["with_slot"] < len(rows) - len(a.inject) - 2:
            bad.append(f"slot extraction too low: {summary['with_slot']}")
        if bad:
            print("PYBIND CHECK FAIL: " + "; ".join(bad), file=sys.stderr)
            sys.exit(1)
        print("PYBIND CHECK OK")


if __name__ == "__main__":
    main()
