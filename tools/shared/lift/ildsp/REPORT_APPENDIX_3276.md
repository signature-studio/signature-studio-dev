# ildsp WaveformColouring: vptr 格納先と helper 到達の native 確定 (T-SH-59 / #3276)

親: #3216 (T-SH-52)。静的解析の未解決 (`REPORT.md` §5-4・§5-5) を、機械語を native 実行して確かめた結果。
`REPORT.md` §5-4 の 2 件の vptr 格納先 (スタック上と推定) と、helper `0x1aedc0`・`0x1b6f4c` の正常系到達が対象。

測定 commit (コードを変えた最後の commit): `9c55235ba` (main 取り込みの merge と、レビュー対応の `native_ref_wc.c` の修正)。初版は `ee6c5d010` (`native_image.py`・`native_ref_wc.c` を追加)。main 取り込みの merge で、main 側の `native_ref.c` (#2529) と同じパスで衝突したため、本 PR の harness を `native_ref_wc.c` に改名した (main 側は変更していない)。

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
  - IAT を stub に差し替える (上限 `MAXIAT` = 128 件。超えたら停止する)。`HeapAlloc` は calloc、`GetProcessHeap` は非 0、`RtlPcToFileHeader` は ImageBase、`RaiseException` は記録して停止、それ以外は 0 を返し件数を記録する。
  - 到達の記録は int3。元の 1 byte を退避して 0xCC にし、trap で rcx・rax・rsp・戻り先を記録し、1 命令だけ単歩して 0xCC を戻す。
- ケース:
  - `normal`: WC CreateInstance `0x1ac470` を呼ぶ (HeapAlloc 成功)。
  - `alloc_fail`: 同じ呼び出しで HeapAlloc が NULL を返す。
  - `alloc_m1`: alloc `0x1ac9c0` を size = -1 で直接呼ぶ (`0x1ad028` 経路を通すため)。

## 実測 (測定 commit `9c55235ba`)
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
- 実行時間: 3 回とも 5 ms (`date +%s%N` の差。プロセス起動を含む。測定前後の load average (1 分) は 0.05 → 0.05)。rc 0 ×3。3 回の stdout は `cmp` で完全一致。出力は repo 外 (`$RUNNER_TEMP/ildsp_3362/c9c/run{1,2,3}.txt`)。
- 再測定の手順 (本 HEAD): `FL_WIN64_DIR=<展開先> python3 tools/shared/lift/ildsp/native_image.py --out-dir <一時dir>` → `gcc -O1 -no-pie -o native_ref tools/shared/lift/ildsp/native_ref_wc.c` → `native_ref image.bin iat.txt` (3 回)。
- 既存の検算も測定 commit `9c55235ba` で再実行した (出力は `$RUNNER_TEMP` 側。`tools/**/work/` は使わない)。`ildsp_closure.py` rc 0 (WaveformColouring: 70 関数・2,757 命令・SIMD 23.8%・間接 19)。`ildsp_wc_dispatch.py` rc 0 (5.534 s。間接の内訳は vcall 1・IAT 16・画像内ポインタ 2・計 19)。`ildsp_wc_dispatch_check.py` rc 0 (`ALL OK`、0.317 s)。
- ビルド: `gcc -O1 -Wall -no-pie` で警告 0・rc 0 (旧版は未使用の `find_iat` で `-Wunused-function`)。
- IAT 上限の試験 (測定 commit `9c55235ba`): IAT 129 件 (73 件 + 56 件の追加行) は `iat: more than 128 imports` で rc 2 (停止)。IAT 128 件 (73 件 + 55 件。`MAXIAT` ちょうど) は rc 0 で、stdout の本体は 73 件のときと一致 (1 行目のヘッダの件数を除く)。追加行は画像末尾の RVA `0x446000` 以降に置いた (本体の出力が変わらなかったため、この経路では読まれていない)。ASan は ImageBase の固定配置と衝突するため使わなかった。
- main 側の `tools/shared/lift/ildsp/native_ref.c` (#2529) は origin/main とバイト一致で、`gcc -O1` でビルドできた (rc 0)。本 PR はこのファイルに触れていない。

## ネガティブコントロール / 陽性対照
- `0x1b6f4c`・`0x1aedc0`・`0x16475a` は、alloc 失敗 (alloc_fail / alloc_m1) で到達する。normal で 0 回なのは、bp が効かないからではない。normal で同じ機構の bp `0x1ac4b4` が 1 回 hit している。
- `0x1cb5e0` の thunk は、harness で rax が 0 (CRT の new handler 未設定) のため最初は SIGSEGV した。trap で rax を 0 を返す stub に差し替えて解消した。この差し替えは例外 path を通すための harness 側の仮定。normal では実行されない (0 回) ため、正常系の結論には影響しない。

## 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| harness の IAT は stub (HeapAlloc = calloc 等)。実 FL の heap・TLS・CRT は再現していない。normal で helper が 0 回なのは「HeapAlloc が成功する」前提の結果 | 正常系の結論の前提 | 本 issue の範囲外。差分テスト (T-SH-52 #3216) の入力定義で扱う |
| `RaiseException` の先 (catch 先) は未追跡 (停止点で止めた) | trap 化か stub 化かの判断 | #5793 (T-SH-155) |
| 残り 8 instance と WC 70 関数の lift・native 全バイト差分 (#2484 の受入 2・3) | 本 issue の範囲外 | T-SH-52 #3216 |
| issue 本文の検証方法 `tools/shared/lift/ildsp/lift_wc.sh all` は repo に存在しない | 検証手順が再現できない。本 PR では harness を直接実行した (`native_image.py` → `native_ref`) | 本 PR の本文に記載 |

## コード差分の証跡
- `git diff 9c55235ba HEAD -- tools/shared/lift/ildsp/native_ref_wc.c tools/shared/lift/ildsp/native_image.py`: 本付録の commit 時点で空 (差分 0)。測定 commit (`9c55235ba`) 以降はコードに変更がないため、再測定は不要 (`docs/WORKFLOW.md` §6)。

## 10. imp_RaiseException の扱い — T-SH-154 (#5789)
- 判断: **据え置き** (`wc_glue.c` の `imp_RaiseException` は `STUB_RET(0)` のまま)。CreateInstance 側 (`ci_iat.c`・RaiseException を記録して exit 3 で停止) とは統一しない。統一すると WaveformColouring の既存の測定値 (`REPORT_APPENDIX_3216.md` §7・PASS 64/64) が変わるおそれがあるため。統一するなら、先に差分テストの値が変わらないことを示す (#5789 の受入 2 の条件)。
- 食い違いの扱い: 同じ IAT 名 (`RaiseException`) に停止規約が二つ並ぶ。WaveformColouring 側は 0 を返して続行し、CreateInstance 側は停止する。正常系では両方とも 0 回 (本ファイルの `§実測` の表) なので、現時点の測定には影響しない。例外 path の catch 先の扱いも未解決で、起票先は #5793 (T-SH-155)。
- 再測定 (測定 commit `07cc0f7c2`・コードは同 commit の `wc_glue.c` のコメント 1 行のみ変更): `FL_WIN64_DIR=<fl-win64 展開先> EMSDK_ENV=<emsdk_env.sh (emsdk 6.0.12)> bash tools/shared/lift/ildsp/lift_wc.sh all`。
  - 本検査 `ok`: x64c `functions 60・insns 2656・unsup {}・traps 0`、wasm 172,024 B、`wc diff cases=64 PASS=64 FAIL=0 excluded=0`、rc 0、2.22 s、load 0.72 0.35 0.14 → 0.72 0.35 0.14。
  - ネガコン `neg-cmp` (wasm 結果を反転): `FAIL=64`、rc 1 (期待どおり FAIL を検出)。`ALL OK`。
  - コード差分の証跡: `git diff 07cc0f7c2 HEAD -- tools/shared/lift/ildsp ':!tools/shared/lift/ildsp/REPORT*.md'` の出力は 0 行 (本節の REPORT の追記後も、実行コードの差分は 0)。`docs/WORKFLOW.md` §6 により、再測定は不要。

## 11. RaiseException (0xe06d7363) の catch 先 — T-SH-156 (#5795)
- 結論: **except 本体 `0x1b8eb1` は、この例外の catch 先ではない**。`0x1b8e68` の唯一の scope は filter `0x1ccb00` が `0xc0000005`・`0xc000001d` (AV・不正命令) しか許可せず、`0xe06d7363` を許可しない。try 範囲も `call 0x1be130` (`ldmxcsr` だけの関数) の 1 命令で、C++ 例外を送出しない。よって `0x1b8e68` の except 6 件 (§7-7b) は C++ 例外 path の到達先から外れる。
- 例外を投げる helper `0x1aedc0` (`0xe06d7363`・args[0] `0x19930520` を組み立てる) の .text 内の rel32 直接 call/jmp は 8 件 (byte 走査)。うち 6 件は EHANDLER を持たない関数内、2 件 (`0x1b006a`・`0x1b056d`) は関数 `0x1afbd4`・`0x1b009c` 内で、いずれも handler `0x1acf00`。
- 未解決 (本 issue のチェックリストに残す): 呼出元 2 件 (`0x1b006a`・`0x1b056d`) は handler `0x1acf00` を持つ関数 (`0x1afbd4`・`0x1b009c`) の中にある。`0x1acf00` は scope 表の形式ではない (MSVC の frame handler の形) ため、本道具では filter と catch 先を確定していない。残りの呼出元 6 件は EHANDLER を持たない関数内で、上位フレームの catch は未確定。
- 方針への影響: `imp_RaiseException` の据え置き (§10) は変えない。0x1b8e68 の except 本体が 0xe06d7363 の catch 先でないことは、§10 の停止規約の統一の判断材料になる。
- 道具: `tools/shared/lift/ildsp/seh_catch_check.py` (`FL_WIN64_DIR` の PE を読み、0x1b8e68 の scope・filter の許可コード・0x1aedc0 の rel32 呼出元 8 件を出す)。
- 実測 (素材 `fl-win64` 26.1.7.5653 の `block24360_PE.bin`): 出力は `UNWIND 0x3f2d94 EHANDLER handler=0x1aebb4 scope_count=1` / `SCOPE try=[0x1b8eaa,0x1b8eb1) ... target=0x1b8eb1` / `FILTER 0x1ccb00 accepts codes: 0xc0000005, 0xc000001d` / `FILTER accepts 0xe06d7363: False` / `DIRECT rel32 call/jmp to 0x1aedc0 ... 8`。
