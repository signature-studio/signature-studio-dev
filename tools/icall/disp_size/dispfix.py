#!/usr/bin/env python3
"""dispfix — capstone の disp_size を信用せずに x86-64 命令の disp 位置・サイズを確定する共通 helper (CAB-229, 欠陥 D9)

D9 の実体 (capstone v5 arch/X86/X86DisassemblerDecoder.c; 5.0.5〜5.0.9 / 6.0.0a11 全てで再現):
  64bit mode の prefix 解析で `displacementSize = hasOpSize ? 2 : 4` (REX.W 無しの枝) を設定するが、
  disp32 を読む readDisplacement() は eaDisplacement だけを見て displacementSize を更新しない。
  → 0x66 prefix (REX.W 無し) 付きの disp32 メモリ命令 (rip 相対 / [reg+disp32] / [abs32]) は disp_size=2 と誤報告される。
  (disp_offset と mem.disp の値は正しい。disp8 は 1 に上書きされるので正しい。F2/F3/REX/segment/67/lock 単独は無害。)
本モジュールは modrm の mod/rm/SIB から disp を再計算する。modrm の有無は capstone の modrm_offset (matrix で検証済み) か
opcode 表 (has_modrm) のどちらかで決め、prefix / opcode map / VEX / EVEX は自前で解析する。

公開 API:
  disp_span(ins) -> (offset, size) | None   disp バイト列の命令内位置/長さ (補正済み)。`ins.disp_offset/disp_size` の drop-in
  disp_size(ins) / disp_offset(ins)         同上を個別に
  is_rip_relative(ins), rip_target(ins)     mod=00 rm=101 か / ins.address+ins.size+disp32 (raw から再読込)
  zero_disp32(buf, insn_off, ins)           正規化ハッシュ用: disp32 をゼロ化 (True = 実施)
  layout(raw, has_modrm_=None) -> Layout    capstone 無しで raw (1 命令分) から prefix/map/modrm/disp を解析
  opsize(lay) / immz_size(lay) / addrsize(lay)   prefix 込みの実効オペランド長 (REX.W > 66 > 既定)
  has_modrm(map, opcode, enc)               opcode 表
  d9_affected(ins)                          capstone の disp_size/disp_offset がこの命令で誤っているか (DEFECTS 信号用)
  capstone_has_d9()                         実行中の capstone が D9 を持つか (起動時 canary; 修正済み upstream なら False)
imm の位置/長さは capstone の imm_offset / imm_size が全 case で正しい (matrix 実測) ので補正しない。
"""
import struct
from collections import namedtuple

LEGACY_PREFIX = frozenset([0x66, 0x67, 0xF0, 0xF2, 0xF3, 0x2E, 0x36, 0x3E, 0x26, 0x64, 0x65])

Layout = namedtuple('Layout', [
    'prefixes',      # legacy prefix bytes (出現順)
    'rex',           # REX byte (0 = 無し)
    'enc',           # 'legacy' | 'vex2' | 'vex3' | 'evex' | 'xop'
    'map',           # 0=1byte 1=0F 2=0F38 3=0F3A (vex/evex は mmmmm / mmm)
    'opcode',        # opcode 最終 byte
    'opcode_offset',
    'modrm_offset',  # None = modrm 無し
    'mod', 'reg', 'rm',
    'sib_offset',    # None = SIB 無し
    'disp_offset', 'disp_size',  # disp 無しは (None, 0)
    'rip',           # mod=00 rm=101 (67 prefix 付きなら eip 相対)
    'moffs',         # A0-A3 (modrm 無し絶対アドレス)
    'opsize16',      # 実効 66 (REX.W 無し)
    'rexw', 'addr32', 'end'])


