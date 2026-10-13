#!/usr/bin/env python3
"""pe_image.py — PE イメージの data 実体化 (m11_data_gen 方式) の共通実装 (GUI-12 / #566)。

m11_data_gen.py (tools/m11, 読取専用) の規則をここに写し、gui_lift_post.py の `__pe_image` が同じ規則を使うようにする:
  - 実体化対象は .data/.rdata などの data 系セクション (.text は lift 済みなので入れない)
  - .reloc の IMAGE_REL_BASED_DIR64 (type 10) が指す 8B 値 (image 内ポインタ) は preferred base 寄生なので補正する
  - 補正対象 = base < v < base + span (m11 は span=0x1ac0000, 厳密な不等号)

2 つの敷設モード:
  lva     : m11 方式。linear memory の固定アドレス LVA = VA - base + lb に置く前提で値を静的に書き換える
            (`rebase_sections`)。tools/m11/m11_data_gen.py の出力とバイト一致する (flengine/pe_image_parity.py で検査)
  runtime : RetDec C 経路 (`__pe_image` は C の静的配列で、アドレスはリンク時まで不定)。補正は静的に書けないので
            再配置テーブル (イメージ内 offset) を出し、起動時に delta = &__pe_image[0] - base を足す (`runtime_image`)。
            .text を指す値 (関数 VA) は fnmap の鍵なので補正しない。

CLI (診断): pe_image.py <pe> [--lb 0x10000]  → セクション別の DIR64 件数と補正件数
"""
import argparse
import struct
import sys

IMG_SPAN_M11 = 0x1ac0000   # m11_data_gen.py / m11_image_gen.py の VA_SPAN


class PE:
    def __init__(self, path):
        d = open(path, "rb").read()
        pe = struct.unpack_from("<I", d, 0x3C)[0]
        assert d[pe:pe + 4] == b"PE\0\0", "not a PE: %s" % path
        nsec = struct.unpack_from("<H", d, pe + 6)[0]
        optsz = struct.unpack_from("<H", d, pe + 20)[0]
        opt = pe + 24
        assert struct.unpack_from("<H", d, opt)[0] == 0x20B, "PE32+ only"
        self.base = struct.unpack_from("<Q", d, opt + 24)[0]
        self.size_of_image = struct.unpack_from("<I", d, opt + 56)[0]
        self.sections = []   # (name, rva, vsize, bytes padded to vsize)
        so = opt + optsz
        for i in range(nsec):
            e = so + i * 40
            name = d[e:e + 8].split(b"\0")[0].decode("latin1")
            vsz, va, rsz, rptr = struct.unpack_from("<IIII", d, e + 8)
            if vsz == 0 or va == 0:
                continue
            raw = d[rptr:rptr + min(rsz, vsz)] if rsz else b""
            raw = raw + bytes(max(0, vsz - len(raw)))
            self.sections.append((name, va, vsz, raw))

    def section(self, name):
        for s in self.sections:
            if s[0] == name:
                return s
        return None

    def dir64_relocs(self):
        """.reloc の DIR64 RVA 表 (m11_data_gen.py と同じ走査; page==0 / 不正 block で打切り)"""
        out = []
        for (n, _va, _vs, data) in self.sections:
            if n != ".reloc":
                continue
            i = 0
            while i + 8 <= len(data):
                page, blk = struct.unpack_from("<II", data, i)
                if blk == 0 or blk < 8 or page == 0:
                    break
                for k in range((blk - 8) // 2):
                    e = struct.unpack_from("<H", data, i + 8 + k * 2)[0]
                    if (e >> 12) == 10:
                        out.append(page + (e & 0xfff))
                i += blk
        return out


def rebase_sections(pe, names=(".rdata", ".data"), lb=0, span=IMG_SPAN_M11):
    """lva モード: names の各セクションの DIR64 値を VA -> LVA (= VA - base + lb) へ補正する (m11_data_gen と同一規則)。
    -> [(name, lo_lva, bytearray, fixed_count)] (セクションの出現順)"""
    relocs = pe.dir64_relocs()
    out = []
    for (n, lo, _vs, data) in pe.sections:
        if n not in names:
            continue
        sd = bytearray(data)
        fixed = 0
        for r in relocs:
            if lo <= r < lo + len(sd) - 8:
                off = r - lo
                v = struct.unpack_from("<Q", sd, off)[0]
                if pe.base < v < pe.base + span:
                    struct.pack_into("<Q", sd, off, v - pe.base + lb)
                    fixed += 1
        out.append((n, lo + lb, sd, fixed))
    return out


def runtime_image(pe, skip=(".text",), relocate=True):
    """runtime モード: SizeOfImage 長のイメージ (skip 以外のセクションを RVA に配置) と再配置テーブルを返す。
    再配置テーブル = DIR64 のうち「値が保持イメージ内を指す (.text は除外)」スロットの image offset。
    relocate=False は検査用 (再配置テーブルを空にする = 補正を飛ばした状態を作るネガコン)。
    -> (bytes, [offset], stats)"""
    img = bytearray(pe.size_of_image)
    for (n, va, vs, data) in pe.sections:
        if n in skip or n == ".reloc":
            continue
        img[va:va + len(data)] = data
    text = [(va, va + vs) for (n, va, vs, _d) in pe.sections if n in skip]
    offs = []
    n_dir64 = 0
    n_text = 0
    n_out = 0
    for r in pe.dir64_relocs():
        n_dir64 += 1
        # スロットが保持イメージ内 (skip セクション内は対象外: 中身が 0)
        if r + 8 > len(img) or any(lo <= r < hi for lo, hi in text):
            continue
        v = struct.unpack_from("<Q", img, r)[0]
        if not (pe.base < v < pe.base + pe.size_of_image):
            n_out += 1
            continue
        if any(lo <= v - pe.base < hi for lo, hi in text):
            n_text += 1     # 関数 VA: fnmap の鍵として VA のまま残す
            continue
        offs.append(r)
    stats = {"dir64": n_dir64, "rebased": len(offs), "text_kept": n_text, "outside_image": n_out}
    return bytes(img), (sorted(offs) if relocate else []), stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pe")
    ap.add_argument("--lb", default="0")
    a = ap.parse_args()
    pe = PE(a.pe)
    lb = int(a.lb, 0)
    print("base=0x%x size_of_image=0x%x DIR64=%d" % (pe.base, pe.size_of_image, len(pe.dir64_relocs())))
    for n, lo, sd, fixed in rebase_sections(pe, (".rdata", ".data"), lb):
        print("lva  %-7s lo=0x%x len=%d fixed=%d" % (n, lo, len(sd), fixed))
    _img, offs, st = runtime_image(pe)
    print("runtime image: %s" % st)


if __name__ == "__main__":
    sys.exit(main())
