=== decomp 7a87c0 -> FUN_007a87c0 @007a87c0 size=1209

longlong FUN_007a87c0(longlong param_1,int param_2,undefined4 param_3,undefined8 param_4,
                     undefined8 param_5,undefined4 param_6)

{
  bool bVar1;
  bool bVar2;
  char cVar3;
  int iVar4;
  longlong lVar5;
  longlong *plVar6;
  longlong lVar7;
  longlong *plVar8;
  byte bVar9;
  int iVar10;
  undefined8 local_58;
  undefined8 local_50 [2];
  undefined8 local_40 [2];
  
  local_58 = 0;
  local_50[0] = 0;
  local_40[0] = 0;
  lVar7 = 0;
  plVar8 = DAT_008e5d00;
  if ((param_1 != 0) && (*(longlong *)(param_1 + 0x40) != 0)) {
    plVar8 = *(longlong **)(param_1 + 0x40);
  }
  if ((plVar8 != (longlong *)0x0) &&
     (cVar3 = (**(code **)(*plVar8 + 0x88))(plVar8,10), cVar3 == '\0')) {
    FUN_005bf650();
    FUN_005bf680();
  }
  if (param_2 < 0x22) {
    if (param_2 == 0x21) {
      FUN_0041b300(&local_58,PTR_u_Fruity_Wrapper_008e5cf8);
      FUN_0056c080(param_5,local_58);
      lVar7 = 1;
      goto LAB_007a8c28;
    }
    if (param_2 == 1) {
      lVar7 = 0x960;
      goto LAB_007a8c28;
    }
    if (param_2 == 2) {
      if ((plVar8 == (longlong *)0x0) || ((*(uint *)(plVar8 + 0x98) & 2) == 0)) {
        lVar7 = 0;
      }
      else {
        lVar7 = (longlong)*(int *)((longlong)plVar8 + 0x9bc);
      }
      goto LAB_007a8c28;
    }
    if (param_2 == 0x20) {
      FUN_0041b300(local_50,PTR_u_Image_Line_008e5cf0);
      FUN_0056c080(param_5,local_50[0]);
      lVar7 = 1;
      goto LAB_007a8c28;
    }
  }
  else {
    if (param_2 == 0x22) {
      lVar7 = 0x271a;
      goto LAB_007a8c28;
    }
    if (param_2 == 0x25) {
      FUN_004138a0(local_40,param_5);
      iVar4 = FUN_00413e60(local_40[0],L"sendVstEvents");
      if ((((((iVar4 == 0) || (iVar4 = FUN_00413e60(local_40[0],L"sendVstMidiEvent"), iVar4 == 0))
            || (iVar4 = FUN_00413e60(local_40[0],L"supportShell"), iVar4 == 0)) ||
           ((iVar4 = FUN_00413e60(local_40[0],L"sendVstTimeInfo"), iVar4 == 0 ||
            (iVar4 = FUN_00413e60(local_40[0],L"supplyIdle"), iVar4 == 0)))) ||
          (iVar4 = FUN_00413e60(local_40[0],L"acceptIOChanges"), iVar4 == 0)) ||
         ((iVar4 = FUN_00413e60(local_40[0],L"receiveVstMidiEvent"), iVar4 == 0 ||
          (iVar4 = FUN_00413e60(local_40[0],L"shellCategory"), iVar4 == 0)))) {
        lVar7 = 1;
      }
      else {
        iVar4 = FUN_00413e60(local_40[0],L"sizeWindow");
        if (iVar4 == 0) {
          lVar7 = 1;
          if ((plVar8 != (longlong *)0x0) &&
             (cVar3 = (**(code **)(*(longlong *)plVar8[0xf] + 0xd8))((longlong *)plVar8[0xf],0),
             cVar3 == '\0')) {
            lVar7 = -1;
          }
        }
        else {
          iVar4 = FUN_00413e60(local_40[0],L"receiveVstEvents");
          if ((((iVar4 == 0) ||
               (iVar4 = FUN_00413e60(local_40[0],L"receiveVstTimeInfo"), iVar4 == 0)) ||
              (iVar4 = FUN_00413e60(local_40[0],L"reportConnectionChanges"), iVar4 == 0)) ||
             ((iVar4 = FUN_00413e60(local_40[0],L"asyncProcessing"), iVar4 == 0 ||
              (iVar4 = FUN_00413e60(local_40[0],L"offline"), iVar4 == 0)))) {
            lVar7 = -1;
          }
          else {
            lVar7 = 0;
          }
        }
      }
      goto LAB_007a8c28;
    }
    if (param_2 == 0x2a) {
      if ((((param_1 != 0) && (plVar8 != (longlong *)0x0)) &&
          (*(char *)((longlong)plVar8 + 0x7a1) == '\0')) &&
         (*(char *)((longlong)plVar8 + 0x7a2) == '\0')) {
        if (((char)plVar8[0x135] == '\0') && (*(char *)((longlong)plVar8 + 0x94) == '\0')) {
          *(undefined1 *)((longlong)plVar8 + 0x7a2) = 1;
          if (*(char *)((longlong)plVar8 + 0x754) != '\0') {
            cVar3 = (**(code **)(*plVar8 + 0x88))(plVar8,8);
            if (cVar3 != '\0') {
              bVar1 = false;
              iVar4 = FUN_00745240();
              iVar10 = 0;
              bVar2 = false;
              if (-1 < iVar4 + -1) {
                do {
                  bVar1 = bVar2;
                  lVar5 = FUN_00745250(plVar8,iVar10);
                  if (*(char *)(lVar5 + 0x38) != '\0') {
                    plVar6 = (longlong *)FUN_00745250(plVar8,iVar10);
                    (**(code **)(*plVar6 + 0x48))(plVar6);
                    bVar1 = true;
                  }
                  iVar10 = iVar10 + 1;
                  iVar4 = iVar4 + -1;
                  bVar2 = bVar1;
                } while (iVar4 != 0);
              }
              if (bVar1) {
                (**(code **)*plVar8)(plVar8,1);
              }
            }
          }
          cVar3 = (**(code **)(*plVar8 + 0x88))(plVar8,9);
          if (cVar3 != '\0') {
            FUN_007b3210(plVar8);
          }
          (**(code **)(*plVar8 + 0x370))(plVar8,1);
          bVar9 = DAT_007a8f10;
          if (((*(longlong *)((longlong)plVar8 + 0x9b4) != 0) &&
              (bVar9 = DAT_007a8f10 | 2, (char)plVar8[0xf4] != '\0')) &&
             (*(int *)(*(longlong *)((longlong)plVar8 + 0x9b4) + 0x2c) !=
              *(int *)((longlong)plVar8 + 0x70c))) {
            (**(code **)(*plVar8 + 0x350))(plVar8);
          }
          (**(code **)(*plVar8 + 0x20))(plVar8,bVar9,1);
          *(undefined1 *)((longlong)plVar8 + 0x7a2) = 0;
        }
        else {
          *(undefined1 *)((longlong)plVar8 + 0x9a9) = 1;
        }
      }
      goto LAB_007a8c28;
    }
  }
  lVar7 = 0;
  if ((param_1 != 0) && (plVar8 != (longlong *)0x0)) {
    lVar7 = FUN_007abca0(plVar8,param_2,param_3,param_4,param_5,param_6);
  }
LAB_007a8c28:
  if ((plVar8 != (longlong *)0x0) &&
     (cVar3 = (**(code **)(*plVar8 + 0x88))(plVar8,10), cVar3 == '\0')) {
    FUN_005bf650();
    FUN_005bf680();
  }
  FUN_00412040(&local_58,2);
  FUN_00411f10(local_40);
  return lVar7;
}


