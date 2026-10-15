# PY-106 (#2909): 例外型 `[[[0x15e1140]]]` (sink 0xd82daf) の型名を確定 (#2809 の残り)

親: #2809 (PY-91)。前段: `tools/python/REPORT_PY91.md` §7・§10。既知類型との関係: 該当なし (lift 作業ではない。PE の静的読みと boot harness の監視 slot の追加のみ)。

## 結論

- **型名 (静的に確定)**: sink 0xd82daf の例外型は `[[[0x15e1140]]]` (load 3 段)。束縛関数 0xc395a0 が slot `0x16b8488` に格納する名前は **`PyExc_RuntimeError`** (`lea` 0xc39ceb → resolver 0x4235f0 → store 0xc39cf7)。呼出しは `[rbx]` (slot `0x16b8408` = `PyErr_SetString`)。
- **実行時の観測 (受入 1): 未達**。lift した FLEngine の boot (unit 209 で停止) では束縛関数が走らず、slot `0x16b8488` は停止時点まで 0。型名を実行時に読めていない (§2)。boot 停止後に束縛関数を直接走らせる試み (§2-2) も、LoadLibrary 経路で止まり未達。
- **RANGE (-4) の照合 (受入 2): 不一致**。repo の写像 `fl_api.h:35` (FL_E_RANGE → IndexError) は、FL の sink の型 (静的に RuntimeError) と一致しない。sink は -1〜-9 の全分岐で共通なので、FL は code によって型を変えない (§3)。
- 実装は行わない (受入 3)。変更は検算スクリプト・boot の監視 slot の追加・REPORT 系のみ。

## 受入条件の判定

| # | 受入条件 (#2909) | 判定 | 根拠 |
|---|---|---|---|
| 1 | 実行時に slot `0x15e1140` の指す型名を観測し REPORT に残す (観測方法と値) | **未達** | §2。観測方法と値 (束縛 slot は 0 のまま、chain は unit 209 で 0 化) は残した。型名は静的 (§1) に留まる |
| 2 | RANGE の例外型割当を `tools/python/provider/fl_api.h` と照合して REPORT に残す | **達成 (不一致あり)** | §3 |
| 3 | 実装は行わない | 達成 | 変更は `exc_type_chain.py`・`fle_boot.c`/`fle_boot.mjs` の監視追加・REPORT 系 |

## 1. 静的な確定 (PE 直読み・検算)

`block00031_PE.bin` (`fl-win64` を `$RUNNER_TEMP/fl-win64` に展開)。

| 項目 | VA | 値・内容 |
|---|---|---|
| chain の起点 (.data) | `0x15e1140` | 値 `0x16b8488` (束縛 slot の番地) |
| sink の load 3 段 | `0xd82daf` `mov rcx,[rip+0x85e38a]` → `0xd82db6` `mov rcx,[rcx]` → `0xd82db9` `mov rcx,[rcx]` | `rcx = [[[0x15e1140]]]` |
| 呼出し | `0xd82dbc` `mov rdx,rax` (msg)、`0xd82dbf` `mov rbx,[0x15e49b8]` (値 `0x16b8408`)、`0xd82dc6` `call [rbx]` | `[rbx]` = PyErr_SetString (slot `0x16b8408` の束縛名) |
| 束縛 (型) | `0xc39ceb` `lea rdx` → UTF-16 `PyExc_RuntimeError` (`0xc3ab2a`)、`0xc39cf2` `call 0x4235f0`、`0xc39cf7` `mov [rip+0xa7e78a],rax` (→ `0x16b8488`) | 名前 = `PyExc_RuntimeError` |
| 束縛 (呼出し) | slot `0x16b8408` = `PyErr_SetString` (`analysis/pybind/pybind_map.tsv`) | |
| IndexError の slot | `0x16b83f8`: rip 相対の参照は束縛 store 1 件 (`0xc39b3d`) のみ | FL 本体は `PyExc_IndexError` を読まない |

