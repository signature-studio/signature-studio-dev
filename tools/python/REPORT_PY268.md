# PY-268 (#3901): 公開表 0x12acb70 と動的メソッド表 0x12ab520 (TFXForm) の参照経路の PE 確定

親: #3616 (PY-220)。前段: `tools/python/REPORT_PY203.md` §1・§5。前段が参照する `REPORT_PY220.md` と `pe_py220_methods.py` は main に存在しない (先行 run の成果は push されていない)。本 REPORT は PE から再確立した。
既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブルと参照走査による解析)。
KPI: 起動・GUI に関わらないため記載不要 (解析のみ)。

## 結論

| 受入 | 結果 | 根拠 |
|---|---|---|
| 1. 0x12acb70 の公開表エントリと DFM の結び付き | **確定** (エントリ・所属・DFM の結び付き) | §1・§3 |
| 2. 0x12ab520 の参照経路 | **確定**: TFXForm の動的メソッド表 (DMT)。命令からの参照は 0 件 | §2 |
| 3. 0x12acb70 の rdx (第 2 引数) の発火側 | **未確定** → 子 #3937 [PY-274] | §4 |
| 4. 0x12ab520 の rdx (第 2 引数) の発火側 | **未確定** → 子 #3937 [PY-274] | §4 |

issue #3901 の範囲を受入 1・2 に縮めた (3・4 は #3937 へ移し、本文から外した)。

## 0. 対象と前提

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` (2.3 GB) を `tar --zstd -xf ... -C $RUNNER_TEMP/fl-win64 --wildcards '*block00031_PE.bin'` で展開 (`<展開先>/extracted/block00031_PE.bin`、2.9 秒)。
- 検証起点 commit: origin/main `512b09ffa`。
- 表記: ImageBase 0x400000、.text の VA 0x401000 (ファイル位置 0x400)。VA は `pe_callgraph.py` と同じ。
- Delphi (Win64) の VMT 配置は標準的な配置 (VMT-40 公開表、VMT-32 動的メソッド表、VMT-24 vmtClassName) を前提とする (推定)。VMT-24 が指す ShortString "TFXForm" で VMT の位置 0x1277ec8 を確かめた。

## 1. 公開表エントリ (受入 1)

- エントリ形式: `{Size u16, Code (8 バイト・上位 4 バイト 0), 名前 (ShortString)}`。Size = 2 + 8 + 1 + len(名前) が以下 3 件で一致。

| Code | エントリ位置 (VA) | Size | 名前 |
|---|---|---|---|
| 0x12acb70 | 0x127956f | 0x1c | MoveLeftMenuClick |
| 0x12ac210 | 0x1279c33 | 0x21 | TracksPanelMMouseWheel |
| 0x12ab710 | 0x1279614 | 0x19 | FormMouseWheel |

- 所属: TFXForm の VMT-40 (0x1277ea0) が指す公開表 0x12793f3 (件数 120)。Size で歩くと 0x127956f がエントリ先頭に一致する。
- 0x12acb70 の Code の出現は 1 件 (表エントリ)。命令の即値・絶対 disp・RIP 相対の参照は 0 件。

## 2. 0x12ab520 の参照経路 (受入 2)

- 0x12ab520 の 4 バイト値の出現は 1 件 (VA 0x127a2bb、8 バイト未整列)。
- 0x127a2b7 が動的メソッド表 (DMT): 件数 u16 = 1、DMTIndex u16 = 0x057f (0x127a2b9)、アドレス 8 バイト = 0x12ab520 (0x127a2bb)。
- DMT の参照元: TFXForm の VMT-32 (0x1277ea8) の qword = 0x127a2b7。
- 命令の即値・絶対 disp・RIP 相対の参照は 0 件。直接 call 0 件 (PY-203 の結論と一致)。
- 直前 2 バイト (0x057f) は公開表の Size の式 (2+8+1+len) と一致しない。0x12ab520 は公開表エントリではなく DMT のエントリ。
- DMT の index 0x057f はメッセージ番号とみられる (推定。Delphi の動的メソッドはメッセージ番号で呼ばれる)。

## 3. DFM の結び付き (受入 1 の続き)

- `.rsrc` の DFM 2 進形式: オブジェクト見出し `TQuickMenuItem "MoveLeftMenu"` (0x13e4d7f) → プロパティ `OnClick = MoveLeftMenuClick` (0x13e4dcf) → 次のオブジェクト見出し `TQuickMenuItem "MoveRightMenu"` (0x13e4df4)。
- `OnMouseWheel = TracksPanelMMouseWheel` は .rsrc に 2 件 (0x13e1575・0x13e191d)。所有オブジェクトは未確認 (本 issue の範囲外)。
- 推定: DFM 読込みで `TMethod(Code = 0x12acb70, Data = TFXForm インスタンス)` が作られ、TQuickMenuItem の OnClick に入る。

## 4. 未確定 (rdx の発火側) → #3937

- 0x12acb70: 発火側は TMenuItem 系の Click (`FOnClick(Self)` に相当) とみられる。rdx = Sender = `TQuickMenuItem` インスタンス (推定)。発火の呼出し箇所は未同定。
- 0x12ab520: 発火側は動的ディスパッチ RTL (VMT-32 を読み DMT の index を照合する関数)。rdx = Message 引数 (推定)。RTL 関数は未同定。
- 試行: `mov r, qword ptr [r' - 0x20]` の全件走査 (16 件) は rbp 相対などの無関係な箇所を含み、VMT-32 の読出しに絞れなかった。

## 5. 検証

- probe: `tools/python/analysis/flapi/pe_py268_rdx.py` (15 件)。
  - 測定 commit (コードを変えた最後の commit): `b5d65bb35`。同一 commit で 2 回測定し、いずれも 15/15 PASS・終了 0 (40.6 秒・40.5 秒)。
  - 実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64/extracted python3 tools/python/analysis/flapi/pe_py268_rdx.py`。
- 差分の証跡: `git diff b5d65bb35 HEAD -- tools/python/analysis/flapi` の出力は 0 行 (本 REPORT の commit は docs のみ)。
- 負の対照: 未実施 (時間制限)。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x12acb70 の発火側 (TMenuItem の Click 系) と rdx の出どころ | 受入 3 | [PY-274] #3937 |
| 0x12ab520 の発火側 (動的ディスパッチ RTL) と rdx の出どころ | 受入 4 | [PY-274] #3937 |
| `REPORT_PY220.md`・`pe_py220_methods.py` が main に無い (前段の参照切れ) | 前段の結論の再現 | 本 PR で再確立 (§1〜§2)。前段側の REPORT 修正は不要 |
