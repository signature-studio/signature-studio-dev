"""#107 (ST-T11): 「inline HWID コード ×24 関数」(GATES G04 / startup REPORT §1) と
「== 0x3f を比較する関数 26」(本 REPORT §3.2) の食い違いを、定義を明示して機械的に突合する (読取専用)。

定義 (PE の import 解決と文字列参照だけを使う。逆アセンブルは peidx.Image の共通部品):
  API  = 関数内の call 先が指す import 名。直接 call は宛先の thunk (`jmp qword ptr [rip+IAT]`) を 1 段たどる。
         `call qword ptr [rip+..]` は IAT スロットを直接指すときだけ解決する (.data の関数ポインタ表は解決しない)
  STR  = rip 相対で `MachineGuid` / `SOFTWARE\\Microsoft\\Cryptography` の ASCII 文字列 VA を指す命令を持つ
  H1   = API に GetComputerNameExW と SHGetFolderPathW を両方含む
  H2   = API に GetComputerNameExW と (RegOpenKeyExA|W・RegQueryValueExW のいずれか) を含む
  H3   = STR を持つ
  G3f  = gradeChar (`[[[0x15e4790]]+0xd0]`) を `cmp ..., 0x3f` で比較する関数 (results/flag_sites.json の grade_sites)
  G40  = 同 `cmp ..., 0x40`

再現: FL_WIN64_DIR=<fl-win64 展開先> python3 tools/startup/license_obs/probe_hwid.py
出力: results/probe_hwid.json (自動生成)。
"""
import collections, json, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from peidx import Image, rip_target  # noqa: E402
import pefile  # noqa: E402

RES = os.path.join(HERE, 'results')
STRINGS = [b'MachineGuid\x00', b'SOFTWARE\\Microsoft\\Cryptography\x00']
GCN = 'GetComputerNameExW'
SHF = 'SHGetFolderPathW'
REG = {'RegOpenKeyExA', 'RegOpenKeyExW', 'RegQueryValueExW'}


def iat_map(im):
    im.pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
    m = {}
    for e in im.pe.DIRECTORY_ENTRY_IMPORT:
        for imp in e.imports:
            if imp.name is None:
                continue
            va = imp.address if imp.address >= im.base else im.base + imp.address
            m[va] = imp.name.decode()
    return m


def thunk_name(im, iat, va, cache):
    key = ('t', va)
    if key not in cache:
        first = None
        if im.text_lo <= va < im.text_hi:
            first = next(iter(im.md.disasm(im.read(va, 16), va)), None)
        nm = None
        if first is not None and first.mnemonic == 'jmp' and rip_target(first) is not None:
            nm = iat.get(rip_target(first))
        cache[key] = nm
    return cache[key]


def string_vas(im):
    out = set()
    for s in STRINGS:
        i = im.raw.find(s)
        while i >= 0:
            rva = im.pe.get_rva_from_offset(i)
            out.add(im.base + rva)
            i = im.raw.find(s, i + 1)
    return out


def main():
    im = Image()
    iat = iat_map(im)
    svas = string_vas(im)
    api = collections.defaultdict(set)
    strf = set()
    cache = {}
    n = 0
    for lo, hi, ins in im.iter_insns():
        n += 1
        for i in ins:
            t = rip_target(i)
            if i.mnemonic == 'call':
                if i.op_str.startswith('0x'):
                    nm = thunk_name(im, iat, int(i.op_str, 16), cache)
                elif t is not None:
                    nm = iat.get(t)
                else:
                    nm = None
                if nm:
                    api[lo].add(nm)
            if t is not None and t in svas:
                strf.add(lo)
    cmp_sets = {'0x3f': set(), '0x40': set()}
    flagged = json.load(open(os.path.join(RES, 'flag_sites.json')))
    for g in flagged['grade_sites']:
        if g.get('op', '').startswith('cmp imm 0x3f'):
            cmp_sets['0x3f'].add(g['func'])
        if g.get('op', '').startswith('cmp imm 0x40'):
            cmp_sets['0x40'].add(g['func'])
    H = {
        'H1 GCN+SHF': {f for f in api if GCN in api[f] and SHF in api[f]},
        'H2 GCN+REG': {f for f in api if GCN in api[f] and api[f] & REG},
        'H3 STR': strf,
        'H4 GCN': {f for f in api if GCN in api[f]},
        'H5 SHF': {f for f in api if SHF in api[f]},
    }
    g3f, g40 = cmp_sets['0x3f'], cmp_sets['0x40']
    rows = []
    for name, s in H.items():
        rows.append({
            'def': name, 'n': len(s),
            'in_G3f': len(s & g3f), 'in_G40': len(s & g40),
            'only_H_not_G3f': len(s - g3f), 'G3f_not_in_H': len(g3f - s),
        })
    out = {
        'image_functions': n,
        'iat_names_resolved': len(iat),
        'string_vas': sorted(hex(v) for v in svas),
        'n_G3f': len(g3f), 'n_G40': len(g40),
        'rows': rows,
        'H': {k: sorted(hex(v) for v in s) for k, s in H.items()},
    }
    os.makedirs(RES, exist_ok=True)
    with open(os.path.join(RES, 'probe_hwid.json'), 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f'functions={n} iat_resolved={len(iat)} string_vas={len(svas)} G3f={len(g3f)} G40={len(g40)}')
    for r in rows:
        print(r)


if __name__ == '__main__':
    main()
