# REPORT_CI 付録 (T-SH-161 #6184): 計算ジャンプ表の経路を IR に戻す

親: `REPORT_CI.md` §11 (本体は分割移動)。

## 計算ジャンプ表の経路を IR に戻す (T-SH-161 #6184)

結論: 表 0x442000 (k = 0〜16) の 17 経路を `ci_restore_jump_table.py` で `switch` に戻した。`ci_lift.sh` は rc 0 (ALL OK)。§8-2 の FAIL は解消した。

測定 commit: `d7107e33b` (コードを変えた最後の commit)。`git diff d7107e33b HEAD -- tools/shared/lift/ildsp ':!*.md'` は本 PR の commit 時点では空 (差分 0)。

### 11-1. 原因 (逆アセンブルと IR で確認)
- x86: `0x1aef74 cmp r8,0x10` → `0x1aef78 jbe 0x1af070` (n ≤ 16)。0x1af070 で `mov eax,[r9+r8*4+0x442000]`・`add r9,rax`・`jmp r9`。
- 表 k = 0〜16 の飛び先は、どれも `dl` を n バイト書いて `ret` する断片 (全 17 件を逆アセンブルで確認)。例: k=1 `mov byte ptr [rcx-1],dl`、k=10 `mov qword ptr [rax],rdx; mov word ptr [rax+8],dx`。
- RetDec の IR は `icmp ult %arg3, 17` で `dec_label_pc_1801af028` (`ret %arg1`) へ直接抜ける。書込みは IR に無い。

### 11-2. 修復 (`ci_restore_jump_table.py`)
- 表の飛び先を x86 から逆アセンブルし、書込みを `(オフセット, 幅)` で取り出す。`rcx` 基準は `k + disp`、`rax` 基準は `disp` (`rcx = arg1 + n`・`rax = arg1` は 0x1af085・0x1af088 で確認)。
- `function_1801aef60` の `br` を `ci_jt` (`switch i64 %arg3`) に差し替え、case k に書込みを置く。`rdx` の値は `%ci_jt_v` (`urem i32 %arg2,256` を 0x0101.. 倍) で、x86 の `imul r9,rdx` と一致。
- 表の飛び先の define 9 件 (呼び出し元が無い) は IR から外す。
- 検査: 書いた IR の case ごとの `(offset, 幅)` を x86 と照合する (`check_ir`)。34 件すべて一致。

### 11-3. 検証
- 実行: `FL_WIN64_DIR=<fl-win64> RETDEC_BIN=<retdec> EMSDK_ENV=<emsdk_env.sh> bash tools/shared/lift/ildsp/ci_lift.sh` (測定 commit `d7107e33b`・4 core)。
  | 項目 | 値 |
  |---|---|
  | `ci_lift.sh` 実行時間 (`time`) | 3.082 s (rc 0・直前の 1 回目は 4.145 s) |
  | census | `計算ジャンプ表の経路 (復元後 IR): 範囲外の define 0 件・orphan 0 件・case ラベル 16/16`・`ALL OK` |
  | 修復の検査 | `check: k=1..16 の書込み (offset, 幅) が x86 と一致 (34 件)` |
- 実行: `EMSDK_ENV=<emsdk_env.sh> bash tools/shared/lift/ildsp/ci_link.sh` → **rc 0**・wasm-ld rc 1 (期待どおりの未解決)。14.8 s (`emcc` のキャッシュ再生成を含む)。未解決は IAT 10 種と呼び出し先 2 種のみ。
- 修復前の値との比較: 未解決の総行数は §9-2 の 149 行から 147 行 (GetLastError 53→51・HeapFree 52→50)。RetDec の関数 `ret` 経路を `switch` に置いた結果、重複参照の数が変わった。増減の原因はこの run では確かめていない。

### 11-4. ネガティブコントロール
| 名前 | 壊し方 | 結果 |
|---|---|---|
| NC4 drop-store | 復元後 IR の `ci_jt_10` の `store i16` 1 件を削る | `x86 [(0, 8), (8, 2)] != IR [(0, 8)]`・FAIL (rc 1) |

### 11-5. 既知の制約
- 表の飛び先の 9 define の除去は「呼び出し元が無い」ことを IR の call 参照で確かめた。表の値そのもの (RVA) は画像から読んでいる。画像が変わると表も変わるので、このパスは FL_WIN64 の 1 版にだけ当たる。
- 修復は RetDec の段を特定していない (§8-4 と同じ未確認)。RetDec 内部でどの段が経路を落としたかは未確認。
- `ci_link.sh` の意味確認 (native との差分) は未実施 (#3320)。

