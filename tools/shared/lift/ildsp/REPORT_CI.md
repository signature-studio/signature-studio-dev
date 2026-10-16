# ildsp GeneralPitchShifter_CreateInstance 単独 closure の RetDec 入力と census (T-SH-62 #3300)

親: #2529 (T-SH-39)。範囲縮小の経緯は #3300 本文。wasm 化は [T-SH-65] #3318、native 差分は [T-SH-66] #3320。

既知類型との関係: DEFECTS D9 と同型 (fe)。検出信号 (`jmp reg` の直前が `lea reg,[rip+…]; mov eax,[reg+idx*4]; add reg,rax`) が一致する。RetDec の IR は計算ジャンプ表の経路 (n = 1〜16) を落としている (§2-2 (b))。入力作成と census のみ。wasm 化と差分は未実施。
測定 commit: `eb6f0e1c7` (#3300 時点の closure 入力作成の測定。本 PR の数値の根拠は下の §7 の `56ec5cf11`)。`git diff eb6f0e1c7 HEAD -- tools/shared/lift/ildsp ':!*.md'` は 24 ファイルの差分があり、差分 0 ではない。

## 結論 (1 行)
closure は 36 関数・961 命令・間接 call 10 件で、RetDec の範囲入力と IR の define 検査は通る。ただし closure は条件分岐と計算ジャンプの先を辿らず、範囲外の直接呼び出し先 1 件が IR に declare のみで残る (§2-2 (a))。IR は計算ジャンプ表の経路 (n = 1〜16) を落とし、その書き込みは IR に無い (§2-2 (b))。baseline 時点の census はこれを検出しなかったが、§8-2 で検出器を追加した (現在は FAIL で検出)。wasm 化 (#3318) と native 差分 (#3320) が残る。

## 1. 再現
```
FL_WIN64_DIR=<fl-win64 展開先> [RETDEC_BIN=<retdec-decompiler>] bash tools/shared/lift/ildsp/ci_lift.sh
```
- `RETDEC_BIN` 未設定なら PATH の `retdec-decompiler` を使う (`[RETDEC]` は docs/REFERENCES.md §1 のローカルツール)。
- `ci_ranges.py`: entry 0x1aa290 から直接 call と .text 内の直接 jmp を辿る (`ildsp_closure.py` の closure() と同じ規則)。出力は 36 関数・961 命令・間接 call 10 (x86 の capstone 走査)。値が一致しなければ exit 1。範囲内の直接分岐のうち範囲外の飛び先を `outside_targets` に出す (jcc を含む)。
- `ci_lift.sh`: 範囲 (VA 形式) を `retdec-decompiler --select-ranges --select-decode-only` に渡す。
- `ci_census.py`: IR (`ci.drc.ll`) の define と宣言を範囲と照合する。範囲の関数が 1 つでも define されていなければ exit 1。declare のみの呼び出し先は、`outside_targets` の飛び先なら「範囲外の直接呼び出し先」、それ以外は「画像内ポインタ」に分ける。

### 実測 (測定 commit `eb6f0e1c7`・4 core・n=3)
| 項目 | 値 |
|---|---|
| `ci_lift.sh` の実行時間 (ranges + RetDec + census。`date` で計測) | 1.943–1.965 s (min–max。1.953 / 1.965 / 1.943) |
| load (実行前の 1 分平均) | 0.31 (3 回とも。直前に素材を展開した後) |
| 3 回の出力 | `ci.drc.ll` と stdout が 3 回とも `cmp` で一致 (rc 0・ALL OK) |

## 2. 結果 (実測)
| 項目 | 値 | 数え方 |
|---|---:|---|
| 範囲の関数数 | 36 | `.pdata` 24 + `.pdata` の無い葉 12 (近似: 次の `.pdata` 先頭まで) |
| 命令数 | 961 | 到達関数の命令開始 RVA の和集合 |
| x86 の間接 call | 10 | 範囲内の `call` で即値でないもの (capstone) |
| x86 の範囲外直接分岐の飛び先 | 1 | `outside_targets`。0x1aefa7 `jne` → 0x1aef40 (§2-2 (a)) |
| RetDec の define | 45 | 範囲 36 + 範囲外の追加 9 (計算ジャンプ表の飛び先。§2-2 (b)) |
| 範囲の define 欠落 | 0 | entry は export 名 `GeneralPitchShifter_CreateInstance` で出る |

### 2-1. IR の外部宣言 (範囲内の呼び出し行数)
| 種別 | 名前 (IR 行数) |
|---|---|
| IAT (10 種) | FlsSetValue 5・HeapAlloc 2・FlsGetValue 2・GetLastError 2・HeapFree 1・EnterCriticalSection 1・LeaveCriticalSection 1・RaiseException 1・RtlPcToFileHeader 1・SetLastError 1 |
| 画像内ポインタ (2 種) | function_1801cb5e0 1 (呼び出し元 0x1aedc0・x86 の間接 call 0x1aedf6・slot 0x268260)・function_1801cb600 1 (呼び出し元 0x1b6f4c・x86 の間接 call 0x1b6f6c・slot 0x268268) |
| 範囲外で define の無い直接呼び出し先 (1 種) | function_1801aef40 1 (呼び出し元 0x1aef60・x86 の飛び元 0x1aefa7 `jne`) |
| SSE helper `__asm_` (8 種) | movaps 7・movntps 8・movups 3・int3 4・movapd 1・movq 1・punpcklbw 1・sfence 1 |

### 2-2. 閉包の取りこぼし (未解決・#3318 で扱う)
closure は `call` と直接 `jmp` だけを辿る。そのため次の 2 種が範囲に入らない。どちらも x86 で確認した。
- **(a) 条件分岐の先の直接呼び出し先 (1 件)**: 0x1aefa7 `jne 0x1801aef40` (閉包関数 0x1aef60 の中)。0x1aef40 は `.pdata` の無い 16 バイトの `rep stosb` ヘルパ (`push rdi; mov eax,edx; mov rdi,rcx; mov rcx,r8; rep stosb; mov rax,r11; pop rdi; ret`)。IR では `declare` だけがあり、0x1aef60 の本体から `call @function_1801aef40` で呼ばれる。`ci_census.py` は「範囲外で define の無い直接呼び出し先」として別行に出す。
- **(b) 計算ジャンプの表の経路 (n = 1〜16) を IR が落とす (9 define は未参照)**: x86 では 0x1aef74 `cmp r8,0x10` → 0x1aef78 `jbe 0x1af070` が、n ≤ 16 のとき計算ジャンプへ進み 1〜16 バイトを書く。0x1af070 の `lea r9,[rip-0x1af07a]` は r9 = イメージ基底 (0x180000000) を作り、0x1af07a `mov eax,[r9+r8*4+0x442000]`・0x1af082 `add r9,rax`・0x1af08b `jmp r9` で飛ぶ。表 0x442000 (`_RDATA`) の k = 0〜16 の 32 bit 値は RVA の 17 件 (k = 17〜19 は 0)。17 件のうち 9 件は RetDec の define の先頭 (function_1801af090・af0a0・af0a8・af0b0・af0c0・af0cc・af0d0・af0e0・af0e8)、残り 8 件は case 本体の途中 (0x1af094・0x1af097・0x1af09b・0x1af09e・0x1af0a4・0x1af0b4・0x1af0c4・0x1af0c7)。
  IR (`ci.drc.ll`) では `@function_1801aef60` の先頭が `%0 = icmp ult i64 %arg3, 17` → `br` で `dec_label_pc_1801af028` (`ret i64 %arg1`) に入る。`1801af070`・`1801af07a` を参照する行は 0 件で、0x1aef60 の本体に `indirectbr`・`switch`・`unreachable` は無い。つまり n = 1〜16 の書き込みは IR に無いまま `ret` する。9 define はどの `call` からも参照されない (census の「IR 内の call 参照 0 件」)。症状は DEFECTS D9 と同じ形 (間接 jmp の経路が `ret` に化け、case ブロックが呼び出し元の無いまま残る)。ret の値は undef ではなく `%arg1`。
  baseline 時点の census は検出しなかった (define の有無だけを見ていた)。§8-2 で orphan 検査を追加して検出するようにした。RetDec 内部でどの段がこの経路を落としたかは未確認。
- 閉包規則を変える (jcc と計算ジャンプの表を辿る) と 36 関数・961 命令が変わるので、再測定を伴う。判断は #3318 で行う。

## 3. IR の呼び出し行数と x86 件数
- **IR の呼び出し行数は x86 の件数と一致しない** (`ci_census.py` の注)。例: FlsSetValue の IR 5 行 = `function_1801b8820` の 4 行 (x86 の `call 0x1801b9334` が 0x1b8865・0x1b8892・0x1b88a3・0x1b88b4 の 4 箇所。件数は一致) + サンク本体 `function_1801b9334` の 1 行 (`jmp qword ptr [rip + IAT]` が define になる)。
- IAT の `jmp [IAT]` サンクは直接 call で呼ばれる。0x1b932c (FlsGetValue) と 0x1b9334 (FlsSetValue) は `call` の直接の先 (0x1b932c は 1 箇所、0x1b9334 は 4 箇所)。0x1bb426 (EnterCriticalSection) と 0x1bb47a (LeaveCriticalSection) は、直接 call される小関数 0x1bb414 と 0x1bb468 の末尾の `jmp [IAT]`。これらは x86 の `call [IAT]` ではないので、間接 call 10 件に入らない。
- 間接 call 4 件 (0x1aedf6 → 0x268260 / 0x1aee04 → RtlPcToFileHeader / 0x1aee4a → RaiseException / 0x1b6f6c → 0x268268) は REPORT_CLOSURE §4.6 と同じ。残り 6 件は IAT (0x1b882f・0x1b88cf・0x1b9061・0x1b909a・0x1b90a4・0x1b9c5a)。
- 検算 (別算法): x86 の間接 call は capstone の走査で 10 件 (`ci_ranges.py`)。`ildsp_closure.py` の entry_only.indirect_calls = 10 と一致。

## 4. ネガティブコントロール
| 名前 | 壊し方 | 結果 |
|---|---|---|
| neg_rename | `ci.drc.ll` の `function_1801ac9c0` の define 名を変更 (`neg.ll`) | `FAIL: 範囲の関数が define されていない: ['function_1801ac9c0']`・rc 1 (測定 commit `eb6f0e1c7` の census) |

## 5. 未解決 (起票先)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| IAT 10 種の stub 化の方針 (C 実装か wasm import)。直接 call のサンク 2 種 (0x1b932c・0x1b9334) と末尾 jmp の 2 種 (0x1bb426・0x1bb47a) を含む | wasm 化 | [T-SH-65] #3318 |
| SSE helper 8 種 (`__asm_`) の C 実装 (解消は §7。5 種は #4229 で C 実装済み) | wasm 化 | [T-SH-65] #3318 |
| 間接 call 4 件の trap 化 (ac 4) | 正常系の到達 | [T-SH-65] #3318 (到達実測は #3250) |
| 閉包の取りこぼし: 直接 jcc 先 function_1801aef40 (§2-2 (a))。閉包規則を変えるか。変えれば 36/961 が変わり再測定 | 範囲・wasm 化の意味 | [T-SH-65] #3318 |
| 計算ジャンプ表の経路 (n = 1〜16) が IR で `ret` になる (§2-2 (b))。表を解く経路を IR に戻すか、欠落を受入として扱うかを決める。baseline の census は検出しなかったため、§8-2 で検出器を追加済み (現在は FAIL で検出) | 1〜16 バイトの書き込みの欠落 (silent) | [T-SH-65] #3318 |
| 全バイト差分・ネガティブコントロール・gate | 受入の残り | [T-SH-66] #3320 |
| `.pdata` の無い葉 12 件の範囲 (次の `.pdata` 先頭まで) | 命令数は上限側に偏りうる | #161 |

## 6. 検証範囲 / 範囲外
- 範囲: 範囲の再現・RetDec の定義生成・census。コードは HEAD で再実行して ALL OK を確認。
- 範囲外: wasm 化・native 実行・差分・gate (子へ)。RetDec の出力 IR の意味論は未検証。IR が計算ジャンプの表の経路を落とすことは §2-2 (b) で確認した。RetDec 内部の原因は未確認。

## 7. SSE ストアの復元と helper 生成 (T-SH-103 #4229)

結論: RetDec は `movups`・`movntps` のストアを IR の store に出さない (11 箇所)。`ci_restore_stores.py` で 19 箇所すべてを `store i128` に戻し、残りの SSE helper 5 種を `gen_helpers.py` で C 実装した。`ci_lift.sh` は rc=0 (ALL OK)。

測定 commit: `56ec5cf11` (ci_restore_stores.py・gen_helpers.py・ci_lift.sh を含む最後のコード commit)。`git diff 56ec5cf11 HEAD -- tools/shared/lift/ildsp tools/shared/lift/libreverb ':!*.md'` の出力は `tools/shared/lift/ildsp/lift_psola_closure.sh` の 9 行だけ (main 取り込みで入った。測定経路の外)。測定経路 (`ci_lift.sh`・`ci_restore_stores.py`・`libreverb/gen_helpers.py` ほか) の差分は 0 (`git diff --stat 56ec5cf11 HEAD -- <測定経路>` の出力は空)。

### 7-1. 書き込みの全数 (x86 の命令と IR の対応・測定 commit `56ec5cf11`)
x86 の書き込み先は全件 `[rcx …]` (xmm0 を書く) (capstone で逆アセンブルして確認)。IR の書き込み先 (復元後) の基準と offset は、x86 の operand と目視で照合した (19 件)。機械照合はしていない。

| RVA | x86 | IR の元の形 | 復元後 |
|---|---|---|---|
| 0x1aefa9 | `movups [rcx], xmm0` | `call void @__asm_movups` (書き込みなし) | `store i128` 先は `%arg1` (関数入口の rcx の値) |
| 0x1aefd0・d3・de・e2・e9・ed・f1 | `movaps [rcx±…], xmm0` (7 件) | `call i64 @__asm_movaps` + `sext` + `store i128` | `store i128 %5` (sext を除去) |
| 0x1aeff5 | `movapd [rcx-0x10], xmm0` | `call i64 @__asm_movapd` + `sext` + `store` | `store i128 %5` |
| 0x1af010 | `movups [rcx], xmm0` | `call void @__asm_movups` (書き込みなし) | `store i128` |
| 0x1af022 | `movups [rcx+r8-0x10], xmm0` | `call void @__asm_movups` (書き込みなし) | `store i128` |
| 0x1af030・33・3e・42・49・4d・51・55 | `movntps [rcx±…], xmm0` (8 件) | `call void @__asm_movntps` (書き込みなし) | `store i128` |

件数: movups 3・movntps 8・movaps 7・movapd 1 (計 19)。`store i128` は 8 件 → 19 件。

movaps/movapd の sext 除去の理由: RetDec の helper は xmm の下位 64bit だけを `i64` で返す (`__asm_movaps(i128) -> i64`)。その後の `sext i64 → i128` は下位 64bit の最上位ビットで上位 64bit を埋めるため、xmm0 の上位が 0 でないと別の値を書く。`movaps [m], xmm` は xmm 全体 (128bit) を書くので、store の値は xmm (`%5`) そのものにする。

### 7-2. 検証
- 実行: `FL_WIN64_DIR=<fl-win64> RETDEC_BIN=<retdec> bash tools/shared/lift/ildsp/ci_lift.sh` (commit `56ec5cf11`・4 core・n=3)
  | 項目 | 値 |
  |---|---|
  | 実行時間 (`date` で計測) | 2.017 / 1.995 / 1.990 s |
  | load (実行前の 1 分平均) | 0.03 / 0.11 / 0.11 |
  | 3 回の stdout | `cmp` で 3 回とも一致。rc 0・ALL OK |
  | 生成物 (`ci.rs.ll`) | md5 `4811e83e9e4343ad70e6ec883023641f` |
  | 生成物 (`ci_helpers.c`) | md5 `497d886223a0625f2b236d105c7df119` |
- 生成した helper: `int3:1, movq:1, punpcklbw:1, sfence:1` (4 種)。`movapd` の分岐は実装したが、復元後の IR には `movapd` が残らないので生成されない。
- `ci_helpers.c` は `cc -c` が通る (警告は `-Wunused-function` の `fb`・`setl` のみ)。

### 7-3. ネガティブコントロール
| 名前 | 壊し方 | 結果 |
|---|---|---|
| NC1 drop-one | `ci_restore_stores.py --drop-one` (movups/movntps の 1 箇所を復元しない) | `[restore] movups: 2 件 (期待 3)`・rc 1 |
| NC2 未対応 | `declare i64 @__asm_cvttss2si(i128)` を `gen_helpers.py` に入れる | `1 unsupported helper signatures`・rc 1 |
| NC3 census の store 照合 (#4293) | `ci.rs.ll` から `store i128` を 1 行削ったコピー (`nc.rs.ll`) を `ci_census.py ci.drc.ll ranges.json nc.rs.ll` に渡す | `復元後の store i128: 18 (復元前 8 + movups/movntps 11 = 19)`・`FAIL: 復元後の store i128 が期待値と違う (store 欠落の疑い)`・rc 1 |

注: `ci_census.py` は第 3 引数 (復元後 IR) を渡すと、SSE helper の件数 (movups 3・movntps 8・movaps 7・movapd 1)・復元後の `store i128` 件数 (= 復元前 + movups/movntps)・復元後に helper 呼び出しが残らないこと を検査する (#4293)。store の欠落は NC1 (restore 側の件数検査) と NC3 (census 側) の 2 段で FAIL する。`ci_lift.sh` は census を restore の後に走らせる。

### 7-6. census の store 照合 (T-SH-112 #4293)
- 測定 commit: `82c802c7b` (`ci_census.py`・`ci_lift.sh` を変えた最後の commit)。
- 期待値 (x86 から数えた件数・§7-1 と一致): movups 3・movntps 8・movaps 7・movapd 1。
- 正常系 (`ci_lift.sh`・rc 0・ALL OK): 復元前の `store i128` 8 → 復元後 19 (movups/movntps の 11 件が増える。movaps/movapd は sext の store を置き換えるだけで件数は変わらない)。helper 呼び出しは census の検査で期待値 3/8/7/1 と一致し、復元後に 0 件。
- 実行: `FL_WIN64_DIR=<fl-win64> RETDEC_BIN=<retdec> bash tools/shared/lift/ildsp/ci_lift.sh` (測定 commit `82c802c7b`・再測定 HEAD `106137f5b`・4 core・n=3)。素材は `fl-win64` と `toolchain-retdec` を `$RUNNER_TEMP` に展開した (`RETDEC_BIN` は `retdec/bin/retdec-decompiler`)。
  | 項目 | 値 |
  |---|---|
  | 実行時間 (`date` で計測) | 1.597 / 2.325 / 1.697 s |
  | load (1 分平均・実行前 / 実行後) | 0.94 / 1.10 (`uptime`) |
  | 3 回の stdout | `cmp` で 3 回とも一致。rc 0・ALL OK |
  | 生成物 (`ci.rs.ll`・`ci_helpers.c`) | §7-2 の md5 と一致 (値は §7-2 のみに記載) |
- NC3 は §7-3 の表を参照。HEAD `106137f5b` で再現: `store i128` 18・期待 19・rc 1。
- 再測定の状態: round 1 の再実測 (`toolchain-retdec` を含む素材での正常系・NC3) は HEAD `106137f5b` で実施済み (上の表と §7-3 の NC3)。
- コード差分: `git diff 82c802c7b HEAD -- tools/shared/lift/ildsp tools/shared/lift/libreverb ':!*.md'` は空 (差分 0)。よって再測定値は測定 commit のコードに対する値として有効。

### 7-4. 既知の制約
- 0x1aefa9 の書き込み先は、RetDec の alloca 経由 (`bitcast i64* %rcx to i128*`) の load である。`store i64 %arg1, i64* %rcx` が関数入口の 1 回だけであることを確認して `%arg1` を値として使った。書き込み直前まで rcx に他の store が無い形なので、この 1 箇所だけに当てはまる。pass は、その形以外では exit 1 で止まる。
- 復元の正しさは IR の構造と x86 の命令の照合で確かめた。wasm 実行と native 差分は未実施 (#3320)。
- 閉包の取りこぼし (§2-2 (a)(b)) と IAT stub は変えていない (#3318)。

### 7-5. 未解決 (起票先)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x1aefa9 の `%arg1` 解決は「入口 store が 1 回だけ」の前提。一般の形は未対応 (pass が exit 1 で止まる) | 別の CreateInstance 形に当たると止まる | [T-SH-65] #3318 |
| `movapd` の helper 分岐は実装したが、復元後 IR に `movapd` が無く生成 0 件。テストと NC は無い | 実行されない分岐 (未検証) | [T-SH-65] #3318 |
| 差分 (native と wasm の全バイト比較・gate) | 復元の意味論が未検証 | [T-SH-66] #3320 |
| IAT stub・閉包の取りこぼし・emcc | wasm 化 | [T-SH-65] #3318 |

## 8. 方針の決定と census の検出 (T-SH-153 #5749)

結論: (a) は閉包規則を変えず範囲外のままにする。(b) は受入として扱わず、census が FAIL で検出するようにした。IR の計算ジャンプ経路の修復は未了 (#3318)。

### 8-1. (a) 直接 jcc 先 function_1801aef40
- x86: 0x1aefa7 `jne 0x1801aef40` は **条件分岐**。0x1aef40 は `rep stosb` の memset ヘルパで、`ret` は呼び出し元へ戻らず 0x1aef60 の呼び出し元 (閉包の外) に返る。
- IR: `call i64 @function_1801aef40` の後に fall-through で 0x1aefa9 へ続く。つまり IR は jcc を call に化かしている。これは現行の IR (baseline) に既にある誤モデルで、閉包を広げても直らない。
- 試算 (scratch, 非コミット・`work/` の probe): jcc を辿ると 37 関数・969 命令 (+1 関数・+8 命令)。`ci_ranges.py` に入れて `ci_lift.sh` を回すと、RetDec は 0x1aef40 を `__asm_rep_stosb_memset` の呼び出しとして出し、`gen_helpers.py` が未対応の signature で exit 1 になった。閉包規則は戻し、コードの差分は 0 (`ci_ranges.py` は HEAD と同じ)。
- 決定: 範囲外のまま扱う。誤モデルを閉包で正すには IR の jcc 扱いを直す必要があり、#3318 で扱う。

### 8-2. (b) 計算ジャンプ表の経路 (n = 1〜16)
- 決定: 欠落を受入として扱わない (silent miscompile を見逃さない)。census に検査を入れた。
- 追加した検査 (`ci_census.py`): 範囲外の define のうち、IR のどの `call` からも参照されないものを FAIL にする。baseline では 9 件 (function_1801af090 ほか 8 件) が該当し、`ci_lift.sh` は rc 1 になる。
- 本 PR の `ci_lift.sh` は HEAD で rc 1 を返す。これは (b) が未修復であることを示す意図した結果。修復 (表を解く経路を IR に戻す) は #3318 で行い、その時点で rc 0 に戻る。
- 検出器の限界: この検査は「範囲外 define のうち IR の call から未参照のもの」という副次的な形にだけ依存する。RetDec が 9 件の define を出さなくなると、(b) の欠落があっても PASS する (現在の RetDec 出力の形に依存する)。
- 実測 (HEAD `ci_census.py` 変更後・4 core・n=1): 出力末尾 `[census] FAIL: 範囲外の define が IR のどの call からも参照されない ... ['function_1801af090', ..., 'function_1801af0e8']` (9 件)・rc 1。範囲の 36 関数は define 欠落 0 (他の検査は通る)。

### 8-3. 閉包規則の再測定
閉包規則 (`ci_ranges.py`) は変えていない。36 関数・961 命令・間接 call 10 は HEAD で再現 (`ci_ranges` ok)。よって 36/961 の再測定は要らない。8-1 の 37/969 は試算値のみ。

### 8-4. 未解決 (起票先)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 計算ジャンプ表の経路 (n = 1〜16) を IR に戻す (RetDec 内部の段は未確認) | 1〜16 バイトの書込みの欠落 (census は FAIL で検出中) | [T-SH-65] #3318 |
| 直接 jcc 先 function_1801aef40 の誤モデル (jcc を call として扱う) | 範囲・意味論。閉包を変えると wasm 化の前提が変わる | [T-SH-65] #3318 |

## 9. wasm リンクと外部グローバル (T-SH-152 #5748)

結論: `ci_lift.sh` の出力を wasm にリンクすると、未解決は IAT 10 種 (#5747) と直接/画像内の呼び出し先 2 種 (閉包の取りこぼし #5749) の集合だけになる。外部グローバル 2 種と `__stack_pointer` はリンクが通った。ただし外部グローバルの画像上の敷設は未決 (§9-2)。

### 9-1. 実測 (`ci_link.sh`・rc 1 = 期待どおりの未解決)
- 測定 commit: `9f3c2a969` (コードを変えた最後の commit。`ci_link.sh` のコメント 1 行と本節の更新)。`ci_lift.sh`・`ci_link.sh` はこの HEAD で実行した。`git diff 332faf055 9f3c2a969 -- tools/shared/lift/ildsp tools/shared/lift/libreverb` の差分は `ci_link.sh` のコメント 1 行のみ (実行されるコードは同じ)。
- 旧 head `5afe607d0` の値 (main 取り込み前・census 検査なし): `ci_lift.sh` rc 0 (ALL OK)・`ci_link.sh` 1.09 s。現 head では成り立たない。
- 素材: `$HOME/artifacts` に `fl-win64`・`toolchain-retdec`・`toolchain-emsdk` の 3 件が実在した。`tar --zstd -xf` で `$RUNNER_TEMP/art` に展開 (`extracted/block24360_PE.bin`・`retdec/bin/retdec-decompiler`・`emsdk/emsdk_env.sh` の実在を確認)。
- 入力の生成 (手順): ① `FL_WIN64_DIR=$RUNNER_TEMP/art RETDEC_BIN=$RUNNER_TEMP/art/retdec/bin/retdec-decompiler bash tools/shared/lift/ildsp/ci_lift.sh` → **rc 1** (2.9 s)。census の `[census] FAIL` (範囲外 define 9 件が IR の call から未参照) で止まり、`ci.rs_norm.ll`・`ci_helpers.c` は作られない。`ci.rs.ll` までは作られる。② 続けて次の 2 行を流す (`ci_lift.sh` の残り手順と同じコマンド):
  ```
  python3 tools/shared/lift/libkio/ir_normalize.py tools/shared/work/lift/ci/ci.rs.ll tools/shared/work/lift/ci/ci.rs_norm.ll
  python3 tools/shared/lift/libreverb/gen_helpers.py tools/shared/work/lift/ci/ci.rs_norm.ll tools/shared/work/lift/ci/ci_helpers.c
  ```
  → 両方 rc 0 (`[gen_helpers] 4 helpers (int3:1, movq:1, punpcklbw:1, sfence:1)`)。
- census の出力 (現 head): `範囲 36 関数 / define 45 (範囲外の追加 define 9・IR 内の call 参照 0 件)`・`FAIL: 範囲外の define が IR のどの call からも参照されない` (9 件: function_1801af090 ほか 8 件)。
- 未設定時: `env -u EMSDK_ENV bash tools/shared/lift/ildsp/ci_link.sh` → rc 1 (`EMSDK_ENV を設定` のエラーで停止し、リンクは走らない・現 head で確認)。
- `ci_link.sh` (`EMSDK_ENV=$RUNNER_TEMP/art/emsdk/emsdk_env.sh`) → **exit 0**・wasm-ld rc 1 (期待どおりの未解決) / 想定外 0 件。実行 (commit `9f3c2a969`): 0.69 s (`ci.o` 等を再生成)。初回 (旧 `332faf055` の作業ツリーで実行) は 14.0 s で、emsdk の sysroot キャッシュ生成を含む。
- `ci_lift.sh` (`9f3c2a969`) → rc 1 (census FAIL・§8-2 で意図どおり)。`ci.o` の未定義シンボルは `llvm-nm -u` で 19 件 (IAT 10・呼び出し先 2・`__asm_*` 4・`__stack_pointer`・`global_var_1803f6610`・`__unnamed_1`)。
- 手順: `grep -v '^  uselistorder'` で行頭 2 空白の 137 行を除く (IR 全体の uselistorder は 174 行)。emcc 6.0.12 の LLVM が `uselistorder` を読めず `wrong number of indexes, expected 4` で止まるため。`ci.ll` → `emcc -c -O1` → `ci.o`。`ci_helpers.c` → `helpers.o`。
- 未解決の一覧 (`link.log` の `undefined symbol` 行の件数。計 153 行): IAT (EnterCriticalSection 11・FlsGetValue 2・FlsSetValue 4・GetLastError 53・HeapAlloc 3・HeapFree 52・LeaveCriticalSection 11・RaiseException 5・RtlPcToFileHeader 5・SetLastError 1 = 10 種 147 行)、呼び出し先 (function_1801aef40 1・function_1801cb600 5 = 2 種 6 行)。
- `ci.o` の未定義シンボル (`llvm-nm -u`、emsdk 同梱。ホストの `nm` は wasm を読めない) は 19 件: IAT 10 種・呼び出し先 2 種・`__asm_int3`/`__asm_movq`/`__asm_punpcklbw`/`__asm_sfence` 4 種・`__stack_pointer`・`global_var_1803f6610`・`__unnamed_1`。旧記述の内訳 (20 件) は `__unnamed_1` を外部グローバル 2 種 (`global_var_1803f6610`・`__unnamed_1`) とは別に数えて二重計上していた。正しくは 19 件。
- `__asm_*` 4 種が EXPECT に無いのに exit 0 になる根拠: `helpers.o` (`ci_helpers.c` から gen_helpers.py が生成) が `__asm_int3`・`__asm_movq`・`__asm_punpcklbw`・`__asm_sfence` を `T` (定義) で持つ (`llvm-nm --defined-only helpers.o`)。よって wasm-ld の未解決は出ず、`undefined.txt` にも現れない。`__stack_pointer` は emcc が供給、`global_var_1803f6610`・`__unnamed_1` は shim.o が定義 (`llvm-nm --defined-only shim.o`)。
- 検証: `ci_link.sh` の判定は wasm-ld のリンクエラー行だけを数える。期待集合 (IAT 10 種 + 2 種) 以外が出ると exit 1、出なければ exit 0。

### 9-2. 外部グローバルの意味 (未決)
- `global_var_1803f6610` (`external global i64`): VA `0x1803f6610` = RVA `0x3f6610` は `.data` の中。`.data` の初期値は 8 byte `0x1803f66a8` (`.data` 内の `global_var_1803f66a8` を指すポインタ)。IR は `icmp eq i64 %4, ptrtoint (ptr @global_var_1803f6610 to i64)` と `load i64, ptr @global_var_1803f6610` で読む。つまり画像内の 1 cell として敷設すれば、IR の意味 (cell の内容 = ポインタ値) と一致する。RetDec が `.data` の他のグローバルを `global` として出すのと同じ形。
- `@0` (`external global i32`): `ret i64 ptrtoint (ptr @0 to i64)` が 3 箇所 (`function_1801aedc0`・`function_1801bb414`・`function_1801bb468` の末尾)。IR に定義が無い。画像上の該当 VA は未特定。
- 敷設方式 (案・未実装): `wc_image.py` は PE 全体を VA 0x30000000 に敷設するので、`global_var_1803f6610` の cell (RVA 0x3f6610) は画像の中に既にある。C 側で別の cell を作ると、画像の `.data` の値 (`0x1803f66a8`) と食い違う。よって IR の `@global_var_1803f6610` を「画像基底 + 0x3f6610」に置き換える方式を案とする。`@0` は画像上の VA が未特定のため、同じ方式は決められない (実体の特定が先)。実装は ir_normalize の段で行う必要があり、本 run では行っていない。
- 仮置きの効果: shim は cell を 0 初期化 (`global_var_1803f6610` は 0)。したがって仮置きのままでは `icmp eq` の比較対象が変わる。**リンクが通ることと、意味が正しいことは別**。意味の確認 (native との差分) は #3320 の範囲。

### 9-3. 残り (起票先)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 外部グローバル 2 種の画像敷設 (`global_var_1803f6610` は `.data` の cell、`@0` は実体未特定) | リンクは通るが、仮置きの値で意味が変わりうる | 本 issue の範囲 (敷設方式を決めるのは次の子 or #3318) |
| `uselistorder` 行 (174 行) を emcc が読めない | ci_link.sh は行を除いて回避。ir_normalize の対応が必要 | [T-SH-65] #3318 |
| IAT 10 種 | 未解決 (リンクエラー) | #5747 |
| 閉包の取りこぼし (function_1801aef40・function_1801cb600) | 未解決 (リンクエラー) | #5749 |
