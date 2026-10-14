# 付録: icall #3136 (ICALL-86) — SlateCore.core_64 の lea 基底の添字参照の静的網羅 (5 件 0x1813068d0〜0x181306910)

> 親: #2224 (ICALL-64)。前付録: `REPORT_APPENDIX_2224.md` (§2.2 の (1)、§2.3 の (2) について SlateCore 上の出力が未取得だった件・§5 の残件)。
> 測定 commit: `e1f253c2` (コード差分の最終 commit)。`git diff e1f253c2 HEAD -- tools/icall/diff tools/targets/freshair` の出力は 0 行。検証起点: `origin/main` `91610209`。
> 走査: `tools/icall/diff/lea_index_scan.py`。負の対照: `tools/icall/diff/lea_index_scan_selftest.sh`。

## 1. 結論

- **受入 1 (列挙・記録)**: SlateCore.core_64 の全命令 3,822,318 件から、添字付きメモリ式 138,443 件を抽出した。このうち基底が `lea [rip+...]` の定数 X を持つ組は 1,235 件 (線形走査と流れ非依存の両方を数えた)。X のもとで 5 件のいずれかに**整数の添字 n で届く**候補は **1,229 件** (同一 (VA・式・X) は 1 件に集約。アクセス: R 1,156・W 45・RW 3・アドレス生成 25)。
- **届かないと示せたもの: 204 件** (添字の値域が定数・movzx・and・shr で確定し、n がその外。§3.1)。
- **届き得るもの: 1,025 件** = 値域内 25 件 (6 関数) + 値域未確定で |n|<2^16 の 99 件 (64 関数) + 値域未確定で |n|≥2^16 の 901 件 (504 関数)。
- **5 件に届く読出しが無いことは示せなかった。** 届き得る 25 件は、前付録が列挙していない disp 範囲外の添字参照を含む (例: `18106e98c` `mov ecx,DWORD PTR [r8+rdx*4+0x106efb0]`、§3.2)。
- **前付録 §2.3 の表 A・B (`18103ce30` の 5 命令) との関係**: 前付録は、呼出し元の実値域 (fn id 0〜4・module id 0〜2) から「届かない」とした。関数内だけを見る本走査では、表 A・B は「届き得る」に分類される (§3.3・§4)。届かない根拠は呼出し元側の値域であり、関数内の走査では示せない。
- **受入 2 (VA・値域・理由の記録)**: 届き得る命令は読出し元の関数 VA と添字の値域を記録した (値域未確定は添字の定義種別を記録)。届かない命令は値域と理由を記録した (§3.1)。
- **受入 3 (baseline)**: `SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh` を `e1f253c2` で再現 (funcs 131・`{rc=0: 69, rc=124: 1, rc=95: 53, rc=98: 8}`・既知 12 中 hit 3)。
- 前付録 §5 の残件のうち、(1) の SlateCore 上の全数と (2) の出力全文は本付録で取得した (§2)。setter 3 件の終端は未確認 (§5)。

## 2. 測定条件

- 素材: `work-icall` → `tools/icall/work/` (展開 22 s)。`plugins-freshair` → `$RUNNER_TEMP/plugins-freshair` → `FA_DL=... bash tools/targets/freshair/fetch.sh` (`win: 17 files, factory .epf: 8, mac: 0 files`)。`fl-win64` は本測定で使わない。
- 逆アセンブル: `objdump -d -M intel SlateCore.core_64` → `tools/icall/work/core64_dis.txt` (4,553,159 行・real 3.8 s)。
- 前付録の (1)(2) (SlateCore 上): `known12_readers.py` real 14.3 s、出力 57 行。(1) は既知 12 を指す直接参照 33 行のうち、5 件 (`0x1813068d0`〜`0x181306910`) は 10 行 (前付録 §2.2 の表と一致)。(2) の候補は 22 行 (前付録 §2.3 の表の命令と一致)。
- 走査: `lea_index_scan.py` real 20.3 s (load 0.54→0.67・単一プロセス)。
- baseline: `slot_trace.sh` real 11.8 s (user 11.0 s・load 0.56→0.63)。

