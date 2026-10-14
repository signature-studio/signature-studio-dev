# 付録: icall #2224 (ICALL-64) — 既知 12 slot のうち 5 件 (`0x1813068d0`〜`0x181306910`) を読む表の特定

> 親: #2197 (ICALL-62)。前付録: `REPORT_APPENDIX_2197.md`・`REPORT_APPENDIX_2198.md`・`REPORT_APPENDIX_2225.md`。
> 本付録は受入条件 (表の特定・起点 VA・index 式、表でなければ読出し元の関数 VA、`slot_trace` の再現) の判定を行う。
> 再現スクリプト: `tools/icall/diff/known12_readers.py` (objdump の全数から読み書き命令を列挙する)。

## 1. 結論

- **5 件を読む表は無い。** 5 件はそれぞれ個別の変数で、RIP 相対の直接参照 (`[rip+disp]`) で読み書きされる。
  添字付き (`[base+idx*scale+disp]`) の参照で、5 件に届くと確認できたものは無い (§2.3)。
  T1 `0x181307100`・T2 `0x1813071a0` (#2197・#2225) の範囲外である。
- **読出し・書込み元 (全数):** 5 件への直接参照は 10 命令。含む関数は 7 個 (§2.2)。
  2 件は 1 命令の setter (`mov [slot],rcx`)、2 件は decode (`ror(slot ^ cookie, cookie & 0x3f)`)、
  残り 1 組が一回限りの初期化ガード `0x181055624` (バイトフラグ・dword フラグ・暗号化ポインタを扱う)。
- **役割 (命令からの推定):** `0x1813068d0`・`0x1813068f8`・`0x181306908` は暗号化ポインタ。
  `0x181306900` は dword の進行フラグ (`xchg`)。`0x181306910` はバイトの初期化済みフラグ (`cmp byte,0` / `mov byte,1`)。
  **`0x181306900`・`0x181306910` は暗号化ポインタではない。** 下の harness 所見 (§3) を参照。
- **測定 (受入条件 3):** `SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh` は baseline を再現した
  (rc=95: 53・既知 12 中 hit 3)。
- **残る抜け (未解決 §5):** 添字の上限が静的に決まらない候補が 4 件ある (§2.3 の「未確定」)。いずれも 5 件に届くには
  観測されない大きさの添字が要る。動的採取で閉じる (#2226)。

## 2. 実測

### 2.1 測定条件と baseline の再現

- 測定 commit: `26f90ada` (main。本付録の差分は `tools/icall/REPORT_APPENDIX_2224.md`・`tools/icall/diff/known12_readers.py`・`docs/DOC_MAP.md` のみで、測定対象のコードは変えていない)。
- 素材: `work-icall` を `tools/icall/work/` に展開、`plugins-freshair` を `$RUNNER_TEMP/plugins-freshair` に展開して
  `FA_DL=... bash tools/targets/freshair/fetch.sh` (出力 `win: 17 files, factory .epf: 8, mac: 0 files`)。
- 実行: `SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh`。
  real 12.778 s / user 11.045 s / sys 1.837 s。load average (uptime 1 分値) 0.75 (開始時 19:21:40) → 0.79 (終了時 19:21:53)。
- 結果: funcs 131・exit `{rc=0: 69, rc=124: 1, rc=95: 53, rc=98: 8}`・zero-fill VA 10 個
  (`0x1813062d0` `0x1813062e0` `0x1813068f8` `0x181306ce0` `0x1813070f8` `0x1813071c8` `0x1813071d0` `0x1813073f0` `0x181307418` `0x181307420`)・
  既知 12 中 hit 3 (`0x1813068f8`・`0x1813073f0`・`0x181307418`)・miss 9。`REPORT_APPENDIX_2197.md` §2.1 の値と一致。
- 5 件のうち実行で読まれたのは `0x1813068f8` だけ (`1810553d0`→`181055400` の decode 内 RIP `0x18105541a`、各 ACC 1)。

### 2.2 5 件への直接参照 (全数・静的)

`tools/icall/diff/known12_readers.py` の (1) 出力 (`objdump -d -M intel` の全数・`.pdata` の関数境界。`int3推定` は .pdata 外で直前の int3 埋めから推定)。

| slot | 役割 (推定) | 命令 | 種別 | 含む関数 | 関数の形 |
|---|---|---|---|---|---|
| `0x1813068d0` | 暗号化ポインタ | `18103d374` | W (`mov [slot],rcx`) | `18103d374` (int3推定) | 1 命令の setter |
| 〃 | 〃 | `18103d3f3` | R (`xor r10,[slot]` → `ror r10,cl`) | `18103d37c` (pdata) | decode |
| `0x1813068f8` | 暗号化ポインタ | `1810553c8` | W | `1810553c8` (int3推定) | 1 命令の setter |
| 〃 | 〃 | `18105541a` | R (`xor rbx,[slot]` → `ror rbx,cl`) | `181055400` (pdata) | decode。`1810553d0` から呼ばれる |
| `0x181306900` | dword の進行フラグ | `18105563f` | RW (`xchg [slot],eax`) | `181055624` (pdata) | 初期化ガード |
| 〃 | 〃 | `18105587c` | R (`mov eax,[slot]`) | `181055870` (int3推定) | 読出しのみ |
| `0x181306908` | 暗号化ポインタ (enc(NULL)=cookie) | `18105565a` | R (`mov rdx,[slot]`・`cmp rdx,rax` で NULL 判定) | `181055624` (pdata) | 初期化ガード |
| 〃 | 〃 | `181055858` | W (`mov [slot],rcx`) | `181055858` (int3推定) | 1 命令の setter |
| `0x181306910` | byte の初期化済みフラグ | `18105562d` | R (`cmp byte [slot],0`) | `181055624` (pdata) | 初期化ガード |
| 〃 | 〃 | `1810556cb` | W (`mov byte [slot],1`) | `181055624` (pdata) | 初期化ガード |

- 初期化ガード `0x181055624`: 順に (1) `0x181306910` が 0 なら続行、(2) `0x181306900` を `xchg` で 1 に置換、
  (3) `0x181306908` を cookie と比べ、cookie と等しければ NULL、それ以外は decode、(4) `call [0x1810c4828]` の呼出し、
  (5) `0x181306910` を 1 にする。
- 既知 12 の残り 7 件 (`0x1813072b0`・`0x1813073f0`〜`0x181307418`) の読書きも同じ出力に全数で出る (スクリプトの (1))。
  いずれも RIP 相対の直接参照だけで、添字付きの読出しは無い。

### 2.3 添字付き参照の判定 (5 件に届き得るか)

`known12_readers.py` (2) が出した候補のうち、`disp` が `.data` の表候補域 (`0x125c000`〜`0x13068d0`) にあるもの。
「届く添字」は、そのまま `base = 0x180000000` (image base) と仮定したときに各 slot へ届く添字の値。

| 命令 (含む関数) | 形 | 5 件に届く添字 | 判定 |
|---|---|---|---|
| `18103ce62`・`18103cf4d`・`18103cf57` (`18103ce30`) | `[r15+rdi*8+0x13068a8]` (表 A・添字 = `ecx` = 関数 id) | 5・10・11・12・13 | **届かない**。`18103ce30` の直接呼出しは 5 件 (`18103cfa0`・`18103cfea`・`18103d032`・`18103d081`・`18103d0dd`)。`ecx` は 0・1・2・3・4 (即値) |
| `18103ce89`・`18103cf05`・`18103cf23` (`18103ce30`) | `[r15+rsi*8+0x1306890]` (表 B・添字 = module id) | 8・13・14・15・16 | **届かない**。module id 配列 (下表) の値は {0, 1, 2} |
| `181011e9b`・`181011ecb` (`181011e6c`) | `[r10+rax|rcx*8+0x13064c0]` | 130・135〜138 | **届かない**。添字はループ `cmp rax,8; jb` で 1〜8 |
| `181011ec3` | `[rcx+r10*1+0x1306510]` (byte) | 960〜1024 | **届かない**。添字 rcx は 1〜8 |
| `181012638`・`18101264d`・`181012748`・`18101275d` | `[r14+rax|rbx*4+0x125eae8|0x125eaec|0x125eb28|0x125eb2c]` (dword) | 約 171,880〜171,914 | **届かない**。走査は 0 の dword で止まり、`.data` 上の非 0 連続長は 14 (`0x18125eae8` 起点) |
| `18105f15f`・`18105f233`・`181060253`・`1810609c1`・`1810609d0` | `[base+idx*1+0x125efa0]` (byte) | 約 686,384〜686,448 | **届かない**。添字は `movzx`/`movsx` の byte 値 (0〜510) |
| `180703913`・`180703b7c` | `[r8|rbx+rcx*8+0x125c7b8|0x125c7e8]` | 87,069〜87,083 | **未確定**。添字 rcx は rodata の dword 表 `0x1810df738` (`movsxd rcx,[r8+rax*4+0x10df738]`) の値。表の先頭 160 dword には 87,069〜87,083 の値が無い (値域は 0〜7,929,940)。表の全長と基底 r8 の値は未確定 |
| `1806dbe61`・`1806f7431` | `[rbx+rax*1+0x125c440|0x125c600]` (float) | 約 697,040〜697,104 | **未確定**。rbx (バイト添字) の上限は静的に決まらない |

- 表 A・B は、5 件に届く添字 (A は 5・10〜13、B は 8・13〜16) が、呼出し元の実値域 (fn id 0〜4・module id 0〜2) の外にある。
  A と B は同じ領域を指すが、B の添字 0〜2 (`0x181306890`〜`0x1813068a0`) と A の添字 0〜4 (`0x1813068a8`〜`0x1813068c8`) は重ならない。
- 呼出し元の引数 (`18103ce30` の (ecx, rdx, r8, r9) = (fn id, 名前, module id 配列の [r8, r9))。5 件とも配列は 8 バイト (2 要素)。

| 呼出し箇所 | fn id (ecx) | module id 配列 [r8, r9) | 値 |
|---|---|---|---|
| `18103cfa0` | 0 | `0x181127c50`〜`c58` | 0, 2 |
| `18103cfea` | 1 | `0x181127c68`〜`c70` | 0, 2 |
| `18103d032` | 2 | `0x181127c78`〜`c80` | 0, 2 |
| `18103d081` | 3 | `0x181127c90`〜`c98` | 0, 2 |
| `18103d0dd` | 4 | `0x181127ca8`〜`cb0` | 1, 2 |

- 静的な参照は、`18103ce30` の直接 call 5 件以外に無い (`lea`・`jmp` による参照も無い)。
- `18103ce30` は closure 131 関数に含まれない。よって動的な ACC は 0 件 (`slot_trace` の対象外)。

### 2.4 測定の鮮度

- `git diff 26f90ada HEAD -- tools/icall/diff/slot_trace.sh tools/icall/diff/slot_trace.c tools/ott tools/targets/freshair` の出力は 0 行 (§6)。
- 静的解析の所要: `known12_readers.py` real 19.4 s (`SLOT_ENC_INIT` 不使用)。

## 3. harness 所見 (SLOT_ENC_INIT の書込み先)

- `slot_trace.c` の `enc[]` (既知 12) は、`SLOT_ENC_INIT=1` で cookie を 8 バイト単位で書く。
  しかし `0x181306900` と `0x181306910` はフラグで、暗号化ポインタではない (§2.2)。
- `0x181306910` の低バイトは cookie `0x2b992ddfa232` の `0x32` で、0 ではない。よって初期化ガード `0x181055624` は
  「初期化済み」と判定して本体を飛ばす。`0x181306900` は dword の一時値で、書込み値はそのまま残る。
- この差は #2247 (ICALL-68・群 C の `SLOT_ENC_INIT` 依存の判定) の材料として渡す。本付録では harness を変えない
  (baseline 再現のため。受入条件 3 は「再現」であり「変更」ではない)。
- 初期化ガード `0x181055624` は closure 131 関数に含まれない。よって closure 実行では `0x181306908`・`0x181306910` の読出し元は動かない。

## 4. 再現

```
FA_DL="$RUNNER_TEMP/plugins-freshair" bash tools/targets/freshair/fetch.sh
SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh
objdump -d -M intel "tools/targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64" > tools/icall/work/core64_dis.txt
python3 tools/icall/diff/known12_readers.py tools/icall/work/core64_dis.txt "tools/targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
```

- `known12_readers.py` は `pefile` を使う (agent-setup の venv にある)。
- 添字の候補 (§2.3) の「届く添字」は、スクリプトの (2) 出力の値から読む。呼出し元の値域 (§2.3 の表) は、`18103ce30` の直接 call 5 件の前 9 命令を objdump で読んで求めた。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `180703913`・`180703b7c` の添字表 (rodata dword 表 `0x1810df738` の全長と基底 `r8`・`rbx` の値) | 5 件に届くかの判定 (届く添字 87,069〜87,083 は先頭 160 dword に無い) | #2226 (ICALL-66・動的な添字の採取) |
| `1806dbe61`・`1806f7431` の float 読出しの添字上限 (`rbx`) | 同上 (届く添字 約 697k) | #2226 (ICALL-66) |
| 初期化ガード `0x181055624` が closure 外で、`0x181306908`・`0x181306910` の読出しが動的に観測されない | 動的な hit 数に現れない。5 件の読出しの動的確認 | #2247 (ICALL-68) |
| `SLOT_ENC_INIT=1` が `0x181306910` (バイトフラグ) と `0x181306900` (dword) に cookie を書く | 群 C の判定・既知 12 の hit 数の解釈 | #2247 (ICALL-68) |

## 6. 検証

- 測定対象の差分 (測定 commit `26f90ada` から HEAD まで): `git diff 26f90ada HEAD -- tools/icall/diff/slot_trace.sh tools/icall/diff/slot_trace.c tools/ott tools/targets/freshair` の出力は 0 行。
  本付録の変更 (`tools/icall/REPORT_APPENDIX_2224.md`・`tools/icall/diff/known12_readers.py`・`docs/DOC_MAP.md`) は測定対象の外。
