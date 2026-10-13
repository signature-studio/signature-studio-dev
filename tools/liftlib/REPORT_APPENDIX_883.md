# LIFTLIB #883 (HB-H21) — ott_getparam の BLK 配線と this 仮引数化 (付録)

親: [`REPORT_APPENDIX.md`](REPORT_APPENDIX.md) §17.9・§17.10 (#415 / PR #807 の追跡)。
REPORT_APPENDIX.md が 250 行上限を超えているため、#883 の実測はこのファイルに分けて置く。

## 状態

未達 (受入条件 4 件のうち 0 件達成)。修正方式は未決定。コード変更なし。

| 受入条件 | 状況 |
|---|---|
| `leafspec targets/ott_getparam.json --n 200` rc=0・match 1.0・wasm_trap 0 | 未達 (下記ベースライン) |
| 修正方向を機械語と IR の突合で決め REPORT に書く | 一部 (下記「確定事項」)。方式の決定は未了 |
| ネガコン (修正を外すと match 0) | 未着手 |
| `liftlib_e2e.sh` / regress 登録 | 未着手 (FAIL のまま登録しない) |

## 実測

測定値 (F.txt `0x18011e5a0-0x18011e76c`・leafspec の match / mismatch / wasm_trap・gate FAIL) は [`REPORT_APPENDIX.md` §17.9](REPORT_APPENDIX.md) を正本とする。
本 fix run では素材 `analysis-ott-binaries` が展開されておらず再実測していない (素材の取得は `docs/WORKFLOW.md` §11)。

## 確定事項

BLK の算出式・32bit 切り詰め・`ICALL_BLK` 不一致・パイプライン順序は §17.10 を参照 (本ファイルでは再掲しない)。
本 PR で新たに確定できた差分はない。

## 実測 (再現・IR 確認)

本 PR (fix run) では再実行していない。`$ARTIFACTS_DIR` に実在するのは `fl-win64.tar.zst` のみで、`analysis-ott-binaries`・`work-*`・`toolchain-*` は展開されていない。
下表の leafspec 数値 (`rc=1`・`match=0 / mismatch=200 / wasm_trap=200`) は §17.9 の記録 (HEAD `83cd9eb4`) の引用であり、本ファイルで独立に再測定したものではない。
§17.9 の実行 run ID は本ファイル作成時点で特定できていない (`83cd9eb4` に紐づく Actions run のログに該当の leafspec 行を確認できなかった)。

IR の観測 (下表) は `work/ott_getparam/ott_getparam_fixed.ll`・`ott_getparam.drc.restored.ll` を参照しているが、`work/` は gitignore 対象で本 PR からは再生成できず、生成コマンドも未記録。以下の件数は**未検証**として扱い、再現手順が確定するまで根拠にしない:

| 項目 | 観測 |
|---|---|
| entry 引数 | `define i64 @function_18011e5a0(i32 %arg1, i64 %arg2)` (fixed) / `(i32 %arg1)` (restored)。本体は `%arg` を一切読まない |
| `this` の読み | `%0 = load i64, inttoptr 6512738312` = BLK+0x08 (rcx)。以降 `add i64 %0, 728/732/...` で使用 |
| `idx` の読み | `%1 = load i64, inttoptr 6512738320` = BLK+0x10 (rdx)。`trunc %1 to i32` / `icmp ult ..., 31` で使用 |
| 戻り値の store | `store i64 %12, inttoptr 6512738432` = BLK+0x80 (rax) (29 箇所)。`store ..., 6512738440` = BLK+0x88 (xmm0) (23 箇所) |
| BLK 参照の範囲 | BLK+0x00〜+0x88 の全 inttoptr 定数 (fixed.ll で計 135 箇所)。`@global_var` 参照は 0 |
| restored の `__icall_dispatch` | 7 箇所 (stub 呼出し → 本 leaf の build では `__builtin_trap()` stub。`stub_externals: true`) |

wasm32 (`p:32:32`) では BLK+0x08 = `0x84308008` / BLK+0x80 = `0x84308080` に切り詰められ、いずれも wasm の線形メモリ外。load・store とも OOB で trap する。

## 確定した因果

1. **入力の欠落**: entry は `this`/`idx` を BLK から読み、`%arg1`/`%arg2` を読まない。harness は wasm 引数として渡すだけで BLK へは書かない (`wasm_runner.mjs` は BLK を書く処理を持たない)。よって仮に BLK が読めても値は 0 (`this` = 0)。
2. **BLK の配置**: `icall_rewrite.py` L653 の `0x184308000` は wasm32 の線形メモリ外。load・store の両方が trap する。`blk_va` 指定は RIP 相対 int32 の制約で不可 (§17.10)。

上の 2 点はどちらも単独で trap の原因になる。1 だけ直しても 2 の store/load で trap し、2 だけ直しても `this` が 0 のまま値が合わない。

## 修正方式 (未決定・子 issue で実施)

- (a) entry の BLK 読みを `%arg` 読みへ差し替える (`this` = `%arg1` を i64 化、`idx` = `%arg2`)。戻り値の BLK store は残るため、(c) と組み合わせる必要がある。
- (b) harness が BLK+0x08/+0x10 へ this/idx を書いてから呼ぶ。BLK の wasm 内配置と同時に必要。
- (c) BLK を wasm 線形メモリ内の範囲へ移す。RIP 相対 int32 制約のため、単純な `blk_va` 指定では不可。module-local global (`@__icall_blk` 相当) へ inttoptr 定数を張り替える方式が候補。

(a)(b)(c) のどれを採るかは、呼出し規約 (`spec.py` の `A <slot>`・`native_runner.c` の gpr 配置) と BLK の書込み主体の突合で決める。本 run では方式選択までは行わない。

## 次の作業

修正・ネガコン・regress 登録は子 issue で行う (本 issue #883 は受入条件 4 件のうち達成 0 件 (4 件とも未達) → 検証未了のため open のまま)。

## 再現

```sh
OTT_DLL=<OTT_vst2_win64.dll の実パス> bash tools/liftlib/gen_ott_getparam_F.sh
cd tools/liftlib && python3 -m liftlib leafspec targets/ott_getparam.json --n 200   # FAIL (match 0)
```
