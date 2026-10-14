# #1324 (LD-45): tracker-no-deref 3 関数の記号実行の修正・5c44b0 の門の確定 — 部分達成

**判定: 受入条件 1・2 は達成、受入条件 3 は部分 (分類 1 組に `raw-after` が増えた)**。`Refs #1324`。

既知類型との関係: 該当なし (DEFECTS.md の類型ではなく ldfix の記号実行の取りこぼし。#1134 REPORT_1134.md §2 の機構を前提にした)。

## 1. 受入条件別

| 受入条件 | 結果 |
|---|---|
| 75a180・db6480・dc27c0 の `f3c_track` が機械語の deref を記録する | **達成**。`trk_probe_1134.py` の deref が 0 → 1 / 1 / 2 件 (§3) |
| 5c44b0 (none) の門 (c) / 置換空振りを `rep_idx` で確定 | **達成**。`rep_idx=[21,45,88]` の置換は `f3c_use_not_entry` で見送り (§4) |
| 修正後も `use_residual_509.py` の既存の分類を壊さない | **部分**。ldfix 出力 IR は修正前後で完全一致 (§5)。分類は tracker-no-deref 3 組だけが移動し、うち db6480 arg4 に `raw-after` が新規に付く (§5.2) |

## 2. 修正 (`ldfix/ldfix.py`)

- `_f3c_bump_slots` (新設): 引数 reg の値を frame slot へ 64bit で 1 回だけ写し、以後ループ内で `add/sub [slot], imm` だけで前進させる slot を求める。値は `argN+可変` なので新タグ `('argv', n)` にする。
- `f3c_track`: bump slot を `('argv', n)` として各ブロックの初期状態に入れる。
- `_f3c_note_uses`: `argv` の値を zero-disp load の base とした場合も `deref` として記録する。
- `argv` は `lsf` / `ptr` / `raw` の判定には使わない (`_f3c_step` の `('arg', n)` 判定は不変)。書き換えの根拠になる `lsf`・`ptr` を変えないための分離。

## 3. 受入条件 1: deref 記録 (実測・`python3 ldfix/trk_probe_1134.py`)

| 関数 | 修正前 deref | 修正後 deref | 機械語の位置 |
|---|---|---|---|
| 75a180 | `[]` | `75a26b arg4 64bit` | ループ内 `mov rax,[rbp+0x60]; mov rdx,[rax]` |
| db6480 | `[]` | `db657b arg4 32bit` | `mov r8,[rbp+0x30]; mov r8d,[r8]` (2 段目) |
| dc27c0 | `[]` | `dc2866 arg2 32bit`・`dc28d1 arg2 32bit` | ループ内 `mov edx,[rdx]` の 2 本 |
| 5c44b0 | `5c44bf arg2 64bit` | 同じ (不変) | entry 先頭 |

## 4. 受入条件 2: 5c44b0 (none) の確定 (`python3 ldfix/gate_5c44b0_1324.py`)

- arg2 は門 (a)(b)(c)(d) のうち (a)(b)(c) を通る (`deref` が entry 内、`raw` 0、IR に `load ptr %arg2` 直接 0)。
- 置換候補 `rep_idx=[21,45,88]` の先頭 21 行目は `entry_end=20` 以降 (ラベル `dec_label_pc_5c4512:` の後) にあり、`fix_f3c_use` は `rep['f3c_use_not_entry']` で見送る。
- `fix_f3c_use` を直接呼んだ結果: `ret=0 rep={'f3c_use_not_entry': 1} changed=False` (`work/trace5c_b.py`、検証後に削除)。
- REPORT_1134 §3 の「門 (c) か置換空振りか」は、**どちらでもなく entry 外の置換先による見送り**が正しい。
- 修復の方針 (entry 外の使用を支配関係つきで置換する) は #1325 (LD-46) の範囲。

## 5. 受入条件 3: 既存分類との比較

### 5.1 ldfix 出力 IR の一致 (実測)

- 入力: `work/boot_final3.ll` (修復前 IR 相当)、`--pe $PE` = `_temp/extracted/block00031_PE.bin` (fl-win64 展開物)。
- 旧 (HEAD = 8483b900) と新 (本 PR) の `ldfix.py` を同一入力に適用し `cmp` した結果は **IDENTICAL** (40 秒・load 0.2 前後)。
- 両者の `F3c(store-arg)=33` / `f3c_use_replaced=66` / `f3c_use_ptrarg=9` / `f3c_use_not_entry=2` が一致。

### 5.2 分類表 (`python3 ldfix/use_residual_509.py work/boot_final3.ll work/m11_image.bin 'work/boot*.drc.config.json' ldfix/results/audit_509_pre.json`)

| 分類 | 修正前 | 修正後 |
|---|---|---|
| none | 22 | 22 |
| first-deref-not-entry | 15 | 16 |
| ptr-arg | 10 | 10 |
| first-deref-not-entry+ptr-arg | 4 | 4 |
| tracker-no-deref | 3 | 0 |
| first-deref-not-entry+w32 | 2 | 3 |
| first-deref-not-entry+w32+raw-after | 0 | 1 |
| 合計 (関数, 引数) | 56 | 56 |

変化した組 (修正前 → 修正後 / `use_residual_509.py ... all`):
- 75a180 arg4: tracker-no-deref → first-deref-not-entry
- dc27c0 arg2: tracker-no-deref → first-deref-not-entry+w32
- db6480 arg4: tracker-no-deref → first-deref-not-entry+w32+raw-after

**ablation** (`bumps = {}` に置換して argv を無効化した版): 上記 3 組以外の 53 組は修正前と完全一致 (`diff` で差 3 行のみ・3 組の分類だけ)。

### 5.3 未解決 (受入条件 3 の残り)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| db6480 arg4 に `raw-after` が新規に付いた (`fix_f3c_use` は門 (b) で見送るため IR は不変。分類表の既存行は崩れていないが、分類の定義上は組が 1 つ増えた) | 分類の解釈のみ。IR 出力は不変 (§5.1) | #1325 (LD-46) の着手前に PM が分類定義を確認 |
| 3 関数の deref を使って `fix_f3c_use` を通す修復は行っていない (門 (a) で見送り) | 3 関数の修復は未着手 | #1325 (LD-46) |

## 6. 検証範囲

- **検証した**: `trk_probe_1134.py` (記号実行の deref)、`use_residual_509.py` (分類)、`ldfix.py` 出力 IR の旧新一致、`gate_5c44b0_1324.py` (5c44b0 の門)。
- **範囲外**: e2e (`ldfix_509_e2e.sh` の 6/7 wasm 比較・7/7 動的確認)。本修正は IR 出力を変えないため、wasm は変わらない (§5.1 の一致より)。e2e は実施していない。
- **範囲外**: `REPORT_930` の 23/24 と 30/33 の不一致 (#1134 §4 で未調査として残件。本 PR では触らない)。

## 7. 再現

```
cd tools/m11
python3 ldfix/trk_probe_1134.py                                    # §3
python3 ldfix/gate_5c44b0_1324.py                                  # §4
python3 ldfix/use_residual_509.py work/boot_final3.ll work/m11_image.bin 'work/boot*.drc.config.json' ldfix/results/audit_509_pre.json  # §5.2
PYTHONPATH=. python3 ldfix/ldfix.py work/boot_final3.ll out.ll --pe <block00031_PE.bin>  # §5.1 (旧新を cmp)
```

入力: `work/` は `tar --zstd -xf $ARTIFACTS_DIR/work-m11.tar.zst -C ../..` で展開 (tools/m11/work/)。PE は `fl-win64` の `extracted/block00031_PE.bin`。

## 8. 測定 commit と差分

測定 commit: 本 PR の HEAD (修正 commit)。測定対象 (`tools/m11/ldfix/`) の差分:

```
git diff 8483b900 HEAD -- tools/m11/ldfix/ldfix.py
```
