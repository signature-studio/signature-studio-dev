# #5164: lift-8 の差分 71 関数の code index → 名前 → VA 対応表 (name section 付き実測)

親: #4547 (本表は `KH656_REPORT_APPENDIX_1821.md` §8.1 から参照する)。REPORT の 250 行上限のため分割移動。

## 1. 測定条件

- 生成: `python3 tools/targets/kilohearts/license/scripts/kh5164_name_map.py` (`emcc -g2` で name section を出す。`-sEMIT_NAME_SECTION` は内部設定で指定できない)。
- 素材: `fl-win64` / `plugins-kilohearts` (installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `work/winpkg/HeartCore.core_64`) / `toolchain-emsdk` (emcc) / `toolchain-retdec`。
- wasm (name 付き・`-g2`): off 56,278 B・sha256 `7d799b40…a122` / on 56,371 B・sha256 `deb15155…d3de`。name 無し build (既存) は off 54,394 B・`7ba79e65…8c7707` / on 54,487 B・`3d2bc6fd…e77287` (sha 一致は script が `code 本体は name 無し build と一致: True` (on/off とも・関数 96) で確認)。
- 測定 commit: `ffc8840a9` (script を追加した commit)。
- コード差分の証跡: `git diff ffc8840a9 HEAD -- tools/targets/kilohearts/license/lift tools/targets/kilohearts/license/lic_build.py tools/targets/kilohearts/license/lic_config.json tools/targets/kilohearts/license/scripts` の出力は 0 行 (本 run・HEAD `9cdce47c7` 時点)。測定から HEAD までの変更は本付録と `KH656_REPORT_APPENDIX_1821.md`・`docs/DOC_MAP.md` の文書のみ。
- 実測 (本 run・HEAD `90c42bcf4` 上で実行・rc=0): 壁時計 1 分 13.9 秒 (`time`・内訳は user 1 分 22 秒)。load 平均は実行後の `uptime` で 0.14 / 0.39 / 0.20 (実行中の load は未採取)・nproc 4・RAM 15 GB。

## 2. 区分別の集計 (表から数え直した値)

| 区分 | 関数数 | off 本体 B | 差分 B |
|---|---|---|---|
| kh_<VA> | 7 | 25,991 | 2,653 |
| function_<VA> | 41 | 9,697 | 692 |
| VA なし (runtime・libc・生成補助) | 23 | 12,675 | 426 |
| 合計 | 71 | 48,363 | 3,771 |

- `sum(diff_B)` = 3,771 = 3,771 B (`REPORT` §8.1 の sha 差の code 差分と一致)。
- LIFT8 の 8 VA との対応 (表の LIFT8 列で確認): `kh_<VA>` 7 件の VA は LIFT8 の 8 件から `180054bd0` を除いた 7 件と一致 (7/7)。`180054bd0` は `kh_` 名を持たず、`function_180054bd0` (code_idx 12・48 B・差分 6 B) のみ。
- 同じ VA に 2 行あるもの (`180045130`・`18004c780`・`1800524e0`・`1800b4ac0`・`1800b4ae0`・`1800b4b10`・`180ef7fc0`): `kh_<VA>` と `function_<VA>` が別の code index で、off_B は一致しない (例: `kh_180045130` 36 B / `function_180045130` 645 B)。両行は wasm 上では別の関数 body (別の code index) で、合計 3,771 B はそれぞれの body の合計。同じ元関数が二つの名前で出ているのか、別の body なのかは本表からは判定しない (未確認)。

## 3. 対応表 (71 行・code index 昇順)

