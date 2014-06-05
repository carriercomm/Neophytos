import client
import os
import os.path
import sys
import pprint
import re

def GetConfigPath():
	# build base path (without file)
	base = '%s/.neophytos' % os.path.expanduser('~')
	# ensure it is created
	if os.path.exists(base) is False:
		os.makedirs(base)
	# add on file
	path = '%s/config.py' % base
	return path
	
def __LoadConfig():
	path = GetConfigPath()
	if os.path.exists(path) is False:
		return {}
	fd = open(path, 'r')
	cfg = eval(fd.read())
	fd.close()
	return cfg
	
def LoadConfig():
	cfg = __LoadConfig()
	if cfg.get('remote-host', None) is None:
		cfg['remote-host'] = 'localhost'
		cfg['remote-port'] = 4322
		cfg['storage-auth-code'] = None
	cfg['paths'] = cfg.get('paths', {})
	return cfg

def cmd_config(args):
	if len(args) < 1:
		print('not enough arguments: <server-auth-code>')
		return
	
	sac = args[0]
	
	cfg = LoadConfig()
	cfg['storage-auth-code'] = sac
	SaveConfig(cfg)
	
def SaveConfig(cfg):
	path = GetConfigPath()
	fd = open(path, 'w')
	pprint.pprint(cfg, fd)
	fd.close()

def cmd_add(args):
	if len(args) < 2:
		print('not enough arguments: <name> <path>')
		return
		
	name = args[0]
	path = args[1]
	
	if os.path.exists(path) is False:
		print('path [%s] does not exist' % path)
	cfg = LoadConfig()
	
	if name in cfg['paths']:
		print('name [%s] already exists' % name)
		return
		
	cfg['paths'][name] = {}
	cfg['paths'][name]['disk-path'] = path
	cfg['paths'][name]['enabled'] = True
	cfg['paths'][name]['filter'] = ['.*']
	
	SaveConfig(cfg)
	
	print('added name [%s] with path [%s]' % (name, path))
	return
	
def cmd_del(args):
	if len(args) < 1:
		print('not enough arguments: <name>')
		return
	
	name = args[0]
	
	cfg = LoadConfig()
	
	if name not in cfg['paths']:
		print('name [%s] does not exist' % name)
		return
	
	path = cfg['paths'][name].get('disk-path', '<error>')
	
	del cfg['paths'][name]
	
	SaveConfig(cfg)
	
	print('deleted name [%s] with path [%s]' % (name, path))
	return
	
def cmd_disable(args):
	if len(args) < 1:
		print('not enough arguments: <name>')
		return
	
	name = args[0]
	
	cfg = LoadConfig()
	
	if name not in cfg['paths']:
		print('name [%s] does not exist' % name)
		return
		
	path = cfg['paths'][name].get('disk-path', '<error>')
		
	cfg['paths'][name]['enabled'] = False

	SaveConfig(cfg)
	
	print('disabled name [%s] with path [%s]' % (name, path))
	return
	
def cmd_enable(args):
	if len(args) < 1:
		print('not enough arguments: <name>')
		return
		
	name = args[0]
	
	cfg = LoadConfig()
	
	if name not in cfg['paths']:
		print('name [%s] does not exist' % name)
		return
		
	path = cfg['paths'][name].get('disk-path', '<error>')
	
	cfg['paths'][name]['enabled'] = True
	
	SaveConfig(cfg)
	
	print('enabled name [%s] with path [%s]' % (name, path))
	return
	
def cmd_addfilter(args):
	if len(args) < 2:
		print('not enough arguments: <name> <pattern>')
		return
	
	name = args[0]
	pattern = args[1]
	
	cfg = LoadConfig()
	
	if name not in cfg['paths']:
		print('name [%s] does not exist' % name)
		return
	
	cfg['paths'][name]['filter'].append(pattern)
	
	SaveConfig(cfg)
	print('added to name [%s] pattern [%s]' % (name, pattern))
	return
	
def cmd_delfilter(args):
	if len(args) < 1:
		print('not enough arguments:')
		print('		<name>				- will list pattern with index')
		print('		<name> <index>		- will delete pattern at index')
		return
		
	cfg = LoadConfig()
		
	name = args[0]
	
	if name not in cfg['paths']:
		print('name [%s] does not exist' % name)
		return
	
	if len(args) < 2:
		print('== LISTING PATTERNS ==')
		# list patterns
		ndx = 0
		for p in cfg['paths'][name]['filter']:
			print('		%02i: [%s]' % (ndx, p))
			ndx = ndx + 1
		return
	
	index = int(args[1])
	
	removed = False
	ndx = 0
	for p in cfg['paths'][name]['filter']:
		if ndx == index:
			cfg['paths'][name]['ipatterns'].remove(p)
			print('removed from name [%s] pattern [%s] at index [%s]' % (name, p, index))
			SaveConfig(cfg)
			return
		ndx = ndx + 1
	print('could not find index [%s]' % index)
	return
	
