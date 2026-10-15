# liftdiff REPORT 付録: LD-131 (#2801) 命令単位の VA を残す方式 (x64c 経路) の決定と静的な命令 VA 表

親 #2192 (LD-83)。前提は `REPORT_APPENDIX_LD83.md` §2・§6 (RetDec IR に命令の VA が無く、site 記録は block 単位)。

既知類型との関係: 該当なし (本付録は命令 VA の出所の決定と、x64c 出力の確認。lift 出力の意味誤りを指す `docs/DEFECTS.md` の D1a〜D23 には当たらない)。

## 結論

- 受入 1 (方式の決定): **(b) x64c の出力を使う** を採る。(a) RetDec IR に命令 VA を残す案は RetDec 路線の新規作業になり (D5)、PM 承認が無いため始めない。
- x64c の C 出力は命令ごとに `/* <VA>: <命令> */` の注記を持ち、分岐 (`if (CC_E) goto L_<VA>;`)・呼出し (`f_<VA>()`・`imp_<名>()`・`ott_unlifted(...)`) も VA と import 名で残る。実行時の記録は未実装で、x64c 側に既定 off の opt-in として入れる想定 (子 #3988)。
- 受入 2 の静的部分: 1801c5e84 の経路の `1c0b6f` (je) と `1c0b82` (HeapFree の call) を命令 VA で示せた (§3)。
- IR の site 記録 (LD-83) の VA は block 先頭であり、命令の VA ではない (§3 の対応表)。命令単位の位置は x64c 経路でしか取れない。
- 未達 (子 issue へ移した): 計装 wasm での実行 trace (受入 2 の動的部分) は #3988 (LD-185)。既定 build との 12 case 差 0 と、未 lift の callee 1 件 (1801c6a04) は #3990 (LD-186)。

## 1. 測定条件

- 測定 commit: `9bbbd6c15` (`feat(liftdiff): add x64c instruction VA map for OTT 6 roots (Refs #2801)`。計測コード・テスト・TSV を入れた最後の commit。本付録の commit はこの範囲の外)。
- 入力: `[ANALYSIS-PLUGINS]` の `ott/binaries/OTT_vst2_win64.dll` (`plugins-ott` と `analysis-ott-binaries` を展開済み。`PLUGINS_DIR` で指す)。
- lift: `tools/ott/lift/x64c.py` (`--closure 6`・root は 6 関数 `1801ab1d0 1801ab258 1801c5e84 1801c621c 1801c682c 1801c69cc`)。
  - 実行: `bash tools/liftdiff/results/ld131/ld131_lift.sh` (出力先は `${RUNNER_TEMP}/ld131`。repo の `work/` は使わない)。
  - 結果: `[x64c] functions 28, insns 941, unsup {}, unlifted callees 1, imports 11`。wall 0.67 s (`real`)。
  - 入力 DLL `OTT_vst2_win64.dll` の sha256: `ecd51e056860a37dbff4223c4dcab1a12f91e3f280161bec249fe8d97ab2378e` (`analysis-ott-binaries` と `plugins-ott` を展開して得た値)。
  - 同一入力 2 回: `ott_lifted.c` の sha256 は両回 `6b6e896bd519ccf41524d91247b2b48be6b5987c73973d178a7df6517686c826` で一致。TSV も `cmp` で一致。
  - 測定 commit `9bbbd6c15` の worktree でも同じ入力から同じ sha256 (`6b6e896b...`) を得た。よって現環境での生成物は測定 commit と同一である。
- 表の生成: `python3 tools/liftdiff/results/ld131/insn_va_map.py <ott_lifted.c> --out tools/liftdiff/results/ld131/insn_map_6fn.tsv` → 941 行 (28 関数)。
- 単体テスト: `python3 tools/liftdiff/tests/test_insn_va_map.py` → 8 件 OK (a26cd568f。round 1 で 2 件追加、§7)。ネガコン (import 呼出しの正規表現を `imp2_` に崩す) → `test_import_call` が FAIL (rc 1)。

### closure の比較 (6 root・同じ入力)

| closure | 関数 | 命令 | 未 lift の callee | import |
|---|---|---|---|---|
| 2 (`lift_build.sh` の既定) | 12 | 472 | 4 (`1801c3d80` `1801c3dc8` `1801c0af4` `1801c1cb8`) | 3 |
| 3 | 16 | 594 | 5 | 6 |
| 4 | 21 | 780 | 5 | 9 |
| 6 (本付録の表) | 28 | 941 | 1 (`1801c6a04`) | 11 |

vm0 の経路 (1c5e84 → 1c0b6c → 1bafb0 → 1c20c8 → 1c3dc8) は、closure 2 では 1c3dc8 が未 lift で止まる。closure 6 では経路の全関数が lift される。

## 2. 方式の比較

| 方式 | 内容 | 判定 |
|---|---|---|
| (a) RetDec IR に命令 VA を残す | RetDec の変換 (IR 生成) を改修し、命令ごとの注記を IR に入れる | 不採用。RetDec 路線の新規作業で、D5 の例外 (issue が明示・PM 承認済み) に当たらない。始めない |
| (b) x64c の出力を使う | x64c の C 出力は命令ごとに VA を持つ。計装は x64c の opt-in (既定 off) で入れる | **採用**。RetDec 非依存 (D5) |

## 3. 命令単位の位置 (1801c5e84 の経路)

native 命令の VA は x64c の VA と同じ (恒等の VA 対応)。TSV の該当行:

| 命令 | VA | 命令文字列 | 種別 | 先 |
|---|---|---|---|---|
| native `1c0b6f` (je) | 1801c0b6f | `je 0x1801c0ba8` | jcc | 1801c0ba8 |
| native `1c0b82` (HeapFree の call) | 1801c0b82 | `call qword ptr [rip + 0x218e8]` | call-imp | HeapFree |
| `1c0b8c` (1c0b6c 内の直接呼出し) | 1801c0b8c | `call 0x1801bafb0` | call | 1801bafb0 |

IR の site 記録 (LD-83 §4 の記号) と命令 VA の対応:

| LD-83 の記録 | 記録に付く VA (IR) | 実際の命令 (x64c) |
|---|---|---|
| `J801c0b6c.0=0` (vm0) | block 先頭 1801c0b6c | je 1801c0b6f (cond=0: 不成立) |
| `C801c0b71.0` (HeapFree) | block 先頭 1801c0b71 (`push rbx`) | call 1801c0b82 |
| `J801c5e84.0=0` (vm0) | block 先頭 1801c5e84 | je 1801c5eb6 → 1801c5ecc (不成立・次の 1801c5eb8 へ) |

VA の不一致は、LD-83 の site 記録が block の先頭 VA を持つことによる。1 block 内の複数の命令の位置は IR から区別できない。

## 4. 未 lift の callee

closure 6 の未 lift は `1801c6a04` の 1 件 (呼出し元 `1801c6a2c`)。closure 2 の未 lift 4 件は closure 6 で全て lift される。`1801c6a04` の扱いは #3990 の受入。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| x64c 出力の計装 (opt-in 既定 off の `OTT_INSN_HIT`) と計装 wasm での vm0・u16 の命令 VA 列 | 実装済み (§9)。計装 wasm の `ret` と native の rax の照合は未実施 | #3988 (LD-185・本 PR で完了) |
| 既定 build との 12 case 差 0 (liftdiff harness の x64c 対応)・未 lift callee `1801c6a04` | 受入 3。harness が x64c の wasm を入力に取れるかは未確認 | #3990 (LD-186・依存 #3988) |

## 6. 測定 commit と差分

- 測定 commit: `9bbbd6c15`。
- 最後にコードを変えた commit: `a26cd568f`。`5bd1e70dd` は本付録のみ。
- `git diff 9bbbd6c15 5bd1e70dd -- tools/liftdiff/results/ld131 tools/liftdiff/tests/test_insn_va_map.py tools/ott/lift tools/shared/env.sh` の要約: 3 ファイル、19 行追加・4 行削除。
  - `tools/liftdiff/results/ld131/insn_va_map.py` (+9/-1): `return;` の後の注記無し文を畳まない。`jmp` 注記で kind `call` の行を `jmp` にする。
  - `tools/liftdiff/results/ld131/insn_map_6fn.tsv` (2 行): `1801c682c 1801c699d` の kind `call`→`jmp`、`1801ce3f0 1801ce3f6` の `call 1801ab1d0` を削除。
  - `tools/liftdiff/tests/test_insn_va_map.py` (+10)。
  - `tools/ott/lift`・`tools/shared/env.sh` は差分なし。
- 差分は 0 ではない。再測定を実施した (§7)。`ld131_lift.sh` で生成した TSV と commit 済みの TSV は `cmp` で一致した (941 行・28 関数)。よって TSV の 2 行は生成物と一致する。
- 起動・GUI に関わらないため、製品 KPI (FLEngine 起動 dispatch 数・通過 unit 数・最初のウィンドウ) は書かない。

## 7. round 1 の修正 (レビュー指摘への対応)

- 指摘 (ret の kind・tail jmp の kind): `ret` 行に `call 1801ab1d0` が付いていた原因は、`parse()` が `return;` の後の注記無し文を直前の命令に畳んでいたこと。`return;` を含む行で収集を止めるよう修正した。`1801c682c` の `jmp` は `f_X(); return;` の形で kind `call` になっていたため、注記が `jmp` なら kind `jmp` にした。
- 単体テストを 2 件追加 (`test_ret_does_not_absorb_following_unannotated_stmt`・`test_tail_jmp_as_call_stmt_is_jmp`)。計 8 件 OK。
- TSV の 2 行は手で直した (修正後の規則と同じ値)。
- 確認: `awk -F'\t' 'NR>1 && $4=="call" && $3 !~ /^call/'` → 0 行。TSV は 941 行・28 関数で、件数は変わらない。

## 8. 再生成での照合 (round 3 の指摘への対応・HEAD = `5bd1e70dd`)

- 素材: `analysis-ott-binaries` と `plugins-ott` を `$RUNNER_TEMP/analysis` に展開。`OTT_vst2_win64.dll` の sha256 は `ecd51e056860a37dbff4223c4dcab1a12f91e3f280161bec249fe8d97ab2378e`。
- 実行: `PLUGINS_DIR=$RUNNER_TEMP/analysis/plugins bash tools/liftdiff/results/ld131/ld131_lift.sh` を 2 回 (出力先は `$RUNNER_TEMP/ld131_{1,2}`)。
  - 結果: `[x64c] functions 28, insns 941, unsup {}, unlifted callees 1, imports 11`。
  - `ott_lifted.c` の sha256 は両回 `6b6e896bd519ccf41524d91247b2b48be6b5987c73973d178a7df6517686c826` で一致。
  - 生成した TSV と commit 済みの `insn_map_6fn.tsv` は `cmp` で一致 (941 行・28 関数)。手編集の 2 行を含め、生成物と一致する。
- 測定 commit `9bbbd6c15` の worktree で同じ入力を lift したところ、`ott_lifted.c` の sha256 は同じ `6b6e896b...`。この環境の生成物は測定 commit と同一である。
- REPORT §1 の旧値 `3eeb9fe0...` は、この環境で再現しなかったため削除した。その原因 (当時の入力 DLL・環境の違い) は特定できていない。

## 9. LD-185 (#3988) x64c の命令単位 trace 計装 (opt-in)

- 実装: `tools/ott/lift/x64c.py` に `OTT_INSNTRACE=1` を追加。各命令の直前に `OTT_INSN_HIT(<shifted VA>);` を出す (既定 off では何も出さない)。runtime は `tools/ott/rt/ott_cpu.c` の `ott_insnhit` (`-DOTT_INSNTRACE` のみ本体あり)。記録は `0x35a00000` に `[u32 count][u32 cap=0x40000][u32 va...]` で書く。`0x35a00000`〜`0x35b00000` は既存の `0x34000000`・`0x35c00000`・`0x35e00000`・`0x35f00000` と重ならない。書込みは volatile・件数上限付き。
- 測定 commit: `ac529158f` (計装コード・ハーネス・検証スクリプトを入れた最後の commit)。
- 検証: `bash tools/liftdiff/results/ld185/ld185_verify.sh` (`LD185_OUT` 既定 `$RUNNER_TEMP/ld185`、`PLUGINS_DIR` は `tools/shared/env.sh` の既定)。所要 4.9 s (`real`、HEAD `ac529158f`)。入力 DLL は §1 と同じ `ecd51e05…`。

### 9.1 受入 1: 既定 off の出力

- 既定 off の `ott_lifted.c` の sha256 は `6b6e896bd519ccf41524d91247b2b48be6b5987c73973d178a7df6517686c826`。main (`21fb46e35`) の `ld131_lift.sh` 出力と `cmp` でバイト一致。
- 受入条件の基準値 `3eeb9fe0…` は現環境で再現しない (§8 と同じ)。本 PR では基準を `6b6e896b…` に読み替えて一致を示す。`3eeb9fe0…` を正にする根拠は無い。

### 9.2 受入 2: 6 root の計装ビルド

- 計装 on の lift: `[x64c] functions 28, insns 941, unsup {}, unlifted callees 1, imports 11`。`OTT_INSN_HIT` は 941 件 (命令ごと 1 件)。
- emcc (`lift_build.sh` と同じ std フラグ + `-DOTT_INSNTRACE`) でビルドが通る。`ottl_insn.wasm` 616787 B。

### 9.3 受入 3: 計装 wasm で 1801c5e84 の vm0・u16 を 1 回ずつ

- 実行: `node tools/liftdiff/results/ld185/ld185_trace.mjs <ottl_insn.cjs> <out.json>`。`ott_run` で `1801c5e84` を呼ぶ。引数は `cases.py` の `vm0` (arena+0x1000 に VMT fixup) / `u16` (arena+0x1000 に UnicodeString ヘッダ) と同じ配置。
- 命令 VA 列の件数: vm0 56、u16 76。ret は両方 `1` (native の rax との照合は未実施)。
- 1801c0b6f (je) と 1801c0b82 (call) の位置 (`ld185_summarize.py`。je 直後の VA が `1801c0ba8` なら成立、`1801c0b71` なら不成立):

| pattern | 命令 index | je 1801c0b6f | 結果 | call 1801c0b82 |
|---|---|---|---|---|
| vm0 | 17 | next 1801c0b71 | not-taken | index 23 |
| vm0 | 36 | next 1801c0ba8 | taken | - |
| vm0 | 45 | next 1801c0ba8 | taken | - |
| u16 | 17 | next 1801c0b71 | not-taken | index 23 |
| u16 | 36 | next 1801c0b71 | not-taken | index 42 |
| u16 | 55 | next 1801c0b71 | not-taken | index 61 |

- 注: vm0 の 2 回目以降の je は `1c0b6c` の分岐 (`1c5eb8 → 1c0b6c` のループ) で、u16 と成立の仕方が違う。LD-136 (`REPORT_APPENDIX_LD136.md`) は case 単位の site 集計で、本節は 1 回実行の命令列なので件数の比較はしない。
- 未確認: 計装 wasm の `ret` と native の rax の照合、LD-83 の site 記録との突合。計装 wasm の結果の妥当性 (native と同一の分岐か) は、次の子 issue で native trace と突き合わせて確かめる。

### 9.4 測定 commit と差分

- 測定 commit `ac529158f`。`git diff 21fb46e35 ac529158f -- tools/ott tools/liftdiff/results/ld185` の出力 (6 files, 154 insertions):

```
 tools/liftdiff/results/ld185/ld185_summarize.py | 34 +++++++++++++++++
 tools/liftdiff/results/ld185/ld185_trace.mjs    | 49 +++++++++++++++++++++++++
 tools/liftdiff/results/ld185/ld185_verify.sh    | 44 ++++++++++++++++++++++
 tools/ott/lift/x64c.py                          |  3 ++
 tools/ott/rt/ott_cpu.c                          | 16 ++++++++
 tools/ott/rt/ott_cpu.h                          |  8 ++++
 6 files changed, 154 insertions(+)
```
