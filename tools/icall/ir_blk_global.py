#!/usr/bin/env python3
"""ir_blk_global.py — route 側 (ott_route.sh) の BLK 参照を module-local global `@__icall_blk` への GEP へ張り替える (#2865, opt-in)。

  python3 ir_blk_global.py IN.ll OUT.ll --map map.json

  入力は ir_normalize / ir5_patch 後の opaque ptr 形 (`inttoptr i64 N to ptr`) の IR。BLK 範囲 [blk, blk+0x200) の
  参照は、restore の rax/comis 読出し (+0x80・+0xb0) を含め全て置き換える。一部だけ置き換えると、body 側が固定 VA の
  BLK を、runtime が global の BLK を見るため、BLK が二重になる。置換の本体は liftlib の leaf 経路と同じ
  `liftlib.passes.icall.blk_global_text`。runtime 側は ott_route.sh が `-DICALL_BLK_GLOBAL` で揃える。
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "liftlib"))
from liftlib.passes.icall import blk_global_text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--map", required=True)
    a = ap.parse_args()
    blk = json.load(open(a.map))["blk"]
    text, n = blk_global_text(open(a.src, errors="replace").read(), blk)
    open(a.dst, "w").write(text)
    print(json.dumps({"blk": blk, "icall_blk_global": n}))


if __name__ == "__main__":
    main()
