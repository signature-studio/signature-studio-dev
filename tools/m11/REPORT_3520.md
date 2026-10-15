# REPORT_3520 — e2e rc=1 の期待値と実測の不一致 (#3520) の原因特定

**結論 (3 行)**
- (c) ptrcheck 71005 は **`M11_FIX_50A830=1` の clean build で再現**した値。既定 (clean) は 71001。既定で 71005 が出るのは `work/obj/ov.o` が古い (ON 側の build で作った) 状態のときだけで、**build キャッシュの取り違え**が原因。`M11_FIX_50A830` に stamp が無かった。修正 (`m11_build.sh` の `fix_ov.stamp`) で再現しなくなった。
- (b) survey exact: 既定の clean 実測は 873、872 は ON 状態 (`M11_FIX_50A830=1`) の値。既定で 872 が出るのも同じ取り違え。pin 872 の出所 (#2714 時の環境) は未切り分けで、survey の ok は環境 (IR・work 状態) で 872〜874 に動く。
- (a) tolerant 完了数 101 (= 通常起動 units_run 98 + skipped 3): clean・ON・既定のどれでも 101 で、`M11_FIX_*` の切替えでは動かない。pin 56 は #2714 時点の値で、その後の commit で通常起動が unit 57 を超えて進んだ。**進んだ commit は未二分** (未解決)。

期待値 (`e2e_expect.env`・`m11_tolerant_gate.py`) は変えていない。

## 1. 測定条件

- PE: `fl-win64` の `extracted/block00031_PE.bin` (sha256 `b2c64da4…`)。素材 `work-m11` は #516 以前の snapshot で、`ir_conditions.json`・`lift_pe.sha256`・`functions_dll.csv` が無い。
- 素材の lift (`boot0〜4.lift.ll`) は snapshot を使い、`boot5.lift.ll` は `m11_lift.sh m11_extra_ranges5.txt boot5` (RetDec・8 秒) で作った。`m11_image_gen.py` の出力は snapshot の `m11_image.bin` と **バイト一致** (LB=0)。よって snapshot の lift は現 PE 由来と見てよい。
- IR は `m11_gen_ir2.sh` で作り直した (ldfix・ld108・ld115 applied)。全再生成 (Ghidra CSV・RetDec 4 chunk) は行っていない。`lift_pe.sha256` は手書きしていない。
- 測定は `m11_e2e.sh` の 97〜111 行 (run・survey・tolerant・judge・gate) と同じ順・同じ環境変数で行った。

## 2. 実測 (clean = 直前に `work/obj/*.o` を全削除してから build)

| 構成 | 測定 tree | IR sha256 (先頭) | strict 完了 (units_run + skipped) | survey ok / trap / miss / noproc | survey ptr (max 71001) | run ptr (max 69359) |
|---|---|---|---|---|---|---|
| 既定・clean (参考・旧 base) | f8867e72e (旧 base の作業ツリー。本 commit 系列の測定 commit ではない。根拠に使わない) | `bcfda317` | 98 + 3 = 101 | 873 / 22 / 46 / 1 | 71001 (pass) | 69669 (**FAIL**) |
| `M11_FIX_50A830=1`・clean | a0d9722fe (記録のみ。tree の個別確認は無い) | `bcfda317` | 98 + 3 = 101 | 872 / 23 / 46 / 1 | **71005 (FAIL)** | 69669 (FAIL) |
| 既定だが直前が ON build (`obj` 削除なし・取り違え) | a0d9722fe (記録のみ) | `bcfda317` | — | 872 / 23 / 46 / 1 | **71005** | 69669 |
| 既定・最初の IR (初回 gen) | 未記録 | `36079b29` | 101 | 873 / 22 / 46 / 1 | 71001 | 未記録 |
| origin/main `8a852f69a` の worktree・既定・clean (修正前) | 8a852f69a | `158b2a8b` | 98 + 3 | (未記録) | 71001 | 69669 |
| 同・ON build (`obj` 削除なし・取り違え・修正前) | 8a852f69a | `158b2a8b` | — | (未記録) | **71001 (既定と同値 = 古い ov.o)** | 69669 |
| 同・修正後 (8a852f69a + a0d9722fe の `m11_build.sh`)・既定 → ON → 既定 (`obj` 削除なし) | 8a852f69a + m11_build.sh (a0d9722fe の tools/m11 と同一) | `158b2a8b` | 98 + 3 | 873 / 22 / 46 / 1 → 872 / 23 / 46 / 1 → 873 / 22 / 46 / 1 | 71001 → **71005** → 71001 | 69669 |

- 行 1〜3 は IR が同じ `bcfda317` だが、tree の記録は行 1 だけ (f8867e72e)。行 2〜3 の tree は前 session の記録 (a0d9722fe) で、個別の確認は無い。**tree を確認できるのは行 5〜7** で、§3 の結論の主根拠はこの並び。
- `M11_FIX_535BF2=0` (取り違えの可能性がある build) は 71001 / run 69668。参考値。
- IR 生成の出力 hash は `36079b29`・`bcfda317`・`158b2a8b` の 3 通りになった。`36079b29` と `bcfda317` は同じ入力での差で、hash seed (未指定・1・2) では `bcfda317` に揃う。`158b2a8b` は 8a852f69a 基点の IR で tree が違うため、上の 2 通りの差とは別に扱う。差の原因は未切り分け (§4)。run ptr 68938 の記録は snapshot の古い wasm (units 17) のもので、基準の判定には使わない。
- survey ptr は、既定 clean で IR の版によらず 71001 だった。

## 3. 原因

### (c) image_va_words_new 71005 / 上限 71001

- `M11_FIX_50A830=1` の clean build で 71005 が出る (+4 語)。既定 clean は 71001。主根拠は §2 の行 5〜7 (修正後: 既定 71001 → ON 71005 → 既定 71001)。
- 既定で 71005 が出た条件は、`m11_build.sh` が `M11_FIX_50A830` を stamp で管理しておらず (`M11_FIX_535BF2` は既存の `work/ov_535bf2.stamp` で管理済み)、`work/obj/ov.o` が mtime だけで再利用されることだった (ov.o は `m11_ov.c` の `#if` でこの 2 フラグを切り替える)。ON build の後に既定 build を流すと、既定の測定が ON の ov.o で行われた。
- PR #3485 の表で既定の行も 71005 になっているのは、同じ取り違えで説明できる (推定。その run のログは repo に無い)。
- 期待値 71001 は既定の値として正しい。gate は正しく動いている。

### (b) survey ok 873 ≠ 期待 872

- 既定 clean の ok は 873。ON (50A830=1) の clean は 872。
- pin 872 は `REPORT_N2714.md` (#2714 時点・既定 0/0・IR `de46cada`・手書きの `lift_pe.sha256`) の値。既定 0/0 は `a7d59a478` (#2714) 時点の既定。535BF2 の既定 0→1 は `d80e9909f` (#2521) で、`a7d59a478` はその前 (祖先) にある。同 `REPORT_N2768.md` の別環境では同じ範囲で 874 が出ている。survey の ok は環境で 872〜874 に動き、pin が環境に依存して安定しない。
- 既定で 872 が出るのは、ON build の後に `ov.o` を消さずに既定 build を流したときだけ (取り違え)。

### (a) tolerant 完了数 101 ≠ 期待 56

- 101 (= units_run 98 + skipped 3) は clean・既定・ON のすべてで出た。`M11_FIX_*` の切替えでは動かない。
- pin 56 は #2714 時点の値 (`REPORT_N2714.md` §: 53 + 3)。`REPORT_N2768.md` でも 56 だった。`REPORT_APPENDIX_2521.md` の表では、PR #3485 の base (`44a7f4465`) で既に 98 (+ skip 3)。
- 停止位置の変化: REPORT §14 では unit 57 (0x16fde0) の後に Halt0。今回は unit 約 101 の `function_535c11` (OOB) で止まる。**停止点が後ろへ動いた**。改善方向の変化で、survey の数値は (b) の範囲で変わっていない。
- 56 → 98 を生んだ commit は**未二分**。候補は `tools/m11/ldfix`・`m11_ov.c`・`m11_gen_ir2.sh` を変えた commit 群 (#3372・#3419・#3426・#2833 など)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) 通常起動の完了数 56 → 98 (+3) を生んだ commit の二分 (未了) | pin 56 が古い。期待値を上げるには根拠が要る | 既存 issue へのコメント: #3520 (close 後も結果の追記先)。PM agent の判断待ち: 二分を依頼するか・既定案: 依頼せず、期待値 56 は据え置く (gate は FAIL のまま) |
| (b) survey ok の環境差 (872〜874) と pin 872 の出所 (#2714 時の build 状態・推定) | 既定の期待値が環境で動く | 既存 issue へのコメント: #3520 (同上)。PM agent の判断待ち: 環境差の切り分けを依頼するか・既定案: 依頼せず、期待値 872 は据え置く |
| 通常起動の ptr 基準 69359 超過 (既定 clean で 69669) | `m11_e2e.sh` の rc=1 の別要因 (本 issue の範囲外) | PM agent の判断待ち: 新 issue を起票するか・既定案: 起票する (e2e の基準の見直しは PM が issue 化) |
| IR 生成が同じ入力で別出力 (`36079b29` と `bcfda317`。hash seed は無関係) | run ptr の基準が IR の状態で変わり得る | PM agent の判断待ち: 新 issue を起票するか・既定案: 起票せず、本表に残す |
| origin/main の `m11_gen_ir2.sh` は qstore を適用しない (`ir_conditions.json` が `qstore=not-applied`) | 旧 main と IR の内容が違う可能性。未確認 | PM agent の判断待ち: 確認を依頼するか・既定案: 本 PR では確認しない (未解決のまま) |
| 全再生成 (Ghidra CSV・RetDec 4 chunk) を行っていない | snapshot の lift と全再生成の IR の一致は未確認 | PM agent の判断待ち: 全再生成を依頼するか・既定案: 依頼しない (時間上限に収まらない) |

## 5. 修正

- `tools/m11/m11_build.sh`: `M11_FIX_535BF2`・`M11_FIX_50A830` の組 (`<535BF2>-<50A830>`) が前回 build と変われば `work/obj/ov.o` を作り直す (`work/fix_ov.stamp`)。既存の instr 系 stamp と同じ書き方。`M11_FIX_535BF2` だけは既存の `work/ov_535bf2.stamp` と重なり、新規は 50A830 の切替え。
- 既定の値・期待値・C 側の転記内容は変えていない。後続の `fix(m11): report corrections (#3520)` commit は、stamp のコメントの誤記 (535BF2 には stamp が無い、という記述) を直しただけで、挙動は変えていない。

## 6. 検証

- 測定 commit: `a0d9722fe` (コード変更を含む最後の commit)。その後のコード差分は `tools/m11/m11_build.sh` のコメント 1 行だけ。非コメント行の差分は 0 行 (§7)。
- **本 fix run では e2e を再実行していない**。素材 (`tools/m11/work`・emsdk・retdec) が run 上に無く、`fl-win64` の展開だけでは lift・IR・build が再現できないため。§2 の数値は前 session の記録で、再測定していない。
- stamp 行の分離テスト (本 fix run・HEAD の `m11_build.sh` の該当行を切り出して実行): 初回 (stamp 無し) rebuild / 同設定 reuse / 50A830 0→1 rebuild / 同設定 reuse / 535BF2 1→0 (50A830=1) rebuild / 50A830 1→0 (535BF2=0) rebuild。
- `m11_e2e.sh` 全体は未実行 (素材 snapshot の全再生成が要り、時間上限に収まらない)。run・survey・tolerant・judge・gate は前 session が個別に実行した (§2)。gate の結果: strict (101 ≠ 56) と survey (873 ≠ 872) は FAIL のまま (期待値は変えていない)。

## 7. 差分

`git diff a0d9722fe HEAD -- tools/m11` は、コメント 1 行の変更 (`m11_build.sh`) と、本 REPORT の追記・修正だけ。`m11_build.sh` の非コメント行の差分は 0 行 (`git diff -U0 a0d9722fe HEAD -- tools/m11/m11_build.sh | grep -E '^[-+]' | grep -vE '^(\+\+\+|---)' | grep -cvE '^[-+][[:space:]]*#'` が 0)。
