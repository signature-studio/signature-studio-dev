# ildsp WaveformColouring: vptr 格納先と helper 到達の native 確定 (T-SH-59 / #3276)

親: #3216 (T-SH-52)。静的解析の未解決 (`REPORT.md` §5-4・§5-5) を、機械語を native 実行して確かめた結果。
`REPORT.md` §5-4 の 2 件の vptr 格納先 (スタック上と推定) と、helper `0x1aedc0`・`0x1b6f4c` の正常系到達が対象。

測定 commit (コードを変えた最後の commit): `ee6c5d010` (`tools/shared/lift/ildsp/native_image.py`・`native_ref_wc.c` を追加)。main 取り込みの merge で、main 側の `native_ref.c` (#2529) と同じパスで衝突したため、本 PR の harness を `native_ref_wc.c` に改名した (main 側は変更していない)。

## 結論
- 正常系 (HeapAlloc 成功) では、helper `0x1aedc0` と new handler `0x1b6f4c` は **0 回** (native で未到達)。
- WC instance の vptr 格納 `0x1ac4b4` は 1 回 (格納先は heap)。返り値の instance の vptr は `0x3e01b0` のまま (WC vtable)。WC vtable slot 3 の値は `0x1a9de0` (`REPORT.md` §5-2 と一致)。
- WC 以外の vptr 格納 2 件は、どちらも例外オブジェクトへの格納で、格納先はスタック上 (格納関数の入口 rsp から +0x28)。
  - `0x1acfff` (vptr `0x3d2778`): alloc 失敗 path A (`0x1ad008`)。
  - `0x16475a` (vptr `0x3d27a0`): alloc 失敗 path B (`0x1ad028`、size = -1)。
- 3 件目と数えられていた `0x1acfe0` (`jmp 0x1801b34a8` の stub) は、3 ケースとも 0 回。格納は無い。
- 例外 path では helper `0x1aedc0` が 1 回ずつ到達し、`RaiseException` (code `0xe06d7363`、ExceptionInformation[0] = `0x19930520`) を呼ぶ。

## 方法
- 素材: `fl-win64.tar.zst` から `extracted/block24360_PE.bin` だけを展開 (`tar --zstd -xf ... --wildcards '*block24360_PE.bin'`、2 秒)。
- `native_image.py`: PE を RVA 配置の image (4,485,120 B = SizeOfImage 0x447000) と IAT 一覧 (73 件) にする。ImageBase は 0x180000000。
- `native_ref_wc.c`:
  - image を ImageBase に固定配置 (`MAP_FIXED_NOREPLACE`)。絶対 VA の vtable・reloc はそのまま使える。
  - IAT 73 件を stub に差し替える。`HeapAlloc` は calloc、`GetProcessHeap` は非 0、`RtlPcToFileHeader` は ImageBase、`RaiseException` は記録して停止、それ以外は 0 を返し件数を記録する。
  - 到達の記録は int3。元の 1 byte を退避して 0xCC にし、trap で rcx・rax・rsp・戻り先を記録し、1 命令だけ単歩して 0xCC を戻す。
- ケース:
  - `normal`: WC CreateInstance `0x1ac470` を呼ぶ (HeapAlloc 成功)。
  - `alloc_fail`: 同じ呼び出しで HeapAlloc が NULL を返す。
  - `alloc_m1`: alloc `0x1ac9c0` を size = -1 で直接呼ぶ (`0x1ad028` 経路を通すため)。

## 実測 (測定 commit `ee6c5d010`)
| bp (RVA) | normal | alloc_fail | alloc_m1 | 意味 |
|---|---:|---:|---:|---|
| `0x1ac4b4` | 1 | 0 | 0 | WC vptr 格納 (instance, heap) |
| `0x1b6f4c` | 0 | 1 | 1 | new handler (alloc 失敗時のみ) |
| `0x1ad008` | 0 | 1 | 0 | throw path A (rbx != -1) |
| `0x1acfe8` | 0 | 1 | 0 | 格納関数 A の入口 |
| `0x1acfff` | 0 | 1 | 0 | vptr `0x3d2778` の格納 (stack rsp+0x28) |
| `0x1ad028` | 0 | 0 | 1 | throw path B (rbx == -1) |
| `0x164740` | 0 | 0 | 1 | 格納関数 B の入口 |
| `0x16475a` | 0 | 0 | 1 | vptr `0x3d27a0` の格納 (stack rsp+0x28) |
| `0x1acfe0` | 0 | 0 | 0 | jmp stub (格納なし) |
| `0x1cb5e0` | 0 | 1 | 1 | new handler の thunk (`jmp rax`) |
| `0x1aedc0` | 0 | 1 | 1 | helper (throw 側) |
| 停止 | returned | RaiseException | RaiseException | |

- normal の返り値: vptr `0x3e01b0` (WC)、slot 3 `0x1a9de0`。
- alloc_fail と alloc_m1 の `RaiseException`: code `0xe06d7363`、args[0] = `0x19930520` (一致 1)。
- 実行時間: 3 回とも 5〜6 ms (`date +%s%N` の差。プロセス起動を含む。測定中の load average (1 分) は 0.08〜0.09)。3 回の stdout は `cmp` で完全一致。出力は repo 外 (`$RUNNER_TEMP/ildsp_3362/run{1,2,3}.txt`)。
- 再測定の手順 (本 HEAD): `FL_WIN64_DIR=<展開先> python3 tools/shared/lift/ildsp/native_image.py --out-dir <一時dir>` → `gcc -O1 -no-pie -o native_ref tools/shared/lift/ildsp/native_ref_wc.c` → `native_ref image.bin iat.txt` (3 回)。
- 既存の検算 (`ildsp_closure.py`・`ildsp_wc_dispatch.py`・`ildsp_wc_dispatch_check.py`) は本 HEAD では再実行していない。この 3 本は `c4a0297c` から HEAD まで変更がない (`git diff c4a0297c HEAD --` が空)。前回 (`c4a0297c`) の結果 (rc 0・`ALL OK`) がそのまま有効。
- main 側の `tools/shared/lift/ildsp/native_ref.c` (#2529) は origin/main とバイト一致で、`gcc -O1` でビルドできた (rc 0)。本 PR はこのファイルに触れていない。

## ネガティブコントロール / 陽性対照
- `0x1b6f4c`・`0x1aedc0`・`0x16475a` は、alloc 失敗 (alloc_fail / alloc_m1) で到達する。normal で 0 回なのは、bp が効かないからではない。normal で同じ機構の bp `0x1ac4b4` が 1 回 hit している。
- `0x1cb5e0` の thunk は、harness で rax が 0 (CRT の new handler 未設定) のため最初は SIGSEGV した。trap で rax を 0 を返す stub に差し替えて解消した。この差し替えは例外 path を通すための harness 側の仮定。normal では実行されない (0 回) ため、正常系の結論には影響しない。

## 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| harness の IAT は stub (HeapAlloc = calloc 等)。実 FL の heap・TLS・CRT は再現していない。normal で helper が 0 回なのは「HeapAlloc が成功する」前提の結果 | 正常系の結論の前提 | 本 issue の範囲外。差分テスト (T-SH-52 #3216) の入力定義で扱う |
| `RaiseException` の先 (catch 先) は未追跡 (停止点で止めた) | trap 化か stub 化かの判断 | T-SH-52 #3216 |
| 残り 8 instance と WC 70 関数の lift・native 全バイト差分 (#2484 の受入 2・3) | 本 issue の範囲外 | T-SH-52 #3216 |
| issue 本文の検証方法 `tools/shared/lift/ildsp/lift_wc.sh all` は repo に存在しない | 検証手順が再現できない。本 PR では harness を直接実行した (`native_image.py` → `native_ref`) | 本 PR の本文に記載 |

## コード差分の証跡
- `git diff ee6c5d010 HEAD -- tools/shared/lift/ildsp/native_ref_wc.c tools/shared/lift/ildsp/native_image.py`: 本付録の commit 時点で空 (差分 0)。測定 commit (`ee6c5d010`) 以降はコードに変更がないため、再測定は不要 (`docs/WORKFLOW.md` §6)。
