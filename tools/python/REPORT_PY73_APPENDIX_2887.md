# PY-103 (#2887) 付録: incEventValue の値源 (表挿入・A 経路 getter) の PE 実測

> **正本**: `tools/python/REPORT_PY73.md` §9・§9-6。本付録は #2887 の 1 回目の run の記録 (REPORT_PY73.md が 250 行上限のため分割移動)。

## 結論

- **表挿入 `0x664090` の移動向きを確定**: 間接先 `[0x15e3478]` は `.bss` の関数ポインタ slot `0x15f3470` を指し、その中身は登録名 `ippsMove_8u` (Intel IPP) の関数。`ippsMove_8u(pSrc, pDst, len)` の順で呼ぶため、挿入は **shift-up** (`arr[index+1..count] ← arr[index..count-1]`)。件数 +1 は `0x664119`。
- **A 経路 getter の入口 `0x1331340` を確定**: `ref ← ([item+0x38] ≠ 0 ? [item+0x38]+0x48 : 0)`、0 なら既定オブジェクト `G = [0x196ed38]`。`G` の生成元と `ref` が参照カウント付きインタフェースであることも確定。
- **bit1 の表は未確定**: `sub = ref.vt[+0x20](ref)` の sub のクラス (vptr) と `sub.vt[+8](0x1a, …)` の本体が未読。`0x13315a0` (X の初期化) に vptr の書込みは無い (§3)。
- **lo・hi・cur は本 run で未着手**: switch 本体は #2033 (PY-64)・#2034 (PY-65)。

## 測定

