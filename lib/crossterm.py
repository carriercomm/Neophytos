'''
    Leonard Kevin McGuire Jr 2014 (kmcg3413@gmail.com)

    CrossTerm

    This gives an implementation similar to ncurses and the python curses module. The
    API is totally different, but it does try to provide a minimal cross-platform 
    support for positional printing and colors.

    It also supports cross-process access. This allows you to query information from
    another process through a TCP server.

    * colors still being implemented
'''

import random
import struct
import sys
import math
import sys

from ctypes import *

try:
    import curses
    hasCurses = True
except:
    hasCurses = False


def findmulti(s, m):
    f = -1
    for _m in m:
        i = s.find(_m)
        if i > -1 and (i < f or f < 0):
            f = i
    return f

'''
    move cursor up N lines
        \x1b[<N>A
    move cursor down N lines
        \x1b[<N>B
    move cursor forward N columns
        \x1b[<N>C
    move cursor backward N columns
        \x1b[<N>D

    This class serves as a proxy to the actual stdout
    stream object under Windows. It translates the 
    implemented ANSI escape sequences into the equivilent
    operation in an console buffer under Windows.
'''
class TextAttribute:
    fg_red =           4
    fg_green =         2
    fg_blue =          1
    fg_intense =       8
    bg_blue =          16
    bg_green =         32
    bg_red =           64
    bg_intense =       128

class ProxyStream:
    colors = {
        1:      TextAttribute.fg_intense | TextAttribute.bg_intense,
        30:     0,
        31:     TextAttribute.fg_red,
        32:     TextAttribute.fg_green,
        33:     TextAttribute.fg_green | TextAttribute.fg_blue,
        34:     TextAttribute.fg_blue,
        35:     TextAttribute.fg_red | TextAttribute.fg_blue,
        36:     TextAttribute.fg_red | TextAttribute.fg_green,
        37:     TextAttribute.fg_red | TextAttribute.fg_green | TextAttribute.fg_blue,
        40:     0,
        41:     TextAttribute.bg_red,
        42:     TextAttribute.bg_green,
        43:     TextAttribute.bg_green | TextAttribute.bg_blue,
        44:     TextAttribute.bg_blue,
        45:     TextAttribute.bg_red | TextAttribute.bg_blue,
        46:     TextAttribute.bg_red | TextAttribute.bg_green,
        47:     TextAttribute.bg_red | TextAttribute.bg_green | TextAttribute.bg_blue,
    }
    def __init__(self, ct):
        self.ct = ct
        # need to read the attributes not guess about them...
        self.cattr = ProxyStream.colors[37] | ProxyStream.colors[40]

    def write(self, data):
        parts = data.split('\x1b')

        self.ct.stdout.write(parts[0])
        for x in range(1, len(parts)):
            part = parts[x]
            # find one of the specific letters codes
            i = findmulti(part, ('A', 'B', 'C', 'D', 'm'))
            val = part[part.find('[') + 1:i]
            code = part[i]
            msg = part[i + 1:]
            # just buffer onto the screen before we change position
            self.ct.stdout.flush()
            cx, cy = self.ct.wingetcursorposition()
            if code == 'A':
                cy = cy - int(val)
            if code == 'B':
                cy = cy + int(val)
            if code == 'C':
                cx = cx + int(val)
            if code == 'D':
                cx = cx - int(val)
            if code == 'm':
                vals = val.split(';')
                attr = self.cattr
                for val in vals:
                    val = int(val)
                    # foreground color set
                    if val >= 30 and val <= 37:
                        attr &= 0xf8
                        attr |= ProxyStream.colors[val]
                        continue
                    # background color set
                    if val >= 40 and val <= 47:
                        # clear background colors
                        attr &= 0x8f
                        attr |= ProxyStream.colors[val]
                        continue
                self.ct.winsetconsoletextattribute(attr)
                self.cattr = attr
            # change position
            self.ct.stdout.write('cx:%s cy:%s\n' % (cx, cy))
            self.ct.winsetcursorposition(cx, cy)
            # write remaining string
            self.ct.stdout.write(msg)
    def flush(self):
        self.ct.stdout.flush()

