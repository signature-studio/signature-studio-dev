# M11 REPORT #2714 (WIN-3): m11 路線の寛容起動 (tolerant boot)

親 #2712 / 関連 #132 (stage 5)・#134 (stage 6)・WIN-4 (`CreateFruityInstance` の呼出し、範囲外)。
本文の結論は `tools/m11/REPORT.md` §14 の続き。ここでは寛容起動の実測と、skip した unit の状態欠落リスクを書く。

## 0. 結論

- **寛容起動 (`tools/m11/m11_tolerant.mjs`) で 942 unit を全て試行した**。ok 874 / noproc 1 / skipped 67 (miss 46・halt0 7・oob 13・unreachable 1)。試行 942 = ok + noproc + skipped の和で、集計は合う。clobber 0。
- **DllMain の後段まで戻った**。終端の Halt0→longjmp が TRUE で戻った (`boot_rc=1`)。この終端は survey (InitUnits 抑止) と同じで (§6)、unit 状態の証拠にならない。
  **`CreateFruityInstance` を呼べるかは未検証**。呼出しは WIN-4 の範囲で、本 run は呼んでいない。欠落 67 unit がその経路に効くかも未検証。
- **ただし 67 unit (7.1%) が欠落している**。うち 46 unit は Init ポインタが `0xfa9390` (関数の先頭ではない値) で、Init が**一度も実行されていない**。
  残り 21 unit は途中で trap し、書いた状態が残っている。下の §4-2 の順位が、状態欠落による silent miscompile のリスク評価。正しさの証明ではない。
- **既存経路の判定値は不変**: 変更前 (origin/main `46c92356`) を同じ環境で走らせた値と、HEAD の値が一致した (§1)。strict は units_run 53 + skipped 3 = 56 完了で停止、survey は ok 872。
  回帰ゲート (`m11_tolerant_gate.py`) はこの 2 つを完全一致で見る。survey の FastMM 通算 GetMem だけ 4 件減った (§1 注。原因は未切り分け)。
- stage 5/6 は未達のまま (judge 判定)。stage 6 は Halt0 を含むため、寛容起動の終端 (Halt0→longjmp) は stage 6 の定義に当たらない (§6)。

## 1. 測定 (測定 commit `cf64d9c8`)

- 測定 commit: `cf64d9c8` (e2e を実行した HEAD)。e2e が実行するコードを最後に変えたのは `ed20a0ea` で、`cf64d9c8` 以降は e2e が呼ばない script のみ (§7)。base は origin/main `46c92356` (PR の base)。
- 環境: runner 4 vCPU・Node v22.23.3・emsdk は [EMSDK]・RetDec は [RETDEC] (いずれも `docs/REFERENCES.md`・runner に既存)。
  素材 work-m11 を両方の worktree に展開し、`m11_e2e.sh` が `m11_gen_ir2.sh` を実行して IR を作った (ldfix=applied・qstore=applied・ld108=applied・ir_sha256 `de46cada…`)。
  PE は `fl-win64` の `extracted/block00031_PE.bin` (sha256 `b2c64da4…`)。
- **注記 (素材の不足・手書き)**: 素材 work-m11 に `work/lift_pe.sha256` が無い。e2e は PE 指紋が一致しないと RetDec の全再生成に入るが、再生成に必要な `tools/m2/work` が無い。
  そこで**現 PE の sha256 を `work/lift_pe.sha256` に手で書いた** (全再生成はしていない)。IR の入力 `boot_final.ll` の sha256 (`69c774de…`) は REPORT_N98 §1・REPORT_N112 の記録と一致した。
- **変更前の実測 (同環境・base `46c92356`)**: REPORT.md §14 の survey 866 は、この環境 (IR `de46cada`) では再現しなかった。
  §14 の測定条件 (IR・PE) は本 REPORT から確認できないため、866 の原因は未切り分け。判定の基準は同環境の変更前実測 (872) とする (`e2e_expect.env` の pin)。

| 実行 | 変更前 (`46c92356`) | HEAD (`cf64d9c8`) | 差 |
|---|---|---|---|
| A 通常起動 (strict) units_run + units_skipped | 53 + 3 = 56 (停止: `unreachable` @ function_8c5eb0) | 53 + 3 = 56 (同じ) | 0 |
| B survey ok / noproc / miss / trap / clobber | 872 / 1 / 46 / 23 / 0 | 872 / 1 / 46 / 23 / 0 | 0 |
| B survey FastMM 通算 GetMem / fastmm_getmem_impl | 2034 / 2120 | 2030 / 2115 | **-4 / -5** (未切り分け・下の注) |
| C 寛容起動 (本 PR) | — | 942 試行・ok 874・noproc 1・skip 67・boot_rc=1 | — |

