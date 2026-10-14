# #1602 付録: C 版内 stderr 計測 (REPORT_714 §13 の全文) と r2〜r4 の再試行 (§14〜§16)

自動生成ではない。`REPORT_714.md` §13 の全文を 250 行上限のため分割移動した (2026-10-14, 差し戻し対応 run)。
本節の測定 commit は `4c3f7458` (origin/main)。

## 13. C 版内 stderr 計測 (#1602, 2026-10-14, n=1)

測定 commit `4c3f7458` (origin/main, 本 PR の作業ベース)。素材 fl-win64・toolchain-retdec・toolchain-emsdk・work-m11・work-liftdiff を展開。`FL_WIN64_DIR=$RUNNER_TEMP/ws1602`、`RETDEC_ROOT=$RUNNER_TEMP/ws1602/retdec`。

| 工程 | 結果 | 所要 |
|---|---|---|
| `m11_gen_ir2.sh` | rc=0 (`boot_final.ll` 490733 行) | 50.5 秒 |
| `m11_build.sh` (計測 OFF) | rc=0 | 16.6 秒 |
| `m11_survey.mjs` (計測 OFF) | rc=0 / ok 870 / trap 24 / noproc 1 / miss 47 | 16.6 秒 |
| `check_682.py` (計測 OFF) | 2/5 (304=trap 555=trap 923=trap 291=ok 296=ok) rc=1 | - |

### HEAD 再測定 (`50ad69da`・既定値・計測 OFF)

測定 commit `4c3f7458` → HEAD `50ad69da` のコード差分は `tools/m11/m11_build.sh` (+5/-2 行) と `tools/m11/trap_triage/probe_entry.sh` (1 行) だけ。既定値 (`M11_TRACE_ISOLATE=1`・`M11_KEEP_BOOT_O` 未設定) で同じ survey 結果になることを、HEAD で確認した。素材は上と同じ 5 点。

| 工程 | 結果 | 所要 |
|---|---|---|
| `m11_gen_ir2.sh` (HEAD) | rc=0 (`boot_final.ll` 490733 行、`F1=902 F1v=4 F2=30 F3a=3 F3b=5 F3c=36 errors=0`) | 50.8 秒 |
| `m11_build.sh` (HEAD、既定値) | rc=0 (`wasm-ld signature mismatch: 0, undefined symbol: 0`) | 24.6 秒 |
| `m11_survey.mjs` (HEAD、既定値) | rc=0 / ok 870 / trap 24 / noproc 1 / miss 47 | 16.4 秒 |

load average は測定中 0.73 前後。`check_682.py` は HEAD では未実行。

**計測の試行 (不採用・patch のみ残す)**: 計測を `M11_INSTR_1602=1` で入れた build は、survey が ok 872 / trap 22、check_682 が 4/5 (304=ok 555=ok 923=trap) になった。`[1602]` 行は 0 件 (範囲外の読みは起きていない)。計測 OFF に戻すと 870 / 24 に戻る。空関数 (中身なし) の対照でも 870 / 24 だった。

### 計測 patch の適用範囲 (2026-10-14 コード確認)

`trap_triage/ov_1602_probe.patch` は次の 2 箇所に計測を入れる。**FIX=0 (既定) では計測の読取りはどちらもコンパイルされない。**

- `function_535bf2` の計測本体 (`__builtin_wasm_memory_size` を含む読取り) は `#if M11_FIX_535BF2` (`m11_ov.c` の 542〜560 行) の内側にある。計測を効かせるには `M11_FIX_535BF2=1` が要る。
- `function_410b10` 側の hook `m11_1602_410b10` は本体が `(void)obj;` の空関数で、読取りを含まない。`M11_INSTR_1602=1` のとき呼出しだけが入る。

したがって、FIX=0 の INSTR=1 build で実際に変わるのは、stamp (`ov_instr_1602.stamp`) による `ov.o` の再ビルドと空関数呼出しだけである。

### 解釈 (差し戻し対応で改訂)

