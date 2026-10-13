#!/usr/bin/env python3
"""gen_boot.py — FLE-2 (x64c M11 boot chain) の boot 生成物を作る。

入力:
  PE                 FLEngine_x64.dll (既定 = analysis/win64/extracted/block00031_PE.bin)
  lift_meta.json     fle_lift.sh の lift 成果物 (iat_map)
  tools/shimx/src/shimx.h    shimx プロトタイプ (thunk 署名のソース)
  tools/shimx/exports.txt    shimx 定義名
  tools/flelift/rt/fle_cpu.c imp_* 定義名 (リンク時 -Dimp_X=impc_X 改名に使う)

出力 (work/boot/ 配下):
  fle_entries_boot.json   x64c --entries 用。roots = コミット済み fle_entries.json + boot 追加分
                          (entry_point 0x1376820, longjmp 落とし先断片 0x1376840)
  fle_textwin.c           .text 内「データとして読まれる」領域の敷設:
                          - PackageInfoHeader / InitTable (0x13768b0..+0x18)
                          - units 配列 942*16B (0x13768e0..)
                          - 各 unit proc 先頭 8B (InitUnits の [proc]!=0 check が読む)
  fle_imp_bridge.c        imp_<Name> (strong) の上書き層:
                          - shimx 実装あり → shimx C 関数を MS x64 レジスタ/スタックから呼ぶ thunk
                          - shimx 無し → 0 返却 soft スタブ (呼出計数つき)
                          - curated (fle_boot.c 側で定義する名前) は生成しない
  fle_link_defs.txt       emcc へ渡す -Dimp_X=impc_X 行 (fle_cpu.c の強定義との重複排除)

usage: gen_boot.py [--pe PE] [--meta lift_meta.json] [--out work/boot] [--nosx] [--strict]
  --nosx    shimx を使わない (fle_cpu 由来のみ + soft) — shimx 寄与の対照実験用
  --strict  soft スタブを「計数のみで 0 返却」から「fail-fast に変更するフラグを出す」だけ
            (実挙動は fle_boot.c の g_soft_failfast で切るので生成物は同一。link 構成の証跡用)
"""
import argparse, json, os, re, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'shared'))
from paths import FL_WIN64_DIR

PE_DEF = f'{FL_WIN64_DIR}/extracted/block00031_PE.bin'
FLE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))          # tools/flelift
REPO = os.path.dirname(FLE)                                                # tools/..
IMG = 0x400000

ENTRY_VA = 0x1376820       # PE AddressOfEntryPoint (DllMain, Delphi SysInit)
LONGJMP_TARGET = 0x1376840 # entry_point 内 setjmp 復帰アドレス (f_4126f0 longjmp の jmp [rcx] 先)
PKGINFO_VA = 0x13768b0     # _StartLib の rdx (= InitContext.InitTable の値)

# fle_boot.c が strong 定義する名前 (生成を skip)。
#   ExitProcess/TerminateProcess = halt 例外化 / GetProcAddress = 0 返却 (lift VA でない host fn ptr が
#   間接 call で dispatch 不解決になるため m11 旧 stub 揃え) / LoadStringW = buf[0]=0 (gui_compat.c 同一挙動) /
#   memset = CRT 実体 / MessageBox* = 自動 IDOK / VirtualAlloc = shimx 委譲 + 計数
CURATED = {'ExitProcess', 'TerminateProcess', 'GetProcAddress', 'LoadStringW', 'memset',
           'MessageBoxA', 'MessageBoxW', 'VirtualAlloc', 'RaiseException',
           # FLE-2: コールバック引数を取る列挙 API。shimx の cbtrans トランポリンは wasm
           # 関数 index をそのまま call_indirect しようとして "table index is out of bounds"
           # に trap する (m11 REPORT #3 と同一)。lift 側で直接 fle_icall9 に落とす。
           'EnumCalendarInfoW', 'EnumSystemLocalesW'}

# ---------------- shimx.h パーサ ----------------

