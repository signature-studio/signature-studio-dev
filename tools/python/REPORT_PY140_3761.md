# tools/python REPORT: PY-140 (#3761, 親 #3035・PY-247): 0xfdd2c0 の op 別の到達先 (ui 12 関数)

> 前段 `tools/python/REPORT_PY120.md` の保留 (`0xfdd2c0` の op 別分岐が未追跡) の続き。`REPORT_PY140.md` と probe `pe_ui_dispatch_probe.py` は origin/main に無かったため、本 PR で新規に作った (issue 本文の「前段」は未 merge と判断)。
> 解析の素材は `[WIN64]` の fl-win64 のうち `extracted/block00031_PE.bin` のみ。

## 結論

- 12 関数 (issue の 11 関数 + scrollWindow) のうち **6 関数の leaf (呼出し先の VA) を確定**。`0xfdd2c0` の op 比較連鎖を op 値ごとに辿った結果で、VA と分岐は下の表。
  - jog (op 0)・jog2 (op 1)・stripJog (op 3): `0xfdda34` → `call 0x1180dd0` (`0xfdda37`)
  - previous (op 5)・next (op 6): `0xfde3e7` → `call 0x1180ef0` (ecx = -1 / +1)。戻り ≥ 0 なら `0xfde483` → `call 0x1063810`、`0xfde4be` → `call 0x11f3400`
  - snapOnOff (op 0x30): `0xfddb7d` → `call 0x12134f0`
- **5 関数は `0xfdd2c0` 内に作用の呼出しが無い** (strip op 2・stripHold op 4・moveJog op 8・horZoom op 0x2c・verZoom op 0x2d)。いずれも比較連鎖で `0xfde854` (共通の終端) に抜ける。作用の有無は呼出し元 (`0xd84680` 側) の確認が要る。
- 12 関数の直接の leaf に `0x8186a0` (送出) は無い。`0x8186a0` に届くのは `ui.up`・`down`・`left`・`right` (op `0x28`〜`0x2b`、`0xfde110`) と `selectWindow` (op `0x3b`、`0xfde0c9`・`0xfde0e6`) のみ (計測ログで確認)。
- `ui.scrollWindow`: `0xd843d0` と callback `0xd6d290` は **保留**。callback は vtable スロット (`[rax+0x98]`・`[rsi+0x40]`) を呼ぶため、PE の静的な呼出し先が定まらない。

