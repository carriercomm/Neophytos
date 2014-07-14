#!/bin/sh
#
#       the final name needs to be different for example:
#
#       cryptxor.x86.so
#       cryptxor.x86_64.so
#       cryptxor.arm.so
#       cryptxor.x86.dll
#       cryptxor.x86_64.dll
#
#       the `dll` or `so` suffix deems it either PE32/PE64 or ELF32/ELF64
#       and i suspect any other format shall have either a different suffix
#       or a different arch thus keeping everything properly named
#
#
gcc cryptxor.c -o cryptxor.so -fPIC -shared
