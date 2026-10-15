# ildsp GeneralPitchShifter vtable 転送先 0x161fc0 の closure lift (T-SH-61 #3299)

既知類型との関係: 該当なし (本 run は lift の前段まで。意味変換と wasm 化は未実施のため、DEFECTS の類型判定は子 issue で行う)。

## 結論 (1 行)

転送先 0x161fc0 を body 基準で選んだ。closure は直接 call と関数外への直接 jmp の辺で求める (67 関数・2,609 命令 (範囲の和) / 2,597 (一意))。閉包に間接 call 18・間接 jmp 6 があり、trap 化は未実装 (§2)。RetDec 段は素材 `toolchain-retdec` (RetDec v5.0) で再測定した: `define` 69・`__asm_*` 宣言 54 種・`gen_helpers.py` は `cvttss2si(i128)` で rc=1 停止 (§3)。

測定 commit: `f180a18d4` (main 取り込みの merge commit。main の `a99604b1a` が `ildsp_vtable.py` を変えたため、測定を取り直した)。`git diff f180a18d4 HEAD -- tools/shared/lift/ildsp/closure_select.py tools/shared/lift/ildsp/lift_vtable.sh tools/shared/scripts/ildsp_vtable.py tools/shared/scripts/ildsp_vtable_check.py tools/shared/env.sh tools/shared/lift/libkio tools/shared/lift/libreverb/gen_helpers.py` の出力は空 (差分 0)。

## 1. 選定 (3 候補の実測)

数え方: 「和」は各関数の範囲 (開始から最大の終端まで逆アセンブル) の命令数の和 (`closure_select.py` の `insn=`)。「一意」は同じ命令アドレスを 1 回だけ数えた数 (`insn_unique=`)。範囲が重なる箇所だけ両者が異なる。

| 転送先 | body 命令数 (.pdata) | closure 関数数 | closure 命令数 (和 / 一意) | 直接 call 辺 | 直接 jmp 辺 | 間接 call | 間接 jmp |
|---|---|---|---|---|---|---|---|
| 0x161fc0 | 324 | 67 | 2,609 / 2,597 | 84 | 7 | 18 | 6 |
| 0x162760 | 395 | 55 | 2,744 / 2,732 | 69 | 4 | 14 | 7 |
| 0x162f90 | 730 | 4 | 810 / 790 | 3 | 0 | 0 | 0 |

