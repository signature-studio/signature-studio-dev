#!/usr/bin/env python3
"""検収の独立再計算 (規則 37・40) — libm 非依存 PCM 自前生成 + MD5/CRC による検算。

検証ハーネス (test_flac.c / test_ffmpeg.c) は FNV-1a hash の一致で合否を決めている。
本スクリプトは **別アルゴリズム** で同じ結論を出せるかを検算する:

  (1) 入力 PCM を resonator 漸化式 (test_flac.c の gen_pcm と同一式・libm 非依存) で
      **自前生成**し、libFLAC が STREAMINFO に書いた **MD5 (RFC1321, 別実装)** と
      照合する。= エンコード→復号の可逆性を MD5 で独立検証。
      (harness は libFLAC 組み込み MD5 を errors=0 で確認しているが、ここでは
       Python の hashlib と自前生成 PCM で独立に検算する)
  (2) 自前で CRC-8 (poly 0x07) / CRC-16 (poly 0x8005) を実装し、FLAC の
      frame header CRC と frame CRC を検算する。= ファイル構造・frame 境界の独立確認
  (3) 自前 RIFF/WAV パーサで gen.wav の data payload を読み、FVN-1a (test_ffmpeg.c と
      同一定義) を計算して FFmpeg pcm_s16le 復号 hash と照合する
  (4) 自前 MPEG audio frame header パーサで out.mp3 の frame 数/バイト数を検算
  (5) 自前 WavPack block header パーサで .wv の構造を検算
  (6) ネガティブコントロール (規則 41): 1B 反転 → CRC-16 不一致 / MD5 不一致を検出

数え方の定義 (規則 36):
- PCM: 22050 個の int32 (L,R インターリーブ)。pcm[2k]=L[k], pcm[2k+1]=R[k]
- MD5 入力: 各サンプルを (bps+7)/8 = 3 バイト little-endian にパックした
  22050*3 = 66150 バイト (libFLAC の FLAC__MD5Accumulate と同じ定義)
- CRC-16: poly x^16+x^15+x^2+1 (0x8005), init 0, MSB first, 反射なし。
  対象 = frame 先頭 (sync を含む) から CRC-16 フィールドの直前まで
- CRC-8: poly x^8+x^2+x+1 (0x07), init 0。対象 = frame header 全域 (CRC-8 の前まで)
"""
import sys, struct, hashlib, os

# ------------------------------------------------------------------ CRC (自前実装)
def crc8(data, crc=0):
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if (crc & 0x80) else ((crc << 1) & 0xFF)
    return crc

def crc16(data, crc=0):
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = (((crc << 1) & 0xFFFF) ^ 0x8005) if (crc & 0x8000) else ((crc << 1) & 0xFFFF)
    return crc

