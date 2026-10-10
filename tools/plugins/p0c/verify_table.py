#!/usr/bin/env python3
"""kernel 表 (45 変数 / 80 実装) の全 DLL 再検証 (CAB-196 P0c)。

背景: p0c/kernel_matrix.py の正規化 (norm_hash) は capstone 5.0.7 が 66-prefix SSE 命令の
RIP 相対 (mod=00/rm=101) で disp_size=2 を誤報告するため disp32 をゼロ化できず、
DLL ごとに 1 kernel (0x5e03f0 系: movupd xmm7,[rip+...] を持つ) が誤って hash mismatch 扱いになる
(129/130 DLL が 79/80)。本スクリプトは disp32 を確実にゼロ化する修正版正規化で再検証する。

方法: 各 DLL について kernel_matrix.json の kernel_va_map 値 (73 VA) + kernels_mismatch (1 VA) の
計 74 実装 VA を修正版正規化でハッシュ化し、Balance 80 kernel のハッシュ集合との包含を確認する。
79/80 は旧正規化でも一致済み (弱い正規化での一致は強い正規化でも一致), 残り 1 を本検証で回収する。
出力: work/table_verify.json + stdout 集計
usage: verify_table.py [kernel_matrix.json]
"""
import json, os, struct, sys, hashlib, collections
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_REG_RIP

HERE = os.path.dirname(os.path.abspath(__file__))
EXT = '/home/ubuntu/work/analysis/win64/extracted'
BALANCE = 18983
MD = Cs(CS_ARCH_X86, CS_MODE_64)
MD.detail = True

base = 0


