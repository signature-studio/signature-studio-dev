#!/usr/bin/env python3
"""gui shim の API 面を生成する。

入力 : analysis/imports_all.json (gui_imports.py 産), src/gui_core.c, src/gui_gdi.c, mingw 由来の arity 表
出力 : build/gui_api.h      — 実装済み + fail-fast stub の lift ABI プロトタイプ (全 int64_t)
       build/gui_stubs.c    — 未実装 import の fail-fast stub (arity は mingw-w64 ヘッダ -aux-info から)
       exports.txt          — 実装済み API 名
       IMPORTS.md           — FL(win) GUI 系 import の優先度付き一覧 (使用頻度 = 静的 xref 推定)
"""
import json, os, re, subprocess, sys, collections

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build"); os.makedirs(BUILD, exist_ok=True)
GUI_DLLS = ["user32.dll", "gdi32.dll", "comctl32.dll", "comdlg32.dll", "opengl32.dll", "uxtheme.dll", "imm32.dll",
            "msimg32.dll", "dwmapi.dll", "winspool.drv", "oleacc.dll", "wtsapi32.dll", "shcore.dll"]
# 本 shim が kernel32 から預かる最小 (テスト/lift 用)
EXTRA_IMPL_K32 = {"ExitProcess", "GetModuleHandleA", "GetModuleHandleW", "OutputDebugStringA", "OutputDebugStringW"}

def impl_names():
    out = collections.OrderedDict()
    for f in ("gui_core.c", "gui_core_ext.inc", "gui_gdi.c"):
        for line in open(os.path.join(HERE, "src", f), encoding="utf-8"):
            m = re.match(r"^API (\w+)\(([^)]*)\) \{", line)
            if m:
                args = m.group(2).strip()
                n = 0 if args in ("", "void") else len([a for a in args.split(",") if a.strip()])
                out[m.group(1)] = n
    return out

def aux_arity():
    """mingw ヘッダの全プロトタイプから name -> argc"""
    aux = os.path.join(BUILD, "aux.txt")
    src = os.path.join(BUILD, "hdr.c")
    open(src, "w").write("#define _WIN32_WINNT 0x0A00\n#define WINVER 0x0A00\n#define NTDDI_VERSION 0x0A000000\n"
        "#include <windows.h>\n#include <commctrl.h>\n#include <imm.h>\n#include <uxtheme.h>\n#include <dwmapi.h>\n"
        "#include <commdlg.h>\n#include <winspool.h>\n#include <oleacc.h>\n#include <wtsapi32.h>\n#include <shellscalingapi.h>\n")
    subprocess.run(["x86_64-w64-mingw32-gcc", "-c", "-aux-info", aux, src, "-o", os.path.join(BUILD, "hdr.o")],
                   check=True, stderr=subprocess.DEVNULL)
    tab = {}
    for line in open(aux, encoding="utf-8", errors="replace"):
        m = re.search(r"extern [^(]*?[ *](\w+) ?\((.*)\);", line)
        if not m: continue
        name, args = m.group(1), m.group(2).strip()
        if args in ("", "void"): n = 0
        else:
            depth = 0; n = 1
            for ch in args:
                if ch == "(": depth += 1
                elif ch == ")": depth -= 1
                elif ch == "," and depth == 0: n += 1
            if args.endswith("..."): n -= 1  # 可変長は固定部のみ
        tab[name] = n
    return tab

