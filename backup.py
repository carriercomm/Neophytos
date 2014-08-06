import os
import os.path
import sys                      
import pprint                               # not used anymore..
import re                                   # not directly used
import threading                            # not used anymore
import time                                 # not used anymore
import signal
import gc
import operator

from lib import misc                        # ... likely old unused junk.. need removal really..
from lib import output                      # serves as tcp status server.. needs to be rebuilt and
                                            # possibly integrated into or with crossterm for remote
                                            # output
from lib.pluginman import getPM

from lib.filter import Filter               # single filter created from file normally
from lib.efilters import EncryptionFilters  # encryption filters created from encryption filter file



import lib.crossterm as crossterm           # cross-platform console API
import lib.flycatcher as flycatcher         # debugging tool

def dumpmemory():
    types = {}
    sizes = {}
    objs = gc.get_objects()
    for obj in objs:
        xtype = type(obj)
        if xtype not in types:
            types[xtype] = 0
            sizes[xtype] = 0
        types[xtype] += 1
        try:
            sizes[xtype] += obj.__sizeof__()
        except:
            pass
    fd = open('memdbg', 'w')
    _sorted = sorted(sizes.items(), key=operator.itemgetter(1))
    for key, value in _sorted:
        fd.write('%s:%s:%s\n' % (sizes[key], types[key], key))
    fd.close()
    exit()

#def hand_inter(signum, frame):
#    dumpmemory()
#    exit()
#signal.signal(signal.SIGINT, hand_inter)

'''
    The fly filter has to be setup before modules are loaded, because
    they may create a logger object during initialization. The logger
    on creation assigns the global filter function to the logger. You
    can set individual loggers with a filter if desired.
'''
def flyFilter(logger, mclass, group, module, caller, lineno, msg):
    if mclass != flycatcher.Class.Debug:
        return True

    onlythese = (
        'keep-length',
    )

    for ot in onlythese:
        if msg.find(ot) > -1:
            return True

    return False

    disableThese = (
        '<request-size>:',
        'patching-section:',
        '<got-size>:',
        #'<up-to-date>:',
        '<got-date>:',
        'hash:',
        #'removing:',
        'patching-split:',
        'patching-match:',
        '<delay-hash-send>:',
    )

    for dt in disableThese:
        if msg.find(dt) == 0:
            return False
    return True
flycatcher.setFilterFunction(flyFilter)

import lib.buops                        # backup operations

