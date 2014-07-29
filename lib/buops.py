'''
    Backup Operations
'''
import time
import os
import sys

from lib import output
from lib.client import Client
from lib.client import Client2
from lib.filter import Filter
from lib.pluginman import getPM

import lib.flycatcher as flycatcher
logger = flycatcher.getLogger('BuOps')

'''
    This is used to share state between the asynchronous sub-jobs
    of a patch operation. When a patch is started one or more sub
    jobs are created which then can at will end and create two more
    jobs in their place. I need a way to share state to build statistics
    and also better determine if they should split or continue.
'''
class PatchJobSharedState:
    def dec(self):
        self.opCount -= 1
        if self.opCount < 0:
            raise Exception('DEC TOO MANY TIMES')
    def inc(self):
        self.opCount += 1

def TruncateFile(lpath, size):
    if os.path.exists(lpath) is False:
        # get base path and ensure directory structure is created
        base = lpath[0:lpath.rfind(b'/')]
        if os.path.exists(base) is False:
            os.makedirs(base)
        
        fd = os.open(lpath, os.O_CREAT)
        os.close(fd)
    fd = os.open(lpath, os.O_RDWR)
    os.ftruncate(fd, size)
    os.close(fd)
    logger.debug('<trun>:%s' % lpath)

'''
    The CallCatchEx was created because I needed a way to hand back
    a default return value instead of None. I also needed to maintain
    backwards compatibility with existing code so I created this additional
    function.
'''
def CallCatch(catches, signal, *args):
    return CallCatchEx(catches, signal, None, *args)
def CallCatchEx(catches, signal, defret, *args):
    if catches is None:
        return defret
    if signal not in catches:
        if 'Uncaught' in catches:
            ret = catches['Uncaught'](*args)
            # if uncaught decided to return something
            # then let that be returned, but if it did
            # nothing then do not override the defret
            if ret is None:
                return defret
            # return what uncaught returned
            return ret
        return defret
    return catches[signal](*args)