- 注 (survey の GetMem): survey の JSON 全キーを突き合わせると、差は `getmem`・`fastmm_getmem_impl` と `top_frame_idx` (wasm 関数番号の付け替え。追加した export の分だけずれた) の 3 系列のみ。
  ok・trap・miss・noproc・clobber・VA の値と unit 単位の kind は一致。GetMem の 4 件減の原因は**未切り分け**。判定 (ok 872) には入らないので、本 PR の受入の外に置く。
- 注 (停止種別): 変更前 (base) の A の停止は `unreachable` (REPORT.md §14 の Halt0 とは違う)。本環境では変更前後とも同じ unit `i=56` (VA 0x16fde0) で止まる。
- 所要時間 (一括 e2e `bash tools/m11/m11_e2e.sh`、n=1 の参考値。n≥3 は素材 (work-m11・emsdk・RetDec) が取れず未測定・§8): 変更前 2 分 36 秒 (gen_ir2・build を含む)・HEAD 2 分 56 秒 (同)・HEAD 増分 1 分 07 秒 (IR・build は前回の生成物を再利用)。
  寛容起動単体 (`node tools/m11/m11_tolerant.mjs`、n=3): 20.13 / 20.43 / 20.20 秒。
- C の詳細: GetMem 2028 / FreeMem 169 (寛容起動は別経路なので survey の 2030・2034 とは比べない)。VirtualAlloc 36 回・1,412.4 MB (survey と同値)・VA 上限 256 MB/unit (`M11_VA_UNIT_BUDGET_MB`、survey と同じ) で OOM 0。
  clobber (InitTable 先頭・末尾の VA 変化) 0。`longjmp_hit=8` = unit 内の Halt0 が 7 + 後段の終端 1。icall ok 2120・miss 46 (uniq 1 = `0xfa9390`)。

## 2. 寛容起動の仕組み

- **C (`tools/m11/m11_ov.c`)**: `g_tolerant=1` (`m11_set_tolerant`) のとき `function_4120c0` (System.InitUnits) は InitTable の `units` と `count` を 1 度だけ読み、JS の `Module.m11_tolerant_run` を呼んで返る。
  1 unit の呼出しは `m11_call_unit_at(units, i)`: strict の InitUnits ループ 1 周と同じ (`InitCount = i+1`・proc NULL なら 0・`ICALL_AT` の site `0x412126`)。
  既定 (`g_tolerant=0`) では strict・survey の分岐に入らない。survey の判定値 (ok・kind・VA) は変わらない (FastMM 通算 GetMem の差は §1 注)。
- **JS (`tools/m11/m11_tolerant.mjs`)**: 942 unit を try/catch で隔離し、trap 後は shadow stack を復元して次へ進む。
  survey と違い **image を戻さない** (状態は unit 間で持ち越す = 逐次起動の再現)。VA 予算は survey と同じ 256 MB/unit。
  InitTable 先頭・末尾の VA が変わったら `clobber` を数える。clobber の unit は kind を `clobber` として skip に入れる (ok・noproc でも同じ)。
  失敗 unit の前後で image の差分区間 (16 B 以内の隙間は同じ区間) を記録する。
- **判定 (`tools/m11/m11_tolerant_gate.py`)**: 試行 = 期待値 (942)・集計の整合 (ok + noproc + skipped = 試行、skipped = 種類別の和)・strict の完了数 (56)・survey の ok (872) を見る。
  `--negctl` は退行の合成入力 3 本 (試行 1 減・strict 完了数 1 減・survey ok 1 減) を判定し、どれも FAIL になることを確かめる。
  `m11_e2e.sh` の実行 C・ゲートとして組み込み、期待値は `e2e_expect.env` (`M11_EXPECT_STRICT_DONE=56`・`M11_EXPECT_SURVEY_OK_EXACT=872`)。pin を更新する手順は同ファイルに書いた。

## 3. 逐次 (寛容) と隔離 (survey) の差

- ok は 872 → 874。差は 2 unit だけ。**unit 304 (`0x483140`) と 555 (`0x7f2500`)** は survey では OOB だが、逐次では ok。
  前に走った unit が状態を作り、その後の unit が通ったもので、**状態依存**の例 (推定: 先行 unit が参照する領域を作ったため)。
