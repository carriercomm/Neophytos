#!/bin/sh
gcc native.c -nostdlib --freestanding -fPIC -shared -o native64.so
