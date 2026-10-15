# ildsp CreateInstance の native 実行 (#2528 / #3249) 付録

> **正本**: 本付録。分割元は REPORT_CLOSURE.md §7 (行数上限のため移動・内容は変えていない)。

### 7. CreateInstance の native 実行 (#2528 / T-SH-38・受入 1・4 を満たして `Closes`。受入 2 → #3249、受入 3 → #3250)
- 測定 commit: `8f643a8c` (ハーネス `tools/shared/scripts/ildsp_native.c`・照合 `ildsp_native_check.py`)。`b0aa27b3` からの変更は、stdout の行バッファ化、呼び出し前の `call` 行 (実験ごとの wrapper を出す)、checker の timeout 処理のみ。`git diff 8f643a8c HEAD -- tools/shared/scripts` の出力は空 (差分 0)。
- 方式: `block24360_PE.bin` を ImageBase 0x180000000 に VA 通りに敷設 (`ott_native.c` と同じ方式、MAP_FIXED_NOREPLACE)。IAT 73 件のうち 7 件 (GetProcessHeap・HeapAlloc・HeapFree・GetLastError・SetLastError・RtlPcToFileHeader・RaiseException) を ms_abi の C 関数で実装し、残りは名前を記録して 0 を返す thunk (実行時に呼ばれた件数を出力)。HeapAlloc は 0x50000000 から bump で確保 (0 埋め)。`CreateInstance` は MS x64 の関数ポインタで直接呼ぶ。CRT の DllMain・TLS・SEH は走らせない。
- 実行形: **単独** = `ildsp_native <PE> --slot K V` (1 プロセス 1 実験。create の後に slot を 1 回呼ぶ)。**全件** = `ildsp_native <PE>` (同一プロセスで slot 1〜5 を順に呼ぶ。実験ごとに create を呼び直すので、ヒープの確保位置が進む)。
- 照合 (create のみ・`--slot 0 0`): wrapper 0x50000000 → vptr `0x1803dfcf8` (= vtable VA、一致)。`ildsp_native_check.py` は ALL OK (rc 0)。ネガティブコントロール (`--neg-lea`): vptr `0x1803dfd00`、`--neg` は FAIL (rc 1)。
- 測定条件: ASLR 有効・既定の環境変数・4 vCPU の runner。各プロセスは `timeout 15` で囲み、rc 124 = 15 秒で timeout (hang)、rc 139 = SIGSEGV。単独は 14 設定 (slot 1〜3 は rdx 4 種ずつ、slot 4・5 は 1 件) を各 n=6、全件は n=6。1 回の再現は `timeout 15 ildsp_native <PE> --slot K V` (単独) または `timeout 15 ildsp_native <PE>` (全件) を繰り返す。
  - セッションの記号: S1 = round 1 の実装者測定 (16 回)。S2 = round 2 の実装者測定 (`551da801` からビルド)。S3 = round 3 の実装者再測定 (`83fac1b7` からビルド。コードは `8f643a8c` と同じ。load average は未記録)。RV1・RV2・RV3 = round 1・2・3 のレビュー側の報告値 (別環境。本 REPORT では再検算していない)。S2 の load average は 0.2〜1.5。

単独実行の表 (1 プロセス 1 実験・S2 の値。slot 1 は表 7-1、slot 2 v0・v2 の変更範囲はセッションで変わる (注 2)):

