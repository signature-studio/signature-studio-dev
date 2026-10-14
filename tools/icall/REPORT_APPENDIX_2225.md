# 付録: icall #2225 (ICALL-65) — SlateCore 符号化表と OTT api-set 表 `0x18026c9f0` の形式比較

> 親: #2197 (ICALL-62)。前付録: `REPORT_APPENDIX_2198.md`。本 run は受入条件 4 (OTT api-set 表との形式比較) のみ。
> T1/T2 の終点・entry 数は #2226 (ICALL-66)、群 B〜I の原因は #2231 (ICALL-67) へ移管済み。

## 1. 結論

- **cookie と decode 規則は一致**: SlateCore `0x18125eaa8` と OTT `0x180260ce0` の cookie はどちらも静的既定 `0x2b992ddfa232` (rot = cookie & 0x3f = 50)。decode は両者とも `ror(entry ^ cookie, cookie & 0x3f)`。
- **配置も一致 (静的状態)**: OTT api-set 表 (32 entry = 256 B) も SlateCore の既知 12 slot・T1 `0x181307100`・T2 `0x1813071a0` も、すべて `.data` の **zero-fill 域** にあり、ファイル上の生値は 0。
- **entry 数は比較できない**: OTT 側は 32 entry と確定。SlateCore 側は T1/T2 の終点が未確定 (#2226)。
- **訂正**: `tools/ott/ACCEPTANCE_CAB137_CAB138.md` §4.3 の「api-set 表 0x18026c9f0 のファイル生値は非ゼロ 32/32」は誤り。実測は 0/32 (§2.3)。`tools/ott/crtinit/REPORT.md` §3 の「全 0」が正しい。本 PR では ACCEPTANCE 文書を書き換えず、未解決表に残す。

## 2. 実測

### 2.1 測定条件

- 測定 commit: `7d15ceab` (`origin/main`・本 PR は tools/ の変更なし。`git diff 7d15ceab HEAD -- tools/icall/diff tools/ott` は空)。
- 再現: `SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh` (既定条件)。
- 所要: real 13.191 s / user 11.032 s / sys 1.916 s。load average 1.18 (測定直前 10:26:33)。
- 素材: `plugins-freshair` (`FA_DL` に展開) と `work-icall` (`tools/icall/work/`)。OTT の生値は `plugins-ott` の `OTT_vst2_win64.dll` を PE 直読み。

### 2.2 slot_trace 集計 (既定条件・再現)

`funcs 131 exit {rc=0: 69, rc=124: 1, rc=95: 53, rc=98: 8}`、zero-fill VA 10、既知 12 hit 3・miss 9。
#2198 のベースライン (c2f52068) と完全一致。

### 2.3 形式比較 (PE 直読み)

| 項目 | OTT `OTT_vst2_win64.dll` | SlateCore `SlateCore.core_64` |
|---|---|---|
| security cookie | VA `0x180260ce0` = `0x2b992ddfa232` | VA `0x18125eaa8` = `0x2b992ddfa232` |
| rot (cookie & 0x3f) | 50 | 50 |
| decode 式 | `ror(entry ^ cookie, cookie & 0x3f)` | `xor reg,[cookie]` → `ror reg,cl` (cl = 50) |
| 表の起点 | `0x18026c9f0` (api-set 表) | T1 `0x181307100`・T2 `0x1813071a0` |
| entry 数 | **32** (8 B × 32 = 256 B) | 未確定 (#2226) |
| 配置 | `.data` zero-fill (raw end `0x180269000`・virt end `0x18026cbcc`) | `.data` zero-fill (raw end `0x18128f400`・virt end `0x18130a000`) |
| 生値 | 32/32 が 0 | 既知 12 slot・T1・T2 の起点が 0 |
| 個別 slot | `0x18026c028`・`0x18026c388`・`0x18026cb40`・`0x18026cb88` すべて 0 | 既知 12 (`0x1813068d0`〜`0x181307418`) すべて 0 |

- 「encoded 表 = zero-fill に enc(NULL)=cookie を敷いて初期化」という形式は、両者で同じ。OTT は `ott_crt_init_tables` が、SlateCore は harness の `SLOT_ENC_INIT=1` が同じ書込みを行う。
- OTT の `enc(NULL)` は `rol(0,14) ^ cookie` で `cookie` に等しい (`crtinit/REPORT.md` と一致)。

### 2.4 注意: 直読みの取り違え

最初の試行では `.data` の raw 末尾 (`0x180269000`) より後ろの VA を `get_offset_from_rva` で読んだため、ファイル内の別位置を読んで「非ゼロ」と誤判定した。zero-fill を明示的に 0 とする読み直し (`cmp3_2225.py` 相当) で 0/32 に確定した。`ACCEPTANCE_CAB137_CAB138.md` §4.3 の「非ゼロ 32/32」は同じ誤りと見られる (因果は未確認)。

## 3. 再現

```
bash tools/targets/freshair/fetch.sh     # FA_DL=$RUNNER_TEMP/plugins-freshair を指定して展開
SLOT_ENC_INIT=1 bash tools/icall/diff/slot_trace.sh
# OTT 側: $HOME/analysis/plugins/ott/binaries/OTT_vst2_win64.dll の .data zero-fill を 0 として
#   0x18026c9f0 から 32 × u64 を読み、cookie 0x180260ce0 と decode する (pefile・§2.3)
```

- 比較スクリプト (`tools/icall/work/cmp3_2225.py`) は gitignore 対象の作業物で、commit しない。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| SlateCore T1/T2 の終点と entry 数 (比較の entry 数の欄) | 受入条件 1 (#2197 本体) | #2226 (ICALL-66) |
| `tools/ott/ACCEPTANCE_CAB137_CAB138.md` §4.3 の「非ゼロ 32/32」の訂正 | 文書の誤記 (OTT の検収文書) | 本 PR 外。PM 判断 |
| SlateCore 側の既知 12 slot が zero-fill である理由 (初期化の主体) | 受入条件 2・3 | #2231 (ICALL-67) |
