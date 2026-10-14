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
  この呼び出しは `FA_ENC_INIT` と無関係に**常に実行される**。したがって §3 の OFF/ON はどちらも data 敷設ありの条件で測られている。`FA_ENC_INIT=1` で変わるのは encoded slot 初期化だけ。

測定 commit: `009c77bd` (コードを変えた最後の commit)。HEAD までのコード差分は 0 (`git diff 009c77bd HEAD` は本ファイルのみ)。

## 3. fa_sweep 実測 (`bash tools/icall/diff/fa_sweep.sh 8 60`)

| 条件 | 所要 | bit一致 | native crash/timeout | wasm のみ err | 値の不一致 | 合計 |
|---|---|---|---|---|---|---|
| OFF (既定) | 82 s (real) | 46 | 66 | 9 | 10 | 131 |
| ON (`FA_ENC_INIT=1`) | 82 s (real) | 46 | 64 | 11 | 10 | 131 |

- 同一 run 内の比較: OFF→ON で bit一致は 46 のまま変化なし。値の不一致は件数 10 のまま。native crash/timeout は 66→64 (−2)、wasm のみ err は 9→11 (+2)。
- 上の差を関数アドレスで説明できた分と未説明の分:
  - `0x181065928`: native crash → wasm abort (`FAIL-FAST`)。crash −1 / err +1 を説明する。
  - `0x1810553d0`: 値の不一致 → wasm abort (`FAIL-FAST`)。不一致 −1 / err +1 を説明する。
  - **未説明**: 不一致 +1 と crash −1 の 1 件。native crash/timeout から値の不一致へ移った関数が 1 件あるはずだが、関数アドレスは特定していない (関数別の `sweep.jsonl` が本 run の work/ に残っていないため)。
  - 合計: crash −2 (説明 1・未説明 1)、err +2 (説明 2)、不一致 0 (説明 −1・未説明 +1)、bit一致 0。
- **前 run (#1921) との比較 (条件差あり・FA_ENC_INIT の効果とは分離できない)**: 前 run の ON は 47/64/9/11 で、bit一致が 47 だった。前 run の `fa_cmp.py` には `_ott_data_install()` が無く、data 未敷設で測られている。本 run は data 敷設ありで測っており、bit一致 47→46 はこの data 敷設の有無 (`_ott_data_install`) を含む条件差による。FA_ENC_INIT の効果とは分離できない。
- **bit一致から外れた関数は未確定**: `0x181065928` が前 run の bit一致から外れたかは確認できていない。本 run の OFF では `0x181065928` は既に native crash であり、OFF/ON の同一 run 比較では bit一致の変化はない。確定には `work-icall`・`plugins-freshair` の素材ありで `fa_sweep.sh 8 60` を再実行し、関数別の判定を見る必要がある。素材は本 run で `$ARTIFACTS_DIR` に無かったため再測定できなかった。
- 原因: `0x1810553d0` → indirect call → `0x1810806a0` が `fa_route` の `icall` テーブルに無い (`map.json` の `func_map` 外)。closure 外の関数で、data 敷設の有無とは別件。
- 所要・load は同一マシン・同条件 (load 0.5〜0.8) で測定。

## 4. crash 残り 3 件 (`0x1803b3fc0`・`0x1803b5b60`・`0x1803b9ff0`)

ON/OFF とも `fa_cmp.py` 単体で crash_or_timeout。原因は未切り分け。`0x1803b3fc0`/`0x1803b5b60` は native 側 SIGSEGV (`addr=nil`)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x1810806a0` (closure 外 indirect target) の解決。`map.json` の範囲を広げるか、該当 import/関数の扱いを決める | `0x1810553d0`・`0x181065928` の wasm abort | #2079 (ICALL-56) |
| encoded 表 (api-set 相当) の連続範囲と数の特定 | 受入条件 2 | #2081 (ICALL-57) |
| crash 残り 3 件の原因切り分け | 受入条件 3 | #2083 (ICALL-58) |
| §3 の未説明差分 (crash −1 / 値の不一致 +1 の 1 件) の関数特定と、前 run からの bit一致 47→46 の関数特定 (素材ありで `fa_sweep.sh` 再実行) | §3 の確認 | 本 PR (#2009) の未解決。素材 (`work-icall`・`plugins-freshair`) 付きの run で確定 |
| 実経路で必要な未実装 import の実装 | 同上 | #1922 (ICALL-52) |

## 6. 再現

```
bash tools/ott/native/build.sh
bash tools/icall/fa_route_build.sh                        # OFF
bash tools/icall/diff/fa_sweep.sh 8 60
FA_ENC_INIT=1 bash tools/icall/fa_route_build.sh          # ON
FA_ENC_INIT=1 bash tools/icall/diff/fa_sweep.sh 8 60
```
