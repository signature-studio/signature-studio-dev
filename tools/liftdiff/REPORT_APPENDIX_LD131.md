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
  - 同一入力 2 回: `ott_lifted.c` の sha256 は両回 `3eeb9fe0c6cc213ca0d170d992a991b26b733c99a0ccd2199b1b33eab885f827` で一致。TSV も `cmp` で一致。
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
| x64c 出力の計装 (opt-in 既定 off の `ld_insn`) と計装 wasm での vm0・u16 の命令 VA 列 | 受入 2 の動的部分。命令単位の trace が無い | #3988 (LD-185) |
| 既定 build との 12 case 差 0 (liftdiff harness の x64c 対応)・未 lift callee `1801c6a04` | 受入 3。harness が x64c の wasm を入力に取れるかは未確認 | #3990 (LD-186・依存 #3988) |

## 6. 測定 commit と差分

- 測定 commit: `9bbbd6c15`。
- `git diff 9bbbd6c15 HEAD -- tools/liftdiff/results/ld131 tools/liftdiff/tests/test_insn_va_map.py tools/ott/lift tools/shared/env.sh` の要約 (HEAD = `a26cd568f`): 3 ファイル、19 行追加・4 行削除。
  - `tools/liftdiff/results/ld131/insn_va_map.py` (+9/-1): `return;` の後の注記無し文を畳まない。`jmp` 注記で kind `call` の行を `jmp` にする。
  - `tools/liftdiff/results/ld131/insn_map_6fn.tsv` (2 行): `1801c682c 1801c699d` の kind `call`→`jmp`、`1801ce3f0 1801ce3f6` の `call 1801ab1d0` を削除。
  - `tools/liftdiff/tests/test_insn_va_map.py` (+10)。
  - `tools/ott/lift`・`tools/shared/env.sh` は差分なし。
- **差分は 0 ではない。** よって下記の再測定が要る。TSV の 2 行は `ld131_lift.sh` で再生成していない (素材 `plugins-ott` / `analysis-ott-binaries` が無い)。再測定 (生成 TSV と現 TSV の `cmp`・`ott_lifted.c` の sha256) は未実施。
- 起動・GUI に関わらないため、製品 KPI (FLEngine 起動 dispatch 数・通過 unit 数・最初のウィンドウ) は書かない。

## 7. round 1 の修正 (レビュー指摘への対応)

- 指摘 (ret の kind・tail jmp の kind): `ret` 行に `call 1801ab1d0` が付いていた原因は、`parse()` が `return;` の後の注記無し文を直前の命令に畳んでいたこと。`return;` を含む行で収集を止めるよう修正した。`1801c682c` の `jmp` は `f_X(); return;` の形で kind `call` になっていたため、注記が `jmp` なら kind `jmp` にした。
- 単体テストを 2 件追加 (`test_ret_does_not_absorb_following_unannotated_stmt`・`test_tail_jmp_as_call_stmt_is_jmp`)。計 8 件 OK。
- TSV の 2 行は手で直した (修正後の規則と同じ値)。再生成での照合は未実施 (§6)。
- 確認: `awk -F'\t' 'NR>1 && $4=="call" && $3 !~ /^call/'` → 0 行。TSV は 941 行・28 関数で、件数は変わらない。
