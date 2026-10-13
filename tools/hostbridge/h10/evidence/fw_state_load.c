=== decomp 870da0 -> FUN_00870da0 @00870da0 size=1042

void FUN_00870da0(longlong param_1,undefined8 param_2,int param_3)

{
  longlong *plVar1;
  undefined8 uVar2;
  undefined8 uVar3;
  undefined1 auStack_88 [32];
  undefined1 local_68;
  undefined1 *local_50;
  undefined8 local_48;
  undefined8 *local_40;
  longlong local_38;
  int local_2c;
  char local_25;
  int local_24;
  longlong *local_20;
  
  local_50 = auStack_88;
  local_20 = (longlong *)FUN_00654e90(PTR_PTR_00654540,1,param_2);
  local_2c = param_3;
  if (param_3 == 2) {
    plVar1 = *(longlong **)(param_1 + 0x5050);
    if (plVar1 != (longlong *)0x0) {
      local_68 = 0;
      (**(code **)(*plVar1 + 0x1a8))(plVar1,local_20,0,0);
    }
  }
  else {
    if (param_3 != 0) {
      if ((*(longlong *)(param_1 + 0x5050) == 0) && (*(longlong *)(param_1 + 0xf6c) != 0)) {
        FUN_00501370(*(undefined8 *)(param_1 + 0xf6c),0);
        plVar1 = *(longlong **)(param_1 + 0xf6c);
        uVar2 = (**(code **)(*plVar1 + 0x18))(plVar1);
        FUN_00501c60(local_20,plVar1,uVar2,0x100000);
      }
      else {
        local_24 = 0xc;
        (**(code **)(*local_20 + 0x38))(local_20,&local_24,4);
        FUN_008712b0(param_1,local_20);
      }
code_r0x00871146:
      FUN_0040ec50(local_20);
      if (param_3 == 0) {
        FUN_008707a0(param_1);
        (**(code **)(**(longlong **)(param_1 + 0x5058) + 0x98))(*(longlong **)(param_1 + 0x5058));
        FUN_008771a0(param_1,DAT_00871258);
      }
      FUN_005bf650();
      FUN_005bf680();
      return;
    }
    local_68 = 0;
    FUN_00873db0(param_1,L"SaveRestoreState - load",0,1);
    uVar2 = FUN_0087b090(param_1);
    FUN_007924d0(uVar2,4,0,0);
    *(undefined1 *)(param_1 + 0x120) = 0;
    *(undefined1 *)(param_1 + 0x121) = 0;
    local_40 = (undefined8 *)(param_1 + 0xf6c);
    local_48 = *local_40;
    *local_40 = 0;
    FUN_0040ec50(local_48);
    (**(code **)(*local_20 + 0x30))(local_20,&local_24,4);
    if (local_24 < 0xd) {
      if (local_24 != -1) {
        *(undefined1 *)(param_1 + 0x506c) = 1;
        FUN_008744b0(param_1);
        if (local_24 < 5) {
          local_25 = FUN_00875800(param_1,local_20,local_24);
        }
        else {
          local_25 = FUN_00875af0(param_1,local_20,local_24);
        }
        if (local_25 == '\0') {
          uVar2 = FUN_0040eb90(PTR_PTR_004c6c28,1);
          *(undefined8 *)(param_1 + 0xf6c) = uVar2;
          uVar3 = (**(code **)(*local_20 + 0x18))(local_20);
          FUN_005013f0(uVar2,uVar3);
          FUN_00501370(local_20,0);
          uVar2 = (**(code **)(*local_20 + 0x18))(local_20);
          FUN_00501c60(*(undefined8 *)(param_1 + 0xf6c),local_20,uVar2,0x100000);
        }
        FUN_008730c0(param_1,*(undefined4 *)(param_1 + 0x854),0);
        FUN_00873150(param_1,*(undefined4 *)(param_1 + 0x858),0);
        FUN_0086d3c0(param_1,0);
        uVar2 = FUN_0087b090(param_1);
        FUN_0078f910(uVar2);
        if (*(char *)(param_1 + 0x120) != '\0') {
          FUN_0087b090(param_1);
        }
        local_38 = FUN_0087b090(param_1);
        if (*(char *)(local_38 + 0xaa8) == '\x02') {
          uVar2 = FUN_0087b090(param_1);
          FUN_0078ebb0(uVar2);
        }
        *(undefined1 *)(param_1 + 0x506c) = 0;
        FUN_00870810(param_1);
        local_68 = 0;
        FUN_00873db0(param_1,L"Finished (SaveRestoreState)",0,0xffffffff);
        goto code_r0x00871146;
      }
    }
    else {
      uVar2 = FUN_0087b090(param_1);
      FUN_007924d0(uVar2,5,0,0);
    }
  }
  FUN_008711c0(0,local_50);
  return;
}


=== decomp 875af0 -> FUN_00875af0 @00875af0 size=5237

bool FUN_00875af0(longlong param_1,longlong *param_2,int param_3)

