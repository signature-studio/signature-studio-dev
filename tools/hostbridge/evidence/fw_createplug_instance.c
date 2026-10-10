=== decomp 86ab10 -> CreatePlugInstance @0086ab10 size=121

undefined8 CreatePlugInstance(undefined8 param_1,undefined8 param_2)

{
  char cVar1;
  undefined8 uVar2;
  longlong lVar3;
  undefined8 *puVar4;
  undefined8 *puVar5;
  undefined8 local_c8 [2];
  undefined1 local_b4 [140];
  
                    /* 0x46ab10  3  CreatePlugInstance */
  puVar4 = &DAT_008f4e6c;
  puVar5 = local_c8;
  for (lVar3 = 0x14; lVar3 != 0; lVar3 = lVar3 + -1) {
    *puVar5 = *puVar4;
    puVar4 = puVar4 + 1;
    puVar5 = puVar5 + 1;
  }
  cVar1 = FUN_0073ee30(param_1,param_2,0,local_b4);
  if (cVar1 == '\0') {
    uVar2 = 0;
  }
  else {
    FUN_0077fbb0(param_1,param_2);
    uVar2 = FUN_00878f00(PTR_PTR_00868918,1,param_2,param_1,local_c8);
  }
  return uVar2;
}