def Pull(rhost, rport, sac, lpath, rpath = None, ssl = True, sformat = True, catches = None):
    if rpath is None:
        rpath = b'/'

    # the default metadata size
    metasize = 128

    sac = bytes(sac, 'utf8')
    c = Client2(rhost, rport, sac, sformat, metasize = metasize)
    print('connecting')
    c.Connect(essl = ssl)
    print('connected')

    rpbsz = len(rpath)
    
    jobFileTime = []
    jobFileSize = []
    jobDownload = []
    
    '''
        Transform each node into it's full remote path, then
        place it into the master node list for processing.
    '''
    def __eventDirEnum(pkg, result, vector):
        rpath = pkg[0]
        nodes = pkg[1]
        print('__eventDirEnum', rpath)
        if result is None:
            return
        for node in result:
            # skip any other revision but current
            if node[3] is not None:
                continue
            # grab the meta data and determine the encoding/encryption tag if any
            meta = node[2]
            if meta is not None:
                tag = meta[1:1+32].strip(b'\x00')
            else:
                tag = None
            # check that its not a special revision or system folder
            name = node[0]
            name = rpath + b'/' + name
            nodes.append((name, node[1], tag))
    def __eventFileTime(pkg, result, vector):
        jobFileTime.append((pkg, result))
    
    def __eventFileSize(pkg, result, vector):
        jobFileSize.append((pkg, result))
    
    def __eventFileRead(pkg, result, vector):
        success = result[0]
        if success != 1:
            # for now.. just let someone know shit screwed up.. if they
            # really need it to work they can come edit the code and skip
            # this and continue onward..
            raise Exception('Error On Read From Remote For [%s] At Offset [%x]' % (_lpath, _off))
            return
        data = result[1]
        _lpath = pkg[0]
        _off = pkg[1]
        _fo = pkg[2]
        _opcount = pkg[3]

        logger.debug('write:%s:%x' % (_lpath, _off))

        print('@@@@WRITE')
        _fo.write(_off, data)
        print('@@@@@')

        _opcount[0] -= 1

        '''
            The [0] is the current operation count and [1]
            is the init flag. If the init flag is True then
            the system is still creating pending requests 
            and therefore we should not terminate based on
            an operation count of zero.
        '''
        if _opcount[0] < 1 and _opcount[1] is False:
            # we are finished
            print('FINISH:%s' % _lpath)
            _fo.finish()

        # hey.. just keep on moving..
        #try:
        #    fd = open(_lpath, 'r+b')
        #    fd.seek(_off)
        #    fd.write(data)
        #    fd.close()
        #except Exception as e:
        #    print('exception writing to %s' % (_lpath))
        #    print(e)
        #    exit()
        
    echo = { 'echo': False }
        
    def __eventEcho(pkg, result, vector):
        pkg['echo'] = True
    
    # first enumerate the remote directory
    print('dirlist for "%s"' % rpath)
    _nodes = c.DirList(rpath, Client.IOMode.Block)
    
    nodes = []
    print('calling event')
    __eventDirEnum((rpath, nodes), _nodes, 0)
    
    sentEcho = False
    while echo['echo'] is False:
        c.handleOrSend()

        quecount = len(nodes) + len(jobFileTime) + len(jobFileSize) + len(jobDownload)
        if quecount == 0 and c.waitCount() == 0 and sentEcho is False:
            sentEcho = True
            c.Echo(Client.IOMode.Callback, (__eventEcho, echo))
        
        # iterate through files
        for x in range(0, min(100, len(nodes))):
            # might be faste to pop from end of list
            # but this will ensure more expected order
            # of operations..
            node = nodes.pop(0)

            _rpath = node[0]
            #_lpath = '%s/%s' % (lpath, node[0][rpbsz:].decode('utf8'))
            _lpath = lpath + b'/' + node[0][rpbsz:]
            # if directory issue enumerate call
            if node[1] == 1:
                print('requestingdirenum:%s' % _rpath)
                pkg = (_rpath, nodes)
                c.DirList(_rpath, Client.IOMode.Callback, (__eventDirEnum, pkg))
                continue
            # if file issue time check
            pkg = (_rpath, _lpath, node[2])
            c.FileTime(_rpath, Client.IOMode.Callback, (__eventFileTime, pkg))
        
        # iterate time responses
        for job in jobFileTime:
            _rpath = job[0][0]
            _lpath = job[0][1]
            _etag = job[0][2]       # etag from meta-data
            _rmtime = job[1]
            if os.path.exists(_lpath):
                stat = os.stat(_lpath)
                _lsize = stat.st_size
                _lmtime = stat.st_mtime
            else:
                _lsize = -1
                _lmtime = 0
                # create the local file (0 sized)
            # if newer then get file size so we can
            # truncate the local file
            if _rmtime >= _lmtime:
                logger.debug('date failed for %s with local:%s remote:%s' % (_lpath, _lmtime, _rmtime))
                pkg = (_rpath, _lpath, _lsize, _etag)
                print('<request-time>:%s' % _lpath)
                c.FileSize(_rpath, Client.IOMode.Callback, (__eventFileSize, pkg))
        jobFileTime = []
        
        # iterate size responses
        for job in jobFileSize:
            _rpath = job[0][0]
            _lpath = job[0][1]
            _lsize = job[0][2]
            _etag = job[0][3]
            _rsize = job[1]
            # if size different truncate local file to match
            if _rsize[0] != 1:
                raise Exception('_rsize for %s failed' % _rpath)
            logger.debug('[size] %s lsize:%s rsize:%s' % (_lpath, _lsize, _rsize))
            _rsize = _rsize[1]
            if _lsize != _rsize:
                # truncate local file
                TruncateFile(_lpath, _rsize)
            # queue a download operation
            pkg = [_rpath, _lpath, _rsize, 0, _etag]
            jobDownload.append(pkg)
        jobFileSize = []
        
        # iterate download operations
        tr = []
        chunksize = 1024 * 1024 * 4     # default to 4MB chunk
        for job in jobDownload:
            _rpath = job[0]
            _lpath = job[1]
            _rsize = job[2]
            _curoff = job[3]
            _etag = job[4]

            '''
                We are going to download this file. We know the etag which is
                used by modification plugins to alter the file for encryption
                or compression for example. So we need to try to match the tag
                back with the plugin and the options for it. Then create a 
                write object so as it is written it is unmodified back to it's
                original form.
            '''
            if len(job) < 6:
                _etag = _etag.decode('utf8', 'ignore')
                _, _plugid, _plugopts = CallCatchEx(catches, 'DecryptByTag', (None, None, None), _etag)

                if _ is None and _etag is not None and len(_etag) > 0:
                    # well, we apparently have no entry for this file so we
                    # need to alert the user or the calling code that there
                    # is a problem that needs to be addressed
                    raise Exception('Tag specified as "%s" but no plugin found.' % _etag)

                if _ is None:
                    # just use the null plugin
                    _ = None
                    _plugid = 'crypt.null'
                    _plugopts = (None, [])

                print('etag:%s _:%s plugid:%s plugopts:%s' % (_etag, _, _plugid, _plugopts))
                plug = getPM().getPluginInstance(_plugid, _etag, (None, _plugopts,))
                _fo = plug.beginwrite(_lpath)
                job.append(_fo)
                _opcount = [0, True]
                job.append(_opcount)
            else:
                _fo = job[5]
                _opcount = job[6]

            # increment operation count
            _opcount[0] += 1

            # determine amount we can read and choose maximum
            _rem = _rsize - _curoff
            rsz = min(_rem, chunksize)
            pkg = (_lpath, _curoff, _fo, _opcount)
            # this should *not* read messages and execute callbacks, because
            # if it does then technically it could call the callback before
            # we have set the init flag to False meaning the file never gets
            # closed
            c.FileRead(_rpath, _curoff, rsz, Client.IOMode.Callback, (__eventFileRead, pkg))
            if _curoff + rsz >= _rsize:
                tr.append(job)
                logger.debug('finish:%s' % (_lpath))
                # set the init flag to False so the callback
                # code knows when the count reaches zero that
                # the file is done
                _opcount[1] = False
                continue
            job[3] = _curoff + rsz
        # remove completed jobs
        for t in tr:
            jobDownload.remove(t)
        # <end-of-loop>
