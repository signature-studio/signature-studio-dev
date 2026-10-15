# REPORT_PY72 の付録 (#3440): 通知 0x550・0x562 の受け手 (Delphi の動的メッセージ表) と窓生成の由来

既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセ・データ構造の解析)。親: #3214 (PY-171)。本 issue #3440 (PY-197) は、親 #3214 の受入 3 (送信元と hwnd) を達成した後に残った 2 件を扱う: (1) msg 0x550・0x562 の受け手 (window proc の分岐先)、(2) `obj+0x1d0` (窓生成) の由来。部分達成のため `Refs #3440` とし、未解決は本文の表に起票先 (#3440 に残す) を付けた。

## 結論

- 分岐先は**動的メッセージ表 (DMT)** で確定した。0x550 は `TPluginForm` の DMT (idx 4) → ハンドラ `0xf6d160`。0x562 は `TFruityLoopsMainForm` の DMT (idx 12) → ハンドラ `0x11d18d0`。親 #3214 の「即値比較に無い」は、Delphi の `message` ハンドラが DMT (データ) に置かれるためと説明できる。
- ただし「hwnd `[obj+0x45c]` の窓プロシージャから Dispatch に届く経路」と「`obj` の実体クラス」は PE 上で確定できない (理由は節 3)。よって受入 1 は部分達成。`0x40ff70` は祖先鎖を辿るので、実体クラスが `TPluginForm` (0x550) / `TFruityLoopsMainForm` (0x562) の子孫のときも分岐先に届く。
- `obj+0x1d0` の由来は、**クラスごとの VMT slot の解決先**まで確定した (節 4)。窓生成の本体は `0x612190` → `0x85fa90` → `CreateWindowExW`。`TFruityLoopsMainForm` だけは `0x612190` → `0x11d10d0` → `0x85fa90` (`0x11d10d0` は後処理で WM_SETICON を送る)。hwnd `[obj+0x45c]` を格納する箇所 (`0x611d0e`) も PE 箇所つきで確定した。hwnd を作る呼出し経路 (3 件の候補) のどれが WP フォームに当たるかは未確定。
- 部分達成。未解決は節 6 の表 (起票先は本 issue #3440 に残す。解析のみの残りのため子 issue は起票しない)。

## 測定

- 測定 commit: `e2fdc6643` (`pe_dmt_scan.py` の `--chain` で VMT の表の外の slot を出さないようにした commit。コードを変えた最後の commit)。以降の commit は本ファイル・`tools/python/REPORT_PY72.md`・`docs/DOC_MAP.md` だけを変える。差分 0 の証跡は節 5。
- 素材: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> extracted/block00031_PE.bin` (`$ARTIFACTS_DIR/fl-win64.tar.zst` の実在を確認してから展開。repo 外)。
- 実行: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_dmt_scan.py 550 562 --chain f55f48` を n=3。3 回とも終了 0・出力の md5 が一致 (`18daa4abd3084760de2a5789da2c8743`)。msg 行・件数は修正前と同じで、変わったのは `--chain` の slot 値の表示のみ。

| 実行 | 所要 (秒) | load (1 分値) |
|---|---|---|
| 1 | 0.216 | 0.15 |
| 2 | 0.207 | 0.15 |
| 3 | 0.208 | 0.15 |

- 名前付き VMT 3449 件 (自己参照スロット `[VMT-0xc8]==VMT` と、`VMT-0x88` の ShortString の両方を満たすもの)。うち DMT 非 nil は 179 件。
- ポジティブ対照: `pe_dmt_scan.py 201` (WM_LBUTTONDOWN) は 6 件 (`TControl` (VMT `0x5fa8d8`・DMT `0x5fb68a`・idx 0・`0x60cfc0`)・`TCustomComboBox`・`TQuickToolBar` など) で命中 (終了 0)。
- ネガティブ対照: `pe_dmt_scan.py 7777` は 0 件 (DMT に無い ID)。なお 0x551 は `TPluginForm` の DMT に有る (idx 9・`0xf69bf0`) ため、対照には使わなかった。

## 1. Delphi x64 の VMT 負オフセット (PE で確認)

`TPublicChannel` (VMT `0xfe2cf8`) で確認: `[VMT-0xc8]=0xfe2cf8` (SelfPtr)・`[VMT-0x88]=0xfe2eae` (ClassName の ShortString)・`[VMT-0x80]=0x8a8` (InstanceSize)・`[VMT-0x90]=0` (DynamicTable が nil。自身の動的メッセージは無い)・`[VMT-0x78]=0xfe28b0` (Parent。親 VMT への**ポインタの番地**で、`[0xfe28b0]` が親の VMT)。

| 負オフセット | 項目 | 用途 |
|---|---|---|
| `-0x90` | vmtDynamicTable | DMT のポインタ (0 なら自クラスに動的メッセージ無し) |
| `-0x88` | vmtClassName | ShortString へのポインタ |
| `-0x78` | vmtParent | 親 VMT へのポインタの番地 (一段デリファレンス) |

## 2. DMT の形式と検索 (PE 箇所つき)

- 形式 (`TControl` の DMT `0x5fb68a` で実測): `Word count` (85)、続けて `Word msgid[count]` (`0x201`・`0xa1`・…)、続けて `QWORD handler[count]` (絶対 VA `0x60cfc0`・…)。ハンドラは `DMT+2+2*count+8*idx`。
- 検索関数 `0x40ff70` (`pe_disasm.py 0x40ff70` で確認): 引数 `rcx` の VMT から `mov rcx,[rax-0x90]` (DMT) を読み、`movzx r10d, word [rcx]` (count)、`cmp word [rcx+r9*2+2], dx` (msgid の線形探索)、`lea rax,[rcx+rax+2]` + `mov rax,[rax+r8]` (handler) の形。DMT が 0 の場合と見つからない場合は、`mov rax,[rax-0x78]` (`0x40ffcb`) で親 VMT へ進み (`jmp 0x40ff73` (`0x40ffd7`))、親が無ければ 0 を返す (`0x40ffd9`)。つまり引数の VMT の**祖先鎖を、近い DMT から順に全部見る**。
- 受信側 `TObject.Dispatch` 相当 `0x410090` (`pe_disasm.py 0x410090` で確認): `movzx rax, word [rdx]` (TMessage.Msg) が `1 ≤ msg < 0xc000` のとき `0x40ff70(rcx=[rbx])` (**obj の VMT** を渡す。祖先鎖を辿る) を引き、見つかれば `handler(obj, msg)` (`0x4100d1`)。見つからなければ `call [vmt-0x38]` (DefaultHandler。`0x4100df`)。`0x40ff70` の直接呼出し元は `0x410090` (`0x4100b8`) と `0x40ffe0` (`0x40ffe8`)。
- `0x40ffe0` (`pe_disasm.py 0x40ffe0` で確認): `mov rcx,[rcx]` で引数を一段デリファレンス (引数はオブジェクトのアドレス) してから `0x40ff70` を呼ぶラッパー。結果が 0 なら `0x40c820` を呼ぶ。祖先を辿るのは `0x40ff70` 側で、`0x40ffe0` 自体は辿らない。呼出し元は未調査 (節 6)。
- DMT を持つ名前付き VMT (179 件) の全走査 (`pe_dmt_scan.py 550 562`): 0x550 を持つのは `TPluginForm` (VMT `0xf55f48`) だけ。0x562 を持つのは `TFruityLoopsMainForm` (VMT `0x1167ea0`) だけ。

## 3. 受け手 (受入 1)

| msg | 受け手クラス (VMT) | DMT (idx/count) | ハンドラ VA |
|---|---|---|---|
| 0x550 | `TPluginForm` (`0xf55f48`) | `0xf58d88` (4/10) | `0xf6d160` |
| 0x562 | `TFruityLoopsMainForm` (`0x1167ea0`) | `0x117409f` (12/42) | `0x11d18d0` |

- `TPluginForm` の DMT 全 10 件: `0x54d`→`0xf5a640`・`0x54e`→`0xf5a660`・`0x57f`→`0xf5a8b0`・`0x54f`→`0xf5a6b0`・**`0x550`→`0xf6d160`**・`0x553`→`0xf6d260`・`0x554`→`0xf6d270`・`0x2e0`→`0xf5a770`・`0xffc8`→`0xf5ab40`・`0x551`→`0xf69bf0`。プラグイン窓が `WM_USER+0x14d`〜`0x154` を個別に受けていて、0x550 はその一つ。
- 祖先鎖 (`pe_dmt_scan.py --chain f55f48`): `TPluginForm` → `TChildVectorForm` (`0x803168`) → `TVectorForm` (`0x802bf0`) → `TUnpaintedWPForm` (`0x801d60`) → `TCustomWPForm` (`0x800d88`) → `TForm` (`0x8512a0`) → `TCustomForm` (`0x84f4b8`) → `TScrollingWinControl` (`0x84cc08`) → `TWinControl` (`0x5fded8`) → `TControl` (`0x5fa8d8`) → `TComponent` (`0x4dd478`) → `TPersistent` (`0x4cba08`) → `TObject` (`0x401a38`)。祖先の DMT に 0x550・0x562 は無い (全 179 件の走査)。
- `TFruityLoopsMainForm` の鎖: `TVectorForm` → `TUnpaintedWPForm` → `TCustomWPForm` → (以下同じ)。
- **送信元の対応**: 0x550 は `0xd5a9ad` (`mov edx,0x550`)・`0xd5a9c0` (`call 0x425210` = PostMessageW)。hwnd は `0x617920(rbx)`、rbx は `0x117baa0(chan)` の戻り値。`0x117baa0` は `0x117bafa`・`0x117bb21` で `0x809260` を呼んで rbx に取る。`0x809260` は、リストの要素のうち `0x40fe90` (is-kind-of 判定) で `TCustomWPForm` (VMT `0x800d88`) に当たり、かつ `[item+0x4c5]≠0` の最初の要素を返す (判定の VMT は `0x80929b` の `rip-0x85e2` = スロット `0x800cc0` の値 `0x800d88`、つまり自己ポインタの読出し)。
- 0x562 は `0xd84498` (`mov edx,0x562`)。hwnd は `0x617920(obj)`、obj は `*(*(0x15e0ff8))` (`0xd84486`〜)。`0x15e0ff8` は `.data` 上の値で、PE 内の直接 store は 0 件 (`pe_xref.py 15e0ff8`: stores=0・loads=1077)。

### 未確定の部分 (受入 1 の残り)

- 0x550: `0x809260` は `TCustomWPForm` 系の要素を返すが、要素の実体クラスは実行時の値。`0x40ff70` は実体の VMT から祖先鎖を辿るので、実体クラスが `TPluginForm` 自身、またはその子孫 (祖先鎖に `TPluginForm` (VMT `0xf55f48`) を含むクラス) のとき `0xf6d160` に届く。0x550 を DMT に持つのは `TPluginForm` だけなので、祖先鎖の途中で別のクラスが先に当たることは無い。祖先鎖に `TPluginForm` を含まない WP フォームは 0 を返し、既定経路 (DefaultHandler) に進む。
- 0x562: `obj` の実体は `0x15e0ff8` の実行時値。実体クラスが `TFruityLoopsMainForm` (VMT `0x1167ea0`)、またはその子孫 (祖先鎖に `0x1167ea0` を含むクラス) のとき `0x11d18d0` に届く。PE だけでは実体を確定できない。
- **hwnd から Dispatch への経路が未確定**: hwnd `[obj+0x45c]` の窓の WndProc が、どこで `0x410090` を呼ぶかは確認できなかった。確認できた範囲は次の 2 点:
  - (a) 窓プロシージャ候補 `0x85d170` (WP フォーム系の `[vtbl+0x288]`。先頭で WM_PAINT(0x0f)・WM_ERASEBKGND(0x14) 等を個別に分岐する) は、表に無い msg (0x550・0x562 を含む) を既定経路 `0x85d3d1` → `0x85d0a0` に流す。`0x85d0a0` は `CallWindowProcW([obj+0x520], [obj+0x65c], msg, wParam, lParam)` (`0x85d0ed`・IAT `0x1971060`)。つまりこの WndProc は DMT を引かずに元のプロシージャへ渡す。`0x85d170` が表の内であることは節 6 に記す。
  - (b) `0x85d170` が差し替えるのは子窓 `[obj+0x65c]` (節 4)。0x550・0x562 は親窓 `[obj+0x45c]` に投函されるので、この WndProc は通らない。
  - 親窓 `[obj+0x45c]` の WndProc は、`0x611c70` (`0x611d09`) の窓クラス (`TCreateParams` の `WinClassName`、`lea rdx,[rax+0x78]`) による。この PE 上の範囲では WndProc の設定が見えない (`0x6118a0` の `SetWindowLongPtrW` `0x611a8b` は `GWL_ID` (-12) で WndProc ではない)。

## 4. 窓生成の由来 (受入 2)

- 呼出し点: `0x6178e0(obj)` (`pe_disasm.py 0x6178e0`): `cmp [obj+0x45c],0`・`jne` (既に有れば戻る)。`[obj+0x78]` (親) が非 0 なら `0x6178e0(parent)` を先に呼ぶ。続けて `mov rbx,[rbx]` (vtable) と `call [rbx+0x1d0]` (`0x617909`) で窓を作る。`0x617920(obj)` は `0x6178e0` の後に `[obj+0x45c]` を返す (`0x617930`)。
- slot `+0x1d0` の解決先 (VMT の値、`pe_dmt_scan.py --chain`):

| クラス (VMT) | `+0x1d0` | 関数の役割 |
|---|---|---|
| `TPluginForm` (`0xf55f48`)・`TFruityLoopsMainForm` (`0x1167ea0`)・`TChildVectorForm` (`0x803168`)・`TVectorForm` (`0x802bf0`) | `0x80a2b0` | `call 0x612190` (`0x80a2bb`) で継承の窓生成を呼んだ後、`call [rbx+0x300]` (`0x80a2d5`) |
| `TUnpaintedWPForm` (`0x801d60`)・`TCustomWPForm` (`0x800d88`)・`TForm`・`TCustomForm`・`TScrollingWinControl`・`TWinControl` | `0x612190` | `TWinControl` 系の窓生成 (下記) |

- `0x612190` (`pe_disasm.py 0x612190`): `cmp [rbx+0x45c],0`・`jne 0x61225d` (作成済みなら戻る)。未作成なら `mov rsi,[rbx]` と `call [rsi+0x1e8]` (`0x6121ae`) で仮想の窓作成を呼び、続けて `SetPropW` (`0x4254a0`)・`SetWindowPos` (`0x425520`) を呼ぶ。
- `[vtbl+0x1e8]`: `TCustomForm` 系 (`TCustomForm`・`TForm`・`TCustomWPForm`・`TUnpaintedWPForm`・`TVectorForm`・`TChildVectorForm`・`TPluginForm`) は `0x85fa90`。`TFruityLoopsMainForm` (`0x1167ea0`) は `0x11d10d0` (次の項)。`TWinControl` は `0x6118a0`・`TScrollingWinControl` は `0x859bd0`。
- `0x85fa90` (フォーム版): 親 `0x617920(obj)` (`0x85fb17`) を得て `CreateWindowExW` (`0x85fb6c`・IAT `0x1970db8`) を呼び、結果を `[obj+0x65c]` に格納 (`0x85fb71`)。続けて `GetWindowLongPtrW(hwnd65c, GWL_WNDPROC)` (`0x85fba9`) → `[obj+0x520]`、`SetWindowLongPtrW(hwnd65c, GWL_WNDPROC, [obj+0x664])` (`0x85fbce`)。`[obj+0x664]` は `0x8586c0` の戻り値で、引数は `[vtbl+0x288]` を code とする TMethod (`0x85fb7c`〜`0x85fb8e`)。
- `0x11d10d0` (`pe_disasm.py 0x11d10d0`・TFruityLoopsMainForm の `[vtbl+0x1e8]`): `call 0x85fa90` (`0x11d10db`) で `[obj+0x65c]` の窓を作らせた後、`call 0x617920(obj)` (`0x11d10e3`) で親窓 `[obj+0x45c]` を得て rbx に取る。続けて `call 0x5cfff0` (`0x11d10fc`) の戻り値を r9 に、`call 0x425390` (IAT = `user32!SendMessageW`) を `edx=0x80` (WM_SETICON)・`r8d=1` (ICON_BIG) で呼ぶ。よって 0x562 の窓生成は `0x80a2b0` → `0x612190` → `0x11d10d0` → `0x85fa90` の順。`0x5cfff0` の内部 (`0x5d0090` 以下) と戻り値の由来は未確認 (節 6)。
- hwnd `[obj+0x45c]` の格納: `0x611c70` の `CreateWindowExW` (`0x611d09`) の直後 `mov [rbx+0x45c], rax` (`0x611d0e`)。`0x611c70` の直接呼出し元は `0x631510` (`0x63155f`・`0x63158e`)・`0x825040` (`0x82504b`)・`0x85fd20` (`0x85fe9e`)。WP フォームの経路でどれが実行されるかは未確定 (節 6)。

## 5. 差分と検証範囲

- 検証範囲: 逆アセと PE データ構造 (VMT・DMT・IAT) の静的解析。実行時のクラス・hwnd の値は範囲外。
- ツール: `analysis/flapi/pe_dmt_scan.py` (本 PR で追加。`e2fdc6643` で `--chain` の表の境界を直した)。`pe_disasm.py`・`pe_xref.py`・`pe_callgraph.py` は既存版を使用 (無変更)。
- `--chain` の表の長さ: VMT の長さは PE に無いため、先頭から連続する `.text` を指す QWORD の本数を表の長さとみなす (近似)。表の外の slot は値を出さず `(表の外)` と印字する。`TObject` (`0x401a38`) は先頭 slot が `.text` を指さず 0 本と判定される (表の外扱い。判定には使っていない)。
- KPI: 解析のみで起動・GUI の変更は無いため、KPI の前後は対象外。
- 差分: `git diff e2fdc6643 HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力は 0 行。

## 6. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| hwnd `[obj+0x45c]` の窓の WndProc と、`0x410090` (Dispatch) に届く経路 | 0x550・0x562 が DMT に届く条件 (受入 1 の残り) | #3440 (本 issue に残す。解析の残りのため子は起票しない) |
| `obj` の実体クラス (0x550: `0x809260` の戻り値、0x562: `*(*(0x15e0ff8))`) | DMT の分岐先が `0xf6d160`・`0x11d18d0` になるかの条件 (祖先鎖に `TPluginForm`・`TFruityLoopsMainForm` を含むか) | #3440 |
| WP フォームの hwnd `[obj+0x45c]` を作る呼出し経路 (`0x611c70` の 3 件の呼出し元のどれか) | 受入 2 の残り (窓生成の確定) | #3440 |
| `0x85d170` が hwnd `[obj+0x45c]` の窓プロシージャとして使われるか。表の内は確認済み (`--chain`: `TCustomForm`・`TForm`・`TCustomWPForm`・`TUnpaintedWPForm`・`TVectorForm`・`TChildVectorForm`・`TPluginForm` の slot 0x288。`TWinControl`・`TScrollingWinControl` では表の外) | 窓プロシージャ候補の確定 | #3440 |
| `0x11d10d0` の後半: `0x5cfff0` (`0x11d10fc`) の内部 (`0x5d0090` 以下) と戻り値 | 0x562 の窓生成の後処理 (WM_SETICON に渡す値の由来) | #3440 |
| `0x40ffe0` (一段デリファレンスして `0x40ff70` を呼ぶラッパー) の呼出し元 | `0x410090` は `0x40ff70` を直接呼ぶ。`0x40ffe0` の呼出し元が 0x550・0x562 の経路か未調査 (`pe_xref.py` は RIP 相対参照だけを列挙するため、`call rel32` の走査が要る) | #3440 |