{
  undefined8 *puVar1;
  bool bVar2;
  byte bVar3;
  char cVar4;
  undefined1 uVar5;
  int iVar6;
  longlong lVar7;
  longlong lVar8;
  ulonglong uVar9;
  undefined8 uVar10;
  ulonglong uVar11;
  int iVar12;
  uint uVar13;
  undefined1 *puVar15;
  bool bVar16;
  bool bVar17;
  bool local_861;
  undefined8 local_858;
  undefined8 local_850;
  undefined8 local_848;
  undefined8 local_840;
  undefined8 local_838;
  undefined8 local_830;
  longlong local_828;
  undefined8 local_820;
  undefined8 local_818;
  undefined8 local_810;
  longlong local_808;
  undefined1 local_800;
  longlong local_7f8;
  undefined1 local_7f0;
  undefined8 local_7e8;
  undefined8 local_7e0;
  undefined8 local_7d8;
  undefined8 local_7d0 [2];
  undefined8 local_7c0;
  undefined8 local_7b8;
  undefined8 local_7b0;
  undefined1 local_7a4 [12];
  undefined8 local_798;
  uint local_790;
  int local_78c;
  undefined8 local_788;
  undefined8 uStack_780;
  uint local_774;
  undefined1 local_770 [8];
  undefined1 local_768 [8];
  undefined1 local_760 [8];
  int local_758;
  undefined1 local_754 [16];
  undefined1 local_744;
  char local_743;
  undefined1 local_740 [8];
  longlong local_738;
  longlong local_730;
  longlong local_728;
  undefined8 local_720;
  uint local_718;
  undefined1 local_714 [522];
  undefined1 local_50a [522];
  undefined8 local_300;
  undefined8 uStack_2f8;
  uint local_2f0;
  int local_2e4;
  undefined1 local_2e0 [524];
  undefined4 local_d4;
  uint local_d0 [4];
  longlong local_c0;
  longlong local_b8;
  longlong local_b0;
  undefined1 local_a1 [16];
  int local_91;
  undefined1 local_8d [16];
  undefined1 local_7d [9];
  uint local_74;
  undefined4 local_70;
  undefined4 local_6b;
  ushort local_67;
  undefined4 local_64;
  undefined4 local_60;
  byte local_5c;
  int local_50;
  longlong local_4c;
  undefined8 *puVar14;
  
  local_850 = 0;
  local_858 = 0;
  local_848 = 0;
  local_838 = 0;
  local_840 = 0;
  local_830 = 0;
  local_828 = 0;
  local_818 = 0;
  local_820 = 0;
  local_7e8 = 0;
  local_810 = 0;
  local_7d8 = 0;
  local_7e0 = 0;
  local_7d0[0] = 0;
  local_b0 = 0;
  local_b8 = 0;
  local_c0 = 0;
  local_720 = 0;
  local_728 = 0;
  local_730 = 0;
  local_738 = 0;
  local_798 = 0;
  local_7b0 = 0;
  local_7c0 = 0;
  FUN_00414500(&local_774,PTR_DAT_008685f8);
  local_861 = true;
  FUN_00411f10(&local_b0);
  FUN_00411f10(&local_730);
  FUN_00411f10(&local_798);
  (**(code **)PTR_DAT_008f6868)(&local_64,0x14);
  FUN_008744d0(param_1,local_7d,0);
  (**(code **)PTR_DAT_008f6868)(local_8d,0x10);
  (**(code **)PTR_DAT_008f6868)(local_d0,0x10);
  (**(code **)PTR_DAT_008f6868)(&local_91,4);
  (**(code **)PTR_DAT_008f6868)(local_a1,0x10);
  local_d4 = 1;
  FUN_00417080(&local_b8,PTR_DAT_00875a60);
  FUN_00417080(&local_c0,PTR_DAT_00875aa8);
  FUN_0086abc0(&local_774);
  FUN_0087afe0(param_1 + 0x864);
  *(int *)(param_1 + 0x864) = param_3;
  bVar3 = DAT_0087701c;
  if (8 < param_3) {
    bVar3 = DAT_0087701c | 2;
  }
  FUN_0074a5b0(local_7a4,param_2,bVar3);
  while( true ) {
    lVar7 = FUN_00501350(param_2);
    lVar8 = (**(code **)(*param_2 + 0x18))(param_2);
    if (lVar8 <= lVar7) break;
    FUN_0074a8e0(local_7a4,&local_50);
    if (local_50 < 0x35) {
      if (local_50 == 0x34) {
        FUN_0074a970(local_7a4,0x10,local_a1,&local_50,1);
      }
      else if (local_50 < 0x20) {
        if (local_50 == 0x1f) {
          iVar12 = (int)(local_4c / 0xc);
          FUN_00416eb0(&local_b8,PTR_DAT_00875a60,1,(longlong)iVar12);
          FUN_0074a970(local_7a4,(longlong)(iVar12 * 0xc),local_b8,&local_50,1);
        }
        else if (local_50 == 1) {
          FUN_0074a970(local_7a4,0x14,&local_64,&local_50,1);
          if (local_5c == 0) {
            local_5c = 2;
          }
          lVar7 = *(longlong *)(param_1 + 0x874);
          *(undefined4 *)(lVar7 + 0x34) = local_64;
          *(undefined4 *)(lVar7 + 0x38) = local_60;
          *(uint *)(lVar7 + 0x1c) = (uint)local_5c;
        }
        else if (local_50 == 2) {
          FUN_0074a970(local_7a4,0x19,local_7d,&local_50,1);
        }
        else if (local_50 == 0x1e) {
          FUN_0074a970(local_7a4,0x10,local_8d,&local_50,1);
        }
      }
      else if (local_50 == 0x20) {
        iVar12 = (int)(local_4c / 0xc);
        FUN_00416eb0(&local_c0,PTR_DAT_00875aa8,1,(longlong)iVar12);
        FUN_0074a970(local_7a4,(longlong)(iVar12 * 0xc),local_c0,&local_50,1);
      }
      else if (local_50 == 0x32) {
        FUN_0074a970(local_7a4,0x10,local_d0,&local_50,1);
      }
      else if (local_50 == 0x33) {
        FUN_0074a970(local_7a4,4,&local_91,&local_50,1);
      }
    }
    else if (local_50 < 0x39) {
      if (local_50 == 0x38) {
        FUN_0074aa40(&local_798,local_7a4,local_4c,0);
      }
      else if (local_50 == 0x35) {
        FUN_005013f0(*(undefined8 *)(param_1 + 0x86c),local_4c);
        FUN_0074a970(local_7a4,local_4c,*(undefined8 *)(*(longlong *)(param_1 + 0x86c) + 8),
                     &local_50,1);
      }
      else if (local_50 == 0x36) {
        FUN_0074aa40(&local_b0,local_7a4,local_4c,0);
      }
      else if (local_50 == 0x37) {
        FUN_0074aa40(local_7d0,local_7a4,local_4c,0);
        local_7b8 = local_7d0[0];
        FUN_0044acd0(&local_7b8,&local_730,0x2f);
      }
    }
    else if (local_50 == 0x39) {
      FUN_0074a970(local_7a4,4,&local_d4,&local_50,1);
    }
    else if (local_50 == 0x3a) {
      FUN_0074aa40(&local_7b0,local_7a4,local_4c,0);
    }
    FUN_0074abd0(local_7a4,&local_50);
  }
  *(undefined1 *)(param_1 + 0x898) = 1;
  if (*(char *)(param_1 + 0x848) == '\0') {
    lVar7 = FUN_0087b090(param_1);
    if (*(byte *)(lVar7 + 0xaa8) < 8) {
      bVar16 = ((byte)((int)CONCAT71((int7)((ulonglong)lVar7 >> 8),1) <<
                      (*(byte *)(lVar7 + 0xaa8) & 0x1f)) & DAT_0087701d) != 0;
    }
    else {
      bVar16 = false;
    }
    if (!bVar16) {
      lVar7 = FUN_0087b090(param_1);
      *(undefined1 *)(param_1 + 0x898) = *(undefined1 *)(lVar7 + 0xaa8);
    }
  }
  else {
    *(char *)(param_1 + 0x898) = *(char *)(param_1 + 0x848);
    *(undefined1 *)(param_1 + 0x848) = 0;
  }
  bVar16 = (local_74 & 0x400000) == 0x400000;
  lVar7 = *(longlong *)(param_1 + 0x874);
  *(bool *)(lVar7 + 0x18) = bVar16;
  if (!bVar16) {
    *(bool *)(lVar7 + 0x19) = (local_74 & 1) != 0;
    *(bool *)(lVar7 + 0x20) = (local_74 & 2) != 0;
    *(bool *)(lVar7 + 0x2c) = (local_74 & 4) != 0;
    *(bool *)(lVar7 + 0x30) = (local_74 & 8) != 0;
    *(bool *)(lVar7 + 0x44) = (local_74 & 0x10) != 0;
    *(bool *)(lVar7 + 0x2d) = (local_74 & 0x80) != 0;
    *(bool *)(lVar7 + 0x29) = (local_74 & 0x40) == 0;
    *(bool *)(lVar7 + 0x3d) = (local_74 & 0x20000) != 0;
    if (6 < param_3) {
      *(bool *)(lVar7 + 0x28) = (local_74 & 0x20) == 0;
      *(bool *)(lVar7 + 0x2e) = (local_74 & 0x800) != 0;
      *(bool *)(lVar7 + 0x31) = (local_74 & 0x2000) != 0;
      *(bool *)(lVar7 + 0x32) = (local_74 & 0x4000) != 0;
      *(bool *)(lVar7 + 0x33) = (local_74 & 0x8000) != 0;
      *(bool *)(lVar7 + 0x2a) = (local_74 & 0x1000) != 0;
      *(bool *)(lVar7 + 0x3c) = (local_74 & 0x10000) != 0;
    }
    if (9 < param_3) {
      *(bool *)(*(longlong *)(param_1 + 0x874) + 0x2b) = (local_74 & 0x20000000) != 0;
      *(bool *)(*(longlong *)(param_1 + 0x874) + 0x51) = (local_74 & 0x40000000) != 0;
    }
    bVar16 = (local_74 & 0x4000000) != 0;
    if ((!bVar16) && (param_3 < 0xb)) {
      if ((local_74 & 0x200) == 0) {
        bVar16 = true;
      }
      else {
        bVar16 = (local_74 & 0x80000) != 0;
      }
    }
    (**(code **)(**(longlong **)(param_1 + 0x5064) + 0x120))
              (*(longlong **)(param_1 + 0x5064),bVar16);
    (**(code **)(**(longlong **)(param_1 + 0x5064) + 0x110))
              (*(longlong **)(param_1 + 0x5064),(local_74 & 0x200000) != 0);
    lVar7 = *(longlong *)(param_1 + 0x874);
    *(undefined1 *)(lVar7 + 0x3f) =
         *(undefined1 *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x3f);
    *(undefined1 *)(lVar7 + 0x45) =
         *(undefined1 *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x45);
    (**(code **)(**(longlong **)(param_1 + 0x5064) + 0x128))
              (*(longlong **)(param_1 + 0x5064),(local_74 & 0x800000) != 0);
    lVar7 = *(longlong *)(param_1 + 0x874);
    *(undefined1 *)(lVar7 + 0x47) =
         *(undefined1 *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x47);
    *(bool *)(lVar7 + 0x48) = (local_74 & 0x1000000) != 0;
    *(bool *)(lVar7 + 0x49) = (local_74 & 0x2000000) == 0;
    *(bool *)(lVar7 + 0x52) = (local_74 & 0x80000000) == 0;
    *(undefined4 *)(lVar7 + 0x4c) = local_6b;
    *(bool *)(lVar7 + 0x50) = (local_74 & 0x10000000) != 0;
    *(bool *)(lVar7 + 0x53) = (local_67 & 1) != 0;
    *(bool *)(lVar7 + 0x54) = (local_67 & 4) == 0;
    *(bool *)(lVar7 + 0x55) = (local_67 & 8) != 0;
    *(bool *)(lVar7 + 0x3e) = (local_67 & 0x10) == 0;
  }
  *(bool *)(param_1 + 0x121) = (local_74 & 0x100) == 0;
  uVar9 = 0;
  if (local_b8 != 0) {
    uVar9 = *(ulonglong *)(local_b8 + -8);
  }
  uVar11 = 0;
  if (local_c0 != 0) {
    uVar11 = *(ulonglong *)(local_c0 + -8);
  }
  FUN_0087af90(param_1 + 0x864,uVar9 & 0xffffffff,uVar11 & 0xffffffff);
  iVar12 = *(int *)(param_1 + 0x87c);
  iVar6 = 0;
  if (iVar12 - 1U < 0x80000000) {
    do {
      puVar14 = (undefined8 *)(*(longlong *)(param_1 + 0x880) + (longlong)iVar6 * 0xc);
      puVar1 = (undefined8 *)(local_b8 + (longlong)iVar6 * 0xc);
      *puVar14 = *puVar1;
      *(undefined4 *)(puVar14 + 1) = *(undefined4 *)(puVar1 + 1);
      iVar6 = iVar6 + 1;
      iVar12 = iVar12 + -1;
    } while (iVar12 != 0);
  }
  iVar12 = *(int *)(param_1 + 0x888);
  iVar6 = 0;
  if (-1 < iVar12 + -1) {
    do {
      puVar14 = (undefined8 *)(*(longlong *)(param_1 + 0x88c) + (longlong)iVar6 * 0xc);
      puVar1 = (undefined8 *)(local_c0 + (longlong)iVar6 * 0xc);
      *puVar14 = *puVar1;
      *(undefined4 *)(puVar14 + 1) = *(undefined4 *)(puVar1 + 1);
      iVar6 = iVar6 + 1;
      iVar12 = iVar12 + -1;
    } while (iVar12 != 0);
  }
  *(undefined4 *)(*(longlong *)(param_1 + 0x874) + 0x24) = local_70;
  (**(code **)PTR_DAT_008f6868)(&local_718,0x644);
  local_790 = 0xffffffff;
  local_718 = local_d0[0];
  bVar16 = false;
  if ((local_74 & 0x100000) == 0x100000) {
    bVar16 = ((local_74 & 0x400) == 0x400) !=
             (*(char *)(*(longlong *)(param_1 + 0x5064) + 0x2d) == '\x03');
  }
  if ((bVar16 == false) && ((local_74 & 0x200) != 0x200)) {
    bVar2 = false;
  }
  else {
    bVar2 = true;
  }
  if (local_d0[0] == 0) {
LAB_008766a1:
    local_2e4 = local_91;
    local_774 = local_d0[0];
    FUN_00412630(local_770,local_730);
    FUN_00412630(local_768,local_b0);
    FUN_00412630(local_760,local_798);
    local_758 = local_2e4;
    FUN_00409bb0(local_a1,local_754,0x10);
    local_744 = (local_74 & 0x400) == 0x400;
    local_743 = bVar16;
    FUN_00871fe0(param_1,&local_730,&local_774,&local_790);
    FUN_0043a7f0(local_50a,local_730,0x104);
    local_861 = local_730 != 0;
    if (local_861) {
      FUN_00413930(&local_7e0,local_50a,0x105);
      FUN_005d4a40(&local_7d8,local_7e0);
      FUN_0043a7f0(local_714,local_7d8,0x104);
    }
    else {
      FUN_0043a7f0(local_714,local_b0,0x104);
    }
    local_2f0 = local_2f0 | 2;
    puVar14 = &local_300;
    FUN_00409bb0(local_a1,puVar14,0x10);
  }
  else if (local_d0[0] == 1) {
LAB_00876802:
    FUN_0043a7f0(local_714,local_b0,0x104);
    FUN_00409bb0(local_a1,&local_300,0x10);
    puVar14 = (undefined8 *)PTR_DAT_008f6f28;
    cVar4 = FUN_004378e0(&local_300,PTR_DAT_008f6f28);
    if (cVar4 != '\0') {
      local_808 = local_b0;
      local_800 = 0x11;
      FUN_00438ce0(&local_810,5);
      local_7f8 = local_810;
      local_7f0 = 0x11;
      FUN_0043ad90(&local_7e8,L"%s|%s",&local_808,1);
      FUN_0041b300(&local_720,local_7e8);
      uVar10 = FUN_00413080(local_720);
      puVar14 = *(undefined8 **)(param_1 + 8);
      (**(code **)**(undefined8 **)(param_1 + 0xbc))
                (*(undefined8 **)(param_1 + 0xbc),puVar14,0x4a,uVar10,3);
      local_861 = false;
    }
  }
  else {
    if (local_d0[0] == 4) goto LAB_008766a1;
    if (local_d0[0] == 5) goto LAB_00876802;
    local_2e4 = local_91;
    local_774 = local_d0[0];
    FUN_00412630(local_770,local_730);
    FUN_00412630(local_768,local_b0);
    FUN_00412630(local_760,local_798);
    local_758 = local_2e4;
    FUN_00409bb0(local_a1,local_754,0x10);
    local_744 = (local_74 & 0x400) == 0x400;
    local_743 = bVar16;
    FUN_00412630(local_740,local_7b0);
    FUN_0043a7f0(local_2e0,local_7b0,0x104);
    FUN_0043a7f0(local_50a,local_730,0x104);
    FUN_00871fe0(param_1,&local_730,&local_774,&local_790);
    if ((local_730 != 0) || (local_790 == 0xffffffff)) {
      FUN_0043a7f0(local_50a,local_730,0x104);
    }
    if (local_b0 == 0) {
      FUN_00413930(&local_820,local_50a,0x105);
      FUN_005d4a40(&local_818,local_820);
      FUN_0043a7f0(local_714,local_818,0x104);
    }
    else {
      FUN_0043a7f0(local_714,local_b0,0x104);
    }
    puVar14 = &local_300;
    FUN_00409bb0(local_a1,puVar14,0x10);
  }
  if (local_718 < 8) {
    uVar13 = (int)CONCAT71((int7)((ulonglong)puVar14 >> 8),1) << ((byte)local_718 & 0x1f);
    puVar14 = (undefined8 *)(ulonglong)uVar13;
    bVar16 = ((byte)uVar13 & DAT_00877038) != 0;
  }
  else {
    bVar16 = false;
  }
  if (bVar16) {
    if (local_790 < 8) {
      uVar13 = (int)CONCAT71((int7)((ulonglong)puVar14 >> 8),1) << ((byte)local_790 & 0x1f);
      puVar14 = (undefined8 *)(ulonglong)uVar13;
      bVar16 = ((byte)uVar13 & DAT_00877038) != 0;
    }
    else {
      bVar16 = false;
    }
    if (bVar16) goto LAB_00876b09;
    bVar16 = true;
  }
  else {
LAB_00876b09:
    bVar16 = false;
  }
  if (local_790 != 0xffffffff) {
    if ((local_718 == 4) && (local_790 == 7)) {
      local_718 = 8;
    }
    else if ((local_718 == 8) && (local_790 == 0)) {
      local_718 = 4;
    }
    else {
      local_718 = local_790;
    }
    local_2e4 = local_78c;
    if (local_78c != 0) {
      local_2f0 = local_2f0 | 2;
    }
    puVar14 = (undefined8 *)PTR_DAT_008f6f28;
    cVar4 = FUN_004378e0(&local_788,PTR_DAT_008f6f28);
    if (cVar4 == '\0') {
      local_300 = local_788;
      uStack_2f8 = uStack_780;
    }
  }
  if (local_790 < 0x10) {
    bVar17 = ((ushort)((int)CONCAT62((int6)((ulonglong)puVar14 >> 0x10),1) <<
                      ((byte)local_790 & 0x1f)) & DAT_00877039) != 0;
  }
  else {
    bVar17 = false;
  }
  *(bool *)(param_1 + 0x8a4) = bVar17;
  bVar3 = DAT_0087703b;
  if ((bVar2) && (((local_74 & 0x40000) == 0x40000 || (param_3 < 8)))) {
    bVar3 = DAT_0087703b | 0x10;
  }
  if (bVar16) {
    bVar3 = bVar3 | 0x80;
    *(int *)(param_1 + 0x89c) = local_91;
    *(undefined4 *)(param_1 + 0x8a0) = local_d4;
  }
  FUN_0086e1a0(param_1,&local_718,bVar3);
  if (((local_74 & 0x40000) == 0x40000) || ((param_3 < 8 && ((local_74 & 0x400) != 0x400)))) {
    uVar5 = 1;
  }
  else {
    uVar5 = 0;
  }
  *(undefined1 *)(param_1 + 0xf68) = uVar5;
  if (*(longlong *)(param_1 + 0x85c) != 0) goto LAB_00876eac;
  if (*(longlong *)(param_1 + 0x5050) == 0) {
    puVar15 = local_50a;
    FUN_00413930(&local_828,puVar15,0x105);
    if (local_828 == 0) {
      if (local_718 < 0x10) {
        bVar16 = ((ushort)((int)CONCAT62((int6)((ulonglong)puVar15 >> 0x10),1) <<
                          ((byte)local_718 & 0x1f)) & DAT_0087703c) != 0;
      }
      else {
        bVar16 = false;
      }
      if (bVar16) goto LAB_00876ea7;
    }
    FUN_0074b040(&local_728,local_718,0);
    FUN_00413930(&local_738,local_714,0x105);
    if (local_738 == 0) {
      FUN_00413930(&local_830,local_50a,0x105);
      FUN_005d4a40(&local_738,local_830);
    }
    FUN_005e2f90(&local_840,L"Error|Something went wrong loading the %s plugin |%s|.");
    local_808 = local_728;
    local_800 = 0x11;
    local_7f8 = local_738;
    local_7f0 = 0x11;
    FUN_0043ad90(&local_838,local_840,&local_808,1);
    FUN_00412630(&local_728,local_838);
    FUN_005e2f90(&local_848,L"Please make sure it\'s installed and registered properly.");
    FUN_00413d90(&local_728,3,local_728,&DAT_008770c8,local_848);
    local_808 = local_b0;
    local_800 = 0x11;
    FUN_00438ce0(&local_858,local_718);
    local_7f8 = local_858;
    local_7f0 = 0x11;
    FUN_0043ad90(&local_850,L"%s|%s",&local_808,1);
    FUN_0041b300(&local_720,local_850);
    uVar10 = FUN_00413080(local_720);
    (**(code **)**(undefined8 **)(param_1 + 0xbc))
              (*(undefined8 **)(param_1 + 0xbc),*(undefined8 *)(param_1 + 8),0x4a,uVar10,0);
    local_7c0 = 0;
    FUN_00411f10(&local_7c0);
  }
LAB_00876ea7:
  local_861 = false;
LAB_00876eac:
  FUN_0086ac20(&local_774);
  FUN_00411ff0(&local_858,10);
  FUN_00411ff0(&local_7e8,4);
  FUN_00411f10(&local_7b0);
  FUN_00411f10(&local_798);
  FUN_00414b20(&local_774,PTR_DAT_008685f8);
  FUN_00411ff0(&local_738,3);
  FUN_00411f60(&local_720);
  FUN_00417080(&local_c0,PTR_DAT_00875aa8);
  FUN_00417080(&local_b8,PTR_DAT_00875a60);
  FUN_00411f10(&local_b0);
  return local_861;
}


