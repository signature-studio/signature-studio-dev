#!/usr/bin/env python3
"""141 プラグイン × SIMD kernel 表 (45 変数 / 80 実装) の妥当性検証 + per-plugin kernel 呼出インタフェース抽出 (CAB-196 P0c)。

kernel 表の正本: Fruity Balance block18983 framework 初期化 0x5e19f0 (inventory/kernel_table.py → lift/kernel_ranges_balance.txt)。
Delphi DLL 133 本それぞれについて:
  (a) 同一 VA 0x5e19f0 の init 関数が Balance と正規化ハッシュ一致するか → kernel 表の構成 (45 変数への代入) が同一
  (b) 80 kernel 実装関数の機械語が正規化ハッシュで Balance と一致するか (位置非依存; range 妥当性 = .pdata 境界)
  (c) kernel 変数 (45 VAs) を経由する間接呼出 site を抽出し、呼出直前の引数レジスタ (rcx/rdx/r8/r9/xmm0-3/stack) の
      設定源と呼出後の rax 使用 (戻り値利用) を記録 → kernel 呼出インタフェース
  (d) framework 非所属 (固有) 関数だけを走査 (fw_overlap.py と同一の正規化ハッシュで ≥13 DLL 共通 = framework と判定)
非 Delphi (MSVC engine 等) は framework 無し → N/A。
出力: p0c/work/kernel_matrix.json (全 raw), 集計は stdout。
usage: kernel_matrix.py [jobs=12] [maxdlls=N]
"""
import json, os, re, struct, sys, collections, hashlib, statistics
from multiprocessing import Pool
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_OP_REG, X86_OP_IMM, X86_REG_RIP

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
from paths import FL_WIN64_DIR  # noqa: E402
sys.path.insert(0, os.path.join(HERE, '..', '..', 'icall', 'disp_size'))
import dispfix as DF      # CAB-229: capstone の disp_size は 66 prefix 付き disp32 で 2 を返す (D9)
EXT = os.path.join(FL_WIN64_DIR, 'extracted')
BALANCE = 18983
INIT_VA = 0x5e19f0
KT = json.load(open(os.path.join(HERE, '..', 'work', 'kernel_table.json')))
VARS = {int(v, 16): [int(x, 16) for x in s] for v, s in KT['vars'].items()}          # var VA -> [impl VA]
KERNELS = {int(k['va'], 16): k for k in KT['kernels']}                                # impl VA -> info
MD = Cs(CS_ARCH_X86, CS_MODE_64)
MD.detail = True


def sections(pe):
    out = []
    for s in pe.sections:
        nm = s.Name.rstrip(b'\0').decode('latin1')
        out.append((nm, base + s.VirtualAddress, s.get_data()[:s.Misc_VirtualSize], s.Characteristics))
    return out


def sec_of(secs, va):
    for nm, a, d, ch in secs:
        if a <= va < a + len(d):
            return nm, d, va - a
    return None, b'', 0


def norm_hash(raw, start):
    """fw_overlap.py と同一の正規化: disp32 / (分岐・call 等) imm32 をゼロ化して md5。"""
    nm = bytearray(raw)
    for ins in MD.disasm(raw, start):
        o = ins.address - start
        DF.zero_disp32(nm, o, ins)
        if ins.imm_size == 4 and (ins.group(1) or ins.group(2) or ins.group(7) or ins.mnemonic in ('call', 'jmp')):
            nm[o + ins.imm_offset:o + ins.imm_offset + 4] = b'\0\0\0\0'
    return hashlib.md5(bytes(nm)).hexdigest()[:16]


def load(i):
    d = open('%s/block%05d_PE.bin' % (EXT, i), 'rb').read()
    return pefile.PE(data=d, fast_load=True), d


