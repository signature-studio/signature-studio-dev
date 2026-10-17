# PY-4852 (#5048・親 #4140): transport jog・marker 系 4 関数の PE 意味論

前段: `tools/python/REPORT_PY5407.md` (dispatch `0xd843d0` の出力 6 値と callback の読み方)・`REPORT_PY120.md` (`0xd84680` → `0xfdd2c0` の UI 側経路)・`REPORT_PY140.md` (`0xfdd2c0` の op 別分岐)。
対象: `transport.continuousMove`・`transport.continuousMovePos`・`transport.markerJumpJog`・`transport.markerSelJog` (`flapi_table.json`)。
解析補助: `analysis/flapi/pe_jog4_va_probe.py` (PyMethodDef 引き)・`pe_disasm.py`・`pe_ui_dispatch_probe.py`。

## 1. VA 表 (PE 確定)

解析の基点: origin/main `a2718eca0`。素材: `fl-win64` の `block00031_PE.bin` (展開先は実行時の `$RUNNER_TEMP/fl-win64/extracted`)。

| 関数 | name 文字列 | 記録 (PyMethodDef) | fn (本体) | 書式 (kwsig) | flags |
|---|---|---|---|---|---|
| continuousMove | 0xd68cd1 | 0x1118f10 | 0xd68860 | `ii` (speed, startStop) | 1 |
| continuousMovePos | 0xd68cab | 0x1118ef0 | 0xd686f0 | `ii` (speed, startStop) | 1 |
| markerJumpJog | 0xd68c46 | 0x1118e90 | 0xd68460 | `i\|i` (value, flags=0xf 既定) | 3 |
| markerSelJog | 0xd68c64 | 0x1118eb0 | 0xd68570 | `i\|i` (value, flags=0xf 既定) | 3 |

flags は `flapi_table.json` の kwsig.flags と一致する。

## 2. continuousMove・continuousMovePos (PE 確定の部分)

両関数は同じ形で、違いは callback だけ。

1. 書式解析 `0x415610` (`ii`)。第 1 int → `[rbp+0x9c]` (speed)、第 2 int → `[rbp+0x98]` (startStop)。
2. 引数の `obj` を `0xd68d10` で取り、dispatch `0xd843d0` を呼ぶ (11 引数)。第 5 引数 = speed (`movsxd [rbp+0x9c]`)、第 6 引数 = startStop (`movsxd [rbp+0x98]`)、第 7〜10 引数 = 0、第 11 引数 = 1 (`byte [rsp+0x50]`)。
3. callback (`r8`): `continuousMove` は `0xd68810`、`continuousMovePos` は `0xd686a0`。
   - 両 callback とも、先頭で `[obj+0x60] = -2`、述語 (`call [rax+0x98]`) が真のときだけ `[obj+0x60] = 0` にして本体を呼ぶ。
   - `continuousMove` の本体: `0xfdd220(ecx = obj+0x18 = speed, edx = obj+0x20 = startStop)`。
   - `continuousMovePos` の本体: `0xfdd1e0(ecx = obj+0x18, edx = obj+0x20)`。
4. `0xd82c20(status)` で結果を変換して返す (例外経路)。

### 2.1 本体の分岐 (`0xfdd220`・`0xfdd1e0`)

- `0xfdd220` (`continuousMove`): `[0x603f6b]` が 0 のとき、`startStop == 1` なら何もしない。`[0x60421b]` が非 0 かつ `startStop != 1` のとき、`speed == 0x7fffffff` なら `speed` そのまま、それ以外は `speed << 4` にして `0xfdd1e0` へ渡す。`[0x603f6b]` が非 0 のときは、`startStop > 0` のとき `0x1180d40(speed, dl=1)` を呼ぶ。
- `0xfdd1e0`: `[0x605ccd] → [+0x7e8]` の object に対し、`edx ≥ 2` なら `0x7cbd30`、それ未満なら `0x7cbd80` を呼ぶ (引数は `ecx`)。

**未確認 (推測で埋めない)**:
- `[0x603f6b]`・`[0x60421b]` の意味 (モードのフラグか、再生状態のフラグか)。§4.2 で指す先の byte までは確定。
- `0x1180d40` の `dl` 引数の意味。`speed << 4` の単位 (tick・pixel・ppq の別) も未確定。`0x1180d40` の呼出し先 (`0x11e79d0`・`0x11f3450`) と呼出し元 4 件は §4.2 で確定。
- `startStop` の値 (0・1・2 以上) が何を意味するか。`edx==1` で止める分岐と `edx≥2` の分岐の対応は PE 上の形だけ確定し、API 名との対応は未確定。

## 3. markerJumpJog・markerSelJog (PE 確定の部分)

両関数は同じ形で、違いは UI op の値だけ。

