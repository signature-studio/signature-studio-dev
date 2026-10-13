# tools/plugins/f1 REPORT — [PLG-F1] stereo-util 9 本 lift (#198)

- 担当 dir: `tools/plugins/f1/` (+ `tools/plugins/inventory/blockmap_from_matrix.py`)。 検証起点 commit: c64a2b3 (§8)。
- 既知類型との関係: **D15 (DEFECTS.md)** (+ Mute 2 fade で **D5 (DEFECTS.md)**) = メモリ間接 `call [mem]` の silent 脱落。 RetDec 路線では `tools/icall/REPORT.md` §4 の **D1 (icall §4)** と同じ事象 (番号体系は別)。 新規類型なし。
- 数え方・コマンドはすべて本ファイル内に併記。 数値はすべて Actions runner (nproc=4) 上の実測。

## 0. 結論 (先出し)

1. **9 本 (T0 8 + T1 1) の固有閉包 lift は Actions 上で再現した**: 9/9 が RetDec+pass 鎖 完走・`emcc -c` 通過・f80 関数 0・未実装 helper 0。 `defines` は PLUGIN_MATRIX の `closure_funcs` と 9/9 一致 (§2)。
2. **ただし「`emcc -c` 通過 = 正しい lift」ではない — 9 本全てで、閉包内のメモリ間接 call 185/185 件が IR から無言で脱落している** (§4)。 vtable 経由の GUI/ホスト呼出に加え、**Eff_Render が DSP を呼ぶ関数ポインタ呼出も含まれる**。
3. **Fruity Phase Inverter の Eff_Render を native 機械語と bit 比較 (492 case × 3 seed)**: in-place 246/246 一致 (符号反転ループの lift は正しい)、**src≠dst の 246 case 中 240 case が不一致** (`dst` が未コピーのまま)。 脱落した `ippsMove_8u` 呼出 1 件だけを手で書き戻した oracle 版は **492/492 一致**、コピー長を 4 byte 短くした陰性対照は 240 fail (§5)。
4. **Fruity Mute 2 の Eff_Render も同様** (510 case × 3 seed, §5b): 無効/mode3/mode1 の分岐は、脱落した IPP 呼出 2 件 (`ippsCopy_64s`, `ippsZero_8u`) を oracle で戻すと 306/306 一致。 **fade 分岐 (mode0/mode2) は 192/204 不一致のまま** — 呼出先 `function_5df490` が float 引数 (xmm3 + スタック) を正しく受けておらず、D5 (DEFECTS.md) 同型の ARG 欠陥が Eff_Render 層で実害になる。
5. **Eff_Render 経路の依存を 9 本分実測** (§3): kernel 表 (P0c) の関数ポインタ変数だけでなく、**dsp_ippv2.dll の動的束縛変数 (`ippsCopy_64s` / `ippsMove_8u` / `ippsZero_8u` / `ippsAdd_32f_I` / `ippsSub_32f_I` / `ippsCplxToReal_32fc` / `ippsRealToCplx_32f`) を呼ぶ**。 Phase Inverter / Mute 2 / Center の Eff_Render は DSP 本体が IPP 呼出で、plugin 固有コードは分岐とループのみ。
6. **#198 の出口条件 (全員で差分試験 bit-exact + Render test .flp) は未達**。 理由は、メモリ間接 call の復元 (#229 ICALL-3) と IPP 関数ポインタの接続 (#38 IPP-10 / `tools/ipp/shim`) が plugin 閉包に未統合であること (§6)。 本 PR は `Refs #198` (Closes しない)。

## 1. 環境・再現

```sh
# Actions: oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk
bash tools/plugins/f1/f1_e2e.sh
```

- `f1/env.sh`: `$ARTIFACTS_DIR/fl-win64.tar.zst` を `$RUNNER_TEMP/fl-win64` に展開 (実測 8.3 秒) し `FL_WIN64_DIR` を設定、`pefile` + `capstone==5.0.7` + `numpy` の venv を `$RUNNER_TEMP/f1venv` に作る。
- **inventory の前提 (今回判明)**: `lift/plugin_closure.py` は `work/win_pe_scan.json` / `work/winfuncs/*.json` / `work/win_abi.json` を要求する。 `win_funcs.py` は `work/nsis_blockmap.json` を要求し、これを作る `nsis_names.py` は
  インストーラ `~/ダウンロード/*.exe` と `block_manifest.json` (fl-win64 tarball に無い) を要求する。 → `inventory/blockmap_from_matrix.py` を追加: `PLUGIN_MATRIX.json` の 181 PE (x64 180) から
  `win_funcs.py` が使う `idx/kind/outdir` だけの最小互換 blockmap を作る (nsis_names.py の 25,164 件の代替ではない)。 これで `win_scan.py` → `blockmap_from_matrix.py` → `win_funcs.py` (180 PE) → `win_abi.py` が素材のみで通る (`win_funcs.py` + `win_abi.py` の合計 **7 分 57 秒**, nproc=4, `win_abi.py` 単体は 2.0 秒)。
