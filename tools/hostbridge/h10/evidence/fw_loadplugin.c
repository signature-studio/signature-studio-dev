=== decomp 86e1a0 -> FUN_0086e1a0 @0086e1a0 size=1920

void FUN_0086e1a0(longlong param_1,uint *param_2,byte param_3)

{
  bool bVar1;
  char cVar2;
  char cVar3;
  char cVar4;
  undefined4 uVar5;
  int iVar6;
  undefined8 uVar7;
  undefined8 uVar8;
  longlong *plVar9;
  longlong lVar10;
  uint *puVar11;
  uint *puVar12;
  undefined4 uVar13;
  undefined8 unaff_R13;
  undefined7 uVar14;
  bool bVar15;
  code *local_e8;
  longlong local_e0;
  undefined8 local_d8;
  undefined8 uStack_d0;
  undefined *local_c8;
  undefined1 local_c0;
  uint *local_b8;
  undefined1 local_b0;
  undefined8 local_a8;
  undefined8 local_a0;
  undefined8 local_98;
  undefined8 local_90;
  undefined8 local_88;
  undefined8 local_80;
  undefined8 local_78;
  undefined8 local_70 [2];
  undefined8 *local_60;
  undefined8 local_58;
  undefined8 local_50;
  undefined4 local_44;
  int local_40;
  undefined8 local_3c;
  undefined8 local_34;
  undefined4 uStack_2c;
  
  local_a8 = 0;
  local_a0 = 0;
  local_98 = 0;
  local_90 = 0;
  local_80 = 0;
  local_88 = 0;
  local_70[0] = 0;
  local_78 = 0;
  local_50 = 0;
  local_58 = 0;
  FUN_00878a60(*(undefined8 *)(param_1 + 0x5058),*(undefined4 *)(param_1 + 0x5100));
  local_60 = (undefined8 *)(param_1 + 0xf6c);
  uVar7 = *local_60;
  *local_60 = 0;
  FUN_0040ec50(uVar7);
  puVar11 = param_2;
  puVar12 = (uint *)(param_1 + 300);
  for (lVar10 = 200; lVar10 != 0; lVar10 = lVar10 + -1) {
    *(undefined8 *)puVar12 = *(undefined8 *)puVar11;
    puVar11 = puVar11 + 2;
    puVar12 = puVar12 + 2;
  }
  *puVar12 = *puVar11;
  *(byte *)(param_1 + 0x770) = param_3;
  (**(code **)**(undefined8 **)(param_1 + 0xbc))
            (*(undefined8 **)(param_1 + 0xbc),*(undefined8 *)(param_1 + 8),0x21,0,0);
  puVar11 = param_2;
  puVar12 = (uint *)(param_1 + 0x8a8);
  for (lVar10 = 200; lVar10 != 0; lVar10 = lVar10 + -1) {
    *(undefined8 *)puVar12 = *(undefined8 *)puVar11;
    puVar11 = puVar11 + 2;
    puVar12 = puVar12 + 2;
  }
  *puVar12 = *puVar11;
  *(undefined1 *)(param_1 + 0xf68) = 0;
  uVar7 = FUN_0087b090();
  FUN_00792ea0(uVar7,0);
  *(undefined1 *)(*(longlong *)(param_1 + 0x5064) + 0x14) = 0;
  bVar15 = (param_3 & 0x10) != 0;
  uVar14 = (undefined7)((ulonglong)unaff_R13 >> 8);
  cVar2 = FUN_0076f3f0(PTR_PTR_0076e6e0,param_2);
  if (!bVar15) {
    if ((cVar2 == *(char *)(*(longlong *)(param_1 + 0x5064) + 0x2d)) || (cVar2 == '\0')) {
      bVar15 = false;
      uVar14 = 0;
    }
    else {
      bVar15 = true;
    }
  }
  cVar3 = FUN_0076f320(PTR_PTR_0076e6e0,param_2);
  if ((!bVar15) && (cVar3 != '\0')) {
    if ((cVar3 == *(char *)(*(longlong *)(param_1 + 0x5064) + 0x2e)) || (cVar3 == '\x03')) {
      bVar15 = false;
      uVar14 = 0;
    }
    else {
      bVar15 = true;
    }
  }
  if ((bVar15) && (cVar3 = FUN_0076f2c0(PTR_PTR_0076e6e0,param_2), cVar3 != '\0')) {
    uVar13 = (undefined4)CONCAT71(uVar14,1);
  }
  else {
    uVar13 = 0;
  }
  bVar15 = false;
  plVar9 = *(longlong **)(param_1 + 0x86c);
  if (plVar9 != (longlong *)0x0) {
    lVar10 = (**(code **)(*plVar9 + 0x18))(plVar9);
    bVar15 = 0 < lVar10;
  }
  if (!bVar15) {
    FUN_00413930(&local_78,(longlong)param_2 + 0x20e,0x105);
    FUN_0074adf0(local_70,local_78);
    FUN_005d4a40(&local_50,local_70[0]);
    uVar5 = FUN_007735b0(0x13,*param_2,local_50,param_2 + 0x106,1);
    (**(code **)(**(longlong **)(param_1 + 0x5064) + 0x120))(*(longlong **)(param_1 + 0x5064),uVar5)
    ;
  }
  *(byte *)(param_1 + 0x868) = param_3;
  plVar9 = *(longlong **)(param_1 + 0x5050);
  if ((plVar9 == (longlong *)0x0) ||
     (cVar3 = (**(code **)(*plVar9 + 0x2a8))(plVar9,param_2), cVar3 == '\0')) {
    bVar15 = false;
  }
  else {
    bVar15 = true;
  }
  if (((param_3 & 8) == 0) && (bVar15)) {
    bVar1 = false;
  }
  else {
    bVar1 = true;
  }
  cVar3 = (char)uVar13;
  if ((bVar1) ||
     (cVar4 = FUN_0040f040(*(undefined8 *)(param_1 + 0x5050),PTR_PTR_0076e6e0), cVar3 != cVar4)) {
    bVar1 = true;
  }
  else {
    bVar1 = false;
  }
  if (bVar15) {
    if ((param_3 & 8) == 0) {
      *(byte *)(param_1 + 0x868) = *(byte *)(param_1 + 0x868) | DAT_0086e958;
    }
  }
  else {
    *(byte *)(param_1 + 0x868) = *(byte *)(param_1 + 0x868) & ~DAT_0086e958;
  }
  if (bVar1) {
    FUN_00411f10(&local_58);
    if (((cVar3 == '\0') || (cVar4 = FUN_005c0040(), cVar4 != '\0')) || (cVar2 == '\x02')) {
      uVar7 = FUN_0087b090(param_1);
      FUN_00413930(&local_90,param_1 + 0x8ac,0x105);
      FUN_00790110(uVar7,local_90,uVar13);
    }
    else {
      uVar7 = FUN_0087b090(param_1);
      FUN_00413930(&local_80,param_1 + 0x8ac,0x105);
      FUN_005e2f90(&local_88,L"Try the 32bit version of the plugin instead.");
      FUN_007924d0(uVar7,7,local_80,local_88);
    }
    uVar7 = 0;
    FUN_00870000(param_1,0,0);
  }
  else {
    uVar8 = FUN_0087b090(param_1);
    FUN_00413930(&local_98,param_1 + 0x8ac,0x105);
    uVar7 = local_98;
    FUN_00790110(uVar8,local_98,uVar13);
  }
  if ((param_2[0x10a] & 4) == 0) {
    if (*param_2 < 8) {
      bVar15 = ((byte)((int)CONCAT71((int7)((ulonglong)uVar7 >> 8),1) << ((byte)*param_2 & 0x1f)) &
               DAT_0086e9c2) != 0;
    }
    else {
      bVar15 = false;
    }
    if (bVar15) {
      FUN_00413930(&local_a0,(longlong)param_2 + 0x20e,0x105);
      iVar6 = FUN_007966d0(*(undefined8 *)(*(longlong *)PTR_DAT_008f67d8 + 0x148),local_a0);
      if (-1 < iVar6) {
        uVar7 = FUN_00796690(*(undefined8 *)(*(longlong *)PTR_DAT_008f67d8 + 0x148),iVar6);
        *(undefined8 *)(param_2 + 0x10b) = uVar7;
        param_2[0x10a] = param_2[0x10a] | 4;
      }
    }
  }
  if (*(char *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x3f) == '\0') {
    param_2[0x10a] = param_2[0x10a] & 0xfffffff7;
  }
  else {
    param_2[0x10a] = param_2[0x10a] | 8;
  }
  FUN_006f84b0();
  local_44 = *(undefined4 *)(*(longlong *)(param_1 + 0xcc) + 8);
  local_40 = *(int *)(param_1 + 0x7cc);
  if (local_40 == 0) {
    local_40 = *(int *)(param_1 + 0x7c8);
  }
  local_3c = *(undefined8 *)(param_1 + 0x7d4);
  local_34 = *(undefined8 *)(param_1 + 0x7dc);
  uStack_2c = *(undefined4 *)(param_1 + 0x7e4);
  FUN_005bf650();
  FUN_005bf680();
  if (bVar1) {
    if (cVar3 == '\0') {
      plVar9 = (longlong *)FUN_0076c8e0(*(undefined8 *)PTR_DAT_008f7800,*param_2);
      if (plVar9 != (longlong *)0x0) {
        uVar7 = (**(code **)(*plVar9 + 0x40))
                          (plVar9,*(undefined8 *)(param_1 + 0x5058),param_2,&local_44);
        *(undefined8 *)(param_1 + 0x85c) = uVar7;
      }
    }
    else {
      local_c8 = (&PTR_u_generator_008f4f10)[*(char *)(param_1 + 0x4fae)];
      local_c0 = 0x11;
      local_b8 = param_2 + 1;
      local_b0 = 10;
      FUN_0043ad90(&local_a8,L"Bridged %s: %s",&local_c8,1);
      FUN_00873db0(param_1,local_a8,0,0,1);
      local_d8 = 0;
      uStack_d0 = 0;
      local_e8 = FUN_00871f80;
      local_e0 = param_1;
      uVar7 = FUN_0076f550(PTR_PTR_0076e6e0,1,*(undefined8 *)(param_1 + 0x5058),param_2,&local_44,
                           &local_d8,&local_e8,0);
      *(undefined8 *)(param_1 + 0x85c) = uVar7;
    }
  }
  else {
    *(undefined8 *)(param_1 + 0x85c) = *(undefined8 *)(param_1 + 0x5050);
  }
  FUN_005bf650();
  FUN_005bf680();
  lVar10 = *(longlong *)(param_1 + 0x85c);
  bVar15 = lVar10 == 0;
  if (lVar10 != 0) {
    bVar15 = *(char *)(lVar10 + 0x94) == '\0';
  }
  if (bVar15) {
    FUN_0086e9f0(param_1);
  }
  FUN_006f8550();
  FUN_00411ff0(&local_a8,8);
  FUN_00411ff0(&local_58,2);
  return;
}