| slot | rdx | rc (n=6) | rax (完走時) | 変更範囲 (完走時) | 間接 call 4 件の hook |
|---|---|---|---|---|---|
| 1 | 0・1・2・0xe | 0 と 124 が混在 (表 7-1) | wrapper+0x1310 (表 7-1) | 33 range が中心 (表 7-1) | 0 件 (注 3) |
| 2 | 0 | 0 ×6 | 0 | `[0x31+1, 0x6e+2]` 6/6 (2 range)。S3 は `[0x6e+2]` 6/6 (注 2) | 0 件 |
| 2 | 1 | 0 ×6 | 0 | なし 6/6 | 0 件 |
| 2 | 2 | 0 ×6 | 2 | `[0x35+1]` 6/6 (1 range)。S3 は なし 6/6 (注 2) | 0 件 |
| 2 | 0xe | 0 ×6 | 0 | なし 6/6 | 0 件 |
| 3 | 0 | 0 ×6 | 0x2e | なし 6/6 | 0 件 |
| 3 | 1 | 139 ×6 | call 内で SIGSEGV | — | — |
| 3 | 2 | 139 ×6 | call 内で SIGSEGV | — | — |
| 3 | 0xe | 139 ×6 | call 内で SIGSEGV | — | — |
| 4 | 内部オブジェクト (0x50000320) | 0 ×6 | 0x35 | なし 6/6 | 0 件 |
| 5 | 0 | 0 ×6 | 0 | なし 6/6 | 0 件 |

表 7-1 slot 1 (単独・n=6 × rdx 4 種。セッションごとの観測。hang は rc 124):

| セッション | rdx | hang | 完走 (rc 0) の rax − wrapper | 完走の変更範囲 (range 数 ×件数) |
|---|---|---:|---|---|
| S2 | 0 | 1/6 | +0x1310 ×5 | 33 ×4・34 ×1 |
| S2 | 1 | 1/6 | +0x1310 ×5 | 33 ×4・34 ×1 |
| S2 | 2 | 3/6 | +0x1310 ×3 | 33 ×3 |
| S2 | 0xe | 5/6 | +0x1310 ×1 | 33 ×1 |
| S3 | 0 | 2/6 | +0x1310 ×4 | 33 ×3・34 ×1 |
| S3 | 1 | 2/6 | +0x1310 ×4 | 33 ×3・35 ×1 |
| S3 | 2 | 4/6 | +0x1310 ×2 | 33 ×2 |
| S3 | 0xe | 4/6 | +0x1310 ×2 | 33 ×2 |
| RV3 | 0 | 2/6 | +0x1310 中心 (注 1) | 33 ×3・32 ×1 |
| RV3 | 1 | 1/6 | +0x1310 中心 (注 1) | 3 種 (内訳未記録) |
| RV3 | 2 | 2/6 | +0x1310 中心 (注 1) | 33 ×3・34 ×1 |
| RV3 | 0xe | 3/6 | +0x1310 中心 (注 1) | 33 ×2・34 ×1 |

表 7-2 slot 1 v0 (全件・同一プロセス・n=6。slot 3 v1 は slot 1 v0 の完走後に到達する):

| セッション | slot 1 v0 hang | slot 3 v1 SIGSEGV | slot 1 v0 完走の rax − wrapper | 完走の変更範囲 (range 数) |
|---|---:|---:|---|---|
| S2 | 3/6 | 3/6 | +0x1350・+0x1310・+0x166aa0 (各 1 件) | 34・34・29 |
| S3 | 4/6 | 2/6 | +0x1310 (2 件) | 33・34 |
| RV2 | 2/6 | 4/6 | 未記録 | 未記録 |
| RV3 | 2/6 | 4/6 | +0x1310 (報告) | 未記録 |

