# 付録: icall #5889 (ICALL-122) — itr_dump の正常終了経路と、6 関数の戻り値-分岐関係の単歩確認 (部分達成)

> 親: #5887 (ICALL-121)。前付録: `REPORT_APPENDIX_3089.md` §9.2・§11.1・§11.2。
> 測定 commit: `749a27433` (origin/main 時点の HEAD)。コード変更は `tools/icall/diff/slot_trace.c` のみ (本 PR)。

## 1. 結論

- **受入 1 (6 関数の機構): 部分達成。** `RtlPcToFileHeader` の戻り値が分岐に効くのは `_CxxThrowException` (`18102f728`) の中だけと確認した。6 関数 (`1803b3fc0`・`1803b5b60`・`180cbd860`・`18100cf60`・`181011058`・`18102f728`) は、単歩トレースで同じ経路を通ることを確認した。ただし **issue 本文の前提 (6 関数が rc=99) は現 main と合わない**。実測は rc=97 (`RaiseException(0xe06d7363)` の handler 無し fail-fast)。rc=99 は `UnhandledExceptionFilter` の 2 件 (`18100ca28`・`18103d218`) だけ。
- **受入 2 (`18100cc50`): 確認済み。** `RtlCaptureContext` の戻り値 `rax` は捨てられ、CONTEXT (`rcx`) は後続の `RtlVirtualUnwind` の入力になる。分岐を決めるのは `RtlLookupFunctionEntry` の戻り値。現 main では rc=0 で完走する (rc=99 ではない)。
- **受入 3: 該当なし** (1・2 とも確認済みの範囲で記録した)。
- **issue 本文の訂正**: 「`RtlPcToFileHeader` は分岐を変えない」という静的解析 (#5887) の見立ては、`_CxxThrowException` の magic 選択 (`0x19930520` / `0x1994000`) については正しい。ただし magic は `RaiseException` 後の例外レコードに入るだけで、guest の分岐そのものは `RaiseException` が fail-fast する時点で止まる。

## 2. 方法

- `tools/icall/diff/slot_trace.c` を修正: 正常終了の `atexit` と、fatal 経路 (`exit(97)` を含む) でも `itr_dump` が走るようにした。従来は `on_acc` の fatal (`_exit(95)`) でしか dump されず、`k_RaiseException` (`exit(97)`) と正常 return では単歩が残らなかった。修正後は `atexit` で `exit` 系と正常 return の両方を拾う。`missing_import` の `_exit(99)` は atexit を通らないため対象外 (rc=99 の 2 件は単歩を取れない)。dump は `g_trace_on` の時のみ。
- 単歩: `SLOT_TRACE_FN=<VA> SLOT_TRACE_OUT=<path> slot_trace <dll> <VA>`。
- 逆アセンブル: `objdump -d --no-show-raw-insn` (素材の SlateCore.core_64 を直接読む。`tools/icall/work/core64_dis.txt`)。
- import 名の確定: PE の import 表 (IAT スロット VA → 名前) を直接引いた。

## 3. 実測

| 関数 | 修正後の rc (現 main・SLOT_ENC_INIT=1) | 単歩 insn 数 | 経路 |
|---|---|---|---|
| `1803b3fc0` | 97 | 10259 | `_CxxThrowException` → `RaiseException(0xe06d7363)` → handler 無し |
| `1803b5b60` | 97 | 13166 | 同上 |
| `180cbd860` | 97 | 10417 | 同上 |
| `18100cf60` | 97 | 10307 | 同上 (throwinfo=`0x1812589c0`) |
| `181011058` | 97 | 10291 | 同上 (throwinfo=`0x1812591b0`) |
| `18102f728` (`_CxxThrowException` 直接) | 97 | 7527 | magic=`0x1994000` 側 (ImageBase 側の分岐なし) |
| `18100cc50` | 0 | 5539 | 正常完走 (`DONE`) |
| `18100ca28`・`18103d218` | 99 | (未測定) | `MISSING IMPORT UnhandledExceptionFilter` |

注: 修正前の同条件 (`SLOT_ENC_INIT=1` の既定 rc) は `1803b3fc0`・`1803b5b60`・`180cbd860`・`18100cf60`・`181011058`・`18102f728` が 97、`18100cc50` が 0。`18100ca28`・`18103d218` が 99。

## 4. 機構 (逆アセンブル + 単歩の突き合わせ)

### 4.1 `_CxxThrowException` (`18102f728`) の分岐

```
18102f764: lea 0x20(%rsp),%rdx ; mov %rbx,%rcx
18102f76c: call *0x1810c4310        ; KERNEL32!RtlPcToFileHeader (IAT idx 85)
18102f772: mov %rax,0x20(%rsp)     ; 戻り値を base として保存
18102f777: test %rbx,%rbx
18102f77a: je  18102f78b                    ; rbx == 0 → magic 0x19930520 のまま
18102f77c: testb $0x8,(%rbx)                ; ThrowInfo の属性
18102f77f: jne 18102f786                    ; 属性 bit3 → magic = 0x1994000
18102f781: test %rax,%rax                   ; RtlPcToFileHeader の戻り値
18102f784: jne 18102f78b                    ; 非 0 → magic 0x19930520
18102f786: mov $0x1994000,%edi
18102f78b: ... call *0x1810c4318            ; KERNEL32!RaiseException
```

- 単歩の実値 (次に実行された命令): 5 関数 (`1803b3fc0`・`1803b5b60`・`180cbd860`・`18100cf60`・`181011058`) は `18102f777` の直後に `18102f78b` を実行し、magic=`0x19930520`。このとき `rax`=`0x180000000` (IMG_BASE)。
- `18102f728` 自身の単歩 (rc=97・magic=`0x1994000`) は `18102f777` の直後に `18102f786` を実行し、`rax`=`0x0`。`18102f786` は magic を `0x1994000` に置く命令。
- よって `RtlPcToFileHeader` の戻り値 (`rax`) は、この分岐で magic 値 (`0x19930520` か `0x1994000`) を決める。`rax` が IMG_BASE なら `0x19930520`、0 なら `0x1994000` の側に入る。ただし `18102f78b` と `18102f786` の間の条件 (`rbx` の属性ビット) は本付録では実測していない。
- 6 関数は issue の列挙どおり。うち `18102f728` は `_CxxThrowException` 本体で、他 5 関数の呼び出し先でもある。
- **分岐を変えるのは `RtlPcToFileHeader` の戻り値そのもの。** 戻り値が guest の制御フロー (`18100cc50` 系の unwind 分岐) には効かない。guest 側の分岐は `RaiseException` の handler 検索 (`eh_walk`) で止まり、handler の有無で rc が決まる。

### 4.2 `18100cc50` (`RtlCaptureContext` の戻り値)

- `18100cc5b`: `call *0x1810c4290` (`KERNEL32!RtlCaptureContext`, IAT idx 69)。戻り値 `rax` は使われない。
- 続く `18100cc61`: `mov 0xf8(%rbx),%rsi` で CONTEXT (`rcx` = `rbx`) の `Rip` (オフセット `0xf8`) を読む。`RtlCaptureContext` が埋めた値が入力になる。
- `18100cc75`: `call *0x1810c4298` (`RtlLookupFunctionEntry`, IAT idx 70)。戻り値 `rax` が `18100cc7b` の `test %rax,%rax; je 18100ccb9` の分岐を決める。`rax` = 0 (`.pdata` 無し) なら unwind ループを抜ける。
- `18100cca5`: `call *0x1810c42a0` (`RtlVirtualUnwind`, IAT idx 71)。`rdx`・`r8`・`r9` は `RtlLookupFunctionEntry` の戻り値と `CONTEXT` 由来。
- **結論: `RtlCaptureContext` の戻り値は使われない。CONTEXT の `Rip`・`Rsp` が後続の `RtlLookupFunctionEntry` の入力になり、その戻り値 `rax` で分岐する。** 現 main では `RtlLookupFunctionEntry` が `.pdata` を引けるため完走する (rc=0)。

## 5. import 名の訂正 (既存の記録との差)

- `tools/icall/diff/fa_import_names.py` の出力は、IAT idx 64 を `LoadLibraryExW` と返す (`python3 tools/icall/diff/fa_import_names.py` の `idx 64`)。`REPORT_APPENDIX_2083.md` の「idx 64 = `KERNEL32!RtlPcToFileHeader`」は、現行の import 表の並びと合わない。
- 本付録では、IAT スロット VA を PE の import 表から直接引いた値を採った: `0x1810c4310` = `RtlPcToFileHeader` (import index 85)・`0x1810c4318` = `RaiseException` (86)・`0x1810c4290` = `RtlCaptureContext` (69)・`0x1810c4298` = `RtlLookupFunctionEntry` (70)・`0x1810c42a0` = `RtlVirtualUnwind` (71)。
- `fa_import_names.py` の idx の扱い (`ott_native.c` の `g_impname` と一致するか) は未確認。起票先: 本 issue の範囲外 (`tools/icall` の import 表の検証は #2083 系の子で扱う)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `18100ca28`・`18103d218` の rc=99 (`UnhandledExceptionFilter`) の単歩 | #4881 の判断の対象 (本 issue の対象外) | #4881 (PM 判断) |
| `fa_import_names.py` の idx 64 と IAT 実名の不一致 | 既存付録 (`REPORT_APPENDIX_2083.md`・`REPORT_APPENDIX_2247.md`) の import 名の記録 | 未起票 (PM 判断。本 PR では訂正のみ) |
| 6 関数の rc=97 (`RaiseException`) を handler 検出後の `__CxxFrameHandler` dispatch まで通すこと | 6 関数が wasm 側の結果になる条件 | #4362 (ICALL-103・既存) |
| 受入 1 の issue 本文 (rc=99 の前提) の更新 | issue 本文と現 main の不一致 | 本 issue のコメントで PM に報告 |
