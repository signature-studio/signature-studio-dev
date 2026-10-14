#!/usr/bin/env python3
"""icall_rewrite.py — RetDec に間接 call/jmp を「落とさせない」ための decode 用 PE 書換え (binary pre-rewrite).

背景: RetDec(capstone2llvmir) は `call [rax+8]` / `call rdx` / `jmp [mem]` を IR に一切出力しない
(raw IR の時点で PC 更新だけが残る)。そこで **decode 専用コピー** の PE で、各間接 call/jmp 部位を

    mov  r11, <元の間接オペランド>          ; target を計算 (RetDec が load/gep として IR 化する)
    mov  [BLK+0x00], r11                    ; 以降 memory-ABI: レジスタ引数を固定 block に明示 store
    mov  [BLK+0x08], rcx / +0x10 rdx / +0x18 r8 / +0x20 r9
    movsd [BLK+0x28..0x40], xmm0..xmm3      ; (low 64bit; f32/f64 スカラ引数)
    call STUB                               ; 共有 stub (block を read/write する中身 = RetDec が readnone と見なさない)
    mov  rax, [BLK+0x80] ; movsd xmm0, [BLK+0x88]   ; 戻り値を明示 load
    (jmp 末尾呼出しは最後に ret)

に展開する。RetDec は register→値の配線 (rcx/rdx/r8/r9/xmm の SSA 値) を **通常の store として** 保持するので、
後段 (ir_icall_restore.py) は stub call を `__icall_dispatch(site_va)` に置換するだけで引数が揃う。
関数ごと新 section(.icall) に再配置するため、branch/rip-relative/jump table を全て張り直す。
出力: 書換え済み PE + map json (new→orig 関数/命令対応, site 表)。

  python3 icall_rewrite.py --pe X.dll --funcs funcs.txt --out X.icall.dll --map X.icall.map.json [--blk-va 0x...]
"""
import argparse, json, os, struct, sys, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capstone
from capstone import x86
import audit_icall as A

LEGACY = {0x66, 0x67, 0xf0, 0xf2, 0xf3, 0x2e, 0x36, 0x3e, 0x26, 0x64, 0x65}
BLK_TARGET, BLK_RCX, BLK_RDX, BLK_R8, BLK_R9 = 0x00, 0x08, 0x10, 0x18, 0x20
BLK_X0 = 0x28            # xmm0..3 at +0x28,+0x30,+0x38,+0x40
BLK_RAX, BLK_XMMRET = 0x80, 0x88
BLK_RAXIN = 0x90
BLK_XMMRET1 = 0x98       # closure 内 direct call の戻り xmm1 (hi/lo 2 値を返す CRT: 1801c1240・1801c0d00 等)。ICALL_ABI_XMM1=0 で無効 (ネガコン)
ABI_XMM1 = os.environ.get('ICALL_ABI_XMM1', '1') == '1'
BLK_STK = 0x48           # 第 5 引数以降 (stack) 配列の先頭アドレス (定数 = blk+BLK_STKBUF; icall_rt.c の __icall_dispatch が設定)
BLK_STKBUF = 0x100       # stack 引数の連続コピー領域: 呼出し点で [rsp+0x20+8k] (jmp 末尾呼出しは +0x28+8k) を k=0..NSTK-1 だけ明示 load/store
BLK_RESERVE = 0x280      # BLK 域 [blk, blk+0x280) は再配置範囲 (関数・stub) と重ならない。0 埋めし、コードバイトを残さない (#2565)
NSTK = 12                # 16 引数まで (IPP ippiResize*_8u 13 引数 = 9 語)
STK_COPY_ONE = 8 + 7     # mov r11,[rsp+disp32] (8B) ; mov [rip+d],r11 (7B)
STK_WINDOW = 48          # nstk 推定: site 直前の同一基本ブロック風の命令列 (直前の call/ret/jmp まで, 最大この命令数) を遡る
SITE_TAIL_BASE = 7 * 6 + 8 * 4 + 5 + 7 + 8


def site_tail_len(nstk):
    return SITE_TAIL_BASE + nstk * STK_COPY_ONE


