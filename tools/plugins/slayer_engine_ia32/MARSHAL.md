# tools/plugins/slayer_engine_ia32/MARSHAL.md — 殻 (x64) ↔ Slayer_Engine.dll (ia32) の VST2 構造体 marshal 表 (#674 受入 3)

- 担当 dir: `tools/plugins/slayer_engine_ia32/` のみ / 親 #536 / 本 issue #674 (受入 5 項目のうち 3 を対象)
- 再現・実測値: `tools/plugins/slayer_engine_ia32/REPORT.md` §9 を参照 (本書は仕様のみを持つ)
- 既知類型との関係 (`docs/DEFECTS.md`): 該当なし (構造体配置の静的表。 lift 出力は作らない)。

## 1. 結論

1. **engine (block22434) の AEffect 構築は 32bit SDK 配置 (sizeof 0x90)**。 殻の x64 配置 (sizeof 0xC0) とは全欄の offset が異なる。 表 §3 のとおり。
2. **engine の AEffect 構築 store 列は、引数由来の 2 欄 (numPrograms・numParams) を除き即値・既知レジスタ値で確定できる**。 引数由来の 2 欄は即値ではなく、呼出し元が値を決める (§3 の表の注)。 未 store の欄は ctor 冒頭の `rep stosd` で 0 埋めされる。
3. **ポインタ欄は全て 8→4 B**。 殻から見た AEffect のポインタ欄は、guest 空間 (ImageBase 基準の 32bit VA) の値として詰め直す。 数値の意味 (thunk 先) は変えない。
4. **VstEvents / ERect は仕様の計算値のみ**。 engine 側の読み取り箇所の裏付けは未取得 (§4)。

## 2. 検証の対象と限界

- 対象: engine の AEffect 構築関数 (ctor RVA 0x10E0〜0x1196)。 `this+0x20` に AEffect を置く。
- 検証は**静的** (capstone の逆アセンブル store 列)。 engine を実行していないので、store 値の正しさは実行で未確認。
- gate (`marshal.py`) が突合するのは、magic・numOutputs・version・ioRatio・uniqueID・numInputs・flags (即値)、object (`edx`)、numPrograms (`ebp`)、numParams (`eax`) の各欄。 引数由来の 2 欄は gate で「即値でなくレジスタ由来」であることを確かめる。
- 限界: 殻の x64 側の配置は `tools/hostbridge/poc/vst2_abi.h` の `_Static_assert` を期待値として使う (殻側の実物 C 構造体はこの PoC の値)。

## 3. marshal 表 (AEffect)

| 欄 | x64 (殻) off/size | x32 (engine) off/size | 変換 |
|---|---|---|---|
| magic | 0x00 / 4 | 0x00 / 4 | そのまま (`'VstP'` 0x56737450) |
| dispatcher | 0x08 / 8 | 0x04 / 4 | ポインタ 8→4 B |
| process | 0x10 / 8 | 0x08 / 4 | ポインタ 8→4 B |
| setParameter | 0x18 / 8 | 0x0c / 4 | ポインタ 8→4 B |
| getParameter | 0x20 / 8 | 0x10 / 4 | ポインタ 8→4 B |
| numPrograms | 0x28 / 4 | 0x14 / 4 | そのまま。 **engine 側は引数由来 (即値でない)**。 値は呼出し元が決める |
| numParams | 0x2c / 4 | 0x18 / 4 | そのまま。 **engine 側は引数由来 (即値でない)**。 値は呼出し元が決める |
| numInputs | 0x30 / 4 | 0x1c / 4 | そのまま |
| numOutputs | 0x34 / 4 | 0x20 / 4 | そのまま |
| flags | 0x38 / 4 | 0x24 / 4 | そのまま |
| resvd1 | 0x40 / 8 | 0x28 / 4 | ポインタ 8→4 B (host 所有) |
| resvd2 | 0x48 / 8 | 0x2c / 4 | ポインタ 8→4 B |
| initialDelay | 0x50 / 4 | 0x30 / 4 | そのまま |
| realQualities | 0x54 / 4 | 0x34 / 4 | そのまま |
| offQualities | 0x58 / 4 | 0x38 / 4 | そのまま |
| ioRatio | 0x5c / 4 | 0x3c / 4 | f32 bit 同一 |
| object | 0x60 / 8 | 0x40 / 4 | ポインタ 8→4 B (plugin 所有・host は不透明に扱う)。 **注: engine の store 値は `edx` (= this, AE の親ブロック)。 AEffect 自身を指さない** |
| user | 0x68 / 8 | 0x44 / 4 | ポインタ 8→4 B |
| uniqueID | 0x70 / 4 | 0x48 / 4 | そのまま |
| version | 0x74 / 4 | 0x4c / 4 | そのまま |
| processReplacing | 0x78 / 8 | 0x50 / 4 | ポインタ 8→4 B |
| processDoubleReplacing | 0x80 / 8 | 0x54 / 4 | ポインタ 8→4 B (engine は 0 埋め由来) |
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
- **未確認 (経路の静的実測・gate は観測値の回帰ガード)**: guest switch `0x10001300` は opcode 0..24 のみ処理し、`effProcessEvents` (25) は default (`0x1000149c`、逆アセンブル読取) で戻り値 0。 switch 内に VstEvents の読取は無い。 gate の `opcode25_default` は定数比較で、VstEvents の読取を証明しない。 読取箇所は未特定 (次 run の対象 §6)。
- ERect: `effEditGetRect` (13) は `[this+8]` の子オブジェクトの slot+4 へ転送する。 子 vtable は実行時に設定されるため、ERect 書込み箇所は静的に未特定。

## 5. ネガコン

`marshal.py --nega` で、壊した入力・誤った期待に対して gate が必ず FAIL することを確認する (N1: magic の 1 bit 破壊、N2: x32 sizeof 期待の誤り、N3: 期待 magic の誤り)。 結果と FAIL 文言の実測は REPORT.md §9。

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
