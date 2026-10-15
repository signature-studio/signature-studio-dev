# tools/shared/lift/rex 付録 — REPORT §12 (T-SH-129 / #4833)

## 12. REX の `.data` 書込の到達元 (DllMain) と DllMain の実行方法 — T-SH-129 (#4833, 受入 1)

測定: `tools/shared/lift/rex/writer_chain.py` (静的。lift・実行はしない)。素材 `fl-win64` の `extracted/block24351_PE.bin` のみ使用。
既知類型との関係: 該当なし (静的解析)。

### 12.1 結論 (1 行)
`.data` へ書く stub (0x1c9dc・0x1f4a8) の到達元は DllMain (AddressOfEntryPoint = 0x1fd78) の `reason == 1` (DLL_PROCESS_ATTACH) 経路。DllMain を native と wasm の両側で export より前に 1 回呼ぶ方式 A を採る。ただし DllMain 閉包は movnti 24 箇所 (#3589) を含み、受入 2 (`.data` 比較) はその扱いが決まるまで実行できない。

### 12.2 呼出連鎖 (直接 call / tail jmp を `.text` 全体で走査して実測)
| 段 | 関数 | 呼出元 → 呼出先 (アドレス) |
|---|---|---|
| 0 | DllMain 0x1fd78 | `edx==1` で `call 0x26fb0` (0x1fd94)。続けて `jmp 0x1fc60` (tail, 0x1fdb0) |
| 1 | 0x1fc60 | `call 0x1fb24` が 0x1fcbe・0x1fd00・0x1fd2d の 3 箇所 |
| 2 | 0x1fb24 | `edx==1` のとき `call 0x25410` (0x1fb34)。その戻り値が非 0 なら `call 0x22630` (0x1fb44) |
| 3 | 0x22630 (初期化) | `call 0x1fabc` (0x22636) |
| 4 | 0x1fabc | `call 0x1c9dc` (0x1facd)・`call 0x1f4a8` (0x1fadd) |
| 5 | stub 0x1c9dc / 0x1f4a8 | `mov [rip+X], rcx; ret`。書込先は 0x600d0 / 0x600e0 (`.data` 0x47000〜0x621d8 の内側) |

- `.text` 全走査で、stub 0x1c9dc / 0x1f4a8 の直接呼出は 0x1facd・0x1fadd の 2 箇所のみ。RIP 相対の関数ポインタ参照は無い。
- 0x1fabc の直接呼出は 0x22636 のみ。0x22630 の直接呼出は 0x1fb44 のみ。0x1fc60 の直接呼出は DllMain の tail jmp (0x1fdb0) のみ。
- 逆アセンブルで確認した分岐: 0x1fb24 は `cmp edx,1; jne` で `edx==1` だけ 0x25410 と 0x22630 に進む。0x1fc60 は `edx` の値で 0x1fb24 を呼ぶ条件が分かれる。

### 12.3 閉包の規模 (`writer_chain.py`・命令の到達可能性で数える)
| 入口 | 関数 | 到達命令 | import 名 | movnti | 間接 call/jmp |
|---|---:|---:|---:|---:|---:|
| DllMain 0x1fd78 | 129 | 5,454 | 63 | 24 | 20 |
| 0x22630 (書込経路の初期化) | 48 | 1,324 | 31 | 8 | 9 |
| 0x1fabc (書込 stub 呼出) | 11 | 51 | 1 | 0 | 0 |
| 0x25410 (ゲート) | 1 | 18 | 2 | 0 | 0 |
| 0x26fb0 (DllMain の `edx==1` 前呼出) | 1 | 39 | 5 | 0 | 0 |

- 現行 harness が IAT に敷設しているのは 5 件 (`native_ref.c`: WaitForSingleObject / ReleaseMutex / RtlPcToFileHeader / RaiseException / GetLastError)。名前の完全一致で、DllMain 閉包の import 63 件と重なるのは 3 件。
- `rex_closure.py` (関数全体で数える) の DllMain 閉包は 130 関数・import 64 件。`writer_chain.py` は到達可能な命令だけを数えるため 129 関数・63 件になる。前回 #4833 コメントの「148 関数・65 件」は、どちらの規則とも一致しない古い数値のため使わない。
- movnti の到達: DllMain 閉包の 24 箇所のうち 8 箇所は 0x1c8f0 (関数 0x1c8f0)。0x22630 閉包の movnti 8 箇所も同じ 0x1c8f0 にある。0x1c8f0 の直接呼出元は 0x1f4cb (関数 0x1f4b0) のみ。0x1f4b0 の直接呼出元は 0x1f643 と 0x23c20・0x23c71・0x23ccc・0x23cf7・0x23d26 (関数 0x23b78)。

### 12.4 DllMain の実行方法 (受入 1 の決定)
方式 A (採用): native (`native_ref.c`) と wasm (`rex_glue.c`) の両側で、イメージを読み込んだ後・export を呼ぶ前に DllMain (0x1fd78) を `reason = 1` で 1 回呼ぶ。
- 根拠: `.data` 書込は DllMain の `reason == 1` 経路にだけ現れる (12.2)。書込経路だけを直接呼ぶ方式 (0x22630 や 0x1fabc を直接呼ぶ) は、0x25410 の戻り値や 0x26fb0 の前提を harness で別に作る必要があり、本付録では測っていない。
- 閉包の扱い: DllMain 閉包 129 関数を x64c の対象に含める。movnti 24 箇所を含むため、現行の x64c は到達時に fail-fast する (#3589 の扱いが前提)。
- IAT: 閉包の import 63 件を敷設対象にする。現行 5 件から 60 件以上の追加になる。

### 12.5 未確定 (本付録では断定しない)
- 0x2231c は `xor ecx,ecx` の後に `jmp [rip+0x11e2b]` (スロット 0x3414f) で、この先の値が `.data` に入る (0x1fac2 の `call 0x2231c` の戻り値)。0x3414f は IAT の名前に対応せず、`.rdata` の値 (dword 0x04630c00) の意味は未確定。ここは harness で値を決める必要がある。
- 0x1fc60 の `call r9` は関数ポインタ `[0x39440]` (`.rdata`) を読む。この slot は静的にゼロで IAT にも無いので、ファイル上では呼出を飛ばして 0x1fb24 に進む。実行時に値が入るかは未確認。
- 静的閉包は実行経路の上限。`reason == 1` の正常経路で実際にどの分岐を通るかは、動的確認 (#4834 側) が必要。
- 間接 jmp/call (DllMain 閉包 20・書込経路 9) の先は辿っていない (下限側)。

### 12.6 受入 2 への含意
- 受入 2 (`.data` の全バイト一致) は、DllMain 閉包の movnti 24 箇所 (#3589) の扱いと、0x2231c の値の決め方が決まるまで実行できない。
- 子 #4834 (受入 2・3) は、方式 A・IAT 63 件・movnti の扱い・0x2231c の値を前提にする。

### 12.7 再現
```
FL_WIN64_DIR=<fl-win64 展開先> python3 tools/shared/lift/rex/writer_chain.py --json OUT.json
```
`<fl-win64 展開先>` は `extracted/block24351_PE.bin` を含むディレクトリ (`tar --zstd -xf fl-win64.tar.zst -C <dir> extracted/block24351_PE.bin`)。生成物は `work/` (gitignore)。
