#!/usr/bin/env python3
"""CAB-46: Inno Setup 6.4.2 (Team V.R repack) setup-0.bin header parser.

Extracts from the loader table of the NI Massive X 1.7.1 win installer:
  - loader offset table (OffsetEXE / Offset0 / Offset1)
  - setup-0.bin first block (decompress LZMA1-raw after de-chunking)
  - TSetupHeader strings/counts + entry tables (languages, messages, types,
    components, dirs, files, file location entries)
Outputs work/header_parse.json with the inventory-relevant fields.

Usage: python3 parse_setup_headers.py <installer.exe> <workdir>
"""
import json
import lzma
import os
import struct
import sys


def read_loader_table(f):
    """Find rDlPtS table (6.4.x packed u32 layout, Version=1)."""
    import re
    f.seek(0)
    prev = b""
    pos = 0
    hit = None
    while True:
        chunk = f.read(1 << 24)
        if not chunk:
            break
        buf = prev + chunk
        m = re.search(re.escape(b"rDlPtS\xcd\xe6\xd7{\x0b*"), buf)
        if m:
            hit = pos - len(prev) + m.start()
            break
        prev = buf[-64:]
        pos += len(chunk)
    if hit is None:
        raise RuntimeError("loader table not found")
    f.seek(hit)
    t = f.read(44)
    (_id, version, total_size, off_exe, unc_exe, crc_exe, off0, off1, table_crc) = \
        struct.unpack("<12sIIIIIIiI"[0:0] + "<12sIIIIIIIi", t[:44]) if False else \
        struct.unpack("<12sIIIIIIIi", t[:44])
    return dict(table_off=hit, version=version, total_size=total_size,
                off_exe=off_exe, unc_exe=unc_exe, off0=off0, off1=off1)


def dechunk(raw):
    """Strip per-4096B-chunk CRC32s (Inno compressed block payload)."""
    out = bytearray()
    i = 0
    n = len(raw)
    while i < n:
        take = min(4096, n - i - 4)
        if take <= 0:
            break
        out += raw[i + 4:i + 4 + take]
        i += 4 + take
    return bytes(out)


def read_setup0_block(f, off0):
    f.seek(off0)
    d = f.read(64 + 9 + (1 << 21))
    block_off = off0 + 64
    ss, = struct.unpack_from("<I", d, 68)
    comp = d[72]
    raw = d[73:73 + ss]
    payload = dechunk(raw)
    props = payload[0]
    pb, rem = divmod(props, 45)
    lp, lc = divmod(rem, 9)
    dict_size, = struct.unpack_from("<I", payload, 1)
    dec = lzma.LZMADecompressor(
        format=lzma.FORMAT_RAW,
        filters=[{"id": lzma.FILTER_LZMA1, "pb": pb, "lp": lp, "lc": lc,
                  "dict_size": dict_size}])
    data = dec.decompress(payload[5:])
    return dict(block_off=block_off, stored_size=ss, compressed=comp,
                props=props, dict_size=dict_size, data=data)


class Cursor:
    def __init__(self, data, off=0):
        self.d = data
        self.off = off

    def u32(self):
        v, = struct.unpack_from("<I", self.d, self.off); self.off += 4; return v

    def i32(self):
        v, = struct.unpack_from("<i", self.d, self.off); self.off += 4; return v

    def i64(self):
        v, = struct.unpack_from("<q", self.d, self.off); self.off += 8; return v

    def u16(self):
        v, = struct.unpack_from("<H", self.d, self.off); self.off += 2; return v

    def i16(self):
        v, = struct.unpack_from("<h", self.d, self.off); self.off += 2; return v

    def u8(self):
        v = self.d[self.off]; self.off += 1; return v

    def raw(self, n):
        v = self.d[self.off:self.off + n]; self.off += n; return v

    def s16(self):
        n = self.u32()
        v = self.d[self.off:self.off + n].decode("utf-16le", "replace")
        self.off += n
        return v

    def s8(self):
        n = self.u32()
        v = self.d[self.off:self.off + n]
        self.off += n
        return v

    def verdata(self):
        return (self.u32(), self.u32(), self.u16())


