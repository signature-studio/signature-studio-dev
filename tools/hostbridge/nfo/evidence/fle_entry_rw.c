=== decomp 910cd0 -> FUN_00910cd0 @00910cd0 size=2176

longlong FUN_00910cd0(undefined8 param_1,undefined8 param_2,longlong param_3,char param_4)

{
  
  local_80 = auStack_178;
  local_148 = 0;
  local_150 = 0;
  local_138 = 0;
  local_140 = 0;
  local_128 = 0;
  local_130 = 0;
  local_118 = 0;
  local_120 = 0;
  local_110 = 0;
  local_108 = 0;
  local_100 = 0;
  local_f8 = 0;
  local_f0 = 0;
  local_e8 = 0;
  local_e0 = 0;
  local_d8 = 0;
  local_c0 = 0;
  local_b8 = 0;
  local_b0 = 0;
  local_a0 = 0;
  local_a8 = 0;
  local_98 = 0;
  local_90 = 0;
  local_88 = 0;
  local_60 = 0;
  local_38 = 0;
  cVar2 = FUN_00819110(param_1);
  if (cVar2 != '\0') {
    local_40 = FUN_008f4e00(PTR_DAT_008f1ca0,1);
    local_30 = FUN_00913450(PTR_DAT_009103e8,1,param_1,1);
    local_64 = FUN_00913be0(local_30,L"fileversion",1);
    FUN_00913d40(local_30,&local_88,L"ps_name");
    FUN_004133f0(local_40 + 0x18,local_88);
    FUN_00913d40(local_30,&local_90,L"ps_presetfilename");
    FUN_004133f0(local_40 + 0x2c,local_90);
    FUN_008f19b0(&local_98,*(undefined8 *)(local_40 + 0x2c),param_2,L"%FLPluginDBPath%");
    FUN_004133f0(local_40 + 0x2c,local_98);
    if (local_64 == 1) {
      FUN_00910810(local_30,local_40,param_4);
    }
    else if (local_64 == 2) {
      iVar6 = FUN_00913be0(local_30,L"ps_files",0);
      local_54 = 0;
      local_50 = iVar6;
      if (-1 < iVar6 + -1) {
        do {
          local_48 = FUN_008f6ad0(PTR_DAT_008f1b10,1);
          FUN_009138a0(local_30,&local_a8,L"ps_file_name",local_54);
          FUN_00913d40(local_30,&local_a0,local_a8);
          FUN_004133f0(local_48 + 8,local_a0);
          FUN_009138a0(local_30,&local_b0,L"ps_file_filename",local_54);
          FUN_00913d40(local_30,&local_60,local_b0);
          if (param_3 != 0) {
            FUN_008f19b0(&local_b8,local_60,param_3,L"%FLPath%");
            FUN_00413480(&local_60,local_b8);
          }
          FUN_004133f0(local_48 + 0x10,local_60);
          FUN_009138a0(local_30,&local_c0,L"ps_file_magic",local_54);
          uVar5 = FUN_00913be0(local_30,local_c0,0);
          *(undefined4 *)(local_48 + 0x20) = uVar5;
          FUN_009138a0(local_30,&local_d8,L"ps_file_guid",local_54);
          FUN_00913a10(local_30,&local_d0,local_d8);
          *(undefined8 *)(local_48 + 0x24) = local_d0;
          *(undefined8 *)(local_48 + 0x2c) = uStack_c8;
          FUN_009138a0(local_30,&local_e0,L"ps_file_date",local_54);
          uVar8 = FUN_009139f0(local_30,local_e0);
          *(undefined8 *)(local_48 + 0x34) = uVar8;
          FUN_009138a0(local_30,&local_e8,L"ps_file_size",local_54);
          uVar8 = FUN_00913ae0(local_30,local_e8,0);
          *(undefined8 *)(local_48 + 0x3c) = uVar8;
          FUN_009138a0(local_30,&local_f0,L"ps_file_plugclass",local_54);
          uVar5 = FUN_00913be0(local_30,local_f0,0xffffffff);
          *(undefined4 *)(local_48 + 0x18) = uVar5;
          FUN_009138a0(local_30,&local_f8,L"ps_file_type",local_54);
          uVar8 = local_f8;
          uVar4 = FUN_00913be0(local_30,local_f8,0);
          *(ushort *)(local_48 + 0x1c) = uVar4;
          if (uVar4 < 8) {
            bVar7 = ((byte)((int)CONCAT71((int7)((ulonglong)uVar8 >> 8),1) << ((byte)uVar4 & 0x1f))
                    & DAT_009117de) != 0;
          }
          else {
            bVar7 = false;
          }
          if (!bVar7) {
            *(undefined2 *)(local_48 + 0x1c) = 0;
          }
          FUN_009138a0(local_30,&local_100,L"ps_file_bitsize",local_54);
          uVar3 = FUN_00913960(local_30,local_100);
          *(undefined1 *)(local_48 + 0x1e) = uVar3;
          FUN_009138a0(local_30,&local_108,L"ps_file_arch",local_54);
          uVar3 = FUN_00913980(local_30,local_108);
          *(undefined1 *)(local_48 + 0x1f) = uVar3;
          FUN_009138a0(local_30,&local_110,L"ps_file_scanflags",local_54);
          uVar3 = FUN_00913cd0(local_30,local_110);
          *(undefined1 *)(local_48 + 0x4c) = uVar3;
          FUN_009138a0(local_30,&local_120,L"ps_file_vendorname",local_54);
          FUN_00913d40(local_30,&local_118,local_120);
          FUN_004133f0(local_48 + 0x50,local_118);
          FUN_009138a0(local_30,&local_130,L"ps_file_category",local_54);
          FUN_00913d40(local_30,&local_128,local_130);
          FUN_004133f0(local_48 + 0x58,local_128);
          FUN_009138a0(local_30,&local_140,L"ps_file_idstring",local_54);
          FUN_00913d40(local_30,&local_138,local_140);
          FUN_004133f0(local_48 + 0x60,local_138);
          FUN_009138a0(local_30,&local_150,L"ps_compatibility",local_54);
          FUN_00913d40(local_30,&local_148,local_150);
          FUN_00510750(*(undefined8 *)(local_48 + 0x68),local_148);
          local_49 = *(int *)(local_48 + 0x18) != -1;
          if ((bool)local_49) {
            FUN_008f49e0(local_40,local_48,0);
          }
          else {
            FUN_0040faa0(local_48);
          }
          local_54 = local_54 + 1;
          iVar6 = iVar6 + -1;
        } while (iVar6 != 0);
      }
    }
    FUN_0040faa0(local_30);
    if ((param_4 != '\0') && (cVar2 = FUN_00819110(*(undefined8 *)(local_40 + 0x2c)), cVar2 == '\0')
       ) {
      FUN_0043c4c0(&local_60,param_1,L".fst");
      cVar2 = FUN_00819110(local_60);
      if (cVar2 != '\0') {
        FUN_004133f0(local_40 + 0x2c,local_60);
      }
    }
    iVar6 = FUN_008f5b40(local_40);
    lVar1 = local_40;
    if (iVar6 == 0) {
      local_70 = local_40;
      local_40 = 0;
      FUN_0040faa0(lVar1);
    }
    if (local_40 != 0) {
      FUN_008f4b50(local_40);
    }
    local_38 = local_40;
  }
  FUN_00412e40(&local_150,0x10);
  FUN_00412e40(&local_c0,8);
  FUN_00412d60(&local_60);
  return local_38;
}


