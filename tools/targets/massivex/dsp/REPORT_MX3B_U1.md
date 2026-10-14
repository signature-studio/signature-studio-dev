# MX-3b U1 (process slot 同定) — 反証と RTTI 突合 (#266)

- 担当: #266 (MX-3b 残件 U1)。前 run の候補 (PR #1422 / REPORT §12) の検証。
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

**U1 (process slot 同定) は未達のまま。** 正しい入口は「`IAudioProcessor` を基底に持つ具体クラスの vtable」を
RTTI の COL 走査で探すこと (§4)。

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

## 4. 次の作業 (U1 の正しい入口)

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

- U1 本体 (IAudioProcessor を基底に持つクラスの主 vtable 同定と process slot の本体解析): **#266** (本 issue・残件)。
- U2/U5 (closure 厳密化): #1122 (CLOSED・成果は `REPORT_MX5.md`)。
- U3/U4 (vectorcall / C++ EH): #1123 (OPEN)。
- MX2-3 (N5/N6): #830 (OPEN)。
