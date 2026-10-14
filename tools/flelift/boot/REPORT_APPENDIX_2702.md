# tools/flelift/boot — FLE-10 (#2702) 付録: IPP 停止 mode・既定経路・工程の実測

> 正本: `tools/flelift/boot/REPORT.md` §10。本書は §10 の詳細 (工程秒・再現コマンド・呼出し点の実測・旧 §10 の全文)。
> 測定 commit: `56e515e1` (コードを変えた最後の commit)。`git diff 56e515e1 HEAD -- tools/flelift/boot` の差分は REPORT と本書のみ。
> 既知類型との関係: 該当なし (`docs/DEFECTS.md` D1a〜D23)。

## A. 工程の実測 (`fle6_measure.sh` 1 回ずつ・4 core・n=1)

| route | 工程 | 秒 | ピーク RSS | 備考 |
|---|---|--:|--:|---|
| root 有 (`FLE_EXTRA_ROOTS` 既定 0x6a7b70) | gen-A | 7 | - | load 1 分値 0.24 開始 |
| | lift (closure 2・cap 13800MB) | 83 | 609MB | 29,908 関数・1,557,903 insn・unlifted callees 1,681 |
| | clang shard ×8 (`-P3`・cap 5000MB) | 103 | 2,182〜2,660MB (8 shard) | 8/8 OK・cap 超過 0 件 |
| | link | - | - | mismatch 0 / undefined 0 / duplicate 0・wasm 127,079,110 B |
| | boot shim `FLE_IPP=1` / negctl `FLE_IPP=0` / ipp2 `FLE_IPP=2` | 24 / 25 / 23 | - | 合計 265 s (21:13:57〜21:18:22)・load 最大 1.93 |
| 既定 (root 無し・`FLE_IPP` 未指定) | gen-A / lift / clang | 7 / 81 / 101 | 610MB / 2,240〜2,531MB | 29,907 関数・1,557,882 insn |
| | link / boot default | - / 10 | - | wasm 127,076,763 B・合計 199 s (21:18:33〜21:21:52)・load 最大 1.91 |

## B. 再現コマンド

```sh
FL_WIN64_DIR=<fl-win64 の展開先> bash tools/flelift/boot/fle6_measure.sh          # root 有: shim → negctl → ipp2 (FLE_BOOT_RUNS 既定)
FLE_EXTRA_ROOTS= FLE_BOOT_WORK=<repo>/tools/flelift/work/boot_noroot FLE_BOOT_TAG=fle10_noroot \
  FLE_BOOT_RUNS=default FL_WIN64_DIR=<fl-win64 の展開先> bash tools/flelift/boot/fle6_measure.sh   # 既定経路
FLE_IPP=<0|1|2|空> FLE_BOOT_VARIANT=plain node tools/flelift/boot/fle_boot.mjs <絶対パス>/fleboot_plain.cjs <out.json> --boot-only
```

- `FLE_EXTRA_ROOTS=` (空) は root を足さない。`:-` から `-` に直したため、空を渡すと 0x6a7b70 が戻らない。
- shim (`FLE_IPP=1`) の `FLEBOOT_IPP_CHECK` は終了時の 0x15F34A0 を見るため NG (exit 3) になる。§10 の通り、呼出しの不発を示さない。
- 結果 JSON: `results/boot_summary_fle6.json` (shim)・`_fle6_negctl.json`・`_fle6_ipp2.json`・`_fle10_noroot_default.json`。`ipp.call_slot` `ipp.token_at` `ipp.stop` を追加。

## C. IPP 呼出しと slot の実測 (summary の `ipp.*`・終了時点)

| run | `ipp.called` | `[0x15e0a48]` (終了時) | `0x15F34A0` (終了時) | image 域 0x400000〜0x2000000 のトークン所在 |
|---|---|---|---|---|
| shim `FLE_IPP=1` | ippsZero_8u × 2 (初回 ret 0x67264d) | 0x0 | 0x0 | 0 件 |
| mode 2 `FLE_IPP=2` | ippsZero_8u × 2 | 0x0 | 0x0 | 0 件 |
| ネガコン `FLE_IPP=0` | なし | 0x0 | 0x0 | - |
| 既定 (root 無し) | なし。0x67264d に `dispatch(0)` (icall-miss) ×1 | 0x15f34a0 | 0x0 | - |

- 0x67264d は `fle_lifted_s5.c` の `mov rax,[0x15e0a48]` → `call qword ptr [rax]` (lift 行の実測)。
- ippsZero_8u が 0x67264d から呼ばれたのは root 有の 2 回だけ。mode 2 は非 ippsZero の IPP 呼出しが 0 件で、停止条件に達しなかった。

## D. 停止点 (root 有・unit 209 の後)

