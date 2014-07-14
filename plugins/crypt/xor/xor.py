'''
    This implements a very simple XOR encryption using either an
    UTF8 string passed or a file passed by file path. It can handles
    random access of the file for reading and writing.
'''
import time

from io import BytesIO

import lib.flycatcher as flycatcher
logger = flycatcher.getLogger('crypt.xor')

class XorFileEncryptObject:
    def __init__(self, lpath, fod):
        self.lpath = lpath

        # determine temporary file names
        lbase = lpath[0:lpath.rfind(b'/') + 1]
        lpath = lpath[lpath.rfind(b'/') + 1:]
        tmpname = 
        ltemp = '%s/%s' % (lbase, tmpname)

        # dump XOR data into temporary file
        xtmpname = 
        lxtemp = '%s/%s.xor' % (lbase, xtmpname)

    def read(self, offset, length):
        pass

    def finish(self):
        # delete temporary files
        pass

class XorFileDecryptObject:
    def __init__(self, lpath, fod):
        pass

    def write(self, offset, data):
        pass

    def finish(self):
        pass

class Xor:
    '''
        This is called to initialize the plugin module. It is called
        for each client session.
    '''
    def __init__(self, client, options):
        options = options.split(',')

        for option in options:
            kv = option.split(':')
            if len(kv) < 2:
                continue
            k = kv[0]
            v = ':'.join(kv[1]) 

            if k == 'file':
                self.fod = ('file', v)
            if k == 'data':
                self.fod = ('data', v)

            logger.warn('ignore option "%s"' % k)

    '''
        Called when the operation on the file specified
        with `lpath` begins an encryption operation.
    '''
    def beginRead(self, lpath):
        return XorFileEncryptObject(lpath, self.fod)
    '''
        Called when the operation on the file specified
        with 'lpath' begins an decryption operation.
    '''
    def beginWrite(self, lpath):
        return XorFileDecryptObject(lpath, self.fod)


def getPlugins():
    # ensure that the class can load properly, and if so then
    # add it to the list of plugins we are exporting


    return (
        ('crypt.xor', Xor),
    )