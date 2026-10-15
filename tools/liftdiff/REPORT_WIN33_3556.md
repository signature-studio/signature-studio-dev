# REPORT — WIN-33 (#3556): 実カタログ供給後の止まり (範囲検査 RTE 201・rep movsq) の同定

親: #2760 (WIN-7 系)。前提 spike: [`REPORT_WIN7_2718.md`](REPORT_WIN7_2718.md) (#2718)。手順の正本は `win33_catalog.sh` / `win33_trace.py` (本 PR)。

測定 commit: `7080aca8a` (コード変更の最後の commit)。再測定を省く根拠 (`docs/WORKFLOW.md` §6): `git diff --name-status 7080aca8a HEAD -- tools/liftdiff` の出力は本 REPORT の追加 (`A tools/liftdiff/REPORT_WIN33_3556.md`) の 1 件だけ (コード差分 0)。
既知類型との関係 (DEFECTS.md): 該当なし (lift 欠陥ではなく、harness の stub 応答と停止の扱い。新規の類型候補は §7)。
再現コマンド: `FL_WIN64_DIR=<fl-win64 展開先> bash tools/liftdiff/win33_catalog.sh` (約 100 s・4 spike/trace 実行)。e2e: `bash tools/liftdiff/liftdiff_e2e.sh --m11-only`。
素材: fl-win64・work-m11・work-liftdiff・toolchain-emsdk (`[EMSDK]`)。`tools/liftdiff/work/` `tools/m11/work/` は展開済み。
実行環境: GitHub Actions runner (4 コア・load average 0.15〜1.3)。

## 0. 結論 (実測)

1. **範囲検査 (rva `0x17bc8`・Delphi RTE 201) の値 V は、`default.moe` の先頭 4 B (`de 12 04 95` = .mo magic `0x950412de`) を Int32 として読んで符号拡張した値 `0xffffffff950412de`** (負数)。V (最後の範囲検査時の値) を直前に書いたのは rva `0x17fc9` (`mov [rbp+0x58], r9`)。r9 は呼出元 `0x4d8642` が `movsxd r9, dword [rbp+0x6c]` で作る。`[rbp+0x6c]` は Stream の Read (rva `0x4d862a` の仮想呼出し) が埋めた 4 B。
   - ReadFile の応答は正しい (全量 47,405 B をバッファへ。先頭 4 B は blob と一致)。SetFilePointer の応答 (BEGIN/CUR/END=0xb92d/BEGIN) も整合。**原因は読取り位置 0 で magic を count として読んでいること**。どの読取りが位置 0 であるべきか (呼出元の読取り仕様 / .mo との形式不一致) は未同定 → §7 の子。