- それ以外の 940 unit の kind は survey と一致 (miss 46・noproc 1・halt0 7・unreachable 1・oob 13 は survey の 15 から 2 減)。
- 1 unit の trap で後続が全滅する型 (スタック破壊・OOM の巻き添え) は**見られなかった**。OOM 0・clobber 0。後続の ok 数は survey と揃う。

## 4. skip 一覧と状態欠落リスク評価

### 4-1. 種類別の一覧 (i は survey と同じ 0 起算)

- **miss 46 unit**: `i` = 29, 38, 39, 105, 115, 121–125, 127, 131, 132, 196–203, 205–219, 225, 287–290, 292, 293, 356, 499, 913。
  全て Init ポインタが `0xfa9390`。`m11_icall` は closure 外の先を見つけると ret 0 で返すので、**この unit の Init 本体は一度も実行されない**。
  image 差分は 1 B ずつ (46 区間・合計 46 B)、全て `.bss` (`InitCount` の書込みのみ・`m11_tolerant_sections.py` の出力)。`0xfa9390` は PE の関数先頭ではない値 (REPORT.md §14 で確認済み)。出所は未確認。
- **trap 21 unit**: halt0 7 (`i` = 114, 245, 279, 314, 509, 647, 895)・oob 13・unreachable 1 (`i`=56 = strict の停止点)。

### 4-2. 状態欠落リスクの順位 (推定。image の差分のみ。heap の範囲は未計測)

表は `python3 tools/m11/m11_tolerant_sections.py <PE> --md` の出力 (入力 `work/tolerant_units.json`・測定 commit `cf64d9c8` の e2e が生成)。
画像の差分区間を PE の RVA のセクションに割った値 (B)。順位は `.text` B の降順、同じなら `.data`+`.bss` B の降順。
「他」の `(other)` は、どのセクションにも入らない RVA (セクション間の隙間) への書込み。`VA 要求` は `VirtualAlloc` の要求量、`GetMem / FreeMem` は unit 内の増分。

| 順位 | i | VA | 種類 | .text B | .data B | .bss B | 他 B | 区間数 | VA 要求 B | GetMem / FreeMem |
|---:|---:|---|---|---:|---:|---:|---|---:|---:|---|
| 1 | 280 | 0x416010 | oob | 9 | 50 | 33 | (other) 31 | 13 | 120,782,848 | 22 / 13 |
| 2 | 149 | 0x264260 | oob | 1 | 0 | 5 | (other) 7 | 4 | 0 | 4 / 4 |
| 3 | 314 | 0x4e48a0 | halt0 | 0 | 72 | 76 | (other) 1 | 17 | 0 | 31 / 1 |
| 4 | 114 | 0x223840 | halt0 | 0 | 77 | 67 | (other) 12 | 22 | 131,465,216 | 60 / 4 |
| 5 | 745 | 0xabb3b0 | oob | 0 | 53 | 46 | (other) 35 | 20 | 0 | 34 / 3 |
| 6 | 492 | 0x6d5700 | oob | 0 | 43 | 23 | 0 | 10 | 0 | 2 / 2 |
| 7 | 56 | 0x16fde0 | unreachable | 0 | 27 | 16 | 0 | 8 | 0 | 40 / 0 |
| 8 | 895 | 0xeddfe0 | halt0 | 0 | 22 | 6 | (other) 1 | 5 | 0 | 0 / 0 |
| 9 | 509 | 0x739ca0 | halt0 | 0 | 7 | 18 | 0 | 8 | 0 | 9 / 0 |
| 10 | 880 | 0xe63540 | oob | 0 | 12 | 9 | (other) 11 | 11 | 0 | 20 / 9 |
| 11 | 279 | 0x4136d0 | halt0 | 0 | 13 | 6 | 0 | 4 | 0 | 2 / 0 |
| 12 | 830 | 0xcd50d0 | oob | 0 | 8 | 5 | (other) 4 | 8 | 0 | 3 / 0 |
| 13 | 647 | 0x897ac0 | halt0 | 0 | 3 | 6 | 0 | 4 | 0 | 2 / 0 |
| 14 | 245 | 0x333090 | halt0 | 0 | 3 | 5 | 0 | 4 | 0 | 2 / 0 |
| 15 | 484 | 0x6d0680 | oob | 0 | 3 | 5 | 0 | 4 | 0 | 2 / 0 |
| 16 | 513 | 0x7654c0 | oob | 0 | 3 | 5 | 0 | 4 | 0 | 2 / 0 |
| 17 | 659 | 0x8eaa30 | oob | 0 | 1 | 7 | 0 | 4 | 21,299,200 | 2 / 0 |
| 18 | 477 | 0x6bfd60 | oob | 0 | 2 | 5 | 0 | 4 | 0 | 2 / 0 |
| 19 | 520 | 0x776bf0 | oob | 0 | 2 | 5 | 0 | 4 | 0 | 2 / 0 |
| 20 | 275 | 0x40e170 | oob | 0 | 1 | 5 | (other) 4 | 4 | 0 | 1 / 0 |
| 21 | 923 | 0xf6c660 | oob | 0 | 0 | 5 | 0 | 2 | 0 | 0 / 0 |

