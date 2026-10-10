#!/usr/bin/env python3
"""keyflow2.py — TRegistry 呼出列の解決 v2: current-key コンテキスト追跡付き。

実機解析で確定した機構 (FLEngine 26.1.7):
  * 共有 TRegistry 管理オブジェクト ([0x6510F0]) — CurrentKey が永続し、次で変化:
      - OpenKey(0x5af5e0) / OpenKeyRO(0x5af7c0) / GetKeyHandle(0x5b16a0→0x5b1750→OpenKey)
      - SetRoot(0x5af3d0) は閉じるだけ
  * key 引数が nil/空文字 → CurrentKey そのもの (0x5aeec0 IsRelative: 空/先頭!=0x5c → 相対)
  * 相対 key → CurrentKey + '\\' + key / 絶対 ('Software\\..' 等) → RootKey(HKCU 既定) 直下
  * CreateKey(0x5af470) / OpenKeyHandle(0x5b0cd0) / WriteXxx/ReadXxx の key 付き版は
    CurrentKey を save→open→write→restore し、**永続しない**
  * 起動時に 0x1104fe0 が 'Software\\Image-Line\\FL Studio 26' を OpenKey(cancreate=1) する
    (0x11c71b0/0x11cde20 は同一関数内で GetKeyHandle(FL26) → 相対 'General' ops の組で実証)
"""
import re
import feparse as F
import fnindex
from xref import str_at

RE_RIP = re.compile(r'\[rip ([+-]) (0x[0-9a-f]+)\]')

USTR_ASG = 0x413480
USTR_CAT3 = 0x414c70

# (name, argnames, persists_current_key)
METHODS = {
    0x5af120: ('Create', ('self',), False),
    0x5af3d0: ('SetRoot', ('self', 'root'), False),
    0x5af470: ('CreateKey', ('self', 'key'), False),
    0x5af5e0: ('OpenKey', ('self', 'key', 'cancreate'), True),
    0x5af7c0: ('OpenKeyRO', ('self', 'key'), True),
    0x5afa50: ('DeleteKey', ('self', 'key'), False),
    0x5afd50: ('DeleteValue', ('self', 'value'), False),
    0x5b0cb0: ('ValueExists', ('self', 'value'), False),
    0x5b1820: ('ReadStr', ('self', 'ret', 'key', 'value'), False),
    0x5b1920: ('WriteStr', ('self', 'key', 'value', 'val'), False),
    0x5b19f0: ('ReadInt', ('self', 'key', 'value', 'default'), False),
    0x5b1b00: ('WriteInt', ('self', 'key', 'value', 'val'), False),
    0x5b1c10: ('ReadBool', ('self', 'key', 'value', 'default'), False),
    0x5b1c50: ('WriteBool', ('self', 'key', 'value', 'val'), False),
    0x5b03a0: ('ReadStrCur', ('self', 'value'), False),
    0x5b0350: ('WriteStrCur', ('self', 'value', 'val'), False),
    0x5b0cd0: ('OpenKeyHandle', ('self', 'key'), False),
    0x5b16a0: ('GetKeyHandle', ('self', 'cancreate', 'key'), True),
    0x5b09c0: ('WriteFloatCur', ('self', 'name', 'val'), False),
    0x651330: ('WrapWriteFloat', ('self', 'key', 'name', 'val'), False),
}

ABS_PREFIX = ('software', 'hkey', 'system', 'clsid', 'hello')


def _reg(r):
    """capstone のレジスタ名を 64bit 正規化 (edx→rdx, r9d→r9)"""
    if not r:
        return r
    if r.startswith('e') and len(r) == 3:
        return 'r' + r[1:]
    if r.startswith('r') and r.endswith('d') and r[1:-1].isdigit():
        return r[:-1]
    return r


def _key_of(opstr):
    m = re.search(r'\[([^\]]+)\]', opstr)
    return '[' + m.group(1) + ']' if m else opstr.strip()


def _s_of(v, slots):
    if v is None:
        return None
    if v[0] == 'str':
        return v[2] if v[2] is not None else '@0x%x' % v[1]
    if v[0] in ('slot', 'slot?'):
        return slots.get(v[1])
    return None


