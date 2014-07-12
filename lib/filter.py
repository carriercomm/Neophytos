import re

class FilterOption:
    MatchFile           = 1
    MatchDir            = 2
    MatchAny            = 0
    MatchAccept         = 8
    MatchPath           = 16
    MatchReject         = 0

'''
    This checks for one of two strings. It return the index
    of whichever comes first or -1 if neither come first.
'''
def findOrFind(hay, needle1, needle2):
    a = hay.find(needle1)
    b = hay.find(needle2)
    if a > -1 and (a < b or b < 0):
        return a
    return b

class Filter:
    def __init__(self, filterFile = None):
        self.filter = None
        if filterFile is not None:
            self.filter = Filter.loadFilterFile(filterFile)

    def check(self, lpath, node, isDir):
        filter = self.filter

        if filter is None:
            # accept everything
            return True
        for fitem in self.filter:
            if isDir and fitem[0] & FilterOption.MatchFile:
                continue
            if not isDir and fitem[0] & FilterOption.MatchDir:
                continue

            if fitem[0] & FilterOption.MatchPath:
                haystack = lpath
            else:
                haystack = node

            match = fitem[1].match(haystack)
            if fitem[0] & FilterOption.MatchAccept and match:
                return True
            if match:
                return False
        # by default if no filter match just reject it
        return False

    '''
        This loads a filter file. It converts all strings into
        an integer which is faster to check, and it compiles
        the regular expression which also makes it fast. It needs
        to be quick because this is going to evaluate every file
        and directory.
    '''
    def loadFilterFile(filterFile):
        fd = open(filterFile, 'rb')
        lines = fd.readlines()
        fd.close()

        filter = []

        for line in lines:
            line = line.strip()
            item = Filter.parseFilterLine(line)
            filter.append(item)
        return filter

    def parseAndAddFilterLine(self, line):
        item = Filter.parseFilterLine(line)
        if item is None:
            return
        if self.filter is None:
            self.filter = []
        self.filter.append(item)

    def parseFilterLine(line):
        i = findOrFind(line, b' ', b'\t')
        if i < 0:
            return None
        f1 = line[0:i].strip().lower()
        line = line[i:].strip()
        i = findOrFind(line, b' ', b'\t')
        if i < 0:
            return None
        f2 = line[0:i].strip().lower()
        line = line[i:].strip()
        f3 = line

        if f1 == b'file':
            f1 = FilterOption.MatchFile
        elif f1 == b'dir':
            f1 = FilterOption.MatchDir
        elif f1 == b'path':
            f1 = FilterOption.MatchPath
        else:
            f1 = FilterOption.MatchAny

        if f2 == b'accept':
            f2 = FilterOption.MatchAccept
        else:
            f2 = FilterOption.MatchReject

        #print('@@', f1, f2, f3)
        #raise Exception('[%s] [%s] [%s]' % (f1, f2, f3))
        f3 = re.compile(f3)
        return (f1 + f2, f3)
