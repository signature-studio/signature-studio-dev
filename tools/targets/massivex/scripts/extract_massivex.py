#!/usr/bin/env python3
"""CAB-46: extract selected files from the NI Massive X 1.7.1 (Team V.R repack)
win installer's single solid LZMA1 chunk.

The installer (Inno Setup 6.4.2 repack) stores the whole 2.337 GB payload as one
'zlb\\x1a' + raw-LZMA1 chunk at the data offset. We stream-decompress and carve
the selected files by (ChunkSuboffset, OriginalSize) from work/locations.json.

Usage: python3 extract_massivex.py <installer.exe> <workdir> [select]
  select = "key" (binaries + license data) or "small" (all files <= 4 MB)
"""
import hashlib
import json
import lzma
import os
import struct
import sys

from parse_setup_headers import read_loader_table


def main():
    installer, workdir = sys.argv[1], sys.argv[2]
    select = sys.argv[3] if len(sys.argv) > 3 else "key"
    files = json.load(open(os.path.join(workdir, "files.json")))
    locs = json.load(open(os.path.join(workdir, "locations.json")))
    with open(installer, "rb") as f:
        tbl = read_loader_table(f)
        data_off = tbl["off1"]

        def want(f_):
            if f_["loc"] < 0:
                return None
            l = locs[f_["loc"]]
            dst = f_["dst"]
            if select == "key":
                keys = ("Massive X.vst3", "Massive X.dll", "cputest.dll",
                        "Service Center", "Native Access", ".nicnt", ".jwt",
                        ".ini", ".mxc", ".meta")
                if not any(k in dst for k in keys):
                    return None
                if dst.endswith((".mxwt", ".nksf", ".ogg", ".wav")):
                    return None
            else:
                if l["osz"] > 4 * 1024 * 1024:
                    return None
            return l

        targets = []
        for f_ in files:
            l = want(f_)
            if l is None:
                continue
            # sanitize dst to a relative path
            dst = f_["dst"]
            for pfx in ("{code:GetDir|0}\\", "{code:GetDir|1}\\", "{cf}\\",
                        "{commondocs}\\", "{userdocs}\\", "{tmp}\\"):
                if dst.startswith(pfx):
                    dst = dst[len(pfx):]
            dst = dst.replace("{code:GetDir|0}", "GetDir0").replace(
                "{code:GetDir|1}", "GetDir1").replace("\\", "/")
            targets.append((l["csub"], l["osz"], dst, f_, l))
        targets.sort(key=lambda t: (t[0], t[1]))
        need_until = max(c + o for c, o, *_ in targets)
        print("selected %d files, decompressing up to %d bytes (%.2f GB)"
              % (len(targets), need_until, need_until / 1e9))

        f.seek(data_off)
        magic = f.read(4)
        assert magic == b"zlb\x1a", magic
        code = f.read(1)[0]
        # LZMA2 chunk: 1-byte dict-size code, then raw LZMA2 stream
        dict_size = (2 | (code & 1)) << (code // 2 + 11)
        dec = lzma.LZMADecompressor(
            format=lzma.FORMAT_RAW,
            filters=[{"id": lzma.FILTER_LZMA2, "dict_size": dict_size}])
        produced = 0            # stream offset of buf[0] (invariant!)
        buf = bytearray()
        outdir = os.path.join(workdir, "extracted")
        results = []
        pending = list(targets)
        CHUNK_IN = 4 << 20
        OUT_MAX = 8 << 20
        while pending and not dec.eof:
            if dec.needs_input:
                data = f.read(CHUNK_IN)
                if not data:
                    break
                block = dec.decompress(data, OUT_MAX)
            else:
                block = dec.decompress(b"", OUT_MAX)
            if not block:
                continue
            if not buf and pending and produced + len(block) < pending[0][0] - (32 << 20):
                # far from the next needed file and nothing buffered: safe skip
                produced += len(block)
                continue
            buf += block
            while pending and pending[0][0] + pending[0][1] <= produced + len(buf):
                c, o, dst, f_, l = pending.pop(0)
                blob = bytes(buf[c - produced:c - produced + o])
                path = os.path.join(outdir, dst)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as of:
                    of.write(blob)
                md5 = hashlib.md5(blob).hexdigest()
                ok = md5 == l["sha16"]
                results.append((dst, o, ok))
                if not ok:
                    print("  checksum mismatch %s md5=%s stored=%s"
                          % (dst, md5, l["sha16"]))
            if pending:
                drop = min(len(buf), max(0, pending[0][0] - produced))
            else:
                drop = len(buf)
            if drop:
                del buf[:drop]
                produced += drop
        produced += len(buf)
        print("decompressed %d bytes; extracted %d files, md5-ok %d/%d"
              % (produced, len(results),
                 sum(1 for r in results if r[2]), len(results)))
        print("decompressed %d bytes; extracted %d files, md5-ok %d/%d"
              % (produced, len(results),
                 sum(1 for r in results if r[2]), len(results)))
        with open(os.path.join(workdir, "extract_log.json"), "w") as jf:
            json.dump(results, jf, ensure_ascii=False, indent=0)


if __name__ == "__main__":
    main()