def resolve_func(va, default_ctx='Software\\Image-Line\\FL Studio 26'):
    """戻り値: ops = [{call, method, key, value, arg3, ctx_at_call}]"""
    f = fnindex.func_of(va)
    if not f:
        return None
    ins_list = F.disasm_func(f[0], f[1] - f[0] + 0x10)
    ops = []
    regs = {}
    slots = {}
    ctx = None  # None = ambient (default_ctx)
    i = 0
    n = len(ins_list)
    while i < n:
        x = ins_list[i]
        m = RE_RIP.search(x.op_str)
        if x.mnemonic == 'lea' and m:
            disp = int(m.group(2), 16) * (1 if m.group(1) == '+' else -1)
            tgt = x.address + x.size + disp
            dst = _reg(x.op_str.split(',')[0])
            regs[dst] = ('str', tgt, str_at(tgt))
        elif x.mnemonic == 'mov':
            if m:
                disp = int(m.group(2), 16) * (1 if m.group(1) == '+' else -1)
                tgt = x.address + x.size + disp
                dst = _reg(x.op_str.split(',')[0])
                regs[dst] = ('mem', tgt, str_at(tgt))
            else:
                parts = x.op_str.split(', ')
                if len(parts) == 2:
                    d, srcp = parts
                    if d.startswith('qword ptr [rbp') or d.startswith('qword ptr [rsp'):
                        v = regs.get(srcp)
                        if v and v[0] == 'str' and v[2] is not None:
                            slots[_key_of(d)] = v[2]
                        elif v and v[0] in ('slot', 'slot?'):
                            slots[_key_of(d)] = slots.get(v[1])
                        else:
                            slots[_key_of(d)] = None
                    elif srcp.startswith('qword ptr [rbp') or srcp.startswith('qword ptr [rsp'):
                        k = _key_of(srcp)
                        regs[d] = ('slot', k, slots.get(k))
                    elif srcp in regs and regs[srcp]:
                        regs[d] = regs[srcp]
                    else:
                        regs.pop(d, None)
        elif x.mnemonic == 'xor' and re.match(r'^(\w+), \1$', x.op_str):
            regs.pop(_reg(x.op_str.split(',')[0]), None)
        elif x.mnemonic == 'call':
            tgt = int(x.op_str, 16) if x.op_str.startswith('0x') else None
            if tgt in (USTR_ASG, USTR_CAT3):
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
                if destk is not None:
                    if tgt == USTR_ASG:
                        v = regs.get('rdx')
                        slots[destk] = _s_of(v, slots) if v and v[0] in ('str', 'slot', 'slot?') else None
                    else:
                        a = _s_of(regs.get('rdx'), slots)
                        b = _s_of(regs.get('r8'), slots)
                        if a is not None and b is not None:
                            slots[destk] = a + b
                        elif a is not None:
                            slots[destk] = a + '<?>'   # 後半が実行時文字列
                        elif b is not None:
                            slots[destk] = '<?>' + b
                        else:
                            slots[destk] = None
            elif tgt in METHODS:
                name, argn, persists = METHODS[tgt]
                rec = {'call': hex(x.address), 'method': name, 'va': hex(tgt), 'ctx_at_call': ctx}
                if tgt == 0x5b1820:  # ReadStr: rdx=result, key=r8, value=r9
                    rec['key'] = _s_of(regs.get('r8'), slots)
                    rec['value'] = _s_of(regs.get('r9'), slots)
                elif tgt in (0x5b19f0, 0x5b1b00, 0x5b1c10, 0x5b1c50, 0x5b1920, 0x651330):
                    rec['key'] = _s_of(regs.get('rdx'), slots)
                    rec['value'] = _s_of(regs.get('r8'), slots)
                    rec['arg3'] = _s_of(regs.get('r9'), slots)
                elif tgt in (0x5b16a0,):
                    rec['key'] = _s_of(regs.get('r8'), slots)
                    rec['cancreate'] = _s_of(regs.get('rdx'), slots)
                else:
                    amap = {'self': 'rcx', 'root': 'rdx', 'key': 'rdx', 'value': 'r8', 'val': 'r9',
                            'default': 'r9', 'name': 'rdx', 'ret': 'rdx', 'cancreate': 'rdx'}
                    for an in argn:
                        if an != 'self':
                            rec[an if an != 'ret' else 'retvar'] = _s_of(regs.get(amap[an]), slots)
                # key が None (nil) → current key
                if rec.get('key') is None and name in ('OpenKey', 'OpenKeyRO', 'CreateKey', 'GetKeyHandle',
                                                       'ReadStr', 'WriteStr', 'ReadInt', 'WriteInt', 'ReadBool',
                                                       'WriteBool', 'DeleteKey', 'WrapWriteFloat'):
                    rec['key'] = '<cur>' if ctx else '<ambient>'
                    rec['key_nil'] = True
                ops.append(rec)
                if persists and rec.get('key') and rec['key'] not in ('<cur>', '<ambient>'):
                    ctx = rec['key']
                elif persists and rec.get('key') == '<cur>' and ctx is None:
                    ctx = default_ctx
            regs['rax'] = None
        elif x.mnemonic == 'ret':
            regs.clear()
        i += 1
    return {'func': hex(f[0]), 'size': f[1] - f[0], 'ops': ops, 'default_ctx': default_ctx}


def full_key(rec, default_ctx='Software\\Image-Line\\FL Studio 26'):
    """op の実効キー (HKCU/HKLM 下の完全パス) を返す。推定要素は ? を付ける"""
    k = rec.get('key')
    if k is None:
        return None
    if k == '<cur>':
        k = rec.get('ctx_at_call') or default_ctx
    elif k == '<ambient>':
        k = default_ctx + ' ?(ambient)'
    if k.endswith('?(ambient)'):
        return k
    kl = k.lower()
    if kl.startswith(ABS_PREFIX):
        return k
    base = rec.get('ctx_at_call') or default_ctx
    return (base + '\\' + k) if base else k


if __name__ == '__main__':
    import sys
    va = int(sys.argv[1], 16)
    r = resolve_func(va)
    print('func %s size %d' % (r['func'], r['size']))
    for o in r['ops']:
        fk = full_key(o)
        print(o['call'], o['method'], '| key=', o.get('key'), '| full=', fk, '| val=', o.get('value'))