- 前提確認: `bash tools/plugins/lift/t0_balance/t0_e2e.sh` (Balance kernel 2 本) は本環境で **3.05 秒・357/357 × 3 seed = 1,071/1,071 一致** (REPORT.md §3 の既存値と同一) → toolchain は Actions 上で健全。

## 2. 9 本のバッチ lift (固有閉包; `batch_lift.sh`, 実測)

3 回実行 (逐次, load avg 1 分値 0.54 / 0.70 / 0.80 開始): **24.74 / 24.75 / 24.84 秒** (9 本合計)。 per-plugin `seconds` は 2〜3 秒。

| block | plugin | Tier | 閉包 関数 / x86 B | IR define | f80 関数 | 未実装 helper | `emcc -c` rc |
|---|---|---|---|--:|--:|--:|--:|
| 18983 | Fruity Balance | T0 | 13 / 6,787 | 13 | 0 | 0 | 0 |
| 18988 | Fruity Center | T0 | 8 / 1,843 | 8 | 0 | 0 | 0 |
| 19049 | Fruity Mute 2 | T0 | 10 / 2,469 | 10 | 0 | 0 | 0 |
| 19056 | Fruity PanOMatic | T0 | 15 / 6,287 | 15 | 0 | 0 | 0 |
| 19065 | Fruity Phase Inverter | T0 | 10 / 1,993 | 10 | 0 | 0 | 0 |
| 19076 | Fruity Send | T0 | 13 / 4,903 | 13 | 0 | 0 | 0 |
| 19084 | Fruity Stereo Enhancer | T0 | 15 / 6,206 | 15 | 0 | 0 | 0 |
| 19085 | Fruity Stereo Shaper | T0 | 20 / 13,601 | 20 | 0 | 0 | 0 |
| 19250 | Spreader | T1 | 26 / 10,483 | 26 | 0 | 0 | 0 |
| 計 | 9 本 | | 130 / 54,572 | 130 | 0 | 0 | 0 |

定義: 閉包 = `plugin_closure.py` が vtable override から `call/jmp rel32` で辿った .pdata 関数 (framework 共通ハッシュ (≥13 DLL) は frontier として除外)。 `IR define` = `p.final.ll` の `define` 行数。
集計: `work/batch/status.csv` (`closure_funcs` と `defines` が 9/9 一致、PLUGIN_MATRIX の `lift.closure_funcs` とも 9/9 一致)。

## 3. Eff_Render 経路の依存マップ (`f1_plan.py`)

`python3 tools/plugins/f1/f1_plan.py <block...>` — Eff_Render から direct call を BFS (framework 側関数も含める) し、`mov reg,[rip+cell]` の cell が指す .bss 変数を分類。
kernel 表は Balance の初期化関数 (0x5e19f0) と位置非依存ハッシュが一致する関数を各 DLL から探して復元 (9 本全てで 1 件に特定、45 変数)。 候補 2 実装のうち ymm/AVX 命令を含まない方を採る。

| plugin | Eff_Render | 経路 関数 / B | kernel 表変数 → 採用実装 (x87) | IPP 動的束縛変数 (束縛名) |
|---|---|--:|---|---|
| Balance | 0x6befc0 | 3 / 742 | 0x71e4f0 → 0x5dee90 (-) | なし |
| Center | 0x6a3100 | 1 / 61 | 0x7005e0 → 0x5ddf10 (**x87**) | 0x6fee90 `ippsCopy_64s` |
| Mute 2 | 0x6baaf0 | 2 / 376 | なし | 0x717ec8 `ippsZero_8u`, 0x717e90 `ippsCopy_64s` |
| PanOMatic | 0x6c6cc0 | 4 / 918 | 0x7274f0 → 0x5def10 (-) | なし |
| Phase Inverter | 0x6ba930 | 2 / 127 | なし | 0x717e98 `ippsMove_8u` |
| Send | 0x6bdb80 | 3 / 917 | 0x71c4f8 → 0x5df3d0, 0x71c4d0 → 0x5df7f0 (-) | 0x71ae90 `ippsCopy_64s` |
| Stereo Enhancer | 0x6bfec0 | 4 / 997 | 0x71f4f0 → 0x5df0e0 (-) | 0x71de90 `ippsCopy_64s` |
| Stereo Shaper | 0x6cf460 | 38 / 5,071 | 0x7324f0 → 0x5dfb70 (-) | `ippsCopy_64s`, `ippsAdd_32f_I`, `ippsSub_32f_I`, `ippsCplxToReal_32fc`, `ippsRealToCplx_32f`, + 1 件 (0x732390) は名前未特定 |
| Spreader | 0x6da430 | 29 / 2,988 | なし | 0x73ce98 `ippsMove_8u` |

