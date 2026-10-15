# tools/flelift/boot — REPORT 付録 (FLE-672 (#672): buf = 0 の fill を戻す診断)

> `REPORT.md` §11 から参照する付録。親 #672 (PM 改訂 2026-10-15)。診断は opt-in (`FLE_DIAG_NULLFILL=1`・既定無効)。
> 本文の数値はすべて本 run の実測 (`results/boot_summary_fle672*.json`・`work/boot*/run_*.log`)。`rt/` と `x64c.py` は変えていない。

## 結論 (先出し)

- **既定経路は不変**: 診断なし・root 有の shim / ネガコンは units 209・GetMem / FreeMem 2,314 / 1,199 と 1,891 / 776 (§9-2・§10 の基準と一致)。既定 (root 無し) は 1,890 / 776・停止 `unlifted 0x6a7b70` (§10 と一致)。
- **診断あり (`FLE_DIAG_NULLFILL=1`)**: fill コールバック `0x6a7b70` の呼出し 1,048,576 件 (= 面の高さ 2^20 行) を戻す。undo slot `0x15e1c78` / `0x15e4790` は 0 化されず、GetMem(0x74) の icall-miss も起きず、`0x15F34A0` は shim 有で非 0 (`0x7f10001c`)。
- **停止点の移動**: 診断ありは unit 209 の中で `MessageBoxW` (`QuickFontCache DLL not found!`) の後、`unlifted 0x6bbc20` (call site ret `0x6c9380` = `f_6c9280`) で停止。units_run は **209 のまま** (診断による前進は修復ではない)。子 issue **#3491 [FLE-14]** に起票。
- 製品 KPI (既定経路): units 209 → 209 (変化なし)。最初のウィンドウ: 未達 (停止は診断なし・診断ありとも unit 209 内)。

## 1. 結果表 (本 run・各 route n=1)

lift は 2 回 (root 有 = `FLE_EXTRA_ROOTS=0x6a7b70` (既定 `work/boot`)、root 無し = `FLE_EXTRA_ROOTS=` (`work/boot_nr`))。clang 8 shard・link は各 1 回 (mismatch 0 / undefined 0 / dup 0)。

| route | lift | FLE_IPP | 診断 | units | GetMem / FreeMem | `ptr_15F34A0` | 停止 | skip |
|---|---|---|---|--:|--:|---|---|--:|
| shim 有 (既定経路) | root 有 | 1 | off | 209 | 2,314 / 1,199 | 0x0 (IPP 判定 NG = 既知) | `MessageBoxA` '' → exit(0) | 0 |
| ネガコン (既定経路) | root 有 | 0 | off | 209 | 1,891 / 776 | 0x0 (OK) | 同上 | 0 |
| 既定 (root 無し) | root 無し | (未指定) | off | 209 | 1,890 / 776 | 0x0 | `unlifted 0x6a7b70` @0x6c7923 | 0 |
| **shim 有 診断** | root 無し | 1 | **on** | 209 | 2,314 / 1,200 | **0x7f10001c (OK)** | `unlifted 0x6bbc20` @0x6c9380 | 1,048,576 |
| **ネガコン 診断** | root 無し | 0 | **on** | 209 | 1,891 / 777 | 0x0 (OK) | `unlifted 0x6bbc20` @0x6c9380 | 1,048,576 |

- FreeMem が +1 (診断 route): skip 後に進んだ unit 209 の FreeMem 1 件による (推定。未追跡)。
- py_events (`0x15e1c78` / `0x15e4790`・終了時の値): 既定経路 (root 有) は unit 209 の GetMem 入口 (site 8) で `0x16bb068 → 0`・`0x141d6b8 → 0` (shim / ネガコン とも)。診断 route は変化イベント 0 件 (終了時も `0x16bb068` / `0x141d6b8` のまま)。
- `dispatch(0)` (icall-miss) のうち、戻り番地 `0x409424` (= `fle_ov_getmem` の MM 表 dispatch): 既定 (root 有) 1 件 (unit 209 の GETMEM seq=2312, size=116)、診断 0 件、既定 (root 無し) 0 件。戻り番地 `0x668629` / `0x8157c4` の miss は 3 route 共通で、本件とは別 (未解析)。

## 2. 仮説の成否 (PM 改訂の 3 項目)

| # | 仮説 (診断ありで) | 判定 | 根拠 |
|---|---|---|---|
| ① | `0x15e1c78` / `0x15e4790` / `0x15F34A0` が 0 化されない | **成立** (`0x15F34A0` は shim 有で非 0 のまま。ゼロ化は fill 由来と観測: root 有で unit 209 の GetMem 入口に 0 化) | §1 py_events・終了時 `0x7f10001c` |
| ② | unit 209 の GetMem(0x74) が icall-miss にならない | **成立** (診断 0 件。root 有は 1 件 = 戻り `0x409424`) | §1 dispatch(0) 集計。`0x13a5c90` (MM 表) は fill の範囲 `[0, 0x1800000)` 内 (算術・推定) |
| ③ | shim 有で終了時 `ptr_15F34A0` ≠ 0 | **成立** (`0x7f10001c`・`ippsZero_8u` 呼出 2 回は診断の有無で同じ) | §1 |

