'''
    This module implements an encryption filters object. This is used to determine
    which encryption and with what options to apply to a data source. It uses the
    Filter object to contain each actual filter and attaches a header with the
    encryption plugin and options.
'''

from lib.filter import Filter

import lib.flycatcher as flycatcher

logger = flycatcher.getLogger('client')

class EncryptionFilters:
    '''
        fpath           file path to the encryption filter file (can be None)
        default         encryption string just like used in encryption filter file (can be None)
    '''
    def __init__(self, fpath = None, default = None):
        # this is used for the default encryption when nothing
        # match the filters from the filter file; if no filter
        # file is specified then this will just always be used
        self.default = None
        if default is not None:
            parts = default.split(',')
            options = ','.join(parts[2:])
            tag = parts[0]
            plugin = parts[1]
            self.default = (tag, plugin, options, None)

        filters = []
        if fpath is not None:
            # load the encryption filter file
            fd = open(fpath, 'rb')
            lines = fd.readlines()
            fd.close()

            for line in lines:
                line = line.strip()
                if line[0] == '#':
                    parts = line[1:].split(',')
                    options = ','.join(parts[2:])
                    tag = parts[0]
                    plugin = parts[1]
                    filter = Filter()
                    filters.append((tag, plugin, options, filter))
                if header is None:
                    logger.debug('junk before header line in encryption filter file [%s]' % line)
                    continue
                filter.parseAndAddFilterLine(line)

        self.filters = filters

    def reverse(self, tag):
        """ Return the (plugintype, options) for the given tag or None if not found. """
        print('CHECK; tag:%s def:%s' % (tag, self.default[0]))
        if tag == self.default[0]:
            return (True, self.default[1], self.default[2])
        for filter in self.filters:
            if filter[0] == tag:
                return (True, filter[1], filter[2])
        return (None, None, None)
    '''
        Try to find a filter that matches and then return
        the tag, plugin name, and options. If no matches
        then return none and the default encryption plugin
        can be used.
    '''
    def check(self, lpath, node, isDir):
        for filter in self.filters:
            if filter.check(lpath, node, isDir):
                return (tag, plugin, options)
        return self.default