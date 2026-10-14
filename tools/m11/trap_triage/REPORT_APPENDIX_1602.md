# #1602 付録: C 版内 stderr 計測 (REPORT_714 §13 の全文)

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
