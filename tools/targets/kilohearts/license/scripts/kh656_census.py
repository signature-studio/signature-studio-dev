#!/usr/bin/env python3
"""kh656_census.py — module F の未 lift callee (kh_lower の unlifted callees) を分類して表示する (#656).

  python3 scripts/kh656_census.py            (前提: lic_build.py --module F を実行済み = work/licF/ が存在)

分類 (排他・上から順):
  shim      : modules.F.shims に登録 (C 実装で置換・lift しない)
  i256/AVX2 : 呼び出し先の本体の機械語が ymm レジスタを使う = gen_simd.py 未対応で lift 不可
  fail-fast : 上記以外の未 lift (呼ばれると unlifted callee 例外で停止)
ymm 判定は PE 上の関数範囲 (.pdata。無い関数は先頭から ret まで) を capstone で逆アセンブルして行う
(未 lift の関数は n1.ll に現れないため n1.ll からは検出できない)。
出力は表 (VA / class / 入口経路での先頭か) と件数。
"""
import json
import os
import re
import struct
import sys

import capstone
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from pe_dis import pe, data, BASE, rd

HERE = os.path.dirname(os.path.abspath(__file__))
LIC = os.path.dirname(HERE)
CFG = json.load(open(os.path.join(LIC, 'lic_config.json'), encoding='utf-8'))['modules']['F']
W = os.path.join(LIC, 'work', 'licF')
st = json.load(open(os.path.join(W, 'stat.json'), encoding='utf-8'))
unl = json.loads(re.search(r"unlifted callees (\[[^\]]*\])", st['passes']).group(1).replace("'", '"'))

pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0]
pb = data[pd.PointerToRawData:pd.PointerToRawData + pd.Misc_VirtualSize]
PD = {}
for i in range(0, len(pb) // 12 * 12, 12):
    x, e, _ = struct.unpack_from('<III', pb, i)
    if x:
        PD[BASE + x] = BASE + e
starts = sorted(PD)
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)


def fn_end(va):
    """関数の終端 VA。.pdata に該当があればその END、無ければ先頭から最初の ret の直後"""
    if va in PD:
        return PD[va]
    a = va
    while True:
        ins = next(md.disasm(rd(a, 16), a, 1))
        a += ins.size
        if ins.mnemonic == 'ret':
            return a


def has_ymm(va):
    end = fn_end(va)
    return any('ymm' in ins.op_str for ins in md.disasm(rd(va, end - va), va))


wide = {va for va in unl if has_ymm(int(va, 16))}
shims = CFG.get('shims', {})
cnt = {'shim': 0, 'i256/AVX2': 0, 'fail-fast': 0}
for va in unl:
    if va in shims:
        cls = 'shim:' + shims[va]
        cnt['shim'] += 1
    elif va in wide:
        cls = 'i256/AVX2'
        cnt['i256/AVX2'] += 1
    else:
        cls = 'fail-fast'
        cnt['fail-fast'] += 1
    first = ' <- 入口経路の先頭' if va == '180112a30' else ''
    print('0x%s  %s%s' % (va, cls, first))
print('unlifted=%d lifted(F)=%d shim=%d i256/AVX2=%d fail-fast=%d wasm=%dB' % (
    len(unl), len(CFG['lift']), cnt['shim'], cnt['i256/AVX2'], cnt['fail-fast'], st['wasm_bytes']))
