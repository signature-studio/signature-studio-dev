# liftdiff LD-42 (#1248): 既定 batch の boot 状態判断と TLS index 充足 (部分達成)

親: #977 (LD-25) / 関連: `REPORT_APPENDIX_LD25.md`。本付録は #1248 の実測と判断。LD-50 (#1464) で、遷移の差分根拠 (§6)・既定 batch の据え置きの確定 (§4)・TLS の機械語確認 (§7) を追記した。残りは子 issue (§5)。

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

- **決定 (LD-50 / #1464・2026-10-15): 既定は units のまま据え置く (確定)。** hybrid は `--state` で明示したときだけ使う。
- 理由: hybrid にすると 67 関数の判定が変わり、`liftdiff_e2e.sh` [4/4] の基準値 (360/230/210) を更新することになる。遷移 67 件のうち、どちらが正しいか (hybrid 側の mismatch が欠陥か、units 側の match が空振り由来か) を関数ごとに示していない。根拠を示さずに基準を動かさない。
- 一方、units の InitUnits 空振りは `check_initunits.py` で既に確定しており (LD-25)、units の 360 一致は「InitUnits が呼ばれない状態での一致」である。
- 据え置きの理由 (§6・§7・§8 の実測): (a) hybrid では InitUnits (0x4120c0) 自体の native 実行が 11/11 パターンで segv する (`check_initunits.py` の hybrid 行)。`check_initunits.py` は空振りしか見ないため PASS のままになる。hybrid の native 側を正の基準にできない (子 LD-153)。(b) 遷移 68 件のうち 25 件 (units 一致 → hybrid 差分) は全件の主因が `callee_divergence` で、呼び先のどちらが誤りかを関数ごとに決められない (§6)。(c) 同じ入力でも件数が揺れる (§8.1)。基準は再現してから動かす (子 LD-154)。
- hybrid へ切り替える条件は §8.2。
- DECISIONS.md の D13 に記録し、状態を「採用」に更新した。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 遷移 67 件それぞれの native/wasm 差分根拠 (受入条件 1) | 完了 (LD-50 で 68 件を §6 に表で記録) | — |
| 既定 batch を hybrid にするか (受入条件 2) | 完了 (units のまま据え置きを確定。§4・D13)。切替は §8.2 の条件 | — |
| hybrid の InitUnits (0x4120c0) の native segv 11/11 (§4 (a)・§6 の B) | hybrid の native 基準が成立しない。遷移 25 件 (§6 の F) の帰属が決まらない | #3349 (LD-153) |
| InitUnits 以外が使う TLS slot の充足確認 (受入条件 3 の残り・§7) | hybrid の TLS は flag=1 の経路で読まれ、precondition の判定 (gs 経路) と一致しない | #3349 (LD-153) |
| 負荷による遷移件数の揺れ (67 → 68、hybrid 不一致 257 → 269・§8.1) | 基準値の再現性。切替 (§8.2 の 3) の前提 | #3350 (LD-154) |

## 6. 遷移 68 件の差分根拠 (LD-50 / #1464・受入条件 1)

測定 commit: `f9df8bf4` (origin/main)。units は `liftdiff_e2e.sh` の [4/4] (`work/m11/batch_sample_800.jsonl`)、hybrid は次の batch (`--state` は [3b/4] が作る `work/m11/boot_state_hybrid.json`)。

```
python3 liftdiff.py batch targets/m11.json --set sample:800 --shards 12 --nobuild --state work/m11/boot_state_hybrid.json --out work/m11/batch_sample_800_hybrid.jsonl
python3 tests/ld42_basis.py work/m11/batch_sample_800.jsonl work/m11/batch_sample_800_hybrid.jsonl --md work/m11/ld42_basis.md
```

- 件数: unexec→mismatch 25・match→mismatch 25・mismatch→match 13・unexec→match 4・match→unexec 1 = **68**。§3 (2b2faf52) の 67 とは 1 件ずれる (§8.1)。
- 根拠の区分 (表の「根拠」列。`ld42_basis.py` の規則で分類し、件数は表から数えた):
  - **A. units で実行不能 → hybrid で実行可能: 29 件**。units の実行不能理由は native_fault 17・native_null_deref 7・hang 5。hybrid の判定は不一致 25 件 (主因 wasm_trap 18・callee_divergence 5・icall_drop 2) と一致 4 件。
  - **B. hybrid で実行不能: 1 件** (行 13 = InitUnits 0x4120c0)。units の一致 11/11 は InitUnits の空振り (§4)。hybrid は native segv 11/11 (`native_null_deref_all_patterns`)。
  - **C. hybrid で一致 (差分 0): 13 件**。units の主因は callee_divergence 9・wasm_trap 4。
  - **F. units 一致 → hybrid 不一致: 25 件**。全件の主因が callee_divergence。pattern 内訳は diff 11 が 20 件、equal 1 + diff 10 が 5 件。
- 「pattern 内訳」は 11 pattern の outcome 件数。`equal` 一致・`diff` 差分・`native_fault` native だけ fault・`both_fault` 両側 fault・`wasm_trap` wasm の trap・`hang` 上限超過・`wasm_timeout_native_long` wasm のみ上限超過。
- 注記: 行 10 (0x12f9ec0) は pattern 8 件が `native_fault` のままで一致判定になっている (`equal` 3)。

| # | va | 名前 | units → hybrid | units 主因 | hybrid 主因 | units の pattern 内訳 | hybrid の pattern 内訳 | 根拠 |
|---|---|---|---|---|---|---|---|---|
| 1 | 0x10293b0 | function_10293b0 | unexec (native_fault_all_patterns) → mismatch | - | wasm_trap | both_fault 19 | both_fault 6, wasm_trap 5 | units は実行不能 (native_fault_all_patterns)。hybrid で実行可能になった |
| 2 | 0x10348b0 | function_10348b0 | unexec (hang) → mismatch | - | wasm_trap | native_fault 5, hang 6 | both_fault 6, wasm_trap 5 | units は実行不能 (hang)。hybrid で実行可能になった |
| 3 | 0x1065eb0 | function_1065eb0 | match → mismatch | - | callee_divergence | equal 11 | diff 11 | hybrid: 両側実行の差分 (主因 callee_divergence) |
| 4 | 0x11562a0 | function_11562a0 | mismatch → match | callee_divergence | - | diff 11 | equal 11 | hybrid で一致 (差分 0) |
| 5 | 0x1252b30 | function_1252b30 | unexec (native_null_deref_all_patterns) → mismatch | - | wasm_trap | both_fault 11 | both_fault 7, wasm_trap 4 | units は実行不能 (native_null_deref_all_patterns)。hybrid で実行可能になった |
| 6 | 0x12b5340 | function_12b5340 | unexec (native_null_deref_all_patterns) → mismatch | - | wasm_trap | both_fault 18 | wasm_trap 11 | units は実行不能 (native_null_deref_all_patterns)。hybrid で実行可能になった |
| 7 | 0x12b5450 | function_12b5450 | unexec (native_null_deref_all_patterns) → mismatch | - | wasm_trap | both_fault 18 | wasm_trap 11 | units は実行不能 (native_null_deref_all_patterns)。hybrid で実行可能になった |
| 8 | 0x12cbeb0 | function_12cbeb0 | mismatch → match | callee_divergence | - | diff 11 | equal 11 | hybrid で一致 (差分 0) |
| 9 | 0x12e3880 | function_12e3880 | unexec (native_fault_all_patterns) → mismatch | - | wasm_trap | both_fault 11 | both_fault 10, wasm_trap 1 | units は実行不能 (native_fault_all_patterns)。hybrid で実行可能になった |
| 10 | 0x12f9ec0 | function_12f9ec0 | unexec (native_fault_all_patterns) → match | - | - | native_fault 19 | equal 3, native_fault 8 | units は実行不能 (native_fault_all_patterns)。hybrid で実行可能になった |
| 11 | 0x136b2a0 | function_136b2a0 | match → mismatch | - | callee_divergence | equal 11 | diff 11 | hybrid: 両側実行の差分 (主因 callee_divergence) |
| 12 | 0x13709d0 | function_13709d0 | unexec (native_fault_all_patterns) → mismatch | - | callee_divergence | native_fault 11 | diff 3, native_fault 8 | units は実行不能 (native_fault_all_patterns)。hybrid で実行可能になった |
| 13 | 0x4120c0 | function_4120c0 | match → unexec (native_null_deref_all_patterns) | - | - | equal 11 | native_fault 11 | hybrid は実行不能 (native_null_deref_all_patterns) |
| 14 | 0x496c80 | function_496c80 | unexec (native_fault_all_patterns) → mismatch | - | wasm_trap | both_fault 11 | both_fault 10, wasm_trap 1 | units は実行不能 (native_fault_all_patterns)。hybrid で実行可能になった |
| 15 | 0x4fe190 | function_4fe190 | unexec (native_null_deref_all_patterns) → mismatch | - | callee_divergence | both_fault 18 | diff 11 | units は実行不能 (native_null_deref_all_patterns)。hybrid で実行可能になった |
| 16 | 0x505c40 | function_505c40 | match → mismatch | - | callee_divergence | equal 11 | diff 11 | hybrid: 両側実行の差分 (主因 callee_divergence) |
| 17 | 0x534860 | function_534860 | unexec (native_fault_all_patterns) → mismatch | - | wasm_trap | native_fault 1, both_fault 15 | native_fault 1, both_fault 9, wasm_trap 1 | units は実行不能 (native_fault_all_patterns)。hybrid で実行可能になった |
| 18 | 0x545d10 | function_545d10 | mismatch → match | callee_divergence | - | diff 11 | equal 11 | hybrid で一致 (差分 0) |
| 19 | 0x5821f0 | function_5821f0 | match → mismatch | - | callee_divergence | equal 11 | diff 11 | hybrid: 両側実行の差分 (主因 callee_divergence) |
| 20 | 0x5920d0 | function_5920d0 | match → mismatch | - | callee_divergence | equal 11 | diff 11 | hybrid: 両側実行の差分 (主因 callee_divergence) |
| 21 | 0x5aa390 | function_5aa390 | match → mismatch | - | callee_divergence | equal 11 | diff 11 | hybrid: 両側実行の差分 (主因 callee_divergence) |
| 22 | 0x5c2550 | function_5c2550 | unexec (hang) → mismatch | - | callee_divergence | hang 11 | diff 3, native_fault 8 | units は実行不能 (hang)。hybrid で実行可能になった |
| 23 | 0x5d25a0 | function_5d25a0 | match → mismatch | - | callee_divergence | equal 11 | diff 11 | hybrid: 両側実行の差分 (主因 callee_divergence) |
| 24 | 0x5d88e0 | function_5d88e0 | match → mismatch | - | callee_divergence | equal 11 | equal 1, diff 10 | hybrid: 両側実行の差分 (主因 callee_divergence) |
| 25 | 0x620cd0 | function_620cd0 | unexec (hang) → mismatch | - | wasm_trap | hang 11 | wasm_trap 3, wasm_timeout_native_long 8 | units は実行不能 (hang)。hybrid で実行可能になった |
| 26 | 0x623840 | function_623840 | unexec (hang) → match | - | - | hang 11 | equal 11 | units は実行不能 (hang)。hybrid で実行可能になった |
| 27 | 0x63aa90 | function_63aa90 | match → mismatch | - | callee_divergence | equal 11 | equal 1, diff 10 | hybrid: 両側実行の差分 (主因 callee_divergence) |
| 28 | 0x646130 | function_646130 | unexec (native_fault_all_patterns) → mismatch | - | wasm_trap | native_fault 1, both_fault 15 | native_fault 1, both_fault 9, wasm_trap 1 | units は実行不能 (native_fault_all_patterns)。hybrid で実行可能になった |
| 29 | 0x64fa70 | function_64fa70 | unexec (native_fault_all_patterns) → mismatch | - | wasm_trap | both_fault 19 | both_fault 10, wasm_trap 1 | units は実行不能 (native_fault_all_patterns)。hybrid で実行可能になった |
| 30 | 0x64fc70 | function_64fc70 | unexec (native_fault_all_patterns) → mismatch | - | wasm_trap | both_fault 16 | both_fault 9, wasm_trap 2 | units は実行不能 (native_fault_all_patterns)。hybrid で実行可能になった |
| 31 | 0x65c9f0 | function_65c9f0 | mismatch → match | callee_divergence | - | diff 11 | equal 11 | hybrid で一致 (差分 0) |
| 32 | 0x664190 | function_664190 | mismatch → match | wasm_trap | - | wasm_trap 11 | equal 11 | hybrid で一致 (差分 0) |
| 33 | 0x66d050 | function_66d050 | unexec (native_fault_all_patterns) → match | - | - | both_fault 11 | equal 11 | units は実行不能 (native_fault_all_patterns)。hybrid で実行可能になった |
| 34 | 0x66dfc0 | function_66dfc0 | match → mismatch | - | callee_divergence | equal 11 | diff 11 | hybrid: 両側実行の差分 (主因 callee_divergence) |
| 35 | 0x66e9a0 | function_66e9a0 | mismatch → match | wasm_trap | - | wasm_trap 11 | equal 11 | hybrid で一致 (差分 0) |
| 36 | 0x672600 | function_672600 | unexec (native_fault_all_patterns) → mismatch | - | icall_drop | native_fault 11 | diff 11 | units は実行不能 (native_fault_all_patterns)。hybrid で実行可能になった |
| 37 | 0x6a3040 | function_6a3040 | unexec (hang) → mismatch | - | wasm_trap | native_fault 10, hang 1 | diff 10, wasm_trap 1 | units は実行不能 (hang)。hybrid で実行可能になった |
| 38 | 0x6a3a00 | function_6a3a00 | unexec (native_fault_all_patterns) → mismatch | - | icall_drop | native_fault 11 | diff 4, native_fault 7 | units は実行不能 (native_fault_all_patterns)。hybrid で実行可能になった |
| 39 | 0x6db440 | function_6db440 | match → mismatch | - | callee_divergence | equal 11 | equal 1, diff 10 | hybrid: 両側実行の差分 (主因 callee_divergence) |
| 40 | 0x776da0 | function_776da0 | unexec (native_fault_all_patterns) → mismatch | - | wasm_trap | native_fault 1, both_fault 10 | native_fault 1, both_fault 7, wasm_trap 3 | units は実行不能 (native_fault_all_patterns)。hybrid で実行可能になった |
| 41 | 0x7948c0 | function_7948c0 | unexec (native_fault_all_patterns) → mismatch | - | wasm_trap | both_fault 16 | both_fault 10, wasm_trap 1 | units は実行不能 (native_fault_all_patterns)。hybrid で実行可能になった |
| 42 | 0x7a7310 | function_7a7310 | match → mismatch | - | callee_divergence | equal 11 | diff 11 | hybrid: 両側実行の差分 (主因 callee_divergence) |
| 43 | 0x7a7360 | function_7a7360 | mismatch → match | callee_divergence | - | diff 11 | equal 11 | hybrid で一致 (差分 0) |
| 44 | 0x81bfd0 | function_81bfd0 | unexec (native_null_deref_all_patterns) → mismatch | - | wasm_trap | both_fault 11 | wasm_trap 11 | units は実行不能 (native_null_deref_all_patterns)。hybrid で実行可能になった |
| 45 | 0x86d240 | function_86d240 | mismatch → match | wasm_trap | - | wasm_trap 11 | equal 11 | hybrid で一致 (差分 0) |
| 46 | 0x8e8db0 | function_8e8db0 | mismatch → match | callee_divergence | - | equal 1, diff 10 | equal 11 | hybrid で一致 (差分 0) |
| 47 | 0x8f7040 | function_8f7040 | match → mismatch | - | callee_divergence | equal 11 | diff 11 | hybrid: 両側実行の差分 (主因 callee_divergence) |
| 48 | 0x8f7070 | function_8f7070 | mismatch → match | callee_divergence | - | diff 11 | equal 11 | hybrid で一致 (差分 0) |
| 49 | 0x91f320 | function_91f320 | unexec (native_fault_all_patterns) → mismatch | - | wasm_trap | native_fault 1, both_fault 15 | native_fault 1, both_fault 9, wasm_trap 1 | units は実行不能 (native_fault_all_patterns)。hybrid で実行可能になった |
| 50 | 0x9a80f0 | function_9a80f0 | match → mismatch | - | callee_divergence | equal 11 | diff 11 | hybrid: 両側実行の差分 (主因 callee_divergence) |
| 51 | 0x9d9520 | function_9d9520 | match → mismatch | - | callee_divergence | equal 11 | diff 11 | hybrid: 両側実行の差分 (主因 callee_divergence) |
| 52 | 0x9dac60 | function_9dac60 | match → mismatch | - | callee_divergence | equal 11 | diff 11 | hybrid: 両側実行の差分 (主因 callee_divergence) |
| 53 | 0xa31210 | function_a31210 | mismatch → match | callee_divergence | - | diff 11 | equal 11 | hybrid で一致 (差分 0) |
| 54 | 0xb39ca0 | function_b39ca0 | mismatch → match | wasm_trap | - | wasm_trap 11 | equal 11 | hybrid で一致 (差分 0) |
| 55 | 0xb3e120 | function_b3e120 | unexec (native_fault_all_patterns) → mismatch | - | wasm_trap | native_fault 1, both_fault 15 | native_fault 1, both_fault 9, wasm_trap 1 | units は実行不能 (native_fault_all_patterns)。hybrid で実行可能になった |
| 56 | 0xc1c7c0 | function_c1c7c0 | match → mismatch | - | callee_divergence | equal 11 | diff 11 | hybrid: 両側実行の差分 (主因 callee_divergence) |
| 57 | 0xc21a00 | function_c21a00 | unexec (native_fault_all_patterns) → mismatch | - | callee_divergence | both_fault 11 | equal 1, diff 10 | units は実行不能 (native_fault_all_patterns)。hybrid で実行可能になった |
| 58 | 0xc63cf0 | function_c63cf0 | match → mismatch | - | callee_divergence | equal 11 | diff 11 | hybrid: 両側実行の差分 (主因 callee_divergence) |
| 59 | 0xc708d0 | function_c708d0 | match → mismatch | - | callee_divergence | equal 11 | equal 1, diff 10 | hybrid: 両側実行の差分 (主因 callee_divergence) |
| 60 | 0xc97ac0 | function_c97ac0 | unexec (native_null_deref_all_patterns) → match | - | - | both_fault 11 | equal 11 | units は実行不能 (native_null_deref_all_patterns)。hybrid で実行可能になった |
| 61 | 0xca1230 | function_ca1230 | match → mismatch | - | callee_divergence | equal 11 | equal 1, diff 10 | hybrid: 両側実行の差分 (主因 callee_divergence) |
| 62 | 0xceeb70 | function_ceeb70 | unexec (native_null_deref_all_patterns) → mismatch | - | callee_divergence | native_fault 14 | diff 11 | units は実行不能 (native_null_deref_all_patterns)。hybrid で実行可能になった |
| 63 | 0xcf06a0 | function_cf06a0 | match → mismatch | - | callee_divergence | equal 11 | diff 11 | hybrid: 両側実行の差分 (主因 callee_divergence) |
| 64 | 0xd33480 | function_d33480 | mismatch → match | callee_divergence | - | diff 11 | equal 11 | hybrid で一致 (差分 0) |
| 65 | 0xdcff80 | function_dcff80 | match → mismatch | - | callee_divergence | equal 11 | diff 11 | hybrid: 両側実行の差分 (主因 callee_divergence) |
| 66 | 0xebb1e0 | function_ebb1e0 | match → mismatch | - | callee_divergence | equal 11 | diff 11 | hybrid: 両側実行の差分 (主因 callee_divergence) |
| 67 | 0xecbe30 | function_ecbe30 | match → mismatch | - | callee_divergence | equal 11 | diff 11 | hybrid: 両側実行の差分 (主因 callee_divergence) |
| 68 | 0xfd3d30 | function_fd3d30 | match → mismatch | - | callee_divergence | equal 11 | diff 11 | hybrid: 両側実行の差分 (主因 callee_divergence) |

## 7. TLS の機械語確認 (LD-50・受入条件 3 の部分)

入力: `$FL_WIN64_DIR/extracted/block00031_PE.bin` (ImageBase 0x400000・`.text` 16,397,824 bytes)。

- `gs:[0x58]` (TEB の TLS 配列ポインタ) の読み出し (`65 48|4c 8b modrm 25 58 00 00 00`) を `.text` 全体で検索: **1 箇所** (VA 0x41d14b)。
- その 1 箇所を含む関数 (VA 0x41d110) への直接 call (`e8 rel32`) を `.text` 全体で検索: **268 箇所**。

取得関数 0x41d110 の分岐 (逆アセンブルで確認):
- `cmp byte ptr [flag], 0` (flag = RVA 0x11ec2d8)。flag == 0 なら gs 経路 (`mov rax, gs:[0x58]`、`mov ecx, [tls_index]` (RVA 0xfa9388)、`mov rax, [rax + rcx*8]`)。
- flag != 0 なら、間接 jmp の import thunk (VA 0x41cf60 ほか) を呼ぶ経路。返りが 0 なら 0x41d000 を経て再試行し、なお 0 なら global `[RVA 0x11cf187]` を使う。

状態別の値 (`ldlib/boot.py` の `_img_u64` と heap 読み出し):

| 項目 | units (`work/m11/boot_state.json`) | hybrid (`work/m11/boot_state_hybrid.json`) |
|---|---|---|
| flag (RVA 0x11ec2d8) | 0 → gs 経路 | 1 → import thunk 経路 |
| tls_index (RVA 0xfa9388) | 未取得 (image run に無い) | 1 |
| heap TLS 配列 (0x1000 + i×8) の非ゼロ slot | 0 本 | 1 本 (slot 1 = 0x10480000) |

確定していること:
- hybrid は flag=1 のため、取得関数は heap の TLS 配列を読まない。`boot.py::precondition` の `tls_set > 0` は gs 経路の充足を見ており、hybrid の実経路の充足を見ていない。よって hybrid の `precondition.ok = True` は TLS 充足の証拠にならない。
- InitUnits (0x4120c0) は `gs:[0x58]` を読まない (PE 全体の読み出しは 0x41d14b の 1 箇所のみ)。InitUnits の呼び先が取得関数を通って TLS を読むかは、未確認 (#3349)。

未確認 (子 issue #3349 へ移した):
- import thunk が wasm 側で何を返すか (stub の値)。
- 268 の call 元が取得する slot の充足。
- units で gs 経路が 0 を返すことが、どの差分に効くか。
- hybrid の InitUnits native segv の原因 (fault の命令位置は rip と register dump からまだ特定していない)。

## 8. 再現性と切替条件 (LD-50)

### 8.1 件数の揺れ

| 測定 | units (一致 / 不一致 / 実行不能) | hybrid (一致 / 不一致 / 実行不能) | 遷移 | 終了時 1 分 load |
|---|---|---|---|---|
| 2b2faf52 (§1・§3) | 360 / 230 / 210 | 353 / 257 / 190 | 67 | units 5.71・hybrid 未記録 |
| f9df8bf4 (LD-50) | 361 / 232 / 207 | 352 / 269 / 179 | 68 | units 5.90・hybrid 8.25 |
| 2d149de9 (LD-50 の HEAD・e2e 再実行。hybrid は未再実行) | 360 / 233 / 207 | — | — | units 5.61 |

- units は 3 回の測定で 一致 360–361・不一致 230–233・実行不能 207–210 (1–3 件の揺れ)。hybrid は不一致 +12・実行不能 −11 動いた。遷移は 67 から 68 に変わった。
- 同じ条件の再測定ではない (f9df8bf4 の hybrid batch は終了時 load 8.25 の環境で走った)。pattern の outcome 件数は units の hang 271・hybrid の hang 264。hang / timeout 判定の負荷依存が揺れの候補だが、未検証。子 issue #3350 (LD-154)。
- 1 回の測定の件数を基準値にしない。

### 8.2 hybrid へ切り替える条件

1. hybrid の InitUnits (0x4120c0) が 11/11 パターンで native ok (#3349)。
2. flag=1 の経路が充足され、precondition がその経路の充足を判定する (#3349)。
3. 同じ入力を 2 回実行して件数が一致する (#3350)。
4. 上の 1–3 を満たしたら、§6 の表を再生成し、F の 25 件の帰属 (主因 callee_divergence) を関数ごとに決めてから、[4/4] の基準値を更新する。

### 8.3 検証 (LD-50)

- 測定 commit: `2d149de9` (コードを変えた最後の commit)。e2e (`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/liftdiff/liftdiff_e2e.sh --m11-only`): rc 0 / 185 s / 終了時 load 5.61 / `CHECK_INITUNITS PASS` (units の空振り 11/11・hybrid の native_fault 11・空振り 0) / 一致 360・不一致 233・実行不能 207 / `LIFTDIFF_E2E PASS`。
- 同じ e2e を f9df8bf4 で実行: rc 0 / 188 s / 終了時 load 5.90 / `CHECK_INITUNITS PASS` / 361・232・207 / `LIFTDIFF_E2E PASS`。
- 測定 commit 以降のコード差分 (`git diff 2d149de9 HEAD -- tools/liftdiff/*.py tools/liftdiff/ldlib tools/liftdiff/tests tools/liftdiff/liftdiff_e2e.sh tools/liftdiff/rt`) は 0 行。以後の commit は本付録の文書のみ。
- 本付録の §6 の表は `tests/ld42_basis.py` で再生成できる (1 コマンド。§6 冒頭)。
