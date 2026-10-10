# tools/plugins/REPORT.md — Fruity プラグイン 141 種 wasm 化マップ (plugin-matrix)

## 0. 結論 (先出し)

1. **141 プラグイン全数 (Effects 90 + Generators 51) の実測インベントリを mac/win 両側で作成** (`PLUGIN_MATRIX.md/.json`)。 win 側はインストーラ内部スクリプト (NSIS ヘッダ, Image-Line "BI" 拡張) を自作解析して **25,165 ブロック中 25,164 の実パス名を復元** (`inventory/nsis_names.py`) し、`block_manifest.json` では不能だった block↔プラグイン対応を確定した。
2. **構造上の最重要発見**: Delphi プラグイン 133 本は **同一の約 1.6 MB framework (FP_DelphiPlug+RTL+VCL, 関数 ~11.3k)** を静的リンクし、プラグイン固有コードは中央値 71 KB (閉包は T0 中央値 6 KB / 17 関数)。 DSP は framework 内の **共有 SIMD kernel 表 (45 変数 / 80 実装 / 10.9 KB)** を関数ポインタ経由で呼ぶ。 → lift は「framework 1 回 + kernel 表 1 回 + プラグイン固有閉包」の 3 層で進めるのが最短。
3. **Tier**: T0 **42** / T1 **45** / T2 **34** / T3 **20** (計 141)。 推定総工数 ~525 人日 (T0 21 / T1 68 / T2 136 / T3 300; 推定)。
4. **ABI (ABI.md)**: 入口は `CreatePlugInstance(Host, Tag)` (※`CreateFruityInstance` は FLEngine 自身の export で別物)。 plugin vtable は C++ 互換の **20 スロット** (Image-Line 版 Delphi は TObject 仮想を vptr の負側に配置)、ホスト `TFruityHost` は **46 スロット**、`Dispatcher(HostTag, ID, Index, Value)` が窓口。 全 133 DLL で機械確認 (132 で vtable、124 で `TFruityPlugInfo`)。
5. **T0 実証 (Fruity Balance の SIMD kernel 2 本)**: RetDec→pass 鎖→emcc→wasm→node の出力が **実機械語 (Linux ms_abi で DLL を VA 敷設して直接実行) と 1,071/1,071 case で bit-exact** (`bash tools/plugins/lift/t0_balance/t0_e2e.sh`, exit 0)。 差分試験で RetDec/pass 鎖の欠陥 4 種を発見・修復 (batch_plan.md §4)。
6. **バッチ lift の機械的到達性 (実測)**: T0 41 閉包 (781 関数/305 KB) と T1 45 閉包 (2,835 関数/1.26 MB) が RetDec+pass 鎖で **全件 lift 完了**、`emcc -c` 通過は §4.3 の通り。 ※通過 ≠ 正しさ (正しさの実証は §3 の 2 kernel のみ)。

## 1. インベントリ (実測)

### 1.1 win64 (NSIS 展開, `block_manifest.json` + 自作 NSIS 解析)
| 項目 | 値 |
|---|---|
| x64 PE / 全 PE | 258 / 313 (x64: DLL 246 + EXE 12; x86: 55) |
| `CreatePlugInstance` を export する PE | **160** (プラグイン tree 159 + `Shared/SG_x64.dll`)。 `CreateFruityInstance` は FLEngine_x64.dll のみ |
| `Plugins/Fruity/{Effects,Generators}/` 配下の PE | 181 (x64 180 + x86 1)。 141 フォルダ全て mac 側と名前一致 |
| 言語 | Delphi(FP_DelphiPlug, Embarcadero) **133** / MSVC 14.29 C++ **42** DLL (engine・単体 41 + FL Mobile bridge 1) / 他 toolchain の同梱 lib 7 (NDI, Spout, ZGE×3, testdll, Slayer_Engine x86 VC6) |
| engine 分離型プラグイン | 39 本 (Delphi 殻 + C++ engine DLL; 殻と engine の両方が `CreatePlugInstance` を export する物 18 本) |
| 付随データ (plugin dir 内) | 6,232 ファイル / 0.20 GB (NSIS 展開側; mac は 1.11 GB で sample/preset 含む) |
| framework 共通 DLL 文字列 (133 本全て) | `dsp_ippv2.dll`, `Blend2D.dll`, `QuickFontCache(_x64).dll`, `ilvideo_x64.dll`, `FLEngine_x64.dll`, `FruityPlug_x64.dll` (+ Win32 標準) — いずれも framework 側の動的参照 |

