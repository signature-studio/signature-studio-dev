# PY-268 (#3901): 公開表 0x12acb70 と動的メソッド表 0x12ab520 (TFXForm) の参照経路の PE 確定

親: #3616 (PY-220)。前段: `tools/python/REPORT_PY203.md` §1・§5、`tools/python/REPORT_PY220.md` (main 取り込み済み。本 REPORT は PY-220 と同じ VMT 0x1277f38・公開表 0x12793f3 を独立に再確認)。
既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブルと参照走査による解析)。
KPI: 起動・GUI に関わらないため記載不要 (解析のみ)。

## 結論

| 受入 | 結果 | 根拠 |
|---|---|---|
| 1. 0x12acb70 の公開表エントリと DFM の結び付き | **確定** (エントリ・所属 (VMT-0x98)・DFM の結び付き) | §1・§3 |
| 2. 0x12ab520 の参照経路 | **確定**: TFXForm の動的メソッド表 (DMT)。VMT-0x90 のデータポインタから辿る。命令からの参照は 0 件 (直接・RIP 相対・即値・絶対値・fall-through の検査) | §2 |
| 3. 0x12acb70 の rdx (第 2 引数) の発火側 | **未確定** → 子 #3937 [PY-274] | §4 |
| 4. 0x12ab520 の rdx (第 2 引数) の発火側 | **未確定** → 子 #3937 [PY-274] | §4 |

issue #3901 の範囲を受入 1・2 に縮めた (3・4 は #3937 へ移し、本文から外した)。

