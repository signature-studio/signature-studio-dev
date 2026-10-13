#!/usr/bin/env python3
"""Serum 2 session state payload codec (SR-1b, #255)。

payload = zstd 展開後の本体は **CBOR (RFC 8949)**。実測 (seed run の既定 Init state):
  - 最上位は map (processor: 0xb8 0xa4 = map/1B長/164 entries, controller: 0xb8 0x3b = 59 entries)
  - key は text string、辞書順 (bytewise) 昇順で書かれる
  - float は float32 (0xfa) で無損失なら 0xfa、でなければ 0xfb (= nlohmann::json::to_cbor の挙動。
    DLL に nlohmann json v3.12 の文字列あり。汎用 CBOR ライブラリは常に float64 化して不一致になる)
  - 0x1801bf1c0 (逆アセンブル): ver=2 は 0x1801bf480 (0x176e0 B ctx 確保 + cpuid BMI2 検査 = zstd 展開と推定, med)
    → 0x1801bfb00 で DOM 化。ver 0/1 は 0x180571dc0 → 0x1801bf5f0 (別経路, 未解析)。
    0x1801bfb00 / 0x1801bf5f0 のどちらが CBOR parser かは未特定 (本 codec は実測バイト一致で担保)
  - 最上位に meta JSON と同名のキー (component/product/productVersion/tags/version...) が重複して入る
コンテナ: u32 展開後長 + u32 版本(=2) + zstd(CBOR)。zstd 自体は SR-3 (#71) の OSS 境界で本 codec は libzstd 相当を使う。

本 codec は float 幅を保つため Float32 ラッパを使う。encode(decode(x)) == x (バイト一致) を seed で検証する。
"""
import struct


class Float32(float):
    """float32 (0xfa) として再エンコードされる値"""


def _head(major, n):
    if n < 24:
        return bytes([major << 5 | n])
    for ai, fmt in ((24, "B"), (25, ">H"), (26, ">I"), (27, ">Q")):
        if n < 1 << (8 * struct.calcsize(fmt)):
            return bytes([major << 5 | ai]) + struct.pack(fmt if fmt != "B" else ">B", n)
    raise ValueError(n)


def encode(o):
    if o is None:
        return b"\xf6"
    if o is False:
        return b"\xf4"
    if o is True:
        return b"\xf5"
    if isinstance(o, int):
        return _head(0, o) if o >= 0 else _head(1, -1 - o)
    if isinstance(o, float):
        # nlohmann::to_cbor 同様: float32 で無損失なら 0xfa、でなければ 0xfb
        if struct.unpack(">f", struct.pack(">f", o))[0] == o or o != o:
            return b"\xfa" + struct.pack(">f", o)
        return b"\xfb" + struct.pack(">d", o)
    if isinstance(o, str):
        b = o.encode()
        return _head(3, len(b)) + b
    if isinstance(o, bytes):
        return _head(2, len(o)) + o
    if isinstance(o, list):
        return _head(4, len(o)) + b"".join(encode(x) for x in o)
    if isinstance(o, dict):
        return _head(5, len(o)) + b"".join(encode(k) + encode(v) for k, v in o.items())
    raise TypeError(type(o))


def decode(d):
    o, i = _dec(d, 0)
    if i != len(d):
        raise ValueError(f"trailing {len(d) - i}B")
    return o


def _arg(d, i, ai):
    if ai < 24:
        return ai, i
    n = {24: 1, 25: 2, 26: 4, 27: 8}[ai]
    return int.from_bytes(d[i:i + n], "big"), i + n


def _dec(d, i):
    b = d[i]
    i += 1
    major, ai = b >> 5, b & 31
    if major == 7:
        if ai == 20: return False, i
        if ai == 21: return True, i
        if ai == 22: return None, i
        if ai == 26: return Float32(struct.unpack(">f", d[i:i + 4])[0]), i + 4
        if ai == 27: return struct.unpack(">d", d[i:i + 8])[0], i + 8
        raise ValueError(f"simple {ai}")
    n, i = _arg(d, i, ai)
    if major == 0: return n, i
    if major == 1: return -1 - n, i
    if major == 2: return d[i:i + n], i + n
    if major == 3: return d[i:i + n].decode(), i + n
    if major == 4:
        out = []
        for _ in range(n):
            x, i = _dec(d, i)
            out.append(x)
        return out, i
    if major == 5:
        out = {}
        for _ in range(n):
            k, i = _dec(d, i)
            v, i = _dec(d, i)
            out[k] = v
        return out, i
    raise ValueError(f"major {major}")


def _zstd(data, decompress):
    try:
        import zstandard
        z = zstandard.ZstdDecompressor() if decompress else zstandard.ZstdCompressor(level=3)
        return z.decompress(data, max_output_size=1 << 26) if decompress else z.compress(data)
    except ImportError:  # zstd CLI フォールバック (python モジュール無しの環境)
        import subprocess
        return subprocess.run(["zstd", "-q", "-c"] + (["-d"] if decompress else ["-3"]),
                              input=data, capture_output=True, check=True).stdout


def unpack_container(payload):
    """u32 展開後長 + u32 版本(=2) + zstd → (CBOR bytes, 版本)"""
    n, ver = struct.unpack("<II", payload[:8])
    raw = _zstd(payload[8:], True)
    assert len(raw) == n, (len(raw), n)
    return raw, ver


def pack_container(raw, ver=2):
    return struct.pack("<II", len(raw), ver) + _zstd(raw, False)


def split_state(blob):
    """XferJson state → (meta JSON bytes, CBOR DOM dict, 版本)。meta 長は u64 LE。"""
    assert blob[:9] == b"XferJson\x00", "magic 不一致"
    jl = struct.unpack("<Q", blob[9:17])[0]
    raw, ver = unpack_container(blob[17 + jl:])
    return blob[17:17 + jl], decode(raw), ver


def join_state(meta, dom, ver=2):
    """key 辞書順 (plugin の書出し順) で再エンコードして封入する。"""
    dom = dict(sorted(dom.items()))
    return b"XferJson\x00" + struct.pack("<Q", len(meta)) + meta + pack_container(encode(dom), ver)
