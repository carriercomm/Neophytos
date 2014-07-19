'''

    mod = __import__('path')
'''
import os
import os.path

pm = None

def getPM():
    global pm

    if pm is None:
        pm = __PluginMan()
    return pm

class __PluginMan:
    def __init__(self):
        # load plugins from the plugin directory
        self.plugins = {}
        self.loadPlugins()
        self.instances = {}

    def getPlugin(self, xid):
        if xid not in self.plugins:
            return None
        return self.plugins[xid]

    def getplugintype(self, plugid):
        """ Return the type object on which static methods or a instance can be created with. """
        return self.getPlugin(plugid)

    def getPluginInstance(self, plugid, tag, options = (), koptions = {}):
        """ Return an instance, possibly an existing instance, of the plugin.

        This allows us to return an instance, which may be an existing instance, which
        helps reduce CPU time because an instance can likely be shared if it has the
        same tag, and options.
        """
        if plugid not in self.instances:
            self.instances[plugid] = {}
        tag = '%s:%s:%s' % (tag, options, koptions)
        if tag not in self.instances[plugid]:
            plugtype = self.getPlugin(plugid)
            if plugtype is None:
                return None
            print('options:%s koptions:%s' % (options, koptions))
            self.instances[plugid][tag] = plugtype(*options, **koptions)
        return self.instances[plugid][tag]

    def loadPlugins(self, relpath = ''):
        nodes = os.listdir('./plugins/%s' % (relpath))

        curdirname = relpath[relpath.rfind('/') + 1:]

        for node in nodes:
            fpath = './plugins/%s/%s' % (relpath, node)
            if os.path.isdir(fpath):
                self.loadPlugins('%s/%s' % (relpath, node))
                continue

            # look for a python file with the same name as the current directory 
            if node == '%s.py' % curdirname:
                ipath = 'plugins%s.%s' % (relpath.replace('/', '.'), curdirname)
                mod = __import__(ipath, globals(), locals(), curdirname)
                mplugins = mod.getplugins()
                for p in mplugins:
                    self.plugins[p[0]] = p[1]