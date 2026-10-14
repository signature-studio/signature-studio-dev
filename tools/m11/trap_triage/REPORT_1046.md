# #1046: unit 492 の OOB (`4133f0` 参照カウント解放経路) の原因特定 (途中経過)

親: #862 (受入 3・4 の持ち越し先)。検証起点: `origin/main` = `9aad4595`。本 PR は `tools/m11/` のコードを変更しない (REPORT のみ)。

**結論 (途中): 受入 1・2 は未達。入力値の実測は未完。D11 (絶対 VA の残り) の疑いは残るが未確定 (表要素は絶対 VA と §9 で判明、入力まで届くかは未実測)。**

## 1. 素材と再現

- 素材: `fl-win64` (`[WIN64]`、`$FL_WIN64_DIR/extracted/`)、`toolchain-emsdk` (`[EMSDK]` 6.0.12)・`toolchain-retdec` (`[RETDEC]` v5.0)、`work-m11`・`work-liftdiff` (`tools/m11/work/`・`tools/liftdiff/work/` へ展開)。
- `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` を指定する (`docs/WORKFLOW.md` §11)。PE は `$FL_WIN64_DIR/extracted/block00031_PE.bin` (`[WIN64]`)。
- IR: `bash tools/m11/m11_gen_ir2.sh` rc 0 (実測 44.0 s、`ldfix=applied`、`boot_final.ll` 490,693 行、`ir_sha256` `2c68ceae…`)。
- build: `bash tools/m11/m11_build.sh` rc 0 (`wasm-ld signature mismatch: 0, undefined symbol: 0`)。
- survey: `node tools/m11/trap_triage/survey_units.mjs` 3 回 (13.27 s・全て rc 0)。per-unit JSON は `cmp` で完全一致。

## 2. survey の実測 (HEAD `9aad4595`、3 回反復)

| 回 | ok | oob | halt0 | miss | other | noproc |
|---|--:|--:|--:|--:|--:|--:|
| 1 | 870 | 16 | 7 | 47 | 1 | 1 |
| 2 | 870 | 16 | 7 | 47 | 1 | 1 |
| 3 | 870 | 16 | 7 | 47 | 1 | 1 |

- unit 492: 3 回とも `oob` (`memory access out of bounds`)。`410630` を含む frame は 0 件。
- halt0 は 114 / 245 / 279 / 314 / 509 / 647 / 895 の 7 件。REPORT_862 §9 の 8 件から unit 368 が抜けている。これは #1043 (`pass_m2q_fn980ed0` による修復、ok 869→870) の既知の変化で、本件の変化ではない。
- oob は 16 件 (144, 149, 275, 280, 304, 477, 484, 492, 513, 520, 555, 659, 745, 830, 880, 923)。

## 3. unit 492 の経路 (全 unit 実行での最上位 frame)

- frames: `function_4133f0 ← function_4473f0 ← function_446400 ← function_446ad0 ← function_ad5700`
- 最上位 frame の wasm offset: `wasm-function[14873]` (= `function_4133f0`) の `0x352bb9` (`top_off` は `oob_top.mjs` による全 unit 実行の値)。
- 命令 (`oob_insn.py m11_boot.cjs.wasm 14873 0x352bb9`): `i32.load offset=0` の直前が `i64.load offset=32` → `i64.const 8` → `i64.add` → `i32.wrap_i64`。つまり `4133f0` の `cmp dword ptr [r13 - 8], 0` に対応する `*(arg - 8)` の読みで OOB。
- 注意: `SV_ONLY=492` の単独実行では最上位 frame が `function_407a50` になり、全 unit 実行と異なる。unit 492 の挙動は先行 unit の状態に依存する。単独実行の frame は採用しない。

## 4. 機械語と IR の対応 (実測)

- `4133f0` (size 135): `rdx` (引数 `r13`) が NULL でなければ `[r13-8]` (refcnt) を読む。解放経路は `lock xadd [rax+8]` → `call 409440`。
- `4473f0` (size 249): `[rbp+0x40]`・`[rbp+0x48]` のスロットを `447df0` で埋めてから `4133f0` を呼ぶ。`447df0` は `cmp qword [rbx],0` が 0 のときだけ `[arg5 + arg4*8]` を読んで `41c820` へ渡す。戻り値は常に `rbx` のアドレス。
- IR (`boot_final.ll` `@function_4473f0`): `447df0` の第 5 引数が `inttoptr i64 16433440` (`0xfac120`)・`16433496` (`0xfac158`) の定数。機械語の `lea rax,[rip+disp]` (`0x447467`・`0x44749e` の直前) はこの表を指すはず。

