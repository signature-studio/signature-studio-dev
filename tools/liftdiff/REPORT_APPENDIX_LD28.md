# 付録: liftdiff LD-28 (#1035) — 型 C・D の原因候補・0x417b70 の idiv/udiv 仮説

> **正本**: `tools/liftdiff/REPORT.md` (結論・§7 未解決)。本書は LD-28 (#1035) の節を `REPORT_APPENDIX.md` §9 から分割移動したもの (250 行上限のため)。`REPORT_APPENDIX.md` §9 には参照 1 行のみ残す。
>
> **追跡状態 (2026-10-14 時点)**: #1035 は CLOSED。本書の「#1035 に残す」「#1035 で追跡」は、PM が reopen するか後継 issue を立てるまで未割当の残件を指す。受入条件 3 (`trace_diverge_418be0.py` の除外 1 件の説明) は未達で、チェックしていない。

#### 型 C・D の原因候補 (LD-28 / #1035)
集計 = `tests/trace_diverge_cd.py` → `results/m11_unreachable_cd.md` (件数の正本)。型 A・B (#864 の D15 候補・leaf) を除いた型 C・D の食い違いを対象にする。
- 結論: 型 C・D の食い違いは原因候補 (P1・P2・P3) に分類した。P2 は L が F の直接 call 先であることを条件に含む。内訳は results 参照。
- P2 の代表例 0x418be0 (呼出元 0x41c820) は P2 候補に分類した。IR 側 (`call 0x407030` の欠落) は再確認していない。call site と IR block の対応づけは未実施。
- P2 の全 20 件で F→L の直接 call 辺 (`L ∈ direct_calls(F)`) が成立することを PE 実測で確認した。
- **測定 commit = `200cc2b4`** (PR #1434 の検証 run: `trace_diverge_cd.py` 15.6 s・`results/m11_unreachable_cd.md` と diff 0 行)。同じ 3 ファイルは `516a2b07` (前回 run の記録: 16.56 s・diff 0 行) でも同一内容。`results/m11_unreachable_cd.md` の再実行は、この fix run では素材が無く行っていない。3 ファイルを最後に変えた commit は `8119565c`。
- **鮮度 (#1268・`docs/WORKFLOW.md` §6)**: 測定 commit からの、測定に使う 3 ファイルの差分。
  ```
  $ git diff 200cc2b4 HEAD -- tools/liftdiff/ldlib/pe.py tools/liftdiff/tests/trace_diverge_cd.py tools/liftdiff/results/m11_unreachable_cd.md
  (出力 0 行)
  ```
  以後の commit は REPORT_APPENDIX の文書のみ。
- P2 の全 20 件で `L ∈ direct_calls(F)` が成立 (同一 PE・同一入力で 20/20 を確認)。
- 候補判定は call 先の集合差分のみ。P1・P2 は候補であり確定ではない。
- **0x417b70 (LD-28 受入条件 1・静的確認のみ、動的未確認)**: 食い違いの次 entry 組の件数は `results/m11_unreachable_diverge.md` の表を正本とする (ここには再掲しない)。
  L の機械語は `417c56: idiv qword ptr [rbp+0x60]` (符号付き除算、直前の `cqo` で符号拡張)。機械語は `block00031_PE.bin` (RVA `0x17c56`, ImageBase `0x400000`) で確認。
  IR は `%29 = udiv i64 %28, %arg4` (符号なし) と前回 run で記録したが、**`boot_final3.ll` の行番号は未確認** (素材 `work-m11` が無く、本 fix run では再照合していない)。
  その直後の `icmp eq %29, %27` が偽のとき `call 0x409730; unreachable` へ進む。stride×count が負で count ≥ 2 なら、符号付き除算は stride を返すが符号なし除算は一致しない。count = 1 では一致する (下記)。
  数値例 (積の符号のみ・64bit 整数で計算): −16×2 (count 2)、−32×4、−8×3、−16×3 で udiv は stride を返さず、idiv は返す。反例: count = 1 では udiv も idiv も stride を返し一致する (−16×1 で両方 −16)。
  仮説: 32 件の一部は、この udiv が trap 経路 (0x409730) を誤って取ることで生じる。**未確認**: 32 件の stride 符号・経路の実測、および sdiv への修正後に食い違いが消えるかの再実行。
  `417c7a`〜`417c81` の `dword [rax+4]==1` 判定と 0x409410/0x409470 の分岐も未確認。
  子 issue: #1238 (LD-41) に追記 (動的確認の受入条件を持つ)。

#### 0x418be0 (P2 20 件) の確認 (LD-28 受入条件 1)
- **測定 commit (機械語・IAT の静的確認)**: 検証起点 = `42446b7b` (main 取り込み後の HEAD、コード差分なし)。同じ PE を読む `pe.py` / `trace_diverge_cd.py` / `results/m11_unreachable_cd.md` は `200cc2b4` から本 HEAD まで差分 0 行 (`git diff 200cc2b4 HEAD -- tools/liftdiff/ldlib/pe.py tools/liftdiff/tests/trace_diverge_cd.py tools/liftdiff/results/m11_unreachable_cd.md` の出力 0 行)。
- **results 行 D の読替え**: `results/m11_unreachable_cd.md` の行 D は自動生成のため手で直さない。行 D の「P2 呼出元の直接 call 脱落」は、本節で「thunk 脱落」ではなく **未特定** として読む (下記の結論)。
- **機械語 (前版で確認・本 fix run では未再確認・`fl-win64` の `block00031_PE.bin`・22227016 bytes・ImageBase `0x400000`)**: `0x41c875: e8 66 c3 ff ff` (`call 0x418be0`) と `0x41c88a: e8 a1 a7 fe ff` (`call 0x407030`) を実バイトで確認。`0x407030` は `ff 25 42 9c 56 01` (`jmp qword ptr [rip+...]`) で、IAT スロットは **VA `0x1970c78` = RVA `0x1570c78`** (ImageBase `0x400000` 基準)。スロットの hint/name は `LoadStringW` (user32.dll)。
- **batch 入力 (参考・出所不明)**: 入力 `tools/liftdiff/work/m11/batch_closure.jsonl` = sha256 `810b4d3a03df1cf0b3cc1e004983e8c575bcaeeaa54c4780f7f0bcf2becfb6bf`、49,316,750 bytes、mtime 2026-10-10 08:54 UTC (素材 `work-liftdiff` 内)。`batch_closure.jsonl` には commit 情報が無い。
  - `tests/trace_diverge_418be0.py` は 0x418be0 を最後の共通 entry とする unreachable case を 20 件数える。最初の食い違いは全件で `0x407030` の有無 (native のみ `0x418be0 → 0x407030 → 0x413060`、wasm は `0x418be0 → 0x413060`)。
  - thunk 0x407030 を除いて再比較すると、**参考値として 16 件** で食い違いが残る (直前の共通 entry 0x410320 が 10、0x446290 が 3、0x464c60 が 2、0x414ad0 が 1)。残り 4 件は trace_head 上限 (12 件) で判定不能。
  - 内訳の正本は `results/m11_418be0_thunk.md` (`tests/trace_diverge_418be0.py` で再生成)。16 / 4 は入力の出所が確定するまで受入の根拠に使わない。
  - **現 head での 1 件再生成 (試行)**: `liftdiff.py batch targets/m11.json --set file:<1 件> --shards 1 --nobuild` を HEAD `ad7d455f` で 1 関数実行 (素材 `fl-win64` の `block00031_PE.bin`・`work-m11` の `tools/m11/work`・archive の `ld_wasm.cjs` を使用)。0x41c820 (`results` の代表 caller) は、closure 記録では `mismatch` (pattern 別: s/p0/q0 が `both_fault`/`native_fault`、qall が `diff`) だったが、現 head の 1 件再生成では `match` (pattern 別: s/p0/q0 が `native_fault`、qall が `both_fault`) で、pattern ごとの outcome も一致しない。`1c4b7c7e` 以降に `tools/liftdiff/ldlib`・`liftdiff.py`・`targets`・`rt` の 21 ファイルが変わっており (差分 1345 行)、closure と同じ生成条件ではない。shards 1 と 14 の差は未検証。このため現 head の 1 件値を closure の値の代わりに使わない。全件の再生成は子 issue [LD-60] に切り出す。
  - **生成 commit (未確定)**: 生成 commit・生成コマンドは記録に無い。
    - 素材内 `batch_closure.log` (`[batch] 7421 functions, shards=14` 〜 `done 602s`・ログ mtime 08:30:33 UTC) から、開始は 08:20:31 UTC (17:20:31 JST)、終了は 08:30:33 UTC と読める。
    - `[batch] done` 出力を持つ harness の初出 commit は `1c4b7c7e` (08:36:56 UTC = 17:36:56 JST) で、生成はそれより前。よって生成は当時の未 commit 作業ツリーで行われた可能性が高い (推定)。
    - 入力のパターン 9 種 (`z, s, p0, p1, p01, pall, pall2, q0, qall`) は `ldlib/cases.py` (`1c4b7c7e` で初めて追加) と一致する。
    - 確定には `fl-win64` と `work-m11` を要する再走が必要。本 run では素材が無く未実施。
- **IR 側の `call 0x407030` 脱落**: 本 run では未確認。前 run (#1569) で「IR は `@LoadStringW` を直接呼ぶ・thunk 経由なし」と記録済み。thunk を除いても 16 件が食い違うため、thunk の脱落は原因ではなく表現差 (#1569 と整合)。
- **結論**: 0x418be0 系の原因は未特定。食い違いの次段は 0x410320 (VMT 間接 call の関数・LD-17 の D15 型候補と同じ entry) が最多で、0x410320 以後の分岐が次の調査対象。受入条件 1 の 0x418be0 は、thunk の表現差の切り分けまで完了・原因は未達 → #1035 に残す。
- **再現手順**: `python3 tools/liftdiff/tests/trace_diverge_418be0.py > tools/liftdiff/results/m11_418be0_thunk.md` (リポジトリルートから実行。既定入力 `tools/liftdiff/work/m11/batch_closure.jsonl`。PE・IR 不要、batch jsonl のみ)。素材は `work-liftdiff` (`tools/liftdiff/work/`)。

#### 現 head での全件再生成と記録の比較 (LD-60 / #1736)
- **測定 commit = `576c4976`** (`origin/main`。本 PR の変更は REPORT のみ。`git diff 576c4976 HEAD -- tools/liftdiff` は空)。
- **コマンド**: `FL_WIN64_DIR=<fl-win64 展開先> python3 tools/liftdiff/liftdiff.py batch tools/liftdiff/targets/m11.json --set closure --shards 14 --nobuild --out tools/liftdiff/work/m11/batch_closure_head.jsonl` (build は同じ target で事前に実施)。
- **入力・出力 sha256**: 素材 `block00031_PE.bin` = `b2c64da4…9496d` (22,227,016 bytes)。比較対象の記録 `batch_closure.jsonl` = `810b4d3a…bf6` (49,316,750 bytes)。再生成出力 `batch_closure_head.jsonl` = `b7990688…ae462` (51,854,845 bytes)。
- **所要**: 858 s (shards 14・4 コア・開始時 load average 0.41・RC 0)。
- **集計 (一致 / 不一致 / 実行不能)**: 記録 2,273 / 2,892 / 2,256 → 現 head 3,233 / 1,488 / 2,700 (関数数 7,421)。
- **0x418be0 系**: 現 head の再生成では `trace_diverge_418be0.py` の対象 (unreachable・直前共通 entry 0x418be0) が **0 件**。記録は 20 件 (16 + 4)。0x418be0 単体は記録・現 head ともに `match`。
- **0x41c820**: 記録 `mismatch` → 現 head `match`。pattern 別 outcome も変わる (qall `diff` → `both_fault`)。
- **差の規模**: verdict が変わった関数 1,807 件。記録と pattern 別 outcome が完全一致した関数は 50 件 / 7,421。現 head は pattern 集合が 9 → 11 (`vm0`・`u16` を追加) で、記録と生成条件が異なる。
- **shards 1 と 14 の差** (関数 302 件 = 乱数 300 件 + 0x418be0 + 0x41c820・`random.Random(7)`): verdict 一致 276 / 302、pattern 別 outcome 一致 232 / 302。shard 数で結果が変わるため、shards 14 の値は shards 1 と同一とみなせない。0x418be0 と 0x41c820 は両 shard 数とも同じ verdict (match)。
- **結論**: 受入条件 1 (commit・sha256・件数の記録) は満たす。条件 2 (差の説明) は規模を定量化したが原因は未特定。条件 4 (0x418be0 系 20 / 16 / 4 の一致) は **未達**。現 head の全件再生成では 0x418be0 系は再現せず、20 / 16 / 4 は受入の根拠に使えない。#1035 の受入条件 1 は [~] のまま。

#### 生成 commit の候補再生成と shards 反復 (LD-74 / #2012)
- **測定 commit = `c171b9dc`** (main 取り込み後の HEAD の基点。head 系の測定はこの commit で行った)。候補 commit は `1c4b7c7e` / `9e9c1315` / `38d53ac8` / `930c6dbc` (`git worktree` の detached checkout で測定)。
- **コード差分 (候補範囲)**: `git diff 1c4b7c7e 930c6dbc -- tools/liftdiff/ldlib tools/liftdiff/liftdiff.py tools/liftdiff/targets tools/liftdiff/rt` は出力 0 行。候補範囲で変わったのは docs だけ。
- **入力の確認**: `work/m11/batch_closure.jsonl` の sha256 = `810b4d3a…bf6` (記録と一致)。jsonl から数えた集計は 2,273 / 2,892 / 2,256 で REPORT と一致。一方、同素材 `batch_closure.log` 末尾の集計 2,275 / 2,885 / 2,261 は jsonl と一致しない (log の集計は別の run の値の可能性)。
- **対象 2 関数の再生成** (`--set file:<2 件>`・既定ビルド):

  | commit | shards | 0x418be0 | 0x41c820 | pattern 別 outcome (記録と一致) |
  |---|---:|---|---|---|
  | `c171b9dc` (HEAD) | 1 | match | match | 0x418be0 は 11 pattern (vm0・u16 追加)、0x41c820 は s/p0/p1/q0 で native_fault、qall で both_fault |
  | `c171b9dc` (HEAD) | 14 × 2 回 | match | match | 2 回とも上と同一 |
  | `1c4b7c7e` | 1 | match | match | 0x418be0 一致 / 0x41c820 不一致 |
  | `1c4b7c7e` | 14 × 2 回 | match | match | 2 回とも同一 |
  | `9e9c1315` | 1 | match | match | 0x418be0 一致 / 0x41c820 不一致 |
  | `38d53ac8` | 1 | match | match | 0x418be0 一致 / 0x41c820 不一致 |
  | `930c6dbc` | 1 | match | match | 0x418be0 一致 / 0x41c820 不一致 |

  記録の 0x41c820 は `mismatch` (qall `diff`) だが、いずれの候補でも `match` (qall `both_fault`)。shard 1 と 14 の間、また同一 shard 数の反復の間では、この 2 関数の判定は変わらなかった。
- **全件 closure の再生成 (`1c4b7c7e`・shards 14・`--nobuild`)**: 632 s (wall 10 m 32 s)・開始時 load average 約 1.0。集計 3,091 / 1,525 / 2,805 (記録 2,273 / 2,892 / 2,256 とも HEAD の 3,233 / 1,488 / 2,700 とも不一致)。記録と verdict が同じ関数は 5,704 / 7,421。
  - **注意 (未確定)**: `--nobuild` のため、ビルド物は work-m11 archive 同梱の `ld_wasm.cjs` で、`1c4b7c7e` のソースからは作っていない。候補 commit の全件判定は、候補ごとにビルドし直した全件再生成が必要。
- **`tests/trace_diverge_418be0.py` の再現**: 記録 jsonl では 20 件 (16 + 4) を再現 (`results/m11_418be0_thunk.md` と同じ表)。`1c4b7c7e` の全件 jsonl に対しては、`trace_head` 文字列の解析で `ValueError` (rc 1) になり、集計できなかった。
- **結論**: 生成 commit は未特定。候補 4 件のいずれも、対象 2 関数の再生成では記録の `0x41c820 mismatch` を再現しなかった。全件の候補別 rebuild と、`trace_diverge_418be0.py` の解析の堅牢化が残る。#1035 の受入条件 1 は [~] のまま。

#### 生成 commit 候補 `9e9c1315` の全件 rebuild (LD-100 / #2276)
- **測定 commit = `9e9c1315`** (候補 commit を detached worktree で checkout・`git worktree add --detach ../ws-2276-9e9c1315 9e9c1315`)。`9e9c1315` は `38d53ac8` の子で、変更は docs (`FORMAT.md` §3) のみ。`git diff 9e9c1315 origin/main -- tools/liftdiff/ldlib tools/liftdiff/liftdiff.py tools/liftdiff/targets tools/liftdiff/rt` の stat は 25 files・+1528 / -91 (1,528 + 91 = **1,619 行**。main 取り込み後の差分)。比較基準の origin/main は `d1bbec7c` (本修正時点)。PR head `7b90bae9` から見た同じ範囲も 25 files・+1528 / -91 で一致する。本節の判定は候補 commit のソースに対するもので、main の HEAD の判定ではない。
- **ビルド**: `liftdiff.py build` (`targets/m11.json` の `pe` を fl-win64 展開先へ向けた複製 target) → rc 0・`sig_mismatch` 0・`undefined` 1 (WindowFromPoint の stub skip 1 件)・wasm 4,439,240 bytes。
- **全件 closure** (`batch --set closure --shards 14 --nobuild`・候補ビルド物): wall 11 m 22 s (開始時 load average 約 1.0・終了時 7.2)・rc 0。出力 `work/m11/batch_closure_9e9c1315.jsonl` (sha256 先頭 16 桁 `2b6a31200bd38f32`・7,421 行)。
  - 集計: **一致 3,092 / 不一致 1,524 / 実行不能 2,805** (記録 2,273 / 2,892 / 2,256 と不一致。前節の `1c4b7c7e` の全件再生成 (`--nobuild`・ビルド物は work-m11 同梱) 3,091 / 1,525 / 2,805 とほぼ同じ。ただし本節は候補ソースからビルドし直した値)。
  - 記録の `batch_closure.jsonl` (sha256 先頭 16 桁 `810b4d3a03df1cf0`) との verdict 一致は 5,705 / 7,421 (`1c4b7c7e` の 5,704 / 7,421 より 1 件多い)。
  - 実行不能の内訳: native_fault_all_patterns 1,342 / native_null_deref_all_patterns 1,102 / hang 311 / unsupported_sig 50。
- **対象 2 関数** (全件 jsonl から): 0x418be0 = **match** (記録 match・一致)。0x41c820 = **match** (記録 mismatch・**不一致**。記録の mismatch は候補 `9e9c1315` の rebuild で再現しなかった)。
- **`tests/trace_diverge_418be0.py` (main の HEAD 時点の版) の全件 jsonl**: rc 0 で終了。出力 = 対象 0 件・thunk 除去後の食い違い 0 件・trace 上限で判定不能 0 件・**解析不能で丸ごと除外 1 件**。前節の `1c4b7c7e` の全件 jsonl では rc 1 (`ValueError`) だった。本節で rc 0 になった理由は未切り分け。版: 測定に使った script は main 版で、その blob は `b679a99a` (PR head `7b90bae9` の `tests/trace_diverge_418be0.py` と同一)。ただし当時この blob を実際に使ったことは、本修正 run では再検証できない (入力 jsonl が runner に残っていない)。`9e9c1315` には当該 script が存在しない (main で後から追加)。**除外 1 件のレコード ID (関数 addr・record 番号) と例外メッセージは未記録・未確認**。`1c4b7c7e` の rc 1 (`ValueError`・上記) と同じ例外かも未確認。したがって本節の受入は「rc 0 で終わり、除外数 (1 件) を出力に含む」まで。「除外 0 件」とは主張しない。出力は `results/m11_418be0_thunk.md` を上書きせず、`$RUNNER_TEMP` に置いた (commit しない)。全件 jsonl の 0x418be0 系は 0 件のため、記録の 20 / 16 / 4 の表は再現していない。
- **結論**: `9e9c1315` をソースからビルドし直した全件 closure は記録 (2,273 / 2,892 / 2,256) と一致しない (3,092 / 1,524 / 2,805)。0x41c820 の記録 mismatch は、この候補の rebuild では再現しない (qall は `match`)。記録と候補の差の原因は未特定 (ビルド条件・work-m11 の由来の切り分けは未実施)。#1035 の受入条件 1 は [~] のまま。
- **HEAD との関係 (§6・鮮度)**: 本判定は候補 `9e9c1315` 自体のもので、**現 HEAD の挙動は主張しない**。HEAD (`7b90bae9`) との liftdiff コード差分は以下 (`git diff --stat 9e9c1315 HEAD -- tools/liftdiff/ldlib tools/liftdiff/liftdiff.py tools/liftdiff/targets tools/liftdiff/rt` の出力・1,528 + 91 = 1,619 行)。
  ```
   tools/liftdiff/ldlib/boot.py                | 160 +++++++++---
   tools/liftdiff/ldlib/build_wasm.py          |  17 +-
   tools/liftdiff/ldlib/cases.py               |  51 ++++
   tools/liftdiff/ldlib/classify.py            |  39 ++-
   tools/liftdiff/ldlib/clift.py               | 217 ++++++++++++++++
   tools/liftdiff/ldlib/compare.py             |  58 ++++-
   tools/liftdiff/ldlib/irtool.py              |  33 ++-
   tools/liftdiff/ldlib/pe.py                  |   9 +-
   tools/liftdiff/ldlib/runners.py             |  24 +-
   tools/liftdiff/ldlib/session.py             |  64 ++++-
   tools/liftdiff/liftdiff.py                  |  23 +-
   tools/liftdiff/rt/fle_ldbridge.c            | 183 ++++++++++++++
   tools/liftdiff/rt/fle_runner.mjs            | 125 ++++++++++
   tools/liftdiff/rt/ld_core.h                 | 368 +++++++++++++++++++++++++++-
   tools/liftdiff/rt/ld_ms_call.S              |   1 +
   tools/liftdiff/rt/ld_native.c               | 115 ++++++++-
   tools/liftdiff/rt/ld_runner.mjs             |   4 +-
   tools/liftdiff/rt/ld_wasm.c                 |  19 +-
   tools/liftdiff/targets/flelift.json         |  20 ++
   tools/liftdiff/targets/m11.json             |   4 +-
   tools/liftdiff/targets/m11_f4_post.json     |  18 ++
   tools/liftdiff/targets/m11_f4_pre.json      |  18 ++
   tools/liftdiff/targets/ott_old.json         |   2 +-
   tools/liftdiff/targets/ott_old_blk.json     |  18 ++
   tools/liftdiff/targets/ott_old_blk_off.json |  29 +++
   25 files changed, 1528 insertions(+), 91 deletions(-)
  ```
  `tools/liftdiff` 全体では 157 files・+21407 / -226 (docs・results 等を含む)。本 PR は REPORT のみ変更し、コードは変えない。
- **素材の実在確認 (本修正 run・`ls` 結果)**: `ls $HOME/artifacts` = `fl-win64.tar.zst` (2,324,302,252 bytes) のみ。`tools/liftdiff/work/` は不在。`work-m11` / `work-liftdiff` / `toolchain-emsdk` / `toolchain-retdec` は本 run に無く、全件 closure の再実行・`trace_diverge_418be0.py` 入力の再照合は未実施。上記の PR 本文の「展開」記述は前 run の記録であり、本 run では再確認できない。

#### 候補 `1c4b7c7e` の全件 closure rebuild (LD-91 / #2242)
- **測定 commit = `1c4b7c7e`** (コードを変えた最後の commit。detached worktree で測定)。素材は `fl-win64` + `work-m11` + `work-liftdiff` (`tools/liftdiff/work/m11/batch_closure.jsonl` は記録と同一素材)。
- **ビルド**: `liftdiff.py build` を `1c4b7c7e` のソースから実行 (rc 0・`sig_mismatch 0`・`undefined 1`・wasm 4,439,240 B)。`--nobuild` の前回値 (LD-74) とは異なり、ビルド物は候補 commit 由来。
- **batch**: `batch --set closure --shards 14 --nobuild` (ビルド直後・`targets/m11_local_2242.json` は `pe` だけ `fl-win64` 展開先へ向けた複製。`targets/m11.json` の `pe` は `/home/ubuntu/...` 固定のため、repo の target は変更していない)。rc 0・**約 9 分 42 秒** (10:47:49 → 10:57:31)・開始時 load 0.94 / 終了時 load 6.23 (shards 14 のため上昇)。
- **集計**: 一致 3,092 / 不一致 1,524 / 実行不能 2,805 (記録 2,273 / 2,892 / 2,256 と不一致・前回 `--nobuild` の 3,091 / 1,525 / 2,805 とほぼ同じ)。**前 run の記録**: 修正 run (`e72196b2`) では work-m11 / work-liftdiff が無く再実行していない。
- **記録との verdict 一致**: 7,421 関数中 5,705 (前回 `--nobuild` は 5,704)。
- **対象 2 関数**: `0x418be0` = 記録 match / rebuild match。`0x41c820` = 記録 mismatch / rebuild match (記録の mismatch は再現せず)。
- **`trace_diverge_418be0.py` (rc 0)**: 本 commit の `tests/` には当該スクリプトが無いため、main の版 (`500acb3d` / `c00790d1` 反映済み) を入力 jsonl に与えた。除外 1 件 (解析不能要素)・対象 0 件 (`0x418be0` の共通 entry 直後の食い違いが無い)。記録 jsonl で得た 20 件 (16 + 4) は、この rebuild では再現しない。
- **結論**: `1c4b7c7e` は記録 (2,273 / 2,892 / 2,256) の生成 commit ではない。`0x41c820` mismatch も再現しない。残りの候補 `9e9c1315` / `38d53ac8` / `930c6dbc` は子 issue に切り出す (1 run に収まらないため): #2276 (`9e9c1315`) / #2277 (`38d53ac8`) / #2278 (`930c6dbc`)。
- **コード差分 (測定 commit → HEAD・候補の判定に影響する範囲)**: `git diff 1c4b7c7e origin/main -- tools/liftdiff/ldlib tools/liftdiff/liftdiff.py tools/liftdiff/targets tools/liftdiff/rt` は 25 ファイル・+1,528 / -91 行 (LD-74 の「候補範囲で差分 0」は、この範囲には当てはまらない)。
