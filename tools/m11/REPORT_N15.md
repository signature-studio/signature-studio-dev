# M11 REPORT §16 (#490 [M11-N15]) の詳細
本体 `REPORT.md` §16 の付録 (250 行上限のため分割)。
## 16. #490 [M11-N15]: main HEAD の 4c3baa4 / faee5b6 状態の実測

起点 `6e5c8dac` (origin/main)。4 vCPU・load 0.4〜0.95・`m11_gen_ir2.sh` で IR を作成 (ldfix=applied, qstore=applied)。PE=`FL_WIN64_DIR` の block00031_PE.bin。

| 構成 | units_run | 停止 (通常起動) | survey ok/trap(oom)/miss/noproc/clobber | e2e 所要 | load |
|---|---|---|---|---|---|
| main HEAD (boot5 あり) | 53 | `memory access out of bounds` @ function_8c6530 | 870/25(1)/46/1/0 | 43.9 s (1 回目) / 48.3 s (2 回目) | 0.69〜0.95 |
| ネガコン: boot5 除去 (IR 再生成) | 52 | 同一関数 (function_8c6530) | 869/25(1)/47/1/0 | 48.3 s | 0.78 |

- 受入 1 (完走実測): 達成。main HEAD の m11_e2e.sh は exit 0。
- 受入 2 (二分): **未達**。faee5b6 の m11_win.c / m11_ov.c 部分を `git apply -R` で外そうとしたが、main の後続変更 (417b70 / 409470 / 410b10 系) と衝突し適用できなかった。退行の切り分けは未実施。main では退行が解消済みのため当面の実害はない。
- 受入 3 (kind 12): 達成 (main #496 で 416720 の間接 call 込みで転記済み, `m11_ov.c` case 12)。kind 12 を実行する unit の実測は未。
- 受入 4 (ネガコン): **部分**。boot5 除去で units_run 53→52、survey ok 870→869、miss 46→47。停止 trap の関数は同一のため「元の停止 (22 unit) に戻る」は成立しない。boot5 (25 関数) の寄与は 1 unit に留まる。
- 環境注記: emsdk の `cache/` が packer 所有で emcc が書けず、`sudo chown -R runner:runner /opt/emsdk/upstream/emscripten/cache` で解消 (CI 環境では要対応)。capstone/pefile は `pip install --user` で導入。
