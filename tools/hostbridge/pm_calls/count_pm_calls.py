#!/usr/bin/env python3
"""HB-H18 (#788): Fruity Wrapper が PluginManager 由来の機能を呼ぶかを実測で数える.

使い方: python3 count_pm_calls.py <PE> [<PE> ...]
  出力: (1) PluginManager 固有文字列の出現数 (ASCII / UTF-16LE)
        (2) プロセス起動・DLL ロード系 import (IAT) への直接 call 箇所数 (E8 thunk 経由 + FF 15 直接)
        (3) ShellExecute* の lpFile 定数文字列 (解決できたもの)
陽性対照: PluginManager 本体 (block25160) は (1) が >0 でなければ検出器が盲目 → FAIL.
陰性: Wrapper (block19091/23676) は PluginManager 文字列 0 件なら「Wrapper は PluginManager を名指しで呼ばない」.
"""
import sys, struct, pefile
from collections import defaultdict

PM_STRINGS = ["PluginManager", "Plugin Manager", "Plugin database", "deepscan", "vstpath",
              "InterprocessPluginScan", "-flcaption"]
LAUNCH_APIS = {"ShellExecuteA", "ShellExecuteW", "ShellExecuteExW", "CreateProcessW",
               "CreateProcessA", "WinExec"}


def count_strings(data):
    out = {}
    for s in PM_STRINGS:
        a = data.count(s.encode("ascii"))
        u = data.count(s.encode("utf-16le"))
        if a or u:
            out[s] = (a, u)
    return out


def iat_sites(pe, img):
    base = pe.OPTIONAL_HEADER.ImageBase
    imp = {}
    for e in pe.DIRECTORY_ENTRY_IMPORT:
        for i in e.imports:
            if i.name:
                imp[i.address] = i.name.decode()
    sites = defaultdict(list)
    text = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".text"][0]
    lo = text.VirtualAddress
    code = img[lo:lo + text.Misc_VirtualSize]
    thunk = {}
    for i in range(len(code) - 6):
        if code[i] == 0xFF and code[i + 1] == 0x25:
            slot = base + lo + i + 6 + struct.unpack_from("<i", code, i + 2)[0]
            if slot in imp and imp[slot] in LAUNCH_APIS:
                thunk[base + lo + i] = imp[slot]
    for i in range(len(code) - 6):
        if code[i] == 0xE8:
            t = base + lo + i + 5 + struct.unpack_from("<i", code, i + 1)[0]
            if t in thunk:
                sites[thunk[t]].append(base + lo + i)
        elif code[i] == 0xFF and code[i + 1] == 0x15:
            slot = base + lo + i + 6 + struct.unpack_from("<i", code, i + 2)[0]
            if slot in imp and imp[slot] in LAUNCH_APIS:
                sites[imp[slot]].append(base + lo + i)
    return sites


def main(paths):
    rc = 0
    for p in paths:
        pe = pefile.PE(p)
        data = open(p, "rb").read()
        img = pe.get_memory_mapped_image()
        print("==", p)
        strs = count_strings(data)
        print("  PM 固有文字列 (ascii,utf16):", strs if strs else "0 件")
        sites = iat_sites(pe, img)
        for k in sorted(sites):
            print("  起動/ロード API", k, len(sites[k]), [hex(x) for x in sites[k]])
        if not sites:
            print("  起動/ロード API: 0 件")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
