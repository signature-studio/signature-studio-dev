#!/usr/bin/env python3
"""VST3 エントリ root の機械特定 (Massive X.vst3)。

方針 (裁定の根拠を機械化):
  1. RTTI (COL -> vftable) からクラスと全 vtable slot を取る。
  2. `process` slot は内容シグネチャで決める。Steinberg::Vst の
     IAudioProcessor::process(const ProcessData& data) は
       ProcessData { i32 processMode; i32 symbolicSampleSize; i32 numSamples; ... }
     であり、MSVC バイナリでは実装が先頭近くで
       [rcx+4] (symbolicSampleSize) と [rcx+8] (numSamples) を dword で比較/読む
     のがほぼ必須 (kSample32/kSample64 分岐、サンプル数ループ)。
     さらに引数は第 1 引数 = rcx (this) 、第 2 引数 = rdx (ProcessData*) なので
     `[rdx+4]` / `[rdx+8]` の dword 参照も同時に見る。
  3. スコア = (rdx+4 dword 参照) + (rdx+8 dword 参照) + サイズ位数。
     ネガティブコントロール: スコア 0 の slot を process 認定しない。

usage: mx_roots.py <pe> <rtti_vtables.json> <out.json>
"""
import sys, json, re, collections, struct
import pefile
import capstone
from capstone import CS_ARCH_X86, CS_MODE_64, CS_OP_MEM, CS_OP_IMM

PDSIG = ('symbolicSampleSize', 'numSamples')


def main(path, vtp, out):
    pe = pefile.PE(path, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(path, 'rb').read()
    secs = {s.Name.rstrip(b'\0').decode(): s for s in pe.sections}
    text = [s for s in pe.sections if s.Characteristics & 0x20000000][0]
    t_lo, t_hi = text.VirtualAddress, text.VirtualArea if False else text.VirtualAddress + text.Misc_VirtualSize
    t_raw = text.PointerToRawData

    def rd(rva, n):
        return data[t_raw + (rva - t_lo): t_raw + (rva - t_lo) + n]

    # .pdata
    pd = secs['.pdata']
    pdb = data[pd.PointerToRawData: pd.PointerToRawData + pd.Misc_VirtualSize]
    fsz = {}
    for i in range(0, len(pdb) - 11, 12):
        b, e, _u = struct.unpack_from('<III', pdb, i)
        if e > b and b:
            fsz[b] = e - b

    vt = json.load(open(vtp))
    md = capstone.Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True

    def sig(rva, cap=0x4000):
        """slot 関数の内容シグネチャ。"""
        sz = fsz.get(rva)
        if sz is None or sz > cap:
            sz = min(sz or cap, cap)
        buf = rd(rva, sz)
        if not buf:
            return None
        n = 0
        plus4 = plus8 = plus0 = 0
        calls = set()
        strs = 0
        end = rva + (sz or 0)
        try:
            for ins in md.disasm(buf, base + rva):
                n += 1
                if ins.id == capstone.x86.X86_INS_CALL:
                    for op in ins.operands:
                        if op.type == CS_OP_IMM:
                            t = op.imm - base
                            if t_lo <= t < t_hi:
                                calls.add(t)
                for op in ins.operands:
                    if op.type != CS_OP_MEM or op.mem.base != capstone.x86.X86_REG_RDX:
                        continue
                    if op.mem.index == 0 and op.size == 4:
                        d = op.mem.disp
                        if d == 4:
                            plus4 += 1
                        elif d == 8:
                            plus8 += 1
                        elif d == 0:
                            plus0 += 1
        except capstone.CsError:
            pass
        return dict(size=sz or 0, n=n, plus4=plus4, plus8=plus8, plus0=plus0,
                    ncalls=len(calls), end=end)

    ONLY = sys.argv[4] if len(sys.argv) > 4 else None

    res = {}
    for name, lst in vt.items():
        m = re.match(r'^\.\?(AV|AU)(.+?)@@(.*)$', name)
        if not m:
            continue
        cls = [p for p in m.group(2).split('@') if p]
        short = cls[-1] if cls else m.group(2)
        if ONLY and ONLY not in short:
            continue
        ent = []
        for v in lst:
            slots = []
            for s in v['slots']:
                rva = int(s, 16) - base
                sg = sig(rva)
                if sg is None:
                    continue
                sg['addr'] = s
                sg['score'] = sg['plus4'] * 3 + sg['plus8'] * 3
                slots.append(sg)
            if slots:
                ent.append({'vtable': v['vtable'], 'off': v['off'], 'nslots': len(slots), 'slots': slots})
        if ent:
            res[name] = {'short': short, 'vtables': ent}

    # VST3 オブジェクト family: Steinberg::Vst インターフェース実装 or MassiveX* クラス
    fam = {}
    for name, e in res.items():
        short = e['short']
        if short in ('SingleComponentEffect', 'ComponentBase', 'EditControllerEx1', 'EditController',
                     'IPluginBase', 'FObject', 'FUnknown', 'IDependent', 'Unit', 'ProgramList',
                     'Parameter', 'AudioBus', 'Bus', 'BusList', 'EventBus'):
            fam.setdefault('steinberg', []).append((name, e))
        if short.startswith('MassiveX') or short.startswith('MX'):
            fam.setdefault('mx', []).append((name, e))
    json.dump({'base': hex(base), 'classes': res, 'family': {k: [n for n, _ in v] for k, v in fam.items()}},
              open(out, 'w'))
    # レポート: MassiveXAudioClass の slot スコア上位
    for key in ('MassiveXAudioClass', 'MassiveXPlugIn'):
        for name, e in res.items():
            if e['short'] != key:
                continue
            for v in e['vtables']:
                top = sorted(v['slots'], key=lambda s: -s['score'])[:6]
                print('%s %s off=%d nslots=%d' % (key, v['vtable'], v['off'], v['nslots']))
                for s in top:
                    print('   slot %-16s sz=%-7d n=%-6d plus4=%-3d plus8=%-3d plus0=%-3d score=%d'
                          % (s['addr'], s['size'], s['n'], s['plus4'], s['plus8'], s['plus0'], s['score']))
    print('classes', len(res), 'family steinberg', len(fam.get('steinberg', [])),
          'mx', len(fam.get('mx', [])), file=sys.stderr)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3])
