# M11 REPORT #2714 (WIN-3): m11 路線の寛容起動 (tolerant boot)

親 #2712 / 関連 #132 (stage 5)・#134 (stage 6)・WIN-4 (`CreateFruityInstance` の呼出し、範囲外)。
本文の結論は `tools/m11/REPORT.md` §14 の続き。ここでは寛容起動の実測と、skip した unit の状態欠落リスクを書く。

## 0. 結論

- **寛容起動 (`tools/m11/m11_tolerant.mjs`) で 942 unit を全て試行した**。ok 874 / noproc 1 / skipped 67 (miss 46・halt0 7・oob 13・unreachable 1)。試行 942 = ok + noproc + skipped の和で、集計は合う。
- **DllMain は戻り値 1 (TRUE) で終端した** (`boot_rc=1`)。終端は 942 unit の後段 (unit の外) の Halt0→longjmp 1 回。
  `CreateFruityInstance` を呼べる状態 (S09 の DllMain 処理後) には**到達した**。呼出し自体は WIN-4 の範囲で、本 run は呼んでいない。
- **ただし 67 unit (7.1%) が欠落している**。うち 46 unit は Init ポインタが `0xfa9390` (関数の先頭ではない値) で、Init が**一度も実行されていない**。
  残り 21 unit は途中で trap し、書いた状態が残っている。下の §4 の順位が、状態欠落による silent miscompile のリスク評価。正しさの証明ではない。
- **既存経路は不変**: strict (通常起動) は units_run 53 + skipped 3 = 56 完了で停止、survey は ok 872。変更前の測定と同じで、回帰ゲート (`m11_tolerant_gate.py`) で完全一致を確認した。
- stage 5/6 は未達のまま (judge 判定)。stage 6 は Halt0 を含むため、寛容起動の終端 (Halt0→longjmp) は stage 6 の定義に当たらない (§6)。

## 1. 測定 (測定 commit `3c0019a6`)

- 測定 commit: `3c0019a6` (コードを変えた最後の commit。base は origin/main `46c92356`)。
  `git diff 3c0019a6 HEAD -- tools/m11 ':!tools/m11/REPORT*.md'` の出力は、本 REPORT を含めた最終 HEAD で 0 行 (§7)。
- 環境: runner 4 vCPU・Node v22.23.3・`/opt/emsdk`。素材 work-m11 を展開し、`m11_gen_ir2.sh` を実行して `ir_conditions.json` を作った (ldfix=applied・qstore=applied・ld108=applied・ir_sha256 `de46cada…`)。
  PE は `fl-win64` の `extracted/block00031_PE.bin` (sha256 `b2c64da4…`)。
- **注記 (素材の不足)**: 素材 work-m11 に `work/lift_pe.sha256` が無かった。e2e は PE 指紋が一致しないと RetDec の全再生成に入るが、再生成に必要な `tools/m2/work` が無い。
  そこで**現 PE の sha256 を `work/lift_pe.sha256` に手で書いた** (全再生成はしていない)。整合の確認: strict の完了数 53+3=56 は REPORT.md §14 と一致した。survey ok 872 は issue #2714 本文の値と一致した (REPORT.md §14 の survey 866 とは差がある。原因は未切り分け)。
- e2e: `bash tools/m11/m11_e2e.sh` (増分 build) 1 分 08 秒、load 0.13→0.78。rc 0 (judge は stage 4/6、回帰ゲート PASS、ネガコン NEGCTL_OK)。

| 実行 | 試行 | ok | noproc | skip (miss / halt0 / oob / unreachable) | 終端 | 所要 |
|---|---:|---:|---:|---|---|---|
| A 通常起動 (strict, 変更なし) | 53 完了 + skip 3 = 56 | 53 | — | 3 (miss) | unit `i=56` (VA 0x16fde0) の `unreachable` で throw | 同 e2e 内 |
| B survey (隔離, 変更なし) | 942 | 872 | 1 | 46 / 7 / 15 / 1 | DllMain done=True | 同 e2e 内 |
| C 寛容起動 (本 PR) | 942 | **874** | 1 | **46 / 7 / 13 / 1** | **boot_rc=1** (後段の Halt0→longjmp 1 回) | 約 20 秒 |