'''
    PUSH
'''
def Push(rhost, rport, sac, lpath, rpath = None, ssl = True, sformat = True, catches = None):
    if rpath is None:
        rpath = b'/'

    metasize = 128

    sac = bytes(sac, 'utf8')
    c = Client2(rhost, rport, sac, sformat, metasize = metasize)
    c.Connect(essl = ssl)

    # produce remote and local paths
    lpbsz = len(lpath)

    #logger.debug('test')
    #print('testing')
    #c.FileTrun(b'/grape', 5, mode = Client.IOMode.Block)
    #c.FileWrite(b'/grape', 0, b'hello', mode = Client.IOMode.Block)
    #print('read', c.FileRead(b'/grape', 0, 5, mode = Client.IOMode.Block))
    #print('hash', c.FileHash(b'/grape', 0, 5, mode = Client.IOMode.Block))
    #_lhash = b'hello'
    #_lhash = c.HashKmc(_lhash, 128)
    #print('local-hash', _lhash)
    #sys.stdout.flush()
    #exit()

    # encryption plugin instances of options
    eplugs = {}
    
    jobDirEnum = []              # to be enumerated
    jobPendingFiles = []         # files pending processing
    jobGetRemoteSize = []        # 
    jobGetModifiedDate = []      #
    jobPatch = []                # patch jobs 
    jobPatchQueryDelayed = []    # delayed patch hash requests
    jobUpload = []               # upload jobs

    jobPatchOperations = []

    def getJobCount():
        return len(jobDirEnum) + len(jobPendingFiles) + len(jobGetRemoteSize) + \
               len(jobGetModifiedDate) + len(jobPatch) + len(jobPatchQueryDelayed) + \
               len(jobUpload)

    jobDirEnum.append(lpath)

    maxque = 2

    echo = { 'echo': False }
    sentEcho = False

    '''
        These turn the async polling model into a async callback model, at
        least to some extent. We still poll but we do not poll individual
        objects which reduces polling time (CPU burn)..
    '''
    def __eventFileSize(pkg, result, vector):
        jobGetRemoteSize.append((pkg, result))
    def __eventFileTime(pkg, result, vector):
        jobGetModifiedDate.append((pkg, result)) 
    def __eventEcho(pkg, result, vector):
        logger.debug('ECHO')
        print('GOT ECHO')
        pkg['echo'] = True
    def __eventFileWrite(pkg, result, vector):
        if result == 0:
            raise Exception('WRITE FAILED')
    def __eventHashReply(pkg, result, vector):
        # hash local file now and compare
        _success = result[0]
        _rhash = result[1]
        _rpath = pkg[0]
        _lpath = pkg[1]
        _rsize = pkg[2]
        _lsize = pkg[3]
        _offset = pkg[4]
        _size = pkg[5]
        _shrstate = pkg[6]
        _fo = pkg[7]

        if _success == 0:
            print('HASH-ERROR:%s' % _rpath)
            exit()
            return

        _data = _fo.read(_offset, _size)
        _lhash = _fo.read(_offset, _size)
        #fd = open(_lpath, 'rb')
        #fd.seek(_offset)
        #_data = fd.read(_size)
        #fd.seek(_offset)
        #_lhash = fd.read(_size)
        #fd.close()

        # function is BAD because it modifies an immutable object, if the
        # call is pure python then it returns a new bytes object but if
        # the call is to C library then it modifies it in place - this is
        # why i assigned the return value so it works for both pure python
        # and an native library call but i need to fix this shit very soon,
        # also its eating precious CPU with the double call above if its
        # using an encryption plugin
        _lhash = c.HashKmc(_lhash, 128)

        if _size < 0:
            print('_size LESS THAN ZERO!?!?!')

        # if we have used more bytes than the file's actual size then we are
        # basically just wasting bandwidth and should immediantly force all
        # remaining operations to perform a write to turn this into an upload
        if _shrstate.bytesProtoUsed > (_shrstate.firstSize * 0.5) - _shrstate.bytesPatched:
            logger.debug('FORCEDPATCH:%s:%x:%x' % (_lpath, _offset, _size))
            _shrstate.bytesPatched += len(_data)
            c.FileWrite(_rpath, _offset, _data, Client.IOMode.Discard)
            logger.debug('hash; [%s] minus one' % id(_shrstate))
            _shrstate.dec()
            if _shrstate.opCount < 1:
                CallCatch(catches, 'Finish', _rpath, _lpath, _offset, _size)
                CallCatch(catches, 'PatchFinish', _shrstate)
                _fo.finish()
            return

        # if the hashes are the same do nothing
        if _lhash != _rhash:
            CallCatch(catches, 'HashBad', _rpath, _lpath, _offset, _size, _rhash, _lhash)
            # let us decide if it is worth breaking down futher
            # or we should just cut our loses and force a patch

            # this section of the remote file is different so,
            # now we must decide to either patch this section 
            # or continue breaking it down further in hopes that
            # we find where it differs -- we could end up spending
            # more bandwidth on 
            #
            logger.debug('hash-bad:%s:%x:%x\n' % (_lpath, _offset, _size))
            # limit the minimum size of a hash
            if _size > 1024 * 1024 * 4:
                # we have not decremented for this operation and we are
                # going to create two new (but we are going to die) so
                # only increment it by one
                logger.debug('hash; [%s] plus one' % id(_shrstate))
                _shrstate.inc()
                _nsz = int(_size / 2)
                if _size % 2 == 0:
                    _aoff = int(_offset + _nsz)
                    _alen = _nsz
                    _boff = _offset
                    _blen = _nsz
                else:
                    _aoff = int(_offset + _nsz)
                    _alen = _nsz
                    _boff = _offset
                    # adjust by one since we had odd number of bytes
                    _blen = _nsz + 1
                # start the queries
                logger.debug('patching-split:%s:%x:%x (a:%x:%x) (b:%x:%x)' % (_lpath, _offset, _size, _aoff, _alen, _boff, _blen))
                # either execute it or delay it
                subjob = [_rpath, _lpath, _rsize, _lsize, _aoff, _alen, _shrstate, _fo]
                jobPatchQueryDelayed.append((_rpath, _aoff, _alen, subjob))

                subjob = [_rpath, _lpath, _rsize, _lsize, _boff, _blen, _shrstate, _fo]
                jobPatchQueryDelayed.append((_rpath, _boff, _blen, subjob))

                # just an estimate of how much we are about to use
                _shrstate.bytesProtoUsed += 128 + (8 * 2 + 32) * 2
                return

            # just upload this section..
            CallCatch(catches, 'Write', _rpath, _lpath, _offset, _size)
            _shrstate.bytesPatched += _size

            logger.debug('patching-section:%s:%x:%x' % (_lpath, _offset, _size))
            c.FileWrite(_rpath, _offset, _data, Client.IOMode.Callback, (__eventFileWrite, None))
        else:
            # track how many bytes we saved!
            _shrstate.bytesSaved += _size
            CallCatch(catches, 'HashGood', _rpath, _lpath, _offset, _size)
            logger.debug('patching-match:%s:%x:%x' % (_lpath, _offset, _size))
        # decrement since we just died and spawned no sub-hash jobs
        logger.debug('hash; [%s] minus one' % id(_shrstate))
        _shrstate.dec()
        if _shrstate.opCount < 1:
            # set the time to the current time to keep it from being check every
            # time by way of hashing
            ct = time.time()
            c.FileSetTime(_rpath, int(ct), int(ct), Client.IOMode.Discard)
            CallCatch(catches, 'Finish', _rpath, _lpath, _offset, _size)
            CallCatch(catches, 'PatchFinish', _shrstate)
            _fo.finish()
    
    # statistics
    databytesout = 0
    stat_uptodate = 0
    stat_uploaded = 0
    stat_patched = 0
    stat_checked = 0
    
    dd = time.time()
    
    # the soft limit for application level buffer size
    buflimit = 1024 * 1024 * 4

    # keep going until we get the echo 
    while echo['echo'] is False:
        # read any messages
        c.handleOrSend()

        # update our throughput
        CallCatch(catches, 'Throughput', c.getThroughput())

        ########################################################
        ##################### LIMITERS #########################
        ########################################################
        #
        # This section sets and adjusts the limits which directly
        # effect memory consumption mainly, and also help to finish
        # things before starting new things. I placed everything
        # into a central location to make it easier to adjust stuff
        # because you can look at everything as a whole.
        #
        #    JOB-DIR-ENUM
        if len(jobPendingFiles) < 1000:
            # only produce more pending files when low
            jobDirEnumLimit = min(500, len(jobDirEnum))
        else:
            jobDirEnumLimit = 0
        #    JOB-PENDING-FILES
        # do not process any new files unless we have no patch operations
        # and no more than 19 upload operations.. otherwise we start spreading
        # things out and nothing really gets completely done
        if c.waitCount() < 500 and len(jobPatchOperations) == 0 and len(jobUpload) < 20:
            # only throw files into pipeline when wait count is low
            jobPendingFilesLimit = min(500, len(jobPendingFiles))
        else:
            jobPendingFilesLimit = 0
        #    JOB-PATCH-QUERY-DELAYED
        # always process delayed patch queries
        jobPatchQueryDelayedLimit = min(2, len(jobPatchQueryDelayed))
        #    JOB-PATCH
        # always process patch jobs
        jobPatchLimit = min(2, len(jobPatch))
        #########################################################
        
        # if our output buffer is empty, we have no jobs, and we are not 
        # waiting on any requests
        if c.getBytesToSend() < 1 and getJobCount() < 1 and c.waitCount() < 1 and sentEcho is False:
            sentEcho = True
            c.Echo(Client.IOMode.Callback, (__eventEcho, echo))
        
        # if we let this continue to grow it could eventually consume all
        # physical memory so we limit it and once it reaches that soft
        # limit it will empty our buffers completely
        boutbuf = c.getBytesToSend()
        if boutbuf > buflimit:
            logger.debug('emptying outbound buffer..')
            # i decided not to force the buffer to completely drain
            # in hopes that if we didnt it would be easier to keep
            # the server working - the more time the server is idle
            # is lost work time
            while c.getBytesToSend() > 1024 * 1024:
                #              STALL/NET-DEADLOCK PREVENTION
                # this will still cause callbacks to be fired and async results
                # to be stored at the same time it will send any data from our
                # application level buffers, which is desired - if we only sent
                # pending data and never read the server's outgoing buffer would
                # fill up because our incoming would fill up these creating a 
                # data lock because we could never send from our buffer because
                # the remote side could not read because it can not write
                c.handleOrSend()

                CallCatch(catches, 'BufferDump', c.getBytesToSend())
                CallCatch(catches, 'Throughput', c.getThroughput())
                time.sleep(0.01)
        else:
            # just send what we can right now
            c.send()

        #
        # JOB-DIR-ENUM
        #
        # DESCRIPTION:
        #       this fills the pending files list; we limit it because if
        #       we do not it could overwhelm physical memory on the machine
        #       so we only produce more when there is room to do so
        x = -1
        for x in range(0, jobDirEnumLimit):
            dej = jobDirEnum[x] 
            nodes = os.listdir(dej)

            for node in nodes:
                print(node, dej)
                _lpath = b'/'.join((dej, node))
                if os.path.isdir(_lpath):
                    # delay this..
                    print('checking dir', node)
                    res = CallCatch(catches, 'Filter', _lpath, node, True)
                    if res or res is None:
                        print('    accepted')
                        jobDirEnum.append(_lpath)
                    continue
                print('checking file', node)
                res = CallCatch(catches, 'Filter', _lpath, node, False)
                if res or res is None:
                    jobPendingFiles.append(_lpath)
                    print('    accepted')
        # drop what we completed
        jobDirEnum = jobDirEnum[x + 1:]

        #
        # JOB-PATCH-QUERY-DELAYED
        #
        # DESCRIPTION:
        #       this happens first because while we wish to work on multiple
        #       files at once we also wish to finish up in progress operations
        #       so in order to do that we first service pending hash requests
        #       which come from hash operations that get delayed because there
        #       was too many outstanding requests; our code path for hashing
        #       can cause physical memory to be overwhelmed if not limited and
        #       thus that is what this is doing - holding patch operations until
        #       our queue count is under the limit.
        x = -1
        for x in range(0, jobPatchQueryDelayedLimit):
            job = jobPatchQueryDelayed[x]
            _rpath = job[0]
            _off = job[1]
            _size = job[2]
            subjob = job[3]
            v = c.FileHash(_rpath, _off, _size, Client.IOMode.Callback, (__eventHashReply, subjob))

        # drop the ones we executed
        jobPatchQueryDelayed = jobPatchQueryDelayed[x + 1:]

        #
        # JOB-PATCH
        #
        # DESCRIPTION:
        #       this will issue new hash requests which starting the patching
        #       process only if the queue is below a certain number of items
        #       which helps keep the memory consumption limited because these
        #       can get out of hand fast if you have a multi-GB file or even
        #       a TB can create one million requests which is a lot
        # LOCATION:
        #       this happens before any new files are placed into the queues
        #       so we can finish our patch jobs before moving on the to next
        #       file

        tr = []
        hv = 0
        he = None
        for op in jobPatchOperations:
            if op.opCount < 1 and op.init is False:
                # this operation has finished
                tr.append(op)
                continue
            # report the longest lived
            if time.time() - op.startTime > hv:
                hv = time.time() - op.startTime
                he = op
        if he is not None:
            CallCatch(catches, 'LongestPatchOp', he)

        for t in tr:
            jobPatchOperations.remove(t)

        x = 0
        while x < jobPatchLimit:
            job = jobPatch[x]
            _rpath = job[0]
            _lpath = job[1]
            _rsize = job[2]
            _lsize = job[3]
            _curoff = job[4]
            # make sure to create the shared state container
            if len(job) < 6:
                shrstate = PatchJobSharedState()
                shrstate.firstOffset = _curoff
                shrstate.firstSize = _lsize
                shrstate.bytesProtoUsed = 0
                shrstate.bytesPatched = 0
                shrstate.bytesSaved = 0
                shrstate.opCount = 0
                shrstate.startTime = time.time()
                shrstate.lpath = _lpath
                shrstate.rpath = _rpath
                shrstate.init = True
                job.append(shrstate)
                jobPatchOperations.append(shrstate)
                '''
                    This _fo object replaces the old code that used to open a file. The _fo
                    is short for file object. It provides the functionality of reading and
                    writing to a file except the implementation can do additional things.

                    See ./plugins/ and especially ./plugins/crypt for examples of the 
                    implementation of this.
                '''
                tag, plugid, plugopts = CallCatchEx(catches, 'EncryptFilter', ('', None), _lpath, _lpath[_lpath.rfind(b'/') + 1:], False)
                if plugid is None:
                    # if none specified then default to null
                    plug = getPM().getPluginInstance('crypt.null', '', (c, []))
                    tag = ''
                else:
                    plug = getPM().getPluginInstance(plugid, tag, plugopts)
                _fo = plug.beginread(_lpath)
                job.append(_fo)
                # make sure the correct metadata type/version (VERSION 1) byte is written
                c.FileWriteMeta(_rpath, 0, b'\xAA', Client.IOMode.Discard)
                # write in the encryption tag (for automated reversal using encryption filter file)
                btag = bytes(tag, 'utf8')
                if len(btag) > 32:
                    raise Exception('The encryption tag "%s" is longer than 32 bytes!' % tag)
                c.FileWriteMeta(_rpath, 1, btag.ljust(32, b'\x00'), Client.IOMode.Discard)
            else:
                # get existing shared state container
                shrstate = job[5]
                _fo = job[6]

            # hash 32MB chunks (server is threaded so it should be okay)
            csz = 1024 * 1024 * 32
            # get actual size due to what we have remaining of the file
            _tsz = min(csz, _lsize - _curoff)

            # increment number of operations ongoing
            shrstate.inc()

            # create job and request with callback
            subjob = [_rpath, _lpath, _rsize, _lsize, _curoff, _tsz, shrstate, _fo]
            c.FileHash(_rpath, _curoff, _tsz, Client.IOMode.Callback, (__eventHashReply, subjob))

            # determine and track if we are finished
            job[4] = job[4] + _tsz
            if job[4] >= _lsize:
                # do not increment x after removing it; this
                # feels kind of hacky but it does work right
                # now at least but i think its on the edge
                # of being bad code
                shrstate.init = False
                del jobPatch[x]
                jobPatchLimit = jobPatchLimit - 1
                continue

            # increment x since we did not remove anything
            x = x = 1

        #
        #  JOB-PENDING-FILES
        #
        # DESCRIPTION:
        #       This takes pending files created by enumeration of local directories,
        #       and starts processin by first issuing a file size request to determine
        #       if the file exist and if it is the correct size.
        x = -1
        for x in range(0, jobPendingFilesLimit):
            _lpath = jobPendingFiles[x]
            ##### DEBUG (NO FILES GREATER THAN 200MB) #####
            stat = os.stat(_lpath)
            _lsize = stat.st_size
            if _lsize > 1024 * 1024 * 200:
                continue
            ###############################################

            '''
                We have to get the modified size of the local file
                since we will be comparing this to the remote. For
                the NULL modification plugin it will be exactly the
                same, but for others it will be different. So we do
                that here. The plugin instance is cached by the plugin
                manager (PM).
            '''
            tag, plug, plugopts = CallCatchEx(catches, 'EncryptFilter', (None, None, None), _lpath, _lpath[_lpath.rfind(b'/') + 1:], False)
            print('encryptfilter returned tag:%s plugid:%s plugopts:%s' % (tag, plug, plugopts))
            if tag is None:
                # if none specified then default to null
                plug = getPM().getPluginInstance('crypt.null', '', (c, []))

            if plug is None:
                raise Exception('Apparently, we are missing a plugin referenced by "%s".' % plugid)

            _esize = plug.getencryptedsize(_lpath)
            print('_lpath:%s _esize:%s _lsize:%s' % (_lpath, _esize, _lsize))
            _lsize = _esize

            _rpath = rpath + _lpath[lpbsz:]
            stat_checked = stat_checked + 1
            pkg = (_rpath, _lpath, _lsize, None, int(stat.st_mtime))
            CallCatch(catches, 'Start', _rpath, _lpath)
            c.FileSize(_rpath, Client.IOMode.Callback, (__eventFileSize, pkg))
        # drop what we completed
        jobPendingFiles = jobPendingFiles[x + 1:]

        ########################################################
        ############## NO LIMIT SECTIONS BELOW #################
        ########################################################

        #
        # JOB-GET-REMOTE-SIZE
        #
        for rsj in jobGetRemoteSize:
            pkg = rsj[0]
            _result = rsj[1]
            _rpath = pkg[0]
            _lpath = pkg[1]
            _lsize = pkg[2]
            _vector = pkg[3]
            _lmtime = pkg[4]

            CallCatch(catches, 'SizeReply', _rpath, _lpath)

            # result[0] = success code is non-zero and result[1] = size (0 on failure code)
            _rsize = _result[1]
            if _lsize == _rsize and _result[0] == 1:
                # need to check modified date
                pkg = (_rpath, _lpath, _rsize, _lsize, _vector, _lmtime)
                c.FileTime(_rpath, Client.IOMode.Callback, (__eventFileTime, pkg))
            else:
                # first make the remote size match the local size
                print('truncate; rpath:%s lsize:%s rsize:%s' % (_rpath, _lsize, _rsize))
                c.FileTrun(_rpath, _lsize, Client.IOMode.Discard)
                if max(_rsize, _lsize) < 1:
                    CallCatch(catches, 'Finished')
                    continue
                # need to decide if we want to upload or patch
                if min(_rsize, _lsize) / max(_rsize, _lsize) < 0.5:
                    # make upload job
                    logger.debug('<upload>:%s' % _lpath)
                    jobUpload.append([_rpath, _lpath, _rsize, _lsize, 0])
                else:
                    # make patch job
                    jobPatch.append([_rpath, _lpath, _rsize, _lsize, 0])
        jobGetRemoteSize = []

        #
        # JOB-GET-MODIFIED-DATE
        #
        for rtj in jobGetModifiedDate:
            pkg = rtj[0]
            _rmtime = rtj[1]
            _rpath = pkg[0]
            _lpath = pkg[1]
            _rsize = pkg[2]
            _lsize = pkg[3]
            _vector = pkg[4]
            _lmtime = pkg[5]

            CallCatch(catches, 'DateReply', _rpath, _lpath)

            if _rmtime < _lmtime:
                # need to decide if we want to upload or patch
                if min(_rsize, _lsize) / (max(_rsize, _lsize) + 1) < 0.5:
                    # make upload job
                    jobUpload.append([_rpath, _lpath, _rsize, _lsize, 0])
                else:
                    # make patch job
                    jobPatch.append([_rpath, _lpath, _rsize, _lsize, 0])
            else:
                # just drop it since its either up to date or newer
                CallCatch(catches, 'Finished')
                stat_uptodate = stat_uptodate + 1
                continue
        jobGetModifiedDate = [] 

        # 
        # JOB-UPLOAD
        #
        tr = []
        cjc = 0
        for uj in jobUpload:
            _rpath = uj[0]
            _lpath = uj[1]
            _rsize = uj[2]
            _lsize = uj[3]
            _curoff = uj[4]

            '''
                Here we have to determine what modification plugin to use
                and then get an instance of it, and use that instance to
                do read operations instead of directly on the file.
            '''
            if len(uj) < 6:
                tag, plug, plutopts = CallCatchEx(catches, 'EncryptFilter', (None, None, None), _lpath, _lpath[_lpath.rfind(b'/') + 1:], False)
                if plug is None:
                    # if none specified then default to null
                    plug = getPM().getPluginInstance('crypt.null', '', (c, []))
                    tag = ''
                print('$$$$$$$$$$$$$$$')
                _fo = plug.beginread(_lpath)
                print('$$$$$$$$$$$$$$$')
                uj.append(_fo)
                # make sure the correct metadata type/version (VERSION 1) byte is written
                c.FileWriteMeta(_rpath, 0, b'\xAA', Client.IOMode.Discard)
                # write in the encryption tag (for automated reversal using encryption filter file)
                btag = bytes(tag, 'utf8')
                if len(btag) > 32:
                    raise Exception('The encryption tag "%s" is longer than 32 bytes!' % tag)
                c.FileWriteMeta(_rpath, 1, btag.ljust(32, b'\x00'), Client.IOMode.Discard)
            else:
                _fo = uj[5]
            '''
                At this point we have the modification plugin instance
                read object and we are treating it like a normal file.
            '''
            _chunksize = 1024 * 1024 * 4
            # see what we can send
            _rem = min(_lsize - _curoff, _chunksize)
            # open local file and read chunk
            #_fd = open(_lpath, 'rb')
            #_fd.seek(_curoff)
            #_data = _fd.read(_rem)
            #_fd.close()


            print('uploading _lpath:%s _curoff:%s _rem:%s' % (_lpath, _curoff, _rem))
            _data = _fo.read(_curoff, _rem)

            # if no more data then stop and terminate this job
            if not _data:
                tr.append(uj)
                continue

            CallCatch(catches, 'Write', _rpath, _lpath, _curoff, _chunksize)

            c.FileWrite(_rpath, _curoff, _data, Client.IOMode.Discard)
            # advance our current offset
            uj[4] = _curoff + len(_data)

            # (UNUSED) -- old code not we check if _data is empty
            # if we reached the EOF then drop it
            if uj[4] >= _lsize:
                tr.append(uj)
            
            # keep accounting for the bytes sent for statistics
            databytesout = databytesout + len(_data)

            # dont overfill our buffers just exit
            if c.getBytesToSend() > buflimit:
                break

            # keep track of number of jobs processed (i think old code)
            cjc = cjc + 1

        # remove finished jobs
        ct = time.time()
        for uj in tr:
            CallCatch(catches, 'Finish', uj[0], uj[1])
            # set the modified time on the file to the current
            # time to represent it is up to date
            _rpath = uj[0]
            c.FileSetTime(_rpath, int(ct), int(ct), Client.IOMode.Discard)
            jobUpload.remove(uj)
            stat_uploaded = stat_uploaded + 1
        continue
    c.close()
    # we are done!
    return

