# 付録: liftdiff LD-28 (#1035) — 型 C・D の原因候補・0x417b70 の idiv/udiv 仮説

> **正本**: `tools/liftdiff/REPORT.md` (結論・§7 未解決)。本書は LD-28 (#1035) の節を `REPORT_APPENDIX.md` §9 から分割移動したもの (250 行上限のため)。`REPORT_APPENDIX.md` §9 には参照 1 行のみ残す。

#### 型 C・D の原因候補 (LD-28 / #1035)
集計 = `tests/trace_diverge_cd.py` → `results/m11_unreachable_cd.md` (件数の正本)。型 A・B (#864 の D15 候補・leaf) を除いた型 C・D の食い違いを対象にする。
- 結論: 型 C・D の食い違いは原因候補 (P1・P2・P3) に分類した。P2 は L が F の直接 call 先であることを条件に含む。内訳は results 参照。
- P2 の代表例 0x418be0 (呼出元 0x41c820) は P2 候補に分類した。IR 側 (`call 0x407030` の欠落) は再確認していない。call site と IR block の対応づけは未実施。
- P2 の全 20 件で F→L の直接 call 辺 (`L ∈ direct_calls(F)`) が成立することを PE 実測で確認した。
- **測定 commit = `200cc2b4`** (PR #1434 の検証 run: `trace_diverge_cd.py` 15.6 s・`results/m11_unreachable_cd.md` と diff 0 行)。同じ 3 ファイルは `516a2b07` (前回 run の記録: 16.56 s・diff 0 行) でも同一内容。`results/m11_unreachable_cd.md` の再実行は本 run では行っていない (前版 run の記録)。3 ファイルを最後に変えた commit は `8119565c`。
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
  IR は `%29 = udiv i64 %28, %arg4` (符号なし) と前回 run で記録したが、**`boot_final3.ll` の行番号は未確認** (本 run でも再照合していない)。
  その直後の `icmp eq %29, %27` が偽のとき `call 0x409730; unreachable` へ進む。stride×count が負で count ≥ 2 なら、符号付き除算は stride を返すが符号なし除算は一致しない。count = 1 では一致する (下記)。
  数値例 (積の符号のみ・64bit 整数で計算): −16×2 (count 2)、−32×4、−8×3、−16×3 で udiv は stride を返さず、idiv は返す。反例: count = 1 では udiv も idiv も stride を返し一致する (−16×1 で両方 −16)。
  仮説: 32 件の一部は、この udiv が trap 経路 (0x409730) を誤って取ることで生じる。**未確認**: 32 件の stride 符号・経路の実測、および sdiv への修正後に食い違いが消えるかの再実行。
  `417c7a`〜`417c81` の `dword [rax+4]==1` 判定と 0x409410/0x409470 の分岐も未確認。
  子 issue: #1238 (LD-41) に追記 (動的確認の受入条件を持つ)。

#### 0x418be0 (P2 20 件) の確認 (LD-28 受入条件 1)
- **測定 commit (機械語・IAT の静的確認)**: 検証起点 = `42446b7b` (main 取り込み後の HEAD、コード差分なし)。同じ PE を読む `pe.py` / `trace_diverge_cd.py` / `results/m11_unreachable_cd.md` は `200cc2b4` から本 HEAD まで差分 0 行 (`git diff 200cc2b4 HEAD -- tools/liftdiff/ldlib/pe.py tools/liftdiff/tests/trace_diverge_cd.py tools/liftdiff/results/m11_unreachable_cd.md` の出力 0 行)。
- **results 行 D の読替え**: `results/m11_unreachable_cd.md` の行 D は自動生成のため手で直さない。行 D の「P2 呼出元の直接 call 脱落」は、本節で「thunk 脱落」ではなく **未特定** として読む (下記の結論)。
- **機械語 (前版 run の記録・本 run では未再確認・`fl-win64` の `block00031_PE.bin`・22227016 bytes・ImageBase `0x400000`)**: `0x41c875: e8 66 c3 ff ff` (`call 0x418be0`) と `0x41c88a: e8 a1 a7 fe ff` (`call 0x407030`) を実バイトで確認。`0x407030` は `ff 25 42 9c 56 01` (`jmp qword ptr [rip+...]`) で、IAT スロットは **VA `0x1970c78` = RVA `0x1570c78`** (ImageBase `0x400000` 基準)。スロットの hint/name は `LoadStringW` (user32.dll)。
- **batch 入力 (参考・出所不明)**: 入力 `tools/liftdiff/work/m11/batch_closure.jsonl` = sha256 `810b4d3a03df1cf0b3cc1e004983e8c575bcaeeaa54c4780f7f0bcf2becfb6bf`、49,316,750 bytes、mtime 2026-10-10 08:54 UTC (素材 `work-liftdiff` 内)。`batch_closure.jsonl` には commit 情報が無い。
  - `tests/trace_diverge_418be0.py` は 0x418be0 を最後の共通 entry とする unreachable case を 20 件数える。最初の食い違いは全件で `0x407030` の有無 (native のみ `0x418be0 → 0x407030 → 0x413060`、wasm は `0x418be0 → 0x413060`)。
  - thunk 0x407030 を除いて再比較すると、**参考値として 16 件** で食い違いが残る (直前の共通 entry 0x410320 が 10、0x446290 が 3、0x464c60 が 2、0x414ad0 が 1)。残り 4 件は trace_head 上限 (12 件) で判定不能。
  - 内訳の正本は `results/m11_418be0_thunk.md` (`tests/trace_diverge_418be0.py` で再生成)。16 / 4 は入力の出所が確定するまで受入の根拠に使わない。
  - **現 head での 1 件再生成 (試行)**: `liftdiff.py batch targets/m11.json --set file:<1 件> --shards 1 --nobuild` を HEAD `ad7d455f` で 1 関数実行 (素材 `fl-win64` の `block00031_PE.bin`・`work-m11` の `tools/m11/work`・archive の `ld_wasm.cjs` を使用)。0x41c820 (`results` の代表 caller) は、closure 記録では `mismatch` (pattern 別: s/p0/q0 が `both_fault`/`native_fault`、qall が `diff`) だったが、現 head の 1 件再生成では `match` (pattern 別: s/p0/q0 が `native_fault`、qall が `both_fault`) で、pattern ごとの outcome も一致しない。`1c4b7c7e` 以降に `tools/liftdiff/ldlib`・`liftdiff.py`・`targets`・`rt` の 21 ファイルが変わっており (差分 1345 行)、closure と同じ生成条件ではない。shards 1 と 14 の差は未検証。このため現 head の 1 件値を closure の値の代わりに使わない。全件の再生成は子 issue [LD-60] に切り出す。
  - **生成 commit (未確定)**: 生成 commit・生成コマンドは記録に無い。
    - 素材内 `batch_closure.log` (`[batch] 7421 functions, shards=14` 〜 `done 602s`・ログ mtime 08:30:33 UTC) から、開始は 08:20:31 UTC (17:20:31 JST)、終了は 08:30:33 UTC と読める。
    - `[batch] done` 出力を持つ harness の初出 commit は `1c4b7c7e` (08:36:56 UTC = 17:36:56 JST) で、生成はそれより前。よって生成は当時の未 commit 作業ツリーで行われた可能性が高い (推定)。
    - 入力のパターン 9 種 (`z, s, p0, p1, p01, pall, pall2, q0, qall`) は `ldlib/cases.py` (`1c4b7c7e` で初めて追加) と一致する。
    - 確定には `fl-win64` と `work-m11` を要する再走が必要。本 run では未実施 (素材は展開済みだが、生成 commit の特定は行っていない)。
- **IR 側の `call 0x407030` 脱落**: 本 run では未確認。前 run (#1569) で「IR は `@LoadStringW` を直接呼ぶ・thunk 経由なし」と記録済み。thunk を除いても 16 件が食い違うため、thunk の脱落は原因ではなく表現差 (#1569 と整合)。
- **結論**: 0x418be0 系の原因は未特定。食い違いの次段は 0x410320 (VMT 間接 call の関数・LD-17 の D15 型候補と同じ entry) が最多で、0x410320 以後の分岐が次の調査対象。受入条件 1 の 0x418be0 は、thunk の表現差の切り分けまで完了・原因は未達 → #1035 に残す。
- **再現手順**: `python3 tools/liftdiff/tests/trace_diverge_418be0.py > tools/liftdiff/results/m11_418be0_thunk.md` (リポジトリルートから実行。既定入力 `tools/liftdiff/work/m11/batch_closure.jsonl`。PE・IR 不要、batch jsonl のみ)。素材は `work-liftdiff` (`tools/liftdiff/work/`)。

#### 現 head での全件再生成と記録の比較 (LD-60 / #1736)
- **測定 commit = `576c4976`** (測定時の `origin/main`)。注: 同一コードという前版の主張は誤りだった。fix run で `git diff 576c4976 8a75e60a -- tools/liftdiff` を確認すると 17 ファイル・444 行追加の差分があり、空ではない。よって本節の再生成値は 576c4976 のコードで得たものと同一とは言えない。
  - 比較 (HEAD `5ab85337`): `git diff 576c4976 HEAD -- tools/liftdiff` = 20 files・587 insertions・6 deletions (main 取り込み merge 825251d5 を含む)。PR 自身の差分 (`git diff origin/main HEAD -- tools/liftdiff`) は `REPORT_APPENDIX_LD28.md` のみ (13 insertions・2 deletions)。
- **コマンド**: `FL_WIN64_DIR=<fl-win64 展開先> python3 tools/liftdiff/liftdiff.py batch tools/liftdiff/targets/m11.json --set closure --shards 14 --nobuild --out tools/liftdiff/work/m11/batch_closure_head.jsonl` (build は同じ target で事前に実施)。
- **入力・出力 sha256**: 素材 `block00031_PE.bin` = `b2c64da4…9496d` (22,227,016 bytes)。比較対象の記録 `batch_closure.jsonl` = `810b4d3a…bf6` (49,316,750 bytes)。再生成出力 `batch_closure_head.jsonl` = `b7990688…ae462` (51,854,845 bytes)。
- **所要**: 858 s (shards 14・4 コア・開始時 load average 0.41・RC 0)。
- **集計 (一致 / 不一致 / 実行不能)**: 記録 2,273 / 2,892 / 2,256 → 現 head 3,233 / 1,488 / 2,700 (関数数 7,421)。
- **0x418be0 系**: 現 head の再生成では `trace_diverge_418be0.py` の対象 (unreachable・直前共通 entry 0x418be0) が **0 件**。記録は 20 件 (16 + 4)。0x418be0 単体は記録・現 head ともに `match`。
- **0x41c820**: 記録 `mismatch` → 現 head `match`。pattern 別 outcome も変わる (qall `diff` → `both_fault`)。
- **差の規模**: verdict が変わった関数 1,807 件。記録と pattern 別 outcome が完全一致した関数は 50 件 / 7,421。現 head は pattern 集合が 9 → 11 (`vm0`・`u16` を追加) で、記録と生成条件が異なる。
- **shards 1 と 14 の差** (関数 302 件 = 乱数 300 件 + 0x418be0 + 0x41c820・`random.Random(7)`): verdict 一致 276 / 302、pattern 別 outcome 一致 232 / 302。shard 数で結果が変わるため、shards 14 の値は shards 1 と同一とみなせない。0x418be0 と 0x41c820 は両 shard 数とも同じ verdict (match)。
- **結論**: 0x418be0 系の件数 (20 / 16 / 4) の出所は **部分的** にしか確定しない。入力の sha256・件数・集計は記録済み。生成 commit は未特定のため、受入条件 1 の「生成 commit」は未達。条件 2 (差の説明) は規模を定量化したが原因は未特定。条件 4 (0x418be0 系 20 / 16 / 4 の一致) は **未達**。現 head の全件再生成では 0x418be0 系は再現せず、20 / 16 / 4 は受入の根拠に使えない。
- **#1035 の状態**: #1035 は CLOSED。本文の「[~] のまま」表記は現状と合わない。未達分は後継 #2012 (LD-74・OPEN) と #1736 (LD-60・OPEN) に移管済み。本 PR では #1035 の状態を変更しない。

#### batch_closure.jsonl の出所の再確認 (LD-70 / #1960)
- **確認した素材**: `work-liftdiff` の `tools/liftdiff/work/m11/batch_closure.jsonl` (sha256 `810b4d3a…bf6`・49,316,750 bytes・mtime 2026-10-10 08:54:42 UTC) と `batch_closure.log` (mtime 08:30:33 UTC・`[batch] 7421 functions, shards=14`・`done 602s`)。`build.json` の wasm は `sig_mismatch` 0・`undefined` 1。
- **jsonl の集計 (実測)**: match 2,273 / mismatch 2,892 / unexec 2,256 (計 7,421)。REPORT の値と一致。pattern 集合は 9 種 (z, s, p0, p1, p01, pall, pall2, q0, qall) が 7,371 件、空が 50 件。`liftdiff_version` は全件 1。
- **同一 run 性 (時刻)**: `batch_closure.log` の done は 08:30:33 UTC、`batch_closure.jsonl` の mtime は 08:54:42 UTC で 24 分ずれている。mtime は jsonl の最終書込み時刻であり、log の done と一致しない。よって両者が同一 run の出力であることは確認できていない。
- **本 run の検算 (実測・HEAD `5ab85337`)**: `$ARTIFACTS_DIR` の `work-liftdiff` / `work-m11` を展開して測定。`sha256sum tools/liftdiff/work/m11/batch_closure.jsonl` = `810b4d3a03df1cf0b3cc1e004983e8c575bcaeeaa54c4780f7f0bcf2becfb6bf` (記録と一致)、49,316,750 bytes、mtime 2026-10-10 08:54:42 UTC。集計 (実測): match 2,273 / mismatch 2,892 / unexec 2,256 (計 7,421、`liftdiff_version` 全件 1)。pattern 集合は 9 種 (z, s, p0, p1, p01, pall, pall2, q0, qall) が 7,371 件、空が 50 件。
- **ログ末尾の集計との不一致**: `batch_closure.log` の `関数数 7421: 一致 2275 / 不一致 2885 / 実行不能 2261` は jsonl の集計と一致しない (match +2・mismatch −7・unexec +5)。ログと jsonl が同一 run の出力かは確認できていない。
- **生成 commit**: 特定できず。`git log -S` で `batch_closure` / `[batch] done` / `wasm_trap` を探しても、記録に対応する commit は残っていない。`ldlib/cases.py` で `vm0`・`u16` が追加されたのは `79584ef7` (2026-10-13) で、jsonl の 9 pattern はそれより前の集合と整合する。ただし commit は一意に決まらない。
- **再生成との対応**: `python3 tools/liftdiff/tests/trace_diverge_418be0.py` の出力は `results/m11_418be0_thunk.md` と diff 0 行で一致 (本 run・HEAD `5ab85337` で実測: rc 0・0.81 s・出力 18 行)。
- **未解決**: (a) 生成 commit の特定と、その commit での 0x418be0 系 20 / 16 / 4 の再走、(b) 現 head と記録の差 (pattern 別 outcome) の説明、(c) shards 1 と 14 の差の原因 (0x418be0 / 0x41c820 の単体 run で非決定性か shard 間の状態共有かを切り分ける)。
