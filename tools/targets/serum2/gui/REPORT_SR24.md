# REPORT — [SR-24 #1710] Splice 3 テンプレートの実体化分岐と demo ダイアログ到達性 (静的)

- 日付: 2026-10-14 / 親: #68 [SR-7] / 前段: `gui/REPORT.md` §2-3・§3 (残留 2 点), `license/authstub/REPORT.md` §4 N7
- 範囲: 静的解析のみ。実 VSTGUI 上の動的確認は受入条件 5 として本 issue の範囲外。
- 入力: `plugins-serum2` の `Install_Xfer_Serum2_2.1.5.exe` → `Serum2.vst3`。sha256 `501e7bb3dd9cafe416b3412df3d4e084c01b7468201e5690b9009d7ecd4e5283` / 19,236,864 B (`gui/REPORT.md` §1 と一致)。`work/` (gitignore) に置いた。
- 検証起点: 本 PR の commit (`1710-sr-24-splice-template-static`, base `origin/main` de62fc46)。

## 0. 結論

| 受入条件 | 判定 |
|---|---|
| 1. state → template の分岐関数を特定 | **未達** (子 #1917 へ移す)。テンプレート名 (`SpliceRTO` / `SpliceExpired` / `SpliceMaxLimit`) は平文・UTF-16 のどちらにも無く、名前で分岐する関数を見つけられなかった。分かったのは sub-controller 生成の経路 (§2) まで |
| 2. 分岐が demo bit (+0x22792) に依存することの静的確認 | **未達** (子 #1917 へ移す)。demo bit の読み出し箇所は特定した (§3) が、Splice 表示条件との結線は未確認 |
| 3. overlay_demo_version(_mini) が patch 後に到達不能 | **未達** (子 #1917 へ移す)。demo ダイアログ呼出 `0x1800501c0` の 5 呼出元のうち、2 関数は直接呼出が無く (vtable 等の間接経路)、到達性を閉じられなかった (§4) |
| 4. REPORT に記録 | 本ファイルで実施。`tools/targets/serum2/REPORT.md` は 250 行上限のため無変更 |
| 5. 実 VSTGUI の動的確認 | 範囲外 (GUI lift 時。`#68` 残作業として追跡) |

### 0-1. 測定 commit と差分 (WORKFLOW §6)

- 測定 commit: `6af8b94a` (コードを変えた最後の commit。`xref_rva.py` はこの commit で作成)。
- `git diff 6af8b94a HEAD -- 'tools/targets/serum2/gui/*.py'` の実出力: 0 行 (コード差分 0)。
- `git diff --stat 6af8b94a HEAD -- tools/targets/serum2/gui` の実出力: `tools/targets/serum2/gui/REPORT_SR24.md | 38 +++++++++++++++++++++++---------` (28 insertions, 10 deletions)。gui 範囲で変わったのは本 REPORT (文書) のみで、測定対象のコード差分は 0 (変更は文書のみ)。
- 本 run の環境: runner 上で `Serum2_win64.vst3` を作れず、上記の実測は再現していない (§1・§4 参照)。

## 1. 再現手順

```sh
# cwd: tools/targets/serum2/ (work/ は gitignore)
tar --zstd -xf "$ARTIFACTS_DIR/plugins-serum2.tar.zst" -C work/plugins-serum2 --wildcards '*Install_Xfer_Serum2_2.1.5.exe'
7z x -y -owork/exe_extract work/plugins-serum2/Install_Xfer_Serum2_2.1.5.exe
cp -f 'work/exe_extract/$COMMONFILES64/VST3/Serum2.vst3/Contents/x86_64-win/Serum2.vst3' work/Serum2_win64.vst3
work/venv/bin/python gui/extract_uidesc.py work/Serum2_win64.vst3 work/uidesc.json   # 2,093,822 B
work/venv/bin/python gui/xref_rva.py work/Serum2_win64.vst3 fc55b4 1195f14            # 文字列の rip 参照元
```

- 依存: `pefile` `capstone` `zstandard` (venv `work/venv`)。
- 所要 (前 run の値・real, 逐次, n=1): `xref_rva.py` 8.87 s (`.text` 全走査)。**load average は未記録** (前 run で `uptime` を取っていない)。
- **本 run (再測定) の状況**: 素材 `plugins-serum2` が runner 上に無く (`$ARTIFACTS_DIR` は `fl-win64.tar.zst` のみ。その中身にも Serum2 は無い)、入力 `Serum2_win64.vst3` を作れなかった。よって `xref_rva.py` の再測定・`extract_uidesc.py` の再測定は**未実施**。上記 8.87 s と 2,093,822 B は前 run の値で、本 run では再現していない。
- `extract_uidesc.py`: **未計測** (理由: 入力 `Serum2_win64.vst3` が本 run で作れないため)。
- **負例・検算 (別バイナリでの動作確認。Serum2 の判定の検算ではない)**: runner 同梱の `jlinenative.dll` (`/usr/share/apache-maven-3.10.0/lib/jline-native/Windows/x86_64/`) の `.text` を対象に `xref_rva.py` を実行。
  - 正の対照: file `0x4800` (VA `0x2e76f6000`, `.rdata`) → `xref_rva.py` は 1 件 (`0x2e76f13b1: lea rdx, [rip + 0x4c48] -> 0x2e76f6000`)。
  - 検算: `objdump -d -M intel` で `# 2e76f6000` を含む rip 参照を数えると 1 件 (同じ `0x2e76f13b1`)。一致。
  - 負の対照: file `0x4801` (VA `0x2e76f6001`, 参照なし) → `xref_rva.py` 0 件、objdump 0 件。一致。
  - 時間計測は本 run では未実施 (所要・load は未記録)。
- 未検算のまま残す項目: `0x1804a22a1` の 1 件 (Serum2 本体は runner に無い)、`0x1804a1950` の vtable スロット 11 (`0x180a86be0`)、`0x1800501c0` の 5 呼出元と上流 2 関数の直接呼出 0 件。いずれも未解決 (6) で追跡。
- 再測定の条件 (未解決 (6) で追跡): `plugins-serum2` を依頼に `oc_artifacts:` で指定して取得し、`uptime` を実行前後に記録、逐次で n≥3 の min–max を取る。

## 2. 分岐の探索結果 (実測)

### 2-1. 名前の所在

| 文字列 | 平文 (ASCII) | UTF-16LE | 備考 |
|---|---|---|---|
| `SpliceRTO` / `SpliceExpired` / `SpliceMaxLimit` | 0 | 0 | uidesc 内 (zstd 圧縮) にのみ存在 |
| `overlay_demo_version` | 0 | 0 | uidesc 内の bitmap 登録のみ |
| `SpliceController` | 2 | - | file 0xfc55b4 (sub-controller 名テーブル), 0x1195f14 (RTTI `.?AVSpliceController@@`) |

### 2-2. sub-controller 名 → 生成の経路

- `SpliceController` 名文字列 (file 0xfc55b4 → VA 0x180fc6bb4) を参照する命令は `0x1804a22a1` の 1 箇所 (`xref_rva.py`)。
- その関数 `0x1804a1950` (size 0xc63) は、渡された名前文字列を `0x180035010` (文字列一致) で順に比較する**名前→ファクトリの振り分け**。`SpliceController` 一致時は `0x1807964d0` 系を呼ぶ。
- `0x1804a1950` の直接呼出元 `0x1804a16b7` (関数 `0x1804a14c0`) は `.rdata` の vtable `0x180a86b88` のスロット 11 (`0x180a86be0`) から参照される。`call`/`lea` での直接参照は無い。
- **分かったこと**: uidesc の `sub-controller: SpliceController` を解決する経路は確定。**テンプレート名 (RTO/Expired/MaxLimit) をどの state で選ぶかは、この経路の上流で決まるため未特定。**

### 2-3. 未確定 (受入条件 1 の残り)

- テンプレート名は平文に無いため、名前で直接選ぶ関数は探せなかった。実体化は uidesc の子 index など名前以外の経路か、vtable 経由 (スロット 11 の上流) の可能性がある。
- `SpliceController` のメソッド候補 (`0x180796320` / `0x180796090` / `0x180542a20`) のうち、`0x180796320` は既知 (support 記事 URL を開くボタン処理, `gui/REPORT.md` §2-2)。`0x180796090` (size 587) は未解析 (前 run から変更なし)。

## 3. demo bit (+0x22792) の読み出し・書込み (実測)

`[rsi+0x22790]` / `[rsi+0x22792]` / `[rsi+0x22b70]` を含む命令を `.text` 全体で走査した結果 (9 件):

| アドレス | 命令 | 関数 (既知) |
|---|---|---|
| 0x1800aa336 | `mov [rsi+0x22790], 0` | (未確認) |
| 0x1800ac7b0 / 0x1800b95ae | `mov rdx, [rsi+0x22790]` (読み) | (未確認) |
| 0x1800c2cfe | `mov [rsi+0x22792], al` (書き・patch N2a-1) | `SerumController::setState` 0x1800c2b50 |
| 0x1800c2d42 | `mov [rsi+0x22792], 1` (書き・patch N2a-2) | 同上 |
| 0x1800c2d52 | `test [rsi+0x22792], 1` (読み) | 同上 |
| 0x1800c2f08 / 0x1800c2f11 | `cmp [rsi+0x22790], 1` / `or [rsi+0x22b70], 0x10` | 同上 |
| 0x1800c6874 | `cmp [rsi+0x22792], 1` (読み) | `SerumController::getState` 0x1800c6090 |

- `license/authstub/REPORT.md` の「+0x22792 の writer は setState の 2 store のみ」と**一致** (前 run で全 .text 走査により確認。本 run では未再確認: 入力 `Serum2_win64.vst3` が無い)。
- 0x1800aa336 / 0x1800ac7b0 / 0x1800b95ae は authstub REPORT に言及が無い。+0x22790 のみで +0x22792 ではない。demo 判定の別経路かは未確認。

## 4. demo ダイアログ呼出 0x1800501c0 の到達性 (受入条件 3)

`0x1800501c0` の呼出元 5 箇所:

| 呼出元 | 所属関数 | 関数の直接呼出元 |
|---|---|---|
| 0x18004fc9c / 0x18004fdaf | 0x18004fad0 (size 0x4ef) | **0 件** (vtable 経由の可能性) |
| 0x1800500b2 | 0x18004ffc0 (size 0x11b) | **0 件** |
| 0x180050769 | 0x1800506b0 (size 0x247c) | 0x18004feb0, 0x1800711f5 |
| 0x1800760e1 | 0x180075d90 (size 0x368) | 0x1800684c4 |

- 直接呼出元が無い 2 関数 (0x18004fad0 / 0x18004ffc0) は、到達性が間接経路に依存するため**静的には閉じられなかった**。
- ネガティブコントロール・検算 (objdump 等による rip 参照元の別手段確認、vtable 位置の確認) は**本 run では未実施**。理由: 入力 `Serum2_win64.vst3` が runner 上に無いため、いずれも実バイナリに対して実行できない。前 run の `0x1804a22a1` 1 件・`0x1800501c0` 呼出元 5 箇所は未検算のまま記載している (未解決 (6) で追跡)。
- patch 後の到達不能を言うには、(a) 0x18004fad0 / 0x18004ffc0 の vtable 上の位置、(b) 0x1800506b0・0x180075d90 の各上流が demo bit で分岐するか、の確認が要る。本 run では未実施。

## 5. 残る作業 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (1) state → template 名の選択経路 (名前で分岐しない場合の index / vtable 経路) | `authstub` N7 の「非表示固定」が未検証 | #1917 |
| (2) demo bit と Splice 表示条件の結線 (§3 の 0x1800aa336 / 0x1800ac7b0 / 0x1800b95ae を含む) | 受入条件 2 | #1917 |
| (3) 0x18004fad0 / 0x18004ffc0 の vtable 位置と demo ダイアログ到達性 | 受入条件 3 | #1917 |
| (4) 0x180796090 の解析 | 受入条件 1 の補助 | #1917 |
| (5) 実 VSTGUI 上の動的確認 | 受入条件 5 | `#68` 残作業 (GUI lift 時) |
| (6) 本 run での再測定・検算・負例 (xref_rva.py の 8.87 s / load / uidesc 計測、ネガティブコントロール、objdump 等による検算) | §1・§4 の数値が未検算 | `#1917` (素材 `plugins-serum2` を依頼で取得してから実施) |