_NO_MODRM_1B = {o for o in range(0x40) if (o & 7) >= 4}
_NO_MODRM_1B |= {0x0F} | set(range(0x40, 0x60)) | {0x60, 0x61, 0x68, 0x6A, 0x6C, 0x6D, 0x6E, 0x6F}
_NO_MODRM_1B |= set(range(0x70, 0x80)) | set(range(0x90, 0xC0))
_NO_MODRM_1B |= {0xC2, 0xC3, 0xC8, 0xC9, 0xCA, 0xCB, 0xCC, 0xCD, 0xCE, 0xCF, 0xD4, 0xD5, 0xD6, 0xD7}
_NO_MODRM_1B |= set(range(0xE0, 0xF0)) | {0xF1, 0xF4, 0xF5, 0xF8, 0xF9, 0xFA, 0xFB, 0xFC, 0xFD}
_NO_MODRM_0F = {0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0E, 0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37,
                0x77, 0xA0, 0xA1, 0xA2, 0xA8, 0xA9, 0xAA} | set(range(0x80, 0x90)) | set(range(0xC8, 0xD0))


def has_modrm(mp, opcode, enc='legacy'):
    """(map, opcode) が ModRM byte を持つか。mp: 0=1byte 1=0F 2=0F38 3=0F3A。VEX/EVEX は vzeroupper (VEX 0F 77) 以外 modrm 有り。"""
    if enc != 'legacy':
        return not (enc in ('vex2', 'vex3') and mp == 1 and opcode == 0x77)
    if mp == 0:
        return opcode not in _NO_MODRM_1B
    if mp == 1:
        return opcode not in _NO_MODRM_0F
    return True


def _modrm_tail(modrm, sib):
    """(sib_len, disp_size, rip). 64bit mode では 67 prefix 付きでも構造は同じ (rm=101 は eip 相対 disp32)。"""
    mod, rm = modrm >> 6, modrm & 7
    if mod == 3:
        return 0, 0, False
    if rm == 4:
        if mod == 0:
            return 1, (4 if (sib & 7) == 5 else 0), False
        return 1, (1 if mod == 1 else 4), False
    if mod == 0:
        return 0, (4 if rm == 5 else 0), rm == 5
    return 0, (1 if mod == 1 else 4), False


def layout(raw, has_modrm_=None):
    """raw (命令先頭から。末尾に余分な byte があっても可) の prefix / map / modrm / disp を解析する。
    has_modrm_ = None なら opcode 表、True/False なら強制 (capstone の modrm_offset 由来)。"""
    n = len(raw)
    i = 0
    pfx = []
    rex = 0
    while i < n:
        b = raw[i]
        if b in LEGACY_PREFIX:
            pfx.append(b); rex = 0; i += 1            # REX の後ろに legacy prefix が来たら REX は無効 (opcode 直前のものだけ有効)
        elif 0x40 <= b <= 0x4F:
            rex = b; i += 1
        else:
            break
    enc, mp = 'legacy', 0
    rexw = bool(rex & 8)
    b = raw[i] if i < n else 0
    oc_off = i
    if b == 0xC5 and i + 2 < n:
        enc, mp, i = 'vex2', 1, i + 2
    elif b == 0xC4 and i + 3 < n:
        enc, mp, rexw, i = 'vex3', raw[i + 1] & 0x1F, bool(raw[i + 2] & 0x80), i + 3
    elif b == 0x62 and i + 4 < n:
        enc, mp, rexw, i = 'evex', raw[i + 1] & 0x07, bool(raw[i + 2] & 0x80), i + 4
    elif b == 0x8F and i + 2 < n and ((raw[i + 1] >> 3) & 7) != 0 and (raw[i + 1] & 0x1F) >= 8:
        enc, mp, rexw, i = 'xop', raw[i + 1] & 0x1F, bool(raw[i + 2] & 0x80), i + 3
    if enc != 'legacy':
        oc_off = i
        opcode = raw[i] if i < n else 0
        i += 1
    else:
        if i < n and raw[i] == 0x0F:
            i += 1
            mp = 1
            if i < n and raw[i] in (0x38, 0x3A):
                mp = 2 if raw[i] == 0x38 else 3
                i += 1
        oc_off = i
        opcode = raw[i] if i < n else 0
        i += 1
    moffs = enc == 'legacy' and mp == 0 and 0xA0 <= opcode <= 0xA3
    addr32 = 0x67 in pfx
    opsize16 = (0x66 in pfx) and not rexw
    mo = sib_off = None
    mod = reg = rm = None
    disp_off, disp_sz, rip = None, 0, False
    if moffs:
        disp_off, disp_sz = i, (4 if addr32 else 8)
        i += disp_sz
    else:
        hm = has_modrm(mp, opcode, enc) if has_modrm_ is None else has_modrm_
        if hm and i < n:
            mo = i
            modrm = raw[i]
            mod, reg, rm = modrm >> 6, (modrm >> 3) & 7, modrm & 7
            sl, disp_sz, rip = _modrm_tail(modrm, raw[i + 1] if i + 1 < n else 0)
            if sl:
                sib_off = i + 1
            if disp_sz:
                disp_off = i + 1 + sl
            i += 1 + sl + disp_sz
    return Layout(tuple(pfx), rex, enc, mp, opcode, oc_off, mo, mod, reg, rm, sib_off, disp_off, disp_sz, rip, moffs,
                  opsize16, rexw, addr32, i)


