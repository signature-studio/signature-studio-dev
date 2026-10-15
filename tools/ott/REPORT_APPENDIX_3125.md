# OTT x64c の i_rcr を実機 rcr の規則に直す (#3125 / KH-47・flelift #3065 の横展開)

既知類型との関係: 該当なし (lift の flags 誤りの新しい型。行案は §5)。

## 0. 結論

- `tools/ott/lift/x64c.py` の `i_rcr` を flelift 版 (`tools/flelift/x64c.py`、#3065 / PR #3081) と同じ規則に直した。
- 旧式の誤りは 4 点: (1) `SETZSP` で ZF/SF/PF を変えていた (実機 rcr は変えない)、(2) OF を `MSB ^ 新 CF` としていた (実機は `MSB ^ MSB-1`)、
  (3) count に `&0x1F` (64bit は `&0x3F`) を掛けず `% (W+1)` のみだった (例: 32bit の count 40 は実機で 8 回転、旧式は 40 % 33 = 7 回転)、
  (4) 64bit で `uint64_t` の `<< 64` を使っていた (未定義動作)。
- OTT の rcr site は lift 全体で **6 箇所**。全て `f_1801bc890` (0x1801bc890 の FP 制御演算) 内の **32bit・count=1** で、
  CF の結果は旧新で同じ。差は OF の式と ZF/SF/PF の書き換えだけ。
- 受入条件 4 件はすべて満たした (§2 の表)。

## 1. 差分

`tools/ott/lift/x64c.py` の `i_rcr` (16 行の差し替え) と、検証スクリプト `tools/ott/lift/rcr_emit_check.py` (新規)。
生成 C の 1 例 (32bit, count=1、新):

```c
{ uint32_t a_ = (R[2] & 0xffffffff); uint32_t r_ = a_; unsigned c_ = (unsigned)(0x1U) & 31; if (c_) { unsigned __int128 v_ = ((unsigned __int128)fCF << 32) | a_; unsigned n_ = c_; while (n_--) v_ = (v_ >> 1) | ((v_ & 1) << 32); fCF = (uint8_t)((v_ >> 32) & 1); r_ = (uint32_t)v_; fOF = ((r_ >> 31) ^ (r_ >> 30)) & 1; } R[2] = (uint32_t)(r_); }
```

## 2. 測定 (測定 commit = `0d527f38a`、コード差分の最後の commit)

環境: `uptime` load average 0.28 (開始時)、x86-64 Linux、gcc / clang (`/usr/bin/`)。素材 `plugins-ott`・`analysis-ott-binaries` (`ANALYSIS_DIR=$HOME/analysis`)・`work-m6-ott` を展開して実行。

| 測定 | コマンド | 結果 |
|---|---|---|
| 新 i_rcr の生成 C vs 実機 rcr | `python3 tools/ott/lift/rcr_emit_check.py` | **4004 / 4004 一致** (w=8/16/32/64、count 0..255、32bit の count 0/32/64/96 を含む、乱数 flags・乱数の上位ビット)。`-Wshift-count-overflow` 0 件 (gcc 0 / clang 0)、`SETZSP` 無し。rc=0、0.22 秒 |
| 対照 (origin/main の旧 i_rcr) | `... --module <旧 x64c.py>` | **32 / 4004 一致**、警告 gcc 3 / clang 3 (`rcr64` の `<< 64`)、`SETZSP` あり。rc=1 (ネガティブコントロール) |
| 参照式 rcr_ref vs 実機 | `python3 tools/flelift/tests/rcr_native_check.py` | 4004 / 4004 (flelift 版・変更なし) |
| OTT e2e (新) | `bash tools/ott/ott_e2e.sh` | **PASS**。scenario 89 本 / 50,236 cell 全 bit 一致、max_ulp 0、state_diff_qwords 0。実時間 19.2 秒 (`real`) |
| OTT e2e (旧、対照) | 旧 x64c.py に一時的に差し替えて同じコマンド (後で新版へ戻し `cmp` で一致を確認) | **PASS** (同じ 89 本 / 50,236 cell)。旧版でも matrix は落ちない |
| lift 差分 | 旧・新の `ott_lifted.c` を diff | **6 箇所のみ変化** (旧 6 行 / 新 6 行、他は 0 差分)。全 6 箇所は `f_1801bc890` 内の rcr (insn 1801bca89・1801bcb9e・1801bcc80・1801bd1dd・1801bd2f1・1801bd3e3) |
| 生成 C の警告 | `clang/gcc -c -Wshift-count-overflow` で lifted C 全体 | 新 0 / 0、旧 0 / 0 |

- matrix の数値は `tools/ott/REPORT.md` §0 と同一 (再測定で一致)。
- 測定 commit 以降のコード差分: `git diff 0d527f38a HEAD -- tools/ott/lift tools/ott/rt tools/ott/diff` は空 (0 行。本 commit は REPORT と DOC_MAP のみ)。
- 旧版でも lifted C に `-Wshift-count-overflow` が出なかった理由: OTT の 6 site は全て 32bit で、`uint64_t << 32` は警告にならない。警告が出るのは 64bit 形 (`<< 64`) だけで、OTT lift はこの形を出さない。受入条件の「警告が出ないこと」は、新版の断片 (全幅 8/16/32/64) で 0 件を確認して満たす。
- 検証範囲: x86-64 実機 (このランナー) との照合・OTT の 6 site を含む e2e。範囲外: 他ホスト (`rcr_emit_check.py` は非 x86-64 で SKIP)。

## 3. 範囲外・既存の挙動

- `i_rcr` を持つのは flelift `x64c.py` と OTT `x64c.py` の 2 箇所だけ (`grep -rln "def i_rcr" tools`)。flelift は #3081 で直し済み。
- 旧式の flags 誤りが後続の jcc の分岐を変えた site は、今回の lift では観測されなかった (matrix 89 本は旧版でも全 bit 一致)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 旧式の rcr で ZF/SF/PF が書き換わることが後続 jcc の分岐を変える site は、今回の 6 site では観測されなかった | 旧版の挙動が他の OTT 入力で出る可能性は残る (修正後は実機と一致するため、残るのは旧版の挙動だけ) | 本 issue #3125 のコメント (新規 issue は起票しない: 修正で解消済み) |

## 5. 類型行案 (DEFECTS 形式・PM 判断)

| ID | 層 | 状態 | 症状 | 根本原因 | 検出信号 | 修復 |
|---|---|---|---|---|---|---|
| (案) | lift | 新規 | rcr 後に ZF/SF/PF が変わり、後続 jcc/setcc の分岐が誤る恐れ (本 lift では未観測) | 命令の flags 規則を SETZSP で一括更新した (実機 rcr は ZF/SF/PF を変えない) | `rcr_emit_check.py` の flags 比較 (旧版 32/4004) | flelift と同じ規則 (`rcr_emit_check.py` で固定) |

## 6. 再現

```
python3 tools/ott/lift/rcr_emit_check.py                  # 4004/4004, 警告 0
python3 tools/ott/lift/rcr_emit_check.py --module <旧 x64c.py>   # 対照: 32/4004 (rc=1)
ANALYSIS_DIR=$HOME/analysis bash tools/ott/ott_e2e.sh     # PASS (約 20 秒)
```
