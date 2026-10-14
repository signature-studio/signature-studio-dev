# REPORT — [SR-28 #1917] Splice テンプレートの実体化経路と demo ダイアログ到達性 (静的)

- 日付: 2026-10-14 / 親: #1710 (SR-24 残件) / 前段: `gui/REPORT_SR24.md` §2-§4
- 範囲: 静的解析のみ。実 VSTGUI 上の動的確認は受入条件 4 (範囲外・GUI lift 時)。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `Serum2.vst3`。sha256 `501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283` / 19,236,864 B (SR-24 と一致)。`work/` (gitignore) に置いた。
- 検証起点: 本 PR の測定 commit (下記 §0-1)。

## 0. 結論

| 受入条件 | 判定 |
|---|---|
| 1. state → template の選択経路 | **部分達成**。テンプレート名は uidesc の `templates` に 3 件 (`SpliceRTO` / `SpliceExpired` / `SpliceMaxLimit`) として定義され、いずれも `sub-controller: SpliceController`。uidesc 内の `template-names` 切替 (`template-switch-control`) からは参照されない。名前で分岐する関数は未特定。SpliceController の factory 振り分け上流で、vtable `0x180a86b88` を設定する 2 コンストラクタ (`0x180498198` / `0x180498734`) まで特定 |
| 2. demo bit (+0x22792) 依存の確認 | **未達**。SR-24 §3 の読み書き箇所との結線は未確認 |
| 3. overlay_demo_version(_mini) / demo ダイアログ 0x1800501c0 の到達不能 | **未達**。直接呼出 0x1800501c0 の 5 呼出元のうち、0x18004fad0 / 0x18004ffc0 は直接呼出 0 件。0x18004fad0 は vtable 0x180a24048 の slot 12 から参照あり (§4)。0x18004ffc0 は参照 0 件 |
| 4. 実 VSTGUI の動的確認 | 範囲外 (GUI lift 時、`#68` 残作業) |

### 0-1. 測定 commit と差分 (WORKFLOW §6)

- 測定 commit: 本 PR の最後のコード変更 commit (`git log -1 -- tools/targets/serum2/gui/*.py` で確認)。本 run では `gui/*.py` を変更していない。
- 検証 HEAD 起点: `00083cdb` (origin/main)。SR-24 の測定 commit `6af8b94a` から `00083cdb` までの gui 範囲の差分は、SR-24 の文書修正のみ (`git diff 6af8b94a 00083cdb -- tools/targets/serum2/gui/*.py` の出力は本 run で確認)。

## 1. 再現手順・実測 (本 run, runner 上)

```sh
# cwd: tools/targets/serum2/ (work/ は gitignore)
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" -C work --wildcards '*Install_Xfer_Serum2_2.1.5.exe'
7z x -y -owork/exe_extract work/Install_Xfer_Serum2_2.1.5.exe
cp -f 'work/exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' work/Serum2_win64.vst3
work/venv/bin/python gui/extract_uidesc.py work/Serum2_win64.vst3 work/uidesc.json
work/venv/bin/python gui/xref_rva.py work/Serum2_win64.vst3 fc55b4 1195f14
```

- 依存: `pefile` `capstone` `zstandard` (venv `work/venv`、python 3.14)。
- 実測 (n=1, 逐次, load は `uptime` の 1 分平均):
  - `extract_uidesc.py`: real 3.187 s, load 0.26 (07:57)。出力 2,093,822 B (SR-24 と一致)。
  - `xref_rva.py` (fc55b4 / 1195f14): real 7.916 s, load 0.32 (07:57)。出力 `0x1804a22a1: lea rdx, [rip + 0xb2490c] -> 0x180fc6bb4 (file 0xfc55b4)` 1 件 (SR-24 と一致)。
- 入力の sha256 と uidesc の bytes は SR-24 の値と一致し、SR-24 の測定を再現できた。
- 補助スクリプト (`work/sr28_*.py`) は `work/` のみに置き、commit していない。以下 §2-§4 の数値はそれらの実出力。

## 2. state → template の選択経路 (受入条件 1)

### 2-1. uidesc 上の定義と参照 (実測)

- `templates/SpliceRTO` `templates/SpliceExpired` `templates/SpliceMaxLimit` は各々 `attributes.sub-controller = SpliceController`、`class = CViewContainer`、`size = 1190, 740`。SpliceRTO は子に `Still having issues?` / `Open the Splice Desktop App, log in, and check again.` / `Check Again` / `Get Help` を持つ。
- `template-names` (`XferUIViewSwitchContainer` の切替) の全 19 件を走査した結果、`Splice*` を含むものは 0 件。`template` 属性 (ウィンドウ内の埋込) にも 0 件。
- `SerumGUI_Splash` の `template-names = SerumGUI,Splash` / `control = UI::SerumGUI::kUIParamShowAbout` が、uidesc 内で実行時にテンプレートを切り替える唯一の仕組み。Splice 3 件はここからは選ばれない。
- `custom/UITemplateController/SelectedTemplate = Splash` (初期値)。

