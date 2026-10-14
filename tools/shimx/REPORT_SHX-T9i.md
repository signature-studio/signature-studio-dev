# tools/shimx REPORT 付録 — SHX-T9i (#2491) 呼出し元 site・戻り値の実測と survey 回帰確認

> 本体: `tools/shimx/REPORT_SHX-T9.md` §3.3.5・§3.3.6 の全文。本体が REPORT 250 行上限を超えるため分割移動 (内容は削除せず、Git 履歴に残す)。数値の出典は `tools/shimx/evidence_2491/`。

## 3.3.5 呼出し元 site と戻り値の実測 (SHX-T9i #2491)

- 測定 commit: `5d261806` (wrapper に呼出し元 site を追加)。clean rebuild `build.sh --trace --soft --fix` (`[sxlink] OK`、`m11_sx_trace_soft_fix.cjs.wasm` sha256 `11c74a05…`)。probe は unit 1〜22 を順に実行した後に unit 23 を 1 回 (`probe_unit23.mjs`)。load 0.30 (4 CPU)。出力は `evidence_2491/probe_u23_shimx_site.txt`。
- 呼出し元の表し方: wasm の C 側から機械語 PC は取れない。`gen_link.py` が `GetModuleHandleW`・`GetProcAddress` の call site ごとに「lifted IR の enclosing 関数名 + IR 行番号」を site ID (i32) として wrapper に渡す。site 表は `trace_wrap.c` の `sxt_site_str` (24 件)。`boot_trace.ll` の同じ行番号 (`sed -n 160493p`) に該当 call がある。wasm バイトオフセットとの対応は未取得。

| unit | 呼出し | 呼出し元 site | 引数 (name) | 戻り値 |
|---|---|---|---|---|
| 2 | GetModuleHandleW ×4 | `function_4099c0@L110523`・`function_418e10@L126428`・`@L126432`・`@L126436` | kernel32.dll | 0x112ee000 |
| 2 | GetProcAddress ×4 | `function_4099c0@L110524`・`function_418e10@L126429`・`@L126433`・`@L126437` | 0x9b02 (下記の訂正参照)・GetThreadPreferredUILanguages・SetThreadPreferredUILanguages・GetThreadUILanguage | 0x0・0x7f00000a・0x7f00000b・0x7f00000c |
| 18 | GetModuleHandleW | `function_44b7e0@L154039` | NTDLL.DLL | 0x11441000 |
| 18 | GetProcAddress | `function_4235f0@L131978` | 0x13fdc (先頭 0 で name 空) | 0x0 |
| 18 | GetModuleHandleW | `function_4104f0@L116255` | kernel32.dll | 0x112ee000 |
| 18 | GetProcAddress | `function_4104f0@L116256` | 0x10602 (GetLogicalProcessorInformation) | 0x25a |
| 22 | GetModuleHandleW | **`function_457c70@L160493`** | oleaut32.dll | 0x11443000 |
| 22 | GetProcAddress | なし | — | — |
| 23 | shimx 呼出し 0 件 | — | — | ret=2 (icall miss `0x4476d0`・`0x457860`) |