## 3. 観測: fill 呼出しの回数 (未特定)

- 既定 (root 有) は `f_6c7610` の fill 呼出しが **6 回** で止まる (`[fill6a7b70]` 6 行。`REPORT_APPENDIX_3090.md` §1-1 と一致)。
- 診断 route は **1,048,576 回** (= rect `(0,0,1048576,1048576)` の行数 2^20) まで回り、1 行ずつ戻る。dst は 0x0 から 0x400000 刻み (`#199` = `0x31c00000` で 199 × 0x400000 と一致)。
- 6 回で止まる源は未特定。推定: root 有の lifted fill が行ごとに image (`[0x400000, 0x1800000)`) を 0 埋めし、その制御データを変えて行ループを抜ける (未検証)。

## 4. 既定経路の不変 (差分の証跡)

- `git diff --stat origin/main -- tools/flelift/x64c.py tools/flelift/rt/` は空 (`rt/`・`x64c.py` は変えていない)。
- 変更は `tools/flelift/boot/` の `fle_boot.c` (診断関数 3 つと `fle_ff` の 1 分岐。`FLE_DIAG_NULLFILL` 未指定で通らない)・`fle_boot.mjs` (env 読取と summary の `boot.diag_nullfill`)・`fle6_measure.sh` (run `diag_shim` / `diag_negctl`)・EXPORTS 3 箇所 (`build.sh` / `boot_e2e.sh` / `iterate_roots.sh`)。
- 既定経路の数値は §1 の 3 行 (診断なし) で基準と一致。

## 5. 再現

```sh
# 素材: fl-win64 toolchain-emsdk (SS_EMSDK_ENV = [EMSDK] の emsdk_env.sh)。FL_WIN64_DIR=<展開先>
FL_WIN64_DIR=... FLE_EXTRA_ROOTS= FLE_BOOT_WORK=$PWD/tools/flelift/work/boot_nr FLE_BOOT_TAG=fle672nr \
  FLE_BOOT_RUNS="default diag_shim diag_negctl" bash tools/flelift/boot/fle6_measure.sh   # 約 4 分 (lift 80 s + clang 100 s + boot)
FL_WIN64_DIR=... FLE_BOOT_TAG=fle672 FLE_BOOT_RUNS="shim negctl" bash tools/flelift/boot/fle6_measure.sh   # root 有 (既定経路)
```

- 測定環境: 4 vCPU・RAM 15 GB・load 0.2〜2.0。lift 66〜80 s、clang 8 shard 99〜101 s (cap 5000MB・peak 2.2〜2.5 GB/shard)、boot 10〜25 s。
- 測定 commit: 本 PR の HEAD (コード変更はこの PR の commit のみ)。検証起点 `origin/main` `195483b2`。

