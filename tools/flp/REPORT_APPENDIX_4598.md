# #4598 (L-18) Render tests の打ち切り 8 本の原因特定と 32-bit float 書き出し (部分達成)

測定 commit: `ccac99706` (`origin/main` 取り込み時点の HEAD)。以降のコード差分は `git diff ccac99706 HEAD -- tools/flp/s1_wine_probe.sh tools/flp/s2_render_probe.sh tools/flp/s2_imm_patch.py tools/flp/s1_g03_patch.py` の出力 0 行 (本 PR は文書と結果 TSV のみ)。

## 1. 条件
- 素材 `fl-win64` 展開 6.2 s (`tar --zstd`)。wine 9.0 (apt `wine64`)・xvfb を導入。
- S1 `s1_wine_probe.sh`: 2 m 10 s。インストール木 25,131 ファイル。FL64.exe の起動は 120 s で rc=124 (GUI 継続)。
- S2 `s2_render_probe.sh`: 1 本ずつ直列、各 1 run。`WFBox`=2・`DitherBox`=0・Sample rate 48000 (既定)。
- 測定時の load: 本 run では `/proc/loadavg` を取っていない (未計測)。

## 2. 結果
結果は `tools/flp/corpus/render_export_4598.tsv`。

| 本 | 上限 | 結果 |
|---|---|---|
| Patcher (effect) | 120 s | **rc=0・16 s**・48 kHz / fmt 3 / 2ch / 32-bit float・data 770,000 B。SHA-256 `1af4ee64…4a58152` は `render_export_4376.tsv` の値と一致 (同環境の別 run) |
| FLEX | 120 s | rc=124・WAV なし |
| Fruity Center | 120 s / 300 s | rc=124・WAV なし (300 s でも同じ) |
| Fruity Convolver | 120 s | rc=124・WAV なし |
| Fruity Parametric EQ 2 | 120 s | rc=124・WAV なし |
| Fruity Slicer | 120 s | rc=124・WAV なし |
| Maximus | 120 s | rc=124・WAV なし |
| Patcher (generator) | 120 s | rc=124・WAV なし |
| Sytrus | 120 s | rc=124・WAV なし |

- 受入 1: 未達 8 本のうち WAV が出たのは 0 本。要確認だった Patcher (effect) は「rc=124 で要確認」から「rc=0 で成功」になった。未達 8 本 (FLEX・Fruity Center・Fruity Convolver・Fruity Parametric EQ 2・Fruity Slicer・Maximus・Patcher (generator)・Sytrus) は 120 s で WAV なしのままで、**原因は未特定**。
- 前段の 5 本 (FLEX・Fruity Center・Fruity Convolver・Fruity Parametric EQ 2・Fruity Slicer) は 120 s の再測定で再現。Fruity Center だけ 300 s まで延ばして確認。他 4 本の 300 s 測定は未実施。
- 残り 3 本 (Maximus・Patcher (generator)・Sytrus) も 120 s の再現まで。

## 3. 原因の手がかり (未確定)
- `s2_run_*.log` は ALSA の警告と xvfb の終了だけで、書き出しの進行は出ない (#4376 §2.4 と同じ)。
- 120 s 以上に延ばしても WAV が出ないのは Fruity Center (300 s) のみ。他は未確認。
- 成功した Patcher (effect) と失敗した Patcher (generator) は同じ系統の素材だが、差は未調査。

## 4. 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 未達 8 本 (FLEX・Fruity Center・Fruity Convolver・Fruity Parametric EQ 2・Fruity Slicer・Maximus・Patcher (generator)・Sytrus) の WAV 未出力の原因 | 受入 1・2 が未達 | #4598 (Refs) |
| 上記 8 本の 300 s 測定 (Fruity Center 以外は未実施) | 遅いだけか、止まっているかの区別がつかない | #4598 |
| Patcher (effect) は同環境の別 run で成功。wine の終了の正常性 (rc=0) は確認済み | 受入 2 (TSV 追記) は本 PR で反映 | — |
