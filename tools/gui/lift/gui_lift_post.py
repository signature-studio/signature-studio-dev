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
usage: gui_lift_post.py <retdec.c> <pe> <out.c> [--wndproc NAME ...] [--no-auto-wndproc] [--no-pe-reloc (検査用)]
"""
import os, re, struct, sys, argparse
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "integ"))
import lift_fnmap
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pe_image


CTYPE = {"int8_t": "int8_t", "uint8_t": "uint8_t", "int16_t": "int16_t", "uint16_t": "uint16_t",
         "int32_t": "int32_t", "uint32_t": "uint32_t", "int64_t": "int64_t", "uint64_t": "uint64_t",
         "char": "char", "bool": "uint8_t", "float": "float", "double": "double"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("pe"); ap.add_argument("out")
    ap.add_argument("--wndproc", action="append", default=[])
    ap.add_argument("--no-auto-wndproc", action="store_true")
    ap.add_argument("--entry-rename", default="lifted_entry")
    ap.add_argument("--no-pe-reloc", action="store_true", help="DIR64 補正を出さない (ネガティブコントロール用)")
    a = ap.parse_args()
    txt = open(a.src, encoding="utf-8").read()
    pe = pe_image.PE(a.pe)
    base = pe.base
    img, relocs, rstat = pe_image.runtime_image(pe, relocate=not a.no_pe_reloc)

    gi = txt.index("// --------------------- Global Variables ---------------------")
    fi = txt.index("// ------------------------ Functions -------------------------")
    gtxt = txt[gi:fi]
    ftxt = txt[fi:]
    if "// --------------------- Meta-Information" in ftxt:
        ftxt = ftxt[:ftxt.index("// --------------------- Meta-Information")]

    # --- globals
    macros = []; gnames = []
    # 関数ポインタ型の大域 `T (*gN)(args) = NULL;` (SetWindowLongPtr の戻り値を保持する WNDPROC 変数など) は int64 の大域として宣言する
    for m in re.finditer(r"^[^\n;=]*?\(\*(g\d+)\)\([^\n;]*\)(?:\s*=\s*[^;]*)?;(?:\s*//\s*(0x[0-9a-fA-F]+))?\s*$", gtxt, re.M):
        name, addr = m.group(1), m.group(2)
        gnames.append(name)
        if addr is None:
            macros.append("static int64_t %s;" % name)
        else:
            macros.append("#define %s (*(int64_t *)(__pe_image + 0x%x))" % (name, int(addr, 16) - base))
    for m in re.finditer(r"^([^\n;=\[]+?)\s+(g\d+)(\[\d+\])?(?:\s*=\s*[^;]*)?;(?:\s*//\s*(0x[0-9a-fA-F]+))?\s*$", gtxt, re.M):
        ty, name, arr, addr = m.group(1).strip(), m.group(2), m.group(3), m.group(4)
        gnames.append(name)
        ct = "int64_t" if ("*" in ty or ty.startswith("struct")) else CTYPE.get(ty, "int64_t")
        cty = "%s (*)%s" % (ct, arr) if arr else "%s *" % ct   # 配列は `&gN` / `gN[i]` が素の C と同じに働く配列 lvalue にする
        if addr is None:
            macros.append("static %s %s%s;" % (ct, name, arr or ""))
        else:
            off = int(addr, 16) - base
            macros.append("#define %s (*(%s)(__pe_image + 0x%x))" % (name, cty, off))

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
        s = re.sub(r"\(\w+ \(\*\)\([^()]*\)\)\(int64_t\)", "(int64_t)", s)   # 整数→関数ポインタ→整数 (VA を保持する大域への代入)
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
    # イメージ内ポインタ (DIR64) のスロット offset 表。起動時に delta = &__pe_image[0] - base を足す (.text 宛 = 関数 VA は fnmap の鍵なので触らない)
    hdr += ['static const uint32_t __pe_image_relocs[] = {' + ",".join("0x%x" % o for o in relocs or [0]) + '};',
            'static const int __pe_image_relocs_n = %d;' % len(relocs),
            'static void __pe_image_fixup(void) {',
            '  static int done;',
            '  if (done) return;',
            '  done = 1;',
            '  uint64_t delta = (uint64_t)(uintptr_t)__pe_image - __pe_image_base;',
            '  for (int i = 0; i < __pe_image_relocs_n; i++) { uint64_t *p = (uint64_t *)(__pe_image + __pe_image_relocs[i]); *p += delta; }',
            '}', '']
    body = "\n".join(hdr + macros + [''] + protos + [''] + out_funcs)
    body += "\n" + lift_fnmap.emit_fnmap(fnmap)
    body += "int64_t gui_lift_entry(void) { __pe_image_fixup(); return %s(); }\n" % a.entry_rename
    open(a.out, "w", encoding="utf-8").write(body)
    print("[post] globals=%d functions kept=%d (thunks dropped=%d) image=%dB base=0x%x dir64=%d rebased=%d text_kept=%d" % (len(macros), len(funcs), (len(parts) - 1) // 3 - len(funcs), len(img), base, rstat["dir64"], len(relocs), rstat["text_kept"]))


if __name__ == "__main__":
    main()
