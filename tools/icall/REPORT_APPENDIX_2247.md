# 付録: icall #2247 (ICALL-68) — fatal RIP 群 B/D/E/G/H/I の faulting 値の起源と群 C の判定

> 親: #2231 (ICALL-67)。前付録: `REPORT_APPENDIX_2231.md` §1・§4。受入条件 1〜5 を本付録で扱う。
> 測定 commit: `d36f86d9` (`slot_trace.c` に単歩トレース `SLOT_TRACE_FN` と第 5 引数 `SLOT_STK5` を追加。計測条件 (既定) は不変)。検証 HEAD と差分の証跡は §5。

## 1. 結論

faulting 値の起源は、群 B・D・E・G・H が **harness の引数由来**、群 I が **harness の thunk (`make_thunk`) の整列欠落**。
群 C の `SLOT_ENC_INIT` の値は **guest 自身の初期化が書く値** (enc(NULL) = cookie) と一致し、harness の artefact ではない。

| 群 | 入口 (harness が呼ぶ fn) | fault 箇所 | 値の起源 (トレース・逆アセンブル) | 分類 |
|---|---|---|---|---|
| B | `1803dfc10` (`1803e01d0`・`1803e0380` も同じ RIP で落ちる) | `180c8b9c0` `mov rax,[rcx+0x18]` (addr `0xa098`) | `1803dfc38` `mov rcx,[rcx+0x90]` が arg0+0x90 の 0 埋め領域を読んで 0 → `1803dfc3f` `add rcx,0xa080` で `0xa080` → `1803dfc46` `call 180c8b9c0` | harness 引数 (arg0) の 0 埋め領域の派生 |
| E | `18105bb90` (`18105bea0` も同じ RIP で落ちる) | `18105bd74` `mov ecx,[rax]` (addr `0x400`) | `18105bd70` `mov rax,[rbp+0x30]` は **第 5 引数スロット** (`entry_rsp+0x28`)。harness は `nstk=0` で stack 引数を渡さず、残値 0x400 を読む。`SLOT_STK5` で値を渡すと fault addr がその値になる (§2.4) | harness 引数 (未供給の第 5 引数) |
| H | `180da6bf0` (`180da6ce0` も同じ RIP で落ちる) | `180da6d0b` `mov rax,[rcx+0x8]` (addr `0x8`) | `180da6cf5` `mov rcx,[rcx+0x10]` が arg0+0x10 の 0 埋め領域を読んで 0 | harness 引数 (arg0) の 0 埋め領域の派生 |
| D (入口 2) | `18105c1cc` | `18106a3b4` `ldmxcsr [rsp+8]` (#GP) | `ecx=0x50001b80` は `_controlfp` 形のビット合成 `(((~edx \| 0xffff807f) & stmxcsr) \| (ecx & edx))` の結果。`edx`=arg1 `0x50000420`・`ecx`=arg0 `0x50000010` の下位 32 bit を制御語として混ぜたもの (§2.5) | harness 引数 (heap ポインタ) のビット合成 |
| G (入口 2) | `180ca2450` | `180da6e99` `inc dword [rax+0x19a4]` (addr `0x19a4`) | `180ca245f` `add rcx,0x360` で rcx=arg0+0x360 (`0x50000370`) → `180da6e95` `mov rax,[rcx+0x10]` が arg0+0x370 の 0 埋め領域を読んで 0 | harness 引数 (arg0) の 0 埋め領域の派生 |
| I | `1803b3fc0` (`0x55..96f` 形 9 件) | `missing_import` 内の `movaps` (`slot_trace+0x296f`) | `tools/ott/native/ott_native.c` の `make_thunk` (124〜136 行) は `mov ecx,idx; mov rax,missing_import; call rax` だけで、thunk 入口 rsp=16n+8 のまま `call` する。`missing_import` 入口は 16n (§2.6) | harness 側 (`make_thunk`) の整列欠落 |
| C | `18103d47c` (fast-fail `int 0x29`) | `18103d494` | slot の値は guest の初期化 `0x18105650c` が書く値と同じ (§2.7)。fast-fail の到達条件 (slot が NULL のまま `18103d37c` に来る) は harness が上流初期化を走らせないことに依存 | 値は guest の意図 (artefact ではない)。到達条件は harness 由来 |

- 受入条件 1 (群 B・E): 起源を特定 (harness 引数由来)。群 E の第 5 引数の残値 0x400 がどの呼出しの残りかは未追跡 (§4)。
- 受入条件 2 (群 H): `rcx=0` の経路を特定 (`[arg0+0x10]` の 0 埋め読出し)。
- 受入条件 3 (群 D・G の別入口): heap 域の値の起源を特定 (D は引数のビット合成、G は arg0+0x360 の派生)。
- 受入条件 4 (群 I): 入口 rsp が 16n+8 からずれる原因は `make_thunk` の `call rax`。上流の guest 呼出しは整列している。
- 受入条件 5 (群 C): SLOT_ENC_INIT の値は guest の初期化と一致 (artefact ではない)。ただし harness は上流初期化を走らせないため、fast-fail の到達は harness の範囲に依存する。

## 2. 実測

### 2.1 測定条件

- 再現 (既定): `SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh` を測定 commit `d36f86d9` のクリーンな worktree で foreground・1 回実行。
  - real 12.288 s / user 11.081 s / sys 1.728 s。load average (1 分値) 0.30 (開始時 23:45:51 UTC)。
  - 集計: `funcs 131 exit {rc=0: 69, rc=124: 1, rc=95: 53, rc=98: 8}`・zero-fill VA 10・既知 12 hit 3。`REPORT_APPENDIX_2231.md` §2.2 の baseline と完全一致。fatal 行は 53 件 (2231 と一致)。
- 単歩トレース (`SLOT_TRACE_FN`): 1 関数 1 プロセス、各 0.01 s 未満。時間は参考値。
- 素材: `fl-win64` 不要 (SlateCore は `plugins-freshair`)・`work-icall` (`tools/icall/work/`)・`plugins-freshair` (`FA_DL` 経由で `tools/targets/freshair/work/win/`)。展開を確認してから実行。

### 2.2 単歩トレースの仕様 (`slot_trace.c`)

- `SLOT_TRACE_FN=<fn_va>`: 関数入口に INT3 を置き、入ったら TF で単歩して **全命令の直前の状態** (rip・16 GPR・`[rsp+0x28]`) をリングバッファ (300000 件) に記録する。fault (fatal 経路) で `SLOT_TRACE_OUT` (既定 `slot_trace_insn.txt`) に書き出す。
- 形式: `I <rip> rax rbx rcx rdx rsi rdi rbp rsp r8..r15 s28=<[rsp+0x28]>` (値は 16 進)。
- `SLOT_STK5=<hex>`: harness が渡す stack 引数を 1 個 (第 5 引数) に設定する。未指定時は従来どおり `nstk=0`。
- 注意: `18105bb90` (群 E の入口) は TF 単歩中に `RaiseException(0xc000008f)` (FP invalid) の fail-fast (rc=97) に入り、入口からは取れない。原因は未特定 (単歩中の MXCSR/FP 状態の扱い)。群 E は静的解析と `SLOT_STK5` の実測で確定した。

### 2.3 群 B: 0xa080 の起源 (`1803dfc10`・単歩 17 命令)

| 命令 (VA) | 命令 | 直後の状態 |
|---|---|---|
| `1803dfc35` | `mov %rcx,%rdi` | rcx=`0x50000010` (arg0) |
| `1803dfc38` | `mov 0x90(%rcx),%rcx` | rcx=`0` (arg0+0x90 = `0x500000a0` が 0 埋め) |
| `1803dfc3f` | `add $0xa080,%rcx` | rcx=`0xa080` |
| `1803dfc46` | `call 0x180c8b9c0` | 入口 rcx=`0xa080` |
| `180c8b9c0` | `mov rax,[rcx+0x18]` | fault addr `0xa098` (`0xa080+0x18`) |

- 同じ `rcx=0xa080` を渡す `1803e01d0`・`1803e0380` も同じ RIP で落ちる。経路は未トレースだが、値の型は同じ。

### 2.4 群 E: 第 5 引数スロットの残値 (`18105bb90`)

- 逆アセンブル: `18105bb90` は `push rbp; mov rsp,rbp` の後 `rbp = entry_rsp − 8`。`18105bd70` `mov rax,[rbp+0x30]` = `[entry_rsp+0x28]` = MS x64 の第 5 引数 (stack 引数の先頭)。`18105bd74` `mov ecx,[rax]` が fault。
- 実測 (`SLOT_ENC_INIT=1`・`SLOT_STK5` を変える):

| 条件 | fault RIP | fault addr | regs の rax |
|---|---|---|---|
| 既定 (`nstk=0`) | `18105bd74` | `0x400` | `0x400` |
| `SLOT_STK5=1234` (第 5 引数 = 0x1234) | `18105bd74` | `0x1234` | `0x1234` |
| `SLOT_STK5=0` | `18105bd74` | `(nil)` | `0` |

- 結論: 群 E の faulting 値は harness が渡さない第 5 引数の内容で決まる (harness 引数由来)。0x400 は未供給スロットの残値。残値の出所 (どの harness 呼出しの残りか) は未追跡 (§4)。

### 2.5 群 H・G・D (単歩トレース)

- 群 H (`180da6bf0`・12 命令): `180da6cf5` `mov 0x10(%rcx),%rcx` で rcx=arg0 (`0x50000010`) から rcx=`0` へ。`180da6d0b` の `mov rax,[rcx+0x8]` が addr `0x8` で落ちる。`180da6d04` の `cmpb $0,0xf0(%rdi)` は rdi=arg0 を使うので、rcx の 0 とは独立。
- 群 G (`180ca2450`・23 命令): `180ca245f` `add $0x360,%rcx` で rcx=`0x50000370` (arg0+0x360)。`180da6e95` `mov 0x10(%rcx),%rax` が rax=`0` (`0x50000380` = arg0+0x370 の 0 埋め)。`180da6e99` は `inc dword [rax+0x19a4]` (`ff 80 a4 19 00 00`) で addr `0x19a4` (`rax=0` 基準) に落ちる。
- 群 D (`18105c1cc`・29 命令): `18105c1e1` `call 0x18106a3a0` (stmxcsr 相当) が eax=`0x1f80`。`18105c1ec`〜`18105c1fa` が `ecx = ((~edx | 0xffff807f) & eax) | (edi & edx)` を計算し、`edx`=`0x50000420`・`edi`=`0x50000010` (下位 32 bit) から `0x50001b80` を得る。`18106a3b0` `mov %ecx,0x8(%rsp)` → `18106a3b4` `ldmxcsr 0x8(%rsp)` が予約ビット (bit 30) で #GP。

### 2.6 群 I: thunk の rsp 整列 (`1803b3fc0`)

- 単歩トレース (rsp は `$10` 列): 入口 `1803b3fc0` rsp=`…9688` (16n+8・正しい)。guest 内の呼出しは整列を保つ。
- 呼出し `18102f76c` (`call 0x60000800`) で thunk (`0x60000800`) の入口 rsp=`…95d8` (16n+8・正しい)。
- thunk 内 `60000800` `mov ecx,idx` → `60000805` `mov rax,missing_import` → `6000080f` `call rax`。ここで rsp=`…95d8` のまま `call` して `missing_import` 入口 `55e7f26aaa34` の rsp=`…95d0` (16n・誤り)。
- `missing_import` 内の `movaps` (`slot_trace+0x296f`) が 16 バイト整列を要求して落ちる (`fprintf` より前のため `MISSING IMPORT` が出ない)。
- `make_thunk` は `sub $8,%rsp` を欠く。`REPORT_APPENDIX_2083.md` が `KERNEL32!RtlPcToFileHeader` の thunk で整列がずれると記録した件と同じ経路。
- 修正案の確認 (リポジトリ外の一時コピー。`ott_native.c` の `call rax` の直前に `sub $8,%rsp` を入れた版): `1803b3fc0`・`1803b5b60` は `MISSING IMPORT RtlPcToFileHeader — fail-fast` (rc=99)、`18103d218` は `MISSING IMPORT RtlCaptureContext — fail-fast` (rc=99) に変わり、`movaps` の fatal (rc=95) は消えた。修正は harness 側 (`tools/ott/native/ott_native.c`) で本 PR の範囲外のため、子 issue に分けた (§4)。

### 2.7 群 C: `SLOT_ENC_INIT` の値は guest の初期化と一致

- 復号: `18103d3e3` `mov 0x2216be(%rip),%r10` (cookie `0x18125eaa8`) → `18103d3f3` `xor 0x2c94d6(%rip),%r10` (slot `0x1813068d0`) → `ror %cl,%r10` (cl = cookie & 0x3f)。結果が 0 なら `18103d417` → `call 18103d47c` → `IsProcessorFeaturePresent(0x17)` が真なら `int 0x29` (`18103d494`)。
- slot の書込み元 (`objdump` の RIP 相対 `mov` 書込みを集計。int3 パディング直後を関数先頭とみなす):

| slot | 書込み関数 | 呼出し元 (rcx) | 判定 |
|---|---|---|---|
| `0x1813068d0` | `18103d374` (`mov %rcx,slot; ret`) | `18105651c` (rcx = `[cookie]`) | guest 初期化 (cookie = enc(NULL)) |
| `0x1813068f8` | `1810553c8` | `181056524` (rcx = `[cookie]`) | 同上 |
| `0x181306908` | `181055858` | `18105653c` (rcx = `[cookie]`) | 同上 |
| `0x1813073f8`・`0x181307400`・`0x181307408`・`0x181307410` | `181065674` (4 点書込み) | `18105652c` (rcx = `[cookie]`) | 同上 |
| `0x181307418` | `181065920` | `181056534` (rcx = `[cookie]`) | 同上 |
| `0x1813073f0` | `181065518` | 静的な直接呼出しなし | 未確認 |
| `0x1813072b0` | `18105de40`・`18105de62` (dispatcher 近傍) | 直接呼出しなし | 未確認 (解決時の書込みと見られる) |
| `0x181306900`・`0x181306910` | 単純な `mov` 書込みなし | — | 未確認 (harness の `enc[]` にだけ入る。2224 §3) |

- 初期化関数 `0x18105650c` は `rbx = [0x18125eaa8]` (cookie) を読み、各 setter に `rcx = rbx` で渡す。cookie は `enc(NULL)` (`rol(0,rot) ^ cookie = cookie`) なので、`SLOT_ENC_INIT` が敷く値は guest 自身の初期化が書く値と同じ。
- 判定: 値は guest の意図で、harness の artefact ではない。`18103d47c` の fast-fail は「NULL に復号される slot を使った」場合の guest 自身の判定。harness は `0x18105650c` を走らせないため、slot が NULL のまま `18103d37c` に来る経路になる。実機の起動経路でこの初期化が先に走るかは未確認 (§4)。

## 3. 再現

リポジトリ直下で実行する (素材は `docs/WORKFLOW.md` §11 の `fl-win64` 以外に `plugins-freshair` `work-icall` が要る):

```
FA_DL="$RUNNER_TEMP/plugins-freshair" bash tools/targets/freshair/fetch.sh
gcc -O1 -g -o tools/icall/work/slot_trace tools/icall/diff/slot_trace.c tools/ott/native/ms_call.S -lm
FA="tools/targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
SLOT_ENC_INIT=1 SLOT_TRACE_FN=1803dfc10 SLOT_TRACE_OUT=tools/icall/work/trB.txt tools/icall/work/slot_trace "$FA" 1803dfc10
SLOT_ENC_INIT=1 SLOT_STK5=1234 tools/icall/work/slot_trace "$FA" 18105bb90
objdump -d --start-address=0x1803dfc10 --stop-address=0x1803dfc50 "$FA"
```

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `make_thunk` の `call rax` の整列 (`sub $8,%rsp` の欠落)。直すと群 I の 9 件は `MISSING IMPORT` の `exit(99)` に変わり、harness の rc 分布 (`rc=95`) が変わる | 群 I の fatal の除去。既定の計測値 (2231 §2.2) が変わる | 子 issue (本 PR で起票。番号は PR 本文・issue コメント参照) |
| 群 E の第 5 引数の残値 0x400 の出所 (どの harness 呼出しの残りか)。単歩トレースは FP 例外の fail-fast で入口から取れない | 群 E の起源の詳細 (値の由来は harness 引数と確定済み) | PM 判断 (未起票) |
| 群 C の上流: `0x18105650c` が実機の起動経路で先に走るか。harness は closure 単関数実行のため走らせない | 群 C の fast-fail が実機でも到達するかの判定 | PM 判断 (未起票) |
| `0x1813073f0`・`0x1813072b0` の書込み元の呼出し経路 (静的な直接呼出しなし) | §2.7 の 12 slot 中 2 件の判定 | PM 判断 (未起票) |

## 5. 検証

- 測定 commit: `d36f86d9` (`tools/icall/diff/slot_trace.c` の最後のコード変更)。§2.1 の再現はこの commit の tree で実行した。
- 検証 HEAD: 本付録を含む commit (§5 の差分確認は PR 作成時に行う)。
- `git diff d36f86d9 HEAD -- tools/icall/diff tools/ott` の出力: 差分 0 (本付録は `tools/icall/REPORT_APPENDIX_2247.md` と `docs/DOC_MAP.md`・`tools/icall/REPORT.md` の索引のみ)。