SCALAR_W = {  # 型名 → bit幅 (wasm32 emcc の C 型として)
    'void': 0, 'int': 32, 'unsigned': 32, 'unsigned int': 32, 'long': 32, 'unsigned long': 32,
    'char': 8, 'unsigned char': 8, 'short': 16, 'unsigned short': 16, 'float': 32, 'double': 64,
    'int8_t': 8, 'uint8_t': 8, 'int16_t': 16, 'uint16_t': 16, 'int32_t': 32, 'uint32_t': 32,
    'int64_t': 64, 'uint64_t': 64, 'size_t': 32, 'ptrdiff_t': 32, 'intptr_t': 32, 'uintptr_t': 32,
    'BOOL': 32, 'BOOLEAN': 8, 'BYTE': 8, 'WORD': 16, 'DWORD': 32, 'UINT': 32, 'ULONG': 32, 'LONG': 32,
    'LONGLONG': 64, 'ULONGLONG': 64, 'DWORD64': 64, 'HRESULT': 32, 'WCHAR': 16, 'CHAR': 8,
    'ATOM': 16, 'LANGID': 16, 'LCID': 32, 'LCTYPE': 32, 'REGSAM': 32, 'LSTATUS': 32, 'COLORREF': 32,
    'SIZE_T': 32, 'ULONG_PTR': 32, 'DWORD_PTR': 32, 'LPARAM_T': 32, 'LRESULT_T': 32, 'UINT_PTR_T': 32,
    'USHORT_T': 16, 'MMRESULT': 32, 'HRESULT': 32, 'errno_t': 32,
}