def stk_slots_stored(items, idx):
    """items[idx] (間接 call site) の直前で [rsp+0x20+8k] (k<NSTK) へ store された最大 k+1 (無ければ 0)。
    全 site で無条件に rsp+0x20.. を読むと、RetDec が leaf 関数の stack 引数と誤認して関数 signature を変える (i64 f(void) 崩れ) ため、
    実際に書かれているスロットだけを BLK へコピーする。"""
    n = 0
    seen = 0
    j = idx - 1
    while j >= 0 and seen < STK_WINDOW:
        it = items[j]
        j -= 1
        if it.kind != 'ins':
            continue
        seen += 1
        ins = it.ins
        mn = ins.mnemonic
        if mn in ('call', 'ret', 'retf', 'jmp'):
            break
        if not ins.operands or ins.operands[0].type != x86.X86_OP_MEM or not (ins.operands[0].access & capstone.CS_AC_WRITE):
            continue   # cmp/test [rsp+..] 等の読み取りは store ではない
        m = ins.operands[0].mem
        if ins.reg_name(m.base) == 'rsp' and not m.index and not m.segment:
            sz = ins.operands[0].size
            if mn.startswith(('movaps', 'movups', 'movdqa', 'movdqu', 'movapd', 'movupd', 'vmov')) or sz not in (1, 2, 4, 8):
                continue   # xmm 退避 (callee-saved の spill 領域) は引数ではない
            d = m.disp - 0x20
            if d >= 0 and d % 8 == 0 and d // 8 < NSTK:
                n = max(n, d // 8 + 1)
    return n



REGNUM = {}
for _i, _n in enumerate(['rax', 'rcx', 'rdx', 'rbx', 'rsp', 'rbp', 'rsi', 'rdi', 'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15']):
    REGNUM[_n] = _i
STRING_MN = ('movsb', 'movsw', 'movsq', 'stos', 'cmps', 'scas', 'lods', 'insb', 'insw', 'insd', 'outs', 'nop', 'prefetch', 'lea', 'fxsave', 'xsave', 'clflush', 'invlpg')   # SSE movss/movsd/movsx は対象 (movsd の文字列版は mem 2 個で別途除外)


def lea_disp8(reg, d):
    """lea reg,[reg+d] (d: signed 8bit). rsp/r12 base は SIB"""
    rex = 0x48 | (0x05 if reg >= 8 else 0)
    low = reg & 7
    if low == 4:
        return bytes([rex, 0x8d, 0x40 | (low << 3) | 4, 0x24, d & 0xff])
    return bytes([rex, 0x8d, 0x40 | (low << 3) | low, d & 0xff])


def deref_base_reg(ins):
    """zero-disp / base-only(+disp 無し) メモリオペランドなら base レジスタ番号 (RetDec D7 回避対象)。対象外 None"""
    if ins.mnemonic.startswith(STRING_MN) or any(ins.mnemonic.startswith(x) for x in ('rep', 'lock')) and False:
        return None
    mem = [op for op in ins.operands if op.type == x86.X86_OP_MEM]
    if len(mem) != 1:
        return None
    m = mem[0].mem
    if not m.base or m.index or m.disp != 0 or m.segment:
        return None
    bn = ins.reg_name(m.base)
    if bn in ('rip', 'rsp', 'eip', 'esp') or bn not in REGNUM:
        return None
    # base と同じ(部分)レジスタを register オペランドとして読む命令は対象外
    for op in ins.operands:
        if op.type == x86.X86_OP_REG:
            rn = ins.reg_name(op.reg)
            if rn is None:
                continue
            if _canon(rn) == bn and (op.access & 1):
                return None
    return REGNUM[bn]


def _canon(rn):
    t = {'eax': 'rax', 'ax': 'rax', 'al': 'rax', 'ah': 'rax', 'ecx': 'rcx', 'cx': 'rcx', 'cl': 'rcx', 'ch': 'rcx', 'edx': 'rdx', 'dx': 'rdx', 'dl': 'rdx', 'dh': 'rdx',
         'ebx': 'rbx', 'bx': 'rbx', 'bl': 'rbx', 'bh': 'rbx', 'esi': 'rsi', 'si': 'rsi', 'sil': 'rsi', 'edi': 'rdi', 'di': 'rdi', 'dil': 'rdi',
         'ebp': 'rbp', 'bp': 'rbp', 'bpl': 'rbp'}
    if rn in t:
        return t[rn]
    for suf in ('d', 'w', 'b'):
        if rn.startswith('r') and rn.endswith(suf) and rn[:-1] in REGNUM:
            return rn[:-1]
    return rn


def writes_reg(ins, regnum):
    try:
        regs_read, regs_write = ins.regs_access()
    except Exception:
        return False
    names = {REGNUM_INV[regnum]}
    return any(_canon(ins.reg_name(r)) in names for r in regs_write)


REGNUM_INV = {v: k for k, v in REGNUM.items()}


def patch_disp(ins, newdisp):
    """base-only メモリオペランドを disp8=newdisp 付きへ書換えた命令バイト列 (RIP 相対でない前提)"""
    raw = bytearray(ins.bytes)
    mo = ins.modrm_offset
    modrm = raw[mo]
    mod = modrm >> 6
    rm = modrm & 7
    has_sib = (rm == 4)
    disp_pos = mo + 1 + (1 if has_sib else 0)
    if mod == 0:
        raw[mo] = (modrm & 0x3f) | 0x40
        raw.insert(disp_pos, newdisp & 0xff)
    elif mod == 1:
        raw[disp_pos] = newdisp & 0xff
    else:
        raise ValueError('unexpected mod %d' % mod)
    return bytes(raw)


def derefix_pieces(ins):
    """(pre, body, post, base) を返す。対象外 None. pre/post は lea 補償 (post は base を書く命令では空)"""
    b = deref_base_reg(ins)
    if b is None:
        return None
    mo = ins.modrm_offset
    if (ins.bytes[mo] >> 6) == 3:
        return None
    body = patch_disp(ins, -8)
    pre = lea_disp8(b, 8)
    post = b'' if writes_reg(ins, b) else lea_disp8(b, -8)
    return pre, body, post, b


def p32(v):
    return struct.pack('<i', v)


class _FakeSite:
    def __init__(self, it):
        self.kind, self.mn, self.text = 'cfgthunk', 'call', 'call cfg-thunk (target=rax)'


class Item:
    __slots__ = ('kind', 'va', 'ins', 'raw', 'site', 'newlen', 'newva', 'tmpl', 'copy')

    def __init__(self, kind, va, ins=None, raw=b'', site=None):
        self.kind, self.va, self.ins, self.raw, self.site = kind, va, ins, raw, site
        self.newlen = 0
        self.newva = 0
        self.tmpl = None
        self.copy = False


def split_prefix(raw):
    i = 0
    pref = []
    while i < len(raw) and raw[i] in LEGACY:
        pref.append(raw[i]); i += 1
    rex = 0
    if i < len(raw) and 0x40 <= raw[i] <= 0x4f:
        rex = raw[i]; i += 1
    return pref, rex, i


def expansion_template(it, tail, abi=True, cfg=False, nstk=0):
    """site 展開の (長さ, builder(pos, blk, stub, newtarget_of_rip) ) を返す. 長さは位置非依存."""
    ins = it.ins
    if cfg:   # MSVC CFG thunk (`jmp rax`) 経由: 実 target は rax → mov r11, rax
        head = bytes([0x4c, 0x8b, 0xd8])
        return len(head) + site_tail_len(nstk) + (1 if tail else 0), (head, b'', False, tail, b'', b'', nstk)
    raw = bytes(ins.bytes)
    pref, rex, i = split_prefix(raw)
    assert raw[i] == 0xff, 'unexpected opcode for indirect call/jmp: %s' % raw.hex()
    modrm = raw[i + 1]
    keep_pref = [b for b in pref if b in (0x64, 0x65, 0x67)]
    rm = modrm & 7
    mod = modrm >> 6
    new_rex = 0x4c | (rex & 0x03)           # W + R(r11) + orig X,B
    head = bytes(keep_pref) + bytes([new_rex, 0x8b, (modrm & 0xc7) | (3 << 3)])
    rest = raw[i + 2:]                      # sib / disp
    riprel = (mod == 0 and rm == 5)
    dfx = None
    if mod == 0 and rm != 5 and not riprel:
        # base-only [reg] (RetDec D7 回避): lea B,[B+8] ; mov r11,[B-8] ; lea B,[B-8]
        base_idx = (rm if rm != 4 else (rest[0] & 7)) | (8 if ((rex & 1) if rm != 4 else (rex & 1)) else 0)
        if rm != 4 or (rest[0] >> 3) & 7 == 4:   # SIB で index 無し
            if not (rm == 4 and (rest[0] & 7) == 5):
                if base_idx not in (4,):
                    dfx = base_idx
    if dfx is not None:
        sibpart = rest
        # mod=01 + disp8=-8
        head2 = bytes(keep_pref) + bytes([new_rex, 0x8b, ((modrm & 0x3f) | 0x40 | (3 << 3)) & 0xff])
        rest = bytes(sibpart) + bytes([0xf8])
        head = head2
        pre = lea_disp8(dfx, 8); post = lea_disp8(dfx, -8)
        return (len(pre) + len(head) + len(rest) + len(post) + site_tail_len(nstk) + (1 if tail else 0)), (head, rest, riprel, tail, pre, post, nstk)
    lenA = len(head) + len(rest)
    # 残り: store 5 reg + 4 xmm + r11 / call / loads / (ret)
    lenB = site_tail_len(nstk) + (1 if tail else 0)
    return lenA + lenB, (head, rest, riprel, tail, b'', b'', nstk)


def build_site(it, pos, blk, stub, tpl):
    head, rest, riprel, tail, pre, post, nstk = tpl
    out = bytearray()
    # [A] mov r11, <operand>
    out += pre
    pos = pos + len(pre)
    rest = bytearray(rest)
    if riprel:
        end_a = pos + len(head) + len(rest)
        # 元 disp32 → 絶対 target を保つ
        old_target = it.ins.address + it.ins.size + struct.unpack('<i', bytes(rest[-4:]))[0]
        rest[-4:] = p32(old_target - end_a)
    out += head + rest + post
    cur = pos + len(out) - len(pre)

    def st(opbytes, off):            # opbytes: prefix+opcode+modrm (rip-rel) ; disp32 follows
        nonlocal cur
        ln = len(opbytes) + 4
        d = (blk + off) - (cur + ln)
        out.extend(opbytes + p32(d)); cur += ln

    st(bytes([0x4c, 0x89, 0x1d]), BLK_TARGET)      # mov [rip+], r11
    # stack 引数: RetDec は rsp を連続領域でなく stack_var 別 alloca に分割するため、rsp+0x20 のアドレスは渡せない。
    # 値を連続 BLK 領域へ明示コピーして SSA 配線を保つ (target は退避済みで r11 は空き)
    for k in range(nstk):
        out.extend(bytes([0x4c, 0x8b, 0x9c, 0x24]) + p32(0x20 + 8 * k)); cur += 8   # mov r11,[rsp+disp32]
        st(bytes([0x4c, 0x89, 0x1d]), BLK_STKBUF + 8 * k)
    st(bytes([0x48, 0x89, 0x05]), BLK_RAXIN)       # rax-in (MSVC CFG thunk: 実 target は rax)
    st(bytes([0x48, 0x89, 0x0d]), BLK_RCX)         # rcx
    st(bytes([0x48, 0x89, 0x15]), BLK_RDX)         # rdx
    st(bytes([0x4c, 0x89, 0x05]), BLK_R8)          # r8
    st(bytes([0x4c, 0x89, 0x0d]), BLK_R9)          # r9
    for k, m in enumerate((0x05, 0x0d, 0x15, 0x1d)):   # movsd [rip+], xmmk
        st(bytes([0xf2, 0x0f, 0x11, m]), BLK_X0 + 8 * k)
    # call stub
    out.extend(b'\xe8' + p32(stub - (cur + 5))); cur += 5
    st(bytes([0x48, 0x8b, 0x05]), BLK_RAX)         # mov rax,[rip+]
    st(bytes([0xf2, 0x0f, 0x10, 0x05]), BLK_XMMRET)  # movsd xmm0,[rip+]
    if tail:
        out.append(0xc3)
    return bytes(out)


def stub_code(pos, blk):
    out = bytearray()
    cur = pos

    def op(b, off):
        nonlocal cur
        ln = len(b) + 4
        out.extend(b + p32(blk + off - (cur + ln))); cur += ln
    op(bytes([0x48, 0x8b, 0x05]), BLK_TARGET)                   # mov rax,[tgt]
    for off in (BLK_RCX, BLK_RDX, BLK_R8, BLK_R9, BLK_X0, BLK_X0 + 8, BLK_X0 + 16, BLK_X0 + 24) + tuple(BLK_STKBUF + 8 * k for k in range(NSTK)):
        op(bytes([0x48, 0x03, 0x05]), off)                      # add rax,[..]
    op(bytes([0x48, 0x89, 0x05]), BLK_RAX)                      # mov [rax_res],rax
    op(bytes([0x48, 0x89, 0x05]), BLK_XMMRET)                   # mov [xmm_res],rax
    out.append(0xc3)
    return bytes(out)



def jtm_head(raw):
    """jmp [mem] (FF /4) を cmp qword [mem], imm32 (REX.W 81 /7) の先頭バイト列へ変換する。非対象は None。"""
    i = raw.find(b'\xff')
    if i not in (0, 1) or (i == 1 and not 0x40 <= raw[0] <= 0x4f):
        return None
    rex = raw[0] if i == 1 else 0
    tail = raw[i + 1:]
    if len(tail) < 2 or (tail[0] & 7) != 4 or (tail[0] >> 6) == 3:       # SIB 付き memory 形のみ (rip 相対・reg 形は対象外)
        return None
    return bytes([0x48 | (rex & 3), 0x81, (tail[0] & 0xC7) | 0x38]) + tail[1:]


class Em:
    def __init__(self, pos):
        self.out = bytearray(); self.pos = pos

    def cur(self):
        return self.pos + len(self.out)

    def raw(self, b):
        self.out += b

    def rip(self, opbytes, target):
        ln = len(opbytes) + 4
        self.out += opbytes + p32(target - (self.cur() + ln))


ST_INT = [(bytes([0x48, 0x89, 0x0d]), BLK_RCX), (bytes([0x48, 0x89, 0x15]), BLK_RDX), (bytes([0x4c, 0x89, 0x05]), BLK_R8), (bytes([0x4c, 0x89, 0x0d]), BLK_R9)]
LD_INT = [(bytes([0x48, 0x8b, 0x0d]), BLK_RCX), (bytes([0x48, 0x8b, 0x15]), BLK_RDX), (bytes([0x4c, 0x8b, 0x05]), BLK_R8), (bytes([0x4c, 0x8b, 0x0d]), BLK_R9)]
XM = (0x05, 0x0d, 0x15, 0x1d)
ABI_SPILL_LEN = 4 * 7 + 4 * 8        # 60
ABI_RELOAD_LEN = 4 * 7 + 4 * 8       # 60
ABI_RETST_LEN = 7 + 8 + (8 if ABI_XMM1 else 0)   # 23 (xmm1 戻りあり) / 15
ABI_RETLD_LEN = 7 + 8 + (8 if ABI_XMM1 else 0)


def abi_spill(em, blk):
    for op, off in ST_INT:
        em.rip(op, blk + off)
    for k, m in enumerate(XM):
        em.rip(bytes([0xf2, 0x0f, 0x11, m]), blk + BLK_X0 + 8 * k)


def abi_reload(em, blk):
    for op, off in LD_INT:
        em.rip(op, blk + off)
    for k, m in enumerate(XM):
        em.rip(bytes([0xf2, 0x0f, 0x10, m]), blk + BLK_X0 + 8 * k)


def abi_ret_store(em, blk):
    em.rip(bytes([0x48, 0x89, 0x05]), blk + BLK_RAX)
    em.rip(bytes([0xf2, 0x0f, 0x11, 0x05]), blk + BLK_XMMRET)
    if ABI_XMM1:
        em.rip(bytes([0xf2, 0x0f, 0x11, 0x0d]), blk + BLK_XMMRET1)   # movsd [rip+],xmm1


def abi_ret_load(em, blk):
    em.rip(bytes([0x48, 0x8b, 0x05]), blk + BLK_RAX)
    em.rip(bytes([0xf2, 0x0f, 0x10, 0x05]), blk + BLK_XMMRET)
    if ABI_XMM1:
        em.rip(bytes([0xf2, 0x0f, 0x10, 0x0d]), blk + BLK_XMMRET1)   # movsd xmm1,[rip+]


BLK_CA, BLK_CB, BLK_CFLAGS, BLK_CKIND = 0xA0, 0xA8, 0xB0, 0xB8
COMIS_KIND = {'comisd': 0, 'ucomisd': 1, 'comiss': 2, 'ucomiss': 3, 'vcomisd': 0, 'vucomisd': 1, 'vcomiss': 2, 'vucomiss': 3}


def modrm_tail_len(raw, mo):
    """modrm の後ろの sib+disp のバイト数 (capstone の disp_size は 66 prefix 命令で誤るため自前)"""
    modrm = raw[mo]
    mod, rm = modrm >> 6, modrm & 7
    if mod == 3:
        return 0
    n = 0
    if rm == 4:
        n += 1
        base = raw[mo + 1] & 7
        if mod == 0 and base == 5:
            return n + 4
    if mod == 0:
        return n + (4 if rm == 5 else 0)
    return n + (1 if mod == 1 else 4)


def load_r11_len(ins):
    """メモリオペランド ins.operands[1] を r11 に load する命令列の長さ (derefix 込み)"""
    return len(_load_r11_parts(ins, 0)[0])


def _load_r11_parts(ins, pos):
    raw = bytes(ins.bytes)
    mo = ins.modrm_offset
    modrm = raw[mo]
    mod, rm = modrm >> 6, modrm & 7
    pref, rex, i = split_prefix(raw[:mo])
    keep = bytes(b for b in pref if b in (0x64, 0x65, 0x67))
    new_rex = 0x4c | (rex & 0x03)
    rest = bytearray(raw[mo + 1:mo + 1 + modrm_tail_len(raw, mo)])
    if mod == 0 and rm == 5:            # rip-relative
        head = keep + bytes([new_rex, 0x8b, (modrm & 0xc7) | 0x18])
        end = pos + len(head) + len(rest)
        old = ins.address + ins.size + struct.unpack('<i', bytes(rest[-4:]))[0]
        rest[-4:] = p32(((old - end) + 2**31) % 2**32 - 2**31)
        return head + bytes(rest), False
    if mod == 0 and not (rm == 4 and (raw[mo + 1] & 7) == 5):
        # base-only: lea B,[B+8] ; mov r11,[B-8] ; lea B,[B-8]
        base = (rm if rm != 4 else (raw[mo + 1] & 7)) | (8 if (rex & 1) else 0)
        if base != 4 and (rm != 4 or ((raw[mo + 1] >> 3) & 7) == 4):
            head = keep + bytes([new_rex, 0x8b, ((modrm & 0x3f) | 0x40 | 0x18)])
            return lea_disp8(base, 8) + head + bytes(raw[mo + 1:mo + 1 + (1 if rm == 4 else 0)]) + b'\xf8' + lea_disp8(base, -8), True
    head = keep + bytes([new_rex, 0x8b, (modrm & 0xc7) | 0x18])
    return head + bytes(rest), False


def comis_len(ins):
    op0, op1 = ins.operands[0], ins.operands[1]
    n = (8 + (1 if ins.reg_name(op0.reg) in XMM_HI else 0))
    if op1.type == x86.X86_OP_REG:
        n += 8 + (1 if ins.reg_name(op1.reg) in XMM_HI else 0)
    else:
        n += load_r11_len(ins) + 7
    return n + 10 + 5 + 3 + 6 + 1 + 3


XMM_HI = {'xmm%d' % k for k in range(8, 16)}


def build_comis(ins, pos, blk, cstub):
    em = Em(pos)
    kind = COMIS_KIND[ins.mnemonic]

    def spill_xmm(reg, off):
        n = int(reg[3:])
        pre = bytes([0xf2]) + (bytes([0x44]) if n >= 8 else b'') + bytes([0x0f, 0x11, ((n & 7) << 3) | 5])
        em.rip(pre, blk + off)
    spill_xmm(ins.reg_name(ins.operands[0].reg), BLK_CA)
    op1 = ins.operands[1]
    if op1.type == x86.X86_OP_REG:
        spill_xmm(ins.reg_name(op1.reg), BLK_CB)
    else:
        b, _ = _load_r11_parts(ins, em.cur())
        em.raw(b)
        em.rip(bytes([0x4c, 0x89, 0x1d]), blk + BLK_CB)
    em.rip(bytes([0xc7, 0x05]), blk + BLK_CKIND - 4)                    # mov dword [rip+d], imm32 (disp は imm の後ろ基準で補正)
    em.out += struct.pack('<I', kind)
    # 上の rip() は disp 計算を imm 長 (4) 分補正済み
    em.raw(b'\x49\x89\xc3')                                             # mov r11, rax   (call 前に退避: RetDec は stub の戻り値を rax と見なす。push/pop は stack 最適化が壊すので使わない)
    em.raw(b'\xe8' + p32(cstub - (em.cur() + 5)))
    em.rip(bytes([0x8a, 0x25]), blk + BLK_CFLAGS)                        # mov ah,[flags]
    em.raw(b'\x9e')                                                     # sahf
    em.raw(b'\x4c\x89\xd8')                                             # mov rax, r11
    return bytes(em.out)


def comis_stub_code(pos, blk):
    em = Em(pos)
    em.rip(bytes([0x48, 0x8b, 0x05]), blk + BLK_CA)
    em.rip(bytes([0x48, 0x03, 0x05]), blk + BLK_CB)
    em.rip(bytes([0x48, 0x03, 0x05]), blk + BLK_CKIND)
    em.rip(bytes([0x48, 0x89, 0x05]), blk + BLK_CFLAGS)
    em.raw(b'\xc3')
    return bytes(em.out)


COMIS_STUB_LEN = 7 * 4 + 1


STUB_LEN = 7 * (11 + NSTK) + 1


def blk_overlap(blk, ranges):
    """(lo, hi, name) の再配置範囲のうち BLK 域 [blk, blk+BLK_RESERVE) と交わるものを返す (#2565)"""
    return [r for r in ranges if r[0] < blk + BLK_RESERVE and r[1] > blk]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pe', required=True)
    ap.add_argument('--funcs', required=True, help='VA 1 行 1 個 (または "0xA-0xB" ranges の CSV も可)')
    ap.add_argument('--out', required=True)
    ap.add_argument('--map', required=True)
    ap.add_argument('--blk-va', type=lambda x: int(x, 0))
    ap.add_argument('--rip-data', action='store_true', default=True, help='call [rip+data] (IAT 以外) も dispatch 化 (既定 on)')
    ap.add_argument('--no-rip-data', dest='rip_data', action='store_false')
    ap.add_argument('--no-derefix', dest='derefix', action='store_false', default=True, help='RetDec D7 (zero-disp live-in reg 参照の脱落) 回避 lea 補償を無効化')
    ap.add_argument('--no-abi', dest='abi', action='store_false', default=True, help='closure 内 direct call/ret/prologue の memory-ABI 化 (rcx,rdx,r8,r9,xmm0-3 / rax,xmm0) を無効化')
    ap.add_argument('--no-comis', dest='comis', action='store_false', default=True, help='comis/ucomis の flag 経路 (stub + sahf) 化を無効化')
    ap.add_argument('--no-jtchain', dest='jtchain', action='store_false', default=True, help='jmp reg 型 jump table を 比較分岐列 (cmp/je) へ展開する処理を無効化 (既定 on: RetDec が switch 化に失敗する表の救済)')
    ap.add_argument('--func-end-from-dsm', action='append', default=[])
    a = ap.parse_args()

    img = A.Image(a.pe)
    toks = []
    for fpath in a.funcs.split(','):
        toks += [t for t in open(fpath).read().replace(',', '\n').split() if t and not t.startswith('#')]
    ranges_given = {}
    fnl = set()
    for t in toks:
        if '-' in t:
            lo, hi = t.split('-')
            if int(hi, 16) - int(lo, 16) >= 4:
                ranges_given[int(lo, 16)] = int(hi, 16)
            fnl.add(int(lo, 16))
        else:
            fnl.add(int(t, 16))
    fns = sorted(fnl)
    for d in a.func_end_from_dsm:
        ranges_given.update(A.parse_dsm_ranges(d))
    img.set_extra_starts(fns)
    dis = A.Disasm(img)
    sec_end = max(lo + len(data) for lo, rva, data, name, ch in img.secs)

    # ---- plan
    funcs = {}
    for f in fns:
        rg = img.func_range(f)
        if f in ranges_given:
            rg = (f, ranges_given[f])
        if not rg:
            print('skip (no range): %x' % f, file=sys.stderr); continue
        fs, fe = rg
        sites = {}
        seen = dis.scan_function(fs, fe, sites)
        gap_ins = {}
        dis.gap_sweep(fs, fe, seen, sites, want_insns=gap_ins)
        allins = dict(seen); allins.update(gap_ins)
        # 範囲末尾の padding(cc)は落とす (関数本体は最後の命令まで)
        items = []
        pos = fs
        order = sorted(allins)
        for va in order:
            if va < pos:
                continue
            if va > pos:
                items.append(Item('data', pos, raw=img.read(pos, va - pos)))
            ins = allins[va]
            site = sites.get(va)
            items.append(Item('ins', va, ins=ins, site=site))
            pos = va + ins.size
        if pos < fe:
            items.append(Item('data', pos, raw=img.read(pos, fe - pos)))
        funcs[f] = (fs, fe, items)

    # ---- chained 断片 (.pdata CHAININFO = 親関数の hot/cold chunk) を、参照する関数へ複製 inline (RetDec は断片を単独関数として扱えず stack が壊れる)
    frags = {f for f in funcs if f in img.pdata_chained}
    lomap_needed = {}
    nfrag = 0
    for f in [x for x in funcs if x not in frags]:
        fs, fe, items = funcs[f]
        pending = [it for it in items if it.kind == 'ins']
        done = set()
        while pending:
            nxt = []
            for it in pending:
                ins = it.ins
                if ins.mnemonic.startswith('j') and ins.operands and ins.operands[0].type == x86.X86_OP_IMM:
                    t = ins.operands[0].imm
                    if t in frags and t not in done and not (fs <= t < fe):
                        done.add(t); nfrag += 1
                        for it2 in funcs[t][2]:
                            c = Item(it2.kind, it2.va, it2.ins, it2.raw, it2.site)
                            c.copy = True
                            items.append(c)
                            if c.kind == 'ins':
                                nxt.append(c)
            pending = nxt
    for g in frags:
        del funcs[g]
    # ---- size
    nsites = 0
    nderef = 0
    nabi = collections.Counter()
    ncomis = 0
    njt = 0
    fset = set(funcs)
    cfg_thunks = {f for f in funcs if img.read(f, 2) == b'\xff\xe0'}      # MSVC CFG dispatch thunk (jmp rax)
    ncfg = 0
    nstk_hist = collections.Counter()
    for f, (fs, fe, items) in funcs.items():
        if a.abi:
            pro = Item('pro', fs); pro.newlen = ABI_RELOAD_LEN
            items.insert(0, pro)
        for ii, it in enumerate(items):
            if it.kind == 'data':
                it.newlen = len(it.raw); continue
            if it.kind == 'pro':
                continue
            ins = it.ins
            st = it.site
            if a.jtchain and st is not None and st.kind == 'jmptable' and st.mn == 'jmp' and st.targets and ins.operands[0].type == x86.X86_OP_REG \
                    and ins.reg_name(ins.operands[0].reg) in REGNUM:
                it.tmpl = ('jt', REGNUM[ins.reg_name(ins.operands[0].reg)], list(st.targets))
                it.newlen = 16 * len(st.targets) + 2
                njt += 1
                continue
            if a.jtchain and st is not None and st.kind == 'jmptable' and st.mn == 'jmp' and st.targets and ins.operands[0].type == x86.X86_OP_MEM \
                    and all(0 <= t < 0x80000000 for t in st.targets):
                head = jtm_head(bytes(ins.bytes))
                if head is not None:
                    it.tmpl = ('jtm', head, list(st.targets))
                    it.newlen = (len(head) + 4 + 6) * len(st.targets) + 2
                    njt += 1
                    continue
            expand = False
            if st is not None and st.kind in ('vtable', 'reg', 'indexed', 'abs_mem') or (st is not None and st.kind == 'rip_data' and a.rip_data):
                expand = True
            cfg = False
            if st is not None and st.kind == 'rip_data' and st.mn == 'call':
                sv = img.read(st.disp, 8)
                if sv is not None and struct.unpack('<Q', sv)[0] in cfg_thunks:
                    cfg = True
            if expand:
                tail = (st.mn == 'jmp')
                nk = 0 if tail else stk_slots_stored(items, ii)
                nstk_hist[nk] += 1
                it.newlen, it.tmpl = expansion_template(it, tail, a.abi, cfg, nk)
                nsites += 1
                ncfg += cfg
                continue
            mn = ins.mnemonic
            raw = bytes(ins.bytes)
            grp = set(ins.groups)
            if ins.operands and ins.operands[0].type == x86.X86_OP_IMM and (x86.X86_GRP_JUMP in grp or x86.X86_GRP_CALL in grp or mn == 'call'):
                tgt = ins.operands[0].imm
                if mn == 'call' and tgt in cfg_thunks:
                    nk = stk_slots_stored(items, ii); nstk_hist[nk] += 1
                    it.newlen, it.tmpl = expansion_template(it, False, a.abi, True, nk); nsites += 1; ncfg += 1
                    it.site = it.site or _FakeSite(it)
                    continue
                if raw[0] in (0xe0, 0xe1, 0xe2, 0xe3):
                    it.newlen = 9
                else:
                    it.newlen = 5 if mn in ('call', 'jmp') else 6
                if a.abi and mn == 'call' and tgt in fset:
                    it.tmpl = ('dcall',); it.newlen = ABI_SPILL_LEN + 5 + ABI_RETLD_LEN; nabi['dcall'] += 1
                elif a.abi and mn == 'jmp' and tgt in fset and tgt != fs:
                    it.tmpl = ('tjmp',); it.newlen = ABI_SPILL_LEN + 5; nabi['tjmp'] += 1
            elif a.comis and mn in COMIS_KIND and len(ins.operands) == 2 and ins.operands[0].type == x86.X86_OP_REG and ins.operands[1].type in (x86.X86_OP_REG, x86.X86_OP_MEM):
                it.tmpl = ('comis',); it.newlen = comis_len(ins); ncomis += 1
            elif a.abi and mn in ('ret', 'retf') and ins.operands == [] or (a.abi and mn == 'ret'):
                it.tmpl = ('ret',); it.newlen = ABI_RETST_LEN + ins.size; nabi['ret'] += 1
            else:
                dp = derefix_pieces(ins) if a.derefix else None
                if dp is not None:
                    it.tmpl = ('dfx', dp)
                    it.newlen = len(dp[0]) + len(dp[1]) + len(dp[2])
                    nderef += 1
                else:
                    it.newlen = ins.size
    # ---- layout
    image_size = img.pe.OPTIONAL_HEADER.SizeOfImage
    sect_va = img.base + ((image_size + 0xfff) & ~0xfff)
    # BLK の VA は消費側 (fw_rt.c・fw_boot.c・hostshim・fw_run.mjs・fw_stage2.sh の --blk) が直書きするため据え置く。
    # 再配置の方を place() で BLK 域の外へ送る (#2565)
    blk = a.blk_va if a.blk_va else (img.base + image_size + 0x4000000 if img.base > 0x100000000 else img.base + image_size + 0x100000)
    cur = sect_va
    new_start = {}

    def next_slot(c):
        # 16 byte 整列。 直前の関数/stub の終端とちょうど連続する (終端が既に 16 の倍数) と、RetDec の --select-ranges が
        # [a,b)+[b,c) を 1 関数に併合して後続関数の define が落ちる (#514: eq-filter 4 block で 5 関数) ので 1 paragraph 空ける
        a = (c + 15) & ~15
        return a + 16 if a == c else a

    def place(c, n):
        # [c, c+n) が BLK 域と重なるなら、BLK 域の直後 (16 byte 整列) へ送る (#2565)
        p = (c + 15) & ~15
        if p < blk + BLK_RESERVE and p + n > blk:
            p = (blk + BLK_RESERVE + 15) & ~15
        return p
    for k, (f, (fs, fe, items)) in enumerate(funcs.items()):
        cur = place(next_slot(cur) if k else sect_va, sum(it.newlen for it in items))
        new_start[f] = cur
        for it in items:
            it.newva = cur; cur += it.newlen
    cur = next_slot(cur)
    stub_va = place(cur, STUB_LEN)
    cur = stub_va + STUB_LEN
    cstub_va = place(next_slot(cur), COMIS_STUB_LEN)
    cur = cstub_va + COMIS_STUB_LEN
    sect_end = cur
    reloc = [(new_start[f], new_start[f] + sum(it.newlen for it in funcs[f][2]), 'func %x' % f) for f in funcs]
    reloc += [(stub_va, stub_va + STUB_LEN, 'stub'), (cstub_va, cstub_va + COMIS_STUB_LEN, 'comis_stub')]
    ovl = blk_overlap(blk, reloc)
    if ovl:
        sys.exit('BLK 域 %#x..%#x が再配置範囲と重なる (fail-closed・#2565): %s' % (blk, blk + BLK_RESERVE, ovl[:5]))
    # old->new map per function (instruction starts)
    omap = {}
    lomap = {}
    for f, (fs, fe, items) in funcs.items():
        lomap[f] = {}
        for it in items:
            if it.kind == 'ins':
                if it.copy:
                    lomap[f][it.va] = it.newva
                else:
                    omap[it.va] = it.newva

    # ---- emit
    buf = bytearray(sect_end - sect_va)
    bo = blk - sect_va
    if 0 <= bo and bo + BLK_RESERVE <= len(buf):
        buf[bo:bo + BLK_RESERVE] = bytes(BLK_RESERVE)                                         # BLK 域は 0 埋め (#2565)
    insn_map = []   # (newva, newlen, origva)
    jt_patches = []  # (table_va, scale, relb, [(index, newtarget)])
    errs = collections.Counter()
    for f, (fs, fe, items) in funcs.items():
        for it in items:
            off = it.newva - sect_va
            if it.kind == 'data':
                buf[off:off + it.newlen] = it.raw; continue
            if it.kind == 'pro':
                em = Em(it.newva); abi_reload(em, blk)
                assert len(em.out) == it.newlen
                buf[off:off + it.newlen] = em.out
                insn_map.append((it.newva, it.newlen, fs))
                continue
            ins = it.ins
            raw = bytes(ins.bytes)
            insn_map.append((it.newva, it.newlen, it.va))
            if it.tmpl is not None and it.tmpl[0] == 'dfx':
                pre, body, post, _b = it.tmpl[1]
                buf[off:off + it.newlen] = pre + body + post
                continue
            if it.tmpl is not None and it.tmpl[0] == 'jt':
                reg, tgts = it.tmpl[1], it.tmpl[2]
                em = Em(it.newva)
                for t in tgts:
                    em.rip(bytes([0x4c, 0x8d, 0x1d]), t)                                  # lea r11,[rip+orig target VA]
                    em.raw(bytes([0x4c | (1 if reg >= 8 else 0), 0x39, 0xd8 | (reg & 7)]))   # cmp reg, r11
                    em.raw(bytes([0x0f, 0x84]) + p32(omap[t] - (em.cur() + 6)))           # je new target
                em.raw(b'\x0f\x0b')                                                          # ud2 (表外)
                assert len(em.out) == it.newlen
                buf[off:off + it.newlen] = em.out
                continue
            if it.tmpl is not None and it.tmpl[0] == 'jtm':
                head, tgts = it.tmpl[1], it.tmpl[2]
                em = Em(it.newva)
                for t in tgts:
                    em.raw(head + p32(t))                                                    # cmp qword [mem], target
                    em.raw(bytes([0x0f, 0x84]) + p32(omap[t] - (em.cur() + 6)))           # je new target
                em.raw(b'\x0f\x0b')                                                          # ud2 (表外)
                assert len(em.out) == it.newlen
                buf[off:off + it.newlen] = em.out
                continue
            if it.tmpl is not None and it.tmpl[0] == 'comis':
                b = build_comis(ins, it.newva, blk, cstub_va)
                assert len(b) == it.newlen, (hex(it.va), len(b), it.newlen)
                buf[off:off + it.newlen] = b
                continue
            if it.tmpl is not None and it.tmpl[0] == 'ret':
                em = Em(it.newva); abi_ret_store(em, blk); em.raw(raw)
                assert len(em.out) == it.newlen
                buf[off:off + it.newlen] = em.out
                continue
            if it.tmpl is not None and it.tmpl[0] in ('dcall', 'tjmp'):
                tgt = ins.operands[0].imm
                em = Em(it.newva); abi_spill(em, blk)
                if it.tmpl[0] == 'dcall':
                    em.raw(b'\xe8' + p32(new_start[tgt] - (em.cur() + 5))); abi_ret_load(em, blk)
                else:
                    em.raw(b'\xe9' + p32(new_start[tgt] - (em.cur() + 5)))
                assert len(em.out) == it.newlen, (hex(it.va), len(em.out), it.newlen)
                buf[off:off + it.newlen] = em.out
                continue
            if it.tmpl is not None:
                b = build_site(it, it.newva, blk, stub_va, it.tmpl)
                assert len(b) == it.newlen, (hex(it.va), len(b), it.newlen)
                buf[off:off + it.newlen] = b
                continue
            mn = ins.mnemonic
            grp = set(ins.groups)
            if ins.operands and ins.operands[0].type == x86.X86_OP_IMM and (x86.X86_GRP_JUMP in grp or x86.X86_GRP_CALL in grp or mn == 'call'):
                tgt = ins.operands[0].imm
                if tgt in lomap[f] and mn != 'call':
                    nt = lomap[f][tgt]            # 複製 inline した断片内への分岐
                elif tgt == fs:
                    nt = omap[fs]                 # 自関数先頭への loop: prologue(reload) は再実行しない
                elif tgt in new_start:
                    nt = new_start[tgt]
                else:
                    nt = omap.get(tgt, tgt)
                if raw[0] in (0xe0, 0xe1, 0xe2, 0xe3):
                    b = bytes([raw[0], 0x02, 0xeb, 0x05, 0xe9]) + p32(nt - (it.newva + 9))
                elif mn == 'call':
                    b = b'\xe8' + p32(nt - (it.newva + 5))
                elif mn == 'jmp':
                    b = b'\xe9' + p32(nt - (it.newva + 5))
                else:
                    pref, rex, i = split_prefix(raw)
                    cc = raw[i] & 0x0f if raw[i] != 0x0f else raw[i + 1] & 0x0f
                    b = bytes([0x0f, 0x80 | cc]) + p32(nt - (it.newva + 6))
                assert len(b) == it.newlen
                buf[off:off + it.newlen] = b
                continue
            b = bytearray(raw)
            if any(op.type == x86.X86_OP_MEM and op.mem.base == x86.X86_REG_RIP for op in ins.operands):
                # capstone の disp_size/disp_offset は 66/F2 prefix 付き SSE で誤る (disp_size=2 等) ので modrm から自前計算
                mo = ins.modrm_offset
                assert (b[mo] >> 6) == 0 and (b[mo] & 7) == 5, 'rip-rel modrm expected at %x' % ins.address
                dpos = mo + 1
                old = struct.unpack_from('<i', b, dpos)[0]
                target = ins.address + ins.size + old
                struct.pack_into('<i', b, dpos, target - (it.newva + ins.size))
            buf[off:off + it.newlen] = b
    # stub
    so = stub_va - sect_va
    buf[so:so + STUB_LEN] = stub_code(stub_va, blk)
    co = cstub_va - sect_va
    buf[co:co + COMIS_STUB_LEN] = comis_stub_code(cstub_va, blk)
    # jump tables
    orig_img = open(a.pe, 'rb').read()
    pe_patches = []   # (file_off, bytes)
    jt_done = set()
    for f, (fs, fe, items) in funcs.items():
        for it in items:
            st = it.site
            if st is None or st.kind != 'jmptable' or not st.jt:
                continue
            if it.tmpl is not None and it.tmpl[0] in ('jt', 'jtm'):
                continue                       # 比較分岐列へ展開済み: 表は原 VA のまま
            taddr, scale, relb, n = st.jt
            if (taddr, scale) in jt_done:
                continue
            jt_done.add((taddr, scale))
            for i in range(n if n else 256):
                ea = taddr + i * scale
                raw = img.read(ea, scale)
                if raw is None:
                    break
                v = struct.unpack('<I' if scale == 4 else '<Q', raw)[0]
                t = (relb + v) if relb is not None else v
                if not (fs <= t < fe):
                    continue
                nt = omap.get(t)
                if nt is None:
                    errs['jt target not insn start'] += 1; continue
                nv = (nt - relb) if relb is not None else nt
                newb = struct.pack('<I' if scale == 4 else '<Q', nv & (0xffffffff if scale == 4 else 0xffffffffffffffff))
                if fs <= ea < fe:
                    # in-code table: 新コピー内の data item に書く
                    for it2 in items:
                        if it2.kind == 'data' and it2.va <= ea < it2.va + it2.newlen:
                            o2 = it2.newva - sect_va + (ea - it2.va)
                            buf[o2:o2 + scale] = newb
                            break
                    else:
                        errs['in-code table entry on insn'] += 1
                else:
                    pe_patches.append((ea, newb))
    if 0 <= bo and bo + BLK_RESERVE <= len(buf):
        assert not any(buf[bo:bo + BLK_RESERVE]), 'BLK 域にコードバイトが残る (#2565)'
    # ---- PE 出力: section 追加
    pe = img.pe
    hdr_end = pe.DOS_HEADER.e_lfanew + 4 + 20 + pe.FILE_HEADER.SizeOfOptionalHeader
    nsec = pe.FILE_HEADER.NumberOfSections
    sec_tab_end = hdr_end + 40 * nsec
    assert sec_tab_end + 40 <= pe.OPTIONAL_HEADER.SizeOfHeaders, 'no room for section header'
    fa = pe.OPTIONAL_HEADER.FileAlignment
    data = bytearray(orig_img)
    # in-image table patches: va -> file offset via sections
    for ea, nb in pe_patches:
        for s in pe.sections:
            lo = img.base + s.VirtualAddress
            if lo <= ea < lo + s.SizeOfRawData:
                fo = s.PointerToRawData + (ea - lo)
                data[fo:fo + len(nb)] = nb
                break
    raw_off = (len(data) + fa - 1) // fa * fa
    data.extend(b'\0' * (raw_off - len(data)))
    raw_size = (len(buf) + fa - 1) // fa * fa
    data.extend(bytes(buf) + b'\0' * (raw_size - len(buf)))
    sh = struct.pack('<8sIIIIIIHHI', b'.icall', len(buf), sect_va - img.base, raw_size, raw_off, 0, 0, 0, 0, 0xe0000060)
    data[sec_tab_end:sec_tab_end + 40] = sh
    nsec_off = pe.DOS_HEADER.e_lfanew + 4 + 2
    struct.pack_into('<H', data, nsec_off, nsec + 1)
    soi = pe.DOS_HEADER.e_lfanew + 4 + 20 + 56
    new_size = ((sect_va - img.base + len(buf)) + pe.OPTIONAL_HEADER.SectionAlignment - 1) // pe.OPTIONAL_HEADER.SectionAlignment * pe.OPTIONAL_HEADER.SectionAlignment
    struct.pack_into('<I', data, soi, new_size)
    open(a.out, 'wb').write(data)
    m = {'pe': a.pe, 'image_base': img.base, 'section_va': sect_va, 'section_size': len(buf), 'blk': blk, 'blk_reserve': BLK_RESERVE, 'blk_stk': BLK_STK, 'blk_stkbuf': BLK_STKBUF, 'nstk_max': NSTK, 'nstk_hist': dict(nstk_hist), 'stub': stub_va, 'stub_len': STUB_LEN, 'comis_stub': cstub_va, 'comis_stub_len': COMIS_STUB_LEN, 'ncomis': ncomis,
         'nsites': nsites, 'nfrag_inlined': nfrag, 'njt': njt, 'ncfg': ncfg, 'cfg_thunks': sorted(cfg_thunks), 'nderef': nderef, 'abi': dict(nabi), 'nfuncs': len(funcs), 'errors': dict(errs),
         'func_map': {hex(f): hex(new_start[f]) for f in funcs},
         'func_range_new': {hex(f): [hex(new_start[f]), hex(new_start[f] + sum(it.newlen for it in funcs[f][2]))] for f in funcs},
         'insn_ranges': [[n, l, o] for n, l, o in insn_map],
         'sites': [{'va': it.va, 'new': it.newva, 'kind': it.site.kind, 'mn': it.site.mn, 'text': it.site.text, 'fn': f, 'nstk': (it.tmpl[6] if len(it.tmpl) > 6 else 0)}
                   for f, (fs, fe, items) in funcs.items() for it in items if it.kind == 'ins' and it.tmpl is not None and isinstance(it.tmpl[0], bytes)],
         }
    json.dump(m, open(a.map, 'w'))
    ranges = ','.join('%s-%s' % tuple(v) for v in m['func_range_new'].values())
    open(a.map + '.ranges', 'w').write(ranges)
    print('rewrote %d funcs, %d sites (うち CFG thunk %d), %d derefix, abi %s -> %s (section +%d B, stub %x, blk %x), errors %s [comis %d, jt-chain %d]' % (len(funcs), nsites, ncfg, nderef, dict(nabi), a.out, len(buf), stub_va, blk, dict(errs), ncomis, njt))


if __name__ == '__main__':
    main()
