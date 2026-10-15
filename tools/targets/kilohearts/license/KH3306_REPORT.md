# KH-51 (#3306) VEX-256 (ymm) と xmm の下位 128bit の同期 (kh_lower の別グローバル問題)

- 担当 dir: `tools/targets/kilohearts/license/` (親 #709 KH-14・後続 #3307 KH-52)
- 既知類型との関係 (DEFECTS.md / icall §4): **該当 ID なし (新類型候補)**。`@xmmN` (i128) と `@ymmN` (i256) が別グローバルで、VEX-128 の書込みが ymm の下位を更新しないため、後続の `load i256 @ymmN` が古い値を読む。silent miscompile (loud failure ではない)。行案は §8。
- 測定 commit: `df5005a7b` (main 取り込みの merge commit。コードを変えた最後の commit。§3-5 で再測定)。前回の測定 commit は `0145b3414` (差し戻し対応)、その前は `ca83f24e`

## 0. 結論 (先出し)

| 受入条件 (#3306) | 結果 |
|---|---|
| 1. xmmN と ymmN の下位 128bit を同一の状態として扱う | **達成**。kh_lower の `ymm_sync` (§2) で、xmm 書込みは ymm 下位を更新 (VEX-128 は上位 0・非 VEX は上位保持)、ymm 書込みは xmm を更新する |
| 2. vzeroupper の `store i256 undef, @ymmN` が xmm の値を壊さない | **達成 (N<16)**。`ymmN := zext(xmmN)` に置換。合成 3 関数の実行後も xmm2 = `0x12345779` (期待値どおり)。N≥16 は従来どおり undef (未解決 1) |
| 3. ネガコン: 同期規則を外すと 2 関数の模擬で不一致 | **達成**。`--skip ymmsync` で `MISMATCH bits=3` (rc 1)。規則あり `OK` (rc 0) |
| 4. 既存 module F (lift 8 件) の wasm sha256 不変 | **達成**。変更前後とも `7ba79e65ec158a711646316579e6f8bc3d8c12f47c61851710a5e2077b8c7707` (54,394 B) |

→ 4 件とも達成。`Closes #3306`。実機 2 関数 (`0x180f89cf0`・`0x180fb6124`) の lift 完了は #3307 (KH-52) の範囲 (gen_simd に i256 語彙が無い)。

差し戻し対応 (review round 1・blocking 1): wrapper の `ymm_sync` が参照する `@ymm0-15` の宣言漏れを修正 (§2)。vzeroupper を含まず ymm 参照が 1 つだけの 2 関数 (`0x180f89cf0`・`0x180fb6124` と同形) は、修正前 `clang -c` が `use of undefined value '@ymm10'` で失敗していた。修正後は受理される。検出用に `ymm_sync_check.py` へ `one` ケースを追加 (§3-1: 修正前 FAIL / 修正後 PASS)。

## 1. 変更点

| ファイル | 内容 |
|---|---|
| `lift/kh_lower.py` | `ymm_sync(lines, rep)` を追加。`ymm_on` (モジュール内の関数本体に `@ymmN` 参照がある時だけ真) のとき、関数本体と wrapper に適用。`--skip ymmsync` で外せる。`@ymmN` の宣言は使用分に加え、`ymm_on` のとき 0-15 を全て宣言 (wrapper の同期用、差し戻し対応) |
| `scripts/ymm_sync_check.py` | 2 関数の模擬 (+ vzeroupper を含む 3 関数) の検証。on / off (ネガコン) の 2 系を clang で実行して判定。差し戻し対応で `one` (vzeroupper なし・ymm 参照 1 つの 2 関数を `clang -c` で検査) を追加 |
| `scripts/ymm_sync_driver.c` | 上記の実行器。OK (rc 0) / MISMATCH (rc 1) |
| `scripts/lowered_identity.sh` | module A/B/E/F の lowered.ll・mod.wasm を、比較元 commit (既定 64fd760) と現 HEAD で cmp (§3-3・§5)。差し戻し対応で追加 |

ymm を参照しないモジュールは `ymm_on` が偽で、出力は従来コードと同一 (§3-3 で A/B/E/F の lowered.ll をバイト比較)。

## 2. 同期規則 (kh_lower `ymm_sync`)

| 形 (stage-0 IR) | 規則 |
|---|---|
| `store i128 %v, @xmmN` かつ `%v` が `call i128 @__asm_v*` の結果 (VEX-128) | `ymmN := zext(%v)` (上位 0)。VEX-128 の書込みは上位を 0 にする |
| `store i128 %v, @xmmN` (非 VEX = legacy SSE) | `ymmN := (ymmN & 上位mask) \| zext(%v)` (上位保持) |
| `store i256 %v, @ymmN` | 元の store の後に `xmmN := trunc(%v)` |
| `store i256 undef, @ymmN` (vzeroupper、N<16) | `ymmN := zext(xmmN)` (下位は xmm の値、上位 0) |

宣言: wrapper (abicheck の `store i128 …, @xmm6..15` と float 引数の `store @xmm0..3`) も `ymm_sync` の対象になり `@ymm0..15` を参照する。`used` (宣言の集計) は wrapper 生成より前に計算されるため、`ymm_on` のとき `@ymm0..15` を全て宣言する (`lift/kh_lower.py` の `regs`)。

限界: VEX かどうかは「書込む値の SSA 定義が `__asm_v*` の呼出か」で判定する。load など別の出所の値は legacy 扱い (上位保持)。実機 2 関数は全て VEX 形のため、legacy 経路は合成テストでも未検証 (未解決 2)。

## 3. 検証 (測定 commit `ca83f24e`)

### 3-1. 合成 3 関数 (実機 2 関数と同じ命令形)

`python3 scripts/ymm_sync_check.py` (license/ で実行。素材不要。clang のみ)

| 系 | kh_lower の出力 | 実行結果 | rc |
|---|---|---|---|
| on (規則あり) | `ymmsync` 33 / `ymmzero` 16 | `OK xmm2=12345779` | 0 |
| off (`--skip ymmsync`) | 規則なし | `MISMATCH bits=3 xmm2=12345779 ymm2_lo=00000000` | 1 |
| one (`--lift 180f89cf0,180fb6124 --skip icall`・vzeroupper なし) | `ymmsync` 23 | `clang -c` 受理 (`lower_rc` 0 / `clang_c_rc` 0) | 0 |
| one の負例 (比較元 64fd760 の kh_lower を一時ツリーで実行) | `ymmsync` 23 | `clang -c` error: `use of undefined value '@ymm10'` (`clang_c_rc` 1) | 1 |

- A: `vmovd` → `vpshufd` で xmm2 を書く (VEX-128)。B: `load i256 @ymm2` と `vinsertf128 ymm2, ymm2, xmm2, 1`。C: `vzeroupper` (ymm0-31 の undef store)。
- driver の判定: bit1 = ymm2 下位 ≠ xmm2、bit2 = ymm2 上位 ≠ 0、bit4 = xmm2 ≠ 期待値。off は bit1 のみでなく bit2 も立つが、ymm2 上位の undef 値に依存するため判定は bit 全体で見る。
- 結果: `RESULT PASS` (on = OK かつ off = MISMATCH かつ one = `clang -c` 受理)。所要 0.46 秒 (wall)。逐次実行 (並列 1・nproc 4)、load average (1 分) は実行前 0.40 → 実行後 0.40。
- one の経路: wrapper の `ymm_sync` が `@ymm6..15` (abicheck) と `@ymm0..3` (float 引数) を参照する。修正前は `regs` が body の集計だけで宣言していたため、`@ymm10` が未宣言になった。

### 3-2. 実機 2 関数の stage-0 IR (素材 `plugins-kilohearts`)

- 素材: `plugins-kilohearts` の Installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B) を手展開。RetDec は [RETDEC] (ランナー既設)、emsdk は [EMSDK] (既設)。
- `capture_stage0` (`0x180f89cf0-0x180f89d96`・`0x180fb6124-0x180fb624d`): 12.2 秒。stage-0 は 4,210 行。
- `kh_lower.py` (`--lift 180f89cf0,180fb6124`、既定 skip): `ymmsync` 33 / `ymmzero` 48 (vzeroupper 3 箇所 × 16 語)。unlifted callees 0・icall sites 0。
- `clang -c` で lowered.ll → object: 36,344 B (受理)。
- 出力例 (`ymm2`): `store i128 %57, @xmm2` の後に `%kys1.z = zext i128 %57 to i256` → `store i256 %kys1.z, @ymm2`。
- 差し戻し対応後の再測定 (`0145b3414`・同じ入力): stage-0 4,210 行 (同じ)、`ymmsync` 33 / `ymmzero` 48 (同じ)、`clang -c` 受理・36,344 B (同じ)。`capture_stage0` + kh_lower + clang を 11.8 秒 (wall)、逐次、load average 0.16 → 0.34。
- **gen_simd は未実施**: 2 関数の `vinsertf128` / `vpcmpeqd` / `vpmovmskb` (i256) の語彙が license の gen_simd に無いため、module 化 (emcc) は KH-52 (#3307) の範囲。

### 3-3. 既存モジュールの不変

- module F の wasm (変更前 `7ba79e65…7707`・変更後 `7ba79e65…7707`・54,394 B・undefined imports 0)。コマンド: `python3 lic_build.py --module F` (retdec 12.0 秒・emcc 0.6〜1.4 秒)。
- 変更前後の kh_lower で `lowered.ll` をバイト比較 (変更前 = origin/main `41623210` の kh_lower を別ディレクトリに置いて同じ引数で実行):

| module | lowered.ll (sha256 先頭 16 桁) | 判定 |
|---|---|---|
| A | `6e060033b8bd083c` (base = new) | IDENTICAL |
| B | `ebc44c3279184fff` | IDENTICAL |
| E | `dce18807b836964a` | IDENTICAL |
| F | `805d43bf3376b701` | IDENTICAL |

- 4 モジュールとも stage-0 の関数本体に `@ymm` 参照が 0 件 (`awk` で数えた)。よって `ymm_on` が偽で、差分は出ない。
- `lic_check.mjs work` (module A/B の 70 項目): ok 70 / fail 0。
- `kh249_check.mjs` (module F の 17 項目): ok 17 / ng 0 (`kh249_product_index.py` を素材から生成してから実行。KH656_REPORT の値と一致)。
- lic_build の A/B/E の wasm sha256 は本 run では比較基準が無い (変更前の値を取っていない)。同一 lowered.ll から下流 (emcc) は同一出力になるため、比較は lowered.ll のバイト一致で代える。

- 差し戻し対応後の再測定 (測定 commit `0145b3414`・比較元 `64fd760` = 差し戻し前の PR head)。`bash scripts/lowered_identity.sh 64fd760` (§5):

| module | lowered.ll | mod.wasm | sha256 | bytes |
|---|---|---|---|---|
| A | IDENTICAL (ymm 参照 0) | IDENTICAL | `411007b8…b6fc` | 26,705 |
| B | IDENTICAL (ymm 参照 0) | IDENTICAL | `62182947…cf04` | 25,249 |
| E | IDENTICAL (ymm 参照 0) | IDENTICAL | `0cf066d1…fed8` | 364,770 |
| F | IDENTICAL (ymm 参照 0) | IDENTICAL | `7ba79e65…7707` | 54,394 |

- module F の wasm は `7ba79e65…7707` (54,394 B) で、変更前の REPORT 値と一致 (`lic_build.py --module F` を `0145b3414` で実行)。所要 24.0 秒 (wall)、逐次実行 (並列 1・nproc 4)、load average (1 分) 0.37 → 0.65。
- `lic_check.mjs` / `kh249_check.mjs` は本対応で再実行していない。A/B/E/F の wasm が比較元と同一 sha のため、判定は前回値 (測定 commit `ca83f24e`) を引き継ぐ。

### 3-4. ネガティブコントロール

| 対象 | 壊した点 | 結果 |
|---|---|---|
| 同期規則 (3-1) | `--skip ymmsync` | MISMATCH bits=3 (rc 1)。on は OK (rc 0) |

vzeroupper の undef 規則を個別に外す対照は未実施 (undef の実行時値に依存して判定が揺れるため、静的検査 `ymm_store_undef_lt16` = 0 で代える)。

### 3-5. main 取り込み後の再測定 (測定 commit `df5005a7b`)

main (`e59ca23b9`) を取り込んだ後の HEAD で §3-1・§3-3 を再実行。比較元は main の `e59ca23b9` (旧比較元 `64fd760` は main の #709 より前のため使わない)。逐次・nproc 4・load average (1 分) 0.43 (実行直前)。

| 検証 | 結果 | 所要 (wall) |
|---|---|---|
| `python3 scripts/ymm_sync_check.py` | `RESULT PASS` (on = `OK xmm2=12345779` rc 0 / off = `MISMATCH bits=3` rc 1 / one = `clang -c` 受理 rc 0) | 0.34 秒 |
| `bash scripts/lowered_identity.sh e59ca23b9` | module A/B/E/F の lowered.ll・mod.wasm すべて IDENTICAL・rc 0。sha256 は §3-3 の表と同じ (F = `7ba79e65…7707`・54,394 B) | 18.8 秒 |

- 取り込みで入った main 側の差分は `gen_simd.py` (+67) と `scripts/kh709_ymm_check.py` (+158) (main の #709)。`lift/kh_lower.py` は PR 側の版と同一 (`git diff aeafbcc48 df5005a7b -- lift/kh_lower.py` 0 行)。
- main の kh_lower 宣言 (#709: `k<16` かつ使用のとき `@ymmN` を宣言) は、PR 側の宣言 (`k<32` かつ使用、または `ymm_on` のとき `k<16`) の部分集合。競合はこの 1 箇所で、PR 側の版を採った。

## 4. 検証範囲 / 範囲外

- 範囲内: kh_lower の同期規則、合成 3 関数の実行、実機 2 関数 stage-0 からの kh_lower 出力と clang の受理、module A/B/E/F の lowered.ll 一致、module F の wasm sha256。
- 範囲外: 実機 2 関数の emcc / 実行 (gen_simd の i256 語彙が無い = #3307)、`run_all.sh` 全体 (snapin 6 種は本 run で未実行)、legacy SSE 経路の実機検証。

## 5. 再現

```sh
cd tools/targets/kilohearts/license
python3 scripts/ymm_sync_check.py          # 合成検証 (素材不要。clang のみ)
KH_UI_WORK=<kilohearts>/work bash ui_eval/extract_core.sh   # 素材: HeartCore.core_64 (plugins-kilohearts を展開。sha256 検証あり)
bash scripts/lowered_identity.sh 64fd760   # A/B/E/F の lowered.ll・mod.wasm を比較元 commit と cmp (RetDec + emsdk)。rc 0 で全 IDENTICAL
python3 lic_build.py --module F            # wasm sha256 = 7ba79e65…7707 (素材 + RetDec + emsdk)
```

## 6. 測定 commit と差分 (docs/WORKFLOW.md §6)

- 測定 commit `df5005a7b` (§3-5)。本 REPORT の commit 以降の HEAD までのコード差分 (`lift`・`scripts` の範囲): 下記で確認。
- 前回の測定 commit `0145b3414` からの差分 (`git diff --stat 0145b3414 df5005a7b -- …lift …scripts`): `lift/gen_simd.py` 67 行・`scripts/kh709_ymm_check.py` 158 行 (どちらも main の #709 の取り込み。PR 側の変更は 0 行)。
- 前回の測定 commit `ca83f24e` からの差分 (`git diff --stat ca83f24e 0145b3414 -- …lift …scripts`): `lift/kh_lower.py` 3 行 (宣言の修正)、`scripts/ymm_sync_check.py` 15 行 (one 追加)、`scripts/lowered_identity.sh` 34 行 (新規)。差し戻し対応 (§0) の範囲。

```
git diff df5005a7b HEAD -- tools/targets/kilohearts/license/lift tools/targets/kilohearts/license/scripts
(出力 0 行)
```

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 1. vzeroupper の `store i256 undef` (N≥16) は従来どおり undef のまま。VZEROUPPER は 64bit モードで ymm0-15 のみ変えるため、model の逸脱。xmm0-15 には影響しない | EVEX 形の関数を lift する時に ymm16-31 の値が未定義になる | #3307 (KH-52) の本文で扱う |
| 2. legacy SSE 書込みの上位保持 (`ymm := (ymm & 上位mask) \| zext`) は合成テストでも実機でも未検証 | 混在コードで上位が誤ると、後続の ymm 読みが狂う | #3307 (KH-52) |
| 3. 実機 2 関数の lift・emcc (gen_simd に i256 語彙が無い: `vinsertf128` / `vpcmpeqd` / `vpmovmskb`) | 実機での bit 一致は未確認 | #3307 (KH-52) |
| 4. wrapper の xmm 引数 (float/double) の同期は適用したが、テストは i64 引数のみ | ymm を読む関数に float 引数が来る経路は未検証 | #3307 (KH-52) |

## 8. DEFECTS.md への行案 (PM 判断)

| ID | 症状 | 根本原因 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|---|
| (PM 採番) | VEX-128 (xmm) の書込み後に ymm の下位を読むと古い値 | stage-0 の `@xmmN` と `@ymmN` が別グローバル。VEX-128 の書込みが ymm を更新しない | `0x180f89cf0` の `store i128 %57, @xmm2` 直後の `load i256 @ymm2` (#709 の 2 関数) | IR に `@xmmN` の store と `@ymmN` の load が同じ関数内で続く | kh_lower `ymm_sync` (本 PR)。検証 `scripts/ymm_sync_check.py` |
