#!/usr/bin/env python3
"""PY-137 (#3026): general.saveUndo の undo 履歴 record の PE 事実 (0x1016ca0・0x1017ad0・0x101b780・0x101d180) を検査する (実機不要)。

  FL_WIN64_DIR=<展開先> python3 analysis/py137_saveundo_record.py

PE は fl-win64 素材の extracted/block00031_PE.bin (ImageBase 0x400000)。
全検査が通れば PASS を出し、いずれかが外れれば AssertionError で止まる (PE 指紋が変わった時の検出)。
検査する事実は REPORT_PY124.md §4 の表と 1 対 1 に対応する (履歴 H = [[0x15e1c78]]・record 構造は同 REPORT)。
"""
import os

import capstone
import pefile

PE = os.path.join(os.environ["FL_WIN64_DIR"], "extracted", "block00031_PE.bin")
RING_STEP = 0x1016CA0     # 履歴スロット取得: pos を進め、count を増やし、last を 0 に戻す
RING_LEN = 0x1016E50      # ring の長さ (配列ヘッダ -8 の qword。null なら 0)
IS_LIST = 0x1017150       # [H+8] != 0 (list 所有者の有無)
REC_ADD = 0x1017AD0       # 核: スロット取得 → 書込み → list 追加 or 項目解放
REC_FILL = 0x101B780      # record への書込み (カテゴリ mask ごとに vtbl+0x10 を呼ぶ)
REC_RESET = 0x101D180     # record の初期化 (mask と名前の設定・項目解放)
LIST_PUSH = 0x1019B70     # [H+8] の配列末尾へ record を追加
ITEMS_CLEAR = 0x1019DD0   # record の項目配列を解放
FINALIZE = 0x101A080      # r9b != 0 のときの後処理
NAME_SET = 0x4133F0       # 名前の代入 (record+0x2c)


def main():
    pe = pefile.PE(PE, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(PE, "rb").read()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def read_va(va, n):
        rva = va - base
        for s in pe.sections:
            if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
                off = s.PointerToRawData + (rva - s.VirtualAddress)
                return data[off:off + n]
        raise AssertionError(f"VA {va:#x} は PE の section に無い")

    def body(va, limit=0x800):
        """va から最初の ret までの命令列 (文字列)。"""
        out = []
        for i in md.disasm(read_va(va, limit), va):
            out.append(f"{i.mnemonic} {i.op_str}".strip())
            if i.mnemonic == "ret":
                break
        return out

    def calls(va):
        """va の関数が ret までに直接 call する先 VA の並び。"""
        out = []
        for i in md.disasm(read_va(va, 0x800), va):
            if i.mnemonic == "ret":
                break
            if i.mnemonic == "call" and i.op_str.startswith("0x"):
                out.append(int(i.op_str, 16))
        return out

    def has_seq(ins, seq):
        """ins の中に seq (命令文字列の並び) が連続して現れるか。"""
        return any(ins[k:k + len(seq)] == seq for k in range(len(ins) - len(seq) + 1))

    # 1. 履歴スロット取得 (0x1016ca0): [H+8] の有無で分岐し、無いとき ring の pos・count・last を更新する
    step = body(RING_STEP)
    assert calls(RING_STEP)[0] == IS_LIST, calls(RING_STEP)
    assert "je 0x1016ce3" in step, "[H+8] == 0 の分岐"
    assert has_seq(step, ["mov ebx, 1", "mov rax, qword ptr [rbp + 0x20]", "sub ebx, dword ptr [rax + 0x20]"]), "ebx = 1 - last"
    assert "idiv ecx" in step and "mov dword ptr [rax + 0x1c], edx" in step, "pos = (pos + ebx + len) % len"
    assert "mov dword ptr [rcx + 0x24], eax" in step and "mov dword ptr [rcx + 0x20], 0" in step, "count 更新・last を 0 に戻す"
    assert "jg 0x1016d36" in step, "count = min(count + ebx, len)"
    assert has_seq(step, ["mov rax, qword ptr [rcx + 0x14]", "movsxd rcx, dword ptr [rcx + 0x1c]",
                          "mov rax, qword ptr [rax + rcx*8]"]), "ring[pos] を返す"
    assert calls(RING_LEN) == [] and "mov rax, qword ptr [rax - 8]" in body(RING_LEN), "len = 配列ヘッダ -8"
    assert body(IS_LIST) == ["cmp qword ptr [rcx + 8], 0", "setne al", "ret"], body(IS_LIST)

    # 2. 核 (0x1017ad0): 順序は スロット取得 → 書込み → IsList 判定 → list 追加 (真) or 項目解放 (偽)
    assert calls(REC_ADD) == [RING_STEP, REC_FILL, IS_LIST, LIST_PUSH, ITEMS_CLEAR], [hex(x) for x in calls(REC_ADD)]
    assert "mov rax, qword ptr [r8]" in body(REC_ADD), "flags は 8 バイトを [r8] から読む"

    # 3. record への書込み (0x101b780): 初期化 → 系列番号の書込み → mask 1 ビットごとに vtbl+0x10 → r9b != 0 で後処理
    fill = body(REC_FILL)
    assert calls(REC_FILL)[0] == REC_RESET, calls(REC_FILL)[:1]
    assert "xor r9, r9" in fill[:24], "初期化は r9b = 0 (reset 経路)"
    assert "mov dword ptr [rax + 0x28], ecx" in fill, "record+0x28 に global の dword (系列番号) を書く"
    assert "shl r8, cl" in fill and "test r8, rax" in fill, "mask のビット判定 (1 << c & [rdx+0x54])"
    assert "mov rax, qword ptr [rdx + 0x54]" in fill
    assert "call qword ptr [rbx + 0x10]" in fill, "カテゴリごとに vtbl+0x10 を呼ぶ"
    assert "cmp byte ptr [rbp + 0xc8], 0" in fill and FINALIZE in calls(REC_FILL), "r9b != 0 のとき 0x101a080"
    assert NAME_SET not in calls(REC_FILL)
    for chars in ([0x0B, 0x0D, 0x23], [0x06, 0x07, 0x09, 0x2D, 0x30, 0x32]):
        for k, c in enumerate(chars):
            imm = str(c) if c < 10 else f"{c:#x}"
            want = f"mov byte ptr [rax], {imm}" if k == 0 else f"mov byte ptr [rax + {k}], {imm}"
            assert want in fill, want

    # 4. record の初期化 (0x101d180): r9b != 0 の経路は mask (*r8) を record+0x54 に書き、名前を record+0x2c に代入する
    reset = body(REC_RESET)
    assert "cmp byte ptr [rbp + 0xe8], 0" in reset and "jne 0x101d469" in reset, "r9b != 0 は項目解放を飛ばす"
    assert "mov qword ptr [rax + 0x54], rcx" in reset, "record+0x54 = *[r8] (mask)"
    assert "mov dword ptr [rax + 0x70], 0xffffffff" in reset, "reset 経路は record+0x70 = -1"
    assert NAME_SET in calls(REC_RESET), "名前の代入 0x4133f0 (record+0x2c)"

    print("PY137 record facts: ring(0x1016ca0) pos/count/last, core(0x1017ad0) order, "
          "fill(0x101b780) mask bits & chars, reset(0x101d180) mask/name")
    print("PASS: py137 saveUndo record PE facts")


if __name__ == "__main__":
    main()
