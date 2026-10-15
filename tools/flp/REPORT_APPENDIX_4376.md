# #4376 (L-17) Render tests 残り 23 本・Demo の 32-bit float 書き出し (部分達成)

測定 commit: `98458ac56` (run 起動時の HEAD、main)。以降の probe script 差分 `git diff 98458ac56 636f74907 -- tools/flp/s1_wine_probe.sh tools/flp/s2_render_probe.sh tools/flp/s2_imm_patch.py tools/flp/s1_g03_patch.py` の出力行数は 0 (本 PR の作業ブランチは 636f74907 から分岐)。前段の測定 commit `54fc3e6ed` からも同じ 4 script の差分は 0 行。

## 1. 条件
- `tools/flp/s2_render_probe.sh` を 1 本ずつ直列、各 1 run。`WFBox`=2・`DitherBox`=0・Sample rate 48000 (#3053 と同じ)。
- 素材 `fl-win64` 展開 8.6 s (`tar --zstd`)。wine 9.0 (apt `wine64`) + xvfb-run を導入。
- S1 (インストール木組立て + 起動 120 s 打ち切り): 2 m 06 s。rc=124 (GUI 継続) で前段と同じ。
- Demo は `Data/Demo projects/Demo songs/` を `S2_SRC` に指定し、`S2_TIMEOUT=300`。

## 2. 結果
### 2.1 Render tests 残り 23 本 (`Harmless.flp` より後)
結果は `tools/flp/corpus/render_export_4376.tsv`。rc=0 は 19 本、rc=124 は 4 本。

- **WAV 成功 (rc=0) 19 本**: 48 kHz / 32-bit float (fmt 3 / 2ch) を確認。所要 11〜13 s。
  - data 770,000 B が 16 本、Low Lifter が 1,538,000 B、Wave Traveller が 660,000 B。
- **WAV 欠落 (120 s 打ち切り) 3 本**: Maximus・Patcher (generator)・Sytrus。
- **rc=124 だが WAV あり 1 本 (要確認)**: Patcher (effect)。WAV は 770,000 B で他と同じ長さ。プロセスの正常終了は確認できていない。成否は未判定とし、#4598 に含める。

Render tests 82 本の内訳: 成功 73 本 (前段 54 + 今回 19)、未達 8 本 (前段の打ち切り 5 + 今回の WAV 欠落 3)、要確認 1 本 (Patcher (effect))。

### 2.2 前段の打ち切り 5 本 (120 s)
FLEX・Fruity Center・Fruity Convolver・Fruity Parametric EQ 2・Fruity Slicer。今回は再実行していない。原因は未調査。

### 2.3 Demo 3 本
- Asher Postman - Future House.flp: 300 s で WAV なし。
- Astes - Bien Duro.flp: 300 s で WAV なし。
- Jay Cactus x Confz - Mic Check Ready.flp: 前段で 600 s でも WAV なし。今回は再実行していない。
- Demo の選定基準は文書に無い。今回の選定は前段の 3 本をそのまま使った。

### 2.4 打ち切りの観測
`s2_run_1.log` は ALSA の警告 (`/dev/snd/seq` 不在) と xvfb の終了だけで、書き出しの進行は出ない。ログからは原因を特定できなかった。

## 3. 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 打ち切り 5 本 (前段) と WAV 欠落 3 本 (Maximus・Patcher (generator)・Sytrus) の原因。Patcher (effect) の成否 (rc=124 で WAV あり) を含む | Render tests 82 本のうち未達 8 本・要確認 1 本 | #4598 |
| Demo 3 本 (Asher・Astes は 300 s でも WAV なし、Jay Cactus は 600 s でも未出力) と選定基準 | 受入 1 の Demo 分が未達 | #4599 |
| SHA の同一環境外での再現性 | SHA は同一環境内のみ有効 (#3052 と同じ) | #3052 |
