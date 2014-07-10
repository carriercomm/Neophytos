#!/bin/sh
gcc native.c -nostdlib --freestanding -fPIC -shared -nostdlib -o native64.so