=== decomp 910810 -> FUN_00910810 @00910810 size=649

/* WARNING: Type propagation algorithm not settling */

void FUN_00910810(undefined8 param_1)

{
  
  local_48[2] = 0;
  local_48[1] = 0;
  local_48[0] = 0;
  local_50 = param_1;
  FUN_00913d40(param_1,local_48 + 2,L"ps_vendorname");
  local_1c = FUN_00913be0(local_50,L"ps_magic",0);
  FUN_00913a10(local_50,local_2c,L"ps_guid");
  uVar2 = FUN_00913be0(local_50,L"ps_plugclass",0);
  FUN_00913d40(local_50,local_48 + 1,L"ps_category");
  local_30 = FUN_00913be0(local_50,L"ps_scanflags",0);
  plVar6 = local_48;
  FUN_00913d40(local_50,plVar6,L"ps_pluginfilename_fl");
  bVar1 = (byte)uVar2;
  if (local_48[0] != 0) {
    if (uVar2 < 0x10) {
      bVar7 = ((ushort)((int)CONCAT62((int6)((ulonglong)plVar6 >> 0x10),1) << (bVar1 & 0x1f)) &
              DAT_00910bca) != 0;
    }
    else {
      bVar7 = false;
    }
    uVar3 = FUN_008f0ab0(bVar7,2);
    FUN_009105f0(auStack_78,uVar3,local_48[0],2);
  }
  plVar6 = local_48;
  FUN_00913d40(local_50,plVar6,L"ps_pluginfilename_vst_32");
  if (local_48[0] != 0) {
    if (uVar2 < 0x10) {
      bVar7 = ((ushort)((int)CONCAT62((int6)((ulonglong)plVar6 >> 0x10),1) << (bVar1 & 0x1f)) &
              DAT_00910bca) != 0;
    }
    else {
      bVar7 = false;
    }
    uVar3 = FUN_008f0ab0(bVar7,0);
    FUN_009105f0(auStack_78,uVar3,local_48[0],2);
  }
  plVar6 = local_48;
  FUN_00913d40(local_50,plVar6,L"ps_pluginfilename_vst_64");
  if (local_48[0] != 0) {
    if (uVar2 < 0x10) {
      bVar7 = ((ushort)((int)CONCAT62((int6)((ulonglong)plVar6 >> 0x10),1) << (bVar1 & 0x1f)) &
              DAT_00910bca) != 0;
    }
    else {
      bVar7 = false;
    }
    uVar3 = FUN_008f0ab0(bVar7,0);
    FUN_009105f0(auStack_78,uVar3,local_48[0],3);
  }
  plVar6 = local_48;
  FUN_00913d40(local_50,plVar6,L"ps_pluginfilename_vst3_32");
  if (local_48[0] != 0) {
    if (uVar2 < 0x10) {
      bVar7 = ((ushort)((int)CONCAT62((int6)((ulonglong)plVar6 >> 0x10),1) << (bVar1 & 0x1f)) &
              DAT_00910bca) != 0;
    }
    else {
      bVar7 = false;
    }
    uVar3 = FUN_008f0ab0(bVar7,7);
    FUN_009105f0(auStack_78,uVar3,local_48[0],2);
  }
  uVar5 = FUN_00913d40(local_50,local_48,L"ps_pluginfilename_vst3_64");
  if (local_48[0] != 0) {
    if (uVar2 < 0x10) {
      iVar4 = (int)CONCAT62((int6)((ulonglong)uVar5 >> 0x10),1) << (bVar1 & 0x1f);
      uVar3 = CONCAT31((int3)((uint)iVar4 >> 8),((ushort)iVar4 & DAT_00910bca) != 0);
    }
    else {
      uVar3 = 0;
    }
    uVar3 = FUN_008f0ab0(uVar3,7);
    FUN_009105f0(auStack_78,uVar3,local_48[0],3);
  }
  FUN_00412e40(local_48,3);
  return;
}


