#!/usr/bin/env python3
"""gui_lift_post.py — RetDec の C 出力 (PE) を GUI shim にリンクできる C に後処理する。

tools/m1 の「main 抽出」より踏み込んだ最小後処理 (lifter 産コードは *書き換えず* 型/データ配置だけ整える):
  1. thunk 関数 (`Foo2` が `Foo()` を呼ぶだけの import スタブ) を除去
  2. `struct tagXXX *` 型を `int64_t` へ (構造体定義を持たないため) — lift ABI は全 int64
  3. 大域変数 gN を PE イメージ (`__pe_image`) 内の固定オフセットへ #define (RetDec は構造体フィールドを
     別々の大域に分けるため、`&g1` を struct ポインタとして渡すには連続配置が必要)
  4. 関数 VA -> 関数ポインタ表 (GuiFnMap) を生成 (WNDCLASS.lpfnWndProc 等は VA 値で lifted コードが保持)
  5. WndProc 系の 4 引数署名を強制。候補は既定で自動検出 (integ/lift_fnmap.py: RegisterClass*/SetWindowLong* を呼ぶ関数の本体で
     VA 定数として取得されている関数)。`--wndproc NAME` は追加指定、`--no-auto-wndproc` で検出を無効化
usage: gui_lift_post.py <retdec.c> <pe> <out.c> [--wndproc NAME ...] [--no-auto-wndproc]
"""
import os, re, struct, sys, argparse
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "integ"))
import lift_fnmap


def read_pe_image(path):
    d = open(path, "rb").read()
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    optsz = struct.unpack_from("<H", d, pe + 20)[0]
    opt = pe + 24
    base = struct.unpack_from("<Q", d, opt + 24)[0]
    size_of_image = struct.unpack_from("<I", d, opt + 56)[0]
    img = bytearray(size_of_image)
    so = opt + optsz
    for i in range(nsec):
        e = so + i * 40
        name = d[e:e + 8].split(b"\0")[0].decode("latin1")
        vsz, va, rsz, rptr = struct.unpack_from("<IIII", d, e + 8)
        if name == ".text":
            continue  # コードは lift 済み。イメージには入れない
        n = min(vsz, rsz) if rsz else 0
        img[va:va + n] = d[rptr:rptr + n]
    return base, bytes(img)