- 旧版の「計測コードの中身 (`__builtin_wasm_memory_size` を含む読取り) が判定を変える」は、patch の適用範囲と合わないため**撤回する**。機構は未特定。
- 計測 ON (872/22) と空関数対照 (870/24) の差は、FIX=0 でコンパイルされる内容がほぼ同じであるため、計測内容では説明できない。ビルドまたは実行の揺らぎ (n=1) の可能性がある。**未確認**。
- 揺らぎの確認 (同一 build の survey の反復) は本 run では未実施。`toolchain-retdec` と `work-m11` が `$ARTIFACTS_DIR` に無く、`m11_gen_ir2.sh` を回せないため、反復も FIX=1 での再測定もできなかった。
- `M11_FIX_535BF2=1` 側の 304・555 計測は、この ON 測定では効いていない (FIX 既定 0 のため `function_535bf2` は lift 版)。未検証。

### 判定 (本 run)

受入 1・2 は**未達のまま**。受入 3 は計測 OFF で確認 (870 / 24、check_682 2/5)。実値採取は、計測の読取りが実際にコンパイルされ、揺らぎが確認された版で行う必要がある (下表)。

### 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 計測 ON で 872/22 になる由来が未特定 (揺らぎか、ビルド差か)。同一 build の survey 反復 (n≥3) で確認が要る | 受入 1・2 が未達 | #1426 (継続) |
| 実際に読取りをコンパイルする計測 (`M11_FIX_535BF2=1` + `M11_INSTR_1602=1`、または 410b10 側に読取りを入れた版) での 304・555・923 の実値採取 | 受入 1・2 が未達 | #1426 (継続) |
| `M11_FIX_535BF2=1` での 304・555 計測は未検証 | 受入 1 が未達 | #1426 (継続) |
| 採取手段の候補 (未着手): (a) `m11_ov.c` の C 版 (`M11_FIX_535BF2=1`) の内部で `tbl`・`cnt` を stderr に出す (C 側は wasm local を直接読める)、(b) trap 直前の `i32.load` の address を `m11_survey.mjs` の catch で wasm memory から逆算する | 同上 | #1426 の範囲 (次 run) |

「#1426 (継続)」は、#1602 の残作業を #1426 (M11-N91) が保持している既存の起票先である。§12 の実値採取の計画もこの起票先に登録されている。

## 14. 再試行 (#1602 r2, 2026-10-14, n=1)

測定 commit `0d9b5385` (origin/main、本 PR の作業ベース。コード変更なし)。素材 fl-win64・toolchain-retdec ([RETDEC])・toolchain-emsdk・work-m11・work-liftdiff を展開。`FL_WIN64_DIR=$RUNNER_TEMP/ws1602/fl-win64`。load average は開始時 1.03。

| 工程 | 結果 | 所要 |
|---|---|---|
| `m11_gen_ir2.sh` | rc=0 (`boot_final.ll` 490733 行、F1=902 errors=0) | 46.9 秒 |
| `m11_build.sh` (既定) | rc=0 | 23.3 秒 |
| `m11_survey.mjs` (既定) | rc=0 / ok 870 / trap 24 / noproc 1 / miss 47 | 15.2 秒 |
| `check_682.py` (既定、`M11_SURVEY_UNITS` の JSON を渡す) | 2/5 (304=trap 555=trap 923=trap 291=ok 296=ok) | - |

計測 hook (`M11_FIX_535BF2=1` で `function_535bf2` 内の範囲チェック付き読取り、`function_410b10` の hook) を入れた版の結果は次のとおり。

| build | survey | check_682 | `[1602]` 行 | 備考 |
|---|---|---|---|---|
| FIX=1, INSTR=0 | ok 870 / trap 24 | 2/5 | - | 対照 |
| FIX=0, INSTR=0 | ok 870 / trap 24 | 2/5 | - | 既定 |
| FIX=1, INSTR=1, 410b10 hook = 空関数 | ok 872 / trap 22 | 4/5 (304=ok 555=ok 923=trap) | 0 | 同一 build を 3 回 survey し、3 回とも同じ |
| FIX=1, INSTR=1, 410b10 hook = 範囲チェック付き読取り | ok 870 / trap 24 | 2/5 | 0 | 同一 build を 2 回取り直し、2 回とも同じ |