- 型の読み方: `0x16b8488` は束縛で resolver の戻り値が入る slot。sink の 3 段 load は、その戻り値が**型変数の番地**であること (2 段目で `[R]` を読んで型オブジェクトを得る) を要求する。resolver 0x4235f0 の data 名に対する挙動は未読 (推定)。
- 検算: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/exc_type_chain.py` → 5 項目 `OK`・`RESULT PASS fails=0` (real 0.09 s、n=3)。
- 直接実行の測定 (§2-2): 測定 commit `f4d462ad5` (プローブ追加のみ。boot の経路は不変)。`FLE_PY106_BIND=1 FLE_BOOT_TAG=py106 FLE_BOOT_RUNS=negctl bash tools/flelift/boot/fle6_measure.sh` → rc 0。lift 82 s・clang plain 102 s・boot 24 s (boot 開始時 load `1.82 1.18 0.71`)。units_run 209/942・IPP 判定 ok。`FLEBOOT_PY106B` は exit・名前 0 件 (§2-2)。
- 測定 commit から本 REPORT の commit までのコード差分: `git diff f4d462ad5 HEAD -- tools/flelift/boot tools/python/analysis/flapi` の出力は 0 行 (本 commit は REPORT のみ)。
- 束縛関数 0xc395a0 の呼出し元は `0xc3b3a2` の 1 件 (`.text` 全域の `e8` rel32 走査)。その上位の起動経路は未追跡。
- **REPORT_PY91 §7 の訂正**: 同節の `rcx = *(*(0x15e1140))` は 2 段と書いたが、実際は 3 段 (上表)。PY91 §7 は式だけ直した。

## 2. 実行時の観測 (lift した FLEngine の boot harness)

- 方法: `tools/flelift/boot/fle6_measure.sh` (gen → x64c lift → clang plain → boot、ネガコン `FLE_IPP=0`) を `FLE_BOOT_TAG=py106 FLE_BOOT_RUNS=negctl` で実行。監視 slot (`fle_boot.c` の `g_py_watch`) に `0x15e1140`・`0x16b8488`・`0x16b8250` (`Py_NewInterpreterFromConfig` の束縛 slot。束縛が走ったかの指標) を追加。停止後に `FLEBOOT_PY106` (chain の値) を出す (`fle_boot.mjs`)。
- 測定 commit: **`c8f80c7f5`** (`feat(flapi): add RANGE exception-type chain check and boot probe (PY-106, #2909)`)。コードを変えた最後の commit。
- 差分 0 の証跡: `git diff c8f80c7f5 HEAD -- tools/flelift/boot tools/python/analysis/flapi` の出力は 0 行 (本 REPORT と DOC_MAP・PY91 §7 の文言だけが後の commit)。
- 実測 (commit `c8f80c7f5`・並列 1・load 開始時 `0.20 0.63 0.43`): real 3 分 17.4 秒 (lift 81 s・clang plain 84 s・boot negctl 26 s)。

| 項目 | 値 |
|---|---|
| boot | units_run 209 / 942、stopped_at 209、boot_threw `exit` (`MessageBoxA` → `exit(0)`。PY-123 §2 と同じ停止点) |
| `FLEBOOT_PY106` (停止時) | chain `[0x15e1140]` = `0x0`、slot `0x16b8488` = null (chain が 0 のため読まない)、`0x16b8250` = `0x0` |
| 監視 events (`FLEBOOT_PY123`) | `0x15e1140`: unit 0・site 0 (fle_run 直前) で `0x0 → 0x16b8488` (PE 値と一致) / unit 209・site 8 (GetMem(0x74) 直前) で `0x16b8488 → 0x0`。`0x16b8488`・`0x16b8250`: unit 0 の初期 snapshot の 0 から一度も変わらない |
| IPP 判定 (negctl) | `ok:true` (従来どおり) |
| 起動 KPI (`tools/flelift/boot/REPORT.md`) | 前後で不変: 通過 unit 209 / 942 (PY-123 の測定と同じ) |

- 読み: (a) 監視 slot の初期値は PE の値どおり (`0x15e1140 → 0x16b8488`)。(b) 束縛 slot `0x16b8488`・`0x16b8250` は boot の unit 1〜209 で一度も書かれない。束縛関数 0xc395a0 は boot で走っていない。(c) unit 209 で `0x15e1140` が 0 になる。PY-123 §2-2 の undo 管理 global (`0x15e1c78`・`0x15e4790`) と**同じ時点・同じ site** で、同じ fill 経路 (PY-123 §2-5 の `f_6a7b70`) と推定 (直接の書込み元は未特定)。
- **結論**: この harness では型名の実行時の値は観測できない。束縛の前提 (0xc395a0 の実行) が boot の外にあるためで、停止点を越えて Python 初期化まで進める必要がある (§6)。

### 2-2. 束縛関数の直接実行 (試行・未達)

- 方法: `fle_boot.c` の `fle_py_bind_probe` が boot 停止後 (summary の書出しの後) に `fle_run(0xc395a0)` を 1 回実行する。プローブ中だけ (a) `LoadLibraryW("Python312")` の load hook が擬似 hmod `0x7f0e0000` を返し、(b) `GetProcAddress` は名前ごとに cell (データ変数の番地) を返す。cell の中身は型トークン `0x7f300000 + i`。束縛された名前は `fle_py_bind_name` で読む。`FLE_PY106_BIND=1` のときだけ動き、boot の経路は変えない。出力は `results/boot_summary_<tag>_<label>_py106bind.json` (`FLEBOOT_PY106B`・`FLEBOOT_PY106RING`)。
- 結果 (測定 commit `f4d462ad5`): `FLEBOOT_PY106B` は `threw: exit (code 0)`、束縛された名前は 0 件。`GetProcAddress` に 1 度も届かず、slot `0x16b8488` は 0 のまま。`FLEBOOT_PY106RING` (直近 dispatch) の末尾は `0xc395a0` の 1 件だけで、以後の dispatch は無い。
- 読み (PE の逆アセンブルと実測): `0xc395a0` は先頭で `[0x16b85c8]` (hmod) を見て、0 なら `0x6539e0` (Python312 のローダ) を呼ぶ。ローダは内部の `0x653660` で、post-boot の状態では null の関数ポインタを踏む (`[fleboot][ff] dispatch(0) -> ret 0`)。そのあと `MessageBoxA` → `exit` (site `0x412a12`) に入る。load hook は 1 度も呼ばれない。
- 別案 (不成立): ローダを飛ばして `0xc395d1` (hmod 判定の後) から始める試みは、`0xc395d1` が lift の関数入口でないため `unlifted` (target `0xc395d1`) で止まった。
- 結論: 束縛を boot の外で走らせる経路は、ローダ内部の null 呼出しで塞がれている。型名の実行時の値は、この段階では得られない (受入 1 は未達のまま)。



## 3. RANGE (-4) と repo の写像 (受入 2)

| 対象 | 写像・文言 | 出典 |
|---|---|---|
| repo: 写像表 | `FL_E_RANGE = 4` → IndexError。enum の注記は「実エンジンの数値は未確認」(暫定値) | `tools/python/provider/fl_api.h:26`・`:35` |
| repo: Python 側 | `_ERR[4] = IndexError`、`raise _ERR.get(code, RuntimeError)(msg)` | `tools/python/src/fl_api.py:18`・`:135` |
| repo: テスト | `range` は `["IndexError", "Index out of range"]` を期待 | `tools/python/tests/provider_check.mjs:171` |
| FL: -4 の分岐 | `0xd82c97` `je 0xd82d3c` → `0xd82d3c` で文言 `"Index out of range"` (VA `0xd82e8c`) を `[rbp+0x38]` に入れ、`jmp 0xd82da6` | PE 逆アセンブル |
| FL: 共通 sink | `0xd82da6` (`call 0x414000`) → `0xd82daf` の `PyErr_SetString([[[0x15e1140]]], msg)` | §1 |
| FL: 他の分岐 | -1〜-3 (`0xd82cfe`・`0xd82d13`・`0xd82d28`・`0xd82d3a`)、-5〜-8 (`0xd82d4c`・`0xd82d5e`・`0xd82d70`・`0xd82d82`・`0xd82d94`)、-9 以下 (`0xd82da1` から直下) も全て `0xd82da6` へ入る | PE 逆アセンブル |

- **照合の結論: 不一致**。repo は RANGE を IndexError にするが、FL の sink は RANGE を含む全分岐で同じ型 (静的には `PyExc_RuntimeError`) を使う。
- 補足: (a) FL は code によって例外型を変えない。repo の code 別写像 (1 → ValueError、4 → IndexError、5 → TypeError) は、FL の sink に対応しない。(b) repo の code (1〜8) と FL の status (-1〜-9) は別の数値で、対応はまだ未確定 (`fl_api.h` の注記どおり)。(c) REPORT_PY125 の `-2` の RuntimeError (`Operation unsafe at current time`) は、同じ sink の型と整合する。(d) REPORT_PY73 の「-4 → IndexError」は repo の写像を書いたもので、FL の型の確認ではない。
- 再確認: `PyExc_IndexError` の slot `0x16b83f8` は FL 本体から rip 相対で読まれない (`pe_rip_refs.py 16b83f8` は 1 件 = 束縛 store `0xc39b3d`)。絶対参照は未検査。

## 4. 検証

- 静的検算: `exc_type_chain.py` → PASS (§1)。
- `pe_rip_refs.py 16b83f8`: real 33.8 s (1 件)。
- boot: §2。測定 commit `c8f80c7f5` で実行し、同じ値を得た (作業ツリーで先に回した 1 回目とも一致)。

## 5. 変更範囲

- 追加: `tools/python/analysis/flapi/exc_type_chain.py` (5 項目の検算)、本 REPORT、`docs/DOC_MAP.md` の索引行。
- 変更: `tools/flelift/boot/fle_boot.c` (`g_py_watch` を 3 → 6 件)、`tools/flelift/boot/fle_boot.mjs` (`FLEBOOT_PY106` 行の追加)、`tools/python/REPORT_PY91.md` §7 (式の訂正と結論への参照)。
- 変更なし: `provider/`・`host/`・`tests/`・`src/` (受入 3)。

## 6. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実行時の型名 (`PyExc_*` の実体) の観測 (受入 1 の残り) | 静的には `PyExc_RuntimeError` と確定したが、実行時の確認は未達。直接実行 (§2-2) はローダ 0x653660 の null 呼出しで止まる | #2909 (open のまま残す。再開条件: (a) ローダ 0x6539e0 → 0x653660 の post-boot の null 呼出し元を特定して解消する、または (b) boot 中に束縛関数 0xc395a0 (呼出し元 `0xc3b3a2`) へ到達する) |
| repo の RANGE → IndexError (`fl_api.h:35`・`fl_api.py:18`・`provider_check.mjs:171`) と FL の型 (RuntimeError) の不一致 | Python 側で RANGE の型が FL と食い違う。直すと tests も直す | 実行時の確認 (上の行) の後に、写像の修正を別 issue で扱う (PM 判断)。未確定の段階では直さない |
| boot の unit 209 で `.data` の `0x15e1140` が 0 になる (PY-123 の undo global と同じ時点) | 停止点で chain を読めない | `tools/python/REPORT_PY123.md` §2-5 (fill 経路。#3090 が追う) |
| FL の status (-1〜-9) と repo の code (1〜8) の数値対応 | 写像の根拠 | `tools/python/REPORT_PY61.md` §4-2 (#2026) の既存の未解決 |

## 7. 再現

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64
tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $FL_WIN64_DIR --wildcards '*block00031_PE.bin'
python3 tools/python/analysis/flapi/exc_type_chain.py
python3 tools/python/analysis/flapi/pe_rip_refs.py 16b83f8
FLE_BOOT_TAG=py106 FLE_BOOT_RUNS=negctl timeout 900 bash tools/flelift/boot/fle6_measure.sh
grep -E 'FLEBOOT_PY106|FLEBOOT_PY123' tools/flelift/work/boot/run_py106_negctl.log
```
