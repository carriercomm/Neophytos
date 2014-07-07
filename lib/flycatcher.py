'''
    When I am writting code I like to write as little as possible, then go back
    later and improve for performance. Well, this little logging module likely
    does not have the highest performance or portability, but for development it
    is really nice because it will automatically get the caller's module name,
    function name, and line number. This makes coding lot easier and finding
    exactly where bugs are present at.
'''

import inspect
import sys

enabled = []
ffunc = None

class Class:
    Debug       = 1
    Warn        = 2

class Logger:
    def __init__(self, group):
        global ffunc
        self.group = group
        self.ffunc = ffunc

    def __getCallerInfo(self):
        sinfo = inspect.stack()[2]
        module = inspect.getmodule(sinfo[0]).__name__
        caller = sinfo[3]
        lineno = inspect.getlineno(sinfo[0])
        return module, caller, lineno

    def setFilterFunction(self, _ffunc):
        self.ffunc = _ffunc

    def warn(self, msg):
        self.report(Class.Warn, msg)

    def debugNEOL(self, msg):
        self.report(Class.Debug, msg, True, False)

    def debug(self, msg):
        self.report(Class.Debug, msg)

    def report(self, mclass, msg, justmsg = False, eol = True):
        global enabled
        # if not enabled then return
        if mclass not in enabled:
            return
        module, caller, lineno = self.__getCallerInfo()
        # the filter function can make it easy to filter out certain messages
        if self.ffunc is not None:
            if self.ffunc(self, mclass, self.group, module, caller, lineno, msg) is False:
                return

        # convert class to textual representation
        if mclass == Class.Warn: mclass = 'WARN'
        if mclass == Class.Debug: mclass = 'DEBUG'

        # if not just message
        if not justmsg:
            msg = '%s:%s:%s:%s:%s:%s' % (mclass, self.group, module, caller, lineno, msg)
        # if no eol
        if eol:
            print(msg)
        else:
            print(msg, end='')
        sys.stdout.flush()

def enable(mclass):
    global enabled
    if mclass not in enabled:
        enabled.append(mclass)

def setFilterFunction(_ffunc):
    global ffunc
    ffunc = _ffunc

def getLogger(group):
    return Logger(group)
