#!/usr/bin/env python3
"""SR-2b ライセンス状態データ合成 (LEGAL §6.0-4 ユーザ承認済み運用)。

「ライセンス済み」状態を 5 保存先 (CAB-71 REPORT §6 座標) に対して決定論的に合成する。
根拠 (lift IR 実測 — 詳細は authstub/REPORT.md §3):
  - demo bit (+0x22792) の writer は全 .text で SerumController::setState (0x1800c2b50) の
    2 store のみ (walk 実測)。prefs/registry/presetdb から demo 判定する経路は静的には存在しない。
  - host session state の reader 契約:
      processor  (0x18004fad0): {"component":"processor"(len9), "version":double∈[0,11.00001]}
                                 で "demoVersion" キーが「無い」ことが licensed 形
      controller (0x1800c2b50): {"component":"controller"(len10), "version":...} 同上
                                 ("kAudioUnitParameterFlag_IsHighResolution":false が demo マーカ)
  - 合成物はキー名・型のみ reader の定数文字列から採り、値は固定 → バイト一致で再生可能。

usage: python3 synth_state.py <outdir>
出力:
  <outdir>/host/processor_state.json    VST3 component (SerumDSP)側 setState 入力
  <outdir>/host/controller_state.json   VST3 controller (SerumController)側 setState 入力
  <outdir>/prefs/Serum2Prefs.json       %APPDATA%/Xfer/Serum2Prefs.json 相当 (空オブジェクト)
  <outdir>/prefs/SerumPrefs.json        %APPDATA%/Xfer/Serum/SerumPrefs.json 相当
  <outdir>/vreg_seed_serum2.json        vreg (CAB-94) への追加 seed 断片
  <outdir>/MANIFEST.sha256              全出力のハッシュ (決定論検証用)
"""
import hashlib
import json
import os
import sys

# reader 契約から採った定数 (.lift 実測)
KEY_COMPONENT = "component"          # 0x180fbabb1 (両 reader 共通)
VAL_PROCESSOR = "processor"          # len 9 (0x18004fad0 が要求)
VAL_CONTROLLER = "controller"        # len 10 (0x1800c2b50 が要求)
KEY_VERSION = "version"              # 0x180fc8fd3 (double, [0, 11.00001])
KEY_PRODUCT_VERSION = "productVersion"  # 0x180fc8fe9 (文字列, "2.0.20" と比較)
VER_SAFE = "2.1.5"                   # >= "2.0.20" → 未 patch でも demo store が起きない
VER_DOUBLE = 2.1                     # [0, 11.00001] 内の固定値
KEY_DEMO_DSP = "demoVersion"         # 0x180fc8ff8 — 書かない (これが licensed 形の本体)
KEY_DEMO_CTRL = "kAudioUnitParameterFlag_IsHighResolution"  # 0xfc8950 — 書かない


def host_state(tag: str) -> bytes:
    """host session state 1 個分。キー順固定・区切り固定で決定論的。"""
    doc = {
        KEY_COMPONENT: tag,
        KEY_VERSION: VER_DOUBLE,
        KEY_PRODUCT_VERSION: VER_SAFE,
    }
    # demo マーカキーは意図的に含めない (KEY_DEMO_DSP / KEY_DEMO_CTRL)
    text = json.dumps(doc, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return (text + "\n").encode("ascii")


def prefs_placeholder() -> bytes:
    # ライセンスキーは XOR 復元未解決 (CAB-71 §8-2) につき空オブジェクト。
    # demo 判定が prefs を読まないことは walk 実測 (REPORT §3) に基づく。
    return b"{}\n"


def vreg_seed() -> bytes:
    """tools/startup/vreg (CAB-94) の seed.json 形式に揃えた追加エントリ。"""
    entries = [
        {
            "hive": "HKCU",
            "key": "Software\\XferRecords\\Serum2InstallerPrefs",
            "name": "(key)",
            "type": "REG_SZ",
            "value": "",
            "apply": True,
            "group": "license",
            "confidence": "推定",
            "key_conf": "確定",
            "value_conf": "推定",
            "basis": "キー名は 0x180267210 の literal (CAB-71 §6 実測)。値名は XOR 復元未解決のため "
                     "空キー作成のみ (存在検査を通す目的)。demo 判定は registry を読まない (walk 実測)。",
            "pinned": True,
            "source": ["CAB-71 REPORT §6", "SR-2b authstub/REPORT.md §3"],
        },
    ]
    return (json.dumps({"_comment": "SR-2b 追加 seed 断片 (Serum2)", "entries": entries},
                       ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    out = sys.argv[1]
    files = {
        "host/processor_state.json": host_state(VAL_PROCESSOR),
        "host/controller_state.json": host_state(VAL_CONTROLLER),
        "prefs/Serum2Prefs.json": prefs_placeholder(),
        "prefs/SerumPrefs.json": prefs_placeholder(),
        "vreg_seed_serum2.json": vreg_seed(),
    }
    manifest = []
    for rel, data in files.items():
        p = os.path.join(out, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
        manifest.append((rel, hashlib.sha256(data).hexdigest(), len(data)))
    with open(os.path.join(out, "MANIFEST.sha256"), "w") as f:
        for rel, h, n in manifest:
            f.write(f"{h}  {rel}  ({n} bytes)\n")
    for rel, h, n in manifest:
        print(f"  {h[:16]}…  {n:4d}B  {rel}")
    print(f"合成完了: {out} ({len(manifest)} files, 決定論的)")


if __name__ == "__main__":
    main()