def SyncLocalWithDeleted(rhost, rport, sac, lpath, rpath = None, ssl = True):
    if rpath is None:
        rpath = b'/'

    sac = bytes(sac, 'utf8')
    c = Client2(rhost, rport, sac, False)
    c.Connect(essl = ssl)

    pfiles = []         # pending files
    pdirs = []          # pending directories

    def _eventFileSize(pkg, result, vector):
        if result[0] == 0:
            # delete local file
            os.remove(pkg[0])

    while True:
        c.handleOrSend()

        pc = c.waitCount() + len(pfiles) + len(pdirs)

        if pc < 1:
            break

        for pdir in pdirs:
            nodes = os.listdir(pdir)

            # enumerate directories and files
            for node in nodes:
                fullpath = pdir + b'/' + node
                # decide if directory or file
                if os.path.isdir(fullpath):
                    pdirs.append(fullpath)
                else:
                    pfiles.append(fullpath)

            # 
            for pfile in pfiles:
                # check if file exists remotely
                pkg = (pfile,)
                c.FileSize(pfile, mode = Client.IOMode.Callback, callback = (_eventFileSize, pkg))
    return


def SyncRemoteWithDeleted(rhost, rport, sac, lpath, rpath = None, ssl = True):
    if rpath is None:
        rpath = b'/'

    sac = bytes(sac, 'utf8')
    c = Client2(rhost, rport, sac, True)
    c.Connect(essl = ssl)

    # used to chop rpath to produce relative which can be affixed to lpath
    rpsz = len(rpath)

    #result = c.DirList(rpath, Client.IOMode.Block)

    penddirenums = []               # pending directories to be enumerated
    pendfiles = []                  # pending files to be checked

    penddirenums.append(rpath)      

    # handle results from directory enumerations
    def _eventDirEnum(pkg, result, vector):
        _rpath = pkg[0]
        # place enumeration as full path nodes
        for node in result:
            # create full path
            fullpath = _rpath + b'/' + node[0]
            # determine if directory and file then
            # place in appropriate pending que
            if node[1] == 1:
                # directory
                penddirenums.append(fullpath)
            else:
                pendfiles.append(fullpath)

    while True:
        c.handleOrSend()

        pc = c.waitCount() + len(penddirenums) + len(pendfiles)

        if pc < 1:
            break

        # enumerate remote directories
        for prepath in penddirenums:
            pkg = (prepath,)
            c.DirList(prepath, mode = Client.IOMode.Callback, callback = (_eventDirEnum, pkg))
        penddirenums = []

        # check if file exists locally
        for _rpath in pendfiles:
            relrpath = _rpath[rpsz:]
            if os.path.exists(lpath + b'/' + relrpath) is False:
                # delete the file from the remote
                print('deleting', _rpath)
                c.FileDel(_rpath, mode = Client.IOMode.Discard)
        pendfiles = []

    exit()
    # done
    return






