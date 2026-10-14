# LIFTLIB #883 (HB-H21) — ott_getparam の BLK 配線と this 仮引数化 (付録)

親: [`REPORT_APPENDIX.md`](REPORT_APPENDIX.md) §17.9・§17.10 (#415 / PR #807 の追跡)。
REPORT_APPENDIX.md が 250 行上限を超えているため、#883 の実測はこのファイルに分けて置く。

## 状態

未達 (受入条件 4 件のうち 0 件達成)。修正方式は未決定。コード変更なし。

| 受入条件 | 状況 |
|---|---|
| `leafspec targets/ott_getparam.json --n 200` rc=0・match 1.0・wasm_trap 0 | 未達 (§17.9 参照・出所未確認) |
| 修正方向を機械語と IR の突合で決め REPORT に書く | 一部 (下記「確定事項」)。方式の決定は未了 |
| ネガコン (修正を外すと match 0) | 未着手 |
| `liftlib_e2e.sh` / regress 登録 | 未着手 (FAIL のまま登録しない) |

## 実測

測定値 (F.txt `0x18011e5a0-0x18011e76c`・leafspec の match / mismatch / wasm_trap・gate FAIL) は [`REPORT_APPENDIX.md` §17.9](REPORT_APPENDIX.md) を正本とする。
本 fix run では素材 `analysis-ott-binaries` が展開されておらず再実測していない (素材の取得は `docs/WORKFLOW.md` §11)。

## 確定事項

BLK の算出式・32bit 切り詰め・`ICALL_BLK` 不一致・パイプライン順序は §17.10 を参照 (本ファイルでは再掲しない)。
本 PR で新たに確定できた差分はない。

## 引用値と IR 確認 (未再測定)

本 PR (fix run) では再実行していない。`$ARTIFACTS_DIR` に実在するのは `fl-win64.tar.zst` のみで、`analysis-ott-binaries`・`work-*`・`toolchain-*` は展開されていない。
leafspec の測定値は [`REPORT_APPENDIX.md` §17.9](REPORT_APPENDIX.md) を参照 (出所未確認の引用。本ファイルで独立に再測定したものではない)。
§17.9 の測定 commit は `83cd9eb4` と記録されているが、その実行 run ID・CI ログは本ファイル作成時点で特定できていない (`gh run list` で `83cd9eb4` に紐づく run は 0 件)。

IR 上の読み (下記) は `work/ott_getparam/` の生成物を参照したものだが、`work/` は gitignore 対象で本 PR からは再生成できず、生成手順・件数の数え方も未記録。**以下はすべて未検証の仮説**であり、件数は根拠にしない:

- entry 引数は `function_18011e5a0` の `%arg1`・`%arg2` (fixed 版) で、本体は `%arg` を読まないように見える。
- `this` は BLK+0x08 (rcx)、`idx` は BLK+0x10 (rdx) から load されているように見える。
- 戻り値の store 先は BLK+0x80 (rax)・BLK+0x88 (xmm0) に見える。
- 参照範囲は BLK+0x00〜+0x88 の inttoptr 定数に見える。

出所未確認の記録にある事実は次の 1 点のみ: §17.9 L240 の wasm trap 解析 (`LL_VERBOSE=1`) で BLK+8 (rcx) の load が OOB で trap したこと。

## 確定事項 (アドレス算出)

1. `icall_rewrite.py` L653 の算出で BLK = `0x184308000`。wasm32 (`p:32:32`) では BLK+0x08 が `0x84308008` に切り詰められる。線形メモリ上限との関係は未確認 (§17.10)。`blk_va` 指定の可否は未確認 (試行の記録が無い)。§17.9 の記録 (出所未確認) にある BLK+8 load の trap 解析の記載のみ。

## 仮説 (未検証)

1. **入力の欠落**: entry が `this`/`idx` を BLK から読み、`%arg` を読まないのであれば、harness は BLK へ書かないため (`wasm_runner.mjs` に BLK を書く処理は無い)、仮に BLK が読めても値は 0 になる。この読みは IR 再生成で確認するまで仮説として扱う。

## 修正方式 (未決定・子 issue で実施)

- (a) entry の BLK 読みを `%arg` 読みへ差し替える (`this` = `%arg1` を i64 化、`idx` = `%arg2`)。戻り値の BLK store は残るため、(c) と組み合わせる必要がある。
- (b) harness が BLK+0x08/+0x10 へ this/idx を書いてから呼ぶ。BLK の wasm 内配置と同時に必要。
- (c) 候補 (未検証): BLK を wasm 線形メモリ内の範囲へ移す。`blk_va` 指定で足りるかは未確認。module-local global (`@__icall_blk` 相当) へ inttoptr 定数を張り替える方式も候補。

(a)(b)(c) のどれを採るかは、呼出し規約 (`spec.py` の `A <slot>`・`native_runner.c` の gpr 配置) と BLK の書込み主体の突合で決める。本 run では方式選択までは行わない。

## 配置の算術と既存機構の確認 (run 3, コード変更なし)

- `icall_rewrite.py` L653 の既定 BLK = `img.base + image_size + 0x4000000` = `0x184308000` (`blk_va` 未指定時)。wasm32 では `0x84308000` に切り詰められる。
- section VA は `0x180308000`。RIP 相対 int32 (±2 GiB) で届く最小番地は `0x100308000` で、4 GiB 未満の wasm 線形メモリ内には届く番地がある。ただし画像は `0x180000000` 系 VA のまま wasm に載るため、BLK を低位へ移すには画像ごと shift する必要がある。
- leaf パイプライン (`targets/ott_getparam.json`) は `passes.shift` を持たず、`pipeline.py` L137 の `remap.shift_va` は実行されない。`recipes/ott.py` (OTT 既存 recipe) は `LB_BASE` (0x30000000 系) へ shift して wasm に載せている。
- したがって #1269 の方式は「leaf 側へ `shift` (newbase) を導入する」が最小候補。その場合 native 側 (`native_runner.c` の VA 敷設) と harness の突合 (#1270) も同時に揃える必要がある。本 run ではコードを変えず、この前提のみを確定した。

## 次の作業

修正・ネガコン・regress 登録は子 issue で行う (本 issue #883 は受入条件 4 件のうち達成 0 件 (4 件とも未達) → 検証未了のため open のまま)。

## #1269 (HB-H28) BLK 配置の実測 (HEAD b1d2fe82 / 測定 commit 604e900f, コード変更なし)

素材 (展開実測): `analysis-ott-binaries` → `$HOME/analysis/plugins/ott/binaries/` (OTT_vst2_win64.dll)、`work-liftlib`・`work-m6-ott`・`work-icall` → 各 `tools/*/work/`。`fl-win64`・`toolchain-*` は本 run では不使用。

| 項目 | 結果 |
|---|---|
| F.txt (`gen_ott_getparam_F.sh`) | `0x18011e5a0-0x18011e76c` (closure 1 関数, 460 bytes) |
| `leafspec targets/ott_getparam.json --n 200` (ベースライン) | rc=1, 5.6 s, match 0 / mismatch 200 / wasm_trap 200 |
| BLK | `0x184308000` (6512738304)。`ott_getparam_fixed.ll` 内の `inttoptr (i64 N to ptr)` 参照は 135 箇所、アドレスは BLK+0x00〜+0x88 の 13 種 |
| `--blk-va 0x100308000` | rewriter が `struct.pack('<i')` で例外終了 (RIP 相対 int32 が範囲外)。map は生成されず |
| `--blk-va 0x30000000` | 同上 (例外終了) |
| `tests/test_icall.py` (測定 commit 604e900f) | RESULT PASS (0 failed) |
| `icall_rt.c` の既定 BLK | `ICALL_BLK = 0x34308000` (rewriter の `0x184308000` と不一致。runtime 側の既定値) |

測定 commit 604e900f → HEAD b1d2fe82 の実行コード差分: `git diff 604e900f b1d2fe82 -- tools/` は REPORT_APPENDIX_883.md のみ (26 行追加・コード差分 0)。

### 方式の判定 (受入条件 1)

- **(b) rewriter 側で wasm32 向け BLK を選ぶ**: 不採用。`--blk-va` で wasm 線形メモリ内 (4 GiB 未満・64 MiB 内) の番地を指定すると、RIP 相対 int32 の制約で rewriter が落ちる。`0x100308000` (section 直下) は RIP 相対変位が int32 範囲外でもある。よって rewriter 単独では BLK を wasm 内へ置けない。
- **(a) module-local global への張り替え**: 採用候補 (未実装)。IR の `inttoptr (i64 BLK+off to ptr)` 135 箇所を、モジュール内の固定配列グローバルへの参照に置き換える。BLK は wasm の data/bss 内に入るため、線形メモリ範囲を超えない。`ir_icall_restore.py` が出す `blk + 0x80`・`blk + 0xb0` の参照も同じ置換が要る。
- 実装は未着手。配置の置換 (IR 135 箇所 + restore の 2 系統) とビルド・ネガコン・`icall_e2e.sh` の前後測定が残るため、本 run では実装せず、#1269 に残す。

### 残作業 (#1269 の受入条件のうち未達)

1. (a) の実装と `leafspec` の wasm_trap 0 の確認 (match の判定は #1270 の受入条件)。
2. `icall_e2e.sh` の前後測定。`ANALYSIS_DIR` は既定値が環境依存のため、環境変数で指定する (本 run では `$HOME/analysis` を指定)。また `tools/ott/work/` (`ott_e2e.sh` の成果物) が前提で、本 run では未展開。
3. ネガコン (修正を外すと wasm_trap 200 に戻る) の実測。

## 再現

```sh
OTT_DLL=<OTT_vst2_win64.dll の実パス> bash tools/liftlib/gen_ott_getparam_F.sh
cd tools/liftlib && python3 -m liftlib leafspec targets/ott_getparam.json --n 200   # FAIL (match 0)
```

## #883 run (測定 commit 9f336206, コード変更なし): shift 併用の実測

素材: `analysis-ott-binaries` / `work-liftlib` / `work-m6-ott` を展開 (`$HOME/analysis/plugins/ott/binaries/OTT_vst2_win64.dll`)。`gen_ott_getparam_F.sh` → F.txt `0x18011e5a0-0x18011e76c` (460 bytes)。

| 設定 (leafspec `--n 200`) | rc | 時間 | match / mismatch / wasm_trap |
|---|---|---|---|
| ベース (`targets/ott_getparam.json`, blk_global=false, shift なし) | 1 | 4.1 s | 0 / 200 / 200 |
| `shift` 0x180000000→0x30000000 のみ | 1 | 1.9 s | 0 / 200 / 200 |
| `blk_global=true` + `shift` 0x180000000→0x30000000 | 1 | 1.9 s | 0 / 200 / 200 |
| `blk_global=true` + `shift` 0x180000000→0x100000 | 1 | 1.9 s | 0 / 200 / 200 |

判定: 3 設定すべて `memory access out of bounds` (`LL_VERBOSE=1`)。一時設定ファイルは削除済み (リポジトリ差分なし)。

### 分かったこと

1. `passes.shift` は `remap.shift_va` で `i64 <定数>` の 193 箇所を平行移動する (`shift_numeric: 193`)。適用はされている。
2. しかし shift 後の `*_fixed.ll` に、加算形の画像 VA 参照が残る: `%17 = add nuw nsw i64 %x, 6442450944` (= 0x180000000) の後に `inttoptr`。`shift_va` は `i64 <定数>` の即値しか対象にしないため、この形は動かない。
3. `blk_global` は BLK を `@__icall_blk` の GEP へ置く (`inttoptr` 定数は 0 件、`@__icall_blk` 136 箇所)。BLK 自体は trap の原因ではなくなった。
4. よって trap の残り原因は、(a) 加算形の image VA (`0x180000000` 基準) が shift されていないこと、(b) 入力 this/idx が BLK から読まれ harness が書かないこと (#1270)、の 2 点。

### 次の作業

- (a) `shift_va` で加算定数 `6442450944` (0x180000000 の加算) を image base 移動の対象に含める (`remap.py` 側の拡張)。その上で shift 後の wasm 線形メモリ上限 (`newbase` の選択と INITIAL_MEMORY) を確認する。
- (b) は #1270 (this/idx 受渡し) で扱う。

## #1583 (HB-H33) run: blk_global 単独の実測 (測定 commit 5f0a8ce9, origin/main 起点 worktree)

素材: `fl-win64` 以外の要求素材を展開 (`analysis-ott-binaries` → `$HOME/analysis/plugins/ott/binaries/`、`work-liftlib`・`work-icall`・`work-m6-ott` → 各 `tools/*/work/`)。`gen_ott_getparam_F.sh` → F.txt `0x18011e5a0-0x18011e76c` (460 bytes)。

| 設定 (leafspec `--n 200`) | rc | 時間 | match / mismatch / wasm_trap |
|---|---|---|---|
| ベース (`blk_global: false`, shift なし) | 1 | 6.1 s | 0 / 200 / 200 |
| `blk_global: true` のみ | 1 | 未計測 | 0 / 200 / 200 |

`blk_global: true` の効果: `work/ott_getparam/ott_getparam_fixed.ll` の BLK 参照は `@__icall_blk` の GEP 136 件へ置換され、`inttoptr (i64 BLK+off)` の残りは 0 件。それでも全シナリオが wasm trap する。

残りの trap 原因 (`ott_getparam_fixed.ll` の静的数え上げ):

- 画像 VA 範囲 (`0x180000000`〜) の `i64` 即値が 193 件 (distinct 65)。`shift_va` の対象は `i64 <即値>` のみ。
- 加算形 `add nuw nsw i64 %x, 6442450944` (= 0x180000000) が 2 件 (例: `%18 = add nuw nsw i64 %17, 6442450944`)。`shift_va` は対象外のため平行移動されず、この形の後の `inttoptr` が画像 VA を指す。
- よって BLK の張り替え (受入条件 1) 単独では wasm trap は消えず、画像 VA 側の shift が要る。

修正方針 (未実装・子 issue へ): `remap.shift_va` に加算定数 (`add ... , <image VA>`) を含める拡張、または leaf 側に `passes.shift` を入れて `newbase` を wasm 線形メモリ内へ移す。いずれも ott 既存 recipe (`recipes/ott.py` の `shift_va`) の出力に影響しうるため、ott_route / ott_iargs の前後一致を確認してから入れる。
