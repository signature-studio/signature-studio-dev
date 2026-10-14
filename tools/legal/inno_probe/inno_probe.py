#!/usr/bin/env python3
"""Inno Setup 6.4.x インストーラの setup-0 を読み、文書の同梱有無を調べる (LGL-10, #2498)。

使い方: python3 inno_probe.py <installer.exe> [header_out.bin]

- オフセット表 (ID `rDlPtS`、TSetupLdrOffsetTable) を exe 内から探し、TableCRC を検査する。
- setup-0 (Offset0) の SetupID・ブロックヘッダ・チャンクを読む。CRC は検査して結果を出すが、
  不一致でも復号は続ける (LZMA1 の終端まで読めるかを見る)。
- 復号したヘッダブロックから、長さ接頭辞の UTF-16LE / ASCII 文字列を拾い、文書系の名前と
  長い本文ブロックを数える。結果は JSON で標準出力に出す。
- 形式の根拠: jrsoftware/issrc tag is-6_4_2 の Shared.Struct.pas (TSetupLdrOffsetTable・SetupID)、
  Compression.Base.pas (TCompressedBlockWriter/Reader: 9 バイトのブロックヘッダ、4096 B 単位のチャンク CRC)、
  Compression.LZMADecompressor.pas (TLZMA1Decompressor: 先頭 5 バイトが props)。
"""
import json
import lzma
import mmap
import re
import struct
import sys
import zlib

TABLE_ID = b"rDlPtS\xcd\xe6\xd7\x7b\x0b\x2a"
TABLE_FMT = "<12sIIIIiIII"
SETUP_ID_PREFIX = b"Inno Setup Setup Data (6."
CHUNK_SIZE = 4096
DOC_NAME = re.compile(r"(?i)eula|licen[cs]e|agreement|readme|terms")
DOC_EXT = re.compile(r"(?i)\.(rtf|pdf|htm|html|doc|docx|md|nfo|chm)$")
UTF16_RUN = re.compile(rb"(?:[\x20-\x7e]\x00){3,}")
ASCII_RUN = re.compile(rb"[\x20-\x7e]{3,}")
TEXT16_BLOB = re.compile(rb"(?:[\x09\x0a\x0d\x20-\x7e]\x00){40,}")


def crc32(buf):
    return zlib.crc32(buf) & 0xFFFFFFFF


def read_offset_table(mm):
    i = mm.find(TABLE_ID)
    if i < 0 or mm.find(TABLE_ID, i + 1) >= 0:
        raise SystemExit("offset table ID not found exactly once")
    size = struct.calcsize(TABLE_FMT)
    fields = struct.unpack_from(TABLE_FMT, mm, i)
    table = {
        "file_offset": i,
        "version": fields[1],
        "total_size": fields[2],
        "offset_exe": fields[3],
        "uncompressed_exe": fields[4],
        "crc_exe": fields[5] & 0xFFFFFFFF,
        "offset0": fields[6],
        "offset1": fields[7],
        "table_crc": fields[8] & 0xFFFFFFFF,
    }
    table["table_crc_computed"] = crc32(bytes(mm[i:i + size - 4]))
    table["table_crc_ok"] = table["table_crc_computed"] == table["table_crc"]
    table["total_size_ok"] = table["total_size"] == len(mm)
    return table


def read_setup0_payload(mm, off0):
    setup_id = bytes(mm[off0:off0 + 64]).rstrip(b"\0")
    if not setup_id.startswith(SETUP_ID_PREFIX):
        raise SystemExit("SetupID mismatch at offset0: %r" % setup_id)
    pos = off0 + 64
    hdr_crc, stored, compressed = struct.unpack_from("<IIB", mm, pos)
    block = {
        "setup_id": setup_id.decode("ascii"),
        "stored_size": stored,
        "compressed": bool(compressed),
        "block_header_crc": hdr_crc,
        "block_header_crc_computed": crc32(struct.pack("<IB", stored, compressed)),
    }
    block["block_header_crc_ok"] = block["block_header_crc_computed"] == hdr_crc
    pos += 9
    left = stored
    payload = bytearray()
    chunks = 0
    chunk_crc_bad = 0
    while left > 0:
        chunk_crc = struct.unpack_from("<I", mm, pos)[0]
        pos += 4
        n = min(left - 4, CHUNK_SIZE)
        data = bytes(mm[pos:pos + n])
        if crc32(data) != chunk_crc:
            chunk_crc_bad += 1
        payload += data
        pos += n
        left -= 4 + n
        chunks += 1
    block["chunks"] = chunks
    block["chunk_crc_mismatch"] = chunk_crc_bad
    return block, bytes(payload)


def lzma1_decode(payload):
    misc = payload[0]
    dict_size = struct.unpack_from("<I", payload, 1)[0]
    lc = misc % 9
    rest = misc // 9
    lp = rest % 5
    pb = rest // 5
    dec = lzma.LZMADecompressor(
        format=lzma.FORMAT_RAW,
        filters=[{"id": lzma.FILTER_LZMA1, "dict_size": dict_size, "lc": lc, "lp": lp, "pb": pb}],
    )
    out = dec.decompress(payload[5:])
    return out, {"lc": lc, "lp": lp, "pb": pb, "dict_size": dict_size, "eof": dec.eof}


def scan_header(data):
    names = set()
    ext_counts = {}
    for m in UTF16_RUN.finditer(data):
        s = m.group().decode("utf-16le")
        if DOC_NAME.search(s) or DOC_EXT.search(s):
            names.add(s[-160:])
    for m in ASCII_RUN.finditer(data):
        s = m.group().decode("ascii")
        if DOC_NAME.search(s) or DOC_EXT.search(s):
            names.add("(ascii) " + s[-160:])
    txt = 0
    for m in UTF16_RUN.finditer(data):
        s = m.group().decode("utf-16le")
        if re.search(r"(?i)\.txt$", s):
            txt += 1
    ext_counts["txt"] = txt
    blobs = []
    for m in TEXT16_BLOB.finditer(data):
        blobs.append(len(m.group()) // 2)
    blobs.sort(reverse=True)
    return {"doc_like": sorted(names), "txt_name_runs": ext_counts["txt"], "long_text_blobs_top": blobs[:5]}


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    exe = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else None
    with open(exe, "rb") as fh:
        mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        table = read_offset_table(mm)
        block, payload = read_setup0_payload(mm, table["offset0"])
        mm.close()
    header, props = lzma1_decode(payload)
    if out_path:
        with open(out_path, "wb") as fh:
            fh.write(header)
    result = {
        "exe_bytes": table["total_size"],
        "offset_table": table,
        "setup0_block": block,
        "lzma1": {**props, "decoded_bytes": len(header)},
        "header_scan": scan_header(header),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