### 2-2. sub-controller 生成の経路

- `SpliceController` 名文字列 (file 0xfc55b4 = VA 0x180fc6bb4) を参照する命令は `0x1804a22a1` 1 件 (`xref_rva.py`)。
- その関数 `0x1804a1950` は、名前文字列を `0x180035010` (文字列一致) で順に比較する**名前→ファクトリ**の振り分け (SR-24 §2-2)。直接呼出元は `0x1804a16b7` (関数 `0x1804a14c0`) の 1 件。
- `0x1804a14c0` の参照: `.rdata` vtable の slot 11 (`0x180a86be0` の slot, 関数 `0x1804a14c0` の vtable 位置、RVA `0xa86be0`) から間接参照のみ。直接 `call`/`lea` は 0 件。
- SpliceController の vtable head `0x180a86b88` を `lea rax, [rip+…]` で設定するコンストラクタは 2 件: `0x180498198` (`0x180498179`–) と `0x180498734` (`0x180498715`–)。いずれも `mov [rdi+0x78]` / `mov [rsi+0x78]` 直前の同型コード (オブジェクト初期化)。
- **未確定**: この 2 コンストラクタの呼出元 (state → Splice 生成の上流) は未追跡。テンプレート名を選ぶ関数はこの後段で特定する必要がある。

### 2-3. 未達の理由

- テンプレート名は平文にも UTF-16 にも無く、uidesc の切替からも参照されないため、名前で選択する関数を静的に探せなかった。
- 選択は `0x180498198` / `0x180498734` の呼出元の上流にあると見ているが、本 run では未追跡 (時間上限)。

## 3. demo bit (+0x22792) との結線 (受入条件 2)

- SR-24 §3 の 9 件 (読み書き) は再確認していない。本 run では `[rsi+0x22792]` の走査を再実行していない。
- 受入条件 2 の「Splice 表示条件が demo bit に依存する」という結線は**未確認**。2-3 の上流 (選択関数) が特定されていないため、結線を示せない。

## 4. demo ダイアログ `0x1800501c0` の到達性 (受入条件 3)

`0x1800501c0` の直接呼出元 (`call`/`jmp` rel32・全 `.text` 走査, 実測):

| 呼出元 | 所属関数 | 関数の参照 |
|---|---|---|
| 0x18004fc9c / 0x18004fdaf | 0x18004fad0 | 直接 0 件。**`.rdata` qword 参照 1 件** (`.rdata+0xa240a8`) |
| 0x1800500b2 | 0x18004ffc0 | 直接 0 件。**`.rdata` qword 参照 0 件**。`.text` の `rip` 相対参照 0 件 |
| 0x180050769 | 0x1800506b0 | 直接 2 件 (0x18004feb0, 0x1800711f5)。`.rdata` qword 参照 1 件 (`.rdata+0xa24180`) |
| 0x1800760e1 | 0x180075d90 | 直接 1 件 (0x1800684c4)。`.rdata` qword 参照 0 件 |

- `0x18004fad0` の vtable 位置 (実測): `.rdata` 0xa240a8 に格納、vtable head `0x180a24048` の **slot 12** (オフセット 0x60)。vtable を設定する `lea rax, [rip+0x9e624c]` が `0x18003ddf5` (`mov [rcx+0x30], rax`)。コンストラクタ側の呼出元は未確認。
- `0x1800506b0` の vtable 位置 (実測): `.rdata` 0xa24180 に格納、vtable head `0x180a24158` の **slot 5** (オフセット 0x28)。設定箇所 `0x18003de1c`。
- `0x18004ffc0` は `.rdata` の qword からも `.text` の rip 相対参照からも参照が無く、**到達経路を静的に 1 つも示せなかった**。
- 検算: 上記 vtable の slot 呼出 (`call [reg+0x60]`・`[reg+0x28]`・`[reg+0x50]`) は heuristic 走査で汎用的すぎ (該当 40 件超)、vtable と結び付かなかった。対応する間接呼出は未特定。
- 結論: patch 後の到達不能は**示せていない**。0x18004fad0 は vtable 経由の到達が残る。

## 5. 残る作業 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (1) 2 コンストラクタ `0x180498198` / `0x180498734` の呼出元 → state から Splice を選ぶ関数 | 受入条件 1・2 | #2000 |
| (2) demo bit (+0x22792) と Splice 選択の結線 | 受入条件 2 | #2000 |
| (3) vtable 0x180a24048 slot 12 (0x18004fad0) / 0x180a24158 slot 5 (0x1800506b0) の間接呼出元と、0x18004ffc0 の到達経路 | 受入条件 3 | #2000 |
| (4) 実 VSTGUI 上の動的確認 | 受入条件 4 | `#68` 残作業 (GUI lift 時) |
