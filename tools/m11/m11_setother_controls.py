#!/usr/bin/env python3
"""set_other 非 imm 分類器 (m11_setother_nonimm_class.py) の対照検査 (#3141 / M11-N173).

素材 (work-m11・fl-win64) を使わず、合成機械語と合成 IR で分類器を動かす。
  正の対照 (7 件) : 戻り値の定数 (ret_value) が既知の値に一致するか (実値化)。
  ネガ対照 (3 件) : 狭い格納の型幅ゲート。IR の define 行の型だけを i64 → i8 に書き換え、
                    台帳 1 行 → trace_slot の main 経路で判定が変わるか。
                    格納幅が SIZE に無い (movups xmmword) は狭い格納に入れず stack_width_other になるか。
  既知の限界 (M1) : 間接 jmp の先の ret。現状の出力を記録する (未修正・偽の定数になりうる)。
使い方: python3 m11_setother_controls.py   (終了コード 0 = 正の対照・ネガ対照が全て期待どおり)
"""
import os, struct, sys, tempfile, json
import capstone
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import m11_setother_repro as R


class FakeMachine:
    """ldmach.Machine の代用 (分類器が使うのは disasm_fn と cs だけ)。VA -> 機械語 bytes。"""

    def __init__(self, funcs):
        self.funcs = funcs
        self.cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.cs.detail = True

    def disasm_fn(self, va):
        if va not in self.funcs:
            return None
        return list(self.cs.disasm(self.funcs[va], va))


def call_rel(at, target):
    return b'\xe8' + struct.pack('<i', target - (at + 5))


def load(funcs, ir_text, fixes):
    d = tempfile.mkdtemp(prefix='m11ctl_')
    ir = os.path.join(d, 'ir.ll')
    fx = os.path.join(d, 'fixes.json')
    open(ir, 'w').write(ir_text)
    json.dump(fixes, open(fx, 'w'))
    return R.classify(open(R.CLS).read(), fx, 'synthetic', ir, FakeMachine(funcs))


def main():
    bad = 0
    # 正の対照: (名前, 機械語, 期待値)。関数 VA は 0x4000 + 0x100 * i。
    base = 0x4000
    pos = [
        ('mov eax,5; ret', bytes.fromhex('b805000000c3'), 5),
        ('xor eax,eax; ret', bytes.fromhex('31c0c3'), 0),
        ('mov eax,5; mov ecx,3; add eax,ecx; ret', bytes.fromhex('b805000000b90300000001c8c3'), 8),
        ('mov eax,5; shl eax,4; ret', bytes.fromhex('b805000000c1e004c3'), 80),
        ('mov eax,5; add eax,-1; ret', bytes.fromhex('b80500000083c0ffc3'), 4),
        ('mov eax,5; xor eax,15; ret', bytes.fromhex('b80500000083f00fc3'), 10),
        ('call B (mov eax,9; ret); ret', call_rel(base + 0x600, base + 0x700) + b'\xc3', 9),
    ]
    funcs = {}
    for i, (_, code, _) in enumerate(pos):
        funcs[base + 0x100 * i] = code
    funcs[base + 0x700] = bytes.fromhex('b809000000c3')
    g = load(funcs, 'define i64 @function_0(i64 %a)\n', {'site_detail': []})
    print('[controls] 正の対照 (戻り値の定数):')
    n_ok = 0
    for i, (name, _, want) in enumerate(pos):
        cls, why, val, _ = g['ret_value'](base + 0x100 * i, 'rax')
        ok = cls == '実値化' and val == want
        n_ok += ok
        bad += not ok
        print('  %s %-42s → %s %s %s (期待 実値化 %d)' % ('ok ' if ok else 'NG ', name, cls, why, val, want))
    print('[controls] 正の対照 %d/%d 一致' % (n_ok, len(pos)))

    # ネガ対照: 呼出元 0x1000 は mov al,[rip+0x10]; mov [rsp+0x20],al; call 0x2000; ret。
    # 台帳 1 行 (引数 pos 4 = スタック引数 [rsp+0x20]) を、callee の IR 型だけ変えて判定する。
    caller, callee = 0x1000, 0x2000
    code = (bytes.fromhex('8a0510000000') + bytes.fromhex('88442420')
            + call_rel(caller + 10, callee) + b'\xc3')
    funcs = {caller: code, callee: b'\xc3'}
    fixes = {'site_detail': [{'status': 'matched', 'caller': 'function_%x' % caller,
                              'callee': 'function_%x' % callee, 'k': 0,
                              'args': {'4': 'stack_set_other'}, 'src': {'4': 'set_other'}}]}
    want = {'i64': 'stack_narrow_ir64_st8', 'i8': 'stack_match>load_global'}
    print('[controls] ネガ対照 (狭い格納の型幅ゲート: 格納幅 8 bit・IR 型だけ変更):')
    n_ok = 0
    for ty, why_want in want.items():
        ir = 'define i64 @function_%x(i64 %%a1, i64 %%a2, i64 %%a3, i64 %%a4, %s %%a5) {\n  ret i64 0\n}\n' % (callee, ty)
        rows = load(funcs, ir, fixes)['rows']
        ok = len(rows) == 1 and rows[0]['reason'] == why_want and rows[0]['class'] == '未決'
        n_ok += ok
        bad += not ok
        got = rows[0]['reason'] if rows else None
        print('  %s IR 型 %-3s → %s (期待 %s)' % ('ok ' if ok else 'NG ', ty, got, why_want))
    code3 = bytes.fromhex('0f11442420') + call_rel(caller + 5, callee) + b'\xc3'
    ir3 = 'define i64 @function_%x(i64 %%a1, i64 %%a2, i64 %%a3, i64 %%a4, i64 %%a5) {\n  ret i64 0\n}\n' % callee
    rows = load({caller: code3, callee: b'\xc3'}, ir3, fixes)['rows']
    ok = len(rows) == 1 and rows[0]['reason'] == 'stack_width_other' and rows[0]['class'] == '未決'
    n_ok += ok
    bad += not ok
    got = rows[0]['reason'] if rows else None
    print('  %s 格納幅が SIZE に無い (movups xmmword ptr [rsp+0x20]) → %s (期待 stack_width_other)' % ('ok ' if ok else 'NG ', got))
    print('[controls] ネガ対照 %d/3 一致' % n_ok)

    # 既知の限界 M1: 間接 jmp (jmp rcx) の後ろの ret を直前の定数の続きとして扱う (偽の定数)。未修正。
    m1 = 0x3000
    g = load({m1: bytes.fromhex('ffe1' 'b807000000' 'c3')}, 'define i64 @function_0(i64 %a)\n', {'site_detail': []})
    cls, why, val, _ = g['ret_value'](m1, 'rax')
    print('[controls] 既知の限界 M1 (未修正): jmp rcx; mov eax,7; ret → %s %s %s (真の値は決まらない)' % (cls, why, val))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
