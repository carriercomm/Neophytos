'''
    Leonard Kevin McGuire Jr 2014 (kmcg3413@gmail.com)

    CrossTerm

    This gives an implementation similar to ncurses and the python curses module. The
    API is totally different, but it does try to provide a minimal cross-platform 
    support for positional printing and colors.

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

class BufferInfo:
    pass


class CrossTerm:
    def __init__(self, win):
        global hasCurses
        self.win = win
        self.hasCurses = hasCurses
        # if on win32 platform use kernel32 dynamic link library
        if not hasCurses:
            self.hdll = windll.LoadLibrary('kernel32.dll')
            #self.hSetConsoleCursorPosition = CFUNCTYPE(c_int)(('SetConsoleCursorPosition', self.hdll))
            self.hSetConsoleCursorPosition = self.hdll['SetConsoleCursorPosition']
            #self.hGetStdHandle = CFUNCTYPE(c_uint)(('GetStdHandle', self.hdll))
            self.hGetStdHandle = self.hdll['GetStdHandle']
            #self.hWriteConsoleOutputCharacter = CFUNCTYPE(c_uint)(('WriteConsoleOutputCharacterA', self.hdll))
            self.hWriteConsoleOutputCharacter = self.hdll['WriteConsoleOutputCharacterA']
            #self.hGetConsoleScreenBufferInfo = CFUNCTYPE(c_uint)(('GetConsoleScreenBufferInfo', self.hdll))
            self.hGetConsoleScreenBufferInfo = self.hdll['GetConsoleScreenBufferInfo']
            sw, sh = self.getScreenSize()

            # scroll the buffer so we get a new blank space
            # similar to how curses initializes the screen
            for i in range(0, sh):
                print('')
            # get the row index of the top line of our current
            # screen
            binfo = self._getConsoleScreenBufferInfo()
            self.topy = binfo.winY

    '''
        This will set the absolute cursor position.

        * curses did not implement this.. so me either but
          just wanted the code to stay for future reference
          if needed (for the win32 function call)
    '''
    #def setCursorPosition(self, x, y):
    #    if self.hasCurses:
    #        
    #    else:
    #        ch = self.hGetStdHandle(c_int(-11))
    #        self.hSetConsoleCursorPosition(c_uint(ch), c_short(x), c_short(y))

    '''
        Will return current cursor position.
    '''
    def getCursorPosition(self):
        if self.hasCurses:
            return self.win.getyx()
        else:
            ch = self.hGetStdHandle(c_int(-11))
            buf = struct.pack('<HHHHHHHHHHH', 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
            self.hGetConsoleScreenBufferInfo(c_uint(ch), c_char_p(buf))
            info = struct.unpack_from('<HHHH', buf)
            cx = info[2]
            cy = info[3]
            return (cx, cy)

    def update(self):
        if self.hasCurses:
            self.win.refresh()

    def clear(self):
        if self.hasCurses:
            self.win.clear()
            return

        # the win32 api has no function to clear the screen 
        # so i have to implement it in this function
        w, h = self.getScreenSize()
        for y in range(0, h):
            # create new lines the height of the current window (to keep scrollable history)
            self.writeStringAt(0, self.topy + h, ' ' * w)

    def _getConsoleScreenBufferInfo(self):
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

    def getScreenSize(self):
        if self.hasCurses:
            return self.win.getyx()
        else:
            binfo = self._getConsoleScreenBufferInfo()
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
    def writeStringAt(self, x, y, s, attr = 0, maxpad = 0):
        if maxpad > 0:
            if len(s) < maxpad:
                s = '%s%s' % (s, ' ' * (maxpad - len(s)))
            else:
                s = s[0:maxpad]

        if self.hasCurses:
            self.win.addstr(y, x, s, attr)
        else:
            y = self.topy + y
            ch = self.hGetStdHandle(c_int(-11))
            s = bytes(s, 'utf8')
            wrote = struct.pack('<Q', 0)
            cord = (y << 16) | x
            err = self.hWriteConsoleOutputCharacter(c_uint(ch), c_char_p(s), c_uint(len(s)), cord, c_char_p(wrote))

'''
    This version mainly adds support to help with boxing. It
    mainly serves to prevent you from overwriting your allocated
    area. 

    I may add support for automatic allocation of boxes somewhere 
    on the screen at a later time. But, for now you must specify
    your box dimensions.