1. 書式解析 `0x415610` 相当 (`i|i`)。value → `[rbp+0x6c]`、flags → `[rbp+0x68]` (既定 0xf を `[rbp+0x68] = 0xf` で入れてから解析)。
2. `0xfdd270` を呼び、戻り値 `al` を mode とする。`0xfdd270` は `[0x607514]` 経由の vtbl+0x80 の結果を表 `0x565956` で引き、`0x81c0a0` の結果で `bit 1` を立てる形 (中身の意味は未確認)。
3. `0xd84680(engine = obj, out = &[rbp+0x50], op, arg = value, mode = al, flags = 0xf)` を呼ぶ。
   - `markerJumpJog`: op = `0x23`。`markerSelJog`: op = `0x24`。
4. `0xd84680`: 先に述語 `0x11d1430` を呼び、偽なら `out = -2`。真なら `0xfdd2c0(op, arg, mode, flags=0xf, 0)` を呼び、戻り値 `-1` なら `out = -1`、それ以外は `out = 0`。
5. `out` が 0 なら `[rbp+0x58]` を引数に vtbl 経由の呼出しで結果を作る (呼出し先の中身は未確認)。非 0 なら `0xd82c20(status)` (例外経路)。

### 3.1 `0xfdd2c0` の op 0x23・0x24 の経路 (`pe_ui_dispatch_probe.py`・arg・mode は未知で両分岐を辿った)

- 両 op とも、`0xfdeaf0` と `0x728f50` の両方に `rcx = op` (0x23 または 0x24) を渡す。
- `0xfde3e7` の `0x1180ef0(ecx = [rbp+0x3c], dl = [rbp+0x43])` で `dl` が **op 0x23 は 0、op 0x24 は 1**。`markerJumpJog` と `markerSelJog` の作用の違いはこの `dl` にあると読めるが、`dl` 分岐の先は §4.1 の表 (`0x1180ef0` の入口と呼出し先) までしか確定していない。
- `0xfdeaf0` は `0x617920` を呼んだ後 `0x425210(obj, [edx], r8 = op, r9 = arg)` を呼ぶ (`0x425210` は PostMessageW の thunk。§4.2)。
- `0x728f50` は `[rip+0xecd1fc]` が 0 なら 0 を返し、非 0 なら `0x72afa0(obj, op, arg)` を呼ぶ (`0x72afa0` の分岐と呼出し元は §4.2)。

**未確認 (推測で埋めない)**:
- `0x1180ef0` の dl 分岐の意味 (jump と select の違い)。
- `0x72b320` 以下の作用 (`op` と marker 状態の対応は §4.2 の未確定点)。
- `0xfdd270` の mode の値 (bit 1 が立つ条件) と、`arg`・`mode` が 0 以外のときの分岐。
- `markerJumpJog`・`markerSelJog` が状態のどこを変えるか (マーカー位置・選択範囲のどれか)。`value` の単位 (tick・bar・marker 番号) と `flags` (`midi.GT_All` の既定) の効果も未確定。

## 4. 結論 (受入 1 の判定)

