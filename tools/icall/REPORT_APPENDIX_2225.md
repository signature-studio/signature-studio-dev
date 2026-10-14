# 付録: icall #2225 (ICALL-65) — SlateCore 符号化表と OTT api-set 表 `0x18026c9f0` の形式比較

> 親: #2197 (ICALL-62)。前付録: `REPORT_APPENDIX_2198.md`。本 run は受入条件 4 (OTT api-set 表との形式比較) のみ。
> T1/T2 の終点・entry 数は #2226 (ICALL-66)、群 B〜I の原因は #2231 (ICALL-67) へ移管済み。

## 1. 結論

- **cookie と decode 規則は一致**: SlateCore `0x18125eaa8` と OTT `0x180260ce0` の cookie はどちらも静的既定 `0x2b992ddfa232` (rot = cookie & 0x3f = 50)。decode は両者とも `ror(entry ^ cookie, cookie & 0x3f)`。
- **配置も一致 (静的状態)**: OTT api-set 表 (32 entry = 256 B) も SlateCore の既知 12 slot・T1 `0x181307100`・T2 `0x1813071a0` も、すべて `.data` の **zero-fill 域** にあり、ファイル上の生値は 0。
- **受入条件「entry 数の比較」は未達**: OTT 側は 32 entry と確定。SlateCore 側は T1/T2 の終点が未確定のため、仮定を置いても一致・相違のどちらとも判定しない。確定は #2226 (ICALL-66)。本 appendix の判定は形式 (cookie・decode 式・zero-fill 配置) の一致のみ。
- **訂正**: `tools/ott/ACCEPTANCE_CAB137_CAB138.md` §4.3 の「api-set 表 0x18026c9f0 のファイル生値は非ゼロ 32/32」は誤り。表は `.data` の raw 範囲外にあり、ファイル上に生値が無い (根拠は §2.4 のセクションヘッダとの比較)。`tools/ott/crtinit/REPORT.md` §3 の「全 0」が正しい。本 PR では ACCEPTANCE 文書を書き換えず、未解決表に残す。

## 2. 実測

### 2.1 測定条件

- 測定 commit: `c98786d1` (コード head。main 取り込み `7b785cd9` を含む)。§2.2 の slot_trace は本 commit で再測定した。
- 旧測定 commit `7d15ceab` から `c98786d1` までの差分 (`docs/WORKFLOW.md` §6)。実出力:
  - `git diff 7d15ceab c98786d1 --stat -- tools/icall/diff tools/ott`
    ```
    tools/icall/diff/fa_wc.py            | 145 +++++++++++++++++++++++++++++++++++
    tools/icall/diff/fa_wc_build.sh      |  18 +++++
    tools/icall/diff/fa_wc_drv.cjs       |  13 ++++
    tools/icall/diff/fa_wc_rt.c          |  16 ++++
    tools/icall/diff/ott_apiset_cmp.py   |  79 +++++++++++++++++++
    tools/icall/diff/slot_table_reach.py |  31 ++++++++
    tools/icall/diff/slot_trace.c        |   8 +-
    tools/icall/diff/slot_trace.sh       |   2 +-
    8 files changed, 310 insertions(+), 2 deletions(-)
    ```
  - 差分の内訳: `slot_trace.c` は fatal 時に stderr へ `regs`・`heap_args` 行を出す処理と `g_gpr` の保存を追加 (stdout の `ACC` 行・rc の経路は変更なし)。`slot_trace.sh` は `ERR_OUT` の grep 対象に `regs|heap_args` を追加。
  - 差分のうち測定対象 (`slot_trace.sh`・`slot_trace.c`) は `7b785cd9` → `c98786d1` で変更なし (下の `git diff 7b785cd9 c98786d1 -- tools/icall/diff tools/ott` は空)。
  - `git diff 7b785cd9 c98786d1 -- tools/icall/diff tools/ott` の出力: 空 (差分 0)。
  - `ott_apiset_cmp.py` (新規) は測定の入力ではない (slot_trace の測定対象外)。
- 再測定 (本 HEAD `c98786d1`・素材 `plugins-freshair` 展開・`tools/icall/work/` を `work-icall` から展開):
  - 所要: real 12.274 s / user 10.991 s / sys 1.780 s。load average 1.21 (開始時) → 1.18 (終了時)。
  - `fatal` 行の stderr 出力: `regs` 53 行・`heap_args` 53 行 (`work/slot_trace_fatal.txt`)。
  - §2.2 の集計は測定 commit `7d15ceab` 時点と一致。
- 再現: `SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh` (既定条件)。
- 旧測定 (`7d15ceab`): real 13.191 s / user 11.032 s / sys 1.916 s。load average 1.18。
- 素材: `plugins-freshair` (`FA_DL` に展開) と `work-icall` (`tools/icall/work/`) を使用。OTT の生値は `analysis-ott-binaries` の `OTT_vst2_win64.dll` を PE 直読み。
- `ott_apiset_cmp.py` は `c98786d1` で `analysis-ott-binaries` の `OTT_vst2_win64.dll` に対して実行した (§2.3 の出力)。

### 2.2 slot_trace 集計 (既定条件・再現)

`funcs 131 exit {rc=0: 69, rc=124: 1, rc=95: 53, rc=98: 8}`、zero-fill VA 10、既知 12 hit 3・miss 9。
#2198 のベースライン (c2f52068) と完全一致。`c98786d1` での再測定も同じ値 (§2.1)。