def parse_shimx_h(path):
    """shimx.h から (name -> {ret, params:[(type,name)]}) と typedef 名集合を取り出す。"""
    txt = open(path, encoding='utf-8', errors='replace').read()
    txt = re.sub(r'/\*.*?\*/', ' ', txt, flags=re.S)
    txt = re.sub(r'//[^\n]*', ' ', txt)
    txt = re.sub(r'#(?:ifdef|ifndef|if|else|elif|endif|define|include|undef)[^\n]*', ' ', txt)
    stmts = []
    depth = 0; cur = ''
    for ch in txt:
        if ch == '{' or ch == '}':
            cur = ''    # 定義本体は捨てる (宣言のみ欲しい)
            continue
        if ch == ';':
            if cur.strip(): stmts.append(cur.strip())
            cur = ''
            continue
        cur += ch
    ptr_names, struct_sizes = set(), {}
    protos = {}
    for st in stmts:
        st = ' '.join(st.split())
        m = re.match(r'^typedef\s+.*\(\s*\*\s*(?P<fp>[A-Za-z_]\w*)\s*\)', st)
        if m:
            ptr_names.add(m.group('fp'))
            m2 = re.search(r'(?P<names>[A-Za-z_]\w*(?:\s*,\s*\**\s*[A-Za-z_]\w*)*)\s*$', st)
            if m2:
                for nm in [re.sub(r'[\s*]', '', x) for x in m2.group('names').split(',')]:
                    if nm: ptr_names.add(nm)
            continue
        m = re.match(r'^typedef\s+(?:struct\s+_?\w+\s*)?\{?(?P<body>[^{}]*)\}?\s*(?P<names>[A-Za-z_]\w*(?:\s*,\s*\**\s*[A-Za-z_]\w*)*)\s*$', st)
        if m and not re.match(r'^typedef\s+.*\(', st):
            # `typedef <base>* NAME;` / `typedef <base>* A, *B;` — ポインタ typedef。
            # 元の正規表現は body 側に識別子の末尾を食われる (`typedef WCHAR* BSTR` → body='WCHAR* BST')
            # ため ptr_names に入らず、戻り値型 kind_of() が None になって soft stub (常に 0 返却) に
            # なり、guest の BSTR/SysAllocStringLen などが nil を返して raise 0xEEDFADE していた (FLE-2)。
            pm = re.match(r'^typedef\s+(?P<base>.+?)\s*\*\s*(?P<names>[A-Za-z_]\w*(?:\s*,\s*\**\s*[A-Za-z_]\w*)*)\s*$', st)
            if pm:
                for nm2 in [re.sub(r'[\s*]', '', x) for x in pm.group('names').split(',')]:
                    if nm2: ptr_names.add(nm2)
                # `, *PLARGE_INTEGER` のような後続ポインタ名も拾う
                for extra in re.findall(r',\s*\*\s*([A-Za-z_]\w*)', st):
                    ptr_names.add(extra)
                continue
            base = m.group('body').strip()
            for nm in [re.sub(r'[\s*]', '', x) for x in m.group('names').split(',')]:
                if not nm: continue
                if '*' in base or nm.startswith(('LP', 'PC', 'NP', 'P')) or 'HANDLE' in nm:
                    ptr_names.add(nm)
                if re.match(r'^struct\b', base) or base.startswith('struct'):
                    pass
            # 1 行 struct のサイズ推定 (wire 型)
            bm = re.match(r'^struct\s+_?\w+\s*\{(.*)\}$', m.group('body').strip())
            if bm:
                fields = [f.strip() for f in bm.group(1).split(',') if f.strip()]
                sz = 0
                for f in fields:
                    fw = 8 if '*' in f else SCALAR_W.get(' '.join(f.split()[:-1] if len(f.split()) > 1 else f.split()), 4)
                    sz += max(fw, 8) // 8 * 8 if 'double' in f or 'int64' in f or 'LONGLONG' in f else 4
                for nm2 in [re.sub(r'[\s*]', '', x) for x in m.group('names').split(',')]:
                    struct_sizes[nm2] = sz
            continue
        m = re.match(r'^(?P<ret>[A-Za-z_][\w\s]*?[\s\*])\(?[\s\*]*(?P<name>[A-Za-z_]\w*)\s*\((?P<par>.*)\)$', st)
        if not m: continue
        name = m.group('name')
        ret = ' '.join(m.group('ret').split())
        params = []
        ps = m.group('par').strip()
        if ps and ps != 'void':
            # トップレベル comma split (関数ポインタ型のネスト ( * )(..) は shimx.h では typedef 経由のみ)
            parts, d2, cur2 = [], 0, ''
            for ch2 in ps:
                if ch2 == '(': d2 += 1
                if ch2 == ')': d2 -= 1
                if ch2 == ',' and d2 == 0: parts.append(cur2); cur2 = ''
                else: cur2 += ch2
            if cur2.strip(): parts.append(cur2)
            for p in parts:
                p = ' '.join(p.split())
                toks = p.split()
                if len(toks) == 1:
                    nm2, t = '', toks[0]
                else:
                    nm2, t = toks[-1], ' '.join(toks[:-1])
                if not re.match(r'^[A-Za-z_]\w*$', nm2):
                    nm2, t = '', p
                params.append((t, nm2))
        protos[name] = {'ret': ret, 'params': params}
    return protos, ptr_names, struct_sizes


