#!/usr/bin/env python3
"""entry_roots.py — 入口拡張版の lift entries.json を作る。

  entry_roots.py DSP_COV.json [ENTRY_COV.json] OUT.json

roots = DSP 4 root + VST 入口関数群 (dispatcher / thunks / overrides / getter 群 /
        editor ctor surrogate / audioMaster trampoline / dtor) + operator new/delete。
calltgt = DSP coverage (実機械語単歩) と entry coverage の call target の和集合。
"""
import json, sys

IMG = 0x180000000
# dispatcher の両 switch が vtable 経由で呼ぶ OTT override / base 既定 (実測: HOSTBRIDGE.md §1.4 +
# tools/ott/entry の jump table 解析; dispatcher low switch op0..24 / X switch op25..79)
ENTRY_ROOTS = [
    0x180128ba0,  # VSTPluginMain (PE export)
    0x180125b40,  # createEffectInstance (operator new → OTTProcessor ctor → editor → resume)
    0x180126c00,  # dispatchEffectClass (AEffect+0x08 静的 thunk)
    0x180127800,  # AudioEffectX::dispatcher X 側 switch (op 25..79)
    0x180126c60,  # dispatcher 低 op 側 switch (op 0..24)
    0x180127430,  # process 静的 thunk (AEffect+0x10)
    0x180127520,  # setParameter 静的 thunk (AEffect+0x18)
    0x1801271a0,  # getParameter 静的 thunk (AEffect+0x20)
    0x180127450,  # processReplacing 静的 thunk (AEffect+0x78)
    0x180127440,  # processDoubleReplacing 静的 thunk (AEffect+0x80)
    0x180125bd0,  # setParameter override (vtbl+0x50) → DSP setParameter + editor 通知
    0x18011e5a0,  # getParameter override (vtbl+0x58, jump table 31 param)
    0x180120ed0,  # setSampleRate (vtbl+0x30)
    0x180120ac0,  # setBlockSize (vtbl+0x38)
    0x18011eae0,  # getProgram (vtbl+0x68)
    0x180120d10,  # setProgram (vtbl+0x70)
    0x180120e90,  # setProgramName (vtbl+0x78)
    0x18011eaf0,  # getProgramName (vtbl+0x80)
    0x18011e7b0,  # getParamLabel (vtbl+0x88)
    0x18011e770,  # getParamDisplay (vtbl+0x90) — float formatter 経路は CRT 未初期化で native crash
    0x18011e820,  # getParamName (vtbl+0x98)
    0x18011eb70,  # getProgramNameIndexed (vtbl+0x1b8)
    0x18011e510,  # getEffectName / getProductString (vtbl+0x2e0/+0x2f0)
    0x18011ebd0,  # getVendorString (vtbl+0x2e8)
    0x18011ec00,  # getVendorVersion (vtbl+0x2f8)
    0x180120f00,  # vendorSpecific (vtbl+0x300)
    0x18011e220,  # canDo (vtbl+0x308)
    0x18011ec10,  # getVstVersion (vtbl+0x310)
    0x18011e520,  # getOutputProperties (vtbl+0x210)
    0x18011c9f0,  # getAeffect (vtbl+0xf0) — VSTPluginMain の tail jmp 先
    0x180125b00,  # scalar deleting destructor (vtbl+0x00) — effClose 経路
    0x18000a9e0,  # base getChunk/setChunk/getVu 系 (return 0)
    0x18000a9f0,  # base getVu (return 0)
    0x18000aa10,  # base bool 返し系 (canDo/CanBeAutomated/getInputProperties 既定)
    0x18000aa50,  # base void 系 (open/close/suspend/processDoubleReplacing 既定)
    0x180020830,  # base -1 返し (processEvents 既定 ほか)
    0x180073ba0,  # base 1 返し (effIdle/effGetTailSize 系既定)
    0x180120ff0,  # OTTEditor ctor — override (ovr_editor_null) で editor=NULL surrogate
    0x1801a04d0,  # operator new (CRT — HeapAlloc 経由で wasm imp_HeapAlloc に落ちる)
    0x1801a0514,  # operator delete
    0x1802f8000,  # audioMaster trampoline — override (ovr_am_shim)
]


def main():
    dsp = json.load(open(sys.argv[1]))
    calltgt = set(int(r) for r in dsp.get('calltgt', []))
    if len(sys.argv) > 2 and sys.argv[2] != '-':
        ent = json.load(open(sys.argv[2]))
        calltgt |= set(ent.get('calltgt', []))
    roots = [0x18011d400, 0x180120af0, 0x180120800, 0x18011ec20] + ENTRY_ROOTS
    for r in ENTRY_ROOTS:
        calltgt.add(r - IMG)
    json.dump({'roots': roots, 'calltgt': sorted(calltgt)}, open(sys.argv[-1], 'w'))
    print('[entry_roots] roots %d / calltgt %d' % (len(roots), len(calltgt)))


if __name__ == '__main__':
    main()