## 5. 未解決 (本 run で切り分けられなかった点)

1. **入力値 (`4133f0` の `rdx`) の実測は未完**。`447df0` が読む表の要素が何か (rdata の表か、機械語の誤読か) を確定していない。
2. IR 定数 `16433440` (`0xfac120`) と `16433496` (`0xfac158`) は RVA (= LVA、`M11_LB_BASE=0`) として `.data` の表の位置を指す。表の要素は **絶対 VA** (`0x4260f0, 0x426100, …` / `0x426160, 0x426170, …`、ImageBase `0x400000` 付き。§9 で実測)。絶対 VA の要素が `447df0` → `41c820` を経て `4133f0` の入力 (`rdx`) まで届くかは **未実測**。届く場合は D11 (PE VA リテラルの wasm32 切り捨て → OOB) に該当するため、D11 の疑いは **残っている** (否定はしない)。
3. DEFECTS 類型への対応: 未確定。表の内容 (`0x4260f0…` 系のポインタ) が何の vtable / 文字列表か、要素 `[arg4*8]` のどれが `41c820` に渡って `4133f0` の OOB 入力になるかは未実測。`lea` の実効位置の照合も未完。

## 6. 受入条件の判定

| # | 条件 | 判定 |
|---|---|---|
| 1 | `4133f0` の OOB の入力値 (ポインタ・長さ) を実測で特定 | **未達**。命令 (`*(arg-8)`) と入力の供給元 (`447df0` の表読み) までは特定。値は未実測 |
| 2 | `4473f0` の配列長計算 (`0x92492493`) の戻り値が原因か実測 | **未達**。`4473f0` の IR と機械語の対応まで確認。戻り値の実測なし |
| 3 | DEFECTS 類型への対応づけ | **未達**。D11 の疑いが残る (表要素が絶対 VA と §9 で判明)。`4133f0` の入力まで絶対 VA が届くかは未実測のため未確定 |
| 4 | unit 492 の kind 実測と per-unit JSON で回帰が無いこと | **達成 (測定のみ)**。3 回とも `oob`、per-unit JSON `cmp` 一致。コード変更なし (回帰 0) |

