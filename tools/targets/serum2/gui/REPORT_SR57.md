# REPORT — [SR-57 #3626] patch 後の demo 表示経路の静的確認 (SR-28 受入 3)

- 日付: 2026-10-15 / 親: #1917 (SR-28 の受入 3 を切り出し) / 前段: `REPORT_SR24.md`・`REPORT_SR28.md`・`REPORT_SR30.md`・`REPORT_SR34.md`
- 範囲: 静的解析のみ。実 VSTGUI 上の動的確認は範囲外 (`#68` 残作業)。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `Serum2.vst3`。sha256 `501e7bb3…5283` / 19,236,864 B (前段と一致)。patch 済み PE は `license/authstub/mpatch.py` (原 bytes 照合 6/6 OK) で作る。
- 測定 commit: `5a3c23a8c` (解析スクリプト 2 本を追加した commit)。以降 `tools/targets/serum2/gui/*.py` は未変更 (`git diff 5a3c23a8c HEAD -- tools/targets/serum2/gui/` の出力 0 行)。

## 0. 結論

| 受入条件 | 判定 |
|---|---|
| 3a. overlay_demo_version(_mini) の呼出元 (表示経路) | **到達不能 (証明)**。uidesc の参照は bitmap 登録の 4 行 (key と path、2 組) だけで、view 属性からの参照は 0 件。PE 本体に文字列は 0 件。patch の有無と無関係に表示経路が無い |
| 3b. demo 表示 (`Serum Demo Version` ダイアログ) の呼出 `0x18004fc9c` | **patch 後に到達不能 (証明)**。関数 `0x18004fad0` 内の CFG で entry から届かない (間接 jmp 0 件)。原 PE では届く |
| 3c. `0x1800501c0` (show_msg_helper) そのものの到達不能 | **示せない (受入の前提が不成立)**。汎用のメッセージ表示関数で、demo 以外の呼出元 4 件が patch 後も到達しうる (下表)。受入文の「0x1800501c0 が到達不能」は demo 呼出 site に限定して読み替える必要がある (PM 判断) |

## 1. 呼出元の一覧 (`0x1800501c0` の直接 call/jmp 5 件・実測)

文字列は `demo_dialog_strings.py` (スタックの XOR 復号) と `lea` 参照 (`demo_dialog_reach.py`) で読んだ。

| site | 所属関数 | 表示文字列 (title / message) | 種別 | 原 PE (関数内) | patch 後 (関数内) | 判定 |
|---|---|---|---|---|---|---|
| `0x18004fc9c` | `0x18004fad0` (DSP setState) | `Serum Demo Version` / `Sorry, the demo does not save or recall state with a host DAW session.` | **demo** | 到達 | **到達不能 (証明)** | 本件の対象 |
| `0x18004fdaf` | `0x18004fad0` | `Unable to restore session state` / `The host provided invalid data to the Audio Processor` | 復元失敗 (非 demo) | 到達 | 到達 (根: vtable `0x180a24048` slot 12・間接) | 非 demo。patch では塞がらない |
| `0x1800500b2` | `0x18004ffc0` (EH funclet) | 文字列は `lea` の窓外。`license/REPORT.md` の既存記述では `An internal error occurred, please report this to Xfer Support.` (本 run で再確認していない) | EH catch (非 demo) | 到達 | 到達 (根: EH。直接呼出 0 件) | 非 demo |
| `0x180050769` | `0x1800506b0` | `Error` / `Not a valid Serum preset.` | preset 読込 (非 demo) | 到達 | 到達 (根: vtable `0x180a24158` slot 5・間接) | 非 demo |
| `0x1800760e1` | `0x180075d90` | `unable to render Warp` / `The Warp modes on this oscillator are set to Off.  Nothing t…` | 非 demo | 判定保留 (間接 jmp 1 件) | 判定保留 | 非 demo |

- `0x18004fdaf` の title「Unable to restore session state」は、`license/REPORT.md` の EH 記述 (復元失敗の文言) と一致する (復号の相互確認)。
- 関数内判定の規則: patch 後の機械語で関数 entry から jcc・jmp・ret・fallthrough を辿り、site に届くかを見る。間接 jmp が 1 件でもあれば判定を保留する。
- 上位の連鎖: 届く site は、所属関数への直接 call を逆向き BFS で辿り、根 (直接呼出元の無い関数・`.rdata` に関数ポインタとして現れる関数) まで届くか見る。根に届くことは「到達可能 (未証明)」であって、到達の証明ではない。

