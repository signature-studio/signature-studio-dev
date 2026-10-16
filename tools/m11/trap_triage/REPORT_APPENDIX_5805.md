# #5805 付録: 証拠表の行 72 の件ごとの判定 (#4885 の子・母数 1)

本付録が行 72 の判定の正本。`REPORT_APPENDIX_4885.md` §4 の行 72 (保留) を SSA 追跡で確定した。結論は `REPORT_718.md` §4l に 1 行で載せる。

## 1. 結果

- 母数 1 件 (証拠表 `strict_evidence.tsv` のデータ行 72・`function_12d3da0` の jcc `12d3dea`)。
- 判定: **真陽性 (構造)** 1 件。偽陽性 0 件。保留 0 件。
- 構造判定である。count ≤ 0 が実行時に来るか (到達性) は未測定 (§5)。
- 偽陽性率は母数 288 の判定が終わるまで書かない。

## 2. 入力と測定

- 入力 IR: `work-m11` の `boot_final.ll` (19,787,837 B・sha256 `69c774de…`。`597757f4…` の系統は使っていない)。
- 入力 PE: `fl-win64` の `extracted/block00031_PE.bin` (22,227,016 B)。
- 測定 commit: `dc45a57aa` (origin/main)。判定に使うコード (`tools/m11/guard699/`・`tools/m11/ldfix/ldmach.py`・`tools/m11/trap_triage/strict_evidence.py`・`judge_ctx.py`) は `097da5a69..dc45a57aa` で 0 行変更。
- 実行 (`dc45a57aa`・foreground・各 1 回): `scan_guard.py --report` 5 s (strict 288・`counts` の strict 288)。`strict_evidence.py` 15 s (TSV 288 行)。この TSV のデータ行 (ヘッダ除く) は、`097da5a69` の main ツリーで作った TSV と `cmp` で一致。load average (1 分値) は開始 0.43・終了 0.59。
- 行 72 の MACH・IR の表示 (`judge_ctx.py <IR> <TSV> <PE> 72 72`) は `097da5a69` の main ツリーで実行した。判定に使うコードは両 commit で同一 (上記 0 行)。

## 3. 機械語 (`function_12d3da0`・`block00031_PE.bin`)

`capstone` で `.text` の RVA を写して逆アセンブルした。

```
12d3dae: je 12d3e1a           ; 0 段のテーブル判定 (IR %6 と一致)
12d3db2: mov ecx, 9           ; 外側カウンタ (IR rcx.0 = 9)
12d3dbe: movsxd rax, ecx
12d3dc9: mov r8d, [r11]
12d3dcc: xor ebx, ebx         ; ebx = 0 (毎回の外側反復で再設定)
12d3dce: lea rax, [rip+0x66bf5f]   ; table = 0x193FD34
12d3dd5: movsxd rsi, edx
12d3dd8: shl rsi, 3 ; lea rsi,[rsi+rsi*2]   ; rsi = 24*edx
12d3de0: mov esi, dword [rax + rsi*8]       ; esi = table[192*arg2] (dword)
12d3de3: sub esi, 1           ; esi = count-1
12d3de6: mov eax, ebx         ; eax = 0
12d3de8: cmp eax, esi
12d3dea: jg 12d3e0c           ; 0 > count-1 なら内側ループを飛ばす
12d3dec: sub esi, ebx ; add esi, 1
12d3df1: movsxd rbx, eax      ; 内側ループ先頭 (L)
...
12d3e0c: sub ecx, 1 ; sub r11, 0x18 ; cmp ecx, -1 ; jne 12d3dbe   ; 外側末尾
```

- jcc の左辺 `eax` は `mov eax, ebx` (12d3de6) で入る。`ebx` は直前の `xor ebx, ebx` (12d3dcc) で 0。よって左辺は**定数 0** で、内側の索引の初期値 (`rax.0 = 0`) と同じ値。
- 右辺 `esi` は `dword [table + 192*arg2] - 1`。count 源は `table = 0x193FD34` (VA)。IR の定数は `22281524 = 0x153FD34 = 0x193FD34 − 0x400000` (ImageBase `0x400000`)。段数 1・幅 dword。
- jcc taken 先 `12d3e0c` は外側末尾のブロック。IR の `dec_label_pc_12d3e0c` と同一 (ecx−1・r11−24・ecx≠−1 で戻る)。

