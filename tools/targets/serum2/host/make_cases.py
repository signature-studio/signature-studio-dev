#!/usr/bin/env python3
"""E2E 用 case state 生成 (v4 — payload = CBOR DOM を直接合成, #255 / #341)。

state 形式 (host 実測 + 逆アセンブル, payload_codec.py 参照):
  "XferJson\\0" + u64LE(meta 長) + meta JSON + u32LE(CBOR 長) + u32LE(2) + zstd(CBOR)
  - setState (0x18004fad0 / 0x1800c2b50) が見る DOM は **payload の CBOR** (0x1801bf1c0 が返す doc)。
    meta JSON への demoVersion 注入は demo 分岐に届かない (#69 実測)。

case:
  licensed      CAB-237 合成 meta + seed payload (従来)
  demo          meta のみに demo マーカ (従来。届かないことの対照)
  lic_sent      seed payload に sentinel (processor mpePitchBendRange=24 / controller presetName) のみ — 復元が適用されたかの対照
  demo_payload  lic_sent + payload DOM に demo マーカ:
                  processor: demoVersion="2.1.5"            (0x18004fad0 が検出 → dialog + 復元打切り)
                  controller: kAudioUnitParameterFlag_IsHighResolution=false (0x1800c2b50 demo bit 経路)
                sentinel が保存 state に反映されない = 復元打切り (demo 分岐発火) の観測量
  lowver        lic_sent + payload DOM 最上位 productVersion を LOWVER (2.0.19 < 2.0.20) に下げる (#341)。
                meta の productVersion は 2.1.5 のまま (payload 側だけの効果を分離)。
                0x1800c2b50 の "2.0.20" 比較 (#238 契約) の実 DLL 突合用

usage: python3 make_cases.py <srcdir(CAB-237 synth 出力)> <seeddir(seed run の保存 state)> <outdir(cases)>
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import payload_codec as pc  # noqa: E402

SENT_PBR = 24            # processor sentinel (既定 48)
SENT_PRESET = "SENTINEL"  # controller sentinel (既定 " - Init - ")
LOWVER = "2.0.19"        # < "2.0.20" (0xfd631e の比較対象)


def synth_meta(src, side, demo_meta):
    synth = json.load(open(os.path.join(src, "host", f"{side}_state.json")))
    if demo_meta:
        if side == "processor":
            synth["demoVersion"] = "2.1.5"
        else:
            synth["kAudioUnitParameterFlag_IsHighResolution"] = False
    return json.dumps(synth, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def main():
    src, seed, out = sys.argv[1], sys.argv[2], sys.argv[3]
    seeds = {}
    for side in ("processor", "controller"):
        _, dom, ver = pc.split_state(open(os.path.join(seed, f"saved_{side}_state.bin"), "rb").read())
        seeds[side] = (dom, ver)

    for case in ("licensed", "demo", "lic_sent", "demo_payload", "lowver"):
        d = os.path.join(out, case)
        os.makedirs(d, exist_ok=True)
        for side in ("processor", "controller"):
            ver = seeds[side][1]
            dom = pc.decode(pc.encode(seeds[side][0]))  # deep copy (Float32 保持)
            if case in ("lic_sent", "demo_payload", "lowver"):
                if side == "processor":
                    dom["mpePitchBendRange"] = SENT_PBR
                else:
                    dom["presetName"] = SENT_PRESET
            if case == "demo_payload":
                if side == "processor":
                    dom["demoVersion"] = "2.1.5"
                else:
                    dom["kAudioUnitParameterFlag_IsHighResolution"] = False
            if case == "lowver":
                assert dom.get("productVersion") == "2.1.5", dom.get("productVersion")  # seed が想定どおり
                dom["productVersion"] = LOWVER
            meta = synth_meta(src, side, demo_meta=(case == "demo"))
            blob = pc.join_state(meta, dom, ver)
            with open(os.path.join(d, f"{side}_state.json"), "wb") as f:
                f.write(blob)
            print(f"  {d}/{side}_state.json: {len(blob)}B")
    print(f"case 生成完了: {out}")


if __name__ == "__main__":
    main()