- 重なり: 0x161fc0 と 0x162760 は、関数 0x1be130 の範囲 (0x1be130-0x1be16d) の中の閉包の入口 0x1be13a (0x1be13a-0x1be16d の 51 バイト・12 命令) を和で二重計上している。0x162f90 は 0x1b2ec8 の範囲の中の入口 0x1b2f04 (0x1b2f04-0x1b2f3a の 54 バイト・20 命令)。
- body 基準 (issue 本文の 324 / 395 / 730) で最小の **0x161fc0** を選んだ。PM 判断 (#3321 のコメント) も 0x161fc0。closure 基準の最小は 0x162f90 (810 / 790 命令)。
- ネガティブコントロール: `closure_with_slots` の `direct_jmp_sites` を空にした JSON を `closure_select.py` に通すと 13 関数・1,119 命令に戻る (`f180a18d4` で再測定)。jmp 辺を辿らない閉包は過少で、以後の結論には使わない。
- 入力: #3299 本文は閉包の入力に `ildsp_closure.py` の出力を指定するが、実装は `ildsp_vtable.py` の出力 (`closure_with_slots` の `direct_call_sites`・`direct_jmp_sites`) を使う。理由: `ildsp_closure.py` は slot ごとの到達集合を出し、辺の一覧 (`direct_*_sites`) を出さないため、関数外への直接 jmp の辺を閉包に入れられないから (grep で確認)。

## 2. 閉包 0x161fc0 の間接分岐 (24 件)

閉包内の間接 call は 18 件、間接 jmp は 6 件。すべて `[rip+disp]` 形。

- import 名が付く 21 件 (call 16・jmp 5): IAT 経由で KERNEL32 の関数名が決まる (`ildsp_vtable.json` の `import`)。
- import 名が付かない 3 件 (call 2・jmp 1): 宛先の slot が `0x268260`・`0x268268` (file 値 `0x1801cb5e0`・`0x1801cb600`)。静的解析では宛先を確定していない。
- issue の 4 件 (`0x1aedc0` の 3 件と `0x1b6f4c` の 1 件) のうち、import 名が付かないのは `0x1aedf6`・`0x1b6f6c` の 2 件。`0x1aee04`・`0x1aee4a` は import 名が付く。到達経路 (BFS の親を辿った最短):
  - `0x161fc0 -call 0x162004-> 0x1ac9b8 -jmp 0x1ac9b8-> 0x1ac9c0 -call 0x1ac9f0-> 0x1ad008 -call 0x1ad022-> 0x1aedc0` (間接 call `0x1aedf6`・`0x1aee04`・`0x1aee4a`)
  - `0x161fc0 -call 0x162004-> 0x1ac9b8 -jmp 0x1ac9b8-> 0x1ac9c0 -call 0x1ac9ce-> 0x1b6f4c` (間接 call `0x1b6f6c`)

扱い: この PR では trap 化しない。子 [T-SH-70] #3346 に移す。wasm 化の前に、これらを lift が黙って通すことを防ぐ必要がある。main の `tools/shared/lift/ildsp/REPORT_APPENDIX_3346.md` (#3346) が同じ 24 件の宛先を分類している (分類の規則と結果は同付録が正本)。本 PR はその分類を入力に使わない。

## 3. RetDec 段 (測定 commit `f180a18d4` で再測定)

- 素材: `toolchain-retdec` を展開し、`RETDEC_BIN` に `retdec/bin/retdec-decompiler` を指定した (RetDec v5.0・commit `53e55b4b`)。`lift_vtable.sh` の RetDec 段は rc=0 で通る。
- 実測 (`--select-ranges` は閉包の 67 範囲): `[ildsp] retdec: 69 functions lifted`、`declare @__asm_*` 54 種。`ir_normalize` の後、`gen_helpers.py` が `declare i32 @__asm_cvttss2si(i128)` で停止 (rc=1)。前回記録 (69・54 種・`cvttss2si(i128)`) と一致する。
- `define` 69 と閉包 67 の差 2 件 (照合済み): RetDec の `define` の番地と閉包の範囲の先頭を比べると、RetDec にだけある番地は次の 2 件で、どちらも閉包の範囲の内側にある。残りの 67 件は閉包の範囲の先頭と一致する。
  - `0x1801bd4f0`: 閉包関数 0x1bd4b8 の範囲 (0x1bd4b8-0x1bd531) の内側。直前の `0x1801bd4e9` は無条件の間接 jmp (`jmp [rip+0xaad78]`)。`0x1801bd4f0` は prologue (`mov [rsp+8],rbx`) で始まる。
  - `0x1801be14e`: 閉包関数 0x1be130 の範囲 (0x1be130-0x1be16d) の内側。直前の `0x1801be14d` は `ret`。`ucomisd` で始まる。
  - どちらも閉包の直接 call / 直接 jmp 辺の宛先ではない (`ildsp_vtable.json` の `direct_call_sites`・`direct_jmp_sites` の宛先に無い)。`.pdata` の開始番地にも無い (`pefile` の例外ディレクトリで確認)。2 件とも無条件分岐 (jmp / ret) の直後の番地。RetDec がこれを独立の関数として切る基準は `[未確認]`。
  - 参考: 間接 jmp `0x1bd4e9` の飛び先 slot `0x268268` の値は `0x1801cb600` で、閉包の外。閉包内の間接分岐の扱いは [T-SH-70] #3346。
- `gen_helpers.py` は最初の未対応 op で rc=1 で止まるため、残りの未対応 op の全数は未測定。

## 4. 検証 (測定 commit `f180a18d4`)

```sh
FL_WIN64_DIR=<fl-win64 展開先> ILDSP_WORK=<作業先> RETDEC_BIN=<toolchain-retdec の bin/retdec-decompiler> bash tools/shared/lift/ildsp/lift_vtable.sh 0x161fc0
```

- `ildsp_vtable_check: ALL OK` (`ildsp_vtable.py` → `ildsp_vtable_check.py`。生バイト検算は `direct_jmp_sites` の照合を含まない。§5 の [T-SH-76] #3405)。
- `closure_select.py`: `body_insn=324`・`closure functions=67 insn=2609 insn_unique=2597 direct_call_edges=84 direct_jmp_edges=7 unresolved_edges=0`・`indirect_calls=18 indirect_jmps=6`。ranges は `1,608 B`。
- 再測定 (素材 `fl-win64` の `extracted/block24360_PE.bin` の sha256 先頭 12 桁 `f4b23b0f93ee`・`toolchain-retdec`): 前段の値は上と同じ。RetDec 段は rc=0、`gen_helpers.py` は rc=1 で停止 (§3)。
- 所要: `f180a18d4` で同じコマンドを 3 回直列に実行。real 1.76〜1.81 秒 (並列 1・実行直後の 1 分 load 0.39)。出力は初回実行と同一 (`diff` で確認)。作業出力は `$RUNNER_TEMP` 下 (`tools/**/work/` を使わない)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `gen_helpers.py` が `__asm_cvttss2si(i128)` で停止 (残りの未対応 op の全数は未測定) | 新 closure の wasm 化に進めない | [T-SH-63] #3316 |
| RetDec が閉包の範囲内の 0x1801bd4f0・0x1801be14e を独立の関数として出す理由 (閉包の辺の到達先ではない・.pdata に無し) | 閉包の関数の開始番地に無い 2 関数が RetDec の .ll に余分に入る。wasm 化で扱いを決める必要 | [T-SH-63] #3316 |
| 閉包内の間接 call 18 件・間接 jmp 6 件 (issue の 4 件を含む) の扱い (trap 化または静的解決) | 未処理のまま lift すると誤変換の恐れ | [T-SH-70] #3346 |
| vtable slot 5 (0x1aa470) の lift と差分テスト | slot 5 が未 lift | [T-SH-84] #3404 |
| 直接 jmp 辺 (`direct_jmp_sites`) の生バイト照合 | jmp 辺の検算が無い | [T-SH-76] #3405 |
| native と wasm の全バイト差分テスト・gate・ネガティブコントロール | 同一性の検証が無い | [T-SH-64] #3317 |

## 6. 受入条件の扱い (#3299)

| 受入条件 (#3299 の原文) | この PR の状態 |
|---|---|
| 3 転送先から最小の closure を選ぶ (根拠を REPORT に) | 達成 (§1) |
| RetDec → ir_normalize → gen_helpers → emcc で wasm 化 | 未達 ([T-SH-63] #3316。RetDec 段は §3) |
| native と wasm の全バイト比較 | 未達 ([T-SH-64] #3317) |
| ネガティブコントロールと gate | 未達 ([T-SH-64] #3317) |
| vtable slot 5 の lift と差分テスト | 未達 ([T-SH-84] #3404) |

本 PR で見つけて範囲外に分けたもの: 間接分岐の扱い ([T-SH-70] #3346)、jmp 辺の生バイト照合 ([T-SH-76] #3405)。

## 7. 検証範囲 / 範囲外

- 範囲内: closure の抽出 (`closure_select.py`・call と jmp の辺)・vtable 生バイト検算 (`ildsp_vtable_check.py`)・3 候補の再測定・RetDec 段の再実行と define の照合 (§3)。
- 範囲外: lift の意味変換の正しさ・wasm の生成・native との比較。どれも未実施。
