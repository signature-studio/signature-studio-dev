# ildsp 0x161fc0 閉包の間接 call / jmp 24 件の宛先確定 (T-SH-70 #3346)

> **正本**: 本付録。親 [T-SH-61] #3299 (0x161fc0 の closure lift)・REPORT_CLOSURE.md §8 から参照。

## 結論
- 0x161fc0 単独の閉包 (67 関数・2,609 命令) の間接 call 18 件・間接 jmp 6 件 = **24 箇所**。issue 本文の 4 件 (0x1aedf6・0x1aee04・0x1aee4a・0x1b6f6c) はこの閉包に含まれる。
- **IAT 21 件** (call 16・jmp 5) は、宛先が **静的に確定**する (KERNEL32 の import 名)。スロットは import directory の IAT 項で、`.rdata` (読み取り専用) にあり、コード内に書き込み命令が 0 件。
- **CFG/XFG dispatch 経由の 3 件** (call 2 : 0x1aedf6・0x1b6f6c、jmp 1 : 0x1bd4e9) は、**trap 化する**。スロットはローダが CFG/XFG の検査を入れる dispatch ポインタで、既定値の先は `jmp rax`。宛先は実行時の `rax` で、静的には決まらない (§3)。
- issue が参照する `REPORT_LIFT.md` と `closure_select.py` は repo に無い。閉包は `ildsp_vtable.py --seed 0x161fc0` で再計算した (閉包規則は REPORT_CLOSURE.md §4.1 と同じ)。

## 1. 測定
- 測定 commit: `a99604b1a` (コードを変えた最後の commit。`ildsp_vtable.py` の `--seed` と import 名の修正、`ildsp_indirect_resolve.py` の新設)。
- 以降のコード差分: `git diff a99604b1a HEAD -- tools/shared/scripts` は空 (本付録と REPORT_CLOSURE.md・DOC_MAP.md の追記のみ)。
- 素材: `fl-win64` の `extracted/block24360_PE.bin` (sha256 `f4b23b0f…`、既知値と一致)。展開先は `$RUNNER_TEMP/fl-win64`。
- 再現:
  ```
  FL_WIN64_DIR=<展開先> python3 tools/shared/scripts/ildsp_vtable.py --seed 0x161fc0
  python3 tools/shared/scripts/ildsp_vtable_check.py tools/shared/work/raw/ildsp_vtable.json
  python3 tools/shared/scripts/ildsp_indirect_resolve.py tools/shared/work/raw/ildsp_vtable.json
  ```
- 実測 (HEAD `a99604b1a`・3 回・4 vCPU・load 0.06〜0.20):
  - `ildsp_vtable.py --seed` 0.24 s × 3。closure[seed 0x161fc0] = 67 関数・2,609 命令・SIMD 440・直接 call 150・間接 call 18・間接 jmp 6。JSON は 3 回とも `cmp` 一致。
  - `ildsp_vtable_check.py` = `ALL OK`。
  - `ildsp_indirect_resolve.py` 3.2 s × 3。出力は 3 回とも `cmp` 一致。summary = IAT 21・ptr 3。

## 2. 24 箇所の一覧
| 種別 | 呼出し元 (site・関数) | スロット | 宛先の確定 | 扱い |
|---|---|---|---|---|
| call | 0x1ad63f (0x1ad634) | 0x268050 | IAT SetUnhandledExceptionFilter | 静的 |
| call | 0x1ad648 (0x1ad634) | 0x268048 | IAT UnhandledExceptionFilter | 静的 |
| call | 0x1ad64e (0x1ad634) | 0x268070 | IAT GetCurrentProcess | 静的 |
| call | 0x1ad676 (0x1ad668) | 0x268060 | IAT IsProcessorFeaturePresent | 静的 |
| call | 0x1ad867 (0x1ad85c) | 0x268028 | IAT RtlCaptureContext | 静的 |
| call | 0x1ad881 (0x1ad85c) | 0x268030 | IAT RtlLookupFunctionEntry | 静的 |
| call | 0x1ad8b8 (0x1ad85c) | 0x268038 | IAT RtlVirtualUnwind | 静的 |
| call | 0x1aedf6 (0x1aedc0) | 0x268260 | **CFG dispatch → rax** | **trap** (§3-1) |
| call | 0x1aee04 (0x1aedc0) | 0x268088 | IAT RtlPcToFileHeader | 静的 |
| call | 0x1aee4a (0x1aedc0) | 0x268090 | IAT RaiseException | 静的 |
| call | 0x1b6f6c (0x1b6f4c) | 0x268268 | **XFG dispatch → rax** | **trap** (§3-2) |
| call | 0x1b882f (0x1b8820) | 0x2680a0 | IAT GetLastError | 静的 |
| call | 0x1b88cf (0x1b8820) | 0x2680a8 | IAT SetLastError | 静的 |
| call | 0x1b8d3c (0x1b8adc) | 0x268090 | IAT RaiseException | 静的 |
| call | 0x1b9061 (0x1b900c) | 0x268128 | IAT HeapAlloc | 静的 |
| call | 0x1b909a (0x1b9084) | 0x268130 | IAT HeapFree | 静的 |
| call | 0x1b90a4 (0x1b9084) | 0x2680a0 | IAT GetLastError | 静的 |
| call | 0x1b9c5a (0x1b9c1c) | 0x268128 | IAT HeapAlloc | 静的 |
| jmp | 0x1ad661 (0x1ad634) | 0x268078 | IAT TerminateProcess | 静的 |
| jmp | 0x1b932c (0x1b932c) | 0x268140 | IAT FlsGetValue | 静的 |
| jmp | 0x1b9334 (0x1b9334) | 0x268148 | IAT FlsSetValue | 静的 |
| jmp | 0x1bb426 (0x1bb414) | 0x2680b8 | IAT EnterCriticalSection | 静的 |
| jmp | 0x1bb47a (0x1bb468) | 0x2680c0 | IAT LeaveCriticalSection | 静的 |
| jmp | 0x1bd4e9 (0x1bd4b8) | 0x268268 | **XFG dispatch → rax** | **trap** (§3-3) |

