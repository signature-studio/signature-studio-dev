#!/usr/bin/env python3
"""ldfix_img.py — ldfix.py を PE 無しで実行するラッパ (#484)。ldmach_img.ImageMachine を差し込むだけで、
ldfix.py 本体は無改変。使い方: python3 ldfix_img.py IN.ll OUT.ll IMAGE.bin 'CONFIG_GLOB' [ldfix.py の他引数]"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ldfix  # noqa: E402
import ldmach_img  # noqa: E402

inp, out, image, cfg = sys.argv[1:5]
ldfix.Machine = lambda _pe: ldmach_img.ImageMachine(image, cfg)
sys.argv = ['ldfix.py', inp, out, '--pe', 'unused'] + sys.argv[5:]
ldfix.main()
