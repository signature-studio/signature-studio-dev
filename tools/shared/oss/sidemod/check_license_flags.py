#!/usr/bin/env python3
"""FFmpeg / LAME の GPL 混入検出 (LGL-4, docs/LEGAL.md §3.2)。

検査対象 (いずれも「実際にビルドされたもの」を見る):
  ffmpeg-config   FFmpeg の configure 引数文字列 (avcodec_configuration() の出力 or build.sh の引数列)
  ffmpeg-configh  ffbuild/config.h の CONFIG_GPL / CONFIG_NONFREE / CONFIG_VERSION3 が 0 であること
  ffmpeg-license  avcodec_license() が "LGPL version 2.1 or later" であること
  lame-configure  LAME の configure 引数に --disable-decoder (= mpglib 無効) があること
  lame-binary     成果物に mpglib のシンボル (hip_decode* / lame_decode*) が無いこと
  artifact        side module (.wasm/.so) のバイト列から configure 文字列・license 文字列を抽出して上を検査

usage:
  check_license_flags.py config   "<configure string>"
  check_license_flags.py configh  <path/to/config.h>
  check_license_flags.py license  "<license string>"
  check_license_flags.py lame     <lame configure args> -- <binary>
  check_license_flags.py artifact <ffmpeg.wasm> <lame.wasm> [config.h]
  check_license_flags.py selftest
終了コード: 0 = クリーン / 1 = GPL 系の混入を検出 / 2 = 使い方の誤り
"""
import re
import sys

# 有効化すると GPL / version3 / nonfree になる (または GPL 専用の) configure オプション。
# 出典: FFmpeg configure の「GPL / version3 / nonfree が必要」な external library 一覧
FORBIDDEN_FLAGS = {
    "gpl", "nonfree", "version3",
    # GPL ライブラリ
    "libx264", "libx265", "libxvid", "libxavs", "libxavs2", "libdavs2", "libcdio",
    "librubberband", "libvidstab", "libzvbi", "frei0r", "avisynth", "libaribcaption",
    # version3 (LGPLv3+ / GPLv3) を要求するライブラリ
    "libopencore-amrnb", "libopencore-amrwb", "libvo-amrwbenc", "libsmbclient",
    "gmp", "libaribb24", "rubberband",
    # nonfree
    "libfdk-aac", "libfdk_aac", "decklink", "openssl", "libnpp", "cuda-nvcc", "libtls",
}
LICENSE_OK = "LGPL version 2.1 or later"
LAME_DECODER_SYMS = (b"hip_decode", b"lame_decode", b"decode_header", b"mpglib")


def forbidden_in(config: str):
    hits = []
    for tok in re.findall(r"--enable-([A-Za-z0-9_+.-]+)", config):
        name = tok.split("=")[0]
        if name in FORBIDDEN_FLAGS:
            hits.append("--enable-" + name)
    return hits


def check_config(config: str):
    return [f"forbidden configure flag: {h}" for h in forbidden_in(config)]


def check_configh(text: str):
    errs = []
    for key in ("CONFIG_GPL", "CONFIG_NONFREE", "CONFIG_VERSION3"):
        m = re.search(r"#define\s+%s\s+(\d+)" % key, text)
        if not m:
            errs.append(f"{key} not found in config.h")
        elif m.group(1) != "0":
            errs.append(f"{key}={m.group(1)}")
    return errs


def check_license(lic: str):
    return [] if lic.strip() == LICENSE_OK else [f"license is {lic.strip()!r}, expected {LICENSE_OK!r}"]


def check_lame(args: str, binary: bytes | None):
    errs = []
    if "--disable-decoder" not in args.split():
        errs.append("LAME configure lacks --disable-decoder (mpglib is GPL)")
    if "--enable-decoder" in args.split():
        errs.append("LAME configure has --enable-decoder")
    if binary is not None:
        for s in LAME_DECODER_SYMS:
            if s in binary:
                errs.append(f"LAME binary contains mpglib symbol {s.decode()!r}")
    return errs


def extract(blob: bytes, pat: bytes):
    m = re.search(pat, blob)
    return m.group(0).decode("latin1") if m else None


