# tools/qfclift 付録 4263 — T-SH-107 (#4263): longjmp 0x40f9c0 の発生条件

REPORT.md §7.7 の未解決「longjmp の発生条件」の解析。検証 HEAD = `6a9f1c3f0` (origin/main 起点)。
道具: `callers_4263.py` (`.pdata` の関数単位で逆アセンブルし、`call` の呼出元と `rip` 相対参照の書込み元を列挙)。出力は `work/callers_4263.txt` (生成物)。

## 1. 結論 (静的解析)

- **issue 本文の番地の訂正**: `0x40fbd4`・`0x40fcbd` は `0x40fa40` の呼出しの**戻り番地**で、呼出し命令ではない。
  実際の `call 0x40fa40` は `0x40fbcf` と `0x40fcb8` (どちらも関数 `0x40fb80` 内)。`0x40fa40` の呼出元は、この 2 箇所だけ。
- **`[0x5aa000]` (flag) の書込みは 2 箇所**: setter `0x40fd10` の `0x40fd14` (`mov [0x5aa000], ecx`) が 1 箇所。
  他に `0x40fa7f` (longjmp 側の 0 クリア) がある。書込みは「エラー code を ecx で渡す」形で、呼出元は次の表。
- **longjmp の戻り値**: `0x40fa6e`〜`0x40fa7c` で `eax = ([0x5aa000] != 0) + 1`。flag 0 なら戻り値 1、非 0 なら 2。
  DllMain の `cmp eax,1` (`0x59c210`) はこの値で分岐する。
- **発火経路は 2 つ** (どちらも `0x40fb80` の内側。`0x40fb80` は DllMain・`0x40f430`・setter `0x40fd10` の末尾から呼ばれる共通の後始末)。

| 経路 | 呼出し箇所 | 発火条件 (静的) | 飛び先 (rcx) |
|---|---|---|---|
| A | `0x40fbcf` | `[0x5d0db0] != 0` (armed) **かつ** `GetCurrentThreadId() == [0x5d0ddc]` | record `0x5d0da8` |
| B | `0x40fcb8` | `byte [0x5d0cb0] != 0` (`0x40fca8`〜`0x40fcaf`) | record `0x5d0c80` |

- **経路 A の arming**: record `0x5d0da8` は `0x40f430` が `[rbp+0x170] >= 2` のときだけ設定する (`0x40f456` の `lea r13,[0x5d0da8]`)。
  `0x40f4d9` で `[r13+8]=1` (armed)、`0x40f49c` で `[r13+0x34]=GetCurrentThreadId()` (= `0x5d0ddc`)。`0x40fbbd` で disarm。
  `[rbp+0x170]` は DllMain の `reason` (`0x59c240` の `r9d = [rbp+0x3c]`)。DllMain の PROCESS_ATTACH (reason 1) では `r13 = 0x5d0c80` になり、経路 A は arm されない。
- **経路 B の flag**: `byte [0x5d0cb0]` の書込みは、`.text` 全体で rip 相対の直接 store が 0 件 (`callers_4263.py` の出力)。
  読みは `0x40fbd4`・`0x40fc06`・`0x40fc22`・`0x40fc4d`・`0x40fc99`・`0x40fca8` (全部 `0x40fb80` 内)。
  **書込み元は未特定** (lea 経由・間接 store の可能性)。ここが「longjmp が発生する条件」の残りの未解決点。

## 2. `[0x5aa000]` の書込み元 (setter `0x40fd10` の呼出元)

| 呼出元 (VA・所属関数) | ecx (code) | 条件 |
|---|---|---|
| `0x40f00e` (fn `0x40eff0`) → `0x40fd30` | `0xd8` | 引数 rcx が NULL |
| `0x40f1e4` / `0x40f237` / `0x40f2b5` (fn `0x40f1c0`・`0x40f290`) → `0x40fd30` | `0xd8` | リスト先頭ノードが NULL |
| `0x4194ee` / `0x419504` (fn `0x4194d0`) → `0x40fd30` | `0xe2` | 直前の検査が失敗 |
| `0x43c75e` (fn `0x43c750`) → `0x40fd10` | `1` | 無条件 (`0x43b1d0` の後) |
| `0x40946b` (fn `0x409460`) → `0x40fd10` | 呼出元の ecx をそのまま通す | 呼出元は未追跡 |

`0x40fd30` は `[0x5aa008]` (引数) を書いてから `0x40fd10` を呼ぶ。`0x40fb80` の先頭 (`0x40fb87`〜`0x40fb91`) は `[0x5aa008] != 0` なら `0x40f8b0` で 16 進を整形し、`0x40faa0` が `GetStdHandle(-11)` + `WriteFile` で出力する (import `0x5db870`・`0x5dbaa8` を確認)。

## 3. 境界の確認 (DllMain 経路)

- DllMain `0x59c1f0`: `0x59c20b call 0x40fa30` (setjmp) → 戻り `0x59c210` で `cmp eax,1`。
  `eax == 0` (通常) なら `0x59c224` で `0x419dc0` (本体) を呼び、`0x59c24f` で `0x40fb80` に入る。
