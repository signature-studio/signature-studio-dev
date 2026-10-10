#!/usr/bin/env python3
"""keyflow.py — 関数内 TRegistry 呼出列の key/value 文字列解決 (線形一括解釈)。

追うパターン (実機 FLEngine の Delphi コードで確認済):
  * lea r64, [rip+X]          -> 文字列定数 (UTF-16, .text 配置) / UStrAsg 用
  * call 0x413480 (UStrAsg)   -> dest(rcx=[rbp+K]) := src(rdx=literal or reg)
  * call 0x414c70 (UStrCat3)  -> dest(rcx=[rbp+K]) := s1(rdx) + s2(r8)
  * call 0x414bb0 (UStrCat)   -> var_args 版 (rcx=dest, rdx=count, その後 args)
  * mov [rbp+K], r64 / mov r64, [rbp+K] -> スロット値の退避/復帰
  * TRegistry メソッド call   -> (method, key, value, arg3) を解決して記録

TRegistry メソッド表 (reg_raw/reg_inventory と整合を取り、未記載分は実測で追加):
  0x5af120 Create / 0x5af3d0 SetRoot / 0x5af470 CreateKey / 0x5af5e0 OpenKey /
  0x5af7c0 OpenKeyRO / 0x5afa50 DeleteKey / 0x5afd50 DeleteValue / 0x5b0cb0 ValueExists /
  0x5b1820 ReadStr(key,v) / 0x5b1920 WriteStr(key,v) / 0x5b19f0 ReadInt(key,v,default) /
  0x5b1b00 WriteInt(key,v,val) / 0x5b1c10 ReadBool / 0x5b1c50 WriteBool /
  0x5b03a0 ReadStrCur(v) / 0x5b0350 WriteStrCur(v) / 0x5b0cd0 OpenKeyEx(返値HKEY) /
  0x5b16a0 GetKeyHandle?(self,cancreate,key)->HKEY / 0x5b09c0 WriteFloatCur(name,val)
"""
import re
import feparse as F
import fnindex
from xref import str_at

RE_RIP = re.compile(r'\[rip ([+-]) (0x[0-9a-f]+)\]')

USTR_ASG = 0x413480
USTR_CAT3 = 0x414c70
USTR_CAT = 0x414bb0

METHODS = {
    0x5af120: ('Create', ('self',)),
    0x5af3d0: ('SetRoot', ('self', 'root')),
    0x5af470: ('CreateKey', ('self', 'key')),
    0x5af5e0: ('OpenKey', ('self', 'key', 'cancreate')),
    0x5af7c0: ('OpenKeyRO', ('self', 'key')),
    0x5afa50: ('DeleteKey', ('self', 'key')),
    0x5afd50: ('DeleteValue', ('self', 'value')),
    0x5b0cb0: ('ValueExists', ('self', 'value')),
    0x5b1820: ('ReadStr', ('self', 'key', 'value', 'default?')),
    0x5b1920: ('WriteStr', ('self', 'key', 'value', 'val')),
    0x5b19f0: ('ReadInt', ('self', 'key', 'value', 'default')),
    0x5b1b00: ('WriteInt', ('self', 'key', 'value', 'val')),
    0x5b1c10: ('ReadBool', ('self', 'key', 'value', 'default')),
    0x5b1c50: ('WriteBool', ('self', 'key', 'value', 'val')),
    0x5b03a0: ('ReadStrCur', ('self', 'value')),
    0x5b0350: ('WriteStrCur', ('self', 'value', 'val')),
    0x5b0cd0: ('OpenKeyHandle', ('self', 'key')),
    0x5b16a0: ('GetKeyHandle', ('self', 'cancreate', 'key')),
    0x5b09c0: ('WriteFloatCur', ('self', 'name', 'val')),
    0x5b0b30: ('WriteData', ('self', 'name', 'buf', 'size', 'type')),
    0x5b0bd0: ('ReadData', ('self', 'name', 'buf', 'size', 'type')),
    0x5b0940: ('ReadFloatCur', ('self', 'name')),
    0x651330: ('WrapWriteFloat', ('self', 'key', 'name', 'val')),
}


class Slot:
    __slots__ = ('val',)

    def __init__(self, val=None):
        self.val = val

    def __repr__(self):
        return 'S(%s)' % (self.val,)


