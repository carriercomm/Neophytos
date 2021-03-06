'''
    This is designed to run tests to verify correct operation.
'''
import random
import subprocess
import os
import sys
import os.path
import shutil
import ctypes
import time

from lib.client import Client2
from lib import buops

from lib.pluginman import getPM

from lib.efilters import EncryptionFilters  # encryption filters created from encryption filter file
from lib.filter import Filter               # single filter created from file normally

pyrandgenbytes_hdll = None
pyrandgenbytes_hfunc = None

def pyrandgenbytes(sz):
    global pyrandgenbytes_hdll
    global pyrandgenbytes_hfunc

    if pyrandgenbytes_hfunc is False:
        return os.urandom(sz)

    if pyrandgenbytes_hdll is None:
        #pyrandgenbytes_hdll = ctypes.cdll.LoadLibrary('%s/pyrandgenbytes.so' % os.getcwd())
        pyrandgenbytes_hdll = ctypes.CDLL('%s/pyrandgenbytes.so' % os.getcwd())
        if pyrandgenbytes_hdll is None:
            pyrandgenbytes_hfunc = False
            return os.urandom(sz)
        pyrandgenbytes_hfunc = pyrandgenbytes_hdll['pyrandgenbytes']

    buf = ctypes.create_string_buffer(sz)
    pyrandgenbytes_hfunc(buf, ctypes.c_uint32(sz))
    return bytes(buf)

def unitTestHashKmc():
    c = Client2(None, None, None, None)

    for lcnt in range(0, 1000):
        h1 = None
        h2 = None
        h3 = None

        # produce test data
        maxsz = 1024 * 1024 * 16
        sz = random.randint(0, maxsz)
        hsz = random.randint(0, maxsz)
        data = []
        for x in range(0, sz):
            data.append(random.randint(0, 255))
        data = bytes(data)

        # test pure python implementation
        _hentry = c.hentry
        c.hentry = None
        #h1 = c.HashKmc(data, hsz)
        # test native implementation (if exists)
        h2 = None
        if _hentry is not None:
            c.hentry = _hentry
            _data = bytes(list(data))
            print('getting H2')
            h2 = c.HashKmc(_data, hsz)
        cwd = os.getcwd()
        cwd = '%s/goserver/src'
        #p = subprocess.Popen(['go build main'], cwd = cwd, shell = True)
        #p.wait()
        cwd = os.getcwd()
        cwd = '%s/goserver/src/' % cwd
        print('--------------------------')
        p = subprocess.Popen(['%ssrc' % cwd, 'testunit-hash'], cwd = cwd, shell = False, stdin = subprocess.PIPE, stdout = subprocess.PIPE)
        bin = []
        bin.append(hsz >> 16 & 0xff)
        bin.append(hsz >> 8 & 0xff)
        bin.append(hsz & 0xff)
        bin.append(sz >> 16 & 0xff)
        bin.append(sz >> 8 & 0xff)
        bin.append(sz & 0xff)
        bin = bytes(bin) + data
        print('getting H3')
        out = p.communicate(bin)
        h3 = out[0]
        if out[1] is not None and len(out[1]) > 0:
            print(out[1])
            exit()
        p.wait()
        if h1: print('h1', len(h1), h1[0:10])
        if h2: print('h2', len(h2), h2[0:10])
        if h3: print('h3', len(h3), h3[0:10])

        if h2 != h3:
            print('FAILED AT HASH TEST')
            return False
            
            return False
    return True

def makeRandomList(sz, charset):
    out = []
    for x in range(0, sz):
        out.append(charset[random.randint(0, len(charset) - 1)])
    return out