=== decomp 911940 -> FUN_00911940 @00911940 size=711

void FUN_00911940(undefined8 param_1,undefined8 param_2,undefined8 param_3,longlong param_4)

{
  
  local_40 = auStack_c8;
  local_80 = 0;
  local_58 = 0;
  local_48 = 0;
  local_50 = 0;
  local_28[0] = 0;
  local_30 = 0;
  local_38 = 0;
  FUN_0043c320(param_1);
  local_18 = FUN_00913450(PTR_DAT_009103e8,1,param_1,0);
  FUN_00914780(local_18,L"fileversion",2,0);
  uVar2 = FUN_008f5ca0(param_4);
  if ((uVar2 & 8) != 0) {
    FUN_00914780(local_18,L"iconindex",0x30,0);
    FUN_0043aa10(&local_50,0x40b6f6,6);
    FUN_00414c70(&local_48,&DAT_00911d34,local_50);
    FUN_00914880(local_18,L"color",local_48,0);
    local_a8 = 1;
    FUN_008f58b0(param_4,local_28,&local_30,&local_38);
    local_78 = local_28[0];
    local_70 = 0x11;
    local_68 = local_38;
    local_60 = 0x11;
    FUN_0043dd60(&local_58,L"%s / %s bit",&local_78,1);
    FUN_00914880(local_18,&DAT_00911d44,local_58,0);
  }
  FUN_00914880(local_18,L"ps_name",*(undefined8 *)(param_4 + 0x18),0);
  FUN_008f1820(&local_80,*(undefined8 *)(param_4 + 0x2c),param_2,L"%FLPluginDBPath%");
  FUN_00914880(local_18,L"ps_presetfilename",local_80,0);
  uVar1 = FUN_008f5b40(param_4);
  FUN_00914780(local_18,L"ps_files",uVar1,0);
  local_88 = local_18;
  local_90 = FUN_00913f40;
  uVar3 = FUN_00414850(param_3);
  FUN_008f53e0(param_4,&local_90,uVar3);
  FUN_00913e30(local_18);
  FUN_0040faa0(local_18);
  FUN_0043c0a0(param_1,2,1);
  FUN_00412d60(&local_80);
  FUN_00412e40(&local_58,3);
  FUN_00412e40(&local_38,3);
  return;
}