def parse_header_head(block):
    """strings (33 wstr + 4 astr) + 16 count integers, SE layout (strings first)."""
    c = Cursor(block)
    names = ["AppName", "AppVerName", "AppId", "AppCopyright", "AppPublisher",
             "AppPublisherURL", "AppSupportPhone", "AppSupportURL", "AppUpdatesURL",
             "AppVersion", "DefaultDirName", "DefaultGroupName", "BaseFilename",
             "UninstallFilesDir", "UninstallDisplayName", "UninstallDisplayIcon",
             "AppMutex", "DefaultUserInfoName", "DefaultUserInfoOrg",
             "DefaultUserInfoSerial", "AppReadmeFile", "AppContact", "AppComments",
             "AppModifyPath", "CreateUninstallRegKey", "Uninstallable",
             "CloseApplicationsFilter", "SetupMutex", "ChangesEnvironment",
             "ChangesAssociations", "ArchitecturesAllowed",
             "ArchitecturesInstallIn64BitMode", "CloseApplicationsFilterExcludes"]
    strs = {}
    for nm in names:
        strs[nm] = c.s16()
    for nm in ["LicenseText", "InfoBeforeText", "InfoAfterText", "CompiledCodeText"]:
        c.s8()
    cnt_names = ["Language", "CustomMessage", "Permission", "Type", "Component",
                 "Task", "Dir", "File", "FileLocation", "Icon", "Ini", "Registry",
                 "InstallDelete", "UninstallDelete", "Run", "UninstallRun"]
    counts = {}
    for nm in cnt_names:
        counts[nm] = c.i32()
    return strs, counts, c.off


def find_languages_start(block, after):
    """The repacked header carries ~48 unaccounted bytes in the fixed-field tail,
    so the language-entry start is located by pattern instead of by struct walk."""
    import re
    pat = struct.pack("<I", 14) + "english".encode("utf-16le")
    m = re.compile(re.escape(pat)).search(block, after)
    if not m:
        raise RuntimeError("language entry anchor not found")
    return m.start()