def dobackup(name, rhost, rport, sac, cfg, dpath, filter, base = None, c = None):
	if c is None:
		print('CONNECTING TO REMOTE SERVER')
		c = client.Client2(rhost, rport, bytes(sac, 'utf8'))
		c.Connect()
		print('CONNECTION ESTABLISHED, SECURED, AND AUTHENTICATED')
		
	if base is None:
		base = dpath
	nodes = os.listdir(dpath)
	for node in nodes:
		fpath = '%s/%s' % (dpath, node)
		# if directory..
		if os.path.isdir(fpath):
			dobackup(fpath, rhost, rport, sac, cfg, fpath, filter, base, c)
			continue
		# run filters
		for f in filter:
			notmatch = False
			if f[0] == '!':
				# match if does not match filter
				notmatch = True
				f = f[1:]
			# do regular expression matching
			_fpath = fpath[len(base):]
			result = re.match(f, _fpath)
			if notmatch:
				if result is not None:
					continue
			else:
				if result is None:
					continue
			# backup the file
			print('PROCESSING [%s]' % _fpath)
			# fpath
			lfile = fpath
			print('name', name)
			fid = (bytes('%s/%s' % (name, _fpath), 'utf8'), 0)
			c.FilePatch(fid, lfile)
	
def __cmd_run_target(cfg, name, target):
	print('running [%s]' % name)
	
	dpath = target['disk-path']
	filter = target['filter']
	
	rhost = cfg['remote-host']
	rport = cfg['remote-port']
	sac = cfg['storage-auth-code']
	dobackup(name = name, rhost = rhost, rport = rport, sac = sac, cfg = cfg, dpath = dpath, filter = filter)
	return
	
def cmd_run(args, dry = True):
	cfg = LoadConfig()

	if cfg['storage-auth-code'] is None:
		print('   Opps.. you need to do <program> config <server-auth-code>')
		print('')
		print('   The server auth code serves as your username and password.')
		print('')
		print('   You can get one from: http://www.kmcg341.net/neophytos')
		return
	
	if len(args) > 0:
		# treat as list of targets to run (run them even if they are disabled)
		for target in args:
			if target not in cfg['paths']:
				print('    target by name [%s] not found' % target)
			else:
				__cmd_run_target(cfg, target, cfg['paths'][target])
		return
	# run all that are enabled
	for k in cfg['paths']:
		__cmd_run_target(cfg, k, cfg['paths'][k])
	return
	
def __cmd_list_showfilter(filter):
	ndx = 0
	for p in filter:
		print('    %02i: [%s]' % (ndx, p))
		ndx = ndx + 1
	
def cmd_list(args):
	if len(args) > 0:
		name = args[0]
	else:
		name = None
	
	cfg = LoadConfig()
	
	if name is not None:
		# display information about name		
		print('== %s ==' % name)
		print('    disk-path: %s' % cfg[name]['disk-path'])
		__cmd_list_showfilter(cfg['paths'][name]['filter'])

	if len(cfg['paths']) < 1:
		print('nothing to list, try:')
		print('  add a new backup path:    <program> add <name> <path>')
		print('  display help:             <program>')
		return
	
	for k in cfg['paths']:
		print('== %s ==' % k)
		print('    disk-path: %s' % cfg['paths'][k]['disk-path'])
		__cmd_list_showfilter(cfg['paths'][k]['filter'])		
	return

def showhelp():
	print('config	- configures the remote server')
	print('add		- add backup path')
	print('del		- delete backup path')
	print('disable		- disable backup path')
	print('enable		- enable backup path')
	print('add-filter	- add inclusive filter')
	print('del-filter	- delete filter')
	print('dry-run		- pretend to do backup')
	print('run		- run all enabled or specified backup')
	print('list		- list backup paths or filters for specified')
	print('	Example:')
	print('		<program> add <name> <path>')
	print('		<program> del <name>')
	print('		<program> disable <name>')
	print('		<program> enable <name>')
	print('		<program> add-inc-filter [displays help]')
	print('		<program> add-exc-filter [displays help]')
	print('		<program> del-filter [displays help]')
	print('		<program> dry-run <(optional)name> <(optional)name> ...')
	print('		<program> run <(optional)name> <(optional)name> ...')
	print('		<program> list <(optional)name>')
	
def main(args):
	if len(args) < 1:
		return showhelp()
	if args[0] == 'add':
		return cmd_add(args[1:])
	if args[0] == 'del':
		return cmd_del(args[1:])
	if args[0] == 'disable':
		return cmd_disable(args[1:])
	if args[0] == 'enable':
		return cmd_enable(args[1:])
	if args[0] == 'add-filter':
		return cmd_addfilter(args[1:])
	if args[0] == 'del-filter':
		return cmd_delfilter(args[1:])
	if args[0] == 'dry-run':
		return cmd_run(args[1:], dry = True)
	if args[0] == 'run':
		return cmd_run(args[1:], dry = False)
	if args[0] == 'list':
		return cmd_list(args[1:])
	if args[0] == 'config':
		return cmd_config(args[1:])
	print('unknown command')
		
main(sys.argv[1:])