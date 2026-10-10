/* 最小 PE32+ ローダ (Linux x86_64 上で win64 の dsp_ippv2_x64.dll を ImageBase に VA 敷設し ms_abi で呼ぶ)。
   tools/m5 の「VA 敷設ネイティブ実行」方式の PE 版。DllMain/CRT 初期化は実行しない (ippSetCpuFeatures で dispatch index のみ初期化)。 */
#pragma once
#include <stdint.h>
#include <stddef.h>
typedef struct { uint8_t *base; uint64_t image_base; uint32_t size; } PE;
int   pe_load(const char *path, PE *pe);
void *pe_export(const PE *pe, const char *name);
#define MS __attribute__((ms_abi))