class Catcher:
    def __init__(self, filterFile, efilterfile, defcryptstring):
        # ensure default encryption filter object is created
        self.efilters = EncryptionFilters(efilterfile, defcryptstring)

        if filterFile is not None:
            self.filter = Filter(filterFile)
        else:
            self.filter = None

        self.writeCount = 0
        self.startCount = 0
        self.finishCount = 0
        self.hashGoodCount = 0
        self.hashBadCount = 0
        self.dateReplyCount = 0
        self.sizeReplyCount = 0
        self.bytesWrote = 0
        self.acceptedCount = 0
        self.rejectedCount = 0

        self.linecnt = 0
        self.smsgcnt = 0

        print('\n\n\n\n\n', end='\x1b[3A')

    def writeline(self, txt, row = 0):
        # write line and move back
        if row > 0:
            print('', end='\x1b[%sB' % row)
        print(txt, end = '\x1b[1000D')
        if row > 0:
            print('', end='\x1b[%sA' % row)

    def event(self, *args):
        ename = args[0]

        #self.writeline(ename)

        if ename == 'DecryptByTag':
            return self.catchDecryptByTag(*args[1:])
        if ename == 'EncryptFilter':
            return self.catchEncryptFilter(*args[1:])
        if ename == 'Filter':
            return self.catchFilter(*args[1:])
        if False:
            return
        if ename == 'FileWrite':
            #txt = '%s:%x:%x' % (args[1], args[2], args[3])
            #txt = txt.ljust(40)
            #self.writeline(txt, row = 3)
            return
        if ename == 'Cycle' or ename == 'DumpCycle':
            return
        if ename == 'DataOut':
            ch = '#'
            vp = '#'.rjust(self.smsgcnt % 40)
            vp = vp.ljust(40)
            vp = 'Local: [%s]' % vp
            self.smsgcnt += 1
            self.writeline(vp, row = 1)            
            return
        if ename == 'DataIn':
            vp = '#'.rjust(self.smsgcnt % 40)
            vp = vp.ljust(40)
            vp = 'Server:[%s]' % vp
            self.smsgcnt += 1
            self.writeline(vp, row = 2)
            return
        
        ignored = ('MessageOut', 'MessageIn')

        if ename in ignored:
            return

        lpath = args[2]
        txt = lpath.decode('utf8', 'ignore')
        if len(txt) > 40:
            txt = txt[-40:]
        txt = 'File:  [%s]' % (txt.ljust(40))
        self.writeline(txt)

        self.linecnt += 1


    def catchDecryptByTag(self, tag):
        # we need to search throuh our encryption filter
        # and attempt to determine the plugin and options
        # to pass for reversal of the encryption
        return self.efilters.reverse(tag)

    def catchEncryptFilter(self, lpath, node, isDir):
        if self.efilters is not None:
            # get the encryption information we need
            einfo = self.efilters.check(lpath, node, isDir)
            # build and name some important stuff for readability
            etag = einfo[0]
            plugid = einfo[1]
            plugopts = einfo[2]
            plugtag = '%s.%s' % (plugid, plugopts)
            plug = getPM().getPluginInstance(plugid, plugtag, (None, plugopts,))
        else:
            # this should rarely be used.. the caller will likely be providing
            # the efilter object when calling this function, but it is here
            # in the event that they do not..
            etag = b''
            plug = getPM().getPluginInstance('crypt.null', '', (c, []))
            plugopts = (c, [])
        return (etag, plug, plugopts)
    def catchFilter(self, lpath, node, isDir):
        if self.filter is None:
            return True
        result = self.filter.check(lpath, node, isDir)
        if result:
            self.acceptedCount += 1
        else:
            self.rejectedCount += 1
        print('result', result)
        return result

def showHelp():
    opts = {}

    opts['--lpath'] = 'specifies the local path'
    opts['--rpath'] = 'specifies the remote stub/target or path'
    opts['--password'] = 'specifies the authorization code'
    opts['--authcode'] = 'specifies the authorization code'
    opts['--push'] = 'pushes files to server (NEVER DELETES)'
    opts['--pull'] = 'pulls files from server (NEVER DELETES)'
    opts['--sync-deleted-to-server'] = 'deletes files on server missing on local'
    opts['--sync-deleted-to-local'] = 'deletes files on local missing on server'
    opts['--host'] = '(optional) the IP or hostname of the server'
    opts['--port'] = '(optional) the port for the server'
    opts['--cipher'] = '(optional) the SSL cipher string to enforce'
    opts['--filter-file'] = '(optional) the filter file'
    opts['--make-sample-filter-file'] = '(optional) produces a sample filter file'
    opts['--no-ssl'] = 'disables SSL/TLS'
    opts['--debug'] = 'displays debug messages; likely to a file called .stdout'
    opts['--no-sformat'] = 'does not use stash file format on server'
    opts['--efilter-file'] = '(optional) encryption filter file'
    opts['--def-crypt'] = '(optional) encryption or default encryption to use if no match in encryption filter file'

    for k in opts:
        print(k.ljust(20), opts[k])

