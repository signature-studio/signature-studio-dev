#!/usr/bin/env python3
"""fw_image.py — Balance (icall 書換え済み PE) を wasm 線形メモリ敷設用イメージにする.

  python3 fw_image.py --pe fw_icall.dll --map fw_map.json --out fw_image.bin --imports fw_imports.json

* 全 section をその VA (= wasm アドレス, shift 無し) に敷いた生イメージ (offset = VA)。
  SizeOfImage 分を確保し, .icall section (BLK 等) も含む — lifted IR が inttoptr 定数で直接読み書きするため。
* IAT (インポート境界テーブル) の qword を合成 VA 0xE000000 + i*8 に差し替え (実行時 loader が無いため;
  dispatch 表側で imp_<name> C 関数に接続, fw_table.py)。
* 出力 json: {imports: [{name, dll, iat_va, syn_va}], image_top, iat_patches}
* 実バイナリ由来なので wasm 埋め込み禁止 (EULA 配慮, m11 と同規則) — node ハーネスが実行時に HEAPU8 へ敷設する。
"""
import argparse, json, struct
import pefile


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pe', required=True)
    ap.add_argument('--map', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--imports', required=True)
    ap.add_argument('--syn-base', type=lambda x: int(x, 0), default=0xE000000)
    a = ap.parse_args()
    pe = pefile.PE(data=open(a.pe, 'rb').read(), fast_load=True)
    pe.parse_data_directories(directories=[
        pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
    base = pe.OPTIONAL_HEADER.ImageBase
    size = pe.OPTIONAL_HEADER.SizeOfImage
    img = bytearray(size)
    for s in pe.sections:
        d = s.get_data()
        va = base + s.VirtualAddress
        img[va - base:va - base + len(d)] = d
    # IAT 差し替え
    imports = []
    syn = a.syn_base
    for e in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
        dll = e.dll.decode()
        for imp in e.imports:
            iat_va = imp.address - base + base   # imp.address は VA
            off = imp.address - base
            if off + 8 <= size:
                struct.pack_into('<Q', img, off, syn)
            imports.append({'name': imp.name.decode() if imp.name else 'ord%d' % imp.ordinal,
                            'dll': dll, 'iat_va': iat_va, 'syn_va': syn})
            syn += 8
    open(a.out, 'wb').write(img)
    json.dump({'image_base': base, 'image_top': size, 'imports': imports,
               'syn_base': a.syn_base, 'n_imports': len(imports)},
              open(a.imports, 'w'), indent=1)
    print('[image] %s: %d bytes (VA 0x%x..0x%x), imports %d (syn 0x%x..0x%x)'
          % (a.out, len(img), base, base + size, len(imports), a.syn_base, syn - 8))


if __name__ == '__main__':
    main()