### 2.3 形式比較 (PE 直読み)

| 項目 | OTT `OTT_vst2_win64.dll` | SlateCore `SlateCore.core_64` |
|---|---|---|
| security cookie | VA `0x180260ce0` = `0x2b992ddfa232` | VA `0x18125eaa8` = `0x2b992ddfa232` |
| rot (cookie & 0x3f) | 50 | 50 |
| decode 式 | `ror(entry ^ cookie, cookie & 0x3f)` | `xor reg,[cookie]` → `ror reg,cl` (cl = 50) |
| 表の起点 | `0x18026c9f0` (api-set 表) | T1 `0x181307100`・T2 `0x1813071a0` |
| entry 数 | **32** (8 B × 32 = 256 B) | 未確定 (#2226) |
| 配置 | `.data` zero-fill (raw end `0x180269000`・virt end `0x18026cbcc`) | `.data` zero-fill (raw end `0x18128f400`・virt end `0x18130a000`) |
| 生値 | raw 範囲外 (zero-fill) のためファイル上に無し | 既知 12 slot・T1・T2 の起点も zero-fill のためファイル上に無し |
| 個別 slot | `0x18026c028`・`0x18026c388`・`0x18026cb40`・`0x18026cb88` も zero-fill (raw 範囲外) | 既知 12 (`0x1813068d0`〜`0x181307418`) も zero-fill (raw 範囲外) |

- 「encoded 表 = zero-fill に enc(NULL)=cookie を敷いて初期化」という形式は、両者で同じ。OTT は `ott_crt_init_tables` が、SlateCore は harness の `SLOT_ENC_INIT=1` が同じ書込みを行う。
- OTT の `enc(NULL)` は `rol(0,14) ^ cookie` で `cookie` に等しい (`crtinit/REPORT.md` と一致)。

#### 実 DLL の出力 (`ott_apiset_cmp.py`・`c98786d1` の状態で実行。素材 `analysis-ott-binaries` の `OTT_vst2_win64.dll`)

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
```

### 2.4 事実の根拠: セクションヘッダの raw end と表の VA

「api-set 表は zero-fill 域にあり、ファイル上の生値は 0」の根拠は、次の PE セクションヘッダの値との比較である (実測値の出力ではない)。

- OTT の `.data`: raw end `0x180269000` (`PointerToRawData + SizeOfRawData` 相当の VA)、virt end `0x18026cbcc`。
- api-set 表の起点 `0x18026c9f0` (8 B × 32 = 終点 `0x18026caf0`) は raw end `0x180269000` より後ろで、virt end の内側。
- よって表の全 entry はファイルの raw 範囲の外にあり、ファイル上の生バイトを持たない。

`tools/icall/diff/ott_apiset_cmp.py` は、entry ごとに VA の区分 (`raw` / `一部 zero-fill` / `zero-fill` / `セクション外`)・セクション名・raw 範囲・virt 範囲を表示する。`zero-fill` と `セクション外` は decode せず、0 固定の値として扱わない。集計行は出さない。
以前の REPORT・検収文書にあった「非ゼロ 32/32」が、どの読み方に由来するかは未確認 (前 run の読出し手順は残っていない)。`tools/ott/ACCEPTANCE_CAB137_CAB138.md` §4.3 の訂正は、本節のセクションヘッダとの比較を根拠とする。

注: 上記 §2.3 の出力は、`c98786d1` の状態で実 DLL に対して実行した結果である (出力 33 行、ブロックは実出力と一致を確認済み)。セクション範囲・VA 区分は、この出力と §2.4 のセクションヘッダの値が一致する。

## 3. 再現

```
bash tools/targets/freshair/fetch.sh     # FA_DL=$RUNNER_TEMP/plugins-freshair を指定して展開
SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh
python3 tools/icall/diff/ott_apiset_cmp.py <OTT_vst2_win64.dll>   # <OTT_vst2_win64.dll> = [ANALYSIS-PLUGINS] の ott/binaries/OTT_vst2_win64.dll
```

- OTT の DLL の所在は `docs/REFERENCES.md` の `[ANALYSIS-PLUGINS]` (`ott/binaries/`)。Actions では `oc_artifacts: analysis-ott-binaries` で取得する (`docs/WORKFLOW.md` §11)。
- `tools/icall/diff/ott_apiset_cmp.py` は cookie `0x180260ce0`・api-set 表 `0x18026c9f0` (32 × u64) を読み、`ror(entry ^ cookie, cookie & 0x3f)` で decode して出力する。zero-fill は 0 とする (§2.4)。
- 実 DLL の出力は §2.3 に貼った (`c98786d1` の状態で実行。素材 `analysis-ott-binaries` の `OTT_vst2_win64.dll`)。



## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| SlateCore T1/T2 の終点と entry 数 (比較の entry 数の欄) | 受入条件 1 (#2197 本体) | #2226 (ICALL-66) |
| `tools/ott/ACCEPTANCE_CAB137_CAB138.md` §4.3 の「非ゼロ 32/32」の訂正 | 文書の誤記 (OTT の検収文書) | 本 PR 外。PM 判断 |
| SlateCore 側の既知 12 slot が zero-fill である理由 (初期化の主体) | 受入条件 2・3 | #2231 (ICALL-67) |
