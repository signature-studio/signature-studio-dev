## 停止: 前提 #1976 [MX-27] が未完了のため着手せず

### 確認したこと
- 本 issue (#1977 [MX-28]) の未達受入条件は 3 件: (1) 差し替え点決定と RULES 追加根拠の REPORT 記載 (2) N6 6 種・N5 4 種の機械検証 (`acpt_verify_mx2.py` 拡張) (3) 実測値の記録。
- 本文の前提は「[MX-27] の結果」であり、範囲の注記にも「呼び出し元が未確定のうちは RULES を変更しない (根拠なしの br_force / store は silent miscompile になる)」とある。
- 前提の #1976 [MX-27] (DLL 側の N5/N6 読み手と呼び出し元の確定) は **OPEN** で、結果が REPORT_APPENDIX.md にまだ無い。
- 親 #1900 の受入 2・3 は、子 #1976 の完了待ちになっている。
- 素材 (fl-win64 / plugins-massivex / toolchain-retdec / toolchain-emsdk) は $HOME/artifacts に実在を確認済み。素材不足は無い。

### 結論
- 呼び出し元が未確定の状態で RULES を変えると silent miscompile になるため、差し替えの実装は行わない。
- 依存 issue: **#1976** (blocked_by の設定を PM にお願いします)。
- #1976 が merge された後に再着手可能。必要な `oc_artifacts`: `plugins-massivex toolchain-retdec toolchain-emsdk`。

### 変更
- コミット・PR は作成していない。
