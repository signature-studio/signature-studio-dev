#!/usr/bin/env python3
"""lift_fnmap.py — lift 出力から (1) 関数 VA -> 関数 の fnmap と (2) WNDPROC 候補の自動検出 (CAB-156 / GUI-3a)。

gui_lift_post.py (RetDec C 経路) から import される汎用部と、m11 IR 向け診断 CLI を兼ねる。

RetDec C 経路 (テスト PE / プラグイン DLL 等):
  - 「アドレス取得済み関数」= 他関数の本体に VA 定数 (0x... 5桁以上) として現れる関数。lpfnWndProc 等は VA 整数で保持される (REPORT §4-5)。
  - WNDPROC 候補 = アドレス取得済み関数のうち、取得元関数が RegisterClass*/SetWindowLong*/SetClassLong*/CreateDialog*/DialogBox*
    を呼ぶもの (--wndproc 手指定を廃止するための検出)。4 引数へ正規化するのは候補のみ (EnumWindows 等 2 引数の callback は触らない)。
m11 IR 経路 (診断のみ: `lift_fnmap.py --ir boot_final.ll`):
  - m11 は VA -> trampoline の統一署名 (m11_icall) を持つため fnmap/正規化は不要。代わりに RegisterClass*/SetWindowLongPtr 呼出点と
    WNDCLASS 定数アドレスを列挙し、CAB-173 で「どの WNDPROC を m11_disp_tab が解決できるべきか」の確認表にする。
"""
import re, sys, argparse

WNDPROC_TAKERS = re.compile(r"\b(RegisterClass(?:Ex)?[AW]|SetWindowLong(?:Ptr)?[AW]|SetClassLong(?:Ptr)?[AW]|CreateDialog\w*|DialogBox\w*)\s*\(")
HEXLIT = re.compile(r"(?<![\w.])0x([0-9a-fA-F]{5,})\b")


def strip_comments(body):
    return "\n".join(l.split("//")[0] for l in body.split("\n"))


def address_taken(funcs):
    """funcs: [(va, name, body)] -> {callee_name: [taker_name,...]} (自己参照は除く)"""
    by_va = {va: name for va, name, _ in funcs}
    out = {}
    for va, name, body in funcs:
        for m in HEXLIT.finditer(strip_comments(body)):
            v = int(m.group(1), 16)
            if v in by_va and by_va[v] != name:
                out.setdefault(by_va[v], []).append(name)
    return out


def detect_wndprocs(funcs):
    """-> (候補名の順序付きリスト, 理由 {name: 'address taken in X near Y()'})"""
    taken = address_taken(funcs)
    bodies = {name: strip_comments(body) for _, name, body in funcs}
    cands, why = [], {}
    for _, name, _b in funcs:
        for taker in taken.get(name, []):
            m = WNDPROC_TAKERS.search(bodies[taker])
            if m:
                cands.append(name); why[name] = "address taken in %s near %s()" % (taker, m.group(1)); break
    return cands, why


def emit_fnmap(entries, table="gui_lift_fnmap"):
    """entries: [(va, cname)] -> C 断片 (GuiFnMap 表)"""
    s = "\nconst GuiFnMap %s[] = {\n" % table + "".join("  { 0x%xull, (void *)%s },\n" % (va, n) for va, n in entries) + "};\n"
    return s + "const int %s_n = %d;\n" % (table, len(entries))


# ------------------------------- m11 IR 診断 -------------------------------
def ir_report(path):
    src = open(path, encoding="utf-8", errors="replace").read()
    fns = {}
    for m in re.finditer(r"^define [^\n]*@(function_[0-9a-f]+)\([^\n]*\{\n(.*?)^\}", src, re.M | re.S):
        fns[m.group(1)] = m.group(2)
    vas = {int(n.split("_")[1], 16): n for n in fns}
    sites = []
    for n, body in fns.items():
        for m in re.finditer(r"call [^\n]*@(RegisterClass(?:Ex)?[AW]|SetWindowLong(?:Ptr)?[AW]|SetClassLong(?:Ptr)?[AW])\(([^\n]*)\)", body):
            api, args = m.group(1), m.group(2)
            cst = re.findall(r"inttoptr \(i64 (\d+) to ptr\)", args)
            consts = [int(x) for x in re.findall(r"\bi64 (\d+)\b", body)]
            taken = sorted({vas[c] for c in consts if c in vas and vas[c] != n})
            sites.append((n, api, [hex(int(c)) for c in cst], taken))
    return sites, len(fns)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--ir", required=True); a = ap.parse_args()
    sites, nf = ir_report(a.ir)
    print("# m11 IR: %d functions; WNDPROC 関連呼出点 %d" % (nf, len(sites)))
    for n, api, cst, taken in sites:
        print("%s calls %s  const-arg=%s  fn-address-constants-in-body=%s" % (n, api, ",".join(cst) or "-", ",".join(taken) or "-"))


if __name__ == "__main__":
    main()
