#!/usr/bin/env python3
# M2-4: shim inventory 自動生成。
#
# win64 FLEEngine_x64.dll (PE32+) / mac FLEEngine x86_64 slice (Mach-O)
# / mac libwinbridge_x64 slice の import・export 一覧を走査して、
# strategy.md §3 shim 表 (12 行) への写影表を機械生成する。
#
# 入力仕様 (スライサーに extract_slice.py を使う: ファイルが universal2 の場合):
#   --win-dll        : win64 FLEEngine_x64.dll (blocks31 等, 抽出物)
#   --win-scan-json  : pescan.py の出力 (imports/exports/IAT)
#   --mac-dylib      : mac FLEEngine x86_64 slice (Mach-O)
#   --winbridge-dylib: mac libwinbridge slice (FAT も可)
#   --out-md         : 出力 SHIM_INVENTORY.md
#   --out-json       : 出力 shim_inventory.json
#
# 出力: §3 の各行 (#1..#12) に対して
#   - win 側: import 名の一致数 + 代表名
#   - mac 側: (winbridge が担う面 / Core* 依存) を categories 別に記載
#   - winbridge export との機械対応 (snake-free 名前突合: 先頭 _ 除く)

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def die(msg: str):
    print(f"[shim_inventory] FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def fat_headers(path):
    data = open(path, "rb").read(65536)
    import struct
    if len(data) < 8:
        return None
    magic, = struct.unpack(">I", data[0:4])
    if magic != 0xCAFEBABE:
        return None
    narch, = struct.unpack(">I", data[4:8])
    archs = []
    for i in range(narch):
        off = 8 + i * 20
        cpu, _sub, aoff, asize, _align = struct.unpack(">5I", data[off:off + 20])
        archs.append({"cpu": cpu, "offset": aoff, "size": asize})
    return archs


def ensure_slice(path, workdir, arch="x86_64"):
    """FAT の場合 slice を workdir に切出してパスを返す (elf/binary のまま返す)。"""
    archs = fat_headers(path)
    if not archs:
        return path
    stalled = None
    for a in archs:
        if a["cpu"] == 0x01000007:
            stalled = a
            break
    if stalled is None or a is None:
        die(f"x86_64 slice が FAT 内にありません: {path}")
    out = os.path.join(workdir, os.path.basename(path).replace("_x64", "") + "_x86_64")
    if not os.path.exists(out):
        data = open(path, "rb").read()
        open(out + ".dylib", "wb").write(data[stalled["offset"]: stalled["offset"] + stalled["size"]])
        out += ".dylib"
    return out


def macho_scan(path):
    """llvm-objdump を用いて Mach-O slice の imports (bind 情報) と exports を採る。"""
    imports = {}   # dylib -> set(symbol)
    exports = []
    for opt in ("--lazy-bind", "--bind", "--weak-bind"):
        text = subprocess.check_output(
            ["llvm-objdump", "--macho", opt, path], text=True, errors="replace")
        for line in text.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[0] == "__DATA" or \
                    len(parts) >= 6 and parts[0] == "__DATA":
                sym = parts[-1]
                dylib = parts[-2]
                if sym.startswith("_"):
                    sym = sym[1:]
                imports.setdefault(dylib, set()).add(sym)
    text = subprocess.check_output(
        ["llvm-objdump", "--macho", "--exports-trie", path], text=True, errors="replace")
    for line in text.splitlines():
        if line.startswith("0x"):
            sym = line.split()[1] if len(line.split()) > 1 else ""
            if sym.startswith("_"):
                sym = sym[1:]
            exports.append(sym)
    # LC_LOAD_DYLIB (依存 dylib 面)
    loadcmds = subprocess.check_output(
        ["llvm-objdump", "--macho", "-p", path], text=True, errors="replace")
    dylibs = []
    for line in loadcmds.splitlines():
        if "name " in line:
            n = line.split("name ", 1)[1]
            dylibs.append(n.strip())
    return imports, sorted(set(exports)), dylibs


# ---------------------------------------------------------------------------

SHIM_ROWS = [
    # (no, キーワード (正規表現の prefix list), 説明)
    ("1", "DirectSound / ASIO → AudioWorklet + SAB",
     ["DirectSound", "EnumerateA", "ASIO", "waveOut", "waveIn", "auxGet"]),
    ("2", "Win32 FS → Emscripten FS",
     ["CreateFile", "ReadFile", "WriteFile", "SetFilePointer", "CloseHandle",
      "FindFirstFile", "FindNextFile", "DeleteFile", "MoveFile", "CopyFile",
      "CreateDirectory", "GetFileAttributes", "GetOpenFileName", "GetSaveFileName"]),
    ("3", "time / .timer → performance",
     ["QueryPerformanceCounter", "QueryPerformanceFrequency", "timeGetTime",
      "timeBeginPeriod", "GetTickCount", "SetTimer", "KillTimer", "SleepEx"]),
    ("4", "thread / 同期 → pthread (SAB) + Atomics",
     ["CreateThread", "TerminateThread", "ExitThread", "CreateEvent", "SetEvent",
      "ResetEvent", "WaitForSingleObject", "WaitForMultipleObjects",
      "EnterCriticalSection", "LeaveCriticalSection", "InitializeCriticalSection",
      "DeleteCriticalSection", "Sleep", "TlsAlloc", "TlsGetValue", "TlsSetValue"]),
    ("5", "GUI / MSG / GDI / Cocoa → OffscreenCanvas",
     ["RegisterClass", "CreateWindow", "GetMessage", "TranslateMessage",
      "DispatchMessage", "SendMessage", "PostMessage", "PeekMessage",
      "BeginPaint", "EndPaint", "BitBlt", "StretchDIBits", "TextOut",
      "GetDC", "ReleaseDC", "InvalidateRect", "CreateFont", "SelectObject",
      "SetPixel", "GetDeviceCaps", "wgl", "opengl32"]),
    ("6", "registry → メモリ (IndexedDB)",
     ["RegOpenKey", "RegCreateKey", "RegQueryValue", "RegSetValue", "RegCloseKey",
      "RegDeleteKey", "RegDeleteValue", "RegEnumKey", "RegEnumValue"]),
    ("7", "module / heap → 自前実装",
     ["LoadLibrary", "GetProcAddress", "FreeLibrary", "GetModuleHandle",
      "VirtualAlloc", "VirtualProtect", "VirtualFree", "HeapCreate", "HeapAlloc",
      "HeapFree", "HeapReAlloc", "GetProcessHeap", "GetProcessHeap"]),
    ("8", "CRT / libc (Delphi RTL 面外の不足部) → Emscripten libc",
     ["memcpy", "memset", "memcmp", "strlen", "strcpy", "sprintf", "printf",
      "malloc", "free", "memcpy", "wcslen", "isspace"]),
    ("9", "外部プロセス起動 / dlopen 外部依存 → stub",
     ["CreateProcess", "ShellExecute", "WinExec", "WaitForInputIdle"]),
    ("10", "MIDI → Web MIDI API",
     ["midiIn", "midiOut", "midiStream", "CMIDI"]),
    ("11", "ネットワーク / 認証 / クラウド → stub",
     ["InternetOpen", "InternetOpenUrl", "HttpSendRequest", "WinHttp",
      "WSAStartup", "socket", "connect", "send ", "recv", "bind(",
      "InternetConnect", "HttpOpenRequest", "WinInet"]),
    ("12", "プラグイン ABI ホスト (FL 内部ジェネレータIF)",
     ["CreateFruityInstance"]),
]


def match_names(names, keys):
    hits = [n for n in names if any(k.lower() in n.lower() for k in keys)]
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--win-dll", required=True)
    ap.add_argument("--win-scan-json", required=True)
    ap.add_argument("--mac-dylib", required=True)
    ap.add_argument("--winbridge-dylib", required=True)
    ap.add_argument("--out-md", required=True)
    ap.add_argument("--out-json", required=True)
    args = ap.parse_args()

    scan = json.load(open(args.win_scan_json))
    imports = scan.get("imports", {})   # dll -> [name]
    win_exports = list(scan.get("exports", {}).keys())

    win_names = [n for v in imports.values() for n in v]

    workdir = os.path.dirname(os.path.abspath(args.out_json))
    if not os.path.isdir(workdir):
        os.makedirs(workdir, exist_ok=True)
    mac_path = args.mac_dylib
    winb_path = ensure_slice(args.winbridge_dylib, workdir)

    mac_imports, mac_exports, mac_dylibs = macho_scan(mac_path)
    winb_imports, winb_exports, winb_dylibs = macho_scan(winb_path)

    winb_stripped = set(winb_exports)
    win_not_covered = []
    for n in win_names:
        if n in winb_stripped:
            continue
        win_not_covered.append(n)

    # §3 12 行への写影
    rows = []
    for no, title, keys in SHIM_ROWS:
        win_hits = match_names(win_names, keys)
        mac_hits = match_names(sum((list(v) for v in mac_imports.values()), []), keys)
        rows.append({
            "no": no, "title": title, "keys": keys,
            "win_count": len(win_hits), "win_examples": sorted(win_hits)[:25],
            "mac_count": len(mac_hits), "mac_examples": sorted(mac_hits)[:25],
        })

    out = {
        "win_dll": args.win_dll,
        "win_imports": {k: v for k, v in imports.items()},
        "win_import_names": len(win_names),
        "win_export_names": win_exports,
        "mac_dylib": args.mac_dylib,
        "mac_imports": {k: sorted(v) for k, v in mac_imports.items()},
        "mac_exports": mac_exports,
        "mac_dylibs": mac_dylibs,
        "winbridge_dylib": args.winbridge_dylib,
        "winbridge_imports": {k: sorted(v) for k, v in winb_imports.items()},
        "winbridge_exports": winb_exports,
        "winbridge_dylib_deps": winb_dylibs,
        "win_imports_not_in_winbridge_exports": sorted(win_not_covered),
        "shim_rows": rows,
    }
    with open(args.out_json, "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)

    # --------- markdown ---------
    md = []
    md.append("# SHIM_INVENTORY (M2 機械生成 + 人手チェック版)")
    md.append("")
    md.append("自動生成: `tools/m2/shim_inventory.py` (win/mac/libwinbridge の "
              "import/export 走査 → strategy.md §3 12 行への写影)。")
    md.append("")

    md.append("## (0) 入力と成立条件")
    md.append("")
    md.append("| 項目 | 値 |")
    md.append("|---|---|")
    md.append(f"| win64 DLL | {args.win_dll} |")
    md.append(f"| win64 import 名数 | {len(win_names)} (依存 DLL {len(imports)}) |")
    md.append(f"| mac slide | {args.mac_dylib} |")
    md.append(f"| mac slice exports | {len(mac_exports)} / imports(外部シンボル) "
              f"{sum(len(v) for v in mac_imports.values())} |")
    md.append(f"| libwinbridge slice | {winb_path} |")
    md.append(f"| libwinbridge exports | {len(winb_exports)} (Win32 shim 面) |")
    md.append("")

    md.append("## (1) libwinbridge exports 一覧 (= shim 実装面の機械採取初版)")
    md.append("")
    for s in winb_exports:
        md.append(f"- `{s}`")
    md.append("")

    md.append("## (2) win64 DLL import 面 → winbridge exports 突合")
    md.append("")
    md.append(f"- win 全 import 名 {len(win_names)} 中、winbridge export 名に **そのまま"
              f"一致するのは {len(win_names) - len(win_not_covered)} 個**"
              f" (覆盖 {len(win_names) - len(win_not_covered)} / {len(win_names)} = "
              f"{100 * (len(win_names) - len(win_not_covered)) / max(1, len(win_names)):.1f}%)")
    md.append(f"- 未覆盖 {len(win_not_covered)} 個 → winbridge に無い import 面"
              f" (mac 版は Cocoa/CoreAudio 系へ置換のため、それらは §3 各行の"
              f"単位で主に自家実装)"
    )
    md.append("")
    md.append("注: mac 版の主target では Win32 API 直呼びが libwinbridge の export 面"
              "と FLEngine 内の platform abstract 化で置換されるため、"
              "上記数値は「参照照合」材料として使う")
    md.append("")

    md.append("## (3) §3 12 行への写影表")
    md.append("")
    md.append("| # | shim | win 側一致数 | mac 側一致数 | win 代表名 |")
    md.append("|---|---|---|---|---|")
    for r in rows:
        ex = ", ".join(f"`{x}`" for x in r["win_examples"][:6])
        md.append(f"| {r['no']} | {r['title']} | {r['win_count']} | "
                  f"{r['mac_count']} | {ex} |")
    md.append("")

    md.append("## (4) mac 側 FLEngine slice の import detail")
    md.append("")
    md.append("| 依存 dylib | シンボル数 |")
    md.append("|---|---|")
    for k in sorted(mac_imports):
        md.append(f"| {k} | {len(mac_imports[k])} |")
    md.append("")
    md.append("**mac slice 依存 dylib 一覧**: " +
              ", ".join(mac_dylibs))
    md.append("")

    md.append("## (5) 注意点 (§3 結合時)")
    md.append("")
    md.append("- 本 inventory は「import 面の静的重み関係」のみを記す。"
              "各 shim 行の実装面 (必要 Win32 依存部分の自家実装量) は §3 表の"
              "工数見積 (P0 40-58人週) とは別に、M4 での単体テストスイートで清掃能力を測定する意図。")
    md.append("- winbridge exports は「PL Registry 面 / DragDrop 面 / WB ソケット等"
              "の小さい意図」に留まる点に留意 (mac shim 面"
              "としては §3 の P0 各行とは別に新規面の増設が必要).")
    md.append("- win 側の registry 面 (advapi32 import) と winbridge の Reg* export は "
              "一対として対応。WinInet/WinHTTP/WSASocket/winspool 等は消去対象・stub 対象で、"
              "§3 注記と §7.3 の遷移記述と対照で評価.")
    md.append("")

    with open(args.out_md, "w") as fh:
        fh.write("\n".join(md))
    print("[shim_inventory] imports/exports scanned:",
          f"win={len(win_names)} mac={sum(len(v) for v in mac_imports.values())} "
          f"winbridge_exports={len(winb_exports)}")
    print(f"[shim_inventory] wrote {args.out_md} / {args.out_json}")


if __name__ == "__main__":
    main()
