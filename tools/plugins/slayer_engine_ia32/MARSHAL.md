# tools/plugins/slayer_engine_ia32/MARSHAL.md — 殻 (x64) ↔ Slayer_Engine.dll (ia32) の VST2 構造体 marshal 表 (#674 受入 3)

- 日付: 2026-10-13 / 担当 dir: `tools/plugins/slayer_engine_ia32/` のみ / 親 #536 / 本 issue #674 (受入 5 項目のうち 3 を対象)
- 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 $PY tools/plugins/slayer_engine_ia32/marshal.py` (gate) と `… marshal.py --nega` (ネガコン)。 `$PY` は前回 REPORT の venv (capstone==5.0.7)。
- 既知類型との関係 (`docs/DEFECTS.md`): 該当なし (構造体配置の静的表。 lift 出力は作らない)。

## 1. 結論

1. **engine (block22434) の AEffect 構築は 32bit SDK 配置 (sizeof 0x90)**。 殻の x64 配置 (sizeof 0xC0) とは全欄の offset が異なる。 表 §3 のとおり。
2. **engine の AEffect 構築 store 列 (実測) は 0x20 欄 (magic / 各 thunk / numPrograms / ioRatio / uniqueID 等) を全て確定できた**。 `rep stosd` の 0 埋め (0x90 B) が AEffect 全体を覆うことを確認し、未 store の `processDoubleReplacing` (x32 0x54) は 0 埋め由来で未初期化ではない。
3. **ポインタ欄は全て 8→4 B**。 殻から見た AEffect のポインタ欄は、guest 空間 (ImageBase 0x10000000 基準の 32bit VA) の値として詰め直す。 数値の意味 (thunk 先) は変えない。
4. **VstEvents / ERect は仕様の計算値のみ**。 engine 側の読み取り箇所の裏付けは未取得 (§4)。

## 2. 検証の対象と限界

- 対象: engine の AEffect 構築関数 `0x10E0`〜`0x1196` (`this+0x20` に AEffect を置き、`rep stosd` で 0x90 B を 0 埋め)。
- 検証は**静的** (capstone の逆アセンブル store 列)。 engine を実行していないので、store 値の正しさは実行で未確認。
- 限界: 殻の x64 側の配置は `tools/hostbridge/poc/vst2_abi.h` の `_Static_assert` を期待値として使う (殻側の実物 C 構造体はこの PoC の値)。

## 3. marshal 表 (AEffect)

| 欄 | x64 (殻) off/size | x32 (engine) off/size | 変換 |
|---|---|---|---|
| magic | 0x00 / 4 | 0x00 / 4 | そのまま (`'VstP'` 0x56737450、engine 実測一致) |
| dispatcher | 0x08 / 8 | 0x04 / 4 | ポインタ 8→4 B |
| process | 0x10 / 8 | 0x08 / 4 | ポインタ 8→4 B |
| setParameter | 0x18 / 8 | 0x0c / 4 | ポインタ 8→4 B |
| getParameter | 0x20 / 8 | 0x10 / 4 | ポインタ 8→4 B |
| numPrograms | 0x28 / 4 | 0x14 / 4 | そのまま |
| numParams | 0x2c / 4 | 0x18 / 4 | そのまま |
| numInputs | 0x30 / 4 | 0x1c / 4 | そのまま |
| numOutputs | 0x34 / 4 | 0x20 / 4 | そのまま |
| flags | 0x38 / 4 | 0x24 / 4 | そのまま |
| resvd1 | 0x40 / 8 | 0x28 / 4 | ポインタ 8→4 B (host 所有) |
| resvd2 | 0x48 / 8 | 0x2c / 4 | ポインタ 8→4 B |
| initialDelay | 0x50 / 4 | 0x30 / 4 | そのまま |
| realQualities | 0x54 / 4 | 0x34 / 4 | そのまま |
| offQualities | 0x58 / 4 | 0x38 / 4 | そのまま |
| ioRatio | 0x5c / 4 | 0x3c / 4 | f32 bit 同一 |
| object | 0x60 / 8 | 0x40 / 4 | ポインタ 8→4 B (plugin 所有・host は不透明に扱う) |
| user | 0x68 / 8 | 0x44 / 4 | ポインタ 8→4 B |
| uniqueID | 0x70 / 4 | 0x48 / 4 | そのまま |
| version | 0x74 / 4 | 0x4c / 4 | そのまま |
| processReplacing | 0x78 / 8 | 0x50 / 4 | ポインタ 8→4 B |
| processDoubleReplacing | 0x80 / 8 | 0x54 / 4 | ポインタ 8→4 B (engine は 0 埋め) |
| future | 0x88 / 56 | 0x58 / 56 | そのまま (不透明) |
| **sizeof** | **0xC0** | **0x90** | |

## 4. VstEvents / ERect (仕様の計算値・engine 側は未確認)

| 構造体 | 欄 | x64 off/size | x32 off/size |
|---|---|---|---|
| VstEvents | numEvents | 0x00 / 4 | 0x00 / 4 |
| VstEvents | reserved | 0x08 / 8 | 0x04 / 4 |
| VstEvents | events[0] | 0x10 / 8 | 0x08 / 4 |
| VstEvent | type / byteSize / deltaFrames / flags / data[16] | 0 / 4 / 8 / 12 / 16 | 同左 (ポインタ無し) |
| ERect | top / left / bottom / right (int16) | 0 / 2 / 4 / 6 | 同左 (ポインタ無し) |

- VstEvents の x32 側 `events[]` の要素は **ポインタ** (4 B)。 殻が渡す `VstEvent*` は 8 B 配列なので、要素を 1 件ずつ詰め直す必要がある (deep copy)。
- **未確認**: engine が `effProcessEvents` (opcode 25) で `numEvents` と `events[]` を読む箇所。 dispatcher (RVA 0x1000) は opcode で分岐せず、ホストの opcode を guest の関数へ渡すだけである。 読取箇所は別の関数にある。 次 run の対象 (§6)。
- ERect は engine の `effEditGetRect` の書込み先として想定されるが、engine 側の store は未確認。

## 5. ネガコン (`marshal.py --nega`)

| NC | 壊した入力・期待 | 期待 FAIL | 実測 |
|---|---|---|---|
| N1 | magic 即値を 1 bit 壊した複製 (値突合のみ、sha 検査は外す) | 値突合 | FAIL: `engine magic = 1450406993, want 1450406992` (HIT) |
| N2 | x32 sizeof 期待を 0xA0 に誤る | sizeof 突合 | FAIL: `x32 sizeof 0x90 != 0xa0` (HIT) |
| N3 | 期待 magic を 1 ずらす | 値突合 | FAIL: `engine magic @0x0 = 1450406992, want 1450406993` (HIT) |

`nega: 0/3 miss`。 gate 本体は `[marshal] OK` (exit 0)。

## 6. 未解決 (起票先: #674 の継続)

| 未解決 | 受入条件 | 起票先 |
|---|---|---|
| VstEvents / ERect の engine 側読取箇所 (effProcessEvents / effEditGetRect) の裏付け | 3 | #674 |
| 殻 (x64) 側の実物構造体の確認 (本表は `vst2_abi.h` の PoC 値を期待値に使用) | 3 | #674 |
| engine の store 値の実行確認 (静的のみ) | 4 (差分試験) | #674 |
| ia32 front-end 本体と `emcc -c` 通過 | 1 | #674 |
| x87 方針と f80 差分試験 | 2 | #674 |
| native vs wasm 差分試験 | 4 | #674 |
| LoadLibrary shim | 5 | #674 |
