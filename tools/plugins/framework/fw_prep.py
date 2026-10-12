#!/usr/bin/env python3
"""fw_prep.py — P0a (CAB-194) framework lift の前処理.

  1. Fruity Balance (block18983) の .pdata 関数一覧 → icall_rewrite 用 F.ranges
     (framework = 位置非依存ハッシュが ≥13 DLL 共有の関数集合; 残り = Balance 固有 glue。
      smoke test は DLL 初期化 (entry_point→_StartLib→_InitLib→InitUnits) を走らせるため
      glue (DllMain 等も含む) も含めて全関数を lift 対象にする。framework 集合の統計は別途出力)
  2. M11 教訓の適用確認用 landmark: FLEngine_x64.dll (block00031) の既知 RTL 関数
     (m11 REPORT §3 の手転記対象: InitUnits/_InitLib/_StartLib/_UStrAsg/RestoreContext/FastMM)
     を位置非依存ハッシュで Balance 側 VA に対応づける (Delphi 36 RTL 共通のため一致するはず)。
  3. Balance 版 InitUnits を逆アセンブルし, InitContext.InitTable を読む rip 相対 global の VA を
     抽出する (smoke test の checkpoint 計測: units_total / units_init を実行後にメモリから読む)。

  出力: work/fw/F.ranges, work/fw/fw_stats.json, work/fw/landmarks.json
  使い方: python3 fw_prep.py
"""
import json, os, re, struct, hashlib, collections
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.join(HERE, '..', 'work', 'fw')
import sys as _sys
_sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared'))
from paths import FL_WIN64_DIR
EXT = os.path.join(FL_WIN64_DIR, 'extracted')
BAL = os.path.join(EXT, 'block18983_PE.bin')          # Fruity Balance_x64.dll (framework 正本)
FLE = os.path.join(EXT, 'block00031_PE.bin')          # FLEngine_x64.dll (M11 の教訓来源)

# FLEngine RTL の既知 VA (tools/m11/REPORT.md §1/§3, m11_ov.c 転記対象)
FLE_LANDMARKS = {
    'InitUnits': 0x4120c0,
    '_InitLib': 0x412160,
    '_StartLib': 0x41d8f0,
    'UStrAsg': 0x4133f0,
    'RestoreContext_longjmp': 0x412770,
    'ApplyRelocs': 0x412510,
    'FastMM_GetMem': 0x407a50,
    'FastMM_mmgr': 0x412d60,
    'WStrClr_sysfreestring': 0x455790,   # m11 shimx_link §3 の _WStrClr 系は個別なので参考値
}


