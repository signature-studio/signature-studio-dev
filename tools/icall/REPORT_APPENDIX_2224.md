# 付録: icall #2224 (ICALL-64) — 既知 12 slot のうち 5 件 (`0x1813068d0`〜`0x181306910`) を読む表の特定

> 親: #2197 (ICALL-62)。前付録: `REPORT_APPENDIX_2197.md`・`REPORT_APPENDIX_2198.md`・`REPORT_APPENDIX_2225.md`。
> 本付録は受入条件 (表の特定・起点 VA・index 式、表でなければ読出し元の関数 VA、`slot_trace` の再現) の判定を行う。
> 再現スクリプト: `tools/icall/diff/known12_readers.py` (objdump の全数から読み書き命令を列挙する)。
> 残件の起票先: 添字の判定の前提と `180703b7c` の表の値域は #3089 (ICALL-85)。確認範囲の外の形 (§1) は #3136 (ICALL-86)。

既知類型との関係: 該当 ID なし (DEFECTS.md D10 と形が近い。D10 は定数 ImageBase を base にした大 disp の表参照で、本付録は同形の参照を §2.3 で列挙し、5 件への届きを判定した)。

## 1. 結論

- **SlateCore.core_64 では、5 件を読む表は見つからなかった。** 5 件はそれぞれ個別の変数で、RIP 相対の直接参照 (`[rip+disp]`) 10 命令 (含む関数 7 個) だけで読み書きされる (§2.2・§2.5 (a))。T1 `0x181307100`・T2 `0x1813071a0` (#2197・#2225) の範囲外である。
- **確認範囲は次の 2 つで、どちらも SlateCore 上で取得した。** (a) RIP 相対の直接参照の全数 (`known12_readers.py` (1))。(b) 添字付き参照 `[base+idx*scale+disp]` のうち disp が `0x125c000`〜`0x13068d0` の形 (`known12_readers.py` (2))。
- **確認範囲の外 (列挙していない形):** disp が無い形 `[base+idx*scale]`、disp が範囲外の添字参照 (例 `[rdx+rcx*8+0x40]`)、基底を `lea` で作る表参照。子 #3136 (ICALL-86) に移した。よって「5 件を読む間接参照は無い」とは言えず、言えるのは上の確認範囲の結論である。
- **読出し・書込み元:** §2.2 の表 (10 命令)。含む関数は `18103d374`・`18103d37c`・`1810553c8`・`181055400`・`181055624`・`181055858`・`181055870` の 7 個。setter 3 件 (`18103d374`・`1810553c8`・`181055858`) は、`mov` の直後が `ret` の 1 命令関数である (§2.5 (c))。
- **役割 (命令からの推定):** `0x1813068d0`・`0x1813068f8`・`0x181306908` は暗号化ポインタ。`0x181306900` は dword の進行フラグ (`xchg`)。`0x181306910` はバイトの初期化済みフラグ (`cmp byte,0` / `mov byte,1`)。`0x181306900`・`0x181306910` は暗号化ポインタではない (§3)。
- **添字の判定 (4 命令)** (`180703913`・`180703b7c`・`1806dbe61`・`1806f7431`): §2.3。#2900 の付録で、`180703913` は前提付きで届かず (入口は fall-through の 1 経路だけ)、`1806dbe61`・`1806f7431` は mode==2 の経路で k ∈ [0, 32] として届かない。前提の裏取り (`180cbb930` の `r13` 保存・`rbx` の上限) と、`180703b7c` の表の値域は #3089 に残る。
- **測定 (受入条件 3):** HEAD (`b1e01dd1`) で `SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh` を実行し、baseline を再現した (rc=95: 53・既知 12 中 hit 3)。§6。

## 2. 実測

### 2.1 測定の履歴

- 前 run (PR #2815 の commit `26f90ada`) の測定 (baseline 再現): 素材は `work-icall` を `tools/icall/work/` に展開し、`plugins-freshair` を `$RUNNER_TEMP/plugins-freshair` に展開して `FA_DL=... bash tools/targets/freshair/fetch.sh` (出力 `win: 17 files, factory .epf: 8, mac: 0 files`)。`SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh` は real 12.778 s / user 11.045 s / sys 1.837 s。load average (uptime 1 分値) 0.75 (開始時 19:21:40) → 0.79 (終了時 19:21:53)。
- 結果: funcs 131・exit `{rc=0: 69, rc=124: 1, rc=95: 53, rc=98: 8}`・zero-fill VA 10 個 (`0x1813062d0` `0x1813062e0` `0x1813068f8` `0x181306ce0` `0x1813070f8` `0x1813071c8` `0x1813071d0` `0x1813073f0` `0x181307418` `0x181307420`)・既知 12 中 hit 3 (`0x1813068f8`・`0x1813073f0`・`0x181307418`)・miss 9。`REPORT_APPENDIX_2197.md` §2.1 の値と一致。
- 5 件のうち実行で読まれたのは `0x1813068f8` だけ (`1810553d0`→`181055400` の decode 内 RIP `0x18105541a`、各 ACC 1)。
- 以後の HEAD での測定は §6。素材の展開は §2.5 と §6 に記す。

### 2.2 5 件への直接参照 (全数・静的)

表は `tools/icall/diff/known12_readers.py` (1) の出力と照合した (SlateCore 上・§2.5 (a))。判定規則は `objdump -d -M intel` の全数と `.pdata` の関数境界。`int3推定` は `.pdata` 外で、直前の int3 埋めから推定した。

| slot | 役割 (推定) | 命令 | 種別 | 含む関数 | 関数の形 |
|---|---|---|---|---|---|
| `0x1813068d0` | 暗号化ポインタ | `18103d374` | W (`mov [slot],rcx`) | `18103d374` (int3推定) | `mov` の直後が `ret` の 1 命令 (§2.5 (c)) |
| 〃 | 〃 | `18103d3f3` | R (`xor r10,[slot]` → `ror r10,cl`) | `18103d37c` (pdata) | decode |
| `0x1813068f8` | 暗号化ポインタ | `1810553c8` | W | `1810553c8` (int3推定) | `mov` の直後が `ret` の 1 命令 (§2.5 (c)) |
| 〃 | 〃 | `18105541a` | R (`xor rbx,[slot]` → `ror rbx,cl`) | `181055400` (pdata) | decode。`1810553d0` から呼ばれる |
| `0x181306900` | dword の進行フラグ | `18105563f` | RW (`xchg [slot],eax`) | `181055624` (pdata) | 初期化ガード |
| 〃 | 〃 | `18105587c` | R (`mov eax,[slot]`) | `181055870` (int3推定) | 読出しのみ |
| `0x181306908` | 暗号化ポインタ (enc(NULL)=cookie) | `18105565a` | R (`mov rdx,[slot]`・`cmp rdx,rax` で NULL 判定) | `181055624` (pdata) | 初期化ガード |
| 〃 | 〃 | `181055858` | W (`mov [slot],rcx`) | `181055858` (int3推定) | `mov` の直後が `ret` の 1 命令 (§2.5 (c)) |
| `0x181306910` | byte の初期化済みフラグ | `18105562d` | R (`cmp byte [slot],0`) | `181055624` (pdata) | 初期化ガード |
| 〃 | 〃 | `1810556cb` | W (`mov byte [slot],1`) | `181055624` (pdata) | 初期化ガード |

- 初期化ガード `0x181055624`: 順に (1) `0x181306910` が 0 なら続行、(2) `0x181306900` を `xchg` で 1 に置換、(3) `0x181306908` を cookie と比べ、cookie と等しければ NULL、それ以外は decode、(4) `call [0x1810c4828]` の呼出し、(5) `0x181306910` を 1 にする。
- 既知 12 の残り 7 件 (`0x1813072b0`・`0x1813073f0`〜`0x181307418`) も (1) の全数に含まれる (§2.5 (a) の 23 行)。§2.5 (b) の表は 5 件の列だけを示す。本付録の対象は 5 件である。

### 2.3 添字付き参照の判定 (5 件に届き得るか)

`known12_readers.py` (2) が出した候補のうち、`disp` が `.data` の表候補域 (`0x125c000`〜`0x13068d0`) にあるもの。「届く添字」は、`base = 0x180000000` (image base) と仮定したときに各 slot へ届く添字の値。`n = (slot − 0x180000000 − disp) / scale` を 5 件について求めた (scale は 1・4・8)。(2) の対象外 (disp が無い形・範囲外の disp・非 slot 基底の `lea`) は §1 の確認範囲に含まれない。

| 命令 (含む関数) | 形 | 5 件に届く添字 | 判定 |
|---|---|---|---|
| `18103ce62`・`18103cf4d`・`18103cf57` (`18103ce30`) | `[r15+rdi*8+0x13068a8]` (表 A・添字 = `ecx` = 関数 id) | 5・10・11・12・13 | **届かない**。`18103ce30` の直接呼出しは 5 件 (`18103cfa0`・`18103cfea`・`18103d032`・`18103d081`・`18103d0dd`)。`ecx` は 0・1・2・3・4 (即値) |
| `18103ce89`・`18103cf05`・`18103cf23` (`18103ce30`) | `[r15+rsi*8+0x1306890]` (表 B・添字 = module id) | 8・13・14・15・16 | **届かない**。module id 配列 (下表) の値は {0, 1, 2} |
| `181011e9b`・`181011ecb` (`181011e6c`) | `[r10+rax|rcx*8+0x13064c0]` | 130・135〜138 | **届かない**。添字はループ `cmp rax,8; jb` で 1〜8 |
| `181011ec3` | `[rcx+r10*1+0x1306510]` (byte) | 960〜1024 | **届かない**。添字 rcx は 1〜8 |
| `181012638`・`18101264d`・`181012748`・`18101275d` | `[r14+rax|rbx*4+0x125eae8|0x125eaec|0x125eb28|0x125eb2c]` (dword) | 171,881〜171,914 | **届かない**。走査は 0 の dword で止まり、`.data` 上の非 0 連続長は 14 (`0x18125eae8` 起点) |
| `18105f15f`・`18105f233`・`181060253`・`1810609c1`・`1810609d0` | `[base+idx*1+0x125efa0]` (byte) | 686,384〜686,448 | **届かない**。添字は `movzx`/`movsx` の byte 値 (0〜510) |
| `180703913` (`180703880`) | `[r8+rcx*8+0x125c7b8]` | 87,075〜87,083 | **届かない (前提付き)**。入口は `18070390b` の fall-through だけで、その経路は `1807038fd` の `jne` が取られないため開かない (#2900 §2.1)。前提 `180cbb930` が `r13` を保存することは未確認で、裏取りは #3089 |
| `180703b7c` (`180703880`) | `[rbx+rcx*8+0x125c7e8]` | 87,069〜87,077 | **未確定 (#3089)**。添字 rcx は rodata の dword 表 `0x1810df738` (`movsxd rcx,[r8+rax*4+0x10df738]`) の値。表の先頭 160 dword には 87,069〜87,083 の値が無い (値域は 0〜7,929,940)。表の全長と、添字を返す `0x180702f50` の値域は未確定 |
| `1806dbe61` (`1806dbc10`) | `[rbx+rax*1+0x125c440]` (float) | 697,488〜697,552 (rbx。k = rbx/4 で 174,372〜174,388) | **届かない (mode==2 の経路)**。mode==2 では `ebp = 2 + 0x1e`・`r12d = 33`・k ∈ [0, 32] (#2900 §2.2)。届く k は範囲外。rbx の上限 (k ∈ [0, 32]) の裏取りは #3089 |
| `1806f7431` (`1806f71e0`) | `[rbx+rax*1+0x125c600]` (float) | 697,040〜697,104 (rbx。k = rbx/4 で 174,260〜174,276) | **届かない (mode==2 の経路)**。mode==2 では k ∈ [0, 32] (#2900 §2.2)。届く k は範囲外。rbx の上限の裏取りは #3089 |

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

- `18103ce30` の直接 call は 5 件以外に無い (`lea`・`jmp` による参照も無い)。`18103ce30` は closure 131 関数に含まれない。よって動的な ACC は 0 件 (`slot_trace` の対象外)。
- 上の「届かない」は論理的な除外であり、ネガティブコントロールは §2.5 (d) の (2) 側。
- 正の対照 (既存の実測): `18105541a` の R 命令 (`xor rbx,[0x1813068f8]`) は、前 run の動的採取で `0x1813068f8` を ACC 1 で読んだ読出し元と一致する。

### 2.4 測定の鮮度

- 前回測定の commit (`718e90fb`・#2900) から HEAD までの `tools/ott` の差分は、`tools/ott/lift/side_*` の 3 ファイルの追加 (+81 行)。`slot_trace.sh` は `side_` を参照しない (grep 0 件)。ただし本 run は HEAD で再測定した (§6)。
- 静的解析: `known12_readers.py` real 19.2 s (§2.5)。

### 2.5 SlateCore 上の再解析 (本 run・`plugins-freshair`)

- **素材:** `$ARTIFACTS_DIR/plugins-freshair.tar.zst` を `$RUNNER_TEMP/plugins-freshair` に展開し、`FA_DL=... bash tools/targets/freshair/fetch.sh` (出力 `win: 17 files, factory .epf: 8, mac: 0 files`)。`SlateCore.core_64` は 36,285,952 bytes。
- **逆アセンブル:** `objdump -d -M intel` (GNU objdump 2.42) の出力は 4,553,159 行 (4.5 s)。`known12_readers.py` は real 19.2 s (pefile 2024.8.26)。出力全文 (`tools/icall/work/known12_out.txt`・gitignore) の sha256: `d5ea04e4b9eca87b1422d5e56f46726af17b7b365a738bb69ad660fa4dcf47c8`。全文は 57 行 (見出し 2 行・(1) 33 行・(2) 22 行)。

**(a) (1) RIP 相対の直接参照のうち 5 件 (10 行)。** 残り 7 件の 23 行は全文に含む。

```
slot 1813068d0  W  insn 18103d374  fn 18103d374(int3推定)  mov    QWORD PTR [rip+0x2c9555],rcx        # 0x1813068d0
slot 1813068d0  R  insn 18103d3f3  fn 18103d37c(pdata)  xor    r10,QWORD PTR [rip+0x2c94d6]        # 0x1813068d0
slot 1813068f8  W  insn 1810553c8  fn 1810553c8(int3推定)  mov    QWORD PTR [rip+0x2b1529],rcx        # 0x1813068f8
slot 1813068f8  R  insn 18105541a  fn 181055400(pdata)  xor    rbx,QWORD PTR [rip+0x2b14d7]        # 0x1813068f8
slot 181306900  RW  insn 18105563f  fn 181055624(pdata)  xchg   DWORD PTR [rip+0x2b12bb],eax        # 0x181306900
slot 181306900  R  insn 18105587c  fn 181055870(int3推定)  mov    eax,DWORD PTR [rip+0x2b107e]        # 0x181306900
slot 181306908  R  insn 18105565a  fn 181055624(pdata)  mov    rdx,QWORD PTR [rip+0x2b12a7]        # 0x181306908
slot 181306908  W  insn 181055858  fn 181055858(int3推定)  mov    QWORD PTR [rip+0x2b10a9],rcx        # 0x181306908
slot 181306910  R  insn 18105562d  fn 181055624(pdata)  cmp    BYTE PTR [rip+0x2b12dc],0x0        # 0x181306910
slot 181306910  W  insn 1810556cb  fn 181055624(pdata)  mov    BYTE PTR [rip+0x2b123e],0x1        # 0x181306910
```

§2.2 の表と一致 (10 命令・種別 R/W/RW・含む関数 7 個)。

**(b) (2) 添字付き参照 (22 行)。** 5 件の列だけを示す (22 行とも 5 件それぞれに届く添字の値を持つ。値は算術上の添字で、実際に取られるかは §2.3 の判定による)。

| 命令 | 形 | 基底 | 5 件 (`d0`・`f8`・`900`・`908`・`910`) に届く添字 |
|---|---|---|---|
| `1806dbe61` | `[rbx+rax*1+0x125c440]` | 未確認 | 697488 / 697528 / 697536 / 697544 / 697552 |
| `1806f7431` | `[rbx+rax*1+0x125c600]` | 未確認 | 697040 / 697080 / 697088 / 697096 / 697104 |
| `180703913` | `[r8+rcx*8+0x125c7b8]` | 未確認 | 87075 / 87080 / 87081 / 87082 / 87083 |
| `180703b7c` | `[rbx+rcx*8+0x125c7e8]` | 未確認 | 87069 / 87074 / 87075 / 87076 / 87077 |
| `181011e9b` | `[r10+rax*8+0x13064c0]` | 未確認 | 130 / 135 / 136 / 137 / 138 |
| `181011ec3` | `[rcx+r10*1+0x1306510]` | 未確認 | 960 / 1000 / 1008 / 1016 / 1024 |
| `181011ecb` | `[r10+rcx*8+0x13064c0]` | 未確認 | 130 / 135 / 136 / 137 / 138 |
| `181012638` | `[r14+rax*4+0x125eaec]` | image base 仮定 | 171897 / 171907 / 171909 / 171911 / 171913 |
| `18101264d` | `[r14+rbx*4+0x125eae8]` | image base 仮定 | 171898 / 171908 / 171910 / 171912 / 171914 |
| `181012748` | `[r14+rax*4+0x125eb2c]` | image base 仮定 | 171881 / 171891 / 171893 / 171895 / 171897 |
| `18101275d` | `[r14+rbx*4+0x125eb28]` | image base 仮定 | 171882 / 171892 / 171894 / 171896 / 171898 |
| `18103ce62` | `[r15+rdi*8+0x13068a8]` | image base 仮定 | 5 / 10 / 11 / 12 / 13 |
| `18103ce89` | `[r15+rsi*8+0x1306890]` | image base 仮定 | 8 / 13 / 14 / 15 / 16 |
| `18103cf05` | `[r15+rsi*8+0x1306890]` | image base 仮定 | 8 / 13 / 14 / 15 / 16 |
| `18103cf23` | `[r15+rsi*8+0x1306890]` | image base 仮定 | 8 / 13 / 14 / 15 / 16 |
| `18103cf4d` | `[r15+rdi*8+0x13068a8]` | image base 仮定 | 5 / 10 / 11 / 12 / 13 |
| `18103cf57` | `[r15+rdi*8+0x13068a8]` | image base 仮定 | 5 / 10 / 11 / 12 / 13 |
| `18105f15f` | `[rcx+r15*1+0x125efa0]` | 未確認 | 686384 / 686424 / 686432 / 686440 / 686448 |
| `18105f233` | `[rax+r15*1+0x125efa0]` | 未確認 | 686384 / 686424 / 686432 / 686440 / 686448 |
| `181060253` | `[rax+r13*1+0x125efa0]` | 未確認 | 686384 / 686424 / 686432 / 686440 / 686448 |
| `1810609c1` | `[rax+r9*1+0x125efa0]` | 未確認 | 686384 / 686424 / 686432 / 686440 / 686448 |
| `1810609d0` | `[r8+r9*1+0x125efa0]` | 未確認 | 686384 / 686424 / 686432 / 686440 / 686448 |

- 添字の判定は §2.3 と一致する。「未確認」の基底は、`known12_readers.py` (2) が image base を仮定していない形。

**(c) setter 3 件の終端 (§2.2 の未確認を解消)。**

| setter | 命令 | 直前 | 次 |
|---|---|---|---|
| `18103d374` | `mov [0x1813068d0],rcx` | int3 (`18103d373`) | `ret` (`18103d37b`) |
| `1810553c8` | `mov [0x1813068f8],rcx` | int3 (`1810553c5`〜`1810553c7`) | `ret` (`1810553cf`) |
| `181055858` | `mov [0x181306908],rcx` | int3 (`181055857`) | `ret` (`18105585f`) |

3 件とも `mov` 1 命令の関数で、含む関数の推定 (int3推定) と一致する。

**(d) ネガティブコントロール (FAIL の確認)。** 入力 (`objdump` 出力) の 2 行を壊した複製で同じスクリプトを実行し、正の出力と diff を取った。

- `18103d3f3` の RIP 参照先を `0x1813068d0` から `0x1813068d8` に変えた → (1) の `slot 1813068d0 R insn 18103d3f3` の行が消えた。
- `18103ce62` の disp を `0x13068a8` から `0x13068a0` に変えた → (2) の同命令で `0x1813068d0` の添字が 5 → 6 (他 4 件も +1) に変わった。
- diff は 2 箇所。期待値との不一致として検出できた (FAIL の確認)。

## 3. harness 所見 (SLOT_ENC_INIT の書込み先)

- `slot_trace.c` の `enc[]` (既知 12) は、`SLOT_ENC_INIT=1` で cookie を 8 バイト単位で書く。しかし `0x181306900` と `0x181306910` はフラグで、暗号化ポインタではない (§2.2)。
- `0x181306910` の低バイトは cookie `0x2b992ddfa232` の `0x32` で、0 ではない。よって初期化ガード `0x181055624` は「初期化済み」と判定して本体を飛ばす (推定。`cmp byte,0` の分岐形と cookie の低バイト `0x32` からの推定。実行では未確認)。`0x181306900` は dword の一時値で、書込み値はそのまま残る。
- この差は #2247 (ICALL-68・群 C の `SLOT_ENC_INIT` 依存の判定) の材料として渡す。本付録では harness を変えない (baseline 再現のため。受入条件 3 は「再現」であり「変更」ではない)。
- 初期化ガード `0x181055624` は closure 131 関数に含まれない。よって closure 実行では `0x181306908`・`0x181306910` の読出し元は動かない。

## 4. 再現

```
python3 -m pip install pefile==2024.8.26
FA_DL="$RUNNER_TEMP/plugins-freshair" bash tools/targets/freshair/fetch.sh
SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh
mkdir -p tools/icall/work
objdump -d -M intel "tools/targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64" > tools/icall/work/core64_dis.txt
python3 tools/icall/diff/known12_readers.py tools/icall/work/core64_dis.txt "tools/targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64" > tools/icall/work/known12_out.txt
```

- `known12_readers.py` は `pefile` (検証した版 2024.8.26) を使う。上の 1 行目で導入する。
- 添字の候補 (§2.3) の「届く添字」は、スクリプトの (2) 出力の値から読む。呼出し元の値域 (§2.3 の表) は、`18103ce30` の直接 call 5 件の前 9 命令を objdump で読んで求めた。
- `slot_trace.sh` は `work-icall` (`tools/icall/work/`) を要する。未展開だと `map.json` が無く、funcs 0 で失敗する (本 run の最初の試行)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `180703b7c` の添字表 (rodata dword 表 `0x1810df738` の全長と基底 `r8`・`rbx`、添字を返す `0x180702f50` の値域) | `180703b7c` が 5 件 (87,069〜87,077) に届くかの判定 | #3089 (ICALL-85・親 #2900) |
| `180703913` の前提 `180cbb930` が `r13` を保存すること (ABI 上の前提。中身は未確認。#2900 §2.1) | `180703913` が届かないとする判定の前提 | #3089 (ICALL-85) |
| `1806dbe61`・`1806f7431` の `rbx` の上限 (k ∈ [0, 32]・mode==2 の経路。#2900 §2.2) | 両命令が届かないとする判定の前提 | #3089 (ICALL-85) |
| disp が範囲外の添字参照・基底を `lea` で作る表参照の網羅 (§1 の確認範囲の外) | 5 件への間接読出しが残る可能性 | #3136 (ICALL-86・親 #2224) |
| 初期化ガード `0x181055624` が closure 外で、`0x181306908`・`0x181306910` の読出しが動的に観測されない | 動的な hit 数に現れない。5 件の読出しの動的確認 | #2247 (ICALL-68) |
| `SLOT_ENC_INIT=1` が `0x181306910` (バイトフラグ) と `0x181306900` (dword) に cookie を書く | 群 C の判定・既知 12 の hit 数の解釈 | #2247 (ICALL-68) |

## 6. 検証

- **測定 commit:** `b1e01dd1` (`origin/main`)。本 PR の commit は `tools/icall/REPORT_APPENDIX_2224.md`・`docs/DOC_MAP.md` だけを変える。
- **測定 (HEAD):** `SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh` (`work-icall` を展開後)。real 12.565 s / user 11.051 s / sys 2.031 s。load average (uptime 1 分値) 0.40 (22:46:10) → 0.53 (22:46:23)。結果: funcs 131・exit `{rc=0: 69, rc=124: 1, rc=95: 53, rc=98: 8}`・zero-fill VA 10 個・既知 12 中 hit 3 (`0x1813068f8`・`0x1813073f0`・`0x181307418`)・miss 9。T1 static entry 20 (read 0)。T2 static entry 34 (distinct read 2・max 6・static max 33・gap 27)。baseline と一致 (rc=95: 53・既知 12 中 hit 3)。
- **測定対象のコード差分:** `git diff b1e01dd1 HEAD -- tools/icall/diff/slot_trace.sh tools/icall/diff/slot_trace.c tools/ott tools/targets/freshair | wc -l` の出力は `0` (確認時の HEAD は `64655ae5`)。本 PR の変更は `tools/icall/REPORT_APPENDIX_2224.md`・`docs/DOC_MAP.md` (確認時点) で、測定対象の外。
- **素材:** `fl-win64`・`toolchain-*` は本 run では不使用。`plugins-freshair` (§2.5)・`work-icall` (§6 の測定) を使った。`work-liftlib` は使っていない。
- **負の対照:** §2.5 (d)。
- **前 run の記録 (素材不要の fix round 1〜3。前版の記録を残す):**
  - 前 run の測定対象の差分 (測定 commit `26f90ada` から HEAD まで): `git diff 26f90ada HEAD -- tools/icall/diff/slot_trace.sh tools/icall/diff/slot_trace.c tools/ott tools/targets/freshair` の出力は 0 行。本付録の変更 (`tools/icall/REPORT_APPENDIX_2224.md`・`tools/icall/diff/known12_readers.py`・`docs/DOC_MAP.md`) は測定対象の外。
  - fix round 1: §2.3 の範囲を Python で再計算した。式は `n = (slot − 0x180000000 − disp) / scale` (5 件の slot、各行の disp と scale は §2.3 の表どおり)。結果は表 A 5〜13・表 B 8〜16・130〜138・960〜1024・171,881〜171,914・686,384〜686,448・87,069〜87,083・697,040〜697,104 と 697,488〜697,552 で、表の値と一致した。§2.2 の命令列・§2.1 の実行値は、この round では再取得していない (当時は素材なし)。
  - fix round 2: `known12_readers.py` の `RIP` を `\[rip\+0x[0-9a-f]+\].*# (?:0x)?([0-9a-f]+)` に直した。旧 `...# 0x([0-9a-f]+)$` は、行末に `<sym>` が付く GNU objdump 2.42 の行 (`# 22fc8 <sym>`・0x 接頭辞なし) に一致しない。symbol の無い PE 出力 (`# 0x1400401c0`) には旧版も一致する (実測)。`objdump -d -M intel /bin/ls` (21,399 命令) を、スクリプトと同じ行解析 (`INS`) で通した結果は、RIP 行 1,211 件に対し旧 0 件・新 1,211 件 (ネガティブコントロール)。新は全 RIP 行に一致し、取れた値は行内の `#` のアドレスと一致した。
  - fix round 3: §5 の 4 命令の起票先を #2226 から #2900 (ICALL-84・親 #2224) に移した (#2226 は T1/T2 の実装 PR #2811 の merge (2026-10-14 19:50:08Z) で閉じられている)。現在の起票先は #3089 (ICALL-85)・#3136 (ICALL-86)。
