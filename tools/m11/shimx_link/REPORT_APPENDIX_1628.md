# M11 × shimx リンク 付録: midiOutShortMsg の HANDLE 幅 (#1628 SHX-T25)

- 本体の要約は `tools/m11/shimx_link/REPORT.md` §12。測定値はこの付録が正本。
- 既知類型との関係: 該当なし。D11 (絶対 VA の i64 定数の切り捨て) と D17 (8B store の 4B 縮小) は wasm32 の幅差を含むが、機構は別。本件は外部関数 (shimx) との宣言の型幅 (IR の `i64` と wasm32 HANDLE の `i32`) の不一致で、切り詰めても HMIDIOUT の値は変わらない (wasm32 のハンドルは i32 に収まる)。

## 12. midiOutShortMsg の HANDLE 幅 (#1628 SHX-T25): IR 側の正規化

測定 commit `e0e35f9a` (修正 pass の測定時点)。本 PR の HEAD は、測定時と `sx_handle_norm.py`・`build.sh`・`*.c`・`*.sh` が同一 (差分 0 行・§12.4)。

- 原因: IR (`boot_final3.ll`) は `declare i32 @midiOutShortMsg(i64, i32)` と `i64 %hmo` で呼ぶ。shimx 定義 (`tools/shimx/src/midi_conv.c:163`) は wasm32 の HANDLE = i32。`signature mismatch` は trace では `trace_wrap.o` (gen_link.py が IR の型を写す)、plain では IR の import 型そのものから出る。
- 方式: 受入条件 1 の後者 (IR 側の正規化)。plain と trace の両方を直せ、gen_link.py が正規化後の IR から trace_wrap.c を作るため。`trunc i64→i32` は値を変えない (HMIDIOUT は wasm32 のハンドルで i32 に収まる)。
- 実装: `sx_handle_norm.py` (宣言 1 件・呼出し 1 件を変換。想定外の参照が残れば fail-closed)。`build.sh` の 2c (`--fix` の後・gen_link の前、全 variant)。

### 12.1 変換結果 (クリーン build)

| variant (gui=soft) | 修正前 (`26f90ada`) | 修正後 (`e0e35f9a`) |
|---|---|---|
| plain / `--fix` / `--fix --ws` / `--fix --midi` | signature mismatch 1 (×4) | 0 (×4) |
| trace / `--trace --fix` | 1 / 未測定 | 0 / 0 |

undefined / duplicate は全件 0。修正前の値は旧 build.sh を一時コピーして同じ IR で実行した (ネガティブコントロール)。

### 12.2 実 boot と出典 (修正前の値との IR 同一性)

- 修正後 trace `--fix` (`e0e35f9a`): `boot_stage 1 / init_count 18 / units_run 17/942 / icall_ok 24 / icall_miss 1 / threw "memory access out of bounds" / total_calls 97 / distinct 28 / dropped 0`。`midiOutShortMsg` は boot 中 0 件。
- 修正前と並べる値の出典は次のとおり。どれも**本測定の IR と同一ではない**:
  - `units_run 17 / threw OOB / total_calls 97 / distinct_called 28 / dropped 0`: `tools/m11/REPORT_SHX-T27.md` §A-1-2 (main `e051402a`・`build.sh --trace --soft` は `signature mismatch=1`)。同節は **stale な work-m11 IR** での値 (T27 §1・§4-F)。
  - `icall_ok 24`: `tools/m11/REPORT_SHX-T26.md` §2 の表 (L21。D19 ガード版の build・`signature mismatch=1`)。**ガードを加えた別 IR** の値。同じ stale IR の snapshot run は `icall_ok 19 / total_calls 94` (T26 §2 の HEAD 再実行行)。
- 結論: 修正前後で boot 到達点が同じかは、**同一 IR で修正前を測っていないため確認できていない**。本 run は emcc (`[EMSDK]`) と `work-m11` が無く、IR を作り直せなかった。

### 12.3 e2e (測定 commit `e0e35f9a`)

