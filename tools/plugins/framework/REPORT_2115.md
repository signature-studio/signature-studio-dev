# #2115 REPORT — 0x4181e0 の 0 引数呼出と `rcx` (前提の訂正・注釈は未変更)

- 担当 issue: #2115 `[PLG-P0b-15]` (親 #2069 / 元 #2069 `[PLG-P0b-13]`)。
- 起点: `origin/main` 637b70de。branch `2115-plg-p0b-15-0x4181e0-rcx`。
- 素材: `fl-win64` → `$RUNNER_TEMP/fl-win64` (`extracted/block18983_PE.bin` を使用)、`work-fw-stage1` を worktree 直下の `tools/plugins/work/fw/` に展開。
- コード変更: なし。本 REPORT の追加のみ。

## 1. 結論

issue #2115 と REPORT_2069 §3.1 の前提「native `0x418190` が `rcx` を解放して返し、`0x4181e0` の戻り値はその `rcx`」は**成り立たない**。
REPORT_2069 の解析は FW の PE (`block18983_PE.bin`) ではなく `block00031_PE.bin` に対して行われていた。

| 項目 | `block00031_PE.bin` (REPORT_2069 が解析した側) | `block18983_PE.bin` (FW PE・`fw_map.json` の対象) |
|---|---|---|
| `.pdata` で `0x418190` が関数先頭 | はい (`0x418190`〜`0x41820c`) | いいえ (`0x418190` は関数先頭でない) |
| `.pdata` で `0x4181e0` が関数先頭 | いいえ | はい (`0x4181e0`〜`0x418233`) |
| `fw_map.json` の `0x4181e0` 対応 | — | `0x7d8990` |

## 2. native `0x4181e0` (FW PE 側・確定)

逆アセンブル (capstone・`block18983_PE.bin`):

```
0x4181e0 sub rsp, 0x28
0x4181e4 cmp byte ptr [rip + 0x2fe0ed], 0
0x4181eb je 0x41821b
0x4181ed mov ecx, dword ptr [rip + 0x2bec7d]   ; ecx を上書き (rcx は入力でない)
0x4181f3 call 0x418030
0x4181f8 test rax, rax
0x4181fb jne 0x41822e
0x4181fd call 0x4180d0
0x418202 mov ecx, dword ptr [rip + 0x2bec68]
0x418208 call 0x418030
0x41820d test rax, rax
0x418210 jne 0x41822e
0x418212 mov rax, qword ptr [rip + 0x2fe0b7]
0x418219 jmp 0x41822e
0x41821b mov rax, qword ptr gs:[0x58]          ; TLS 配列
0x418224 mov ecx, dword ptr [rip + 0x2bec46]
0x41822a mov rax, qword ptr [rax + rcx*8]
0x41822e add rsp, 0x28
0x418232 ret
```

- 引数を取らない TLS getter。`rcx` は読まれる前に毎経路で上書きされるため、**入力の `rcx` は使われない**。
- 戻り値は TLS 値 (`gs:[0x58]` の配列要素) か、フォールバックのグローバル `[0x7162d0]` 系。
- 0 引数の呼出元が `rcx` を store しなくても、native の戻り値は変わらない。

## 3. lift 側 (stage-1 IR・確定)

- 0 引数版 `@function_4181e0()` (`fw0.restored.ll:7185`) は `[BLK+0x20..0x40]` と `[BLK+0x88]` を読む。**`[BLK+8]` (= 9048072) を読まない**。REPORT_2069 §3.2 の通り、`9048072` を使う IR は 0 件。
- よって「`[BLK+8]` の復元が必要」は不要。0 引数版の本体は `rcx` 非依存で、戻り値は `spec.select(TLS 経由の値, @global_var_7162d0)` の形を取る。
- 0 引数呼出元 142 件 (fw0 14・fw1 10・fw2 7・fw3 2・fw4 6・fw5 12・fw6 8・fw7 8・r2 8・fw_all 67 の内訳は REPORT_2069 §3.2 の値)。本 run では `work-fw-stage1` が無く**再確認していない** (件数も IR 行も未再生成)。
- 引数付き呼出は r3 のみ 8 件 (r3 7054・7078・7100・82308・82312・144053・192518・192530)。0 引数定義との不一致は残る (受入 1 の付随確認)。

## 4. 受入条件の達成状況

