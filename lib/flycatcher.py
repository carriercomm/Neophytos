'''
    When I am writting code I like to write as little as possible, then go back
    later and improve for performance. Well, this little logging module likely
    does not have the highest performance or portability, but for development it
    is really nice because it will automatically get the caller's module name,
    function name, and line number. This makes coding lot easier and finding
    exactly where bugs are present at.
'''

import inspect

enabled = False

class Logger:
    def __init__(self, group):
        self.group = group

    def __getCallerInfo(self):
        sinfo = inspect.stack()[2]
        module = inspect.getmodule(sinfo[0]).__name__
        caller = sinfo[3]
        lineno = inspect.getlineno(sinfo[0])
        return module, caller, lineno

    def debug(self, msg):
        if not enabled:
            return
        module, caller, lineno = self.__getCallerInfo()
        fmt = fmt % args
        print('DEBUG:%s:%s:%s' % (self.group, module, caller, lineno, msg))

def enable():
    enabled = True

def getLogger(group):
    return Logger(group)
