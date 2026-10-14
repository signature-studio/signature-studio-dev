# PY-123 (#3028): boot 停止時点の undo 管理オブジェクトと安全判定の実行時値を実測する

親: #2998 (PY-123)。前段: #2978 (PY-120)・PE 解析は #2998 の issue コメント (2026-10-14 21:08Z)。
前 run: #3055 (merge 済み・測定 commit `3064340a`・boot 停止時点の 0 を確認)。
命名: 親の ID は PY-123。#3028 のタイトルは `[PY-137]` だが、PR・REPORT・commit は親に合わせて PY-123 で統一する (#3055 と同じ慣行)。
既知類型との関係: 未判定。0 化の書込みは直接の RIP 相対書込みではなく、`docs/DEFECTS.md` の既知類型に当たるかは未確認。

## 結論

- **受入条件 1〜3 は未達。** boot は unit 209 (1-based) で止まる。停止点は `MessageBoxA` (lpText 空・自動 IDOK) → `exit(0)` (call site `0x412a12`) で、既存の記録 (`tools/flelift/boot/REPORT.md` §9・§10、`REPORT_APPENDIX_2702.md` §D) と一致する (§2-4)。停止の直前に GetMem(0x74) が FastMM への dispatch で 0 を返し、`fle_ov_getmem` の失敗経路 (`f_409730` = Error) に入る。停止時点の undo 系 global は 0 になっており、起動直後の pos/count・安全判定 VA・singleton の値として使えない。
- **0 化の位置.** 監視 slot `0x15e1c78`・`0x15e4790` は `fle_run` 直前には PE の値 (`0x16bb068`・`0x141d6b8`) を持つ。0 になるのは **unit 209 の中**。unit 1〜208 の unit 境界・memset・FastMM の GetMem/FreeMem では変化しない。最初に 0 を観測したのは **GetMem(0x74) 呼出し直前 (site 8・GETMEM seq 2312)**。その前の検査点 (site 5・6・7) では非 0 だった (§2-2)。
- **QuickFontCache は停止点ではない。** `[fleboot][MessageBoxW] text='QuickFontCache DLL not found!'` は shim 有の stderr 8117 行 (GETMEM seq 1849 の直前) に 1 回出るが、boot はその後も GetMem を続けて進む。停止は末尾の `MessageBoxA` である (§2-4)。前版 (本 PR の初版) の「MessageBoxW → GetMem 失敗 → exit」は途中の MessageBoxW を停止点と取り違えた記述で、本版で訂正した。
- 書込みは直接の `mov [rip+slot], reg` ではない (`pe_xref` の書込み 0 件と整合)。書込み命令そのものは未特定 (§2-3)。
- singleton `0x16b82e0` は boot 中ずっと 0 (PE 上も 0 で、変化なし)。
- したがって boot 停止点の値は実 FL の起動直後の状態ではない。起動直後の状態を測るには、unit 209 の停止経路 (GetMem(0x74) の失敗) を越える boot が要る (§5)。

## 受入条件の判定

| # | 受入条件 (issue #3028) | 判定 | 根拠 |
|---|---|---|---|
| 1 | undo 管理オブジェクトの起動直後の `+0x20` (pos)・`+0x24` (count) を実測 | **未達** | slot `0x15e1c78` は unit 209 の GetMem(0x74) 直前で 0 に変わるため、起動直後のオブジェクトが測れない (§2-2)。 |
| 2 | 安全判定述語 (`[obj+0x98]`・`[obj+0x88]`、`obj = [[0x15e4790]+8]`) の関数 VA | **未達** | `0x15e4790` も同じ位置で 0 (§2-2)。`obj` を辿れない。 |
| 3 | 成功時戻り値 singleton `[0x16b82e0]` が `None` か | **未達** | 値は boot 全体で 0 (未設定)。`None` か否かは判定できない。 |
| 4 | 上 3 件を本ファイルに書き、#2998 の実装を再開する | **部分** | 本ファイルに書いた。1〜3 が未達のため #2998 の実装は未再開。 |

## 1. 静的な値 (PE 直読み・実測)

`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` (`fl-win64` を `tar --zstd -xf` で展開。7 秒)。`block00031_PE.bin` (22,227,016 B、ImageBase `0x400000`)。前 run の実測。

