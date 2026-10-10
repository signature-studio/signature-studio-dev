#!/usr/bin/env python3
"""CAB-68 E2E 用 case state 生成 (v2 — XferJson コンテナ式)。

実測した state 形式 (host 実測, 2026-10-10):
  "XferJson\\0" + int32LE(json長) + int32LE(0) + JSON(meta) + int32LE(展開後長) + int32LE(2) + zstd(payload)
  - meta JSON のみ (payload 無し) では setState が kResultFalse (V1 実測)
  - meta + plugin 既定 payload で kResultTrue (V2 実測) → 本形式を採用
  - plugin が書く meta: component/hash/preset*/product/productVersion/url/vendor/version(11.0)

licensed case: CAB-237 synth_state.py の meta (マーカキー不在 = licensed 形) をそのまま封入。
demo case:     同一書式に demo マーカを追加した「デモ抑止を再現させる入力」:
  - processor meta: demoVersion キー追加 (0x18004fad0 が検出 → ダイアログ + 復元打ち切り)
  - controller meta: kAudioUnitParameterFlag_IsHighResolution: false 追加
    (0x1800c2b50 で demo bit +0x22792 = ¬false = 1 → 0x1800c3080 ロード + 0x800010 通知)

payload は plugin 自身が書いた既定 Init state から抽出 (seed run 成果物)。ライセンス性は持たない。

usage: python3 make_cases.py <srcdir(CAB-237 synth 出力)> <seeddir(seed run の保存 state)> <outdir(cases)>
"""
import json
import os
import struct
import sys


def container(meta_js: bytes, payload: bytes) -> bytes:
    # payload は「int32LE(展開後長) + int32LE(2) + zstd」を含めた領域をそのまま再利用する
    # (長さヘッダを再計算すると zstd 圧縮後長を展開後長として書くことになり崩れる — 実測バグ)
    return b"XferJson\x00" + struct.pack("<II", len(meta_js), 0) + meta_js + payload


def split_saved(path):
    """seed run の保存 state から (meta JSON, payload 領域) を取り出す。

    payload 領域 = int32LE(展開後長) + int32LE(2) + zstdストリーム (長さヘッダごと持つ)。
    """
    d = open(path, "rb").read()
    assert d[:9] == b"XferJson\x00", f"magic 不一致: {path}"
    jlen, _ = struct.unpack("<II", d[9:17])
    meta = d[17:17 + jlen]
    payload = d[17 + jlen:]
    return meta, payload


def main():
    src, seed, out = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(out, exist_ok=True)

    payloads = {}
    for side in ("processor", "controller"):
        meta, payload = split_saved(os.path.join(seed, f"saved_{side}_state.bin"))
        payloads[side] = payload

    for case in ("licensed", "demo"):
        d = os.path.join(out, case)
        os.makedirs(d, exist_ok=True)
        for side in ("processor", "controller"):
            synth = json.load(open(os.path.join(src, "host", f"{side}_state.json")))
            if case == "demo":
                if side == "processor":
                    synth["demoVersion"] = "2.1.5"
                else:
                    synth["kAudioUnitParameterFlag_IsHighResolution"] = False
            meta_js = json.dumps(synth, ensure_ascii=True, sort_keys=True,
                                 separators=(",", ":")).encode()
            blob = container(meta_js, payloads[side])
            with open(os.path.join(d, f"{side}_state.json"), "wb") as f:
                f.write(blob)
            print(f"  {d}/{side}_state.json: {len(blob)}B meta={meta_js.decode()}")

    print(f"case 生成完了: {out} (licensed/demo × XferJson コンテナ式)")


if __name__ == "__main__":
    main()