## 3. 結果

判定は、添字 I の値域 (線形区間での最後の定義から分類) と n = (slot − X − disp)/sc の組で決める。

### 3.1 届かない (204 件)

| 添字の定義 (値域) | 件数 | 備考 |
|---|---|---|
| movzx byte (0..255) の外 | 81 | n は約 4.97M など大きい |
| and imm (0..imm) の外 | 80 | |
| shr k (0..2^(bits−k)−1) の外 | 29 | k=15・16・24 の順 (16・12・1) |
| movsx byte (−128..127) の外 | 5 | |
| movzx word (0..65535) の外 | 5 | |
| 定数 (xor/mov 即値) と n が不一致 | 4 | 定数 0・128 |

内訳はアクセス別に R 198・W 5・アドレス生成 1。

### 3.2 届き得る・値域内 (25 件・6 関数)

| 関数 | 命令 VA | 式 (X・disp・sc) | 添字の定義 (値域) | n (5 件) | アクセス |
|---|---|---|---|---|---|
| `1800cb470` | `1800cb662` | `[rcx+rax*8]` (X=181141a68) | `shr rax,0x20` (0..2^32−1) | 231885〜231893 | R |
| `181046890` | `181046a20`・`181046a2a`・`181046ab2`・`181046abc`・`1810475f4`・`1810475fe`・`181047675`・`18104767b` (8 件) | `[r9\|rdx+r8*8]` (X=18112a030/18112a840/181131860/181132070) | `shr r8,0x2c` (0..2^20−1) | 239884〜243996 | R (浮動小数の読出し) |
| `181049d40` | `181049e0b`・`181049e80`・`181049e8d`・`18104a0ae`・`18104a109`・`18104a116` (6 件) | `[r9\|rdx+rax*8]` | `shr rax,0x2c` (0..2^20−1) | 239884〜240692 | R |
| `18104b530` | `18104b600`・`18104b67d`・`18104b68a`・`18104b8de`・`18104b941`・`18104b94e` (6 件) | `[r9\|rdx+rax*8]` | `shr rax,0x2c` (0..2^20−1) | 238904〜240692 | R |
| `18106e8e0` | `18106e98c` | `[r8+rdx*4+0x106efb0]` (X=180000000・sc=4) | `shr edx,0x4` (0..2^28−1) | 679496〜679512 | R |
| `c181072590` | `181072602`・`18107262b`・`181072654` (3 件) | `[r11+rcx*4+0x11862a0]` (X=180000000・sc=4) | `shr rcx,0x8` (0..2^56−1) | 393612〜393628 | R |

- 「shr 44 (値域 0..2^20−1)」の 20 件 (§3.2 の表の 2〜4 行目) の n は 238,904〜243,996。値域内だが、添字がその値を取る経路の有無は静的に決まらない。
- `18106e98c` の基底は、`18106e975` の `lea r8,[rip+0xfffffffffef91684]` (= 0x180000000) で作られる (raw 行で確認)。n = (0x1813068d0 − 0x180000000 − 0x106efb0)/4 = 679,496 (整除)。

### 3.3 値域未確定・|n|<2^16 (99 件・64 関数)

- 添字の定義: `sar` 53・線形区間に定義なし 24・lea 11・mov 8・imul 2・dec 1。
- 基底 X: `0x181306cf0` が 61 件 (`[reg+idx*8]` で n = −132〜−124 相当 = 負の添字。`sar` は符号付きのため値域は確定しない)。image base `0x180000000` が 15 件 (disp は 0x106efb0 等の範囲外)。
- アクセス: R 80・RW 3・W 7・アドレス生成 9。
- 表 A・B (前付録 §2.3): `18103ce62` (`mov edi,ecx` 由来・n = 5〜13)、`18103cf05`・`18103cf23` (`rsi` は関数入口由来・n = 8〜16) は、関数内の定義では値域が確定しない。前付録の「届かない」は呼出し元の値域 (§4) に基づく。

### 3.4 値域未確定・|n|≥2^16 (901 件・504 関数)

