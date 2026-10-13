#!/usr/bin/env python3
"""extract_constants.py — FLEngine_x64.dll から ILRegKey 解読に必要な定数を実抽出し data/constants.json へ出力する。

実バイナリを直接読む (推定の混入を防ぐ)。出力は決定的。
対象: FLEngine_x64.dll 26.1 (win64, ImageBase 0x400000)
"""
import json
import os
import struct
import sys

import pefile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..', 'shared'))
from paths import REPO_ROOT, FL_WIN64_DIR  # noqa: E402

DLL_REL = 'tools/startup/work/FLEngine_x64.dll'
_DLL_DEFAULT = os.path.join(REPO_ROOT, *DLL_REL.split('/'))
if not os.path.exists(_DLL_DEFAULT):
    _DLL_DEFAULT = os.path.join(FL_WIN64_DIR, 'extracted', 'block00031_PE.bin')
DLL = sys.argv[1] if len(sys.argv) > 1 else _DLL_DEFAULT
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), '..', 'data', 'constants.json')

pe = pefile.PE(DLL, fast_load=True)
BASE = pe.OPTIONAL_HEADER.ImageBase


def utf16z(va, n=96):
    d = pe.get_data(va - BASE, n)
    out = []
    for i in range(0, n - 1, 2):
        w = d[i] | d[i + 1] << 8
        if w == 0:
            break
        out.append(chr(w))
    return ''.join(out)


def dword(va):
    return struct.unpack('<I', pe.get_data(va - BASE, 4))[0]


def qword(va):
    return struct.unpack('<Q', pe.get_data(va - BASE, 8))[0]


def istr_table(va):
    """IL 難読化文字列定数レコード: [magic 0x000204b0][cp -1][len][wchars][null] の len/chars を読む。
    va は chars 先頭 (len は va-4)。"""
    ln = dword(va - 4)
    raw = pe.get_data(va - BASE, min(ln * 2 + 2, 256))
    chars = [struct.unpack_from('<H', raw, i * 2)[0] for i in range(ln)]
    return {'len': ln, 'chars': chars, 'text': ''.join(chr(c) for c in chars)}


def apply_delta(rec, delta):
    # delta は call site の即値下位 16bit を int16 として解釈 (FUN_008cfdc0 の short param_4)
    d = delta if delta < 0x8000 else delta - 0x10000
    return ''.join(chr((ord(c) + d) & 0xFFFF) for c in rec['text'])


K = {}
k_addr = None
# SHA-256 K テーブル探索 (0x428a2f98, 0x71374491 連続)
raw_all = pe.__data__
needle = struct.pack('<II', 0x428a2f98, 0x71374491)
i = raw_all.find(needle)
if i != -1:
    for s in pe.sections:
        if s.PointerToRawData and s.PointerToRawData <= i < s.PointerToRawData + s.SizeOfRawData:
            k_addr = BASE + s.VirtualAddress + (i - s.PointerToRawData)
    ks = struct.unpack('<64I', pe.get_data(k_addr - BASE, 256))
    K = {'va': k_addr, 'first': [hex(x) for x in ks[:4]], 'last': hex(ks[63]), 'ok': ks[0] == 0x428a2f98 and ks[63] == 0xc67178f2}

table = []
for i in range(8):
    v = dword(0x15B7F00 + i * 4)
    table.append(v)

