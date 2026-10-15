# tools/qfclift 付録 3410 — T-SH-77 (#3410): longjmp 継続の対応 (§7.8 の全文)

REPORT.md §7.8 の全文 (250 行上限のため分割移動)。検証 HEAD = `08002efca`。

## 1. 起動元・override・root (§7.8 の全文)

既知類型との関係 (docs/DEFECTS.md): 該当なし (x64c の setjmp/longjmp 継続。FLEngine の `fle_ov_longjmp` と同型の扱い)。

- **起動元 (逆アセンブル・lift C で確認)**: DllMain `0x59c20b` の `call 0x40fa30` (= setjmp `0x40f950` へ jmp) の戻り番地が `0x59c210`。
  longjmp `0x40f9c0` を呼ぶのは `0x40fa40` (関数内 `0x40fa8f`)。`0x40fa40` は jmp_buf を複写し、
  `[0x5aa000]` の値から `eax = (flag != 0) + 1` (1 以上) を作って longjmp する (逆アセンブル `setne al; add eax,1` からの読み)。
  戻り値が 1 以上なので DllMain の `cmp eax,1` は後段へ分岐する。`0x40fa40` の呼出元は `0x40fbcf`・`0x40fcb8` (訂正: 旧版の `0x40fbd4`・`0x40fcbd` は戻り番地。付録 4263 §1。lift C の call 行で確認。
  そこで flag がどう決まるかは未解析で、longjmp の発生条件は未確定)。
- **override**: `qfc_ov.c` (`qfc_ov_longjmp`) は FLEngine `fle_ov_longjmp` と同型。`qfc_boot.sh` のみで有効 (`--override 0x40f9c0=qfc_ov_longjmp`)。
- **root**: 戻り先 `0x59c210` を boot 専用 entries に加えた (`work/boot/entries_boot.json`)。e2e の entries と assert (6,347) は変えない。

切り分け (boot の soft 版、同一 HEAD 系統。各 1 回):

| 構成 | 停止点 (`stopped_by`) |
|---|---|
| 元 (override なし・root なし) | `call to UNLIFTED function 0x59c210 ret=0` (REPORT §7.3 と一致) |
| override のみ (root なし) | `call to UNLIFTED function 0x59c210 ret=0` (停止点は動かない) |
| root のみ (override なし) | `[fle] ExitProcess(0)` |
| **override + root (本命)** | `[fle] ExitProcess(0)` |

- **停止点を動かしたのは root 追加であり、override 単独では効かない**。`ExitProcess` (rt 実装済み import) へ進んだが、
  呼出元は未確認。longjmp 後の継続が C の呼出し階層を巻き戻さないため、この進行は継続の不整合による偽の停止の可能性がある (推定。未検証)。
  したがって「DllMain が完走した」とは書かない。strict 版は従来どおり `MISSING IMPORT LocalAlloc` で止まる (変化なし)。
- 判定: boot の PASS 条件 (3 段 ok・RAX = 1・soft 呼出し 0) は未達のまま (FAIL)。

## 1b. ExitProcess(0) の呼出元と偽の停止の判定 (T-SH-106 / #4262)

- **呼出元 (lift C・逆アセンブル)**: `ExitProcess` の呼出し `call 0x406dc0` は `0x40fcdd` (戻り番地 `0x40fce2`)。関数 `0x40fb80` の中。
  `0x40fb80` は `0x59c254` (DllMain の `call 0x40fb80`、戻り番地 `0x59c254`) から呼ばれる。
  `0x40fcdd` の直前は `[0x5aa000]` の値を見る分岐で、`0x40fcb8` の `call 0x40fa40` (= longjmp 呼出し) の戻り番地 `0x40fcbd` から続く経路。
- **計測 (`qfc_probe_4262.sh`・soft 版・work/probe に別ビルド)**: 実行順は次のとおり。
  1. `enter 40fb80` (DllMain の `0x59c254` 系の呼出し)
  2. `longjmp site=40fcb8` (`0x40fa40` → `qfc_ov_longjmp`)
  3. `enter 59c210 eax=1` (戻り先の継続。DllMain は `eax=1` で `0x59c254` へ進む)
  4. `pre-ExitProcess site=40fcdd 5aa000=0` → `[fle] ExitProcess(0)`
- **判定 (偽の停止)**: 3 の継続は正しく進み、DllMain は `eax=1` で `ret` する。その `ret` は lift C では C の `return` で、
  longjmp を呼んだ古い C フレーム (`0x40fa40` → `0x40fb80`) へ戻る。古いフレームは longjmp の後の行 (`0x40fcbd` 以降) を再開し、
  `0x40fcdd` で `ExitProcess(0)` に至る。実機の longjmp は戻らないので、この経路は実機に存在しない。
  よって停止は **偽の停止** (非局所復帰を C の戻りで代用した不整合)。推定ではなく、上の実行順の実測で判定した。
- **修正の範囲 (未実装)**: 修正は非局所復帰で longjmp を呼んだ C フレームを捨てる (dispatch 構造・rt の変更) が要る。
  1 run に収まらないため、子 issue #4510 ([T-SH-126]) に分けた。

## 2. 検証 (HEAD = `08002efca`)

- 測定 commit: `08002efca` (コードを変えた commit)。boot の `qfc_boot.sh` (HEAD) と e2e (HEAD)。

| run | 対象 | 結果 | real | load 終了 |
|---|---|---|---|---|
| R1 | boot (`QFC_BOOT_REBUILD=1`・lift 再生成) | FAIL (strict LocalAlloc / soft ExitProcess(0)) | 52 s | 0.70 0.55 0.33 |
| H1 | boot | FAIL (同上) | 21 s | 0.64 0.54 0.34 |
| H2 | boot | FAIL (同上) | 21 s | 0.74 0.57 0.36 |
| E1 | e2e (`qfc_e2e.sh`) | PASS (exit 0)・negctl 4 本 FAIL 検出 | 131 s | 1.33 0.82 0.48 |
| E2 | e2e | PASS (exit 0)・negctl 4 本 FAIL 検出 | 131 s | 1.04 0.89 0.55 |

- e2e の内容: functions 6,347 / insns 208,714 / unsup 0 / unlifted 0 (e2e 側は不変)。
- 起動 load は E1/E2 とも未採取 (終了 load のみ)。boot の値域は 21 s の 2 回のみで、n=3 未満。
- 負の対照 (停止点が `0x59c210` のまま動かないこと) は §1 の表 (override のみ) が該当する。