- miss 46 unit: image 差分 合計 46 B・区間 46 個 (セクション別: `.bss` 46)。

### 4-3. 上位の評価 (推定は推定と書く)

1. **`i`=280 (oob, `.text` 9 B 書換え)**: 最優先。REPORT.md §3 の 5 行目のとおり、Delphi は InitTable 等の定数表を `.text` に置く。書換えた 9 B がその表に当たれば、後続 unit と `CreateFruityInstance` の経路が**例外を出さずに誤った値を読む**恐れがある (推定。どの表の何バイトかは未特定)。
   VA 要求 121 MB は REPORT.md §12 の巨大 VA 要求と同型の疑い (推定)。
2. **`i`=149 (oob, `.text` 1 B)**: `.text` の 1 B のみだが、順位 1 と同じ型。1 B が有意かは未確認。
3. **`i`=314 (halt0, `.data` 72 B・`.bss` 76 B) と `i`=114 (halt0, `.data` 77 B・`.bss` 67 B, VA 131 MB)**: 初期化の途中で離脱。書いた globals の一部だけが設定された状態 (推定)。114 の VA 要求も同型の疑い (推定)。
4. **`i`=745 (oob, `.data` 53 B・`.bss` 46 B)**: 書込み量が多く、後続 unit の参照先に当たる可能性がある (推定)。
5. **`i`=56 (strict の停止点、unreachable, `.data` 27 B・`.bss` 16 B, GetMem 40)**: 寛容起動でも失敗のまま。後続 unit (57 以降は ok) が依存していないかは未確認。
6. **miss 46 unit (Init 未実行)**: 欠落の規模としては最大 (4.9%)。image 差分は `InitCount` の 1 B のみで、**この unit が担う globals は 0 のまま**。
   影響範囲は本 run で特定していない。CreateFruityInstance の経路 (S11 以降の Init core paths・ユーザデータ) が参照するかは WIN-4 で確認する (推定は未確認)。
   D17 (64bit 局所の縮退) と D19 (件数 0 のループ) との対応は未確認。出所が分かるまで既知の型とは断定しない。

**評価の限界**: (a) 成功した 874 unit の書込みは計測していない (image 差分を取るのは失敗 unit のみ)。
(b) heap の範囲は計測していない (GetMem・VirtualAlloc の増分のみ)。heap 範囲の計測は子 #2768 (`[M11-N155]`) に移管済み (親 #2714 の受入から外した)。(c) 「参照されうる」は推定で、参照の追跡はしていない。
(d) 本リスク一覧は**正しさの証明ではない** (docs/DEFECTS.md D17・D19 の型と同じく、差分から見た候補の列挙)。

## 5. 修復はしていない (範囲外)

skip した unit の修復はしていない。最後まで試行できたので、「スタック破壊で後続が全滅する」場合の回避策は必要なかった。
trap 21 unit の修復と miss 46 の `0xfa9390` の出所特定は、次の作業 (PM 判断) として PR 本文の未解決表に書く。

## 6. DllMain の後段 (unit の後) と終端

- InitUnits (reason=1) は `m11_InitLib` から直接 return する (`return function_4120c0()`)。その後段は `entry_point` 側に残り、本 run でも実行された。
- 終端の Halt0→longjmp (`function_412770`) は 1 回。**survey (InitUnits 抑止) でも同じ終端が起きる** (`DllMain done=True`)。
  つまり unit 由来ではなく、DllMain の後段の終端である。`boot_rc=1` は unit 後段の計算結果ではなく、終端の longjmp が setjmp 点で TRUE として戻った値。C のコメント (`function_412770`) も「実機では setjmp 点で TRUE が返る」としている。
  したがって `boot_rc=1` は「unit 状態が正しい」の証拠ではない。`CreateFruityInstance` を呼べる状態かは WIN-4 で確かめる。
- ただし `m11_judge.py` の stage 6 は「Halt0 無し・skip 0」を要求するため、寛容起動の結果は stage 6 に当たらない (skip 67 のため未達)。
  終端の扱いを judge の定義に入れるかは PM 判断。

