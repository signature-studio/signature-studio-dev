# 付録: icall #3136 (ICALL-86) — SlateCore.core_64 の lea 基底の添字参照の静的網羅 (5 件 0x1813068d0〜0x181306910)

> 親: #2224 (ICALL-64)。前付録: `REPORT_APPENDIX_2224.md` (§2.2 の (1)、§2.3 の (2) について SlateCore 上の出力が未取得だった件・§5 の残件)。
> **状態: 再測定待ち。旧測定の数値は撤回する。** review 5525932625 の B1 (分岐先の 0x 無し形式が線形区間の境界にならない) と B2 (流れ非依存の基底で「届かない」と判定) は、コードを直した (下記 §4)。修正後の再測定 (§1・§3 の全数値、方式別件数、候補の表、受入 3 の baseline) は、素材 `work-icall`・`plugins-freshair` が必要。本 run では `$ARTIFACTS_DIR` に `fl-win64` しか無く未実施。
> 測定 commit: 未定 (再測定を行った commit で更新する)。旧測定の commit は `e1f253c2` (`git diff e1f253c2 HEAD -- tools/icall/diff tools/targets/freshair` は非 0 行になった)。
> 走査: `tools/icall/diff/lea_index_scan.py`。負の対照: `tools/icall/diff/lea_index_scan_selftest.sh` (合成入力・素材不要)。

## 1. 結論

- **旧測定の結論は撤回する。** 旧測定 (`e1f253c2`) の「届かないと示せた 204 件」は、分岐先の 0x 無し形式 (`4020 <sym+0x..>`) を境界として拾えていなかった (B1) ことと、流れ非依存の基底を「届かない」に使った (B2) ことに依る。旧数値 (1,229・204・1,025・25・99・901) は再測定まで無効。§3 の表は旧出力のまま残すが、読まないこと。
- **コードの修正 (本 commit)**: B1 は `JT_OP` で分岐先を 0x の有無を問わず読む。B2 は、流れ非依存の基底 X からの候補を「届き得る (基底が流れ非依存)」に限り、「届かない」にしない。方式別 (線形・流れ非依存) の件数は `# 方式別` 行に出す。
- **負の対照**: `lea_index_scan_selftest.sh` に B1 (`je <sym>` の分岐先) と B2 (入口由来の経路を含む基底) の 2 件を追加。旧コード (`e1f253c2`) では 2 件とも FAIL、修正後は 5/5 PASS。
- **未実施 (素材不足)**: SlateCore.core_64 の再走査 (受入 1・2)、候補の表 (B3)、受入 3 の baseline。`fl-win64` のみ取得。`work-icall`・`plugins-freshair` は本 run に無い。PR 本文に `oc_artifacts: work-icall plugins-freshair` を追記した (次の起動で取得される)。
- 5 件に届く読出しが無いことは、再測定まで示せない。

## 2. 測定条件 (旧測定 `e1f253c2`・撤回)

- 素材: `work-icall` → `tools/icall/work/` (展開 22 s)。`plugins-freshair` → `$RUNNER_TEMP/plugins-freshair` → `FA_DL=... bash tools/targets/freshair/fetch.sh` (`win: 17 files, factory .epf: 8, mac: 0 files`)。`fl-win64` は本測定で使わない。
- 逆アセンブル: `objdump -d -M intel SlateCore.core_64` → `tools/icall/work/core64_dis.txt` (4,553,159 行・real 3.8 s)。
- 前付録の (1)(2) (SlateCore 上): `known12_readers.py` real 14.3 s、出力 57 行。(1) は既知 12 を指す直接参照 33 行のうち、5 件 (`0x1813068d0`〜`0x181306910`) は 10 行 (前付録 §2.2 の表と一致)。(2) の候補は 22 行 (前付録 §2.3 の表の命令と一致)。
- 走査: `lea_index_scan.py` real 20.3 s (load 0.54→0.67・単一プロセス)。
- baseline: `slot_trace.sh` real 11.8 s (user 11.0 s・load 0.56→0.63)。

## 3. 結果 (旧測定 `e1f253c2` の出力。撤回・再測定後に差し替える)

