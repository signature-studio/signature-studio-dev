# REPORT_APPENDIX_3127_B — REPORT_APPENDIX_3127 §11 の分割移動 (#6039・受入条件 3 の残り)

## 11. 残り 4 呼出しの引数の由来と入力範囲 (#6039・受入条件 3 の残り)

- 入力・方法: §10 と同じ (`block22434_PE.bin`・`objdump -d -M intel`)。 引数番号は、呼出し元の push 順と callee の `[ebp+N]` の使い方から対応づけた。
- callee の引数 (確認済み):
  - 0x1001147e (GetStringType 系・7 引数): `[ebp+8]` dwInfoType・`[ebp+0xc]` lpSrc・`[ebp+0x10]` cchSrc・`[ebp+0x14]` lpCharType・`[ebp+0x18]` CP (0 なら `[0x10068160]`)・`[ebp+0x1c]` Locale (0 なら `[0x10068150]`)・`[ebp+0x20]` flag 選択。
  - 0x100115c7 (LCMapString 系・8 引数): `[ebp+8]` Locale・`[ebp+0xc]` MapFlags・`[ebp+0x10]` lpSrc・`[ebp+0x14]` cchSrc・`[ebp+0x18]` lpDest・`[ebp+0x1c]` cchDest (MSDN 仕様ではバイト数上限。PE 内では未検証)・`[ebp+0x20]` CP (0 なら `[0x10068160]`)・`[ebp+0x24]` flag 選択 (0 なら MB_PRECOMPOSED=1、非 0 なら 9)。 モード `[0x10068168]` が 2 なら LCMapStringA (0x100130cc)、1 なら MB→WC (0x100130c0)→LCMapStringW (0x100130d0)→WC→MB (0x10013094) の経路。
- 呼出し元 4 件の引数 (即値・グローバル・スタック上の固定領域):

| 呼出し元 | 呼出し先 | 引数 (Locale / dwInfoType, MapFlags, src, cch, dest, cchDest, CP, flag 選択) | 入力の由来 |
|---|---|---|---|
| 0x100111e2 | 0x1001147e | dwInfoType=1, src=`[ebp-0x114]` (256), cch=256, lpCharType=`[ebp-0x514]` (WORD×256), CP=`[0x100682b0]`, Locale=`[0x100684e4]`, flag 選択=0 | `0x10011148` が 0〜255 の恒等表を `[ebp-0x114]` に詰める (`0x1001116d`〜`0x10011172`) |
| 0x10011206 | 0x100115c7 | Locale=`[0x100684e4]`, MapFlags=0x100, src=`[ebp-0x114]` (256), cch=256, dest=`[ebp-0x214]`, cchDest=256, CP=`[0x100682b0]`, flag 選択=0 | 同上 |
| 0x1001122e | 0x100115c7 | Locale=`[0x100684e4]`, MapFlags=0x200, src=`[ebp-0x114]` (256), cch=256, dest=`[ebp-0x314]`, cchDest=256, CP=`[0x100682b0]`, flag 選択=0 | 同上 |
| 0x10012529 | 0x100115c7 | Locale=`[0x10068150]`, MapFlags=0x200, src=`&[ebp+8]`, cch=eax (1 か 2)、dest=`&[ebp-4]` (4 バイト), cchDest=3, CP=0 (`[0x10068160]`), flag 選択=1 (flag 9) | 0x10012484 の `[ebp+8]` (1 バイト目)。 `[ebp+9]` は 2 バイト目 |

- 固定長の 3 件 (0x100111e2・0x10011206・0x1001122e) は、入力の長さも dest もスタック上の固定領域で、SIGSEGV しない範囲は「常に成立」。
- 0x10012529 は dest 4 バイト・cchDest=3 である。 仕様上 (MSDN) は cchDest がバイト上限なので書込みは 3 バイト以内に収まるはずだが、これは PE では確認していない。 入力は cch=eax (1 か 2) で、呼出し元 0x10012484 から渡される `[ebp+8]` の 1 バイト目 (2 バイト目は `[ebp+9]`) が入力。 その呼出し元の入力範囲は未追跡。

### 11.1 未了 (受入条件 3 の残り・4)

- 0x10012484 の呼出し元 (0x10012461 の上位) が `[ebp+8]` に渡す値の範囲。 これが決まるまで 0x10012529 の入力範囲は確定しない。
- host 値: `[0x100682b0]` (CP) と `[0x100684e4]` (Locale) は PE 内で書かれる箇所があるが (`0x10010f6e`・`0x10011014`・`0x1001102c`・`0x10011058`・`0x10011134`・`0x1001113e`・`0x10010f59` の `and`)、各書込み値の由来 (0x100110ec の戻り値など) は未追跡。 `[0x10068150]` は PE 内に書込み命令が無い。 実行時値は host 側が決める (§9.1 と同じ扱い)。
- 受入条件 4 (#4356 へ入力範囲と失敗時の扱いを渡す): 上記が揃った後。
