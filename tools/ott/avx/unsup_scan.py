#!/usr/bin/env python3
"""unsup_scan.py — CAB-135: lift 集合に含まれる未対応命令 (ott_unsup になる箇所) を
関数単位・coverage 単位・命令形式 (VEX2/VEX3/EVEX, xmm/ymm) 別に分類する。

usage: unsup_scan.py ENTRIES.json COV_DSP.json COV_ENTRY.json COV_CRT.json OUT.json

既存 lift (lift/x64c.py) を同一条件 (--closure 3, crt_roots.py の override) で再実行し、
各 unsup 箇所の (関数 VA, 命令 VA, mnemonic, operands) を記録する。coverage は
native 単歩実行の insn RVA集合 / calltgt RVA集合で判定:
  - insn_exec : 命令そのものが native 実行 coverage に含まれる (_flags=0 の現行経路で到達)
  - fn_exec   : 含まれる関数が native 実行 coverage の calltgt に含まれる (分岐未実行)
分類は ①fn_exec (entry/DSP 実行で到達する関数) ②0x1801bc890 (FP 制御切替) ③その他用。
"""
import sys, os, json, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'lift'))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
import x64c  # noqa: E402
from paths import PLUGINS_DIR  # noqa: E402

IMG = 0x180000000
DLL = os.path.join(PLUGINS_DIR, 'ott', 'binaries', 'OTT_vst2_win64.dll')
CLOSURE = 3
FPCTRL_FN = '1801bc890'   # CAB-138 §8: FP 制御切替 (vldmxcsr/vstmxcsr/rcr を含む大きい関数)


def main():
    entries_path, dsp_path, entry_path, crt_path, out = sys.argv[1:6]
    pe = x64c.PEInfo(DLL)
    md = x64c.Cs(x64c.CS_ARCH_X86, x64c.CS_MODE_64); md.detail = True
    cfg = json.load(open(entries_path))
    entries = set(IMG + r for r in cfg.get('calltgt', [])) | set(cfg.get('roots', []))
    thunks = {}

    def thunk_name(va):
        code = pe.bytes_at(va, 8)
        for i in md.disasm(code, va, 1):
            if i.mnemonic == 'jmp' and i.operands[0].type == x64c.X86_OP_MEM and i.operands[0].mem.base == x64c.X86_REG_RIP:
                slot = va + i.size + i.operands[0].mem.disp
                return pe.iat.get(slot)
        return None
    for e in list(entries):
        nm = thunk_name(e)
        if nm:
            thunks[e] = nm; entries.discard(e)
    known = set(entries)
    queue = sorted(entries)
    done = {}
    sys.path.insert(0, os.path.join(HERE, '..', 'crtinit'))
    import crt_roots  # noqa: E402
    overrides = crt_roots.overrides()
    depth = 0
    while True:
        newc = set()
        for e in queue:
            if e in done: continue
            f = x64c.FnLift(pe, e, known, md, thunks)
            done[e] = f
            if e not in overrides:
                f.lift()   # main() と同一: override 関数は lift しない (calls も空扱い)
            for t in f.calls:
                if t not in known and t not in thunks:
                    nm = thunk_name(t)
                    if nm: thunks[t] = nm
                    else: newc.add(t)
        if depth >= CLOSURE or not newc: break
        depth += 1
        known |= newc
        queue = sorted(newc)
    final = {}
    for e in sorted(done):
        f = x64c.FnLift(pe, e, known, md, thunks)
        final[e] = f
        if e not in overrides:
            f.lift()

    # coverage 読み込み (RVA)
    cov = {}
    for tag, path in (('dsp', dsp_path), ('entry', entry_path), ('crt', crt_path)):
        d = json.load(open(path))
        cov[tag] = {'insn': set(d.get('insn', [])), 'fn': set(d.get('calltgt', []))}

    PREFIXES = {0x66, 0xf2, 0xf3, 0x2e, 0x3e, 0x26, 0x36, 0x64, 0x65, 0x67, 0xf0}

    def enc_of(b0):
        if b0 == 0xc4: return 'VEX3'
        if b0 == 0xc5: return 'VEX2'
        if b0 == 0x62: return 'EVEX'
        return 'legacy'

    def enc_before(va):
        # 命令直前の prefix を読み飛ばして最初の opcode byte を得る (軽量推定)
        o = va - IMG
        while o > 0 and pe.img[o] in PREFIXES:
            o -= 1
        return enc_of(pe.img[o])

    sites = []
    for e, f in sorted(final.items()):
        if e in overrides:
            continue    # override 関数は C 実装に置換される (lift_meta も数えない)
        for va, ins in sorted(f.insns.items()):
            m = x64c.strip_prefix(ins.mnemonic)
            try:
                f.one(ins)
            except x64c.Unsup as ex:
                regs = []
                for op in ins.operands:
                    if op.type == x64c.X86_OP_REG:
                        regs.append(ins.reg_name(op.reg))
                ymm = any(r.startswith('ymm') for r in regs) or 'ymm' in str(ex)
                sites.append({
                    'fn': '%x' % e, 'va': '%x' % va, 'm': m, 'ops': ins.op_str,
                    'err': str(ex), 'enc': enc_before(va), 'wide': 'ymm' if ymm else 'xmm',
                    'insn_exec': {t: (va - IMG in cov[t]['insn']) for t in cov},
                    'fn_exec': {t: (e - IMG in cov[t]['fn']) for t in cov},
                })
    # 関数の実行実績 (calltgt 和集合)
    fnexec = {}
    for e in final:
        fnexec['%x' % e] = {t: (e - IMG in cov[t]['fn']) for t in cov}

    # 集計
    by_kind = collections.Counter()
    by_prio = collections.Counter()
    for s in sites:
        prio = '2_fpctrl' if s['fn'] == FPCTRL_FN else ('1_fnexec' if any(s['fn_exec'].values()) else '3_other')
        s['prio'] = prio
        by_kind[s['m']] += 1
        by_prio[prio] += 1
        by_prio[prio + '_' + s['wide']] += 1
        by_prio[prio + '_' + s['enc']] += 1
    fns = sorted({s['fn'] for s in sites})
    outd = {
        'n_sites': len(sites), 'n_kinds': len(by_kind), 'by_kind': dict(by_kind.most_common()),
        'by_prio': dict(by_prio), 'n_fns': len(fns),
        'lifted': sorted('%x' % e for e in final),
        'fns': [{'fn': fn,
                 'prio': [s['prio'] for s in sites if s['fn'] == fn][0],
                 'fn_exec': fnexec.get(fn),
                 'n_sites': sum(1 for s in sites if s['fn'] == fn),
                 'kinds': sorted({s['m'] for s in sites if s['fn'] == fn})} for fn in fns],
        'sites': sites,
    }
    json.dump(outd, open(out, 'w'), indent=1)
    print('[unsup_scan] sites %d / kinds %d / fns %d' % (len(sites), len(by_kind), len(fns)))
    for k, v in by_prio.most_common():
        print('  %-20s %d' % (k, v))


if __name__ == '__main__':
    main()
