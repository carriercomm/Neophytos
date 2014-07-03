'''
    Backup Operations
'''
import time
import os
import sys

from lib import output
from lib.client import Client
from lib.client import Client2

def TruncateFile(lpath, size):
    if os.path.exists(lpath) is False:
        # get base path and ensure directory structure is created
        base = lpath[0:lpath.rfind('/')]
        if os.path.exists(base) is False:
            os.makedirs(base)
        
        fd = os.open(lpath, os.O_CREAT)
        os.close(fd)
    fd = os.open(lpath, os.O_RDWR)
    os.ftruncate(fd, size)
    os.close(fd)
    print('<trun>:%s' % lpath)

def Pull(rhost, rport, sac, lpath, rpath = None, filter = None, ssl = True, sformat = True):
    if rpath is None:
        rpath = b'/'

    sac = bytes(sac, 'utf8')
    c = Client2(rhost, rport, sac, sformat)
    c.Connect(essl = ssl)

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
        if result is None:
            return
        for node in result:
            name = node[0]
            
            # stash format is handled special
            if sformat:
                rev = name[0:name.find(b'.')].decode('utf8')
                if int(rev) != 0:
                    continue
                name = name[name.find(b'.') + 1:]

            name = rpath + b'/' + name
            nodes.append((name, node[1]))
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
        print('write:%s:%x' % (_lpath, _off))
        # hey.. just keep on moving..
        try:
            fd = open(_lpath, 'r+b')
            fd.seek(_off)
            fd.write(data)
            fd.close()
        except Exception as e:
            print('exception writing to %s' % (_lpath))
            print(e)
            exit()
        
    echo = { 'echo': False }
        
    def __eventEcho(pkg, result, vector):
        pkg['echo'] = True
    
    # first enumerate the remote directory
    _nodes = c.DirList(rpath, Client.IOMode.Block)
    
    nodes = []
    __eventDirEnum((rpath, nodes), _nodes, 0)
    
    sentEcho = False
    while echo['echo'] is False:
        c.HandleMessages(0, None)

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
            _lpath = '%s/%s' % (lpath,node[0][rpbsz:].decode('utf8'))
            # if directory issue enumerate call
            if node[1] == 1:
                print('requestingdirenum', _rpath)
                pkg = (_rpath, nodes)
                c.DirList(_rpath, Client.IOMode.Callback, (__eventDirEnum, pkg))
                continue
            # if file issue time check
            pkg = (_rpath, _lpath)
            c.FileTime(_rpath, Client.IOMode.Callback, (__eventFileTime, pkg))
        
        # iterate time responses
        for job in jobFileTime:
            _rpath = job[0][0]
            _lpath = job[0][1]
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
                print('date failed for %s with local:%s remote:%s' % (_lpath, _lmtime, _rmtime))
                pkg = (_rpath, _lpath, _lsize)
                c.FileSize(_rpath, Client.IOMode.Callback, (__eventFileSize, pkg))
        jobFileTime = []
        
        # iterate size responses
        for job in jobFileSize:
            _rpath = job[0][0]
            _lpath = job[0][1]
            _lsize = job[0][2]
            _rsize = job[1]
            # if size different truncate local file to match
            if _rsize[0] != 1:
                raise Exception('_rsize for %s failed' % _rpath)
            print('[size] %s lsize:%s rsize:%s' % (_lpath, _lsize, _rsize))
            _rsize = _rsize[1]
            if _lsize != _rsize:
                # truncate local file
                TruncateFile(_lpath, _rsize)
            # queue a download operation
            pkg = [_rpath, _lpath, _rsize, 0]
            jobDownload.append(pkg)
        jobFileSize = []
        
        # iterate download operations
        tr = []
        chunksize = 1024 * 1024 * 4
        for job in jobDownload:
            _rpath = job[0]
            _lpath = job[1]
            _rsize = job[2]
            _curoff = job[3]
            # determine amount we can read and choose maximum
            _rem = _rsize - _curoff
            if _rem > chunksize:
                _rem = chunksize
            #print('read', _rpath, _rem, _curoff, _rsize)
            pkg = (_lpath, _curoff)
            c.FileRead(_rpath, _curoff, chunksize, Client.IOMode.Callback, (__eventFileRead, pkg))
            if _curoff + _rem >= _rsize:
                tr.append(job)
                print('finish:%s' % (_lpath))
            job[3] = _curoff + _rem
        # remove completed jobs
        for t in tr:
            jobDownload.remove(t)
        # <end-of-loop>