# ---- 優先度ルール : (regex, category, base priority) 先勝ち ----
RULES = [
    (r"^(DefFrameProc|DefMDIChildProc|TranslateMDISysAccel|IsDialogMessage|BeginBufferedPaint|EndBufferedPaint|BufferedPaint|MaskBlt|GradientFill|GetBitmapBits|GetDCOrgEx)", "aux", 2),
    (r"^(CallNextHookEx|SetWindowsHookEx|UnhookWindowsHookEx|AttachThreadInput|MsgWaitForMultipleObjects|GetMessageExtraInfo|NotifyWinEvent)", "hook/sync", 1),
    (r"^(GetWindowPlacement|SetWindowPlacement|FindWindow|EnumWindows|EnumChildWindows|EnumThreadWindows|GetDlgItem|SetProp|GetProp|RemoveProp|SetWindowRgn|GetLastActivePopup|ShowOwnedPopups|IsWindowUnicode|GetTopWindow|BeginDeferWindowPos|DeferWindowPos|EndDeferWindowPos|SetClassLong|GetClassLong|GetClassName|ScrollDC|ScrollWindow|CreateDIBitmap|ValidateRgn|GetUpdateRgn)", "window-aux", 1),
    (r"^(RegisterClass|UnregisterClass|GetClassInfo|CreateWindowEx|DestroyWindow|ShowWindow|UpdateWindow|DefWindowProc|CallWindowProc|DefFrameProc|DefMDIChildProc|SetWindowPos|MoveWindow|BeginDeferWindowPos|DeferWindowPos|EndDeferWindowPos|GetWindowLong|SetWindowLong|GetClassLong|SetClassLong|GetParent|SetParent|GetWindow$|GetAncestor|IsWindow|IsChild|EnableWindow|GetDesktopWindow|GetClientRect|GetWindowRect|ClientToScreen|ScreenToClient|MapWindowPoints|AdjustWindowRect|GetWindowPlacement|SetWindowPlacement|GetTopWindow|FindWindow|EnumWindows|EnumChildWindows|EnumThreadWindows|GetWindowThreadProcessId|SetWindowText|GetWindowText|GetClassName|GetDlgItem|SetProp|GetProp|RemoveProp|SetWindowRgn|GetLastActivePopup|ShowOwnedPopups|IsWindowVisible|IsWindowEnabled|IsWindowUnicode|IsIconic|IsZoomed)", "window", 0),
    (r"^(GetMessage|PeekMessage|PostMessage|SendMessage|DispatchMessage|TranslateMessage|PostQuitMessage|WaitMessage|MsgWaitForMultipleObjects|RegisterWindowMessage|PostThreadMessage|GetMessagePos|GetMessageTime|GetMessageExtraInfo|IsDialogMessage|TranslateMDISysAccel|SetTimer|KillTimer|CallNextHookEx|SetWindowsHookEx|UnhookWindowsHookEx|NotifyWinEvent)", "message", 0),
    (r"^(BeginPaint|EndPaint|InvalidateRect|InvalidateRgn|ValidateRect|ValidateRgn|RedrawWindow|GetUpdateRect|GetUpdateRgn|GetDC|GetDCEx|GetWindowDC|ReleaseDC|LockWindowUpdate|ScrollWindow|ScrollDC|ScrollWindowEx|BeginBufferedPaint|EndBufferedPaint|BufferedPaint)", "paint", 0),
    (r"^(SetCapture|ReleaseCapture|GetCapture|SetFocus|GetFocus|SetActiveWindow|GetActiveWindow|GetForegroundWindow|SetForegroundWindow|AttachThreadInput|WindowFromPoint|GetCursorPos|SetCursorPos|GetPhysicalCursorPos|SetPhysicalCursorPos|GetClipCursor|GetKeyState|GetAsyncKeyState|GetKeyboardState|SetKeyboardState|MapVirtualKey|ToAscii|ToUnicode|GetKeyNameText|SendInput|GetCursorInfo|PhysicalToLogicalPoint|LogicalToPhysicalPoint|GetKeyboardLayout|ActivateKeyboardLayout|LoadKeyboardLayout)", "input", 0),
    (r"^(GetSystemMetrics|SystemParametersInfo|GetSysColor|GetDoubleClickTime|GetMonitorInfo|MonitorFromWindow|MonitorFromRect|MonitorFromPoint|EnumDisplayMonitors|EnumDisplaySettings|SetThreadDpi|IsProcessDPIAware|GetDpiForMonitor|GetProcessDpiAwareness|GetGuiResources)", "system", 1),
    (r"^(SetRect|OffsetRect|InflateRect|IntersectRect|UnionRect|SubtractRect|PtInRect|EqualRect|IsRectEmpty|CopyRect|EvaluateProximity|PackTouch|CharNext|CharLower|CharUpper|CharToOem|LoadString|MessageBox|MessageBeep)", "util", 1),
    (r"^(LoadCursor|SetCursor|GetCursor|DestroyCursor|ShowCursor|LoadIcon|LoadImage|LoadBitmap|CopyImage|CreateIcon|DestroyIcon|DrawIcon|GetIconInfo|SetCaretPos|ShowCaret|HideCaret|CreateCaret|DestroyCaret)", "cursor/icon", 1),
    (r"^(FillRect|FrameRect|DrawEdge|DrawFocusRect|DrawFrameControl|DrawText)", "user-draw", 1),
    (r"^(OpenClipboard|CloseClipboard|EmptyClipboard|GetClipboardData|SetClipboardData|RegisterClipboardFormat|EnumClipboardFormats|CountClipboardFormats|IsClipboardFormatAvailable|GetClipboardFormatName)", "clipboard", 1),
    (r".*Menu.*|^(TrackPopupMenu|InsertMenu|RemoveMenu|DeleteMenu|CheckMenuItem|EnableMenuItem|GetSubMenu|GetSystemMenu|SetMenu|GetMenu|DrawMenuBar)", "menu", 2),
    (r".*Scroll.*|^FlatSB_|^InitializeFlatSB", "scrollbar", 2),
    (r"^(SetGestureConfig|GetGestureInfo|CloseGestureInfoHandle|RegisterTouch)", "touch/gesture", 3),
    (r"^Imm", "IME", 2),
    (r"^ImageList_", "imagelist", 2),
    (r"^_TrackMouseEvent", "input", 1),
    (r"^(CreateCompatibleDC|DeleteDC|SelectObject|DeleteObject|GetObject|CreateDIBSection|CreateCompatibleBitmap|CreateBitmap|BitBlt|StretchBlt|StretchDIBits|SetDIBitsToDevice|GetDIBits|SetDIBits|CreateDIBitmap|PatBlt|GdiFlush|AlphaBlend|GradientFill|MaskBlt|SetStretchBltMode|GetStretchBltMode|GetBitmapBits)", "bitmap/blit", 0),
    (r"^(CreateSolidBrush|CreatePen|CreateBrushIndirect|CreatePenIndirect|CreatePatternBrush|GetStockObject|SetBkColor|GetBkColor|SetTextColor|GetTextColor|SetBkMode|SetROP2|SaveDC|RestoreDC|SetWindowOrgEx|GetWindowOrgEx|SetViewportOrgEx|SetMapMode|SetBrushOrgEx|GetBrushOrgEx|LPtoDP|GetDeviceCaps|GetCurrentObject|GetDCOrgEx|CreateDCW|CreateICW)", "dc-state", 1),
    (r"^(CombineRgn|CreateRectRgn|CreateRectRgnIndirect|OffsetRgn|SetRectRgn|SelectClipRgn|ExtSelectClipRgn|IntersectClipRect|ExcludeClipRect|GetClipBox|GetClipRgn|GetRgnBox|EqualRgn|RectInRegion|GetRandomRgn|GetRegionData|CreatePolygonRgn|FrameRgn|RectVisible)", "clip/region", 1),
    (r"^(MoveToEx|LineTo|Rectangle|SetPixelV|SetPixel|GetPixel|GetCurrentPositionEx|Polyline|Polygon|Ellipse|RoundRect|Arc|ArcTo|AngleArc|Chord|Pie|PolyBezier|PolyBezierTo|ExtFloodFill|BeginPath|EndPath|SelectClipPath)", "gdi-vector", 2),
    (r"^(TextOut|ExtTextOut|GetTextExtentPoint|GetTextMetrics|SetTextAlign|GetTextAlign|CreateFont|EnumFont|CreateFontIndirect)", "text/font", 1),
    (r".*Palette.*|^(RealizePalette|UnrealizePalette|ResizePalette|GetNearestPaletteIndex|CreateHalftonePalette|SelectPalette|GetDIBColorTable|SetDIBColorTable|UnrealizeObject)", "palette", 2),
    (r".*EnhMetaFile.*|.*WinMetaFile.*|^(PlayEnhMetaFile|CopyEnhMetaFile|GetEnhMetaFile)", "metafile", 3),
    (r"^(StartDoc|EndDoc|StartPage|EndPage|SetAbortProc|EnumPrinters|OpenPrinter|ClosePrinter|DocumentProperties|GetDefaultPrinter)", "printing", 3),
    (r"^wgl", "opengl", 3),
    (r"^(GetOpenFileName|GetSaveFileName)", "dialog", 2),
    (r"^(DwmExtendFrame|DwmIsComposition|WTS|LresultFromObject)", "shell-integration", 3),
]