### 1.2 mac (pkg 展開)
| 項目 | 値 |
|---|---|
| Mach-O | 177 (**全て universal2** x86_64+arm64; 合計 450 MB / 457 MB) |
| 言語 | **FPC 3.2.3** (Pascal) 134 / clang C++ (libc++) 43。 main (入口) は FPC 129 / clang 12 |
| 入口 | `_CreatePlugInstance` (+ `_SetExternalAppHandle`)。 **export trie にのみ存在** (symtab は strip) — 全 141 フォルダで ≥1 |
| 非 system dylib 依存 | **0** (共有 lib は dlopen 名参照; LC_LOAD_DYLIB は system のみ) |
| 8 本の VST engine ラップ | Delay 3, Frequency Splitter, Transient Processor, Newtone, Vintage Chorus/Phaser, Multiband Delay, Tuner (`engine.vst`) |

### 1.3 プラグイン所有コード量 (framework 共通を除く)
win 固有コードと mac 固有コードの順位相関は **Spearman 0.90 (n=124)**、mac/win 比の中央値 0.88 → Tier はプラットフォーム非依存。 framework 共通部は win 中央値 1.73 MB / mac 1.61 MB。

### 1.4 GUI / ファイル IO / ネットワーク (プラグイン固有コードの Win32 直接呼出; 稀な API のみ計上)
全 133 Delphi プラグインが VCL+Blend2D の GUI を framework 経由で持つ。 固有コードが直接呼ぶ API 分類 (プラグイン数): file_io 45 / dynload(LoadLibrary) 46 / threads 34 / gdi_direct 33 / clipboard_dnd 31 / registry 19 / process 18 / network 4 / audio_codec_midi 4。 **network 4 本は Newtone engine, ZGE(NDI), FL Mobile 系** (ws2_32/sqlite)。 ホスト経由の I/O (Dispatcher ID) は含まない。 他社・外部 lib の文字列依存: elastique 文字列 31 DLL, DirectWave 6, sqlite 3 (FL Mobile), OpenGL/ZGE 2。 (文字列存在 = 使用の証明ではない)

## 2. Tier 分類 (規則と結果は PLUGIN_MATRIX.md §1)
U = framework 共通を除く固有コード。 T0 U<45 KB / T1 <160 KB / T2 <700 KB / T3 ≥700 KB or 単一 engine ≥2 MB or 巨大第三者 (規則は `tier.py`)。

| Tier | 計 | Effects | Generators | 閉包(Delphi 本体, 中央値) | 直接参照する framework 関数(distinct) |
|---|--:|--:|--:|---|---|
| T0 | 42 | 38 | 4 | 6.3 KB / 17 関数 | 283 (53 KB) |
| T1 | 45 | 29 | 16 | 22 KB / 60 関数 | 623 (127 KB); T0+T1 合算 660 (132 KB) |
| T2 | 34 | 17 | 17 | 25 KB / 40 関数 (+ C++ engine 別) | 795 (163 KB) |
| T3 | 20 | 6 | 14 | 34 KB / 81 関数 | 563 (111 KB) |

