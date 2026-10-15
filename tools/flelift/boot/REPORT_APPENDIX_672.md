# tools/flelift/boot — REPORT 付録 (FLE-672 (#672): buf = 0 の fill を戻す診断)

> `REPORT.md` §11 から参照する付録。親 #672 (PM 改訂 2026-10-15)。診断は opt-in (`FLE_DIAG_NULLFILL=1`・既定無効)。
> 本文の数値はすべて本 run の実測 (`results/boot_summary_fle672*.json`・`work/boot*/run_*.log`)。`rt/` と `x64c.py` は変えていない。

## 結論 (先出し)

- **既定経路は不変**: 診断なし・root 有の shim / ネガコンは units 209・GetMem / FreeMem 2,314 / 1,199 と 1,891 / 776 (§9-2・§10 の基準と一致)。既定 (root 無し) は 1,890 / 776・停止 `unlifted 0x6a7b70` (§10 と一致)。
- **診断あり (`FLE_DIAG_NULLFILL=1`)**: fill コールバック `0x6a7b70` の呼出し 1,048,576 件 (= 面の高さ 2^20 行) を戻す。undo slot `0x15e1c78` / `0x15e4790` は 0 化されず、GetMem(0x74) の icall-miss も起きず、`0x15F34A0` は shim 有で非 0 (`0x7f10001c`)。
- **停止点の移動**: 診断ありは unit 209 の中で `MessageBoxW` (`QuickFontCache DLL not found!`) の後、`unlifted 0x6bbc20` (call site ret `0x6c9380` = `f_6c9280`) で停止。units_run は **209 のまま** (診断による前進は修復ではない)。子 issue **#3491 [FLE-14]** に起票。
- 製品 KPI (既定経路): §C 参照 (訂正済み: 既定経路は boot_roots 追加後 209 → 895)。最初のウィンドウ: 未達 (停止は診断なし・診断ありとも unit 209 内)。

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

## §B. 分岐入力の判定と ILTools 分岐入力の実験 (2026-10-15・PM 改訂 2 の『次の 1 手』)

> 静的判定の出典: `python3 tools/flelift/boot/fle672_static.py <PE>` (PE = `$FL_WIN64_DIR/extracted/block00031_PE.bin`)。
> 動的: `FL_WIN64_DIR=<fl-win64> SS_EMSDK_ENV=<emsdk_env.sh> FLE_BOOT_TAG=fle672ilt FLE_BOOT_RUNS="shim negctl ilt" bash tools/flelift/boot/fle6_measure.sh`。
> 結果 JSON: `results/boot_summary_fle672ilt{,_negctl,_ilt}.json`。

### B-1 結論 (先出し)

- **仮説 B が成立 (判定 (2))**。2^20 × 2^20 の面は `f_815050` が作る。その呼出元 `f_815e10` (`0x815e10`) の分岐 `0x815e86`〜`0x815e8d` は、
  `[VA 0x15F6F88]` が 0 のとき `f_815050` (2^20 面) に入り、非 0 なら代替経路 (`call [0x15F6F88]`・`0x815e96`) に入る。
  `[0x15F6F88]` = `GetProcAddress(LoadLibraryW("ILTools"), "CreateCursorFromFont")` の戻り値 (`0x815e52`・`0x815e38`)。
  lift の stub は LoadLibraryW・GetProcAddress とも 0 を返すため、**lift だけが 2^20 面の経路に入る** (推定: native は ILTools_x64.dll を読めて非 0 になる。`tools/iltools/REPORT.md` の対象 DLL。読込成功の native 実測は未実施)。