def makeRandomNodes(path, maxSpace = 1024 * 1024 * 2, maxFiles = 20, maxPathLength = 38):
    cs = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i']

    files = {}

    spaceUsed = 0

    # make random files
    for x in range(0, maxFiles):
        # get random name of random length
        fname = makeRandomList(random.randint(1, 4), cs)
        fname = '/'.join(fname)
        fname = '%s/%s' % (fname, ''.join(makeRandomList(random.randint(1, 8), cs)))
        if fname[-1] == '/':
            continue
        # get random data of random length
        if fname not in files:
            # at least 1024, but no larger than 32 and less than 32 if less than remaining space
            files[fname] = random.randint(0, min(max(maxSpace - spaceUsed, 1024), 1024 * 1024 * 32))
            print('new', fname)

    for xfile in files:
        fsz = files[xfile]
        base = '%s/%s' % (path, xfile[0:xfile.rfind('/')])
        xfile = '%s/%s' % (path, xfile)
        if os.path.exists(base) is False:
            try:
                os.makedirs(base)
            except:
                continue
        #print('    writing data')
        spaceUsed += fsz
        # write data into file
        try:
            fd = open(xfile, 'wb')
            data = pyrandgenbytes(fsz)
            fd.write(data)
            fd.close()
            print('made-file:%s' % xfile)
        except:
            continue
    return

def chooseRandomFileFromPath(_lpath):
    # keep going until we get a file not a directory
    # just incase we have some empty directories
    lpath = _lpath
    while os.path.isdir(lpath):
        lpath = _lpath
        while os.path.isdir(lpath):
            nodes = os.listdir(lpath)
            # well apparently, we have run into
            # an empty directory so we will have
            # to try again
            if len(nodes) < 1:
                break
            node = random.choice(nodes)
            lpath = lpath + b'/' + node
    return lpath

'''
    Does compareTreeTo but for both directions.
'''
def compareTreeToTree(lpath, rpath, lmetasize = 0, rmetasize = 128):
    compareTreeTo(lpath, rpath, lmetasize, rmetasize, True)
    compareTreeTo(rpath, lpath, rmetasize, lmetasize, False)

'''
    Makes sure that all files under lpath also exist under rpath, but
    does not check if all files in rpath exist under lpath.
'''
def compareTreeTo(lpath, rpath, lmetasize = 0, rmetasize = 128, checkcontents = True):
    dirstc = []
    dirstc.append(lpath)

    failed = False

    while len(dirstc) > 0:
        _dirstc = []
        for cdir in dirstc:
            #print('looking at', cdir)
            nodes = os.listdir(cdir)
            for node in nodes:
                fpath = '%s/%s' % (cdir, node)
                if os.path.isdir(fpath):
                    _dirstc.append(fpath)
                    continue
                # check that this node also exists in rpath
                relsuff = fpath[len(lpath):]
                frpath = '%s/%s' % (rpath, relsuff)
                if not os.path.exists(frpath):
                    print('oops.. no exist.. local:%s remote:%s' % (fpath, frpath))
                    exit()
                print('exists fpath:%s rpath:%s' % (fpath, frpath))
                # check file contents
                if not checkcontents:
                    continue
                foa = open(fpath, 'rb')
                fob = open(frpath, 'rb')

                foa.seek(0, 2)
                fob.seek(0, 2)          # account for default meta-data
                if foa.tell() - lmetasize != fob.tell() - rmetasize:
                    print('fpath:%s rpath:%s' % (fpath, frpath))
                    print('  foa.tell():%s lmetasize:%s fob.tell():%s rmetasize:%s' % (foa.tell(), lmetasize, fob.tell(), rmetasize))
                    print('  file size no match with %s:%s' % (foa.tell() - lmetasize, fob.tell() - rmetasize))
                    #raise Exception('File Size Does Not Match')
                    failed = True
                    continue

                sz = foa.tell()
                rem = sz
                foa.seek(lmetasize, 0)
                fob.seek(rmetasize, 0)            # account for default meta-data
                while rem > 0:
                    o = foa.tell()
                    a = foa.read(min(1024 * 1024 * 4, rem))
                    b = fob.read(min(1024 * 1024 * 4, rem))
                    if a != b:
                        print('  Data Not Same')
                        failed = True
                    #for x in range(0, len(a)):
                    #    if a[x] != b[x]:
                            #fd = open('tempa', 'wb')
                            #fd.write(a)
                            #fd.close()
                            #fd = open('tempb', 'wb')
                            #fd.write(b)
                            #fd.close()
                    #        print('a:%s b:%s' % (a[x], b[x]))
                    #        print('byte not same on offset:%s rem:%s sz:%s' % (o, rem, sz))
                    #        exit()
                    rem = rem - len(a)
        # 
        dirstc = _dirstc
    if failed:
        raise Exception('Test Failed')
