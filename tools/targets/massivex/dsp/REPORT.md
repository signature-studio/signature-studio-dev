# Massive X DSP closure 特定と lift 計画 (MX-3 / CAB-263)

- **REPORT 行数**: 246 行 (上限 250 行・docs/DOC_MAP.md §1)

- 解析日: 2026-10-11 / 担当: `tools/targets/massivex/dsp/` (大物は `work/`, gitignore 済)
- 素材: `work/extracted/VST3/Massive X.vst3` (95,356,824 B, md5 622993e76565f49c094063a2b717d6ca)
- 既知類型 (DEFECTS.md): **D11 (chained .pdata) 該当** — .pdata 1 entry が複数論理関数を包含し
  直接 call の 99.58% (592,497 / 594,978 unique target) が非 begin に向く (§4・検収訂正後の値)。
  D15 (メモリ間接 call) は VST3 vtable 面で濃密と推定。
  D9 (icall §4 の disp_size) は x64c が disp_size 非依存のため影響なし。
- ff4999169333 (検収時・2026-10-11 09:37 JST)
- **検収 (2026-10-11・検収 agent)**: 誤記 2 件を訂正 — ①「83.0%」は再現不可 → 99.58% (§0-3/§4)
  ②「round 1 = 3,226」は e2e 再現値、mx_closure.py の実測は 3,227 (§2 注)。上記 2 件とも結論 (D11 非信頼・発散) は変わらない。

## 0. 結論 (先出し)

1. **DSP 到達集合は OTT (65 関数) / KH (khbase 112) と同規模ではない。** VST3 エントリ面
   (export 4 + MassiveX*/Steinberg::Vst 系 vtable slot 563) からの到達は
   **round 1 で 3,227 / round 2 で 45,611 / round 3 で 320,877** と発散し .text ほぼ全体に接続 (§2)。
   起票時の「process 起点 closure 100〜300 関数」は**成立しない** (推定)。
2. **x64c 未対応語彙は VST3 面だけで 38,485 site / 264 種** (FLEngine 全体は 1,105 site)。
   内訳: **AVX (VEX/EVEX) 37,630 (97.8%)**、AES/SHA-NI 224、x87 演算 73、その他 558 (実測 §3・測定 commit `458405518`)。
   FLEngine closure が SSE2 中心だったのに対し Massive X は **AVX2/AVX-512 + x87 演算**を伴う。
3. **.pdata は信頼できない (D11)**: 186,960 関数 / 58,062,780 B (.text の 96.4%) しか載っておらず、
   直接 call の **99.6% (592,497 / 594,978 unique target) が非 begin を指す**。
   独立再計算 (線形 E8/E9 走査・別実装) でも unique target 594,978・非 begin 率 **99.6%** で一致 (§4)。
   ※訂正 (検収・fix): 旧記載の「83.0% (521,307 / 627,863 edge)」は **どのスクリプトからも再現できない**。
   763,898 site / 594,978 target の全数再計算では非 begin は 99.6%。親 CAB-263 起票文の 83.0% も同値なので
   両方とも訂正が必要 (本 REPORT §4 に実測と定義を残す)。D11 の結論 (pdata 非信頼) は 99.6% でも同じ。
4. **D11 実例**: `GetPluginFactory` (0x18000a870) の callee `0x18011ca74` は pdata 関数 `0x11ca50`
   (501 B) の interior (offset 36)。0x11ca74 は FNV-1a ハッシュ再 insert として完結した実コード
   = **pdata の end が論理関数を跨いでいる**。
5. **推奨 lift 経路**: x64c 直積は不適 (AVX 語彙欠落 + 非 pdata 関数の到達不能)。**Ghidra 12.1.4 の
   完全 decompile → Lean 風 IR 自前変換**、または **AVX 語彙を x64c に追加して scope を
   「process 起点 2-3 ホップ」に絞る**二択。後者は U1 (process slot 未確定) が前提 (§5, §6)。

## 1. VST3 エントリ面の特定 (実測)