- 注:
  1. slot 1 の rax と変更範囲: 完走時の rax は、単独では wrapper+0x1310 (絶対値 0x50001620) がほとんどで、例外は RV3 の報告にある +0x110610 (32 range) の完走で、報告の件数は 1〜2 件と食い違う (再検算していない)。全件では slot 1 v0 の rax が実行ごとに揺れ (表 7-2)、変更範囲の range 数は 29〜35 の間で揺れる。揺れる原因は未確認。ヒープ確保位置が候補だが未検証。
  2. slot 2 の変更範囲 (セッション差): 単独 v0 は S2 `[0x31+1, 0x6e+2]` 6/6、S3 `[0x6e+2]` 6/6、RV2 `[0x6e+2]` 8/8。単独 v2 は S2 `[0x35+1]` 6/6、S3 なし 6/6、RV2 なし (2 回)。全件 v0 は S2 `[0x31+1, 0x6e+2]` 3/3、S3 `[0x30+4, 0x6e+2]` 2/2、RV2 `[0x30+4, 0x6e+2]` 2/2。RV3 は slot 2 の値を REPORT と一致と報告 (内訳未記録)。セッションで一致しない。原因未確認。
  3. 間接 call 4 件 (0x1aedf6・0x1aee04・0x1aee4a・0x1b6f6c): 完走した実行では hook 0 件 (S2・S3 とも)。hang した実行は hook の出力行が出ない。0 件は「この実験で到達しなかった」の意味だけを持ち、到達しない根拠ではない。発火を確認する正の対照は未実施で、#3250 の初手で入れる。どの入力が helper 0x1aedc0 / 0x1b6f4c に入るかは未確定。
  4. ASLR 無効 (`setarch x86_64 -R`) と空の環境 (`env -i`) は、S1 (round 1 の実装者測定) のみ。S2・S3 では再測定しておらず、未検証。
