#!/usr/bin/env python3
"""dir64_boundary_enum.py — DIR64 補正境界 (section 末尾 8B slot) の複製を全数列挙する (#593 / M11-N22)。

2 算法で独立に列挙して突合する:
  (A) grep 系 : 行単位の正規表現。`reloc` / `DIR64` を含むファイルの中で「<区間下限> <=? r <=? <下限> + <長さ> - (7|8)」形の比較行
  (B) AST 系  : python の ast で Compare ノードを走査。比較子に `X - 8` / `X - 7` (X は加算式) があり、同一ファイル内に reloc を扱う記述があるもの
どちらかにだけ出る行があれば FAIL (列挙漏れ)。判定:
  OLD     : `r < lo + len - 8`  (末尾 8B slot が落ちる = 旧 m11 と同じ off-by-one)
  OK      : `r <= lo + len - 8` / `r < lo + len - 7` (末尾 slot を含む)
OLD が 1 件でも残れば exit 1 (不合格で exit 0 にならない)。

  python3 tools/liftlib/dir64_boundary_enum.py [--root DIR] [--json out.json]
"""
import ast
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
EXTS = (".py", ".mjs", ".js", ".ts", ".sh", ".c", ".h")
SKIP = ("/work/", "/node_modules/", "/__pycache__/", "/venv/")
# 旧境界を「意図して」持つ行 (旧式と新式の選択差を測る監査式)。ここ以外の OLD は残存欠陥として FAIL する。
INTENDED_OLD = {("m11/m11_reloc_audit.py", 83): "式 OLD: 旧条件との選択差を測る監査用 (#572)"}

# (A) 比較行: `... <|<= ... + ... - 7|8` (lo + len(sd) - 8 / va + vs - 7 / lo + min(len(a), len(b)) - 8 など)
RE_CMP = re.compile(r"(?P<op><=|<)\s*[\w.\[\]]+\s*\+\s*[^:\n]*?-\s*(?P<k>[78])\b")
RE_LOWER = re.compile(r"\b[\w.\[\]]+\s*<=\s*r\b|\br\b\s*(?P<op2><=|<)")


def classify(op, k):
    """r OP lo+len-k の OP/k から末尾 slot (r == lo+len-8) を含むかを返す。"""
    if k == "8":
        return "OK" if op == "<=" else "OLD"
    return "OK" if op == "<" else "OLD?"      # k == 7: `<` で r<=lo+len-8 と同値, `<=` は slot がはみ出す


def files(root):
    for dp, dn, fn in os.walk(root):
        p = "/" + os.path.relpath(dp, root).replace(os.sep, "/") + "/"   # root 外 (runner の /work/ 等) に反応させない
        if any(s in p for s in SKIP):
            continue
        for f in fn:
            fp = os.path.join(dp, f)
            if f.endswith(EXTS) and not f.startswith("dir64_boundary_"):   # 本検査自身 (docstring / sed 例) は対象外
                yield fp


def has_reloc(txt):
    return "DIR64" in txt or "reloc" in txt


def enum_grep(root):
    out = {}
    for path in files(root):
        try:
            txt = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if not has_reloc(txt):
            continue
        for ln, line in enumerate(txt.splitlines(), 1):
            if "r" not in line or not re.search(r"\br\b", line):
                continue
            m = RE_CMP.search(line)
            if not m or not re.search(r"\b\w+\s*<=?\s*r\b|\br\s*<=?\s*\w", line):
                continue
            if "range(" in line or re.search(r"\bsed\b", line) or line.lstrip().startswith(("#", "//", "*")):
                continue
            out[(os.path.relpath(path, root), ln)] = classify(m.group("op"), m.group("k"))
    return out


def _src_has_k(node):
    """BinOp(Sub, <Add式>, Constant 7|8) か。"""
    return (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub)
            and isinstance(node.right, ast.Constant) and node.right.value in (7, 8)
            and isinstance(node.left, ast.BinOp) and isinstance(node.left.op, ast.Add))


def enum_ast(root):
    out = {}
    for path in files(root):
        if not path.endswith(".py"):
            continue
        try:
            txt = open(path, encoding="utf-8", errors="replace").read()
            tree = ast.parse(txt)
        except (OSError, SyntaxError):
            continue
        if not has_reloc(txt):
            continue
        for n in ast.walk(tree):
            if not isinstance(n, ast.Compare):
                continue
            # 連鎖比較 a <= r < b の最後の比較子が `lo + len - k` のもの
            if not (n.comparators and _src_has_k(n.comparators[-1])):
                continue
            names = [x.id for x in ast.walk(n) if isinstance(x, ast.Name)]
            if "r" not in names:
                continue
            op = n.ops[-1]
            k = str(n.comparators[-1].right.value)
            out[(os.path.relpath(path, root), n.lineno)] = classify("<=" if isinstance(op, ast.LtE) else "<", k)
    return out


def main():
    args = sys.argv[1:]
    root = DEFAULT_ROOT
    jpath = None
    if "--root" in args:
        root = os.path.abspath(args[args.index("--root") + 1])
    if "--json" in args:
        jpath = args[args.index("--json") + 1]
    a, b = enum_grep(root), enum_ast(root)
    allk = sorted(set(a) | set(b))
    rows = []
    for k in allk:
        rows.append(dict(file=k[0], line=k[1], grep=a.get(k), ast=b.get(k)))
        print("[enum] %-60s %4d  grep=%-5s ast=%-5s" % (k[0], k[1], a.get(k), b.get(k)))
    # 突合 (grep vs AST) は .py のみ (AST は python 専用。.sh/.mjs 等は grep のみで列挙し件数を別掲)
    mism = [r for r in rows if r["file"].endswith(".py") and r["grep"] != r["ast"]]
    nonpy = [r for r in rows if not r["file"].endswith(".py")]
    old = [r for r in rows if ("OLD" in (r["grep"] or "") or "OLD" in (r["ast"] or ""))
           and (r["file"], r["line"]) not in INTENDED_OLD]
    for r in rows:
        if (r["file"], r["line"]) in INTENDED_OLD:
            print("[enum] 意図的な旧式 (許可): %s:%d  %s" % (r["file"], r["line"], INTENDED_OLD[(r["file"], r["line"])]))
    print("[enum] grep のみで列挙 (非 .py): %d 件" % len(nonpy))
    print("[enum] root=%s 件数 grep=%d ast=%d 和集合=%d 不一致=%d OLD=%d" % (root, len(a), len(b), len(rows), len(mism), len(old)))
    if jpath:
        json.dump(dict(root=root, rows=rows, mismatch=len(mism), old=len(old)), open(jpath, "w"), indent=1, ensure_ascii=False)
    if not rows:
        print("[enum] FAIL: 1 件も見つからない (列挙ロジックが壊れている)")
        return 1
    if mism:
        print("[enum] FAIL: grep 系と AST 系で列挙が一致しない")
        return 1
    if old:
        print("[enum] FAIL: 旧境界 (末尾 8B slot が落ちる) が残っている")
        return 1
    print("[enum] PASS: 旧境界 0 件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