- IPP 変数の名前は、framework の binder (`lea rdx,[var]; lea r8,[name]; call GetProcAddress 相当`) の文字列 (UTF-16) を機械語から読んだ値 (Phase Inverter 0x717e98 → `ippsMove_8u` は手動の逆アセンブルでも確認)。
- Send は kernel 側 BFS が 40 関数を追加で引き込む (経路 3 → 計 43 関数 / 5,115 B)。 kernel 内の direct call 先は未精査。
- Center の採用 kernel 0x5ddf10 は x87 命令を含む → P0c の f80 pass (`tools/plugins/p0c/REPORT.md`) が必要。
- Balance / PanOMatic の経路には `ramp` (0x5dfef0 等) が入る。 これは float 引数 (xmm3 + スタック) を取り、ARG pass が必要 (batch_plan §4 の ARG)。

## 4. 脱落 call の静的監査 (`f1_call_audit.py`)

`python3 tools/plugins/f1/f1_call_audit.py <block...>` — 閉包の各関数の機械語 `call` 数 (direct / `call [mem]` / `call reg`) と、`p.final.ll` の対応 `define` の call 数
(`llvm.*` と `__asm_*` helper は除外) を比べる。 `dropped_est = max(0, 機械語 call 総数 − IR call 数)` (下限の目安; tail-jmp・関数分割は考慮しない)。

| block | plugin | 関数 | 機械語 direct | 機械語 `call [mem]` | `call reg` | IR call | dropped_est | 脱落のある関数 |
|---|---|--:|--:|--:|--:|--:|--:|--:|
| 18983 | Balance | 13 | 120 | 11 | 0 | 119 | 12 | 7 |
| 18988 | Center | 8 | 40 | 13 | 0 | 40 | 13 | 5 |
| 19049 | Mute 2 | 10 | 49 | 13 | 0 | 49 | 13 | 5 |
| 19056 | PanOMatic | 15 | 113 | 12 | 0 | 113 | 12 | 6 |
| 19065 | Phase Inverter | 10 | 45 | 11 | 0 | 45 | 11 | 5 |
| 19076 | Send | 13 | 75 | 18 | 0 | 75 | 18 | 6 |
| 19084 | Stereo Enhancer | 15 | 114 | 15 | 0 | 115 | 15 | 7 |
| 19085 | Stereo Shaper | 20 | 303 | 33 | 0 | 303 | 33 | 10 |
| 19250 | Spreader | 26 | 188 | 59 | 0 | 189 | 59 | 13 |
| 計 | | 130 | 1,047 | **185** | 0 | 1,048 | 186 | 64 |

- **direct call はほぼ全て保存される (1,047 → IR 1,048) が、`call [mem]` は 185/185 が IR に出ない**。 `dropped_est` の計 186 = 185 + Balance の 1 件 (0x6c0000: 機械語 direct 22 に対し IR 21 — `call [mem]` 由来ではなく原因未調査, §6)。
  Spreader (19250) と Stereo Enhancer (19084) の IR が direct より各 +1 多いのは tail-jmp の call 化と推定 (未確認)。
- 脱落の中身は 2 種: ① vtable 経由のホスト/GUI 呼出 (Dispatcher / ProcessParam / SaveRestoreState 等)、② **Eff_Render 自身の関数ポインタ呼出** (例: Balance 0x6befc0 の `call [rax]` = kernel 0x5dee90、Phase Inverter 0x6ba930 の `ippsMove_8u`)。 ②は DSP が丸ごと消える。
- ネガティブコントロール: §5 の oracle 版は脱落 1 件を戻すだけで 240 fail → 0 fail になる (= 本監査の検出対象と実害が一致)。

## 5. Fruity Phase Inverter Eff_Render 差分試験 (`pi/pi_e2e.sh`)

