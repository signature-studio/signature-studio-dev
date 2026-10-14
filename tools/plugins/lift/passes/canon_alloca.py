#!/usr/bin/env python3
# RetDec の alloca 並び非決定を正規化する (LIFTLIB-11 / #887 の canon_alloca_order を lift 段から呼ぶ薄いラッパ)。
#
# python3 canon_alloca.py IN.ll OUT.ll
#
# 正本の実装は tools/liftlib/liftlib/passes/base.py の canon_alloca_order。ここでは import して適用するだけ。

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "liftlib"))

from liftlib.passes.base import canon_alloca_order  # noqa: E402

if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    with open(src) as f:
        text = f.read()
    with open(dst, "w") as f:
        f.write(canon_alloca_order(text))