| # | 受入条件 | 結果 |
|---|---|---|
| 1 | 0 引数呼出元で `rcx` が失われる経路を確定し、REPORT に呼出元の IR 行を列挙 | **部分達成**。前提は誤り: `rcx` は失われても native も lift も読まない (§2・§3)。native 呼出元 68 件は call site 単位で一覧化 (§5)。**lift 側の呼出元 IR 行 (142 件) は未列挙** (`work-fw-stage1` 不在で再生成不可。§8 へ移送) |
| 2 | 正しい戻り値を確定し `fw_hostfix.py` の 0x4181e0 注釈を修正 | **未達**。正しい戻り値 (TLS 値の実体・`[0x7162d0]` の初期値) は未確定。確定前に注釈を変えると REPORT_2069 §4 の silent miscompile になるため、変更していない |
| 3 | 実測 (所要・load・PASS/FAIL) とネガティブコントロール | **未達**。本 PR はコード変更がなく、e2e を走らせていない。e2e の数値は下記 §6 |

## 5. native 呼出元 (`block18983`・`call 0x4181e0` の直接 rel32)

`.text` の `E8` rel32 走査で call site 68 件 (capstone の線形走査と一致)。含む関数は 28 個。表の 1 行 = 1 call site。

| 関数 VA | call site VA |
|---|---|
| 0x4070f0 | 0x4070ff |
| 0x4070f0 | 0x407121 |
| 0x4070f0 | 0x40715c |
| 0x4071a0 | 0x4071ac |
| 0x4071a0 | 0x4071c2 |
| 0x4071a0 | 0x4071e0 |
| 0x407200 | 0x407204 |
| 0x407230 | 0x407234 |
| 0x407260 | 0x407265 |
| 0x4072d0 | 0x4072f7 |
| 0x407350 | 0x407358 |
| 0x407380 | 0x407387 |
| 0x4073c0 | 0x4073c5 |
| 0x4073c0 | 0x4073d0 |
| 0x40cc80 | 0x40cff9 |
| 0x40cc80 | 0x40d1b8 |
| 0x40cc80 | 0x40d36a |
| 0x40cc80 | 0x40d3c4 |
| 0x40d5d0 | 0x40d5e7 |
| 0x40d5d0 | 0x40d641 |
| 0x40d860 | 0x40d866 |
| 0x40d8b0 | 0x40d8b9 |
| 0x40d8b0 | 0x40d8f7 |
| 0x40d8b0 | 0x40d90b |
| 0x40d8b0 | 0x40d95c |
| 0x40d980 | 0x40d98a |
| 0x412f60 | 0x412f69 |
| 0x412f60 | 0x412f77 |
| 0x412f60 | 0x412f91 |
| 0x412f60 | 0x412f9d |
| 0x463730 | 0x463737 |
| 0x463730 | 0x463746 |
| 0x463730 | 0x46377c |
| 0x463730 | 0x4637a0 |
| 0x463730 | 0x4637ac |
| 0x463730 | 0x4637bb |
| 0x463730 | 0x4637d9 |
| 0x4e5ed0 | 0x4e5eda |
| 0x4e5ed0 | 0x4e5efc |
| 0x4e5ed0 | 0x4e5f08 |
| 0x4e5ed0 | 0x4e5f38 |
| 0x4e5f50 | 0x4e5f59 |
| 0x4e5fc0 | 0x4e5fc6 |
| 0x4e5fc0 | 0x4e5fd7 |
| 0x4e5fc0 | 0x4e5fff |
| 0x4e5fc0 | 0x4e6031 |
| 0x4f4f90 | 0x4f51b5 |
| 0x4ff2f0 | 0x4ff301 |
| 0x4ff9f0 | 0x4ff9f5 |
| 0x4ff9f0 | 0x4ffa24 |
| 0x4ff9f0 | 0x4ffa30 |
| 0x506230 | 0x506296 |
| 0x506230 | 0x5062a2 |
| 0x5567e0 | 0x5567f8 |
| 0x5567e0 | 0x556807 |
| 0x5567e0 | 0x556816 |
| 0x5567e0 | 0x556825 |
| 0x5567e0 | 0x556834 |
| 0x5567e0 | 0x556843 |
| 0x5567e0 | 0x556852 |
| 0x5567e0 | 0x556861 |
| 0x5567e0 | 0x556870 |
| 0x5ae990 | 0x5ae9a9 |
| 0x6b8e80 | 0x6b90a8 |
| 0x6b92f0 | 0x6b9383 |
| 0x6b92f0 | 0x6b93ab |
| 0x6b9e70 | 0x6b9eea |
| 0x6b9e70 | 0x6b9f26 |

