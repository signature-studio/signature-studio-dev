#!/usr/bin/env python3
"""VSTGUI 版 (13.x / 14.x) の判定: 版ごとに差のある配置名リテラルのバイナリ出現を見る。

前提: work/vstgui4 は steinbergmedia/vstgui の blobless clone (git -C work/vstgui4 grep が使える)。
入力: work/Serum2_win64.vst3 (REPORT §9-1 の手順で展開)。
出力: 版ごとの「製品コード (tests/ 除外) に存在する 9 配置名」件数と、バイナリ内の出現件数。
"""
import subprocess
import sys

VSTGUI = "work/vstgui4"
BIN = "work/Serum2_win64.vst3"
NINE = ["top-left", "top-center", "top-right", "middle-left", "middle-center",
        "middle-right", "bottom-left", "bottom-center", "bottom-right"]
TAGS = ["vstgui4_13_0", "vstgui4_13_3", "vstgui4_14_0", "vstgui4_14_3"]


def product_hits(tag, s):
    out = subprocess.run(["git", "-C", VSTGUI, "grep", "-l", "-F", f'"{s}"', tag, "--", "vstgui/"],
                         capture_output=True, text=True).stdout
    return [p for p in out.splitlines() if "/tests/" not in p]


def main():
    data = open(BIN, "rb").read()
    for tag in TAGS:
        files = {s: len(product_hits(tag, s)) for s in NINE}
        n_files_ok = sum(1 for v in files.values() if v > 0)
        print(f"{tag}: 製品コードに出現する配置名 {n_files_ok}/9")
    print("バイナリ内 (ASCII) の出現件数:")
    for s in NINE:
        print(f"  {s}: {data.count(s.encode())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