## 2. 3a overlay_demo_version(_mini) の確認 (実測)

| 対象 | 方法 | 結果 |
|---|---|---|
| uidesc (`.rsrc` の zstd 展開。`gui/extract_uidesc.py`・2,093,822 B) | `overlay_demo_version` の出現 | 4 件。すべて `"overlay_demo_version": { "path": "overlay_demo_version" }` 形式の bitmap 登録 (`_mini` 側も同形)。`bitmap` 属性や template からの参照は 0 件 |
| PE 本体 (raw bytes) | ASCII・UTF-16LE の `overlay_demo_version` | 0 件 / 0 件 |

- 既存の `REPORT.md` §3 の「bitmap 登録のみ」と一致する。呼出元は 0 件なので、patch の前後のどちらでも表示されない。
- 「patch 後に到達不能」という表現は、この件では patch と無関係な事実 (そもそも参照されない) である。

## 3. 再現手順

```sh
cd $S   # tools/targets/serum2 の work/ (gitignore)
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" -C ext --wildcards '*Install_Xfer_Serum2_2.1.5.exe'
7z x -y -oexe_extract ext/Install_Xfer_Serum2_2.1.5.exe '$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3'
cp -f 'exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' Serum2_win64.vst3
python3 license/authstub/mpatch.py work/Serum2_win64.vst3 work/Serum2_win64.authstub.vst3
python3 gui/demo_dialog_reach.py work/Serum2_win64.vst3 work/Serum2_win64.authstub.vst3   # 1 本目: patch 後の判定
python3 gui/demo_dialog_reach.py work/Serum2_win64.vst3 work/Serum2_win64.vst3           # 対照: 原 PE (patch 無し)
python3 gui/demo_dialog_strings.py work/Serum2_win64.vst3                                 # 2 呼出の文字列 (復号)
python3 gui/extract_uidesc.py work/Serum2_win64.vst3 work/uidesc.json                     # uidesc (3a)
```

- 依存: `pefile` `capstone` `zstandard` (python 3.14)。
- 実測 (n=1, 逐次): `demo_dialog_reach.py` (patch 後) real **15.3 s**・load (実行直前の 1 分平均) **0.39**。`demo_dialog_strings.py` は 1 s 未満。
- 対照 (原 PE): `0x18004fc9c` は `intra-reach orig=True` で届く。patch で届かなくなるのは `0x18004fc9c` だけで、`0x18004fdaf` は両方とも届く。判定は patch の有無に依存している (ネガティブコントロール: `mpatch.py` の N1 を外すと、demo site は届く)。

## 4. 検証範囲 / 範囲外

- 範囲内: `0x18004fad0` (size 1263) と、直接呼出元 5 件の所属関数 (`0x18004ffc0`・`0x1800506b0`・`0x180075d90` を含む)。関数内 CFG の判定は、間接 jmp 0 件の関数で成り立つ。
- 範囲外: 間接呼出 (`call [reg+disp]`) の呼出元の列挙 (SR-34 の (A)・(B))。実 VSTGUI 上の動的確認 (`#68`)。switch 表の解決 (`0x1800760e1` の間接 jmp 1 件)。
- 復号は、同じ命令列の即値と `rip` 相対参照を読んで再現した。復号規則は命令列から導いたもので、実行による確認はしていない (文字列は 2 件とも既存 REPORT の記述と整合)。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入 3 の文言「`0x1800501c0` が到達不能」は、汎用関数のため成立しない。demo 表示 site (`0x18004fc9c`) に限定して読み替えるかは PM 判断 | 受入 3 | 本 PR 本文 (issue 本文の訂正は PM) |
| `0x18004fad0` の entry が実際に呼ばれる経路 (vtable `0x180a24048` slot 12 の間接呼出元) | demo 表示の最上流 (実際に呼ばれるか) | #3236・#3237 (SR-34 系) |
| `0x1800760e1` (`0x180075d90`) の判定保留 (間接 jmp 1 件・switch 表) | 非 demo の補足 | 本 PR 本文 (demo と無関係) |
| 実 VSTGUI 上の動的確認 | 受入 4 相当 | `#68` 残作業 |