2. **rep movsq (rva `0x12a25`) は実カタログ供給の後の偽の止まり**。RTE 201 の後始末で `ExitProcess(0xc9)` の stub が戻る (`r=0`) ため、後続の `mov rsi,[rip+0x11d8267]` (この時点で 0 の global) からコピーして segv する。実プロセスの ExitProcess は戻らない。
3. S12〜S22 の対応は §5 (実測の import 列と止まり地点を `STARTUP.md` §2 の段に対応づけ、未観測は未観測と書く)。
4. **既定 (`LD_CATALOG_MO` 未指定) は不変**: spike 928/942・first_fail 830・segv `0x4e0fab`・35 import (= #2718 と同一)。`liftdiff_e2e.sh --m11-only` は clean `origin/main` と本 HEAD で同一値 (sample:800 = 一致 360 / 不一致 234 / 実行不能 206)・PASS。

## 1. 実測結果 (HEAD `7080aca8a`・`win33_catalog.sh` 1 回目の実測)

| 項目 | 既定 (`LD_CATALOG_MO` なし) | 実カタログ (`LD_CATALOG_MO=block25158`) |
|---|---|---|
| hybrid boot | units_run 928/942・first_fail 830 | units_run 928/942・first_fail 895 (830 は通過) |
| CreateFruityInstance (CFI) の status | segv `rip_rva=0x4e0fab` (null 読み) | segv `rip_rva=0x12a25` (`rep movsq`・rcx=0x25・rsi=0) |
| CFI の import 数 | 35 (`calls_over` 0) | 39 (下記 1.1 の 4 件が増加) |
| 範囲検査の入口 0x17b70 | 到達せず | 5 回 (うち最後の 1 回で負数 V) |
| 再実行 (同一 commit) | `win33_catalog.sh` の 2 回と HEAD の 1 回で同一の値 | 同左 |

### 1.1 実カタログ時の import 列 (末尾。既定と同じ前半は省略)

`… CreateFileW SetFilePointer SetFilePointer SetFilePointer SetFilePointer **ReadFile** CloseHandle **user32.dll!MessageBoxA** TlsGetValue **ExitProcess(0xc9)**`
(太字 = 既定に無い 4 件。ExitProcess の戻り値 `r=0`。)
ReadFile の引数: `h=0x65000001`・`buf=0x3d49240`・`n=0xb92d` (= END の位置 = 全量)・`pnread=0x7fffffffa1fc`。

## 2. 方法 (再現用の仕組み)

- `ld_core.h`: `LD_CATALOG_MO` 指定時だけ `CreateFileW` が `default.moe` を仮ハンドル `0x65000001` で開き、`ReadFile`・`SetFilePointer`・`GetFileSize` を実バイトで応答する (前の実験の再現。既定では `ld_cat_blob == NULL` で分岐に入らない)。
- `ld_native.c` の trace 拡張 (環境変数のみ・既定無効): `LD_STEP_ID=<case id>` で 1 case だけ命令 trace、`LD_STEP_MEM=<VA>` で 8B の変化を `MEM writer_last_img_rva=…` 行として記録、`LD_CASE_TMO_US` で case の timer (既定 1.5 s)。`ldlib/runners.py` の `LD_RUNNER_TMO` は Runner の read timeout (既定 20 s) を上書きする (trace が長いため)。
- trace の 1 行は `rva rax rcx rdx rbx rsp rbp rsi rdi r8 r9` (実行前のレジスタ)。cfi の trace は約 8.82 M 命令 (trace 行 8,819,946 で `0x12a25`)。
- スタック上のアドレス (V の場所) は環境変数の長さで変わるため、`win33_catalog.sh` は 1 回目の trace で最後の `0x17b70` の r9 を取り、同じ環境長で 2 回目に `LD_STEP_MEM` を付ける。

## 3. 受入条件 1: 範囲検査の値 V の出所

### 3.1 範囲検査の機械語 (`win33_trace.py dis 17b70 17bce`・rva)

```
17b70 push rbp / push rbx / sub rsp,0x98 / mov rbp,rsp      ; 入口 r9 = V のアドレス (0x17b70 の r9)
17b80 mov [rbp+0xb0],rcx / [rbp+0xb8],rdx / [rbp+0xc0],r8 / [rbp+0xc8],r9
17baa mov rax,[rbp+0xc8]      ; rax = V のアドレス
17bb1 mov rax,[rax]           ; rax = V (8B)
17bb4 mov [rbp+0x60],rax
17bb8 cmp qword [rbp+0x60],0 ; jg 0x417be5 (V>0 は正常)
17bbf cmp qword [rbp+0x60],0 ; jge 0x417bcd (V==0 は正常)
17bc6 mov cl,4 ; call 0x409730   ← V<0: RunError (code 201)。戻り番地 0x417bcd が「at」の値
```

### 3.2 trace で見た V (`win33_trace.py trace` の出力・rva 0x17bb8 直後の rax = V)

| trace 行 | 入口 r9 (V のアドレス) | V | 判定 |
|---|---|---|---|
| 3574 | 0x7fffffffb7a8 | 0x186a0 (100000) | 正常 |
| 4404524 | 0x7fffffffb7a8 | 0x186a0 | 正常 |
| 8809353 | 0x7fffffffb6c8 | 0x4 | 正常 |
| 8810609 | 0x7fffffffb6c8 | 0x8 | 正常 |
| **8819677** | **0x7fffffffa2f8** | **0xffffffff950412de** | **負数 → RTE 201** |

(V のアドレスは実行ごとに環境長で変わる。上の値は `win33_catalog.sh` の 1 回目の trace 時の実測。)

### 3.3 V の書込み履歴 (`LD_STEP_MEM=7fffffffa2f8`・MEM 行)

| 変化 (trace 行) | 書込み直前の image 命令 rva | 旧値 → 新値 |
|---|---|---|
| 8817398 | 0x7a51 | 0 → 0x3d552b0 |
| 8817620 | 0x234f0 | 0x3d552b0 → 0 |
| 8818105 | 0x113274 | 0 → 0x20 |
| 8818718 | 0x1134f1 | 0x20 → 0x4d3a28 |
| 8819048 | 0x141a5 | 0x4d3a28 → 0x4141aa |
| **8819652** | **0x17fc9** | **0x4141aa → 0xffffffff950412de** |

`0x17fc9` は `mov qword [rbp+0x58], r9` (4 B)。直後の rip は `0x17fcd`。0x17fc0 は 4 引数の spill 関数で、r9 (= 呼出元が渡した Int32 の符号拡張) を自分の局所 `[rbp+0x58]` に置く (17fc9)。続けて `lea rbx,[rbp+0x58]; mov r9,rbx` (17fd9・17fe9) で、その番地を範囲検査 (0x17b70) の r9 として渡す。

### 3.4 値の作り方 (呼出元 `0x4d8604`〜`0x4d8642`・逆アセンブル)

```
4d8604 mov qword [rbp+0x60],0 ; mov qword [rbp+0x58],0
4d8615 mov rcx,[rbp+0x38]     ; Stream オブジェクト
4d8619 lea rdx,[rbp+0x6c]     ; 読取り先 (4 B)
4d861d mov r8d,4
4d8627 mov rax,[rbp+0x38] ; mov rax,[rax] ; call qword [rax+0x30]   ← Stream.Read(buf, 4)
4d862d lea rcx,[rbp+0x70] ...
4d863e movsxd r9, dword [rbp+0x6c]      ; ← 読んだ 4 B を符号拡張
4d8642 call 0x417fc0                     ; → 0x17fc9 で [rbp+0x58] へ
```

- 仮想呼出し先: `0x113b90` (1 回のみ実行・trace 上)→ `call [rbx+0x40]` → `0x113b60` 系の `Move` (`call 0x409c80`)。ストリームの `Memory + Position` から `count` 字をコピーし `Position` を進める (`add [rbx+0x18],rsi`)。
- 返った 4 B は blob の先頭 4 B (`de 12 04 95`)。よって**この Read は Position 0 で行われた** (Position 0 の内容が magic と一致)。CFI 経路では、この Stream に対する Read はこの 1 回だけ (trace の `4d862a` 1 件・`113b90` 1 件)。
- Int32 の magic `0x950412de` は最上位ビットが立つため、`movsxd` で負数になる。範囲検査 (V≥0 を要求) がこれを弾く。

### 3.5 判定

| 候補 | 判定 | 根拠 |
|---|---|---|
| ReadFile の応答 | 正しい | 全量 47,405 B を書込み。先頭 4 B は blob と一致 (3.4) |
| SetFilePointer の応答 | 整合 (原因ではない) | BEGIN 0 / CUR 0 / END 0xb92d / BEGIN 0。END が全量と一致 |
| .mo ヘッダ | **値の出所** | V は magic `0x950412de` そのもの (負数化は符号拡張) |
| ストリーム位置 | **原因** | Position 0 で読んだ (3.4)。この読取りを count として扱う呼出元の仕様と、.mo の先頭 4 B (magic) が合わない |

**結論**: 範囲検査の値は .mo ヘッダの magic。原因は「Position 0 の Int32 を count として読む読取り」であり、ReadFile/SetFilePointer の応答ではない。Position を 4 以降にすべきか、この Stream が別形式 (.moe の FL 独自形式) を読んでいるかは未同定 (§7 の子)。

## 4. 受入条件 2: rep movsq (rva `0x12a25`) の呼出元と rsi=0 の由来

- ExitProcess の stub は戻り値 `r=0` (`calls_full` の最後の要素)。`ExitProcess` は `ld_core.h` の既定 (`return 0`) に落ちる。
- 直後の trace (実カタログ・trace の 2 回目): `12a07` → `12a0d call 0x6fc0` → `12a12 mov rsi,[rip+0x11d8267]` (rsi=0) → `12a19`/`12a20` (`lea rdi`・`mov ecx,0x25`) → `12a25 rep movsq` で segv (rcx=0x25・rsi=0・rdi=0x15eac80)。
- 戻り番地の検査: 実カタログの detail `s5=0x417bcd` = RTE 201 の「at」。よって `rep movsq` は**範囲検査の RunError の後始末** (rva 0x12a0x 系の関数) に属する。
- rsi=0 の由来: `[rip+0x11d8267]` は Delphi の後始末が読む global で、この実行では 0 のまま (未初期化)。実プロセスでは ExitProcess が戻らないため、この後始末に進まない。

判定: **harness 由来の偽の止まり**。lift 欠陥ではない。ExitProcess の stub を「case を status=exit(code) で終える」に変えれば、0x12a25 は到達しなくなる (§7 の子)。

## 5. 受入条件 3: S12〜S22 の対応表 (`tools/startup/STARTUP.md` §2 の段 ↔ 本 spike)

既定・実カタログとも同じ前半。import の順序は `REPORT_WIN7_2718.md` §1.1 と一致 (実カタログ時の追加は §1.1)。判定列: 観測 = import または止まり地点で確認、推定 = import の順序からの対応づけ、未観測 = spike で通過も止まりも確認できず。

| 段 (STARTUP.md) | 内容 | spike での観測 | 判定 |
|---|---|---|---|
| S12 | timeGetTime・旧版設定移行 | import #1 `timeGetTime`。Reg* の呼出し 0 (移行は no-op) | 観測 (移行 no-op は推定) |
| S13 | ログ ON・`Startup\*.log` | 対応する import を観測していない | 未観測 |
| S14 | 自己署名検証 (WinVerifyTrust) | WinVerifyTrust の呼出し 0 | 未観測 |
| S15 | ユーザデータ dir (Shared data) | `GetFileAttributesW`×2・`FindFirstFileW`×2・`GetLastError` (import #21〜#29) | 推定 |
| S16 | `0x13754b0` ユーザデータ配下の初期化 | `VirtualAlloc`×2・`InitializeCriticalSection`×6 (import #2〜#9) | 推定 |
| S17 | CPUID・多重起動 | CPUID は import ではない。FindWindowW の呼出し 0 | 未観測 |
| S18 | BasicInitialization (一時 dir・約 21 シングルトン) | `TlsGetValue`×5 (#10〜#14)・`GetCurrentThreadId` (#25) | 推定 |
| S19 | TApplication 窓 (RegisterClassW・不可視窓) | `GetClassInfoW`→`RegisterClassW("TApplication")`→`CreateWindowExW`→`SetWindowLongPtrW` (#15〜#18) | **観測** (STARTUP.md S19 と一致) |
| S20 | cmdline・スプラッシュ・BeforeRunning (設定・言語カタログ・フォーム) | `CompareStringW`・`WideCharToMultiByte` (#19・#20)・言語カタログ `default.moe` の読込み (`CreateFileW` #30→`SetFilePointer`×4 #31〜#34→`ReadFile`→`CloseHandle` #35)。既定は読込み後の null 読み `0x4e0fab` で止まる | **観測** (止まり地点まで) |
| S21 | `*iface = …` | 未到達 | 未観測 |
| S22 | TApplication.Run (メッセージループ) | 未到達 (実カタログは RTE 201 → ExitProcess) | 未観測 |

注: 既定の止まり `0x4e0fab` の呼出元 VA `0x8e1a36` (REPORT_WIN7_2718 §1.2) は S20 の言語カタログ読込み側 (推定)。実カタログで読込みが通ると、止まりは S20 の範囲検査 (3 節) に進む。

## 6. 受入条件 4 と製品 KPI

| 項目 | 前 (既定) | 後 (既定) | 判定 |
|---|---|---|---|
| spike の units_run / first_fail | 928/942・830 | 928/942・830 | 不変 |
| CFI の止まり | segv `0x4e0fab` | segv `0x4e0fab` | 不変 |
| CFI の import 数 | 35 | 35 | 不変 |
| e2e `--m11-only` sample:800 (一致/不一致/実行不能) | clean `origin/main` (c42713e52): 360/234/206 | 本 HEAD (7080aca8a): 360/234/206 | 不変 |
| e2e `--m11-only` の結果 | `LIFTDIFF_E2E PASS` (2m43s) | `LIFTDIFF_E2E PASS` (2m44s) | 不変 |

KPI (`docs/WORKFLOW.md` §7・起動に関わる PR): FLEngine 起動の dispatch 数・通過 unit 数 は既定で不変 (928/942)。実カタログ時は first_fail が 830 → 895 (830 は通過)。最初のウィンドウ (画素) は**動かしていない** (画素統計は未取得。`CreateWindowExW` は両方で呼ばれる)。

## 7. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 読取り位置 0 で .mo の magic を count として読む呼出元 (`0x4d8600` 付近) の同定。Stream の Position `[obj+0x18]` の PEEK と、読む対象 (.mo か FL 独自の .moe 形式か) | 範囲検査 RTE 201 を消すための正しい読取り位置・形式が決まらない。実カタログを通せない | 子 issue (本 PR の次段) |
| ExitProcess の stub が戻る (harness) → 0x12a25 の偽の segv | 実カタログ時の止まり地点が偽になる (status 判定が歪む) | 子 issue |
| REPORT_WIN7_2718 §5 (`LD_CATALOG_MO` の実測と rva `0x17bcd`・`0x12a25`) が repo に無かった | 出典が欠けていた。本 REPORT の §3・§4 で再測定して代替 | 本 PR で解消 (`win33_catalog.sh` で再現) |
| 窓の画素統計・`CreateWindowExW` の呼出元 VA | 最初のウィンドウ KPI は未取得 | 範囲外 (親 #2760 の子・#3556 の範囲外) |

## 8. 検証範囲 / 範囲外

- 検証: 既定 spike・実カタログ spike・命令 trace (2 回)・e2e `--m11-only` (clean `origin/main` と本 HEAD)。いずれも `7080aca8a` (HEAD) で再現。
- 範囲外: wasm 化 (`rt/fle_ldbridge.c` の wasm ビルドは本 PR で触らない。`ld_core.h` の追加は `ld_cat_blob == NULL` で分岐に入らない)。本番コード化。画素統計。
- 限界: スタックのアドレスは環境変数長に依存 (`win33_catalog.sh` が同じ環境長で取り直す)。trace は単一 case (`cfi`) のみ。Stream の Position は直接 PEEK していない (3.4 の magic 一致からの推定)。
- 単一 run の実測。e2e の絶対値は負荷で変わる (REPORT.md §6.2) ため、clean HEAD との同一 run 比較で判定した。
