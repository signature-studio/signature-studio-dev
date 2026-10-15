# #3053 (L-15) Render tests の 32-bit float 全数書き出し (部分達成)

測定 commit: `54fc3e6ed` (`S2_SRC` / `S2_TIMEOUT` を入れた script で測定)。以降のコード差分は `git diff 54fc3e6ed HEAD -- tools/flp/s2_render_probe.sh` = 0 行。

## 1. 条件
- FL64.exe を wine64 9.0 + xvfb で `/R` 実行 (`tools/flp/s2_render_probe.sh`)。`WFBox`=2・`DitherBox`=0 (REPORT_APPENDIX_3052 §17 の経路)、Sample rate 48000。
- 1 本ずつ直列、各 1 run。`$RUNNER_TEMP` 配下で書き出し、commit は要約 TSV だけ。
- 素材 `fl-win64` 展開 5.8 s。S1 (インストール木組立て + 起動 120 s 打ち切り) 2 m 09 s。
- 書き出しの所要: 1 本 14〜16 s (Autogun 16 s / 3OSC 14 s)。

## 2. 結果
- Render tests 82 本のうち **59 本を実行**。結果は `tools/flp/corpus/render_export_3053.tsv` (SHA-256 は data チャンク)。
  - **54 本が 48 kHz / 32-bit float (fmt 3 / 2ch / data 770,000 B)** で成功。SHA は全 54 本で相違 (重複 0)。
  - **5 本は 120 s で WAV が出ず打ち切り** (FLEX / Fruity Center / Fruity Convolver / Fruity Parametric EQ 2 / Fruity Slicer)。原因は未調査。
- **未実行 23 本** (Harmless 以降の残り)。1 本約 29 秒で 1 run の上限に収まらず、時間切れで区切った。
- **代表 Demo 3 本: 未達**。`Jay Cactus x Confz - Mic Check Ready.flp` (215 s・プラグイン 91 件) は 600 s で WAV が出ず。Demo 3 本の選定基準は文書に無く、`Demo songs` の 3 本 (Asher Postman・Astes・Jay Cactus) を仮に選んだ。Asher・Astes は未実行。

## 3. 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| Render tests の未実行 23 本 | 受入 1 の全数が未達 | #3053 |
| 打ち切り 5 本 (120 s) の原因 | 受入 1 の 54/82 の内訳 | #3053 |
| Demo 3 本の書き出し (Jay Cactus は 600 s 超) と Demo の選定基準 | 受入 1 の Demo 分が未達 | #3053 |
| SHA の同一環境外での再現性 | SHA は同一環境内のみ有効 (#3052 と同じ) | #3052 |
