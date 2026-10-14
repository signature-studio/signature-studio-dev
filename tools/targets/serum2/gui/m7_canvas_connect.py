#!/usr/bin/env python3
"""SR-7 (#68): canvas platform の CanvasFrame を M7 HUD (tools/gui) の surface / out ring へ接続できるかの静的照合。

入力は repo 内のみ: tools/gui/include/gui_proto.h と tools/targets/serum2/gui/canvas/canvas_frame.{h,cpp}・canvas_bitmap.cpp。
出力: CanvasFrame の各 method の本体 (実装 / stub) と、対応する M7 プロトコル記号・判定の表。
記号が gui_proto.h のコード部 (コメントを除く・単語境界で一致) に無ければ exit 1 (対応表の誤記・宣言の欠落を検出する)。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PROTO = ROOT / "tools/gui/include/gui_proto.h"
CANVAS = ROOT / "tools/targets/serum2/gui/canvas"

# method -> (M7 記号, 判定)。判定: 接続可 / 代替可 / 要設計 / 未対応 / 対象外
MAP = {
    "getGlobalPosition": (["GuiSurface", "GUI_CMD_SURF_CHANGE"], "接続可"),
    "setSize": (["GUI_CMD_SURF_CREATE", "GUI_CMD_SURF_CHANGE"], "接続可"),
    "getSize": (["GuiSurface"], "接続可"),
    "getCurrentMousePosition": (["cursor_x"], "接続可"),
    "getCurrentMouseButtons": (["buttons"], "接続可"),
    "getCurrentModifiers": (["GUI_MOD_SHIFT", "GUI_MOD_CTRL", "GUI_MOD_ALT", "GUI_MOD_META"], "接続可"),
    "setMouseCursor": (["GUI_CMD_SET_CURSOR"], "接続可"),
    "invalidRect": (["GUI_CMD_PRESENT", "GUI_CMD_FRAME_END"], "接続可"),
    "scrollRect": (["GUI_CMD_PRESENT"], "代替可"),
    "showTooltip": (["GUI_CMD_SURF_CREATE"], "要設計"),
    "hideTooltip": (["GUI_CMD_SURF_DESTROY"], "要設計"),
    "getPlatformRepresentation": (["pixels"], "要設計"),
    "createPlatformTextEdit": (["GUI_IN_IME", "GUI_CMD_IME_POS"], "要設計"),
    "createPlatformOptionMenu": ([], "未対応"),
    "setupGenericOptionMenu": ([], "要設計"),
    "doDrag": ([], "未対応"),
    "createPlatformViewLayer": ([], "要設計"),
    "onFrameClosed": (["GUI_IN_CLOSE"], "接続可"),
    "convertCurrentKeyEventToText": (["GUI_IN_CHAR"], "接続可"),
    "getPlatformType": ([], "対象外"),
}

STUB_STMT = re.compile(r"^\(void\)\s*\w+\s*;$")
STUB_RET = re.compile(r"^return\s*(false|nullptr|\{\}|k[A-Z]\w*|[A-Za-z_]\w*::\w+|)\s*;$")


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def method_bodies(text):
    """CanvasFrame::NAME ( ... ) { body } を (name, body) で返す。"""
    out = []
    for m in re.finditer(r"CanvasFrame::(\w+)\s*\(", text):
        if m.group(1) == "CanvasFrame":
            continue
        i = text.index("{", m.end())
        depth, j = 0, i
        while True:
            c = text[j]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        out.append((m.group(1), text[i + 1 : j]))
    return out


def has_symbol(code, s):
    return re.search(r"\b" + re.escape(s) + r"\b", code) is not None


def is_stub(body):
    stmts = [s.strip() for s in re.split(r";", body) if s.strip()]
    rest = [s + ";" for s in stmts if not STUB_STMT.match(s + ";") and not STUB_RET.match(s + ";")]
    if rest:
        return False
    return True


def main():
    proto = PROTO.read_text(encoding="utf-8")
    proto_code = strip_comments(proto)
    cpp = strip_comments((CANVAS / "canvas_frame.cpp").read_text(encoding="utf-8"))
    bitmap = strip_comments((CANVAS / "canvas_bitmap.cpp").read_text(encoding="utf-8"))

    rc = 0
    rows = []
    for name, body in method_bodies(cpp):
        symbols, verdict = MAP[name]
        missing = [s for s in symbols if not has_symbol(proto_code, s)]
        if missing:
            rc = 1
        stub = is_stub(strip_comments(body))
        sym = " / ".join(symbols) if symbols else "—"
        flag = " (MISSING: " + ", ".join(missing) + ")" if missing else ""
        rows.append((name, "stub" if stub else "実装", sym + flag, verdict))

    print("| method | 本体 | M7 記号 (gui_proto.h) | 判定 |")
    print("|---|---|---|---|")
    for r in rows:
        print("| {} | {} | {} | {} |".format(*r))

    total = len(rows)
    stub_n = sum(1 for r in rows if r[1] == "stub")
    print()
    print("定義数 {} / stub {} / 実装 {}".format(total, stub_n, total - stub_n))
    for v in ("接続可", "代替可", "要設計", "未対応", "対象外"):
        print("{}: {}".format(v, sum(1 for r in rows if r[3] == v)))

    canvas_fmt = "RGBA" if re.search(r"IPlatformBitmapPixelAccess::kRGBA", bitmap) else "不明"
    # 画素形式は宣言行のコメントにしか無いので、コメントを除かず pixels 宣言行で見る
    m7_fmt = "BGRA32" if re.search(r"uint32_t\s+pixels;[^\n]*BGRA32", proto) else "不明"
    print("画素形式: canvas bitmap = {} / M7 surface = {} / 不一致 = {}".format(
        canvas_fmt, m7_fmt, canvas_fmt != m7_fmt))
    return rc


if __name__ == "__main__":
    sys.exit(main())