- slot 1 の hang: 単独 (4 rdx × n=6) の件数は S2 10/24・S3 12/24・RV3 8/24、全件の slot 1 v0 は S2 3/6・S3 4/6・RV2 2/6・RV3 2/6。RV1 の単独 slot 1 v0 は 0/4。S1 は 16 回中 9 回。件数はセッションごとに変わり、rdx ごとの偏りも一定しない (1 セッション 6 回では rdx の差は判定できない)。hang は slot 1 の call 内で起きる。原因は未確認。仮説 (未検証): 未初期化値・スタック位置・環境変数長に依存する分岐。負荷の影響は未検証。
- 全件実行 (同一プロセス・n=6): 表 7-2。slot 3 v0 の rax 0x2e は S2・S3 とも一致。slot 4・5 には届かない。
- slot 0 (dtor) は §7.2 で実行済み (#4117)。

### 7.2 slot 0 (dtor) の native 実行 (#4117 / T-SH-97)
- 測定 commit: `19a9c85d2` (ハーネス `ildsp_native.c`: HeapFree を記録・二重解放を検出・`--slot 0 V` で slot 0 を実行。checker は `--create-only` で create のみ照合)。`git diff 19a9c85d2 HEAD -- tools/shared/scripts` の出力は空 (差分 0)。
- 対象: vtable `0x1803dfcf8` の [0] = RVA `0x1aa2e0` (ファイル offset `0x1a96e0`)。逆アセンブルでは `vptr ← 0x1803df0f8` を書き、6 メンバ (+0x10・+0x18・+0x20・+0x208・+0x258・+0x260) それぞれに `call 0x1abdb0` し、最後に inner (0x2f8) と wrapper (0x10) を解放する形。`0x1abdb0` の中身は未同定 (virtual call の thunk に見えるが未確認)。
- 実測 (n=6・各プロセス `timeout 15`・rc 0 ×6・load average 0.13〜0.16・4 vCPU):

| 項目 | 値 |
|---|---|
| 戻り値 rax | 0x1 (6/6) |
| HeapFree 呼び出し | 2 件 (6/6): `0x50000320` (inner, 0x2f8) → `0x50000310` (wrapper, 0x10) |
| 二重解放 | 0 件 (6/6) |
| 未実装 import 呼び出し | 0 件 (6/6) |
| 変更範囲 (`changed`) | なし (dtor は inner の 0x2f8 を書き換えない) |
| 実行前のメンバ | +0x10・+0x18・+0x20・+0x208・+0x258・+0x260 は全て 0 (create 直後) |
| 所要 | 1 プロセス約 3.5 ms |

- 受入 1 の「解放の対象 (inner・配列)」: 解放された 2 ブロックは inner (0x50000320) と wrapper (0x50000310)。メンバ 6 件は create 直後に全て null のため、非 null メンバを解放する経路は**この測定では通っていない**。子 [T-SH-98] #4154 で扱う。
- 受入 2: HeapFree を観測する形に直し、2 回・二重解放 0 件を確認。
- 受入 3: `ildsp_native_check.py` (create のみ) は ALL OK (rc 0)。`--neg` は FAIL (rc 1) のまま。
- 注: 全件実行 (`ildsp_native <PE>`・slot 1〜5) は、既存の表どおり slot 3 rdx=1 で SIGSEGV (rc 139) する。今回の変更で変わっていない。

#### 7.1 slot の役割表 (#3249 / T-SH-53)
- 測定 commit: `3248b5154` (`ildsp_native.c` は slot 1・2 の引数を float で渡すよう修正。`ildsp_native_check.py` ALL OK)。
- 方法: 同じ PE の逆アセンブル (`objdump -d -M intel`) と、単独実行 (`ildsp_native <PE> --slot K V`・1 プロセス 1 実験・`timeout 15`・各 n=6) を突き合わせる。
- 添字の注意: `--slot K V` の V は rdx の値ではなく `rdx_list = {0, 1, 2, 0xe}` の添字 (V=0→rdx 0、V=1→rdx 1、V=2→rdx 2、V=3→rdx 0xe)。slot 4 のみ V=0 で、rdx は内部オブジェクト (0x50000320)。
- 測定: 上の役割表の「単独実行」列が正本 (水準ごとに n=6)。slot 1〜5 の 14 設定 × 各 n=6 = 84 回を、同一 PE (sha256 `f4b23b0f…`)・同一ビルドで実行。load average は測定前後で 0.06〜0.21。所要 4 秒。
- 役割 (this = 配列を持つ wrapper の inner `[wrapper+8]`):

| slot | vtable 先 (RVA) | 実体 (RVA) | 役割 (逆アセンブル) | 引数 (MS x64) | 単独実行 (n=6) |
|---|---|---|---|---|---|
| 1 | 0x1aa370 | 0x161fc0 | `[this+8]` に xmm1 (float) を書き、`[this+0x28]` (= ⌊xmm1 × 定数⌋) 個の 4 byte 配列を 3 本 確保 (`HeapAlloc` 相当の 0x1801ac9b8) して、各要素を 0 で埋める。大きさの設定と初期化 | rdx = 未使用, xmm1 = float (1.0 で実行) | rdx=0 で rc 0 ×6・rax 0x50001620 ×6。rdx=1・2・0xe も同じ (各 rc 0 ×6・rax 0x50001620 ×6)。rdx は結果に影響しない |
| 2 | 0x1aa380 | 0x162760 | rdx の値で switch (`cmp edx,0xe`・jump table 0x162f54) し、各 case で `[this+0x30..0x50]` などの float パラメタ 1 つを xmm2 (float) から書く。`edx > 0xe` は即 return | rdx = case 番号 (0〜0xe), xmm2 = float | rdx=0 で rc 0 ×6・rax 0x5 ×6 (変更 2 件)。rdx=1 で rc 0 ×6・rax 0 ×6 (変更なし)。rdx=2 で rc 0 ×6・rax 0x2 ×6 (変更 1 件)。rdx=0xe で rc 0 ×6・rax 0x1 ×6 (変更 1 件) |
| 3 | 0x1aa390 | 0x162f90 | `edx` が 0 以下なら即 return。それ以外は配列 (`r15`) の要素 (`[r15 + ecx*4]`・`[r15 + ecx*4 + 4]`) を読み、`[this+0x254]` の値で分岐して `[this+0x224]` などを更新する。**引数 5 番目 (stack) の意味は未確定** | rdx = 件数 (`test edx,edx` で判定), r8d = 第 3 引数 (`esi` に保存して stride に使用), r9 = 配列ポインタ (`r15` に保存) | rdx=0 で rc 0 ×6・rax 0x1801aa390 ×6 (変更なし)。rdx=1 で rc 139 (SIGSEGV) ×6。rdx=2 で rc 139 ×6。rdx=0xe で rc 139 ×6 (SIGSEGV は計 18/18。ポインタ引数の未設定が原因と考えられるが未検証) |
| 4 | 0x1aa3a0 | (inline) | `[this+0x28]` 個の要素の配列を `[this+0x10/0x18/0x20]` の 3 本に対して 0 で埋め、`[this+0x244]` 個の要素の配列を `[this+0x258/0x260]` に対して 0 で埋め、最後に `[this+0x284..]` 等を 0 にする。**内部状態のリセット (reset)** | rdx = 内部オブジェクト (0x50000320) | rc 0 ×6・rax 0x1801aa3a0 ×6 (変更 0 件) |
| 5 | 0x1aa470 | (inline) | `xor eax,eax; ret`。何もしない | 未使用 | rc 0 ×6・rax 0 ×6 (変更 0 件) |

- 注:
  1. slot 1 の表示 (`rax` と変更範囲) は全件・単独とも `0x50001620` (wrapper+0x1310) で、§7 の注 1 の揺れは単独の 6 回では出なかった。
  2. slot 2 の変更範囲は rdx ごとに 1 種 (§7 の注 2 のセッション差は今回の 6 回では出なかった)。
  3. slot 3 の 5 番目引数の意味は未確定 (r9 の配列の要素数・内容も未確定)。rdx≠0 の SIGSEGV を解くには、この引数の意味の確定が前提。本 issue の範囲外として子に移す。
  4. 「役割」の列は逆アセンブルの読みであり、C++ の method 名は PE に無いため付けていない。
   5. 表の `rax` は slot 関数の戻り値 (`ildsp_native` の `slot ... rax=`)。`call` 行の `wrapper=0x50000310` は this 引数であり戻り値ではない。slot 3 (rdx=0) と slot 4 の rax は関数 VA の `0x1801aa390`・`0x1801aa3a0` と一致する (d433846e8 で各 n=6 を再測定し一致を確認)。
- 未解決 (本節の範囲外):

| 未解決 | 影響 | 起票先 |
|---|---|---|
| slot 3 の引数 (5 番目・r9 の配列) の意味と、rdx≠0 の SIGSEGV の原因 | slot 3 の役割が「添字付きの配列更新」以上に確定できない | [T-SH-96] #4116 |
| slot 0 (dtor) は未実行 | 受入 2 の一部 | [T-SH-97] #4117 |

未解決 (受入 1・4 の範囲外):

| 未解決 | 影響 | 起票先 |
|---|---|---|
| slot 1–3・5 の役割 (どの method か・引数の意味。呼び出し規約) | 受入 2 | [T-SH-53] #3249 |
| 間接 call 4 件 (0x1aedf6・0x1aee04・0x1aee4a・0x1b6f6c) の到達条件と扱い | 受入 3 | [T-SH-54] #3250 |
| 間接 call hook の正の対照が無い (発火を確認する入力を入れていない。0 件は到達しなかったことの意味のみ) | 受入 3 の結論 | [T-SH-54] #3250 (初手で発火を確認) |
| 非 null メンバ (+0x10・+0x18・+0x20・+0x208・+0x258・+0x260) を helper 0x1abdb0 が解放する経路は未実行 (create 直後は全て null) | 配列の解放の確定 | [T-SH-98] #4154 |
| slot 1 の hang (単独 10/24・12/24・8/24、全件 3/6・4/6・2/6。原因未確認。仮説: 未初期化値・スタック位置・環境変数長。負荷の影響は未検証) | slot 1 の結果を単独で採れない | 追跡 issue なし (PM 判断: 子の起票要否) |
| slot 1 の完走時の rax と変更範囲は、単独・全件とも実行ごとに揺れる (原因未確認。注 1) | slot 1 の出力の定義 | 追跡 issue なし (PM 判断: 子の起票要否) |
| slot 2 v0・v2 の変更範囲がセッションで違う (注 2。原因未確認) | 差分テストの入出力の定義 | 追跡 issue なし (PM 判断: 子の起票要否) |
| slot 3 (rdx=1・2・0xe) の SIGSEGV (単独 18/18 (S2・S3 とも)。全件は slot 3 v1 で 2〜4/6。原因未確認) | slot 3 の入力の扱い。全件は slot 4・5 に届かない | #4178 [T-SH-101] |

### 7.1 slot 3 (vtable 0x1aa390 → 実体 0x162f90) の引数 (#4116 / T-SH-96)
- 測定 commit: `f06912763` (`ildsp_native.c` に `--s3-bufs` を追加。既定経路は変えていない)。素材 fl-win64 (`26.1.7.5653`)。`git diff f06912763 HEAD -- tools/shared/scripts` の出力は空 (差分 0)。
- 逆アセンブル (capstone・静的): 呼び出し規約は `(this=rcx, rdx=frames, r8d=channels, r9=入力 float*, [entry+0x28]=出力 float*)`。`rdx ≤ 0` なら即 return (`0x162f92 jle`)。入力は `r15[rbp*4]` (rbp = frame×ch の添字)、出力は `r12[rbp*4]` で、ch=1 のとき出力は 1 点・ch=2 のとき 2 点書く。第 5 引数は `[rsp+0x120]` を関数先頭で `r12` に退避して読む。
- 内部オブジェクト (`this`=`[w+8]`) の前提 (逆アセンブルから読んだ範囲): `+0x208` (入力 float の base)・`+0x258`・`+0x260` (ring の base)・`+0x10`・`+0x18`・`+0x20` (buffer)・`+0x244` (wrap 長)・`+0x204`・`+0xc4`・`+0x114` (`0x1634xx` の遅延計算で使う)。各フィールドの意味は未確定。
- 実行 (`--slot 3 V --s3-bufs`・単独・1 プロセス 1 実験・`timeout 15`): 入力 0.25・ch=2 の float 配列を張ったうえで、rdx 4 種を V=0〜3 で実行。
  - V=0 (rdx=0): rc 0 (rax=0x1801aa390・変更範囲 14 range)。
  - V=1〜3 (rdx=1・2・0xe): rc 98 (SIGSEGV) を、`+0x244`・`+0x28`・`+0x204` 等を正に設定した後も再現。SIGSEGV は `0x1634bb` (`mulss xmm0, [r8+rdx*4]`・`rdx=0x80000000`) で、直前の `cvttss2si` が NaN 由来の `0x80000000` を返すことが直接原因。
  - 途中の観測: `+0x244=0` のとき `0x163380` の `[rbx+0x164+idx*4]` 累積ループで hang (rc 124 相当)。`+0x28=0` のとき同じ hang。`+0x28=1` で hang は消えた。
- 未確定 (受入 1 の残り): slot 3 は `0x16340e` で `[rbx+rcx*4+0xc4]` と `0x16341c` で `[+0x114]` を自分で書いており、呼び出し前に外から与えた値は上書きされる。`0x1634bb` の分母が 0 になる条件 (どの初期化値が要るか) は未確定。rdx=1 の既定経路 (4 引数) は従来どおり rc 139 のままで、checker は ALL OK。
- 未解決: 引数の意味 (逆アセンブル上の役割) は確定したが、rdx≠0 の SIGSEGV の原因は未確定。`0x16340e` が `+0xc4` を書き換えるため、外から与えた `+0xc4[0]` が 0 のまま残る理由が次の切り分け点。起票先: #4178 [T-SH-101] (本 PR は部分達成のため `Refs #4116`)。