class CrossTerm:
    def __init__(self):
        global hasCurses
        self.hasCurses = hasCurses
        # if on win32 platform use kernel32 dynamic link library and
        # use a proxy to implement the ANSI escape sequences
        if not hasCurses:
            self.hdll = windll.LoadLibrary('kernel32.dll')
            self.hSetConsoleCursorPosition = self.hdll['SetConsoleCursorPosition']
            self.hGetStdHandle = self.hdll['GetStdHandle']
            self.hWriteConsoleOutputCharacter = self.hdll['WriteConsoleOutputCharacterA']
            self.hGetConsoleScreenBufferInfo = self.hdll['GetConsoleScreenBufferInfo']
            self.hSetConsoleTextAttribute = self.hdll['SetConsoleTextAttribute']
            self.hSetConsoleMode = self.hdll['SetConsoleMode']
            self.hGetConsoleMode = self.hdll['GetConsoleMode']
            self.stdout = sys.stdout
            self.stderr = sys.stderr
            sys.stdout = ProxyStream(self)

    def winsetconsolemode(self, mode):
        ch = self.hGetStdHandle(c_int(-11))
        return self.hSetConsoleMode(c_uint(ch), c_uint(mode))

    def winsetconsoletextattribute(self, attr):
        ch = self.hGetStdHandle(c_int(-11))
        return self.hSetConsoleTextAttribute(c_uint(ch), c_uint(attr))

    '''
        This will set the absolute cursor position.
    '''
    def winsetcursorposition(self, x, y):
        ch = self.hGetStdHandle(c_int(-11))
        s = (y << 16) | (x)
        return self.hSetConsoleCursorPosition(c_uint(ch), c_ulong(s))

    '''
        Will return current cursor position.
    '''
    def wingetcursorposition(self):
        ch = self.hGetStdHandle(c_int(-11))
        buf = struct.pack('<HHHHHHHHHHH', 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.hGetConsoleScreenBufferInfo(c_uint(ch), c_char_p(buf))
        info = struct.unpack_from('hhhh', buf)
        cx = info[2]
        cy = info[3]
        return (cx, cy)

    def _getconsolescreenbufferinfo(self):
            ch = self.hGetStdHandle(c_int(-11))
            buf = struct.pack('<HHHHHHHHHHH', 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
            self.hGetConsoleScreenBufferInfo(c_uint(ch), c_char_p(buf))
            info = struct.unpack_from('<HHHHHHHHH', buf)
            # http://msdn.microsoft.com/en-us/library/ms682093(v=vs.85).aspx
            binfo = BufferInfo()
            binfo.sizeW = info[0]
            binfo.sizeH = info[1]
            binfo.cursorPosX = info[2]
            binfo.cursorPosY = info[3]
            binfo.attributes = info[4]
            binfo.winX = info[5]
            binfo.winY = info[6]
            binfo.winW = info[7]
            binfo.winH = info[8]
            return binfo

    '''
        Get size of visible screen. (Does not include buffer size if any.)
    '''
    def getscreensize(self):
        if self.hasCurses:
            return self.win.getyx()
        else:
            binfo = self._getconsolescreenbufferinfo()
            #w = info[0] - width of entire screen buffer
            #h = info[1] - height of entire screen buffer

            #print(info[5])
            #print(info[6])
            #print(info[7])
            #print(info[8])

            w = binfo.winW - binfo.winX
            h = binfo.winH - binfo.winY
            return (w, h)

    '''
        Write string at position.
    '''
    def winwritestringat(self, x, y, s, attr = 0):
        y = self.topy + y
        ch = self.hGetStdHandle(c_int(-11))
        s = bytes(s, 'utf8')
        wrote = struct.pack('<Q', 0)
        cord = (y << 16) | x
        err = self.hWriteConsoleOutputCharacter(c_uint(ch), c_char_p(s), c_uint(len(s)), cord, c_char_p(wrote))

ct = CrossTerm()

if __name__ == '__main__':
    wrapper(main)