## 7. 検証と差分

- 再現: `bash tools/m11/m11_e2e.sh` (`FL_WIN64_DIR` と work-m11 が要る。`lift_pe.sha256` は §1 の注記どおり手で書く)。
  寛容起動だけなら `M11_TOLERANT_OUT=work/tolerant_units.json node tools/m11/m11_tolerant.mjs`。
- 判定: `python3 tools/m11/m11_tolerant_gate.py --strict-done 56 --survey-ok 872` (exit 0)、`--negctl --strict-done 56 --survey-ok 872` (NEGCTL_OK ×3)。
- 区間内訳: `python3 tools/m11/m11_tolerant_sections.py <PE> --md` (§4-2 の表はこの出力)。
- コード差分 (測定 commit `cf64d9c8` → HEAD): `git diff cf64d9c8 HEAD -- tools/m11 ':!tools/m11/REPORT*.md'` は 25 files (1416 行追加・32 行削除)。内訳は次のとおり。
  - PR の script: `m11_tolerant_sections.py` (§4-2 の区間内訳)。
  - main 取り込み (`7a97f430`) で入った分: `ldfix/` の診断 script と結果 (`trap_units.mjs`・`trap_probe_942.mjs`・`probe_*.py`・`ld104_reach.py`・`ld120_*.py`・`ir_reach_2660.py`・`results/*`)・`shimx_link/build.sh` (`--midi` 追加と `sxt_*` の export を `--trace` 時だけに変更)・`trap_triage/`・各 REPORT。
- **e2e が実行するコードに差分は 0 件**: `m11_e2e.sh` の呼出し先 (`m11_gen_ir2.sh` → `ldfix/ldfix.py`・`ldfix/fix_ld108.py`・`qstore/m11_qstore.py`・`m11_passes.py` ほか、`m11_lift.sh`、`m11_build.sh`・`m11_ov.c`、`m11_run.mjs`・`m11_survey.mjs`・`m11_tolerant.mjs`・`m11_judge.py`・`m11_tolerant_gate.py`) のどれも、上の 25 files に含まれない。上の変更ファイルは、フルパス (`ldfix/trap_units.mjs` 等) で検索すると e2e の呼出し元から参照が無いことを確認した。
  よって §1 の測定値 (`cf64d9c8` の e2e 結果) は HEAD にそのまま当たり、再測定は要らない。
- e2e の実行コードを最後に変えた commit は `ed20a0ea`。`cf64d9c8` は `m11_tolerant_sections.py` の追加のみ (`git diff --stat ed20a0ea cf64d9c8 -- tools/m11 ':!tools/m11/REPORT*.md'`: 76 行追加)、`3722021f` は同 script の PE 引数の変更のみ。
  §4-2 の表は変更後の script で再生成し、変更前と同一 (diff 0) を確認した。

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| miss 46 unit の Init ポインタ `0xfa9390` (関数先頭ではない値・closure 外)。出所未確認 | 46 unit (4.9%) の初期化が丸ごと実行されない | PM 判断 (#132 の系統か、新規の子) |
| trap 21 unit の修復 (順位 1 の `.text` 書換え 9 B を含む) | skip 67 のため stage 5/6 未達 | #132 (範囲外として残す) |
| 失敗 unit の heap 範囲は未計測 → #2768 で計測 (`REPORT_N2768.md`) | 計測済み。成功 unit 側の heap は未計測 | 完了 (#2768) |
| 成功 874 unit の書込み範囲は未計測 | 成功 unit 側の状態欠落は見ていない | PR 本文の未解決表に留める (起票しない。#2768 の範囲外) |
| survey の FastMM 通算 GetMem -4 (fastmm_getmem_impl -5)。原因未切り分け | 判定には入らない (ok・trap は一致) | 本 PR の未解決表 (再測定の子は起票しない) |
| 寛容起動の終端 (Halt0→longjmp, boot_rc=1) を stage 6 に含めるか | judge の定義と食い違う | PM 判断 (judge の定義) |
| `CreateFruityInstance` の呼出しと、その経路の状態 (欠落 67 unit の影響) | 「呼べる状態」は未検証 | WIN-4 (#2715) |
| 巨大 VA 要求 (i=114 の 131 MB・i=280 の 121 MB・i=659 の 21 MB) | 同型の既知 (REPORT.md §12) | #132 |
| 素材 work-m11 に `lift_pe.sha256` が無い (手で書いた) | 再現時に同じ手順が要る | 依頼者 (素材の再梱包) |
