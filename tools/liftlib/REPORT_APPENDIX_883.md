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

## 確定事項 (本 PR で新たに確定した差分)

§17.9・§17.10 に無い点のみ記す。BLK の算出式・32bit 切り詰め・`ICALL_BLK` 不一致・パイプライン順序は §17.10 を参照。
出典は前 run の IR 実測 (`tools/liftlib/work/ott_getparam/ott_getparam_fixed.ll`・gitignore・本 run では不在)。

1. entry 先頭で BLK+0x10 (`idx`/rdx 相当) も直接 load する (§17.10 では未確認)。`%arg1` (this) と `%arg2` (idx) は本体で読まれない。
2. 戻り値の store 先も BLK 絶対アドレス: BLK+0x80 (rax)・BLK+0x88 (xmm0)。

## 未確定 (次の作業)

- **修正方式の選択**: (a) entry の BLK 読みを `%arg` 読みに差し替える (`this`/`idx` を仮引数から取る)、(b) harness が BLK へ this/idx を書いてから呼ぶ、(c) BLK の配置自体を wasm 内の範囲に収める (`blk_va` 指定は rewriter の RIP 相対 int32 制約で不可 = §17.10 の試行)。
- (a) と (b) のどちらが正しいかは、呼出し規約の正本 (`spec.py` / `native_runner.c` の引数 slot) と BLK の書込み主体を突合して決める。今回はその突合まで到達していない。
- 本 run の harness 経路 (`wasm_runner.mjs`) は BLK を書く処理を持つかを確認していない。

## 再現

```sh
OTT_DLL=<OTT_vst2_win64.dll の実パス> bash tools/liftlib/gen_ott_getparam_F.sh
cd tools/liftlib && python3 -m liftlib leafspec targets/ott_getparam.json --n 200   # FAIL (match 0)
```
