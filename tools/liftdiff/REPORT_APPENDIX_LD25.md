# liftdiff LD-25 (#977): 状態前提 (InitTable / TLS index) を満たす case 生成

親: #235 / 関連: PR #805 (InitUnits の空振り一致が未解決)。本付録は #977 の実測と判定。

## 1. 原因 (機械語で確定)

`System.@InitUnits` (image 0x4120c0) は次を読む (逆アセンブル: `capstone` + `ldlib.pe`):

- `0x4120cc`: `mov rax, [0x11eac90]` = InitTable 参照 (global slot)
- `0x4120d3`: `test rax, rax` → `je` で **0 なら何もせず戻る**
- `0x4120d8`: `mov ecx, [rax]` = unit 数、`0x4120e4`: `mov rax, [rax+8]` = unit 配列
- `0x41210f`: `mov [0x11eac98], eax` = `System.InitCount` (unit 呼出し前にインクリメント)

units モード (`work/m11/boot_state.json`・22 unit 状態) の boot 状態では、
`0x11eac90` は **0** のまま (state の img run に含まれない)。InitUnits は何もせず戻る。
native も wasm も同じく ok を返すため、**空振り一致**になる。

`0x11eac90` / `0x11eac98` は `[WIN64]` の `extracted/block00031_PE.bin` 上で `.bss` (ファイル上の raw size 0) に置かれ、初期値は 0 (`pefile` で section 確認・2026-10-13)。units の img run に値が無いのは pristine 側も 0 のためで、`boot.precondition()` の 0 判定はこの前提で正しい。

## 2. 実測 (`tests/check_initunits.py`・`liftdiff_e2e.sh --m11-only` の [3b/4])

測定 commit `3b689b25` (#977 ブランチ・main `dee83f6c` を merge 済み) で `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/liftdiff/liftdiff_e2e.sh --m11-only` を実行 (2026-10-13 実測: exit 0 / 198s / PASS、[3b/4] CHECK_INITUNITS PASS)。
11 pattern すべて:

| state | precondition (InitTable ptr / InitCount / TLS set) | 11 pattern の結果 | 空振り (EMPTY) |
|---|---|---|---|
| units (`boot_state.json`, batch 既定) | 0 / 0 / 0 → **NG** | equal 11 (両側 calls 0・mem 0) | **11 / 11** |
| hybrid (`boot_state_hybrid.json`, `bootstate --mode hybrid`) | 0x1376 8b0 / 246 / 1 → **OK** | native_fault (segv) 11 / wasm ok | 0 / 11 |

- hybrid で InitUnits が実際に走り、native は既知の unit 830 (`0x4e0fab` 付近) 相当の segv で落ちる。
  これは **明示的な非一致 (unexec)** として区別される (空振り一致ではなくなった)。
- 判定 `CHECK_INITUNITS PASS` = hybrid で EMPTY が 0 件。units の EMPTY 件数は defect の記録 (FAIL 条件ではない)。

## 3. 既存 pattern への影響 (sample:800・受入条件 3)

既定 batch 経路 (units) は**変更していない**。実行 HEAD `feef8ce6` で hybrid と突き合わせ、判定遷移を比較 (実測: units は e2e 経由 109s・単独 107s/111s、hybrid は単独 229s):

| state | match | mismatch | unexec |
|---|---|---|---|
| units (既定・`--m11-only` の [4/4]) | 360 | 230 | 210 |
| units (単独実行) | 361 | 229 | 210 |
| hybrid (`batch --state work/m11/boot_state_hybrid.json`) | 352 | 258 | 190 |

遷移 (units e2e 経由 → hybrid): match→mismatch 25 / mismatch→match 13 / unexec→match 5 / unexec→mismatch 19 /
mismatch→unexec 3 / match→unexec 1。計 66 関数 (800 中 8.3%)。単独 units との突合では 67 関数 (差は `0x959a40` の揺れ 1 件)。
(件数は JSONL (`work/m11/batch_sample_800.jsonl`・`work/m11/batch_sample_800_hybrid.jsonl`) の function.va 単位の突合で算出。)

判断: 既定を hybrid に切り替えると既存の判定基準が変わるため、**既定は units のまま**とした。
hybrid を既定にするかは別 issue で、遷移表 (上記) を根拠に判断する。

## 4. 実装 (変更点)

| パス | 変更 |
|---|---|
| `ldlib/boot.py` | `precondition(st)`: InitTable 参照・InitCount・TLS index (heap 内 TLS 配列の非ゼロ数) を判定 |
| `liftdiff.py bootstate` | mode が units 以外なら `boot_state_<mode>.json` に保存 (units の既定ファイルを上書きしない)。precondition を表示 |
| `tests/check_initunits.py` (新規) | units / hybrid の両 state で InitUnits 11 pattern を実行し、空振り一致 (呼出列・書込み 0 件の equal) を検出。hybrid で 1 件でもあれば FAIL |
| `liftdiff_e2e.sh` | [3b/4] として `check_initunits.py` を追加 |

## 5. 未解決

- 既定 batch 状態を hybrid にするか (上記 §3 の 66 関数の遷移を伴う)。起票先: 親 #235 にコメント。
- hybrid の unit 830 segv (残 3 unit) は REPORT §2.2 の既存の下流課題。

## 6. 検証 (測定 commit と差分)

- 測定 commit: `3b689b25` (`9fb30a45` に main `dee83f6c` を merge。#977 fix モード)。
- 差分: `git diff 5d2df224 3b689b25 -- tools/liftdiff` は 11 ファイル / +615 −7 (`ldlib/cases.py` +29・`ldlib/session.py` +35 を含む)。旧 `5d2df224` の値は無効として、本節の値で置き換えた。
- 素材: `fl-win64 work-m11 work-liftdiff` を `$RUNNER_TEMP` に展開し `tools/` 配下へ配置 (gitignore 対象)。`toolchain-emsdk` は `emsdk install 6.0.12` で [EMSDK] に pin 版を導入。
- 実行 HEAD `feef8ce6` (`tools/liftdiff` は `3b689b25` から docs のみ変更) で `liftdiff_e2e.sh --m11-only`: exit 0 / 189s / load 6.15→6.02 / **LIFTDIFF_E2E PASS**。[3b/4] **CHECK_INITUNITS PASS**。[4/4] sample:800 一致 360 / 不一致 230 / 実行不能 210 (batch 109s)。
- 揺れ: 同じ HEAD で `batch --set sample:800` を単独実行 (`--state auto`) すると 2 回とも 361 / 229 / 210 (107s・111s)。差は `0x959a40` の 1 件のみ (`p1`・`pall`・`qall` の判定が diff と equal の間で揺れる)。e2e 経由では mismatch、単独では match。sample:800 の一致は 360〜361 の範囲で揺れる。
- hybrid (`batch --state work/m11/boot_state_hybrid.json --set sample:800`・単独 1 回): 一致 352 / 不一致 258 / 実行不能 190 (229s)。units (単独 r2) → hybrid の遷移は 67 関数 (e2e 経由の units 結果では 66)。
