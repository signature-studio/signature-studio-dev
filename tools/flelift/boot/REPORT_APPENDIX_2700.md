# tools/flelift/boot — REPORT 付録 (FLE-8 (#2698) の詳細)

> `REPORT.md` の行数上限 (250 行, `docs/DOC_MAP.md` §1) 超過に伴う**分割移動**。内容は削除していない
> (元の位置は Git 履歴の `REPORT.md` で、`a741a0ca` の直前)。FLE-9 (#2700) の正本は `REPORT.md` §9。

---

## E. §9 から移動: FLE-8 (#2698) の取込と clang RSS 上限 (2026-10-14)

- **結論**: lift は runner 内で完走する (ピーク RSS **609MB**・**63〜64 s**)。単一 TU の `emcc -c fle_lifted.c` は **cap 11000MB 超で打ち切られる** (11261〜11436MB・97〜98 s)。cap の下で runner は生存し、本節まで到達した。**boot 未到達** (clang 段で停止、残作業は #2700)。#918 で runner を落としたのは lift ではなく clang の単一 TU (旧 lift は 13.8GB 超で kill、付録 §C)。
- 既知類型との関係: 該当なし (`docs/DEFECTS.md` D1a〜D23 と照合。出力は旧 x64c と cmp 一致 (§9-2) のため新たな類型は生じない)。
- 測定 commit: `a3639395` (コードを変えた最後の commit。取込元 `c4895395` = `fa0ecaad`)。検証起点: `origin/main` `aaa3763e`。
- 差分 0 の証跡: `git diff --stat a3639395 HEAD -- tools/flelift/x64c.py tools/flelift/boot/rss_cap.py tools/flelift/boot/build.sh tools/flelift/boot/boot_e2e.sh` は空 (本節の commit は REPORT のみ)。
- 再現: `FL_WIN64_DIR=<fl-win64 展開先> bash tools/flelift/boot/fle6_measure.sh` (gen-A → lift → build plain。clang 段の cap 超過で rc=1)。素材 `oc_artifacts: fl-win64 toolchain-emsdk` (emsdk は `[EMSDK]`)。

### E-1. 工程の実測 (コミット済み HEAD で 2 回)

| 工程 | run1 (17:15 UTC・同一コード) | run2 (17:21 UTC・クリーン `a3639395`) |
|---|---|---|
| gen-A | 7 s | 6 s |
| lift (x64c closure 2・`FLE_EXTRA_ROOTS=0x6a7b70`・cap 13800MB) | rc 0・64 s・peak 609MB | rc 0・63 s・peak 609MB |
| clang `emcc -c fle_lifted.c` (-O0・1 TU・cap 11000MB) | **KILLED(cap)** 98 s・peak 11261MB | **KILLED(cap)** 97 s・peak 11436MB |
| link / boot | 未到達 | 未到達 |

- lift 結果 (両 run): functions 29,908・insns 1,557,903・unlifted callees 1,681・imports 680。issue 想定の 29,907 / 1,557,882 との差 1 関数・21 命令は、`FLE_EXTRA_ROOTS=0x6a7b70` が 1 関数として加わるため。root 無し (`FLE_EXTRA_ROOTS=` 空・roots 21,311) の 1 回では **29,907 / 1,557,882・610MB・61 s** で §2 と一致。
- clang の RSS (run2、`rss_cap.py` が 1 s ごとに採取): 13 s 1,356MB / 28 s 2,896MB / 43 s 4,477MB / 89 s 6,907MB / 97 s 11,436MB (打ち切り)。memavail 14.1GB → 3.3GB。1 s 採取のため上限を約 0.4GB 超えて止まる。
- 打ち切りの出力: `[build] clang RSS cap 超過: .../fle_lifted.c peak=11436MB (cap 11000MB, ...)` と exit 1。打ち切り時の kill 対象は PID 1 個 (`kill pids=[4839]`。emcc が clang を exec したかは未確認)。

### E-2. 検証 (同一性・負例対照)

- **出力同一性**: roots 先頭 400 件・`--closure 2` で旧 `x64c.py` (origin/main) と新の `fle_lifted.c` (1,434,084 B)・`lift_meta.json` が `cmp` 一致 (386 関数・13,293 insn)。負例: `fle_lifted.c` の 1 byte (offset 2197) を反転した複製は `cmp` rc=1 (`differ: byte 2198, line 72`)、無変更の比較は rc=0 (HEAD で再実行)。
- **子孫 kill**: 子が孫 (300MB 確保) を起こし上限 100MB で打ち切る小テスト。旧 `rss_cap.py` は直接の子だけに SIGTERM し、**孫 318MB が PPID=1 の孤児として残存** (`ps` で確認)。新版は `kill pids=[3901, 3902]` で両方止まり、残存 0。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 単一 TU の lifted C が clang -O0 で 11GB 超 (cap で打ち切り) | boot・link の実測が無い (#918 の boot 到達は残る) | 既存 #2700 [FLE-9] (TU 分割) |
| cap 11000MB は打ち切り 2 回のみから決めた値 | cap が低すぎて通る TU を落とす可能性 | #2700 の分割後に再測定 |

# FLE-9 (#2700) の全文 (REPORT §9 から分割移動・250 行上限のため)


- **結論**: 単一 TU の clang は cap 11000MB 超で打ち切られていた (FLE-8・付録 E-1)。8 shard (`FLE_SHARDS=8`・`xargs -P3`・各 cap 5000MB) では全て cap 内で完走 (各ピーク 2,202〜2,666MB・clang 段 89 s)。link は mismatch/undefined/duplicate 0・wasm 127,078,695 B。**boot は両 variant とも unit 209 で停止**。shim 有の IPP 判定は NG (`ptr_15F34A0=0x0`)。最初のウィンドウは未到達。
- 測定 commit: `a741a0ca` (コードを変えた最後の commit。検証起点 `origin/main` `26f90ada`)。差分 0 の証跡: `git diff --stat a741a0ca HEAD -- tools/flelift/x64c.py tools/flelift/boot/build.sh tools/flelift/boot/fle6_measure.sh tools/flelift/boot/rss_cap.py` が空 (本節の commit は REPORT・付録のみ)。
- 出力同一性: `--shards 1` は旧 `x64c.py` (origin/main) と小入力 (roots 先頭 400・closure 2・386 関数) で `fle_lifted.c` / `lift_meta.json` が sha256 一致。N=8 は関数本体の集合が N=1 と一致し、`ott_dispatch`・`imp_tab` は shard 0 のみ。既知類型: 該当なし (`docs/DEFECTS.md` D1a〜D23)。
- 再現: `FL_WIN64_DIR=<fl-win64 展開先> bash tools/flelift/boot/fle6_measure.sh` (既定 `FLE_SHARDS=8`)。素材 `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk work-m11 work-liftdiff`。

### 9-1. 工程の実測 (HEAD `a741a0ca`・`fle6_measure.sh` 1 回。同内容の前回実行は lift 67 s / clang 105 s で、boot の数値は同一)

| 工程 | 結果 | 秒 | ピーク RSS |
|---|---|---|---|
| gen-A | rc 0 | 8 | - |
| lift (closure 2・root 0x6a7b70・cap 13800MB) | rc 0・29,908 関数・1,557,903 insn | 88 | 610MB |
| clang shard ×8 (-O0・-P3・cap 5000MB) | 8/8 OK・cap 超過 0 件 | 89 (工程計) | s0 2,666 / s1 2,243 / s2 2,406 / s3 2,345 / s4 2,202 / s5 2,363 / s6 2,387 / s7 2,487 MB |
| shard 別の秒 (s0〜s7) | 46 / 31 / 32 / 20 / 23 / 27 / 26 / 22 | - | - |
| link | mismatch 0・undefined 0・duplicate 0・wasm 127,078,695 B | - | - |
| boot shim (`FLE_IPP=1`) | units 209・stopped 209・IPP check NG | 24 | - |
| boot ネガコン (`FLE_IPP=0`) | units 209・stopped 209・IPP check OK | 25 | - |

### 9-2. 起動指標 (前後)

- **units_run**: 前 209 (FLE-5/6・§2) → 後 **209 のまま** (停止点=209)。shim 有・ネガコンとも同じ。
- shim 有の確保 `GetMem` 2,314 / `FreeMem` 1,199 (ネガコン 1,891 / 776)。`ipp.called` 全件は `ippsZero_8u` ×2 のみ。`ptr_15F34A0` は shim 有でも `0x0`。
- 停止: 両方とも unit 209 の後に `MessageBoxA` (text 空・自動 IDOK) → `exit(0)` (call site `0x412a12`)。最初のウィンドウは未達 (生成は未確認)。既定経路 (root 無し) は未測定。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| shim 有で `0x15F34A0` が 0 のまま (`ippsZero_8u` は 2 回呼ばれる)。登録経路が未解明 | FLE-6 の IPP 判定 NG・units 209 据え置き | 既存 #2702 [FLE-10] (`blockedBy: #2700`)。本 PR で事実を追記 |
| unit 209 の後の `MessageBoxA` → `exit(0)` の原因 | 次の blocker (最初のウィンドウ未達) | 既存 #2702 (同上) |
| 既定経路 (root 0x6a7b70 無し) の boot 未測定 | 209 据え置きの確認が未了 | 既存 #2702 作業 1 |