## 7. 再現

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64   # PE: $FL_WIN64_DIR/extracted/block00031_PE.bin
bash tools/m11/m11_gen_ir2.sh
bash tools/m11/m11_build.sh
node tools/m11/trap_triage/survey_units.mjs tools/m11/work/trap_triage/run1.json
node tools/m11/trap_triage/oob_top.mjs tools/m11/work/trap_triage/topall.json   # 最上位 frame と top_off
python3 tools/m11/trap_triage/oob_insn.py tools/m11/work/m11_boot.cjs.wasm 14873 0x352bb9 40
LD_M11_PE=$FL_WIN64_DIR/extracted/block00031_PE.bin python3 tools/m11/trap_triage/disasm_fn.py 4133f0 4473f0 447df0
```

注: `disasm_fn.py` は `LD_M11_PE` で PE を指定する (`$FL_WIN64_DIR/extracted/block00031_PE.bin` と同一。`[WIN64]`)。

## 8. 測定 commit からの差分 (差分 0 の証跡)

- 測定 commit: `9aad4595` (§1・§2 の測定)。検証 HEAD: `b55c9f7c` (main `d7d91d26` を取り込み)。
- `git diff --stat 9aad4595 b55c9f7c -- tools/m11/m11_gen_ir2.sh tools/m11/m11_build.sh tools/m11/trap_triage/ tools/shim tools/m11/*.py tools/m11/*.sh`: 出力は `tools/m11/trap_triage/REPORT_1046.md` (+67) と `REPORT_714.md` (+42) のみ。コード差分 0。
- 同範囲外の差分 (`tools/shared/lift/libkio/*`・`tools/m11/ldfix/ldfix_509_e2e.sh`) は m11 の IR 生成・build・survey から参照されない (`grep` で 0 件)。

## 9. 再着手 run の追加測定 (HEAD `a647ceba`、コード変更なし)

- 再現: `m11_gen_ir2.sh` rc 0 (36.6 s、490,693 行) → `m11_build.sh` rc 0 (wasm-ld signature mismatch 0・undefined 0) → `survey_units.mjs` rc 0 (9.9 s)。結果 `ok 870 / oob 16 / halt0 7 / miss 47 / other 1 / noproc 1` で §2 と一致。
- `.data` の表 (RVA `0xfac120` / `0xfac158`) の中身は絶対 VA (`0x4260f0`, `0x426100`, … / `0x426160`, `0x426170`, …、ImageBase `0x400000` 付き)。RVA の `.text` では読めず `.data` 配置で読んだ。§5-2 の「6 要素のポインタ配列」は同じ値を指し、その要素が絶対 VA である点を示す。これにより §5-2 の「D11 は否定」は撤回する (上記 §5-2 参照)。
- `SV_ONLY=492 SV_TRACE_AT=492` の単独実行: `oob` 1 件のみ (trace 行 4 件)。全 unit 実行の `SV_TRACE_AT=492` では trace 行 `[m11][UStrAsg]` が 146 件 (dest/src の 0 が 24 件、`src=0x10e1ac` が 9 件)。ただし unit 境界の行が出ないため、unit 492 の OOB 直前の `UStrAsg` を切り出せなかった。
- 結論: 受入 1 (OOB 入力値 `src`) は未達のまま。入力値を取るには `function_4133f0` の入口で unit 番号つきの値を記録するビルドが要る (`m11_ov.c` の `M11_TRACE` は unit 番号を出さない)。受入 2・3 も未達。未解決は #1288 (`[M11-N79]`) に残す。

## 10. #1288 の実測: unit 492 の OOB 入力値 (HEAD `604e900f` 起点、測定 commit は本節を含む commit)

- 再現: `m11_gen_ir2.sh` rc 0 (44.8 s、490,693 行) → `m11_build.sh` rc 0 → `survey_units.mjs` rc 0 (13.1 s)。結果 `ok 870 / oob 16 / halt0 7 / miss 47 / other 1 / noproc 1` で §2 と一致。
- 計装: `m11_ov.c` の `[m11][UStrAsg]` trace 行に `old=Q(dest)` を追加 (trace 有効時のみ出力。非 trace の survey 結果は不変)。
  `SV_PROG=1 SV_TRACE_AT=492 node survey_units.mjs <out>.json` で unit 492 の trace を切り出した (`unit 492` 〜 `unit 493` の間)。
- unit 492 の UStrAsg 全 12 行のうち最後の 2 件 (実測):
  - `dest=0x10a9f908 src=0x0 old=0x0`
  - `dest=0x10a9f910 src=0x0 old=0x100000003` ← **OOB の入力**。`old` は wasm32 の有効ポインタではない (下位 dword 3・上位 dword 1 の packed 値)。
- `0x10a9f910` は unit 492 内の先行 UStrAsg の dest に現れない。値を書いたのは UStrAsg 以外の store (未特定)。
- `0x100000003` は IR 定数として `boot_final.ll` に無い (`grep 4294967299` 0 件)。実行時に作られた値。
- 呼出経路 (IR 確認): `4473f0` の `447df0` 出力スロット `stack_var_-48/-56` は `store i64 0` で初期化され、`4133f0` の `src` 入力はこの値。ただし OOB の `dest` (`0x10a9f910`) の slot の出自 (どの frame の何か) は未確認。`4473f0` 経路との接続は未検証。

### 受入条件の判定 (#1288)

| # | 条件 | 判定 |
|---|---|---|
| 1 | `4133f0` の OOB 入力値 (ポインタ・長さ) を実測 | **達成 (値)**: `dest=0x10a9f910`、`old=0x100000003` (上記)。`src` 側は `0x0` (NULL) で OOB と無関係。書込み元の store は未特定 |
| 2 | `4473f0` の配列長計算 `0x92492493` が原因か実測 | **未達**。今回の OOB 入力は `447df0` 経由の表要素ではなく `old` (dest 側)。配列長の影響は未検証 |
| 3 | DEFECTS 類型への対応 | **部分**。packed 値 (dword 2 つ分の 3・1) が 8B slot に入る形は D17 (qword store の 4B 縮退で上位 4B が未初期化 → ゴミ) と同型の疑い。書込み元の store を確定していないため未確定 |
| 4 | 修復後の unit 492 kind と per-unit JSON 回帰確認 | **未達** (修復未実施。測定のみ) |

### 未解決 (起票先: #1288 を継続)

1. `0x10a9f910` に `0x100000003` を書いた store の特定 (`watch_store_682` 方式で `addr == 0x10a9f910` の書込み元 IR site を取る)。
2. その store が D17 (qword → i32 縮退) か別類型かの判定。
3. `4473f0` の `0x92492493` 配列長計算は未検証 (受入 2)。

## 11. #1288 再着手 run (HEAD `243c9060` 起点、コード変更なし)

- 素材: `fl-win64`・`toolchain-retdec`・`toolchain-emsdk`・`work-m11`・`work-liftdiff` を展開 (`work-m11` は `tools/m11/work/`、`work-liftdiff` は `tools/liftdiff/work/`)。
- 再現: `m11_gen_ir2.sh` rc 0 (27.8 s、490,693 行) → `m11_build.sh` rc 0 → `survey_units.mjs` rc 0 (6.8 s)。結果 `ok 870 / oob 16 / halt0 7 / miss 47 / other 1 / noproc 1` で §2・§9・§10 と一致。
- 計装 (一時、`tools/m11/work/probe1288/` のみ・commit なし): `boot_final3.ll` の全 store (54,041 site) に `m11_sw` を入れ、`addr` が `0x10a9f910` の 8B を覆う書込みを出した。
  - 結果は**採用できない**: 計装版の survey は `ok 872 / oob 14` と本番 (`870 / 16`) から変わった。`[sw]` 行は 3,204,589 件で、unit 境界が無いため unit 492 の範囲に絞れていない。
  - 計装を外して再 build し、`ok 870 / oob 16` に戻ることを確認 (作業ツリーに差分なし)。
- 受入の判定 (本 run): 2 (`0x92492493` 配列長) は未着手。3 (DEFECTS 類型) は §10 の D17 同型の疑いのまま未確定。4 (修復後の kind) は修復を行っていないため未達。
- 未解決 (起票先 #1288): (a) unit 492 の範囲に限定した `0x10a9f910` 書込みの store 特定 (unit 境界の出力を計装側に入れる必要あり)、(b) D17 か別類型かの判定、(c) `4473f0` `0x92492493` の検証。

## 12. 再着手 run (HEAD `cb3a89a6` 起点): 書込み元 store の探索 (途中・結論なし)

- 測定 commit: `cb3a89a6` (本節の計装と §12 の監視結果を取った時点のコード)。
- 再現 (`cb3a89a6` 時点で実施): `m11_gen_ir2.sh` rc 0 (29.0 s) → `m11_build.sh` rc 0 → `survey_units.mjs` rc 0 (6.7 s)。結果 `ok 870 / oob 16 / halt0 7 / miss 47 / other 1 / noproc 1` で §2 と一致。
- 現 head での再測定は未実施 (素材 `toolchain-emsdk`・`toolchain-retdec`・`work-m11`・`work-liftdiff` が Actions run に無く、再 build 不可)。
- `cb3a89a6` → `a7d3975d` の `tools/m11` 差分 (実測。`git diff --stat cb3a89a6 a7d3975d -- tools/m11`: 28 files, +3055 / -53)。実行パスに効く 16 files (`m11_gen_ir2.sh`・`m11_win.c`・`ldfix/`) の出力は下記。これらは本 PR のコミットではなく、main 取り込み (`564`・`577` 系の merge、`cb3a89a6` の後) で入った変更。本 PR の 3 ファイル (`REPORT_1046.md`・`store_watch_1046.sh`・`watch_addr_1046.c`) はコード差分を含まない。
  ```
  git diff --stat cb3a89a6 a7d3975d -- tools/m11/m11_gen_ir2.sh tools/m11/m11_build.sh tools/m11/m11_win.c tools/m11/ldfix/
   16 files changed, 2688 insertions(+), 13 deletions(-)
  ```
- 計装: `trap_triage/watch_addr_1046.c` (監視番地 `0x10a9f910` の固定版。`watch_store_682.c` の `[[g+8]+8]` 監視は使わない) と `trap_triage/store_watch_1046.sh` (`SV_ONLY` で unit を絞れる)。全 store に `m11_sw` を入れる IR は `watch_store_682.py` を流用。
- 全 942 unit 実行 (監視版): `[aw]` は unit 106 付近まで記録されたが 900 秒の上限で打ち切り。`0x10a9f910` への書込みは unit の前半から多数 (`val=10bd48f0`、`val=537301`、`val=10bb6820` 等)。
- `SV_ONLY=492` 単独 (監視版): `[aw]` 0 件、survey は `oob 1`。全 unit 実行で見えた書込みは unit 492 単独では起きない。`0x10a9f910` の値は前の unit が共有ヒープに残した状態に依存する。
- 結論: 書込み元 store は未特定。単独 unit では再現しないため、OOB 直前の書込みを探すには全 unit 実行の監視が要るが、この run の時間では完了できなかった。

### 次の手順 (#1288 を継続)

1. 監視版を全 unit 実行で完走させる (`store_watch_1046.sh` を `timeout` の上限を延ばして実行。900 秒では不足)。
2. 最後の `[aw]` 書込み (`val=0x100000003` 相当の store) の `site` を `sites.json` で IR 行に戻す。
3. その store が D17 (qword → i32 縮退) か別類型かを判定する。

## 13. 4 回目の再着手 run (HEAD `1017f349` = origin/main、コード変更なし)

- 測定 commit: `1017f349` (コード差分 0)。素材: `work-m11`・`work-liftdiff` を `ws-1046` の `tools/m11/work/`・`tools/liftdiff/work/` に展開、`fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`FL_WIN64_DIR`)。
- 再現: `m11_gen_ir2.sh` rc 0 (50.5 s、490,733 行) → `m11_build.sh` rc 0 (24.4 s、wasm-ld signature mismatch 0・undefined 0) → `survey_units.mjs` rc 0 (13.2 s): `ok 870 / oob 16 / halt0 7 / miss 47 / other 1 / noproc 1`。
- 全 942 unit の監視版 (`store_watch_1046.sh`、`timeout 1500`): 上限で打ち切り (rc 124、25 分 21 秒)。`unit 106` で停止。`[aw]` 行は **0 件**。§12 の「unit 106 付近まで `[aw]` が記録された」とは一致しない (計装・素材の差が未切り分け)。
- 打ち切り後、`work/obj/sw682.o`・`boot.o`・`ov.o` を消して `m11_build.sh` で再 build し、survey を再実行: `ok 870 / oob 16 / halt0 7 / miss 47 / other 1 / noproc 1` に戻ることを確認 (計装が残っていない)。`timeout` で殺された場合は `store_watch` の EXIT trap が走らないため、手動で復元が要る。
- 結論: 書込み元 store は未特定。監視版の全 unit 完走には 25 分超が要り、1 run の上限内では完了しない。次回は unit 範囲を分けて (例: 0–105 / 106–941) 実行するか、`[aw]` に unit 境界を出す計装を入れる。受入 2・3・4 は未達のまま。

## 14. 5 回目の再着手 run: unit 単位の値遷移 probe (HEAD `72260b63` = origin/main、コード変更なし)

- 測定 commit: `72260b63` (コード差分 0。計装は本節の probe のみ・survey 本体は不変)。
- 差分 0 の証跡 (`git diff --stat 72260b63 HEAD -- tools/m11/m11_gen_ir2.sh tools/m11/m11_build.sh tools/m11/trap_triage/survey_units.mjs tools/m11/m11_win.c tools/m11/ldfix/` の出力は空。範囲内のコード差分 0):
- 本 PR の差分は `git diff --stat 72260b63 HEAD -- tools/m11` で `tools/m11/trap_triage/REPORT_1046.md` (+14) と `tools/m11/trap_triage/probe_1046_watch.mjs` (+32) の 2 ファイルのみ。
- 再現: `m11_gen_ir2.sh` rc 0 (36.2 s、490,733 行) → `m11_build.sh` rc 0 → `survey_units.mjs` rc 0: `ok 870 / oob 16 / halt0 7 / miss 47 / other 1 / noproc 1` (§2 と一致)。
- 新規 `trap_triage/probe_1046_watch.mjs`: 各 unit 実行の前後で `0x10a9f910` の 8B を読み、値が変わった unit を出す (読取りのみ、IR 不変)。全 942 unit を **13.1 s** で完走 (§12・§13 の全 store 計装は 900〜1500 秒で打ち切り)。
- 値の遷移 (抜粋・実測):
  - `unit 477 exc 0x1_1029e5d8 -> 0x1_2`
  - `unit 484 exc 0x1_2 -> 0x1_3` (**unit 484 は OOB (`function_903e00` 系)**)
  - `unit 492 exc 0x1_3 -> 0x0` (unit 492 の OOB 入力 `old=0x100000003` は unit 484 が残した値)
- 要点: issue #1620 の前提「unit 492 の中で `0x100000003` が書かれる」は**誤り**。値は unit 484 で `0x1_3` になり、unit 492 はそれを読んで OOB する。書込み元は unit 477〜484 の範囲に絞れた。
- 全 store 計装 (`store_watch_1046.sh`、`SV_ONLY=0..484`、`SV_ERR_LOG` 付き) は 800 秒で打ち切り (rc 124)。`[aw]` は unit 95 までの 265 件のみ。打ち切り後に計装を除去し、基準 build (`ok 870 / oob 16 / halt0 7 / miss 47 / other 1 / noproc 1`) に戻ることを実測で確認。
- unit 477〜484 だけを `SV_ONLY` で実行した場合 (store 計装版): `[sw]` 0 件、survey は `oob 2 / ok 6` (44 s)。同範囲の値遷移 probe も `0x0` のまま変化しない。**値 `0x1_2`・`0x1_3` は unit 0〜476 が共有ヒープに残した状態に依存し、単独範囲では再現しない**。
- 結論: 書込み元 store は未特定。0〜484 を通す全件計装は前回 800 秒で打ち切り。#1620 の残りは「0〜484 を通した計装を、時間内に完走させる手段 (unit 境界を出す計装・実行の分割と状態の受け渡し) を作ること」。

## 15. #1288 再着手 run (HEAD `04a7ff1a` 起点): 監視版の全 unit 実行は unit 106 で停止 (結論なし)

- 測定 commit: `04a7ff1a` (コード変更なし。本節の追記のみ)。`tools/m11` 全体の差分は main 取り込みで 7 ファイル (+145 行: `REPORT_N15.md`・`REPORT_1274.md`・`REPORT_1317.md`・`REPORT_1463.md`・`trap_triage/probe_1046_watch.mjs`・`trap_triage/probe_entry.py`・`REPORT_1046.md`) あるが、§15 の実測経路 (`m11_gen_ir2.sh`・`m11_build.sh`・`survey_units.mjs`・`m11_ptrcheck.mjs`・`ldfix/`・`m11_win.c`・`store_watch_1046.sh`・`watch_addr_1046.c`) の差分は 0 (`git diff --quiet 04a7ff1a 6edffd41 -- <上記>` が空)。`probe_1046_watch.mjs`・`probe_entry.py` は §15 の実行に使っていない。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`extracted/block00031_PE.bin` 確認)。`work-m11`・`work-liftdiff` は `tools/m11/work`・`tools/liftdiff/work` に展開済み。retdec・emsdk は `/opt` にあり。
- 再現 (`04a7ff1a`): `m11_gen_ir2.sh` rc 0 (38.8 s、490,733 行) → `m11_build.sh` rc 0 (18.0 s) → `survey_units.mjs` rc 0 (9.0 s)。結果 `ok 870 / oob 16 / halt0 7 / miss 47 / other 1 / noproc 1` で §2・§9〜§12 と一致。load average 約 1.0。
- 全 store 計装版 (`store_watch_1046.sh`、監視番地 `0x10a9f910`) の試行:
  - `SV_ONLY=0..9`: 34.6 s、`unit 0`〜`unit 9` 完走、`[aw]` 0 件。
  - 全 942 unit (`full1`): `timeout 1500` で打ち切り (rc 124、25 分 15 秒)。`full1.err` の最後の行は `unit 106` で、その時刻は 03:18 (開始直後)。以後 25 分間 unit 107 以降の行も `[aw]` も出なかった。`[aw]` は 0 件。
  - 通常 build の survey は同じ 942 unit を 9 秒で完走する。計装版だけが unit 106 付近で進まなくなる (計装 IR の副作用、または unit 106 の実行時間の大幅な増加。切り分け未了)。
- 記録上の注意 (本 run で判明):
  - 監視版の `[aw]` 行は `watch_addr_1046.c` の `LOG_MAX 4000` で上限があるが、今回は 0 件のため上限には達していない。§12 では `[aw]` を unit 106 付近まで記録したが、本 run は 0 件で不一致。原因は未切り分け (§13 の注記と同じ)。
  - `store_watch_1046.sh` は最後の `grep -c "^\[sw\]"` が 0 件で終了コード 1 を返す (`[sw]` ではなく `[aw]` を数えるべき)。survey の結果には影響しない。
  - `store_watch_682.sh` は生成した `survey_sv.mjs` を `work/probe682/` に置くため、`import ... './m11_ptrcheck.mjs'` が解決できず survey が起動しない (`ERR_MODULE_NOT_FOUND`)。`store_watch_1046.sh` は `tools/m11/` 直下に `survey_sv_1046.mjs` を置くので影響しない。
- 受入の判定 (本 run): 1 は §10 で達成済み。2 (`0x92492493`) は未着手。3 は未確定 (書込み元 store の特定が未了)。4 は修復未実施で未達。
- 次の手順: (a) 計装版が unit 106 で止まる原因を切り分ける (unit 106 だけを `SV_ONLY=106` で単独実行し、時間と停止位置を取る)。(b) 止まらない計装 (例: 監視を unit 492 の直前だけ有効にする) で、`0x10a9f910` への最後の書込みを IR 行に戻す。(c) D17 か別類型かを判定する。

## 16. #1620 run (HEAD `7e665077` = origin/main、コード変更なし): 計装の停止点の切り分け

- 測定 commit: `7e665077` (コード差分 0。本節の追記のみ)。素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`extracted/block00031_PE.bin` 確認)。`work-m11`・`work-liftdiff` は worktree `ws-1620` の `tools/m11/work`・`tools/liftdiff/work` に実コピー (硬リンクにしていない)。
- 再現: `m11_gen_ir2.sh` rc 0 (49.8 s、490,733 行、ldfix errors=0) → `m11_build.sh` rc 0 (24.6 s、wasm-ld signature mismatch 0・undefined 0) → `survey_units.mjs` rc 0 (12.8 s): `ok 870 / oob 16 / halt0 7 / miss 47 / other 1 / noproc 1` (§2 と一致)。
- 停止点の切り分け: 全 store 計装版 (`store_watch_1046.sh`) を `SV_ONLY=106` で単独実行 → rc 1 (`[sw] hits: 0` の grep 終了コード。survey 自体は完走)、約 45 秒。unit 106 は計装版でも単独では止まらない。§15 の「unit 106 で停止」は計装版の全件実行の副作用で、unit 106 の処理そのものではない可能性が高い (全件実行の切り分けは未了)。
- 値遷移 probe (`probe_1046_watch.mjs`、HEAD `7e665077`): 全 942 unit を 12.8 s で完走。`0x10a9f910` の遷移は §14 と一致: `unit 477 exc 0x1_1029e5d8 -> 0x1_2`、`unit 484 exc 0x1_2 -> 0x1_3`、`unit 492 exc 0x1_3 -> 0x0`。
- 結論 (本 run): 受入条件 1 (書込み元 store の IR site 特定) は未達。全 store 計装を unit 0〜484 で完走させる手段は本 run の時間内に作れなかった。`[aw]` 計装は本 run では入れていない (build 後の基準 survey で一致を確認)。
- 次の手順: (a) 計装版の 0〜484 全件実行を unit 範囲に分割して (例: 0–240 / 241–484) 実行し、各範囲の `[aw]` を取る。範囲をまたぐ状態は probe で確かめた `0x1_2` 遷移点 (unit 477) を起点にする。(b) `[aw]` に unit 境界を出す計装 (`unit N` 行を `[aw]` と同じ stderr に出す) を入れ、計装有無で survey 結果が変わらないことを確認する。(c) D17 か別類型かを判定する。

## 17. #1620 run (HEAD `82c44c61` = origin/main、コード変更なし): unit 範囲つき監視の試行 (結論なし)

- 測定 commit: `82c44c61` (コード差分 0。本 PR の追加は `store_watch_1046b.sh` と `watch_addr_1046b.c` の 2 ファイルのみ・既存コードは不変)。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`extracted/block00031_PE.bin` 確認)。`work-m11`・`work-liftdiff` は worktree の `tools/m11/work`・`tools/liftdiff/work` に展開。
- 基準の survey 数値と値遷移 (unit 477・484・492 の遷移) は §2・§14 と一致 (本 run で再確認)。
- 単独範囲: unit 484 を `SV_ONLY` 相当で単独実行 (全 store 計装版) → `[aw]` 0 件。値は前段 unit 依存のため、単独では書込みが起きない (§14 と一致)。
- 監視 ON/OFF を unit 境界で切る版 (`store_watch_1046b.sh 0 484 <tag> 477 484`、`watch_addr_1046b.c`): 全 store 計装で unit 0〜484 を流したところ、**unit 106 で停止** (実時間 15 分 22 秒、CPU 41 秒、`[aw]` 0 件)。監視を unit 477〜484 だけ ON にしても、停止点は前段の unit 106 のまま。timeout 900 秒で打ち切り (rc 124)。
- 打ち切り後は `trap` の復元 (`m11_build.sh` 再実行) で基準に戻ることを確認 (§2 の基準と一致)。`git status` は既存ファイルに差分なし。

### 結論 (本 run)
- 停止点 unit 106 は、監視の ON/OFF (unit 477〜484 のみ) と無関係に出た。計装が入った IR の実行で unit 106 以降が進まなくなる原因は**仮説・未切り分け**である (計装版 build の副作用と考えられる。次の手順 1 で切り分ける)。REPORT §15・§16 の切り分けと一致し、「単独 `SV_ONLY=106` では止まらない」点とも整合する。
- 書込み元 store は未特定。受入条件 1 (IR site 特定) は未達。

### 次の手順 (#1620 へ)
1. unit 106 で計装版が止まる原因を、計装版 IR の unit 105 → 106 の間の挙動で切り分ける (`[aw]` でなく、unit 106 直前の `[m11]` trace の有無で確認)。計装 `m11_sw` の呼び出しを、必要な unit 範囲だけ IR 内で分岐させる形 (`if (watch_on)` を IR 側に入れる) へ変えると、計装の副作用が減るか試す。
2. 計装版が完走したら、`[aw]` の unit 境界 (`unit N` 行) と sites.json で fn・IR 行に戻す。

## 18. #1620 run (HEAD `c171b9dc` = origin/main、コード変更なし): 計装版の停止を「計装 IR 固有」まで切り分け (結論なし)

- 測定 commit: `c171b9dc` (コード差分 0。本節の追記のみ)。素材: `fl-win64` を展開し `[WIN64]` の `extracted/block00031_PE.bin` を確認。`work-m11`・`work-liftdiff` は worktree の `tools/m11/work`・`tools/liftdiff/work` に展開。ツールチェーンは `[EMSDK]`・`[RETDEC]` を使用。
- 再現 (素の build): `m11_gen_ir2.sh` rc 0 (50.5 s、490,733 行) → `m11_build.sh` rc 0 (25.1 s) → `survey_units.mjs` rc 0 (13.4 s): `ok 870 / oob 16 / halt0 7 / miss 47 / other 1 / noproc 1` (§2 と一致)。
- 計装版の停止 (`store_watch_1046b.sh 0 110 t110 0 110`): unit 106 で停止 (timeout 400 s、rc 124、CPU 42 s)。
- 切り分け (計装版 build を手で作り、survey を通さない素の実行ループ `run_plain` で確認):
  - 素の build で unit 0〜941 を 12.9 s で完走 (rc 0)。survey と同じ戻り値 (104: ok、105: miss、106: ok)。
  - 計装版 build (`boot.o` を計装 IR に差し替え) で unit 0〜106: 120 s の timeout で rc 124 (CPU 120 s、計算の暴走)。`unit 106` の後で止まる。
  - 計装版で unit 106 単独 (前段なし) は 0.4 s で `ret 1`。前段の影響。
  - 開始 unit を変えると: `from 0`・`from 1` は停止、`from 2` 以降は完走。**unit 1 単独 (`0..1`) は計装版でも完走**。`1..106` は停止。したがって unit 1 の実行後の状態が 106 を壊す。
  - unit 1 の後の `0x10a9f910` の 8B: 素の build は `00 00 00 00 00 00 00 00` のまま、計装版は `04 00 00 00 29 32 00 00` (unit 1 が書く)。素の build では unit 1 はこの番地に書かない。
  - `m11_sw` / `m11_watch_on` を空関数 (nop) に差し替えた計装版でも、`0..106` は停止 (timeout 60 s、rc 124)。**停止は C 側の監視関数ではなく、計装 IR (`watch_store_682.py` の出力) 側の性質**。
  - 計装 IR の検査: `wsa_`/`wsv_`/`call void @m11_sw` 行を除いた後の `boot_sw.ll` と `boot_final3.ll` の全行 diff は `declare` 1 行のみ。したがって元の SSA 値・分岐は変えていない、と読める。ただし差分 0 件でも挙動が変わる原因 (最適化・未定義挙動・ヒープ配置) は未切り分け。
- 素の build の値遷移 (読取りのみ): `unit 477 → 0x1_2`、`unit 484 → 0x1_3`、`unit 492 → 0`。§14 と一致。
- 計装版の survey 結果の基準 (計装有無で同一になるべき条件): 素の build に戻した後、`0..106` と `0..941` の素の実行が完走することを確認 (rebuild rc 0)。`git status` は既存ファイルに差分 0 (work/ は gitignore)。

### 結論 (本 run)
- 受入 1 (書込み元 store の IR site 特定): **未達**。計装 IR では unit 106 が止まり、全 store 計装で unit 0〜484 を通せない。
- 停止の性質: 「`m11_sw` の C 実装」ではなく「計装 IR そのもの」が、前段 unit 1 の挙動 (`0x10a9f910` への書込み) を変えている。原因は未切り分け。
- 次の手順 (子 issue に移す): (a) 計装 IR の差分 (`declare` 以外の追加行) を、`wsa_`/`wsv_` を消さずに 1 種類ずつ外して、unit 1 の書込みが消える最小の変更を探す。(b) 最小変更で unit 0〜484 が完走する計装版を作り、`[aw]` の unit 境界で `0x10a9f910` への書込み site を取る。(c) D17 か別類型かを判定する。