- 注: A の停止種別は REPORT.md §14 では Halt0 と記録されているが、本環境 (変更前後とも) は `unreachable` で throw する。同じ unit `i=56` で止まる点は一致する。
- C の詳細: GetMem 2028 / FreeMem 169 / VirtualAlloc 36 回・1,412.4 MB (survey と同値)・VA 上限 256 MB/unit (`M11_VA_UNIT_BUDGET_MB`、survey と同じ) で OOM 0。
  clobber (InitTable 先頭・末尾の VA 変化) 0。`longjmp_hit=8` = unit 内の Halt0 が 7 + 後段の終端 1。icall ok 2120・miss 46 (uniq 1 = `0xfa9390`)。

## 2. 寛容起動の仕組み

- **C (`tools/m11/m11_ov.c`)**: `g_tolerant=1` (`m11_set_tolerant`) のとき `function_4120c0` (System.InitUnits) は InitTable の `units` と `count` を 1 度だけ読み、JS の `Module.m11_tolerant_run` を呼んで返る。
  1 unit の呼出しは `m11_call_unit_at(units, i)`: strict の InitUnits ループ 1 周と同じ (`InitCount = i+1`・proc NULL なら 0・`ICALL_AT` の site `0x412126`)。
  既定 (`g_tolerant=0`) の経路 (strict・survey) は変えていない。
- **JS (`tools/m11/m11_tolerant.mjs`)**: 942 unit を try/catch で隔離し、trap 後は shadow stack を復元して次へ進む。
  survey と違い **image を戻さない** (状態は unit 間で持ち越す = 逐次起動の再現)。VA 予算は survey と同じ 256 MB/unit。
  InitTable 先頭・末尾の VA が変わったら `clobber` を数える。失敗 unit の前後で image の差分区間 (16 B 以内の隙間は同じ区間) を記録する。
- **判定 (`tools/m11/m11_tolerant_gate.py`)**: 試行 = 期待値 (942)・集計の整合・strict の完了数 (56)・survey の ok (872) を見る。`--negctl` は試行を 1 つ減らした合成入力で必ず FAIL になることを確かめる (NEGCTL_OK)。
  `m11_e2e.sh` の実行 C・ゲートとして組み込み、期待値は `e2e_expect.env` (`M11_EXPECT_STRICT_DONE=56`・`M11_EXPECT_SURVEY_OK_EXACT=872`)。

## 3. 逐次 (寛容) と隔離 (survey) の差

- ok は 872 → 874。差は 2 unit だけ。**unit 304 (`0x483140`) と 555 (`0x7f2500`)** は survey では OOB だが、逐次では ok。
  前に走った unit が状態を作り、その後の unit が通ったもので、**状態依存**の例 (推定: 先行 unit が参照する領域を作ったため)。
- それ以外の 940 unit の kind は survey と一致 (miss 46・noproc 1・halt0 7・unreachable 1・oob 13 は survey の 15 から 2 減)。
- 1 unit の trap で後続が全滅する型 (スタック破壊・OOM の巻き添え) は**見られなかった**。OOM 0・clobber 0。後続の ok 数は survey と揃う。

## 4. skip 一覧と状態欠落リスク評価

### 4-1. 種類別の一覧 (i は survey と同じ 0 起算)

- **miss 46 unit**: `i` = 29, 38, 39, 105, 115, 121–125, 127, 131, 132, 196–203, 205–219, 225, 287–290, 292, 293, 356, 499, 913。
  全て Init ポインタが `0xfa9390`。`m11_icall` は closure 外の先を見つけると ret 0 で返すので、**この unit の Init 本体は一度も実行されない**。
  image 差分は `.bss` の 1 B (`InitCount` の書込みのみ)。`0xfa9390` は PE の関数先頭ではない値 (REPORT.md §14 で確認済み)。出所は未確認。
