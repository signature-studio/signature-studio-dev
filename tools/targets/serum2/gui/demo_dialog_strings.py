#!/usr/bin/env python3
"""SR-57 #3626: DSP setState (0x18004fad0) の 2 つの show_msg_helper 呼出 (0x18004fc9c / 0x18004fdaf) の引数文字列を復号する。

文字列はスタック (rbp 相対) に 16 byte ずつ movups で置かれ、一部を mov で上書きし、
loop で XOR して作られる (lea では読めない)。本スクリプトは、その命令列の即値と rip 相対参照を
capstone で読み、同じ規則で復号する。規則は次の 2 通り:
  site A (0x18004fc9c): msg[i] = enc[i] ^ ((acc_i ^ edx_i) & 0xff) ^ 0xcc, acc_i = 0xfa*i, edx_i = (i&7)+0x2e, len 70
                       title[i] = enc[i] ^ (i+0x40), len 18
  site B (0x18004fdaf): msg[i] = enc[i] ^ ((acc_i ^ edx_i) & 0xff) ^ 0xc7, acc_i = 0x5c*i, edx_i = (i&7)+0x86, len 53
                       title[i] = enc[i] ^ ((i-0x55) & 0xff), len 31
usage: demo_dialog_strings.py <pe>
"""
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

pe = pefile.PE(sys.argv[1], fast_load=True)
raw = open(sys.argv[1], 'rb').read()
IMG = pe.OPTIONAL_HEADER.ImageBase


def off(va):
    rva = va - IMG
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.PointerToRawData + rva - s.VirtualAddress
    raise SystemExit(f'{va:#x} not in image')


md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True
LO, HI = 0x18004fbb0, 0x18004fe00
code = raw[off(LO):off(LO) + (HI - LO)]
insns = {i.address: i for i in md.disasm(code, LO)}


def rip_bytes(addr, n=16):
    i = insns[addr]
    disp = i.operands[1].mem.disp
    return raw[off(i.address + i.size + disp):][:n]


def qword_imm(addr):
    return int(insns[addr].op_str.split(',')[1].strip(), 16).to_bytes(8, 'little')


def decode(stores, length, edx_base, acc_mul, xorc):
    enc = bytearray(80)
    for base, data in stores:
        enc[base:base + len(data)] = data
    return bytes(((((acc_mul * i) & 0xff) ^ ((i & 7) + edx_base) ^ enc[i] ^ xorc) & 0xff) for i in range(length))


def title(stores, length, key_fn):
    enc = bytearray(40)
    for base, data in stores:
        enc[base:base + len(data)] = data
    return bytes(enc[i] ^ key_fn(i) for i in range(length))


# site A: 0x18004fc9c (msg は rbp-0x10 から 70 byte、title は rbp-0x30 から 18 byte)
A_msg_stores = [
    (0, rip_bytes(0x18004fc04)),
    (16, rip_bytes(0x18004fbf9)),
    (32, rip_bytes(0x18004fbee)),
    (48, rip_bytes(0x18004fbe3)),
    (63, qword_imm(0x18004fc0f)),
]
A_title_enc = bytearray(rip_bytes(0x18004fc62)[:15]) + bytearray(b'\x26\x3f\x3f')
A_title_stores = [(0, bytes(A_title_enc))]
# site B: 0x18004fdaf (msg は rbp-0x10 から 53 byte、title は rbp-0x30 から 31 byte)
B_msg_stores = [
    (0, rip_bytes(0x18004fd14)),
    (16, rip_bytes(0x18004fd09)),
    (32, rip_bytes(0x18004fcfe)),
    (46, qword_imm(0x18004fd1f)),
]
B_title_stores = [
    (0, rip_bytes(0x18004fd7e)),
    (16, rip_bytes(0x18004fd73)),
]

A_msg = decode(A_msg_stores, 70, 0x2e, 0xfa, 0xcc)
B_msg = decode(B_msg_stores, 53, 0x86, 0x5c, 0xc7)
A_title = title(A_title_stores, 18, lambda i: (i + 0x40) & 0xff)
B_title = title(B_title_stores, 31, lambda i: (i - 0x55) & 0xff)

for name, t, m in (('A 0x18004fc9c', A_title, A_msg), ('B 0x18004fdaf', B_title, B_msg)):
    print(f'{name}: title={t.decode("latin-1")!r}')
    print(f'{name}: msg={m.decode("latin-1")!r}')