root 定義 (規則 36): export 4 本 + RTTI の class vtable slot のうち .pdata begin であるもの。
class 判定 = RTTI short 名が Steinberg::Vst 系 (IComponent/IAudioProcessor/IEditController/
Bus/Unit/Parameter 等) または `MassiveX`/`MX` 前缀。

| クラス (short) | vtable slot (.pdata begin) |
|---|--:|
| MX (namespace 全体) | 426 |
| MassiveXPlugIn | 53 |
| MassiveXAudioClass | 34 |
| MassiveXEditor | 29 |
| MassiveXApp | 16 |
| MassiveXModule | 5 |
| **計** | **563** |

- export: `InitDll` 0x18000a850 / `ExitDll` 0x18000a860 / `GetPluginFactory` 0x18000a870 /
  `factoriesListGetter` 0x181188680
- `MassiveXAudioClass` 主 vtable = 0x183976038 (47 slot)、partial = 0x1839761b8 (off=128, 11 slot)。
  `GetPluginFactory` は `mov edx, 0x4e692448` (PluginID) を実測確認。
- **`process` slot は内容シグネチャで確定できなかった** (0/47 slot が ProcessData の
  `[rdx+4]`/`[rdx+8]` dword 参照パターンを持たない)。→ §6 U1。

## 2. closure の実測 (再帰降下・入口集合ベース)

定義: 入口 = 直接 call/jmp rel32 先。関数 = 入口のうち .pdata begin か直近 begin との間の leaf 区間。

| round | 入口数 | 増分 |
|--:|--:|--:|
| seeds | 567 | — |
| 1 | 3,227 | +2,660 |
| 2 | 45,611 | +42,384 |
| 3 | 320,877 | +275,266 |

全 .pdata 関数 186,960 / .text 60,223,894 B。round 3 の 320,877 は pdata 関数数の **1.72 倍**。
発散のため厳密な上限は未確定 (§6 U2)。

注 (検収・再現確認): round 1/2/3 は検収 agent が `mx_closure.py` を clean HEAD から再実行し
**3,227 / 45,611 / 320,877 を全部一致確認** (所要 15〜20 分・負荷 2 ユーザ)。§2 の values は正しい。
ただし **e2e.sh には mx_closure が含まれない** (§9.3 個別コマンド・25 分) ので、
headline の round 2/3 は 1 コマンド e2e では再現できない (規則 37 の一部未達)。
→ e2e が再現するのは round 1 (mx_entry_surface の one_round_closure = 3,226) のみ。

## 3. x64c 未対応命令センサス (実測 / flelift x64c.py を読取実行)

`--img 0x180000000 --shift 0 --img-size 0x6616000`。対象 = §1 の 563 slot + export 4 = **567 関数**。

| 指標 | 値 |
|---|--:|
| lift 関数 | 567 |
| 命令数 | 258,087 |
| **unsupported site** | **38,485** (14.91% / 258,087) |
| unsupported 種別 | 264 |

| 群 | site | 内訳 (上位) |
|---|--:|---|
| **AVX (VEX/EVEX)** | **37,630** | vmulps 6,614 / vaddps 4,342 / vbroadcastss 3,871 / vpslld 1,667 / vblendvps 1,561 / vinsertps 1,400 / vsubps 1,223 / vpaddd 1,179 / vpsrld 1,177 / vaesenc·vaesdec 等 224 / **zmm 系 20** (vmovups 13 / vpaddq 5 / vmovaps 2) |
| AES / SHA-NI | 224 | sha256rnds2 64 / aesenc 52 / aesdec 52 / sha256msg1 24 / sha256msg2 24 / aesenclast·aesdeclast 8 |
| x87 **演算** | 73 | fmul 8 / fisttp 8 / fadd 3 / fild 6 / fdiv 2 / fcmovnb 2 … |
| その他 | 558 | mulx 49 / adcx 44 / out 41 / tzcnt 39 / repz ret 37 / adox 32 / in 31 / pshufb 24 / palignr 24 / int1 22 / cli 19 / retf 18 / enter 17 … |

