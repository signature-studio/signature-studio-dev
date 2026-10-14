# 付録: icall #2079 (ICALL-56) — closure 外 indirect target 0x1810806a0 の扱い

> 親: #2009 (ICALL-55)。前付録: `REPORT_APPENDIX_2009.md`。本 run は受入条件 1 の「扱いを決める」までの実装と、`fa_sweep.sh 8 60` の実測。受入条件 1 の「`0x1810553d0` の値の不一致が解消する」と、受入条件 2 は未達。

## 1. 結論

- `0x1810806a0` は closure の root に入っていなかった (`closure.py` は直接 call / 末尾 jmp しか辿らないため、間接 call 先は閉包に入らない)。**扱いの決定: closure root に追加する** (stub 化はしない。実体のある関数で、native 基準を持てるため)。
- 追加後、`0x1810553d0` の wasm abort は「未登録 target」(`unresolved indirect target 0x310806a0`) から「target が不正値 `0xb77e88c8000`」に変わった。値の不一致は**解消していない** (受入条件 1 未達)。
- `0x181065928` は native が SIGSEGV で基準値が無く、wasm 側は `RangeError: Maximum call stack size exceeded` (abort ではなく stack overflow)。件数変化は §3。

## 2. 変更

- `tools/icall/fa_ranges_2079.txt` (新規): `fa_ranges_1633.txt` (HEAD の 151 関数) に `0x1810806a0` を root として `closure.py` で再計算した **152 関数**。
- 再生成手順 (`work/` は gitignore): `closure.py --roots fa_ranges_1633.txt,<0x1810806a0> --out ...` → `roundtrip.sh <SlateCore.core_64> <範囲> freshair-core` (`CHUNKS` は既定 1) → `fa_route_build.sh`。

注意 (CHUNKS): `CHUNKS=4` で回すと `after.0.restored.ll` に全関数が入らず、`fa_route` の table が 36 件になる。`fa_route_build.sh` は chunk 0 しか読まないため、既定 1 で回すこと。

測定 commit: `8e1eed27` (`fa_ranges_2079.txt` を追加した commit。以降のコード変更なし)。HEAD までの差分は本付録のみ。

## 3. fa_sweep 実測 (`bash tools/icall/diff/fa_sweep.sh 8 60`、152 関数の closure で再生成)

| 条件 | 所要 (real) | load | bit一致 | native crash/timeout | wasm のみ err | 値の不一致 | 合計 |
|---|---|---|---|---|---|---|---|
| OFF (既定) | 70.6 s | 0.79 | 61 | 74 | 2 | 5 | 142 |
| ON (`FA_ENC_INIT=1`) | 130.8 s | 0.97 | 61 | 73 | 3 | 5 | 142 |

- OFF→ON の差: `0x1810553d0` が native crash/timeout → wasm のみ err (abort) に移った (1 件)。他は不変。ON の所要が長いのは `0x1810553d0` の経路が増えたことによる (原因は未切り分け)。
- `0x181065928`: OFF/ON とも `crash_or_timeout` (native SIGSEGV で基準が無い)。件数の変化は無し。

sweep の `funcs 142` は closure 152 との差 10 件を含む。その 10 件は `func_map` 外で、REPORT_APPENDIX_1633 §3 で既出 (`1803b5546`・`18040ca0d` 等)。

## 4. 残った wasm abort の切り分け

- `fa_route` の FAIL-FAST: `[icall] FAIL-FAST: unresolved indirect target 0xb77e88c8000 at site VA 0x310553e6`。site `0x1810553e6` の間接 call で、target 値は image 外の不正値。
- 値は `0x1810806a0` の shifted 値ではない。符号化 (encoded) された関数ポインタを復号せずに使っている疑いがある。これは ICALL-57 (#2081、encoded 表の連続範囲と数) の範囲と推定 (未検証)。
- `0x181065928`: wasm 側は `Maximum call stack size exceeded`。再帰の疑い (未切り分け)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x1810553d0` の site `0x1810553e6` が不正 target `0xb77e88c8000` を呼ぶ (encoded 関数ポインタの復号が疑われる)。受入条件 1 の値の不一致解消 | `0x1810553d0` の wasm abort | #2081 (ICALL-57) で確認予定 (推定・未検証) |
| `0x181065928` の wasm 側 stack overflow (`RangeError`) と native SIGSEGV (基準なし) | 受入条件 2 の件数変化の確定 | #2079 (本 issue。再現の切り分けを残す) |
| encoded 表 (api-set 相当) の連続範囲と数 | 受入条件 2 | #2081 (ICALL-57) |
| crash 残り 3 件の原因切り分け | 前 run の残件 | #2083 (ICALL-58) |
| 実経路で必要な未実装 import の実装 | 同上 | #1922 (ICALL-52) |

## 6. 再現

```
bash tools/ott/native/build.sh
python3 tools/icall/closure.py --pe "<SlateCore.core_64>" --roots tools/icall/fa_ranges_2079.txt --out F.ranges   # 152 関数で確認
bash tools/icall/roundtrip.sh "<SlateCore.core_64>" tools/icall/fa_ranges_2079.txt freshair-core               # CHUNKS=1 (既定)
bash tools/icall/fa_route_build.sh
bash tools/icall/diff/fa_sweep.sh 8 60
FA_ENC_INIT=1 bash tools/icall/fa_route_build.sh
FA_ENC_INIT=1 bash tools/icall/diff/fa_sweep.sh 8 60
```