def opsize(lay):
    """実効オペランドサイズ (bytes): REX.W (VEX.W) → 8, 66 → 2, 既定 4。byte 幅 opcode (偶数 ALU 等) は呼出側が別判定。"""
    return 8 if lay.rexw else (2 if lay.opsize16 else 4)


def immz_size(lay):
    """Iz 型 imm のサイズ: 66 → 2、それ以外 4 (REX.W でも 4 で 64bit へ符号拡張)。"""
    return 2 if lay.opsize16 else 4


def addrsize(lay):
    return 4 if lay.addr32 else 8


def _lay(ins):
    raw = bytes(ins.bytes)
    return layout(raw, bool(ins.modrm_offset))


def disp_span(ins):
    """(offset, size) — 命令内 disp の位置と長さ (補正済み)。disp 無しは None。"""
    lay = _lay(ins)
    return (lay.disp_offset, lay.disp_size) if lay.disp_size else None


def disp_size(ins):
    s = disp_span(ins)
    return s[1] if s else 0


def disp_offset(ins):
    s = disp_span(ins)
    return s[0] if s else 0


def is_rip_relative(ins):
    return _lay(ins).rip


def rip_target(ins):
    """rip 相対 (mod=00 rm=101) なら実効 VA、そうでなければ None。disp は raw から再読込 (capstone mem.disp に依存しない)。"""
    lay = _lay(ins)
    if not lay.rip:
        return None
    d = struct.unpack_from('<i', bytes(ins.bytes), lay.disp_offset)[0]
    t = ins.address + ins.size + d
    return t & 0xFFFFFFFF if lay.addr32 else t & 0xFFFFFFFFFFFFFFFF


def zero_disp32(buf, insn_off, ins):
    """正規化ハッシュ用: buf[insn_off + disp_offset : +4] をゼロ化 (disp32 のみ)。実施したら True。
    旧 `if ins.disp_size == 4: nm[o+ins.disp_offset:o+ins.disp_offset+4] = 0` の置換え (66 prefix 付きでも効く)。"""
    s = disp_span(ins)
    if s and s[1] == 4:
        buf[insn_off + s[0]:insn_off + s[0] + 4] = b'\0\0\0\0'
        return True
    return False


def d9_affected(ins):
    """capstone の (disp_size, disp_offset) が真値と異なれば True。ins.disp_size==0 かつ真値も無しなら False。"""
    s = disp_span(ins)
    if s is None:
        return bool(ins.disp_size)
    return ins.disp_size != s[1] or ins.disp_offset != s[0]


def capstone_has_d9():
    """`66 0f 2f 05 <disp32>` (comisd xmm0,[rip+0x10]) の disp_size が 4 でなければ D9 健在。"""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    cs = Cs(CS_ARCH_X86, CS_MODE_64)
    cs.detail = True
    ins = next(cs.disasm(bytes.fromhex('660f2f0510000000'), 0x1000))
    return ins.disp_size != 4