def categorize(name):
    for rx, cat, base in RULES:
        if re.match(rx, name):
            return cat, base
    return "other", 2

def priority(name, xref, cat, base):
    p = base
    if xref >= 20 and p > 0: p -= 1
    if xref <= 2 and p < 3 and cat not in ("window", "message", "paint", "bitmap/blit"): p += 1
    return min(p, 3)

def emit_reach(impl, stubs, gui):
    """到達 API ログ / rename / i64 wrapper の生成 (CAB-156)。
    build/gui_reach_tab.c  : 名前昇順の表 {name, stub, prio}  (src/gui_reach.c が参照; 全ビルドでリンク)
    build/gui_rename.h     : 全 shim API を gui_impl_<Name> へ改名する #define (wrap/adapt ビルドで shim 本体の TU にだけ -include)
    build/gui_wrap_i64.c   : 公開名 <Name> (lift ABI, 全 int64) -> reach hit -> gui_impl_<Name> の薄い wrapper
    build/gui_reach_tab.json : 表の索引 (gen_adapt.py が adapter に埋める idx 用)"""
    xref = {r["name"]: r["xref"] for r in gui}
    stub_names = {n for n, _ in stubs}
    ar = dict(impl); ar.update(dict(stubs))
    prio = {}
    for r in gui:
        cat, base = categorize(r["name"]); prio[r["name"]] = priority(r["name"], r["xref"], cat, base)
    names = sorted(ar)
    with open(os.path.join(BUILD, "gui_reach_tab.c"), "w") as f:
        f.write("/* generated by gen_api.py — 到達 API ログ表 (名前昇順; prio -1 = FL 非 import) */\n#include <stdint.h>\n"
                "typedef struct { const char *name; uint8_t stub; int8_t prio; } GuiReachEnt;\nconst GuiReachEnt gui_reach_tab[] = {\n")
        for n in names:
            f.write('  { "%s", %d, %d },\n' % (n, 1 if n in stub_names else 0, prio.get(n, -1)))
        f.write("};\nconst int gui_reach_n = %d;\n" % len(names))
    json.dump({"names": names, "stub": sorted(stub_names), "prio": {n: prio.get(n, -1) for n in names}, "arity": ar},
              open(os.path.join(BUILD, "gui_reach_tab.json"), "w"))
    with open(os.path.join(BUILD, "gui_rename.h"), "w") as f:
        f.write("/* generated by gen_api.py — shim 本体 TU 用 (-include)。公開名は gui_wrap_i64.c / gui_adapt_w32.c が再定義する */\n"
                "#ifndef GUI_RENAME_H\n#define GUI_RENAME_H\n")
        for n in names:
            f.write("#define %s gui_impl_%s\n" % (n, n))
        f.write("#endif\n")
    with open(os.path.join(BUILD, "gui_wrap_i64.c"), "w") as f:
        f.write("/* generated by gen_api.py — reach ログ付き lift ABI wrapper (native/wasm 共通) */\n#include <stdint.h>\n"
                "extern void gui_reach_hit(int idx);\n")
        for i, n in enumerate(names):
            a = ar[n]
            ps = ", ".join("int64_t a%d" % k for k in range(a)) if a else "void"
            cs = ", ".join("a%d" % k for k in range(a))
            f.write("extern int64_t gui_impl_%s(%s);\nint64_t %s(%s) { gui_reach_hit(%d); return gui_impl_%s(%s); }\n"
                    % (n, ", ".join(["int64_t"] * a) if a else "void", n, ps, i, n, cs))

