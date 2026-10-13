# MX-3b U1 (process slot 同定) — 反証と RTTI 突合 (#266)

- 担当: #266 (MX-3b 残件 U1)。前 run の候補 (PR #1422 / REPORT §12) の検証。
- 測定素材: `plugins-massivex` の `Native Instruments Massive X v1.7.1.exe` を `work/` に展開し、
  `parse_setup_headers.py` → `extract_massivex.py` で `work/extracted/VST3/Massive X.vst3` (95,356,824 B) を生成。
  md5-ok 0/125 (既知・#798 REPORT §11.1)。`work/` は gitignore。
- 測定 commit: 本節を追加する commit。ワーキングツリーは origin/main (35e6031e) 起点。

## 1. 結論

**PR #1422 の候補「partial vtable 0x1839761b8 の slot 9 = process」は、前提が崩れたため棄却する。**

- partial vtable 0x1839761b8 は **`MassiveXAudioClass` の副 vtable (this offset 0x80)** で、IAudioProcessor の vtable ではない
  (RTTI COL の型名は両方とも `.?AVMassiveXAudioClass@@`・基底は自分のみ)。
- したがって partial slot 9 を IAudioProcessor の process とみなす根拠は無い。
- slot 9 本体 (0x1800119c0) は ProcessData (rdx) を読まず (`xor edx, edx` で上書き)、process の形ではない。

**U1 (process slot 同定) は未達のまま。** 正しい入口は「`IAudioProcessor` を基底に持つ具体クラスの vtable」を
RTTI の COL 走査で探すこと (§4)。

## 2. 測定

| 項目 | 結果 | 実行 |
|---|---|---|
| 主 vtable 0x183976038 の slot 0〜11 | 0x180017f60 / 0x18002a6c0 / 0x1800dd0e0 / 0x1800de4a0 / 0x180011450 / 0x1800114e0 / 0x180011830 / 0x1800118f0 / 0x1800119a0 / 0x1800119c0 / 0x180011980 ほか | `dsp/scripts/mx_slot_probe.py` |
| 各 slot 本体の `[rdx+disp]` 集計 (max 400 insn) | 0 件 (slot 0,1,2,3,4,6,8,9,10)。slot 5・7 で `[rdx+0x70]` が 1 件 (`lea` 直後の関数 post 処理) | `dsp/scripts/mx_slot_body.py` |
| 0x1839761b8 (partial) を RIP 相対で参照する命令 | 0x18000e58e (`lea rax,[rip+...]; mov [rcx+0x80],rax`) / 0x18000e924 | `dsp/scripts/mx_vtable_xref.py` (43 s) |
| 0x183976038 (主) を参照する命令 | 0x18000e580 (`mov [rcx],rax`) / 0x18000e91a | 同上 |
| RTTI (COL) | 両 vtable とも COL 型名 `.?AVMassiveXAudioClass@@`・offset 0x0 / 0x80 | `dsp/scripts/mx_vtable_rtti.py` |

0x18000e580 は、0x183976038 (主) を `[rcx]` に、0x1839761b8 (副) を `[rcx+0x80]` に書くコンストラクタ部。
`MassiveXAudioClass` の多重継承の副基底 vtable と読める。

## 3. 前 run の誤りの原因

- PR #1422 は「partial = IAudioProcessor の vtable」と仮定して 0-based 順で slot 9 を選んだ。仮定の検証 (RTTI 突合) を
  行わなかった。REPORT §12 の「前提 (未確認)」にも同じ注記があった。
- 本 run で RTTI を突合したところ、partial は MassiveXAudioClass 自身の副 vtable だった。

## 4. 次の作業 (U1 の正しい入口)

1. RTTI 全走査: 型名 `.?AVIAudioProcessor@Vst@Steinberg@@` の TypeDescriptor を指す COL を探し、その COL の
   `pClassDescriptor` の base 配列から、IAudioProcessor を基底に持つ具体クラスを列挙する (`mx_vtable_rtti.py` の拡張)。
2. 見つかったクラスの主 vtable の、IAudioProcessor 由来の slot (IUnknown 3 + IPluginBase 2 + IAudioProcessor 順) を読む。
3. その slot 先の本体で ProcessData (rdx) の `[rdx+disp]` を集計する (`mx_slot_body.py`)。

**注意**: `mx_roots.py` は全 class 実行で 15 分超のため (#266 の前 run 報告)、RTTI 全走査は対象を限定して行う。

## 5. 本 run の検証 (実測)

- `mx_vtable_xref.py`: 0x1839761b8 / 0x183976038 の RIP 相対参照を 2 件ずつ検出 (43 s, load 未測定)。
- `mx_vtable_rtti.py`: 2 vtable とも COL 型名 `MassiveXAudioClass`。
- 線形逆アセンブル (`capstone` を `.text` 先頭から) は 0x180004c27 で停止 (データ・未対応命令)。
  このため xref は disp32 の全位置照合方式にした。線形を使う方式は採らない。

## 6. 未解決 (起票先)

- U1 本体 (IAudioProcessor を基底に持つクラスの主 vtable 同定と process slot の本体解析): **#266** (本 issue・残件)。
- U2/U5 (closure 厳密化): #1122 (CLOSED・成果は `REPORT_MX5.md`)。
- U3/U4 (vectorcall / C++ EH): #1123 (OPEN)。
- MX2-3 (N5/N6): #830 (OPEN)。
