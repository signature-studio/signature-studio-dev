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
- `_f3c_note_uses`: `argv` の値を zero-disp load の base とした場合も `deref` として記録する。タプルは `('deref', addr, n, 幅, 出所)` (出所 = `'arg'` | `'argv'`)。
- `argv` は `lsf` / `ptr` / `raw` の判定に使わない (`_f3c_step` の `('arg', n)` 判定は不変)。
- **`fix_f3c_use` の門 (a) は出所 `'arg'` の deref だけを数える** (レビュー指摘 1 への修正)。`argv` 由来の deref で IR を書き換えない。
- 分類 (`use_residual_509.py`・`trk_probe_1134.py`・`gate_5c44b0_1324.py`) は出所を問わず全 deref を数える (`u[4]` は見ない)。
- 注: 修正前 (c5e6944c) の §3・§4・§5 の数値は、この出所フィルタを入れる前のコードでの測定。修正後の再測定は §6 参照。

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

### 5.3 db6480 arg4 の `raw-after` の由来 (指摘 2 への回答)

- 分類の定義: `raw-after` = 「最初の deref より後に、同じ argN の生の使用がある」。
- 修正前 (c5e6944c 以前) は db6480 arg4 の deref が 0 件 (`tracker-no-deref`) で、`raw-after` は判定されない。
- `argv` 導入後は db657b (`mov r8d,[r8]`、2 段目) の 32bit deref が唯一の deref になり、その後に arg4 の生の使用が残るため `raw-after` が付く。
- 2 段目の deref は `argv` (bump slot) 由来。根拠は ablation (§5.2): `bumps = {}` で 3 組以外が完全一致し、db6480 だけが変わるため。ただし `work/` が無く、db657b の出所タグを直接は再確認していない。
- したがって `raw-after` は argv 由来の deref を起点に付いたものである。

### 5.4 指摘 1 の修正 (出所フィルタ) が IR を変えない根拠 (コード上)

- `_f3c_step` で `argv` を参照するのは `st` の値の伝播だけ。`lsf` は `('ld', ...)`、`ptr` は `('arg', ...)` のみを採るので、`argv` は `lsf`・`ptr` に入らない。
- `_f3c_note_uses` の raw 記録は `('arg', ...)` のみ。`'arg'` の値の集合と順序は、`argv` が入る前と同じ。
- `fix_f3c_use` の門 (a)〜(d) の入力は、出所 `'arg'` の deref と raw だけになった。よって `fix_f3c_use` の出力 IR は、argv 導入前 (8483b900) と同一になるはず。
- 修正 commit 後の旧新 `cmp` は未実施 (§6)。上記はコードの読解による推論である。

### 5.5 未解決 (受入条件 3 の残り)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| db6480 arg4 の `raw-after` (argv 由来の新しい deref が起点) を分類定義上どう扱うか | 分類の解釈のみ。IR 出力は不変 (§5.4)。受入条件 3 は未チェックのまま | PM 判断 (#1325 (LD-46) の着手前) |
| 3 関数の deref を使って `fix_f3c_use` を通す修復は行っていない (門 (a) で見送り) | 3 関数の修復は未着手 | #1325 (LD-46) |

## 6. 検証範囲

- **検証した (修正前コードでの実測・§3〜§5)**: `trk_probe_1134.py`、`use_residual_509.py`、`ldfix.py` 出力 IR の旧新一致、`gate_5c44b0_1324.py`。
- **修正後 (出所フィルタ入り) の再測定は未実施**: この run では `work/boot_final3.ll`・`work/m11_image.bin` が無く (`$ARTIFACTS_DIR` に `work-m11.tar.zst` なし。`fl-win64` のみ)、上記スクリプトを実行できなかった。`py_compile` と import は通過。
- **修正後 IR が変わらないことの根拠 (推論・未測定)**: §3 の 3 関数の deref は 75a180 (loop 内 = entry 外)、db6480 (32bit)、dc27c0 (32bit) で、修正前も門 (a) で落ちていた。出所 `'arg'` の deref だけに絞ると、この 3 組で門の判定は変わらない。ただし同一 n に arg 由来と argv 由来の deref が混在する関数では、門の `first` と 64bit 判定が変わり得る。混在の有無は未確認。
- **範囲外**: e2e (`ldfix_509_e2e.sh` の 6/7 wasm 比較・7/7 動的確認)。e2e は未実施。wasm が変わらないとは、修正後の旧新 `cmp` (work-m11 素材が要る) が取れるまで言えない。
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
