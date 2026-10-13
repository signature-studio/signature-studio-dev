#!/usr/bin/env python3
# M11-N21 (#572): .data 末尾 slot (既定 RVA 0x11e5000) を実行時に参照し得る経路の静的調査。
#   (1) .text 全体を capstone で線形走査し、RIP 相対 memory operand の実効アドレスが [slot-WIN, slot+8) に入る命令
#   (2) .text 内の DIR64 reloc (絶対アドレス imm64 / mem disp) の値が同範囲を指すもの
#   (3) .data 内の DIR64 のうち値が同範囲を指すもの (テーブル→テーブル参照)
#   (4) slot の値 (関数ポインタ) の指す関数と、その関数への直接 call / 参照数
# 注: 線形走査は .text 内のデータ混在で取りこぼし/誤復号があり得る。結果は「静的に見つかった範囲」であり、
#     見つからない = 参照されない、ではない (配列を base+index*8 で参照するコードは base 側だけが範囲に入る)。
#   python3 m11_reloc_xref.py PE [--slot 0x11e5000] [--win 0x40] [--json out.json]
import sys, os, struct, json, argparse
import capstone
from capstone import x86
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.environ.get('M11_OTTLIB_DIR', os.path.join(BASE, '..', 'm6')))
from ottlib import Bin
from m11_reloc_audit import collect_relocs

IMG = 0x400000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pe')
    ap.add_argument('--slot', default='0x11e5000')
    ap.add_argument('--win', default='0x40')
    ap.add_argument('--json')
    a = ap.parse_args()
    slot = int(a.slot, 0); win = int(a.win, 0)
    W = Bin(a.pe)
    lo_t, text = W.sec_find('.text')
    lo_d, data = W.sec_find('.data')
    val = struct.unpack_from('<Q', data, slot - lo_d)[0]
    tgt_rva = val - IMG
    print('[xref] slot RVA 0x%x value 0x%x (-> RVA 0x%x, %s)' % (
        slot, val, tgt_rva, '.text' if lo_t <= tgt_rva < lo_t + len(text) else '?'))
    lo_r, hi_r = slot - win, slot + 8      # 参照範囲 (slot より前も含め、テーブル先頭からの参照を拾う)

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    rip_hits, abs_hits = [], []
    call_hits = []
    # .pdata 関数境界で区切って復号 (.text 内データ混在対策)
    fns = sorted(W.fns)
    n_ins = 0
    for (start, size) in fns:
        if not (lo_t <= start < lo_t + len(text)):
            continue
        off = start - lo_t
        code = text[off:off + size]
        for ins in md.disasm(code, start + IMG):
            n_ins += 1
            for op in ins.operands:
                if op.type == x86.X86_OP_MEM and op.mem.base == x86.X86_REG_RIP:
                    ea = ins.address + ins.size + op.mem.disp - IMG
                    if lo_r <= ea < hi_r:
                        rip_hits.append(dict(fn=start, at=ins.address - IMG, ea=ea, asm='%s %s' % (ins.mnemonic, ins.op_str)))
            if ins.mnemonic == 'call' and ins.operands and ins.operands[0].type == x86.X86_OP_IMM:
                if ins.operands[0].imm - IMG == tgt_rva:
                    call_hits.append(dict(fn=start, at=ins.address - IMG))
    relocs = collect_relocs(W)
    for r in relocs:
        for (n, lo, d) in W.sections:
            if lo <= r < lo + len(d) and r - lo + 8 <= len(d):
                v = struct.unpack_from('<Q', d, r - lo)[0]
                if lo_r <= v - IMG < hi_r:
                    abs_hits.append(dict(sec=n, rva=r, v=v))
                break
    # 関数ポインタ値そのものへの参照 (slot 値 = 関数 VA)
    fn_ref = []
    for r in relocs:
        for (n, lo, d) in W.sections:
            if lo <= r < lo + len(d) and r - lo + 8 <= len(d):
                v = struct.unpack_from('<Q', d, r - lo)[0]
                if v == val:
                    fn_ref.append(dict(sec=n, rva=r))
                break
    # 関数ポインタの指す先が .pdata 関数開始か
    fn_start = any(s == tgt_rva for (s, _) in fns)
    print('[xref] 復号命令数=%d (関数数 %d)' % (n_ins, len(fns)))
    print('[xref] (1) RIP 相対で [0x%x, 0x%x) を指す命令: %d 件' % (lo_r, hi_r, len(rip_hits)))
    for h in rip_hits[:40]:
        print('[xref]     fn=0x%x at=0x%x ea=0x%x  %s' % (h['fn'], h['at'], h['ea'], h['asm']))
    print('[xref] (2/3) DIR64 の値が同範囲を指す: %d 件 %s' % (len(abs_hits), json.dumps(abs_hits[:20])))
    print('[xref] (4) 値 0x%x の関数: .pdata 関数開始=%s / 直接 call=%d 件 / DIR64 で同値を持つ slot=%d 件 %s' % (
        val, fn_start, len(call_hits), len(fn_ref), json.dumps(fn_ref[:10])))
    res = dict(slot=slot, value=val, rip_hits=rip_hits, abs_hits=abs_hits, call_hits=call_hits,
               same_value_dir64=fn_ref, target_is_fn_start=fn_start, n_ins=n_ins)
    if a.json:
        json.dump(res, open(a.json, 'w'), indent=1)


if __name__ == '__main__':
    main()