- `ws_e2e.mjs` (`--fix --ws`): PASS 19 / FAIL 0 (0.40 s)。
- `midi_e2e.mjs` (`--fix --midi`): ALL PASS (0.29 s)。
- `m11_judge.py --require-stage 4 --min-survey-ok 800`: rc 0 (`survey_ok` 812。入力は M11 本体の出力で、shimx_link は入力にならない)。
- 942 unit survey (`survey_trace.mjs`) と plain の boot 到達点は未実施 (未解決: SHX-T32 #2877)。

### 12.4 fail-closed 化の扱い (本 PR から外した)

- 経緯: `763a599d` で `sx_handle_norm.py` に fail-closed を入れた (参照数の境界一致、素の declare 無しで失敗、i32 宣言の残 i64 呼出しで失敗)。この版の build 6 variant と e2e は測定していない (emcc・work-m11 が本 run に無い)。WORKFLOW §6 の「差分の分だけ再測定」を満たせないため、`sx_handle_norm.py` を測定時の版 (`e0e35f9a`) に戻した。fail-closed 化は未解決 (§12.5 → SHX-T32)。
- 実行経路の差分 (測定 commit から HEAD まで): `git diff e0e35f9a HEAD -- tools/m11/shimx_link/sx_handle_norm.py tools/m11/shimx_link/build.sh tools/m11/shimx_link/*.c tools/m11/shimx_link/*.sh` の出力は 0 行。`build.sh` が呼ぶのは `sx_handle_norm.py` のみ (`grep -n sx_handle_norm tools/m11/shimx_link/build.sh`)。
- `test_sx_handle_norm.py` は `763a599d` で追加されたもので、`e0e35f9a` には無い。本 PR では fail-closed のケースを外し、旧版の挙動で通る 4 ケースに縮めた (`cases=4 fail=0`)。
- 旧版 (`e0e35f9a`) の挙動 (合成 IR、2026-10-14 実測。旧版の `sx_handle_norm.py` をそのまま実行。「i64 の呼出し残」は `call`/`invoke` の行で `@midiOutShortMsg(i64` が残った件数):

| 入力 | rc | i64 の呼出し残 | i64 の宣言残 |
|---|---|---|---|
| A 素の `declare` (実 IR と同じ形) | 0 | 0 | 0 |
| B 属性付き `declare dso_local ...` | 0 | 1 | 1 |
| C 宣言無し・参照あり | 0 | 1 | 0 |
| D 宣言 i32・i64 の呼出し残 | 0 | 1 | 0 |
| E 関数ポインタ参照 (`@fp = global ptr @midiOutShortMsg` を追加) | 0 | 0 | 0 |

- B・C・D は旧版では無言で通る (止めるのは `763a599d` の版だけ)。E は呼出しの型を変えないが、`(` を伴わない参照は旧版の数え方の対象外。
- 実 IR については、§12.1 の mismatch 0 が旧版での実測である。B の形なら正規化が効かず mismatch 1 が残るはずなので、測定時の実 IR は B ではない (この推定の確認は SHX-T32)。

### 12.5 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| RetDec の IR 生成が HMIDIOUT を `i64` と推定する根本 | 本 PR は link 時の正規化で対処。IR 生成は未修正 | 新規子 #2839 `[SHX-T31]` (親 #1628) |
| `sx_handle_norm.py` の fail-closed 化 (`763a599d`) の復元と、HEAD での build 6 variant・e2e・942 unit survey・plain の boot 到達点の再測定 (修正前 `26f90ada` との同一 IR 比較を含む) | 本 PR は測定時の版 (fail-closed なし) を出す。属性付き宣言・宣言無し・宣言 i32 の残 i64 呼出しは旧版で無言に通る (§12.4)。HEAD の build・e2e は本 run で未測定 (差分 0 行の証跡のみ) | 新規子 #2877 `[SHX-T32]` (親 #1628)。旧 #2444 へのコメントは受け先を移したため撤回 |
