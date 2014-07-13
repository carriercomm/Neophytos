'''
    This implements a very simple XOR encryption using either an
    UTF8 string passed or a file passed by file path. It can handles
    random access of the file for reading and writing.
'''
from io import BytesIO

import lib.flycatcher as flycatcher
logger = flycatcher.getLogger('crypt.xor')

class XorFileEncryptObject:
    def __init__(self, lpath, fod):
        self.lpath = lpath
        if fod[0] == 'file':
            self.xfo = open(fod[1], 'rb')
        else:
            self.xfo = BytesIO(bytes(fod[1], 'utf8'))

        self.xfo.seek(0, 2)
        self.xfosz = self.xfo.tell()

        self.fo = open(lpath, 'rb')

    def read(self, offset, length):
        _data = bytearray(length)

        # seek to the position in the XOR data relative to our file position
        # in which we are considering that we loop over our XOR data
        self.xfo.seek(offset - (int(offset / self.xfosz) * self.xfosz))
        self.fo.seek(offset)

        self.fo.readinto(_data)
        # encrypt the data
        rem = length
        off = 0
        while rem > 0:
            xdata = self.xfo.read(rem)
            if len(xdata) < 1:
                # if we run out of bytes just seek back
                # to the beginning and start over..
                self.xfo.seek(0)
                continue

            for x in range(0, len(xdata)):
                # yeah.. not sure this is performance code..
                _data[x] = _data[x] ^ xdata[x]

            rem = rem - len(xdata)
            off = off + len(xdata)
        return bytes(_data)

    def finish(self):
        self.fo.close()
        self.xfo.close()

class XorFileDecryptObject:
    def __init__(self, lpath, fod):
        self.lpath = lpath
        if fod[0] == 'file':
            self.xfo = open(fod[1], 'rb')
        else:
            self.xfo = BytesIO(bytes(fod[1], 'utf8'))
        self.fo = open(lpath, 'rb')

        self.xfo.seek(0, 2)
        self.xfosz = self.xfo.tell()

    def write(self, offset, data):
        _data = BytesIO()

        self.xfo.seek(offset - (int(offset / self.xfosz) * self.xfosz))

        # encrypt the data
        rem = len(data)
        off = 0
        while rem > 0:
            xdata = self.xfo.read(rem)
            if len(xdata) < 1:
                # if we run out of bytes just seek back
                # to the beginning and start over..
                self.xfo.seek(0)
                continue

            for x in range(0, len(xdata)):
                # yeah.. not sure this is performance code..
                _data.write(bytes((data[off + x] ^ xdata[x],)))

            rem = rem - len(xdata)
            off = off + len(xdata)

        self.fo.seek(offset)
        self.fo.write(_data.getbuffer())
        return

    def finish(self):
        self.fo.close()
        self.xfo.close()

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
    return (
        ('crypt.xor', Xor),
    )