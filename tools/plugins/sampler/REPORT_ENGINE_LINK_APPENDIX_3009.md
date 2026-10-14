# sampler REPORT 付録: #3009 selector 2・4 の戻り値、wrapper の呼出し元、0x84bd8f の内側 id (#540 受入条件 4 の続き)

`REPORT_ENGINE_LINK.md` §10 の (a)(b)(c) を再解析した結果。 再現は `dispatch_selectors.py` (測定 commit `74c4b07e`)。

## 1. 結論

- **(c) 戻り値 (確定)**: sel 2 は第 2 段の 15 case 全てが `0x180147cf5` を経て `xor eax,eax` (`0x180147d02`) を通るため、戻り値は常に 0。 sel 4 は 15 case 全てが `rax` を返し、型は int32 (idx 0〜4・6〜10・12〜14)、bool (idx 5)、`const char*` (idx 11)。 sel 4 の 12 呼出し元のうち 11 件は戻り値を使い、0x843d39 の 1 件は 0x843d30 の戻り値として返る (0x843d30 の呼出し元 6 件は未追跡)。
- **(a) 0x84bd8f の内側 id (確定、ただし集合)**: 内側 id は `esi` で、`esi = |[rbx+0x18]|` の下位 32bit を写像した値。 ただし 0x84bd8f に届くのは `esi ∈ {3, 7}` のみ (§5)。 3 は `[[rsp+0x38]+0x7c8]+0x48e == 0` のときだけ。 **0x84bdfa の内側 id** と **関数 0x84bc30 の呼出し元 (rbx の由来)** は未確定。
- **(b) sel 10 の第 2 引数 (C 文字列) の内容 (未確定)**: 関数 0x843930 の呼出し元は 6 件 (5 関数)。 いずれも `rdx` の由来は実行時の値 (vtable 呼出しの結果・オブジェクトのフィールド・関数引数・関数ポインタ経由) で、`.rdata` の文字列リテラルを直接渡す呼出しは無い (§6)。

## 2. 測定の前提

- 素材: `fl-win64` を `$FL_WIN64_DIR/extracted` に展開 (`tar --zstd -xf`、block23663・block23664 の 2 件のみ)。 対象は block23663 (殻)・block23664 (engine)。
- 測定 commit: **`8135335f`** (`dispatch_selectors.py` に 8 byte 絶対 VA の走査を足した commit。 直前の測定 commit は `74c4b07e`)。 本付録と REPORT の追記は md のみ。 `git diff 8135335f HEAD -- tools/plugins/sampler ':!*.md'` の出力は 0 行 (§8)。
- 実行: `python3 tools/plugins/sampler/dispatch_selectors.py "$FL_WIN64_DIR/extracted"`。 `RESULT: PASS` (CHECK 12 件 OK)、`--nc` は MISMATCH 1 件・exit 1。 時間・RSS・load は §8。
- 走査: 関数は `.pdata` の全 RUNTIME_FUNCTION から作る。 参照は命令単位 (即値・RIP 相対) とデータ内の 4 byte RVA で数える (線形走査は使わない)。

## 3. (c) engine 側 `DispatchToEngine` (block23664) の戻り値

第 1 段 (VA 0x14831c): sel 2 = 0x180147d38 (外部呼出し後に第 2 段 `0x148350` を `r9` で引く)、sel 4 = 0x180147f6d (第 2 段 `0x14838c`)。 いずれも戻り値は第 2 段の case が決める。 第 2 段の範囲外 (`cmp r12d,0xe; ja`) は sel 2 が `0x180147cf5`、sel 4 が `0x180147d02` で、どちらも 0。

sel 2 の第 2 段 (VA 0x148350、15 件、**全件 0 を返す**):

| 内側 id | case VA | 動作 (先頭命令) | 戻り値 |
|--:|--|--|--|
| 0 | 0x180147d7c | `[rbx+0x60] = esi` | 0 |
| 1 | 0x180147d8c | `[rcx+rbx+0x94] = esi` (index edi) | 0 |
| 2 | 0x180147d9f | `[rcx+rbx+0x98] = esi` | 0 |
| 3 | 0x180147db2 | `[rcx+rbx+0xa8] = esi` | 0 |
| 4 | 0x180147dc5 | `[rcx+rbx+0x9c] = esi` | 0 |
| 5 | 0x180147dd8 | `[rbx+0x14] = (esi != 0)` | 0 |
| 6 | 0x180147de5 | `[rbx+0x10] = esi` | 0 |
| 7 | 0x180147ded | `[rcx+rbx+0x88] = esi` | 0 |
| 8 | 0x180147e00 | `[rbx+0x5c]`・`[rbx+0x58]`・`[rbx+0x36f8]` 周辺の配列の再配置 (詳細は未読) | 0 |
| 9 | 0x180147d84 | `[rbx+8] = esi` | 0 |
| 10 | 0x180147e70 | `[rcx+rbx+0x90] = esi` | 0 |
| 11 | 0x180147e83 | `rsi` (第 5 引数) の C 文字列を `std::string` に格納 | 0 |
| 12 | 0x180147f65 | `[rbx+0x1c] = esi` | 0 |
| 13 | 0x180147d6d | `[[r14+0x1c8]+0x28] = esi` | 0 |
| 14 | 0x180147d5b | `[[[r14+0x1c8]]+0x380c] = esi` | 0 |

