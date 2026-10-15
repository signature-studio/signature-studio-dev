# PY-179 REPORT (#3271): patterns 数え・選択系 4 関数の C/mock 実装 (仮置き) と PE 確定事項

親: #3220 (PY-173)・#1804 (PY-48)。前段: `REPORT_PY173.md` (索引基準・述語の論理式)・`REPORT_PY172.md` (件数 0 の仮置きの型)。既知類型との関係: 該当なし (逆アセンブルの読解と実装のみ・lift 作業ではない)。

## 1. 結論

- **PE で確定: 達成。** isPatternDefault の範囲外は `-4` を `0xd82c20` へ渡す経路で、status -4 は文言 "Index out of range" = `FL_E_RANGE` (code 4)。patternNumber の slot の指す先の初期値は 1 (1 始まり)。
- **C provider・mock に 4 関数を実装: 達成 (値は仮置き)。** patternCount = 999・patternNumber = 1・isPatternDefault = 範囲 [1, 999] の外 code 4・それ以外 偽・isPatternSelected = 偽 (範囲検査なし)。値は PE の静的状態からの導出で、実行時の値は未実測。
- **未達 (子へ移す):** 述語の構造体 `E` の各フィールドの意味 → 子 #3536 (PY-210)。選択リスト `G+0x6ac` と `G` の初期化 → 子 #3537 (PY-211)。戻り値の型 (int/bool) → patternCount・isPatternDefault は子 #3536、isPatternSelected は子 #3537 (§2・§5)。
- **未実行:** `FL_ENGINE=wasm node tests/all_tools.mjs` の 48/48。wasm CPython (`dist/flpy.js`) と `work/midi.py` が要り、本 run では用意できなかった (§5)。

## 2. 関数ごとの事実と実装 (根拠: PE の VA・section 実測)