CTYPE = {"int8_t": "int8_t", "uint8_t": "uint8_t", "int16_t": "int16_t", "uint16_t": "uint16_t",
         "int32_t": "int32_t", "uint32_t": "uint32_t", "int64_t": "int64_t", "uint64_t": "uint64_t",
         "char": "char", "bool": "uint8_t", "float": "float", "double": "double"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("pe"); ap.add_argument("out")
    ap.add_argument("--wndproc", action="append", default=[])
    ap.add_argument("--no-auto-wndproc", action="store_true")
    ap.add_argument("--entry-rename", default="lifted_entry")
    a = ap.parse_args()
    txt = open(a.src, encoding="utf-8").read()
    base, img = read_pe_image(a.pe)

    gi = txt.index("// --------------------- Global Variables ---------------------")
    fi = txt.index("// ------------------------ Functions -------------------------")
    gtxt = txt[gi:fi]
    ftxt = txt[fi:]
    if "// --------------------- Meta-Information" in ftxt:
        ftxt = ftxt[:ftxt.index("// --------------------- Meta-Information")]

    # --- globals
    macros = []; gnames = []
    for m in re.finditer(r"^([^\n;=]+?)\s+(g\d+)(?:\s*=\s*[^;]*)?;(?:\s*//\s*(0x[0-9a-fA-F]+))?\s*$", gtxt, re.M):
        ty, name, addr = m.group(1).strip(), m.group(2), m.group(3)
        gnames.append(name)
        ct = "int64_t" if ("*" in ty or ty.startswith("struct")) else CTYPE.get(ty, "int64_t")
        if addr is None:
            macros.append("static %s %s;" % (ct, name))
        else:
            off = int(addr, 16) - base
            macros.append("#define %s (*(%s *)(__pe_image + 0x%x))" % (name, ct, off))

    # --- functions
    parts = re.split(r"(?m)^// Address range: (0x[0-9a-f]+) - (0x[0-9a-f]+)\n", ftxt)
    funcs = []  # (va, name, text)
    for i in range(1, len(parts), 3):
        va, body = int(parts[i], 16), parts[i + 2].rstrip() + "\n"
        m = re.match(r"([^\n(]*?)(\w+)\(([^\n]*)\) \{\n", body)
        if not m:
            continue
        name = m.group(2)
        stmts = [l.strip() for l in body.split("\n")[1:] if l.strip() and not l.strip().startswith("//") and l.strip() != "}"]
        callee = name.rstrip("0123456789")
        if len(stmts) == 1 and callee != name and re.match(r"(return\s+)?%s\(" % re.escape(callee), stmts[0]):
            continue  # import thunk
        funcs.append((va, name, body))

    def fix_types(s):
        s = re.sub(r"struct\s+\w+\s*\*+\s*", "int64_t ", s)
        s = re.sub(r"\(struct\s+\w+\s*\*+\)", "(int64_t)", s)
        s = re.sub(r"\(int64_t\s*\*\*+\)", "(int64_t)", s)
        return s

    if not a.no_auto_wndproc:
        auto, why = lift_fnmap.detect_wndprocs(funcs)
        for n in auto:
            if n not in a.wndproc:
                a.wndproc.append(n)
            print("[post] auto-detected WNDPROC: %s (%s)" % (n, why[n]))
        if not auto and not a.wndproc:
            print("[post] WARN: no WNDPROC candidate detected (use --wndproc NAME)", file=sys.stderr)

    protos = []; out_funcs = []; fnmap = []
    for va, name, body in funcs:
        body = fix_types(body)
        if name in a.wndproc:
            # WNDPROC は shim が i64(i64,i64,i64,i64) で間接呼出する。RetDec は未使用引数を落とす (例: WndProc(a1)) ので
            # 元の仮引数名を保ったまま 4 引数へ正規化する (署名不一致は wasm の call_indirect trap になる)。
            m0 = re.match(r"[^\n(]*?%s\(([^\n]*)\) \{" % re.escape(name), body)
            orig = [x.strip().split()[-1].lstrip("*") for x in m0.group(1).split(",") if x.strip() and x.strip() != "void"] if m0 else []
            if len(orig) > 4:
                print("[post] WARN: %s has %d params (> 4)" % (name, len(orig)), file=sys.stderr)
            names = orig[:4] + ["__wp_pad%d" % i for i in range(len(orig), 4)]
            body = re.sub(r"^[^\n(]*?%s\([^\n]*\) \{" % re.escape(name),
                          "int64_t %s(%s) {" % (name, ", ".join("int64_t " + n for n in names)), body, count=1, flags=re.M)
            if len(orig) != 4:
                print("[post] normalized %s: %d -> 4 params (%s)" % (name, len(orig), ",".join(names)))
        if name == "entry":
            body = body.replace("int64_t entry(void)", "int64_t %s(void)" % a.entry_rename, 1)
            name = a.entry_rename
        sig = body.split("\n")[0].rstrip(" {")
        protos.append(sig + ";")
        out_funcs.append(body)
        fnmap.append((va, name))

    hdr = ['/* generated by gui_lift_post.py from RetDec output — 手編集禁止 */',
           '#include <stdint.h>', '#include <stdbool.h>', '#include <stddef.h>', '#include "gui_api.h"', '',
           'static const uint64_t __pe_image_base = 0x%x;' % base,
           'static uint8_t __pe_image[%d] __attribute__((aligned(4096))) = {' % len(img)]
    rows = []
    for i in range(0, len(img), 32):
        chunk = img[i:i + 32]
        rows.append("  " + ",".join("0x%02x" % b for b in chunk) + ",")
    hdr += rows + ['};', '']
    body = "\n".join(hdr + macros + [''] + protos + [''] + out_funcs)
    body += "\n" + lift_fnmap.emit_fnmap(fnmap)
    body += "int64_t gui_lift_entry(void) { return %s(); }\n" % a.entry_rename
    open(a.out, "w", encoding="utf-8").write(body)
    print("[post] globals=%d functions kept=%d (thunks dropped=%d) image=%dB base=0x%x" % (len(macros), len(funcs), (len(parts) - 1) // 3 - len(funcs), len(img), base))


if __name__ == "__main__":
    main()