def resolve_func(va, verbose=False):
    """returns dict: {'ops': [ {call, method, args:{name:val}} ], 'slots': {...}}"""
    f = fnindex.func_of(va)
    if not f:
        return None
    ins_list = F.disasm_func(f[0], f[1] - f[0] + 0x10)
    # index by address
    byaddr = {x.address: x for x in ins_list}
    order = [x.address for x in ins_list]
    # 線形トレース (ret/int3 で打ち切り)
    ops = []
    regs = {}
    slots = {}
    i = 0
    n = len(ins_list)
    while i < n:
        x = ins_list[i]
        m = RE_RIP.search(x.op_str)
        if x.mnemonic == 'lea' and m:
            disp = int(m.group(2), 16) * (1 if m.group(1) == '+' else -1)
            tgt = x.address + x.size + disp
            s = str_at(tgt)
            dst = x.op_str.split(',')[0]
            # UStrAsg / Cat3 パターン検出: lea rcx,[rbp+K] を slot store として扱う
            if dst in ('rcx', 'rdx', 'r8', 'r9'):
                regs[dst] = ('str', tgt, s)
            else:
                regs[dst] = ('str', tgt, s)
            # 次の命令が lea rdx,[rip+..] で call 0x413480/0x414c70 なら slot 書込
            if dst == 'rcx' and i + 2 < n and x.op_str.startswith('rcx, [rbp') or x.op_str.startswith('rcx, [rsp'):
                pass
        elif x.mnemonic == 'mov':
            if m:
                disp = int(m.group(2), 16) * (1 if m.group(1) == '+' else -1)
                tgt = x.address + x.size + disp
                dst = x.op_str.split(',')[0]
                s = str_at(tgt)
                regs[dst] = ('mem', tgt, s)
            else:
                parts = x.op_str.split(', ')
                if len(parts) == 2:
                    d, srcp = parts
                    if d.startswith('qword ptr [rbp') or d.startswith('qword ptr [rsp'):
                        v = regs.get(srcp)
                        if v and v[0] == 'str' and v[2] is not None:
                            slots[_key_of(d)] = v[2]
                        elif srcp in regs and regs[srcp] and regs[srcp][0] == 'slot':
                            slots[_key_of(d)] = regs[srcp][2]
                        else:
                            slots[_key_of(d)] = None
                        # store 先が 'lea rcx,[rbp+K]' 形式で UStrAsg の dest にも使われる
                    elif srcp.startswith('qword ptr [rbp') or srcp.startswith('qword ptr [rsp'):
                        k = _key_of(srcp)
                        if k in slots:
                            regs[d] = ('slot', k, slots[k])
                        else:
                            regs[d] = ('slot?', k, None)
                    elif srcp in regs:
                        regs[d] = regs[srcp]
                    else:
                        regs.pop(d, None)
        elif x.mnemonic == 'call':
            tgt = int(x.op_str, 16) if x.op_str.startswith('0x') else None
            if tgt in (USTR_ASG, USTR_CAT3):
                # rcx = dest slot addr (最大 4 命令戻って lea rcx,[rbp+K] を探す)
                destk = None
                for back in range(1, 5):
                    if i - back < 0:
                        break
                    p = ins_list[i - back]
                    if p.mnemonic == 'call':
                        break
                    if p.mnemonic == 'lea' and (p.op_str.startswith('rcx, [rbp') or p.op_str.startswith('rcx, [rsp')):
                        destk = _key_of('qword ' + p.op_str.split('rcx, ')[1])
                        break
                if tgt == USTR_ASG and destk is not None:
                    v = regs.get('rdx')
                    slots[destk] = v[2] if v and v[0] == 'str' else (v[2] if v and v[0] == 'slot' else None)
                elif tgt == USTR_CAT3 and destk is not None:
                    a = regs.get('rdx')
                    b = regs.get('r8')
                    sa = _s_of(a, slots)
                    sb = _s_of(b, slots)
                    slots[destk] = (sa + sb) if (sa is not None and sb is not None) else None
            elif tgt in METHODS:
                name, argn = METHODS[tgt]
                args = {}
                amap = {'self': 'rcx', 'root': 'rdx', 'key': 'rdx', 'cancreate': 'rdx', 'value': 'r8',
                        'val': 'r9', 'default': 'r9', 'name': 'rdx', 'buf': 'r8', 'size': 'r9', 'default?': 'r9'}
                # ReadStr/WriteStr/ReadInt/WriteInt/ReadBool/WriteBool は (self,key,value,def)
                if tgt in (0x5b19f0, 0x5b1b00, 0x5b1c10, 0x5b1c50):
                    args['key'] = _s_of(regs.get('rdx'), slots)
                    args['value'] = _s_of(regs.get('r8'), slots)
                    args['arg3'] = _s_of(regs.get('r9'), slots)
                elif tgt == 0x5b1820:  # ReadStr: rdx=result var, key=r8, value=r9
                    args['key'] = _s_of(regs.get('r8'), slots)
                    args['value'] = _s_of(regs.get('r9'), slots)
                else:
                    for ai, an in enumerate(argn):
                        r = ('rcx', 'rdx', 'r8', 'r9')[ai]
                        if an != 'self':
                            args[an] = _s_of(regs.get(r), slots)
                ops.append({'call': hex(x.address), 'method': name, 'va': hex(tgt), 'args': args})
            regs['rax'] = None
        elif x.mnemonic == 'ret':
            regs.clear()
        i += 1
    return {'func': hex(f[0]), 'size': f[1] - f[0], 'ops': ops, 'slots': slots}


def _key_of(opstr):
    m = re.search(r'\[([^\]]+)\]', opstr)
    return '[' + m.group(1) + ']' if m else opstr.strip()


def _s_of(v, slots):
    if v is None:
        return None
    if v[0] in ('str',):
        return v[2] if v[2] is not None else '@0x%x' % v[1]
    if v[0] in ('slot', 'slot?'):
        return slots.get(v[1])
    return None


if __name__ == '__main__':
    import sys
    va = int(sys.argv[1], 16)
    r = resolve_func(va)
    print('func %s size %d' % (r['func'], r['size']))
    for o in r['ops']:
        print(o['call'], o['method'], o['args'])