def kind_of(ty, ptr_names, struct_sizes):
    """'ptr' | 'f32' | 'f64' | 'i64' | 'i32' | 'void' | 'struct:N' | None(不明)"""
    ty = ty.strip()
    if ty == 'void': return 'void'
    if '*' in ty: return 'ptr'
    base = re.sub(r'^(?:const\s+|unsigned\s+|signed\s+)+', '', ty).strip()
    if base in ('float', 'FLOAT'): return 'f32'
    if base in ('double', 'DOUBLE'): return 'f64'
    if base in SCALAR_W: return 'i64' if SCALAR_W[base] == 64 else 'i32'
    if base in ptr_names: return 'ptr'
    if base in struct_sizes: return 'struct:%d' % struct_sizes[base]
    # ポインタ風名 (H*/LP*/PC*/P*) のヒューリスティック
    if re.match(r'^(H|LP|PC|NP|P)[A-Z]', base): return 'ptr'
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pe', default=PE_DEF)
    ap.add_argument('--meta', default='', help='lift_meta.json (無ければ entries/textwin のみ生成)')
    ap.add_argument('--out', default=os.path.join(FLE, 'work', 'boot'))
    ap.add_argument('--nosx', action='store_true')
    ap.add_argument('--no-vmt', action='store_true', help='VMT/関数ポインタ harvest をしない (M11 closure + boot 断片のみ)')
    a = ap.parse_args()

    import pefile
    pe = pefile.PE(a.pe)
    img = pe.get_memory_mapped_image()

    have_meta = a.meta and os.path.exists(a.meta)
    meta = json.load(open(a.meta)) if have_meta else {'iat_map': {}}
    iat_names = sorted(set(e['name'] for e in meta.get('iat_map', {}).values()))

    sx_hdr = os.path.join(REPO, 'shimx', 'src', 'shimx.h')
    sx_hdr2 = os.path.join(REPO, 'shimx', 'src', 'shimx_stubs.h')
    sx_exp = os.path.join(REPO, 'shimx', 'exports.txt')
    protos, ptr_names, struct_sizes = parse_shimx_h(sx_hdr)
    if os.path.exists(sx_hdr2):
        p2, ptr2, sz2 = parse_shimx_h(sx_hdr2)
        protos.update(p2); ptr_names |= ptr2
        for k, v in sz2.items(): struct_sizes.setdefault(k, v)
    shimx_names = set(l.strip() for l in open(sx_exp) if l.strip() and not l.startswith('#'))
    cpu_src = open(os.path.join(FLE, 'rt', 'fle_cpu.c')).read()
    cpu_imps = sorted(set(re.findall(r'^void (imp_[A-Za-z0-9_]+)\(void\)', cpu_src, re.M)))

    os.makedirs(a.out, exist_ok=True)

    # ---- 1. entries: roots = コミット済み fle_entries + VMT/関数ポインタ harvest + boot 断片 ----
    #   FLEngine (Delphi) は VMT を .text に置き、仮想 call は ott_dispatch で解決されるため、
    #   .data/.reloc/.rdata/.didata + .text から .pdata 開始点を指す qword を「関数ポインタ」として
    #   root に追加する (VMT method / proc 表 / callback 表)。boot の間接 call を lift 集合に含める。
    base = json.load(open(os.path.join(FLE, 'fle_entries.json')))
    roots = set(int(x) if not isinstance(x, str) else int(x, 16) for x in base['roots'])
    frag_add = [ENTRY_VA, LONGJMP_TARGET]
    roots |= set(frag_add)
    # 実行時に発見された unlifted target の累積 (boot_roots.json — コミット済み、REVIEW 可能)
    extra_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'boot_roots.json')
    if os.path.exists(extra_path):
        for x in json.load(open(extra_path)):
            roots.add(int(x, 16))
    # FLE-6 実測専用: FLE_EXTRA_ROOTS (カンマ区切り hex) を一時的に root に足す。boot_roots.json は汚さない
    for x in filter(None, os.environ.get('FLE_EXTRA_ROOTS', '').split(',')):
        roots.add(int(x.strip(), 16))
    if not a.no_vmt:
        pdata = []
        for s in pe.sections:
            if s.Name.startswith(b'.pdata'):
                raw = s.get_data()
                for i in range(0, len(raw) // 12 * 12, 12):
                    b, e, u = struct.unpack_from('<III', raw, i)
                    if b == 0 and e == 0:
                        break
                    pdata.append(IMG + b)
                break
        pset = set(pdata)
        # FLE-2: VMT スロットや **jump table の case body** が「.pdata 整列でない関数途中」を指す。
        # 全 .text word を root にすると 6 万超 (= 全域 lift) になって実用的でないため、
        # **boot_roots.json に明記された target のみ** を追加で root にする
        # (実行時に unlifted として発見 → 累積する既存方式)。
        # 実測: 0x527592 系 (fn 0x5274c0 は 1 バイトの縮退 .pdata) / 0x433051 系 (fn 0x42daa0 内)。
        # いずれも `add rcx,-imm; jmp <target>` の Delphi switch テーブルで、x64c の
        # jump_table_abs が解決するには当該 VA が roots に入っている必要がある。
        extra_targets = {int(x, 16) for x in json.load(open(extra_path))} if os.path.exists(extra_path) else set()
        for s in pe.sections:
            n = s.Name.rstrip(b'\0').decode()
            if n not in ('.data', '.reloc', '.rdata', '.didata', '.text'):
                continue
            va, sz, rawsz = s.VirtualAddress, s.Misc_VirtualSize, s.SizeOfRawData
            data = bytes(img[va:va + min(sz, rawsz) if rawsz else sz])
            for off in range(0, len(data) - 7, 8):
                v = struct.unpack_from('<Q', data, off)[0]
                if v in pset or v in extra_targets:
                    roots.add(v)
        # ---- FLE-2: Delphi switch テーブルの case body 自動 harvest ----
        # .text 内に「.text を指す 8B 値が 2〜16 個連続する」領域 = jump table 候補。
        # case body は Delphi RTL の同一 shape `48 83 c1 <imm8>  e9 <rel32>`
        # (add rcx,-imm ; jmp 共通継続) で .pdata 整列でないことが多い
        # (縮退 .pdata の fn 0x5274c0 / fn 0x42daa0 等)。
        # 無条件採取は非コード領域まで root 化して unsupported 命令が爆発するため
        # (実測: 40,263 関数 / unsup 60 種)、shape 検査を通ったものだけ roots に入れる。
        # 連続数上限は 32 (実測の最大テーブルは 0x642e78 の 20 entry)。
        text_lo, text_hi = 0x401000, 0x401000 + 0xfa34b0
        def is_delphi_case(va):
            b = bytes(img[va - IMG: va - IMG + 12])
            if len(b) < 12:
                return False
            return b[0] == 0x48 and b[1] == 0x83 and b[2] == 0xc1 and b[4] == 0xe9
        tsec = None
        for s in pe.sections:
            if s.Name.rstrip(b'\0').decode().startswith('.text'):
                tsec = s; break
        if tsec is not None:
            va0, sz, rawsz = tsec.VirtualAddress, tsec.Misc_VirtualSize, tsec.SizeOfRawData
            data = bytes(img[va0:va0 + min(sz, rawsz) if rawsz else sz])
            run = []
            def flush():
                if 2 <= len(run) <= 32:
                    for x in run:
                        if x not in pset and text_lo <= x < text_hi and is_delphi_case(x):
                            roots.add(x)
            # 注 (FLE-4): .text 内の「.pdata 整齊エントリの連続」= Delphi VMT スロット配列も
            # 含まれうるが、対象 0x6a7b70 は **image 内に qword 参照を持たない** (実行時構築
            # vtable) ため本 scan では拾えない。boot_roots.json への実行時累積で対応する。
            for off in range(0, len(data) - 7, 8):
                v = struct.unpack_from('<Q', data, off)[0]
                if text_lo <= v < text_hi:
                    run.append(v)
                else:
                    flush(); run = []
            flush()
    json.dump({'roots': sorted(roots), 'calltgt': base.get('calltgt', [])},
              open(os.path.join(a.out, 'fle_entries_boot.json'), 'w'), indent=1)

    # ---- 2. .text 窓 — FLEngine は VMT / PackageInfo / units 配列 / InitTable を .text に置く
    #      (実測: unit#17 の f_410320 が VMT 負領域 [VMT-0x30]=vmtNewInstance を .text から読む) ので
    #      boot 構成では .text 全域をデータ敷設する (#embed で高速コンパイル)。冗長な小窓は廃止。
    def q(va): return struct.unpack_from('<Q', img, va - IMG)[0]
    def d(va): return struct.unpack_from('<I', img, va - IMG)[0]
    cnt = d(PKGINFO_VA); units_arr = q(PKGINFO_VA + 8)
    assert 900 <= cnt <= 1100, 'unexpected unit count %d' % cnt
    text_va = 0x401000
    text_size = 0xfa34b0
    bin_path = os.path.join(a.out, 'text.bin')
    with open(bin_path, 'wb') as fb:
        fb.write(bytes(img[text_va - IMG: text_va - IMG + text_size]))
    out = ['/* auto-gen by gen_boot.py: .text 全域のデータ敷設 (VMT/PackageInfo/units 配列/unit proc 含む) */',
           '#include <stdint.h>', '#include <string.h>', '#include "fle_cpu.h"',
           'static const unsigned char fle_text_seg[] = {',
           '#embed "%s"' % bin_path,
           '};',
           'void fle_textwin_install(void) {',
           '  memcpy((void*)0x%xu, fle_text_seg, %du);' % (text_va, text_size),
           '}']
    open(os.path.join(a.out, 'fle_textwin.c'), 'w').write('\n'.join(out) + '\n')
    total = text_size; wlist = [(text_va, text_size)]

    # ---- 3. imp bridge (lift_meta が無い場合は skip — boot_e2e が lift 後に再呼出する) ----
    if not have_meta:
        print('[gen_boot] lift_meta 無し → entries/textwin のみ生成 (bridge は lift 後に再実行)')
        json.dump({'stats': None, 'unit_count': cnt, 'units_arr': hex(units_arr),
                   'frag_roots': [hex(x) for x in frag_add]},
                  open(os.path.join(a.out, 'gen_report.json'), 'w'), indent=1)
        return

    def rx(i, kind):
        if i < 4:
            reg = {0: 'R[1]', 1: 'R[2]', 2: 'R[8]', 3: 'R[9]'}[i]
            if kind == 'f32': return 'X[%d].f[0]' % i
            if kind == 'f64': return 'X[%d].df[0]' % i
            return reg
        off = 'R[4] + 0x28ull + 8ull * %d' % (i - 4)
        if kind == 'f32': return 'bits_f32(%s)' % off
        if kind == 'f64': return 'bits_f64(%s)' % off
        return 'LD64(%s)' % off

    gen = ['/* auto-gen by gen_boot.py — imp_<Name> strong 上書き層 (FLE-2)',
           ' * shimx 実装へ MS x64 ABI (rcx/rdx/r8/r9 + [rsp+0x28+8k], float は X[0..3]) で橋絡み。',
           ' * shimx 無しの名前は 0 返却 soft スタブ (fle_boot.c の計数に集計)。curated は fle_boot.c。*/',
           '#include "fle_cpu.h"', '#include "../../shimx/src/shimx.h"',
           'extern long fle_soft_hit(const char* nm);', 'extern unsigned char fle_g_strict;',
           'static inline float bits_f32(uint64_t a){uint32_t v=LD32(a);float f;__builtin_memcpy(&f,&v,4);return f;}',
           'static inline double bits_f64(uint64_t a){uint64_t v=LD64(a);double f;__builtin_memcpy(&f,&v,8);return f;}',
           '#define PX(v) ((void*)(uintptr_t)(v))']
    stats = {'shimx': 0, 'soft': 0, 'curated': 0, 'noproto': 0, 'structarg': 0, 'vararg': 0}
    noproto_list, structarg_list = [], []
    bridge_names = []
    for nm in iat_names:
        if nm in CURATED:
            stats['curated'] += 1
            continue
        use_sx = (not a.nosx) and nm in shimx_names and nm in protos
        if not use_sx:
            if nm in shimx_names and nm not in protos:
                stats['noproto'] += 1; noproto_list.append(nm)
            stats['soft'] += 1
            gen.append('void imp_%s(void) { fle_soft_hit("%s"); R[4] += 8; R[0] = 0; }' % (nm, nm))
            continue
        pr = protos[nm]
        rk = kind_of(pr['ret'], ptr_names, struct_sizes)
        if rk is None:  # 戻り型不明 → soft 扱い
            stats['noproto'] += 1; noproto_list.append(nm)
            stats['soft'] += 1
            gen.append('void imp_%s(void) { fle_soft_hit("%s"); R[4] += 8; R[0] = 0; }' % (nm, nm))
            continue
        bad = False
        argexprs = []
        prelude = []
        for i, (ty, _pn) in enumerate(pr['params']):
            k = kind_of(ty, ptr_names, struct_sizes)
            if k is None or (k.startswith('struct:') and int(k.split(':')[1]) not in (4, 8)):
                if k is not None: stats['structarg'] += 1; structarg_list.append('%s:%s' % (nm, ty))
                bad = True; break
            raw = rx(i, 'i32' if not k.startswith(('f32', 'f64')) else k)
            prelude.append('  uint64_t a%d = (uint64_t)(%s);' % (i, raw) if not k.startswith(('f32', 'f64'))
                           else '  %s a%d = (%s);' % ('float' if k == 'f32' else 'double', i, raw))
            if k.startswith('struct:'):
                n = int(k.split(':')[1])
                argexprs.append('(*(uint%d_t*)&a%d)' % (n * 8, i) if n == 8 else '(uint32_t)a%d' % i)
            elif k == 'ptr':
                argexprs.append('PX(a%d)' % i)
            elif k == 'f32':
                argexprs.append('(float)a%d' % i)
            elif k == 'f64':
                argexprs.append('(double)a%d' % i)
            else:
                argexprs.append('(%s)a%d' % (ty.split('*')[0].strip() if '*' in ty else ty, i))
        if bad:
            stats['soft'] += 1
            gen.append('void imp_%s(void) { fle_soft_hit("%s"); R[4] += 8; R[0] = 0; }' % (nm, nm))
            continue
        body_args = ', '.join(argexprs)
        call = '%s(%s)' % (nm, body_args)
        th = ['void imp_%s(void) {' % nm]
        th.extend(prelude)                       # R[4] 調整前に全引数を退避 (stack args の読み位置保証)
        th.append('  R[4] += 8; /* IMP_RET */')
        if rk == 'void':
            th.append('  %s;' % call)
        elif rk == 'f32':
            th.append('  X[0].f[0] = (float)%s;' % call)
        elif rk == 'f64':
            th.append('  X[0].df[0] = (double)%s;' % call)
        elif rk == 'i64':
            th.append('  R[0] = (uint64_t)%s;' % call)
        else:
            th.append('  R[0] = (uint32_t)(%s);' % call)
        th.append('}')
        gen.extend(th)
        stats['shimx'] += 1
        bridge_names.append(nm)

    open(os.path.join(a.out, 'fle_imp_bridge.c'), 'w').write('\n'.join(gen) + '\n')

    # ---- 4. fle_cpu.c の imp 改名定義 (-D) ----
    defs = ' '.join('-D%s=impc_%s' % (x, x[4:]) for x in cpu_imps)
    open(os.path.join(a.out, 'fle_link_defs.txt'), 'w').write(defs + '\n')

    print('[gen_boot] entries %d roots (+frag %s, +vmt harvest)' if not a.no_vmt else '[gen_boot] entries %d roots (no-vmt, frag %s) / textwin %d windows %d B / imp: shimx %d soft %d curated %d noproto %d structarg %d' % (
        len(roots), [hex(x) for x in frag_add], len(wlist), total, stats['shimx'], stats['soft'], stats['curated'], stats['noproto'], stats['structarg']))
    if noproto_list: print('[gen_boot] noproto (shimx あるが shimx.h 宣言無し):', noproto_list[:20])
    if structarg_list: print('[gen_boot] struct-by-value args (soft 化):', structarg_list[:20])
    json.dump({'stats': stats, 'bridge_names': bridge_names, 'noproto': noproto_list,
               'unit_count': cnt, 'units_arr': hex(units_arr),
               'frag_roots': [hex(x) for x in frag_add]},
              open(os.path.join(a.out, 'gen_report.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
