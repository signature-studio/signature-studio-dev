# ildsp GeneralPitchShifter vtable 転送先 0x161fc0 の closure lift (T-SH-61 #3299)

既知類型との関係: 該当なし (本 run は lift の前段まで。意味変換と wasm 化は未実施のため、DEFECTS の類型判定は子 issue で行う)。

## 結論 (1 行)

転送先 0x161fc0 を body 基準で選んだ。closure は直接 call と関数外への直接 jmp の辺で求める (67 関数・2,609 命令 (範囲の和) / 2,597 (一意))。閉包に間接 call 18・間接 jmp 6 があり、trap 化は未実装 (§2)。RetDec 段は素材 (`toolchain-retdec`) が無く、本 run では再測定できていない (§3)。

測定 commit: `7d27d51cf` (`closure_select.py` の一意数追加・`lift_vtable.sh` の注記を含む最後のコード commit)。`git diff 7d27d51cf HEAD -- tools/shared/lift/ildsp tools/shared/scripts tools/shared/env.sh` の出力は main 取り込みで増えた別の子 area のファイル (`ci_*`・`wc_*`・`REPORT.md` 等) のみで、本 pipeline の入力 (`ildsp_vtable.py`・`ildsp_vtable_check.py`・`closure_select.py`・`lift_vtable.sh`・`libkio`・`libreverb`・`env.sh`) には差分が無い。

## 1. 選定 (3 候補の実測)

数え方: 「和」は各関数の範囲 (開始から最大の終端まで逆アセンブル) の命令数の和 (`closure_select.py` の `insn=`)。「一意」は同じ命令アドレスを 1 回だけ数えた数 (`insn_unique=`)。範囲が重なる箇所だけ両者が異なる。

| 転送先 | body 命令数 (.pdata) | closure 関数数 | closure 命令数 (和 / 一意) | 直接 call 辺 | 直接 jmp 辺 | 間接 call | 間接 jmp |
|---|---|---|---|---|---|---|---|
| 0x161fc0 | 324 | 67 | 2,609 / 2,597 | 84 | 7 | 18 | 6 |
| 0x162760 | 395 | 55 | 2,744 / 2,732 | 69 | 4 | 14 | 7 |
| 0x162f90 | 730 | 4 | 810 / 790 | 3 | 0 | 0 | 0 |