=== decomp 911e10 -> FUN_00911e10 @00911e10 size=2654

longlong FUN_00911e10(longlong *param_1,undefined8 param_2,undefined8 param_3,longlong param_4,
                     char param_5)

{
  
  local_b0 = auStack_1d8;
  local_1a0 = 0;
  local_1a8 = 0;
  local_190 = 0;
  local_198 = 0;
  local_180 = 0;
  local_188 = 0;
  local_170 = 0;
  local_178 = 0;
  local_168 = 0;
  local_160 = 0;
  local_158 = 0;
  local_150 = 0;
  local_148 = 0;
  local_140 = 0;
  local_138 = 0;
  local_130 = 0;
  local_118 = 0;
  local_110 = 0;
  local_108 = 0;
  local_f8 = 0;
  local_100 = 0;
  local_f0 = 0;
  local_e8 = 0;
  local_e0 = 0;
  local_b8 = 0;
  local_80 = 0;
  local_88 = 0;
  local_60 = FUN_008f4e00(PTR_DAT_008f1ca0,1);
  local_50 = FUN_00511fe0(PTR_PTR_004cf268,1);
  local_40 = FUN_00913450(PTR_DAT_009103e8,1,0,0);
  (**(code **)(*param_1 + 0xa0))(param_1,param_2,local_50);
  local_30 = (longlong *)0x0;
  local_30 = (longlong *)FUN_0050dfc0(PTR_DAT_004cd0e0,1,local_50);
  while( true ) {
    local_98 = local_30;
    iVar5 = (**(code **)(*(longlong *)local_30[2] + 0x28))((longlong *)local_30[2]);
    local_99 = (int)local_98[1] < iVar5 + -1;
    if (!(bool)local_99) break;
    *(int *)(local_98 + 1) = (int)local_98[1] + 1;
    FUN_0050e080(local_30,&local_88);
    local_1b8 = 0;
    (**(code **)(*param_1 + 0x10))(param_1,&local_80,param_2,local_88);
    local_d8 = local_88;
    local_d0 = 0x11;
    local_c8 = local_80;
    local_c0 = 0x11;
    FUN_0043dd60(&local_b8,L"%s=%s",&local_d8,1);
    (**(code **)(**(longlong **)(local_40 + 0x14) + 0x78))(*(longlong **)(local_40 + 0x14),local_b8)
    ;
  }
  if (local_30 != (longlong *)0x0) {
    (**(code **)(*local_30 + -0x20))(local_30,1);
  }
  local_8c = FUN_00913be0(local_40,L"fileversion",1);
  FUN_00913d40(local_40,&local_e0,L"ps_name");
  FUN_004133f0(local_60 + 0x18,local_e0);
  FUN_00913d40(local_40,&local_e8,L"ps_presetfilename");
  FUN_004133f0(local_60 + 0x2c,local_e8);
  FUN_008f19b0(&local_f0,*(undefined8 *)(local_60 + 0x2c),param_3,L"%FLPluginDBPath%");
  FUN_004133f0(local_60 + 0x2c,local_f0);
  if (local_8c == 1) {
    FUN_00910810(local_40,local_60,param_5);
  }
  else if (local_8c == 2) {
    iVar5 = FUN_00913be0(local_40,L"ps_files",0);
    local_74 = 0;
    local_70 = iVar5;
    if (-1 < iVar5 + -1) {
      do {
        local_68 = FUN_008f6ad0(PTR_DAT_008f1b10,1);
        FUN_009138a0(local_40,&local_100,L"ps_file_name",local_74);
        FUN_00913d40(local_40,&local_f8,local_100);
        FUN_004133f0(local_68 + 8,local_f8);
        FUN_009138a0(local_40,&local_108,L"ps_file_filename",local_74);
        FUN_00913d40(local_40,&local_80,local_108);
        if (param_4 != 0) {
          FUN_008f19b0(&local_110,local_80,param_4,L"%FLPath%");
          FUN_00413480(&local_80,local_110);
        }
        FUN_004133f0(local_68 + 0x10,local_80);
        FUN_009138a0(local_40,&local_118,L"ps_file_magic",local_74);
        uVar6 = FUN_00913be0(local_40,local_118,0);
        *(undefined4 *)(local_68 + 0x20) = uVar6;
        FUN_009138a0(local_40,&local_130,L"ps_file_guid",local_74);
        FUN_00913a10(local_40,&local_128,local_130);
        *(undefined8 *)(local_68 + 0x24) = local_128;
        *(undefined8 *)(local_68 + 0x2c) = uStack_120;
        FUN_009138a0(local_40,&local_138,L"ps_file_date",local_74);
        uVar8 = FUN_009139f0(local_40,local_138);
        *(undefined8 *)(local_68 + 0x34) = uVar8;
        FUN_009138a0(local_40,&local_140,L"ps_file_size",local_74);
        uVar8 = FUN_00913ae0(local_40,local_140,0);
        *(undefined8 *)(local_68 + 0x3c) = uVar8;
        FUN_009138a0(local_40,&local_148,L"ps_file_plugclass",local_74);
        uVar6 = FUN_00913be0(local_40,local_148,0xffffffff);
        *(undefined4 *)(local_68 + 0x18) = uVar6;
        FUN_009138a0(local_40,&local_150,L"ps_file_type",local_74);
        uVar8 = local_150;
        uVar4 = FUN_00913be0(local_40,local_150,0);
        *(ushort *)(local_68 + 0x1c) = uVar4;
        if (uVar4 < 8) {
          bVar7 = ((byte)((int)CONCAT71((int7)((ulonglong)uVar8 >> 8),1) << ((byte)uVar4 & 0x1f)) &
                  DAT_00912ba6) != 0;
        }
        else {
          bVar7 = false;
        }
        if (!bVar7) {
          *(undefined2 *)(local_68 + 0x1c) = 0;
        }
        FUN_009138a0(local_40,&local_158,L"ps_file_bitsize",local_74);
        uVar2 = FUN_00913960(local_40,local_158);
        *(undefined1 *)(local_68 + 0x1e) = uVar2;
        FUN_009138a0(local_40,&local_160,L"ps_file_arch",local_74);
        uVar2 = FUN_00913980(local_40,local_160);
        *(undefined1 *)(local_68 + 0x1f) = uVar2;
        FUN_009138a0(local_40,&local_168,L"ps_file_scanflags",local_74);
        uVar2 = FUN_00913cd0(local_40,local_168);
        *(undefined1 *)(local_68 + 0x4c) = uVar2;
        FUN_009138a0(local_40,&local_178,L"ps_file_vendorname",local_74);
        FUN_00913d40(local_40,&local_170,local_178);
        FUN_004133f0(local_68 + 0x50,local_170);
        FUN_009138a0(local_40,&local_188,L"ps_file_category",local_74);
        FUN_00913d40(local_40,&local_180,local_188);
        FUN_004133f0(local_68 + 0x58,local_180);
        FUN_009138a0(local_40,&local_198,L"ps_file_idstring",local_74);
        FUN_00913d40(local_40,&local_190,local_198);
        FUN_004133f0(local_68 + 0x60,local_190);
        FUN_009138a0(local_40,&local_1a8,L"ps_compatibility",local_74);
        FUN_00913d40(local_40,&local_1a0,local_1a8);
        FUN_00510750(*(undefined8 *)(local_68 + 0x68),local_1a0);
        local_69 = *(int *)(local_68 + 0x18) != -1;
        if ((bool)local_69) {
          FUN_008f49e0(local_60,local_68,0);
        }
        else {
          FUN_0040faa0(local_68);
        }
        local_74 = local_74 + 1;
        iVar5 = iVar5 + -1;
      } while (iVar5 != 0);
    }
  }
  lVar1 = local_40;
  local_38 = local_40;
  local_40 = 0;
  FUN_0040faa0(lVar1);
  uVar8 = local_50;
  local_48 = local_50;
  local_50 = 0;
  FUN_0040faa0(uVar8);
  if ((param_5 != '\0') && (cVar3 = FUN_00819110(*(undefined8 *)(local_60 + 0x2c)), cVar3 == '\0'))
  {
    FUN_0043c4c0(&local_80,param_2,L".fst");
    cVar3 = FUN_00819110(local_80);
    if (cVar3 != '\0') {
      FUN_004133f0(local_60 + 0x2c,local_80);
    }
  }
  iVar5 = FUN_008f5b40(local_60);
  lVar1 = local_60;
  if (iVar5 == 0) {
    local_a8 = local_60;
    local_60 = 0;
    FUN_0040faa0(lVar1);
  }
  if (local_60 != 0) {
    FUN_008f4b50(local_60);
  }
  local_58 = local_60;
  FUN_00412e40(&local_1a8,0x10);
  FUN_00412e40(&local_118,8);
  FUN_00412d60(&local_b8);
  FUN_00412e40(&local_88,2);
  return local_58;
}


