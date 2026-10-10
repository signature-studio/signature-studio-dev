=== decomp 7a9db0 -> FUN_007a9db0 @007a9db0 size=4815

longlong *
FUN_007a9db0(longlong *param_1,char param_2,undefined8 param_3,longlong param_4,undefined4 *param_5,
            undefined8 param_6)

{
  undefined1 *puVar1;
  undefined1 uVar2;
  char cVar3;
  DWORD DVar4;
  int iVar5;
  undefined4 uVar6;
  undefined8 uVar7;
  longlong lVar8;
  longlong *local_res8;
  undefined1 auStack_368 [32];
  undefined4 *local_348;
  undefined4 local_340;
  undefined8 local_338;
  undefined8 local_330;
  undefined8 local_328;
  undefined8 local_320;
  undefined8 local_318;
  undefined8 local_310;
  undefined8 local_308;
  undefined8 local_300;
  undefined8 local_2f8;
  undefined8 local_2f0;
  undefined8 local_2e8;
  undefined8 local_2e0;
  undefined8 local_2d8;
  longlong local_2d0;
  undefined1 local_2c8;
  undefined8 local_2c0;
  undefined8 local_2b8;
  undefined8 local_2b0;
  longlong local_2a8;
  undefined1 local_2a0;
  undefined8 local_298;
  undefined1 local_290;
  undefined8 local_288;
  undefined1 *local_280;
  longlong *local_278;
  longlong local_270;
  longlong local_260;
  undefined1 local_251 [16];
  undefined1 local_241 [513];
  undefined8 local_40;
  int local_34;
  code *local_30;
  longlong local_28 [3];
  
  local_280 = auStack_368;
  local_338 = 0;
  local_330 = 0;
  local_328 = 0;
  local_310 = 0;
  local_318 = 0;
  local_320 = 0;
  local_308 = 0;
  local_2f8 = 0;
  local_300 = 0;
  local_2e0 = 0;
  local_2e8 = 0;
  local_2f0 = 0;
  local_2d8 = 0;
  local_2c0 = 0;
  local_2b8 = 0;
  local_288 = 0;
  local_2b0 = 0;
  local_28[0] = 0;
  local_res8 = param_1;
  puVar1 = auStack_368;
  if (param_2 != '\0') {
    local_res8 = (longlong *)FUN_0040f4d0(param_1,param_2);
    puVar1 = local_280;
  }
  local_280 = puVar1;
  local_348 = param_5;
  FUN_007445f0(local_res8,0,param_3,param_4);
  *(undefined1 *)(local_res8 + 0xf4) = 1;
  *(undefined1 *)((longlong)local_res8 + 0x7a1) = 0;
  *(undefined1 *)((longlong)local_res8 + 0x7a2) = 0;
  local_2a8 = param_4 + 0x20e;
  local_2a0 = 10;
  FUN_00784e10(&local_2b0,*(undefined4 *)(param_4 + 0x434));
  local_298 = local_2b0;
  local_290 = 0x11;
  FUN_0043ad90(&local_288,L"Create VST plugin: file=\"%s\" id=%s",&local_2a8,1);
  local_348 = (undefined4 *)CONCAT71(local_348._1_7_,1);
  (**(code **)(*local_res8 + 0x378))(local_res8,local_288,1,1);
  *(undefined1 *)((longlong)local_res8 + 0x2e) = 1;
  *(undefined1 *)((longlong)local_res8 + 0x8d5) = 0;
  *(undefined1 *)((longlong)local_res8 + 0x8d6) = 0;
  *(undefined1 *)((longlong)local_res8 + 0x8b4) = 1;
  *(undefined1 *)((longlong)local_res8 + 0x8d4) = 0;
  *(undefined1 *)((longlong)local_res8 + 0x7a3) = 0;
  DVar4 = timeGetTime();
  *(DWORD *)(local_res8 + 0x11b) = DVar4;
  *(undefined4 *)((longlong)local_res8 + 0x9a4) = 0;
  *(undefined1 *)(local_res8 + 0x138) = 0;
  *(undefined1 *)((longlong)local_res8 + 0x7a4) = 0;
  *(undefined8 *)((longlong)local_res8 + 0x8dc) = 0;
  *(undefined8 *)((longlong)local_res8 + 0x8e4) = 0;
  *(undefined1 *)(local_res8 + 0xec) = 0;
  *(undefined1 *)(local_res8 + 0x135) = 0;
  *(undefined1 *)((longlong)local_res8 + 0x9a9) = 0;
  *(undefined8 *)((longlong)local_res8 + 0x8ec) = 0;
  local_res8[0x139] = 0;
  local_res8[0x13a] = 0;
  uVar7 = FUN_00474360(PTR_PTR_00473178,1);
  *(undefined8 *)((longlong)local_res8 + 0x9ac) = uVar7;
  local_res8[0x118] = 0;
  *(undefined4 *)(local_res8 + 0x119) = 0;
  uVar7 = FUN_00612b70(PTR_PTR_006126b0,1,0x38,1);
  *(undefined8 *)((longlong)local_res8 + 0x8cc) = uVar7;
  *(undefined1 *)(local_res8 + 0x12a) = 0;
  FUN_00411f10(local_res8 + 299);
  FUN_00411f10(local_res8 + 300);
  local_res8[0x12d] = 0;
  *(undefined4 *)(local_res8 + 0x12e) = 0;
  local_res8[0x12d] = 0;
  *(undefined1 *)((longlong)local_res8 + 0x974) = 0;
  FUN_00411f10((longlong)local_res8 + 0x97c);
  FUN_00411f10((longlong)local_res8 + 0x984);
  *(undefined8 *)((longlong)local_res8 + 0x98c) = 0;
  *(undefined4 *)((longlong)local_res8 + 0x994) = 0;
  *(undefined8 *)((longlong)local_res8 + 0x98c) = 0;
  local_res8[0x133] = 0;
  *(undefined4 *)(local_res8 + 0x134) = 0;
  *(undefined1 *)((longlong)local_res8 + 0x94c) = 0;
  FUN_00413930(&local_2b8,(longlong)local_res8 + 0x2a6,0x105);
  uVar2 = FUN_007a9030(local_2b8,param_6);
  *(undefined1 *)(local_res8 + 0x12) = uVar2;
  DAT_008e5d00 = local_res8;
  *(undefined1 *)((longlong)local_res8 + 0x94) = 1;
  if ((char)local_res8[0x12] != '\0') {
    local_348 = (undefined4 *)((ulonglong)local_348 & 0xffffffffffffff00);
    (**(code **)(*local_res8 + 0x378))(local_res8,L"loading dll",1,0);
    local_2d0 = (longlong)local_res8 + 0x2a6;
    local_2c8 = 10;
    FUN_0043ad90(&local_2c0,L"  filename=%s",&local_2d0,0);
    local_348 = (undefined4 *)((ulonglong)local_348 & 0xffffffffffffff00);
    (**(code **)(*local_res8 + 0x378))(local_res8,local_2c0,1,0);
    FUN_00413930(&local_2d8,(longlong)local_res8 + 0x2a6,0x105);
    uVar7 = FUN_00449770(local_2d8,0x8000);
    *(undefined8 *)((longlong)local_res8 + 0x8ac) = uVar7;
    if (*(longlong *)((longlong)local_res8 + 0x8ac) != 0) {
      local_348 = (undefined4 *)((ulonglong)local_348._1_7_ << 8);
      (**(code **)(*local_res8 + 0x378))(local_res8,L"dll loaded",1,0);
      (**(code **)(*local_res8 + 0xa0))(local_res8,*(undefined8 *)((longlong)local_res8 + 0x8ac));
      local_30 = (code *)(**(code **)(*local_res8 + 0x3b8))
                                   (local_res8,*(undefined8 *)((longlong)local_res8 + 0x8ac),param_6
                                   );
      *(bool *)(local_res8 + 0x12) = local_30 != (code *)0x0;
      if (local_30 != (code *)0x0) {
        local_348 = (undefined4 *)((ulonglong)local_348._1_7_ << 8);
        (**(code **)(*local_res8 + 0x378))(local_res8,L"found main function",1,0);
        FUN_00413930(&local_2f0,(longlong)local_res8 + 0x2a6,0x105);
        FUN_0043a1f0(&local_2e8,local_2f0);
        FUN_0041b300(&local_2e0,local_2e8);
        FUN_0056c080((longlong)local_res8 + 0x7a5,local_2e0);
        FUN_00413900(&local_300,(longlong)local_res8 + 0x7a5,0x105);
        FUN_00413c60(&local_2f8,L"dll path: ",local_300);
        local_348 = (undefined4 *)((ulonglong)local_348 & 0xffffffffffffff00);
        (**(code **)(*local_res8 + 0x378))(local_res8,local_2f8,1,0);
        *(undefined4 *)((longlong)local_res8 + 0x9bc) = 0;
        if ((*(uint *)(local_res8 + 0x98) & 2) != 0) {
          *(undefined4 *)((longlong)local_res8 + 0x9bc) =
               *(undefined4 *)((longlong)local_res8 + 0x4cc);
        }
        local_348 = (undefined4 *)((ulonglong)local_348 & 0xffffffffffffff00);
        (**(code **)(*local_res8 + 0x378))(local_res8,L"Call main",1,1);
        FUN_005bf650();
        FUN_005bf680();
        local_348 = (undefined4 *)((ulonglong)local_348 & 0xffffffffffffff00);
        (**(code **)(*local_res8 + 0x378))(local_res8,&DAT_007ab3f8,1,0);
        FUN_00745570(local_res8);
        uVar7 = (*local_30)(FUN_007a87c0);
        *(undefined8 *)((longlong)local_res8 + 0x9b4) = uVar7;
        FUN_007455c0(local_res8);
        local_348 = (undefined4 *)((ulonglong)local_348 & 0xffffffffffffff00);
        (**(code **)(*local_res8 + 0x378))(local_res8,&DAT_007ab408,1,0);
        local_348 = (undefined4 *)((ulonglong)local_348 & 0xffffffffffffff00);
        (**(code **)(*local_res8 + 0x378))(local_res8,&DAT_007ab460,1,0);
        FUN_005bf650();
        FUN_005bf680();
        local_348 = (undefined4 *)((ulonglong)local_348 & 0xffffffffffffff00);
        (**(code **)(*local_res8 + 0x378))(local_res8,L"Finished (call main)",1,0xffffffff);
        local_34 = FUN_00784de0(**(undefined1 **)PTR_PTR_008f7a60,
                                *(undefined1 *)(*(longlong *)PTR_PTR_008f7a60 + 1),
                                *(undefined1 *)(*(longlong *)PTR_PTR_008f7a60 + 2),
                                *(undefined1 *)(*(longlong *)PTR_PTR_008f7a60 + 3));
        if ((*(int **)((longlong)local_res8 + 0x9b4) != (int *)0x0) &&
           (local_34 != **(int **)((longlong)local_res8 + 0x9b4))) {
          *(undefined8 *)((longlong)local_res8 + 0x9b4) = 0;
        }
        if (*(longlong *)((longlong)local_res8 + 0x9b4) != 0) {
          *(longlong **)(*(longlong *)((longlong)local_res8 + 0x9b4) + 0x40) = local_res8;
          if (((*(uint *)(local_res8 + 0x98) & 2) != 0) &&
             (*(int *)((longlong)local_res8 + 0x9bc) != 0)) {
            *(undefined4 *)(*(longlong *)((longlong)local_res8 + 0x9b4) + 0x70) =
                 *(undefined4 *)((longlong)local_res8 + 0x9bc);
          }
          *(undefined4 *)((longlong)local_res8 + 0x9bc) =
               *(undefined4 *)(*(longlong *)((longlong)local_res8 + 0x9b4) + 0x70);
          local_260 = *(longlong *)((longlong)local_res8 + 0x9b4);
          FUN_005bf650();
          FUN_005bf680();
          (**(code **)(*local_res8 + 0x130))(local_res8,*param_5);
          (**(code **)(*local_res8 + 0x138))(local_res8,param_5[1]);
          FUN_00745570(local_res8);
          local_348 = (undefined4 *)0x0;
          local_340 = DAT_007ab120;
          (**(code **)(local_260 + 8))(*(undefined8 *)((longlong)local_res8 + 0x9b4),0,0,0);
          FUN_007455c0(local_res8);
          (**(code **)(*local_res8 + 0x130))(local_res8,*param_5);
          (**(code **)(*local_res8 + 0x138))(local_res8,param_5[1]);
          *(undefined1 *)((longlong)local_res8 + 0x91) = 1;
          (**(code **)(*local_res8 + 0x2a0))(local_res8,1);
          if ((*(uint *)(local_260 + 0x38) & 1) != 0) {
            local_40 = FUN_007b35e0(PTR_PTR_007a8158,1,local_res8);
            FUN_007451b0(local_res8,local_40);
          }
          FUN_00413930(&local_320,(longlong)local_res8 + 0x2a6,0x105);
          FUN_0043a480(&local_318,local_320);
          FUN_0043a0d0(&local_310,local_318,0);
          FUN_004125a0(local_res8 + 0x10,local_310);
          local_270 = local_res8[0x10];
          iVar5 = FUN_004140c0(L"Fruity ",local_270,1);
          if (iVar5 == 1) {
            FUN_007ac4c0(local_res8,&local_328,local_res8[0x10]);
            FUN_004125a0(local_res8 + 0x10,local_328);
          }
          local_241[0] = 0;
          local_348 = (undefined4 *)local_241;
          local_340 = DAT_007ab120;
          (**(code **)(local_260 + 8))(*(undefined8 *)((longlong)local_res8 + 0x9b4),0x2d,0,0);
          FUN_00413900(local_28,local_241,0x201);
          if (local_28[0] != 0) {
            FUN_004125a0(local_res8 + 0x10,local_28[0]);
          }
          local_348 = (undefined4 *)0x0;
          local_340 = DAT_007ab120;
          (**(code **)(local_260 + 8))(*(undefined8 *)((longlong)local_res8 + 0x9b4),0x3d,0,2);
          local_348 = (undefined4 *)0x0;
          local_340 = DAT_007ab120;
          lVar8 = (**(code **)(*(longlong *)((longlong)local_res8 + 0x9b4) + 8))
                            (*(longlong *)((longlong)local_res8 + 0x9b4),0x23,0,0);
          *(bool *)(local_res8 + 0xec) = lVar8 == 10;
          *(bool *)((longlong)local_res8 + 0x94c) =
               (*(uint *)(*(longlong *)((longlong)local_res8 + 0x9b4) + 0x38) & 0x20) == 0x20;
          FUN_007af630(local_res8);
          local_348 = (undefined4 *)0x0;
          local_340 = DAT_007ab120;
          uVar6 = (**(code **)(*(longlong *)((longlong)local_res8 + 0x9b4) + 8))
                            (*(longlong *)((longlong)local_res8 + 0x9b4),0x3a,0,0);
          *(undefined4 *)((longlong)local_res8 + 0x9c4) = uVar6;
          if ((*(int *)((longlong)local_res8 + 0x9c4) < 2) && ((char)local_res8[0xec] == '\0')) {
            cVar3 = '\x01';
          }
          else {
            cVar3 = '\0';
          }
          *(char *)(local_res8 + 0x138) = cVar3;
          if (cVar3 != '\0') {
            uVar7 = FUN_00500f90(PTR_PTR_004c1db0,1);
            *(undefined8 *)((longlong)local_res8 + 0x8dc) = uVar7;
            iVar5 = *(int *)(*(longlong *)((longlong)local_res8 + 0x9b4) + 0x28);
            local_34 = 0;
            if (-1 < iVar5 + -1) {
              do {
                local_348 = (undefined4 *)CONCAT71(local_348._1_7_,1);
                FUN_007b2880(local_res8,&local_330,local_34,0);
                (**(code **)(**(longlong **)((longlong)local_res8 + 0x8dc) + 0x78))
                          (*(longlong **)((longlong)local_res8 + 0x8dc),local_330);
                local_34 = local_34 + 1;
                iVar5 = iVar5 + -1;
              } while (iVar5 != 0);
            }
          }
          FUN_007b1d10(local_res8,0,1);
          cVar3 = (**(code **)(*local_res8 + 0x88))(local_res8,6);
          if (cVar3 == '\0') {
            FUN_007b1f00(local_res8,local_res8 + 0x12a);
          }
          local_res8[0x133] = 0;
          FUN_007ab5b0(local_res8);
          goto code_r0x007aad66;
        }
        (**(code **)(*local_res8 + 0xa8))(local_res8,*(undefined8 *)((longlong)local_res8 + 0x8ac));
        FreeLibrary(*(HMODULE *)((longlong)local_res8 + 0x8ac));
        local_348 = (undefined4 *)((ulonglong)local_348 & 0xffffffffffffff00);
        (**(code **)(*local_res8 + 0x378))(local_res8,L"Finished (no effect)",1,0xffffffff);
      }
      else {
        local_348 = (undefined4 *)((ulonglong)local_348._1_7_ << 8);
        (**(code **)(*local_res8 + 0x378))
                  (local_res8,L"Finished (failed to find import function)",1,0xffffffff);
        (**(code **)(*local_res8 + 0xa8))(local_res8,*(undefined8 *)((longlong)local_res8 + 0x8ac));
        FreeLibrary(*(HMODULE *)((longlong)local_res8 + 0x8ac));
      }
      FUN_007ab180(0,local_280);
      goto LAB_007ab065;
    }
    local_348 = (undefined4 *)CONCAT71(local_348._1_7_,1);
    (**(code **)(*local_res8 + 0x378))(local_res8,L"Failed to load plugin dll (handle=0)",1,0);
code_r0x007aad66:
    local_348 = (undefined4 *)((ulonglong)local_348 & 0xffffffffffffff00);
    (**(code **)(*local_res8 + 0x378))(local_res8,L"reached finally",0,0);
    DAT_008e5d00 = (longlong *)0x0;
  }
  *(undefined1 *)((longlong)local_res8 + 0x94) = 0;
  *(undefined1 *)(local_res8 + 0xf4) = 0;
  (**(code **)(*local_res8 + 0x350))(local_res8);
  if (((*(int *)((longlong)local_res8 + 0x9c4) < 2) &&
      (*(char *)((longlong)local_res8 + 0x96) != '\0')) && ((char)local_res8[0xec] == '\0')) {
    uVar7 = FUN_00500f90(PTR_PTR_004c1db0,1);
    *(undefined8 *)((longlong)local_res8 + 0x8e4) = uVar7;
    iVar5 = *(int *)((longlong)local_res8 + 0x70c);
    local_34 = 0;
    if (-1 < iVar5 + -1) {
      do {
        local_241[0] = 0;
        local_348 = (undefined4 *)local_241;
        local_340 = DAT_007ab120;
        (**(code **)(*(longlong *)((longlong)local_res8 + 0x9b4) + 8))
                  (*(longlong *)((longlong)local_res8 + 0x9b4),8,local_34,0);
        FUN_00413900(&local_338,local_241,0x201);
        (**(code **)(**(longlong **)((longlong)local_res8 + 0x8e4) + 0x78))
                  (*(longlong **)((longlong)local_res8 + 0x8e4),local_338);
        local_34 = local_34 + 1;
        iVar5 = iVar5 + -1;
      } while (iVar5 != 0);
    }
  }
  if (*(char *)((longlong)local_res8 + 0x91) != '\0') {
    if ((char)local_res8[0xec] != '\0') {
      if (((*(uint *)(local_res8 + 0x98) & 4) == 0) ||
         (*(longlong *)((longlong)local_res8 + 0x4c4) == 0)) {
        (**(code **)(*local_res8 + 0x358))(local_res8);
      }
      else {
        FUN_00746540(local_res8[2],*(undefined8 *)((longlong)local_res8 + 0x4c4));
      }
      *(undefined8 *)((longlong)local_res8 + 0x4c4) = 0;
      *(uint *)(local_res8 + 0x98) = *(uint *)(local_res8 + 0x98) & 0xfffffffb;
    }
    local_241[0] = 0;
    local_348 = (undefined4 *)local_241;
    local_340 = DAT_007ab120;
    (**(code **)(*(longlong *)((longlong)local_res8 + 0x9b4) + 8))
              (*(longlong *)((longlong)local_res8 + 0x9b4),0x2f,0,0);
    FUN_00413900((longlong)local_res8 + 0x3c,local_241,0x201);
    cVar3 = FUN_007ad100(local_res8,local_251);
    if (cVar3 != '\0') {
      local_278 = local_res8 + 0x96;
      FUN_00409bb0(local_251,local_278,0x10);
    }
  }
  FUN_005bf650();
  FUN_005bf680();
  local_348 = (undefined4 *)((ulonglong)local_348 & 0xffffffffffffff00);
  (**(code **)(*local_res8 + 0x378))(local_res8,L"Finished (Create)",1,0xffffffff);
LAB_007ab065:
  FUN_00411ff0(&local_338,0xb);
  FUN_00411f60(&local_2e0);
  FUN_00411f10(&local_2d8);
  FUN_00411ff0(&local_2c0,3);
  FUN_00411f10(&local_288);
  FUN_00411f10(local_28);
  if (param_2 != '\0') {
    local_res8 = (longlong *)FUN_0040f510(local_res8);
  }
  return local_res8;
}


