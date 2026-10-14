#!/usr/bin/env python3
"""value 17 関数の .rdata 参照スロットが base relocation (DIR64) の対象かを調べる (#2024)。

目的: RVA 候補 (上位 32 bit が 0) の語が、リンカの再配置対象 (ImageBase + RVA の絶対ポインタ) か
      再配置対象でない整数定数かを切り分ける。DIR64 の対象なら、ファイル上の値は絶対アドレスになる。
出力: 関数ごとの参照スロット数・再配置対象数、語分類ごとの再配置対象件数 (JSON)。
usage: ks_rdata_reloc_check.py <HeartCore.core_64> <SlateCore.core_64> <ks_rdata_class.json> <out.json>
"""
import sys, os, json, struct, re, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ks_identity import Pe
from ks_rdata_value import sec_of


def reloc_set(pe):
    """DIR64 再配置の対象 RVA の集合。"""
    s = set()
    pe.pe.parse_data_directories()
    for d in getattr(pe.pe, 'DIRECTORY_ENTRY_BASERELOC', []):
        for e in d.entries:
            if e.type == 10:  # IMAGE_REL_BASED_DIR64
                s.add(e.rva)
    return s


def rip_slots(pe, va):
    """関数内の [rip+disp] 参照先 (.rdata) のスロット RVA を出現順に 4 語 (32 B) 分返す。"""
    ins, _ = pe.disasm(va)
    out = []
    for i in ins:
        m = re.search(r'\[rip ([+-]) (0x[0-9a-f]+)\]', i.op_str)
        if not m:
            continue
        t = i.address + i.size + (int(m.group(2), 16) * (1 if m.group(1) == '+' else -1))
        rva = t - pe.base
        sec = next((x for x in pe.pe.sections if x.VirtualAddress <= rva < x.VirtualAddress + x.Misc_VirtualSize), None)
        if sec is not None and sec.Name.rstrip(b'\0') == b'.rdata':
            out.append(rva)
    return out


def main(kp, sp, cls_json, out):
    kh, sc = Pe(kp), Pe(sp)
    rs_sc, rs_kh = reloc_set(sc), reloc_set(kh)
    print('reloc DIR64 count', 'sc', len(rs_sc), 'kh', len(rs_kh))
    rc = json.load(open(cls_json))
    tot = collections.Counter()
    funcs = {}
    for s, info in sorted(rc.items()):
        if info['cls'] != 'value':
            continue
        sl_sc = rip_slots(sc, int(s, 16))
        sl_kh = rip_slots(kh, int(info['kh_va'], 16))
        c = collections.Counter()
        for r in sl_sc:
            for k in range(0, 32, 8):
                c['sc_slot_words'] += 1
                if (r + k) in rs_sc:
                    c['sc_reloc_word'] += 1
        for r in sl_kh:
            for k in range(0, 32, 8):
                c['kh_slot_words'] += 1
                if (r + k) in rs_kh:
                    c['kh_reloc_word'] += 1
        funcs[s] = dict(c)
        tot.update(c)
        print(s, dict(c))
    res = dict(sorted(tot.items()))
    print(json.dumps(res, sort_keys=True))
    json.dump(dict(summary=res, funcs=funcs), open(out, 'w'), indent=1, sort_keys=True)


if __name__ == '__main__':
    main(*sys.argv[1:5])
