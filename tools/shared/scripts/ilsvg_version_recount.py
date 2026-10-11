#!/usr/bin/env python3
"""ILSvg version 特定の独立再計算 (規則 37)。

ILSvg_x64.x86_64.dylib の (a) Xcode object ファイル名集合 と (b) namespace 別 class 集合を
upstream repo の各 tag と突合し、data/ilsvg_version.json の結論を再計算する。

Usage: python3 scripts/ilsvg_version_recount.py

数え方の定義 (規則 36):
- .o 集合: Mach-O __TEXT 文字列の /build/ILSvg.build/.../<base>.o を unique に数える
- class 集合: llvm-nm --defined-only の T/t を llvm-cxxfilt し、
  '<ns>::<rest>' の rest の先頭識別子 (class 名) を unique に数える。
  但し rest が class でない free function (svgdom::load 等) も "class 名" として数える
  (低次の近似であり、TAIL の絞り込み材料としてのみ使う)
- tag の class 集合: `git grep -hoE '(class|struct) +[a-z_0-9]+' <tag> -- src` の unique
"""
import subprocess, sys, re, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "work/src"
SVG = ROOT / "work/svg"
DYLIB = ROOT / "work/slices/ILSvg_x64.x86_64.dylib"
CXXFILT = "/opt/emsdk/upstream/bin/llvm-cxxfilt"

def sh(*a, **kw):
    return subprocess.run(a, capture_output=True, text=True, cwd=kw.get("cwd")).stdout

def binary_obj_files():
    # .o 名の basename (64-hex suffix は CMake の名前衝突回避) を取る
    return set(m for m in re.findall(r"Objects-normal/x86_64/([A-Za-z0-9_.]+?)(?:-[0-9a-f]{64})?\.o$",
                                          sh("strings", "-a", str(DYLIB)), re.M))

def binary_classes():
    dem = (SVG / "ilsvg_demangled.txt").read_text()
    out = {}
    for ns in ("svgdom", "svgren", "papki", "utki", "mikroxml", "cssom"):
        s = set()
        for line in dem.split("\n"):
            if line.startswith(ns + "::"):
                rest = line[len(ns) + 2:]
                parts = rest.split("::")
                if len(parts) >= 2:
                    s.add(parts[0])
        out[ns] = s
    return out

def tag_obj_files(repo, tag):
    files = sh("git", "ls-tree", "-r", "--name-only", tag, "--", "src", cwd=SRC / f"cppfw-{repo}").split()
    return set(f.rsplit("/", 1)[-1][:-4] for f in files if f.endswith(".cpp"))

def tag_classes(repo, tag):
    txt = sh("git", "grep", "-hoE", r"(class|struct) +[a-z_0-9]+", tag, "--", "src", cwd=SRC / f"cppfw-{repo}")
    return set(x.split()[-1] for x in txt.split("\n") if x.strip())

def main():
    objs = binary_obj_files()
    cls = binary_classes()
    print(f"[recount] binary .o files: {len(objs)}")
    for ns, c in cls.items():
        print(f"[recount] {ns}: {len(c)} class names")

    # (1) svgdom: .o 集合で range を絞る
    repo = "svgdom"
    tags = [t for t in sh("git", "tag", cwd=SRC / f"cppfw-{repo}").split() if re.match(r"^v?\d+\.\d+\.\d+$", t)]
    match = [t for t in tags if tag_obj_files(repo, t) <= objs]
    print(f"[recount] svgdom tags whose .cpp set ⊆ binary .o set: {len(match)} ({match[0]}..{match[-1]})")

    # (2) svgren: gradient_setter の有無 + path_type/spread_templ の有無 + canvas.cpp
    repo = "svgren"
    tags = [t for t in sh("git", "tag", cwd=SRC / f"cppfw-{repo}").split() if re.match(r"^v?\d+\.\d+\.\d+$", t)]
    ok = []
    for t in tags:
        txt = sh("git", "grep", "-l", "gradient_setter", t, "--", "src", cwd=SRC / f"cppfw-{repo}")
        has_gs = bool(txt.strip())
        has_pt = bool(sh("git", "grep", "-l", "path_type", t, "--", "src", cwd=SRC / f"cppfw-{repo}").strip())
        has_canvas = "canvas.cpp" in tag_obj_files(repo, t) | {f[:-4] for f in tag_obj_files(repo, t)}
        if has_gs and not has_pt and has_canvas:
            ok.append(t)
    print(f"[recount] svgren tags with gradient_setter & canvas.cpp & no path_type: {ok}")

    # (3) AGG: ILSvg がコンパイルした agg_*.o が tag の file set に含まれるか
    ilsvg_agg = set(o for o in objs if o.startswith("agg_"))
    print(f"[recount] ILSvg agg .o count: {len(ilsvg_agg)}")
    repo = "agg"
    agg_tags = [t for t in sh("git", "tag", cwd=SRC / f"cppfw-{repo}").split() if re.match(r"^v?\d+\.\d+\.\d+$", t)]
    for t in agg_tags:
        tset = tag_obj_files(repo, t) | {f[:-4] for f in sh("git", "ls-tree", "-r", "--name-only", t, cwd=SRC / f"cppfw-{repo}").split() if f.endswith(".cpp")}
        tset = set(x.rsplit("/", 1)[-1][:-4] for x in tset)
        if ilsvg_agg <= tset:
            print(f"[recount] agg tag {t} contains all ILSvg agg objects ({len(ilsvg_agg)}/{len(ilsvg_agg)})")
            break
    else:
        print("[recount] agg: no single tag contains all (vendored subset)")

    # (4) papki: dir() 追加日 (2024-02-25) 以降のコミット
    repo = "papki"
    commits = sh("git", "log", "--format=%h %ci", "--until=2025-12-31", "HEAD", cwd=SRC / f"cppfw-{repo}").split("\n")[:3]
    print(f"[recount] papki HEAD-range commits (tag なし): {commits}")

    print("[recount] OK: data/ilsvg_version.json の結論と一致すれば期待値")

if __name__ == "__main__":
    main()
