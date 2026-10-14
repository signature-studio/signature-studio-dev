#!/usr/bin/env python3
"""REX export を実際に呼ぶ importer の静的特定 (T-SH-45 / #2734 受入 2)。

REX の export は importer の IAT に載らず、REX 本体を除く 32 件すべてが GetProcAddress で動的に解決する (REPORT §8.2)。
文字列の存在では判定せず、次のデータフローで呼出先を確定する:
  (1) .text の `lea reg,[rip+d]` が REX 名の文字列 VA を指す (参照箇所。disp32 から逆算して検出)
  (2) その直後 LOOK 命令以内に GetProcAddress の呼出 (`call`/`jmp [rip+IAT]`)。直接 call 先 (ヘルパ) は
      HELPER_DEPTH 段まで辿り、その中の IAT 呼出 (thunk の `jmp` を含む) を GetProcAddress とみなす
  (3) 直後 4 命令以内の `mov [rip+S],rax` で戻り値を data slot S に保存していれば、S を名前に束縛する
  (4) S を読む箇所のうち `call [rip+S]`、または `mov reg,[rip+S]` の後 6 命令以内の `call reg` を呼出とみなす
判定: (4) の呼出数 >= 1 を「その export を呼ぶ」とする。(2) の GetProcAddress 呼出で (3) の格納先が無いものは
「格納先未確定」(unbound) として数え、(4) で読むだけで呼出を確認できないものは loads_only として数える。
usage: python3 importers.py <fl-win64 展開先 (extracted/ を含む親)> [--json OUT]
"""
import sys, os, json, glob, subprocess, argparse, struct
import pefile
import capstone
from capstone import CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_OP_IMM, X86_OP_REG, X86_REG_RIP

REX_NAMES = ['REXCreate', 'REXDelete', 'REXGetCreatorInfo', 'REXGetInfo', 'REXGetInfoFromBuffer',
             'REXGetSliceInfo', 'REXRenderPreviewBatch', 'REXRenderSlice', 'REXSetOutputSampleRate',
             'REXSetPreviewTempo', 'REXStartPreview', 'REXStopPreview']
LOOK = 12
HELPER_LOOK = 60
HELPER_DEPTH = 2


def rva_of_offset(pe, off):
    for s in pe.sections:
        if s.PointerToRawData <= off < s.PointerToRawData + s.SizeOfRawData:
            return s.VirtualAddress + (off - s.PointerToRawData)
    return None


def string_vas(pe, data, base):
    out = {}
    for n in REX_NAMES:
        pat = b'\x00' + n.encode() + b'\x00'
        i = data.find(pat)
        while i >= 0:
            rva = rva_of_offset(pe, i + 1)
            if rva is not None:
                out.setdefault(base + rva, n)
            i = data.find(pat, i + 1)
    return out


def rip_target(ins, op):
    return ins.address + ins.size + op.mem.disp


def rip_hits(raw, va, targets):
    """raw 内で disp32 の終端 (p+4) が targets の VA を指す箇所 (RIP 相対参照) を返す。"""
    out = []
    for p in range(1, len(raw) - 4):
        rel = struct.unpack_from('<i', raw, p)[0]
        t = va + p + 4 + rel
        if t in targets:
            out.append((va + p, t, raw[p - 2] if p >= 2 else None, raw[p - 1]))
    return out


def is_gpa_call(ins, gpa_slots):
    return ins.mnemonic in ('call', 'jmp') and bool(ins.operands) and ins.operands[0].type == X86_OP_MEM \
        and ins.operands[0].mem.base == X86_REG_RIP and rip_target(ins, ins.operands[0]) in gpa_slots


def overwrites_rax(ins):
    """rax (GetProcAddress の戻り値) を上書きしうる命令: call/jmp/ret、または rax 系レジスタへの書込み (cmp/test を除く)。"""
    if ins.mnemonic in ('call', 'jmp', 'ret'):
        return True
    return ins.mnemonic not in ('cmp', 'test') and bool(ins.operands) and ins.operands[0].type == X86_OP_REG \
        and ins.reg_name(ins.operands[0].reg) in ('rax', 'eax', 'ax', 'al')


def helper_calls_gpa(md, secs, va, gpa_slots, depth=HELPER_DEPTH, _cache={}):
    """直接 call 先 (ヘルパ) の先頭 HELPER_LOOK 命令に GetProcAddress の IAT 呼出があるか。
    直接 call を depth 段まで辿る (ヘルパ → ヘルパ → GetProcAddress)。"""
    key = (id(gpa_slots), va, depth)
    if key in _cache:
        return _cache[key]
    ok = False
    for sva, raw in secs:
        if sva <= va < sva + len(raw):
            body = list(md.disasm(raw[va - sva:va - sva + 0x400], va))[:HELPER_LOOK]
            if any(is_gpa_call(i, gpa_slots) for i in body):
                ok = True
            elif depth > 0:
                ok = any(i.mnemonic == 'call' and i.operands and i.operands[0].type == X86_OP_IMM
                         and helper_calls_gpa(md, secs, i.operands[0].imm, gpa_slots, depth - 1) for i in body)
            break
    _cache[key] = ok
    return ok


