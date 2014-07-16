import os
import os.path
import sys                      
import pprint                               # not used anymore..
import re                                   # not directly used
import threading                            # not used anymore
import time                                 # not used anymore

from lib import misc                        # ... likely old unused junk.. need removal really..
from lib import output                      # serves as tcp status server.. needs to be rebuilt and
                                            # possibly integrated into or with crossterm for remote
                                            # output

from lib.filter import Filter               # single filter created from file normally
from lib.efilters import EncryptionFilters  # encryption filters created from encryption filter file

import lib.crossterm as crossterm           # cross-platform console API
import lib.flycatcher as flycatcher         # debugging tool

'''
    The fly filter has to be setup before modules are loaded, because
    they may create a logger object during initialization. The logger
    on creation assigns the global filter function to the logger. You
    can set individual loggers with a filter if desired.
'''
def flyFilter(logger, mclass, group, module, caller, lineno, msg):
    if mclass != flycatcher.Class.Debug:
        return True

    return True

    onlythese = (
        '<wrote>',
    )

    for ot in onlythese:
        if msg.find(ot) == 0:
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
    def __init__(self, ct, filterFile, efilterFile, defcryptstring):
        self.ct = ct

        # ensure default encryption filter object is created
        self.efilters = EncryptionFilters(efilterfile, defcryptstring)

        if filterFile is not None:
            self.filter = Filter(filterFile)
        else:
            self.filter = None
        fsz = 30
        # allocate boxes to be used to hold status elements
        self.boxCurFile = ct.getBox(0, 0, 80, 1,     'CurFile:   ')
        self.boxStartCount = ct.getBox(0, 1, fsz, 1,  'Processed: ')
        self.boxFinishCount = ct.getBox(0, 2, fsz, 1, 'Finished:  ')
        self.boxHashGood = ct.getBox(0, 3, fsz, 1,    'HashGood:  ')
        self.boxHashBad = ct.getBox(0, 4, fsz, 1,     'HashBad:   ')
        self.boxDateReply = ct.getBox(0, 5, fsz, 1,   'DateReply: ')
        self.boxSizeReply = ct.getBox(0, 6, fsz, 1,   'SizeReply: ')
        self.boxBufferSize = ct.getBox(0, 7, fsz, 1,  'Buffer:    ')
        self.boxBytesWrote = ct.getBox(0, 8, fsz, 1,  'BytesOut:  ')
        self.boxLocalHash = ct.getBox(0, 9, 128, 1,   'LocalHash: ')
        self.boxRemoteHash = ct.getBox(0, 10, 128, 1, 'RemoteHash:')
        self.boxWriteCount = ct.getBox(0, 11, fsz, 1, 'WriteCount:')
        self.boxLastWrite = ct.getBox(0, 12, 128, 1,  'LastWrite: ')
        self.boxThroughput = ct.getBox(0, 13, fsz, 1, 'Throughput:')
        self.boxLPatchTime = ct.getBox(0, 14, fsz, 1, 'LPatch:Time: ')
        self.boxLPatchFile = ct.getBox(0, 15, 128, 1, 'LPatch:File: ')
        self.boxLPatchUp = ct.getBox(0, 16, fsz, 1,   'LPatch:Data: ')
        self.boxLPatchCtrl = ct.getBox(0, 17, fsz, 1, 'LPatch:Ctrl: ')
        self.boxLPatchOpCnt = ct.getBox(0, 18, fsz, 1,'LPatch:Ops:  ')
        self.boxLPatchSaved = ct.getBox(0, 19, fsz, 1,'LPatch:Saved:')
        self.boxAccepted = ct.getBox(0, 20, fsz, 1,   'Accepted:  ')
        self.boxRejected = ct.getBox(0, 21, fsz, 1,   'Rejected:  ')

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

    def catchEncryptFilter(self, lpath, node, isDir):
        if self.efilters is not None:
            # get the encryption information we need
            einfo = self.efilters.check(lpath, node, isDir)
            # build and name some important stuff for readability
            etag = einfo[0]
            plugid = einfo[1]
            plugopts = einfo[2]
            plugtag = '%s.%s' % (plugid, plugopts)
            plug = getPM().getPluginInstance(plugid, plugtag, (c, plugopts,))
        else:
            # this should rarely be used.. the caller will likely be providing
            # the efilter object when calling this function, but it is here
            # in the event that they do not..
            plug = getPM().getPluginInstance('crypt.null', '', (c, []))
        return plug
    def catchFilter(self, lpath, node, isDir):
        result = self.filter.check(lpath, node, isDir)
        if result:
            self.acceptedCount += 1
        else:
            self.rejectedCount += 1
        print('result', result)
        return result
    def catchPatchFinish(self, shrstate):
        self.catchFinished(None)
    def catchLongestPatchOp(self, op):
        self.boxLPatchTime.write('%s' % (time.time() - op.startTime))
        self.boxLPatchFile.write('%s' % op.lpath)
        self.boxLPatchUp.write('%s' % op.bytesPatched)
        self.boxLPatchCtrl.write('%s' % op.bytesProtoUsed)
        self.boxLPatchOpCnt.write('%s' % op.opCount)
        self.boxLPatchSaved.write('%s' % op.bytesSaved)
        self.ct.update()
    def catchThroughput(self, throughput):
        self.boxThroughput.write('%.01f' % throughput)
        self.ct.update()
    def catchFinished(self, *args):
        self.finishCount += 1
        self.boxFinishCount.write('%s' % self.finishCount)
        # i need to stuff these somewhere so they were not
        # called constantly from the filter function; it would
        # likely decrease the speed by a large amount
        self.boxAccepted.write('%s' % (self.acceptedCount))
        self.boxRejected.write('%s' % (self.rejectedCount))
        self.ct.update()
    def catchPatchReply(self, *args):
        pass
    def catchDateReply(self, *args):
        self.dateReplyCount += 1
        self.boxDateReply.write('%s' % self.dateReplyCount)
        self.ct.update()
    def catchSizeReply(self, *args):
        self.sizeReplyCount += 1
        self.boxSizeReply.write('%s' % self.sizeReplyCount)
        self.ct.update()
    def catchStart(self, *args):
        self.startCount += 1
        self.boxCurFile.write(args[1])
        self.boxStartCount.write('%s' % self.startCount)
        self.ct.update()
    def catchHashBad(self, *args):
        self.hashBadCount += 1
        self.boxHashBad.write('%s' % self.hashBadCount)
        rhash = args[4]
        lhash = args[5]
        rhash = '%s:%s' % (len(rhash), ''.join('{:02x}'.format(c) for c in rhash))
        lhash = '%s:%s' % (len(lhash), ''.join('{:02x}'.format(c) for c in lhash))
        self.boxLocalHash.write(lhash)
        self.boxRemoteHash.write(rhash)
        self.ct.update()
    def catchHashGood(self, *args):
        self.hashGoodCount += 1
        self.boxHashGood.write('%s' % self.hashGoodCount)
        self.ct.update()
    def catchBufferDump(self, *args):
        self.boxBufferSize.write('%s' % args[0])
        self.ct.update()
    def catchWrite(self, *args):
        # rfile, lfile, offset, size
        self.writeCount += 1
        self.bytesWrote += args[3]
        self.boxBytesWrote.write('%s' % self.bytesWrote)
        self.boxWriteCount.write('%s' % self.writeCount)
        self.boxLastWrite.write('%s' % args[1])
        self.ct.update()
    def catchUncaught(self, *args):
        pass

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