## 6. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 診断後の停止点 `unlifted 0x6bbc20` (f_6c9280 ← 0x6c9380) の実体と解消 | 最初のウィンドウ未達・units 209 据え置き | 子 issue #3491 [FLE-14] (親 #672) |
| 行ループが root 有で 6 回、診断 route で 2^20 回になる差の源 | 0 化の時点・面の寸法の正しさが決まらない | 既存 #3112 [FLE-13] (親 #3090) |
| `MessageBoxW` `QuickFontCache DLL not found!` (両 route で出る) | QuickFontCache の読込失敗が本当の停止原因か未確定 | 既存 T-SH 系 (#3410・#3412・#3434) |
| 戻り `0x668629` / `0x8157c4` の icall-miss (3 route 共通) | 既定経路の silent miscompile の疑い | 未起票 (本 PR の範囲外・既知の未解決として残す) |

## §A. 旧記述の移動 (REPORT.md から分割移動・全文)

REPORT §0 (旧 11〜14 行):

```
  **unit 進行は 209 で横ばい** — ただし FLE-5 で unit 進行の blocker は
  `f_6c7900` の fill ループ幅「未初期化」ではなく、
  **`f_653f40` (VCL フォーム登録ルーチン) が早期 return して
  fill コールバック `0x15F34A0` が未設定** であることを 5 段の逆引きで実証 (付録 §B 3-5)。
```

REPORT §5 (旧 138〜145 行):

```
1. **unit#209 の次の blocker は `unlifted 0x6a7b70`** (fill コールバック、付録 §B 3-4)。
   root 化しても `f_6c7900` の fill ループが暴走 → ExitProcess → **survey が成立しない**
   ため `FLE_ROOT_BLOCKLIST` (既定 `0x6a7b70`) で自動累積から除外している。
   真因は 付録 §B 3-5 の通り **`f_653f40` が `f_53c5e0` 側の VCL リソース読み出し失敗で
   早期 return し、fill コールバック `0x15F34A0` を登録できない**こと。
2. **unit 進行 209 で横ばい**。前ラウンド目標の 250+ には未達。
   次の一手は 付録 §B 3-5 の `f_43c5e0` / `f_414ec0` が out = 0 を返す理由の特定
   (VCL リーダのクラス解決 or リソース未検出)。
```

REPORT §7 (旧 165〜167 行):

```
1. **最優先: `f_43c5e0` / `f_414ec0` が out = 0 を返す理由の特定** (付録 §B 3-5)。
   VCL リーダのクラス解決 or リソース未検出のいずれか。ここが外れれば
   `f_653f40` がコールバック `0x15F34A0` を登録し、unit 進行が 209 を超える。
```

訂正 (#672・FLE-12 の実測): 「`f_414ec0` は out = 0 を返す」は誤認で、`f_414ec0` は `UStrCopy` である。`f_653f40` の早期 return は VCL リソース読み出しの失敗ではなく、`dsp_ippv2_x64.dll` の `LoadLibraryW` 失敗 (host shim の欠落) による。`0x15F34A0` = `ippsZero_8u` (`REPORT_APPENDIX_2702.md` §E・§10)。

## 7. #3770: 有界実行で 0x6bbc20 を root 化した診断 route (2026-10-15・HEAD 測定)

- 手順: `FLE_EXTRA_ROOTS=0x6bbc20 FLE_DIAG_NULLFILL=1` (`FLE_BOOT_RUNS="diag_shim diag_negctl"`・`FLE_BOOT_SECS=150`・`FLE_BOOT_LOG_MB=200`)。lift 61 s・clang 8 shard 74 s・link mismatch 0 / undefined 0 / dup 0。`fle6_measure.sh` に opt-in の `FLE_BOOT_SECS` (timeout) と `FLE_BOOT_LOG_MB` (`ulimit -f`) を足した (未指定は従来どおり)。
- 結果 (n=1・150 s で打ち切り・結果 JSON は無し):

| route | 停止 | GetMem / FreeMem (打ち切り時) | `unlifted` 行 | `MessageBoxW` 'QuickFontCache DLL not found!' | ログ |
|---|---|--:|--:|---|--:|
| shim 有 + 診断 + root `0x6bbc20` | 150 s で打ち切り (rc 124) | 2,312 / 1,200 | 0 | あり (行 8117) の後も GETMEM / FREEMEM が続く | 739 KB |
| ネガコン + 診断 + root `0x6bbc20` | 150 s で打ち切り (rc 124) | 1,889 / 777 | 0 | あり (行 4733) の後も続く | 520 KB |

- 読み取り (実測): root 化すると、§1 の `unlifted 0x6bbc20` の停止は消える。診断 route は 150 s 内に戻らず、GetMem 2,312 は既定経路の最終値 2,314 に近い。打ち切り時の unit 番号は JSON が戻りで書かれるため取れていない (units_run は未取得)。
- 本 run のログは 1 回目 (#3491 の 1,200 s で 20 GB) より遙かに小さい (150 s で 0.5〜0.7 MB)。反復の 16 byte 列は GETMEM / FREEMEM の `blkdiag` 出力で、20 GB の出力は本 run では再現していない (推定: 時間の長さによる)。
- `[diag672][nullfill] skip` は 64 件 (表示上限。最後は `#63`・dst `0xfc00000`)。診断 route の fill の戻し件数の総数は出していない (未計測)。

### 7-1. 既定経路の再実測 (変更後の `fle6_measure.sh`・root `0x6a7b70`・診断なし)

| route | units_run | GetMem / FreeMem | `ptr_15F34A0` | 停止 | 判定 |
|---|--:|--:|---|---|---|
| shim 有 (`FLE_IPP=1`) | 209 | 2,314 / 1,199 | 0x0 | `MessageBoxA` → exit(0) | rc 3 (IPP 判定 NG = 既知) |
| ネガコン (`FLE_IPP=0`) | 209 | 1,891 / 776 | 0x0 | 同上 | OK |

- §1 の表 (既定経路) と一致。`fle6_measure.sh` の変更は既定値で従来と同じ経路 (`ulimit` / `timeout` を付けない) を通る。結果: `tools/flelift/boot/results/boot_summary_fle672d*.json`。

### 7-2. #3770 の受入の判定

| 受入 | 判定 | 根拠 |
|---|---|---|
| 1. 診断 route で `0x6bbc20` 解消後の units_run と次の停止点 | **未達** (次の停止点は未到達) | 150 s で打ち切り。`unlifted` 0 件・MessageBoxW の後も進む。units は JSON が無く取れない |
| 2. `0x6c937a` の呼出し回数と矩形の寸法 | **未達** (未計測) | 計数の計装が `fle_boot.c` に無い。`rt/` は変えない方針 |
| 3. 既定経路の再実測 | 達成 | §7-1 (209 / 2,314 / 1,199・209 / 1,891 / 776) |

- 次の一手 (未解決): 打ち切りの時間を延ばすか、戻り時に部分の JSON を書く (`fle_boot.mjs` の変更) ことで、unit 番号と停止点を取る。どちらも #3770 の範囲 (`Refs #3770`)。
- 既定経路の `units` 209 は動かしていない (本 PR は計測の補助のみ)。