def parse(block, counts, lang_start):
    c = Cursor(block, lang_start)
    H = {}
    # language entries: 6 wstr + 4 astr + u32 + 4xi32 + u8
    langs = []
    for i in range(counts["Language"]):
        e = [c.s16() for _ in range(6)]
        for _ in range(4):
            c.s8()
        lid = c.u32()
        sizes = (c.i32(), c.i32(), c.i32(), c.i32())
        rtl = c.u8()
        langs.append({"name": e[0], "langname": e[1], "id": lid})
    H["languages"] = langs

    # custom messages: 2 wstr + i32
    msgs = []
    for i in range(counts["CustomMessage"]):
        n = c.s16(); v = c.s16(); li = c.i32()
        msgs.append((n, v, li))
    H["num_custom_messages_parsed"] = len(msgs)

    # permissions: 0 strings + 1 ansi (count is 0 here, skip generically)
    for i in range(counts["Permission"]):
        c.s8()

    # types: 4 wstr + verdata x2 + u8 + u8 + i64
    types = []
    for i in range(counts["Type"]):
        nm = c.s16(); desc = c.s16(); c.s16(); c.s16()
        c.verdata(); c.verdata()
        opts = c.u8(); typ = c.u8(); size = c.i64()
        types.append((nm, desc, opts, typ, size))
    H["types"] = types

    # components: 5 wstr + i64 + i32 + u8 + verdata x2 + u8 + i64
    comps = []
    for i in range(counts["Component"]):
        nm = c.s16(); desc = c.s16(); c.s16(); c.s16(); c.s16()
        ed = c.i64(); lvl = c.i32(); used = c.u8()
        c.verdata(); c.verdata()
        opts = c.u8(); size = c.i64()
        comps.append((nm, lvl, size))
    H["components"] = comps

    # tasks: 6 wstr + verdata x2 + u8 + u8 + i64 (count 0 here, keep generic)
    for i in range(counts["Task"]):
        for _ in range(6):
            c.s16()
        c.verdata(); c.verdata()
        c.u8(); c.u8(); c.i64()

    # dirs: 7 wstr + i32 + verdata x2 + i16 + u8
    dirs = []
    for i in range(counts["Dir"]):
        dn = c.s16()
        for _ in range(6):
            c.s16()
        c.i32(); c.verdata(); c.verdata(); c.i16(); c.u8()
        dirs.append(dn)
    H["dirs"] = dirs

    # files: 10 wstr + verdata x2 + i32 + i32 + i64 + i16 + u32 + u8
    files = []
    for i in range(counts["File"]):
        src = c.s16(); dst = c.s16()
        for _ in range(2):
            c.s16()
        comps = c.s16()
        for _ in range(5):
            c.s16()
        c.verdata(); c.verdata()
        loc = c.i32(); attribs = c.i32(); esz = c.i64()
        c.i16(); c.u32(); ft = c.u8()
        files.append({"src": src, "dst": dst, "comps": comps, "loc": loc,
                      "size": esz})
    H["files"] = files

    # icons: 13 wstr + GUID(16) + verdata x2 + i32 + i32 + u8 + u16 + u32
    for i in range(counts["Icon"]):
        for _ in range(13):
            c.s16()
        c.raw(16)
        c.verdata(); c.verdata()
        c.i32(); c.i32(); c.u8(); c.u16(); c.u32()

    # ini: 10 wstr + verdata x2 + u8
    for i in range(counts["Ini"]):
        for _ in range(10):
            c.s16()
        c.verdata(); c.verdata()
        c.u8()

    # registry: 9 wstr + verdata x2 + u32 + i16 + u8 + u16
    reg = []
    for i in range(counts["Registry"]):
        vals = [c.s16() for _ in range(9)]
        c.verdata(); c.verdata()
        root = c.u32(); c.i16(); typ = c.u8(); c.u16()
        reg.append(vals)
    H["registry_sample"] = reg[:3]

    # installdelete / uninstalldelete: 7 wstr + verdata x2 + u8
    for cnt in ("InstallDelete", "UninstallDelete"):
        for i in range(counts[cnt]):
            for _ in range(7):
                c.s16()
            c.verdata(); c.verdata()
            c.u8()

    # run: 13 wstr + verdata x2 + i32 + u8 + u16
    runs = []
    for i in range(counts["Run"]):
        vals = [c.s16() for _ in range(13)]
        c.verdata(); c.verdata()
        sc = c.i32(); w = c.u8(); c.u16()
        runs.append(vals)
    H["runs"] = runs
    for i in range(counts["UninstallRun"]):
        for _ in range(13):
            c.s16()
        c.verdata(); c.verdata()
        c.i32(); c.u8(); c.u16()

    H["block1_end_off"] = c.off
    return H


def parse_locations(block, count):
    """Block 2 of setup-0.bin: TSetupFileLocationEntry entries.

    This repacked 6.4.2 installer stores 71 bytes per entry
    (16B checksum instead of the stock SHA256; fields verified empirically):
      i32 first, i32 last, i32 start, i64 csub, i64 osz, i64 csz,
      16B checksum, i64 timestamp, u32 verMS, u32 verLS, u16 flags, u8 sign
    """
    c = Cursor(block)
    locs = []
    bad = 0
    for i in range(count):
        first = c.i32(); last = c.i32(); start = c.i32()
        csub = c.i64(); osz = c.i64(); csz = c.i64()
        sha = c.raw(16)
        ts = c.i64()
        fvm = c.u32(); fvl = c.u32()
        flags = c.u16()
        sign = c.u8()
        ok = (0 <= first <= 9) and (0 <= last <= 9) and (0 <= start < (1 << 31)
              and 0 <= csub and 0 <= osz <= (1 << 31) and 0 <= csz <= (1 << 32)
              and sign <= 3)
        if not ok:
            bad += 1
        locs.append({"idx": i, "first": first, "last": last, "start": start,
                     "csub": csub, "osz": osz, "csz": csz, "flags": flags,
                     "sha16": sha.hex()})
    return locs, bad, c.off