- 4 関数の **PE 上の入口・書式・呼出し経路** は確定した (§1・§2・§3)。
- **作用の意味論 (状態のどこを変えるか・単位)** は、§2.1 と §3.1 の未確認点で止まっている。mock (`host/fl_mock.mjs`) と C provider の実装は、これらが確定するまで推測になるため、本 PR では行わない (#5510 の受入 2・3 は未着手のまま)。
- 次の一手: `0x1180ef0` (dl 分岐) と `0x7cbd30`・`0x7cbd80` (continuous の作用先) を読む子 issue を、親 #5048 の REPORT 記録の後に起票する (本 PR では起票しない)。

## 4.1 追加確定 (#6183・8 箇所のうち 3 箇所 (`0x1180ef0`・`0x7cbd30`・`0x7cbd80`) の入口と呼出し先)

| VA | 確定した内容 (PE 上の事実) | 根拠 |
|---|---|---|
| `0x1180ef0` | 引数を `[rbp+0x3c]` (ecx) と `[rbp+0x43]` (dl) に保存する。`dl` で分岐し、`dl=0` (jump 側) は `0x1181075` 以降 (`[rsi+0xd78] ≥ 0` のとき、`[rbp+0x3c]` を符号 (−1・0・+1) に置き換えてから `[rdi]` 配列を走査する)、`dl=1` (select 側) は `0x1180ffd` 以降で `0xe43d30(rcx=rsi, edx=r13d, r8d=eax, r9b=1)` を呼ぶ。 | `pe_disasm.py 1180ef0` (0x1180ff4 の `test al,al` / `je 0x1181075`・0x118106b の `call 0xe43d30`) |
| `0xe43d30` | `[rbx+0xd74]` に第 2 引数 (`edx`)、`[rbx+0xd78]` に第 3 引数 (`r8d`) を格納する。格納前の `[rbx+0xd78] ≥ 0` なら `0xe4b3a0` を先に呼ぶ。 | `pe_disasm.py e43d30` (0xe43d63〜0xe43d69) |
| `0x7cbd30` | `[obj+0x434] = edx` (speed) を格納する。`[obj+0x420]` が 0 か 10 のとき 10 にして、`0x6d9ca0(ecx=0x3c, rdx=&{obj, ...})` を呼ぶ。 | `pe_disasm.py 7cbd30` |
| `0x7cbd80` | `edx == 0x7fffffff` または `[obj+0x434] == edx` のとき `0x6d9d50` を呼び、`[obj+0x420] = 0` にする。 | `pe_disasm.py 7cbd80` |

この 4 箇所の作用先 (`0x6d9ca0`・`0x6d9d50`・`0xe4b3a0`) と、`0xe43d30` が書く `[rbx+0xd74]`・`[rbx+0xd78]` の意味 (マーカー位置か選択範囲か) は**未確認**。推測で埋めない。

## 4.2 残り 5 箇所の確定 (#6183 の残作業)

| VA | 確定した内容 (PE 上の事実) | 根拠 |
|---|---|---|
| `0x425210` | **user32!PostMessageW の import thunk**。`jmp qword ptr [rip+0x154b8fa]` の IAT slot RVA `0x1570b10` が `PostMessageW` (hint/name RVA `0x1572476`)。`0x1572476` は VA ではなく RVA として読む。`0xfdeaf0` (marker 系) から `edx = [ポインタ]`・`r8 = op`・`r9 = arg` で呼ばれる。 | `pe_thunk_target.py` の出力 `0x1572476` を RVA とみなし IAT (`pefile` の import 表) と照合 |
| `0x72afa0` | `(obj, op, arg)` を受け、`op` で分岐 (`0xb`・`0xd`・`0x1b`・`0x2b` 等) し、`0x72af60` を経由して `0x72b320([obj+0x40], ...)` を呼ぶ薄いディスパッチ (`0x72af60` は引数を組み立てるだけ)。唯一の呼出し元は `0x728f50` (`[rip+0xecd1fc]` が非 0 のとき)。 | `pe_disasm.py 72afa0` `72b003`〜`72b0cb`・`72af60`。呼出し元は capstone 全走査 (`0x728f74`) |
| `0x1180d40` | `ecx` (speed) を受け、`0x40c660` の結果 (double) と `0x1180c10` の結果の積で位置を計算し、`0x11e79d0`・`0x11f3450` を呼ぶ。`dl` は `[rip+0x3f]` の byte (`esi` の経路で `0xd0b740` も呼ぶ)。呼出し元は `0xfdd23a` (§2.1 の `dl=1` 側) ほか 3 箇所。 | `pe_disasm.py 1180d40` / capstone 全走査 (`call 0x1180d40` 4 件) |
| `[0x603f6b]` | `.data` (VA `0x15e1198`) のポインタ変数。その指す先の **byte** を `cmp byte ptr [rcx], 0` で読み、フラグとして分岐する。モード名の確定はしていない。 | `pe_disasm.py fdd220` の `0xfdd226`・`0xfdd22d`・実効アドレスは `next_ip + disp` で計算 |
| `[0x60421b]` | `.data` (VA `0x15e1468`) のポインタ変数で、同じく指す先の byte をフラグとして読む (`0xfdd246`・`0xfdd24d`)。 | 同上 |

**残った未確認 (推測で埋めない)**:
- `0x72b320` 以下の作用 (`0x72af60` の先)。`op` と marker の状態 (マーカー位置か選択範囲か) の対応は未確定。
- `[0x603f6b]`・`[0x60421b]` が指す byte の意味 (モードか再生状態か) と、その値を書く側。
- `0x1180ef0` の jump 側 (`dl=0`) の終端と、`[rsi+0xd74]`・`[rsi+0xd78]` の意味。

**前 run の誤り (訂正)**: §3.1 の `0x425210` は「飛び先 `0x1572476` が不自然・作用先不明」と書いたが、これは RVA を VA として逆アセンブルしたための誤読だった。正しくは PostMessageW の thunk (本節の表)。

## 5. 検証

- `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/flapi/pe_jog4_va_probe.py` → 4 件を出力・終了 0・所要 0.13 s (load 0.25)。
- `pe_disasm.py` で 0xd68860・0xd686f0・0xd68460・0xd68570・0xd68d10・0xd84680・0xfdd220・0xfdd1e0・0xfdd270・0xfdd2c0 を読んだ (終了 0)。
- `pe_ui_dispatch_probe.py 23 24 --arg - --mode -` → 両 op の到達 call 一覧を出力 (終了 0)。
- mock・C provider・`tests/all_tools.mjs` は本 PR で変更しないため、再測定しない。