- **実測**: ILTools の擬似モジュール (`FLE_IPP=3`・本 PR で追加) で分岐入力を非 0 にすると、**units_run 209 → 851 (942 中)**。fill (`0x6a7b70`) 6 回 → 0 回、空の `MessageBoxA` → `exit(0)` は出ない。ネガコン (`FLE_IPP=0`) と shim (`FLE_IPP=1`) は 209 のまま (同じ lift・同じバイナリで mode だけ変えた差)。
- **仮説 A は支持されない**。`f_6b8fa0` のサイズは 32bit `imul` で 0 (mod 2^32) になり GetMem(0) → nil。native の `System._GetMem` も size ≤ 0 で nil (`0x409410`・`0x40941a`) で、ホストの `fle_ov_getmem` と一致する (GetMem の差ではない)。この経路に入れば native も buf = 0 のまま fill する。したがって例外回復の捕捉先を探す必要は、分岐を回避できた今は無い。
- ~~**既定経路は不変** (FLE_IPP 未指定・0 = 209 / 1,891・776)。opt-in の `FLE_IPP=3` だけが変わる。よって PR は `Refs #672` (`Closes` の条件『診断なしの既定経路で units_run > 209』は未達)。~~ → 訂正 (§C-2): 既定経路は boot_roots の `0x976da0` 追加後 895 (受入 2 達成)。PR の `Refs` / `Closes` は PM 判断どおり `Refs #672` のまま。

### B-2 静的判定 (`fle672_static.py` の出力の要点)

| 関数 | VA | pdata flags | EH scope | 判定への意味 |
|---|---|---|---|---|
| `f_815050` (2^20 面を作る) | 0x815050 | 2 (UHANDLER のみ) | なし | 自身に try/except は無い |
| `f_815e10` (分岐) | 0x815e10 | 0 | なし | 分岐入力の源 (B-1) |
| `f_11c2d80` (`f_815e10` の呼出元) | 0x11c2d80 | 3 | kind 2 は `0x11c3adf`〜`0x11c3b0f` のみ。呼出し `0x11c3713` は kind 0 (後始末) の範囲 | 捕捉なし |
| `f_6b8fa0` / `f_6cefb0` / `f_6c7610` | — | 0 | なし | 確保・取得・fill に EH は無い |
| `f_4120c0` (System.InitUnits) | 0x4120c0 | 3 | kind 2 `0x4120ed`〜`0x412135` | unit 209 の後の `MessageBoxA` 経路 (`0x4128b0`→`0x412a12`) の上位 (参考) |

分岐の要点 (`fle672_static.py` §2):
- `0x815e1e` の `cmp [0x15F6F90]` が 0 の初回だけ初期化 (`f_6539e0` = LoadLibraryW → `[0x15F6F80]`、`f_4235f0` = GetProcAddress → `[0x15F6F88]`)。
- `0x815e60`〜`0x815e6b`: `[0x15F6F91] = ([0x15F6F88] != 0)`。`0x815e8d` で 0 なら `0x815eb5` → `call 0x815050` (2^20 面)。
- 名前 (UTF-16): `L"ILTools"` (`0x815edc`)・`L"CreateCursorFromFont"` (`0x815eec`)。`ILTools_x64.dll` の export にあたる (`tools/iltools/REPORT.md`)。
- `f_815050` の寸法: `movabs rax, 0x4130000000000000` = 1048576.0 (`0x81571b`・`0x81572c`)。`W = f(c1) + SPI + f(2^20 + c2) + 4·SPI` で、定数 2^20 は stub 値に依らない。**寸法 2^20 は stub の誤りではない**。誤るのは『その面を作る分岐に入ること』。

### B-3 実測 (同一 lift・clang 1 回。`fle6_measure.sh` の route)

| route | FLE_IPP | units_run | GetMem / FreeMem | fill `0x6a7b70` | 空の MessageBoxA | 停止 (threw) | CreateCursorFromFont 呼出し | `ptr_15F34A0` |
|---|--:|--:|--:|--:|--:|---|--:|---|
| shim (既定の shim) | 1 | 209 | 2,314 / 1,199 | 6 | 1 | `exit(0)` @0x412a12 | 0 | 0x0 (IPP 判定 NG = 既知) |
| ネガコン | 0 | 209 | 1,891 / 776 | 6 | 1 | `exit(0)` @0x412a12 | 0 | 0x0 (OK) |
| **ILTools 分岐入力 (本 PR)** | **3** | **851** | 3,139 / 1,490 | **0** | **0** | `unlifted 0x976da0` (呼出元 `0x92d24e`・`f_92d150` 内) | **64** (0x815e9c・fail-soft 0) | 0x7f10001c (OK) |

