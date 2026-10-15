# tools/m6 REPORT 付録: #4217 (CI-187) OTT 解析スクリプトの固定パス直書き置換

親: #294。本付録は `tools/m6/REPORT.md` (行数上限超過のため新規付録に分割) の追補。

## 変更内容

`tools/m6/` の 11 ファイルの既定パスを `tools/shared/paths.py` / `tools/shared/env.sh` の `PLUGINS_DIR` 経由に置換した。

| ファイル | 変更 |
|---|---|
| `ir6_gdata.py`・`m6_data_gen.py`・`m6_scan.py` | `WINF` を `f'{PLUGINS_DIR}/ott/binaries/OTT_vst2_win64.dll'` に。`m6_data_gen.py` は `M6_PE` 環境変数の既定値 |
| `ott_match.py`・`ott_match2.py`・`ott_match3.py`・`ott_match4.py`・`ott_vtables.py`・`ott_vtables2.py` | `MAC`/`MACF`・`WIN`/`WINF`・`NMLOG` を `PLUGINS_DIR` 基準に |
| `m6_lift.sh` | `source tools/shared/env.sh` の後、`BIN="$PLUGINS_DIR/ott/binaries/OTT_vst2_win64.dll"` |
| `m6_diag.py` | `sys.path` の repo 外の固定 dir を `__file__` 基準に (repo 外パスを消した) |

既定値は従来と同一。`paths.py` の `PLUGINS_DIR` 既定は `$ANALYSIS_DIR/plugins` で、作業用 VM の旧 literal (`ANALYSIS_DIR` 既定 + `/plugins`) と一致する。

## 実測 (既定値・環境変数上書き)

| 項目 | 結果 |
|---|---|
| `env -u PLUGINS_DIR -u ANALYSIS_DIR python3 tools/shared/paths.py` | `PLUGINS_DIR` = 作業用 VM の旧 literal (`ANALYSIS_DIR` 既定 + `/plugins`) |
| `PLUGINS_DIR=/tmp/x python3 tools/shared/paths.py` | `PLUGINS_DIR=/tmp/x` (上書き有効) |
| bash 既定 (`source tools/shared/env.sh`) | `<PLUGINS_DIR>/ott/binaries/OTT_vst2_win64.dll` = 置換前 literal と一致 |
| `tools/m6/*.py` の `py_compile` | 全件 成功 |
| `bash -n tools/m6/m6_lift.sh` | 成功 |
| 旧パス文字列の `grep` (tools/m6 内) | 0 件 |

## 受入条件 2 (`m6_lift.sh` 前後の出力 sha256 一致) の実測 (#5122)

測定 commit: `2d0357a51` (main)。`06d58a49a` から HEAD までの `tools/m6`・`tools/shared/{env,paths}.*`・`tools/m2`・`tools/m5` のコード差分は 0 件。

- 素材: `plugins-ott.tar.zst` はインストーラのみ。`Install_Xfer_OTT_137.exe` を `7z x` で展開し、`$_13_/OTT_x64.dll` を `$PLUGINS_DIR/ott/binaries/OTT_vst2_win64.dll` に配置 (sha256 `ecd51e05…2378e`)。
- `m6_scan.py` (`PLUGINS_DIR` 指定) → `tools/m6/work/ott_ranges.txt` 3983 bytes (166 関数)。
- 実行環境: 4 core / load 0.61。RetDec は `/opt/retdec`。

| 実行 | 入力の BIN | 所要 | `work/ott_lift.ll` sha256 |
|---|---|---|---|
| 置換後 (HEAD) 1 回目 | `$PLUGINS_DIR/...` | 8 s | `0e81b107f00cf3d39fce18b7dd37750721d370ee2a44cd1555c5001d29f2bb10` |
| 置換後 (HEAD) 2 回目 | 同上 | (同一 run) | 同上 (`cmp` で 1 回目と一致) |
| 置換前相当 | 旧 `BIN=` 行の文字列を同じ DLL パスに向けた一時版 | (同一 run) | 同上 (`cmp` で一致) |

- 置換前の literal (`/home/ubuntu/...`) は本 VM に作れない (`/home/ubuntu` 不在・sudo 無し) ため、旧スクリプトをそのまま実行はしていない。上の「置換前相当」は `BIN` 行だけを旧文字列と同じ変数展開先に差し替えた版であり、BIN 以外の差分は HEAD と同一。
- 判定: 置換後の `ott_lift.ll` は 2 回の実行と置換前相当版で sha256 が一致。受入条件 2 は満たした。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 子 1 (#5121) の issue が open のまま (置換は #4462 で main 済み) | issue 状態のみ。コードには影響なし | #5121 (PM の close 判断) |