| 関数 | C/mock の値 | 根拠 (PE) | 確定 / 仮置き |
|---|---|---|---|
| patternCount | 999 | `0xd64d40`: `i = 1..999` で `pred(i,1,0,0)` が偽のものを数える。`E = 0x193fce0+i*0xc0` は section `.bss` (raw サイズ 0) で、全 0 から `byte[E+0x84]=0` → pred 偽 → 全 999 を数える | 仮置き (述語テーブル未投入を仮定) |
| patternNumber | 1 | `0xd64d20`: `*(int*)(*(void**)0x15e4018)`。slot `0x15e4018` (.data) の中身は `0x15d51a0` (.data)、その dword は `01000000` = 1 | 初期値は確定。実行中の書込み元は未確定 (#3536) |
| isPatternDefault | `1 ≤ i ≤ 999` で偽、範囲外は code 4 | `0xd66060`: `cmp rax,1`・`cmp rax,0x3e7`。範囲外は `-4` → `0xd82c20`。文言対応は `REPORT_PY61.md` §8 (`-4` ↔ "Index out of range") | 範囲と code は確定。値 (偽) は仮置き (`pred(i,1,1,1)` が E 全 0 から偽) |
| isPatternSelected | 偽 (範囲検査なし) | `0xd65ff0`: 引数 `i-1` を `0xea7420` へ渡す。`G = [[0x15e35c8]+0xd34]`。`[0x15e35c8]` (.data) = `0x16ba808`、その `+0xd34` は 0 (raw 外で zero 埋め)。G が null の経路は `0xd82c20(1)` の戻り値 `[0x16b82e0]` (.bss 0) をそのまま返す = 偽 | 偽は静的状態からの導出 (G 未確定・#3537) |

- `G` の null 経路で返す `[0x16b82e0]` は変換スロットを通らず、C/mock では偽 (0) として扱う。REPORT_PY173 §2 の型の不揃いは、本実装では値 0 に揃う。
- 索引基準 (1 始まり・0 始まり) は REPORT_PY173 §1 の通り。本 PR で変えない。
- **型は仮置き**: patternCount・patternNumber は int (`fl_ret_i`)、isPatternDefault・isPatternSelected は bool (`fl_ret_b`)。変換スロット `0x15e4280` は int と bool で共通に呼ばれ (REPORT_PY173 §2)、PE からは呼出し側の型を区別できない。型の確定は子 #3536・#3537 (§5)。

### 訂正 (REPORT_PY100 §4b)

REPORT_PY100 の表「`patternNumber()` (0xd64d20 が読む slot) `0x15e4018` は `int` を返す」は一段足りない。slot の中身はポインタ (`0x15d51a0`)、int はそのポインタの指す先の dword (= 1)。`REPORT_PY100.md` 本文は書き換えず、この訂正をここに記す (REPORT_PY173 §2 の注と同じ)。

## 3. 差分検査と検証

測定 commit: `35b9b764b` (`Merge remote-tracking branch 'origin/main' into 3271-pattern-impl`。コードを変えた最後の commit)。`5a41297b5` で測った後に main を取り込み、`git diff c6fb962e2 35b9b764b -- tools/python/provider tools/python/host tools/python/tests` で main 側の変更 (4 files・76 行追加・3 行削除。#1529 の channels 5 関数の C・mock 実装と `channels_diff.mjs`・件数 assert) が入った。ハンドラ数が 148 から 153 に変わったため、merge 後の HEAD で全項目を再測定した。以後の commit は本 REPORT の文言だけを変える。

| コマンド | 結果 | wall (n=3 の min–max) | load (1 分値・各回の開始時) |
|---|---|---|---|
| `bash tools/python/provider/build.sh` (emcc は `[EMSDK]`) | rc 0。`fl_table.c: 435 関数, ハンドラ 153` (実装数 153 と一致) | 810–857 ms | 0.47 |
| `node tests/patterns_diff.mjs` (25 呼出し: 戻り値・範囲・個数・型) | `{"calls":25,"diffs":0,"PASS":true}` rc 0 (n=3 とも同じ) | 41–43 ms | 0.47 |
| `node tests/patterns_group_diff.mjs` (PY-172 の回帰) | `{"calls":14,"diffs":0,"PASS":true}` rc 0 (n=3 とも同じ) | 41–43 ms | 0.47 |
| ネガティブコントロール: `fl_engine.c` の `PAT_N` を 998 に壊して build → `patterns_diff.mjs` | rc 1・`patterns 数え・選択系 差分 2 件` (patternCount と isPatternDefault(999)) | 単発 (未計測) | 未計測 |
| 同 (`PAT_N` を 999 へ戻して build → 再実行) | rc 0・`diffs 0`。`fl_engine.c` は元に戻した (`git diff` 空) | 単発 (未計測) | 未計測 |
| `node tests/provider_check.mjs` | 件数 assert (line 76: `impl 153`・`unimpl 282`) 通過。line 128 の既存 flpy 部 (`work/midi.py` 無し) で ENOENT 停止 | 単発 (未計測) | 0.48 |
| `FL_ENGINE=wasm node tests/all_tools.mjs` | 未実行 (`dist/flpy.js` と `work/midi.py` が本 run に無い。`build_cpython_wasm.sh` が前提) | — | — |

測定環境: `nproc` 4・並列数 1 (直列実行)。wall は `date +%s%N` の差 (ms)。load は `/proc/loadavg` の 1 分値。build の初回 (cold) は 1194 ms・load 0.62 で、表の n=3 には含めない。

- 測定 commit から HEAD までの差分 (本 REPORT の commit 後に実行。差分 0 行): `git diff 35b9b764b HEAD -- tools/python/provider tools/python/host tools/python/tests` (出力 0 行)。
- ネガティブコントロールは「期待値を壊すと FAIL する」ことの確認。C と mock を同時に壊すケースは検出できない (mock は独立に書いた値で照合する)。
- 検証範囲: C provider の 4 関数の戻り値・code と mock の一致。範囲外: 実行時の値 (仮置き)・型 (§2)・flpy 経由の Python 呼出し・`all_tools.mjs`。

## 4. 再現

```
bash tools/python/provider/build.sh                       # rc 0 (EMSDK_ENV 既定は [EMSDK] の emsdk_env.sh)
cd tools/python && node tests/patterns_diff.mjs           # {"calls":25,"diffs":0,"PASS":true}
cd tools/python && node tests/patterns_group_diff.mjs     # {"calls":14,"diffs":0,"PASS":true}
FL_WIN64_DIR=<fl-win64 展開先> python3 analysis/flapi/pe_pattern_probe.py   # rc 0 (REPORT_PY173 §7)
```

`<fl-win64 展開先>` は `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'` で得る。静的確認 (section・dword・ポインタ) は同じ `block00031_PE.bin` を `pefile` で読んだ一時スクリプトで行い、その値を §2 に書いた (スクリプトは work 外に残さない)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 述語の構造体 `E` の各フィールドの意味と `[E+0x20]`・`[E+0x28]` の指す先 | patternCount (999)・isPatternDefault (偽) が仮置き | 子 #3536 (PY-210) |
| `E` の投入箇所 (仮置きの前提「未投入」が実起動で起きるか) と patternNumber の実行中の書込み元 | 同上・patternNumber の実行時の値 | 子 #3536 (PY-210) |
| 選択リスト `G+0x6ac` の書込み元とレコードの内容・`G` の初期化・G が null のときの `[0x16b82e0]` の意味 | isPatternSelected (偽) が仮置き | 子 #3537 (PY-211) |
| `FL_ENGINE=wasm node tests/all_tools.mjs` 48/48 と `provider_check.mjs` の flpy 部 (`dist/flpy.js`・`work/midi.py` が要る) | 受入 7 は未実測。flpy 経路の回帰も未検証 (既存の未検証範囲・PY-157 と同じ) | 子 #3536・#3537 の PR で実測する (再測定だけの子は起票しない) |
| probe (`pe_pattern_probe.py`) は分岐の飛び先を検査しない (REPORT_PY173 §5) | 同種の分岐の読み違いを probe が検出しない | 子 #3536 の PR で扱う (実装に直結する分)。残りは #3220 |
| 4 関数の戻り値の型 (int/bool)。変換スロット `0x15e4280` は int と bool で共通で、PE から区別できない | 型は仮置き (patternCount・patternNumber = int、isPatternDefault・isPatternSelected = bool)。呼出し側の読みで変わり得る | patternCount・isPatternDefault → 子 #3536 (PY-210)、isPatternSelected → 子 #3537 (PY-211) の受入へ追記 (両 issue の本文に追記済み) |
