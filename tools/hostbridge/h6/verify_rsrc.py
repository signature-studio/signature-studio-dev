#!/usr/bin/env python3
"""verify_rsrc.py — rsrc_extract.mjs の別アルゴリズム検算 (PE リソース木を使わない).
DLL 全体を生バイトで走査し PNG signature → chunk を IEND まで辿って PNG を列挙する (CRC 検査付き)。
出力 JSON: [{off,size,w,h,sha256}]。リソース木経由の抽出結果 (index.json) と件数・サイズ・sha256 が一致することを h6_check.mjs が照合する。
usage: verify_rsrc.py <dll> <out.json>"""
import hashlib, json, struct, sys, zlib

SIG = b"\x89PNG\r\n\x1a\n"

def scan(buf):
    out, pos = [], 0
    while True:
        i = buf.find(SIG, pos)
        if i < 0:
            break
        p, ok, w, h = i + 8, False, 0, 0
        while p + 12 <= len(buf):
            n, t = struct.unpack(">I4s", buf[p:p + 8])
            body = buf[p + 8:p + 8 + n]
            crc = struct.unpack(">I", buf[p + 8 + n:p + 12 + n])[0]
            if zlib.crc32(t + body) & 0xffffffff != crc:
                break
            if t == b"IHDR":
                w, h = struct.unpack(">II", body[:8])
            p += 12 + n
            if t == b"IEND":
                ok = True
                break
        if ok:
            out.append({"off": i, "size": p - i, "w": w, "h": h, "sha256": hashlib.sha256(buf[i:p]).hexdigest()})
            pos = p
        else:
            pos = i + 8
    return out

if __name__ == "__main__":
    dll, outp = sys.argv[1:3]
    r = scan(open(dll, "rb").read())
    json.dump(r, open(outp, "w"), indent=1)
    print(f"png={len(r)} bytes={sum(x['size'] for x in r)}")
