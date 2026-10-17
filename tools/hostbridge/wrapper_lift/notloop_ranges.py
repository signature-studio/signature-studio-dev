"""#5743: 飛び先 VA を含む関数の範囲 (lo-hi) を .pdata から引く。

使い方: FL_WIN64_DIR=<fl-win64 展開先>/extracted python3 tools/hostbridge/wrapper_lift/notloop_ranges.py <VA>...
出力: 1 行 1 VA。`<飛び先VA> <関数 begin>-<関数 end>` (範囲が引けなければ `<VA> NORANGE`)。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "liftlib"))
from liftlib.pe import Image  # noqa: E402

PE = os.path.join(os.environ["FL_WIN64_DIR"], "block19091_PE.bin")


def main() -> None:
    img = Image(PE)
    for arg in sys.argv[1:]:
        va = int(arg, 16)
        f = img.func_at(va)
        if f is None:
            print(f"{arg} NORANGE")
        else:
            print(f"{arg} {f[0]:#x}-{f[1]:#x}")


if __name__ == "__main__":
    main()
