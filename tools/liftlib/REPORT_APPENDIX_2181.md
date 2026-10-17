# liftlib #2181 (HB-H45, 部分達成) — ott_getparam F=281 の SSA dominance 欠陥 (iargs) を直し emcc を通す (付録)

親: #2161 (HB-H44) / 本 issue の範囲縮小: 受入 3 (FAIL-FAST) は子 #2859 (HB-H48)、支配しない値の代替が無い call 引数 176 件は子 #2861 (HB-H49)。
既知類型との関係: [DEFECTS.md](../../docs/DEFECTS.md) の D1a〜D23 に該当なし (機械語の到達定義を IR の支配関係なしに使ったことによる dominance 違反。silent ではなく emcc が落とす型)。

## 0. 結論

| 受入 (#2181 本文) | 結果 (実測) |
|---|---|
| 1. F=281 で emcc が dominance 違反 0 | **達成**。変更前: `Instruction does not dominate all uses!` ×4 で emcc 失敗。変更後: `ott_getparam_fixed.ll` を emcc が受理し link まで成功 |
| 2. `icall_tbl_n > 0` を `*_stubs.c` で確認 | **達成**。`icall_tbl_n = 105` (`ott_getparam_stubs.c`)。登録 105 関数 (引数無し i64 関数) |
| 3. FAIL-FAST 経路が発火する入力で wasm_trap に数える (ネガティブコントロール) | **一部達成** (#4299)。直接呼出し (`__icall_dispatch`) で、表に無い target の abort を wasm crash として計数し、表有無で呼出し結果が分かれることを確認 (§4.3。測定 commit `e05270d33`)。leafspec の 200 scenario では fail-fast 不発火のまま |
| 4. leafspec `wasm_trap` 0 のまま、T2 の IR 不変 | **達成**。現 HEAD `e05270d33` で leafspec `ott_getparam_idx` = **200/200 PASS** (wasm_trap 0)。同 spec を `b1c2d148` で測ると 147/200 (従来値) で、HEAD の変更で match が上がった。`tests/test_unit.py` の再実行は本 fix run では未実施 |

leafspec の gate は現 HEAD で PASS (`match_rate_excl_crash` 1.000)。`b1c2d148` の 147/200 (gate FAIL) は HEAD の値ではない。

測定 commit の扱い (#4299 review round 2 への対応):

- 測定 commit は **`e05270d33` (HEAD) の 1 つ**。leafspec と §4.3 の probe 表の両方をこの commit で測り直した。
- `b1c2d148` の 147/53/0/0 は、旧い測定 commit の値として §4.1 (変更前後の比較) にだけ残す。`b1c2d148` → `e05270d33` の liftlib/icall の差分は 1636 行 (下の確認コマンド)。
- 旧 PR 本文にあった `ott_getparam_idx` match 200 / mismatch 0 (1m33s) は、そのときの記録が無かったため撤回していた。今回 HEAD で再測定し 200/200 を得た (§0 の値はこの測定による)。

確認コマンド (差分の数):

```
git diff b1c2d148 e05270d33 -- tools/liftlib/liftlib tools/liftlib/targets tools/icall/rt | wc -l    # 1636 (leafspec の 147 → 200 の差はこの間の変更に由来。個別の切り分けは未実施)
git diff e05270d33 HEAD -- tools/liftlib/liftlib tools/liftlib/targets tools/icall/rt | wc -l          # 測定後に記録 (本 REPORT の commit は docs のみ)
```

## 1. 測定 config

| 項目 | 値 |
|---|---|
| 測定 commit (コードを変えた最後の commit) | `e05270d33` (leafspec と §4.3 probe 表の両方)。`b1c2d148` は §4.1 の変更前後比較の旧測定として残す |
| 測定 commit 以降の差分 | `e05270d33` 以降は docs (REPORT) のみの commit を積む。コード差分は下の確認コマンドで 0 |
| 素材 | `$ARTIFACTS_DIR` の `fl-win64` (`$HOME/analysis/win64`)・`work-liftlib` / `work-icall` (`tools/liftlib/work`・`tools/icall/work`)・`analysis-ott-binaries` (`$HOME/analysis/plugins/ott/binaries`)・`toolchain-emsdk` (`/opt/emsdk`)・`toolchain-retdec` (`/opt/retdec`) を fix run で展開 |
| 再現 | `cd tools/liftlib && python3 -m liftlib leafspec targets/ott_getparam.json --n 200` (leafspec 200/200 は 1m19.8s の実測。rc 0) |
| 負荷 | 開始時 load 1.84 / 1.05 / 0.44 (runner 4 コア, 単発。14:50:28) |
| 対照 | 同じ spec を `b1c2d148` で測定 (worktree で `work-liftlib` / `work-icall` を展開): 147/53/0/0、1m16.5s、rc 1 (gate FAIL)。fix run 内の実測 (HEAD と同一の素材・同一 cfg) |
| 単体 | `tests/test_unit.py` は本 fix run では未再実行 (前回 run の 19:35 実測は `b1c2d148` 時点の値) |

## 2. 原因 (機械語 / IR の対応)

## 2. 原因 (機械語 / IR の対応)

- `iargs.run` §2 は呼出し引数 k の値を `binder.bind(reg, C)` で得る。bind は機械語の到達定義 (CFG 対応) → その定義 VA に付いた IR 命令の値を返す。
- 対象 site `0x1801ac430` / `0x1801ac455` / `0x1801ac47f` (`function_1801ac21c`): r9 の到達定義は `0x1801ac3fc` (`lea rsi,[rbx+0x28]`, rsi を `mov r9,rsi` で複写) で、IR 値は `%.pre6 = add i64 %2, 40`。この命令は crit edge block (block 34) に置かれており、use 側 (block 42 など) を支配しない。移動の原因は RetDec 側の最適化と推定 (未確認)。
- 同じ値は reg2mem alloca `%.pre-phi7.reg2mem` に 2 経路から store されている (`%.pre6` と `%161`。どちらも rsi = rbx+0x28)。merge block `dec_label_pc_18031ac8a` の `%.pre-phi7.reload` は use を支配し、正しい値になる。
- 対象 site `0x1801c2a84` (`function_1801c29f4`) の r8 (`lea r8d,[rbp+1]`) は、base rbp の IR 値 `%55 = and i64 %arg2, 4294967295` が block 0 の use を支配しない。同じ値を覆う alloca は無いため、この修正では救えない (子 #2861)。

## 3. 修正 (`b1c2d148`)

| ファイル | 変更 |
|---|---|
| `tools/liftlib/liftlib/passes/iargs.py` | `_bind_use`: bind 値の定義が呼出し位置 (block, 行順) を支配するか検査。支配しなければ、同じ値を store する reg2mem alloca の、支配する load を返す。無ければ None (従来は支配しない値をそのまま使っていた)。`_resolve` の再帰 (movzx / lea) も同じ呼出し位置で検査する。`use` 省略時は従来どおり (T16b の偽 binder を壊さない) |
| `tools/liftlib/liftlib/pipeline.py` | `prepare`: 宣言 (`scan_decls`) を正規化前のテキストから読む。正規化後に読むと、ptr 引数の `rep_stosb_memset` / `rep_movsb_memcpy` が `__vpbq__vpbq` / `__vppq__vppq` に二重正規化され、IR 側 (`__vpbq`) と link で一致しなかった |
| `tools/liftlib/targets/ott_getparam.json` | `passes.icall.funcs` を F=281 (`tools/icall/work/ott_F.txt`) に変更。`stub_skip` に `icall_rt.c` が定義する Win32 名 7 件 (`HeapAlloc` `HeapFree` `GetCurrentThreadId` `GetLastError` `SetLastError` `EnterCriticalSection` `LeaveCriticalSection`) を追加 (スタブの trap 定義と重複していたため) |

emcc の link 段で出た順の障害: dominance ×4 → 重複シンボル (Win32 名) → `rep_*` の未定義 (宣言名の二重正規化)。各段で 1 件ずつ直した。

## 4. 実測

### 4.1 変更前後 (同一 cfg・同一 F=281)

| 設定 | emcc | leafspec `ott_getparam_idx` (match / mismatch / native_crash / wasm_trap) | iargs `site_unbound` | `args_added` | `sites_fixed` |
|---|---|---|---|---|---|
| 変更前 (`_bind_use` を旧 bind に差し替えて lift のみ実行) | **失敗** (dominance ×4) | 未実施 (build 失敗) | 175 | 463 | 376 |
| 変更後 `b1c2d148` | **成功** (link 成功) | **147 / 53 / 0 / 0** (gate FAIL: rate 0.735, thr 1.00。旧測定) | 176 | 462 | 376 |
| 現 HEAD `e05270d33` | 成功 (fix run で再ビルド) | **200 / 0 / 0 / 0** (gate PASS: rate 1.000。1m19.8s・rc 0) | 未再計数 | 未再計数 | 未再計数 |

- 変更前の unbound 175 は、`_bind_use` だけを旧動作に戻して lift した値 (`probe` 相当、emcc 前で停止)。
- `b1c2d148` の 147/53/0/0 は `REPORT_APPENDIX_2128.md` の測定 (F=1) と同値。現 HEAD の 200/200 は、`b1c2d148` → `e05270d33` の間の liftlib 変更 (`git log b1c2d148..e05270d33 -- tools/liftlib/liftlib tools/liftlib/targets` の #1270 系など) によるものと読めるが、個別の切り分けは未実施。wasm_trap は両方 0。
- `site_unbound` の +1 は、支配しない `%55` を使わなくなった `0x1801c2a84` の r8 (子 #2861)。r9 (`lea r9,[rsp+0x40]`) は修正前から rsp 基準の合成対象外で unbound (子 #2861)。

### 4.2 `icall_tbl_n` と stub の内訳 (`pipeline_report.json`)

- `icall_tbl` = 105 (引数無し i64 の `function_*` 登録数)、`stubs` = 35。
- `wasm-ld` 警告 `function signature mismatch: IsDebuggerPresent` は残る (警告のみ・本 issue 外)。

### 4.3 ネガティブコントロール (受入 3) — 一部達成 (#4299)

- 試験ドライバ: `tools/liftlib/harness/icall_probe/` (`probe.c` が BLK+0 に target・BLK+16 に index=19・BLK+24 に 64 byte バッファを置いて `__icall_dispatch` を呼ぶ。`build.py` が通常変種と表空変種を作る。`drive.mjs` が 1 試行 1 プロセスで走らせる。`run_matrix.sh` が 4 試行を流す)。
- 測定 commit: `e05270d33` (現 HEAD。fix run で `build.py` と `run_matrix.sh` を再実行した。表の値は PR 作成時 `3870e0afc` の測定と同一)。
- 数値の出所: `drive.mjs` が出す `crashed` (JS 例外の有無)。diff.py の `crash` → `wasm_trap` 判定とは同じ条件 (abort = wasm crash) として扱うが、diff.py 経路 (leafspec) は通していない。
- 試行数: 各セル 1 試行。表有り・表空の差を示すためで、件数を比べる根拠にはしない。
- 結果 (各試行 1 プロセス):

| 変種 | target | `crashed` | 出力 |
|---|---|---|---|
| 通常 | `0x8011e7b0` (表に有る) | 0 | ok |
| 通常 | `0x8011e7b1` (表に無い) | 1 | FAIL-FAST abort |
| 表空 | `0x8011e7b0` (表に有る) | 1 | FAIL-FAST abort |
| 表空 | `0x8011e7b1` (表に無い) | 1 | FAIL-FAST abort |

- 解釈: 表に無い target の abort は、表の有無によらず wasm の crash として数えられる (受入 1 の前半)。表に有る target は通常変種では正常終了し、表空変種では abort する。つまり表の有無が呼出し結果を分けることが数値で示せた。
- 前回の表有り変種の OOB (`memory access out of bounds`) は、BLK+16 の index が 0 のとき関数本体が `0x8011E800` 付近の線形外アドレスを読むため。index を 19 以上にして解消した。
- 未解決: 200 scenario (leafspec) では fail-fast が発火しないため、leafspec 経由の wasm_trap 計数は未確認 (この節の結果は `__icall_dispatch` の直接呼出し経路)。
- 33bit→uint32 の切り捨ては `icall_tbl_va` が `uint32_t` であることで確認済み。`__icall_dispatch` は `(t >> 32)` で 33bit の target を必ず abort するため、表引きには届かない。

- 旧測定 (`b1c2d148` 時点・PR 作成時 run。現 HEAD では未再測定): cfg の `funcs` だけ F=281 にした作業コピーで生成した `ott_getparam_stubs.c` の `const unsigned icall_tbl_n = 105;` を `0` に書き換えた変種を emcc で作り、同じ spec・同じ 200 scenario を流した。結果 `match=147 mismatch=53 native_crash=0 wasm_trap=0`。表を空にしても trap は出なかった。
- 現 HEAD の leafspec (表有り・通常変種) は 200/200・wasm_trap 0 (§0)。表空の leafspec 変種は現 HEAD では未測定。
- 解釈: 200 scenario の実行で `__icall_dispatch` の表未登録経路 (fail-fast) が**到達していない**可能性が高い (到達の有無は未切り分け)。受入 3 の「発火する入力」は本 leaf の spec からは作れていない。次の作業は子 #2859。

## 5. 検証範囲 / 範囲外

- 範囲内: F=281 の emcc 成功、`icall_tbl_n`、leafspec の wasm_trap (200 scenario)、`tests/test_unit.py` 全件 (T2 含む)。
- 範囲外: match 率 (#1270, HB-H29)、表未登録 target の fail-fast (子 #2859)、支配しない値の代替が無い引数 (子 #2861)。
- 他 cfg への影響: `_bind_use` は支配しない IR 値だけを変える (支配する値は従来どおり返す)。iargs を使う他 cfg (例 `ott_iargs_ctor.json`) の再測定は**未実行** (本 PR の範囲外として未解決に残す)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| leafspec の 200 scenario で fail-fast が発火しない (直接呼出しでは §4.3 で計数済み) | leafspec 経由の wasm_trap 計数は未確認 | 子 #2859 (HB-H48) |
| 支配しない値の代替が無い call 引数 176 件 (0 を渡す。0x1801c2a84 の r8, rsp 基準 lea の r9 など) | 呼出先に 0 の誤値が入る可能性 (match への影響は未測定) | 子 #2861 (HB-H49) |
| leafspec の旧値 147/200 (`b1c2d148`) と現 HEAD の 200/200 の差の切り分け (どの commit の変更で上がったか) は未実施。現 HEAD は gate PASS | 旧 REPORT 値の由来の説明が未完 | #1270 (HB-H29) (既存) |
| iargs を使う他 cfg の回帰 (`_bind_use` の副作用) | 支配しない値を使っていた既存出力の変化 | 本 PR の未解決 (未測定) |