=== decomp 86e9f0 -> FUN_0086e9f0 @0086e9f0 size=5058

void FUN_0086e9f0(longlong param_1)

{
  longlong *plVar1;
  char cVar2;
  longlong lVar3;
  undefined8 uVar4;
  HWND hWnd;
  int iVar5;
  undefined4 uVar6;
  undefined1 auStack_168 [32];
  ulonglong local_148;
  code *local_130;
  longlong local_128;
  undefined8 local_120;
  undefined8 local_118;
  undefined8 local_110;
  undefined8 local_108;
  undefined8 local_100;
  undefined8 local_f8;
  undefined8 local_f0;
  undefined8 local_e8;
  undefined8 local_e0;
  wchar_t *local_d8;
  undefined1 local_d0;
  undefined8 local_c8;
  undefined1 local_c0;
  undefined8 local_b8;
  undefined1 *local_b0;
  longlong local_a0;
  longlong local_98;
  longlong local_90;
  undefined8 local_88;
  undefined8 *local_80;
  undefined8 local_78;
  undefined8 *local_70;
  undefined8 local_68;
  undefined8 *local_60;
  undefined8 local_58;
  char local_4b;
  char local_4a;
  undefined1 local_49;
  int local_48;
  int local_44;
  undefined8 local_40;
  undefined8 local_38;
  wchar_t *local_30;
  undefined8 local_28 [2];
  
  local_b0 = auStack_168;
  local_120 = 0;
  local_110 = 0;
  local_118 = 0;
  local_100 = 0;
  local_108 = 0;
  local_f0 = 0;
  local_f8 = 0;
  local_e8 = 0;
  local_b8 = 0;
  local_e0 = 0;
  local_28[0] = 0;
  local_30 = (wchar_t *)0x0;
  local_38 = 0;
  local_49 = *(undefined1 *)(param_1 + 0x898);
  local_4b = '\0';
  local_148 = local_148 & 0xffffffffffffff00;
  FUN_00873db0(param_1,L"LoadPlugin_Finish",1);
  lVar3 = *(longlong *)(param_1 + 0x85c);
  if (lVar3 == 0) {
    FUN_008772c0(param_1,0,1);
    local_d8 = (wchar_t *)(param_1 + 0x8ac);
    local_d0 = 10;
    FUN_00438ce0(&local_118,*(undefined4 *)(param_1 + 0x8a8));
    local_c8 = local_118;
    local_c0 = 0x11;
    FUN_0043ad90(&local_110,L"%s|%s",&local_d8,1);
    FUN_0041b300(local_28,local_110);
    FUN_00413080(local_28[0]);
    local_148 = 0;
    (**(code **)**(undefined8 **)(param_1 + 0xbc))
              (*(undefined8 **)(param_1 + 0xbc),*(undefined8 *)(param_1 + 8),0x4a);
  }
  else {
    local_4b = FUN_0040f040(lVar3,PTR_PTR_0076e6e0);
    if (*(char *)(lVar3 + 0x91) == '\0') {
      local_148 = local_148 & 0xffffffffffffff00;
      FUN_00873db0(param_1,L"not valid - destroy loading plugin",1);
      local_60 = (undefined8 *)(param_1 + 0x85c);
      local_68 = *local_60;
      *local_60 = 0;
      FUN_0040ec50(local_68);
      FUN_008772c0(param_1,0,(*(byte *)(param_1 + 0x868) & 4) != 0);
      if ((*(byte *)(param_1 + 0x868) & 1) == 0) {
        local_d8 = (wchar_t *)(param_1 + 0x8ac);
        local_d0 = 10;
        FUN_00438ce0(&local_e0,*(undefined4 *)(param_1 + 0x8a8));
        local_c8 = local_e0;
        local_c0 = 0x11;
        FUN_0043ad90(&local_b8,L"%s|%s",&local_d8,1);
        FUN_0041b300(local_28,local_b8);
        FUN_00413080(local_28[0]);
        local_148 = 0;
        (**(code **)**(undefined8 **)(param_1 + 0xbc))
                  (*(undefined8 **)(param_1 + 0xbc),*(undefined8 *)(param_1 + 8),0x4a);
      }
    }
    else {
      lVar3 = *(longlong *)(param_1 + 0x85c);
      if ((*(char *)(lVar3 + 0x757) == '\0') && (*(char *)(param_1 + 0x4fad) != '\0')) {
        FUN_00413930(&local_30,lVar3 + 0x9c,0x105);
        FUN_00438ce0(&local_38,*(undefined4 *)(lVar3 + 0x98));
        local_70 = (undefined8 *)(param_1 + 0x85c);
        local_78 = *local_70;
        *local_70 = 0;
        FUN_0040ec50(local_78);
        FUN_008772c0(param_1,0,(*(byte *)(param_1 + 0x868) & 4) != 0);
        local_d8 = local_30;
        local_d0 = 0x11;
        local_c8 = local_38;
        local_c0 = 0x11;
        FUN_0043ad90(&local_e8,L"%s|%s",&local_d8,1);
        FUN_0041b300(local_28,local_e8);
        FUN_00413080(local_28[0]);
        local_148 = 1;
        (**(code **)**(undefined8 **)(param_1 + 0xbc))
                  (*(undefined8 **)(param_1 + 0xbc),*(undefined8 *)(param_1 + 8),0x4a);
      }
      else {
        if (*(char *)(lVar3 + 0x754) == '\0') {
          FUN_0086b990(param_1,lVar3);
        }
        FUN_00877550(param_1);
        *(undefined8 *)(param_1 + 0x5050) = *(undefined8 *)(param_1 + 0x85c);
        *(undefined8 *)(*(longlong *)(param_1 + 0x838) + 0x10) = *(undefined8 *)(param_1 + 0x85c);
        *(undefined8 *)(param_1 + 0x85c) = 0;
        FUN_00870810(param_1);
        cVar2 = (**(code **)(**(longlong **)(param_1 + 0x5050) + 0xb8))
                          (*(longlong **)(param_1 + 0x5050));
        if (cVar2 == '\0') {
          local_80 = (undefined8 *)(param_1 + 0x5050);
          local_88 = *local_80;
          *local_80 = 0;
          FUN_0040ec50(local_88);
          local_d8 = (wchar_t *)(*(longlong *)(param_1 + 0x5050) + 0x9c);
          local_d0 = 10;
          FUN_00438ce0(&local_f8,*(undefined4 *)(*(longlong *)(param_1 + 0x5050) + 0x98));
          local_c8 = local_f8;
          local_c0 = 0x11;
          FUN_0043ad90(&local_f0,L"%s|%s",&local_d8,1);
          FUN_0041b300(local_28,local_f0);
          FUN_00413080(local_28[0]);
          local_148 = 2;
          (**(code **)**(undefined8 **)(param_1 + 0xbc))
                    (*(undefined8 **)(param_1 + 0xbc),*(undefined8 *)(param_1 + 8),0x4a);
        }
        FUN_00877580(param_1);
        if (*(longlong *)(param_1 + 0x5050) != 0) {
          local_148 = (ulonglong)*(int *)(*(longlong *)(param_1 + 0x5050) + 0x780);
          (**(code **)**(undefined8 **)(param_1 + 0xbc))
                    (*(undefined8 **)(param_1 + 0xbc),*(undefined8 *)(param_1 + 8),9,0);
          FUN_008772c0(param_1,*(undefined8 *)(*(longlong *)(param_1 + 0x5050) + 0x80),
                       (*(byte *)(param_1 + 0x868) & 4) != 0);
          local_d8 = L"Fruity Wrapper";
          local_d0 = 0x11;
          local_c8 = *(undefined8 *)(*(longlong *)(param_1 + 0x5050) + 0x80);
          local_c0 = 0x11;
          FUN_0043ad90(&local_108,L"%s - %s",&local_d8,1);
          FUN_006f7be0(&local_100,local_108);
          FUN_0041b300(local_28,local_100);
          local_148 = FUN_00413080(local_28[0]);
          (**(code **)**(undefined8 **)(param_1 + 0xbc))
                    (*(undefined8 **)(param_1 + 0xbc),*(undefined8 *)(param_1 + 8),0x23,0);
          (**(code **)(**(longlong **)(param_1 + 0x5050) + 0x150))
                    (*(longlong **)(param_1 + 0x5050),*(undefined1 *)(param_1 + 0x7e9));
          (**(code **)(**(longlong **)(param_1 + 0x5050) + 0x158))
                    (*(longlong **)(param_1 + 0x5050),*(undefined4 *)(param_1 + 0x7ec),0);
          (**(code **)(**(longlong **)(param_1 + 0x5050) + 0x168))
                    (*(longlong **)(param_1 + 0x5050),*(undefined4 *)(param_1 + 0x808));
          (**(code **)(**(longlong **)(param_1 + 0x5050) + 0x140))
                    (*(longlong **)(param_1 + 0x5050),*(undefined8 *)(param_1 + 0x7d4));
          (**(code **)(**(longlong **)(param_1 + 0x5064) + 0x118))(*(longlong **)(param_1 + 0x5064))
          ;
          (**(code **)(**(longlong **)(param_1 + 0x5050) + 0x170))
                    (*(longlong **)(param_1 + 0x5050),*(undefined4 *)(param_1 + 0x82c),
                     *(undefined4 *)(param_1 + 0x830));
        }
      }
    }
    plVar1 = *(longlong **)(param_1 + 0x5064);
    *(undefined4 *)(*(longlong *)((longlong)plVar1 + 0xc) + 0x40) = 0;
    (**(code **)(*plVar1 + 0x28))(plVar1);
    if ((*(byte *)(param_1 + 0x868) & 0x20) != 0) {
      plVar1 = *(longlong **)(param_1 + 0x86c);
      if ((((plVar1 != (longlong *)0x0) && (*(longlong *)(param_1 + 0x5050) != 0)) &&
          (lVar3 = (**(code **)(*plVar1 + 0x18))(plVar1), 0 < lVar3)) &&
         (FUN_00501370(*(undefined8 *)(param_1 + 0x86c),0), *(longlong *)(param_1 + 0x5050) != 0)) {
        local_4a = '\0';
        if ((*(byte *)(param_1 + 0x868) & 0x80) != 0) {
          local_4a = (**(code **)(**(longlong **)(param_1 + 0x5050) + 0x1b0))
                               (*(longlong **)(param_1 + 0x5050),*(undefined8 *)(param_1 + 0x86c),
                                *(undefined4 *)(param_1 + 0x89c));
        }
        if (local_4a == '\0') {
          local_148 = local_148 & 0xffffffffffffff00;
          (**(code **)(**(longlong **)(param_1 + 0x5050) + 0x1a8))
                    (*(longlong **)(param_1 + 0x5050),*(undefined8 *)(param_1 + 0x86c),0);
        }
      }
      if (*(char *)(*(longlong *)(param_1 + 0x874) + 0x18) == '\0') {
        if ((*(char *)(param_1 + 0x8a4) != '\0') && (*(int *)(param_1 + 0x864) < 0xc)) {
          *(undefined1 *)(*(longlong *)(param_1 + 0x874) + 0x19) = 1;
        }
        (**(code **)(**(longlong **)(param_1 + 0x874) + 0x10))
                  (*(longlong **)(param_1 + 0x874),*(undefined8 *)(param_1 + 0x5064),
                   *(undefined4 *)(param_1 + 0x864));
      }
      if (*(longlong *)(param_1 + 0x5050) != 0) {
        local_48 = FUN_0079e420(*(undefined4 *)(*(longlong *)(param_1 + 0x5050) + 0x714),
                                *(undefined4 *)(param_1 + 0x87c));
        local_44 = 0;
        iVar5 = local_48;
        if (-1 < local_48 + -1) {
          do {
            lVar3 = (longlong)local_44;
            *(undefined4 *)(*(longlong *)(*(longlong *)(param_1 + 0x5050) + 0x72c) + lVar3 * 8) =
                 *(undefined4 *)(*(longlong *)(param_1 + 0x880) + lVar3 * 0xc);
            if (5 < *(int *)(param_1 + 0x864)) {
              *(bool *)(*(longlong *)(*(longlong *)(param_1 + 0x5050) + 0x72c) + 4 + lVar3 * 8) =
                   (*(byte *)(*(longlong *)(param_1 + 0x880) + 4 + lVar3 * 0xc) & 1) == 1;
            }
            local_44 = local_44 + 1;
            iVar5 = iVar5 + -1;
          } while (iVar5 != 0);
        }
        local_48 = FUN_0079e420(*(undefined4 *)(*(longlong *)(param_1 + 0x5050) + 0x718),
                                *(undefined4 *)(param_1 + 0x888));
        local_44 = 0;
        iVar5 = local_48;
        if (-1 < local_48 + -1) {
          do {
            lVar3 = (longlong)local_44;
            *(undefined4 *)(*(longlong *)(*(longlong *)(param_1 + 0x5050) + 0x734) + lVar3 * 8) =
                 *(undefined4 *)(*(longlong *)(param_1 + 0x88c) + lVar3 * 0xc);
            if (5 < *(int *)(param_1 + 0x864)) {
              *(bool *)(*(longlong *)(*(longlong *)(param_1 + 0x5050) + 0x734) + 4 + lVar3 * 8) =
                   (*(byte *)(*(longlong *)(param_1 + 0x88c) + 4 + lVar3 * 0xc) & 1) == 1;
            }
            local_44 = local_44 + 1;
            iVar5 = iVar5 + -1;
          } while (iVar5 != 0);
        }
        iVar5 = *(int *)(*(longlong *)(param_1 + 0x5050) + 0x714);
        local_44 = 0;
        if (-1 < iVar5 + -1) {
          do {
            local_148 = CONCAT71(local_148._1_7_,1);
            (**(code **)(**(longlong **)(param_1 + 0x5050) + 0x360))
                      (*(longlong **)(param_1 + 0x5050),1,local_44);
            local_44 = local_44 + 1;
            iVar5 = iVar5 + -1;
          } while (iVar5 != 0);
        }
        iVar5 = *(int *)(*(longlong *)(param_1 + 0x5050) + 0x718);
        local_44 = 0;
        if (-1 < iVar5 + -1) {
          do {
            local_148 = CONCAT71(local_148._1_7_,1);
            (**(code **)(**(longlong **)(param_1 + 0x5050) + 0x360))
                      (*(longlong **)(param_1 + 0x5050),0,local_44);
            local_44 = local_44 + 1;
            iVar5 = iVar5 + -1;
          } while (iVar5 != 0);
        }
      }
      if (*(longlong *)(param_1 + 0x5050) == 0) {
        local_49 = 3;
      }
    }
  }
  if (*(longlong *)(param_1 + 0x5050) == 0) {
    FUN_00417080(param_1 + 0x84c,PTR_DAT_00868668);
  }
  else {
    FUN_00877550(param_1);
    FUN_0079e420(*(undefined4 *)(*(longlong *)(param_1 + 0x5050) + 0x70c),0x1000);
    FUN_00416eb0(param_1 + 0x84c,PTR_DAT_00868668,1);
    local_90 = *(longlong *)(param_1 + 0x84c);
    local_98 = local_90;
    if (local_90 != 0) {
      local_98 = *(longlong *)(local_90 + -8);
    }
    iVar5 = (int)local_98;
    local_44 = 0;
    if (-1 < iVar5 + -1) {
      do {
        uVar6 = (**(code **)(**(longlong **)(param_1 + 0x5050) + 0x1e8))
                          (*(longlong **)(param_1 + 0x5050),local_44,0);
        *(undefined4 *)(*(longlong *)(param_1 + 0x84c) + (longlong)local_44 * 4) = uVar6;
        local_44 = local_44 + 1;
        iVar5 = iVar5 + -1;
      } while (iVar5 != 0);
    }
    FUN_00877580(param_1);
  }
  plVar1 = *(longlong **)(param_1 + 0x5050);
  if (plVar1 != (longlong *)0x0) {
    (**(code **)(*plVar1 + 0x298))(plVar1,1);
  }
  *(longlong *)(*(longlong *)(param_1 + 0x5064) + 0x38) = param_1;
  if (*(longlong *)(param_1 + 0x5050) == 0) {
    uVar4 = FUN_0087b090(param_1);
    FUN_00790010(uVar4,param_1 + 0x8a8);
  }
  if ((*(byte *)(param_1 + 0x868) & 2) != 0) {
    uVar4 = FUN_0087b090(param_1);
    FUN_0078f910(uVar4);
  }
  if (((*(char *)(param_1 + 0x4fad) != '\0') && (*(char *)(param_1 + 0x506c) == '\0')) &&
     (*(longlong *)(param_1 + 0x5050) != 0)) {
    FUN_00878d40(param_1,0);
    FUN_00878e60(param_1);
  }
  FUN_00877550(param_1);
  *(bool *)(param_1 + 0x50f4) = *(longlong *)(param_1 + 0x5050) != 0;
  *(bool *)(param_1 + 0x50f5) = *(longlong *)(param_1 + 0x5050) == 0;
  FUN_00877580(param_1);
  FUN_005bf650();
  FUN_005bf680();
  local_148 = 2;
  (**(code **)**(undefined8 **)(param_1 + 0xbc))
            (*(undefined8 **)(param_1 + 0xbc),*(undefined8 *)(param_1 + 8),3);
  local_148 = 0;
  (**(code **)**(undefined8 **)(param_1 + 0xbc))
            (*(undefined8 **)(param_1 + 0xbc),*(undefined8 *)(param_1 + 8),3);
  if (*(longlong *)(param_1 + 0x5050) == 0) {
    local_148 = 0;
    (**(code **)**(undefined8 **)(param_1 + 0xbc))
              (*(undefined8 **)(param_1 + 0xbc),*(undefined8 *)(param_1 + 8));
  }
  else {
    local_148 = 0x1090;
    (**(code **)**(undefined8 **)(param_1 + 0xbc))
              (*(undefined8 **)(param_1 + 0xbc),*(undefined8 *)(param_1 + 8));
  }
  local_a0 = param_1 + 0x506d;
  (**(code **)PTR_DAT_008f6868)(local_a0,0x80);
  *(undefined1 *)(param_1 + 0x50ed) = 0x7f;
  plVar1 = *(longlong **)(param_1 + 0x5050);
  if ((plVar1 != (longlong *)0x0) && (*(char *)(param_1 + 0x7e8) != '\0')) {
    (**(code **)(*plVar1 + 0x2a0))(plVar1,*(undefined1 *)(param_1 + 0x7e8));
  }
  FUN_008771a0(param_1,DAT_0086ff8e);
  uVar4 = FUN_0087b090(param_1);
  FUN_0078ebb0(uVar4);
  local_58 = FUN_0087b090(param_1);
  if (*(longlong *)(param_1 + 0x5050) != 0) {
    local_40 = *(undefined8 *)(*(longlong *)(param_1 + 0x5050) + 0x10);
    if ((*(char *)(*(longlong *)(param_1 + 0x5050) + 0x760) == '\0') ||
       (iVar5 = FUN_00746780(local_40), iVar5 < 1)) {
      FUN_00792ea0(local_58,0);
    }
    else {
      uVar4 = FUN_0087b090(param_1);
      hWnd = (HWND)FUN_0059efe0(uVar4);
      PostMessageW(hWnd,0x40f,0,0);
    }
  }
  local_148 = (ulonglong)
              (*(char *)(*(longlong *)(*(longlong *)(param_1 + 0x5064) + 0xc) + 0x48) == '\0');
  (**(code **)**(undefined8 **)(param_1 + 0xbc))
            (*(undefined8 **)(param_1 + 0xbc),*(undefined8 *)(param_1 + 8),0x43,0);
  if (local_4b != '\0') {
    FUN_00765f70(*(undefined8 *)PTR_DAT_008f6a00);
  }
  if (*(longlong *)(param_1 + 0x5050) != 0) {
    FUN_004f9f80(*(undefined8 *)(*(longlong *)PTR_DAT_008f67d8 + 0x158),param_1);
  }
  plVar1 = *(longlong **)(param_1 + 0x5064);
  (**(code **)(*plVar1 + 0xf8))
            (plVar1,*(undefined1 *)(*(longlong *)((longlong)plVar1 + 0xc) + 0x2a),1);
  plVar1 = *(longlong **)(param_1 + 0x5064);
  (**(code **)(*plVar1 + 0x100))
            (plVar1,*(undefined1 *)(*(longlong *)((longlong)plVar1 + 0xc) + 0x2b),1);
  if (*(longlong *)(param_1 + 0x5050) != 0) {
    if (*(longlong *)(param_1 + 0xf8c) == 0) {
      uVar4 = FUN_0087b090(param_1);
      FUN_007918d0(uVar4,local_49,DAT_0086ffb4);
    }
    else {
      FUN_0086c150(param_1);
    }
  }
  if (*(longlong *)(param_1 + 0x5050) != 0) {
    local_130 = FUN_00871f00;
    local_128 = param_1;
    FUN_0068a5f0(&local_130,0);
  }
  if ((*(longlong *)(param_1 + 0x5050) != 0) &&
     ((*(uint *)(*(longlong *)(param_1 + 0x5050) + 0x758) & 0x800000) != 0)) {
    (**(code **)(**(longlong **)(param_1 + 0x5064) + 0x128))(*(longlong **)(param_1 + 0x5064),1);
  }
  FUN_008736f0(param_1);
  local_148 = local_148 & 0xffffffffffffff00;
  FUN_00873db0(param_1,L"Finished (LoadPlugin_Finish)",1,0xffffffff);
  FUN_00411ff0(&local_120,9);
  FUN_00411f10(&local_b8);
  FUN_00411ff0(&local_38,2);
  FUN_00411f60(local_28);
  return;
}


=== decomp 87c980 -> FUN_0087c980 @0087c980 size=55

void FUN_0087c980(undefined8 param_1,undefined8 param_2,undefined8 param_3,undefined8 param_4)

{
  FUN_007a9db0(PTR_PTR_007a78a0,1,param_2,param_3,param_4,0);
  return;
}


