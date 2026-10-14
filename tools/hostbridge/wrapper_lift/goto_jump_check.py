"""RetDec 出力 C の `// break -> 0x<VA>` (goto 相当) の飛び先を、機械語の jump と照合する (#1679)。

使い方 (cwd=リポジトリルート):
  FL_WIN64_DIR=<fl-win64 展開先>/extracted python3 tools/hostbridge/wrapper_lift/goto_jump_check.py <c_dir>
判定: 各 `// break -> 0x<VA>` の関数範囲 (`// Address range:`) を線形 decode し、
      飛び先 VA への直接 jump (j*) が存在すれば jump_in_machine_code、無ければ no_jump_to_target。
"""
import collections
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "liftlib"))
from capstone import Cs, CS_ARCH_X86, CS_MODE_64  # noqa: E402
from liftlib.pe import Image  # noqa: E402

BRK = re.compile(r"^\s*// break(?: \(via goto\))? -> (0x[0-9a-f]+)\s*$")
FUNC = re.compile(r"^// Address range: 0x([0-9a-f]+) - 0x([0-9a-f]+)")


def main():
    src = sys.argv[1]
    img = Image(os.path.join(os.environ["FL_WIN64_DIR"], "block19091_PE.bin"))
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    cnt = collections.Counter()
    cache = {}
    for f in sorted(os.listdir(src)):
        if not f.endswith(".c"):
            continue
        cur = None
        for x in open(os.path.join(src, f), errors="replace").read().split("\n"):
            m = FUNC.match(x)
            if m:
                cur = (int(m.group(1), 16), int(m.group(2), 16))
                continue
            b = BRK.match(x)
            if not b or cur is None:
                continue
            tgt = int(b.group(1), 16)
            if cur not in cache:
                lo, hi = cur
                cache[cur] = {int(i.op_str, 16) for i in md.disasm(img.read(lo, hi - lo), lo)
                              if i.mnemonic.startswith("j") and i.op_str.startswith("0x")}
            cnt["jump_in_machine_code" if tgt in cache[cur] else "no_jump_to_target"] += 1
    print(dict(cnt))


if __name__ == "__main__":
    main()