比較 (CAB-226 実績): FLEngine lift 集合 7,031 関数 / 340,774 命令 / 未対応 **1,105 site (0.32%)**
→ x64c 拡張で 0。**Massive X の VST3 面だけで 38,485 = FLEngine 全体の 34.8 倍**
(定義: 38,485 ÷ 1,105 = 34.8)。AES/SHA-NI は OpenSSL 静的リンク由来と推定 (MX-1 REPORT §5 実測)。
旧値 48,612 は x64c の `ac58a8749`・`fe2dc9ed9` より前の値 (現 HEAD で再測定。詳細は massivex REPORT §11.4)。

- 群分けは `e2e.sh` の判定順のまま: `v` 接頭辞判定が先のため vaes 系 224 は AVX に入り、pshufb / palignr / pclmulqdq は「その他」に入る。合計 38,485 は不変 (表示のみ・起票先: #3487 [MX-36])。
- **vectorcall**: 567 関数の到達 import は COM (`CoCreateFreeThreadedMarshaler` 等) 3 件のみ。
  独自 vectorcall 修飾子は未検出 — ただし x64c は import 修飾子を無視するため**範囲外** (§6 U3)。
- **MSVC C++ EH**: .pdata の chained 関数が多数 (D11) ゆえ unwind チェインが濃密と推定。未解析 (§6 U4)。

## 4. 独立再計算 (別アルゴリズム: 線形 E8/E9 バイトスキャン) — 検収で訂正

`mx_recount.py` = 再帰降下ではなく .text 全 60,223,894 B を線形走査して E8/E9 rel32 を数える。

| 指標 | 実装側 (recursive) | 再計算 (linear scan) | 一致 |
|---|--:|--:|:--:|
| .pdata 関数 | 186,960 | 186,960 | ✓ |
| .pdata バイト | 58,062,780 | 58,062,780 | ✓ |
| call site 数 | 627,863 edge | 763,898 site | — |
| call target 数 (unique) | 457,506 | 594,978 | — |
| **非 pdata begin の割合** | **99.58%** | **99.58%** | ✓ |

- **訂正 (検収・fix)**: 旧記載の「83.0% (521,307 / 627,863 edge)」は再現できない。
  検収 agent の numpy 別実装 (`dsp/scripts/acpt_recount_np.py`) でも unique target 594,978 /
  非 begin 592,497 = **99.58%** (検証: python ループ・numpy の 2 実装で一致)。
  「457,506」は mx_recount.py が出力する値 (`targets` 集合) であり、mx_recount.py 自身の再実行でも
  594,978 と一致する (457,506 は mx_closure.py の実測値と混同されたと推定)。
- 差分 (763,898 vs 627,863) = recursive 側は辿けた入口だけを数えるため下界、linear 側はデータ領域の
  擬似 E8/E9 を含むため上界。**非 begin 率 99.58% は両定義で一致** = D11 の頑健な実測。
  (結論「.pdata は信頼できない」は 83.0% でも 99.58% でも変わらない)

## 5. lift 計画・見積もり (推定ラベル付き)

### 5.1 案 A: Ghidra 完全 decompile → Lean 風 IR 自前変換 (推奨・推定)
- `[GHIDRA]` 12.1.4 で 95 MB / 187K 関数を decompile。~15 GB 級 (RetDec 全 decode と同等規模)。
- 利点: D11 と vtable 間接 call (D15) を Ghidra の参照解析が解決。未対応 AVX 語彙も不要。
- リスク (推定): decompile C は数十 GB 級、wasm 再コンパイルに Emscripten + MS ABI shim が別途必要。
- **見積 (推定): 15〜30 人日** (根拠: RetDec 全 decode ~15 GB と同規模、OTT/KH は 60〜190 関数で
  1-3 人日規模の比からの外挿 + import 面の広さを上方修正)。

### 5.2 案 B: x64c 語彙拡張 + scope 絞り込み (部分的・推定)
- AVX2 (VEX ymm) + AVX-512 (EVEX zmm) + x87 演算 + AES/SHA を x64c に実装。
  flelift REPORT §2 と同じやり方で可能だが **site 数が 44 倍**。
- scope 絞り (process 起点 2-3 ホップ) には U1 (process slot 確定) が前提。
- **見積 (推定): 語彙拡張 10〜20 人日 + closure 確定 3〜5 人日 + lift 5〜15 人日**。

### 5.3 MX-2 との境界
| 層 | 現状 | MX-3 での扱い |
|---|---|---|
| license (evaluateRAS2 / productCheckSerial / productGetSubscription + demo UI) | MX-2 で完全 stub 化済 (検収再現: 11/11 PASS・commit e181c63) | **触らない** |
| DSP (process 本体) | 未解析 | 本 REPORT の対象 |
| nfo spec | 登録済 (path 単一ファイルモジュール形 / mx_check 19 checks) | 変更なし |

## 6. 未解決・限界 (起票先付き)

| # | 未解決 | 影響 | 起票先 |
|---|---|---|---|
| U1 | `process` slot の内容シグネチャが 0/47 slot で不発 (ProcessData `[rdx+4]`/`[rdx+8]` 参照パターン無し)。off=128 の partial (11 slot) も未確認 | process 起点 closure の厳密な root が決まらない / 案 B の前提 | (a) CAB-244 (MX-1) にコメント — IAudioProcessor vtable の slot index 表を突合 |
| U2 | 再帰降下が round 3 で 320,877 に発散。code/data の区別が無いため target の一部が偽 | closure 上限が未確定 / lift scope が決まらない | (b) 新規子チケット CAB-265 [MX-3b] |
| U3 | vectorcall 独自規約の有無が未確定 (x64c は import 修飾子を無視) | 呼出規約モデル欠落で silent miscompile の恐れ | (c) CAB-265 |
| U4 | MSVC C++ EH (chained .pdata の unwind チェイン) の構造が未解析 | CAB-227 と同型の欠陥が潜伏しうる | (a) CAB-227 |
| U5 | leaf 関数サイズを「次の pdata begin まで」で近似 | closure バイト数は参考値 | (c) CAB-265 |
| U6 | Mac dmg (BitRock JL) 未展開で win/mac closure 比較が不能 | mac 優先度判断材料が無い | (a) CAB-244 [MX-4] |

## 7. ユーザ依頼事項・環境前提

**無し** — `~/ダウンロード` の VST3 と振出済 `work/extracted/` で不足なし (preflight 規則 43 準拠)。
`MX_PE` / `MX_X64C` で PE・x64c パスを差し替え可。依存: python3 + capstone 5.0.7 + pefile 2024.8.26
(`[GHIDRA]` 12.1.4 は未使用・案 A 向け)。TMPDIR は実ディスク (`work/tmp`)。生成物は `dsp/work/`
(gitignore 済・48 MB)。x64c は `tools/flelift/x64c.py` (CAB-252 継続稼働中につき読取実行のみ・未変更)。

## 8. 再現

```sh
bash dsp/e2e.sh            # RTTI + 入口面 + x64c probe + 独立再計算
bash dsp/negctl.sh         # ネガティブコントロール (規則 41)
```

### 9.1 e2e 実測 (規則 38: 実測秒 + load average)

| 実行 | 経過秒 | load average (start → end) |
|---|--:|---|
| e2e.sh 全工程 (検収・clean HEAD) | **36 s** (実装側 3 回 35〜69 s) | 16.11 16.37 15.16 → 16.64 16.48 15.24 |
| negctl.sh 3 本 (検収) | **11 s** | 15.12 15.90 15.19 → 9.4 12.7 13.1 |

内訳 (実装側): RTTI 2.2 s / entry_surface 0.2 s / x64c probe 24 s / 独立再計算 6.2 s。
検証起点 commit = **e6c6e91** (検証時 HEAD は a76310f)。個別コマンドは §11 に記載。

## 10. 検証範囲 / 範囲外 (規則 40)

**クリーン HEAD 検証 (規則 45)**: `git archive HEAD -- tools/targets/massivex/dsp | tar -x -C <tmp>`
から e2e.sh 再実行 → **全数値不一致なく再現** (567 関数 / 258,087 命令 / 48,612 site / 246 種 /
.pdata 186,960 / 非 begin 率 99.58%)。検収 agent 実測 36 s, load 16.11 16.37 15.16 → 16.64 16.48 15.24。
現 HEAD `458405518` の再検証 (#3454・clean checkout): 567 関数 / 258,087 命令 / **38,485 site / 264 種** / e8e9_targets 594,978 (不変)・23 s。詳細は massivex REPORT §11.4。
検証起点 commit = **e6c6e91** (検証時 HEAD は a76310f、dsp/ は e6c6e91 以降 report corrections のみ)。
注: 展開先に gitignore 済み work/ が無いため `mkdir -p dsp/work/lift_seeds dsp/work/logs` が必要
(mx_rtti.py は出力先 dir が無いと FileNotFoundError)。PE は `MX_PE=` で実体を指す。

**検証した**: (1) RTTI/MSVC vtable の機械抽出と VST3 入口面の特定。(2) 567 関数の x64c lift と
未対応命令センサス。(3) .pdata 完全性 (独立再計算で交差確認)。(4) NC 3 件。(5) 線形スキャン再計測。
**検証していない**: (1) **native 実機 / 実 DSP 実行との比較** (静的解析のみ)。(2) process slot の
内容同定 (0/47 slot 不発、U1)。(3) closure の厳密な上限 (round 3 発散、U2)。(4) code/data 区別に
基づく偽 target の除去。(5) 間接 call / vtable 経由の到達 (D15 は推定のみ)。(6) Mac 版 (未展開)。
(7) vectorcall 独自規約・MSVC C++ EH の構造 (U3/U4)。

## 11. 成果物 / 検収スクリプト

```
tools/targets/massivex/dsp/
├── REPORT.md / e2e.sh (1 コマンド) / negctl.sh (NC 3 件 FAIL)
└── scripts/  mx_rtti.py, mx_entry_surface.py, mx_recount.py, mx_cg.py, mx_closure.py, mx_roots.py
              + acpt_recount_np.py / acpt_verify_mx3.py   (検収 agent の別実装)
    MX-2 側: license/scripts/acpt_verify_mx2.py            (12 点 IR 検証)
    work/   (gitignore 済・48 MB)

python3 dsp/scripts/acpt_recount_np.py   <pe> <out.json>   # numpy 別実装 → 非 begin 率 99.58%
python3 dsp/scripts/acpt_verify_mx3.py   <pe> <rtti.json> <lift_meta.json>
python3 license/scripts/acpt_verify_mx2.py <license_work_dir> <pe>
```
検収実測: acpt_recount_np 15 s / acpt_verify_mx3 0.9 s (load 1.7→2.1, nproc=16)。
acpt_recount_np = pdata 186,960 / sites 763,898 / targets 594,978 / non-begin 592,497 = **99.58%**
(python ループの mx_recount.py と完全一致 = 2 実装の交差確認)。
実施記録: `work/lift_one/` (round-1 closure の x64c lift) は 20 分で完了せず中断。完了分
(seeds 567 関数) を §3 の実測値として採用。Linear: CAB-263 起票→In Review / 子チケット CAB-265。

## 12. U1 進捗 (MX-3b / #266 · pdata 非依存の slot 計測)

**結論 (未確定)**: partial vtable 0x1839761b8 の **slot 9 (0x1800119c0)** が `process` の候補。主 vtable 0x183976038 には process が無い (全 slot が共有スタブか小関数)。IAudioProcessor の 0-based 順 (IUnknown 3 + setBusArrangements / getBusArrangement / canProcessSampleSize / getLatencySamples / setupProcessing / setProcessing / process) では process は slot 9 になる。ただし ProcessData 参照の確証は未取得。

| 項目 | 結果 |
|---|---|
| 計測スクリプト | `dsp/scripts/mx_slot_probe.py` (slot → 先頭 VA・先頭命令列)・`dsp/scripts/mx_slot_body.py` (関数本体の `[rdx+disp]` 集計と call 列・pdata 非依存) |
| 主 vtable slot 0-11 | 0x180017f10 / 0x18000eb30 / 0x18017a630 / 0x18000efe0 / 0x180005680 (×4: slot 4,5,8,9,10 は同一) / 0x18000fad0 / 0x18000fb00 / 0x18000fa90 等。共有スタブ |
| partial slot 0-10 | slot 9 = 0x1800119c0 (prologue: push rbp/rsi/rdi, sub 0x80) / slot 10 = 0x180011980 (`mov rcx,[rcx+0x28]; call` の薄いラッパ) |
| slot 9 本体 (max 400 insn 内) | 83 insn・`[rdx+disp]` 参照 0 件 (rdx を退避してから使う可能性あり・未確定)・call 14 件 (先頭 `call 0x1800edeca`、`call [rax+0x18]`、`call [rax+0xa0]` など) |
| 素材 | plugins-massivex (前回 run の実測: 展開 2.3 s・parse 0.3 s・extract 11.2 s・md5-ok 0/125)。**本 run の素材は fl-win64 のみで再現せず (未検証)**。PE 上の slot/本体数値は再測定待ち |

**反証データ (弱める材料)**: slot 9 本体に `[rdx+disp]` が 0 件。process なら ProcessData (rdx) のフィールドを読むのが普通なので、候補を弱める。rdx を退避してから使う可能性は残るが未確認。
**前提**: 「IAudioProcessor の 0-based 順で slot 9」は、partial vtable 0x1839761b8 がその interface の vtable であることが前提 (未確認。RTTI 上の所属は未突合)。
**停止規則 (mx_slot_body.py)**: 最大 400 命令。ただし `ret` を 30 命令超の後に最初に見た地点で止める (ret/int3 の境界は見ない)。
**ネガティブコントロール**: `mx_slot_body.py --selftest` (PE 不要・既知エンコード)。正例 `mov rax,[rdx+0x18]; mov ecx,[rdx+4]; ret` → rdx 参照 2 件 (offset 4・0x18) を検出、負例 `mov rax,[rcx+0x18]; ret` → 0 件。PE 上の既知 rdx 参照関数での確認は素材 plugins-massivex 未展開のため未実施。

**未解決 (起票先)**: slot 9 が process であることの確証 (rdx の退避先追跡・Ghidra 参照解析) → #266 (MX-3b, OPEN) のコメント https://github.com/signature-studio/signature-studio-dev/issues/266#issuecomment-6156301544 に記載済み。closure 厳密化は #1122 (MX-5, CLOSED・成果は REPORT_MX5.md) のため、残件は #266 へのコメントで示す。vectorcall / C++ EH → #1123 (MX-6, OPEN)。

**検証 commit と差分 (docs/WORKFLOW.md §6)**: PE 実測の測定 commit = **133007f1**。その後 dsp のコードを変えた最後の commit = **59d2f022** (`mx_slot_body.py` を関数化し `--selftest` と停止規則を追加。解析ロジック・集計条件は不変)。
- `git diff 133007f1 0cf4cb10 -- tools/targets/massivex/dsp` は **148 行** (0cf4cb10 時点の実測。差分 0 ではない。59d2f022 でコードを変えたため。0 行を主張していた旧記載は誤り)。以降の commit で変わるのは REPORT.md のみ。
- `git diff 59d2f022 HEAD -- tools/targets/massivex/dsp/scripts` は **0 行** (59d2f022 以降にスクリプトの変更なし。以降の差分は本 REPORT.md のみ)。
- selftest (59d2f022・PE 不要・実測): `selftest PASS: positive rdx refs=2 (offsets [(4, 1), (24, 1)]), negative rdx refs=0`。
- PE 依存の数値 (slot アドレス・slot 9 本体の 83 insn / call 14 件) は素材未展開のため本 run では再測定していない (前回 run の値・未検証)。
