#!/usr/bin/env python3
"""Shared ライブラリの OSS / プロプラ分類 (根拠は strings / symbol の正規表現で機械検査し hit を記録)。
 -> data/classification.json, data/classification.md"""
import sys, os, re, json
sys.path.insert(0, os.path.dirname(__file__))
from common import *

S = f"{WORK}/strings"
def strings_of(key):
    if key.startswith("BIN:"):
        return open(f"{MAC_SHARED}/{key[4:]}", "rb").read().decode("latin1")
    p = f"{S}/{key}.txt"
    return open(p, errors="replace").read() if os.path.exists(p) else ""

# key = work/strings のファイル名 stem。 ev = [(strings key, regex, 説明)]
LIBS = [
 dict(lib="libfreetype_x64", mac="libfreetype_x64.dylib", win=("freetype.dll", 24359), cls="OSS", upstream="FreeType 2.7 (2016)", lic="FTL/GPLv2 (dual)",
      ev=[("libfreetype_x64.x86_64", r"/Users/eugene/Documents/freetype-2\.7/", "mac 内ビルドパス freetype-2.7"), ("libfreetype_x64.x86_64", r"ftgrays|ftsmooth|ftbase\.c", "FreeType 標準モジュール名")],
      plan="wasm 再ビルド (PoC 済・LP64 bit 一致に ftgrays patch か wasm64 要)", diff="易", ticket="T-SH-01"),
 dict(lib="libblend2d", mac="libblend2d.dylib", win=("Blend2D.dll", 24339), cls="OSS + プロプラ glue (Agg2D)", upstream="Blend2D 0.11.x 系 (pre-v0.20, camelCase C ABI) + asmjit 1.13 + FL 独自 Agg2D glue", lic="zlib (Blend2D/asmjit) + IL 独自",
      ev=[("libblend2d.x86_64", r"\[Blend2D\] ASSERTION FAILURE", "Blend2D runtime assert 文字列"), ("libblend2d.x86_64", r"N6asmjit9_abi_1_13", "asmjit ABI 名前空間 _abi_1_13"),
          ("libblend2d.x86_64", r"_blArrayInit", "camelCase C ABI (v0.20 で snake_case 化)"), ("libblend2d.x86_64", r"Agg2D", "Agg2D glue (export は AggCreateInstance 1 本)")],
      plan="Blend2D 本体は wasm 再ビルド (no-JIT, PoC 済 pixel-exact)。Agg2D glue (~140 symbol) は lift か C++ 再実装", diff="易(本体)/中(glue)", ticket="T-SH-02"),
 dict(lib="liboggio_x64", mac="liboggio_x64.dylib", win=("oggio_x64.dll", 24361), cls="OSS 集合 + プロプラ wrapper + 静的 IPP", upstream="libogg 1.3.x + libvorbis 1.3.5 + libFLAC 1.3.1 (+FLAC++)", lic="BSD-3 (Xiph) + Intel IPP 静的",
      ev=[("liboggio_x64.x86_64", r"reference libFLAC 1\.3\.1 20141125", "libFLAC 1.3.1"), ("liboggio_x64.x86_64", r"Xiph\.Org libVorbis 1\.3\.5", "libvorbis 1.3.5"), ("win_24361", r"Xiph\.Org libVorbis I 20150105", "win 側 vorbis vendor 文字列"),
          ("liboggio_x64.x86_64", r"_e9_ippsConvert_32f32s_Sfs", "静的 IPP (CPU dispatch prefix e9_)")],
      plan="ogg+vorbis wasm 再ビルド (PoC 済 byte-exact)。FLAC 1.3.1 も同様。Oggio* wrapper (9 export, C++) は lift/再実装。IPP 静的部は自前 C に置換", diff="易(OSS)/中(wrapper)", ticket="T-SH-03"),
 dict(lib="ffmpeg (avcodec58/avformat58/avutil56/swscale5/swresample3)", mac="ffmpeg/osx64/*.dylib", win=("avcodec-58.dll ほか", 24433), cls="OSS", upstream="FFmpeg n4.4.3 (mac) / n4.4.2-2-g7ffb7d4b04 (win)", lic="LGPL (--enable-gpl 無し)。win n4.4.2 = `--enable-version3` (LGPLv3+, 内部 license 文字列 \"LGPL version 3 or later\") / mac n4.4.3 = version3 無し (\"LGPL version 2.1 or later\"); 出典 tools/docs/LEGAL.md",
      ev=[("BIN:ffmpeg/osx64/libavutil.56.dylib", r"n4\.4\.3-1-ga1f13b592b", "mac libavutil の version 文字列 n4.4.3"), ("BIN:ffmpeg/osx64/libavcodec.58.dylib", r"--disable-x86asm", "configure 行 (--enable-gpl 無し = LGPL)"),
          ("BIN:ffmpeg/osx64/libavcodec.58.dylib", r"Lavc58", "libavcodec 58 系")],
      plan="emscripten で n4.4.x を --disable-programs --disable-x86asm 相当で再ビルド (ffmpeg.wasm 先例)。libILVideo (プロプラ wrapper 26 export) は別途", diff="中", ticket="T-SH-04"),
 dict(lib="Python.framework 3.12", mac="Python/Python.framework", win=("python312.dll + 拡張 34 本", 24420), cls="OSS", upstream="CPython 3.12.1", lic="PSF",
      ev=[("BIN:Python/Python.framework/Versions/3.12/Resources/Info.plist", r"3\.12\.1, \(c\) 2001-2023 Python Software Foundation", "mac Info.plist = 3.12.1")],
      plan="wasm32-emscripten (CPython Tier-3 / Pyodide 手法) で 3.12.1 を再ビルド。ctypes/sqlite/ssl 等は不要分を除外", diff="中", ticket="T-SH-05"),
 dict(lib="libmp3lame_x64", mac="libmp3lame_x64.dylib", win=("lame_enc_dll.dll", 24348), cls="OSS", upstream="LAME 3.99.5", lic="LGPL",
      ev=[("libmp3lame_x64.x86_64", r"LAME %s version %s", "LAME バージョン書式"), ("libmp3lame_x64.x86_64", r"3\.99\.5", "3.99.5")],
      plan="wasm 再ビルド", diff="易", ticket="T-SH-03b"),
 dict(lib="wavpack_x64", mac="wavpack_x64.dylib", win=("wavpackdll.dll", 24364), cls="OSS", upstream="WavPack 4.80 (mac) / 4.60 (win)", lic="BSD-3",
      ev=[("wavpack_x64.x86_64", r"4\.80\.0", "mac 4.80.0"), ("wavpack_x64.x86_64", r"can't read all of WavPack file", "WavPack 標準メッセージ")],
      plan="wasm 再ビルド", diff="易", ticket="T-SH-03b"),
 dict(lib="EasyFLAC_x64", mac="EasyFLAC_x64.dylib", win=("EasyFLAC_x64.dll", 24342), cls="OSS(libFLAC) + 薄いプロプラ wrapper", upstream="libFLAC 1.5.0 (mac) / M2 で crc8 lift 済", lic="BSD-3 + IL",
      ev=[("EasyFLAC_x64.x86_64", r"reference libFLAC 1\.5\.0 20250211", "libFLAC 1.5.0")],
      plan="libFLAC 再ビルド + EasyFLAC_* 10 関数を薄く再実装 (M2/M3 の crc8 lift は参考のみ)", diff="易", ticket="T-SH-03"),
 dict(lib="ILSvg_x64", mac="ILSvg_x64.dylib", win=("ILSvg_x64.dll", 24346), cls="OSS 派生 (svgdom+svgren+AGG) + 3 関数 wrapper", upstream="cppfw: svgdom / svgren / papki / utki / mikroxml + AGG 2.4", lic="MIT (cppfw) + AGG(2.4 BSD 系)",
      ev=[("ILSvg_x64.x86_64", r"N6svgren8rendererE", "svgren::renderer"), ("ILSvg_x64.x86_64", r"N6svgdom", "svgdom 名前空間"), ("ILSvg_x64.x86_64", r"agg_vcgen_stroke\.cpp", "AGG ソース名"), ("win_24346", r"svgren", "win 側にも svgren")],
      plan="upstream (cppfw) の同 version を特定して wasm 再ビルド (version 特定が TODO) + svgCreate/Render/Destroy を薄く実装", diff="中", ticket="T-SH-06"),
 dict(lib="dsp_ippv2_x64", mac="dsp_ippv2_x64.dylib", win=("dsp_ippv2_x64.dll", 24356), cls="プロプラ(Intel) + OSS 同梱 (AGG Agg2D / GPC)", upstream="Intel oneAPI IPP 2021.7 + AGG(Agg2D) + GPC polygon clipper", lic="Intel Simplified SW License (再配布可・改変不可) / AGG / GPC(非商用条項あり)",
      ev=[("dsp_ippv2_x64.x86_64", r"ippCore", "ippCore"), ("dsp_ippv2_x64.x86_64", r"2021\.7 \(r0xa954907f\)", "IPP 2021.7"), ("dsp_ippv2_x64.x86_64", r"N3agg\d+\w+ctrl", "AGG ctrl クラス"), ("dsp_ippv2_x64.x86_64", r"tristrip node creation", "GPC (General Polygon Clipper) の alloc 文字列")],
      plan="lift しない。実使用関数 (静的参照 win 229 / mac x86_64 234 / 和集合 239; tools/ipp の実測。本 tool の初版 win 12 / mac 159 は二段間接を数え落とした過少値) を自前 C(+wasm SIMD) で実装し 420 名を同名 export (詳細は tools/ipp)。Agg2D は Blend2D 側で代替", diff="中(使用部のみ)", ticket="T-SH-07"),
 dict(lib="elastique_x64", mac="elastique_x64.dylib", win=("elastique_x64.dll", 24357), cls="プロプラ(zplane 第三者)", upstream="zplane élastique (2.2.15-elastiqueProV2)", lic="商用ライセンス (SDK 契約)",
      ev=[("elastique_x64.x86_64", r"2\.2\.15-elastiqueProV2", "élastique version"), ("elastique_x64.x86_64", r"TElastiquePro", "zplane クラス名")],
      plan="第三者バイナリ: lift 対象 (win は静的 IPP 約 1MB 含む → mac 版 (Accelerate 依存) か win 版 + 自前 IPP)。EULA 事実整理要", diff="難", ticket="T-SH-10"),
 dict(lib="REX Shared Library", mac="REX Shared Library.framework", win=("REX Shared Library.dll", 24351), cls="プロプラ(Reason Studios 第三者)", upstream="REX SDK (Propellerhead Software AB 2000-2010, win DLL の著作権表示)", lic="REX SDK ライセンス", ev=[("win_24351", r"REX2", "REX2 クラス名 (CREX2DecompressCallback / XREX2BadFormat)"), ("win_24351_u16", r"Copyright Propellerhead Software AB 2000-2010", "著作権表示 (Propellerhead = Reason Studios 前身; UTF-16 リソース)")],
      plan="第三者バイナリ。REX 読込は優先度低 (DirectWave/Slicer 経由)", diff="難", ticket="T-SH-11"),
 dict(lib="ILTools_x64", mac="ILTools_x64.dylib", win=("ILTools_x64.dll", 24347), cls="プロプラ(IL)", upstream="FPC 3.2.3 (mac) / Delphi (win) — 同一 Pascal ソース", lic="IL 独自",
      ev=[("ILTools_x64.x86_64", r"FPC 3\.2\.3 \[2023/12/20\] for x86_64 - Darwin", "FPC 3.2.3"), ("ILTools_x64.x86_64", r"TDelphiHashFactory", "FPC generics.defaults")],
      plan="win Delphi x64 (3.66MB) を M5 A9/M11 と同じパイプラインで lift。PathManager 等 OS 依存が大きく shim 先行", diff="難", ticket="T-SH-12"),
 dict(lib="SGv2_x64", mac="SGv2_x64.dylib", win=("FruityPlug_x64.dll (export CreatePlugInstance 一致; 推定)", 24353), cls="プロプラ(IL)", upstream="FPC 3.2.3 (mac) / Delphi (win)", lic="IL 独自",
      ev=[("SGv2_x64.x86_64", r"FPC 3\.2\.3 \[2023/12/20\] for x86_64 - Darwin", "FPC 3.2.3"), ("SGv2_x64.x86_64", r"TDelphiFruityPlug", "Fruity plugin ホスト層")],
      plan="Fruity プラグイン SDK ホスト層。GUI 結合が強く FLEngine lift 後に着手", diff="難", ticket="T-SH-12"),
 dict(lib="libQuickFontCachev2_x64", mac="libQuickFontCachev2_x64.dylib", win=("QuickFontCache_x64.dll", 24350), cls="プロプラ(IL)", upstream="FPC 3.2.3 (mac) / Delphi (win)", lic="IL 独自",
      ev=[("libQuickFontCachev2_x64.x86_64", r"FPC 3\.2\.3 \[2023/12/20\] for x86_64 - Darwin", "FPC 3.2.3"), ("libQuickFontCachev2_x64.x86_64", r"FontCache_AcquireFont|CreateVST3Instance", "export 面 (font cache + 共有 timer/thread bank/Python/elastique ローダ)")],
      plan="共有サービス層 (FontCache/AnimTimer/ThreadBank/InitSharedPython/LoadSharedElastiqueDll)。Delphi lift 候補だが freetype 結合のため OSS 再ビルド後", diff="中-難", ticket="T-SH-12"),
 dict(lib="libwinbridge_x64", mac="libwinbridge_x64.dylib", win=("(なし: mac 専用)", None), cls="プロプラ(IL) mac 専用", upstream="FPC 3.2.3", lic="IL 独自",
      ev=[("libwinbridge_x64.x86_64", r"FPC 3\.2\.3 \[2023/12/20\] for x86_64 - Darwin", "FPC 3.2.3"), ("libwinbridge_x64.x86_64", r"TFPGMap<Winapi", "Winapi 型を mac へ橋渡し")],
      plan="移植不要: Win32 面は tools/shim (M4) + M2 SHIM_INVENTORY で代替。lift しない", diff="n/a", ticket="-"),
 dict(lib="DirectWaveCtEngine_x64", mac="DirectWaveCtEngine_x64.dylib", win=("DirectWaveCtEngine.dll", 24341), cls="プロプラ(IL/第三者形式 importer)", upstream="C++ (libc++), SampleImport (Kontakt/EXS/Akai/SF2/SFZ/REX)", lic="IL 独自",
      ev=[("DirectWaveCtEngine_x64.x86_64", r"SampleImport/", "ソースパス SampleImport"), ("DirectWaveCtEngine_x64.x86_64", r"CKontaktStruct", "Kontakt importer"), ("win_24341", r"CreateKontakt", "win 側にも Kontakt 実装を内蔵")],
      plan="DirectWave 用サンプル形式 importer。FS shim 完成後に lift (MSVC C++ x64)。優先度低", diff="難", ticket="T-SH-13"),
 dict(lib="libkio_x64", mac="libkio_x64.dylib", win=("(DirectWaveCtEngine.dll に内蔵)", 24341), cls="プロプラ(第三者 NI K4PL 派生)", upstream="GCC C++ + boost, namespace NI::GP / K4PO / K4PatchLib (Kontakt 4 patch lib)", lic="第三者(NI)派生・要確認",
      ev=[("libkio_x64.x86_64", r"K4PL|K4PatchLib|CKontaktStruct_RCS", "Kontakt 4 patch lib 名前空間"), ("libkio_x64.x86_64", r"N5boost", "boost 使用")],
      plan="NKI(Kontakt) 読込。DirectWave と同チケット。lift PoC: 純粋ユーティリティ 15 関数 (REPORT §4)", diff="中-難", ticket="T-SH-13"),
 dict(lib="beat_tracker", mac="beat_tracker.dylib", win=("beat_tracker_dll.dll", 24354), cls="プロプラ(IL) + Eigen(MPL2)", upstream="C++ (libc++) + Eigen, librosa/madmom 風 (estimate_bpm / forward_backward_decode / bar_position_hmm)", lic="IL 独自 + MPL2 (Eigen)",
      ev=[("beat_tracker.x86_64", r"N5Eigen6Matrix", "Eigen 使用"), ("beat_tracker.x86_64", r"estimate_bpm|forward_backward_decode|bar_position_hmm", "librosa/madmom 風アルゴリズム名"), ("win_24354", r"beatTrackerEstimateBpm", "win export")],
      plan="export 14 本の小 API。Eigen テンプレ展開部が大 (SSE packed 24%)。x86_64 mac slice を RetDec lift が現実的だが double 精度/決定性の検証要", diff="中-難", ticket="T-SH-14"),
 dict(lib="ildsp_x64", mac="ildsp_x64.dylib", win=("ildsp_x64.dll", 24360), cls="プロプラ(IL)", upstream="C++ (libc++) DSP (Limiter/PSOLA/Shimmer/StereoEnhancer…)", lic="IL 独自",
      ev=[("ildsp_x64.x86_64", r"Lowpass1\.cpp|GRAdaptiveRel\.cpp|MathUtils\.cpp", "IL ソース名")],
      plan="OTT と同型の DSP (SIMD 40%): M6-M11 手法 (mac x86_64 SSE のみ版が lift しやすい)", diff="中", ticket="T-SH-15"),
 dict(lib="libreverb_x64", mac="libreverb_x64.dylib", win=("Reverb.dll", 24352), cls="プロプラ(IL)", upstream="C++ (libc++) Fruity Reverb", lic="IL 独自",
      ev=[("libreverb_x64.x86_64", r"DelayLine\.cpp", "IL ソース名")],
      plan="最小 DSP lib (5.6K 命令)。M6-M11 手法の別 PoC 候補 (Process_Fruity は SSE scalar → __asm_* helper 要)", diff="易-中", ticket="T-SH-15"),
 dict(lib="ILRemoteServerOSX_x64", mac="ILRemoteServerOSX_x64.dylib", win=("ILRemoteServerCppDLL.dll", 24345), cls="プロプラ(IL)", upstream="C++ (ILR_ServerManager)", lic="IL 独自",
      ev=[("ILRemoteServerOSX_x64.x86_64", r"ILRemoteClientClass", "ILRemote")],
      plan="リモートコントロール(ネットワーク)。対象外 (外部通信)", diff="n/a", ticket="-"),
]
catalog = {r["file"]: r for r in json.load(open(f"{RAW}/win_pe_catalog.json"))} if os.path.exists(f"{RAW}/win_pe_catalog.json") else {}

