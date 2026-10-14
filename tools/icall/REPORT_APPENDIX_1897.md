# 付録: icall #1897 (ICALL-49) — 引数付き lifted 関数の dispatch table 登録

> 親: #1852 (ICALL-44)。本付録は ICALL-49 の結論を記録する。基準は `REPORT_APPENDIX_1633.md` §4.1・§4.2。

## 1. 結論

- 原因: `ir_flatten.py --table` が 0 引数 `define` だけを `icall_tbl_va` に登録していた。引数付き (`i64 %arg1` 等) の lifted 関数は表に無く、`ott_run` / `__icall_dispatch` の `lookup` が NULL を返して `unknown entry` → `abort()` になっていた。
- 対応: 引数付き関数は、BLK から引数を読んで渡す wrapper (`long long w_<va>(void)`) を生成して登録する。BLK 配置は `icall_rewrite.py` と一致させた (rcx=+0x08, rdx=+0x10, r8=+0x18, r9=+0x20, xmm0..3=+0x28+8k, 第 5 引数以降=+0x100+8k)。
- 結果: 対象 6 関数のうち **5 件が abort から bit 一致 (8/8, wasm_err 0)** に変わった。wasm のみ err は **14 → 9**。
- 未解決 1 件: `180ca1480` は `function_180ca1651` が IR に定義の無い declare のみ (閉包外 callee)。引数付き登録では解けないため、子 issue に切り出す (§4)。

## 2. 測定

測定 commit: `6be1eb20` (`tools/icall/ir_flatten.py` のみ変更。以降のコード変更なし)。
基準 commit: `ba5f2206` (main)。

| 項目 | 値 |
|---|---|
| 素材 | `work-icall` (`rt_freshair-core`)・`work-liftlib`・`plugins-freshair`・`fl-win64`・`toolchain-retdec`・`toolchain-emsdk` |
| `fa_route_build.sh` | 7.5 s (table entries 131、うち wrapper 18) |
| `fa_sweep.sh 8 60` (131 関数) | 1 m 9.9 s、load 0.21 |

前提: `bash tools/ott/native/build.sh` を先に実行する (`libottnative.so` が無いと全件 native crash 扱いになる。§5)。

| 区分 | 基準 (`ba5f2206`) | 測定 (`6be1eb20`) |
|---|---|---|
| bit 一致 | 42 | 47 |
| native crash・timeout | 66 | 66 |
| wasm のみ err | 14 | 9 |
| 値の不一致 | 9 | 9 |

### 2.1 対象 6 関数

| VA | 基準 | 測定 |
|---|---|---|
| 180c8b310 | abort (unknown entry) | bit 一致 (wasm_err 0) |
| 180c9d880 | abort | bit 一致 (wasm_err 0) |
| 180ca1480 | missing `function_180ca1651` | 変化なし (閉包外 callee, §4) |
| 180da3f80 | abort | bit 一致 (wasm_err 0) |
| 18103fd60 | abort | bit 一致 (wasm_err 0) |
| 18106a3ba | abort | bit 一致 (wasm_err 0) |

副次変化: `18105d9fc` は wasm_err 0 のまま値の不一致 (出力値が変化)。table に載ったことによる既存の値不一致の変化で、改善でも悪化でもない。

## 3. 再現

```
bash tools/ott/native/build.sh
bash tools/icall/fa_route_build.sh
bash tools/icall/diff/fa_sweep.sh 8 60
```

前提: `work-icall` (`tools/icall/work/`)・`work-liftlib`・`plugins-freshair` (`fetch.sh` 済み)・`toolchain-retdec`・`toolchain-emsdk`・`fl-win64` (`FL_WIN64_DIR`)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `180ca1480`: `function_180ca1651` が IR に定義の無い declare のみ (閉包外 callee) | wasm_err 8 のまま (missing function) | #1953 (ICALL-53) |
| `180c8b280`・`181057b38`: memory access out of bounds (本 issue の 6 関数の外) | wasm_err 2 / 8 | 未起票 (`REPORT_APPENDIX_1633.md` §4.1 に既記載) |
| `18105d9fc`: 値の不一致 (wasm_err 0 のまま、出力値のみ変化) | 不一致 8/8 のまま | 未起票 (副次変化) |

## 5. 注意

- `fa_cmp.py` は `tools/ott/work/libottnative.so` を要する。無いと全件 `native_err` 扱いで `crash_or_timeout` になる。基準測定で一度これに当たった。
