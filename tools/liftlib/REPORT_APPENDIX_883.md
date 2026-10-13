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

## 実測 (2026-10-13 run, 基点 origin/main 3c11af59)

素材: `fl-win64` / `toolchain-retdec` / `toolchain-emsdk` / `plugins-ott` / `analysis-ott-binaries` / `work-liftlib` / `work-m6-ott` / `work-icall` を `$HOME/artifacts` で実在確認。OTT 実機 DLL は `$HOME/analysis/plugins/ott/binaries/OTT_vst2_win64.dll` (3146752 B)。依存 capstone/pefile は venv (`$RUNNER_TEMP`) に導入。

| 手順 | 結果 |
|---|---|
| `OTT_DLL=... bash tools/liftlib/gen_ott_getparam_F.sh` | F.txt = `0x18011e5a0-0x18011e76c` (1 関数, 460 B) |
| `python3 -m liftlib leafspec targets/ott_getparam.json --n 200` | match=0 / mismatch=200 / wasm_trap=200 / native_crash=0、gate `rate=0.000 thr=1.00 -> FAIL`、RESULT: FAIL |

## 確定事項 (IR 実測)

`work/ott_getparam/ott_getparam_fixed.ll` (define は `i64 @function_18011e5a0(i32 %arg1, i64 %arg2)`):

1. entry 先頭 (L7〜L22) で `inttoptr i64 6512738312` (= 0x184308008 = BLK+8, `this`/rcx) と BLK+0x10 (`idx`/rdx) などを直接 load する。`%arg1` (this) と `%arg2` (idx) は本体で読まれない。
2. 戻り値の store 先も BLK 絶対アドレス (例: `6512738432` = 0x184308080 = BLK+0x80 (rax)、`6512738440` = BLK+0x88 (xmm0))。
3. BLK 基準は `icall_rewrite.py` L653: `blk = img.base + image_size + 0x4000000` (`img.base > 0x100000000` の枝)。`img.base` 0x180000000 のため、wasm32 (`p:32:32`) では `0x84308000` 付近に切り詰められ範囲外になる。
4. `icall_rt.c` の既定 BLK は `ICALL_BLK = 0x34308000` で rewriter の値と一致しない (leaf build は `icall_rt.c` を link しないため、この不一致は今回の trap の直接原因ではない)。
5. パイプラインの順序 (`liftlib/pipeline.py` L102-135): `icall.restore` (BLK 読みの IR 化) → `iargs` (仮引数追加) → `f2` → `p1` → `f7` → `leafabi` → `gdata`。`iargs` は仮引数を足すだけで、BLK 読みは置換しない。

## 未確定 (次の作業)

- **修正方式の選択**: (a) entry の BLK 読みを `%arg` 読みに差し替える (`this`/`idx` を仮引数から取る)、(b) harness が BLK へ this/idx を書いてから呼ぶ、(c) BLK の配置自体を wasm 内の範囲に収める (`blk_va` 指定は rewriter の RIP 相対 int32 制約で不可 = §17.10 の試行)。
- (a) と (b) のどちらが正しいかは、呼出し規約の正本 (`spec.py` / `native_runner.c` の引数 slot) と BLK の書込み主体を突合して決める。今回はその突合まで到達していない。
- 本 run の harness 経路 (`wasm_runner.mjs`) は BLK を書く処理を持つかを確認していない。

## 再現

```sh
export OTT_DLL=$HOME/analysis/plugins/ott/binaries/OTT_vst2_win64.dll
bash tools/liftlib/gen_ott_getparam_F.sh
cd tools/liftlib && python3 -m liftlib leafspec targets/ott_getparam.json --n 200   # FAIL (match 0)
```
