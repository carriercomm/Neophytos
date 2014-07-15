'''
    This is designed to run tests to verify correct operation.
'''
import random
import subprocess
import os
import sys
import os.path
import shutil

from lib.client import Client2
from lib import buops

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

def makeRandomNodes(path, maxSpace = 1024 * 1024 * 100, maxFiles = 100, maxPathLength = 38):
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
            data = os.urandom(fsz)
            fd.write(data)
            fd.close()
            print('made-file:%s' % xfile)
        except:
            continue
    return

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
                    print('file size no match with %s:%s' % (foa.tell() - lmetasize, fob.tell() - rmetasize))
                    exit()

                sz = foa.tell()
                rem = sz
                foa.seek(lmetasize, 0)
                fob.seek(rmetasize, 0)            # account for default meta-data
                while rem > 0:
                    o = foa.tell()
                    a = foa.read(min(1024 * 1024 * 4, rem))
                    b = fob.read(min(1024 * 1024 * 4, rem))
                    if a != b:
                        print('data not same')
                        exit()
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
#s chapter

def unitTestBackupOps():
    for run in range(0, 100):
        # remove temp directories if they exist
        if True:
            if os.path.exists('./temp/local'):
                shutil.rmtree('./temp/local')
            if os.path.exists('./temp/remote'):
                shutil.rmtree('./temp/remote')
            # create temp directorys
            os.makedirs('./temp/local')
            os.makedirs('./temp/remote')

            print('building random file tree (may take a while..)')
            makeRandomNodes('./temp/local')
        # create account file
        # start the server
        # issue a push operation (most basic operation.. no filters.. no catches..)
        if True:
            buops.Push(
                'localhost', 4322, 'ok493L3Dx92Xs029W', b'./temp/local',
                b'', None, True, True, None, None
            )
        # verify directories are the same and file contents are equal
        compareTreeToTree('./temp/local', './temp/remote')

        # 17240826
        
        # issue a pull operation
        # verify pull operation results of files and contents
        # delete some random local directory files
        # sync locally deleted files
        # verify results
        # delete some random remote directory files
        # verify results
        # issue a push operation with encryption
        # issue a pull operation with decryption
        # verify fs tree is the same as original local

def main():
    #if unitTestHashKmc() is False:
    #    print('[TestHashKmc]    FAILED')
    if unitTestBackupOps() is False:
        print('[TestBackupOps]  FAILED')


main()