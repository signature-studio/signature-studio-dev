dsp_ippv2 export: win x64 446 (ipps 366 / ippi 71 / core+Agg 9), mac 434
※ 以下 win/mac 使用数は VAR 直接参照のみの下限値 (二段間接を除く)。確定値は tools/ipp: win 229 / mac 234 / 和集合 239 / loader 420 名
win 使用 (VAR 直接参照のみ): distinct 12 / PE 54  族別 {'memory': 4, 'arith_reduce': 3, 'transcendental': 3, 'dsp_filter_fft': 1, 'image': 1}
mac 使用 (VAR 直接参照のみ): distinct 159 / Mach-O 143  族別 {'memory': 21, 'convert_shuffle': 10, 'arith_reduce': 43, 'transcendental': 31, 'image': 43, 'dsp_filter_fft': 11}; FLEngine mac distinct 115 (call site 410)
win 使用関数: ippsMove_8u(49), ippsMove_32f(49), ippsZero_8u(49), ippsMulC_32f_I(49), ippsAdd_32f_I(25), ippsZero_32f(2), ippsAtan_32f_A24(1), ippsTrunc_64f(1), ippsExp_32f_A11(1), ippsFIR64f_32f(1), ippsThreshold_LTValGTVal_32f_I(1), ippiFilterRoundGetBufSize32f_8u_C1R(1)