=== decomp 875800 -> FUN_00875800 @00875800 size=608

undefined4 FUN_00875800(longlong param_1,longlong *param_2,int param_3)

{
  longlong *plVar1;
  longlong lVar2;
  undefined4 uVar3;
  int iVar4;
  longlong lVar5;
  int iVar6;
  byte local_3d;
  int local_3c [3];
  
  local_3c[0] = 0;
  if (param_3 == 3) {
    (**(code **)(*param_2 + 0x30))(param_2,local_3c,4);
  }
  uVar3 = FUN_00874a40(param_1,param_2,param_3);
  if (3 < param_3) {
    (**(code **)(*param_2 + 0x30))(param_2,local_3c,4);
  }
  if (2 < param_3) {
    lVar5 = FUN_00501350(param_2);
    (**(code **)(*param_2 + 0x30))(param_2,param_1 + 0x854,4);
    (**(code **)(*param_2 + 0x30))(param_2,param_1 + 0x858,4);
    if (8 < local_3c[0]) {
      (**(code **)(*param_2 + 0x30))(param_2,&local_3d,1);
      plVar1 = *(longlong **)(param_1 + 0x5050);
      if (plVar1 != (longlong *)0x0) {
        (**(code **)(*plVar1 + 0x90))(plVar1,6,0);
      }
    }
    if (9 < local_3c[0]) {
      (**(code **)(*param_2 + 0x30))(param_2,&local_3d,1);
      if (*(longlong *)(param_1 + 0x5050) != 0) {
        if ((*(char *)(param_1 + 0x4fad) != '\0') && ((local_3d & 1) != 0)) {
          iVar6 = *(int *)(*(longlong *)(param_1 + 0x5050) + 0x718);
          iVar4 = 0;
          if (-1 < iVar6 + -1) {
            do {
              *(int *)(*(longlong *)(*(longlong *)(param_1 + 0x5050) + 0x734) + (longlong)iVar4 * 8)
                   = iVar4;
              iVar4 = iVar4 + 1;
              iVar6 = iVar6 + -1;
            } while (iVar6 != 0);
          }
        }
        (**(code **)(**(longlong **)(param_1 + 0x5050) + 0x90))
                  (*(longlong **)(param_1 + 0x5050),1,(local_3d & 2) == 0);
      }
    }
    if (10 < local_3c[0]) {
      (**(code **)(*param_2 + 0x30))(param_2,&local_3d,1);
      (**(code **)(**(longlong **)(param_1 + 0x5064) + 0xe0))
                (*(longlong **)(param_1 + 0x5064),(local_3d & 1) != 0);
      (**(code **)(**(longlong **)(param_1 + 0x5064) + 0xa8))
                (*(longlong **)(param_1 + 0x5064),(local_3d & 2) != 0);
      lVar2 = *(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc);
      *(bool *)(lVar2 + 0x2c) = (local_3d & 8) != 0;
      *(bool *)(lVar2 + 0x30) = (local_3d & 0x10) != 0;
      if (*(char *)(param_1 + 0x4fad) == '\0') {
        *(undefined1 *)(lVar2 + 0x44) = 0;
      }
      else {
        *(bool *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x44) =
             (local_3d & 0x20) != 0;
      }
      *(bool *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x28) =
           (local_3d & 0x40) == 0;
    }
    FUN_00501370(param_2,lVar5 + local_3c[0]);
  }
  *(undefined1 *)(param_1 + 0x121) = 1;
  return uVar3;
}


