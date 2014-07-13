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
        print('plugins', xid, self.plugins)
        if xid not in self.plugins:
            return None
        return self.plugins[xid]

    '''
        For some plugins we create one instance, and to reduce calling code
        from having to manage this we provide that here. This reduces the
        calling code complexity although it decreases readability in my
        opinion it can reduce bugs.
    '''
    def getPluginInstance(self, plugid, tag, options = (), koptions = {}):
        if plugid not in self.instances:
            self.instances[plugid] = {}
        if tag not in self.instances[plugid]:
            self.instances[plugid][tag] = self.getPlugin(plugid)(*options, **koptions)
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
                print('ipath', ipath)
                mod = __import__(ipath, globals(), locals(), curdirname)
                mplugins = mod.getPlugins()
                for p in mplugins:
                    self.plugins[p[0]] = p[1]
        print('done loading plugins with..', self.plugins)