'''
class BoxOverlapException(Exception):
    pass

class CrossTerm2Box:
    def __init__(self, ct, x, y, w, h, prefix = ''):
        self.ct = ct
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.prefix = prefix

    def setPrefix(self, prefix):
        self.prefix = prefix

    def getRect(self):
        return (self.x, self.y, self.w, self.h)

    def write(self, text):
        text = '%s%s' % (self.prefix, text)
        if len(text) > self.w * self.h:
            # truncate it
            text = text[0:self.w * self.h]
        rowcnt = int(math.ceil(len(text) / self.w))
        # write it over entire box
        for row in range(0, rowcnt):
            off = row * self.w
            line = text[off:self.w]
            self.ct.writeStringAt(self.x, self.y + row, line)

class CrossTerm2(CrossTerm):
    def __init__(self, *args):
        super().__init__(*args)
        self.w, self.h = self.getScreenSize()
        self.boxes = []

    '''
        You specify the box width and height and it will
        find a spot to put it.
    '''
    def getBoxAuto(self, w, h, prefix = ''):
        for x in range(0, self.w):
            for y in range(0, self.h):
                box = self.getBox(x, y, w, h, prefix = prefix)
                if box is not None:
                    return box
        # no space big enough for the box
        return None

    def getBox(self, x, y, w, h, prefix = ''):
        # look through list of boxes and find place to put
        nx1 = x
        ny1 = y
        nx2 = (x + w) - 1
        ny2 = (y + h) - 1

        # check for overlap
        for box in self.boxes:
            bx1, by1, bx2, by2 = box.getRect()
            bx2 += bx1
            by2 += by1

            if nx1 >= bx1 and nx1 < bx2 and ny1 >= by1 and ny1 < by2:
                if nx2 >= bx1 and nx2 < bx2 and ny2 >= by1 and ny2 < by2:
                    return None
        nbox = CrossTerm2Box(self, x, y, w, h, prefix = prefix)
        # trigger prefix if any
        if len(prefix) > 0:
            nbox.write('')
        self.boxes.append(nbox)
        return nbox

'''
    If using curses it wraps the code path so the terminal
    can be restored when program exits. If not using curses
    it either does an alternative initialization or nothing.
'''
def wrapper(f, *args):
    win = None
    if hasCurses:
        # initial screen
        win = curses.initscr()
        # turn on cbreak
        curses.cbreak()
        # turn off echo
        curses.noecho()
        # turn on terminal keypad
        win.keypad(1)
        # initialize colors
        try:
            curses.start_color()
        except:
            pass

    ct = CrossTerm2(win)
    if True or not hasCurses:
        #
        #            WINDOWS ONLY
        #
        # to keep the programming from accidentally
        # messing the window up by print something
        # to the screen we will direct all output
        # from print statements to a file; curses on
        # linux can handle print statements and do
        # not effect the buffer but we have no good 
        # way to do it on windows platform unless 
        # we created a brand new console window just
        # for our output
        stdout = open('.stdout', 'w')
        ct.stdout = sys.stdout         # save it
        sys.stdout = stdout            # protect it
        sys.stderr = stdout

    try:
        f(ct, *args)
    finally:
        if hasCurses:
            # restore cooked mode
            curses.nocbreak()
            # turns on echo
            curses.echo()
            # disales terminal keypad
            win.keypad(0)
            # restore terminal mode
            curses.endwin()
        else:
            ct.stdout.close()
'''
    My testing function.
'''
def main(xc):
    #print('\033[%sA' % y)   # move cursor up
    #print('\033[%sD' % x)   # move cursor left
    #print('\033[%s;%sH%s' % (y + 1, x + 1, s))   # set cursor position
    #writeStringAtPosition(0, 0, 'a world')
    #writeStringAtPosition(0, 1, 'b apple')
    #writeStringAtPosition(0, 2, 'c grape')
    #print('\033[6n')
    #win = curses.initscr()

    xc.clear()

    for a in range(0, 15):
        xc.writeStringAt(10, 2 + a, 'HELLO WORLD', 253)
    #xc.writeStringAt(10, 10, 'HELLO WORLD')
    xc.update()

    while True:
        pass

if __name__ == '__main__':
    wrapper(main)