判定は、添字 I の値域 (線形区間での最後の定義から分類) と n = (slot − X − disp)/sc の組で決める。B2 の修正後は、流れ非依存の基底の候補はすべて「届き得る」に移る (旧表の「届かない」は、流れ非依存の候補を含むため無効)。

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
- `c181072590` (§3.2 の表の最終行) は、pdata 外の推定チャンク (走査の key `c` = int3 直後の推定開始) であり、確定した関数 VA ではない。
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

- 負の対照 (`bash tools/icall/diff/lea_index_scan_selftest.sh`・5/5 PASS): 正 = 「lea 基底 0x1813068c0 + rdx*8 + 0x10」は 0x1813068d0 に添字 0 で届く (届く・定数一致)。負 1 = disp を 0x11 に壊すと候補 0 件。負 2 = 添字を 1 にすると「届かない・定数不一致」。負 3 = `je 180001011 <f+0x11>` (0x 無し) の分岐先が境界になり、011 の候補は「届き得る」(旧コードは「届かない」で FAIL)。負 4 = 入口由来の経路を含む基底 (rdx の定義が lea だけ) は「届き得る」(旧コードは「届かない」で FAIL)。
- 原文の検算: §3.2 の `18106e98c` は、raw 行の `lea r8` (18106e975) と読出し (18106e98c) の組で確認した (上記)。
- 表 A・B の判定が食い違う理由: 前付録 §2.3 は `18103ce30` の直接 call 5 件の引数 (fn id 0〜4・module id 0〜2) から届かないとした。本走査は関数内の定義だけを使うため、この前提を使えない。両者は別の前提に基づく。
- 限界:
  - 基底 X は、線形区間 (分岐先・ret/jmp/int3/ud2/hlt の直後で破棄) の lea 直値、または関数内の全定義が lea-rip の場合の集合に限る。`add`/`sub` で進めた基底は未追跡。
  - 流れ非依存の X (全定義が lea-rip の集合) は、入口由来の経路 (引数レジスタ等) を排除できない。判定は「届き得る」に限り、「届かない」にしない (B2 の修正)。方式別の件数は `# 方式別` 行。
  - 添字の値域は、線形区間での最後の定義から分類する。分岐先は `JT_OP` で 0x の有無を問わず読む (B1 の修正)。直接分岐の先が全て拾えていることを前提にする。
  - 間接ジャンプの先は解析していない (直前が ret/jmp の命令の次を区間の先頭とする)。間接分岐の先から入る経路は、基底・添字の値を追えない。
  - 関数入口の引数レジスタ (rcx・rdx・r8・r9 等) は、呼出し元の値を持たない (値域未確定)。
  - 別アルゴリズムによる検算は未実施 (レビュー側に委ねる)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 値域未確定の 1,000 件 (§3.3 の 99 件・§3.4 の 901 件) の添字上限 (sar・add・mov・入口由来の定義) | 5 件に届くかの判定。届き得る 25 件 (§3.2) の実行到達 | #3089 (ICALL-85・open)。件数と再現コマンドをコメントで渡す |
| 表 A・B (`18103ce30` の 5 命令) の「届かない」は呼出し元の値域に依る | 関数内の走査では届き得る。判定の根拠 | #3089 (同上)。前付録 §2.3 の記述は変えない |
| setter 3 件 (`18103d374`・`1810553c8`・`181055858`) の終端 (前付録 §2.2 (b)) | 関数形の裏取り | #2224 (親に残す) |
| 再測定: B1・B2 修正後の全数値 (§1・§3)、方式別件数、候補の表 (B3)、受入 3 の baseline | 本 run で `work-icall`・`plugins-freshair` が無く未実施。この表の結論は撤回のまま | 本 PR (#3165)。`oc_artifacts: work-icall plugins-freshair` を本文に追記済みで、次の起動で取得する |

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

- `lea_index_scan.txt` の先頭行が統計 (命令・式・組の件数)、末尾の `# 集計` と `# 方式別` が §1〜§3 の表の元。全候補の行は `tools/icall/work/` に出る (gitignore 対象)。
- 候補の表 (B3・再測定の後に commit): 先頭行 `自動生成: <cmd>` の TSV を `tools/icall/REPORT_APPENDIX_3136_candidates.tsv` に置く。`<cmd>` は `lea_index_scan.py` の出力から候補行 (`#` で始まらない行) を取り出す `grep -v '^#' tools/icall/work/lea_index_scan.txt` 。列は VA・関数キー・方式・X・disp・sc・基底・添字・命令・判定・区分・理由・n・添字の定義・アクセス。
