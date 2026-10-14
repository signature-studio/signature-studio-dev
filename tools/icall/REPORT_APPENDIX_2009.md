# 付録: icall #2009 (ICALL-55) — wasm 側 encoded slot 初期化と crash 残り 3 件の切り分け

> 親: #1921 (ICALL-51)。前付録: `REPORT_APPENDIX_1921.md`。本 run は受入条件 1 の一部・4 の実測まで。

## 1. 結論

- 受入条件 1 (wasm 側に enc(NULL)=cookie を入れ、`0x1810553d0` の不一致が解消するか): **未達**。
  wasm 側の初期化 (`FA_ENC_INIT=1`) は入れたが、`0x1810553d0` は closure 外の `0x1810806a0` (未解決 indirect target) を呼び、wasm が abort する。不一致は解消しない。
- 受入条件 2 (encoded 表の連続範囲と数の特定): **未達**。本 run では着手していない。
- 受入条件 3 (crash 残り 3 件の原因切り分け): **未達**。ON/OFF いずれでも crash のまま。
- 受入条件 4 (`fa_sweep.sh 8 60` の件数変化の実測): **達成**。§3。

## 2. 変更

- `tools/icall/fa_route_build.sh`: `FA_ENC_INIT=1` のとき、data install の末尾で encoded slot 12 件に cookie (`0x3125eaa8` 相当) を書く。既定 (未設定) は従来と同一。
- `tools/icall/diff/fa_cmp.py`: wasm 実行前に `_ott_data_install()` を呼ぶ。従来は data 未敷設のまま比較していた。

測定 commit: `009c77bd` (コードを変えた最後の commit)。HEAD までの差分は 0。

## 3. fa_sweep 実測 (`bash tools/icall/diff/fa_sweep.sh 8 60`)

| 条件 | 所要 | bit一致 | native crash/timeout | wasm のみ err | 値の不一致 | 合計 |
|---|---|---|---|---|---|---|
| OFF (既定) | 82 s (real) | 46 | 66 | 9 | 10 | 131 |
| ON (`FA_ENC_INIT=1`) | 82 s (real) | 46 | 64 | 11 | 10 | 131 |

- 前 run (#1921) の ON 47/64/9/11 は、`_ott_data_install()` を呼ばない比較で出た値。今回の修正後の ON は 46/64/11/10 で、一致件数は増えていない。
- OFF→ON で状態が変わった関数:
  - `0x181065928`: crash → wasm abort (`FAIL-FAST`)。前 run の「bit一致」が data 未敷設に依存していたかは未検証 (推定)。
  - `0x1810553d0`: crash → wasm abort。
- 原因: `0x1810553d0` → indirect call → `0x1810806a0` が `fa_route` の `icall` テーブルに無い (`map.json` の `func_map` 外)。closure 外の関数で、data 敷設の有無とは別件。
- 所要・load は同一マシン・同条件 (load 0.5〜0.8) で測定。

## 4. crash 残り 3 件 (`0x1803b3fc0`・`0x1803b5b60`・`0x1803b9ff0`)

ON/OFF とも `fa_cmp.py` 単体で crash_or_timeout。原因は未切り分け。`0x1803b3fc0`/`0x1803b5b60` は native 側 SIGSEGV (`addr=nil`)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x1810806a0` (closure 外 indirect target) の解決。`map.json` の範囲を広げるか、該当 import/関数の扱いを決める | `0x1810553d0`・`0x181065928` の wasm abort | ICALL-55 (子) |
| encoded 表 (api-set 相当) の連続範囲と数の特定 | 受入条件 2 | ICALL-55 (子) |
| crash 残り 3 件の原因切り分け | 受入条件 3 | ICALL-55 (子) |
| 実経路で必要な未実装 import の実装 | 同上 | #1922 (ICALL-52) |

## 6. 再現

```
bash tools/ott/native/build.sh
bash tools/icall/fa_route_build.sh                        # OFF
bash tools/icall/diff/fa_sweep.sh 8 60
FA_ENC_INIT=1 bash tools/icall/fa_route_build.sh          # ON
FA_ENC_INIT=1 bash tools/icall/diff/fa_sweep.sh 8 60
```
