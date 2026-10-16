set pagination off
set architecture i386:x86-64
handle SIGUSR1 nostop noprint pass
break *__ADDR__
commands
silent
printf "HIT dl=0x%02x rcx=0x%016lx vptr=0x%016lx ret=0x%016lx\n", $dl, $rcx, *(unsigned long*)$rcx, *(unsigned long*)$rsp
continue
end
continue