def funcs_of(path):
    d = open(path, 'rb').read()
    pe = pefile.PE(data=d, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    pdata = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0].get_data()
    fs = sorted({(b, e) for b, e, u in (struct.unpack_from('<III', pdata, 12 * k) for k in range(len(pdata) // 12)) if b and not u & 1})
    code = {s.VirtualAddress: s.get_data()[:s.Misc_VirtualSize] for s in pe.sections if s.Characteristics & 0x20000000}
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    out = {}
    for b, e in fs:
        raw = next((c[b - va:e - va] for va, c in code.items() if va <= b < va + len(c)), b'')
        if len(raw) != e - b or not raw:
            continue
        # 正規化は tools/plugins/inventory/win_funcs.py と同一規約:
        #   関数外への call/jmp rel32 と全 rip 相対 disp32 をゼロ化 (位置非依存化)
        from capstone.x86 import X86_OP_MEM, X86_REG_RIP
        nm = bytearray(raw)
        for ins in md.disasm(raw, b):
            o = ins.address - b
            if ins.mnemonic in ('call', 'jmp') and ins.imm_size == 4:
                tgt = ins.operands[0].imm if ins.operands else 0
                if not (b <= tgt < e):
                    nm[o + ins.imm_offset:o + ins.imm_offset + 4] = b'\0\0\0\0'
                continue
            if ins.mnemonic.startswith('j') and ins.imm_size == 4:
                tgt = ins.operands[0].imm if ins.operands else 0
                if not (b <= tgt < e):
                    nm[o + ins.imm_offset:o + ins.imm_offset + 4] = b'\0\0\0\0'
                continue
            if ins.disp_size == 4:
                for op in ins.operands:
                    if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                        nm[o + ins.disp_offset:o + ins.disp_offset + 4] = b'\0\0\0\0'
                        break
        out[base + b] = {'end': base + e, 'size': e - b,
                         'hash': hashlib.sha1(bytes(nm)).hexdigest()[:12], 'raw': raw}
    return pe, base, out


def main():
    os.makedirs(W, exist_ok=True)
    hc = json.load(open(os.path.join(HERE, '..', 'work', 'fw_hash_counts.json')))

    peB, baseB, fB = funcs_of(BAL)
    peF, baseF, fF = funcs_of(FLE)
    print('[prep] Balance: %d funcs / %d bytes;  FLEngine: %d funcs'
          % (len(fB), sum(f['size'] for f in fB.values()), len(fF)))

    # framework subset (>=13 DLL 共有ハッシュ)
    fw = {va: f for va, f in fB.items() if hc.get(f['hash'], 0) >= 13}
    fw_bytes = sum(f['size'] for f in fw.values())
    print('[prep] framework(>=13): %d funcs / %d bytes (%.2f MB); non-fw (Balance glue): %d funcs / %d bytes'
          % (len(fw), fw_bytes, fw_bytes / 1e6, len(fB) - len(fw), sum(f['size'] for f in fB.values()) - fw_bytes))

    # F.ranges = 全 Balance 関数 (framework + glue)
    ranges = ['0x%x-0x%x' % (va, fB[va]['end'] - 1) for va in sorted(fB)]
    open(os.path.join(W, 'F.ranges'), 'w').write(','.join(ranges) + '\n')

    # landmark: FLEngine 既知 RTL 関数のハッシュ → Balance VA
    h2b = collections.defaultdict(list)
    for va, f in fB.items():
        h2b[f['hash']].append(va)
    landmarks = {}
    for name, va in FLE_LANDMARKS.items():
        f = fF.get(va)
        if not f:
            continue
        cands = h2b.get(f['hash'], [])
        landmarks[name] = {'fle_va': hex(va), 'balance_va': [hex(x) for x in cands],
                           'size': f['size'], 'matched': len(cands) == 1}

    # Balance 版 InitUnits の rip 相対 global (InitContext.InitTable) 抽出
    initunits = landmarks.get('InitUnits', {})
    iu_va = int(initunits['balance_va'][0], 16) if initunits.get('matched') else None
    init_tbl_gv = None
    if iu_va:
        md = Cs(CS_ARCH_X86, CS_MODE_64)
        md.detail = True
        from capstone.x86 import X86_OP_MEM, X86_REG_RIP
        f = fB[iu_va]
        for ins in md.disasm(f['raw'], iu_va):
            for op in ins.operands:
                if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP and ins.mnemonic in ('mov', 'movsxd'):
                    init_tbl_gv = ins.address + ins.size + op.mem.disp
                    break
            if init_tbl_gv:
                break
    if init_tbl_gv:
        landmarks['InitUnits']['init_table_gv'] = hex(init_tbl_gv)

    stats = {
        'balance': {'pe': BAL, 'image_base': hex(baseB), 'sizeof_image': hex(peB.OPTIONAL_HEADER.SizeOfImage),
                    'entry_va': hex(baseB + peB.OPTIONAL_HEADER.AddressOfEntryPoint),
                    'funcs': len(fB), 'bytes': sum(f['size'] for f in fB.values()),
                    'fw_funcs_ge13': len(fw), 'fw_bytes_ge13': fw_bytes,
                    'glue_funcs': len(fB) - len(fw), 'glue_bytes': sum(f['size'] for f in fB.values()) - fw_bytes},
        'landmarks': landmarks,
    }
    json.dump(stats, open(os.path.join(W, 'fw_stats.json'), 'w'), indent=1, ensure_ascii=False)
    for k, v in stats['landmarks'].items():
        print('[prep] landmark %-24s balance=%s (matched=%s)' % (k, v['balance_va'], v['matched']))


if __name__ == '__main__':
    main()