- **判定を変えているのは読取り値ではない**。どちらの版も `[1602]` 行は 0 件で、範囲外の読みは起きていない。空関数版と読取り版の差は hook の本体だけで、それがコンパイル後のコードを変えて 304・555 の判定が変わったと見るのが妥当 (機構は未確認)。
- **よって受入 1・2 の実値はこの方式でも採れていない**。範囲内なので値は読めたはずだが、ログに出す条件 (範囲外のときだけ出す) に一度も当たらず、実値は出力されない。実値を見るには「範囲内でも常に出す」版が要る。
- trap 位置 (`M11_SURVEY_STACK=304,923,555`、既定 build、wasm 関数名は `m11_wasmnames.py`): 304 と 555 の先頭フレームは `function_535bf2` (wasm 3372)、923 は `function_410b10` (wasm 14900)。OOB がこの 2 関数で起きることを確認した。
- 計測 patch: `trap_triage/ov_1602_probe_r2.patch` (`git apply --check` は本ツリーで通る)。`m11_build.sh` と `m11_ov.c` の 2 ファイル。本体には入れていない。前の `ov_1602_probe.patch` は現行 main に当たらないため、そのまま残す (旧版として扱う)。

### 判定 (r2)

受入 1・2 は**未達のまま**。受入 3 (回帰 0) は既定 build で ok 870 / trap 24 / noproc 1 / miss 47、check_682 2/5 を確認 (前 run と一致)。

### 未解決 (r2)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 範囲内でも常に値を出す計測版での 304・555・923 の実値採取 (現行は範囲外のときだけ出すため値が出ない) | 受入 1・2 が未達 | #1426 (継続) |
| 410b10 の hook 本体の違い (空関数 / 読取り) で 304・555 の判定が 872/22 ↔ 870/24 と変わる機構が未特定 | 計測の影響を判定に使えない | #1426 (継続) |

## 15. 範囲内でも常に出す計測版 (#1602 r3, 2026-10-14, n=1)

測定 commit `27a324e0` (origin/main、コード変更なし)。素材 fl-win64・toolchain-retdec・toolchain-emsdk・work-m11 を展開。`FL_WIN64_DIR=$RUNNER_TEMP/ws1602/fl-win64` (`extracted/` の親を指定)。

| 工程 | 結果 | 所要 |
|---|---|---|
| `m11_gen_ir2.sh` | rc=0 (`boot_final.ll` 490733 行、F1=902 errors=0) | 33.0 秒 |
| `m11_build.sh` (既定) | rc=0 (`undefined symbol: 0`) | 18.7 秒 |
| `m11_survey.mjs` (既定) | rc=0 / ok 870 / noproc 1 / miss 47 | 8.7 秒 |

計測版 (`ov_1602_probe_r3.patch`: `function_535bf2` と `function_410b10` の入口で、範囲内でも必ず 1 行出す。`#define M11_PROBE_1602 1` を入れたとき) の結果:

| build | survey | `[1602]` 行 | 備考 |
|---|---|---|---|
| 既定 | ok 870 / trap 24 / miss 47 | - | 対照 |
| `M11_PROBE_1602=1` (範囲内でも常に出す) | ok 837 / trap 43 / miss 61 | 0 | `wasm-ld` が `undefined symbol: 1` を出す (原因未確認) |

- 計測版は判定を大きく変える (870 → 837、trap 24 → 43)。`[1602]` 行が 0 件なので、ログ出力そのものは実行されていない、もしくは出力が survey の捕捉から漏れている。どちらかは未確認。
- したがって、この計測版では受入 1・2 の値は採れていない。受入 3 (計測の影響なし) も満たさない。
- r2 の patch (`ov_1602_probe_r2.patch`) は現行 main に当たらない (`m11_build.sh` の CF 行が変わっている)。r3 の patch は `m11_ov.c` 単体で、`27a324e0` に対して作成。
- 候補 (b) (trap address の逆算) は未着手。survey の catch で受け取る RuntimeError に faulting address が含まれるかは未確認。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 計測版で判定が 870 → 837 に動く機構 (`undefined symbol: 1` と `[1602]` 0 件の原因を含む) | 受入 1・2 が未達 | #1426 (継続) |
| 候補 (b) trap address の逆算の実現性 (RuntimeError の address の有無) | 受入 1・2 が未達 | #1426 (継続) |

## 16. V8 inspector による trap 時点の local 採取 (#1602 r4, 2026-10-14, n=2)