def analyze(path):
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
    base = pe.OPTIONAL_HEADER.ImageBase
    raw_file = open(path, 'rb').read()
    strs = string_vas(pe, raw_file, base)
    slots = {}
    for d in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
        for s in d.imports:
            if s.name:
                slots[s.address] = s.name.decode()
    gpa_slots = {k for k, v in slots.items() if v == 'GetProcAddress'}
    res = {'file': os.path.basename(path), 'strings': sorted(set(strs.values())), 'gpa_slots': len(gpa_slots),
           'name_refs': 0, 'gpa_calls_named': 0, 'bound': {}, 'unbound_sites': 0, 'calls': {}, 'loads_only': 0,
           'loads_only_names': {}, 'unbound_names': {}}
    if not strs or not gpa_slots:
        res['note'] = 'string or GetProcAddress missing'
        return res
    md = capstone.Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    secs = [(base + s.VirtualAddress, s.get_data()) for s in pe.sections if s.Characteristics & 0x20000000]
    lea_sites = []
    for sva, raw in secs:
        for at, t, op, modrm in rip_hits(raw, sva, set(strs)):
            if op == 0x8d and (modrm & 0xC7) == 0x05:
                lea_sites.append((at, strs[t], raw, sva))
    res['name_refs'] = len(lea_sites)
    stores = {}
    for at, name, raw, sva in lea_sites:
        off = at - sva
        # lea [rip+d] は即値を持たないので、命令の終端は disp32 の直後 (at + 4)
        nxt = list(md.disasm(raw[off + 4:off + 4 + 0x80], at + 4))
        gpa = None
        for j, i2 in enumerate(nxt[:LOOK]):
            if is_gpa_call(i2, gpa_slots):
                gpa = j
                break
            if i2.mnemonic == 'call' and i2.operands and i2.operands[0].type == X86_OP_IMM \
                    and helper_calls_gpa(md, secs, i2.operands[0].imm, gpa_slots):
                gpa = j
                break
        if gpa is None:
            continue
        res['gpa_calls_named'] += 1
        slot = None
        for i2 in nxt[gpa + 1:gpa + 5]:
            if i2.mnemonic == 'mov' and len(i2.operands) == 2 and i2.operands[0].type == X86_OP_MEM \
                    and i2.operands[0].mem.base == X86_REG_RIP and i2.operands[1].type == X86_OP_REG \
                    and i2.reg_name(i2.operands[1].reg) == 'rax':
                slot = rip_target(i2, i2.operands[0])
                break
            if overwrites_rax(i2):
                break
        if slot is None:
            res['unbound_sites'] += 1
            res['unbound_names'][name] = res['unbound_names'].get(name, 0) + 1
            continue
        stores.setdefault(slot, set()).add(name)
    res['bound'] = {n: sorted(hex(k) for k, v in stores.items() if n in v) for n in sorted({n for v in stores.values() for n in v})}
    for sva, raw in secs:
        for at, t, op, modrm in rip_hits(raw, sva, set(stores)):
            names = stores[t]
            if op == 0xff and modrm == 0x15:
                for n in names:
                    res['calls'][n] = res['calls'].get(n, 0) + 1
            elif op == 0x8b and (modrm & 0xC7) == 0x05:
                off = at - sva
                nx = list(md.disasm(raw[off + 4:off + 4 + 0x40], at + 4))[:6]
                if any(i.mnemonic == 'call' and i.operands and i.operands[0].type == X86_OP_REG for i in nx):
                    for n in names:
                        res['calls'][n] = res['calls'].get(n, 0) + 1
                else:
                    res['loads_only'] += 1
                    for n in names:
                        res['loads_only_names'][n] = res['loads_only_names'].get(n, 0) + 1
    return res


def scan(root):
    files = subprocess.run(['grep', '-rl', '-a', 'REXCreate', os.path.join(root, 'extracted')],
                           capture_output=True, text=True).stdout.split()
    return sorted(f for f in files if os.path.isfile(f))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root', help='fl-win64 の展開先 (extracted/ を含む)')
    ap.add_argument('--json', default=None)
    a = ap.parse_args()
    out = []
    for f in scan(a.root):
        try:
            r = analyze(f)
        except Exception as ex:
            r = {'file': os.path.basename(f), 'error': str(ex)}
        out.append(r)
        print('%-22s name_refs=%-3s gpa_sites=%-3s bound=%-3s calls=%s unbound=%s loads_only=%s' % (
            r['file'], r.get('name_refs', '-'), r.get('gpa_calls_named', '-'), len(r.get('bound', {})),
            r.get('calls', '-'), r.get('unbound_sites', '-'), r.get('loads_only', '-')))
    called = [r for r in out if r.get('calls')]
    print('[importers] files=%d  calls-resolved=%d  REX names called=%s' % (
        len(out), len(called), sorted({n for r in out for n in r.get('calls', {})})))
    if a.json:
        json.dump(out, open(a.json, 'w'), indent=1)


if __name__ == '__main__':
    main()
