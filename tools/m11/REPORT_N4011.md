# REPORT_N4011 — #4011 段 2: `pass_m2v_fn40fcf0_arg1` (gated, 既定 OFF)

REPORT.md §19 の付録。PR #5109 (`Refs #4011`) の実測・検証記録の正本。

## 1. 変更

- `tools/m11/m11_passes.py`: `pass_m2v_fn40fcf0_arg1` を追加 (26 行)。`function_40fcf0` の `function_40fd90` 呼出しの第 1 引数を `self` から `[self]` (VMT) に直す。呼出し 1 箇所だけを対象にし、`M11_M2V=1` の gate の内側に置く (既定 OFF)。
- 根拠: 機械語 `40fd0b: mov rcx,[rbx]` (rbx = self) で VMT を渡している。IR は self をそのまま渡していた。

## 2. 測定 commit と差分 0 の証跡

- 測定 commit: `af6e700c47d35dadb4057df22b90881a9cc6a1c1` (コード差分の最終 commit)。
- `git diff af6e700c4 HEAD -- tools/m11 ':!tools/m11/REPORT*.md'` の出力: 0 行 (本節を足す前の HEAD で確認)。
  本節と REPORT.md の変更はドキュメントのみで、測定対象のコードは変わらない (`docs/WORKFLOW.md` §6)。

## 3. 実測 (作者測定・commit `af6e700c4`)

素材: fl-win64 / toolchain-retdec / toolchain-emsdk / work-m11 を展開。`ir_conditions.json` は `m11_gen_ir2.sh` で run 内に生成 (ldfix=applied)。PE は `block00031_PE.bin`。

| 構成 | units_run | init | icall_miss | last_unit | threw |
|---|---|---|---|---|---|
| 既定 OFF (前後で同じ) | 109 | 111 | 7 | 114 (Halt0) | null |
| `M11_M2V=1 M11_M2S=1` (本 PR) | 129 | 132 | 16 | 144 (`0x65c540`) | `memory access out of bounds` |

- `m11_gen_ir2.sh` rc 0 (約 41 秒・`[M2v] function_40fcf0 arg1 VMT: 1 sites`)
- `m11_build.sh` rc 0 (wasm-ld signature mismatch 0 / undefined 0・約 23 秒)
- `tools/gui/flengine/build.sh` rc 0 (約 19 秒)
- `boot_halt_probe.mjs` rc 0 (数秒)

### 本 run での再現

- 本 fix run では `work-m11` / `toolchain-retdec` / `toolchain-emsdk` が `$ARTIFACTS_DIR` に無く (fl-win64 のみ)、上の実測を**再現していない**。
- 再現には PR 本文の `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk work-m11` での再起動が要る (次の run で測る)。

## 4. 受入と判定

- 受入 1 (`last_unit.index0 > 114`): 数値は 144 に前進したが、OOB は残り、`icall_miss` 7→16 (新規 miss 3 件)。**未達と判定**。「前進」ではなく「偽の前進」の疑いがある (miss は `return 0` で処理を飛ばす)。
- 受入 2 (`function_41a800` の vtable 判定): 段 1 で確認済み (§19 の節を参照・本段では変更なし)。

## 5. ネガティブコントロール

- 未実施。pass を無効化して OOB が再現することを数値で示すのが次の一手 (下の未解決表)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| OOB の発生箇所が未特定 (probe は `function_40fd90` の 2025 フレームを含まず、trap の wasm offset を採取していない) | 受入 1 未達 | #4011 (次 run) |
| 新規 icall miss 3 件 (`0x457860` / `0xfa9390` / `0x85df70`) の由来が未確認 (`return 0` の経路) | 偽の前進の可能性 | #4011 (次 run) |
| `M11_M2S` 単独 (`function_40fd90` の IID 比較のみ) は未測定 | 組合せの寄与が不明 | #4011 (次 run) |
| AddRef (`function_40fcf0` の `call [rax+8]`・VA `0x40fd3a`) は未復元 | 受入 2 の完全形に必要 | #4011 (次 run) |
| 再現スクリプトが無い (測定は手順の文章のみ) | 再現性 | #4011 (次 run) |
| 受入 3 (CS-INIT `0x12bd390`) | 範囲外 | #4031 |

## 7. 次の一手

1. probe の trap の wasm offset を採取し、`m11_wasmnames.py` で関数名を取る。miss 3 件の呼出し元 (`m11_icall` の target) を VA にして、その由来を確認する。
2. `M11_M2S=1` 単独を測り、組合せの寄与を分ける。
3. `M11_M2V=1` を外して OOB が出ないことを示すネガティブコントロールを取る。
4. 受入 1 は、miss 0 のまま `last_unit.index0 > 114` になった時だけ issue 完了の判定に進める。
