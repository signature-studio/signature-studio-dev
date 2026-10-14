"""SR-19 #1351: PoC 境界 (CTextLabel + XferOnOffButton 系) が要る upstream VSTGUI ソースの対象量を実測する。

入力: work/vstgui4/vstgui (vstgui4_14_3 の clone, depth 1)
出力: stdout。工数 (人日) は測らない。対象量 (ファイル数・行数・バイト) のみ。

方法: PoC の起点クラス宣言ファイルから、vstgui/ 内の #include "..." を再帰的に辿る (include 閉包)。
platform/ 以下は canvas 実装で置き換える前提のため、閉包とは別に集計する。
"""
import os
import re
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "work/vstgui4/vstgui"
SEEDS = ["CTextLabel", "CViewContainer", "CView", "CControl", "CBitmap", "CDrawContext"]
INC = re.compile(r'^\s*#\s*include\s+"([^"]+)"', re.M)

files = {}
for dp, dn, fn in os.walk(ROOT):
    if "tests" in dp.split(os.sep):
        continue
    for f in fn:
        if f.endswith((".h", ".cpp", ".mm")):
            p = os.path.join(dp, f)
            files[os.path.relpath(p, ROOT)] = p


def decl_files(name):
    pat = re.compile(rf"^\s*(class|struct)\s+{re.escape(name)}\b", re.M)
    hit = []
    for rel, p in files.items():
        if rel.endswith(".h") or rel.endswith(".cpp"):
            with open(p, encoding="utf-8", errors="replace") as fh:
                if pat.search(fh.read()):
                    hit.append(rel)
    return hit


def resolve(inc, frm):
    cand = [os.path.normpath(os.path.join(os.path.dirname(frm), inc)),
            os.path.normpath(inc)]
    for c in cand:
        if c in files:
            return c
    return None


def closure(starts):
    seen, stack = set(), list(starts)
    while stack:
        rel = stack.pop()
        if rel in seen or rel not in files:
            continue
        seen.add(rel)
        with open(files[rel], encoding="utf-8", errors="replace") as fh:
            for m in INC.finditer(fh.read()):
                r = resolve(m.group(1), rel)
                if r:
                    stack.append(r)
    return seen


def size(rels):
    lines = nbytes = 0
    for r in rels:
        b = open(files[r], "rb").read()
        nbytes += len(b)
        lines += b.count(b"\n")
    return lines, nbytes


seed_files = []
for s in SEEDS:
    d = decl_files(s)
    print(f"seed {s}: decl {d}")
    seed_files += d

cl = closure(seed_files)
plat = {r for r in cl if r.startswith("lib" + os.sep + "platform") or r.startswith("platform")}
non_plat = cl - plat
l1, b1 = size(non_plat)
l2, b2 = size(plat)
print("include closure (non-test, vstgui/ 内):", len(cl), "files")
print("  excluding platform/:", len(non_plat), "files /", l1, "lines /", b1, "B")
print("  platform/ only    :", len(plat), "files /", l2, "lines /", b2, "B")

COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)
PURE = re.compile(r"\bvirtual\b[^;{}]*?=\s*0\s*;", re.S)
iface = sorted(r for r in files if r.startswith(os.path.join("lib", "platform") + os.sep)
               and (os.path.basename(r).startswith("iplatform") or os.path.basename(r) == "platformfactory.h")
               and r.endswith(".h"))
print("canvas interface (lib/platform/iplatform*.h + platformfactory.h):", len(iface), "files")
total = 0
rows = []
for r in iface:
    with open(files[r], encoding="utf-8", errors="replace") as fh:
        n = len(PURE.findall(COMMENT.sub("", fh.read())))
    rows.append((r, n))
    total += n
for r, n in rows:
    print(f"  {n:3d}  {r}")
print("pure virtual functions:", total)
