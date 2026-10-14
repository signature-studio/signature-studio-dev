# liftdiff REPORT 付録: LD-133 (#2821) HeapFree 応答の統一後の再測定

親 #2193 (LD-84)。前提は `REPORT_APPENDIX_LD84.md` §4 (最初の分岐は `1c0b71` の HeapFree 戻り値)。
既知類型との関係: D24 (LD-84 の行案) は本付録で解消 (wasm の応答を native に揃えた)。新類型 D25 の行案は §4 (`docs/DEFECTS.md` は PM 編集)。

## 結論

- 受入 1 (応答表の統一): 前 run の PR #3049 (merge 済み。shim の commit `7278e857`) で wasm の HeapFree を native 参照 (`tools/liftdiff/rt/ld_core.h:430`) と同じ応答 (TRUE) に揃えた。決定は `tools/shim/REPORT.md` §6。
- 受入 2 (再測定): 1c5e84・1c621c・1c682c・1c69cc の vm0/u16 (計 8 case) の wasm block 入口列は、**native と全件一致** (共通接頭辞 = wasm 入口数 = native 入口数)。LD-84 で 8 case すべてにあった分岐 (`1c0b71` の HeapFree 戻り値による) は消えた。分岐点の原因を示す必要は無い。
- 受入 3 (測定 commit と差分): 測定 commit `0dc0aa4b` (計測コードの最後の変更)。`git diff 0dc0aa4b HEAD -- <範囲>` は 0 行 (§5)。
- 残った差は block 列の外にある (§4): 8 case の `outcome` は依然 `diff`。原因は (a) import 呼出し記録の差 (計装上の差、8 case)、(b) `sext i1` による rax の差の疑い (6 case。IR の機構は確認。rax の差との因果は未検証で推定)、(c) 1c621c の rax の差 (2 case。未特定)。

## 1. 測定条件