| VA | セクション | file 内の u64 | 備考 |
|---|---|---|---|
| `0x15e1c78` (undo 管理 global) | `.data` (raw `0x11e0678`) | `0x16bb068` | 非 0 |
| `0x15e4790` (安全判定 global) | `.data` (raw `0x11e3190`) | `0x141d6b8` | 非 0 |
| `0x141d6b8` | `.data` | `0x0` | `obj` の候補先は file 上 0 |
| `0x16b82e0` (戻り値 singleton) | `.bss` | (file 実体無し) | 静的には決まらない |

- `analysis/flapi/pe_xref.py 15e1c78` (`.text` 全域・5,022,467 命令・35.0 秒): 読出し 768 件・**書込み 0 件** (`stores=0`)。`mov [rip+slot], reg` の直接書込みは PE に無い。
- `analysis/flapi/pe_slot_writers.py 15e1c78` (36.0 秒): `[reg+8]` への書込み候補 1 件 (`0xf698af`)。`0xf698af` の周辺は `call 0xf82530` で得た確保先に `[rax+8]`・`[rax+0x10]` を書く別レコードの初期化と読め、undo 管理オブジェクトへの書込みとは断定しない (逆アセンブル確認: `tools/python/analysis/flapi/pe_disasm.py 0xf69840 70`)。本 run (HEAD `f57b7dff`) で再確認: `0xf69893 call 0xf82530` → `0xf6989b mov rax, rbx` の後、`0xf698af mov dword ptr [rax + 8], ecx`・`0xf698b5 mov dword ptr [rax + 0x10], ecx`。`rbx` は確保直後の戻り値で、その配列に `rbx` を格納する (`0xf698db`)。

## 2. boot 停止時点の実行時値 (前 run の測定、commit `3064340a`)

測定 commit: **`3064340a`** (`feat(flelift): probe undo slots after boot (PY-123, #3028)`)。コードを変えた最後の commit。
`git diff 3064340a HEAD -- tools/flelift/boot` の出力は空 (差分 0)。