def fat_size(p):
    full = f"{MAC_SHARED}/{p}"
    return os.path.getsize(full) if os.path.isfile(full) else None

out = []
for L in LIBS:
    row = {k: L[k] for k in ("lib", "cls", "upstream", "lic", "plan", "diff", "ticket")}
    stem = L["mac"].replace(".dylib", "")
    row["mac_fat_bytes"] = fat_size(L["mac"])
    sl = f"{WORK}/slices/{stem}.x86_64.dylib"
    if os.path.exists(sl):
        row["mac_x86_64_bytes"] = os.path.getsize(sl)
        row["mac_exports"] = len(run(["llvm-nm", "-gU", sl]).stdout.splitlines())
        sj = f"{WORK}/simd/{stem}.json"
        if os.path.exists(sj):
            j = json.load(open(sj)); row["mac_instructions"] = j["instructions"]; row["mac_simd_ratio"] = j["simd_ratio"]; row["mac_classes"] = j["classes"]
    wn, wb = L["win"]; row["win"] = wn
    if wb:
        c = catalog.get(f"block{wb:05d}_PE.bin")
        if c: row["win_bytes"] = c["size"]; row["win_exports"] = len(c["exports"]); row["win_arch"] = c["machine"]
    ev = []
    for key, rx, desc in L["ev"]:
        t = strings_of(key); m = re.search(rx, t, re.M)
        ev.append({"check": desc, "pattern": rx, "hit": bool(m), "sample": (m.group(0)[:80] if m else "")})
    row["evidence"] = ev
    out.append(row)
json.dump(out, open(f"{DATA}/classification.json", "w"), indent=1, ensure_ascii=False)
tot = sum(len(r["evidence"]) for r in out); hit = sum(e["hit"] for r in out for e in r["evidence"])
print(f"libs={len(out)} evidence hit {hit}/{tot}")
for r in out:
    miss = [e["check"] for e in r["evidence"] if not e["hit"]]
    print(f"{r['lib'][:34]:34s} {r['cls'][:40]:40s} fat={r['mac_fat_bytes']} ex={r.get('mac_exports')} ins={r.get('mac_instructions')} simd={r.get('mac_simd_ratio')} {'MISS:'+str(miss) if miss else ''}")