consts = {
    'dll': {'path': DLL_REL, 'image_base': BASE, 'size': os.path.getsize(DLL)},
    'flag_byte': {
        'va': '0x14f84a8', 'ptr_slot': '0x15e0698',
        'static_init': pe.get_data(0x14F84A8 - BASE, 1)[0],
        'init_value_src': '0x10d08d8 (=0x00)',
    },
    'separators': {
        'colon': {'va': '0x10d0b2c', **istr_table(0x10D0B2C)},
        'pipe': {'va': '0x10d0b3c', **istr_table(0x10D0B3C)},
        'sep1_encoded': {'va': '0x10d0b4c', **istr_table(0x10D0B4C), 'delta': -0x10, 'decoded': apply_delta(istr_table(0x10D0B4C), 0xFFF0)},
        'sep2_encoded': {'va': '0x10d0b68', **istr_table(0x10D0B68), 'delta': 0xFFDF, 'decoded': apply_delta(istr_table(0x10D0B68), 0xFFDF)},
        'marker_encoded': {'va': '0x10d0b80', **istr_table(0x10D0B80), 'delta': 0xFFEC, 'decoded': apply_delta(istr_table(0x10D0B80), 0xFFEC)},
        'marker_result': {'va': '0x10d0b98', **istr_table(0x10D0B98)},
        'rec_a': {'va': '0x10d0ba8', **istr_table(0x10D0BA8)},
        'fmt_s_s': {'va': '0x10d0bbc', **istr_table(0x10D0BBC)},
        'generic_colon': {'va': '0x8e6db8', 'text': utf16z(0x8E6DB8, 8)},
        'generic_pipe': {'va': '0x8e6dc8', 'text': utf16z(0x8E6DC8, 8)},
    },
    'id_prefix': {
        'encoded': {'va': '0x10d0bd8', 'text': utf16z(0x10D0BD8, 12)},
        'delta': -0x32,
        'decoded': ''.join(chr((ord(c) - 0x32) & 0xFFFF) for c in utf16z(0x10D0BD8, 12)),
    },
    'feature_table': {'va': '0x15b7f00', 'dwords': table,
                      'tiers': [
                          {'grade_char': 'A', 'first': table[0], 'second': table[3]},
                          {'grade_char': 'B', 'first': table[1], 'second': table[4]},
                          {'grade_char': 'C', 'first': table[2], 'second': table[5]},
                      ]},
    'grade_mask': {'va': '0x10d0be0', 'value': dword(0x10D0BE0), 'bits': [b for b in range(8) if (dword(0x10D0BE0) >> b) & 1]},
    'strings': {
        'please_remember': {'va': '0x10d0c18', 'text': utf16z(0x10D0C18, 64)},
        'product': {'va': '0x10d0a70', 'text': utf16z(0x10D0A70, 64)},
        'machine_guid_key': {'text': 'SOFTWARE\\Microsoft\\Cryptography', 'value': 'MachineGuid'},
        'hsd': {'key': 'Software\\Image-Line\\Shared\\General', 'value': 'HSD', 'va_value_name': '0x10c7cc4'},
    },
    'sha256': {
        'init_func': '0xbf89b0', 'compress_func': '0xbf86f0',
        'h_init': ['0x6a09e667', '0xbb67ae85', '0x3c6ef372', '0xa54ff53a', '0x510e527f', '0x9b05688c', '0x1f83d9ab', '0x5be0cd19'],
        'k_table': K,
    },
    'vm_program': {'va': '0x14111e0', 'size': 0x2AF},
    'globals': {
        'user_name': '0x15e43f8', 'webpass': '0x15e4bd0', 'fls_info': '0x15e3b00',
        'license_plate': '0x15e19f8', 'machine_string': '0x15e1358',
        'decoded': '0x15e49a8', 'reg_name_display': '0x15dfdf8',
        'button_id': '0x15e0488', 'grade_char_obj': '0x15e4790(+0xd0)',
        'days_remaining': '0x15e14a8', 'fire_mode': '0x15e3d80',
        'dup_flag': '0x15e1b10', 'fire_dates': ['0x15e1948', '0x15e4cb8'],
        'today_cache': '0x15e1608', 'grade_cache': '0x15e0ab0',
    },
    'key_funcs': {
        'parser': '0x10c7cd0', 'parser_size': 32177,
        'machine_hash_helper': '0x10d3a30', 'days_remaining': '0x10c7850',
        'reg_info_display': '0x10c7530', 'observe_registration': '0x8e6150',
        'box_string': '0x8cfd20', 'delta_box': '0x8cfdc0', 'char_encode_rec': '0x8cf800',
        'hex_unpack_and_cipher': '0x8d0580', 'cipher_vm_run': '0x8d0380',
        'date_from_8chars': '0x8e6660', 'date_encode': '0x442770',
        'decode_cached': '0x8e7080', 'split_first_group': '0x8e6770',
        'charsum5': '0x8e5f80', 'normalize_rec': '0x8e6e30',
    },
}

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, 'w') as f:
    json.dump(consts, f, ensure_ascii=False, indent=1)
print('wrote', OUT)
