# liftlib #2181 (HB-H45, 部分達成) — ott_getparam F=281 の SSA dominance 欠陥 (iargs) を直し emcc を通す (付録)

親: #2161 (HB-H44) / 本 issue の範囲縮小: 受入 3 (FAIL-FAST) は子 #2859 (HB-H48)、支配しない値の代替が無い call 引数 176 件は子 #2861 (HB-H49)。
既知類型との関係: [DEFECTS.md](../../docs/DEFECTS.md) の D1a〜D23 に該当なし (機械語の到達定義を IR の支配関係なしに使ったことによる dominance 違反。silent ではなく emcc が落とす型)。

## 0. 結論

| 受入 (#2181 本文) | 結果 (実測) |
|---|---|
| 1. F=281 で emcc が dominance 違反 0 | **達成**。変更前: `Instruction does not dominate all uses!` ×4 で emcc 失敗。変更後: `ott_getparam_fixed.ll` を emcc が受理し link まで成功 |
| 2. `icall_tbl_n > 0` を `*_stubs.c` で確認 | **達成**。`icall_tbl_n = 105` (`ott_getparam_stubs.c`)。登録 105 関数 (引数無し i64 関数) |
| 3. FAIL-FAST 経路が発火する入力で wasm_trap に数える (ネガティブコントロール) | **一部達成** (#4299)。直接呼出し (`__icall_dispatch`) で、表に無い target の abort を wasm crash として計数し、表有無で呼出し結果が分かれることを確認 (§4.3)。leafspec の 200 scenario では fail-fast 不発火のまま |
| 4. leafspec `wasm_trap` 0 のまま、T2 の IR 不変 | **達成** (wasm_trap 0)。`tests/test_unit.py` は `ALL UNIT TESTS PASS` (T2 含む)。match は 147/200 で変化なし (#2128 付録と同値) |

leafspec の gate は FAIL のまま (`match_rate_excl_crash` 0.735 < 1.0)。これは #1270 (HB-H29) の範囲で、本 issue の範囲外。

## 1. 測定 config

| 項目 | 値 |
|---|---|
| 測定 commit (コードを変えた最後の commit) | `b1c2d148` (`fix(liftlib): bind iargs call args only where they dominate (#2181)`) |
| 測定 commit 以降の差分 | 本付録と `docs/DOC_MAP.md` の行・`tools/liftlib/REPORT.md` の索引行のみ (下の確認コマンド) |
| 素材 | `$ARTIFACTS_DIR` の `work-liftlib` (raw RetDec .ll と F.txt の作業物)・`work-icall` (`tools/icall/work/ott_F.txt` = F=281)・`analysis-ott-binaries` (OTT_vst2_win64.dll)・`toolchain-emsdk` ([EMSDK])・`toolchain-retdec` ([RETDEC]) |
| 再現 | `cd tools/liftlib && python3 -m liftlib leafspec targets/ott_getparam.json --n 200` (RetDec は raw .ll を再利用。wall 64 秒 = 19:43:23〜19:44:27 の実測) |
| 負荷 | 開始時 load 0.23 / 0.64 / 0.55 (runner 4 コア, 単発) |
| 単体 | `python3 tests/test_unit.py` → `ALL UNIT TESTS PASS` (19:35:45〜19:40:31 の実測, 4 分 46 秒) |

確認コマンド (測定 commit から HEAD までのコード差分。0 なら測定値は現 HEAD で有効):

```
git diff b1c2d148 HEAD -- tools/liftlib/liftlib tools/liftlib/targets tools/icall/rt | wc -l
0
```

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
| 変更後 `b1c2d148` | **成功** (link 成功) | **147 / 53 / 0 / 0** (gate FAIL: rate 0.735, thr 1.00) | 176 | 462 | 376 |

- 変更前の unbound 175 は、`_bind_use` だけを旧動作に戻して lift した値 (`probe` 相当、emcc 前で停止)。
- 基準の 147/53/0/0 は `REPORT_APPENDIX_2128.md` の測定 (F=1) と同値。F=281 にしても match は変わらず、wasm_trap も 0 のまま。
- `site_unbound` の +1 は、支配しない `%55` を使わなくなった `0x1801c2a84` の r8 (子 #2861)。r9 (`lea r9,[rsp+0x40]`) は修正前から rsp 基準の合成対象外で unbound (子 #2861)。

### 4.2 `icall_tbl_n` と stub の内訳 (`pipeline_report.json`)

- `icall_tbl` = 105 (引数無し i64 の `function_*` 登録数)、`stubs` = 35。
- `wasm-ld` 警告 `function signature mismatch: IsDebuggerPresent` は残る (警告のみ・本 issue 外)。

### 4.3 ネガティブコントロール (受入 3) — 一部達成 (#4299)

- 試験ドライバ: `tools/liftlib/harness/icall_probe/` (`probe.c` が BLK+0 に target・BLK+16 に index=19・BLK+24 に 64 byte バッファを置いて `__icall_dispatch` を呼ぶ。`build.py` が通常変種と表空変種を作る。`drive.mjs` が 1 試行 1 プロセスで走らせる。`run_matrix.sh` が 4 試行を流す)。
- 測定 commit: `de7278d5a` (liftlib / icall は `097225b74` と差分 0)。
- 結果 (各試行 1 プロセス。`crashed` = diff.py の `crash` → `wasm_trap` に相当):

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

- 方法: 測定 commit と同内容の作業コピー (cfg の `funcs` だけ `tools/liftlib/work/ott_getparam/F.txt` を使用。`cmp` で `tools/icall/work/ott_F.txt` と一致を確認) で生成した `ott_getparam_stubs.c` の `const unsigned icall_tbl_n = 105;` を `0` に書き換えた変種を emcc で作り、同じ spec・同じ 200 scenario を流す。
- 結果: `match=147 mismatch=53 native_crash=0 wasm_trap=0`。表を空にしても trap は出なかった。
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
| leafspec gate FAIL (match 147/200, rate 0.735) | gate 未達 | #1270 (HB-H29) (既存) |
| iargs を使う他 cfg の回帰 (`_bind_use` の副作用) | 支配しない値を使っていた既存出力の変化 | 本 PR の未解決 (未測定) |
