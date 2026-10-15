# 付録: icall #4529 (ICALL-104) — SetUnhandledExceptionFilter の native IMPL 追加

> 親: #4338 (ICALL-100)。前付録: `REPORT_APPENDIX_4338.md`。子 (未達の unwind 経路): #4362 (ICALL-103)。

## 1. 結論

- 受入条件 1 (`SetUnhandledExceptionFilter` を `tools/ott/native/ott_native.c` の IMPL 表に追加): **達成**。§2。
- 受入条件 2 (`18100ca28` の fail-fast 理由の変化を単独実行で記録): **達成**。§3。fail-fast は `SetUnhandledExceptionFilter` から `UnhandledExceptionFilter` に移った。
- 受入条件 3 (`fa_sweep.sh 8 60` の件数を変更前後の同一 tree で測定): **達成**。§4。件数は変わらなかった (bit一致 55・値の不一致 2)。
- 関数単位の差分は 0 行。`18100ca28` の通過は sweep の判定に現れない (sweep 上では依然 native crash/timeout に含まれる)。

## 2. 実装

`tools/ott/native/ott_native.c`:
- `k_SetUnhandledExceptionFilter`: 前の filter を返し、新しい filter を登録する (初期値 NULL)。filter は呼ばない。
- IMPL 表に `{"SetUnhandledExceptionFilter", k_SetUnhandledExceptionFilter}` を追加。
- `UnhandledExceptionFilter` 本体は未実装 (fail-fast のまま)。別関数として扱う。

コード変更の commit: `c29e2e270`。

## 3. 単独実行 (fail-fast 理由の変化)

`python3 tools/icall/diff/fa_cmp.py 18100ca28 --n 8`

| commit | 出力 |
|---|---|
| 変更前 `636f74907` (origin/main) | `[ott_native] MISSING IMPORT SetUnhandledExceptionFilter — fail-fast` |
| 変更後 `c29e2e270` | `[ott_native] MISSING IMPORT UnhandledExceptionFilter — fail-fast` |

`18100ca28` の本体は `SetUnhandledExceptionFilter(NULL)` の後に `UnhandledExceptionFilter(ExceptionInfo)` を呼ぶ (`work/lift/fa.drc.c` 3216〜3217 行)。次の fail-fast 先は `UnhandledExceptionFilter` で、これは前付録 §3 の「`UnhandledExceptionFilter`」の誤記が指していた経路。`UnhandledExceptionFilter` は本件の範囲外で、起票先は親 #4338 への提案 (§5)。

## 4. fa_sweep 実測

測定 commit: `c29e2e270` (コードを変えた最後の commit)。変更前は `636f74907` (origin/main) で測定。両者とも同一 worktree (`ws-4529`)・同一手順。

手順:
```
bash tools/ott/native/build.sh               # [native/build] OK work/libottnative.so
bash tools/icall/fa_route_build.sh           # [fa_route] OK: fa_route.cjs
bash tools/icall/diff/fa_sweep.sh 8 60       # funcs 131 ...
```

| 項目 | 変更前 `636f74907` | 変更後 `c29e2e270` | 差分 |
|---|---|---|---|
| funcs | 131 | 131 | 0 |
| bit一致 | 55 | 55 | 0 |
| native crash/timeout | 65 | 65 | 0 |
| wasm のみ err | 9 | 9 | 0 |
| 値の不一致 | 2 | 2 | 0 |
| 所要 (`real`) | 1m14.020s | 1m13.768s (HEAD 再測定) | — |
| load average (sweep 後) | 0.78 / 0.54 / 0.27 | 1.03 / 0.74 / 0.40 | — |

注: 前付録 (`REPORT_APPENDIX_4338.md` §4) の基準値は bit一致 56・値の不一致 1 だった。今回の変更前ベースラインは 55・2 で、前付録とは一致しない。原因は未確認 (関数 `0x180c8b280`・`0x180da4030` の判定が変わっている)。本件は同一 tree・同一手順の前後比較のみを根拠にする。

関数単位の差分: `sort` した sweep の `diff` は 0 行 (全 131 関数の結果が変化なし)。

コード差分 (`git diff 636f74907 c29e2e270 -- tools/ott tools/icall`):
```
 tools/ott/native/ott_native.c | 6 ++++++
 1 file changed, 6 insertions(+)
```

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `UnhandledExceptionFilter` (`18100ca28` の次の fail-fast 先) | `18100ca28` は依然 fail-fast | 親 #4338 への提案 (本 PR では未着手。次に進める場合に子を起票) |
| `RtlLookupFunctionEntry` (2 関数: `18100cc50`・`18103d218`) | unwind 情報が要る | #4362 (ICALL-103・既存) |
| `RaiseException 0xe06d7363` 経路 (6 関数) | fail-fast のまま | #4362 (ICALL-103・既存) |
| 前付録との基準差 (bit一致 56 → 55) | 原因未確認。前後比較には影響しない | なし (追跡のみ・未解決表に記載) |

## 6. 再現

```
bash tools/ott/native/build.sh
bash tools/icall/fa_route_build.sh
bash tools/icall/diff/fa_sweep.sh 8 60
python3 tools/icall/diff/fa_cmp.py 18100ca28 --n 8   # MISSING IMPORT UnhandledExceptionFilter
```
