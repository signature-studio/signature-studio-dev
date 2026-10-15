# REPORT_APPENDIX_4565 — ICALL-105: C++ EH の x64 unwind (`.pdata` 検索・UNWIND_INFO 逆適用) の native 実装

親: #4565。子: #4592 (ICALL-106: `RtlUnwindEx`・`__CxxFrameHandler` 系の dispatch)。

## 1. 結論

- `tools/ott/native/ott_native.c` に `RtlLookupFunctionEntry`・`RtlVirtualUnwind` を実装した。`.pdata` (25063 件) を二分探索し、UNWIND_INFO の codes を逆適用して呼び出し元へ遡る。
- 6 関数 (`1803b3fc0`・`1803b5b60`・`180cbd860`・`18100cf60`・`181011058`・`18102f728`) は、`RaiseException(0xe06d7363)` の時点で `.pdata` を辿れるようになった。ただし単独 harness の境界 (`ott_ms_call` の戻り先) まで遡っても handler が見つからず、fail-fast のままである。
- wasm route は変更しない。`fa_sweep.sh 8 60` は main (`7288cd52b`) 比で件数が 1 件だけ変わった: `0x18100cc50` が `crash_or_timeout` から `wasm_err 8` (比較可能) になった。他 130 行は全行一致。
- 受入条件 (`RtlUnwindEx`・`__CxxFrameHandler` 系の dispatch) は未達。子 #4592 に分離した。

## 2. 環境

- 測定 commit `12ad05e7b` (PR HEAD、main `7288cd52b` を取り込んだ merge。コードを変えた最後の commit)。変更前 = `7288cd52b` (`origin/main` の現行 HEAD を別 worktree で build)。
- 素材: `work-icall`・`work-liftlib` (`$ARTIFACTS_DIR`)・`plugins-freshair` (`FA_DL` で `fetch.sh`: `win: 17 files, factory .epf: 8, mac: 0 files`)・`toolchain-emsdk` ([EMSDK] 6.0.12)。`fl-win64` は本測定の経路に無い。
- `bash tools/icall/fa_route_build.sh`: 5.8 s、`fa_route.cjs` 生成 (`missing` 4 関数は既存の出力)。wasm route は両 commit で同一物を使う。

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

| VA | 変更前 (`7288cd52b`) | 変更後 (`12ad05e7b`) |
|---|---|---|
| `1803b3fc0` | `RaiseException(0xe06d7363) 到達 — fail-fast` (exit 97) | `handler が見つからない (walk=-1)` (exit 97) |
| `1803b5b60` | 同上 | 同上 |
| `180cbd860` | 同上 | 同上 |
| `18100cf60` | 同上 | 同上 |
| `181011058` | 同上 | 同上 |
| `18102f728` | 同上 (`magic=0x1994000`) | 同上 |

変更後の EH walk: 各 VA とも `.pdata` を辿り、戻り先 (ott_ms_call の呼び出し元 = ホスト側) で `.pdata` が無くなって止まる。単独 harness では catch 側に届かない。

### 4.2 `fa_sweep.sh 8 60` (同一条件で各 commit を測定)

| 条件 | wall | 件数 (funcs 131) |
|---|---|---|
| 変更前 (`7288cd52b`) | 69.829 s (load 1.47→1.14) | bit一致 56 / native crash/timeout 65 / wasm のみ err 9 / 値の不一致 1 |
| 変更後 (`12ad05e7b`) | 69.921 s (load 0.85→1.47) | bit一致 56 / native crash/timeout 64 / wasm のみ err 10 / 値の不一致 1 |

行単位の比較 (`sweep_base`・`sweep_head` の 131 行): 差分 1 行のみ。

| VA | 変更前 | 変更後 |
|---|---|---|
| `0x18100cc50` | `crash_or_timeout` (`MISSING IMPORT RtlLookupFunctionEntry — fail-fast`, exit 99) | `n 8, mismatch 8, wasm_err 8` (`RuntimeError: unreachable`) |

`0x18100cc50` は変更前に `RtlLookupFunctionEntry` が未登録で落ちていた。変更後は native が完走し、wasm と比較できる。`bit一致` 件数は 56 で不変。`wasm のみ err` が 9 → 10 に増えたのは、この 1 件が crash から wasm_err に移ったため。

### 4.3 差分 (測定 commit `12ad05e7b` と PR の `tools/ott/native`)

- 変更前 (`7288cd52b`) → 測定 commit (`12ad05e7b`): `git diff 7288cd52b 12ad05e7b -- tools/ott/native` は `build.sh` 1 行 + `ott_native.c` 129 行 (122 insertions / 9 deletions)。
- 測定 commit → PR HEAD: `git diff 12ad05e7b HEAD -- tools/ott/native` は **0 行** (本 REPORT の commit は REPORT のみ)。
- 取り込み済みの main 側差分 (`SetUnhandledExceptionFilter` ICALL-104・`RtlCaptureContext` ICALL-100) は測定 commit に含まれる。両者とも base 側にも入っているため、比較は head と base で同じ IMPL を持つ条件で行った。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `RtlUnwindEx` と `__CxxFrameHandler` 系 (guest の handler 呼び出し) の dispatch | 6 関数は fail-fast のまま。受入条件 1 件・2 件目 (6 関数の成功) は未達 | #4592 (ICALL-106・子) |
| 単独 harness の境界 (`ott_ms_call` の戻り先に `.pdata` が無い) | catch 側が harness の外にあるため、単独実行では EH の成否を確認できない | #4592 (ICALL-106・子) |
| `rbx`・`rsi`・`rdi`・`r12`〜`r15` の unwind 値 | `RaiseException` 時点の値を正しく取れない。handler の引数復元に影響しうる | #4592 (ICALL-106・子) |