=== decomp 912d10 -> FUN_00912d10 @00912d10 size=1065

void FUN_00912d10(longlong *param_1,undefined8 param_2,undefined8 param_3,undefined8 param_4,
                 longlong param_5)

{
  
  local_90 = auStack_118;
  local_e8 = 0;
  local_d0 = 0;
  local_a8 = 0;
  local_98 = 0;
  local_a0 = 0;
  local_38[0] = 0;
  local_40 = 0;
  local_48 = 0;
  local_50 = 0;
  local_58 = 0;
  local_60 = 0;
  local_68 = 0;
  local_28 = FUN_00913450(PTR_DAT_009103e8,1,param_2,0);
  FUN_00914780(local_28,L"fileversion",2,0);
  uVar3 = FUN_008f5ca0(param_5);
  if ((uVar3 & 8) != 0) {
    FUN_00914780(local_28,L"iconindex",0x30,0);
    FUN_0043aa10(&local_a0,0x40b6f6,6);
    FUN_00414c70(&local_98,&DAT_0091327c,local_a0);
    FUN_00914880(local_28,L"color",local_98,0);
    local_f8 = 1;
    FUN_008f58b0(param_5,local_38,&local_40,&local_48);
    local_c8 = local_38[0];
    local_c0 = 0x11;
    local_b8 = local_48;
    local_b0 = 0x11;
    FUN_0043dd60(&local_a8,L"%s / %s bit",&local_c8,1);
    FUN_00914880(local_28,&DAT_0091328c,local_a8,0);
  }
  FUN_00914880(local_28,L"ps_name",*(undefined8 *)(param_5 + 0x18),0);
  FUN_008f1820(&local_d0,*(undefined8 *)(param_5 + 0x2c),param_3,L"%FLPluginDBPath%");
  FUN_00914880(local_28,L"ps_presetfilename",local_d0,0);
  uVar1 = FUN_008f5b40(param_5);
  FUN_00914780(local_28,L"ps_files",uVar1,0);
  local_d8 = local_28;
  local_e0 = FUN_00913f40;
  uVar4 = FUN_00414850(param_4);
  FUN_008f53e0(param_5,&local_e0,uVar4);
  FUN_00413480(&local_58,param_2);
  local_20 = (longlong *)0x0;
  local_70 = *(undefined8 *)(local_28 + 0x14);
  local_20 = (longlong *)FUN_0050dfc0(PTR_DAT_004cd0e0,1,local_70);
  while( true ) {
    local_78 = local_20;
    iVar2 = (**(code **)(*(longlong *)local_20[2] + 0x28))((longlong *)local_20[2]);
    local_79 = (int)local_78[1] < iVar2 + -1;
    if (!(bool)local_79) break;
    *(int *)(local_78 + 1) = (int)local_78[1] + 1;
    FUN_0050e080(local_20,&local_50);
    FUN_00439c90(&local_e8,local_50);
    if (local_e8 != 0) {
      FUN_0065df50(local_50,&local_60,&local_68);
      (**(code **)(*param_1 + 0x18))(param_1,local_58,local_60,local_68);
    }
  }
  if (local_20 != (longlong *)0x0) {
    (**(code **)(*local_20 + -0x20))(local_20,1);
  }
  FUN_0040faa0(local_28);
  FUN_0043c0a0(param_2,2,1);
  FUN_00412d60(&local_e8);
  FUN_00412d60(&local_d0);
  FUN_00412e40(&local_a8,3);
  FUN_00412e40(&local_68,7);
  return;
}