- 重なり: 0x161fc0 と 0x162760 は、関数 0x1be130 の範囲 (0x1be130-0x1be16d) の中の閉包の入口 0x1be13a (0x1be13a-0x1be16d の 51 バイト・12 命令) を和で二重計上している。0x162f90 は 0x1b2ec8 の範囲の中の入口 0x1b2f04 (0x1b2f04-0x1b2f3a の 54 バイト・20 命令)。
- body 基準 (issue 本文の 324 / 395 / 730) で最小の **0x161fc0** を選んだ。PM 判断 (#3321 のコメント) も 0x161fc0。closure 基準の最小は 0x162f90 (810 / 790 命令)。
- ネガティブコントロール: 直接 jmp 辺を外して call 辺だけで閉包を求めると 13 関数・1,119 命令に戻る (旧値。測定 commit `372bbe95` の値と一致)。jmp 辺を辿らない閉包は過少で、以後の結論には使わない。
- 入力: #3299 本文は閉包の入力に `ildsp_closure.py` の出力を指定するが、実装は `ildsp_vtable.py` の出力 (`closure_with_slots` の `direct_call_sites`・`direct_jmp_sites`) を使う。理由: `ildsp_closure.py` は slot ごとの到達集合を出し、辺の一覧 (`direct_*_sites`) を出さないため、関数外への直接 jmp の辺を閉包に入れられないから (grep で確認)。

## 2. 閉包 0x161fc0 の間接分岐 (24 件)

閉包内の間接 call は 18 件、間接 jmp は 6 件。すべて `[rip+disp]` 形で、import 名が付かない (`.data` 側の slot)。静的解析では宛先を確定していない。

issue の 4 件 (`0x1aedc0` の 3 件と `0x1b6f4c` の 1 件) の到達経路 (BFS の親を辿った最短):

- `0x161fc0 -call 0x162004-> 0x1ac9b8 -jmp 0x1ac9b8-> 0x1ac9c0 -call 0x1ac9f0-> 0x1ad008 -call 0x1ad022-> 0x1aedc0` (間接 call `0x1aedf6`・`0x1aee04`・`0x1aee4a`)
- `0x161fc0 -call 0x162004-> 0x1ac9b8 -jmp 0x1ac9b8-> 0x1ac9c0 -call 0x1ac9ce-> 0x1b6f4c` (間接 call `0x1b6f6c`)

扱い: この PR では trap 化しない。子 [T-SH-70] #3346 に移す。wasm 化の前に、これらを lift が黙って通すことを防ぐ必要がある。

## 3. RetDec 段 (本 run では未再測定)

- 本 run の素材は `fl-win64` のみ (`$ARTIFACTS_DIR` に `toolchain-retdec` が無い。`retdec-decompiler` も PATH に無い)。`lift_vtable.sh` は RetDec 段で止まる (`retdec-decompiler: command not found`、終了コード 127)。
- PR 本文の `oc_artifacts` に `toolchain-retdec` を加えた。素材付きの run で `RETDEC_BIN=<toolchain-retdec の bin/retdec-decompiler>` を指定して測り直し、下の値を差し替える。
- 前回の実測 (出典の RetDec 本体は [未確認]。本 run では再現していない): `--select-ranges` で `define` 69、`declare @__asm_*` 54 種、`gen_helpers.py` が `declare i32 @__asm_cvttss2si(i128)` で停止 (rc=1)。
- `define` 69 と閉包 67 の差 2 件 (前回の RetDec 出力で確認された名前): `0x1bd4f0` (閉包関数 0x1bd4b8 の範囲 0x1bd4b8-0x1bd531 の内側) と `0x1be14e` (閉包関数 0x1be130 の範囲の内側)。両者は閉包の直接 call / jmp 辺の到達先ではない (`ildsp_vtable.json` に該当する辺が無い)。`closure_select.py` は範囲の内側の番地を関数として数えないため、RetDec が独立の関数として出す理由は未確認。素材付きの再測定で RetDec の出力と照合する。
- `gen_helpers.py` は最初の未対応 op で rc=1 で止まるため、残りの未対応 op の全数は未測定。

## 4. 検証 (測定 commit `7d27d51cf`)

```sh
FL_WIN64_DIR=<fl-win64 展開先> ILDSP_WORK=<作業先> RETDEC_BIN=<toolchain-retdec の bin/retdec-decompiler> bash tools/shared/lift/ildsp/lift_vtable.sh 0x161fc0
```

- `ildsp_vtable_check: ALL OK` (`ildsp_vtable.py` → `ildsp_vtable_check.py`。生バイト検算は `direct_jmp_sites` の照合を含まない。§5 の [T-SH-76] #3405)。
- `closure_select.py`: `body_insn=324`・`closure functions=67 insn=2609 insn_unique=2597 direct_call_edges=84 direct_jmp_edges=7 unresolved_edges=0`・`indirect_calls=18 indirect_jmps=6`。ranges は `1,608 B`。
- 本 run の再現 (素材 `fl-win64` の `extracted/block24360_PE.bin` の sha256 先頭 12 桁 `f4b23b0f93ee`): 上の前段は同じ値。RetDec 段で rc=127 (§3)。前段の所要は 0.26 秒 (1 回・並列 1・uptime の 1 分 load 0.05)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| RetDec 段の再測定 (`toolchain-retdec` 素材。define 数・宣言 op 種数・停止点の差し替え、define 69 と 67 の差 2 件の照合) | §3 の値が未再現 | 本 PR (`oc_artifacts` に `toolchain-retdec` を指定した次の run) |
| `gen_helpers.py` が `__asm_cvttss2si(i128)` で停止 (残りの未対応 op の全数は未測定) | 新 closure の wasm 化に進めない | [T-SH-63] #3316 |
| 閉包内の間接 call 18 件・間接 jmp 6 件 (issue の 4 件を含む) の扱い (trap 化または静的解決) | 未処理のまま lift すると誤変換の恐れ | [T-SH-70] #3346 |
| vtable slot 5 (0x1aa470) の lift と差分テスト | slot 5 が未 lift | [T-SH-75] #3404 |
| 直接 jmp 辺 (`direct_jmp_sites`) の生バイト照合 | jmp 辺の検算が無い | [T-SH-76] #3405 |
| native と wasm の全バイト差分テスト・gate・ネガティブコントロール | 同一性の検証が無い | [T-SH-64] #3317 |

## 6. 受入条件の扱い (#3299)

| 受入条件 (#3299 の原文) | この PR の状態 |
|---|---|
| 3 転送先から最小の closure を選ぶ (根拠を REPORT に) | 達成 (§1) |
| RetDec → ir_normalize → gen_helpers → emcc で wasm 化 | 未達 ([T-SH-63] #3316。RetDec 段は §3) |
| native と wasm の全バイト比較 | 未達 ([T-SH-64] #3317) |
| ネガティブコントロールと gate | 未達 ([T-SH-64] #3317) |
| vtable slot 5 の lift と差分テスト | 未達 ([T-SH-75] #3404) |

本 PR で見つけて範囲外に分けたもの: 間接分岐の扱い ([T-SH-70] #3346)、jmp 辺の生バイト照合 ([T-SH-76] #3405)。

## 7. 検証範囲 / 範囲外

- 範囲内: closure の抽出 (`closure_select.py`・call と jmp の辺)・vtable 生バイト検算 (`ildsp_vtable_check.py`)・3 候補の再測定。
- 範囲外: RetDec の再実行・lift の意味変換の正しさ・wasm の生成・native との比較。どれも未実施。