def fnv(b, h=1469598103934665603):
    for c in b:
        h ^= c
        h = (h * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return h

# ------------------------------------------------------------------ 入力 PCM (自前生成)
def gen_pcm(n):
    """test_flac.c の gen_pcm() と同一 (共振器漸化式 + xorshift64 LCG・libm 非依存)"""
    x1, x2, y = 0.037, -0.021, 0.0
    s = 88172645463325252
    out = []
    for _ in range(n):
        s ^= (s << 13) & 0xFFFFFFFFFFFFFFFF
        s ^= s >> 7
        s ^= (s << 17) & 0xFFFFFFFFFFFFFFFF
        xn = ((s >> 40) / 16777216.0) * 2.0 - 1.0
        y = 0.9821 * y - 0.0179 * x1 + 0.0007 * x2 + xn * 0.31
        x2 = x1
        x1 = xn
        v = y * 4000000.0
        if v > 8388607.0:
            v = 8388607.0
        if v < -8388608.0:
            v = -8388608.0
        out.append(int(v))
    return out

def pcm_md5(pcm, bytes_per_sample=3, channels=2):
    """libFLAC FLAC__MD5Accumulate と同じ little-endian インターリーブ packing"""
    b = bytearray()
    for i in range(len(pcm) // channels):
        for c in range(channels):
            v = pcm[i * channels + c] & ((1 << (bytes_per_sample * 8)) - 1)
            for k in range(bytes_per_sample):
                b.append((v >> (8 * k)) & 0xFF)
    return hashlib.md5(bytes(b)).digest()

# ------------------------------------------------------------------ WAV (自前 RIFF パーサ)
def parse_wav(path):
    d = open(path, "rb").read()
    assert d[0:4] == b"RIFF" and d[8:12] == b"WAVE", "not RIFF/WAVE"
    pos = 12
    chunks = {}
    while pos + 8 <= len(d):
        cid = d[pos:pos + 4]
        sz = struct.unpack("<I", d[pos + 4:pos + 8])[0]
        body = d[pos + 8: pos + 8 + sz]
        chunks.setdefault(cid, body)
        pos += 8 + sz + (sz & 1)
    fmt = chunks[b"fmt "]
    af, ch, rate, byterate, align, bits = struct.unpack("<HHIIHH", fmt[:16])
    return dict(audio_format=af, channels=ch, rate=rate, bits=bits,
                data=chunks.get(b"data", b""), total=len(d))

# ------------------------------------------------------------------ MP3 (自前 frame header パーサ)
MPEG_BITRATE_V1L3 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
MPEG_SR = {3: [44100, 48000, 32000, 0]}

def parse_mp3(path):
    d = open(path, "rb").read()
    frames = []
    i = 0
    while i + 4 <= len(d):
        if d[i] != 0xFF or (d[i + 1] & 0xE0) != 0xE0:
            i += 1
            continue
        ver = (d[i + 1] >> 3) & 3
        layer = (d[i + 1] >> 1) & 3
        br_idx = (d[i + 2] >> 4) & 0xF
        sr_idx = (d[i + 2] >> 2) & 3
        pad = (d[i + 2] >> 1) & 1
        chmode = (d[i + 3] >> 6) & 3
        if layer != 1 or br_idx == 0 or br_idx == 15 or sr_idx == 3:
            i += 1
            continue
        br = MPEG_BITRATE_V1L3[br_idx] * 1000
        sr = 44100
        flen = 144 * br // sr + pad
        if flen < 4:
            i += 1
            continue
        # 自分が計算した frame 長の先が sync でなければ偽 sync → 1 byte ずらして再探索
        if i + flen + 4 > len(d):
            i += 1
            continue
        if frames and not (d[i + flen] == 0xFF and (d[i + flen + 1] & 0xE0) == 0xE0):
            i += 1
            continue
        frames.append((i, flen, br, sr, chmode))
        i += flen
    total = sum(f[1] for f in frames)
    return frames, total, len(d)

# ------------------------------------------------------------------ WavPack (自前 header パーサ)
WVPACK_SRATES = [6000, 8000, 9600, 11025, 12000, 16000, 22050, 24000, 32000,
                44100, 48000, 64000, 88200, 96000, 192000, None]

def parse_wv(path):
    """WavPackHeader (wavpack.h, WavpackHeaderFormat "4LS2LLLLL", 32 byte):
       ckID(4) ckSize(4) version(2) track_no(1) index_no(1)
       total_samples(4) block_index(4) block_samples(4) flags(4) crc(4)"""
    d = open(path, "rb").read()
    assert d[0:4] == b"wvpk", "not wvpk"
    offs = []
    i = 0
    while i + 32 <= len(d) and d[i:i + 4] == b"wvpk":
        offs.append(i)
        cs = int.from_bytes(d[i + 4:i + 8], "little")
        i += 8 + cs
    hdrs = []
    for o in offs:
        cs = int.from_bytes(d[o + 4:o + 8], "little")
        ver = int.from_bytes(d[o + 8:o + 10], "little")
        total = int.from_bytes(d[o + 12:o + 16], "little")
        bidx = int.from_bytes(d[o + 16:o + 20], "little")
        bsmp = int.from_bytes(d[o + 20:o + 24], "little")
        fl = int.from_bytes(d[o + 24:o + 28], "little")
        hdrs.append(dict(off=o, ck_size=cs, version=ver, total_samples=total,
                         block_index=bidx, block_samples=bsmp,
                         bytes_per_sample=(fl & 3) + 1,
                         srate=WVPACK_SRATES[(fl >> 23) & 0xF],
                         initial=bool(fl & 0x800), final=bool(fl & 0x1000)))
    return dict(block_count=len(hdrs), blocks=hdrs,
                covered=sum(8 + h["ck_size"] for h in hdrs), file_size=len(d))

# ------------------------------------------------------------------ FLAC 構造検証
def utf8_vlc_len(b0):
    if b0 & 0x80 == 0:
        return 1
    if b0 & 0xE0 == 0xC0:
        return 2
    if b0 & 0xF0 == 0xE0:
        return 3
    if b0 & 0xF8 == 0xF0:
        return 4
    if b0 & 0xFC == 0xF8:
        return 5
    if b0 & 0xFE == 0xFC:
        return 6
    raise ValueError("bad utf8")

def verify_flac(path, ref_pcm=None):
    d = open(path, "rb").read()
    assert d[:4] == b"fLaC"
    out = {"size": len(d), "file_fnv": "%016x" % fnv(d)}
    # metadata
    pos = 4
    md5_stored = None
    while True:
        h = d[pos]; pos += 1
        last = h >> 7; mtype = h & 0x7F
        ln = int.from_bytes(d[pos:pos + 3], "big"); pos += 3
        if mtype == 0:
            md5_stored = d[pos + 18:pos + 34]
            out["streaminfo"] = dict(
                minblk=int.from_bytes(d[pos:pos + 2], "big"),
                maxblk=int.from_bytes(d[pos + 2:pos + 4], "big"),
                rate=(d[pos + 10] << 12) | (d[pos + 11] << 4) | (d[pos + 12] >> 4),
                ch=((d[pos + 12] >> 1) & 7) + 1,
                bps=(((d[pos + 12] & 1) << 4) | (d[pos + 13] >> 4)) + 1,
                total=(d[pos + 13] & 0x0F) << 32 | int.from_bytes(d[pos + 14:pos + 18], "big"))
        pos += ln
        if last:
            break
    out["md5_stored"] = md5_stored.hex() if md5_stored else None
    # audio frames: 有効な frame header (frame 番号が連番) だけを採用して自前 CRC を検算する
    frames = []
    i = pos
    n = 0
    while i < len(d):
        start = None
        j = i
        while j < len(d) - 6:
            if d[j] == 0xFF and (d[j + 1] & 0xFC) == 0xF8 and (d[j + 3] & 1) == 0:
                bsb_t = d[j + 2] >> 4
                srb_t = d[j + 2] & 0x0F
                ca_t = d[j + 3] >> 4
                ssb_t = (d[j + 3] >> 1) & 7
                if srb_t <= 14 and ca_t <= 10 and ssb_t <= 6:
                    try:
                        vlen = utf8_vlc_len(d[j + 4])
                    except ValueError:
                        j += 1
                        continue
                    if j + 4 + vlen > len(d):
                        j += 1
                        continue
                    fn = 0
                    for k in range(vlen):
                        c = d[j + 4 + k]
                        fn = (fn << 6) | (c & (0xFF >> (1 + vlen) if k == 0 else 0x7F))
                    if fn == n:
                        start = j
                        break
            j += 1
        if start is None:
            break
        i = start
        vlen = utf8_vlc_len(d[i + 4])
        bsb = d[i + 2] >> 4
        srb = d[i + 2] & 0x0F
        ca = d[i + 3] >> 4
        ssb = (d[i + 3] >> 1) & 7
        hend = i + 4 + vlen
        if bsb == 6:
            hend += 1
        elif bsb == 7:
            hend += 2
        if srb in (12, 13, 14):
            hend += 1 if srb == 12 else 2
        stored_crc8 = d[hend]
        crc8_chk = crc8(d[i:hend])
        # frame 境界 = 次に「連番 frame 番号を持つ有効な sync」。偽 sync では切らない
        nxt = len(d)
        k = i + 1
        while k < len(d) - 6:
            if d[k] == 0xFF and (d[k + 1] & 0xFC) == 0xF8 and (d[k + 3] & 1) == 0:
                if (d[k + 2] & 0x0F) <= 14 and (d[k + 3] >> 4) <= 10 and ((d[k + 3] >> 1) & 7) <= 6:
                    try:
                        vl2 = utf8_vlc_len(d[k + 4])
                    except ValueError:
                        k += 1
                        continue
                    if k + 4 + vl2 <= len(d):
                        fn2 = 0
                        for t in range(vl2):
                            c = d[k + 4 + t]
                            fn2 = (fn2 << 6) | (c & (0xFF >> (1 + vl2) if t == 0 else 0x7F))
                        if fn2 == n + 1:
                            nxt = k
                            break
            k += 1
        c16 = crc16(d[i:nxt - 2])
        frames.append(dict(off=i, end=nxt,
                           crc8_ok=(crc8_chk == stored_crc8),
                           crc8_calc="%02x" % crc8_chk, crc8_stored="%02x" % stored_crc8,
                           bsb=bsb, srb=srb, ca=ca, ssb=ssb,
                           crc16_ok=(c16 == int.from_bytes(d[nxt - 2:nxt], "big")),
                           crc16_calc="%04x" % c16, crc16_stored=d[nxt - 2:nxt].hex()))
        i = nxt
        n += 1
    out["frames"] = frames
    out["crc8_all_ok"] = all(f["crc8_ok"] for f in frames)
    out["crc16_all_ok"] = all(f["crc16_ok"] for f in frames)
    out["last_frame_end"] = frames[-1]["end"] if frames else None
    if ref_pcm is not None:
        out["md5_self"] = pcm_md5(ref_pcm).hex()
    return out

# ------------------------------------------------------------------ main
def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    flacs, waves, mp3s, wvs = [], [], [], []
    for a in args:
        if a.endswith(".flac"):
            flacs.append(a)
        elif a.endswith(".wav"):
            waves.append(a)
        elif a.endswith(".mp3"):
            mp3s.append(a)
        elif a.endswith(".wv"):
            wvs.append(a)
    allok = True
    ref = gen_pcm(22050)
    print("[indep] self-generated reference PCM: 22050 samples (2ch x 11025)")
    print("[indep] self PCM MD5 (3B LE packed, libFLAC MD5Accumulate definition) = %s" % pcm_md5(ref).hex())

    for p in flacs:
        neg = "bad-" in os.path.basename(p)
        print("\n=== FLAC %s ===" % p + ("   [negative control: 検出を期待]" if neg else ""))
        r = verify_flac(p, ref)
        si = r.get("streaminfo") or {}
        print("[indep] size=%d FNV(file)=%s" % (r["size"], r["file_fnv"]))
        print("[indep] STREAMINFO rate=%d ch=%d bps=%d total=%d minblk=%s maxblk=%s"
              % (si.get("rate", 0), si.get("ch", 0), si.get("bps", 0), si.get("total", 0),
                 si.get("minblk"), si.get("maxblk")))
        print("[indep] MD5 stored in STREAMINFO      = %s" % r["md5_stored"])
        print("[indep] MD5 of self-generated PCM     = %s" % r["md5_self"])
        ok_md5 = (r["md5_stored"] == r["md5_self"])
        print("[indep] %s  <- encode->decode reversibility, independent MD5"
              % ("PASS" if ok_md5 else "FAIL"))
        ca = {}
        for f in r["frames"]:
            ca[f["ca"]] = ca.get(f["ca"], 0) + 1
        print("[indep] frames=%d  crc8_all=%s crc16_all=%s  last_frame_end=%d (file %d)"
              % (len(r["frames"]), r["crc8_all_ok"], r["crc16_all_ok"], r["last_frame_end"], r["size"]))
        print("[indep] channel_assignment histogram = %s  (8=L/S,9=R/S,10=M/S,<8=independent)"
              % dict(sorted(ca.items())))
        print("[indep] frame offsets = %s" % [f["off"] for f in r["frames"]])
        ok = ok_md5 and r["crc8_all_ok"] and r["crc16_all_ok"] and (r["last_frame_end"] == r["size"])
        if neg:
            # ネガティブコントロール: 破損が CRC で検出されること (正常ファイルでは全 CRC が一致)
            detected = (not r["crc16_all_ok"]) or (not r["crc8_all_ok"]) or (r["md5_stored"] != r["md5_self"])
            print("[indep] %s  <- 1B 破損を自前 CRC/MD5 で検出" % ("PASS (caught)" if detected else "FAIL (missed)"))
            allok = allok and detected
        else:
            print("[indep] %s" % ("PASS" if ok else "FAIL"))
            allok = allok and ok

    for p in waves:
        print("\n=== WAV %s ===" % p)
        w = parse_wav(p)
        h = fnv(w["data"])
        print("[indep] RIFF parse: fmt=%d ch=%d rate=%d bits=%d data=%dB total=%dB"
              % (w["audio_format"], w["channels"], w["rate"], w["bits"], len(w["data"]), w["total"]))
        print("[indep] FNV-1a over data payload = %016x" % h)
        for expect in args_exp:
            if expect[0] == p:
                ok = ("%016x" % h) == expect[1]
                print("[indep] expected (FFmpeg pcm decode hash) = %s -> %s"
                      % (expect[1], "PASS" if ok else "FAIL"))
                allok = allok and ok
                break

    for p in mp3s:
        print("\n=== MP3 %s ===" % p)
        fr, total, size = parse_mp3(p)
        brs = sorted(set(f[2] for f in fr))
        chm = {}
        for f in fr:
            chm[f[4]] = chm.get(f[4], 0) + 1
        print("[indep] frames=%d payload_bytes=%d file_bytes=%d (residual=%d)"
              % (len(fr), total, size, size - total))
        print("[indep] bitrates=%s channel_modes=%s (0=stereo,1=joint,2=dual,3=mono)"
              % (brs, chm))

    for p in wvs:
        print("\n=== WavPack %s ===" % p)
        v = parse_wv(p)
        print("[indep] blocks=%d covered=%d bytes of file %d (%s)"
              % (v["block_count"], v["covered"], v["file_size"],
                 "OK" if v["covered"] == v["file_size"] else "MISMATCH"))
        for b in v["blocks"]:
            print("[indep]   block @%-7d ckSize=%-6d ver=0x%04x total_samples=%d block_index=%d block_samples=%d bytes/sample=%d srate=%s %s%s"
                  % (b["off"], b["ck_size"], b["version"], b["total_samples"], b["block_index"],
                     b["block_samples"], b["bytes_per_sample"], b["srate"],
                     "INITIAL " if b["initial"] else "", "FINAL" if b["final"] else ""))

    print("\n[indep] overall: %s" % ("PASS" if allok else "FAIL"))
    return 0 if allok else 1

args_exp = []
if __name__ == "__main__":
    # --expect <path> <hash> で FNV 期待値 (FFmpeg pcm decode hash) を渡す
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a == "--expect":
            args_exp.append((argv[i + 1], argv[i + 2]))
            argv[i] = argv[i + 1] = argv[i + 2] = "--"
    sys.argv = [sys.argv[0]] + argv
    sys.exit(main())