=== decomp 913f40 -> FUN_00913f40 @00913f40 size=1099

void FUN_00913f40(undefined8 param_1,undefined8 param_2,undefined4 param_3,longlong param_4,
                 undefined8 param_5)

{
  
  local_98 = 0;
  local_a0 = 0;
  local_90 = 0;
  local_88 = 0;
  local_80 = 0;
  local_78 = 0;
  local_70 = 0;
  local_68 = 0;
  local_60 = 0;
  local_58 = 0;
  local_50 = 0;
  local_48 = 0;
  local_40 = 0;
  local_38 = 0;
  local_28 = 0;
  local_30 = 0;
  local_20[0] = 0;
  local_10 = 0;
  FUN_004148e0(&local_10,param_5);
  FUN_009138a0(param_1,local_20,L"ps_file_name",param_3);
  FUN_00914880(param_1,local_20[0],*(undefined8 *)(param_4 + 8),0);
  FUN_009138a0(param_1,&local_28,L"ps_file_filename",param_3);
  FUN_008f1820(&local_30,*(undefined8 *)(param_4 + 0x10),local_10,L"%FLPath%");
  FUN_00914880(param_1,local_28,local_30,0);
  FUN_009138a0(param_1,&local_38,L"ps_file_plugclass",param_3);
  FUN_00914780(param_1,local_38,*(undefined4 *)(param_4 + 0x18),0xffffffff);
  FUN_009138a0(param_1,&local_40,L"ps_file_type",param_3);
  FUN_00914780(param_1,local_40,*(undefined2 *)(param_4 + 0x1c),0);
  FUN_009138a0(param_1,&local_48,L"ps_file_bitsize",param_3);
  FUN_00913e60(param_1,local_48,*(undefined1 *)(param_4 + 0x1e));
  FUN_009138a0(param_1,&local_50,L"ps_file_arch",param_3);
  FUN_00913ea0(param_1,local_50,*(undefined1 *)(param_4 + 0x1f));
  if (*(int *)(param_4 + 0x20) != 0) {
    FUN_009138a0(param_1,&local_58,L"ps_file_magic",param_3);
    FUN_00914780(param_1,local_58,*(undefined4 *)(param_4 + 0x20),0);
  }
  cVar1 = IsEqualGUID(param_4 + 0x24,PTR_DAT_015e1f60);
  if (cVar1 == '\0') {
    FUN_009138a0(param_1,&local_60,L"ps_file_guid",param_3);
    FUN_00914690(param_1,local_60,param_4 + 0x24);
  }
  FUN_009138a0(param_1,&local_68,L"ps_file_date",param_3);
  FUN_00913f10(param_1,local_68,*(undefined8 *)(param_4 + 0x34),DAT_00914390);
  FUN_009138a0(param_1,&local_70,L"ps_file_size",param_3);
  FUN_00914700(param_1,local_70,*(undefined8 *)(param_4 + 0x3c),0);
  FUN_009138a0(param_1,&local_78,L"ps_file_scanflags",param_3);
  FUN_00914800(param_1,local_78,*(undefined1 *)(param_4 + 0x4c),DAT_009145c4);
  FUN_009138a0(param_1,&local_80,L"ps_file_vendorname",param_3);
  FUN_00914880(param_1,local_80,*(undefined8 *)(param_4 + 0x50),0);
  FUN_009138a0(param_1,&local_88,L"ps_file_category",param_3);
  FUN_00914880(param_1,local_88,*(undefined8 *)(param_4 + 0x58),0);
  FUN_009138a0(param_1,&local_90,L"ps_file_idstring",param_3);
  FUN_00914880(param_1,local_90,*(undefined8 *)(param_4 + 0x60),0);
  FUN_009138a0(param_1,&local_98,L"ps_compatibility",param_3);
  FUN_0050ee30(*(undefined8 *)(param_4 + 0x68),&local_a0);
  FUN_00914880(param_1,local_98,local_a0,0);
  FUN_00412e40(&local_a0,0x11);
  FUN_00412d60(&local_10);
  return;
}


=== decomp abe970 -> FUN_00abe970 @00abe970 size=231

void FUN_00abe970(undefined8 param_1,undefined8 param_2,undefined1 *param_3)

{
  
  local_20 = auStack_58;
  local_28 = 0;
  local_18 = 0;
  FUN_00412d60(param_2);
  *param_3 = 0;
  local_38 = L".NFO";
  FUN_00414da0(&local_18,3,param_1,L"plugin");
  cVar1 = FUN_00819110(local_18);
  if (cVar1 != '\0') {
    local_10 = FUN_00913450(PTR_DAT_009103e8,1,local_18,1);
    FUN_00913d40(local_10,&local_28,L"ps_vendorname");
    FUN_004133f0(param_2,local_28);
    iVar2 = FUN_00913be0(local_10,L"ps_dummy64bit",0);
    *param_3 = iVar2 != 0;
    FUN_0040faa0(local_10);
  }
  FUN_00412d60(&local_28);
  FUN_00412d60(&local_18);
  return;
}