sel 4 の第 2 段 (VA 0x14838c、15 件、**全件 `rax` を返す**):

| 内側 id | case VA | 戻り値の型 | 読むフィールド |
|--:|--|--|--|
| 0 | 0x180147fb6 | int32 | `[rbx+0x60]` |
| 1 | 0x180147fbf | int32 | `[rcx+rbx+0x94]` |
| 2 | 0x180147fd3 | int32 | `[rcx+rbx+0x98]` |
| 3 | 0x180147fe7 | int32 | `[rcx+rbx+0xa8]` |
| 4 | 0x180147ffb | int32 | `[rcx+rbx+0x9c]` |
| 5 | 0x18014800f | **bool** (0/1) | `[rbx+0x14] != 0` (`setne`) |
| 6 | 0x18014801f | int32 | `[rbx+0x10]` |
| 7 | 0x180148028 | int32 | `[rcx+rbx+0x88]` |
| 8 | 0x18014803c | int32 | `[rbx+0x58]` |
| 9 | 0x180147fad | int32 | `[rbx+8]` |
| 10 | 0x180148045 | int32 | `[rcx+rbx+0x90]` |
| 11 | 0x180148059 | **`const char*`** (`c_str`。 `cap < 0x10` のときは格納アドレス) | `std::string` の `c_str` |
| 12 | 0x180148079 | int32 | `[rbx+0x1c]` |
| 13 | 0x180147f9d | int32 | `[[r14+0x1c8]+0x28]` |
| 14 | 0x180147f87 | int32 | `[[[r14+0x1c8]]+0x380c]` |

## 4. 殻の wrapper の呼出し元 (訂正を含む)

pdata の全関数から走査した呼出し元。 前の付録 (`REPORT_ENGINE_LINK_APPENDIX_540.md` §10) の件数は少なかった (下の訂正)。

- wrapper 0x846a80 (sel 2): **11 件**。 内側 id と戻り値の扱い:

| 呼出し元 | fn | 内側 id | 戻り値 |
|--|--|--:|--|
| 0x84422f | 0x844130 | 0 | 直後に `xor eax,eax` で上書き |
| 0x84433f | 0x844130 | 1 | 使わない |
| 0x84435a | 0x844130 | 2 | 使わない |
| 0x844375 | 0x844130 | 10 | 使わない |
| 0x8443b0 | 0x844130 | 11 | 直後に `rax` を上書き |
| 0x844533 | 0x8444f0 | 13 | 関数の戻り値に直送 |
| 0x8446b0 | 0x844540 | 11 | 直後に `rax` を上書き |
| 0x84571c | 0x8456d0 | 14 | 直後に `rax` を上書き |
| 0x84b49e | 0x84b3c0 | 8 | 使わない |
| 0x84bd8f | 0x84bc30 | {3, 7} (§5) | 使わない (ループ先頭で上書き) |
| 0x84bdfa | 0x84bc30 | §5 の集合 | 使う: 直後の `mov ax,1` (16bit の部分書込み) の後、`shl eax,cl` が eax 全体を読む (eax の上位 16bit は call の戻り値のまま)。 sel 2 の戻り値は常に 0 のため値には依らない |

- wrapper 0x846ac0 (sel 4): **12 件**。 戻り値を使う件が多い:

