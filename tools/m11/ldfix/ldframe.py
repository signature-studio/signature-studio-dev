"""ldframe.py — frame (rbp/rsp 相対) の機械語モデルと IR の escape 判定 (audit_undefload.py / ldfix F4 共用, #564)。"""
import re

WRITE_ONLY = ('stmxcsr', 'fnstsw', 'fnstcw', 'fst', 'fstp', 'fist', 'fistp', 'fisttp')


def is_write_only(ins):
    """メモリオペランドが dest で値を読まない命令 (mov / setcc / stmxcsr 等)。cmp/add/sub/xor 等は RMW か read。"""
    mn = ins.mnemonic
    if not ins.operands or ins.operands[0].type != 3:   # CS_OP_MEM
        return False
    return mn.startswith('mov') or mn.startswith('set') or mn in WRITE_ONLY


def frame_model(cs, ins_list):
    """{insn addr: (rsp, rbp)} — entry rsp (= return address slot) を 0 とする相対値。RetDec の `%stack_var_-N` は
    この座標 (番地 = N だけ entry rsp より下) と一致する (52a7f0: rbp = -200, [rbp+0x68] = -96 = stack_var_-96)。
    push/pop/`sub|add rsp,imm`/`mov rbp,rsp`/`lea rbp,[rsp+K]`/`lea rsp,[rbp+K]` だけ解釈し、他の rsp/rbp 書込みは None (不明)。"""
    rsp, rbp, body = 0, None, None
    out = {}
    for i in ins_list:
        out[i.address] = (rsp, rbp)
        mn, ops = i.mnemonic, i.operands
        r0 = cs.reg_name(ops[0].reg) if ops and ops[0].type == 1 else None
        if mn == 'push':
            rsp = None if rsp is None else rsp - 8
        elif mn == 'pop':
            rsp = None if rsp is None else rsp + 8
            if r0 == 'rbp':
                rbp = None
        elif r0 == 'rsp' and mn in ('sub', 'add') and len(ops) == 2 and ops[1].type == 2:
            rsp = None if rsp is None else (rsp - ops[1].imm if mn == 'sub' else rsp + ops[1].imm)
        elif r0 == 'rbp' and mn == 'mov' and ops[1].type == 1 and cs.reg_name(ops[1].reg) == 'rsp':
            rbp, body = rsp, rsp
        elif r0 == 'rbp' and mn == 'lea' and ops[1].type == 3 and cs.reg_name(ops[1].mem.base) == 'rsp' and not ops[1].mem.index:
            rbp = None if rsp is None else rsp + ops[1].mem.disp
            body = rsp
        elif r0 == 'rsp' and mn == 'lea' and ops[1].type == 3 and cs.reg_name(ops[1].mem.base) == 'rbp' and not ops[1].mem.index:
            rsp = None if rbp is None else rbp + ops[1].mem.disp
        elif r0 == 'rsp':
            rsp = None
        elif r0 == 'rbp' and mn != 'cmp' and mn != 'test':
            rbp = None
        if mn == 'ret' and body is not None:
            rsp = body
    return out


def escaped_stack_vars(fn_text):
    """IR 関数本文から {N: escaped?} (`%stack_var_-N` alloca とその bitcast 別名が call / ptrtoint の引数に現れるか)。"""
    vs = {int(m.group(1)): '%%stack_var_-%s' % m.group(1) for m in re.finditer(r'^  %stack_var_-(\d+) = alloca ', fn_text, re.M)}
    res = {}
    for n, v in vs.items():
        al = {v}
        for m in re.finditer(r'^  (%[\w.$-]+) = bitcast ptr (%[\w.$-]+) to ptr', fn_text, re.M):
            if m.group(2) in al:
                al.add(m.group(1))
        esc = False
        for m in re.finditer(r'^\s*(?:%[\w.$-]+ = )?(?:call|ptrtoint) [^\n]*$', fn_text, re.M):
            if any(re.search(re.escape(a) + r'(?![\w.$-])', m.group(0)) for a in al):
                esc = True
                break
        res[n] = esc
    return res