## 手段

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` から `tar --zstd -xf … --wildcards '*block00031_PE.bin'` で `extracted/block00031_PE.bin` のみ展開 (2.7 秒)。`FL_WIN64_DIR` は展開先。
- probe: `analysis/flapi/pe_ui_dispatch_probe.py` (本 PR で新規)。`.pdata` の範囲を逆アセンブル (capstone)。op を定数として関数先頭から制御フローを辿る。`cmp`・`sub`・`test`・`jcc` は既知の値のときだけ確定させる。未知 (メモリ・呼出しの戻り値・部分レジスタ書込み) は両方向に辿る。読むのは読み取り専用の `.text`・`.rdata` だけ (`.data`・`.bss` は実行時に変わるため読まない)。出力は「到達しうる呼出し」の上位集合で、`det` 欄が op で確定した分岐、`unknown_forks` 欄が未知の分岐の件数。
- 手で確認した分岐 (逆アセンブル `0xfdd2c0`): `0xfdd77d` `test [rbp+0x48],8` (r9 = 0xf は `0xd84680` が渡す定数。`REPORT_PY120.md` の `0xfdd2c0(op, arg, mode, 0xf, 0)`)、`0xfdd788`〜`0xfdd7d9` の op 比較連鎖、`0xfdd849`〜`0xfdd8a1` (0x1e 以上の枝)、`0xfde380`〜`0xfde3d7` (op 5・6 の前処理)。

## 12 関数の到達先

`det` は op 値で確定した分岐 (VA と結果)。`arg` は第 2 引数 (`[rbp+0x44]`)。

| 関数 (op) | 0xfdd2c0 内の確定分岐 | leaf (呼出し VA → 先) | 引数 (既知分) | 備考 |
|---|---|---|---|---|
| `ui.jog` (0) | `0xfdd7bc` `cmp eax,2; jb` = T → `0xfdda34` | `0xfdda37` → `0x1180dd0` | ecx = arg | 戻り後 `0xfde854` |
| `ui.jog2` (1) | `0xfdd7bc` = T → `0xfdda34` | `0xfdda37` → `0x1180dd0` | ecx = arg | 同上 |
| `ui.strip` (2) | `0xfdd7c7` = F (`sub 3`≠0)・`0xfdd7d3` `jae` = T → `0xfde854` | なし | — | 作用の呼出し無し |
| `ui.stripJog` (3) | `0xfdd7c7` `sub 3; je` = T → `0xfdda34` | `0xfdda37` → `0x1180dd0` | ecx = arg | jog と同じ先 |
| `ui.stripHold` (4) | `0xfdd7d3` `jae` = T → `0xfde854` | なし | — | 作用の呼出し無し |
| `ui.previous` (5) | `0xfdd7d3` = F → `jmp 0xfde380`・`0xfde3c7` `cmp ecx,5; jne` = F (`0xfde3cc` `or eax,-1`) | `0xfde3e7` → `0x1180ef0` (ecx = -1) | ecx = -1 | `0xfde38a` の実行時フラグが 0、または `arg ≤ 0` (`0xfde3bb`・`[0xfdea18]` = 0x60 の bit 5) で `0xfde854` |
| `ui.next` (6) | 同上 (`0xfde3d2` `cmp ecx,6; jne` = F → `0xfde3d7` `mov eax,1`) | `0xfde3e7` → `0x1180ef0` (ecx = 1) | ecx = 1 | 同上 (bit 6) |
| `ui.moveJog` (8) | `0xfdd7d3` `jae` = T → `0xfde854` | なし | — | 作用の呼出し無し |
| `ui.horZoom` (0x2c) | `0xfdd7a0` `jge` = T → `0xfdd849`・`0xfdd85a` `jge 0xfdd885` = T・`0xfdd8a1` `jne` = T → `0xfde854` | なし | — | 作用の呼出し無し |
| `ui.verZoom` (0x2d) | 同上 (`0xfdd8a1` = T) | なし | — | 作用の呼出し無し |
| `ui.snapOnOff` (0x30) | `0xfdd85a` = T・`0xfdd896` `je 0xfddb68` = T | `0xfddb7d` → `0x12134f0` (`arg > 0` の枝) | rcx = `*[*(rip X)]` | `0xfddb6d` `jle` が taken (`arg ≤ 0`) なら `0xfde854` |

op 5・6 の経路の後段 (`ebx` = `0x1180ef0` の戻り):

- `ebx ≥ 0`: `0xfde483` → `call 0x1063810` (rcx = engine 内の object `[+0xd84]`・r8d = ebx・r9b = 1)、`0xfde493` → `call 0x8da350`、`0xfde4be` → `call 0x11f3400` (r8d = `[rax+0x3c0]`)、`0xfde504` → `call 0x414da0`、`0xfde51d` → `call 0x11f16b0`
- `ebx < 0`: `0xfde527` → `call 0x8da350` (`0xfde532`) → `call 0x11f16b0` (`0xfde548`) → `0xfde854`

`0xfde854` の終端: `mov eax,8` → `[rbp+0x4c]` = 8 → `call 0xfdee80` (`or [global],0x100; ret`) → `0xfde89e` で `[rbp+0x4c]` を返す。作用の呼出しがある op も `jmp 0xfde854` で同じ終端を通るため、戻り値 8 から作用の有無は区別できない。

## switch に入る前のゲート (共通)

- `0xfdd3e9` `test al,2` (mode の bit 1) が 0 なら `0xfdd3ed` で `[rbp+0x4c]` = -1 とし、`0xfdd3f3` で終端へ。mode の実機値は未確定 (`0xfdd270` の戻り)。
- `0xfdd5f9` `call 0x60c220` (rdx = 0x57f・r8 = op・r9 = arg) の戻り > 0 なら `[rbp+0x4c]` = 1 とし、`0xfdd610` で switch を飛ばして `0xfdd766` へ。op に応じて `0x60c220` の問い合わせが追加で入る (`0xfdd678` 等・r8 = 7・0x1e・0x16・0x21 など)。
- `0xfdd774` `[rbp+0x4c] ≠ 0` なら `0xfde861` で戻る。`0xfdd77d` `test [rbp+0x48],8` が 0 なら戻る (`[rbp+0x48]` は r9 = 0xf)。
- 上記ゲートの戻り値は実行時状態で決まるため未確定。表の leaf は「ゲートを通過した場合に op で決まる到達先」。

## scrollWindow の保留 (`0xd843d0`・callback `0xd6d290`)

- 呼出し元 `0xd6d300` (scrollWindow): `0xd6d37e` `lea r8,[rip-0xf5]` (= `0xd6d290`) → `0xd6d3cc` `call 0xd843d0`。戻りは `0xd6d3da` `call 0xd82c20`。
- `0xd843d0`: size 0x13e・84 命令・直接の呼出し 10 件 (`0xd84f30`・`0xd841e0`・`0x4133f0`・`0x617920`・`0x425210`・`0x526190`・`0x40faa0` 等) と間接の `call [rax]` (`0xd84481`)・`call [rdi]` (`0xd844f6`)。
- callback `0xd6d290`: size 0x67・28 命令・呼出し 2 件とも間接 (`0xd6d2b5` `call [rax+0x98]`、`0xd6d2e5` `call [rsi+0x40]`)。
- 判定: **保留**。作用先は実行時オブジェクトの vtable スロットで決まり、PE の静的な解析だけでは定まらない。確定には vtable の実体 (オブジェクトの型) の同定が要る。

## 検証

- 測定 commit: `e26790a78` (probe のコードを最後に変えた commit。`7c85d2405` に続く `--describe` 追加)。
- 実行 (FL_WIN64_DIR は展開先):

```
python3 analysis/flapi/pe_ui_dispatch_probe.py fdd2c0 0x0,0x1,0x2,0x3,0x4,0x5,0x6,0x8,0x28,0x29,0x2a,0x2b,0x2c,0x2d,0x30,0x3b --from fdd788
python3 analysis/flapi/pe_ui_dispatch_probe.py fdd2c0 --describe 1180dd0 1180ef0 1063810 11f3400 12134f0 d843d0 d6d290 fdee80 8da350 414c70
```

| コマンド (測定 commit `e26790a78`) | 結果 | wall |
|---|---|---|
| 上の 1 行目 (16 op) | 16/16 status=OK・steps 537〜766 | 3.3 秒 (2 コマンド合計) |
| 上の 2 行目 (`--describe` 10 関数) | rc 0・全関数 `ret=1` | 同上 |

- 負の対照 (組込み): op 2 と op 3 は `0xfdd7c7` の `sub 3; je` だけで分かれ、op 2 は leaf なし (`0xfde854`)、op 3 は `0x1180dd0` へ入る。op 0x2c と 0x30 も `0xfdd896` で分かれる。
- 計測ログ (`op → call_sites` と leaf の対応) は手で確認した分岐と一致した (op 0・1・3 → `0x1180dd0`、op 5・6 → `0x1180ef0`、op 0x30 → `0x12134f0`、op 0x28〜0x2b → `0x8186a0`)。
- 環境: runner 4 core・load average 0.12 (計測時)。起動・GUI の挙動は変えていない (解析のみ・KPI 対象外)。
- 差分 (測定 commit から HEAD まで・コード範囲): `git diff e26790a78 HEAD -- tools/python ':!*.md'` → 空 (本 PR の HEAD で変わるのは REPORT と DOC_MAP だけ)。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| leaf 先 `0x1180dd0` (jog)・`0x1180ef0` (previous/next)・`0x1063810`・`0x11f3400`・`0x12134f0` (snapOnOff) の UI 上の作用 (どの状態・どの関数を変えるか) | 8 関数の作用の中身 | #3035 (PY-140) |
| op 2・4・8・0x2c・0x2d の作用の有無 (`0xfdd2c0` 内に呼出しが無い)。呼出し元 `0xd84680` 側の処理の確認 | 5 関数の作用 | #3035 (PY-140) |
| mode (`r8b`) の実機値 (`0xfdd270` の戻り)・`0x60c220` の戻り (ゲート) | leaf に入る条件 | #3035 (PY-140) |
| `0xd843d0`・callback `0xd6d290` の vtable 実体 (オブジェクト型) | scrollWindow の作用 | #3035 (PY-140) |