測定コマンド (コミット済み HEAD で実行):

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64
time timeout 900 bash tools/flelift/boot/fle6_measure.sh
```

- 所要: 実測 real 2 分 13.8 秒 (user 3 分 12.6 秒・sys 19.7 秒)。工程: gen-A 5 s・lift 51 s (x64c・closure 2・8 shard)・clang-plain 48 s (8 shard・peak RSS 2.2〜2.7 GB/本)・boot 15 s・negctl 14 s。
- load average: 開始時 `0.22 0.59 0.37`、clang 中 `1.61 0.94 0.52`、boot 中 `1.54 0.96 0.53`。並列 1 本 (1 回のみ)。

| 実行 | units_run / total | boot_threw | slot `0x15e1c78` | pos `+0x20` / count `+0x24` | slot `0x15e4790` | `[0x16b82e0]` | IPP 判定 |
|---|---|---|---|---|---|---|---|
| shim 有 (`FLE_IPP=1`) | 209 / 942 | `exit` | `0x0` | null / null | `0x0` | `0x0` | `ok:false` (既知 NG) |
| ネガコン (`FLE_IPP=0`) | 209 / 942 | `exit` | `0x0` | null / null | `0x0` | `0x0` | `ok:true` |

- 判定: **boot 停止時点で 3 つの global とも 0。** shim の有無で変わらない。
- `FLEBOOT_IPP_CHECK ok:false` (shim 有) は既知の NG。`tools/flelift/boot/REPORT.md` §9 の「shim 有の IPP 判定は NG (#2702 が追う)」と同じ結果。本変更は IPP 判定の式に触れていない。
- 停止点は unit 209 の `MessageBoxA` → `exit(0)`。`FLE-9` の記録と同じ。

### 2-1. 正の対照 (probe が非 0 を読めることの確認)

`tools/flelift/boot/undo_probe_check.mjs` (コミット済み) を `tools/flelift/work/boot/fleboot_plain.cjs` に対して実行。

```sh
FLE_BOOT_VARIANT=plain node tools/flelift/boot/undo_probe_check.mjs "$PWD/tools/flelift/work/boot/fleboot_plain.cjs"
```

| 時点 | slot `0x15e1c78` | slot `0x15e4790` |
|---|---|---|
| 敷設前 | `0x0` | `0x0` |
| `_fle_data_install` 直後 | `0x16bb068` | `0x141d6b8` |
| `_fle_init` 直後 | `0x16bb068` | `0x141d6b8` |

- 判定: 敷設直後には PE の値が読める (probe は非 0 を検出できる)。`_fle_init` では消えない。
- つまり、boot 停止時点の 0 は「probe が読めない」ではなく「boot の途中で 0 に戻った」結果。本 run (HEAD `f57b7dff`) で同じ値を再確認した。

## 2-2. unit 単位の変化点 (測定 commit `b1b95f97`・再測定 HEAD `f57b7dff`)

`tools/flelift/boot/fle_boot.c` の `py_watch` (計測のみ・挙動は変えない) で、監視 slot の値が変わった時点を記録した。site の意味: 0 = `fle_run` 直前 / 1・2 = unit dispatch の直前・直後 / 3 = memset 直後 / 4 = ExitProcess / 5 = MessageBoxW / 6 = GetMem 直後 / 7 = FreeMem 直後 / 8 = GetMem 呼出し直前。

| 実行 | 変化点 (unit 1-based, site, slot, old → new) | 件数 |
|---|---|---|
| shim 有 | unit 209, site 8, `0x15e1c78` `0x16bb068`→`0x0`・`0x15e4790` `0x141d6b8`→`0x0` | 5 (うち site 0 の snap 3) |
| ネガコン | 同上 | 5 |

- 開始時 (site 0): `0x15e1c78` = `0x16bb068`・`0x15e4790` = `0x141d6b8`・`0x16b82e0` = `0x0`。
- unit 1〜208 の dispatch 前後、memset (site 3)、FastMM の GetMem・FreeMem (site 6・7) では変化なし。
- MessageBoxW (site 5・`QuickFontCache DLL not found!`・stderr 8117 行) では変化なし (この時点の slot は非 0)。この MessageBoxW の unit 番号は events に出ない (変化点でないため)。
- unit 209 の GetMem(0x74) 呼出し直前 (site 8・GETMEM seq 2312) で 0。GetMem の戻り値は 0 (§2-4)。
- 終了 (site 4, `ExitProcess`, call site `0x412a12`) では既に 0。
- 戻り番地の連鎖 (`exit-stack`): `0x412a12` → `0x409433` (`fle_ov_getmem` の失敗経路 → `Error`) → `0x412a4f` (GetMem 呼出し元) … → `0x410380`。

### 2-3. 0 化の位置の逆アセンブル (unit 209 の GetMem 呼出し元)

`pe_disasm.py 0x412960 120` (GetMem 呼出し元 `0x412a4f` の直前まで)。直接の 0 書込み `mov qword ptr [rip+0x11d82bf], 0` (VA `0x4129be`) はあるが、書込み先は `0x15eac88` で対象外 (命令長 11 で計算)。対象 slot (`0x15e1c78`・`0x15e4790`・`0x16b82e0`) を指す RIP 相対の書込みは、この 120 命令の窓には無い。
窓の外 (呼出し先 `0x4128b0`・`0x406fc0` など) は未確認。書込み命令は未特定で、「間接書込み」は推定にとどまる。

### 2-4. 停止点の確定 (再測定・HEAD `f57b7dff`・GitHub Actions run `38653934214`)

採取: `tools/flelift/work/boot/run_py123_shim.log` (1,059,537 行) と `run_py123_negctl.log` (1,056,155 行) (gitignore。同じ測定の `boot_summary_py123*.json` は `results/` にコミット済み)。

| 行 (shim) | stderr (抜粋) | 意味 |
|---|---|---|
| 8117 | `[fleboot][MessageBoxW] text='QuickFontCache DLL not found!' (自動 IDOK)` | 途中の呼出し。停止点ではない。直後も GetMem が続く (seq 1849) |
| 1059520 | `[blkdiag] GETMEM  seq=2312 size=116 site=0x412cc3<-0x410380` | 停止直前の GetMem(0x74) |
| 1059521 | `[fleboot][ff] dispatch(0) -> ret 0 (m11 icall-miss 揃え, call site ret=0x409424)` | FastMM への dispatch が icall-miss で 0 を返す (GetMem は NULL) |
| 1059522 | `[fleboot][MessageBoxA] text='' (自動 IDOK)` | **停止点の API と text** |
| 1059523 | `[fleboot][exit] code=0 call_site=0x412a12` | `exit(0)` |

negctl: 4733 行 (`MessageBoxW` QuickFontCache、途中)・1056140 行 `MessageBoxA text=''`・1056141 行 `exit(0)` (call site `0x412a12`)。

- 停止の機構 (`tools/flelift/boot/fle_boot.c` `fle_ov_getmem`): `ott_dispatch` の戻り番地が `0x409424`。戻り値 `R[0]` が 0 なら `if (!p)` の経路で戻り番地 `0x409433` を積み `f_409730()` (= Error) を呼ぶ。Error の先で `MessageBoxA ''` → `exit(0)` になる。
- 既存の記録との関係: `REPORT.md` §9-2・§10、`REPORT_APPENDIX_2702.md` §D の「`MessageBoxA` (text 空) → `exit(0)` (0x412a12)」は本 run で再現した。既存の記録は正しく、変更しない。
- 前版 (本 PR の初版) の「`MessageBoxW` (QuickFontCache) → GetMem(0x74) 失敗 → exit」は誤り。MessageBoxW は途中の呼出しで、停止の順序は `GETMEM seq 2312 → icall-miss (ret 0) → Error → MessageBoxA '' → exit(0)`。#3060 [FLE-11] の前提 (MessageBoxA の text 源と呼出元) は有効のまま。
- 0 化 (site 8) と icall-miss (`dispatch(0)` の ret 0) の因果は未確認。

## 3. 解釈 (今回の範囲)

- boot 停止点の 0 は、停止直前の GetMem(0x74) の失敗経路 (Error → exit) の区間で起きる。正常な起動の途中ではない。
- 前 run の絞り込み (前版 §3): `fle_boot_enter` の順序は `fle_data_install` → `fle_textwin_install` → `fle_init` → (boot 本体: DllMain → `_InitLib` → InitUnits)。`fle_data_install` と `fle_init` は値を消さない (§2-1)。本 run で unit 209 の GetMem(0x74) 直前まで絞り込んだ (§2-2)。
- `QuickFontCache` 系の既存の追跡: #154 (lift)・#2220 (FT 解決経路の到達性)。途中の MessageBoxW (QuickFontCache) の DLL 読込み経路は未確認。停止点ではないため本 PR では扱わない。

## 4. 変更内容 (本 PR)

| ファイル | 変更 |
|---|---|
| `tools/flelift/boot/fle_boot.c` | `py_watch` (監視 slot の変化点の記録・site 0〜8) と、`fle_py_ev_*` の export。`imp_ExitProcess`・`imp_MessageBoxW`・`fle_ov_getmem`・`fle_ov_freemem`・`fle_ov_initunits`・`imp_memset` に検査点を追加。`imp_ExitProcess` は stderr に戻り番地の連鎖を出す |
| `tools/flelift/boot/fle_boot.mjs` | 変化点を `FLEBOOT_PY123` 行と summary の `boot.py_events` に出す |
| `tools/flelift/boot/build.sh` | `_fle_py_ev_ptr`・`_fle_py_ev_n`・`_fle_py_ev_over` を export に追加 (main 取り込み時は main 側の export 一覧に追記) |
| `tools/flelift/boot/results/boot_summary_py123.json`・`boot_summary_py123_negctl.json` | 再測定 (HEAD `f57b7dff`) の summary |
| `tools/python/REPORT_PY123.md` | 本ファイル |
| `docs/DOC_MAP.md` | 本ファイルの索引行 |

- main 取り込み (`f57b7dff`): main 側で `tools/flelift/boot` のコードが変わっていたため (`fle_boot.c`・`fle_boot.mjs`・`build.sh`・`fle6_measure.sh`)、merge 後の HEAD で測り直した。`build.sh` の競合は export 一覧の行 (main 側の行に PY-123 の 3 件を追記)。
- KPI (起動に関わる変更のため。`docs/WORKFLOW.md` §7): FLEngine 起動の dispatch 数 (units_run) は **前 209 / 後 209** (main の既定経路 `tools/flelift/boot/REPORT.md` §2・§9、`REPORT_APPENDIX_2719.md` と一致)。最初のウィンドウ: **無し** (unit 209 の停止 `MessageBoxA` → `exit(0)`)。GetMem/FreeMem は shim 有 2314 / 1199・ネガコン 1891 / 776 (前 run の `results/boot_summary_fle6*.json` と一致)。boot の挙動は計測の追加で変わらない。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 209 の停止直前の GetMem(0x74): FastMM への dispatch が icall-miss (`dispatch(0)` ret 0) で NULL になる経路 | 停止 (Error → exit) の原因。lift 由来の silent miscompile か、実機でも起きるかが不明。0 化との因果も未確認 | #3060 [FLE-11] (受入条件に追加) |
| slot `0x15e1c78`・`0x15e4790` を 0 にする命令 (間接書込み) の特定 | 0 化の原因が不明。窓の外 (呼出し先 `0x4128b0`・`0x406fc0` など) は未確認 | #3028 に残す (次 run。unit 209 の GetMem(0x74) 直前区間の窓の外を逆アセンブルする) |
| 安全判定述語の VA・singleton の中身 | `restoreUndoLevel` の分岐・戻り値の判定ができない | #3028 (上の 2 件が解消した後に測る) |
| boot が unit 209 で止まる (`MessageBoxA` text 源と呼出元) | 起動直後の状態に届かない | #3060 [FLE-11] (open) |
| shim 有の IPP 判定 NG (`ok:false`) | 本測定の shim 有の判定が通らない (変更前から) | #3060 (呼出時の `[0x15e0a48]`・`0x15F34A0` の登録経路。`REPORT_APPENDIX_2702.md` の未解決表から移送。#2702 は CLOSED) |

## 6. 検証範囲

- 測定 commit: `b1b95f97` (PY-123 の計測コードを変えた最後の commit)。main 取り込み後の再測定は `f57b7dff` (merge commit)。以降の commit は本 REPORT と `docs/DOC_MAP.md` のみ。
- 差分 (WORKFLOW §6): `git diff f57b7dff HEAD -- tools/flelift/boot/fle_boot.c tools/flelift/boot/fle_boot.mjs tools/flelift/boot/build.sh tools/flelift/boot/fle6_measure.sh` の出力は **空 (差分 0)**。`git diff b1b95f97 f57b7dff` (main 取り込みの分) はコードを変えるため、再測定で置き換えた。
- 範囲内: boot の unit 単位の変化点 (shim 有・ネガコンの 2 条件、各 1 回・`f57b7dff`)。開始時の値 (site 0)・unit 209 の GetMem(0x74) 呼出し直前の値 (site 8)・停止点 (site 4・`MessageBoxA`)。停止点の stderr 行 (§2-4)。
- 範囲外: 起動直後 (停止経路を抜けた後)。安全判定の実体。singleton の中身。0 化を行う命令の特定。
- 未実施: `provider/build.sh` (emcc)・`node tests/general_diff.mjs`・`node tests/provider_check.mjs`・`FL_ENGINE=wasm node tests/all_tools.mjs` (実装が無いため走らせていない)。

## 7. 再現

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64
FLE_BOOT_TAG=py123 FLE_BOOT_RUNS="shim negctl" bash tools/flelift/boot/fle6_measure.sh   # 約 2 分 40 秒 (§2-2)
FLE_BOOT_VARIANT=plain node tools/flelift/boot/undo_probe_check.mjs "$PWD/tools/flelift/work/boot/fleboot_plain.cjs"   # §2-1
python3 tools/python/analysis/flapi/pe_xref.py 15e1c78           # §1 (FL_WIN64_DIR 必須)
python3 tools/python/analysis/flapi/pe_slot_writers.py 15e1c78   # §1
python3 tools/python/analysis/flapi/pe_disasm.py 0xf69840 70     # §1
python3 tools/python/analysis/flapi/pe_disasm.py 0x412960 120    # §2-3
```

- 生成物は `tools/flelift/work/boot/` (gitignore)。結果 JSON は `tools/flelift/boot/results/` にコミット済み。
- `build.sh` は `[EMSDK]` (`docs/REFERENCES.md` §4) の `emsdk_env.sh` を直接 source する (`SS_EMSDK_ENV` は `fle6_measure.sh` 側のみ)。emsdk 6.0.12 を `$RUNNER_TEMP/emsdk` に入れ、`[EMSDK]` の位置へ symlink して測った。
- 測定 (`f57b7dff`・run `38653934214`): real 2 分 41.8 秒 (gen-A 5 s・lift 56 s・clang-plain 65 s・boot shim 17 s・negctl 19 s)。load average (開始) `0.24 0.69 0.41`。並列 1 本。
- 前測定 (`b1b95f97`): real 2 分 12.2 秒 (lift 49 s・clang 49 s・boot shim 14 s・negctl 14 s)。load average (開始) `1.07 1.02 0.61`。