def main(args):
    '''
    '''
    # parse command line arguments
    opts = (
        'lpath', 'rpath', 'password', 'push', 'pull', 'sync-deleted-to-server',
        'host', 'port', 'cipher', 'filter-file', 'make-sample-filter-file',
        'password', 'authcode', 'auth-code', 'no-ssl', 'debug', 'no-sformat',
        'sync-deleted-to-local', 'efilter-file', 'def-crypt'
    )

    if len(args) == 0 or '--help' in args or '/?' in args:
        return showHelp()

    setopts = {}
    for arg in args:
        for opt in opts:
            _opt = '--%s' % opt
            if arg.find(_opt) == 0:
                val = arg[len(_opt):]
                if len(val)> 0 and val[0] == '=':
                    val = val[1:] 
                setopts[opt] = val

    # by default enable warnings
    flycatcher.enable(flycatcher.Class.Warn)
    # enable debugging output if specified
    if 'debug' in setopts:
        flycatcher.enable(flycatcher.Class.Debug)

    # fill in any missing arguments 
    if 'host' not in setopts:
        setopts['host'] = 'kmcg3413.net'
    if 'port' not in setopts:
        setopts['port'] = '4322'

    if 'authcode' in setopts:
        setopts['password'] = setopts['authcode']
    if 'auth-code' in setopts:
        setopts['password'] = setopts['auth-code']

    if 'rpath' not in setopts:
        setopts['rpath'] = '/'
    if 'lpath' not in setopts:
        print('--lpath=<path> must be specified')
        return

    # all path operations are done using bytes which allow
    # us to handle filenames using any characters...

    # convert remote path into bytes
    setopts['rpath'] = bytes(setopts['rpath'], 'utf8')
    # convert local path into bytes
    setopts['lpath'] = bytes(setopts['lpath'], 'utf8')        


    if 'no-ssl' not in setopts:
        setopts['ssl'] = True
    else:
        setopts['ssl'] = False
    if 'no-sformat' not in setopts:
        setopts['sformat'] = True
    else:
        setopts['sformat'] = False

    # load filter file if specified
    filter = None
    if 'filter-file' in setopts:
        filterFile = setopts['filter-file']
    else:
        filterFile = None

    # convert certain arguments needed into proper types
    if 'port' in setopts:
        try:
            setopts['port'] = int(setopts['port'])
        except ValueError:
            print('the port must be an integer value not "%s"' % setopts[opt])
            return

    if 'host' not in setopts or 'port' not in setopts:
        print('the --host=<host> and --port=<port> must be specified')
        return

    if 'push' not in setopts and 'pull' not in setopts and 'sync-deleted-to-server' not in setopts and 'sync-deleted-to-local' not in setopts:
        print('..you must specify an operation of push, pull, sync-rdel, or sync-ldel')
        showHelp()
        return

    sw = Catcher(filterFile, setopts.get('efilter-file', None), setopts.get('def-crypt', ',crypt.null'))

    if 'push' in setopts:
        lib.buops.Push(
            setopts['host'], setopts['port'], setopts['password'], setopts['lpath'],
            setopts['rpath'], setopts['ssl'], sw.event
        )
        return 
    if 'pull' in setopts:
        lib.buops.Pull(
            setopts['host'], setopts['port'], setopts['password'], setopts['lpath'],
            setopts['rpath'], setopts['ssl'], sw.event
        )
        return
    if 'sync-deleted-to-server' in setopts:
        lib.buops.SyncRemoteWithDeleted(
            setopts['host'], setopts['port'], setopts['password'], setopts['lpath'],
            setopts['rpath'], setopts['ssl'], sw.event
        )
        return
    if 'sync-deleted-to-local' in setopts:
        lib.buops.SyncLocalWithDeleted(
            setopts['host'], setopts['port'], setopts['password'], setopts['lpath'],
            setopts['rpath'], setopts['ssl'], sw.event
        )
        return
        
    return

# only execute this if we are the primary
# script file being executed by Python
if __name__ == '__main__':
    # set ourselves to idle unless specified to run as normal
    misc.setProcessPriorityIdle()
    # setup standard outputs (run TCP server)
    output.Init(output.Mode.TCPServer)
    main(sys.argv[1:])