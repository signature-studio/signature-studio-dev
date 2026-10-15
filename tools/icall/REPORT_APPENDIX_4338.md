# 付録: icall #4338 (ICALL-100) — RtlCaptureContext の native IMPL 追加

> 親: #1922 (ICALL-52)。前付録: `REPORT_APPENDIX_1922.md`。子: #4529 (ICALL-104・`SetUnhandledExceptionFilter`)。

## 1. 結論

- 受入条件 1 (`RtlCaptureContext` を IMPL 表に追加): **部分達成**。`RtlCaptureContext` は追加した (§2)。
  `UnhandledExceptionFilter` は追加していない。`18100ca28` が実際に失敗するのは `SetUnhandledExceptionFilter` で、`UnhandledExceptionFilter` ではない (§3)。
- 受入条件 2 (3 関数の fail-fast 理由の変化を単独実行で記録): **達成**。§3。
- 受入条件 3 (`fa_sweep.sh 8 60` の件数を変更前後の同一 tree で測定): **達成**。§4。件数は変わらなかった。
- 未達の `SetUnhandledExceptionFilter` は子 #4529 (ICALL-104) に移した。

## 2. 実装

`tools/ott/native/ott_native.c`:
- `k_RtlCaptureContext`: x64 CONTEXT (0x4d0 B) を 0 埋めし、`ContextFlags`・`MxCsr`・`SegCs`・`SegSs`・`EFlags`・`Rip`・`Rsp` を埋める。
  汎用レジスタ・XMM は native 側から実値を取れないためゼロ。unwind 用の実値が要る経路は §3 の `RtlLookupFunctionEntry` で止まる。
- IMPL 表に `{"RtlCaptureContext", k_RtlCaptureContext}` を追加。

コード変更の commit: `945cf6010`。

## 3. 3 関数の単独実行 (fail-fast 理由)

| 関数 | 変更前 (commit `a17fca6fb`) | 変更後 (commit `945cf6010`) |
|---|---|---|
| `18100cc50` | `MISSING IMPORT RtlCaptureContext` | `MISSING IMPORT RtlLookupFunctionEntry` |
| `18103d218` | `MISSING IMPORT RtlCaptureContext` | `MISSING IMPORT RtlLookupFunctionEntry` |
| `18100ca28` | `MISSING IMPORT SetUnhandledExceptionFilter` | `MISSING IMPORT SetUnhandledExceptionFilter` (変化なし) |

- `18100ca28` の import 名は **`SetUnhandledExceptionFilter`**。SlateCore の IAT には `UnhandledExceptionFilter` と `SetUnhandledExceptionFilter` の両方があるが、この関数が呼ぶのは後者。issue 本文と親付録 (`REPORT_APPENDIX_1922.md` §4) の「`UnhandledExceptionFilter`」は誤り。
- `RtlLookupFunctionEntry` は unwind 経路。#4362 (ICALL-103・`RaiseException 0xe06d7363` の unwind) の範囲。

## 4. fa_sweep 実測

測定 commit: `945cf6010` (コードを変えた最後の commit)。変更前は `a17fca6fb` (main) で測定。

手順 (両 commit とも同一手順):

```
bash tools/ott/native/build.sh               # [native/build] OK work/libottnative.so
bash tools/icall/fa_route_build.sh           # [fa_route] OK: fa_route.cjs
bash tools/icall/diff/fa_sweep.sh 8 60       # funcs 131 ...
```

| 項目 | 変更前 `a17fca6fb` | 変更後 `945cf6010` | 差分 |
|---|---|---|---|
| funcs | 131 | 131 | 0 |
| bit一致 | 56 | 56 | 0 |
| native crash/timeout | 65 | 65 | 0 |
| wasm のみ err | 9 | 9 | 0 |
| 値の不一致 | 1 | 1 | 0 |
| 所要 (`real`) | 1m13.067s | 1m12.605s | — |
| load average (sweep 前後) | 0.37 / 0.81 | 0.18 / 0.77 | — |

関数単位の差分: `sort` した sweep.jsonl の `diff` は 0 行 (全 131 関数の結果が変化なし)。

コード差分 (`git diff a17fca6fb 945cf6010 -- tools/ott tools/icall`):

```
 tools/ott/native/ott_native.c | 16 ++++++++++++++++
 1 file changed, 16 insertions(+)
```

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `SetUnhandledExceptionFilter` (1 関数: `18100ca28`) | fail-fast のまま | #4529 (ICALL-104・子) |
| `RtlLookupFunctionEntry` (2 関数: `18100cc50`・`18103d218`) | `RtlCaptureContext` 追加後の fail-fast 先。unwind 情報が要る | #4362 (ICALL-103・既存) |
| `RaiseException 0xe06d7363` 経路 (6 関数) | fail-fast のまま | #4362 (ICALL-103・既存) |
| SIGSEGV (未計数) | 既存 | ICALL-55 (#2009) |

## 6. 再現

```
bash tools/ott/native/build.sh
bash tools/icall/fa_route_build.sh
bash tools/icall/diff/fa_sweep.sh 8 60
python3 tools/icall/diff/fa_cmp.py 18100cc50 --n 8   # MISSING IMPORT RtlLookupFunctionEntry
python3 tools/icall/diff/fa_cmp.py 18100ca28 --n 8   # MISSING IMPORT SetUnhandledExceptionFilter
```
