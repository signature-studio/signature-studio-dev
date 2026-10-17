# tools/shared/lift/rex 付録 — REPORT §13 (T-SH-130 / #4834)

## 13. dllmain モードの実測 (`.data` の一致判定) — T-SH-130 (#4834, 受入 2 は未達)

### 13.1 結論 (1 行)
`dllmain` モード (DllMain 後の `.data` を基準にした全バイト比較) は 223 件とも FAIL。native/wasm の不一致は `.data` の 12 バイト (RVA `0x48030`〜`0x4803b`)。別に、同一入力の 2 回実行で `data_base.bin` が変わるバイトが 6 個 (RVA `0x48032`〜`0x4803c`、ASLR 依存)。両者は別の測定で、後者は前者の範囲に含まれない (`0x4803c` が 12 バイトの外)。既定の `ok` は PASS (223/223 一致) のまま。`all` は ALL OK。

### 13.2 測定条件
- 測定 commit: `0403e1a49` (`tools/shared/lift/rex/` の最後のコード変更。HEAD と一致)。
- 素材: `fl-win64` の `extracted/block24351_PE.bin` のみ展開 (`tar --zstd -xf ... --wildcards '*block24351_PE.bin'`)。
- emsdk: 上流 6.0.12 (`git clone --depth 1 https://github.com/emscripten-core/emsdk.git` → `./emsdk install 6.0.12` → `./emsdk activate 6.0.12`)。
- 実行環境: GitHub Actions 上の Linux runner (素材は `[WIN64]` の `fl-win64`)。

### 13.3 実測
| 実行 | 結果 | 数値 | wall | load (start→end) |
|---|---|---|---|---|
| `all` (ok + neg-cmp + neg-ctx + neg-owner + movnti) | ALL OK (rc=0) | 下記 | 12.3 s (`time` の real) | 0.93 0.40 0.15 → 1.39 0.52 0.19 |
| `ok` | PASS | `cases=296 compared=223 match=223 mismatch=0 native_crash_excluded=73`・`writes data=0` | 2 s | 0.93 0.40 0.15 → 0.93 0.40 0.15 |
| `neg-cmp` | FAIL (期待どおり) | `match=222 mismatch=1` (case 2, offset 21) | 3 s | — |
| `neg-ctx` | FAIL (期待どおり) | `match=0 mismatch=223` | 2 s | — |
| `neg-owner` | FAIL (期待どおり) | 一覧 `owner/rex_glue.c owner/rex_side.wasm` ≠ 期待 | 2 s | — |
| `movnti` | PASS | reach 16 件 arena 内で完了 | 3 s | 1.39 0.52 0.19 → 1.39 0.52 0.19 |
| `dllmain` 実行 1 | FAIL | `compared=223 match=0 mismatch=223`・`writes ... data=223` | 2 s | 1.28 0.51 0.19 → 1.28 0.51 0.19 |
| `dllmain` 実行 2 | FAIL | `compared=223 match=0 mismatch=223`・`writes ... data=223` | 2 s | 1.28 0.51 0.19 → 1.26 0.52 0.19 |

`dllmain` の不一致は全件 `.data` の同じ 12 バイト (RVA `0x48030`〜`0x4803b`)。`writes data=223` は DllMain 前の初期 `.data` を基準にした書込の数で、DllMain が `.data` を書くため 0 にならない。

### 13.4 ASLR による 6 バイトの変化 (2 回実行の出力、RVA `0x48032`〜`0x4803c`)
`REX_DATA_BASE_OUT` で書かれる `data_base.bin` (`.data` の先頭 111,064 B) を 2 回の `dllmain` 実行で比較した。
この 6 バイトは「2 回実行で変わる範囲」であり、§13.1 の native/wasm 不一致 (12 バイト) とは別の測定。`0x4803c` は 12 バイト範囲の外なので、6 バイトは 12 バイトに含まれない。両者の包含関係は未測定 (native/wasm 側の不一致バイトを ASLR 無効で測り直していないため、12 バイトとの重なりは主張しない)。

```
$ cmp -l data_base_1.bin data_base_2.bin | wc -l
6
$ cmp -l data_base_1.bin data_base_2.bin
  4147 200  40      # file offset 0x1032 (RVA 0x48032)
  4148  63 302      # 0x1033 (0x48033)
  4149  23 337      # 0x1034 (0x48034)
  4155 177 337      # 0x103a (0x4803a)
  4156 314  75      # 0x103b (0x4803b)
  4157 354  40      # 0x103c (0x4803c)
```
(`cmp -l` の値は 8 進数。)

`setarch x86_64 -R` (ASLR 無効) で同じ 2 回を実行すると、差は 0 バイト (`cmp` が SAME)。したがって 2 回実行の 6 バイトの変化は host のアドレス (ASLR) に由来する。lifter の誤りではなく、比較の基準 (native 側の DllMain 後の `.data`) に host 依存の値が入っている。

### 13.5 判定の扱い
受入 2 (`.data` 全バイト一致) は本 PR では解決しない。一致判定から host 依存のバイトを外すか、決定的な値にするかの判断は PM (#4834)。native/wasm の不一致 12 バイトと ASLR の 6 バイトの関係は、判断の前に測り直す必要がある (本 PR では未測定)。既定案は本 PR では判定を変えず、`dllmain` は FAIL のまま残し、`all` には含めない。

### 13.6 再現
```
FL_WIN64_DIR=<fl-win64 展開先> EMSDK_ENV=<emsdk 6.0.12 の emsdk_env.sh> bash tools/shared/lift/rex/lift_x64c.sh all
FL_WIN64_DIR=<fl-win64 展開先> EMSDK_ENV=<同> bash tools/shared/lift/rex/lift_x64c.sh dllmain    # 2 回実行
cmp -l tools/shared/work/lift/rex/data_base.bin <2 回目の data_base.bin> | wc -l                 # 6 (ASLR 有効)
setarch x86_64 -R bash tools/shared/lift/rex/lift_x64c.sh dllmain                              # ASLR 無効で 2 回 → cmp 差 0
```
`<fl-win64 展開先>` は `extracted/` を含むディレクトリ。生成物は `tools/shared/work/lift/rex/` (gitignore)。

### 13.7 測定後のコード差分 (差分 0 の証跡)
`git diff 0403e1a49 HEAD -- tools/shared/lift/rex ':(exclude)*.md'` の出力: 行数 0 (コード差分なし。md の変更は REPORT.md の 1 行参照と本付録のみ)。
