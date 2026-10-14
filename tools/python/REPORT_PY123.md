# PY-123 (#3028): boot 停止時点の undo 管理オブジェクトと安全判定の実行時値を実測する

親: #2998 (PY-123)。前段: #2978 (PY-120)・PE 解析は #2998 の issue コメント (2026-10-14 21:08Z)。
前 run: #3055 (merge 済み・測定 commit `3064340a`・boot 停止時点の 0 を確認)。
既知類型との関係: 未判定。0 化の書込みは直接の RIP 相対書込みではなく、`docs/DEFECTS.md` の既知類型に当たるかは未確認。

## 結論

- **受入条件 1〜3 は未達。** boot は unit 209 (1-based) で `QuickFontCache DLL not found!` の MessageBox を出し、直後に GetMem(0x74) が NULL を返して `Error` → `exit(0)` で止まる。停止時点の undo 系 global は boot 中のこの経路で 0 になっており、起動直後の pos/count・安全判定 VA・singleton の値として使えない。
- **0 化の位置 (今回の新結果)。** 監視 slot `0x15e1c78`・`0x15e4790` は `fle_run` 直前には PE の値 (`0x16bb068`・`0x141d6b8`) を持つ。0 になるのは **unit 209 の中**。unit 208 までの unit 境界・memset・FastMM の GetMem/FreeMem では変化しない。最初に検出したのは **GetMem 呼出し直前 (site 8)**。よって 0 化は FastMM の中ではなく、unit 209 の生成コードのうち MessageBoxW の後から GetMem 呼出しまでの区間で起きる。
- 書込みは直接の `mov [rip+slot], reg` ではない (`pe_xref` の書込み 0 件と整合)。書込み命令そのものは未特定。
- singleton `0x16b82e0` は boot 中ずっと 0 (PE 上も 0 で、変化なし)。
- したがって boot 停止点の値は実 FL の起動直後の状態ではない。受入条件 1〜3 を測るには、unit 209 の `QuickFontCache DLL not found!` 経路を抜けた boot が要る (§5)。

## 受入条件の判定

| # | 受入条件 (issue #3028) | 判定 | 根拠 |
|---|---|---|---|
| 1 | undo 管理オブジェクトの起動直後の `+0x20` (pos)・`+0x24` (count) を実測 | **未達** | slot `0x15e1c78` は unit 209 で 0 に変わるため、起動直後のオブジェクトが測れない (§2-2)。 |
| 2 | 安全判定述語 (`[obj+0x98]`・`[obj+0x88]`、`obj = [[0x15e4790]+8]`) の関数 VA | **未達** | `0x15e4790` も unit 209 で 0 (§2-2)。`obj` を辿れない。 |
| 3 | 成功時戻り値 singleton `[0x16b82e0]` が `None` か | **未達** | 値は boot 全体で 0 (未設定)。`None` か否かは判定できない。 |
| 4 | 上 3 件を本ファイルに書き、#2998 の実装を再開する | **部分** | 本ファイルに書いた。1〜3 が未達のため #2998 の実装は未再開。 |

## 1. 静的な値 (PE 直読み・実測)

`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` (`fl-win64` を `tar --zstd -xf` で展開。7 秒)。`block00031_PE.bin` (22,227,016 B、ImageBase `0x400000`)。

| VA | セクション | file 内の u64 | 備考 |
|---|---|---|---|
| `0x15e1c78` (undo 管理 global) | `.data` (raw `0x11e0678`) | `0x16bb068` | 非 0 |
| `0x15e4790` (安全判定 global) | `.data` (raw `0x11e3190`) | `0x141d6b8` | 非 0 |
| `0x141d6b8` | `.data` | `0x0` | `obj` の候補先は file 上 0 |
| `0x16b82e0` (戻り値 singleton) | `.bss` | (file 実体無し) | 静的には決まらない |