- 「呼出元で `rcx` が書き換えられるか」の分類は**本 REPORT では未実施**。線形走査で試算したが、分類の定義 (基本ブロック・分岐をまたぐか) を確定できず、数値を採用しない。
- 関数単位の件数 (例: `0x5567e0` 9 件・`0x463730` 7 件) は一覧から数えられる。ただし `rcx` 書換えの有無は §2 の通り戻り値に影響しない。

## 6. 実測 (測定 commit: 本 PR のコード差分 0)

| 手順 | 結果 | 所要 | load |
|---|---|---|---|
| `work-fw-stage1` 展開 | 成功 | 0.45 秒 | — |
| `fl-win64` 展開 | 成功 | 9.46 秒 | 1.96 / 0.69 / 0.25 (開始時) |
| `fw_stage2.sh` | 未実施 | — | — |
| `hs_e2e.sh --fresh` | 未実施 | — | — |

- 測定 commit は 637b70de (起点)。`git diff 637b70de HEAD -- tools/plugins/framework` の差分は 0 (本 REPORT の追加のみ・注釈は未変更)。
- e2e を未実施の理由: 注釈を変えていないため、Phase A/B に変化が出る根拠がない。REPORT_2069 の基準値 (Phase A `dispatch=38 ff=0`・Phase B OOB) は前回の測定 (commit 0d9b5385) のまま。

## 7. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64
tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64
tar --zstd -xf $ARTIFACTS_DIR/work-fw-stage1.tar.zst            # repo ルートで展開 (§3 用・本 run では不在)
# block18983_PE.bin の .pdata で 0x4181e0 が関数先頭 (0x418233 まで) / 0x418190 は先頭でないことを確認
# (pefile で DIRECTORY_ENTRY_EXCEPTION の BeginAddress を比較)
grep -c 'call i64 @function_4181e0()' tools/plugins/work/fw/*.restored.ll   # 計 142 件 (§3・未再確認)
grep -c 'i64 9048072' tools/plugins/work/fw/*.restored.ll                    # 0 件が期待値
```

native 側 68 件 (§5) の確認 (`pefile` で `.text` の raw bytes を読む。入力は `block18983_PE.bin` のみ):

```python
# 送り先 = 命令末尾 (E8 の位置 + 5) + rel32 が 0x4181e0 (VA) なら call site
# 関数 VA は DIRECTORY_ENTRY_EXCEPTION の BeginAddress (+ ImageBase) で範囲判定
import re, pefile
pe = pefile.PE("block18983_PE.bin"); b = pe.OPTIONAL_HEADER.ImageBase
t = next(s for s in pe.sections if s.Name.startswith(b".text"))
d = t.get_data()[: t.Misc_VirtualSize]; tb = b + t.VirtualAddress
for m in re.finditer(b"\xe8", d):
    o = m.start()
    if o + 5 <= len(d) and tb + o + 5 + int.from_bytes(d[o+1:o+5], "little", signed=True) == 0x4181E0:
        print(hex(tb + o))   # 68 行 (call site)
```

- 生の `E8` 走査 (上記) と capstone の線形逆アセンブル (`skipdata=True`) で call site が一致することを確認済み (68 件)。
- 関数 VA への写像は、上記の `pe.DIRECTORY_ENTRY_EXCEPTION` の範囲判定で行う (§5 の表の関数 VA 列)。

## 8. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `fw_hostfix.py` の 0x4181e0 注釈 (`return 0`) の妥当性。正しい TLS 値 (`gs:[0x58]` 配列と `[0x7162d0]`) の確定 | Phase B OOB の原因が注釈かどうか未確定 | #2115 (本 issue。受入 2・3 を継続) |
| lift 側 0 引数呼出元 142 件の IR 行 (ファイル名・行番号) の列挙 | 受入 1 の残り | #2115 (`work-fw-stage1` を用意して再生成) |
| `rcx` 書換えの有無による呼出元の分類 | 本 REPORT では採用せず (戻り値に影響しないため判断は不要) | 未実施のまま (定義を決めてから再測定) |
| REPORT_2069 §3.1 の解析対象の誤り (`block00031` を使用) | 前提の誤伝播 | 本 PR で §1 に訂正を記載 |
| r3 系の引数付き呼出 (8 件) と 0 引数定義の不一致 | 引数規約の不整合 | #2115 (同上) |
| fold deref (`0x40d6e0` / `[0x710040]`) と `plug != 0` | Phase B OOB | #1890 / #2008 (既存) |