def Push(rhost, rport, sac, lpath, rpath = None, filter = None, ssl = True, sformat = True):
    if rpath is None:
        rpath = b'/'
    else:
        rpath = bytes(rpath, 'utf8')

    sac = bytes(sac, 'utf8')
    c = Client2(rhost, rport, sac, sformat)
    c.Connect(essl = ssl)
    # produce remote and local paths
    lpbsz = len(lpath)
    
    jobDirEnum = []              # to be enumerated
    jobPendingFiles = []         # files pending processing
    jobGetRemoteSize = []        # 
    jobGetModifiedDate = []      #
    jobPatch = []                # patch jobs 
    jobPatchQueryDelayed = []    # delayed patch hash requests
    jobUpload = []               # upload jobs
    
    jobDirEnum.append(lpath)

    echo = { 'echo': False }
    sentEcho = False

    def getQueCount():
        return c.waitCount() + len(jobGetRemoteSize) + len(jobGetModifiedDate) + len(jobPatch) + len(jobUpload)
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
        print('ECHO ECHO')
        pkg['echo'] = True
    def __eventHashReply(pkg, result, vector):
        # hash local file now and compare
        _success = result[0]
        _rhash = result[1]
        _rpath = pkg[0]
        _lpath = pkg[1]
        _size = pkg[3]
        _offset = pkg[4]
        _size = pkg[5]
        _osize = pkg[6]
        _depth = pkg[7]
        fd = open(_lpath, 'rb')
        fd.seek(_offset)
        _data = fd.read(_size)
        _lhash = c.HashKmc(_data, 128)
        fd.close()

        # if the hashes are the same do nothing
        if _lhash != _rhash:
            # this section of the remote file is different so,
            # now we must decide to either patch this section 
            # or continue breaking it down further in hopes that
            # we find where it differs -- we could end up spending
            # more bandwidth on 
            #

            # limit the minimum size of a hash
            if _size > 1024 * 1024:
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
                print('patching-split:%s:%x:%x (a:%x:%x) (b:%x:%x)' % (_lpath, _offset, _size, _aoff, _alen, _boff, _blen))
                # either execute it or delay it
                subjob = [_rpath, _lpath, _rsize, _lsize, _aoff, _alen, _osize, _depth + 1]
                if getQueCount() > 100:
                    jobPatchQueryDelayed.append((_rpath, _aoff, _alen, subjob))
                else:
                    c.FileHash(_rpath, _aoff, _alen, (__eventHashReply, subjob))
                # either execute it or delay it
                subjob = [_rpath, _lpath, _rsize, _lsize, _boff, _blen, _osize, _depth + 1]
                if getQueCount() > 100:
                    jobPatchQueryDelayed.append((_rpath, _boff, _blen, subjob))
                else:
                    c.FileHash(_rpath, _boff, _blen, (__eventHashReply, subjob))
                return
            print('patching-section:%s:%x:%x' % (_lpath, _offset, _size))
            # just upload this section..
            c.FileWrite(_rpath, _offset, _data, Client.IOMode.Discard)
            return
        print('patching-match:%s:%x:%x' % (_lpath, _offset, _size))
    
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
        c.HandleMessages(0, None)
        
        #if time.time() - dd > 20:
        #    c.dbgdump()
        #    exit()
        
        # do this after handle messages because there may be some added; if quecount
        # is zero it means no pending operations
        quecount = len(jobDirEnum) + len(jobGetRemoteSize) + len(jobGetModifiedDate) + len(jobPatch) + len(jobUpload)
        
        output.SetTitle('WaitingVectors', c.waitCount())
        # if we are not waiting on anything from the client then we could close
        # the connection *except* it might cause the remote to drop packets that
        # are not waiting on a result from.. so since we can determine that we
        # will never generate any more packets we can send an echo which will
        # get a reply and once that happens we can shut down the connection
        if len(jobDirEnum) + len(jobPendingFiles) + getQueCount() == 0 and sentEcho is False:
            print('sending echo')
            sentEcho = True
            c.Echo(Client.IOMode.Callback, (__eventEcho, echo))
        
        # i do this after handle messages because it will be calling
        # the callbacks which will update the job lists and if we call
        # it before only jobUpload and jobPatch will likely be over zero
        # because the other jobs execute right as they are received
        dt = time.time() - c.bytesoutst
        outdata = '%.03f' % (databytesout / 1024 / 1024 / dt)
        outcontrol = '%.03f' % ((c.allbytesout - databytesout) / 1024 / 1024 / dt)
        output.SetTitle('DataOutMB', outdata)
        output.SetTitle('ControlOutMB', outcontrol)
        output.SetTitle('Jobs[DirEnum]', len(jobDirEnum))
        output.SetTitle('Jobs[GetRemoteSize]', len(jobGetRemoteSize))
        output.SetTitle('Jobs[GetModDate]', len(jobGetModifiedDate))
        output.SetTitle('Jobs[Patch]', len(jobPatch))
        output.SetTitle('Jobs[Upload]', len(jobUpload))
        output.SetTitle('UpToDate', stat_uptodate)
        output.SetTitle('Uploaded', stat_uploaded)
        output.SetTitle('Checked', stat_checked)
        output.SetTitle('Patched', stat_patched)

        # send if can send
        boutbuf = c.getBytesToSend()
        # just hold here until we get the buffer down; this
        # is mainly going to be caused by upload operations
        # throwing megabytes of data into the buffer
        if boutbuf > buflimit:
            print('emptying outbound buffer..')
            # just empty the out going buffer completely.. then of course
            # fill it up again; having the buffer fill up is not actually
            # a bad thing as it means we are exceeding the network throughput
            # which is good because our CPU wont be running wide open
            while c.getBytesToSend() > 0:
                # pull data out of network driver buffers into our own buffers or
                # process it if it has callbacks and essentially place it into
                # our own buffers just processed <humor intended> ...
                # OR/AND
                # flush data from our buffers
                c.handleOrSend()
                #print('left:%s' % c.getBytesToSend())
                
                # keep the status updated
                dt = time.time() - c.bytesoutst
                outdata = '%.03f' % (databytesout / 1024 / 1024 / dt)
                outcontrol = '%.03f' % ((c.allbytesout - databytesout) / 1024 / 1024 / dt)
                output.SetTitle('DataOutMB', outdata)
                output.SetTitle('ControlOutMB', outcontrol)
                output.SetTitle('OutBuffer', c.getBytesToSend())
                time.sleep(0.05)
            #print('continuing..')
        else:
            # just send what we can right now
            c.send()

        #
    

        # do not produce too many - limit to limit memory usage; the
        # alternative is to let it run free.. which could in certain
        # situations consume massive amounts of memory
        if len(jobPendingFiles) < 5000:
            for x in range(0, min(100, len(jobDirEnum))):
                dej = jobDirEnum[x]
                output.SetTitle('LastDir', dej)
                #print('<enuming-dir>:%s' % dej)
                nodes = os.listdir(dej)

                for node in nodes:
                    _lpath = '%s/%s' % (dej, node)
                    if os.path.isdir(_lpath):
                        # delay this..
                        jobDirEnum.append(_lpath)
                        #print('[enum]:%s' % _lpath)
                        continue
                    jobPendingFiles.append(_lpath)
            # drop what we completed
            jobDirEnum = jobDirEnum[x + 1:]

        #
        # this comes before jobPendingFiles because otherwise 
        # we would never finish our current pending jobs
        #
        # this is delayed hash requests; they were likely delayed
        # because there was too many out standing jobs and requests
        if getQueCount() < 100:
            dbg = False
            for x in range(0, min(100, len(jobPatchQueryDelayed))):
                dbg = True
                job = jobPatchQueryDelayed[x]
                _rpath = job[0]
                _off = job[1]
                _size = job[2]
                subjob = job[3]
                print('pending-hash:%s:%x:%x' % (_rpath, _off, _size))
                c.FileHash(_rpath, _off, _size, Client.IOMode.Callback, (__eventHashReply, subjob))
            # drop the ones we executed
            jobPatchQueryDelayed = jobPatchQueryDelayed[x + 1:]

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
        mcnt = max(0, 200 - getQueCount())
        tr = []
        for x in range(0, min(mcnt, len(jobPatch))):
            job = jobPatch[x]
            _rpath = job[0]
            _lpath = job[1]
            _rsize = job[2]
            _lsize = job[3]
            _curoff = job[4]
            _off = 0
            csz = 1024 * 1024
            _tsz = min(csz, _lsize - _off)
            subjob = [_rpath, _lpath, _rsize, _lsize, _off, _tsz, _lsize, 0]
            c.FileHash(_rpath, _off, _tsz, Client.IOMode.Callback, (__eventHashReply, subjob))
            job[4] = job[4] + csz
            if job[4] >= _lsize:
                tr.append(job)
        for t in tr:
            jobPatch.remove(t)

        # DESCRIPTION:
        #     
        if getQueCount() < 100:
            for x in range(0, min(100, len(jobPendingFiles))):
                    _lpath = jobPendingFiles[x]
                    stat = os.stat(_lpath)
                    # send request and create job entry
                    _lsize = stat.st_size
                    _rpath = rpath + bytes(_lpath[lpbsz:], 'utf8')
                    #print('<getting-size>:%s' % _rpath)
                    if _lsize > 1024 * 1024 * 200:
                        continue
                    stat_checked = stat_checked + 1
                    pkg = (_rpath, _lpath, _lsize, None, int(stat.st_mtime))
                    #print('[size]:%s' % _rpath)
                    c.FileSize(_rpath, Client.IOMode.Callback, (__eventFileSize, pkg))
            # drop what we completed
            jobPendingFiles = jobPendingFiles[x + 1:]

        ########################################################
        ############## NO LIMIT SECTIONS BELOW #################
        ########################################################

        # look for replies on remote sizes and create next job
        tr = []
        for rsj in jobGetRemoteSize:
            pkg = rsj[0]
            _result = rsj[1]
            _rpath = pkg[0]
            _lpath = pkg[1]
            _lsize = pkg[2]
            _vector = pkg[3]
            _lmtime = pkg[4]
            # result[0] = success code is non-zero and result[1] = size (0 on failure code)
            _rsize = _result[1]
            # if file does not exist go trun/upload route.. if it does
            # exist and the size is the same then check the file modified
            # date and go from there
            #if _lsize != _rsize:
                #print('[size] file:%s local:%s remote:%s' % (_lpath, _lsize, _rsize))
            if _lsize == _rsize and _result[0] == 1:
                # need to check modified date
                #print('<getting-time>:%s' % _lpath)
                #print('<gettime>:%s' % _lpath)
                pkg = (_rpath, _lpath, _rsize, _lsize, _vector, _lmtime)
                c.FileTime(_rpath, Client.IOMode.Callback, (__eventFileTime, pkg))
            else:
                # first make the remote size match the local size
                #print('<trun>:%s' % _lpath)
                c.FileTrun(_rpath, _lsize, Client.IOMode.Discard)
                # need to decide if we want to upload or patch
                if False and (min(_rsize, _lsize) / max(_rsize, _lsize) < 0.5):
                    # make upload job
                    print('<upload>:%s' % _lpath)
                    jobUpload.append([_rpath, _lpath, _rsize, _lsize, 0])
                else:
                    # make patch job
                    #print('<make-patch-job>:%s' % _lpath)
                    jobPatch.append([_rpath, _lpath, _rsize, _lsize, 0])
        jobGetRemoteSize = []

        # iterate
        tr = []
        for rtj in jobGetModifiedDate:
            pkg = rtj[0]
            _rmtime = rtj[1]
            _rpath = pkg[0]
            _lpath = pkg[1]
            _rsize = pkg[2]
            _lsize = pkg[3]
            _vector = pkg[4]
            _lmtime = pkg[5]

            #print('<handling-time-reply>:%s' % _lpath)

            if _rmtime < _lmtime:
                # need to decide if we want to upload or patch
                if False and math.min(_rsize, _lsize) / math.max(_rsize, _lsize) < 0.5:
                    # make upload job
                    print('<upload>:%s' % _lpath)
                    jobUpload.append([_rpath, _lpath, _rsize, _lsize, 0])
                else:
                    #print('<make-patch>:%s' % _lpath)
                    # make patch job
                    jobPatch.append([_rpath, _lpath, _rsize, _lsize, 0])
            else:
                # just drop it since its either up to date or newer
                #print('<up-to-date>:%s' % _lpath)
                stat_uptodate = stat_uptodate + 1
                continue
        jobGetModifiedDate = [] 

        # 
        tr = []
        cjc = 0
        for uj in jobUpload:
            _rpath = uj[0]
            _lpath = uj[1]
            _rsize = uj[2]
            _lsize = uj[3]
            _curoff = uj[4]
            _chunksize = 1024 * 1024
            # see what we can send
            _rem = _lsize - _curoff
            if _rem > _chunksize:
                _rem = _chunksize
            else:
                tr.append(uj)
            # open local file and read chunk
            _fd = open(_lpath, 'rb')
            _fd.seek(_curoff)
            _data = _fd.read(_rem)
            _fd.close()
            print('<wrote>:%s:%x' % (_lpath, _curoff))
            c.FileWrite(_rpath, _curoff, _data, Client.IOMode.Discard)
            # help track statistics for data out in bytes (non-control data)
            databytesout = databytesout + _rem
            if c.getBytesToSend() > buflimit:
                break
            # just a kinda safe upper limit in the case something
            # happens and we have tons of super small files i dont
            # want that the overload memory
            if cjc > 10000:
                break
            # advance our current offset
            uj[4] = _curoff + _rem
            cjc = cjc + 1
        # remove finished jobs
        ct = time.time()
        for uj in tr:
            # set the modified time on the file to the current
            # time to represent it is up to date
            _rpath = uj[0]
            c.FileSetTime(_rpath, int(ct), int(ct), Client.IOMode.Discard)
            jobUpload.remove(uj)
            stat_uploaded = stat_uploaded + 1
        continue
    c.close()

