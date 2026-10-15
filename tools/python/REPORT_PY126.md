# tools/python REPORT: PY-126 general.processRECEvent の 0xd84740 の意味と out の構造 (#3002, 親 #2979)

> 前段: `tools/python/REPORT_PY121.md` (呼出し鎖・書式。#3004 で main 取り込み済み)・`REPORT_PY125.md` (dispatch `0xd843d0` の out の写し方・述語 P)・`REPORT_PY39.md` / `REPORT_PY70.md` (channels 版の書式)。
> 既知類型との関係: 該当なし (lift ではなく PE の直接逆アセンブル。docs/DEFECTS.md の類型は対象外)。

## 結論

- **`0xd84740` の意味を確定**: dispatch `0xd843d0` を sync=1 で呼ぶ薄いラッパー (call 前の 18 命令は rbx 退避・rsp 調整・引数格納・callback の lea・sync=1 の設定)。callback `0xd846e0` が述語 P を真と判定したときだけ `0x1046a30(eventId, value, flags)` の戻り値を結果とする。
- **out の構造を確定**: `out[0]` (+0x00) = status (int64。0 = 実行済み、-2 = 未実行の sentinel。callback が書く値はこの 2 つだけ)。`out[+0x08]` = 結果 (int64。`0x1046a30` の int32 戻り値を `movsxd`)。`out[+0x10]` = `0x4133f0(job+0x50)` (未読。processRECEvent は読まない)。
- **Python 側の写像を確定** (`0xd69f00`): status (out[0] の 64 bit 全体) ≠ 0 なら `mov ecx, eax` で下位 32 bit を `0xd82c20(ecx)` に渡してエラー、0 なら `out[+0x08]` の下位 dword を int 変換 (`0x15e4280`) して返す。
- **未確定** (受入条件 2〜4 の前提): `0x1046a30` の戻り値の式と分岐。出口は 2 種 (早期 exit の -1 と通常経路の `[rbp+0x5b8]`) まで確定したが、通常経路の値を決める分岐 (eventId 参照 38・flags 参照 186) は未読。述語 P の実行時値と報告ゲート R も未確定 (PY125 と同じ)。
- **mock・C provider は変えていない**。戻り値の式が未確定のため、実装すると silent miscompile になる。`tests/general_diff.mjs` と `provider_check.mjs` の件数は変化なし。受入 2〜4 は子 issue に移した (下の未解決表)。

## PE 根拠 (VA)

| 段 | VA | 動作 |
|---|---|---|
| handler | 0xd69f00 | PyArg 書式 `Iii`。eventId = `[rbp+0x7c]` (I = unsigned)、value = `[rbp+0x78]`、flags = `[rbp+0x74]` (i)。解析失敗 (rax ≤ 0) は 0xd69f94 で `0xd82c20(eax)`。成功は 0xd84740 を呼ぶ (0xd69f74) |
| handler 後段 | 0xd69f79〜0xd69f96 | `rax = out[0]` (0xd69f79)。非 0 は 0xd69f80 `jne` で 0xd69f94 へ飛び、`mov ecx, eax` (status の下位 32 bit) の後 `0xd82c20(ecx)`。0 は 0xd69f82 で `ecx = dword [rbp+0x60]` (= out+0x08 の下位) を `0x15e4280` 経由で int 化 |
| wrapper | 0xd84740〜0xd847a5 | rcx = eng、rdx = out、r8d = eventId (`mov r8d, r8d` = unsigned)、r9d = value (`movsxd`)、5 番目 = flags (`movsxd`)。dispatch の arg5〜arg7 = eventId・value・flags、arg8〜10 = 0、arg11 = `byte [rsp+0x50] = 1` (sync)。callback は `lea` で 0xd846e0 (次命令 0xd84752 + disp -0x72) |
| dispatch | 0xd843d0 | PY125 §1 と同じ。`out[0] = job+0x60`、`out+0x08 = job+0x10` (0xd844c2・0xd844db) |
| callback | 0xd846e0〜0xd84731 | `job+0x60 = -2` (0xd846e8)。P = `[[[0x15e4790]+8]]->vcall[+0x98]()` (0xd846f0〜0xd84704。PY125 の G と同じ式)。P 真で `job+0x60 = 0` (0xd8470e)、`ecx = job+0x18`・`edx = job+0x20`・`r8d = job+0x28` で `0x1046a30` を呼ぶ (0xd84716〜0xd84720)、`movsxd` して `job+0x10` へ (0xd84725〜0xd84728)。P 偽は -2 のまま |
| body | 0x1046a30〜0x104ccca | 単一の `ret` (0x104ccca)。入口で eventId → `[rbp+0x5b0]`・value → `[rbp+0x5b8]`・flags → `[rbp+0x5c0]`。戻り値は `[rbp+0x584]` (int32) |

### 0x1046a30 の出口 (確定した部分)

- `[rbp+0x584] = -1` を 0x1046d79 で書き、直後に `byte [*(0x15e1890)] != 0` なら 0x1046d8d `jne 0x104cc72` で本体を飛ばして `-1` を返す (0x104cc72 は `[rbp+0x584]` の複写 0x104cc6b を通らない)。
- 通常経路は 0x104cc65 `eax = [rbp+0x5b8]` → 0x104cc6b `[rbp+0x584] = eax` → 0x104ccba `eax = [rbp+0x584]` → 0x104ccca `ret`。
- `[rbp+0x584]` への書込みは 2 箇所だけ (0x1046d79・0x104cc6b)。`[rbp+0x5b8]` は入口の `value` を初期値とし、本体の 73 箇所で書き換わる (0x1047719 以降。`grep -c 'mov dword ptr \[rbp + 0x5b8\], '` の結果 74 件のうち入口の 1 件を除く)。よって通常経路の戻り値は「value をどう変換したか」で決まる。
- 0x104cc42〜0x104cc5b は `dword [rax] == 1` の分岐と `call 0xbd68e0(7, 0)`。0x104cc60 は `call 0x11d5520` の後で 0x104cc65 に合流する。この経路の意味は未読。

## 手段

- 展開: `mkdir -p "$RUNNER_TEMP/fl-win64" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64" --wildcards '*block00031_PE.bin'` (1.6 秒)。`$ARTIFACTS_DIR` の `fl-win64.tar.zst` の実在を確認してから展開。
- 逆アセンブル: `cd tools/python && FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/flapi/pe_disasm.py <VA> <命令数>`。0x1046a30 は線形走査 (4,679 命令) で ret が 1 箇所 (0x104ccca) であることを確認。
- 再現・検証: `cd tools/python && FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/py126_process_rec_chain.py` (上記の VA と命令の 26 件を assert)。
- RIP 相対の絶対アドレスは次命令 + disp で手計算し、スクリプトで検算 (`0xd84740` の lea → 0xd846e0、`0xd846f0` の `[0x15e4790]` は `0xd846f7 + 0x860099 = 0x15e4790`、`0x1046d83` の global は `0x1046d8a + 0x59ab06 = 0x15e1890`)。

## 検証

- 測定 commit: `5ac75460c` (`analysis/py126_process_rec_chain.py` を追加した commit)。以後スクリプトは無変更。main 取り込み後の merge commit `d170d964c` でも同じ結果 (26 件 ok・rc 0)。
- `python3 analysis/py126_process_rec_chain.py`: 26 件 ok・rc 0。
- ネガティブコントロール: スクリプトの期待 VA `0xD846E0` を `0xD846E1` に変えた複製で実行 → `FAIL 0xd84740: callback = 0xd846e0 (次命令 + disp)` で rc 1。元のスクリプトは無変更。
- e2e (`general_diff.mjs`・`provider_check.mjs`・`all_tools.mjs`): 実装を変えていないため対象外。件数は変化なし。
- コード差分: `git diff 5ac75460c HEAD -- tools/python/analysis/py126_process_rec_chain.py` は 0 行 (スクリプト無変更)。`git diff --stat 5ac75460c HEAD -- tools/python ':!*.md'` は main 取り込み分のみ (`host/fl_mock.mjs` 11 行・`provider/fl_engine.c` 15 行・`tests/`・`analysis/flapi/` の追加 3 件)。本 PR の検証対象 (スクリプトと PE) には影響しない。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x1046a30` の通常経路の戻り値 (`[rbp+0x5b8]` の変換式・eventId 別の分岐・early-exit gate `*(0x15e1890)` の意味) | processRECEvent の成功時の値が確定しない。mock/C 未実装 (受入 2・3・4 の前提) | #3701 (PY-235) |
| 述語 P の実行時値 (`[[[0x15e4790]+8]]->vcall[+0x98]`)・報告ゲート R・dispatch gate `0xd84f30` | -2 の経路 (None か RuntimeError) を確定できない。mock/C は P 真を仮置きする | #3045 (PY-145) へ追記 |
| `0x4133f0` (out+0x10)・`0x412e40`・`0x41a770`・`0x412d60` (ローカルの後始末) | processRECEvent は読まないため実装に影響なし | 本表のみ |