scope: in 121 / host 9 (Fruity Wrapper×2, Patcher×2, ReWired, MIDI Out, Razer Chroma, Control Surface, Video Player) / big3p 6 (DirectWave, FLEX, ZGE, FL Mobile×3) / gui 5。 優先度は `(1+2×demo出現+0.1×preset+3×RenderTest)/工数`: 上位は Parametric EQ, Limiter, Delay, Stereo Shaper, WaveShaper, Peak Controller, Soft Clipper… (demo = Data 内 .flp 82 本での出現数; Render test .flp **81 本をプラグインに対応付け**)。

## 3. T0 実証 — lift→wasm→node ⟷ native 機械語 (bit-exact)
対象: `Fruity Balance_x64.dll` (block 18983) の mix kernel `0x5dee90` (432 B, 2×2 matrix mix + ramp, SSE) と peak kernel `0x5df940` (248 B)。
参照 = 実 DLL を VA 0x400000 に敷設し MS x64 ABI (gcc `ms_abi`) で実行 (`lift/t0_balance/native_ref.c`、lift IR/wasm に非依存)。

| 工程 | 一致 case / 全 case (357 case: mix 306 [6 mode × n={0..257} × in-place/整列違い] + peak 51) |
|---|---|
| ir5_patch 鎖のみ (RetDec 既定) | 165 / 357 |
| + fix_regparam_alloca (R1) + fix_asm_stores (S1c: movlps store) | 313 / 357 |
| + S1d (128bit store の i64 sext 破壊) | 325 / 357 |
| + fix_orcond_xnor (C1: RetDec が `A&&B` を XNOR に誤畳み込み) | **357 / 357** (3 seed 計 **1,071 / 1,071**) |

`bash tools/plugins/lift/t0_balance/t0_e2e.sh` が lift→build→3 seed 比較を 2.3 秒で実行 (exit 0=全一致)。 peak kernel は無修正で 51/51。
未実証: Eff_Render 本体 (float 引数 xmm3/スタック → `ir7_argpass` 系の再適用が必要), 関数ポインタ変数 `0x71e4f0` の初期化 (`0x5e19f0` 静的解決)。

## 4. バッチ lift 雛形の実測
### 4.1 DSP kernel 表 (framework 初期化 `0x5e19f0`)
45 変数 / 80 実装 (35 変数は 2 実装から選択) / 計 10.9 KB。 **80 本全て RetDec 完走・`__asm_*` helper 48 種は全て実装済 (署名駆動生成)**。 ただし **26/80 本に x87 (`x86_fp80`) が混入** → wasm バックエンドで libcall 無し (f80→f64 lowering pass が未実装, batch_plan F80)。
### 4.2 lift 鎖の追加 pass (差分試験・バッチで実測した欠陥 → 修復)
R1/S1c/S1d/C1 (§3), D1 重複 declare (T0 5/42 本), T1 ptr 仮引数不整合 (T1 7/45 本; `fix_ptr_params.py`)。
### 4.3 バッチ結果 (`work/batch/status.csv`, 閉包のみ lift; framework は P0 側)
| Tier | 閉包数 | RetDec+pass 鎖 完走 | `emcc -c` 通過 | 閉包規模 (関数 / x86 コード) | 備考 |
|---|--:|--:|--:|---|---|
| T0 | 41 | 41 | **41** | 781 関数 / 305 KB (計 97 秒) | f80 0, 未実装 helper 0 |
| T1 | 45 | 45 | **44** | 2,835 関数 / 1.26 MB (計 163 秒) | 失敗は ReWired (f80 2 関数)。 未実装 helper 5 本: `rep_stosb_memset` ×4 (Love Philter, Granulizer, Slicer, ReWired = memset へ写像可), `prefetcht0` / AVX `vaddps`,`vmovaps` (Harmless; CPUID 分岐で SSE 路固定) |

