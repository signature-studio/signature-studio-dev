# 付録: liftdiff LD-28 (#1035) — 型 C・D の原因候補・0x417b70 の idiv/udiv 仮説

> **正本**: `tools/liftdiff/REPORT.md` (結論・§7 未解決)。本書は LD-28 (#1035) の節を `REPORT_APPENDIX.md` §9 から分割移動したもの (250 行上限のため)。`REPORT_APPENDIX.md` §9 には参照 1 行のみ残す。

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
- **batch 実測 (入力 sha256 `810b4d3a` で再生成し一致・本 run で確認)**: 入力 `tools/liftdiff/work/m11/batch_closure.jsonl` = sha256 `810b4d3a03df1cf0b3cc1e004983e8c575bcaeeaa54c4780f7f0bcf2becfb6bf`、49,316,750 bytes、mtime 2026-10-10 08:54 UTC (素材 `work-liftdiff` 内)。`python3 tools/liftdiff/tests/trace_diverge_418be0.py` の出力を `results/m11_418be0_thunk.md` と比較し **diff 0 行で一致**。0x418be0 を最後の共通 entry とする unreachable case は 20 件。最初の食い違いは全件で `0x407030` の有無 (native のみ `0x418be0 → 0x407030 → 0x413060`、wasm は `0x418be0 → 0x413060`)。
  - thunk 0x407030 を除いて再比較すると、16 件で trace_head 内に食い違いが残る (直前の共通 entry 0x410320 が 10、0x446290 が 3、0x464c60 が 2、0x414ad0 が 1)。残り 4 件は trace_head 上限 (12 件) で判定不能。
  - 内訳と件数の正本は `results/m11_418be0_thunk.md` (`tests/trace_diverge_418be0.py` で再生成)。
  - **生成 commit (未確定)**: 生成 commit・生成コマンドは記録に無い。`batch_closure.log` の最終行 (`done 602s`) の mtime は 08:30:33 UTC で、開始は約 08:20 UTC と読める。これは harness の commit `1c4b7c7e` (08:36 UTC) より前であり、生成はコミットされていない作業ツリーで行われた可能性がある。入力のパターン 9 種 (`z, s, p0, p1, p01, pall, pall2, q0, qall`) は `ldlib/cases.py` (`1c4b7c7e` で初めて追加) と一致し、後から追加された `fvm` 等を含まない。つまり `1c4b7c7e` 以降の harness で生成された可能性はあるが、commit 単位の特定はできていない。確定には `fb30426c` での再走 (native PE `fl-win64` が要る) が必要で、本 run では素材が無く未実施。
  - 「16 件」「4 件」は入力 sha256 `810b4d3a` の再生成で一致 (上記)。内訳 (0x410320 ×10・0x446290 ×3・0x464c60 ×2・0x414ad0 ×1) も再生成結果と一致。
- **IR 側の `call 0x407030` 脱落**: 本 run では未確認。前 run (#1569) で「IR は `@LoadStringW` を直接呼ぶ・thunk 経由なし」と記録済み。thunk を除いても 16 件が食い違うため、thunk の脱落は原因ではなく表現差 (#1569 と整合)。
- **結論**: 0x418be0 系の原因は未特定。食い違いの次段は 0x410320 (VMT 間接 call の関数・LD-17 の D15 型候補と同じ entry) が最多で、0x410320 以後の分岐が次の調査対象。受入条件 1 の 0x418be0 は、thunk の表現差の切り分けまで完了・原因は未達 → #1035 に残す。
- **再現手順**: `python3 tools/liftdiff/tests/trace_diverge_418be0.py > tools/liftdiff/results/m11_418be0_thunk.md` (リポジトリルートから実行。既定入力 `tools/liftdiff/work/m11/batch_closure.jsonl`。PE・IR 不要、batch jsonl のみ)。素材は `work-liftdiff` (`tools/liftdiff/work/`)。
