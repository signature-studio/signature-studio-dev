# PLG-P0b-47 (#4385) — Dispatcher 0x11a0 格納元 6 ID の書込み関数の呼出し経路の計装

親 #3986 (PLG-P0b-41)。前身は `REPORT_DISPATCHER_APPENDIX_3673.md` §4.1 (Dispatcher 単独では 6 ID の書込み VA 0x41d919・0x11fc2b3・0x9dec3f に未到達)。
本付録は新規ファイルで、分割移動ではない。

## 0. 結論

| 受入 | 結果 | 状態 |
|---|---|---|
| 1 0x41d8f0 (G18) と 0x11fba90 (P45) の経路で 0x41d919・0x11fc2b3 の到達と書込み値 | G18: 0x41d8f0 を `r9=1` で単独実行すると 0x41d919 に 6 ID とも到達。書込み直前の `r8` (ID) が引数どおり。P45: 0x11fbaef までは到達、分岐 0x11fbb4f の前提が無く 0x11fc2b3 は未到達 | 部分 |
| 2 0x9dec3f (P56) の到達と 0x40f9e0 の戻り値 | 未実施 (本 run の時間内では呼出し元の経路を確定できなかった) | 未着手 |
| 3 6 ID の実行時の値の確定 | 未確定 (G18 の値は ID そのものと確定したが、Dispatcher 実行時に `r9=1` になる条件が未確定) | 未確定 |
| 4 hostshim.c の応答表の更新・Phase A 回帰 | 応答値は変えていない。Phase A 回帰は本 run で再実行できなかった (§4) | 未着手 |

## 1. 測定条件

- 測定 commit: PR 本文の「測定 commit」行 (`hs_val_probe.py` を変えた最後の commit。基点は main `e16513904`)。
- 素材: `fl-win64` の `extracted/block00031_PE.bin` を `$RUNNER_TEMP/fl-win64` に展開 (`tar --zstd -xf` 6.7 秒 real)。
- Python: `$RUNNER_TEMP/hsvenv` (`unicorn 2.1.4` / `pefile` / `capstone 5.0.7`)。
- 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 $RUNNER_TEMP/hsvenv/bin/python hs_val_probe.py g18caller` / `p45caller`。
  `g18caller` 6.7 秒 real、`p45caller` 6.6 秒 real (n=1)。load average は 0.47 (09:59 時点)。
- 呼出し元の走査: `.text` の rel32 `call` (E8) を全件走査して呼出し先を集計した (作業ファイルは `$RUNNER_TEMP`・repo 外)。

## 2. 呼出し元 (静的・rel32 call のみ)

未コミットの走査 (repo 外・再現コード無し。参考値)。コミット済みの手順では再現できない。

| 対象 | 直接の呼出し元 |
|---|---|
| 0x41d8f0 (G18 の書込み関数) | 0x1376870 の 1 件 (未コミット走査) |
| 0x11fba90 (P45 の書込み関数) | 0x124e621 の 1 件 (未コミット走査) |
| 0x1376870・0x124e621・0x1376820 | 直接の呼出し無し (間接呼出しの可能性。未確認) |
| 0x13173a0 (Dispatcher) | 直接の呼出し無し |

## 3. 実測 (受入 1)

### 3.1 G18: `g18caller` (0x41d8f0 を r8=ID・r9=1 で単独実行)

| ID | 0x41d919 到達 | 書込み直前の r8 |
|---|---|---|
| 0x18 | 到達 | 0x18 |
| 0x45 | 到達 | 0x45 |
| 0x54 | 到達 | 0x54 |
| 0x56 | 到達 | 0x56 |
| 0x64 | 到達 | 0x64 |
| 0x65 | 到達 | 0x65 |

- `r9=0` のときは 0x41d919 に届かない (`g18caller` の `r9=0` 行で確認。6 ID とも NOT reached)。よって G18 の書込みは `r9≠0` の分岐でのみ起きる。
- 0x41d8f0 の呼出し元 0x1376870 が `r9` に何を入れるかは未確定。ここが確定しないと、G18 に入る値の実行時の決定はできない。

### 3.2 P45: `p45caller` (0x11fba90 を this=HOST・[this+0x34a8]=0 で単独実行)

- 0x11fbaef (`[this+0x34a8] <= 0` の入口) まで到達。
- 0x11fbb4f (`cmp eax,0xb`) と 0x11fc2b3 (`mov [P45], rax`) には未到達。`[rbp+0x140]` の `[+0x10]` の前提 (0xb) を与えないと分岐に届かない。
- 未コミットの試行 (再現コード無し): `[rbp+0x140]` の `[+0x10]` に 0xb を置いて試したが、0x11fbb4f には届かなかった。この試行は `p45caller` に含まれず、コミット済みの手順では再現できない。`[rbp+0x140]` の初期値の経路は未確定。よって P45 の値は未確定。

## 4. 受入 4 と Phase A (未実施)

- `hostshim.c` は変更していない。
- Phase A `hs_e2e.sh` は実行できなかった: `work-fw-stage1` (stage-1 の 12 ファイル) を展開したが、`hs_e2e.sh` の前提 (`fw_flat4_canon3.ll` ほか。`fw_stage2.sh` の出力) は無い。`work-fw-stage1` には含まれない。
- 変更は `hs_val_probe.py` のみ (33 行追加・既存関数の変更なし)。`hs_val_probe.py` を呼ぶ e2e 経路は無い (grep 済み)。`git diff 98458ac56 HEAD -- tools/plugins/framework/hostshim ':!*.md'` は `hs_val_probe.py` の 33 行のみ。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x41d8f0 の呼出し元 0x1376870 (間接呼出し) の経路と、`r9=1` になる条件 (G18 の実値) | 受入 1・3 (G18) | 子 #4557 `[PLG-P0b-51]` |
| P45 の分岐 0x11fbb4f の前提 (`[rbp+0x140]` の値) と 0x11fc2b3 の到達 | 受入 1・3 (P45) | 子 #4557 `[PLG-P0b-51]` |
| 0x9dec3f (P56) の到達と 0x40f9e0 の戻り値、6 ID の残り (0x54・0x64・0x65) | 受入 2・3 | 子 #4558 `[PLG-P0b-52]` |
| hostshim.c の応答表の更新 (値が確定した後) と Phase A 回帰 | 受入 4 | 子 #4558 `[PLG-P0b-52]` |
| Phase B の `memory access out of bounds` | Phase B の PASS | #2911 (既存) |
