# MX-3b U1 (process slot 同定) — 反証と RTTI 突合 (#266)

- 担当: #266 (MX-3b 残件 U1)。前 run の候補 (`tools/targets/massivex/dsp/REPORT.md` §12「U1 進捗」・PR #1422 由来) の検証。
- 測定素材: `plugins-massivex` の `Native Instruments Massive X v1.7.1.exe` を `work/` に展開し、
  `parse_setup_headers.py` → `extract_massivex.py` で `work/extracted/VST3/Massive X.vst3` (95,356,824 B) を生成。
  md5-ok 0/125 (既知・#798 REPORT §11.1)。`work/` は gitignore。
- 測定 commit: `43661d6d` (`mx_vtable_rtti.py` を最後に変更した commit。本 run の測定はこの版のスクリプトで実施)。

## 1. 結論

**PR #1422 の候補「partial vtable 0x1839761b8 の slot 9 = process」は棄却する。**

- 0x1839761b8 は `MassiveXAudioClass` の副 vtable (COL.offset = 0x80)。COL の完全オブジェクト階層 (§2) に IAudioProcessor は無い。
  階層は MSVC の BaseClassArray が間接基底まで含むため、IAudioProcessor が副基底としても存在しない。
  よって 0x1839761b8 は IAudioProcessor のサブオブジェクト vtable ではない。
- したがって partial slot 9 を IAudioProcessor の process とみなす根拠は無い。
- slot 9 本体 (0x1800119c0) は ProcessData (rdx) を読まず (`xor edx, edx` で上書き)、process の形ではない。

**U1 (process slot 同定) は部分確定。** `MassiveXPlugIn` の IAudioProcessor サブオブジェクト vtable `0x183973108` の
slot 9 = `0x180082400` が process と特定した (根拠は §9)。Ghidra による独立確認は未了。

## 2. 測定 (測定 commit 43661d6d)

| 項目 | 結果 | 実行 |
|---|---|---|
| RTTI 0x1839761b8 (副, COL=0x1839763d0, COL.offset=0x80) | type `.?AVMassiveXAudioClass@@`・cd=0x183976258・numBaseClasses=5: base[0] MassiveXAudioClass (numContained=4, mdisp=0) / base[1] `.?AVIInstrument@AB@NI@@` (mdisp=0) / base[2] `.?AVMXInstance@MX@Lechtal@@` (numContained=1, mdisp=128) / base[3] `.?AVIMXInstance@MX@Lechtal@@` (mdisp=128) / base[4] `.?AVEventTarget@UIA@NI@@` (mdisp=4483264=0x4468c0) | `dsp/scripts/mx_vtable_rtti.py` |
| RTTI 0x183976038 (主, COL=0x183976240, COL.offset=0) | type・基底 5 件は副と同一 (COL は別)。cd=0x183976258 は副と共有 | `dsp/scripts/mx_vtable_rtti.py` |
| cd 共有の確認 | 両 COL が指す ClassHierarchyDescriptor は同一 (cd=0x183976258)、numBaseClasses = `cd+8` = 5。`cd` の出力は 43661d6d で追加 | `dsp/scripts/mx_vtable_rtti.py` (本 run) |
| xref 0x1839761b8 (副) | 2 件: `0x18000e58e` (`lea rax,[rip+0x3967c23]`) / `0x18000e924` (`lea rax,[rip+0x396788d]`) | `dsp/scripts/mx_vtable_xref.py` (本 run) |
| xref 0x183976038 (主) | 2 件: `0x18000e580` (`lea rax,[rip+0x3967ab1]`) / `0x18000e91a` (`lea rax,[rip+0x3967717]`) | `dsp/scripts/mx_vtable_xref.py` (本 run) |
| 0x18000e560〜0x18000e595・0x18000e900〜0x18000e92b の逆アセンブル | 未検証。リポジトリ内スクリプトでは再現していない (前 run の一時 `capstone` 出力のみ)。どの関数の ctor か・`this+0x4468c0` の構築の有無は未了のため、本 REPORT では結論に使わない | — |
| 主 vtable 0x183976038 の slot 0〜11 | 0x180017f10 / 0x18000eb30 / 0x18017a630 / 0x18000efe0 / 0x180005680 / 0x180005680 / 0x18000fad0 / 0x18000fb00 / 0x180005680 / 0x180005680 / 0x180005680 / 0x18000fa90 | `dsp/scripts/mx_slot_probe.py` (本 run) |
| 副 vtable 0x1839761b8 の slot 0〜11 | 0x180017f60 / 0x18002a6c0 / 0x1800dd0e0 / 0x1800de4a0 / 0x180011450 / 0x1800114e0 / 0x180011830 / 0x1800118f0 / 0x1800119a0 / 0x1800119c0 / 0x180011980 / 0x1839763f0 (slot 11 は .rdata) | `dsp/scripts/mx_slot_probe.py` (本 run) |
| 各 slot 本体の `[rdx+disp]` 集計 (max 400 insn) | 前 run の値 (副 vtable 0x1839761b8 の slot 0,1,2,3,4,6,8,9,10 で 0 件、slot 5・7 で `[rdx+0x70]` 1 件) のみ。本 run 未再測定 | `dsp/scripts/mx_slot_body.py` (前 run) |

## 3. 前 run の誤りの原因

- PR #1422 は「partial = IAudioProcessor の vtable」と仮定して 0-based 順で slot 9 を選んだ。仮定の検証 (RTTI 突合) を
  行わなかった。REPORT §12 の「前提 (未確認)」にも同じ注記があった。
- 前 run の RTTI は `numBaseClasses` を `cd+4` (attributes) から、BaseClassDescriptor のフィールドを 1 つずつずらして読んでいた
  (#1565 レビューで指摘)。修正は `mx_vtable_rtti.py` に反映済み (6264ca83)。
- 前 run の xref 記述「0x18000e580 (`mov [rcx],rax`)」は誤り。実際は `lea rax,[rip+...]` の位置で、
  直後の `mov [rcx],rax` が書き込み。前 run の「2 件ずつ」は本 run の件数と一致した。

## 4. 次の作業 (U1 の入口と実施状況)

1〜3 の相当作業は §9 で実施済み (手段は §9.1)。残るのは Ghidra 等による独立確認 (§9.2)。

1. RTTI 全走査: 型名 `.?AVIAudioProcessor@Vst@Steinberg@@` の TypeDescriptor を指す COL を探し、その COL の
   `pClassDescriptor` の base 配列から、IAudioProcessor を基底に持つ具体クラスを列挙する (`mx_vtable_rtti.py` の拡張)。
2. 見つかったクラスの主 vtable の、IAudioProcessor 由来の slot (IUnknown 3 + IPluginBase 2 + IAudioProcessor 順) を読む。
3. その slot 先の本体で ProcessData (rdx) の `[rdx+disp]` を集計する (`mx_slot_body.py`)。

**注意**: `mx_roots.py` は全 class 実行で 15 分超のため (#266 の前 run 報告)、RTTI 全走査は対象を限定して行う。

## 5. 前 run の検証記録

- `mx_vtable_xref.py` (前 run・43 s) の 2 件ずつは、本 run (6264ca83・69 s) で件数・アドレスとも再現した (§2)。
  ただし前 run の表の「`mov [rcx],rax` 直接参照」の記述は誤りだったため撤回した。
- 線形逆アセンブル (`capstone` を `.text` 先頭から) は 0x180004c27 で停止 (データ・未対応命令)。
  このため xref は disp32 の全位置照合方式にした。線形を使う方式は採らない。

## 6. 本 run の測定と差分証跡

- 測定 commit: `43661d6d` (`mx_vtable_rtti.py` の最後のコード変更。`cd` アドレスの出力を追加)。
  §2 の RTTI・xref・slot 値はこの commit のスクリプトで実測した。`mx_vtable_xref.py` / `mx_slot_probe.py` は 6264ca83 から変更なし。
- 差分証跡: `git diff 43661d6d HEAD -- tools/targets/massivex/dsp/scripts` は 0 行 (本 REPORT の commit 以降、スクリプトは変えていない)。
  `dsp` 全体の差分は本 REPORT の更新のみ (測定結果には影響しない)。
- 環境: `plugins-massivex` を `$ARTIFACTS_DIR` から展開 (3.4 GB の tar.zst) し、`Native Instruments Massive X v1.7.1.exe` (installer) を
  `parse_setup_headers.py` → `extract_massivex.py <exe> work key` で `$RUNNER_TEMP/mx/work/extracted/VST3/Massive X.vst3` (95,356,824 B、md5 `622993e7…`) に生成。
  リポジトリ外に置いたため `work/` は使っていない。抽出は `md5-ok 0/125` (既知・#798 REPORT §11.1)。測定時の load は 0.8 (測定開始時)。

## 7. 再測定の手順 (次 run)

1. `oc_artifacts: plugins-massivex` で起動し、`work/extracted/VST3/Massive X.vst3` を再生成する。
2. `python3 dsp/scripts/mx_vtable_rtti.py <pe> 0x1839761b8 0x183976038` で基底一覧を出す。
3. `python3 dsp/scripts/mx_vtable_xref.py <pe> 0x1839761b8 0x183976038` で RIP 相対参照の全件を出す。
4. 測定 commit と `git diff <測定 commit> HEAD -- tools/targets/massivex/dsp` を本節に添える。

## 8. 未解決 (起票先)

- U1 (IAudioProcessor の process slot): 部分確定 (§9)。Ghidra による独立確認は未了で、**#266** (本 issue・残件)。
- U2/U5 (closure 厳密化): #1122 (CLOSED・成果は `REPORT_MX5.md`)。
- U3/U4 (vectorcall / C++ EH): #1123 (OPEN)。
- MX2-3 (N5/N6): #830 (OPEN)。

## 9. U1 結論 (IAudioProcessor の process slot 同定・#266)

**結論 (部分確定・Ghidra 独立確認は未了): `MassiveXPlugIn` の IAudioProcessor サブオブジェクト vtable `0x183973108` の slot 9 = `0x180082400` が process。**
§1 の「0x1839761b8 slot 9」候補は誤り (同 vtable は `MassiveXAudioClass` の副 vtable で、IAudioProcessor を含まない)。
「§12」は同ディレクトリの `REPORT.md` §12 (「U1 進捗」・PR #1422 由来) を指す (本ファイルには §12 は無い)。

### 9.1 方法 (Ghidra は未導入のため pefile + capstone で代替)

1. 全 COL 走査 (`dsp/scripts/mx_iap_vtable.py`): x64 COL (sig=1 かつ pSelf 一致) を列挙し、基底一覧に
   `.?AVIAudioProcessor@Vst@Steinberg@@` を持つ COL を出す。→ 8,961 候補のうち、Massive X 固有の具象クラスは
   `.?AVMassiveXPlugIn@@` (16 vtable)。SDK 基底のみの `InterfaceVST3*` / `SingleComponentEffect` は除外。
2. `MassiveXPlugIn` の基底表 (`dsp/scripts/mx_iap_cols.py`): 基底 25 が `IAudioProcessor` で mdisp=192。
   よって IAudioProcessor サブオブジェクトは COL.offset=0xC0 の vtable。
3. その vtable を指す COL (`dsp/scripts/mx_iap_slots.py`): `0x183973108` (offset=0xc0) の slot 0〜11 は
   `0x18000afe0 / 0x18000aff0 / 0x18000b000 / 0x180083ed0 / 0x180084d20 / 0x180082330 / 0x180082c70 /
   0x180082340 / 0x180082ca0 / 0x180082400 / 0x180082c80 / 0x183974330`。
4. slot の対応: FUnknown 3 + IAudioProcessor (VST3 SDK の宣言順) = setBusArrangements 3 / getBusArrangement 4 /
   canProcessSampleSize 5 / getLatencySamples 6 / setupProcessing 7 / setProcessing 8 / **process 9** / getTailSamples 10。
5. 本体の検証 (`dsp/scripts/mx_slot_body.py`、pdata 非依存):
   - slot 9 `0x180082400`: `rdx+8` 2 件 (ProcessData の numSamples に一致)。上限 400 insn で `insns=401`、3000 insn でも `rdx+8` 2 件・
     `insns=422`。
   - slot 7 `0x180082340`: `rdx+4` 1 件・`rdx+16` 1 件 (ProcessSetup の symbolicSampleSize / sampleRate に一致)。
   - 整合: setupProcessing(7) が ProcessSetup を、process(9) が ProcessData を読むという SDK の型と合う。

### 9.2 限界

- Ghidra 参照解析ではないため、「SDK 宣言順 = vtable 順」は MSVC の配置前提に依る。slot 7/9 の `rdx` 参照形は
  この前提と整合するが、独立の証拠 (例: 同 vtable への直接 call 元) は未取得。
- slot 9 の closure (process 起点の到達集合) と U2/U5 (closure 厳密化) は本 REPORT の範囲外 (#1122 / 未起票の残件)。
- `rdx+8` の 2 件は numSamples 読み出しの候補。他の `rdx` 派生の読みは未分離。

### 9.3 再現

- 測定 commit: **5ed14324** (`dsp/scripts/mx_iap_*.py` を追加した commit。以後コード変更なし)。
- 手順: `work/extracted/VST3/Massive X.vst3` を §6 の手順で生成 → 上記 1〜5 のコマンド。
- 差分証跡: `git diff 5ed14324 HEAD -- tools/targets/massivex/dsp/scripts` は 0 行。

### 9.4 非 Ghidra 確認 (既存スクリプト + 線形逆アセンブル・#266 の残件 1)

Ghidra は未導入のため、§9.2 の参照元確認を既存スクリプト `mx_vtable_xref.py` と線形逆アセンブルで行った。Ghidra 参照解析ではないので「独立確認」とは呼ばない。

- 測定 commit: **5ed14324** (`git diff 5ed14324 HEAD -- tools/targets/massivex/dsp/scripts` = 0 行を再確認済み)。
- 再測定 (本 run・素材 `plugins-massivex` を展開。`Massive X.vst3` = 95,356,824 B / md5 `622993e76565f49c094063a2b717d6ca`、md5-ok 0/125 は既知):
  - `mx_vtable_xref.py <pe> 0x183973108` の生出力 (本 run: 41.6 s・load 0.80→0.96):
    ```
    0x180009e8a lea rax, [rip + 0x3969277] -> 0x183973108
    # target 0x183973108: 1 refs
    ```
  - 逆アセンブル `0x180009e2b`〜`0x180009ed0` の生出力 (線形復号・`.pdata` 不使用):
    ```
    0x180009e2b mov qword ptr [rbp], 0xfffffffffffffffe
    0x180009e33 mov rsi, rcx
    0x180009e36 call 0x180015dbb
    0x180009e3b lea rax, [rip + 0x3968f36]
    0x180009e42 mov qword ptr [rsi], rax
    0x180009e45 lea rax, [rip + 0x396906c]
    0x180009e4c mov qword ptr [rsi + 0x10], rax
    0x180009e50 lea rax, [rip + 0x3969091]
    0x180009e57 mov qword ptr [rsi + 0x18], rax
    0x180009e5b lea rax, [rip + 0x39690c6]
    0x180009e62 mov qword ptr [rsi + 0x30], rax
    0x180009e66 lea rax, [rip + 0x396915b]
    0x180009e6d mov qword ptr [rsi + 0x38], rax
    0x180009e71 lea rax, [rip + 0x3969190]
    0x180009e78 mov qword ptr [rsi + 0x68], rax
    0x180009e7c lea rax, [rip + 0x3969205]
    0x180009e83 mov qword ptr [rsi + 0xb8], rax
    0x180009e8a lea rax, [rip + 0x3969277]
    0x180009e91 mov qword ptr [rsi + 0xc0], rax
    0x180009e98 lea rax, [rip + 0x39692c9]
    0x180009e9f mov qword ptr [rsi + 0xc8], rax
    0x180009ea6 lea rax, [rip + 0x39692eb]
    0x180009ead mov qword ptr [rsi + 0x1b0], rax
    0x180009eb4 lea rax, [rip + 0x39693ed]
    0x180009ebb mov qword ptr [rsi + 0xd30], rax
    0x180009ec2 lea rax, [rip + 0x396940f]
    0x180009ec9 mov qword ptr [rsi + 0xd38], rax
    0x180009ed0 lea rax, [rip + 0x3969431]
    ```
  - 測定 commit: **5ed14324** (上記 `dsp/scripts` 差分 = 0 行)。
- 直接参照: `0x183973108` を指す RIP 相対参照は **1 件** (`0x180009e8a`、`lea rax,[rip+0x3969277]`)。
- 参照元の文脈: `0x180009e2b`〜`0x180009ed0` の範囲で `[rsi]`・`[rsi+0x10]`・…・`[rsi+0xb8]` へ複数の vtable を書き込み、`0x180009e8a` の直後が `mov [rsi+0xc0], rax`。開始 `0x180009e2b` は命令境界が `0x180009e8a` まで揃った候補の一つで、関数境界としては未検証。
  `rsi` が this を保持しているとみなすのは推論。根拠は `0x180009e33 mov rsi, rcx` (第 1 引数 `rcx` を `rsi` に退避) が `0x180009e36 call 0x180015dbb` の**前**にあり、`rsi` は callee-saved のため call を跨いで保持されるはず、という点。`call` 後の `mov rsi, rcx` ではない。関数境界を検証していないため、「コンストラクタ」とは断定しない。この推論が正しければ、§9.1 の COL.offset=0xC0 と整合する。
- 確認できたのは「`0x183973108` を書き込む参照がこの 1 件である」ことと、その書き込み先が `this+0xc0` と推論されること、までである。**vtable が IAudioProcessor サブオブジェクトであることの確定は、§9.1 の COL 情報に依る**。
- **未確認**: slot 9 = process の対応 (SDK 宣言順 = vtable 順)。slot 9 の closure と U2/U5 は #1122 (CLOSED) と本 REPORT の範囲外。
- 逆アセンブルは `.pdata` を使わず線形に復号した (関数 begin とは限らない点に注意)。
- 再測定の手順: `oc_artifacts: plugins-massivex` で素材を取得 → `parse_setup_headers.py` → `extract_massivex.py <exe> work key` で `work/extracted/VST3/Massive X.vst3` を作り、`mx_vtable_xref.py <pe> 0x183973108` と `0x180009e2b`〜`0x180009ed0` の線形逆アセンブルを実行 (上記の生出力)。

§9 の結論 (部分確定) は変えない。残る未確定は「SDK 宣言順 = vtable 順」の確認のみ。