- `[fleboot][MessageBoxA] text=''` → `[fleboot][exit] code=0 call_site=0x412a12`。
- `fle_lifted_s2.c` の 0x4129f5 `jne 0x412a12` は `[0x15eac80] != 0` で分岐する。text 源 (lpText) と呼出元関数は**未特定** (次の blocker。#3060 [FLE-11])。
- 既定経路 (root 無し) は同じ unit で止まらず `unlifted 0x6a7b70` (`target 6978416`)。

## E. 旧 REPORT §10 の全文 (FLE-6 #672。REPORT の 250 行上限のため分割移動・内容は無変更)

## 10. FLE-6: dsp_ippv2 shim と 0x6a7b70 root (#672, PR #681)

- **真因 (#672 の 08:07 UTC 実測コメントが出典)**: `0x15F34A0` = `ippsZero_8u`。`LoadLibraryW("dsp_ippv2_x64.dll")` の失敗 → `f_653f40` の early return → 登録されず 0。`f_414ec0` (UStrCopy) の out=0 は VCL リーダの誤りではなく、この連鎖の結果。**FLE-5 の「VCL リーダ起因」は誤認**。lift 欠陥ではなく host shim の欠落。
- **shim** (`fle_boot.c`): `shimx_set_load_hook` で dsp_ippv2 を擬似 HMODULE 登録、`imp_GetProcAddress` が名前ごとのトークンを返す。`ippsZero_8u` のみ実装、他は `R[0]=0` の fail-soft + 呼出計数。`LoadLibrary` hook は `#if !FLEBOOT_NOSX` 内のため **nosx variant では dsp_ippv2 は解決されない (意図どおり)**。
- **DEFECTS.md 照合**: 該当なし。D15 (メモリ間接 call の空ブロック) とは別事象。lift 欠陥ではないことを #672 で実測済み。
- **fail-soft の silent miscompile 面**: `ipp_call` は `ippsZero_8u` 以外の全 IPP で何もせず `R[0]=0` を返す。IppStatus 系は ippStsNoErr のまま出力を埋めず、`ippMalloc` (0x15F33C0) は NULL 相当。units_run の前進がこの stub 由来の可能性がある。**呼ばれた IPP 名と回数の全一覧は実測未了 (起票依頼 ①)**。
- **0x6a7b70 root**: `boot_roots.json` からは**除外したまま** (blocklist と REPORT §0/§5/§7 の不変条件を維持)。`fle6_measure.sh` だけが `FLE_EXTRA_ROOTS=0x6a7b70` で一時的に root 化する。survey 非破裂は未確認 (起票依頼 ②)。
- **summary への証跡** (`fle_boot.mjs`): `ipp.ptr_15F34A0` / `ipp.ptr_15F40E8` / `ipp.total` / `ipp.called` を JSON と `FLEBOOT_RESULT` に出す。`FLEBOOT_IPP_CHECK` 行で判定 (shim 有: 0x15F34A0 ≠ 0 / `FLE_IPP=0`: = 0)、NG は exit 3。`fle6_measure.sh` の `run_boot` は `fle_boot.mjs` の rc を `rc` に捕まえて伝播し、判定行・JSON が無ければ exit 4 で止まる (`grep 'FLEBOOT_RESULT' ... || true` は表示用で判定には使わない)。
- `dbg_probe.mjs` は main にも本 PR の head にも存在しないため、本 PR では扱わない (観測は `fle_boot.mjs` の summary に統合する方針)。

| 項目 | 状態 |
|---|---|
| lift/clang/link/boot の到達 | **到達 (FLE-9・§9-1)**。boot は unit 209 で停止 (`MessageBoxA` → `exit(0)`)。最初のウィンドウは未達 |
| shim 有 / ネガコン (`0x15F34A0` 判定) | **取得 (§9-1)**: shim 有は NG (`ptr_15F34A0=0x0`)、ネガコンは OK |
| units_run の前進・次の停止点 | **209 のまま** (shim 有・ネガコン同値、§9-2)。前 run の値 (209) は #672 08:07 コメントに残るが、本 PR では比較していない |
| `ipp.called` 全件・`stopped_at` | shim 有: `ippsZero_8u` ×2 のみ・`stopped_at`=209 (両方) |
| survey 再実測 (0x6a7b70 root の非破裂確認) | **未取得 (#918)**。0x6a7b70 の恒久 root 化は採用しない (PM 判断 4/14 のまま) |
| 既定経路 (`FLE_IPP` 未指定) の非変化 | **未測定**。「209 据え置き」とは書かない |

起票依頼: ① IPP fail-soft の呼出名一覧と silent miscompile 検査 ② survey 再実測と 0x6a7b70 root 化の可否判断 (PM 判断) ③ `bash tools/flelift/boot/fle6_measure.sh` を emsdk 込みの runner で再採取 (素材: `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk work-m11 work-liftdiff`)。
`boot_e2e.sh` / `build.sh` / `iterate_roots.sh` の `[EMSDK]` 直書きは既存の書式で、本 PR の範囲外 (起票依頼 ④)。

### 10.x 実測の試行

- 結論 (fix run 2026-10-13): **この PR では lift が runner の上限内で完走しない** (cap 13800MB で実測 4 が kill)。clang・boot・ネガコン・`FLEBOOT_IPP_CHECK` は未到達で、分割 lift は #918 (FLE-7)。実測 1〜4 の詳細と経緯は `REPORT_APPENDIX.md` §C。
- **実測 4 (PM 指示の 1 回採取, 16:43 UTC 開始, head は本 commit)**: `rss_cap.py --cap-mb 13800` で `x64c.py --closure 1` (`FLE_EXTRA_ROOTS=0x6a7b70`)。**126 s・ピーク RSS 13832MB で kill (rc=143)**。closure 2 は再採取せず、実測 3 の時間切れを残す。
- 既定経路: shim は既定で無効 (`55acfb6d`)。`FLE_IPP=1` のときだけ有効。boot 未到達のため、既定経路の数値 (209 据え置き等) が変わるかは未測定。