=== decomp 8744b0 -> FUN_008744b0 @008744b0 size=21

void FUN_008744b0(longlong param_1)

{
  *(undefined4 *)(param_1 + 0x858) = 0xffffffff;
  *(undefined4 *)(param_1 + 0x854) = 0xffffffff;
  return;
}


=== decomp 8744d0 -> FUN_008744d0 @008744d0 size=1376

void FUN_008744d0(longlong param_1,undefined1 *param_2,char param_3)

{
  longlong *plVar1;
  char cVar2;
  longlong lVar3;
  bool bVar4;
  
  (**(code **)PTR_DAT_008f6868)(param_2,0x19);
  *(undefined4 *)(param_2 + 9) = 0x7900;
  if (param_3 != '\0') {
    lVar3 = FUN_0087b090(param_1);
    *(undefined4 *)(param_2 + 1) = *(undefined4 *)(*(longlong *)(lVar3 + 0x6f0) + 0x98);
    lVar3 = FUN_0087b090(param_1);
    *(undefined4 *)(param_2 + 5) = *(undefined4 *)(*(longlong *)(lVar3 + 0x6f0) + 0x9c);
    lVar3 = FUN_0087b090(param_1);
    if (*(byte *)(lVar3 + 0xaa8) < 8) {
      bVar4 = ((byte)((int)CONCAT71((int7)((ulonglong)lVar3 >> 8),1) <<
                     (*(byte *)(lVar3 + 0xaa8) & 0x1f)) & DAT_00874a30) != 0;
    }
    else {
      bVar4 = false;
    }
    if (bVar4) {
      *param_2 = 0;
    }
    else {
      *param_2 = 1;
    }
    *(undefined4 *)(param_2 + 9) = 0x100;
    *(undefined2 *)(param_2 + 0x16) = 0;
    plVar1 = *(longlong **)(param_1 + 0x5050);
    if (plVar1 != (longlong *)0x0) {
      cVar2 = (**(code **)(*plVar1 + 0x88))(plVar1,6);
      if (cVar2 != '\0') {
        *(uint *)(param_2 + 9) = *(uint *)(param_2 + 9) | 0x80;
      }
      cVar2 = (**(code **)(**(longlong **)(param_1 + 0x5050) + 0x88))
                        (*(longlong **)(param_1 + 0x5050),1);
      if (cVar2 == '\0') {
        *(uint *)(param_2 + 9) = *(uint *)(param_2 + 9) | 0x40;
      }
      cVar2 = (**(code **)(**(longlong **)(param_1 + 0x5050) + 0x88))
                        (*(longlong **)(param_1 + 0x5050),2);
      if (cVar2 != '\0') {
        *(uint *)(param_2 + 9) = *(uint *)(param_2 + 9) | 0x800;
      }
      cVar2 = (**(code **)(**(longlong **)(param_1 + 0x5050) + 0x88))
                        (*(longlong **)(param_1 + 0x5050),9);
      if (cVar2 != '\0') {
        *(uint *)(param_2 + 9) = *(uint *)(param_2 + 9) | 0x2000;
      }
      cVar2 = (**(code **)(**(longlong **)(param_1 + 0x5050) + 0x88))
                        (*(longlong **)(param_1 + 0x5050),8);
      if (cVar2 != '\0') {
        *(uint *)(param_2 + 9) = *(uint *)(param_2 + 9) | 0x4000;
      }
      cVar2 = (**(code **)(**(longlong **)(param_1 + 0x5050) + 0x88))
                        (*(longlong **)(param_1 + 0x5050),7);
      if (cVar2 != '\0') {
        *(uint *)(param_2 + 9) = *(uint *)(param_2 + 9) | 0x8000;
      }
      cVar2 = (**(code **)(**(longlong **)(param_1 + 0x5050) + 0x88))
                        (*(longlong **)(param_1 + 0x5050),10);
      if (cVar2 != '\0') {
        *(uint *)(param_2 + 9) = *(uint *)(param_2 + 9) | 0x10000;
      }
      cVar2 = (**(code **)(**(longlong **)(param_1 + 0x5050) + 0x88))
                        (*(longlong **)(param_1 + 0x5050),0xb);
      if (cVar2 != '\0') {
        *(uint *)(param_2 + 9) = *(uint *)(param_2 + 9) | 0x40000000;
      }
      cVar2 = FUN_0040f040(*(undefined8 *)(param_1 + 0x5050),PTR_PTR_0076e6e0);
      if (cVar2 != '\0') {
        *(uint *)(param_2 + 9) = *(uint *)(param_2 + 9) | 0x200;
      }
      if (*(char *)(param_1 + 0xf68) != '\0') {
        *(uint *)(param_2 + 9) = *(uint *)(param_2 + 9) | 0x40000;
      }
      if (*(char *)(*(longlong *)(param_1 + 0x5050) + 0x761) == '\x03') {
        *(uint *)(param_2 + 9) = *(uint *)(param_2 + 9) | 0x400;
      }
    }
    if (*(char *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x19) != '\0') {
      *(uint *)(param_2 + 9) = *(uint *)(param_2 + 9) | 1;
    }
    if (*(char *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x20) != '\0') {
      *(uint *)(param_2 + 9) = *(uint *)(param_2 + 9) | 2;
    }
    if (*(char *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x2c) != '\0') {
      *(uint *)(param_2 + 9) = *(uint *)(param_2 + 9) | 4;
    }
    if (*(char *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x30) != '\0') {
      *(uint *)(param_2 + 9) = *(uint *)(param_2 + 9) | 8;
    }
    if (*(char *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x2a) != '\0') {
      *(uint *)(param_2 + 9) = *(uint *)(param_2 + 9) | 0x1000;
    }
    if (*(char *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x2b) != '\0') {
      *(uint *)(param_2 + 9) = *(uint *)(param_2 + 9) | 0x20000000;
    }
    if ((*(char *)(param_1 + 0x4fad) != '\0') &&
       (*(char *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x44) != '\0')) {
      *(uint *)(param_2 + 9) = *(uint *)(param_2 + 9) | 0x10;
    }
    if (*(char *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x28) == '\0') {
      *(uint *)(param_2 + 9) = *(uint *)(param_2 + 9) | 0x20;
    }
    if (*(char *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x3d) != '\0') {
      *(uint *)(param_2 + 9) = *(uint *)(param_2 + 9) | 0x20000;
    }
    if (*(char *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x3f) != '\0') {
      *(uint *)(param_2 + 9) = *(uint *)(param_2 + 9) | 0x4000000;
    }
    if (*(char *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x45) != '\0') {
      *(uint *)(param_2 + 9) = *(uint *)(param_2 + 9) | 0x200000;
    }
    if (*(char *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x47) != '\0') {
      *(uint *)(param_2 + 9) = *(uint *)(param_2 + 9) | 0x800000;
    }
    if (*(char *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x48) != '\0') {
      *(uint *)(param_2 + 9) = *(uint *)(param_2 + 9) | 0x1000000;
    }
    if (*(char *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x49) == '\0') {
      *(uint *)(param_2 + 9) = *(uint *)(param_2 + 9) | 0x2000000;
    }
    if (*(char *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x52) == '\0') {
      *(uint *)(param_2 + 9) = *(uint *)(param_2 + 9) | 0x80000000;
    }
    *(undefined4 *)(param_2 + 0xd) =
         *(undefined4 *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x24);
    cVar2 = *(char *)(*(longlong *)(param_1 + 0x5064) + 0x2d);
    if (cVar2 == '\x02') {
      param_2[0x11] = 0;
    }
    else if (cVar2 == '\x03') {
      param_2[0x11] = 1;
    }
    else {
      param_2[0x11] = 0;
    }
    *(undefined4 *)(param_2 + 0x12) =
         *(undefined4 *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x4c);
    if (*(char *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x50) != '\0') {
      *(uint *)(param_2 + 9) = *(uint *)(param_2 + 9) | 0x10000000;
    }
    if (*(char *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x53) != '\0') {
      *(ushort *)(param_2 + 0x16) = *(ushort *)(param_2 + 0x16) | 1;
    }
    if (*(char *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x54) == '\0') {
      *(ushort *)(param_2 + 0x16) = *(ushort *)(param_2 + 0x16) | 4;
    }
    if (*(char *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x55) != '\0') {
      *(ushort *)(param_2 + 0x16) = *(ushort *)(param_2 + 0x16) | 8;
    }
    if (*(char *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x3e) == '\0') {
      *(ushort *)(param_2 + 0x16) = *(ushort *)(param_2 + 0x16) | 0x10;
    }
  }
  return;
}