def check_artifact(ff: bytes, lame: bytes, config_h: str | None):
    errs = []
    cfg = extract(ff, rb"--prefix=[\x20-\x7e]*--enable-[\x20-\x7e]*|--target-os=[\x20-\x7e]+")
    if cfg is None:
        errs.append("ffmpeg artifact: configure string not found (avcodec_configuration missing)")
    else:
        errs += check_config(cfg)
    lic = extract(ff, rb"LGPL version [0-9.]+ or later|GPL version [0-9.]+ or later|nonfree and unredistributable")
    if lic is None:
        errs.append("ffmpeg artifact: license string not found")
    else:
        errs += check_license(lic)
    if config_h:
        errs += check_configh(config_h)
    errs += check_lame("--disable-decoder", lame)
    return errs


def selftest():
    good = "--prefix=/nonexistent --target-os=none --disable-everything --enable-decoder=flac,mp3 --enable-pic"
    cases = [
        ("clean config", check_config(good), False),
        ("--enable-gpl", check_config(good + " --enable-gpl"), True),
        ("--enable-version3", check_config(good + " --enable-version3"), True),
        ("--enable-nonfree", check_config(good + " --enable-nonfree"), True),
        ("--enable-libx264", check_config(good + " --enable-libx264"), True),
        ("--enable-libx265=yes", check_config(good + " --enable-libx265=yes"), True),
        ("--disable-gpl is fine", check_config(good + " --disable-gpl"), False),
        ("config.h clean", check_configh("#define CONFIG_GPL 0\n#define CONFIG_NONFREE 0\n#define CONFIG_VERSION3 0\n"), False),
        ("config.h GPL=1", check_configh("#define CONFIG_GPL 1\n#define CONFIG_NONFREE 0\n#define CONFIG_VERSION3 0\n"), True),
        ("config.h VERSION3=1", check_configh("#define CONFIG_GPL 0\n#define CONFIG_NONFREE 0\n#define CONFIG_VERSION3 1\n"), True),
        ("license LGPL2.1+", check_license("LGPL version 2.1 or later"), False),
        ("license LGPL3+", check_license("LGPL version 3 or later"), True),
        ("license GPL2+", check_license("GPL version 2 or later"), True),
        ("lame clean", check_lame("--disable-decoder --disable-shared", b"lame_encode_buffer"), False),
        ("lame w/o --disable-decoder", check_lame("--disable-shared", None), True),
        ("lame w/ hip_decode", check_lame("--disable-decoder", b"xx hip_decode1 xx"), True),
        ("artifact clean", check_artifact(
            b"\0--prefix=/nonexistent --target-os=none --enable-decoder=flac\0LGPL version 2.1 or later\0", b"lame_encode_buffer", None), False),
        ("artifact w/ gpl", check_artifact(
            b"\0--prefix=/nonexistent --enable-gpl --enable-libx264\0GPL version 2 or later\0", b"lame_encode_buffer", None), True),
    ]
    bad = 0
    for name, errs, want_fail in cases:
        ok = bool(errs) == want_fail
        print(f"[selftest] {'OK ' if ok else 'BAD'} {name}: {'detected ' + errs[0] if errs else 'clean'}")
        bad += not ok
    print(f"[selftest] {len(cases) - bad}/{len(cases)} ok")
    return 1 if bad else 0


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    cmd = argv[1]
    if cmd == "selftest":
        return selftest()
    if cmd == "config" and len(argv) == 3:
        errs = check_config(argv[2])
    elif cmd == "configh" and len(argv) == 3:
        errs = check_configh(open(argv[2]).read())
    elif cmd == "license" and len(argv) == 3:
        errs = check_license(argv[2])
    elif cmd == "lame" and "--" in argv:
        i = argv.index("--")
        errs = check_lame(" ".join(argv[2:i]), open(argv[i + 1], "rb").read() if len(argv) > i + 1 else None)
    elif cmd == "artifact" and len(argv) in (4, 5):
        errs = check_artifact(open(argv[2], "rb").read(), open(argv[3], "rb").read(),
                              open(argv[4]).read() if len(argv) == 5 else None)
    else:
        print(__doc__); return 2
    for e in errs:
        print("GPL-GUARD FAIL:", e)
    if not errs:
        print("GPL-GUARD OK")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
