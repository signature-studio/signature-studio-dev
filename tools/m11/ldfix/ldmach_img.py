#!/usr/bin/env python3
"""ldmach_img.py — PE 無しで ldfix / audit_lsf を動かす ldmach.Machine 互換 shim (#484)。

PE (`block00031_PE.bin`, fl-win64 素材) の代わりに、work-m11 に入っている
 - `work/m11_image.bin` (m11_image_gen.py 出力: .text を RVA+LB_BASE 座標に敷いた生イメージ)
 - `work/boot*.drc.config.json` (RetDec の functions[].startAddr/endAddr = 関数区間)
から Machine と同じ API (fns / read / disasm_fn) を提供する。
.pdata の RUNTIME_FUNCTION 区間との同値性は、本 shim 版 ldfix の修復関数リストを
`work/ldfix_report.json` (PE 版 ldfix の出力) と突合して検証する (REPORT_484 §2)。
"""
import glob
import json
import os
import sys

import capstone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ldmach import Machine  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lb_base import LB, IMG_BASE  # noqa: E402


class ImageMachine(Machine):
    def __init__(self, image_path, config_glob):
        self.pef = None
        self.base = IMG_BASE
        data = open(image_path, 'rb').read()
        self.text = (-LB, data)        # read(rva) -> data[rva + LB]
        self.pdata = None
        self.fns = {}
        for cfg in sorted(glob.glob(config_glob)):
            for f in json.load(open(cfg))['functions']:
                if f.get('fncType') != 'decompilerDefined':
                    continue
                s = int(f['startAddr'], 16)
                e = int(f['endAddr'], 16)
                if e <= s:
                    continue
                rva = s - IMG_BASE
                prev = self.fns.get(s)
                if prev is None or prev[1] < e - s:
                    self.fns[s] = (rva, e - s)
        self.cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.cs.detail = True
        self._cache = {}

    def cover(self, va, last_label):
        """RetDec config の endAddr は IR ラベルより短い関数がある (REPORT_484 §4)。最大 IR ラベルから最初の ret/ud2 まで区間を延ばす
        (PE の .pdata 区間には相当する差が無い。ldfix.main が hasattr で呼ぶ)"""
        ent = self.fns.get(va)
        if not ent or last_label < va + ent[1]:
            return
        a = last_label
        while True:
            got = list(self.cs.disasm(self.read(a - self.base, 16), a, 1))
            if not got:
                break
            a += got[0].size
            if got[0].mnemonic in ('ret', 'retn', 'ud2', 'int3', 'hlt'):
                break
        self.fns[va] = (ent[0], max(ent[1], a - va))
        self._cache.pop(va, None)
