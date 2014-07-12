'''
    This encryption plugin is used when none is specified. It does
    not encryption anything. It is just like a place holder.
'''

'''
    The read and write file objects help protect the
    programmer by providing a specific object with 
    only the methods valid for usage with the file.
'''
class NullFileEncryptObject:
    '''
        This might be a good place to go ahead and encrypt the file
        and store it in a temporary file so we access it in a random
        way. A more efficient way might be to encrypt as we access it
        but this is not going to always be easy or maybe even possible.
    '''
    def __init__(self, lpath):
        self.lpath = lpath
        self.fd = open(self.lpath, 'rb')
    def read(self, offset, length):
        self.fd.seek(offset)
        return self.fd.read(length)
    def finish(self):
        self.fd.close()

class NullFileDecryptObject:
    '''
        Good place to go ahead and prepare the temporary file.
    '''
    def __init__(self, lpath):
        self.lpath = lpath
        # truncates the file to zero length
        self.fd = open(self.lpath, 'wb')
    def write(self, offset, data):
        self.fd.seek(offset)
        self.fd.write(data)
    '''
        This might be a good place to go ahead and decrypt the file
        from the temporary location and place it where `lpath`
        specifies.
    '''
    def finish(self):
        self.fd.close()

class Null:
    '''
        This is called to initialize the plugin module. It is called
        for each client session.
    '''
    def __init__(self, client):
        pass
    '''
        Called when the operation on the file specified
        with `lpath` begins an encryption operation.
    '''
    def beginRead(self, lpath, options):
        return NullFileEncryptObject(lpath)
    '''
        Called when the operation on the file specified
        with 'lpath' begins an decryption operation.
    '''
    def beginWrite(self, lpath):
        return NullFileDecryptObject(lpath)


def getPlugins():
    return (
        ('crypt.null', Null),
    )