# 付録: icall #2225 (ICALL-65) — SlateCore 符号化表と OTT api-set 表 `0x18026c9f0` の形式比較

> 親: #2197 (ICALL-62)。前付録: `REPORT_APPENDIX_2198.md`。受入条件 4 (OTT api-set 表との形式比較)。
> 初版 (PR #2239) は SlateCore 側の終点が未確定のため entry 数を判定しなかった。本版 (§2.5) は、両 PE の CRT 初期化関数のループ終点から T1/T2 の終点を静的に確定し、entry 数を比較した。
> T1/T2 の動的な最大 index は #2226 (ICALL-66)、群 B〜I の原因は #2231 (ICALL-67)・#2247 (ICALL-68)。

## 1. 結論

- **cookie と decode 規則は一致**: SlateCore `0x18125eaa8` と OTT `0x180260ce0` の cookie はどちらも静的既定 `0x2b992ddfa232` (rot = cookie & 0x3f = 50)。decode は両者とも `ror(entry ^ cookie, cookie & 0x3f)`。
- **表の対応 (実測)**: 両 PE は同じ形の遅延解決ディスパッチャ (OTT `0x1801c38c8`・SlateCore `0x18105de80`) を持ち、2 表を引く。T1 = module handle 表 (index = module id、`[r14+rsi*8+T1]`)、T2 = encoded 関数ポインタ表 (index = function id = `ecx`、`[r14+r15*8+T2]`)。OTT の「api-set 表 `0x18026c9f0`」は T2 に当たる。
  OTT は T1 `0x18026c950`・T2 `0x18026c9f0`、SlateCore は T1 `0x181307100`・T2 `0x1813071a0`。
- **entry 数は一致 (T1 20・T2 34)** (§2.5):

  | 表 | OTT | SlateCore | 根拠 (どちらの PE も同じ形) |
  |---|---|---|---|
  | T1 (module handle) | `0x18026c950`〜`0x18026c9f0` = 20 | `0x181307100`〜`0x1813071a0` = 20 | 終了関数のループ終点 = T2 起点。`module_names` 配列の有効ポインタ 20 件 |
  | T2 (encoded 関数ポインタ) | `0x18026c9f0`〜`0x18026cb00` = **34** | `0x1813071a0`〜`0x1813072b0` = **34** | 初期化関数の `rep stosq` 個数 `and ecx, 0x22` = 34 |

  - **仮定 (明記)**: 初期化・終了関数のループ終点を表の宣言サイズとみなす (コンパイラが `sizeof(table)/8` から生成した定数と読む。シンボルが無いため名前の対応 `try_get_function` 等は形からの推定)。
    この仮定と矛盾する材料は無い: call site が渡す function id の最大は両 PE とも 29 (< 34)、module id の最大は 18 (< 20)。
  - SlateCore の `0x1813072b0` (既知 12 slot の 1 つ) は T2 の終点の次の番地。OTT も T2 終点 `0x18026cb00` の後ろに個別 slot (`0x18026cb40`・`0x18026cb88`) が続く。
- **配置も一致 (静的状態)**: T1・T2 は両 PE とも `.data` の **zero-fill 域** にあり、ファイル上の生値は 0。
- **OTT 側の訂正 (実測)**: OTT の api-set 表は **34 entry** で、`tools/ott/crtinit/ott_crt.c` の `APISET_N` と `crtinit/REPORT.md` の「32 entry」は 2 entry 不足。`ott_crt_init_tables` は index 32・33 (`0x18026caf0`・`0x18026caf8`) に cookie を書かない。
  実行経路への影響は未発生とみられる (call site の最大 function id は 29。ただし index 32・33 を引く経路が無いことの動的確認はしていない)。修正は本 issue の範囲外 (wasm 側の初期化変更を含まない) で、#2412 (ICALL-76) に移した。
- **既知 12 slot は T1/T2 のどちらにも入らない**: #2197 §2.2 の「12 中 7 件が T1/T2 の index 域内」は index の上限が無い前提の判定だった。上限確定後は、`0x1813068d0`〜`0x181306910` の 5 件は T1 起点未満、`0x1813072b0`・`0x1813073f0`〜`0x181307418` の 7 件は T2 終点以降で、12 件すべて表の外。個別 slot (OTT の `0x18026c028` ほか 4 件に相当) と読むのが自然。
- **harness の副次所見 (実測)**: `SLOT_ENC_INIT=1` は `slot_trace.c` の `enc[]` (既知 12 slot) にだけ cookie を敷く。T2 の 34 entry は 0 のままで、ディスパッチャが T2 を読むと decode(0) = `ror(cookie, 50)` (非 0) になる。OTT の `ott_crt_init_tables` は T2 を cookie で敷いている点が異なる。#2247 の「`SLOT_ENC_INIT` 依存の判定」の材料として渡す。
- **訂正**: `tools/ott/ACCEPTANCE_CAB137_CAB138.md` §4.3 の「api-set 表 0x18026c9f0 のファイル生値は非ゼロ 32/32」は誤り。表は `.data` の raw 範囲外にあり、ファイル上に生値が無い (根拠は §2.4)。`tools/ott/crtinit/REPORT.md` §3 の「全 0」が正しい。ACCEPTANCE 文書は本 PR では書き換えず、PM 判断に残す。

## 2. 実測

### 2.1 測定条件

- スクリプト (`dispatcher_ids.py` 新規・`ott_apiset_cmp.py` の entry 数 32 → 34) の測定 commit: `5f6547c2` (コード commit)。§2.3・§2.5 の出力は、この commit のクリーンな tree で実行した。
- `slot_trace` の測定 commit: `14150b46` (main の先頭)。`slot_trace.sh`・`slot_trace.c`・`tools/ott` は #2239 の測定 commit `c98786d1` から変更なし。
  - `git diff c98786d1 14150b46 --stat -- tools/icall/diff/slot_trace.sh tools/icall/diff/slot_trace.c tools/ott` の出力: 空 (差分 0)。
  - `git diff 5f6547c2 HEAD --stat -- tools/icall/diff tools/ott` の出力: 空 (差分 0。REPORT と DOC_MAP の commit のみ)。
- 素材: `plugins-freshair` (`FA_DL` に展開)・`work-icall` (リポジトリ直下に展開)・`analysis-ott-binaries` (`OTT_vst2_win64.dll`)。
- 再現 (既定条件): `SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh`。
  - 所要: real 12.559 s / user 11.040 s / sys 1.873 s。load average (uptime の 1 分値) 0.93 (開始時 12:18:17) → 0.94 (終了時 12:18:29)。
  - 旧測定 (`7d15ceab`): real 13.191 s / user 11.032 s / sys 1.916 s。load average 1.18。
- `dispatcher_ids.py` の所要: SlateCore real 29.984 s、OTT real 3.736 s (load average 0.77。終了時 12:28:26)。

### 2.2 slot_trace 集計 (既定条件・再現)

`funcs 131 exit {rc=0: 69, rc=124: 1, rc=95: 53, rc=98: 8}`、zero-fill VA 10、既知 12 hit 3・miss 9。
#2198 のベースライン (c2f52068)・#2239 の再測定 (c98786d1) と完全一致。

zero-fill VA のうち T1/T2 の範囲 (§2.5) に入るのは `0x1813071c8` (T2 index 5)・`0x1813071d0` (T2 index 6) の 2 件で、RIP はどちらもディスパッチャの T2 参照 `0x18105deaf` (ACC 行数 1 と 6)。
残りの 8 件 (`0x1813073f0`・`0x181307418` ほか) は T1/T2 の外で、ACC の RIP はディスパッチャ (`0x18105de80`〜`0x18105e055`) の外にある。

### 2.3 形式比較 (PE 直読み)

| 項目 | OTT `OTT_vst2_win64.dll` | SlateCore `SlateCore.core_64` |
|---|---|---|
| security cookie | VA `0x180260ce0` = `0x2b992ddfa232` | VA `0x18125eaa8` = `0x2b992ddfa232` |
| rot (cookie & 0x3f) | 50 | 50 |
| decode 式 | `ror(entry ^ cookie, cookie & 0x3f)` | `xor reg,[cookie]` → `ror reg,cl` (cl = 50) |
| T1 (module handle 表) | `0x18026c950`・20 entry | `0x181307100`・20 entry |
| T2 (encoded 関数ポインタ表) | `0x18026c9f0`・**34 entry** (REPORT の 32 は不足) | `0x1813071a0`・**34 entry** |
| 配置 | `.data` zero-fill (raw end `0x180269000`・virt end `0x18026cbcc`) | `.data` zero-fill (raw end `0x18128f400`・virt end `0x18130a000`) |
| 生値 | raw 範囲外 (zero-fill) のためファイル上に無し | T1・T2 とも zero-fill のためファイル上に無し |
| 個別 slot | `0x18026c028`・`0x18026c388`・`0x18026cb40`・`0x18026cb88` も zero-fill | 既知 12 (`0x1813068d0`〜`0x181307418`) も zero-fill |

- 「encoded 表 = zero-fill に enc(NULL)=cookie を敷いて初期化」という形式は、両者で同じ。OTT は `ott_crt_init_tables` が、CRT 自身の初期化関数 (OTT `0x1801c43a4`・SlateCore `0x18105ea78`) が T2 を cookie で敷く処理に相当する。
  SlateCore の harness (`SLOT_ENC_INIT=1`) は T2 を敷かず、既知 12 slot だけを敷く (§1)。
- OTT の `enc(NULL)` は `rol(0,14) ^ cookie` で `cookie` に等しい (`crtinit/REPORT.md` と一致)。

#### 実 DLL の出力 (`ott_apiset_cmp.py`・`5f6547c2` で実行。素材 `analysis-ott-binaries` の `OTT_vst2_win64.dll`)

```
cookie VA 0x180260ce0 = 0x2b992ddfa232 (rot 50) [raw] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc
entry[ 0] VA 0x18026c9f0 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[ 1] VA 0x18026c9f8 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[ 2] VA 0x18026ca00 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[ 3] VA 0x18026ca08 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[ 4] VA 0x18026ca10 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[ 5] VA 0x18026ca18 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[ 6] VA 0x18026ca20 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[ 7] VA 0x18026ca28 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[ 8] VA 0x18026ca30 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[ 9] VA 0x18026ca38 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[10] VA 0x18026ca40 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[11] VA 0x18026ca48 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[12] VA 0x18026ca50 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[13] VA 0x18026ca58 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[14] VA 0x18026ca60 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[15] VA 0x18026ca68 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[16] VA 0x18026ca70 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[17] VA 0x18026ca78 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[18] VA 0x18026ca80 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[19] VA 0x18026ca88 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[20] VA 0x18026ca90 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[21] VA 0x18026ca98 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[22] VA 0x18026caa0 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[23] VA 0x18026caa8 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[24] VA 0x18026cab0 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[25] VA 0x18026cab8 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[26] VA 0x18026cac0 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[27] VA 0x18026cac8 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[28] VA 0x18026cad0 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[29] VA 0x18026cad8 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[30] VA 0x18026cae0 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[31] VA 0x18026cae8 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[32] VA 0x18026caf0 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
entry[33] VA 0x18026caf8 [zero-fill (ファイル外・0 固定。読取りではない)] セクション .data: raw 0x18025f000-0x180269000, virt 0x18025f000-0x18026cbcc → decode 対象外
```

### 2.4 事実の根拠: セクションヘッダの raw end と表の VA

「api-set 表は zero-fill 域にあり、ファイル上の生値は 0」の根拠は、次の PE セクションヘッダの値との比較である (実測値の出力ではない)。

- OTT の `.data`: raw end `0x180269000` (`PointerToRawData + SizeOfRawData` 相当の VA)、virt end `0x18026cbcc`。
- api-set 表の起点 `0x18026c9f0` (8 B × 34 = 終点 `0x18026cb00`) は raw end `0x180269000` より後ろで、終点 `0x18026cb00` は virt end の内側。
- よって表の全 entry はファイルの raw 範囲の外にあり、ファイル上の生バイトを持たない。

`tools/icall/diff/ott_apiset_cmp.py` は、entry ごとに VA の区分 (`raw` / `一部 zero-fill` / `zero-fill` / `セクション外`)・セクション名・raw 範囲・virt 範囲を表示する。`zero-fill` と `セクション外` は decode せず、0 固定の値として扱わない。集計行は出さない。
以前の REPORT・検収文書にあった「非ゼロ 32/32」が、どの読み方に由来するかは未確認 (前 run の読出し手順は残っていない)。`tools/ott/ACCEPTANCE_CAB137_CAB138.md` §4.3 の訂正は、本節のセクションヘッダとの比較を根拠とする。

### 2.5 T1/T2 の終点と entry 数 (静的・`dispatcher_ids.py`)

`tools/icall/diff/dispatcher_ids.py` は次を出す: ディスパッチャへの `call` を `.pdata` の関数境界ごとに線形逆アセンブルして拾い、直前の `ecx` 即値 (function id) と r8/r9 の module id 列を集める。
T1/T2 の起点を `lea` で参照する関数 (CRT の初期化・終了関数) の逆アセンブル全体と、`module_names` 配列の有効ポインタ数も出す。

読み取れること (どちらの PE も同じ):

- **T2 の終点と個数**: 初期化関数が `lea rdi,[T2]`・`lea rax,[T2 の終点]` で範囲を取り、`rax = [cookie]` を `rep stosq` で `ecx` = `0x22` 個書く。`0x22` = 34。範囲 (終点 − 起点) / 8 とも一致する (OTT `0x110 / 8`・SlateCore `0x110 / 8`)。
- **T1 の終点と個数**: 終了関数が `lea rbx,[T1]` から 8 B ずつ進み、`lea rax,[T2 の起点]` と等しくなるまで `FreeLibrary` (相当) を呼ぶ。範囲 = T2 起点 − T1 起点 = `0xa0` = 20 entry。
  ディスパッチャが T1 とともに引く `[r14+rsi*8+module_names]` の配列 (OTT `0x18021e500`・SlateCore `0x181134720`) も、有効ポインタが 20 件で終わる (モジュール名は両 PE で同じ 20 本。index 0 = `api-ms-win-core-datetime-l1-1-1`・index 19 = `user32`。名前の行は上の出力では省略)。
- **call site**: ディスパッチャへの call は OTT 30 件・SlateCore 31 件。function id (`ecx`) の最大は両 PE とも 29 (`0x1d`)、module id の最大は 18。どちらも表の個数 (34・20) の範囲内で、矛盾しない。
  function id と module id の対応も同じ (例: id 0x1c・0x1d は module 18、id 0x1a・0x1b は module 9、id 5・6 は module 1)。同じ CRT の enum を使っていると読める。

実出力 (`5f6547c2`・`call` 行と `module_names` 行は省略。全文は `dispatcher_ids.py` の再実行で得る):

SlateCore (`python3 tools/icall/diff/dispatcher_ids.py <SlateCore.core_64>`):

```
call site 数: 31
T2 function_id: 即値 31 件・distinct 20・最大 29 → T2 は少なくとも 30 entry
T1 module_id (call site が渡す列): distinct [0, 1, 3, 4, 6, 7, 9, 16, 18]・最大 18 → T1 は少なくとも 19 entry
T1/T2 起点を lea で参照する関数 0x18105ea78:
  0x18105ea78: mov qword ptr [rsp + 8], rdi
  0x18105ea7d: lea rdi, [rip + 0x2a871c]  # 0x1813071a0
  0x18105ea84: lea rax, [rip + 0x2a8825]  # 0x1813072b0
  0x18105ea8b: cmp rax, rdi
  0x18105ea8e: mov rax, qword ptr [rip + 0x200013]  # 0x18125eaa8
  0x18105ea95: sbb rcx, rcx
  0x18105ea98: not rcx
  0x18105ea9b: and ecx, 0x22
  0x18105ea9e: rep stosq qword ptr [rdi], rax
  0x18105eaa1: mov rdi, qword ptr [rsp + 8]
  0x18105eaa6: mov al, 1
  0x18105eaa8: ret 
T1/T2 起点を lea で参照する関数 0x18105eaac:
  0x18105eaac: push rbx
  0x18105eaae: sub rsp, 0x20
  0x18105eab2: test cl, cl
  0x18105eab4: jne 0x18105eae5
  0x18105eab6: lea rbx, [rip + 0x2a8643]  # 0x181307100
  0x18105eabd: mov rcx, qword ptr [rbx]
  0x18105eac0: test rcx, rcx
  0x18105eac3: je 0x18105ead5
  0x18105eac5: cmp rcx, -1
  0x18105eac9: je 0x18105ead1
  0x18105eacb: call qword ptr [rip + 0x6579f]  # 0x1810c4270
  0x18105ead1: and qword ptr [rbx], 0
  0x18105ead5: add rbx, 8
  0x18105ead9: lea rax, [rip + 0x2a86c0]  # 0x1813071a0
  0x18105eae0: cmp rbx, rax
  0x18105eae3: jne 0x18105eabd
  0x18105eae5: mov al, 1
  0x18105eae7: add rsp, 0x20
  0x18105eaeb: pop rbx
  0x18105eaec: ret 
module_names (0x181134720) の連続する有効ポインタ: 20 件 (終端 = 0x1811347c0)
T1 起点 0x181307100 と T2 起点 0x1813071a0 の差: 0xa0 B = 20 entry (8 B)
```

OTT (`python3 tools/icall/diff/dispatcher_ids.py <OTT_vst2_win64.dll> 0x1801c38c8 0x18026c950 0x18026c9f0 0x18021e500`):

```
call site 数: 30
T2 function_id: 即値 30 件・distinct 21・最大 29 → T2 は少なくとも 30 entry
T1 module_id (call site が渡す列): distinct [0, 1, 3, 4, 6, 7, 8, 9, 16, 18]・最大 18 → T1 は少なくとも 19 entry
T1/T2 起点を lea で参照する関数 0x1801c43a4:
  0x1801c43a4: mov qword ptr [rsp + 8], rdi
  0x1801c43a9: lea rdi, [rip + 0xa8640]  # 0x18026c9f0
  0x1801c43b0: lea rax, [rip + 0xa8749]  # 0x18026cb00
  0x1801c43b7: cmp rax, rdi
  0x1801c43ba: mov rax, qword ptr [rip + 0x9c91f]  # 0x180260ce0
  0x1801c43c1: sbb rcx, rcx
  0x1801c43c4: not rcx
  0x1801c43c7: and ecx, 0x22
  0x1801c43ca: rep stosq qword ptr [rdi], rax
  0x1801c43cd: mov rdi, qword ptr [rsp + 8]
  0x1801c43d2: mov al, 1
  0x1801c43d4: ret 
T1/T2 起点を lea で参照する関数 0x1801c43d8:
  0x1801c43d8: push rbx
  0x1801c43da: sub rsp, 0x20
  0x1801c43de: test cl, cl
  0x1801c43e0: jne 0x1801c4411
  0x1801c43e2: lea rbx, [rip + 0xa8567]  # 0x18026c950
  0x1801c43e9: mov rcx, qword ptr [rbx]
  0x1801c43ec: test rcx, rcx
  0x1801c43ef: je 0x1801c4401
  0x1801c43f1: cmp rcx, -1
  0x1801c43f5: je 0x1801c43fd
  0x1801c43f7: call qword ptr [rip + 0x1df83]  # 0x1801e2380
  0x1801c43fd: and qword ptr [rbx], 0
  0x1801c4401: add rbx, 8
  0x1801c4405: lea rax, [rip + 0xa85e4]  # 0x18026c9f0
  0x1801c440c: cmp rbx, rax
  0x1801c440f: jne 0x1801c43e9
  0x1801c4411: mov al, 1
  0x1801c4413: add rsp, 0x20
  0x1801c4417: pop rbx
  0x1801c4418: ret 
module_names (0x18021e500) の連続する有効ポインタ: 20 件 (終端 = 0x18021e5a0)
T1 起点 0x18026c950 と T2 起点 0x18026c9f0 の差: 0xa0 B = 20 entry (8 B)
```

## 3. 再現

```
bash tools/targets/freshair/fetch.sh     # FA_DL=$RUNNER_TEMP/plugins-freshair を指定して展開
SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh
python3 tools/icall/diff/ott_apiset_cmp.py <OTT_vst2_win64.dll>   # <OTT_vst2_win64.dll> = [ANALYSIS-PLUGINS] の ott/binaries/OTT_vst2_win64.dll
python3 tools/icall/diff/dispatcher_ids.py <SlateCore.core_64>
python3 tools/icall/diff/dispatcher_ids.py <OTT_vst2_win64.dll> 0x1801c38c8 0x18026c950 0x18026c9f0 0x18021e500
```

- OTT の DLL の所在は `docs/REFERENCES.md` の `[ANALYSIS-PLUGINS]` (`ott/binaries/`)。Actions では `oc_artifacts: analysis-ott-binaries` で取得する (`docs/WORKFLOW.md` §11)。
- `SlateCore.core_64` は `fetch.sh` が `tools/targets/freshair/work/win/Fresh Air/.../` に展開する。`dispatcher_ids.py` は capstone と pefile を使う (agent-setup の venv にある)。
- `ott_apiset_cmp.py` は cookie `0x180260ce0`・api-set 表 `0x18026c9f0` (34 × u64) を読み、`ror(entry ^ cookie, cookie & 0x3f)` で decode して出力する。zero-fill は decode しない (§2.4)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| T1/T2 の動的な最大 index (`slot_trace` の ACC を index 付きで記録) と静的な終点 (T1 20・T2 34) の差 | #2226 の受入条件 2 (静的な終点・entry 数は本付録 §2.5 で確定) | #2226 (ICALL-66) |
| `SLOT_ENC_INIT=1` が T2 の 34 entry を敷かない (§1)。群 C の `SLOT_ENC_INIT` 依存の判定材料 | #2247 の受入条件 5 | #2247 (ICALL-68) |
| 既知 12 slot が読まれる表の特定 (12 件すべて T1/T2 の外。個別 slot と読むのが自然) | #2224 の受入条件 | #2224 (ICALL-64) |
| OTT `ott_crt.c` の `APISET_N` 32 → 34 と `crtinit/REPORT.md` の「32 entry」の訂正 (index 32・33 を引く経路が無いことの動的確認を含む) | OTT の crtinit | #2412 (ICALL-76・本 PR で起票) |
| `tools/ott/ACCEPTANCE_CAB137_CAB138.md` §4.3 の「非ゼロ 32/32」の訂正 | 文書の誤記 (OTT の検収文書) | 本 PR 外。PM 判断 |
| SlateCore 側の既知 12 slot が zero-fill である理由 (初期化の主体) | #2231 の受入条件 | #2231 (ICALL-67) |