def SyncRemoteWithDeleted(rhost, rport, sac, lpath, rpath = None, filter = None, stash = True, ssl = True, sformat = True):
    if rpath is None:
        rpath = b'/'

    sac = bytes(cfg['storage-auth-code'], 'utf8')
    c = Client2(rhost, rport, sac, sformat)
    c.Connect(essl = ssl)
    # produce remote and local paths
    
    # initialize our wait list
    waitlist = {}
    waitlist[c.DirList(rpath, block = False, discard = False)] = (lpath, rpath)
    
    output.SetTitle('account', account)
    output.SetTitle('target', target)
    
    donecount = 0
    stashfilecount = 0
    stashdircount = 0
    
    # keep going until nothing is left in the wait list
    while len(waitlist) > 0:
        dt = time.time() - c.bytesoutst
        
        outdata = '%.03f' % (c.bytesout / 1024 / 1024 / dt)
        outcontrol = '%.03f' % ((c.allbytesout - c.bytesout) / 1024 / 1024 / dt)
        
        output.SetTitle('DataOutMB', outdata)
        output.SetTitle('ControlOutMB', outcontrol)
        output.SetTitle('PendingRequests', len(waitlist))
        output.SetTitle('FileDoneCount', donecount)
        output.SetTitle('StashedFiles', stashfilecount)
        output.SetTitle('StashedDirs', stashdircount)
    
        # process any incoming messages; the 0 means
        # wait 0 seconds which is non-blocking; if
        # it was None we would block for a message
        #print('handling messages')
        c.HandleMessages(0, None)
        
        # do we have pending data to be sent
        if c.canSend():
            # send it.. we can eventually stall out
            # waiting for data when there is data to
            # send and the server's incoming buffer is
            # empty
            c.send()
        
        # see if anything has arrived
        toremove = []
        toadd = []
        #print('checking for arrived requests')
        for v in waitlist:
            #print('checking for %s' % v)
            # check if it has arrived
            nodes = c.GetStoredMessage(v)
            # okay remove it from waitlist
            if nodes is None:
                #print('    not arrived')
                continue
            toremove.append(v)
            # yes, so process it
            subdirs = []
            for node in nodes:
                lpath = waitlist[v][0]
                rpath = waitlist[v][1]
            
                nodename = node[0]
                nodetype = node[1]
                
                donecount = donecount + 1
                
                # get stash id 
                try:
                    nodestashid = int(nodename[0:nodename.find(b'.')])
                except:
                    # just skip it.. non-conforming to stash format or non-numeric stash id
                    continue
                
                # check if current
                if nodestashid != 0:
                    # it is a stashed version (skip it)
                    continue
                
                # drop stash id
                nodename = nodename[nodename.find(b'.') + 1:]
                
                # build remote path as bytes type
                remote = rpath + b'/' + nodename
                
                # build local path as string
                local = '%s/%s' % (lpath, nodename.decode('utf8'))
                
                # determine if local resource exists
                lexist = os.path.exists(local) 
                rexist = True
                
                #print('checking remote:[%s] for local:[%s]' % (remote, local))
                
                # determine if remote is directory
                if nodetype == 1:
                    risdir = True
                else:
                    risdir = False
                
                # determine if local is a directory
                if lexist:
                    lisdir = os.path.isdir(local)
                else:
                    lisdir = False

                #remote = b'%s/%s.%s' % (rpath, nodestashid, nodename)                # bytes  (including stash id)
                remote = rpath + b'/' + bytes('%s' % nodestashid, 'utf8') + b'\x00' + nodename
                
                # local exist and both local and remote is a directory
                if lexist and risdir and lisdir:
                    # go into remote directory and check deeper
                    # delay this..
                    _lpath = '%s/%s' % (lpath, nodename.decode('utf8'))                            # string
                    #print('[pushing for sub-directory]:%s' % _lpath)
                    subdirs.append((_lpath, remote))
                    continue
                
                # local exist and remote is a directory but local is a file
                if lexist and risdir and not lisdir:
                    print('[stashing remote directory]:%s' % local)
                    # stash remote directory, use time.time() as the stash id since it
                    # should be unique and also easily serves to identify the latest stashed
                    # remote since zero/0 is reserved for current working version
                    stashdircount = stashdircount + 1
                    t = int(time.time() * 1000000.0)
                    _newremote = rpath + b'/' + bytes('%s' % t, 'utf8') + b'\x00' + nodename
                    # one problem is the remote directory could contain a lot of files that
                    # are were actually moved or copied somewhere else - i am thinking of
                    # using another algorithm to pass over and link up clones saving server
                    # space
                    c.FileMove(remote, _newremote, Client.IOMode.Discard)
                    # let push function update local file to remote
                    continue
                    
                # local exist and remote is a file but local is a directory
                if lexist and not risdir and lisdir:
                    print('[stashing remote file]:%s' % local)
                    # stash remote file
                    stashfilecount = stashfilecount + 1
                    #_newremote = b'%s/%s.%s' % (rpath, time.time(), nodename)
                    t = int(time.time() * 1000000.0)
                    _newremote = rpath + b'/' + bytes('%s' % t, 'utf8') + b'\x00' + nodename
                    c.FileMove(remote, _newremote, Client.IOMode.Discard)
                    # let push function update local directory to remote
                    continue
                    
                # local does not exist
                if not lexist:
                    print('[stashing deleted]:%s' % local)
                    if risdir:
                        stashdircount = stashdircount + 1
                    else:
                        stashfilecount = stashfilecount + 1
                    #_newremote = b'%s/%s.%s' % (rpath, time.time(), nodename)
                    t = int(time.time() * 1000000.0)
                    _newremote = rpath + b'/' + bytes('%s' % t, 'utf8') + b'\x00' + nodename
                    c.FileMove(remote, _newremote, Client.IOMode.Discard)
                    continue
                continue
                # <end-of-node-loop> (looping over results of request)
            # create requests for any sub-directories
            for subdir in subdirs:
                _lpath = subdir[0]
                _rpath = subdir[1]
                #print('[requesting]:%s' % _rpath)
                output.SetTitle('RecentDir', _lpath)
                toadd.append((c.DirList(_rpath, block = False, discard = False), _lpath, _rpath))
            # <end-of-wait-list-loop> (looping over waiting vectors)
        
        # add anything we got
        for p in toadd:
            waitlist[p[0]] = (p[1], p[2])
        # remove anything we got from the wait list
        for v in toremove:
            del waitlist[v]
        
        # if we just fly by we will end up burning
        # like 100% CPU *maybe* so lets delay a bit in
        #time.sleep(0.01)
