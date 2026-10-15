# 付録: icall #4362 (ICALL-103) — RaiseException 0xe06d7363 (C++ 例外) の到達位置の記録

> 親: #1922 (ICALL-52)。前付録: `REPORT_APPENDIX_1922.md`。子: #4565 (ICALL-105・unwind 本体)。

## 1. 結論

- 受入条件 1 (unwind の実装): **未達**。unwind 本体 (`RtlUnwindEx`・`RtlVirtualUnwind`・`RtlLookupFunctionEntry`) は #4565 (ICALL-105) へ移した。
- 受入条件 2 (6 関数の fail-fast 理由の記録): **達成**。§2。
- 受入条件 3 (`fa_sweep.sh 8 60` の件数を前後測定): **部分達成**。§3。変更前は `808d0e54f`、変更後は `220e79252` で測った (差分は診断出力の 14 行のみ)。同一 tree の厳密な前後測定は未実施。件数は一致した。

## 2. 6 関数の fail-fast 理由 (単独実行)

測定 commit: `220e79252` (本 PR の唯一のコード変更)。

`python3 tools/icall/diff/fa_cmp.py <va> --n 2` の stderr (1 行目):

| VA | fail-fast 行 |
|---|---|
| `1803b3fc0` | `RaiseException(0xe06d7363) 到達 — fail-fast (unwind 未実装) magic=0x19930520 obj=0x7fffffffbba0 throwinfo=0x181258050 throw_site_rva=0x102f7b8` |
| `1803b5b60` | 同 magic・throw_site_rva。throwinfo=`0x1812589f8` |
| `180cbd860` | 同 magic・throw_site_rva。throwinfo=`0x1812589f8` |
| `18100cf60` | 同 magic・throw_site_rva。throwinfo=`0x1812589c0` |
| `181011058` | 同 magic・throw_site_rva。throwinfo=`0x1812591b0` |
| `18102f728` | 同 throw_site_rva。引数 magic=`0x1994000` (直接呼び出し時の入力値のため、実 throw ではない) |

静的解析 (`objdump` / `.pdata`):

- 6 関数は `.pdata` の UNWIND_INFO で EH/UH フラグが 0。自身に handler は無い。
- 5 関数は `0x18102f728` (`EH_MAGIC 0x19930520` を積んで `RaiseException` を呼ぶ throw 関数) を直接 call する。
- throw 関数 `0x18102f728` の呼び出し元は画像内に 439 箇所。catch 側は呼び出し元の上流にあり、単独実行の closure の外。

## 3. fa_sweep 件数 (変更前 `808d0e54f` / 変更後 `220e79252`)

| 測定 commit | 件数 |
|---|---|
| `808d0e54f` (main 基準・変更前) | funcs 131 / bit一致 55 / native crash/timeout 65 / wasm のみ err 9 / 値の不一致 2 |
| `220e79252` (変更後・本 PR) | funcs 131 / bit一致 55 / native crash/timeout 65 / wasm のみ err 9 / 値の不一致 2 |

2 つの測定は同一 tree ではない。両 commit の差は `tools/ott/native/ott_native.c` の診断出力 14 行 (`git diff --stat` で確認) のみで、件数は一致した。同一 tree の厳密な前後測定は未実施。

`REPORT_APPENDIX_1922.md` §5 の値 (bit一致 56 / 値の不一致 1) とは一致しない。1922 の測定は別 base (`3d397cb4`) のため、比較対象にしていない。

所要: 1m13.8s (`real 1m13.760s`)。sweep 前後の load average は 0.42 → 0.83。

コード差分 (`git diff 808d0e54f 220e79252 -- tools/ott/native tools/icall`):

```
 tools/ott/native/ott_native.c | 14 +++++++++++---
 1 file changed, 11 insertions(+), 3 deletions(-)
```

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unwind 本体 (`RtlUnwindEx`・`RtlVirtualUnwind`・`RtlLookupFunctionEntry`・guest handler 呼び出し) | 6 関数が `RaiseException` で fail-fast のまま | #4565 (ICALL-105・子) |
| `RtlCaptureContext` (2 関数)・`UnhandledExceptionFilter` (1 関数) | fail-fast のまま | #4338 (ICALL-100) |

## 5. 再現

```
bash tools/ott/native/build.sh
bash tools/icall/fa_route_build.sh
bash tools/icall/diff/fa_sweep.sh 8 60
python3 tools/icall/diff/fa_cmp.py 1803b3fc0 --n 2
```
