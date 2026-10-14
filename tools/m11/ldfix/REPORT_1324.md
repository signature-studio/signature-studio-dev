# #1324 (LD-45): tracker-no-deref 3 関数の記号実行の修正・5c44b0 の門の確定

**判定: 受入条件 1・2・3 達成 (head `ea1a8c80` で実測)。e2e は未実施 (理由は §6)。`Refs #1324`。**

既知類型との関係: 該当なし (DEFECTS.md の類型ではなく ldfix の記号実行の取りこぼし。#1134 REPORT_1134.md §2 の機構を前提にした)。

## 1. 受入条件別

| 受入条件 | 結果 |
|---|---|
| 75a180・db6480・dc27c0 の `f3c_track` が機械語の deref を記録する | **達成**。`trk_probe_1134.py` の deref が 0 → 1 / 1 / 2 件 (§3、head で再測定・一致) |
| 5c44b0 (none) の門 (c) / 置換空振りを `rep_idx` で確定 | **達成**。`rep_idx=[21,45,88]` の置換は `f3c_use_not_entry` で見送り (§4、head で再測定・一致) |
| 修正後も `use_residual_509.py` の既存の分類を壊さない | **達成**。ldfix 出力 IR は 8483b900 と head で完全一致 (§5.1)。分類は tracker-no-deref 3 組だけが移動し、残り 53 組は ablation と完全一致 (§5.2)。移動先 db6480 arg4 の `raw-after` は argv 由来の deref が起点と確認 (§5.3) |

## 2. 修正 (`ldfix/ldfix.py`)

- `_f3c_bump_slots` (新設): 引数 reg の値を frame slot へ 64bit で 1 回だけ写し、以後ループ内で `add/sub [slot], imm` だけで前進させる slot を求める。値は `argN+可変` なので新タグ `('argv', n)` にする。
- `f3c_track`: bump slot を `('argv', n)` として各ブロックの初期状態に入れる。
- `_f3c_note_uses`: `argv` の値を zero-disp load の base とした場合も `deref` として記録する。タプルは `('deref', addr, n, 幅, 出所)` (出所 = `'arg'` | `'argv'`)。
- `argv` は `lsf` / `ptr` / `raw` の判定に使わない (`_f3c_step` の `('arg', n)` 判定は不変)。
- **`fix_f3c_use` の門 (a) は出所 `'arg'` の deref だけを数える** (レビュー指摘 1 への修正 `1af9cad2`)。`argv` 由来の deref で IR を書き換えない。
- 分類 (`use_residual_509.py`・`trk_probe_1134.py`・`gate_5c44b0_1324.py`) は出所を問わず全 deref を数える。

## 3. 受入条件 1: deref 記録 (`python3 ldfix/trk_probe_1134.py`)

測定 commit `ea1a8c80` (head)。実行時間 0.9 秒。出力は表の値と一致 (判定の PASS/FAIL 出力は無い)。

| 関数 | 修正前 deref | 修正後 deref (head 実測) | 出所 | 機械語の位置 |
|---|---|---|---|---|
| 75a180 | `[]` | `75a26b arg4 64bit` | argv | ループ内 `mov rax,[rbp+0x60]; mov rdx,[rax]` |
| db6480 | `[]` | `db657b arg4 32bit` | argv | `mov r8,[rbp+0x30]; mov r8d,[r8]` (2 段目) |
| dc27c0 | `[]` | `dc2866 arg2 32bit`・`dc28d1 arg2 32bit` | argv | ループ内 `mov edx,[rdx]` の 2 本 |
| 5c44b0 | `5c44bf arg2 64bit` | 同じ (不変) | arg | entry 先頭 |

## 4. 受入条件 2: 5c44b0 (none) の確定 (`python3 ldfix/gate_5c44b0_1324.py`)

測定 commit `ea1a8c80` (head)。実行時間 0.5 秒。

- arg2 は門 (a)(b)(c) を通る (`deref` が entry 内・64bit・出所 `'arg'`、`raw` 0、IR に `load ptr %arg2` 直接 0)。
- 置換候補 `rep_idx=[21,45,88]` の先頭 21 行目は `entry_end=20` 以降 (ラベル `dec_label_pc_5c4512:` の後) にあり、`fix_f3c_use` は `rep['f3c_use_not_entry']` で見送る。
- REPORT の初版 (c5e6944c) にあった `fix_f3c_use` の直接呼び出し (`ret=0 rep={'f3c_use_not_entry': 1} changed=False`) は、head では再実行していない (作業スクリプト `trace5c_b.py` は repo に無い)。門の判定は gate スクリプトの出力で head 一致を確認した。
- 修復の方針 (entry 外の使用を支配関係つきで置換する) は #1325 (LD-46) の範囲。

## 5. 受入条件 3: 既存分類との比較

### 5.1 ldfix 出力 IR の一致 (実測・head)

- 入力: `work/boot_final3.ll` (修復前 IR 相当)、`--pe work/extracted/block00031_PE.bin` (fl-win64 の `extracted/block00031_PE.bin` を展開)。
- 旧 = 8483b900 の `tools/m11` を `git archive` で別ディレクトリに展開して実行 (33.7 秒・rc=0)。新 = head `ea1a8c80` (39.0 秒・rc=0)。
- `cmp old.ll head.ll` → **IDENTICAL** (21,772,659 bytes)。
- 両者の `F1=0 / F1v=0 / F2=0 / F3a=2 / F3b=0 / F3c(store-arg)=33 (errors=0)` が一致。

### 5.2 分類表 (`python3 ldfix/use_residual_509.py work/boot_final3.ll work/m11_image.bin 'work/boot*.drc.config.json' ldfix/results/audit_509_pre.json`)

head `ea1a8c80` で実測。合計 56 (関数, 引数) / 52 関数。

| 分類 | 修正前 (ablation = `bumps={}` で実測) | 修正後 (head 実測) |
|---|---|---|
| none | 22 | 22 |
| first-deref-not-entry | 15 | 16 |
| ptr-arg | 10 | 10 |
| first-deref-not-entry+ptr-arg | 4 | 4 |
| tracker-no-deref | 3 | 0 |
| first-deref-not-entry+w32 | 2 | 3 |
| first-deref-not-entry+w32+raw-after | 0 | 1 |

変化した組 (修正前 → 修正後):
- 75a180 arg4: tracker-no-deref → first-deref-not-entry
- dc27c0 arg2: tracker-no-deref → first-deref-not-entry+w32
- db6480 arg4: tracker-no-deref → first-deref-not-entry+w32+raw-after

**ablation** (`ldfix.py` の `bumps = {}` に置換した別ツリーで同じ分類を実行): 全 56 組のうち 53 組は head と完全一致 (`diff` の差は上記 3 組の行のみ)。修正前の分類 (none 22 / fdne 15 / ptr-arg 10 / fdne+ptr 4 / tracker-no-deref 3 / fdne+w32 2) は REPORT 初版の「修正前」列と一致した。

### 5.3 db6480 arg4 の `raw-after` の由来 (ablation + 出所の直接測定)

- 分類の定義: `raw-after` = 「最初の deref より後に、同じ argN の生の使用がある」。
- `python3 ldfix/origin_probe_1324.py` (head 実測) の出力:
  - function_75a180 arg4: `('deref', 7709291, 4, 64, 'argv')`
  - function_db6480 arg4: `('deref', 14378363, 4, 32, 'argv')`・`('raw', 14378480, 4)`
  - function_dc27c0 arg2: `('deref', 14428262, 2, 32, 'argv')`・`('deref', 14428369, 2, 32, 'argv')`
  - function_5c44b0 arg2: `('deref', 6046911, 2, 64, 'arg')` (不変)
- db6480 arg4 の唯一の deref は出所 `'argv'` (db657b)。`raw-after` はこの deref の後の生の使用 (14378480) で判定される。
- ablation (`bumps={}`) では db6480 arg4 が `tracker-no-deref` に戻り、`raw-after` は消える。よって `raw-after` の増加は argv 由来の deref を起点とする。
- 指摘 2 への判断: 3 組の移動は、修正の目的 (tracker-no-deref を解消する) そのものの結果で、既存の分類を壊していない (残り 53 組は不変)。受入条件 3 は (i) の条件を満たす。

### 5.4 指摘 1 の修正 (出所フィルタ) が IR を変えないこと (実測)

- `fix_f3c_use` の門 (a) は `u[4] == 'arg'` の deref だけを数える (head `ea1a8c80` でも同じ)。
- §5.1 の `cmp` で、head の出力 IR は 8483b900 と完全一致した。argv 由来の deref が門に入る形 (修正前の `1af9cad2` 以前の挙動) との比較は行っていない。
- 測定の範囲は入力 `boot_final3.ll` の全関数。ldfix は同じ入力の全関数を処理するため、この入力に対しては門の変化は IR に現れなかった。他の M11 入力については未測定。

### 5.5 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 3 関数の deref を使って `fix_f3c_use` を通す修復は行っていない (門 (a) で見送り) | 3 関数の修復は未着手 | #1325 (LD-46) |

## 6. 検証範囲

- **実測 (head `ea1a8c80`)**: `trk_probe_1134.py` (§3)・`gate_5c44b0_1324.py` (§4)・`use_residual_509.py` 全 56 組 (§5.2)・`origin_probe_1324.py` (§5.3)・ldfix 出力 IR の旧新 `cmp` (§5.1)・ablation (§5.2・§5.3)。
- **e2e (`ldfix_509_e2e.sh` の 6/7 wasm 比較・7/7 動的確認) は未実施**。IR が 8483b900 と完全一致したことは実測したが、wasm の e2e 比較は行っていない。「wasm が変わらない」の根拠は IR 一致 (§5.1) に限る。e2e の実行は本 PR の範囲外 (修復を入れる #1325 で行う)。
- **範囲外**: `REPORT_930` の 23/24 と 30/33 の不一致 (#1134 §4 で未調査として残件。本 PR では触らない)。

## 7. 再現

```
cd tools/m11
python3 ldfix/trk_probe_1134.py                                    # §3
python3 ldfix/gate_5c44b0_1324.py                                  # §4
python3 ldfix/use_residual_509.py work/boot_final3.ll work/m11_image.bin 'work/boot*.drc.config.json' ldfix/results/audit_509_pre.json all  # §5.2
python3 ldfix/origin_probe_1324.py                                 # §5.3
PYTHONPATH=. python3 ldfix/ldfix.py work/boot_final3.ll out.ll --pe work/extracted/block00031_PE.bin  # §5.1 (旧 8483b900 と cmp)
```

入力: `work/` は `tar --zstd -xf $ARTIFACTS_DIR/work-m11.tar.zst` で `tools/m11/` 直下に展開 (`work/` の中身がそのまま入る)。PE は `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C work extracted/block00031_PE.bin`。

## 8. 測定 commit と差分

測定 commit: `ea1a8c80` (ldfix.py の内容はこの commit のもの。以後のコード変更は `origin_probe_1324.py` の追加のみ)。

ldfix の差分 (8483b900 → 測定 commit):

```
git diff 8483b900 ea1a8c80 -- tools/m11/ldfix/ldfix.py
```

測定 commit からの差分 (`git diff ea1a8c80 HEAD -- tools/m11/ldfix`) は PR 本文の検証節を参照。

## 9. レビュー差し戻し後の対応 (fix モード)

| 指摘 | 対応 | 状態 |
|---|---|---|
| 1. argv 由来 deref が `fix_f3c_use` の門に入る | `1af9cad2` で門 (a) を `u[4] == 'arg'` の deref に限定 (§2) | 解消。head で IR 一致を実測 (§5.1) |
| 2. 受入条件 3 が未達 | PM 決定 (i) に従い、ablation と出所測定で示した (§5.2・§5.3) | 達成 |
| 3. head での再測定 | `work-m11` 素材が届いたので head `ea1a8c80` で再測定 (§3・§4・§5) | 実測済み |
| 4. REPORT の測定 commit が head と不一致 (差し戻し 2 回目) | §3〜§5 の数値を head で取り直し、測定 commit を `ea1a8c80` に統一 | 解消 |
