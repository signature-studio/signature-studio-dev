# Massive X DSP closure 特定と lift 計画 (MX-3 / CAB-263)

- **REPORT 行数**: 220 行 (上限 200 行超過・検収の訂正追記に伴う。超過分は訂正・検収
  スクリプト案内のみ。元実測・未解決は圧縮済み)

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
2. **x64c 未対応語彙は VST3 面だけで 48,612 site / 246 種** (FLEngine 全体は 1,105 site)。
   内訳: **AVX (VEX/EVEX) 47,741 (98.2%)**、AES/SHA-NI 224、x87 演算 73 (実測 §3)。
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
| **unsupported site** | **48,612** (18.84% / 258,087) |
| unsupported 種別 | 246 |

| 群 | site | 内訳 (上位) |
|---|--:|---|
| **AVX (VEX/EVEX)** | **47,741** | vbroadcastss 3,871 / vmulps 6,614 / vaddps 4,342 / vblendvps 1,561 / vpslld 1,667 / vpxor 1,825 / vmovss 1,368 / vmovd 1,260 / vpsrld 1,177 / **zmm 系 (vmovdqa64/vpxord/vprold/kmovw/vextracti32x8/vpblendmw) ~200** |
| AES / SHA-NI | 224 | aesenc/dec 108 / vaesenc/dec 216 / sha256rnds2 64 / pclmulqdq 3 |
| x87 **演算** | 73 | fmul 8 / fisttp 8 / fadd 3 / fild 6 / fdiv 2 / fcmovnb 2 … |
| その他 | 574 | mulx 49 / adcx 44 / adox 32 / repz ret 37 / tzcnt 39 / in 31 / out 41 / enter 17 / cli 19 / scasb 7 / scasd 6 / mov fs·gs 6 … |

比較 (CAB-226 実績): FLEngine lift 集合 7,031 関数 / 340,774 命令 / 未対応 **1,105 site (0.32%)**
→ x64c 拡張で 0。**Massive X の VST3 面だけで 48,612 = FLEngine 全体の 44.0 倍**
(定義: 48,612 ÷ 1,105 = 44.0)。AES/SHA-NI は OpenSSL 静的リンク由来と推定 (MX-1 REPORT §5 実測)。

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