def load_pe(i):
    global base
    pe = pefile.PE(data=open('%s/block%05d_PE.bin' % (EXT, i), 'rb').read(), fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    return pe


def pdata_funcs(pe):
    pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0].get_data()
    F = {}
    for k in range(len(pd) // 12):
        b, e, u = struct.unpack_from('<III', pd, 12 * k)
        if b and not u & 1:
            F[base + b] = base + e
    return F


def fbytes(pe, F, va):
    for s in pe.sections:
        a = base + s.VirtualAddress
        if a <= va:
            d = s.get_data()
            o = va - a
            return d[o:F[va] - a]
    return b''


def norm_hash_fixed(raw, start):
    """修正版正規化: RIP 相対 (mod=00, rm=101) の disp32 と分岐/call の imm32 をゼロ化。
    capstone の disp_size 誤報告 (66-prefix で 2 を返す) に依存せず、
    「disp32 は命令末尾の imm 直前 4 バイト」というエンコーディング事実から位置を求める。"""
    nm = bytearray(raw)
    for ins in MD.disasm(raw, start):
        if not ins.operands:
            continue
        riprel = False
        for op in ins.operands:
            if op.type == X86_OP_MEM and (op.mem.base == 0 or op.mem.base == X86_REG_RIP) and op.mem.index == 0:
                # capstone 5: RIP 相対は base==X86_REG_RIP (または正規化で base==0) で disp に target 相対が入る
                riprel = True
        if not riprel:
            # 分岐/call の imm32 ゼロ化 (旧実装と同一の条件)
            if ins.imm_size == 4 and (ins.group(1) or ins.group(2) or ins.group(7) or ins.mnemonic in ('call', 'jmp')):
                o = ins.address - start
                nm[o + ins.imm_offset:o + ins.imm_offset + 4] = b'\0\0\0\0'
            continue
        o = ins.address - start
        end = o + len(ins.bytes)
        if ins.imm_size:
            end -= ins.imm_size
        if end - 4 >= o:
            nm[end - 4:end] = b'\0\0\0\0'       # disp32 (RIP 相対は常に disp32)
        if ins.imm_size == 4 and (ins.group(1) or ins.group(2) or ins.group(7) or ins.mnemonic in ('call', 'jmp')):
            nm[o + ins.imm_offset:o + ins.imm_offset + 4] = b'\0\0\0\0'
    return hashlib.md5(bytes(nm)).hexdigest()[:16]


def main():
    mpath = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'work', 'kernel_matrix.json')
    M = json.load(open(mpath))
    pe0 = load_pe(BALANCE)
    F0 = pdata_funcs(pe0)
    # Balance 80 kernel の修正版ハッシュ
    kt = json.load(open(os.path.join(HERE, '..', 'work', 'kernel_table.json')))
    bal = {}
    for k in kt['kernels']:
        va = int(k['va'], 16)
        bal[va] = norm_hash_fixed(fbytes(pe0, F0, va), va)
    balset = set(bal.values())
    print('Balance kernels: %d, distinct fixed-hash: %d' % (len(bal), len(balset)))

    dlls = [k for k in M if M[k].get('delphi') and M[k].get('init_found')]
    full = 0
    missing = {}
    detail = {}
    for b in dlls:
        pe = load_pe(int(b))
        F = pdata_funcs(pe)
        v = M[b]
        vas = [int(t, 16) for t in v['kernel_va_map'].values() if t]
        vas += [int(t, 16) for t in v.get('kernels_mismatch', [])]
        hs = {norm_hash_fixed(fbytes(pe, F, va), va) for va in vas}
        miss = sorted(hex(kv) for kv, h in bal.items() if h not in hs)
        detail[b] = {'n_impl_va': len(vas), 'n_distinct_hash': len(hs), 'balance_kernels_missing': miss}
        if not miss:
            full += 1
        else:
            missing[b] = miss
    print('DLL 検証: %d / %d で 80/80 kernel hash 一致 (修正版正規化)' % (full, len(dlls)))
    if missing:
        for b, m in sorted(missing.items()):
            print('  block %s missing: %s' % (b, m))
    json.dump({'balance_distinct': len(balset), 'dlls_full': full, 'dlls_total': len(dlls), 'detail': detail},
              open(os.path.join(HERE, 'work', 'table_verify.json'), 'w'), indent=1)

    # 未使用 kernel (静的走査)。kernel_used_norm.json の key は混在:
    #   - kernel_va_map で正規化済みの Balance VA (旧正規化で一致した 79 kernel 分)
    #   - 正規化出来なかった DLL ローカル VA (0x5e03f0 系 variant 分)
    # どちらも「ハッシュが Balance kernel 集合に含まれるか」で属性付けする
    # (DLL ローカル VA は当該 DLL の PE で、Balance VA は Balance PE で判定)。
    try:
        used = json.load(open(os.path.join(HERE, 'work', 'kernel_used_norm.json')))
        h2kvs = {}
        for kv, h in bal.items():
            h2kvs.setdefault(h, []).append(kv)
        used_kvs = set()
        used_sites = 0
        unknown = collections.Counter()
        F0c = F0  # Balance
        for dll, ku in used.items():
            pe = load_pe(int(dll))
            F = pdata_funcs(pe)
            for dva, c in ku.items():
                used_sites += c
                va = int(dva, 16)
                hit = None
                if va in F:   # DLL ローカル VA として判定
                    h = norm_hash_fixed(fbytes(pe, F, va), va)
                    if h in h2kvs:
                        hit = h2kvs[h]
                if hit is None and va in F0c:   # Balance VA として判定
                    h = norm_hash_fixed(fbytes(pe0, F0c, va), va)
                    if h in h2kvs:
                        hit = h2kvs[h]
                if hit:
                    used_kvs.update(hit)
                else:
                    unknown[dva] += c
        ngroup = len({bal[kv] for kv in used_kvs})
        unused = sorted(hex(kv) for kv in bal if bal[kv] not in {bal[k] for k in used_kvs})
        print('呼出 site 検出済み kernel: %d 実装 / %d distinct-group / 80 (未使用 %d 実装, site 総数 %d)' %
              (len(used_kvs), ngroup, 80 - len(used_kvs), used_sites))
        if unused:
            print('  未使用:', unused)
        if unknown:
            print('  kernel 表外への呼出/未帰属: %d site, 例: %s' % (sum(unknown.values()), unknown.most_common(3)))
    except FileNotFoundError:
        print('work/kernel_used_norm.json 無し (kernel_matrix.py 実行後に再実行で未使用集計)')


if __name__ == '__main__':
    main()
