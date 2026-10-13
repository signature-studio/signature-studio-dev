# liftdiff LD-42 (#1248): 既定 batch の boot 状態判断と TLS index 充足 (部分達成)

親: #977 (LD-25) / 関連: `REPORT_APPENDIX_LD25.md`。本付録は #1248 の実測と判断。受入条件のうち「遷移の各関数の差分根拠」は未達 (§5)。

## 1. 測定 (実測・2026-10-13)

測定 commit: `2b2faf52` (origin/main。本 PR は `tests/ld42_transition.py` の追加と本付録のみで、e2e の経路は変えていない)。
素材: `fl-win64 toolchain-emsdk work-m11 work-liftdiff` を展開 (`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`・`TMPDIR=$RUNNER_TEMP`)。emsdk は `[EMSDK]` (`docs/REFERENCES.md`) を使用。

| 測定 | コマンド | 結果 |
|---|---|---|
| e2e (units 既定) | `bash tools/liftdiff/liftdiff_e2e.sh --m11-only` | rc 0 / **187 s** / load 0.33→5.71 / **LIFTDIFF_E2E PASS** / [3b/4] CHECK_INITUNITS PASS / [4/4] 一致 360・不一致 230・実行不能 210 |
| hybrid batch | `python3 liftdiff.py batch targets/m11.json --set sample:800 --shards 12 --nobuild --state work/m11/boot_state_hybrid.json` | rc 0 / **234 s** / 一致 **353**・不一致 **257**・実行不能 **190** |

- LD-25 の記録 (hybrid 352 / 258 / 190) とは 1 件ずれる。同じ hybrid state でも揺れが出る関数があるため、本付録は今回の実測値を採る。

## 2. precondition (受入条件: TLS index)

`ldlib/boot.py::precondition` の実測 (e2e ログ):

| state | table_ptr | init_count | tls_set | ok |
|---|---|---|---|---|
| units (`boot_state.json`) | 0 | 0 | 0 | False (InitUnits 空振り 11/11) |
| hybrid (`boot_state_hybrid.json`) | 0x1376 8b0 | 246 | 1 | True |

- hybrid の heap 内 TLS 配列の非ゼロ数は 1 (precondition の想定どおり)。
- 残件: 「InitUnits 以外が使う TLS slot が未充足のままか」は未確認。非ゼロ 1 は main thread の slot 1 本のみで、どの unit が他の slot を読むかは機械語で未追跡 (§5)。

## 3. 判定遷移 (units → hybrid・sample:800)

`tests/ld42_transition.py work/m11/batch_sample_800.jsonl work/m11/batch_sample_800_hybrid.jsonl --tsv work/m11/ld42_transitions.tsv` (関数単位の突合。TSV は gitignore の `work/`):

| 遷移 | 件数 |
|---|---|
| match → mismatch | 25 |
| unexec → mismatch | 19 |
| mismatch → match | 14 |
| unexec → match | 5 |
| mismatch → unexec | 3 |
| match → unexec | 1 |
| **計 (変化した関数)** | **67 / 800** |

LD-25 の遷移表 (66 件) と比べ、件数は 1 件増えた (`mismatch→match` 13→14)。揺れの範囲内。

## 4. 既定 batch の判断

- **決定: 既定は units のまま据え置く (保留)**。
- 理由: hybrid にすると 67 関数の判定が変わり、`liftdiff_e2e.sh` [4/4] の基準値 (360/230/210) を更新することになる。遷移 67 件のうち、どちらが正しいか (hybrid 側の mismatch が欠陥か、units 側の match が空振り由来か) を関数ごとに示していない。根拠を示さずに基準を動かさない。
- 一方、units の InitUnits 空振りは `check_initunits.py` で既に確定しており (LD-25)、units の 360 一致は「InitUnits が呼ばれない状態での一致」である。基準を動かす判断は、67 件の根拠が揃った後に行う (§5 の子 issue)。
- DECISIONS.md に D13 として記録する。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 遷移 67 件それぞれの native/wasm 差分根拠 (受入条件 1) | 既定 batch の判断材料が不足 | #1464 |
| 既定 batch を hybrid にするか (受入条件 2) | 基準値の更新を伴う。根拠待ち | #1464 |
| InitUnits 以外が使う TLS slot の充足確認 (受入条件 3 の残り) | hybrid の TLS が 1 本のみ。他 unit の前提が未充足の可能性 | #1464 |