- 測定 commit (コードを変えた最後の commit): `468f23826` (`analysis/flapi/pe_slot_names.py` の docstring 修正)。以後の commit は REPORT・付録・DOC_MAP のみ。
- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` を `$RUNNER_TEMP/fl-win64` に `*block00031_PE.bin` のみ展開 (実測 2.8 秒)。
- 実行 (HEAD `468f23826`、load average 0.07〜0.91):
  - `pe_slot_names.py 15f3468,15f3470,15f3478` → 終了 0・名前 3 件 (`ippsCopy_64s`・`ippsMove_8u`・`ippsMove_16s`)・29.9 秒。
  - ネガティブコントロール `pe_slot_names.py 15f3471` → 名前 0 件・29.6 秒。
  - `pe_xref.py 15f3470` → hits 2・stores 0・62.9 秒 (参照は `0x653c6d` の call と `0x654231` の lea)。
  - 補助: `pe_xref.py 196ed38` → hits 7・stores 0・63.2 秒。`pe_xref.py 15e3478` → hits 62・stores 0・62.7 秒。
  - `pe_disasm.py 664090 30`・`13315a0 60`・`40f9e0 60`・`104d100 30`・`1331340 24` → いずれも終了 0。登録呼出し `654212`・`654231`・`654250` の末尾はいずれも `call 0x653dd0`。
- 検証範囲: PE の逆アセンブルと RIP 参照・登録名の列挙のみ。wasm・mock は未実行 (コード差分 0)。

## 1. 表挿入 `0x664090` (移動向きの確定)

| 段 | VA | 内容 |
|---|---|---|
| 拡張 | `0x6640a1`〜`0x6640a9` | count == cap なら `0x663aa0` で拡張 |
| 退避 | `0x6640b5`〜`0x6640bc` | `rdi ← arr[count]` (空き枠の値を退避) |
| 移動 | `0x6640c3`〜`0x6640ee` | `call [[0x15e3478]]`。引数 `rcx=&arr[index]` (pSrc)・`rdx=&arr[index+1]` (pDst)・`r8d=(count-index)*8` |
| 差し込み | `0x6640f0`〜`0x6640f4` | `arr[index] ← rdi` (退避した旧 `arr[count]`) |
| 生成 | `0x6640f8`〜`0x664115` | `arr[index] == 0` なら `arr[index] ← 0x409410(this+0x20)` |
| 件数 | `0x664119` | `count += 1`。戻り値は `arr[index]` |

- 間接先の確定: `0x6640e7` の `mov rax,[0x15e3478]` の `.data` 値は `0x15f3470` (`.bss` の slot。ファイル上は 0 で、起動時に登録される)。`call [rax]` は `[0x15f3470]` を呼ぶ。
- `[0x15f3470]` は起動時に `0x653dd0` で登録される。登録の並びは `0x654212` (`lea rdx` = slot `0x15f3468`・名前 `ippsCopy_64s`)、`0x654231` (slot `0x15f3470`・`ippsMove_8u`)、`0x654250` (slot `0x15f3478`・`ippsMove_16s`)。
- 登録関数 `0x653dd0` は `(ctx, &slot, &名前, flag)` を受け、名前 (UTF-16LE) を `0x414850` → `0x4235f0` に渡して `*slot` に書く (`0x653e11`)。`pe_xref` は `rdx` 経由の書込みを見ないため、名前は `pe_slot_names.py` で読んだ。
- 向き: `ippsMove_8u` は `(pSrc, pDst, len)` の順 (Intel IPP の Move は重なり可)。よって `arr[index+1..count] ← arr[index..count-1]` の shift-up になり、退避した旧 `arr[count]` (空き枠の値) を `arr[index]` に入れ、0 なら新規生成する。挿入として整合する。
- 0x664090 の list layout: `+8` = arr、`+0x10` = count、`+0x14` = cap、`+0x20` = 生成関数への引数。

## 2. O (`[0x16bafc8]`) の件数増加元

- 初期化元 (`0x11be530`〜`0x11be548`: `O = 0x663960(ctx=0xfe3340, 1, 1)`) は前回の記録 (issue #2887 コメント) の再掲。本 run では再確認していない。
- `0x664090` は O に呼ばれない (前回の E8 走査)。RIP 直接の store は 0 件。レジスタ経由の書込みは未列挙で、O の件数 `[O+0x10]` の増加元は未確定。

## 3. A 経路 getter (`0x104d0d0` の `ref`・`sub`)

名前の定義 (本付録と REPORT_PY73 §9-2 はこの定義に従う):

- `ref`: `0x1331340` が出力する参照カウント付きインタフェース。`[item+0x38] ≠ 0` なら `[item+0x38]+0x48` (以下 `X+0x48`)、0 なら既定オブジェクト `G = [0x196ed38]`。呼出し側では `[rbp+0x28]` が格納先 (0x104d10f で `lea rdx,[rbp+0x28]` として渡す)。
- `sub`: `ref` の vtable の `+0x20` を `ref` を引数に呼んだ戻り値 (`0x104d123`)。bit1 は `sub.vt[+8](sub, 0x1a, L-0x8000, 0)` (`0x104d142`〜`0x104d145`) の戻り値の下位 8 bit で決まる。`sub` の値は `ref` の vptr の `+0x20` の本体が決め、`ref` と同一とは限らない (未読)。

| 段 | VA | 内容 |
|---|---|---|
| ref 代入 | `0x1331340` (rcx=item, rdx=&ref) | `ref ← ([item+0x38] ≠ 0 ? [item+0x38]+0x48 : 0)`。代入は `0x41a7b0` |
| 既定 | `0x1331362`〜`0x1331372` | `ref == 0` なら `ref ← G = [0x196ed38]` |
| 代入の意味 | `0x41a7b0` | 新値の `vt[+8]` (AddRef) → 格納 → 旧値の `vt[+0x10]` (Release)。`ref` は参照カウント付きインタフェース |
| G の生成 | `0x1330f29`〜`0x1330f6f` | `G == 0` のとき `X = 0x132e7a0(...)` を作り、`G ← X ? X+0x48 : 0` |
| X の生成 | `0x132e7d3`〜`0x132e7e7` | `dl≠0` で `X = ctx.vt[-0x30](ctx)` (`0x410320` 経由) |
| X の初期化 | `0x13315a0` | 本体の書込みは `X+0x2c ← r8` (0x13315f7)・`X+0x1c` ← 16 byte (0x1331607〜0x1331609)・`X+0x18 ← 1` (0x133160f) の 3 つだけ。vptr の書込みは無い |
| X の初期化の呼出し | `0x13315e7` | `0x40f9e0(X, edx=0)`。0x40f9e0 は edx=0 のとき引数 `rcx` をそのまま返し (0x40f9ed〜0x40fa5a)、vptr を書かない |
| G の解放 | `0x132e074` | `&G` を `0x41a770` (Release) に渡す (解放側。文脈は未読) |
| sub | `0x104d118`〜`0x104d123` | `sub = ref.vt[+0x20](ref)` (REPORT_PY73 §9-2 の既述) |
| flags | `0x104d13b`〜`0x104d153` | `low8(sub.vt[+8](sub, 0x1a, L-0x8000, 0))` (既述) |

- 確定: `ref` は、item の `+0x38` 配下の参照カウント付きオブジェクトの `+0x48` (`X+0x48`) か、既定 `G`。`G` も `X` の生成物の `+0x48` (`G ← X ? X+0x48 : 0`)。
- 未確定: `sub` のクラス (vptr) と `sub.vt[+8]` の本体。bit1 (0x02) の決まり方はこれで決まる。次に読む先は (a) `[ref]` (`ref` の vptr。`X+0x48` の先頭 qword) の書込み元 (0x40f9e0 と 0x13315a0 には無い。X の生成 `0x132e7d3` の先を含む)、(b) `[ref]` の vtable の `+0x20` 本体 (sub を返す関数)。

## 4. 受入条件 (#2887) の判定

- [ ] 1. A 経路 getter: 部分達成。入口 (`0x1331340`)・既定 `G`・`G` の生成・`X` の初期化は PE 確定。bit1 の表は `sub` のクラス未確定のため未達。
- [ ] 2. lo・hi・cur の表: 本 run では未着手 (共通経路は REPORT_PY73 §9-6 の記録のまま)。switch 本体は #2033・#2034 の範囲。
- [x] 3. `0x664090` の挿入と件数更新、`O` の初期化元: 確定 (§1 と前回の記録)。`O` の件数増加元は `0x664090` の外にあり、§2 の未解決に残す。
- [x] 4. 推測の初期値では実装しない: 遵守 (provider・mock・tests の変更 0)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `sub` (= `ref.vt[+0x20](ref)` の戻り値) のクラス・`sub.vt[+8](0x1a)` の本体 (`[ref]` の書込み元・`ref` の vtable の `+0x20` 本体・`ctx.vt[-0x30]` の先を含む) | A 経路の bit1 (float 型か) が決まらない | #2887 (再開時) |
| `0x1046a30` の mode 0x20 (lo・hi)・mode 2 (cur) の switch 本体 | incEventValue の lo・hi・cur が決まらない | #2033 (PY-64)・#2034 (PY-65) |
| O (`[0x16bafc8]`) の件数 `[+0x10]` の増加元 (レジスタ経由の書込み) | O の中身の増え方 | #2887 (再開時) |