- 最小 |n| = 80,512。届くには添字が 80,512 以上 (または負) であることが必要。
- 添字の定義: 線形区間に定義なし 241・add 167・mov 130・lea 122・shl 56・movd 40・movsxd 30・xor 26・pextrd 24・and 20・その他 (neg・seta 等)。32 bit 定義 (零拡張で [0,2^32)) と 64 bit 定義 (未確定) の別は出力の `判定` 列に記録。
- アクセス: R 853・W 33・アドレス生成 15。
- 添字が 2^16 以上を取り得るかは、この静的解析では判定できない。

## 4. 検算・負の対照・限界

- 負の対照 (`bash tools/icall/diff/lea_index_scan_selftest.sh`・3/3 PASS): 正 = 「lea 基底 0x1813068c0 + rdx*8 + 0x10」は 0x1813068d0 に添字 0 で届く (届く・定数一致)。負 1 = disp を 0x11 に壊すと候補 0 件。負 2 = 添字を 1 にすると「届かない・定数不一致」。
- 原文の検算: §3.2 の `18106e98c` は、raw 行の `lea r8` (18106e975) と読出し (18106e98c) の組で確認した (上記)。
- 表 A・B の判定が食い違う理由: 前付録 §2.3 は `18103ce30` の直接 call 5 件の引数 (fn id 0〜4・module id 0〜2) から届かないとした。本走査は関数内の定義だけを使うため、この前提を使えない。両者は別の前提に基づく。
- 限界:
  - 基底 X は、線形区間 (分岐先・ret/jmp/int3/ud2/hlt の直後で破棄) の lea 直値、または関数内の全定義が lea-rip の場合の集合に限る。`add`/`sub` で進めた基底は未追跡。
  - 添字の値域は、線形区間での最後の定義から分類する。分岐先で区切るため、到達定義と一致する前提。
  - 間接ジャンプの先は解析していない (直前が ret/jmp の命令の次を区間の先頭とする)。
  - 関数入口の引数レジスタ (rcx・rdx・r8・r9 等) は、呼出し元の値を持たない (値域未確定)。
  - 別アルゴリズムによる検算は未実施 (レビュー側に委ねる)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 値域未確定の 1,000 件 (§3.3 の 99 件・§3.4 の 901 件) の添字上限 (sar・add・mov・入口由来の定義) | 5 件に届くかの判定。届き得る 25 件 (§3.2) の実行到達 | #3089 (ICALL-85・open)。件数と再現コマンドをコメントで渡す |
| 表 A・B (`18103ce30` の 5 命令) の「届かない」は呼出し元の値域に依る | 関数内の走査では届き得る。判定の根拠 | #3089 (同上)。前付録 §2.3 の記述は変えない |
| setter 3 件 (`18103d374`・`1810553c8`・`181055858`) の終端 (前付録 §2.2 (b)) | 関数形の裏取り | #2224 (親に残す) |

## 6. 再現

```sh
tar --zstd -xf "$ARTIFACTS_DIR/work-icall.tar.zst" -C .              # tools/icall/work/ へ展開
mkdir -p "$RUNNER_TEMP/plugins-freshair" && tar --zstd -xf "$ARTIFACTS_DIR/plugins-freshair.tar.zst" -C "$RUNNER_TEMP/plugins-freshair"
FA_DL="$RUNNER_TEMP/plugins-freshair" bash tools/targets/freshair/fetch.sh
SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh                  # baseline (受入 3)
S="tools/targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
objdump -d -M intel "$S" > tools/icall/work/core64_dis.txt
python3 tools/icall/diff/known12_readers.py tools/icall/work/core64_dis.txt "$S" > tools/icall/work/known12_out.txt
python3 tools/icall/diff/lea_index_scan.py tools/icall/work/core64_dis.txt "$S" > tools/icall/work/lea_index_scan.txt
bash tools/icall/diff/lea_index_scan_selftest.sh                     # 負の対照
```

- `lea_index_scan.txt` の先頭行が統計 (命令・式・組の件数)、末尾の `# 集計` が §1〜§3 の表の元。全 1,229 候補の行は `tools/icall/work/` に出る (gitignore 対象のため本 PR には含めない)。