| 呼出し元 | fn | 内側 id | 戻り値 |
|--|--|--:|--|
| 0x843d39 | 0x843d30 | 0 | そのまま 0x843d30 の戻り値 (0x843d30 の呼出し元 6 件は未追跡) |
| 0x843dd2 | 0x843d50 | 1 | `mov rsi, rax` |
| 0x843de6 | 0x843d50 | 10 | `mov rdi, rax` |
| 0x843dfa | 0x843d50 | 11 | `mov rdx, rax` (`const char*` として渡す。 idx 11 の型と整合) |
| 0x844a05 | 0x8447d0 | 12 | `mov edx, eax` |
| 0x844ab6 | 0x8447d0 | 3 | `mov edx, eax` (直後の vtable 呼出し `[rbx+0x1f0]` の引数) |
| 0x844ae0 | 0x8447d0 | 7 | `mov edx, eax` |
| 0x844b05 | 0x8447d0 | 8 | `mov edx, eax` |
| 0x845692 | 0x845670 | 6 | `mov edx, eax` |
| 0x8456b3 | 0x845670 | 7 | `mov edx, eax` |
| 0x847863 | 0x847670 | 1 | `mov edx, eax` |
| 0x847e56 | 0x847e40 | 10 | `test eax,eax; jge` |

- 訂正: 付録 540 §10 の「sel 2 の呼出し元 9 件・sel 4 の 8 件」は、0x844533・0x84bdfa (sel 2) と 0x843de6・0x843dfa・0x844a05・0x845692 (sel 4) を含まない。 正しくは sel 2 が 11 件、sel 4 が 12 件。 0x843930 の呼出し元も 5 件ではなく 6 件 (0x843b9f を含む)。 0x84bc30 の命令参照 (即値・RIP 相対) は 0 件。 8 byte 絶対 VA は `.text` 内の表の 1 件 (§5)。

## 5. (a) 0x84bd8f と 0x84bdfa の内側 id

関数 0x84bc30 (`rbx` = 第 2 引数 = `rdx`)。 制御の流れ (逆アセンブル、VA 基準):

1. `0x84bc7d`: `rsi = [rbx+0x18]` (64bit)、負なら反転 (`|v|`)。 `esi` は下位 32bit。
2. `0x84bcd1`: `esi == 3` かつ `[[rsp+0x38]+0x7c8]+0x48e != 0` なら `esi = 0xc`。
3. `0x84bcf2`: `eax = esi`。 `eax > 7` なら mask 判定は偽。 `eax ≤ 7` なら `al = ((1 << eax) & byte)`、`byte` は `movzx rax, byte [rip+0x154]` (0x84bd00) の読む先 **0x84be5c** の値 **0x88** (.text 内の定数)。
4. `0x84bd13`: mask 判定が真なら `0x84bd19` のループに入る。 ループ内 `0x84bd8f` で `call 0x846a80` (sel 2) を `rdx = esi` で呼ぶ。
5. `0x84bda3`: mask 判定が偽。 `esi ≥ 0x110` (符号付き) なら sel 3 setter (0x846b10)。 それ以外は `0x84bde1` で `call 0x846a80` (sel 2、`rdx = esi`)。 これが 0x84bdfa。

- 0x84bd8f の集合: mask 0x88 のビットは {3, 7}。 `esi = 3` は手順 2 で `0xc` に写るため、フラグ `[[rsp+0x38]+0x7c8]+0x48e == 0` のときだけ残る。 よって **{3, 7}** (script の CHECK `0x84bd8f inner ids` = [3, 7] OK)。
- 0x84bdfa の集合: `esi` が符号付きで 0x110 未満、かつ手順 4 (ループ) に入らないもの。 `|[rbx+0x18]|` の値域に依存し、rbx の由来が未確定のため **未確定**。
- 0x84bc30 の参照 (`dispatch_selectors.py` の 3 種の走査。 命令の即値・RIP 相対は全関数 (`.text` を含む)、4 byte RVA は `.text` 以外のデータ section、8 byte 絶対 VA は全 section):
  - 命令の即値・RIP 相対: 0 件。
  - 4 byte RVA (`.text` 以外): 1 件 (`.pdata` の unwind 項目、VA 0x9a1858)。 `.text` の 4 byte 列は走査しない (偶発一致が出るため。 例: 0x843d30 は `.text` に 4 byte 一致 1 件 (VA 0x430877) があるが、4 byte 境界にない非整列の偶発一致で、参照ではない)。
  - 8 byte 絶対 VA (全 section): **1 件** (VA 0x84a468、`.text` 内、8 byte 整列、`.reloc` の DIR64 項目に載る = ローダが補正する画像内ポインタ)。 この位置は名前文字列と関数ポインタが並ぶ表に見える (0x84a400〜0x84a4b8 で確認。 隣の 0x84a488 は 0x84bba0 を指す)。 **この表が 0x84bc30 の参照元の候補**。 表を読む側のコードは未確認 (§7)。
  - 0x846a80・0x846ac0・0x843930・0x843d30 は 8 byte 絶対 VA で 0 件。

## 6. (b) sel 10 の第 2 引数 (関数 0x843930 の `rdx`)

