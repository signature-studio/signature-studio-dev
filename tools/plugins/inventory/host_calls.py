#!/usr/bin/env python3
"""プラグイン→ホスト呼び出し面の実測 (win Delphi プラグイン 133 DLL)。

TFruityPlug インスタンスは `[this+0xbc]` に Host (TFruityPlugHost*) を持つ (ctor 逆アセンブルで確認)。
簡易 taint で
   Host = [reg+0xbc] → vt = [Host] → call [vt+disp]
を追跡し、vtable offset (disp) の使用頻度と、Dispatcher (disp==0) の ID (r8 に積まれた即値) を収集する。
framework 共通関数 (ハッシュが 13 DLL 以上) と plugin 固有関数を分けて集計。
出力: work/host_calls.json
"""
import os, sys, json, re, collections, struct
from multiprocessing import Pool
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_OP_REG, X86_OP_IMM

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, '..', 'work')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared'))
from paths import FL_WIN64_DIR  # noqa: E402
EXT = os.path.join(FL_WIN64_DIR, 'extracted')
HOSTOFF = 0xbc


def get_funcs(pe):
    pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0]
    data = pd.get_data()[:pd.Misc_VirtualSize]
    out = set()
    for i in range(len(data) // 12):
        b, e, u = struct.unpack_from('<III', data, 12 * i)
        if b and not (u & 1):
            out.add((b, e))
    return sorted(out)


def scan(fn):
    d = open(os.path.join(EXT, fn), 'rb').read()
    pe = pefile.PE(data=d, fast_load=True)
    text = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
    tb = text.get_data()
    tv = text.VirtualAddress
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    fidx = {}
    res = []  # (func_rva, disp, id)
    for (b, e) in get_funcs(pe):
        host = set()
        vt = set()
        lastimm = {}
        for ins in md.disasm(tb[b - tv: e - tv], b):
            mn = ins.mnemonic
            ops = ins.operands
            if mn == 'call' and ops and ops[0].type == X86_OP_MEM and ops[0].mem.base != 0:
                base = ins.reg_name(ops[0].mem.base)
                if base in vt and ops[0].mem.index == 0:
                    disp = ops[0].mem.disp
                    ident = lastimm.get('r8') if disp == 0 else None
                    res.append((b, disp, ident))
                # call clobbers volatile
                for r in ('rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'):
                    host.discard(r)
                    vt.discard(r)
                    lastimm.pop(r, None)
                lastimm.pop('r8', None)
                continue
            if mn == 'call':
                for r in ('rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'):
                    host.discard(r)
                    vt.discard(r)
                lastimm.pop('r8', None)
                continue
            if len(ops) == 2 and ops[0].type == X86_OP_REG:
                dst = ins.reg_name(ops[0].reg)
                if mn == 'mov' and ops[1].type == X86_OP_MEM and ops[1].mem.base != 0 and ops[1].mem.index == 0:
                    sb = ins.reg_name(ops[1].mem.base)
                    if ops[1].mem.disp == HOSTOFF and ops[0].size == 8:
                        host.add(dst); vt.discard(dst)
                        continue
                    if ops[1].mem.disp == 0 and sb in host:
                        vt.add(dst); host.discard(dst)
                        continue
                    host.discard(dst); vt.discard(dst)
                elif mn == 'mov' and ops[1].type == X86_OP_REG:
                    sr = ins.reg_name(ops[1].reg)
                    (host.add if sr in host else host.discard)(dst)
                    (vt.add if sr in vt else vt.discard)(dst)
                    if sr in lastimm:
                        lastimm[dst] = lastimm[sr]
                    else:
                        lastimm.pop(dst, None)
                else:
                    host.discard(dst); vt.discard(dst)
                    # r8/r8d immediate tracking
                    d32 = {'r8d': 'r8', 'r8': 'r8', 'r8w': 'r8', 'r8b': 'r8'}.get(dst)
                    if d32 and mn == 'mov' and ops[1].type == X86_OP_IMM:
                        lastimm['r8'] = ops[1].imm
                    elif d32 and mn == 'xor':
                        lastimm['r8'] = 0
                    elif d32:
                        lastimm.pop('r8', None)
                # 32bit alias handling for r8d writes
                if dst in ('r8d',) and mn == 'mov' and ops[1].type == X86_OP_IMM:
                    lastimm['r8'] = ops[1].imm
                if mn == 'mov' and dst in ('r8d',) and ops[1].type != X86_OP_IMM:
                    lastimm.pop('r8', None)
    return fn, res


def main():
    S = {r['file']: r for r in json.load(open(os.path.join(WORK, 'win_pe_scan.json')))}
    U = json.load(open(os.path.join(WORK, 'win_unique.json')))
    files = sorted(f for f, r in S.items() if 'FP_DelphiPlug' in r['hints'] and 'CreatePlugInstance' in r['exports']
                   and os.path.exists(os.path.join(WORK, 'winfuncs', f[:-7] + '.json')))
    raw = os.path.join(WORK, 'host_calls_raw.json')
    if '--reuse' in sys.argv and os.path.exists(raw):
        out = {k: [tuple(x) for x in v] for k, v in json.load(open(raw)).items()}
    else:
        with Pool(14) as p:
            out = dict(p.map(scan, files))
        json.dump(out, open(raw, 'w'))
    # classify framework vs unique using winfuncs hash counts
    FD = os.path.join(WORK, 'winfuncs')
    cnt = collections.Counter()
    fh = {}
    for f in files:
        k = f[:-7]
        j = json.load(open(os.path.join(FD, k + '.json')))
        fh[f] = {x[0]: x[2] for x in j['funcs']}
        for h in set(fh[f].values()):
            cnt[h] += 1
    agg_fw = collections.Counter()
    agg_fw_id = collections.Counter()
    per = {}
    uniq_slots = collections.defaultdict(collections.Counter)
    uniq_ids = collections.defaultdict(collections.Counter)
    fwsites = collections.Counter()
    for f, res in out.items():
        k = f[:-7]
        for (rva, disp, ident) in res:
            h = fh[f].get(rva)
            is_fw = h is not None and cnt[h] >= 13
            if is_fw:
                fwsites[(rva_h := h, disp, ident)] += 0
            if is_fw:
                pass
        per[k] = {'sites': len(res)}
    # framework: 1 DLL 分 (Balance) の framework 関数だけ
    ref = 'block18983_PE.bin'
    for (rva, disp, ident) in out[ref]:
        h = fh[ref].get(rva)
        if h is not None and cnt[h] >= 13:
            agg_fw[disp] += 1
            if disp == 0:
                agg_fw_id[ident] += 1
    for f, res in out.items():
        k = f[:-7]
        for (rva, disp, ident) in res:
            h = fh[f].get(rva)
            if h is None or cnt[h] < 13:
                uniq_slots[k][disp] += 1
                if disp == 0:
                    uniq_ids[k][ident] += 1
    allid = collections.Counter()
    allslot = collections.Counter()
    for k in uniq_slots:
        allslot.update(uniq_slots[k])
        allid.update(uniq_ids[k])
    js = {'framework_slots(Balance)': {hex(k): v for k, v in sorted(agg_fw.items())},
          'framework_ids(Balance)': {str(k): v for k, v in sorted(agg_fw_id.items(), key=lambda kv: (kv[0] is None, kv[0]))},
          'unique_slots_total': {hex(k): v for k, v in sorted(allslot.items())},
          'unique_ids_total': {str(k): v for k, v in sorted(allid.items(), key=lambda kv: (kv[0] is None, kv[0]))},
          'unique_ids_per_plugin': {k: {str(i): c for i, c in v.items()} for k, v in uniq_ids.items()},
          'unique_slots_per_plugin': {k: {hex(i): c for i, c in v.items()} for k, v in uniq_slots.items()}}
    json.dump(js, open(os.path.join(WORK, 'host_calls.json'), 'w'), indent=0)
    print('framework host vtable offsets (Balance):', js['framework_slots(Balance)'])
    print('framework Dispatcher IDs (Balance):', js['framework_ids(Balance)'])
    print('plugin-unique host vtable offsets (sum over 133):', js['unique_slots_total'])
    print('plugin-unique Dispatcher IDs (sum over 133):', js['unique_ids_total'])


if __name__ == '__main__':
    main()