`bash tools/plugins/f1/pi/pi_e2e.sh` — 全体 **4.8 秒** (load avg 1 分値 0.37)。
- 対象: Eff_Render `0x6ba930` (127 B / 2 関数: 本体 + 符号反転ループ 0x6ba910)。 `this` は 0x400 B の合成領域 (`[this+0x128]` = mode のみ設定)。
- native 参照 `pi/native_pi.c`: 実 DLL を VA 0x400000 に MAP_FIXED 敷設し MS x64 ABI で実機械語を実行 (lift IR/wasm に非依存)。 `[0x717e98]` (ippsMove_8u の関数ポインタ) には同一意味 (memmove) の ms_abi 関数を差し込む (dsp_ippv2.dll は Linux で動かせないため)。
- wasm: `lift_ranges.sh` → `t0_balance/build_wasm.sh` (`pi.wasm` 621 B) → node。 比較対象は `dst` (2n+16 word, ガード 16 word 込み) と `src` (2n word, 不変性)。
- case: n ∈ {0,1,2,3,4,5,7,8,9,15,16,17,31,33,64,100,257} × mode ∈ {−1,0,1,2,3} × {in-place, src≠dst} × 3 rep (src は ±0 / denormal / ±inf / NaN を混ぜた乱数) = **492 case** (n=0 かつ mode>0 は除外, 下記)。
- **除外の根拠**: n=0 かつ mode>0 では native 側が `neg r8; … inc r8; jne` (64bit カウンタ) を 2^64 回回して SEGV する (実測: `SEGV rip=6ba91f, r8=0x3ffff`)。 ホストは Length≥1 で呼ぶと仮定して範囲外にした (未確認)。

| 版 | seed 305441741 | seed 1 | seed 2863311530 |
|---|---|---|---|
| lift そのまま (`pi`) | 252 / 492 | 252 / 492 | 252 / 492 |
| 脱落 call 1 件を oracle で書き戻し (`pir`) | **492 / 492** | **492 / 492** | **492 / 492** |
| 陰性対照: コピー長 −4 B (`pin`) | 252 / 492 | 252 / 492 | 252 / 492 |

`pi` の内訳 (一致 / 不一致): in-place は mode≤0 102/0・L 反転 96/0・R 反転 48/0 = **246/0**。 src≠dst は mode≤0 6/96 (一致 6 は n=0)・L 反転 0/96・R 反転 0/48 = **6/240**。
不一致の形は 1 通り: wasm の `dst` が `0xA5A5A5A5` (試験側のフィル値) のまま = コピーされていない (L 反転は先頭 word が `0x25a5a5a5` = 符号ビットだけ反転した未コピー値)。
- `pir` は `pi_repair_oracle.py` が `function_6ba930` の先頭に `if (src != dst) f1_ipps_move_8u(src, dst, Length<<3)` を挿入した**試験専用**版 (lift pass ではない)。 目的は「この経路の差分の原因は脱落 call 1 件のみ」の確認 (ablation)。
- 陰性対照 `pin` (`PI_NEGCTL=1`): コピー長を 4 B 短くすると in-place 以外の n>0 が全て落ちる (240 fail)。 試験は 1 word の欠落を検出できる。
- 検証範囲 (Phase Inverter): Eff_Render の分岐 (`mode≤0` / `==2` / その他)・in-place 判定・符号ビット反転ループ・コピー呼出の有無。 範囲外: IPP 実装そのもの (stub の意味は memmove と仮定)、ホスト経由の Eff_Render 呼出、他 8 本。

## 5b. Fruity Mute 2 Eff_Render 差分試験 (`mute/mute_e2e.sh`)

`bash tools/plugins/f1/mute/mute_e2e.sh` — 全体 **9.9 秒** (3 seed × 3 版)。 Phase Inverter と同じ構成 (native: `mute/native_mute.c`, wasm: `mu.wasm` 2,877 B)。
- 対象: Eff_Render `0x6baaf0` (+ framework の fade `0x5df490`, 経路 2 関数 / 376 B)。 `this`: `[+0x128]` = 有効 (byte), `[+0x12c]` = mode (int)。
- native の IPP 変数: `0x717ec8` = `ippsZero_8u(pDst,len)` (memset 0), `0x717e90` = `ippsCopy_64s(pSrc,pDst,len)` (len 要素 × 8 B の memmove) を同一意味の ms_abi 関数で差し込む。
- case: n × 17 値 × {無効, 有効 mode0/1/2/3} × {in-place, src≠dst} × 3 rep = **510 case** (src は NaN/inf を含まない乱数: wasm の NaN 伝播は非決定的なため)。
- 分岐の意味 (機械語): 無効 → src≠dst なら Copy_64s。 mode0 → fade A (`5df490` に定数 2 つ: 0x6bab94/0x6bab98 の float)。 mode1 → Zero_8u(dst, n<<3)。 mode2 → fade B (定数の順を入れ替え)。 mode≥3 → 何もしない。

