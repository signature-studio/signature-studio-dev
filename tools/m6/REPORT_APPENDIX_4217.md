# tools/m6 REPORT 付録: #4217 (CI-187) OTT 解析スクリプトの `/home/ubuntu` 直書き置換

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
| `grep -rn /home/ubuntu tools/m6` | 0 件 |

## 受入条件 2 (`m6_lift.sh` 前後の出力 sha256 一致) は未実施

- 素材 `plugins-ott.tar.zst` の中身は `Install_Xfer_OTT_137.exe` / `.dmg` (インストーラ) のみ。`OTT_vst2_win64.dll` は含まれない (`tar --zstd -tf` で実測)。
- `m6_lift.sh` は `work/ott_ranges.txt` (gitignore 対象・前段 `ott_closure` の生成物) を読むが、本 run では存在しない。
- 素材 `analysis-ott-binaries` は許可名だが、本 run の素材置き場には無い。
- よって置換前後の sha256 を実測できない。この項目は未解決 (下表)。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `m6_lift.sh` 前後の出力 sha256 一致の実測 (受入条件 2) | 既定値の同一性はパス文字列の比較で確認済みだが、実行結果の同一性は未確認 | #4217 (部分達成のため Refs) |