- **trap 21 unit**: halt0 7 (`i` = 114, 245, 279, 314, 509, 647, 895)・oob 13・unreachable 1 (`i`=56 = strict の停止点)。

### 4-2. 状態欠落リスクの順位 (推定。image の差分のみで、heap の範囲は未計測)

順位は `.text` の書換えを最優先 (定数表を壊す型)、次に `.data`・`.bss` の書込み量。VA 要求と GetMem は同じ表に併記した。

| 順位 | i | VA | 種類 | .text B | .data B | .bss B | VA 要求 B | GetMem / FreeMem |
|---:|---:|---|---|---:|---:|---:|---:|---|
| 1 | 280 | 0x416010 | oob | 9 | 50 | 33 | 120,782,848 | 22 / 13 |
| 2 | 314 | 0x4e48a0 | halt0 | 0 | 72 | 76 | 0 | 31 / 1 |
| 3 | 114 | 0x223840 | halt0 | 0 | 77 | 67 | 131,465,216 | 60 / 4 |
| 4 | 149 | 0x264260 | oob | 1 | 0 | 5 | 0 | 4 / 4 |
| 5 | 745 | 0xabb3b0 | oob | 0 | 53 | 46 | 0 | 34 / 3 |
| 6 | 492 | 0x6d5700 | oob | 0 | 43 | 23 | 0 | 2 / 2 |
| 7 | 56 | 0x16fde0 | unreachable | 0 | 27 | 16 | 0 | 40 / 0 |
| 8 | 895 | 0xeddfe0 | halt0 | 0 | 22 | 6 | 0 | 0 / 0 |
| 9 | 509 | 0x739ca0 | halt0 | 0 | 7 | 18 | 0 | 9 / 0 |
| 10 | 880 | 0xe63540 | oob | 0 | 12 | 9 | 0 | 20 / 9 |
| 11 | 279 | 0x4136d0 | halt0 | 0 | 13 | 6 | 0 | 2 / 0 |
| 12 | 830 | 0xcd50d0 | oob | 0 | 8 | 5 | 0 | 3 / 0 |
| 13–21 | 647, 245, 484, 513, 659, 477, 520, 275, 923 | — | halt0 / oob | 0 | 0–3 | 5–7 | 0 (659 のみ 21,299,200) | 0–2 / 0 |

- 上の表の `.text` 以外のヘッダ・セクション間の書込みは、前回の集計で合計 106 B (`i`=280 が 31 B、745 が 35 B、880 が 11 B、114 が 12 B など)。個別には判定していない。

### 4-3. 上位の評価 (推定は推定と書く)

1. **`i`=280 (oob, `.text` 9 B 書換え)**: 最優先。REPORT.md §3 の 5 行目のとおり、Delphi は InitTable 等の定数表を `.text` に置く。書換えた 9 B がその表に当たれば、後続 unit と `CreateFruityInstance` の経路が**例外を出さずに誤った値を読む**恐れがある (推定。どの表の何バイトかは未特定)。
   VA 要求 121 MB は REPORT.md §12 の巨大 VA 要求と同型の疑い (size 算出の誤り・推定)。どの table の何バイトかは未特定。
2. **`i`=114 (halt0, `.data` 77 B・`.bss` 67 B、VA 131 MB)**: 初期化の途中で離脱。書いた globals の一部だけが設定された状態。VA 要求も同型の疑い (推定)。
3. **`i`=314 (halt0, `.data` 72 B・`.bss` 76 B)** と **`i`=745 (oob, `.data` 53 B・`.bss` 46 B)**: 書込み量が多く、後続 unit の参照先に当たる可能性がある (推定)。
4. **`i`=149 (oob, `.text` 1 B)**: `.text` の 1 B のみだが、順位 1 と同じ型。1 B が有意かは未確認。
5. **`i`=56 (strict の停止点、unreachable, `.data` 27 B・`.bss` 16 B, GetMem 40)**: 寛容起動でも失敗のまま。後続 unit (57 以降は ok) が依存していないかは未確認。
6. **miss 46 unit (Init 未実行)**: 欠落の規模としては最大 (4.9%)。image 差分は `InitCount` の 1 B のみで、**この unit が担う globals は 0 のまま**。
   影響範囲は本 run で特定していない。CreateFruityInstance の経路 (S11 以降の Init core paths・ユーザデータ) が参照するかは WIN-4 で確認する (推定は未確認)。
   D17 (64bit 局所の縮退) と D19 (件数 0 のループ) との対応は未確認。出所が分かるまで既知の型とは断定しない。

