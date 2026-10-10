#!/usr/bin/env python3
"""Fruity Wrapper の VSTPlug unit (0x7a8000-0x7b6000) decompile から、AEffect.dispatcher (+8) 呼出の opcode を集計する."""
import re, sys, collections
t = open(sys.argv[1]).read()
parts = re.split(r'//// FUNC (\w+) size=\d+\n', t)
funcs = {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}
NAMES = {0:'effOpen',1:'effClose',2:'effSetProgram',3:'effGetProgram',4:'effSetProgramName',5:'effGetProgramName',6:'effGetParamLabel',
 7:'effGetParamDisplay',8:'effGetParamName',10:'effSetSampleRate',11:'effSetBlockSize',12:'effMainsChanged',13:'effEditGetRect',14:'effEditOpen',
 15:'effEditClose',19:'effEditIdle',23:'effGetChunk',24:'effSetChunk',25:'effProcessEvents',29:'effGetProgramNameIndexed',33:'effGetInputProperties',
 34:'effGetOutputProperties',35:'effGetPlugCategory',45:'effGetEffectName',47:'effGetVendorString',50:'effVendorSpecific',51:'effCanDo',53:'effIdle',
 55:'effSetViewPosition(?)',58:'effGetVstVersion',61:'effSetEditKnobMode',66:'effGetMidiKeyName(?)',67:'effBeginSetProgram',68:'effEndSetProgram',
 70:'effShellGetNextPlugin',0x10000:'(FL private?)'}
cnt = collections.defaultdict(set)
for a, b in funcs.items():
    for m in re.finditer(r'\+ 8\)\)\s*\(([^;]*?)\);', b, re.S):
        args = [x.strip() for x in m.group(1).replace('\n', ' ').split(',')]
        if len(args) >= 4:
            try: op = int(args[1], 0)
            except ValueError: continue
            cnt[op].add(a)
print('# opcode (decimal)  name  [呼出元関数 (VA, ImageBase 0x400000)]')
for op in sorted(cnt):
    print(f'{op:>6}  {NAMES.get(op,"?"):<28} {sorted(cnt[op])[:6]}')