#s chapter

def unitTestBackupOps():
    for run in range(0, 100):
        # remove temp directories if they exist
        if True:                                   # remove local
            if os.path.exists('./temp/local'):
                shutil.rmtree('./temp/local')
            os.makedirs('./temp/local')
            print('building random file tree (may take a while..)')
            makeRandomNodes('./temp/local', maxFiles = 25)

        if True:                                    # remove server storage location
            if os.path.exists('./temp/remote'):
                shutil.rmtree('./temp/remote')
            os.makedirs('./temp/remote')
        if True:                                   # remove pulled
            if os.path.exists('./temp/pulled'):
                shutil.rmtree('./temp/pulled')
            os.makedirs('./temp/pulled')

        class Catcher:
            def __init__(self, ct, filterfile, efilterfile, defcryptstring):
                self.ct = ct

                # ensure default encryption filter object is created
                self.efilters = EncryptionFilters(efilterfile, defcryptstring)

                if filterfile is not None:
                    self.filter = Filter(filterfile)
                else:
                    self.filter = None

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
                    plug = getPM().getPluginInstance(plugid, plugtag, (None, plugopts))
                else:
                    # this should rarely be used.. the caller will likely be providing
                    # the efilter object when calling this function, but it is here
                    # in the event that they do not..
                    etag = b''
                    plug = getPM().getPluginInstance('crypt.null', '', (None, []))
                    plugopts = (c, [])
                return (etag, plug, plugopts)


        # filter-file
        # efilter-file
        # defencstring
        fo = open('./temp/efilter', 'w')
        fo.close()

        fo = open('./temp/filter', 'w')
        fo.write('any     accept    .*\n')
        fo.close()

        sw = Catcher(None, './temp/filter', './temp/efilter', 'apple,crypt.aesctrmulti,pass:mypassword')
        catches = {
            'DecryptByTag':         sw.catchDecryptByTag,       #
            'EncryptFilter':        sw.catchEncryptFilter,      #
        }

        # create account file
        # start the server
        # issue a push operation (most basic operation.. no filters.. no catches..)
        if True:
            buops.Push(
                'localhost', 4322, 'ok493L3Dx92Xs029W', b'./temp/local',
                b'', True, catches = catches
            )
        # verify directories are the same and file contents are equal

        #if True:
        #    compareTreeToTree('./temp/local', './temp/remote')

        # perform a pull operation and verify files and contents
        if True:
            buops.Pull(
                'localhost', 4322, 'ok493L3Dx92Xs029W', b'./temp/pulled',
                b'', True, catches = catches
            )

        if True:
            # give it a chance to update the FS especially if it is
            # a non-standard file system...
            time.sleep(2)
            compareTreeToTree('./temp/local', './temp/pulled', 0, 0)

        if True:
            # pick some random file
            fdeleted = chooseRandomFileFromPath(b'./temp/local')
            # delete the file
            os.remove(fdeleted)

        if True:
            # synchronize the deleted file
            buops.SyncRemoteWithDeleted(
                'localhost', 4322, 'ok493L3Dx92Xs029W', b'./temp/local',
                b'', True
            )

        if True:
            # synchronize pulled directory
            buops.SyncLocalWithDeleted(
                'localhost', 4322, 'ok493L3Dx92Xs029W', b'./temp/pulled',
                b'', True
            )

def main():
    #if unitTestHashKmc() is False:
    #    print('[TestHashKmc]    FAILED')
    if unitTestBackupOps() is False:
        print('[TestBackupOps]  FAILED')

main()