結論: build を変えずに、node の inspector (`Debugger.setPauseOnExceptions` all) で RuntimeError が投げられた瞬間の wasm local を読めた。判定は不変 (unit 別ラベル JSON が通常 survey とバイト一致)。304・555 は `function_535bf2` の `obj = 0`、923 は `function_410b10` の `*(obj) = 0` (vptr が NULL) が OOB の直接原因。

測定 commit `2ae50140` (`inspect_trap.mjs` を追加した commit。コードを変えた最後の commit)。上の測定は、その 1 つ後の `9e5ef3af` (同ファイルのヘッダのコメント 5 行だけを追加) で実行した。`git diff 2ae50140 HEAD -- tools ':!*.md'` の出力は `inspect_trap.mjs` の `+//` コメント 5 行のみ (`M11_INSPECT_PEEK`・`DUMP`・`FRAMES` の説明と 1 行の要約)。コード差分は 0。作業ベース `14150b46` (origin/main)。素材 fl-win64・toolchain-retdec・toolchain-emsdk・work-m11・work-liftdiff を展開。`FL_WIN64_DIR=$RUNNER_TEMP/ws1602/fl-win64`。load average は開始時 0.17。node v22.23.3。

| 工程 | 結果 | 所要 |
|---|---|---|
| `m11_gen_ir2.sh` | rc=0 (`boot_final.ll` 490733 行、F1=902 errors=0) | 42.6 秒 |
| `m11_build.sh` (既定) | rc=0 (`wasm-ld signature mismatch: 0, undefined symbol: 0`) | 21.5 秒 |
| `m11_survey.mjs` (既定・inspector なし) | rc=0 / ok 870 / trap 24 / noproc 1 / miss 47 | 13.4 秒 |
| `check_682.py` (既定) | 2/5 (304=trap 555=trap 923=trap 291=ok 296=ok) rc=1 | - |
| `m11_survey.mjs` + `inspect_trap.mjs` (1 回目) | rc=0 / ok 870 / trap 24 / noproc 1 / miss 47 | 21.8 秒 |
| 同 (2 回目) | 同上 | 21.8 秒 |
| `check_682.py` (inspector 版の unit JSON) | 2/5 (同じ) | - |

- 判定不変: inspector 版 2 回の `M11_SURVEY_UNITS` JSON は、inspector なしの JSON と `cmp` でバイト一致 (942 unit 全て同じラベル)。追加の試走 4 回 (測定 commit の前) も同じ。2 回の記録 JSONL も `cmp` で一致。
- 手段: `trap_triage/inspect_trap.mjs` を `node --wasm-enforce-bounds-checks --import ... tools/m11/m11_survey.mjs` で preload する (build・C 版・wasm は無変更)。`Debugger.paused` で top frame の `local` scope を `Runtime.getProperties` で読み、すぐ resume する。
- `--wasm-enforce-bounds-checks` が要る。既定 (trap handler による OOB 検出) では OOB 時の frame に local の side table が無く、`local` scope が空で返る (最小の wasm module で、フラグ無し = 空・有り = `$var0`/`$var1` の値、を確認)。フラグは範囲チェックを明示コードにするだけで、OOB の判定は同じ。
- 事象と unit の対応: 非 halt0 の RuntimeError 17 件が、unit 別ラベルの trap のうち halt0 でない 17 unit と順序で 1 対 1 に対応する。304・555・923 は、事象の (wasm 関数 index, offset) が `M11_SURVEY_STACK` の先頭フレーム (3372:0x1a3376, 3372:0x1a3376, 14900:0x354f51) と一致した。

### 304・555 (`function_535bf2`、wasm 3372、OOB 命令 0x1a3376)

線形メモリは 1655963648 B (0x62b40000)。読み式は `tbl = *(*(obj+8)+8)`、`cnt = *(obj+0x10)` を +1 した値、アドレス = `(tbl + cnt*24) mod 2^32` (REPORT §6)。

