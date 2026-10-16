# tools/python REPORT: PY-5350 plugins.getName の PE 意味論 (#5488, 親 #5106・#4861)

親: #5106 (plugins 残り関数の実装) の子。兄弟: #5489 (plugins.getPadInfo)。`device.getName` (#3569・#4663) とは別の関数。

## 結論

1. **引数は確定**: `plugins.getName` (`0xd80d60`) は `i|iiii`、kwlist `index, slotIndex, flag, paramIndex, useGlobalIndex`。既定値は slotIndex = -1・flag = 0・paramIndex = -1・useGlobalIndex = 0。(§1)
2. **解決順は確定**: `slotIndex == -1` は channel (`0x1005730`) を解決し、有効性 `0x132f780` が偽なら code -8。`slotIndex != -1` は mixer 件数 `[0x15e2198]` で index を、slot ≤ 9 で slot を検査する。範囲外は code -4 (文言 `Index out of range`)。PY-228 (`getParamValueString`) と同じ並び。(§2)
3. **戻りの経路は確定、中身は未確定**: `flag == 6` (`midi.FPN_Preset`) と それ以外で経路が分かれ、どちらも最後は `0xc3cfa0` で文字列化する。文字列の**中身** (何の名前か) は、plugin の vtable 先を読むまで確定していない。(§3)
4. **受入条件 1 は部分達成**: 引数・解決順・戻りの経路は確定したが、戻り値の中身は未確定。未確定の点は §4 に「未確認」と明記した。推測による実装はしていない (親 #5106 の受入 4)。

## 測定

| 項目 | 値 |
|---|---|
| 測定 commit (コードを最後に変えた commit) | `23f286181` (検査スクリプトに呼出し経路 4 件を assert として追加) |
| 素材 | `[WIN64]` (`fl-win64.tar.zst`) から `block00031_PE.bin`・`block24429_DATA.bin` (midi.py)・`block24430_DATA.bin` (utils.py)・`block25159_DATA.bin` を展開 (展開先は `FL_WIN64_DIR/extracted`)。`tar --zstd --wildcards` で real 2.642 s (1 回目は `block_manifest.json` が無く警告のみ) |
| 検査 | `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/plugins_getname_facts.py` → 27 項目 PASS・FAIL 0・rc 0 (`23f286181` で実行) |
| 逆アセンブル | capstone 5.0.7。`0xd80d60`〜`0xd81127` (約 220 命令)。補助関数 `0x12b69b0`・`0x1331340`・`0x41a7b0`・`0xc3cfa0`・`0x413a60`・`0x41c650`・`0x414200`・`0x43c870` を読んだ |
| load | 測定時の load average は 1 未満 (4 core) |

差分確認: 検査の対象 (`analysis/flapi/plugins_getname_facts.py`・`analysis/flapi/flapi_kwargs.json`) は `git diff 23f286181 HEAD -- tools/python/analysis/flapi/plugins_getname_facts.py tools/python/analysis/flapi/flapi_kwargs.json` が 0 行で、測定 commit から変わっていない。本 REPORT の文言修正 (docs のみ) は測定 commit より後の commit に入る。入力の bin は素材 (`fl-win64`) 由来で git の管理対象外。

## 1. 引数 (確定)

| 項目 | 根拠 (VA・出所) |
|---|---|
| fmt `i\|iiii` | `0xd8117c` の文字列 (ASCII) と `0xd80d60` の PyArg 解析 (`call [rip+0x863766]`, `0xd80e3b`〜`0xd80e42`)。`analysis/flapi/flapi_kwargs.json` と一致 |
| kwlist `index, slotIndex, flag, paramIndex, useGlobalIndex` | `flapi_kwargs.json` (`fn_va: 0xd80d60`)。PE 上の kwlist 文字列は本 REPORT では読んでいない (出所は JSON) |
| 既定値 | `0xd80dba` (slotIndex = `0xffffffff`)、`0xd80dc4` (flag = 0)、`0xd80dce` (paramIndex = `0xffffffff`)、`0xd80ddf` (useGlobalIndex = 0) |
| 必須 | `required: 1`・`max: 5` (`flapi_kwargs.json`)。index のみ必須 |

## 2. 解決順 (確定)

| 順 | 判定 (VA) | 範囲外・空 |
|---|---|---|
| 1 | `slotIndex == -1` (`0xd80e52`〜`0xd80e59`) → channel 経路 (`0xd80e5f`〜)。`!= -1` → slot 経路 (`0xd80f89`〜) | — |
| 2 (channel) | `0x1005730(index, dl = useGlobalIndex > 0, &obj)` (`0xd80e7d`。`dl` は `0xd80e73` の `setg`)。偽なら失敗 (`0xd810d6`) | code -4 (文言 `Index out of range`, `0xd82e8c`) |
| 3 (channel) | `0x132f780(obj)` = `[obj+0x64] >= 0` (`0xd80e91`)。偽なら `0xd80f7d` | code -8 (文言 `Plugin not valid`, `0xd82f3c`) |
| 2 (slot) | `0 ≤ index ≤ [0x15e2198]-1` (`0xd80fa0`〜`0xd80faf`)。`[0x15e2198]` は mixer 件数 (PY-228 と同じ変数) | code -4 |
| 3 (slot) | `0 ≤ slotIndex ≤ 9` (`0xd80fc8`〜`0xd80fcc`) | code -4 |
| 4 (slot) | obj = `[mixer配列 + index*0x28f*8 + slot*8 + 0x134c]` (`0xd80fd2`〜`0xd80ff2`)。`0x132f780(obj)` (`0xd8101e`) | 偽なら code -8 (`0xd810cf`) |

- code -4 / -8 の Python 側の値 (4 / 8) への変換は PY-228 の既存対応を引き継いだ。本 issue では `0xd82c20` の戻り値を確かめていない (未確認)。
- slot 経路は `0x132f780` より前に obj の NULL 判定が無い (`0xd80ffd` で `0x1331340(obj)` が `[obj+0x38]` を読む)。NULL のときの挙動は未確認。
- **paramIndex の範囲検査は getName 本体には無い** (PY-228 の getParamValueString と違う点)。`flag != 6` では負の paramIndex を 0 に丸める (`0xd80f01`〜`0xd80f0a`) だけで、件数との比較は無い。件数以上のときの挙動は未確認 (§4)。

## 3. 戻りの経路 (確定) と中身 (未確定)

戻りは `[rbp+0x68]`。失敗時は `0xd82c20(code)` の戻り値をそのまま返す (`0xd810d8`・`0xd810dd`)。

経路は flag で分かれ、channel と slot は後半 (`0xd80edc`・`0xd81036`〜) で同じ形を取る:

| flag | 経路 (VA) | 文字列化 |
|---|---|---|
| `== 6` (`midi.FPN_Preset` = 6・`block24429` midi.py で確認) | `0x12b69b0(obj, &[rbp+0xb0], paramIndex)` (`0xd80efa`・`0xd81055`) が `[rbp+0xb0]` を書く | `0xc3cfa0([rbp+0xb0])` (`0xd80f6f`・`0xd810c4`) |
| `!= 6` | `obj.vtable[+0x20](obj, flag, paramIndex, 0, &buf)` (`0xd80f36`・`0xd81091`)。`buf` = `[rbp+0xbc]`。plugin が `buf` に書く | `0x413a60(&[rbp+0x80], &buf, 0x1000)` (`0xd80f50`) → `0x41c650(&[rbp+0xb0], [rbp+0x80])` (`0xd80f63`) → `0xc3cfa0([rbp+0xb0])` (`0xd80f6f`)。`0x413a60` は長さ上限 0x1000 の文字列読み、`0x41c650` は代入と読める (推定。関数名は付いていない) |

- `0xc3cfa0` は `0x414200` へ **定数 `0xfde9` (= 65001 = UTF-8)** を渡す (`0xc3cfbd`)。その後 `0x414000` と、`[rip+0xa7b2e7]` (= `0x16b82c0`) の間接呼出し (`0xc3cfd3`) で Python 側の値にする。間接呼出し先は import table に無く、ファイル上の値は `0x2000000000000000` で、実行時に埋まる。**Python 側の最終的な型は未確認**。
- 戻りの型は C 表 `tools/python/provider/gen/fl_table.c` の `{"plugins", "getName", 's', 5, 1, "iiiib", ...}` (戻り型 `'s'`) と一致する。

`0x12b69b0` (flag == 6 の本体) の確定分:
- `paramIndex == -1` のとき `obj[+0xc0] >= 0` なら、その値を paramIndex に使う (`0x12b6a03`〜`0x12b6a22`)。それ以外は -1 のまま。
- `obj[+0x94]` の vtable `+0x28` の戻り値 (件数と読める。推定) と paramIndex を比べ、paramIndex < 件数 なら `+0x18` と `0x43c870` で名前を取る (`0x12b6a9a`〜`0x12b6ad1`)。以上なら `0x511fe0` の経路 (`0x12b6aff`) へ。

## 4. 未確認 (推測で実装していない)

| 未確認の点 | 影響 | 扱い |
|---|---|---|
| `flag != 6` で plugin の vtable `+0x20` が `buf` に書く名前の意味 | 戻り値の中身が決まらない。C・mock の文字列を置けない | #5529 (PY-5355)。`obj` の vtable 先 (`[rax+0x20]` の実体) を PE で読む |
| `flag == 6` の `0x12b69b0` が書く名前の意味 (プリセット名か) | 同上 | 同上 |
| `flag` の値 1〜5 と 7 以上の意味 | 戻りの中身 | 同上 (`midi.py` の `FPN_*` 定数と照合) |
| `0xc3cfa0` の末尾の間接呼出し先 (Python 側の型・生成関数) | 戻り値の Python 型 | 未確認 (C で型を決めるときに確定) |
| `paramIndex` が件数以上・負のとき (flag != 6 の vtable・`0x511fe0`) | 範囲外の code と値 | 未確認 |
| slot 経路で obj が NULL のとき | 未確認 | 未確認 |
| 引数解析失敗時の code (`0xd80e4c`・PyArg の戻り値を `esi` に入れて `0xd82c20` へ) | 不正引数の code | 未確認 |
| code -4 / -8 の Python 側の値 (4 / 8) と `0xd82c20` の戻り値 | 例外の型と値 | PY-228 の対応を引き継ぐ。未確認 |

### 4.1 PY-5361 (#5490) の追記: getColor の呼出し形 (PE 確認・検査 `analysis/flapi/plugins_getcolor_facts.py`)

- `plugins.getColor` (0xd80a40) の値式は 2 箇所 (`0xd80b8d`・`0xd80c8c`) で同じ形を取る: `0x1331340(obj 取得, [rbp+0x78])` → `[rbp+0x78]` の `vtable[+0x20]` (`0xd80b5a`) → 得た obj に対し `obj.vtable[+8](obj, 0x21, [rbp+0xa4] (= flag), [rbp+0xa0] (= paramIndex))`。
- 戻り値 `eax` は BGR→RGB 入替え (`0xff00ff`・`0xff00ff00`) の後に `[rip+0x8636ce]` の関数へ渡る (`0xd80bab`)。alpha の付与は見えない。
- 経路の分岐 (PE 確認・検査 19 件 PASS): `slotIndex == -1` (channel) は `0x1005730(index, dl, &obj)` で obj を得て、`0x132f780(obj)` = `[obj+0x64] >= 0` で有効性を見る (`0xd80b27`〜`0xd80b3d`)。slot 経路は `obj = [mixer配列 + index*0x28f*8 + slot*8 + 0x134c]` で得て、同じく `0x132f780` で見る (`0xd80c12`〜`0xd80c65`)。`0x1005730` の obj の取り方は `0xfe8bb0(array, index)` の戻り値 (`[array+8][index]`、範囲外は NULL。`0xfe8bb0`〜`0xfe8bd5`)。配列の要素型は、この関数の呼出し元と格納元 (未追跡) で決まるため未同定。
- 訂正 (PY-5361 #5490・本 run): 前 run までの「`0xd80b40` で `ecx = [rbp+0x90]` (32 bit)」は誤読。`0xd80b40` は命令の途中で、正しい開始は `0xd80b3f` の `mov rcx, qword ptr [rbp+0x90]` (64 bit)。検査の開始位置も `0xd80b3f` に直した。
- `0x1331340(this, &out)` は `[this+0x38]` が非 NULL なら `&([this+0x38]+0x48)`、NULL なら NULL を out へ代入する。out が NULL のままなら `[rip+0x63d9c6]` の値で代入し直す (`0x1331362`〜`0x1331372`)。代入は `0x41a7b0` (新値 AddRef・旧値 Release) (`0x1331340`〜`0x133137f`・`0x41a7b0`〜`0x41a7f4`)。
- **未確認 (受入 1 の未達)**: `vtable[+8]` の先の VA。obj の class (vtable) は、`[this+0x38]` の書込み元 (コンストラクタ・代入箇所) で決まるため、この run では未同定。ID `0x21` の意味。flag・paramIndex の意味。`[rip+0x8636ce]` の関数の名前。

## 5. C・mock への影響

- 本 issue では C provider と mock を変えていない (受入の実装は親 #5106 の範囲)。
- #5106 で実装するときの前提: 解決順 (§2) と経路の分岐 (§3) は確定。**戻り値の中身は未確認**なので、§4 の 1 と 2 を確定させてから名前を実装する。推測で名前を置かない。

## 6. PY-5355 (#5529) の追記: 戻り値の中身を決める経路の PE 上の確認

戻り値の文字列の中身を決める経路を、`0x12b69b0` (flag == 6) と `0xd80f36` (flag != 6) について機械語で確かめた。結論は「中身は静的な PE だけでは確定できない」。

- **flag == 6 (`0x12b69b0`)**: `0x1331340` (`0x12b6a2c`) で sub-object の参照を得て、その vtable `+0x20` を `edx = 6` で呼ぶ (`0x12b6a3c`・`0x12b6a56`・`0x12b6a71`)。戻る名前は `0x413a60` (`0x12b6a88`、長さ上限 0x1000) で読み、`0x41c650` (`0x12b6a95`) で `[rbp+0x60]` に代入する。`0x1331340` は `REPORT_PY163.md` §3・§4 で機械語を読んだ関数と同じ (`[this+0x38]+0x48` を out 引数へ書く)。
- **flag != 6 (`0xd80f36`)**: `obj.vt[+0x20](obj, flag, paramIndex, 0, &buf)` を呼ぶ (§3 の既述)。
- **未確定**: 両経路の `+0x20` の実体は、呼ばれる object の具体的な class (vtable) で決まる。その class は `0x1331340` の `[this+0x38]` の値 (PY163 で未確定) に依存し、PE の静的な読みでは確定しない。よって戻り値の中身 (何の名前か) と flag 1〜5・7 以上の意味は、本 PR では「未確認」のまま。推測で名前を実装しない。
- 検査 (`analysis/flapi/plugins_getname_facts.py`) に、上の呼出し経路 4 件を assert として加えた (27 項目 PASS)。

受入条件 1 (戻り値の中身の確定) は**未達**。残りは §4 の 1・2 (vtable 先の実体と flag の意味) で、親 #5106 が扱う。

## 関連

- `tools/python/analysis/flapi/plugins_getname_facts.py` (本 REPORT の根拠 27 件を assert)
- `tools/python/REPORT_PY228.md` (`getParamValueString`・同じ解決の並び。§2・§3)
- `tools/python/REPORT_PY16.md` (`plugins.getName` の既定値 `midi.FPN_Param`・許可表)