- ILT route のログには `MessageBoxW text='QuickFontCache DLL not found!'` が出る (既知の T-SH 系の別件・B-4)。
- 製品 KPI (既定経路): §C 参照 (訂正済み: 209 → 895)。最初のウィンドウ: 未達 (ILT route は訂正前の測定で unit 851 の unlifted 0x976da0 で停止)。
- 検証範囲: 1 本の lift (`closure 2`・root `0x6a7b70`)。n = 1。範囲外: native 実行による ILTools の読込・CreateCursorFromFont の戻り値の突合。

### B-4 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ILT route の停止 `unlifted 0x976da0` (呼出元 `0x92d24e`・`f_92d150`) | 最初のウィンドウ未達 | 子 issue (本 PR で起票) |
| `CreateCursorFromFont` の戻り値 0 (fail-soft) と代替経路の後続 (`0x866290`) の値の正しさ | 851 の内容が未検証 | 子 issue (同上) |
| ILT 分岐入力を既定 (`FLE_IPP` 未指定) にするか | KPI の既定経路 (209 → 851) | PM 判断 (本 PR は opt-in のまま) |
| `ILTools` の native 読込成功 (DLL の存在と LoadLibraryW の結果) は未実測 | 分岐入力の native 値の前提 (推定) | 子 issue (同上) |
| `QuickFontCache DLL not found!` (MessageBoxW) | 別の停止要因の可能性 | 既存 T-SH 系 (#3410・#3412・#3434) |
| `f_6cefb0` の rect fill で buf = 0 の書込み (shim・ネガコン) が native で AV になるか | 分岐回避のため現時点では影響なし | 本 PR では未扱い (下の D27 案) |

### B-5 欠陥類型の候補 (`docs/DEFECTS.md` 形式の行案・直接編集は PM 判断)

| ID (案) | 種別 | 症状 | 根本原因 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|---|---|
| D26 (案) | ours (shim) | 条件分岐が native と別の計算経路 (2^20 面) に入り、後続 unit が止まる | 外部 API の soft stub の既定戻り値 0 (LoadLibraryW・GetProcAddress) が分岐入力に入る | 本 PR: FLE_IPP=3 で 209 → 851 (mode 1 は 209) | 分岐入力に入る API 戻り値を native 値と突合 | 分岐入力を native 相当の非 0 にする擬似モジュール (本 PR・opt-in) |
| D27 (案) | ours (harness) | buf = 0 の fill が AV にならず、native の例外経路を通らない (推定) | guest メモリは平坦で 0 番地への書込みが AV にならない | shim・ネガコン で fill 6 回 (buf = 0) | buf = 0 の fill 呼出し (`FLE_DIAG_NULLFILL` の計数) | 未実装 (経路回避で当面見えない) |

### B-6 旧判定の訂正

- §1-2 (`REPORT_APPENDIX_3090.md`) の『native では面の生成が失敗して別経路に入る (推定)』は、**別経路 = 代替経路 (`f_815e10` の flag != 0) への分岐**であり、面の確保失敗 (仮説 A) ではない。
- `REPORT_APPENDIX_3090.md` §1-2 の『`[this+0x50]` buf = 0 のまま』は、2^20 面の経路に入った lift の結果であり、native の状態ではない (B-1)。

- §D (#4783 の既定変更の影響の実測・受入 1〜3) は `REPORT_APPENDIX_4783.md` に分割移動 (250 行上限)。
### B-7 停止点 `unlifted 0x976da0` の実体 (#4032・測定 commit は本 PR の HEAD)

> 再現: `python3 tools/flelift/boot/fle672_static.py <PE>` と下の逆アセンブル (capstone)。動的は `FLE_EXTRA_ROOTS=0x6a7b70,0x976da0 FLE_BOOT_TAG=fle672root976 FLE_BOOT_RUNS=ilt bash tools/flelift/boot/fle6_measure.sh`。結果 JSON: `results/boot_summary_fle672root976_ilt.json`。

- **実体**: PE 内の小さな thunk (`.text`・pdata あり)。`0x976da0: sub rsp,0x28; call 0x976fd0; add rsp,0x28; ret`。`0x976fd0` は `call 0x425210` (`jmp [IAT]`) で、IAT slot `0x1970b10` = **`user32!PostMessageW`**。つまり『ウィンドウへメッセージを投げる』薄いラッパ。ILTools の API ではなく、lift 関数でもない (PE 内の関数)。
- **なぜ unlifted か**: 直接 call / jmp の先ではない。関数 `0x976c80` が `lea rcx,[rip+0x109]` → `mov [rax+0xc], rcx` で **オブジェクトの vtable 風スロット (+0xc)** に格納する。呼出元 `0x92d24e` は `call [rbx+0xc]` の戻り先で、間接 dispatch。lift の `textrefs` (11,037 件) にも `0x976da0`・`0x976fd0` は無い (`lift_meta.json`)。したがって lift は root / 直接 callee として発見できず、実行時に unlifted で止まる。
- **実測 (n = 1・同一 lift 方式)**:

| route | 追加 root | units_run | 停止 (boot_threw) | getmem / freemem | CreateCursorFromFont 呼出し |
|---|---|--:|---|--:|--:|
| 既定 (FLE_IPP 未指定) | なし | **209** | `exit` @0x412a12 | 1,891 / 776 | 0 |
| ネガコン (FLE_IPP=0) | なし | **209** | `exit` @0x412a12 | 1,891 / 776 | 0 |
| ILT 分岐入力 (FLE_IPP=3) | なし | 851 | `unlifted 0x976da0` | 3,139 / 1,490 | 64 |
| ILT 分岐入力 + 0x976da0 root | `0x976da0` | **895** | `oob memory access out of bounds` | — | 64 |

- 0x976da0 を root 化すると、停止点は unit 851 → 895 に進み、`unlifted` は消える。
- **訂正 (2026-10-15 再測定・§C-2)**: 次の停止は `oob memory access out of bounds` と書いたが、同じ構成 (ILT + root `0x976da0`) を新規 lift で測ると `exit` (code 0) で止まり、`oob` は再現しなかった。下の『既定経路は不変』も誤りで、既定経路は `boot_roots.json` の `0x976da0` 追加後に 209 → 895 になっている (§C)。
- ~~**既定経路は不変** (209 → 209)。よって受入 2『既定経路で units_run > 209』は**未達**。root 化は `FLE_EXTRA_ROOTS` の opt-in で、既定 (`fle6` の root 0x6a7b70 のみ) には入っていない。~~ → 訂正: 既定経路は boot_roots 追加後 895 (§C-1・§C-2 で再現)。受入 2 は達成。

### B-8 未解決 (起票先付き・本 PR)

訂正 (§C-2): 下表の『既定経路で units_run > 209 (受入 2)』『子 #4286 (FLE-22)』は、既定経路が 895 に達した (§C) ことで不要になった。受入 2 は達成済み。『oob』行は再現しなかった (§C-2) ので、下表の更新版を使う。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x976da0 の root 化 (既定 root) の survey 破裂の有無 (`survey_drive.sh` 未実施) | 既定の survey 942 unit の functional 判定 | #4783 [FLE-25] |
| unit 895 の `exit` (code 0) が正常終了か (MessageBoxW 不在の影響か) | 最初のウィンドウ未達 | #4782 [FLE-24] |
| ILTools の native 読込の成否 (mode 3 の入力の正しさ・推定のまま) | 既定経路 895 の前提 | #4783 [FLE-25] |
| B-7 の `oob` 再現の不一致 (旧 run の build・lift の差の原因) | 再現性 | 再現せず (§C-2)。原因不明のまま記録 |
| 0x976c80 の vtable 格納を lift の間接 callee 解析で拾う方式 | 同種の thunk が他にもある可能性 | PM 判断 (未起票) |

### C-2 再測定 (2026-10-15・HEAD 再 lift・toolchain-emsdk 6.0.12 上流 install)

- 素材: `fl-win64` は取得済み。`toolchain-emsdk` は `$ARTIFACTS_DIR` に無かったため、上流 `emsdk install 6.0.12` (`tools/m1/flags.sh` の pin と同版) で代替した。
- 測定 commit: `dec8fa928` (コードを変えた最後の commit)。`git diff dec8fa928 HEAD -- tools/flelift/boot` は空。

| route | 追加 root | units_run | 停止 (boot_threw) | getmem / freemem | IPP 判定 | 結果 JSON |
|---|---|--:|---|--:|---|---|
| 既定 (`FLE_EXTRA_ROOTS` 未指定・mode 3) | 0x6a7b70 + boot_roots (0x976da0) | **895** | `exit` (code 0) | 3,680 / 1,499 | ok (ptr=0x7f10001c) | `results/boot_summary_fle672rerun_default.json` |
| ネガコン (`FLE_IPP=0`) | 同上 | **209** | `exit` (code 0) | 1,891 / 776 | ok (ptr=0) | `results/boot_summary_fle672rerun_negctl.json` |
| B-7 構成 (ILT + `FLE_EXTRA_ROOTS=0x6a7b70,0x976da0`) | 同上 | **895** | `exit` (code 0) | 3,680 / 1,499 | ok (ptr=0x7f10001c) | `results/boot_summary_fle672b7rerun_ilt.json` |

- 停止点: 既定 (と B-7 構成) とも unit 895 の後に `exit` (code 0・call site `0x412a12`)。`oob memory access out of bounds` は **どの構成でも再現しなかった**。B-7 の旧 `oob` run は再現できず、原因は未切り分け (旧 run の build・lift の差の可能性)。
- 所要 (実測): lift 81 s・clang plain (8 shard) 100 s (既定) / 83 s (B-7)・boot default 10 s・boot negctl 26 s。load 1.1〜2.2 (4 vCPU)。
- 結論: 既定経路 209 → 895 は新規 lift で再現した。受入 2 (既定経路 > 209) は満たす。`oob` は再現しないため、PM 判断 (2026-10-15) どおり本 PR は `Refs #672` のまま (`oob` の切り分けが #4782 で未了のため `Closes` にしない)。`exit` (code 0) が正常終了か (最初のウィンドウ未達) は未解決。

## §C. 既定経路の更新 (2026-10-15・PM 判断 1・2 の実装)

- **判断 1 (ILT 分岐入力の既定化)**: `fle_boot.mjs` の `FLE_IPP` 未指定・空を mode 3 (旧 `FLE_IPP=3` と同じ ILTools 擬似モジュール) にした。`FLE_IPP=0` (ネガコン) と `1` / `2` は変えていない。ILTools の native 読込成功は**推定のまま** (未実測)。
- **判断 2 (0x976da0 の既定 root 化)**: `boot_roots.json` に `0x976da0` を追加 (`FLE_EXTRA_ROOTS` の一時指定ではなく既定の root)。survey 破裂の有無は未確認 (前例 0x6a7b70 は破裂)。
- **既定 root**: `fle6_measure.sh` の既定 (`FLE_EXTRA_ROOTS` 未指定) は `0x6a7b70` を足す。既定経路 = `0x6a7b70` (従来) + `boot_roots.json` の `0x976da0` (本変更)。

### C-1 実測 (n=1・既定 route・同一 lift・clang plain 1 本)

| route | `FLE_IPP` | root | units_run | GetMem / FreeMem | IPP 判定 | 停止 (boot_threw) |
|---|--:|---|--:|--:|---|---|
| 既定 (本変更) | 未指定 (→3) | 0x6a7b70 + boot_roots (0x976da0) | **895** | 3,680 / 1,499 | ok (ptr=0x7f10001c) | `exit` @0x412a12 |
| ネガコン | 0 | 0x6a7b70 + boot_roots (0x976da0) | **209** | 1,891 / 776 | ok (ptr=0) | `exit` @0x412a12 |
| 参考: 既定 (root 無し `FLE_EXTRA_ROOTS=`) | 未指定 (→3) | boot_roots (0x976da0) | 895 | 3,680 / 1,499 | ok | `exit` |
| 参考: ネガコン (root 無し) | 0 | boot_roots (0x976da0) | 209 | 1,890 / 776 | ok | `unlifted` 0x6a7b70 |

- 製品 KPI (既定経路・起動): units **209 → 895**。最初のウィンドウ: 未達 (停止は `exit` (code 0)。`MessageBoxW` 系の表示は本 run の範囲外)。
- ネガコン (`FLE_IPP=0`) は 209 のまま。既定化の効果は ILT 分岐入力 (IPP mode 3) によるもので、root 0x976da0 単独の効果は未測定。
- B-8 の予測 (`oob memory access out of bounds`) とは異なる。B-7 の `oob` run は `FLE_EXTRA_ROOTS=0x6a7b70,0x976da0` で、既定 (同じ root・mode 3) では `exit` だった。B-7 と本 run の差は未切り分け (lift の再生成・build の差の可能性)。
- 所要 (実測): lift 81 s・clang plain (8 shard) 99〜102 s・boot default 9 s・boot negctl 10〜25 s。load 1.0〜1.95 (4 vCPU)。
- 未解決: 既定 root 化の survey 破裂 (`survey_drive.sh` 未実施)・unit 895 の `exit` が正常終了か (MessageBoxW 不在の影響か) は未特定。
- **測定 commit `dec8fa928`** (コードを変えた最後の commit)。HEAD で再測定 (`FLE_BOOT_RUNS="default negctl"`・`FLE_EXTRA_ROOTS` 未指定): 既定 units **895** (GetMem 3,680 / FreeMem 1,499・`exit`)、ネガコン units **209** (1,891 / 776・`exit`)。C-1 と同値。lift 80 s・clang 96 s・boot 9 s / 25 s。`git diff dec8fa928 HEAD -- tools/flelift/boot` は空。

### E. #4782 (FLE-24): 既定経路の unit 895 と B-7 `oob` の切り分け (2026-10-15)

- 測定 commit: `8a61b584f` (origin/main。コードを変えた最後の commit)。結果 JSON は `results/boot_summary_fle24def_default.json` と `results/boot_summary_b7re_ilt.json` の 2 件。`git diff 8a61b584f HEAD -- tools/flelift/boot/*.c tools/flelift/boot/*.mjs tools/flelift/boot/*.py tools/flelift/boot/*.sh tools/flelift/boot/boot_roots.json` は空。
- **E-1 既定経路 (`FLE_BOOT_RUNS=default`・`FLE_EXTRA_ROOTS` 未指定・lift を新規に再生成)**: units **895**・GetMem 3,680 / FreeMem 1,499・`threw` = `exit` (code 0)。`oob` 無しの根拠は `threw.cls = exit` (code 0) と `units_run = 895` だけ。**ログは保存していない** (`log_cap.cap = 0`・`bytes = 0`・`head`/`tail` 空)。そのため、ログ件数 (`out of bounds`・`MessageBoxW`) と trap 箇所 (call site) は根拠にしない。trap 箇所は特定していない。`exit` が正常終了かは未判定 (子 issue #4970 [FLE-36])。
- **E-2 同一 binary の再実行**: 同じ `fleboot_plain.cjs` を 2 回再実行 (`FLE_IPP` 未指定・`FLE_BOOT_LOG_CAP=0`) と、`FLE_BOOT_LOG_CAP=268435456` (B-7 の run の値) の 1 回は、いずれも 895・`exit` と記録した。**結果 JSON は残していない** (成果物なし・件数の記録のみ)。決定性の根拠としては検証できない記録として扱う。
- **E-3 B-7 構成を現 head で再測定**: 測定 commit `024bfc63c` (本 PR の検証 HEAD・boot の実行コードは `8a61b584f` と同一)。`FLE_EXTRA_ROOTS=0x6a7b70,0x976da0 FLE_BOOT_RUNS=ilt` で lift・clang (8 shard)・boot を最初から実行した。結果は 895・`exit` (code 0)・`oob` 無し。結果 JSON: `results/boot_summary_b7re_ilt.json` (前回の e64581479 の値を差し替え)。所要 3m17s (lift 80 s・clang 101 s・boot 9 s)。素材: `fl-win64`・`toolchain-emsdk` 6.0.12。
- **E-4 切り分けの結果**: `oob` は現在の lift・build・同一構成のどれでも再現しない (E-1・E-3 の 2 系統)。B-7 と既定の `exit` の差の原因は**未切り分け**。候補は、当時の lift・clang の差 (成果物が無い) と、当時の emsdk の版の差 (成果物が無い)。
- 所要 (実測): lift 80 s・clang plain 8 shard 114 s・boot default 10 s・全体 3m30s。load 0.99〜2.28 (4 vCPU)。素材: `fl-win64`・`toolchain-emsdk` (6.0.12)。
