dsp_ippv2 export: win x64 446 (ipps 366 / ippi 71 / core+Agg 9), mac 434
win 使用 (直接参照あり): distinct 12 / PE 54  族別 {'memory': 4, 'arith_reduce': 3, 'transcendental': 3, 'dsp_filter_fft': 1, 'image': 1}
mac 使用 (直接参照あり): distinct 159 / Mach-O 143  族別 {'memory': 21, 'convert_shuffle': 10, 'arith_reduce': 43, 'transcendental': 31, 'image': 43, 'dsp_filter_fft': 11}; FLEngine mac distinct 115 (call site 410)
win 使用関数: ippsMove_8u(49), ippsMove_32f(49), ippsZero_8u(49), ippsMulC_32f_I(49), ippsAdd_32f_I(25), ippsZero_32f(2), ippsAtan_32f_A24(1), ippsTrunc_64f(1), ippsExp_32f_A11(1), ippsFIR64f_32f(1), ippsThreshold_LTValGTVal_32f_I(1), ippiFilterRoundGetBufSize32f_8u_C1R(1)