- 「静的」は宛先の同定 (どの import か) までを指す。IAT の stub 化の方針 (C 実装か trap か) は [T-SH-65] #3318 の受入 2 で決める。
- IAT 21 件の根拠: スロットは import directory の IAT 項 (`pefile` の import 名と一致)。`.rdata` は書き込み不可 (セクション属性に MEM_WRITE が無い)。ローダだけが書き、コードからの書込み 0 件 (`ildsp_indirect_resolve.py` の `writes=0`)。

## 3. 実行時依存の 3 件 (trap)
- 共通: スロット `0x268260` は load config の `GuardCFDispatchFunctionPointer`、`0x268268` は `GuardXFGDispatchFunctionPointer` (`.rdata`・再配置あり)。ファイル上の値は `0x1cb5e0` (`jmp rax`) と `0x1cb600` (`jmp [0x268260]`)。`.rdata` に書き込む命令は無い。したがって宛先は、スロットの値ではなく **`rax` の実行時値**で決まる。
- 1. **0x1aedf6** (helper 0x1aedc0): `mov rcx,[rcx]; sub rcx,8; mov rax,[rcx]; mov rax,[rax+0x40]` の後に `call [0x268260]`。`rax` は引数 `rcx` から辿るオブジェクトの vtable の index 8 (`[rax+0x40]`)。オブジェクトは実行時の値。
- 2. **0x1b6f6c** (関数 0x1b6f4c): `call 0x1b6f88` の戻り値 `rax` を `test rax,rax; je` の後も変えずに、`movabs r10,…` (XFG の型ハッシュと見られる・推定)、`mov rcx,rbx` を経て `call [0x268268]`。`rax` は実行時の戻り値。
- 3. **0x1bd4e9** (関数 0x1bd4b8・tail jmp): `rax = ror(zext(A32) ^ G, A & 0x3f)` (A = 0x3f5d98・G = 0x3f84d0 は `.data`)。
  - A は `0x1ad0d8: mov [A], rax` で書かれる (コード内の唯一の書込み)。
  - G は `0x1bd4b0: mov [G], rcx` で書かれる (ファイル値 0・呼出し元の `rcx` が入る)。
  - 両方とも実行時の値で、宛先は実行時に決まる。

判断: 3 件は**静的確定しない**ので trap 化する。lift 出力では、各箇所の先頭で非 0 終了する TRAP を置く (実装は下の未解決)。[T-SH-65] #3318 の受入 3 は 0x1aedf6・0x1b6f6c を trap 化すると明記しており、本判断と一致する。0x1bd4e9 は 0x161fc0 閉包の lift ([T-SH-61] #3299) の TRAP gate に入れる。

## 4. 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x1aedf6・0x1b6f6c の trap 挿入 (lift 出力と非 0 終了 gate) | 到達時に止まる検査が無い (受入 2 の残り) | [T-SH-65] #3318 (受入 3 に既存) |
| 0x1bd4e9 の trap 挿入 | 同上 (0x161fc0 の lift 出力が無いため未実施) | [T-SH-61] #3299 (TRAP gate に既存) |
| IAT 21 件の stub 方針 (C 実装か trap か) | 静的に同定できても lift 上の扱いは未定 | [T-SH-65] #3318 (受入 2 に既存) |
| 4 件 (0x1aedf6・0x1aee04・0x1aee4a・0x1b6f6c) の到達条件 | 到達しない根拠ではない (完走実験で 0 件) | [T-SH-54] #3250 |
| 線形走査の不復号区間 (`.text` 69 byte・`IPPCODE` 1,624 byte) | 書込み 0 件の判定は、この区間に書込み命令が隠れていないことを仮定する | 追跡 issue なし (PM 判断) |
| `A` (0x3f5d98) の書込みは `.text` 走査のみ | `IPPCODE`・データ内の書込み経路は未確認 (A の値が変わっても 0x1bd4e9 は実行時依存のまま) | 追跡 issue なし (判断に影響しない) |
