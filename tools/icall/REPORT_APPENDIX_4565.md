# REPORT_APPENDIX_4565 — ICALL-105: C++ EH の x64 unwind (`.pdata` 検索・UNWIND_INFO 逆適用) の native 実装

親: #4565。子: #4592 (ICALL-106: `RtlUnwindEx`・`__CxxFrameHandler` 系の dispatch)。

## 1. 結論

- `tools/ott/native/ott_native.c` に `RtlLookupFunctionEntry`・`RtlVirtualUnwind` を実装した。`.pdata` (25063 件) を二分探索し、UNWIND_INFO の codes を逆適用して呼び出し元へ遡る。
- 6 関数 (`1803b3fc0`・`1803b5b60`・`180cbd860`・`18100cf60`・`181011058`・`18102f728`) は、`RaiseException(0xe06d7363)` の時点で `.pdata` を辿れるようになった。ただし単独 harness の境界 (`ott_ms_call` の戻り先) まで遡っても handler が見つからず、fail-fast のままである。
- wasm route は変更しない。`fa_sweep.sh 8 60` の件数は変更前後で同一 (`bit一致 55 / native crash/timeout 65 / wasm のみ err 9 / 値の不一致 2`)。131 行は全行一致。
- 受入条件 (`RtlUnwindEx`・`__CxxFrameHandler` 系の dispatch) は未達。子 #4592 に分離した。

## 2. 環境

- HEAD `248816185` (origin/main、branch `4565-icall-cxx-eh-unwind`)。素材: `fl-win64`・`plugins-freshair`・`toolchain-emsdk` (`/opt/emsdk`)・`work-icall`・`work-liftlib` を展開。`RetDec` (`/opt/retdec`) は本作業の経路に無い。
- `bash tools/targets/freshair/fetch.sh` (`FA_DL=$RUNNER_TEMP/plugins-freshair`): `win: 17 files, factory .epf: 8, mac: 0 files` (mac は `xar`・pkg 無しで skip)。
- `bash tools/icall/fa_route_build.sh`: 10.1 s、`fa_route.cjs` 生成 (`missing` 4 関数は既存の出力)。

## 3. 実装内容 (`tools/ott/native/ott_native.c`)

| 要素 | 内容 |
|---|---|
| `ott_load` | DataDirectory[3] (Exception = `.pdata`) の RVA と件数 (`/12`) を読む |
| `lookup_fn` | `pc` を RVA にし、`.pdata` を二分探索。`begin <= r < end` の `RtFn` を返す |
| `unwind_codes` | UNWIND_CODE を逆適用 (PUSH_NONVOL・ALLOC_SMALL/LARGE・SET_FPREG・SAVE_NONVOL・SAVE_XMM128 など)。`filt` で `CodeOffset > off` を飛ばす |
| `virt_unwind` | 1 段戻す。CHAININFO は先頭 prolog の codes を続けて適用。EHANDLER/UHANDLER の handler RVA を返す |
| `k_RaiseException` | `code == 0xe06d7363` のとき `__builtin_frame_address` から呼び出し元の UCtx を作り `eh_walk` で handler を探す。見つかっても dispatch は未実装 (fail-fast) |
| `k_RtlLookupFunctionEntry` / `k_RtlVirtualUnwind` | Win64 の API 形で公開 (IAT に登録) |

`build.sh` に `-fno-omit-frame-pointer` を追加 (`__builtin_frame_address` で guest の rbp を取るため)。

**制限**: `rbx`・`rsi`・`rdi`・`r12`〜`r15` は `RaiseException` 呼び出し時点の値を正しく取れない (C 関数の prologue で書き換わりうる)。`RSP`・`RIP`・`RBP` は正しい。`UWOP` の 6 (EPILOG)・7 (SPARE)・10〜15 は未対応 (-1)。

## 4. 実測

### 4.1 6 関数の単独実行 (`fa_cmp.py <va> --n 2`)

変更前 (`origin/main` の `ott_native.c`): 6 関数とも `RaiseException(0xe06d7363) 到達 — fail-fast` (exit 97)。

変更後:

| VA | EH walk (harness 内) | 結果 |
|---|---|---|
| `1803b3fc0` | `18102f7b8` (`fn [102f728,102f7c8)`) → `1803b3fdf` (`fn [3b3fc0,3b3fe0)`) → 戻り先 `7ffff7003f7f` (`.pdata` 無し) | `handler が見つからない (walk=-1)` — fail-fast |
| `1803b5b60` | `18102f7b8` → `180cbd882` → `1803b5b70` → 戻り先 (`.pdata` 無し) | 同上 |
| `180cbd860` | `18102f7b8` → `180cbd882` → 戻り先 | 同上 |
| `18100cf60` | `18102f7b8` → `18100cf7f` → 戻り先 | 同上 |
| `181011058` | `18102f7b8` → `181011077` → 戻り先 | 同上 |
| `18102f728` | `18102f7b8` → 戻り先 | 同上 |

6 関数とも `handler_rva=0` (EH walk の各フレーム)。戻り先 `7ffff7003f7f` は ott_ms_call の呼び出し元 (ホスト側) で、`.pdata` を持たない。従って単独 harness では handler に届かない。

### 4.2 `fa_sweep.sh 8 60` (変更前後、同一 tree)

| 条件 | 所要 | 件数 (funcs 131) |
|---|---|---|
| 変更前 (`origin/main` の `ott_native.c`) | 測定時刻 10:0x (wall 未計測) | bit一致 55 / native crash/timeout 65 / wasm のみ err 9 / 値の不一致 2 |
| 変更後 | real 1m14.120s・user 1m10.060s・sys 4.652s。load average 1.03 → 1.26 | bit一致 55 / native crash/timeout 65 / wasm のみ err 9 / 値の不一致 2 |

行単位の比較 (`sweep_base.jsonl` vs `sweep_new.jsonl`): 131 行中 差分 0。6 関数はいずれも `{"status": "crash_or_timeout"}`。

### 4.3 差分 (測定 commit `248816185` → 作業 commit)

測定 commit (コードを変えた最後の commit): 作業 commit を参照 (本節末尾)。
`git diff 248816185 HEAD -- tools/ott/native` の行数は、commit 後に記録する。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `RtlUnwindEx` と `__CxxFrameHandler` 系 (guest の handler 呼び出し) の dispatch | 6 関数は fail-fast のまま。受入条件 1 件・2 件目 (6 関数の成功) は未達 | #4592 (ICALL-106・子) |
| 単独 harness の境界 (`ott_ms_call` の戻り先に `.pdata` が無い) | catch 側が harness の外にあるため、単独実行では EH の成否を確認できない | #4592 (ICALL-106・子) |
| `rbx`・`rsi`・`rdi`・`r12`〜`r15` の unwind 値 | `RaiseException` 時点の値を正しく取れない。handler の引数復元に影響しうる | #4592 (ICALL-106・子) |