## 0. 対象と前提

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` (2.3 GB・実在を確認) を `tar --zstd -xf ... -C $RUNNER_TEMP/fl-win64 --wildcards '*block00031_PE.bin'` で展開 (`$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin`、2.9 秒)。`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64` (WORKFLOW §11)。
- 検証起点: origin/main `f14b81315` を merge 済み (merge commit `ce63da063`・rebase なし)。
- 表記: ImageBase 0x400000、.text の VA 0x401000 (ファイル位置 0x400)。`.rsrc` は VA 0x1ab1000・ファイル位置 0x1321c00。§3 の `0x13e…` はファイル位置で、VA ではない。
- Delphi (Win64) の VMT 配置 (標準): 自己ポインタ VMT-0xc8、公開表ポインタ VMT-0x98、動的メソッド表ポインタ VMT-0x90、vmtClassName VMT-0x88。
- VMT の同定 (classname の位置から逆算しない): .text の 8 バイト整列位置 p のうち `[p] == p+0xc8` を満たす候補は 3728 件 (PY-220 §2 の 3530 件とは数え方が異なる・未調査)。そのうち `[V-0x88]` が ShortString "TFXForm" を指すのは 1 件で、**VMT = 0x1277f38**。陽性の根拠は `[0x1277e70] = 0x1277f38` (VMT-0xc8 の自己ポインタ)。
- 前版の訂正: 前版は VMT を 0x1277ec8 (VMT-40/-32/-24 の配置を前提) とした。VMT-24 の検査は classname の位置から逆算した値で、必ず通る同語反復だった。0x1277ec8 は自己ポインタ検査で不一致 (`[0x1277e00] = 0x20000000001`) なので誤り。本版で訂正した。

## 1. 公開表エントリ (受入 1)

- エントリ形式: `{Size u16, Code (8 バイト・上位 4 バイト 0), 名前 (ShortString)}`。Size = 2 + 8 + 1 + len(名前)。

| Code | エントリ位置 (VA) | Size | 名前 |
|---|---|---|---|
| 0x12acb70 | 0x127956f | 0x1c | MoveLeftMenuClick |
| 0x12ac210 | 0x1279c33 | 0x21 | TracksPanelMMouseWheel |
| 0x12ab710 | 0x1279614 | 0x19 | FormMouseWheel |

- 所属: TFXForm の VMT-0x98 (0x1277ea0) が指す公開表 0x12793f3 (件数 120)。Size で 120 件歩くと 0x127956f・0x1279614・0x1279c33 の 3 件すべてに一致する。
- 負の対照: 先頭エントリの Size を +1 にずらすと、既知の 3 件の一致は 0 件に落ちる (検出)。
- 各 Code の出現は 1 件 (表エントリ)。命令からの参照は 0 件 (§2 と同じ検査)。

## 2. 0x12ab520 の参照経路 (受入 2)

- 0x12ab520 の 4 バイト値は全ブロックで 1 件 (ファイル位置 0xe796bb = VA 0x127a2bb・8 バイト未整列)。8 バイト整列位置の出現は 0 件。
- 動的メソッド表 (DMT) 0x127a2b7: 件数 u16 = 1、DMTIndex u16 = 0x057f (0x127a2b9)、アドレス 8 バイト = 0x12ab520 (0x127a2bb)。
- DMT の参照元: 8 バイト整列の 0x127a2b7 の出現は 1 件 = VMT-0x90 (0x1277ea8)。
- 命令の参照 (直接分岐・絶対 disp・RIP 相対・即値) は線形走査で 0 件 (0x12ab520・0x127a2bb・0x127a2b9)。
- 0x127a2ba の検査 (線形走査の読みで DMT の中に起点がある。`05 20 b5 2a 01`):
  - 分岐先・即値として 0x127a2ba: 0 件。
  - 0x127a2ba で終わる命令 (fall-through 元): 15 バイト前からの各開始位置の復号で 0 件。
  - 絶対値 (4 バイト・8 バイト) として 0x127a2ba: 0 件。
  - 逐次復号では `add eax, 0x12ab520` と読めるが、これは DMT の index 上位 (0x05) と address 欄の重なり読みで、上の 3 検査により 0x127a2ba へ到達する経路は無い。
- 結論: 0x12ab520 は命令から参照されず、VMT-0x90 から辿る DMT のエントリ。上の検査は直接参照・fall-through・絶対値に限る (レジスタ経由で計算された間接参照は対象外)。
- DMT の index 0x057f はメッセージ番号とみられる (推定。Delphi の動的メソッドはメッセージ番号で呼ばれる)。

## 3. DFM の結び付き (受入 1 の続き)

- `.rsrc` の DFM 2 進形式 (ファイル位置。VA ではない): オブジェクト見出し `TQuickMenuItem "MoveLeftMenu"` (0x13e4d7f) → プロパティ `OnClick = MoveLeftMenuClick` (0x13e4dcf) → 次のオブジェクト見出し `TQuickMenuItem "MoveRightMenu"` (0x13e4df4)。
- `OnMouseWheel = TracksPanelMMouseWheel` は `.rsrc` に 2 件 (ファイル位置 0x13e1575・0x13e191d)。所有オブジェクトは未確認 (本 issue の範囲外)。
- 推定: DFM 読込みで `TMethod(Code = 0x12acb70, Data = TFXForm インスタンス)` が作られ、TQuickMenuItem の OnClick に入る。

## 4. 未確定 (rdx の発火側) → #3937

- 0x12acb70: 発火側は TMenuItem 系の Click (`FOnClick(Self)` に相当) とみられる。rdx = Sender = `TQuickMenuItem` インスタンス (推定)。発火の呼出し箇所は未同定。
- 0x12ab520: 発火側は動的ディスパッチ RTL (VMT-0x90 を読み DMT の index を照合する関数)。rdx = Message 引数 (推定)。RTL 関数は未同定。
- 試行: `mov r, qword ptr [r' - 0x20]` の全件走査 (16 件) は rbp 相対などの無関係な箇所を含み、VMT-0x90 の読出しに絞れなかった。
- 子 #3937 の起票区分 (WORKFLOW §3 の「実装・修復」か「原因特定」か) は PM 判断 (pm-decision)。本 REPORT では変更していない。

## 5. 検証

- probe: `tools/python/analysis/flapi/pe_py268_rdx.py` (22 件)。
- 測定 commit (コードを変えた最後の commit): `4452538fb`。同一 commit で 3 回測定し、いずれも 22/22 PASS・終了 0。
  - 所要: 42.91 秒・42.90 秒・42.66 秒。load average (1 分値・4 コア): 開始前 0.74・0.88・0.94 → 終了後 0.88・0.94・0.97。
  - 実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/pe_py268_rdx.py`
- 負の対照 (検出できれば PASS): (a) VMT 候補 0x1277ec8 の自己ポインタ検査 → FAIL (検出)。(b) 公開表先頭 Size +1 → 既知 3 件の一致 0 件 (検出)。(c) 0x127a2ba の絶対値・fall-through の検査は陽性の対照を持たない (0 件の確認のみ)。
- 差分の証跡: `git diff 4452538fb HEAD -- tools/python/analysis/flapi` の出力は 0 行 (本 REPORT の commit は docs のみ)。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x12acb70 の発火側 (TMenuItem の Click 系) と rdx の出どころ | 受入 3 | [PY-274] #3937 |
| 0x12ab520 の発火側 (動的ディスパッチ RTL) と rdx の出どころ | 受入 4 | [PY-274] #3937 |
| 子 #3937 の起票区分 (実装・修復か原因特定か) | WORKFLOW §3 の境界 | PM 判断 (pm-decision) |