def read_block(f, off):
    """Read one TCompressedBlockReader block starting at file offset `off`
    (the [HdrCRC][StoredSize][Compressed] header), return decompressed bytes."""
    f.seek(off)
    hdr = f.read(9)
    ss, comp = struct.unpack_from("<IB", hdr, 4)
    raw = f.read(ss)
    payload = dechunk(raw)
    props = payload[0]
    pb, rem = divmod(props, 45)
    lp, lc = divmod(rem, 9)
    dict_size, = struct.unpack_from("<I", payload, 1)
    dec = lzma.LZMADecompressor(
        format=lzma.FORMAT_RAW,
        filters=[{"id": lzma.FILTER_LZMA1, "pb": pb, "lp": lp, "lc": lc,
                  "dict_size": dict_size}])
    data = dec.decompress(payload[5:])
    return data, off + 9 + ss


def main():
    installer, workdir = sys.argv[1], sys.argv[2]
    os.makedirs(workdir, exist_ok=True)
    with open(installer, "rb") as f:
        tbl = read_loader_table(f)
        print("loader table:", tbl)
        blk1, next_off = read_block(f, tbl["off0"] + 64)
        print("setup-0 block1 @%#x -> %d bytes" % (tbl["off0"] + 64, len(blk1)))
        open(os.path.join(workdir, "hdr_block1.bin"), "wb").write(blk1)
        strs, counts, head_end = parse_header_head(blk1)
        lang_start = find_languages_start(blk1, head_end)
        print("header head ends @%d, languages start @%d (tail=%d B)"
              % (head_end, lang_start, lang_start - head_end))
        H = parse(blk1, counts, lang_start)
        H["strings"] = strs
        H["counts"] = counts
        print("block1 entries end_off=%d total=%d" % (H["block1_end_off"], len(blk1)))
        s = H["strings"]
        print("App:", s["AppName"], s["AppVersion"], "/", s["AppPublisher"])
        print("DefaultDirName:", s["DefaultDirName"])
        print("counts:", H["counts"])
        # block 2 = file location entries
        blk2, next2 = read_block(f, next_off)
        print("setup-0 block2 @%#x -> %d bytes (next @%#x)" % (next_off, len(blk2), next2))
        locs, bad, lend = parse_locations(blk2, counts["FileLocation"])
        print("locations: %d parsed, %d bad, consumed %d of %d"
              % (len(locs), bad, lend, len(blk2)))
        H["locations"] = locs
        tot_orig = sum(l["osz"] for l in locs)
        print("location total original: %d (%.3f GB)" % (tot_orig, tot_orig / 1e9))
        out = {k: v for k, v in H.items() if k not in ("files", "locations")}
        out["files"] = H["files"][:400] + ["...(%d total)" % len(H["files"])]
        out["locations_first10"] = locs[:10]
        out["location_total_original"] = tot_orig
        with open(os.path.join(workdir, "header_parse.json"), "w") as jf:
            json.dump(out, jf, ensure_ascii=False, indent=1, default=str)
        # full dumps for extraction step
        with open(os.path.join(workdir, "files.json"), "w") as jf:
            json.dump(H["files"], jf, ensure_ascii=False)
        with open(os.path.join(workdir, "locations.json"), "w") as jf:
            json.dump(locs, jf, ensure_ascii=False)


if __name__ == "__main__":
    main()
