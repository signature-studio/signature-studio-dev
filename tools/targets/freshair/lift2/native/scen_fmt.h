/* Compressor シナリオ共通フォーマット (native_comp.c / comp_harness.mjs で同一解釈)。
 * 1 行 = 1 シナリオ = 複数 call (同一 S/P/host/vector を共有)。全トークン 16 進:
 *   sc_idx nCalls { nW {region off val}*nW  n  L[n] R[n]  hasSC [SL[n] SR[n]] }*nCalls
 * region: 0=S(this) 1=P(S+0x90) 2=ctx 3=Q(vector holder); +0x10 で 1 byte 書込。val は 32 bit。 */