**評価の限界**: (a) 成功した 874 unit の書込みは計測していない (image 差分を取るのは失敗 unit のみ)。
(b) heap の範囲は計測していない (GetMem・VirtualAlloc の増分のみ)。(c) 「参照されうる」は推定で、参照の追跡はしていない。
(d) 本リスク一覧は**正しさの証明ではない** (docs/DEFECTS.md D17・D19 の型と同じく、差分から見た候補の列挙)。

## 5. 修復はしていない (範囲外)

skip した unit の修復はしていない。最後まで試行できたので、「スタック破壊で後続が全滅する」場合の回避策は必要なかった。
trap 21 unit の修復と miss 46 の `0xfa9390` の出所特定は、次の作業 (子 issue か PM 判断) として PR 本文の未解決表に書く。

## 6. DllMain の後段 (unit の後) と終端

- InitUnits (reason=1) は `m11_InitLib` から直接 return する (`return function_4120c0()`)。その後段は `entry_point` 側に残り、本 run でも実行された。
- 終端の Halt0→longjmp (`function_412770`) は 1 回。survey (InitUnits 抑止) でも同じ終端が起きる (`DllMain done=True`)。
  つまり unit 由来ではなく、DllMain の後段の終端である。C のコメント (`function_412770`) は「実機では setjmp 点で TRUE が返る」としている。`boot_rc=1` はこれと一致する。
- ただし `m11_judge.py` の stage 6 は「Halt0 無し・skip 0」を要求するため、寛容起動の結果は stage 6 に当たらない (skip 67 のため未達)。
  終端の扱いを judge の定義に入れるかは PM 判断。

## 7. 検証と差分

- 再現: `bash tools/m11/m11_e2e.sh` (`FL_WIN64_DIR` と work-m11 が要る。`lift_pe.sha256` は §1 の注記どおり手で書く)。
  寛容起動だけなら `M11_TOLERANT_OUT=work/tolerant_units.json node tools/m11/m11_tolerant.mjs`。
- 判定: `python3 tools/m11/m11_tolerant_gate.py --strict-done 56 --survey-ok 872` (exit 0)、`--negctl` (NEGCTL_OK)。
- 測定 commit `3c0019a6` から HEAD までのコード差分: 出力は §1 の注記のとおり 0 行 (本 REPORT のみの変更)。

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| miss 46 unit の Init ポインタ `0xfa9390` (関数先頭ではない値・closure 外)。出所未確認 | 46 unit (4.9%) の初期化が丸ごと実行されない | PM 判断 (#132 の系統か、新規の子) |
| trap 21 unit の修復 (順位 1 の `.text` 書換え 9 B を含む) | skip 67 のため stage 5/6 未達 | #132 (範囲外として残す) |
| 失敗 unit の heap 範囲は未計測・成功 unit の書込みは未計測 | 状態欠落のリスクが image の失敗 unit に限られる | 本 REPORT の限界 (§4-3) |
| 寛容起動の終端 (Halt0→longjmp, boot_rc=1) を stage 6 に含めるか | judge の定義と食い違う | PM 判断 (judge の定義) |
| 巨大 VA 要求 (i=114 の 131 MB・i=280 の 121 MB・i=659 の 21 MB) | 同型の既知 (REPORT.md §12) | #132 |
| 素材 work-m11 に `lift_pe.sha256` が無い (手で書いた) | 再現時に同じ手順が要る | 依頼者 (素材の再梱包) |
