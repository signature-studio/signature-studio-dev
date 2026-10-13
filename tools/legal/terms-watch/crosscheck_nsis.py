"""別算法の検算: nsis.mjs / lib.mjs とは独立に (Python 標準ライブラリのみ) NSIS インストーラのライセンス文の正規化 SHA-256 を算出する。

  python3 tools/legal/terms-watch/crosscheck_nsis.py <installer.exe> [<license.txt>]

出力は `installer <sha256> <chars>` と、<license.txt> 指定時は `source <sha256> <chars>` (元テキストを同じ規則で正規化)。
対象は SF_TEXT 形式のライセンス文 (RTF は対象外)。両者と台帳 (docs/LEGAL_TERMS_LEDGER.json) の値が一致することを期待する。
"""
import hashlib
import re
import struct
import sys
import unicodedata
import zlib
from pathlib import Path


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = re.sub("[\u200b-\u200d\u2060\ufeff\u00ad]", "", s)
    s = re.sub("[\u2018\u2019\u201a\u201b\u02bc\u2032]", "'", s)
    s = re.sub("[\u201c-\u201f\u2033]", '"', s)
    s = re.sub("[\u2010-\u2015\u2212]", "-", s)
    return re.sub(r"\s+", " ", s).strip()


def license_texts(path: Path) -> list[str]:
    d = path.read_bytes()
    sig = bytes.fromhex("efbeadde") + b"NullsoftInst"
    pos = 0
    while True:
        i = d.find(sig, pos)
        assert i >= 4, "NSIS firstheader なし"
        if (i - 4) % 512 == 0:
            break
        pos = i + 1
    base = i - 4
    hdr_len, _following, word = struct.unpack_from("<iiI", d, base + 20)
    assert word & 0x80000000, "非圧縮ヘッダは未対応"
    hdr = zlib.decompress(d[base + 32 : base + 32 + (word & 0x7FFFFFFF)], -15)
    assert len(hdr) == hdr_len
    blocks = struct.unpack_from("<16i", hdr, 4)  # (offset, num) x 8
    strings_off, langtab_off = blocks[6], blocks[8]
    raw = hdr[strings_off:langtab_off].decode("utf-16-le", errors="replace")
    out = []
    for s in raw.split("\0"):
        if len(s) > 200 and s[0] in ("\x01", "\x11"):
            out.append(s[1:])
    return out


def main() -> int:
    texts = license_texts(Path(sys.argv[1]))
    for t in texts:
        n = normalize(t)
        print(f"installer {hashlib.sha256(n.encode()).hexdigest()} {len(n)}")
    if len(sys.argv) > 2:
        n = normalize(Path(sys.argv[2]).read_text(encoding="utf-8"))
        print(f"source {hashlib.sha256(n.encode()).hexdigest()} {len(n)}")
    return 0 if texts else 1


if __name__ == "__main__":
    sys.exit(main())
