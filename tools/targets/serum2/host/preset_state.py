#!/usr/bin/env python3
# SR-46 (#2384): factory .SerumPreset を processor 側の state (XferJson) に直す。
# usage: python3 preset_state.py <preset.SerumPreset> <seed_processor_state.bin> <out.json> [exact|overlay]
#   preset       .SerumPreset (XferJson: meta JSON + u32 展開後長 + u32 版本 + zstd(CBOR))。
#   seed         既定 Init の processor state (ref_render.sh の save-only 実行が出す saved_processor_state.bin)。
#   out.json     processor_state.json として host に渡す XferJson。
#   exact        preset の DOM をそのまま使う。
#   overlay      seed の DOM に preset の DOM を重ねる (preset に無い key は seed の既定値)。
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import payload_codec as pc  # noqa: E402

src, seed, dst = sys.argv[1], sys.argv[2], sys.argv[3]
mode = sys.argv[4] if len(sys.argv) > 4 else "overlay"
assert mode in ("exact", "overlay"), "mode must be exact|overlay"

_, pdom, _ = pc.split_state(open(src, "rb").read())
smeta, sdom, sver = pc.split_state(open(seed, "rb").read())
dom = dict(sdom) if mode == "overlay" else {}
for k, v in pdom.items():
    if k != "fileType":
        dom[k] = v
blob = pc.join_state(smeta, dom, sver)
open(dst, "wb").write(blob)
print(f"mode={mode} keys={len(dom)} bytes={len(blob)}")
