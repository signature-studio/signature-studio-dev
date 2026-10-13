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

## 次の作業

修正・ネガコン・regress 登録は子 issue で行う (本 issue #883 は受入条件 4 件のうち達成 0 件 (4 件とも未達) → 検証未了のため open のまま)。

## 再現

```sh
OTT_DLL=<OTT_vst2_win64.dll の実パス> bash tools/liftlib/gen_ott_getparam_F.sh
cd tools/liftlib && python3 -m liftlib leafspec targets/ott_getparam.json --n 200   # FAIL (match 0)
```