呼出し元 6 件。 `rdx` の由来 (直前の代入):

| 呼出し元 | fn | `rdx` の由来 | 内容 |
|--|--|--|--|
| 0x843b21 | 0x843a60 | `[rbp+0x48]` ← 0x41b5e0(`[rbp+0x38]`) ← 0x412c30(`[rbp+0x7b]`, 0x105 byte の読取り) | 実行時 (`[rbp+0x7b]` は直前の vtable 呼出し `[rax+0x68]` の後に読む)。 未確定 |
| 0x843b9f | 0x843b80 | `[rbx+0x3d0]` (this のフィールド) | 実行時。 フィールドの設定元は未確定。 fn 0x843b80 の呼出し元は 0x83f4b5 (fn 0x83f4a0) の 1 件 |
| 0x844cf5 | 0x844b60 | `[rbp+0x78]` ← 0x41b670(`[rbp+0x40]`) | 実行時 (`[rbp+0x40]` の由来未確定)。 fn 0x844b60 の直接の呼出し 0 件 |
| 0x846ca5 | 0x846c60 | `rsi` = 第 3 引数 (`r8`) | 実行時。 fn 0x846c60 の直接の呼出し 0 件 |
| 0x847029 | 0x846ce0 | `[rbp+0x88]` ← 0x412650(`[rbp+0x50]`)、`[rbp+0x50]` ← 0x734750(`[rbp+0x88]`) | 実行時 (初期値の由来未確定)。 fn 0x846ce0 は 0x843397 で `lea` 参照 (関数ポインタ) |
| 0x847099 | 0x846ce0 | `[[[rbp+0x30]+0x120]+0xa0]` (オブジェクトのフィールド) | 実行時 |

- 結論: **未確定**。 6 件とも `rdx` は `.rdata` のリテラルを直接指さず、実行時の値 (vtable の戻り値・オブジェクトのフィールド・関数引数・関数ポインタ経由) に依る。 wine 等の動的確認は runner に無い (#540 AC5 と同じ制約)。

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x84bc30 の参照元 (8 byte 絶対 VA は表 0x84a468 の 1 件のみ。 表を読む側のコードは未確認のまま残す) と `|[rbx+0x18]|` の値域 (0x84bdfa の内側 id の集合) | sel 2 の 0x84bdfa 経路の内側 id | #540 (継続。 表を読む側の参照の確認を含む) |
| `[[rsp+0x38]+0x7c8]+0x48e` の設定元 (3 と 12 の分岐) | 0x84bd8f で id 3 が届くかどうか | #540 (継続) |
| sel 10 の第 2 引数 (C 文字列) の内容。 §6 の 6 呼出し元の由来 (実行時値) | sel 10・14 の入力文字列 | #540 (継続)。 動的確認は wine 不在のため不可 |
| sel 4 の id 0 の戻り値 (0x843d30 の呼出し元 6 件での使用) | sel 4 id 0 の値の使われ方 | #540 (継続) |

## 8. 検証

- 測定 commit: `8135335f` (コードを変えた最後の commit)。 その commit 以降の sampler のコード差分 (md 以外): `git diff 8135335f HEAD -- tools/plugins/sampler ':!*.md'` の出力は 0 行 (本 REPORT の commit は md のみ)。 再測定は要らない。
- 通常実行 (n=1、4 vCPU、`/usr/bin/time -v`): `RESULT: PASS`、CHECK 12 件 OK、exit 0、wall 20.40 s、最大 RSS 330,668 KB、load average 0.16 (1 分平均、開始前) → 0.40 (終了後)。 CHECK の内訳: sel 2 の 0 返し 15/15、sel 4 の 0 返し 0/15、sel 2 呼出し元 11、sel 4 呼出し元 12、0x84bd8f の id [3, 7]、0x84bc30 の命令参照 0、0x843930 の命令参照 6、8 byte 絶対 VA は 0x84bc30 = 1 件 (VA 0x84a468)・0x846a80・0x846ac0・0x843930・0x843d30 = 0 件。
- ネガティブコントロール: `dispatch_selectors.py <dir> --nc` は sel 2 の 0 返しの期待値を 14 に変え、`MISMATCH` で exit 1 (wall 20.74 s、最大 RSS 330,436 KB)。
- 測定の範囲 (機械化の制限): `classify_case` は線形走査で、jcc の分岐先を追わず、最初の jmp・ret・共通出口で止まる。 sel 2・4 の結論の根拠は script の CHECK と、レビュー側の CFG 走査 (jcc・noreturn を考慮) による独立検算の一致。 CFG 走査は script に入れていない。