def pdata_funcs(pe):
    pd = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.pdata'][0].get_data()
    fs = {}
    for k in range(len(pd) // 12):
        b, e, u = struct.unpack_from('<III', pd, 12 * k)
        if b and not u & 1:
            fs[base + b] = base + e
    return fs


# ---- 正本 (Balance) のリファレンスハッシュ ----
pe0, _ = load(BALANCE)
base = pe0.OPTIONAL_HEADER.ImageBase
S0 = sections(pe0)
F0 = pdata_funcs(pe0)
_, t0, o0 = sec_of(S0, INIT_VA)
INIT_RAW = t0[o0:o0 + F0[INIT_VA] - INIT_VA]
INIT_HASH = norm_hash(INIT_RAW, INIT_VA)
KHASH = {}
for kv in KERNELS:
    _, t, o = sec_of(S0, kv)
    KHASH[kv] = norm_hash(t[o:F0[kv] - kv + o], kv)

ARG64 = ['rcx', 'rdx', 'r8', 'r9']


def srcdesc(ins, op):
    """オペランドの人間可読な設定源 (kind, detail)。"""
    if op.type == X86_OP_IMM:
        return {'kind': 'imm', 'val': op.imm}
    if op.type == X86_OP_REG:
        return {'kind': 'reg', 'val': ins.reg_name(op.reg)}
    if op.type == X86_OP_MEM:
        b = ins.reg_name(op.mem.base) if op.mem.base else ''
        ix = ins.reg_name(op.mem.index) if op.mem.index else ''
        if b == 'rip':
            return {'kind': 'mem_rip', 'target': hex(ins.address + ins.size + op.mem.disp)}
        d = op.mem.disp
        s = (b + ('+%s*%d' % (ix, op.mem.scale) if ix else '') + ('%+#x' % d if d else ''))
        return {'kind': 'lea' if ins.mnemonic == 'lea' else 'mem', 'val': s}
    return {'kind': 'other'}


def scan_dll(i):
    global base
    pe, d = load(i)
    if pe.FILE_HEADER.Machine != 0x8664:
        return i, {'delphi': False, 'reason': 'not x64'}
    base = pe.OPTIONAL_HEADER.ImageBase
    raw = d
    delphi = b'FP_DelphiPlug' in raw
    F = pdata_funcs(pe)
    secs = sections(pe)
    fn_starts = sorted(F)
    import bisect

    def find_fn(va):
        k = bisect.bisect_right(fn_starts, va) - 1
        if k < 0:
            return None
        s = fn_starts[k]
        return s if va < F[s] else None

    res = {'delphi': delphi, 'nfuncs': len(F)}
    if not delphi:
        return i, res
    # --- 全関数の正規化ハッシュ → init (Balance 0x5e19f0 と同一の関数) を探索 ---
    _, text, _ = sec_of(secs, fn_starts[0])
    for nm, a, dd, ch in secs:
        if nm == '.text':
            text = dd
            break
    tva = [a for nm, a, dd, ch in secs if nm == '.text'][0]

    def fbytes(fs):
        _, t, o = sec_of(secs, fs)
        return t[o:o + F[fs] - fs]

    init_va = None
    fh = {}
    for fs in fn_starts:
        h = norm_hash(fbytes(fs), fs)
        fh[fs] = h
        if init_va is None and h == INIT_HASH:
            init_va = fs
    if init_va is None:
        res['init_found'] = False
        return i, res
    res['init_found'] = True
    res['init_va'] = hex(init_va)
    # --- init の disasm から (var, impl) 代入対を復元 (kernel_table.py と同一のパターン) ---
    regv, assigns = {}, []
    for ins in MD.disasm(fbytes(init_va), init_va):
        ops = ins.operands
        if ins.mnemonic == 'lea' and len(ops) == 2 and ops[0].type == X86_OP_REG and ops[1].type == X86_OP_MEM and ops[1].mem.base == X86_REG_RIP:
            regv[ops[0].reg] = ins.address + ins.size + ops[1].mem.disp
        elif ins.mnemonic == 'mov' and len(ops) == 2 and ops[0].type == X86_OP_MEM and ops[0].mem.base == X86_REG_RIP and ops[1].type == X86_OP_REG and ops[1].reg in regv:
            assigns.append((ins.address + ins.size + ops[0].mem.disp, regv[ops[1].reg]))
    vars_ = collections.defaultdict(set)
    for v, t in assigns:
        vars_[v].add(t)
    dvars = {v: sorted(s) for v, s in vars_.items()}
    res['nvars'] = len(dvars)
    res['nimpls'] = len({t for _, t in assigns})
    # --- kernel 本体の正規化ハッシュが Balance の 80 本と一致するか ---
    bal_khash_set = set(KHASH.values())
    ok = bad = 0
    mism = []
    dker = {}
    for v, ts in dvars.items():
        for t in ts:
            dker[t] = v
    for t in sorted(dker):
        h = norm_hash(fbytes(t), t)
        if h in bal_khash_set:
            ok += 1
        else:
            bad += 1
            if len(mism) < 8:
                mism.append(hex(t))
    res['kernels_hash_ok'] = ok
    res['kernels_hash_bad'] = bad
    if mism:
        res['kernels_mismatch'] = mism
    # Balance kernel VA → hash → 本 DLL の対応 VA (diff test 用の per-DLL range)
    h2va = {}
    for fs, h in fh.items():
        h2va.setdefault(h, fs)
    kmap = {}
    for kv, h in KHASH.items():
        kmap[hex(kv)] = hex(h2va[h]) if h in h2va else None
    res['kernel_va_map'] = kmap
    # (c) kernel 呼出走査。3 経路:
    #   direct:  call rel32 → kernel VA 直接
    #   var:     call qword ptr [rip+var]
    #   varptr:  mov rax,[rip+slot] (slot の値 = var VA) → call [rax+off] / call rax
    #  候補関数だけを disasm し、呼出直前の引数レジスタ設定源と rax 使用を記録する。
    import numpy as np
    varset = set(dvars)
    # var-pointer slots (.data/.bss の中で値が var VA の 8 バイト位置)
    varptr = {}
    for nm, a, dd, ch in secs:
        if nm in ('.data', '.bss') and len(dd) >= 8:
            arr8 = np.frombuffer(dd[:((len(dd) - 7) // 8) * 8], dtype='<u8').astype(np.int64)
            hit = np.isin(arr8, np.array(sorted(varset), dtype=np.int64))
            for k in np.nonzero(hit)[0]:
                varptr[int(a + 8 * k)] = int(arr8[k])
    _, text, _ = sec_of(secs, fn_starts[0])
    for nm, a, dd, ch in secs:
        if nm == '.text':
            text = dd
            break
    tva = [a for nm, a, dd, ch in secs if nm == '.text'][0]
    n = len(text)
    refs = []
    if n > 8:
        sw = np.lib.stride_tricks.sliding_window_view(np.frombuffer(text, dtype=np.uint8), 4).copy()
        D = sw.view(np.int32).ravel().astype(np.int64)
        targets = tva + np.arange(len(D), dtype=np.int64) + 4 + D
        m1 = np.isin(targets, np.array(sorted(varset), dtype=np.int64))
        m2 = np.isin(targets, np.array(sorted(varptr), dtype=np.int64)) if varptr else np.zeros(len(D), bool)
        cand_pos = np.nonzero(m1 | m2)[0]
        # direct call rel32 (E8): target ∈ kernels
        e8 = np.nonzero(np.frombuffer(text, dtype=np.uint8) == 0xE8)[0]
        kt_arr = np.array(sorted(dker), dtype=np.int64)
        if len(e8):
            dt = tva + e8.astype(np.int64) + 5 + D[e8]
            e8k = e8[np.isin(dt, kt_arr)]
        else:
            e8k = []
        fset = {find_fn(tva + int(p) + 4) for p in cand_pos} - {None}
        fset |= {find_fn(tva + int(p) + 5) for p in e8k} - {None}
        fns_needed = sorted(fset)
    else:
        fns_needed = []
    callsites = []
    used_kernels = collections.Counter()
    for fs in fns_needed:
        fe = F[fs]
        _, t, o = sec_of(secs, fs)
        rawf = t[o:o + fe - fs]
        insns = list(MD.disasm(rawf, fs))
        last = {}       # reg -> (srcdesc, insn va, via)  via: ('var',VA) | ('varptr',slotVA) | None
        xmmw = {}       # xmm -> (srcdesc, va)
        stackw = {}     # [rsp+off] -> (srcdesc, va)  (call 直前の引数積み)
        for idx, ins in enumerate(insns):
            va = ins.address
            ops = ins.operands
            mn = ins.mnemonic
            # --- call 検出 (direct / call [rip+var] / call reg(var load) / call [reg±off](varptr load)) ---
            if mn == 'call' and ops:
                op = ops[0]
                kind = None
                var = None
                if op.type == X86_OP_IMM:
                    if op.imm in KERNELS:
                        kind, var = 'direct', op.imm
                elif op.type == X86_OP_MEM:
                    bb = ins.reg_name(op.mem.base) if op.mem.base else ''
                    if bb == 'rip':
                        tgt = ins.address + ins.size + op.mem.disp
                        if tgt in varset:
                            kind, var = 'call_mem', tgt
                    elif bb in last and last[bb][2]:
                        v = last[bb][2]
                        if v[0] == 'varptr':
                            cand = v[1] + op.mem.disp
                            if cand in varset:
                                kind, var = 'call_varptr', cand
                        elif v[0] == 'var' and op.mem.disp == 0:
                            kind, var = 'call_reg_deref', v[1]
                elif op.type == X86_OP_REG:
                    rn = ins.reg_name(op.reg)
                    if rn in last and last[rn][2] and last[rn][2][0] == 'var':
                        kind, var = 'call_reg', last[rn][2][1]
                if kind:
                    args = {}
                    for rn in ARG64:
                        if rn in last:
                            args[rn] = {'src': last[rn][0], 'at': hex(last[rn][1])}
                    for xn in ('xmm0', 'xmm1', 'xmm2', 'xmm3'):
                        if xn in xmmw:
                            args[xn] = {'src': xmmw[xn][0], 'at': hex(xmmw[xn][1])}
                    sa = {}
                    for off, (sd, sva) in stackw.items():
                        sa['%#x' % off] = {'src': sd, 'at': hex(sva)}
                    # 呼出直後の rax 使用
                    retused = False
                    if idx + 1 < len(insns):
                        nx = insns[idx + 1]
                        names = set()
                        for op2 in nx.operands:
                            if op2.type == X86_OP_REG:
                                names.add(nx.reg_name(op2.reg))
                            elif op2.type == X86_OP_MEM:
                                if nx.reg_name(op2.mem.base):
                                    names.add(nx.reg_name(op2.mem.base))
                                if nx.reg_name(op2.mem.index):
                                    names.add(nx.reg_name(op2.mem.index))
                        names.discard('')
                        if 'rax' in names and nx.mnemonic not in ('lea', 'movq', 'movd', 'xchg'):
                            retused = True
                    if kind == 'direct':
                        kern, kerns = var, [var]
                    else:
                        kerns = dvars[var]
                        kern = kerns[0]
                    callsites.append({'func': hex(fs), 'site': hex(va), 'var': None if kind == 'direct' else hex(var),
                                      'via': kind, 'kernel': hex(kern), 'kernels': [hex(k) for k in kerns],
                                      'args': args, 'stack': sa, 'ret_used': retused})
                    used_kernels[hex(kern)] += 1
                    last.clear(); xmmw.clear(); stackw.clear()  # 状態リセット (保守的)
                    continue
                # kernel 以外の call でも状態はクリア (引数は call 後に再設定される)
                last.clear(); xmmw.clear(); stackw.clear()
                continue
            # レジスタ追跡
            if mn.startswith('j') or mn in ('cmp', 'test', 'nop', 'ret', 'leave', 'int3', 'hlt'):
                continue
            if not ops:
                continue
            dst = ops[0]
            if dst.type == X86_OP_REG:
                rn = ins.reg_name(dst.reg)
                isxmm = rn.startswith('xmm')
                if not isxmm:
                    # 32/16/8bit 名を 64bit 正規名へ (r8d→r8, eax→rax, cl→rcx)
                    m8 = {'al': 'rax', 'cl': 'rcx', 'dl': 'rdx', 'bl': 'rbx', 'spl': 'rsp', 'bpl': 'rbp', 'sil': 'rsi', 'dil': 'rdi'}
                    if rn in m8:
                        rn = m8[rn]
                    elif rn.endswith('d') and rn[:-1] in ('r' + str(i) for i in range(8, 16)) or rn in ('eax', 'ecx', 'edx', 'ebx', 'esi', 'edi', 'ebp', 'esp'):
                        rn = rn[:-1] if rn.startswith('r') else 'r' + rn[1:]
                    elif rn.endswith('w') and rn.startswith('r'):
                        rn = rn[:-1]
                sd = srcdesc(ins, ops[1]) if len(ops) > 1 else {'kind': 'self', 'val': mn}
                via = None
                if len(ops) > 1 and ops[1].type == X86_OP_MEM and ins.reg_name(ops[1].mem.base) == 'rip':
                    tgt2 = ins.address + ins.size + ops[1].mem.disp
                    if tgt2 in varset:
                        via = ('var', tgt2)
                    elif tgt2 in varptr:
                        via = ('varptr', varptr[tgt2])
                if isxmm:
                    xmmw[rn] = (sd, va)
                else:
                    last[rn] = (sd, va, via)
            elif dst.type == X86_OP_MEM and dst.mem.base and ins.reg_name(dst.mem.base) == 'rsp':
                sd = srcdesc(ins, ops[1]) if len(ops) > 1 else {'kind': 'self'}
                stackw[dst.mem.disp] = (sd, va)
    res['callsites'] = callsites
    res['kernels_used'] = dict(used_kernels)
    res['ncallsites'] = len(callsites)
    return i, res


def dll_ids():
    B = json.load(open(os.path.join(HERE, '..', 'work', 'nsis_blockmap.json')))
    ids = sorted({r['idx'] for r in B if r['kind'] == 'PE' and re.match(r'^\$V31\\Plugins\\Fruity\\(Effects|Generators)\\', r['outdir'])})
    return ids


if __name__ == '__main__':
    jobs = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    ids = dll_ids()
    lim = int(sys.argv[2]) if len(sys.argv) > 2 else None
    if lim:
        ids = ids[:lim]
    with Pool(jobs) as p:
        R = dict(p.map(scan_dll, ids))
    os.makedirs(os.path.join(HERE, 'work'), exist_ok=True)
    json.dump({str(i): r for i, r in R.items()}, open(os.path.join(HERE, 'work', 'kernel_matrix.json'), 'w'), indent=1)
    # 集計
    delphi = [i for i, r in R.items() if r.get('delphi')]
    init_ok = [i for i in delphi if R[i].get('init_found')]
    print('DLLs scanned:', len(ids), 'delphi:', len(delphi))
    print('init(=Balance 0x5e19f0 関数) 発見:', len(init_ok), '/', len(delphi),
          ' 未発見:', sorted(set(delphi) - set(init_ok)))
    kok = collections.Counter()
    for i in init_ok:
        kok[(R[i].get('kernels_hash_ok', 0), R[i].get('nvars', 0), R[i].get('nimpls', 0))] += 1
    print('(kernel_hash_ok, vars, impls) 分布:', dict(sorted(kok.items())))
    tot = sum(R[i].get('ncallsites', 0) for i in init_ok)
    print('kernel 呼出 sites 合計:', tot)
    # per-DLL kernel VA → Balance kernel VA に正規化して集計
    kuse = collections.Counter()
    per_dll_used = {}
    for i in init_ok:
        kmap = R[i].get('kernel_va_map', {})   # balanceVA -> dllVA | None
        inv = {v: k for k, v in kmap.items() if v}
        used = {inv.get(dva, dva): c for dva, c in R[i].get('kernels_used', {}).items()}
        per_dll_used[i] = used
        for k, c in used.items():
            kuse[k] += c
    json.dump({str(i): u for i, u in per_dll_used.items()}, open(os.path.join(HERE, 'work', 'kernel_used_norm.json'), 'w'), indent=1)
    nun = sum(1 for kv in KERNELS if kuse.get(hex(kv), 0) == 0)
    print('kernel 実装別呼出数: top', kuse.most_common(6), ' 未使用(静的走査):', nun, '/ 80')
    for kv in sorted(KERNELS):
        if kuse.get(hex(kv), 0) == 0:
            print('  UNUSED', hex(kv))
    # プラグインごとの kernel 使用数
    nuse = sorted(((i, len(u)) for i, u in per_dll_used.items()), key=lambda x: -x[1])
    print('plugin 別使用 kernel 種類数: max', nuse[0] if nuse else None, '中央値', statistics.median([n for _, n in nuse]) if nuse else 0)