def main(ct, args):
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

    sw = Catcher(ct, filterFile, setopts.get('efilter-file', None), setopts.get('def-crypt', ',crypt.null'))

    '''
        A catch is basically a callback, but were are not really going to be
        performing work but rather displaying the status. You could technically
        control something from a catch, but is not yet implemented.
    '''
    catches = {
        'Finished':             sw.catchFinished,           # when file is finished
        'PatchReply':           sw.catchPatchReply,         # on hash/patch reply
        'HashBad':              sw.catchHashBad,            # if hash was bad
        'HashGood':             sw.catchHashGood,           # if hash was good
        'DateReply':            sw.catchDateReply,          # on date/time reply
        'SizeReply':            sw.catchSizeReply,          # on size eply
        'Start':                sw.catchStart,              # when file is started
        'Uncaught':             sw.catchUncaught,           # anything we dont catch
        'Write':                sw.catchWrite,              # when write happens
        'BufferDump':           sw.catchBufferDump,         # during buffer dumps
        'Throughput':           sw.catchThroughput,         # periodically
        'LongestPatchOp':       sw.catchLongestPatchOp,     # longest living patch operation
        'PatchFinish':          sw.catchPatchFinish,        # when patch operation finishes
        'Filter':               sw.catchFilter,             # called to filter a file or dir
    }

    if 'push' in setopts:
        print('push')
        lib.buops.Push(
            setopts['host'], setopts['port'], setopts['password'], setopts['lpath'],
            setopts['rpath'], filter, setopts['ssl'], setopts['sformat'], catches,
            efilters
        )
        return 
    if 'pull' in setopts:
        lib.buops.Pull(
            setopts['host'], setopts['port'], setopts['password'], setopts['lpath'],
            setopts['rpath'], filter, setopts['ssl'], setopts['sformat'], catches
        )
        return
    if 'sync-deleted-to-server' in setopts:
        lib.buops.SyncRemoteWithDeleted(
            setopts['host'], setopts['port'], setopts['password'], setopts['lpath'],
            setopts['rpath'], filter, setopts['stash'], setopts['ssl'], setopts['sformat'], catches
        )
        return
    if 'sync-deleted-to-local' in setopts:
        raise Exception('not implemented')
    return

# only execute this if we are the primary
# script file being executed by Python
if __name__ == '__main__':
    # set ourselves to idle unless specified to run as normal
    misc.setProcessPriorityIdle()
    # setup standard outputs (run TCP server)
    output.Init(output.Mode.TCPServer)
    crossterm.wrapper(main, sys.argv[1:])