def main():
    data = json.load(open(os.path.join(HERE, "analysis", "imports_all.json")))
    impl = impl_names()
    arity = aux_arity()
    gui = [r for r in data["imports"] if r["dll"] in GUI_DLLS]
    gui_names = {r["name"] for r in gui}
    stubs = []; nohdr = []
    for r in gui:
        n = r["name"]
        if n in impl: continue
        if n in arity: stubs.append((n, arity[n]))
        else: nohdr.append(n)
    # 手動 arity (mingw ヘッダ未収録)
    MANUAL = {"EvaluateProximityToRect": 3, "PackTouchHitTestingProximityEvaluation": 2, "RegisterTouchHitTestingWindow": 2,
              "SetThreadDpiHostingBehavior": 1, "SetGestureConfig": 4, "GetGestureInfo": 2, "CloseGestureInfoHandle": 1,
              "PhysicalToLogicalPoint": 2, "LogicalToPhysicalPoint": 2, "SetPhysicalCursorPos": 2, "GetPhysicalCursorPos": 1,
              "RegisterTouchWindow": 2, "BufferedPaintSetAlpha": 3, "BufferedPaintInit": 0, "BufferedPaintUnInit": 0,
              "GetRandomRgn": 3, "GetProcessDpiAwareness": 2, "GetDpiForMonitor": 4, "SetThreadDpiAwarenessContext": 1}
    still = []
    for n in nohdr:
        if n in MANUAL: stubs.append((n, MANUAL[n]))
        else: still.append(n)
    stub_names = {n for n, _ in stubs}
    # --- gui_api.h
    with open(os.path.join(BUILD, "gui_api.h"), "w") as f:
        f.write("/* generated by gen_api.py — lift ABI: 全引数/戻り値 int64_t */\n#ifndef GUI_API_H\n#define GUI_API_H\n#include <stdint.h>\n")
        for n, a in sorted(impl.items()):
            f.write("int64_t %s(%s);\n" % (n, ", ".join(["int64_t"] * a) if a else "void"))
        for n, a in sorted(stubs):
            f.write("int64_t %s(%s);\n" % (n, ", ".join(["int64_t"] * a) if a else "void"))
        f.write("typedef struct { uint64_t va; void *fn; } GuiFnMap;\nvoid gui_register_fnmap(const GuiFnMap *m, int n);\n#endif\n")
    with open(os.path.join(BUILD, "gui_stubs.c"), "w") as f:
        f.write("/* generated by gen_api.py — 未実装 import の fail-fast stub */\n#include <stdint.h>\n"
                "extern void gui_failfast(const char *api, const char *why) __attribute__((noreturn));\n")
        for n, a in sorted(stubs):
            ps = ", ".join("int64_t a%d" % i for i in range(a)) if a else "void"
            f.write('int64_t %s(%s) { gui_failfast("%s", 0); }\n' % (n, ps, n))
    emit_reach(impl, stubs, gui)
    with open(os.path.join(HERE, "exports.txt"), "w") as f:
        f.write("# 実装済み API (gen_api.py 生成)\n")
        for n in sorted(impl): f.write(n + "\n")
        for n in sorted(EXTRA_IMPL_K32 & set(impl)): pass
    # --- IMPORTS.md
    rows = []
    for r in gui:
        cat, base = categorize(r["name"])
        pr = priority(r["name"], r["xref"], cat, base)
        st = "IMPL" if r["name"] in impl else ("STUB" if r["name"] in stub_names else "NOHDR")
        rows.append((pr, -r["xref"], r["dll"], r["name"], cat, st, r["xref"]))
    rows.sort()
    per_dll = collections.OrderedDict()
    for r in data["imports"]:
        d = per_dll.setdefault(r["dll"], [0, 0]); d[0] += 1; d[1] += r["xref"]
    # GUI-3 (#174): 実 FLEngine lift で shim に実到達した API (tools/gui/flengine/e2e.sh が results/*.json を更新する)
    reach = {}; reach_kind = {}
    for fn, tag in (("boot.json", "起動"), ("survey_soft_chain.json", "survey"), ("probe.json", "probe")):
        try:
            for e in json.load(open(os.path.join(HERE, "flengine", "results", fn)))["reach"]:
                reach.setdefault(e["name"], []).append(tag)
                reach_kind.setdefault(e["name"], set()).add(e["kind"])  # 実行時の kind (IMPL / STUB)。静的表 (st) は使わない
        except (OSError, KeyError, ValueError):
            pass
    with open(os.path.join(HERE, "IMPORTS.md"), "w") as f:
        w = f.write
        w("# 自動生成: `python3 tools/gui/analysis/gui_imports.py && python3 tools/gui/gen_api.py`\n\n"
          "> **人手編集禁止** (生成元を直す)。本ファイルは測定・抽出結果の**単一の正本**。\n"
          "> **行数目安**: 自動生成ファイルのため行数上限はなし (`docs/DOC_MAP.md` §1)。\n\n\n")
        w("# FL (win64 FLEngine_x64.dll) GUI 系 import と shim 優先度\n")
        w("自動生成: `python3 tools/gui/analysis/gui_imports.py && python3 tools/gui/gen_api.py` "
          "(入力 `tools/m2/work/block00031_PE.bin` = FLEngine_x64.dll 22,227,016 B)。\n\n")
        w("使用頻度 = `.text` の静的 xref 推定 (FF15/FF25/mov [rip+IAT] と、IAT へ jmp する thunk への E8/E9 call の件数; Ghidra 非使用の推定値)。\n\n")
        w("## 1. DLL 別 import 数 (全 %d 名 / %d DLL; うち delay-load %d)\n\n" % (data["total_imports"], len(per_dll), sum(1 for r in data["imports"] if r["kind"] == "delay")))
        w("| DLL | import 数 | xref 計 | GUI 系 |\n|---|---|---|---|\n")
        for d, (n, x) in sorted(per_dll.items(), key=lambda kv: -kv[1][1]):
            w("| %s | %d | %d | %s |\n" % (d, n, x, "●" if d in GUI_DLLS else ""))
        tot_gui = len(gui); n_impl = sum(1 for r in rows if r[5] == "IMPL"); n_stub = sum(1 for r in rows if r[5] == "STUB"); n_no = sum(1 for r in rows if r[5] == "NOHDR")
        w("\nGUI 系 DLL (%s) の import 合計 **%d 名**: 実装済み **%d** / fail-fast stub **%d** / arity 不明で未生成 **%d**。\n\n" % (", ".join(GUI_DLLS), tot_gui, n_impl, n_stub, n_no))
        w("## 2. 優先度定義\n\n"
          "- **P0** 起動〜描画ループに必須 (ウィンドウ生成・メッセージポンプ・paint・DC/DIB・BitBlt/StretchDIBits)。未実装なら FL が立ち上がらない。\n"
          "- **P1** 通常 UI 操作に必要 (入力状態・テキスト・クリップ/リージョン・カーソル・システム値・クリップボード)。fail-fast で段階導入。\n"
          "- **P2** 周辺 (メニュー・スクロールバー・IME・ImageList・パレット・ベクタ描画・ダイアログ)。\n"
          "- **P3** 当面スコープ外 (印刷・メタファイル・wgl・タッチ/ジェスチャ・Dwm/WTS)。stub のまま。\n\n")
        for p in range(4):
            sub = [r for r in rows if r[0] == p]
            w("## 3.%d P%d (%d 名)\n\n| API | DLL | カテゴリ | xref | 状態 | 実到達 (GUI-3 #174) |\n|---|---|---|---|---|---|\n" % (p, p, len(sub)))
            for r in sub:
                w("| %s | %s | %s | %d | %s | %s |\n" % (r[3], r[2].replace(".dll", ""), r[4], r[6], r[5], "●" + "/".join(reach[r[3]]) if r[3] in reach else ""))
            w("\n")
        if reach:
            gui_names = {r[3]: r for r in rows}
            w("## 4. 実到達ベースの優先順位入力 (GUI-3 #174)\n\n"
              "実 FLEngine の lift (m11 closure) に本 shim を結合して実行し、shim に到達した API (表の「実到達」列: 起動 = DllMain attach / survey = 942 unit 隔離 / probe = 指向呼出)。"
              "回数・分母・手順は `tools/gui/flengine/REPORT.md`、機械可読は `tools/gui/flengine/results/*.json`。\n\n"
              "| 区分 | API (P 分類) |\n|---|---|\n")
            def lab(n): return "%s (P%d)" % (n, gui_names[n][0]) if n in gui_names else n
            w("| 到達 & 実装済み (実行時 kind = IMPL のみ) | %s |\n" % ", ".join(lab(n) for n in sorted(reach) if n in gui_names and reach_kind[n] == {"IMPL"}))
            w("| 到達 & STUB 経路を通った (**実装必須へ昇格**) | %s |\n" % (", ".join(lab(n) for n in sorted(reach) if n in gui_names and reach_kind[n] != {"IMPL"}) or "なし"))
            w("| 到達 & P2/P3 (**P1 以上へ昇格候補**) | %s |\n" % (", ".join(lab(n) for n in sorted(reach) if n in gui_names and gui_names[n][0] >= 2) or "なし"))
            w("| 未到達の P0 (現 m11 到達段では未実行) | %s |\n\n" % ", ".join(r[3] for r in rows if r[0] == 0 and r[3] not in reach))
        w(("## %d. arity 不明 (mingw ヘッダ未収録) で stub 未生成\n\n" % (5 if reach else 4)) + (", ".join(still) if still else "なし") + "\n")
    print("gui imports=%d impl=%d stub=%d nohdr=%d (impl total in sources=%d)" % (tot_gui, n_impl, n_stub, len(still), len(impl)))
    prio = collections.Counter(r[0] for r in rows)
    print("priority:", dict(sorted(prio.items())))
    p0 = [r for r in rows if r[0] == 0]
    print("P0 total=%d impl=%d" % (len(p0), sum(1 for r in p0 if r[5] == "IMPL")))
    p1 = [r for r in rows if r[0] == 1]
    print("P1 total=%d impl=%d" % (len(p1), sum(1 for r in p1 if r[5] == "IMPL")))
    miss0 = [r[3] for r in p0 if r[5] != "IMPL"]
    print("P0 not implemented:", miss0)

if __name__ == "__main__":
    main()