## 4. IR (`function_12d3da0`・`boot_final.ll` 88674〜88764 行)

- preheader (`12d3dbe.preheader`): `%7 = mul nsw %0, 192`、`%8 = %7 + 22281524`、`%10 = load i32 [%9]`、`%11 = zext`。これが count 源。
- `store i64 9, rcx.0` と `store %ce1n11…, r11.0` の後、`12d3dbe` へ `br`。
- `12d3dbe`: `store i64 0, ptr %rax.0.reg2mem` (索引 0)、`store i64 %11, ptr %rsi.0.reg2mem` (count)、`br label %12d3df1` (**無条件**)。
- `12d3df1` (内側 L): 比較 `%21 = icmp eq i32 %15, %20` で入口判定は無い。count ≤ 0 の判定は IR のどこにも無い。
- `12d3e02`: `%24 = rsi−1`、`%27 = icmp eq trunc(%24), 0`、`%28 = icmp eq %27, false` → 真なら `12d3df1` へ戻る (後判定の do-while)。

## 5. 判定の根拠

1. **左辺の SSA 対応**: 機械語の jcc 左辺 `eax` は定数 0 (12d3dcc の `xor` → 12d3de6 の `mov`)。IR の対応物は `store i64 0, ptr %rax.0.reg2mem` (`12d3dbe`)。両者とも内側ループの索引の初期値 0 で、同じ値。
2. **右辺の対応**: 機械語の `esi = count−1` と IR の count (`%11`・`%10` の load 連鎖) は、同じテーブル・同じ段数・同じ幅 (dword)。IR は `rsi.0 = count` で後判定 (count 回の反復)。機械語は `count−1` を `jg` で判定 (count 回の反復)。count ≥ 1 では同じ反復数。
3. **不一致**: count ≤ 0 のとき、機械語は内側を 1 回も回らず `12d3e0c` へ抜ける (符号付き `jg`)。IR は `12d3dbe` から内側へ無条件に入り、`rsi = count` (`zext` で扱う) を `rsi−1` しながら後判定で回す。count = 0 や負の count では、IR の内側は入口判定無しに 1 回以上回る (`rsi` が 0 から回り込む)。
4. **脱出先**: 機械語の `jg` 先 `12d3e0c` は IR の外側末尾 `12d3e0c` と一致する。

以上より、IR に count ≤ 0 の入口判定が無く、機械語の jcc が count ≤ 0 で脱出先 `12d3e0c` へ行く。`REPORT_APPENDIX_4885.md` §3 の真陽性の基準 (count 源・段数・幅が一致し、IR に入口判定が無く、脱出先 T が機械語で到達可能) を満たす。判定は**真陽性 (構造)**。

## 6. 判定方法 (件ごと)

- 機械語: `capstone` で `block00031_PE.bin` の `12d3da0`〜`12d3e1e` を逆アセンブル (RVA→ファイル位置は `.text` RVA `0x1000` → ファイル位置 `0x400`)。`judge_ctx.py 72 72` の MACH と一致を確認。
- IR: `boot_final.ll` の `function_12d3da0` 本体 (88674〜88764 行) を読み、`rax.0`・`rsi.0`・`rcx.0` の store/load を reg2mem の alloca 経由で遡った。
- レジスタ名の一致 (`eax` と `%rax.0`) は根拠にしていない。左辺は「`ebx` の定数 0」、右辺は「テーブルの段数・幅」で結んだ。
- `tools/m11/guard699/`・`tools/m11/ldfix/`・RetDec 本体・`m11_ov.c` は変更していない。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| count ≤ 0 が実行時に来るか (到達性)。count の源 (`dword [table+192*arg2]`) の値域 | 真陽性 (構造) の実害は未確認 | #4885 (Refs)・#3502 の範囲外 |
| 偽陽性率 (母数 288 の判定が終わるまで書かない) | — | #4885 (Refs) |