| 版 | 一致 / 510 (seed 305441741) | seed 1 | seed 2863311530 | 一致の内訳 (seed 305441741) |
|---|---|---|---|---|
| lift そのまま (`mu`) | 174 | 175 | 174 | 無効 in-place 51 / 無効 copy 3 / mode3 102 / mode1 6 / fade 計 12 (全て n=0) |
| IPP 2 件を oracle で書き戻し (`mur`) | **318** | 319 | 318 | 無効 102 / mode1 102 / mode3 102 (= 非 fade 分岐 **306/306**) + fade 12 (n=0) |
| 陰性対照 (`mun`: Zero の長さ −4 B) | 222 | 223 | 222 | `mur` から mode1 の 96 case が落ちる (他は同じ) |

- **非 fade 分岐**: `mu` では無効 copy (3/51)・mode1 (6/102) が落ちる = 脱落した IPP 呼出の実害。 `mur` で 306/306 一致、`mun` で mode1 が 6/102 に戻る (試験の識別力)。
- **fade 分岐 (mode0/mode2)**: `mur` でも 4 グループ × 48 = **192 case 不一致** (一致 12 は n=0 のみ。 seed 1 は mode0-copy が 4/51 で +1)。 原因は呼出先 `function_5df490` の IR: 4 番目の整数引数 (`%arg4`) を `movss xmm0` に使い、本来の `xmm3` (開始ゲイン) は零ベクトル (`xor i128 0, 0`) に置換されている。
  caller 側は `xmm3` の値 (開始ゲイン) を渡さず、スタック引数 (終了ゲイン) だけを第 4 整数引数に載せる。 → **D5 (DEFECTS.md) = float 引数の脱落**と同型で、ramp/fade 系 framework 関数 (Balance・PanOMatic も経由) を呼ぶ Eff_Render は ARG pass なしでは動かない。
- 検証範囲: 分岐 5 通り・in-place/非 in-place・n=0〜257・IPP 2 関数の呼出有無。 範囲外: fade の数値 (ARG 未修復), 実 IPP。

