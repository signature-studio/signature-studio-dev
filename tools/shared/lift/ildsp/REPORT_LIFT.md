# ildsp GeneralPitchShifter vtable 転送先 0x161fc0 の closure lift (T-SH-61 #3299)

既知類型との関係: 該当なし (本 run は lift の前段まで。意味変換と wasm 化は未実施のため、DEFECTS の類型判定は子 issue で行う)。

## 結論 (1 行)

転送先 0x161fc0 を body 基準で選定した。closure は直接 call と関数外への直接 jmp の辺で求める (67 関数・2,609 命令)。閉包内に間接 call 18・間接 jmp 6 があり、trap 化は未実装 (§2・§4)。RetDec 段はこの run で再実行できず、前回値は無効 (§3)。

測定 commit: `9c096c56` (`closure_select.py`・`lift_vtable.sh`・`ildsp_vtable.py` を含む最後のコード commit)。`git diff 9c096c56 HEAD -- tools/shared/lift/ildsp` は本ファイルの差分のみ。

## 1. 選定 (3 候補の実測)

同じ定義 (call 辺と関数外への jmp 辺で到達する関数の集合) で測定:

| 転送先 | body 命令数 (.pdata) | closure 関数数 | closure 命令数 | 直接 call 辺 | 直接 jmp 辺 | 間接 call | 間接 jmp |
|---|---|---|---|---|---|---|---|
| 0x161fc0 | 324 | 67 | 2,609 | 84 | 7 | 18 | 6 |
| 0x162760 | 395 | 55 | 2,744 | 69 | 4 | 14 | 7 |
| 0x162f90 | 730 | 4 | 810 | 3 | 0 | 0 | 0 |

- body 命令数は issue 本文の値 (324 / 395 / 730) と一致する。
- body 基準で最小の **0x161fc0** を選んだ (issue 本文どおり)。
- closure 基準 (lift する量) では **0x162f90 (810 命令)** が最小。どちらを選ぶかは PM 判断 (§4)。
- 旧 closure (call 辺のみ・測定 commit `372bbe95`) は 13 関数・1,119 命令だった。関数外への jmp 辺を辿っていなかったための過少値で、以後の結論には使わない。

## 2. 閉包 0x161fc0 の間接分岐 (24 件)

閉包内の間接 call は 18 件、間接 jmp は 6 件。すべて `[rip+disp]` 形で、import 名が付かない (`.data` 側の slot)。静的解析では宛先を確定していない。

issue の 4 件 (`0x1aedc0` の 3 件と `0x1b6f4c` の 1 件) の到達経路 (BFS の親を辿った最短):

- `0x161fc0 -call 0x162004-> 0x1ac9b8 -jmp 0x1ac9b8-> 0x1ac9c0 -call 0x1ac9f0-> 0x1ad008 -call 0x1ad022-> 0x1aedc0` (間接 call `0x1aedf6`・`0x1aee04`・`0x1aee4a`)
- `0x161fc0 -call 0x162004-> 0x1ac9b8 -jmp 0x1ac9b8-> 0x1ac9c0 -call 0x1ac9ce-> 0x1b6f4c` (間接 call `0x1b6f6c`)

扱い: この PR では trap 化しない。子 issue [T-SH-70] #3346 に移す (§4)。wasm 化の前に、これらを lift が黙って通すことを防ぐ必要がある。

## 3. 再現と実測 (測定 commit `9c096c56`)

```sh
FL_WIN64_DIR=<fl-win64 展開先> ILDSP_WORK=<作業先> bash tools/shared/lift/ildsp/lift_vtable.sh 0x161fc0
```

- `ildsp_vtable_check.py`: `ALL OK`。
- `closure_select.py`: `body_insn=324`・`closure functions=67 insn=2609 direct_call_edges=84 direct_jmp_edges=7 unresolved_edges=0`・`indirect_calls=18 indirect_jmps=6`。
- RetDec 段: RetDec 本体 (`RETDEC_BIN`) が無く、`toolchain-retdec` 素材も無いため、この run では実行できない (`rc=127`)。**RetDec・ir_normalize・gen_helpers の結果は、新しい closure について未測定。** 前回 (`372bbe95`) の `13 functions lifted`・`declare @__asm_*` の種類数 49・`cvttss2si` での停止は旧 closure の値で、無効。
- 所要 (lift.sh の RetDec 前段まで): 0.38 秒 (1 回・時間計測のみ)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| RetDec・ir_normalize・gen_helpers を新しい closure の ranges で再実行 (`toolchain-retdec` が必要) | 新 closure の lift 結果が無い | 本 PR の再起動 (`oc_artifacts: fl-win64 toolchain-retdec`) |
| 閉包内の間接 call 18 件・間接 jmp 6 件 (うち issue の 4 件) の扱い (trap 化または静的解決) | 未処理のまま lift すると黙って誤変換する恐れ | 子 [T-SH-70] #3346 |
| `gen_helpers.py` が扱えない SSE/AVX 命令 (lift 出力の宣言 op 名は旧 closure で 49 種) | wasm 化に進めない | [T-SH-63] #3316 |
| native と wasm の差分テスト・gate・ネガティブコントロール | 同一性の検証が無い | [T-SH-64] #3317 |
| 選定基準の不一致 (body 基準で 0x161fc0、closure 基準で 0x162f90 の 810 命令) | lift 量が増える | PM 判断 (#3299 のコメント) |
| `ildsp_vtable_check.py` は直接 jmp 辺 (`direct_jmp_sites`) を生バイトで照合していない | jmp 辺の検算が無い | 本 PR の残り (未実施) |

## 5. 受入条件の扱い

| 受入条件 (#3299) | この PR の状態 |
|---|---|
| 3 転送先から最小の closure を選ぶ (根拠を REPORT に) | 達成 (§1。基準の不一致は未解決) |
| RetDec → ir_normalize → gen_helpers → emcc で wasm 化 | 未達 (RetDec 段を新 closure で再測定できず・gen_helpers 以降は未達) |
| native と wasm の全バイト比較 | 未達 ([T-SH-64] #3317) |
| ネガティブコントロールと gate | 未達 ([T-SH-64] #3317) |
| 間接 call 4 件の扱い | 扱いは未実装。子 [T-SH-70] #3346 に移した (§2) |

## 6. 検証範囲 / 範囲外

- 範囲内: closure の抽出 (`closure_select.py`・call と jmp の辺)・vtable 生バイト検算 (`ildsp_vtable_check.py`)・3 候補の再測定。
- 範囲外: RetDec の再実行・lift の意味変換の正しさ・wasm の生成・native との比較。どれも未実施。