- `analysis/flapi/pe_xref.py 15e1c78` (`.text` 全域): 読出し 768 件・**書込み 0 件**。
- `analysis/flapi/pe_slot_writers.py 15e1c78`: `[reg+8]` への書込み候補 1 件 (`0xf698af`)。undo への書込みとは断定しない (前 run の判断どおり)。

## 2. boot 停止時点の実行時値 (前 run の測定、commit `3064340a`)

| 実行 | units_run / total | slot `0x15e1c78` | pos / count | slot `0x15e4790` | `[0x16b82e0]` | IPP 判定 |
|---|---|---|---|---|---|---|
| shim 有 (`FLE_IPP=1`) | 209 / 942 | `0x0` | null / null | `0x0` | `0x0` | `ok:false` (既知 NG #2702) |
| ネガコン (`FLE_IPP=0`) | 209 / 942 | `0x0` | null / null | `0x0` | `0x0` | `ok:true` |

正の対照 (`tools/flelift/boot/undo_probe_check.mjs`): 敷設前 `0x0` → `_fle_data_install` 直後 `0x16bb068`・`0x141d6b8` → `_fle_init` 直後も同じ。boot 本体の途中で 0 に戻る。

## 2-2. unit 単位の変化点 (今回の測定、測定 commit `b1b95f97`)

`tools/flelift/boot/fle_boot.c` の `py_watch` (計測のみ・挙動は変えない) で、監視 slot の値が変わった時点を記録した。site の意味: 0 = `fle_run` 直前 / 1・2 = unit dispatch の直前・直後 / 3 = memset 直後 / 4 = ExitProcess / 5 = MessageBoxW / 6 = GetMem 直後 / 7 = FreeMem 直後 / 8 = GetMem 呼出し直前。

| 実行 | 変化点 (unit 1-based, site, slot, old → new) | 件数 |
|---|---|---|
| shim 有 | unit 209, site 8, `0x15e1c78` `0x16bb068`→`0x0`・`0x15e4790` `0x141d6b8`→`0x0` | 5 (うち site 0 の snap 3) |
| ネガコン | 同上 | 5 |

- 開始時 (site 0): `0x15e1c78` = `0x16bb068`・`0x15e4790` = `0x141d6b8`・`0x16b82e0` = `0x0`。
- unit 1〜208 の dispatch 前後、memset (site 3)、FastMM の GetMem・FreeMem (site 6・7) では変化なし。
- unit 209 の MessageBoxW (site 5) では変化なし (site 5 の検査時点ではまだ非 0)。
- unit 209 の GetMem 呼出し直前 (site 8) で 0。GetMem の戻り値は 0 (失敗)。
- 終了 (site 4, `ExitProcess`, call site `0x412a12`) では既に 0。
- 戻り番地の連鎖 (`exit-stack`): `0x412a12` → `0x409433` (`fle_ov_getmem` の失敗経路 → `Error`) → `0x412a4f` (GetMem 呼出し元) … → `0x410380`。

### 2-3. 0 化の位置の逆アセンブル (unit 209 の GetMem 呼出し元)

`pe_disasm.py 0x412960 120` (GetMem 呼出し元 `0x412a4f` の直前まで)。直接の 0 書込み `mov qword ptr [rip+0x11d82bf], 0` (VA `0x4129be`) はあるが、書込み先は `0x15eac88` で対象外。対象 slot (`0x15e1c78`) を指す RIP 相対の書込みは、この区間には見つからなかった。書込みは間接 (ポインタ・計算アドレス経由) と見られる。

## 3. 解釈 (今回の範囲)

- boot 停止点の 0 は、unit 209 の error 経路 (`QuickFontCache DLL not found!` → GetMem 失敗 → `Error` → `exit`) の途中で起きる。正常な起動の途中ではない。
- `QuickFontCache` 系の既存の追跡: #154 (lift)・#2220 (FT 解決経路の到達性)。本 run では DLL 読込みの経路は確認していない。

## 4. 変更内容 (本 PR)

| ファイル | 変更 |
|---|---|
| `tools/flelift/boot/fle_boot.c` | `py_watch` (監視 slot の変化点の記録・site 0〜8) と、`fle_py_ev_*` の export。`imp_ExitProcess`・`imp_MessageBoxW`・`fle_ov_getmem`・`fle_ov_freemem`・`fle_ov_initunits`・`imp_memset` に検査点を追加。`imp_ExitProcess` は stderr に戻り番地の連鎖を出す |
| `tools/flelift/boot/fle_boot.mjs` | 変化点を `FLEBOOT_PY123` 行と summary の `boot.py_events` に出す |
| `tools/flelift/boot/build.sh` | `_fle_py_ev_ptr`・`_fle_py_ev_n`・`_fle_py_ev_over` を export に追加 |
| `tools/flelift/boot/results/boot_summary_py123.json`・`boot_summary_py123_negctl.json` | 測定 (`b1b95f97`) の summary |
| `tools/python/REPORT_PY123.md` | 本ファイル |

- KPI (起動に関わる変更のため。`docs/WORKFLOW.md` §7): FLEngine 起動の dispatch 数 (units_run) は **前 209 / 後 209** (`tools/flelift/boot/REPORT.md` §2・§9 と一致)。最初のウィンドウ: **無し** (unit 209 の MessageBox → `exit(0)`)。boot の挙動は計測の追加で変わらない (GetMem/FreeMem は shim 有 2314 / 1199・ネガコン 1891 / 776 で、前 run の `results/boot_summary_fle6*.json` と一致)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 209 の GetMem 呼出し直前までの区間で、slot `0x15e1c78`・`0x15e4790` を 0 にする命令 (間接書込み) の特定 | 0 化の原因が lift 由来の silent miscompile か、unit 209 の経路で実機でも起きるかが不明 | #3028 に残す (次 run。`fle_chk` (FLE_CHK 変種) の住所検査か、unit 209 の逆アセンブルで書込み命令を探す) |
| unit 209 の `QuickFontCache DLL not found!` 経路 (DLL 読込みの失敗) | この経路を抜けない限り、起動直後の状態 (受入条件 1〜3) を測れない | #3028 に残す。関連: #154・#2220 (QuickFontCache 系)。DLL 読込みの経路は未確認 |
| 安全判定述語の VA・singleton の中身 | `restoreUndoLevel` の分岐・戻り値の判定ができない | #3028 (上の 2 件が解消した後に測る) |
| boot が unit 209 で止まる | 起動直後の状態に届かない | 既存の追跡: `tools/flelift/boot/REPORT.md` §9 (#2700 系) |
| shim 有の IPP 判定 NG (`ok:false`) | 本測定の shim 有の判定が通らない (変更前から) | #2702 |

## 6. 検証範囲

- 範囲内: boot の unit 単位の変化点 (shim 有・ネガコンの 2 条件、各 1 回・測定 commit `b1b95f97`)。開始時の値 (site 0)・unit 209 の GetMem 呼出し直前の値 (site 8)・停止点 (site 4)。
- 範囲外: 起動直後 (QuickFontCache 経路を抜けた後)。安全判定の実体。singleton の中身。0 化を行う命令の特定。
- 未実施: `provider/build.sh` (emcc)・`node tests/general_diff.mjs`・`node tests/provider_check.mjs`・`FL_ENGINE=wasm node tests/all_tools.mjs` (実装が無いため走らせていない)。

## 7. 再現

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64
FLE_BOOT_TAG=py123 FLE_BOOT_RUNS="shim negctl" bash tools/flelift/boot/fle6_measure.sh   # 約 2 分 12 秒 (§2-2)
python3 tools/python/analysis/flapi/pe_disasm.py 0x412960 120                            # §2-3
```

- 生成物は `tools/flelift/work/boot/` (gitignore)。結果 JSON は `tools/flelift/boot/results/` にコミット済み。
- 測定 (`b1b95f97`): real 2 分 12.2 秒 (lift 49 s・clang 49 s・boot shim 14 s・negctl 14 s)。load average (開始) `1.07 1.02 0.61`。並列 1 本。