## 6. 未解決・ブロッカー (起票依頼)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 閉包内メモリ間接 call 185/185 の脱落 (§4)。 復元は `tools/icall` の binary pre-rewrite (`icall_rewrite.py`) を plugin 閉包に適用する必要がある | 9 本全ての Eff_Render が silent に誤動作。 #198 の出口条件の前提 | 既存 **#229 [ICALL-3]** にコメント (plugin 閉包 = Delphi 殻への適用を追加スコープに) |
| Eff_Render の関数ポインタ変数 (kernel 表 + IPP 動的束縛) の接続: wasm 側で変数に table index を書く初期化手順が無い (framework 初期化 0x5e19f0 は CPUID 分岐、IPP は binder 経由) | 復元後も DSP が動かない | 新規 `[PLG-F1b] Eff_Render 用 kernel 表/IPP 関数ポインタ初期化 (wasm table 登録)` を P0a #195 の子として起票依頼 |
| IPP 7 関数 (`ippsCopy_64s`/`Move_8u`/`Zero_8u`/`Add_32f_I`/`Sub_32f_I`/`CplxToReal_32fc`/`RealToCplx_32f`) の plugin 閉包からの利用経路。 Stereo Shaper の 1 件は名前未特定 (0x732390) | native 参照も dsp_ippv2 無しでは再現不能 (本 PR は memmove stub で代替) | 既存 **#38 [IPP-10]** にコメント (F1 の 7 関数を優先候補に) |
| Center の採用 kernel 0x5ddf10 は x87 | P0c f80 pass の plugin 閉包への適用 | **#195 (P0a)** / P0c 系の既存 issue にコメント |
| ARG (float 引数): **Mute 2 の fade `function_5df490` で実害を実測** (§5b: xmm3 → 零ベクトル, スタック引数 → 第 4 整数引数)。 Balance / PanOMatic の ramp (0x5dfef0 等) も同型の見込み (未検証) | fade/ramp を呼ぶ Eff_Render 全般 | 既存 [PLG-P0c] 系の ARG 項 (p0c REPORT §11) にコメント |
| Balance 0x6c0000: 機械語 direct call 22 に対し IR 21 (direct 1 件の脱落または noreturn 畳み込みの可能性) | 原因未調査 | 本 issue (#198) 上で継続調査 |
| 残る 7 本の Eff_Render 差分 (Center / Send / Stereo Enhancer は §3 の通り IPP + kernel の glue で同型の試験が可能。 Balance / PanOMatic / Stereo Shaper / Spreader は ARG・f80・大きな経路が絡む) | #198 出口条件の残り | #198 を open のまま継続 (本 PR は `Refs #198`) |
| Render test .flp による E2E (PLUGIN_MATRIX の RT 列) | 未実施。 CreatePlugInstance 完全到達 (P0b の未達, `framework/REPORT.md` §6) が前提 | #195 (P0a) / P0b 系 |

## 7. 成果物

| ファイル | 内容 |
|---|---|
| `f1_e2e.sh` | 1 コマンド再現 (素材展開 → inventory → batch lift → plan → audit → Phase Inverter / Mute 2 差分) |
| `env.sh` | `FL_WIN64_DIR` 展開・venv・TMPDIR |
| `f1_plan.py` | Eff_Render 経路 + kernel 表変数 + IPP 束縛変数の抽出 (`work/f1/<block>/plan.json`, `ranges.txt`) |
| `f1_call_audit.py` | 脱落 call の静的監査 (`work/f1/call_audit.json`) |
| `pi/pi_e2e.sh` `pi/native_pi.c` `pi/run_pi.mjs` `pi/pi_repair_oracle.py` | Phase Inverter Eff_Render 差分試験 + oracle ablation + 陰性対照 |
| `mute/mute_e2e.sh` `mute/native_mute.c` `mute/run_mute.mjs` `mute/mute_repair_oracle.py` | Mute 2 Eff_Render 差分試験 (同構成; fade 分岐は ARG 未修復) |
| `../inventory/blockmap_from_matrix.py` | installer 無しで `win_funcs.py` を動かす最小 blockmap |

## 8. 検証 (コミット済み HEAD)

検証起点 commit: **c64a2b3** (`git worktree add --detach … c64a2b3` で展開。 inventory 4 ファイル (`win_pe_scan.json` / `nsis_blockmap.json` / `winfuncs/` / `win_abi.json`) だけを手元から複写し、batch lift 以降は全て HEAD のコードで再実行)。 先行の検証起点 2b7275c (Phase Inverter まで) でも同値を確認済み (exit 0 / 68.9 秒)。

| 項目 | 結果 (実測) |
|---|---|
| `bash tools/plugins/f1/f1_e2e.sh` | **exit 0 / 77.8 秒** (load avg 1 分値 0.10 開始 → 0.76 終了, nproc=4, inventory は再利用) |
| batch lift 9 本 | **26 秒**・9/9 `rc=0 emcc_c=0 f80=0` (§2 と一致; §2 の 3 回計測は 24.74–24.84 秒) |
| 脱落 call 監査 | 9 block とも §4 の表と同値 (direct 1,047 / `call [mem]` 185 / IR 1,048 / dropped_est 186) |
| Phase Inverter 差分 | 3 seed × {pi: 252/492, pir: 492/492, pin: 252/492} (§5 と同値) |
| Mute 2 差分 | seed 305441741 / 1 / 2863311530 × {mu: 174 / 175 / 174, mur: 318 / 319 / 318, mun: 222 / 223 / 222} (/510; §5b と同値) |

衛生確認: `git status --porcelain=v1 -- tools/plugins/f1 tools/plugins/inventory/blockmap_from_matrix.py` = 空 / `git diff --stat origin/main c64a2b3` = `tools/plugins/f1/` と `tools/plugins/inventory/blockmap_from_matrix.py` のみ (他 dir 0) / 20 MiB 超の blob なし。

### DEFECTS.md への行案 (PM 判断)

新規類型なし。 D5 (DEFECTS.md) の観測欄に「Mute 2 fade (`function_5df490`) で xmm3→零ベクトル、Eff_Render 層で 192/204 case 不一致」、D15 (DEFECTS.md) の観測欄に「plugin 閉包 (Delphi 殻) 9 本でも `call [mem]` 185/185 脱落; Phase Inverter Eff_Render で実害 (src≠dst の 240/246 case で dst 未コピー)」を追記する案。