- `0x419dc0` → `0x40f430` (`0x419e54`) は mode = `r13d` = reason = 1。`0x40f430` は `[0x5d0c80]` に `rcx` (= DllMain の frame `rbp+0x48`、非 0) を保存する。
- 経路 B で longjmp されると、`0x40fa40` が保存された frame を複写し、`0x59c210` (DllMain の setjmp の戻り番地) に戻る。戻り値は flag から決まる 1 か 2。
  flag 0 なら `eax = 1` で `setle` → `0x59c254` へ分岐し、本体 `0x419dc0` を**飛ばして** DllMain が戻る。

## 4. boot の停止点との関係 (解釈。未検証)

- REPORT §7.8 の「override + root で `ExitProcess(0)`」は、経路 B の longjmp が `0x59c210` に戻った後の進行である可能性が高い (flag 0・`eax=1` で本体を飛ばして戻る)。
- ただし `ExitProcess` (import `0x5db840`) の呼出し元は、`0x40fb80` 末尾の `0x40fcd7` (`mov ecx,[0x5aa000]; call 0x406dc0`) 以外にも候補があり、本解析では特定していない。
  `0x40fcd7` に届くには `[0x5d0c80] == 0` が必要。`0x40f430` の保存で非 0 になるはずなので、この経路が boot の `ExitProcess(0)` かは**未確定**。
- **boot の lift 設定は変更しない**。静的な発火条件だけでは override・root の追加先が決まらず、停止点の変化を実測する根拠も無いため。
  経路 B の飛び先 (`0x5d0c80`) の実行時の値と、`[0x5d0cb0]` の書込み元は、実行時のトレースで決める必要がある。

## 5. 経路 B の flag `byte [0x5d0cb0]` の書込み元 (特定)

- 書込みは `0x40f4eb`: `mov byte ptr [r13+0x30], al` (所属関数 `0x40f430`)。`r13` は `0x40f446` で `0x5d0c80`、`0x40f456` で `0x5d0da8` (`[rbp+0x170] >= 2` のとき)。
  `0x5d0cb0 = 0x5d0c80 + 0x30` なので、rip 相対の直接 store 0 件は「レコード経由の store」だった。`0x40f4e1`〜`0x40f4eb` で `al = [rbp+0x170] + 1` (= reason + 1)。
- 読みは `0x40fca8` (`cmp byte [0x5d0cb0], 0`)。非 0 なら `0x40fcb8` で `0x40fa40` を呼ぶ (= 経路 B)。
- **reason 1 (PROCESS_ATTACH) では flag = 2 (非 0)**。`r13 = 0x5d0c80` のため、経路 B は DllMain 本体 (`0x419dc0`) の後に必ず発火する。経路 A は arm されない (§1)。
- 再現: `python3 disasm_range_4263.py block24350_PE.bin 0x40f4e1 0x40f4f0` (道具は `tools/qfclift/disasm_range_4263.py`)。

### 5.1 実測 (boot、HEAD `bfbe3f683` の lift 設定。`qfc_boot.sh`)

- `qfc_boot.sh` (strict / soft) の結果: strict は `MISSING IMPORT LocalAlloc` で DllMain の trap (FAIL)。soft は `DllMain(PROCESS_ATTACH)` が `ok rax=0x1`、続く `FontCache_GetStats` で `call to UNLIFTED function 0 ret=0x57fb09` (FAIL)。
- 既存の lift 設定 (override `0x40f9c0=qfc_ov_longjmp`・root `0x59c210`) で、経路 B の戻り先は既に入っている。このため新しい override・root の追加は不要。
- 経路 B の発火条件は §5 で確定した。停止点 (`FontCache_GetStats`) は経路 B の後の段であり、経路 B 自体の不具合ではない。次の停止点は FT 解決 (`0x563000`) の未解決ポインタ (#4296 / #4510 §2)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 経路 A の発火は DllMain reason 1 では起きない (`r13=0x5d0c80`)。reason ≥2 の経路 (boot 未測定) | 別 reason の挙動が不明 | #4263 (継続) |
| `ExitProcess(0)` の呼出し元と、`[0x5d0c80]` の boot 時の値 | 偽の停止か否かの判定 | #4262 (T-SH-106) |
| 呼出元 `0x40946b` (fn `0x409460`) の上位呼出元 | setter へ渡る code の出所 | #4263 (継続) |

## 7. 検証

- 解析: `python3 callers_4263.py <block24350_PE.bin>` (1.8 s)。`.pdata` 関数単位の逆アセンブル。
  依存: `pip install pefile capstone` (Python 3)。表の番地は上記スクリプトの `call` 行 (呼出し命令の VA) で確認した。
- lift 設定 (`qfc_boot.sh`・`qfc_ov.c`・`qfc_e2e.sh`) は変更していない。e2e は下記の値で確認。