- 測定 commit: `0dc0aa4b` (範囲 `tools/shim/src tools/shim/test tools/liftdiff/liftdiff.py tools/liftdiff/targets tools/liftdiff/rt tools/liftdiff/ldlib tools/liftdiff/results/ld67/compare_blk.py tools/liftdiff/results/ld57 tools/liftdiff/results/ld84/ld84_block_map.py tools/ott/rt tools/m6 tools/m8 tools/m9 tools/m10` で最後に変わった commit)。run の HEAD は `e9881327` (origin/main)。範囲の内容は両者で同じ (§5)。
- 作業ツリー: `ws-2821` (branch `2821-ld84-remeasure`、base `origin/main` の `e9881327`)。
- 素材 (本 run で `ls` 確認済み):
  - `work-m6-ott` → `tools/{m6,m8,m9,m10,ott}/work/`。worktree へ複製 (main の共有ツリーには書いていない)。`tools/ott/work/ott.ll` は 957,145 B・sha256 `989cf685e9091c0a1d4a01e7a6b89f7f5bf4da75d5962be8bfd533db8797cd3f`。
  - `analysis-ott-binaries` → `[ANALYSIS-DIR]/plugins/ott/binaries/OTT_vst2_win64.dll` (PE の逆アセンブル用)。
  - `toolchain-emsdk` → `[EMSDK]` (`emcc`)。
  - `work-liftdiff` は使っていない。`ott_old` と `ott_old_blk` は worktree で新規に build した (旧 build は #3049 より前の `heap.c` を含むため)。
- 実行 (n=1。所要は参考値で結論には使わない。並列数 1):
  - 計装版: `cd tools/liftdiff && python3 liftdiff.py run targets/ott_old_blk.json --fn 0x1801ab1d0,0x1801ab258,0x1801c5e84,0x1801c621c,0x1801c682c,0x1801c69cc --pattern vm0,u16 --notrace -v --json work/ld84/blk_all.json` (build+run 12.29 s wall。build は `heap.c` を含めて新規)
  - 既定版: 同じ引数で `targets/ott_old.json`・`work/ld84/def_all.json` (11.35 s wall。新規 build)
  - 比較: `python3 results/ld67/compare_blk.py work/ld84/def_all.json work/ld84/blk_all.json` → `cases=12 diff=0`
  - 対応表: `python3 results/ld84/ld84_block_map.py` → `results/ld84/block_map_<fn>_<pat>.tsv` (8 ファイル更新)・要約は `work/ld84/map_summary.txt`
- load average: 測定終了時 `0.08 0.20 0.15` (`uptime` 23:06 UTC)。

## 2. 既定版と計装版の比較 (12 case)

既定版と計装版の outcome は 12 case 全て一致 (`cases=12 diff=0`)。計装による戻り値・outcome の変化は無い。

| 関数 | pattern | outcome (既定 = 計装) | wasm_status | 計装 blk 件数 |
|---|---|---|---|---|
| 1ab1d0 | vm0 / u16 | equal / equal | ok / ok | 4 / 4 |
| 1ab258 | vm0 / u16 | equal / equal | ok / ok | 4 / 4 |
| 1c5e84 (参照) | vm0 / u16 | diff / diff | ok / ok | 18 / 22 |
| 1c621c | vm0 / u16 | diff / diff | ok / ok | 278 / 283 |
| 1c682c | vm0 / u16 | diff / diff | ok / ok | 33 / 34 |
| 1c69cc | vm0 / u16 | diff / diff | ok / ok | 286 / 291 |

LD-84 (§2) では 1c5e84・1c621c・1c69cc の u16 が `wasm_trap` だった。#3049 後は trap が消え、outcome は `diff` になった。

## 3. 対応表 (native 入口 ↔ wasm 入口) の旧と新

native 入口数は LD-84 と同じ (変わらない)。wasm 入口数と共通接頭辞が変わった。

| 関数 | pattern | wasm 入口数 旧→新 | native 入口数 | 共通接頭辞 旧→新 | 最初の不一致 旧 → 新 |
|---|---|---|---|---|---|
| 1ab1d0 | vm0 / u16 | 4 → 4 / 4 → 4 | 4 / 4 | 4 → 4 / 4 → 4 | — → — |
| 1ab258 | vm0 / u16 | 4 → 4 / 4 → 4 | 4 / 4 | 4 → 4 / 4 → 4 | — → — |
| 1c5e84 (参照) | vm0 | 27 → 18 | 18 | 4 → 18 | k=4 (`1c0b8c`/`1c0ba8`) → なし |
| 1c5e84 (参照) | u16 | 4 → 22 | 22 | 4 → 22 | wasm trap → なし |
| 1c621c | vm0 | 287 → 278 | 278 | 6 → 278 | k=6 → なし |
| 1c621c | u16 | 6 → 283 | 283 | 6 → 283 | wasm trap → なし |
| 1c682c | vm0 | 42 → 33 | 33 | 32 → 33 | k=32 → なし |
| 1c682c | u16 | 43 → 34 | 34 | 33 → 34 | k=33 → なし |
| 1c69cc | vm0 | 304 → 286 | 286 | 10 → 286 | k=10 → なし |
| 1c69cc | u16 | 10 → 291 | 291 | 10 → 291 | wasm trap → なし |

- 新の 12 case は全て `identical=True` (wasm 入口数 = 共通接頭辞 = native 入口数)。
- 非 label への切替 (anomaly) の件数は LD-84 §6 と一致 (`jne 0x1801c0ba3` 由来が中心。1c5e84 vm0 1・u16 5、1c621c 1・6、1c682c 1・1、1c69cc 2・7、1ab1d0 と 1ab258 は各 1)。
- ネガティブコントロール (スクリプト内): 一致 case (1801ab1d0 vm0) の `wasm[1]` を `wasm[0]` に置換 → `prefix=1` (期待どおり不一致)。

## 4. 残った outcome の差の原因

8 case (1c5e84・1c621c・1c682c・1c69cc の vm0/u16) の `outcome` は `diff`。block 入口列は一致したので、これは block 列の外の差である。

**(a) import 呼出し記録の差 (8 case 全て・計装上の差)**: native の記録には HeapFree の呼出しが出るが、wasm の `raw.wasm.calls` には出ない。shim の HeapFree は IAT import stub ではなく shim の関数として呼ばれるため (LD-84 §4 の注記と同じ)。block 列には影響しない。

**(b) rax の差: 1c5e84 (vm0/u16)・1c682c (vm0/u16)・1c69cc (vm0/u16) の 6 case**: native `rax=1`、wasm `rax=0xffffffffffffffff`。
- IR の機構 (`tools/ott/work/ott.ll`、`function_1801c0b6c` の block `1c0b71`): `%4 = call i1 @HeapFree(...)` → `%5 = sext i1 %4 to i64` → `store i64 %5, ptr %rax.0.reg2mem` → `ret i64`。TRUE を `sext` すると -1 になる。
- native の観測は rax=1。BOOL の戻り値 (eax=1) が 0 拡張されたためかは未確認 (推定)。
- rax の値の出典 (未コミット): `tools/liftdiff/work/ld84/blk_all.json` (計装版 run の出力。`results/` には無い)。要素のうち `function.va` が該当 VA (例 `0x1801c5e84`) のものの `cases[]` で、`pattern` が vm0 か u16 の case。`cases[].raw.native.rax` が native、`cases[].raw.wasm.rax` が wasm。`raw` は `outcome` が `diff`・`wasm_trap` の case にだけ入る。
- **試験は未実施 (推定)**: `sext` を `zext` に置き換えた場合の rax は測っていない。`tools/ott/work/` は書き換えない (AGENTS.md 禁止事項 4)。(b) の原因が `sext` であるかは推定にとどまる。検証は子 #3180 (LD-147) の受入で、`work/` の外の複製により行う。
- 影響範囲: `ott.ll` の `call i1 @` は 18 件 (WriteFile 6 件、WriteConsoleW 2 件、IsProcessorFeaturePresent 2 件 ほか)。BOOL 戻り値の型幅の扱いは HeapFree 固有ではない。sext の実影響は未検証。
- 新類型の行案 (`docs/DEFECTS.md` は PM 判断で編集するため、ここに残す):

| D25 | fe (機構は IR で確認。型決定の段は推定) | **新規** (LD-133 / #2821 で発見) | Win32 BOOL の import 戻り値を `i1` で受け、`sext i1→i64` で rax に入れる。TRUE が `0xffffffffffffffff` になる疑い (native は eax=1 で rax=1) | BOOL の戻り値幅の決め方 (`i1` 宣言 + `sext`)。`ott.ll` の `function_1801c0b6c` `1c0b71` で機構を確認 | **未試験** (推定)。rax 差との因果は未検証 | 子 #3180 (LD-147・親 #2821)。DEFECTS.md への登録の要否は PM agent の判断待ち・既定案: #3180 の検証結果が出るまで登録しない |

**(c) 1c621c (vm0/u16) の rax の差**: native `0x1720f22a0` (heap ポインタ)、wasm `0x1801c5e84` (1c5e84 の VA と同じ値)。出典は上の (b) の行と同じ。原因は未特定 (推定もしない)。原因の特定は子を作らず、#2801 (LD-131) へのコメントで追跡する。

## 5. 測定 commit と差分

- 測定 commit: `0dc0aa4b`。`git merge-base --is-ancestor 0dc0aa4b HEAD` で HEAD の祖先であることを確認。run の HEAD は `e9881327`。
- 範囲 (§1) の `git diff 0dc0aa4b HEAD -- <範囲>` の出力は **0 行** (差分なし)。よって計測コードに対する再測定は不要。上の数値は HEAD の計測コードで得た値に等しい。
- 参考: 旧測定 commit `7278e857` (#3049) から `0dc0aa4b` までは範囲内に 64 行の差がある (`tools/shim/test/test_main.c` ほか。他の PR による変更で、本付録の数値には入っている)。

## 6. 検証範囲・範囲外

- 範囲内: 6 関数 (1c5e84 は参照) × vm0/u16 の計装版 wasm trace と、既存の native 実行トレース (`results/ld57/`・追跡済み)。native トレースは再取得していない (n=1)。
- 範囲外: 命令単位の wasm trace (IR に元の VA が無い。#2192 / LD-83)。実機 Windows の HeapFree の無効 p の応答 (未検証)。GlobalFree・LocalFree の範囲外の応答 (`tools/shim/REPORT.md` 側の未解決)。
- 「block 入口列が一致する」の判定は、スクリプトの label 一致法と、区間法の検算 (非 label 切替の件数) で行った。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| BOOL 戻り値の `i1` + `sext` (D25 行案 §4 (b)) | 6 case の rax 差の疑い (TRUE が -1)。`ott.ll` の `call i1` 18 件に同じ型決定。因果は未検証 | 子 #3180 (LD-147・親 #2821)。DEFECTS.md への D25 登録の要否は PM agent の判断待ち・既定案: #3180 の検証結果が出るまで登録しない |
| 1c621c の rax 差 (§4 (c)) | 2 case。原因未特定 | #2801 (LD-131) へのコメントで追跡 (命令単位の wasm trace で rax の源を示す) |
| import 呼出し記録の差 (§4 (a)) | 8 case の outcome を `diff` にする計装上の差 | PM agent の判断待ち: 計装の改修を子 issue にするか・既定案: 子は起票せず #2801 (LD-131) へのコメントで追跡 |
| 実機 Windows の HeapFree 戻り値 (割当て外 p) | 応答表の根拠が未検証 | PM agent の判断待ち: 実機検証の起票先・既定案: 本 run では実機検証しない。`tools/shim/REPORT.md` §6 の未検証注記を正本とする |
| GlobalFree・LocalFree の範囲外の応答 (native stub は 0、shim は `h`) | HeapFree 以外。native と shim が一致しない | #2841 (LD-136) へのコメントで追跡 (shim の範囲外応答の残り。`tools/shim/REPORT.md` §6 の注記を参照) |