- **GetModuleHandleW("oleaut32.dll") は unit 22 に 1 回だけ、`function_457c70` から呼ばれる** (本体 §3.3.1 の引数一致による推定が確定)。戻り値 0x11443000 は非 NULL。
- **GetProcAddress は unit 1〜23 で 0 回。`VarBstrFromBool` の呼出しは無い**。`function_457c40` 内の GetProcAddress (`@L160478`) は 1 回も記録されない。
- IR 上 `function_457c70` は `function_457c40` を 22 回呼ぶ。`function_457c40` が GetProcAddress に到達するのは `*(arg1+40) != 0` の分岐のみなので、22 回すべてこの分岐を取らず fallback (arg3) を返したと推論する (`+40` の実行時値は未測定)。
- `0x11F10E0` (VarBstrFromBool の slot) への store は `function_457c70` の L160537 (22 番目の呼出し、値は fallback `0x457860`)。`PRE|unit 22 slot 0x457860` (unit 22 の後で slot が 0 から変わる) と一致。**slot は GetProcAddress の結果ではなく fallback で埋まる**。name は素材イメージ offset 360446 の `VarBstrFromBool\0` で確認。
- 原因の推定 (未検証): `function_457c70` の alloca `%stack_var_-56` には store が一度も無く、`GetModuleHandleW` の戻り値 `%0` は未使用。HMODULE が `arg1+40` に入らないため GetProcAddress 経路に入らない。lift で HMODULE の store が脱落した疑いがあり、既知類型では D3 (メモリ宛 store 脱落) が近い。元 x86 との照合は未実施 (起票先: #1985)。
- **本体 §2.1 の訂正 (kernel32 `#39682`)**: 序数ではない。第 2 引数 0x9b02 は LVA の文字列 `GetLogicalProcessorInformation` を指す (素材イメージで確認)。shimx は Win32 規則 (< 0x10000 は序数) で序数扱いし miss にする。同じ API は unit 18 では 0x10602 で解決される (r=0x25a)。LVA が 0x10000 未満に載ることが原因で、R1 (敷設 ≥0x10000) と同根。
- ntdll (unit 18) の GetProcAddress は引数 0x13fdc の先頭が 0 で name 空。引数の意味は未追跡。
- 整合: RET 行数はカウンタと一致 (GetProcAddress 6 行 = 計数 6、GetModuleHandleW 7 行 = 計数 7)。unit 23 の wrapper 呼出しは 0 件。wrapper 追加の前後で unit 23 の結果 (ret=2・icall miss 2 件) は同じ (`evidence_2491/probe_u23_shimx_before_site.txt`)。

## 3.3.6 survey 全 942 unit の回帰確認 (SHX-T9i #2491)

- 測定 commit: `5d261806` (上と同じ build)。`SHIMX_TRACE=1 node survey_trace.mjs m11_sx_trace_soft_fix.cjs --out DIR`、load 0.28–0.43 (4 CPU)、所要 5 分 12 秒 (UTC 14:52:08 → 14:57:20 の date 差分)。
- 結果: ok 789 / oob 95 / closure_outside 47 / halt0 9 / clobber 1 / noproc 1 / reboots 1 (本体 §3.1 と一致)。
- 独立検算: `evidence_2491/check_survey_vs_1255.py` で 942 unit の kind と shim_calls を `evidence_1255/shimx_trace_soft_fix.survey.json` と unit 番号で突き合わせ → kind 差分 0・shim_calls 差分 0。ネガティブコントロール (unit 1 の kind を 1 件書き換えた複製) では kind 差分 1 件で FAIL することを確認。
- 再現: `bash tools/shimx/evidence_2491/repro.sh` (clean rebuild → probe → diff。HEAD `5d261806` 系で `probe: SAME`)。
- 測定後のコード差分: `git diff 5d261806 HEAD -- tools/m11/shimx_link tools/shimx/src` は出力 0 行 (本節の追記は REPORT と `evidence_2491/` のみ)。

## 3.3.7 main 取り込み後の再測定 (PR #2550 の競合解消)

- 測定 commit: `c068783c` (`origin/main` `3ef67b40` を merge した commit。コードを変えた最後の commit)。初回測定 `5d261806` からのコード差分: `git diff 5d261806 c068783c -- tools/m11/shimx_link tools/shimx/src` は `probe_lasterr_1985.mjs` の 1 ファイル 42 行追加のみ (main #1985 の probe。build.sh・gen_link.py・trace_rt.c は無変更で、build の入力に含まれない)。
- clean rebuild: `bash tools/shimx/evidence_2491/repro.sh` の build → `[sxlink] OK trace_soft_fix: signature mismatch=1 undefined symbol=0 duplicate=0`。`m11_sx_trace_soft_fix.cjs.wasm` の sha256 先頭 `11c74a05…` (初回と同一)。`repro.sh` 全体 (build と probe) の所要 11 秒。
- probe unit 1〜23: `probe: SAME` (保存出力 `evidence_2491/probe_u23_shimx_site.txt` と diff 0 行)。
- survey 942 unit: ok 789 / oob 95 / closure_outside 47 / halt0 9 / clobber 1 / noproc 1 / reboots 1 (初回と同一)。所要 2 分 25 秒 (開始時 load 0.64、4 CPU)。`check_survey_vs_1255.py` で `evidence_1255` と kind 差分 0・shim_calls 差分 0。
- 素材: `work-m11`・`work-liftdiff` を `$ARTIFACTS_DIR` から展開 (実在確認済み)。EMSDK は [EMSDK] (`docs/REFERENCES.md`) の環境を使用。
