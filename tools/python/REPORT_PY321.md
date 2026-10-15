# PY-321 (#4347): 動的ディスパッチ 0x410090 の上流 (TMessage* を作る経路) と msgid 0x057f の送り手

親: #3937 (PY-274)。前段: `tools/python/REPORT_PY274.md` §2 (0x410090 は確定。rdx の上流は未同定)。
既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブルと参照走査による解析)。
KPI: 起動・GUI に関わらないため記載不要 (解析のみ)。

## 結論

| 受入 | 結果 | 根拠 |
|---|---|---|
| 1. 0x410090 の rdx (TMessage*) を作る上流の関数を特定し、Msg に 0x057f が入る経路を確定 | **部分確定**: msgid 0x057f の送り手 `0xfdd2c0` と、TMessage を組み立てる `0x60c220` (Perform 相当) を確定。`0x60c220` の `[rbx+0x80]` が `0x410090` を指す経路は未同定 | §2・§3 |
| 2. probe を追加し、既存 probe `pe_py274_dispatch.py` 8/8 が PASS のままであることを確認 | **達成** (新 probe `pe_py321_upstream.py` 8/8 PASS。既存 probe も 8/8 PASS) | §4 |

issue #4347 の受入 1 は満たしていない。`Refs #4347` の部分達成。未解決は §5。

## 0. 対象と前提

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` (2.3 GB) を `tar --zstd -xf ... --wildcards '*block00031_PE.bin'` で展開 (2.9 秒)。`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`。
- 素材には `*_PE.bin` が 313 個ある。本 REPORT の走査は `block00031_PE.bin` (0x410090 の所在モジュール) に限る。他ブロックは未走査。
- 検証起点: origin/main `57830f31e` の worktree (`ws-4347`・branch `4347-py321-dispatch-upstream`)。

## 1. 0x410090 への参照 (間接経路の確認)

`pe_py321_upstream.py` の走査のうち、direct call/jmp・RIP 相対・即値の 3 形態は 0x410090 への参照 0 件。
絶対 qword (VMT・関数ポインタ表) は **旧版の probe が誤っていた** (`ImageBase + TARGET` を探索し、TARGET が既に絶対 VA のため 0 件と判定していた)。修正後は 3532 件 (`.text` 内・8 バイト整列 3531 件)。
- 連続表の例: VA `0x4019d8` から `0x410040`・`0x410030`・`0x410070`・`0x410080`・`0x410090`・`0x410060`… と関数アドレスが並ぶ。表の所属 (どの VMT か) は未確定。
- 表先頭の切り分け (code pointer の連続で遡る) は不正確で、スロット番号 (0x80 = index 16) は確定していない。`0x410090` が `[rbx+0x80]` に入るという対応は未確認。
- dword RVA `0x10090` の一致は block00031 内に 128 件 (4 バイト整列 28 件)。テーブル参照かどうかは未確定。
正の対照: 同じ走査で `0x40ff70` を掛けると direct call 3 件 (0x40ffe8・0x4100b8 ほか) を検出した。走査は機能している。

## 2. msgid 0x057f の送り手 (0xfdd2c0)

- `0xfdd5ea`: `mov edx, 0x57f` (msgid)、`0xfdd5f9`: `call 0x60c220`。同関数内に同形の呼出しが 6 件 (0xfdd5f9・0xfdd678・0xfdd6bf・0xfdd702・0xfdd72f・0xfdd754)。
- 送り手の関数は `0xfdd2c0`。直接呼出し元は計 275 箇所・48 関数 (`pe_callgraph.py callers 0xfdd2c0` 実測)。うち `0x11d2110` 内が 11 箇所 (`0x11d22c5`〜`0x11d2463`)、`0x13173a0` (`0x1322575`) が 1 箇所、残り 263 箇所は他の 46 関数に分布 (`0xfc9480`・`0xfdb560` 等)。
- `0x13173a0` は直接呼出し元 0 件・RIP 参照 0 件。VMT スロットや関数ポインタ経由で呼ばれると推定 (未確定)。
- `0x11d2110` の直接呼出し元は `0xe43650` (`0xe4371c`)。`0xe43650` の直接呼出し元は 0 件。

## 3. TMessage の組立て (0x60c220)

- `0x60c220`: `edx` (msgid) を `[rbp+0x20]` に格納し、`rdx = &[rbp+0x20]` を第 2 引数として `call [rbx+0x80]` (rcx = `[rbx+0x88]`) を呼ぶ。
- よって TMessage* = `&[rbp+0x20]`。格納は dword (`mov dword ptr [rbp+0x20], edx`) で、msgid はその下位 16bit。0x410090 の `rsi = rdx` と `word [rsi]` の読みと整合する。
- `0x60c220` の直接呼出しは 214 箇所 (152 関数・`pe_callgraph.py callers` 実測)。msgid は各呼出しの直前の `mov edx, imm` で読める (0x57f は 6 件、上記 §2)。
- 未確定: `[rbx+0x80]` (Code) に 0x410090 が入る経路。0x410090 の参照が block00031 に無いため、Code 欄の書込み先 (VMT 構築・TMethod 格納) を別途追う必要がある。

## 4. 検証

- 新 probe: `tools/python/analysis/flapi/pe_py321_upstream.py` (8 件・全 PASS)。0x410090 の参照形態 (direct・RIP・即値は 0 件、絶対 qword は 3532 件を検出) と、msgid 0x057f の送り手の 4 命令 (0xfdd5ea・0xfdd5f9・0x60c22c・0x60c24f) を照合する。
- 旧版の絶対 qword 判定は誤り (§1)。修正版を次 run 以降の基準とする。
- 既存 probe: `tools/python/analysis/flapi/pe_py274_dispatch.py` 8/8 PASS (worktree 検証時 37.9 秒、load 0.78)。
- 測定 commit (コードを変えた最後の commit): `8b902f6a9`。
  - `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/pe_py321_upstream.py`
  - 所要 2 分 7 秒 (実測)、load average (1 分値・4 コア) 0.97。PASS 8/8。
- 差分の証跡: `git diff 8b902f6a9 HEAD -- tools/python/analysis/flapi` は本 REPORT の commit 時点で 0 行 (probe を変えていない)。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x60c220` の `[rbx+0x80]` に 0x410090 が入る経路 (VMT・TMethod の格納) | 受入 1 の rdx 上流の完了 | #4347 (本 issue・部分達成のまま。次 run で継続) |
| 0x13173a0 の呼出し経路 (VMT スロット・間接呼出し) | msgid 0x057f の送り手の上位 | #4347 (同上) |
| block00031 以外の PE ブロック (313 個中 1 個のみ走査) | 上流が別モジュールにある場合の見落とし | #4347 (同上) |

親 #3937 の受入は満たしていない。0x12acb70 の発火側 (PY-320・#4346) は別 issue。