(Wasp と Wasp XT は同一 block を共有するため T0 の閉包は 41 件で 42 プラグインを覆う。) 初回実行では D1/ptr 型不整合で T0 5/42・T1 8/45 が `emcc -c` 不通過 → `fix_dup_decls.py` / `fix_ptr_params.py` で解消 (差分: T1 の 7 本が同一原因)。

## 5. 未解決・ブロッカー
1. **F80** (kernel 26/80, ReWired 等): x87 混入 IR の wasm 化 (f80 lowering pass)。
2. **float 引数/関数ポインタ/仮想呼出**: Eff_Render 本体の lift には `ir7_argpass`+VMT/関数ポインタ direct 化が必要 (T0 実証は pointer/int 引数の leaf kernel に限定)。
3. **GUI**: 133 本は VCL+Blend2D エディタを framework に内包。 headless (ShowEditor 非到達) 前提の計画。 GUI 表示は M7 路線 (別チケット)。
4. **Host Dispatcher ID の意味**: 上位 ID の出現頻度は実測 (ABI.md §6) だが、名称付けは公開 SDK の記憶と実測挙動の合致確認 (ID 0/2/4/5) に留まる。 `TFruityHost.Dispatcher` (0x13173a0) の全 case 解析は未。 host vtable 使用 offset の taint 追跡は近似 (0x100/0x108 に偽陽性の疑い)。
5. `TFruityPlugInfo` 抽出 124/133 (9 本は ctor 形状違い; ZGE は vtable 構造自体が別)。 Info.Flags の bit 名は未検証。
6. mac 側 ABI は FPC VMT 配置 (vNewInstance @+0x68 を実測) までで、vtable スロット対応表は未作成 (win 版を正本とし mac は交差検証用)。
7. 他社同梱エンジン (zplane Newtone/elastique 等) の **EULA/再配布は未判断** (事実整理のみ: Newtone engine 5.0 MB ws2_32 保有, elastique 文字列 31 DLL)。

## 6. ユーザ依頼事項
なし (素材は既存で足りた)。 任意: FL Studio 実行環境でのレンダ出力 (Render tests 82 FLP の wav) があれば、native 機械語自己参照より強い参照音源になる。

## 7. 成果物・再現
| ファイル | 内容 |
|---|---|
| `PLUGIN_MATRIX.md/.json` | 141 本の全実測 (サイズ/言語/固有コード/ABI/閉包/使用頻度/プリセット/RT/Tier) |
| `ABI.md` | FruityPlug ABI (逆アセンブル根拠付き) |
| `batch_plan.md` | フェーズ/欠陥表/検証戦略/下流チケット案 |
| `build_all.sh` | 全実測→マトリクスを 1 コマンドで再生成 (`--quick` で重い解析を再利用) |
| `inventory/*.py` | win_scan, nsis_names, mac_scan(+export trie), win_funcs/win_unique, mac_funcs, win_abi, host_calls, build_matrix_raw, family_table, delphi_vmt/pedis/macdis |
| `lift/` | `lift_ranges.sh`, `plugin_closure.py`, `batch_lift.sh`, `passes/` (m2/m5/m6/m7/m8/m11 参照コピー + 追加 5 pass; `SOURCES.txt`), `t0_balance/` (build_wasm.sh, native_ref.c, run_t0.mjs, t0_e2e.sh) |

```sh
bash tools/plugins/build_all.sh --quick            # マトリクス再生成 (~1 分)
bash tools/plugins/lift/t0_balance/t0_e2e.sh       # T0 実証 (2 秒)
bash tools/plugins/lift/batch_lift.sh --tier T0    # T0 バッチ lift (~1.5 分)
```

## 8. 次タスク提案 (下流チケット)
batch_plan.md §7 の通り。 優先順: **PLG-P0a framework headless lift → P0b Host shim → P0c kernel 表 (f80 pass) → F1 stereo-util / F2 eq-filter / F6 distortion / F5 modulation (T0 主体) → F4 reverb-delay / F3 dynamics (T1) → G1〜G3 → T3 個別**。
