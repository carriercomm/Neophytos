'''
	This module provides a curses output on systems that support it. If not
	it just places in a dummy proxy that does nothing. It could be extended
	to support other things. I suppose, and hope, maybe I can use it for a
	connection to a GUI front end.
	
	
	There are a few different modes the application can execute under:
		1. it does not use this module and outputs directly to the standard output
		2. it uses this module in curses mode
		3. it uses this module in standard output mode
		4. it uses this module in socket mode
		
	The 4th mode can be used in conjunction with any of the other modes. It provides
	a server socket that can accept connections and update the client on the status
	and bring them up to status on some things.
'''
import math
import os
import sys
import threading

try:
	import curses
	supported = True
except ImportError:
	supported = False
	
class stdoutwindow:
	def addstr(self, y, x, str):
		pass
	def getmaxyx(self):
		return (5, 5)
	def clrtoeol(self):
		pass
	def erase(self):
		pass
	def refresh(self):
		pass
class stdoutcurses:
	def initscr():
		return stdoutwindow()
	
title = ''
win = None
working = {}
__working = []
lock = threading.Lock()

class Working:
	pass
	
def IsSupported():
	global supported
	return supported

def __update():
	global win
	global working
	global __working
	global title
	
	if win is None:
		return
	
	my, mx = win.getmaxyx()
	
	win.erase()
	
	win.addstr(0, 0, title)
	win.clrtoeol()
	
	row = 1
	# draw items to screen
	x = 0
	while x < len(__working):
		if row >= my:
			break
		name = __working[x]
		x = x + 1
		work = working[name]
		if not work.old:
			win.addstr(row, 0, '@')
			if type(name) is str:
				txt = name
			else:
				txt = name.GetName()

			# if longer than 50 then grab start and end
			# which makes it easier to see paths and 
			# other things
			if len(txt) > 50:
				txt = '%s..%s' % (txt[0:24], txt[-24:])
				
			win.addstr(row, 1, txt[-50:])
			win.addstr(row, 52, work.status[-20:])
			# create progress bar
			value = work.progress
			#max = 20
			#value = int(max * value)
			#space = max - value
			#bar = '[%s%s]' % ('#' * value, ' ' * space)
			bar = '%s' % value
			win.addstr(row, 52 + 20 + 5, bar)
			row = row + 1
	x = 0
	while x < len(__working):
		if row >= my:
			break
		name = __working[x]
		x = x + 1
		work = working[name]
		if work.old:
			win.addstr(row, 0, ' ')
			if type(name) is str:
				txt = name
			else:
				txt = name.GetName()

			# if longer than 50 then grab start and end
			# which makes it easier to see paths and 
			# other things
			if len(txt) > 50:
				txt = '%s..%s' % (txt[0:24], txt[-24:])
			win.addstr(row, 1, txt[-50:])
			win.addstr(row, 52, work.status[-20:])
			# create progress bar
			value = work.progress
			#max = 20
			#value = int(max * value)
			#space = max - value
			#bar = '[%s%s]' % ('#' * value, ' ' * space)
			bar = '%s' % value
			win.addstr(row, 52 + 20 + 5, bar)
			row = row + 1
	win.refresh()
	
def Configure(tcpserver = False):
	# find and modify sys.argv
	mode = Modes.StandardConsole
	for arg in sys.argv:
		if arg == '--curses':
			mode = Modes.Curses
			sys.argv.remove(arg)
		if arg == '--std':
			mode = Modes.StandardConsole
			sys.argv.remove(arg)
	Init(mode, tcpserver = tcpserver)
	
class Modes:
	StandardConsole		= 1
	Curses				= 2

# os.devnull
def Init(mode, tcpserver = False, stdout = None, stderr = None):
	global win
	if mode == Modes.StandardConsole:
		stdout = sys.stdout
		stderr = sys.stderr
	if mode == Modes.Curses:
		if stdout is None:
			stdout = 'stdout'
		else:
			stdout = open(stdout, 'w')
		if stderr is None:
			stderr = 'stderr'
		else:
			stderr = open(stderr, 'w')
			
	# redirect to appropriate facility
	sys.stdout = stdout
	sys.stderr = stderr
	
	# initialize curses
	if mode == Modes.Curses:
		# use the real curses output
		win = curses.initscr()
	else:
		# use the fake curses output
		win = stdoutcurses.initscr()
	
def SetTitle(_title):
	global lock
	global title
	
	with lock:
		title = _title
	
def AddWorkingItem(name):
	global working
	global __working
	global lock
	
	with lock:	
		working[name] = Working()
		working[name].status = ''
		working[name].progress = 0.0
		working[name].old = False
		
		__working.insert(0, name)
		
		__update()

		while len(__working) > 100:
			x = len(__working) - 1
			while x > -1:
				_name = __working[x]
				x = x - 1
				
				if working[_name].old is True:
					__working.remove(_name)
					del working[_name]
					break
		
def Update():
	with lock:
		__update()

def SetCurrentStatus(name, status):
	global working
	global lock
	
	with lock:
		working[name].status = status
		__update()
	
def SetCurrentProgress(name, value):
	global working
	global lock
	
	with lock:
		working[name].progress = value
		__update()
	
def RemWorkingItem(name):
	global working
	global __working
	global lock
	
	with lock:
		working[name].old = True
		__update()
		
		while len(__working) > 100:
			x = len(__working) - 1
			while x > -1:
				_name = __working[x]
				x = x - 1
				
				if working[_name].old is True:
					__working.remove(_name)
					del working[_name]
					break