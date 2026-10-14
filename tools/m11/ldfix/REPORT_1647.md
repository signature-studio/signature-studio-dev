# REPORT_1647 — dest 追跡監査 (audit_undefload_dest.py) の状態と分類の根拠

親: #564 / 本 issue: #1647 / 子 (残件): 子 issue を参照 (PR 本文の未解決表)

## 1. 結果 JSON の状態 (未検証)

`results/audit_undefload_dest_1647.json` は **未検証の出力**として扱う。

- 生成に使った commit は確認できない。PR 本文の「1m10.343s・2729 site」の run は、PR 自身が「バグ版」と書いた版の出力に当たる (REGLIVE 2502 / sites 2729)。
- 入力の `tools/m11/work/boot{0..4}.norm0.ll` (`work-m11`) は #680 の通り現行の生成手順と一致しない。現行の `m11_gen_ir2.sh` 由来の IR での再生成は、この run では行っていない (`work-m11` 未展開・RetDec 未導入)。
- よって本 JSON から件数や偽陰性の結論を引かない。再生成と sha256・load の記録は子 issue で行う。

## 2. DEST_FRAME_IN_ESCAPED 18 site の分類

18 site のうち 3 site は、追跡した frame read の値を**メモリアクセスのベース (アドレス) として使う**。

| 関数 | 消費者 | 追跡 writer |
|---|---|---|
| 4425f0 | `movsd qword ptr [rax], xmm0` | `mov rax, qword ptr [rbp + 0x60]` |
| e9d8a0 | `movsq qword ptr [rdi], qword ptr [rsi]` | `mov rsi, qword ptr [rbp + 0x68]` |
| 783d00 | `mov word ptr [rax + 0x2c], 0x3d` | `mov rax, qword ptr [rbp + 0xb0]` |

この 3 site が読むのは「未定義値」ではなく**ポインタ値**である (frame の slot に入った有効なポインタを使っている)。
残りの 15 site は、detail 欄の消費者を見る限り、読んだ値を演算・比較・frame 格納の値として使っており、メモリのベースには使っていない。

扱いの決定: 本 JSON の `by_class` は変えず、上の 3 site を「ポインタ値の read」として数える (分類の分割はコード変更なので、子 issue で行う)。
偽陰性の判定 (未定義 read の脱落) には、この 3 site を含めない。

## 3. 数字の訂正 (REPORT_564 §3 との対応)

REPORT_564 §3 は F4 修復済み 10 関数のうち監査で偽陰性と見た関数を、次の 5 件として挙げる: 132e8e0 / 44d1c0 / 69c360 / 865020 / 977e40。
REPORT_564 §3 が REGLIVE になる原因 (read 命令と消費者が別命令) を確認したと記すのは 44d1c0 / 69c360 / 865020 / 977e40 の 4 関数。**132e8e0 は未調査** (REPORT_564 の記載どおり)。
本 PR で DEST 追跡が検出したのは 865020 (`test eax,1` ← `mov eax,[rbp+0x4c]`) の 1 関数だけで、他 3 関数は全数監査の結果に出ていない。