| 項目 | 304 | 555 |
|---|---|---|
| `obj` (local 0, i64) | 0x0 (NULL) | 0x0 (NULL) |
| `*(obj+8)` (addr 0x8) | 0x6c006c0064002e | 同左 |
| `*(obj+8)+8` を i32 に wrap した addr | 0x640036 (線形メモリ内) | 同左 |
| `tbl` = その位置の i64 | 0xb00474ffd03c8352 (メモリ範囲外の値) | 同左 |
| `obj+0x10` (addr 0x10) の `cnt` (+1 後) | 0x3400360078005f (範囲外の値) | 0x34003600780060 (同) |
| OOB アドレス `(tbl + cnt*24) mod 2^32` | 0xdb7c8c3a | 0xdb7c8c52 |
| 範囲判定 | addr+4 > 0x62b40000 で OOB | 同左 |

- `obj = 0` のため、`obj+8`・`obj+0x10` は guest メモリの先頭 (addr 8, 16) を読む。trap 時点の addr 0〜0x3f は、addr 8 = UTF-16LE の ".dll"、addr 0x10 = "_x64.dll" (304) / "`x64.dll" (555) だった。`cnt` の +1 は addr 0x10 の先頭 wide char を書き換える (0x5f → 0x60 が 304 → 555 の差)。
- 呼出し鎖 (top から): `function_535bf2` ← `function_535c11` ← `function_4fad10` ← `function_4fb910` ← 304 は `function_883140`、555 は `function_bf2500`。`function_535c11` の local0 は 304 が 280842688、555 が 280847200 で、どちらも非 0。
- `obj = 0` は IR と整合する: `boot_final.ll` の `function_535c11` は `call i64 @function_535bf2()` を引数なしで呼ぶ (`m11_ov.c` 537 行のコメント・REPORT_1275 の「RetDec が `jl 0x535bf2` を rcx=0 の call にした」と同じ)。本 run は IR 側の再検証はしていない (実測は obj = 0 まで)。

### 923 (`function_410b10`、wasm 14900、OOB 命令 0x354f51)

読み式は `*( *(obj) - 0x80 )` (REPORT §6)。

| 項目 | 値 |
|---|---|
| `obj` (local 0, i64。関数入口の引数と同じ。local は書換わらない) | 0x10bd3960 (線形メモリ内) |
| `*(obj)` (vptr 相当) | 0x0 |
| `*(obj) - 0x80` の i32 wrap | 0xffffff80 (範囲外 → OOB) |
| 参考: `obj - 0x80` | 0x10bd38e0 (範囲内)。OOB の原因は `obj-0x80` ではなく `*(obj)-0x80` |
| `obj` 先頭 64 B | 全て 0 (trap 時点) |

- 呼出し鎖: `function_410b10` ← `function_410730` (local0 = 同じ obj 0x10bd3960) ← `function_4fb910` (local0 = 0xf6b900, local1 = 0x1fa8d8) ← `function_136c660` ← `m11_tr_function_136c660`。
- 同じ addr 0x10bd3960 は 304・555 の `function_4fad10` の local0 (280836448) でもある。そのときの先頭 8 B は 0x0f3120 (非 0) で、923 の時点では 0。同一 addr の別時点の状態であり、同一オブジェクトかは未確認。

### 判定 (r4)

- 受入 1 (304・555 の `obj`・`*(obj+8)`・`*(obj+8)+8`・`obj+0x10` の実測、`tbl`/`cnt` の範囲判定): **達成** (上表)。
- 受入 2 (923 の `obj` の実測、範囲外の判定): **達成**。`obj` は範囲内、`*(obj)-0x80` が範囲外。
- 受入 3 (入口 dump 以外の採取手段で、判定が変わらない): **達成**。手段は issue 本文の候補 (a)・(b) ではなく (c) V8 inspector。unit JSON はバイト一致。
- 受入 4 (回帰 0、既定 OFF の survey が ok 870 / trap 24 / noproc 1 / miss 47): **達成** (build 側のコード変更は 0 件)。

### 未解決 (r4)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 304・555: `function_535c11` → `function_535bf2` の引数なし call (obj = 0) の修復 (`M11_FIX_535BF2` の C 版は REPORT §3) | OOB の除去 | #714 (継続) |
| 923: `obj` (0x10bd3960) の vptr が 0 になる由来 (構築が走らないのか、解放・消去後か)。`inspect_trap.mjs` で `function_4fb910` 以降の生成元を追える | OOB の除去 | #714 (継続) |