| code_idx | name | VA | LIFT8 | 区分 | off_B | diff_B |
|---|---|---|---|---|---|---|
| 1 | `kh_180045130` | 180045130 | Y | kh_<VA> | 36 | 3 |
| 2 | `kh_18004c780` | 18004c780 | Y | kh_<VA> | 1400 | 114 |
| 3 | `kh_1800524e0` | 1800524e0 | Y | kh_<VA> | 2918 | 298 |
| 5 | `kh_1800b4ac0` | 1800b4ac0 | Y | kh_<VA> | 393 | 42 |
| 6 | `kh_1800b4ae0` | 1800b4ae0 | Y | kh_<VA> | 137 | 15 |
| 7 | `kh_1800b4b10` | 1800b4b10 | Y | kh_<VA> | 1352 | 123 |
| 8 | `kh_180ef7fc0` | 180ef7fc0 | Y | kh_<VA> | 19755 | 2058 |
| 9 | `function_180045130` | 180045130 | Y | function_<VA> | 645 | 57 |
| 10 | `function_18004c780` | 18004c780 | Y | function_<VA> | 1292 | 101 |
| 11 | `function_1800524e0` | 1800524e0 | Y | function_<VA> | 1292 | 101 |
| 12 | `function_180054bd0` | 180054bd0 | Y | function_<VA> | 48 | 6 |
| 13 | `function_1800b4ac0` | 1800b4ac0 | Y | function_<VA> | 1292 | 101 |
| 14 | `function_1800b4ae0` | 1800b4ae0 | Y | function_<VA> | 746 | 69 |
| 15 | `function_1800b4b10` | 1800b4b10 | Y | function_<VA> | 1292 | 101 |
| 16 | `function_180ef7fc0` | 180ef7fc0 | Y | function_<VA> | 1292 | 101 |
| 21 | `function_180005000` | 180005000 | - | function_<VA> | 55 | 2 |
| 22 | `function_180005c30` | 180005c30 | - | function_<VA> | 55 | 2 |
| 23 | `function_180005c50` | 180005c50 | - | function_<VA> | 55 | 1 |
| 24 | `function_18000caf0` | 18000caf0 | - | function_<VA> | 55 | 2 |
| 25 | `function_18000f590` | 18000f590 | - | function_<VA> | 55 | 1 |
| 26 | `function_1800448e0` | 1800448e0 | - | function_<VA> | 55 | 2 |
| 27 | `function_1800541b0` | 1800541b0 | - | function_<VA> | 55 | 1 |
| 28 | `function_18006ac50` | 18006ac50 | - | function_<VA> | 55 | 2 |
| 29 | `function_180112a30` | 180112a30 | - | function_<VA> | 55 | 1 |
| 30 | `function_18012e420` | 18012e420 | - | function_<VA> | 55 | 2 |
| 31 | `function_18012fba0` | 18012fba0 | - | function_<VA> | 55 | 2 |
| 32 | `function_180130560` | 180130560 | - | function_<VA> | 55 | 1 |
| 33 | `function_18013b9e0` | 18013b9e0 | - | function_<VA> | 55 | 2 |
| 34 | `function_18013c9c0` | 18013c9c0 | - | function_<VA> | 55 | 1 |
| 35 | `function_1803965a0` | 1803965a0 | - | function_<VA> | 55 | 2 |
| 36 | `function_180396b00` | 180396b00 | - | function_<VA> | 55 | 1 |
| 37 | `function_180396f40` | 180396f40 | - | function_<VA> | 55 | 2 |
| 38 | `function_18065bbd0` | 18065bbd0 | - | function_<VA> | 55 | 1 |
| 39 | `function_180c433b0` | 180c433b0 | - | function_<VA> | 55 | 2 |
| 40 | `function_180c44b50` | 180c44b50 | - | function_<VA> | 55 | 2 |
| 41 | `function_180c44d20` | 180c44d20 | - | function_<VA> | 55 | 1 |
| 42 | `function_180c44d30` | 180c44d30 | - | function_<VA> | 55 | 2 |
| 43 | `function_180c44d50` | 180c44d50 | - | function_<VA> | 55 | 1 |
| 44 | `function_180c47b50` | 180c47b50 | - | function_<VA> | 55 | 2 |
| 45 | `function_180ef8ef0` | 180ef8ef0 | - | function_<VA> | 55 | 1 |
| 46 | `function_180ef92b0` | 180ef92b0 | - | function_<VA> | 55 | 2 |
| 47 | `function_180ef9b70` | 180ef9b70 | - | function_<VA> | 55 | 1 |
| 48 | `function_180f878e0` | 180f878e0 | - | function_<VA> | 68 | 2 |
| 49 | `function_180f8791c` | 180f8791c | - | function_<VA> | 15 | 1 |
| 50 | `function_180f89cf0` | 180f89cf0 | - | function_<VA> | 55 | 2 |
| 51 | `function_180fb5f5c` | 180fb5f5c | - | function_<VA> | 55 | 1 |
| 52 | `function_180fb6124` | 180fb6124 | - | function_<VA> | 55 | 1 |
| 53 | `function_181384040` | 181384040 | - | function_<VA> | 65 | 6 |
| 54 | `kh_stack_ptr` | - | - | VA なし | 8 | 2 |
| 55 | `kh_icall` | - | - | VA なし | 356 | 4 |
| 63 | `__errno_location` | - | - | VA なし | 8 | 2 |
| 64 | `emscripten_get_sbrk_ptr` | - | - | VA なし | 8 | 2 |
| 65 | `_sbrk64` | - | - | VA なし | 143 | 4 |
| 66 | `sbrk` | - | - | VA なし | 100 | 4 |
| 67 | `brk` | - | - | VA なし | 177 | 8 |
| 70 | `emscripten_builtin_malloc` | - | - | VA なし | 4694 | 147 |
| 71 | `prepend_alloc` | - | - | VA なし | 1060 | 30 |
| 72 | `emscripten_builtin_free` | - | - | VA なし | 1674 | 52 |
| 75 | `try_realloc_chunk` | - | - | VA なし | 995 | 22 |
| 80 | `dlvalloc` | - | - | VA なし | 175 | 13 |
| 81 | `dlpvalloc` | - | - | VA なし | 203 | 13 |
| 82 | `dlmallinfo` | - | - | VA なし | 399 | 16 |
| 83 | `dlmallopt` | - | - | VA なし | 202 | 19 |
| 84 | `dlmalloc_trim` | - | - | VA なし | 225 | 16 |
| 86 | `dlmalloc_footprint` | - | - | VA なし | 11 | 1 |
| 87 | `dlmalloc_max_footprint` | - | - | VA なし | 11 | 1 |
| 88 | `dlmalloc_footprint_limit` | - | - | VA なし | 20 | 1 |
| 89 | `dlmalloc_set_footprint_limit` | - | - | VA なし | 56 | 3 |
| 91 | `ialloc` | - | - | VA なし | 535 | 11 |
| 94 | `dispose_chunk` | - | - | VA なし | 1577 | 49 |
| 95 | `setThrew` | - | - | VA なし | 38 | 6 |

## 4. 注記

- `kh_<VA>` 7 件の VA は名前の末尾 16 進 (`kh_` の後) から引いた。LIFT8 との対応は行ごとに上の表で示す (7/7 一致)。
- `function_<VA>` 41 件は export 名から引いた (REPORT §8.1 の既存測定)。
- VA なし 23 件: `emscripten_builtin_*`・`dlmalloc` 系・`dispose_chunk`・`ialloc`・`try_realloc_chunk`・`prepend_alloc`・`sbrk`・`_sbrk64`・`brk`・`emscripten_get_sbrk_ptr`・`__errno_location`・`setThrew` は emscripten/dlmalloc runtime。`kh_stack_ptr` は `lift/gen_stubs_sigs.py`、`kh_icall` は `lift/kh_lower.py` が生成する補助関数 (lift 本体ではない)。名前で確かめた。
