"""SR-36 #2065: canvas の描画系関数のうち、本体が no-op のものを数える (静的計数)。

判定: 本体 (コメント除去・`(void)x;` 除去後) が空、または `return false;` `return nullptr;` `return 0.;`
`return -1.;` `return {};` `return;` のみ、を no-op とする。本体が 1 文でも実処理があれば実装ありとする。
対象: 関数名が draw・clearRect・fill (fillMode を除く) で始まるもの (描画命令)、set / save / restore で始まるもの (状態設定)。
usage: python3 count_canvas_noop.py   (cwd は gui/ でも canvas/ でもよい)
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ["canvas_graphicsdevice.cpp", "canvas_graphicspath.cpp", "canvas_font.cpp", "canvas_bitmap.cpp", "canvas_frame.cpp", "canvas_string.cpp"]
DRAW = re.compile(r"^(draw|clearRect|fill(?!Mode))")
STATE = re.compile(r"^(set|save|restore)")
FUNC = re.compile(r"(?P<sig>[^{};]*?)\{(?P<body>[^{}]*)\}", re.S)
NOOP_BODY = {"", "return false;", "return nullptr;", "return 0.;", "return -1.;", "return {};", "return;"}


def classify(body):
    b = re.sub(r"//[^\n]*", "", body)
    b = re.sub(r"\(void\)\s*[\w:.]+;", "", b)
    b = re.sub(r"\s+", " ", b).strip()
    return "noop" if b in NOOP_BODY else "impl"


def funcs(text):
    for m in FUNC.finditer(text):
        sig = m.group("sig")
        names = re.findall(r"(\w+)\s*\(", sig)
        if not names:
            continue
        yield names[-1], classify(m.group("body"))


def main():
    totals = {"draw": [0, 0], "state": [0, 0]}
    rows = []
    for f in FILES:
        path = os.path.join(HERE, f)
        if not os.path.exists(path):
            continue
        text = open(path, encoding="utf-8").read()
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        for name, kind in funcs(text):
            if DRAW.match(name):
                cat = "draw"
            elif STATE.match(name):
                cat = "state"
            else:
                continue
            totals[cat][0] += 1
            if kind == "noop":
                totals[cat][1] += 1
            rows.append((f, cat, name, kind))
    for f, cat, name, kind in rows:
        print(f"{cat:5s} {kind:4s} {f} {name}")
    for cat, (n, k) in totals.items():
        print(f"TOTAL {cat}: functions={n} noop={k} impl={n - k}")


if __name__ == "__main__":
    sys.exit(main())
