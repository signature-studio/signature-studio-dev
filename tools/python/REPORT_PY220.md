# PY-220 (#3616): 間接呼出し 4 関数の所属データ構造 (公開メソッド表・VMT スロット)

親: #3476 (PY-203)。前段: `tools/python/REPORT_PY203.md` §1・§5 (PY-220 行)。
既知類型との関係: 該当なし (lift 作業ではない。PE のデータ構造 (公開メソッド表・VMT) の照合)。
子 (未達の受入条件): #3901 (PY-268)・#3902 (PY-269)・#3903 (PY-270)。

## 結論 (PE 実測で確定した範囲)

- **0x12acb70・0x12ac210・0x12ab710 は、TFXForm の公開メソッド表のエントリ**。名前は `MoveLeftMenuClick`・`TracksPanelMMouseWheel`・`FormMouseWheel`。表 (先頭 0x12793f5、Count 120) は TFXForm の VMT (0x1277f38) の `VMT-0x98` から参照される。公開メソッドは名前でイベントに結び付く Delphi の仕組み (推定。発火側は TMethod (Code, Data) を介して呼ぶとみられる)。
- **0x1021670 は VMT 0x1012f40 (TUndoEvent_MovedFXTracks) のスロット 1** (VMT+8)。`call qword ptr [reg+0x8]` の直接形は 0 件。
- **0x12ab520 は VMT 推定を否定**。公開表にも VMT にも無い。唯一の qword 参照 (0x127a2bb) は 8 バイト未整列で、全 VMT (3530 件) の整列 (8 バイト) に合わない。
- 残り (rdx の出どころ・0x1021670 の呼出し元と [rbp+0x30]・r9 の出どころ) は子 issue へ移した (#3901・#3902・#3903)。呼出し元の確定は本 PR の範囲外。

## 0 対象と前提

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` の実在を確認 → `--wildcards '*block00031_PE.bin'` で `$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin` に展開 (2.8 秒)。
- 検証起点 commit: `58ed035cf` (origin/main)。測定 commit: `ee0073017` (コードを変えた最後の commit)。
- 照合はバイト列の判定だけで、命令境界に依存しない。判定式:
  - 公開表エントリ: `[Len: word][Code: qword][Name: ShortString]`、Len = 2 + 8 + (1 + 名前長)。Code は .text 内、Name は印字可能 ASCII。表先頭は Count word (先頭エントリの 2 バイト前)。
  - VMT: `[VMT-0xc8] == VMT` (自己ポインタ) かつ `[VMT-0x88]` が ShortString へのポインタ (`pe_vmt_probe.py`・PY-72 と同じ判定)。

## 1. 公開メソッド表 (0x12acb70・0x12ac210・0x12ab710)

スクリプト: `tools/python/analysis/flapi/pe_py220_methods.py` (.text を 1 バイトずつ走査)。

| 関数 VA | 公開表エントリ | 名前 | Len (16 進) | 名前長 |
|---|---|---|---|---|
| 0x12acb70 | 0x127956f | MoveLeftMenuClick | 0x1c | 17 |
| 0x12ac210 | 0x1279c33 | TracksPanelMMouseWheel | 0x21 | 22 |
| 0x12ab710 | 0x1279614 | FormMouseWheel | 0x19 | 14 |

- 公開表エントリ候補は .text 全体で 2766 件。Len で連結すると鎖は 104 本 (長さ 2 以上)。**全 104 本で Count = 鎖の長さ** (104/104)。
- 3 件の表先頭はすべて 0x12793f5 (Count 120)。表ポインタは 0x1277ea0 (値 = 表先頭 − 2 = 0x12793f3)。所属 VMT は 0x1277f38 (TFXForm、表ポインタの位置 VMT-0x98)。
- 負の対照: Len を 1 バイトずらした判定では候補 0 件 (2766 → 0)。

## 2. 0x12ab520: VMT 推定の検証

| 判定 | 結果 |
|---|---|
| 公開表のエントリ (Code == 0x12ab520) | 0 件 |
| qword 参照 (.text 全体) | 1 件、VA 0x127a2bb、mod 8 = 3 |
| 参照の直後 | ShortString `TFXForm` (PY-203 §1 の記述どおり) |
| VMT の後方候補 (VMT + 8i、i < 0x400) | 0 件 |
| 全 VMT の整列 (自己ポインタ判定 3530 件) | 3530/3530 が 8 バイト整列 |

- 結論: 0x127a2bb は VMT のスロットではない (VMT のスロットは 8 バイト整列の VMT から 8i の位置にある)。**VMT 推定は否定**。
- 観測 (推定。命令境界は未確定): 0x127a2ba から前向きに復号すると `add eax, 0x12ab520` と読める。0x12ab520 を読む命令は本 probe では見つかっていない (即値参照 0 件・PY-203 probe)。参照経路 (データ島か命令か) は #3901 で確定する。

## 3. 0x1021670: VMT スロット 1 (呼出し元は未確定)

- qword 参照 1 件 (VA 0x1012f48 = VMT 0x1012f40 + 8、スロット 1)。最近の VMT 候補は 0x1012f40 (vmtClassName = `TUndoEvent_MovedFXTracks`)。
- `pe_vmt_probe.py 0x1012f40 0x1012f48 --disp 8`: `call qword ptr [reg+0x8]` (仮想スロット 1 の直接呼出し) **0 件**。VMT の値を持つ slot は 2 件 (0x1012e78・0x1012f9a)、それを RIP 相対で読む命令は 1 件 (0x101ca74 `mov rcx, qword ptr [rip - 0x9c03]`)。
- 呼出し元は `mov reg, [reg+8]` → `call reg` などの経路とみられる (推定)。未確定 → #3902。

## 4. 検証

- 実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/pe_py220_methods.py` → **11/11 PASS・終了 0** (n=3)。
- 所要: 14.96・15.08・15.12 秒。load average (1 分): 0.19・0.43・0.56 (4 コア)。
- 検証範囲: .text の公開表と VMT の判定 (バイト列)。範囲外: 0x12acb70・0x12ac210・0x12ab710 の呼出し元 (発火側の rdx・r9)、0x1021670 の呼出し元、[rbp+0x30] (#3901・#3902・#3903)。
- 負の対照・陽性対照: Len の 1 バイトずらし → 候補 0 件 (2766 → 0)。既知の VMT TPublicChannel (0xfe2cf8) のスロット 35 (0xfe2e10) は同じ判定で VMT 0xfe2cf8 と一致する (陽性)。
- 測定 commit 以降の差分 (probe の範囲): `git diff ee0073017 HEAD -- tools/python/analysis/flapi` は 0 行。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x12acb70 と 0x12ab520 の rdx (第 2 引数) の出どころ。0x12ab520 の参照経路 (0x127a2bb の読出し命令の有無) | 受入 1 の rdx 2 件 | #3901 (PY-268) |
| 0x1021670 (VMT スロット 1) の呼出し元と [rbp+0x30] (0x45c290 の引数) の所属 | 受入 2 の残り | #3902 (PY-269) |
| 0x12ac210 の第 4 引数 r9 (WheelDelta と推定) の出どころ。推定の検証 | 受入 3 | #3903 (PY-270) |
