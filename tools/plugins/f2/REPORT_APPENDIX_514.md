# PLG-F2 付録 (#514): icall waiver 18979 0x741035 の機械検証

測定 commit: `8eddfb09` (コードを変えた最後の commit。検査スクリプトと f2_step2.sh 接続)。PE は `block18979_PE.bin` (fl-win64 素材の抽出、ImageBase 0x400000)。
親 REPORT: `REPORT.md` §7 (icall 復元と回帰ゲート)。

## 1. 結論

- 受入条件 1 の残件 (549 / 550) の 1 site = block 18979 の `0x741035 call qword ptr [rdi+0x1f0]` について、waiver の「到達不能で RetDec が基本ブロックごと除去」という主張を、手作業の追跡 (`icall_gate_waivers.json` の evidence) から機械検査 `f2/waiver_proof.py` (V1〜V5) に置き換えた。V1〜V5 は全て PASS。
- 全数検査 (int32 全 2^32 値) も PASS。ネガコン 2/2 DETECTED。
- 受入条件 1 の文言どおりの一致 (549 ≠ 550) は未解消。IR に 0x741035 の call は載らない (RetDec の除去は設計どおり)。waiver を「説明済み」とみなすかは PM 判断 (issue コメント参照)。

## 2. 検査 (`tools/plugins/f2/waiver_proof.py`)

| 検査 | 内容 | 結果 (`8eddfb09`) |
|---|---|---|
| V1 | 0x741035 の所属関数 (.pdata) が 0x740e30 | PASS ([0x740e30, 0x7413d0)) |
| — | B の確定: 0x741035 直前の無条件 jmp (0x741002) の次 = 0x741007。B 内に終端命令なし | PASS |
| V2 | B へ入る参照は PE 全体で 1 件 (0x740f28 の `jmp 0x741007`)。コード参照 (直接 target・即値・rip 相対) とデータ参照 (絶対 8 byte・RVA 4 byte、範囲 [B, 0x74103b) の全アドレス) | PASS (コード参照 1 件、データ参照 0 件) |
| V3 | 0x740e30 の関数内に間接 jmp が無い | PASS (0 件) |
| V4 | 引数 v の格納先 `[rbp+0x40]` への書込みは入口 0x740e46 の 1 件、その address を取る lea が無い、rbp は prologue/epilogue 以外で変わらない | PASS |
| V5 | 入口 0x740e6a から 0x740f28 までの経路を v の全域で評価。0x740f28 に到達する v は 0 件 | PASS (下表) |
| V5' | 非空振り: 0x7411dd (jae 成立) に到達する v が 1 以上 | PASS |

評価器の方式: decode 結果を解釈する (mov で eax に v を載せ、cmp/test/sub/jcc/jmp を追う)。eax や flags を追えない分岐 (`[rbp+0x48]` 依存の test 等) は両方向を試す過大近似で、P=0 の結論は過大近似に対して安全側。

理論上の根拠 (V5 の数値と一致することを確認): 0x740f28 は `sub eax,8; cmp eax,6; jae` の不成立時に実行される。v-14 が符号なしで 6 未満 ⇔ v∈[14,19]。一方、入口の `cmp eax,0xe; jge` で v<14 の経路だけを見るので、両者は両立しない。

## 3. 実測

| 項目 | 結果 |
|---|---|
| window (既定、4096 値) | PASS、wall 5.35 s (load 0.21/0.28)。reach P=0、reach 0x7411dd=2055 |
| full (`--domain full`、4,294,967,296 値、chunk 2^24) | PASS、wall 540 s (real 9m0.2s / user 6m26s / sys 2m34s)、reach P=0、reach 0x7411dd=2,147,483,655 |
| NC-A: 0x740f22 の `jae`→`jb` (0f83→0f82) | DETECTED (rc 1)。V5: reach P=7 (v∈[7,13] の 7 値) |
| NC-B: 0x740e6d の `cmp eax,0xe`→`0x14` (83f80e→83f814) | DETECTED (rc 1)。V5: reach P=6 (v∈[14,19] の 6 値) |
| 関数外の間接 jmp (PE 全体、4 件) | 0x40aa83 (絶対 8 byte テーブル。ファイル全体の絶対 VA 検索で B を指すエントリ 0 件)、0x40f432 (`jmp [rcx]`、実行時に決まる関数ポインタ。B を指す静的 VA 0 件)、0x54de26・0x551a58 (相対 4 byte テーブル。one-off 検算でエントリ 35・31 件の全てが各関数内に入り、B を指さない) |

full 検査は 540 s かかるため既定ゲートは窓モード (5 秒)。窓の境界値は、経路の定数 (全て |c|<512) の近傍と符号境界 (±2^31) の近傍に限られるので、全数検査と同じ区間分割を覆う (full の結果と一致することを本測定で確認: reach P=0 は両モードで同じ)。

## 4. 配線と再現

- `f2_step2.sh` に `f2/waiver_proof.py` と `f2/nc_waiver_proof.py` を追加 (回帰ゲートの直後)。`icall_gate_waivers.json` の 18979 entry に `proof` 参照を追加 (ゲートは未知のキーを無視する)。
- 再現: `python3 tools/plugins/f2/waiver_proof.py` (窓)、`python3 tools/plugins/f2/waiver_proof.py --domain full` (全数、約 9 分)、`python3 tools/plugins/f2/nc_waiver_proof.py`。PE は `FL_WIN64_DIR/extracted/block18979_PE.bin`。
- `f2_step2.sh` 全体 (lift 11 閉包 + 回帰ゲート) は本 run では再実行していない。前提の `work/winfuncs` の生成が約 518 秒かかり、本 run の上限に収まらないため。本変更で f2_step2.sh に加えた 2 行は、上記の単体実行で代替検証した。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入条件 1 の文言 (549 ≠ 550): 0x741035 は IR に載らない。waiver を「説明済み」として受け入れるか | issue を close できるかの判断 | PM 判断 (#514 コメント) |
| RetDec が到達不能ブロックを除去する挙動の改修 (IR に死コードを残す) | 本件の範囲外。改修すると 550=550 になるが、死コードを人工注入する形になる | 起票しない (PM 判断後に決める) |
