'''

    mod = __import__('path')
'''
import os
import os.path

pm = None

def getPluginMan():
    global pm

    if pm is None:
        pm = __PluginMan()
    return pm

class __PluginMan:
    def __init__(self):
        # load plugins from the plugin directory
        self.loadPlugins()

    def getPlugin(self, id):
        if id not in self.plugins:
            return None
        return self.plugins[id]

    def loadPlugins(self, relpath = ''):
        nodes = os.listdir('./plugins/%s' % (relpath))

        curdirname = relpath[relpath.rfind('/') + 1:]

        self.plugins = {}
        for node in nodes:
            fpath = './plugins/%s/%s' % (relpath, node)
            if os.path.isdir(fpath):
                self.loadPlugins('%s/%s' % (relpath, node))
                continue

            # look for a python file with the same name as the current directory 
            if node == 'main.py':
                ipath = 'plugins%s.%s' % (relpath.replace('/', '.'), 'main')
                print(ipath)
                mod = __import__(ipath, globals(), locals(), 'main')
                mplugins = mod.main.getPlugins()
                for p in mplugins:
                    self.plugins[p[0]] = p[1] 