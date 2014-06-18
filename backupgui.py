'''
	This implements a client GUI.
'''
import os
import os.path
import sys
import backup
from PyQt4 import QtGui
from PyQt4 import QtCore
import io
import os.path
import pprint
import status
import threading
import time
import types
import subprocess

def ChangeStyle(widget, name):
	widget.setObjectName(name)
	widget.style().polish(widget)

class ClientInterface:
	'''
		The following functions form an textual stream interface between the
		backup command line utility. I got down and thought hard about making
		a more Python interface since I am importing backup, but I decided this
		might actually be more flexible in allowing us to interface with things
		not written in Python. We would of course be unable to import it and have
		to call it directly using subprocess, but we could still parse it's
		output like we do below.
		
		I am considering moving this section into a separate module that could be
		dynamically specified by the client we are using. So backup.py would specify
		a backup_comm.py file which including doing everything needed to return
		the data. Basically, backup_comm.py would implement the interface below.
	'''
	def GetTargets(account):
		out = ClientInterface.ConsoleCommand([account, 'list'])
		lines = out.split('\n')
		targets = {}
		for line in lines:
			if line.find('==') == 0:
				name = line[line.find(' ') + 1:line.rfind(' ')]
				target = {}
				filters = []
				
				targets[name] = target
				target['filter'] = filters
			if line.find('    ') == 0:
				line = line.strip()
				if line.find('disk-path:') == 0:
					diskpath = line[line.find(' ') + 1:]
					target['disk-path'] = diskpath
				elif line.find('enabled:') == 0:
					target['enabled'] = line[line.find(':') + 1:].strip()
				else:
					filterndx = int(line[0:line.find(':')])
					filter = eval(line[line.find('[') + 1:line.find(']')])
					filters.append(filter)
		return targets
	
	def GetAccounts():
		out = ClientInterface.ConsoleCommand(['list'])
		lines = out.split('\n')
		accounts = []
		for line in lines:
			if line.find('    ') == 0:
				accounts.append(line.strip())
		return accounts
		
	def ConsoleCommand(cmd):
		ca = backup.ConsoleApplication()
		oldstdout = sys.stdout
		buf = io.StringIO()
		sys.stdout = buf
		ca.main(cmd)
		sys.stdout = oldstdout
		buf.seek(0)
		return buf.read()
		
	def GetConfigPath(self):
		# build base path (without file)
		base = self.GetConfigBase()
		# add on file
		path = '%s/%s.py' % (base, self.accountname)
		return path
		
	def GetConfigBase():
		base = '%s/.neophytos/accounts' % os.path.expanduser('~')
		if os.path.exists(base) is False:
			os.makedirs(base)
		return base

	def GetServiceConfig(account):
		base = ClientInterface.GetConfigBase()
		fpath = '%s/%s.service.py' % (base, account)
		if os.path.exists(fpath) is False:
			return None
		fd = open(fpath, 'r')
		py = fd.read()
		fd.close()
		return eval(py)
		
	def SaveServiceConfig(account, cfg):
		base = ClientInterface.GetConfigBase()
		fpath = '%s/%s.service.py' % (base, account)
		fd = open(fpath, 'w')
		pprint.pprint(fd, cfg)
		fd.close()

class QCompactLayout():
	def __init__(self, horizontal = True, defxpad = 5, defypad = 5):
		self.widgets = []
		self.horizontal = horizontal
		self.parent = None
		self.defxpad = defxpad
		self.defypad = defypad
	
	def SetParent(self, parent):
		# if we had a parent set...
		if self.parent is not None:
			# if our parent had us set as the layout..
			if self.parent.xlayout is self:
				# remove ourselves..
				self.parent.xlayout = None
		self.parent = parent
		parent.xlayout = self
		
	def AddLayout(self, layout):
		dframe = QtGui.QFrame(self.parent)
		self.AddWidget(dframe)
		layout.SetParent(dframe)
		layout.MigrateWidgetsTo(dframe)
		
	def MigrateWidgetsTo(self, towidget):
		for widget in self.widgets:
			widget.setParent(towidget)
		
	def AddWidget(self, widget):
		self.widgets.append(widget)
	
	def Do(self):
		i = 0
		cx = 0
		cy = 0
		mx = 0
		my = 0
		while i < len(self.widgets):
			w = self.widgets[i]
			if hasattr(w, 'xlayout'):
				w.xlayout.Do()
			w.move(cx, cy)
			if self.horizontal:
				if hasattr(w, 'xpadding'):
					cx = cx + w.xpadding
				cx = cx + w.width() + self.defxpad
				if w.height() > my:
					my = w.height()
			else:
				cy = cy + w.height() + self.defypad
				if w.width() > mx:
					mx = w.width()
			i = i + 1
		if self.horizontal:
			self.parent.resize(cx, my)
			return (cx, my)
		self.parent.resize(mx, cy)
		return (mx, cy)
		
class HandlerAction(QtGui.QAction):
	def __init__(self, icon, text, parent, handler, arg):
		QtGui.QAction.__init__(self, icon, text, parent)
		self.triggered.connect(lambda : handler(*arg))
				
def DumpObjectTree(obj, space = ''):
	print('%s%s [%s]' % (space, obj, obj.objectName()))
	for child in obj.children():
		if isinstance(obj, QtGui.QWidget):
			DumpObjectTree(child, space = '%s ' % space)
			
class QLabelWith(QtGui.QFrame):
	def __init__(self, parent, label, widget):
		self.init = False
		super().__init__(parent)
		self.xlabel = QtGui.QLabel(self)
		self.xwidget = widget
		widget.setParent(self)
		self.xlabel.setText(label)
		self.init = True
	def label(self):
		return self.xlabel
	def widget(self):
		return self.xwidget
	def size(self):
		self.xlabel.move(0, 3)
		self.xwidget.move(self.xlabel.width() + 5, 0)
		if self.xlabel.height() > self.xwidget.height():
			h = self.xlabel.height()
		else:
			h = self.xwidget.height()
		self.resize(self.xlabel.width() + self.xwidget.width() + 5, h)
	def event(self, event):
		# yes.. very very evil.. but for gods
		# sake at least it gets a final width
		# and height on the label and is able
		# to position the widgets properly
		if self.init:
			self.size()
		return True
'''

	Account: [edittable drop down populated]    Authorization Code:[authorization code]
	Target: [editbox for target name]
	Path: [button to browse for path] [editbox for disk-path]
	Filters: [editbox with string to check filters against (for testing)]
			 [listbox with filters in order][vertical line of buttons for moving up/down/delete/add][each line is editable]
	
	[button to save] [button to discard]
'''
class QTargetEditor(QtGui.QDialog):
	def __init__(self, account = None, target = None):
		super().__init__()
		
		self.resize(10, 10)
		icon = QtGui.QIcon('./media/edit.ico')
		self.setWindowIcon(icon)

		self.setWindowTitle('Edit Entry')
		
		# create controls
		editAccount = QLabelWith(self, 'Account:', QtGui.QComboBox())
		editAccount.widget().setMinimumContentsLength(20)
		editAccount.widget().setEditable(True)
		
		editAuth = QLabelWith(self, 'Authorization Code:', QtGui.QLineEdit())
		editAuth.widget().setFixedWidth(200)
		
		editTarget = QLabelWith(self, 'Target:', QtGui.QComboBox())
		editTarget.widget().setMinimumContentsLength(20)
		editTarget.widget().setEditable(True)

		editPath = QLabelWith(self, 'Path:', QtGui.QLineEdit())
		editPath.widget().setFixedWidth(150)
		btnPath = QtGui.QPushButton(self)					# display path selection dialog
		btnPath.setText('Browse For Path')
		
		#labelFilter = QtGui.QLabel('Filter:', self)
		#labelFilterTest = QtGui.QLineEdit(self) 			# on change re-test with filter
		
		editFilterTest = QLabelWith(self, 'Test:', QtGui.QLineEdit())
		editFilterTest.widget().setFixedWidth(250)
		
		listFilter = QtGui.QTableWidget(self)				# on change re-test the test string
		#btnFilterAdd = QtGui.QPushButton('Add', self)
		#btnFilterDel = QtGui.QPushButton('Del', self)
		#btnFilterUp = QtGui.QPushButton('Up', self) 
		#btnFilterDown = QtGui.QPushButton('Down', self)
		
		
		
		#btnSave = QtGui.QPushButton(self)
		#btnCancel = QtGui.QPushButton(self)
		
		# place controls
		lv0 = QCompactLayout(horizontal = False)
		lv0.SetParent(self)
		
		lh1 = QCompactLayout(horizontal = True)
		lh1.AddWidget(editAccount)
		lh1.AddWidget(editAuth)
		
		lh2 = QCompactLayout(horizontal = True)
		lh2.AddWidget(editTarget)
		lh2.AddWidget(editPath)
		lh2.AddWidget(btnPath)
		
		#lv2 = QCompactLayout(horizontal = False)
		#lv2.AddWidget(btnFilterAdd)
		#lv2.AddWidget(btnFilterDel)
		#lv2.AddWidget(btnFilterUp)
		#lv2.AddWidget(btnFilterDown)
		
		lh3 = QCompactLayout(horizontal = True)
		lh3.AddWidget(listFilter)
		#lh3.AddLayout(lv2)
		
		lv0.AddLayout(lh1)
		lv0.AddLayout(lh2)
		lv0.AddWidget(editFilterTest)
		lv0.AddLayout(lh3)
		
		lv0.Do()
		
		self.lv0 = lv0
		
		def menuAdd(self):
			pass
			
		def menuDelete(self):
			pass

		def __contextMenuEvent(self, event):
			# i just like the style of building the menu when needed
			if self.menu is None:
				self.menu = QtGui.QMenu(self)
				self.menu2.addAction(HandlerAction(QtGui.QIcon(), 'Add New Target', self.menu, menuAdd, (self,)))
				self.menu.addAction(HandlerAction(QtGui.QIcon(), 'Delete', self.menu, menuDelete, (self,)))
				
				self.menu2 = QtGui.QMenu(self)
				self.menu2.addAction(HandlerAction(QtGui.QIcon(), 'Add New Target', self.menu, menuAdd, (self,)))
				
			# get the item then the row
			item = self.itemAt(event.x(), event.y())
			# no item was under cursor so exit
			if item is None:
				# execute menu 2 instead
				self.menu2.exec(event.globalPos())
				return
			self.__row = item.row()
			
			self.menu.exec(event.globalPos())

		listFilter.menu = None
		listFilter.contextMenuEvent = types.MethodType(__contextMenuEvent, listFilter)
		
		listFilter.setColumnCount(3)
		listFilter.setHorizontalHeaderLabels(['Invert', 'Type', 'Expression'])
		
		listFilter.resize(500, 100)
		
		# populate account combo box with accounts
		self.bku = backup.ConsoleApplication()
		configs = self.bku.GetConfigs()
		
		for config in configs:
			editAccount.widget().insertItem(0, config)
			
		def actionAccountTextChanged(self, text):
			print('account', self, text)
			# is this a valid account
			bku = self.bku
			
			configs = bku.GetConfigs()
			existing = False
			if text in configs:
				if text.lower() == text:
					existing = True
			
			if existing:
				ChangeStyle(self.editAccount.widget(), 'EditValid')
			else:
				ChangeStyle(self.editAccount.widget(), 'EditInvalid')
			
			# populate
			cpath = bku.GetConfigPath(account = text)
			
			# remove all items in target combobox
			while self.editTarget.widget().count() > 0:
				self.editTarget.widget().removeItem(0)
			
			if os.path.exists(cpath):
				fd = open(cpath, 'r')
				cfg = eval(fd.read())
				fd.close()
				
				paths = cfg['paths']
							
				# add new targets
				for path in paths:
					self.editTarget.widget().insertItem(0, path)
			
			actionTargetTextChanged(self, self.editTarget.widget().currentText())
			
		def actionTargetTextChanged(self, text):
			print('target', self, text)
			
			bku = self.bku
			
			cpath = bku.GetConfigPath(account = self.editAccount.widget().currentText())
			
			# load
			exists = False
			if os.path.exists(cpath):
				fd = open(cpath, 'r')
				cfg = eval(fd.read())
				fd.close()
				if self.editTarget.widget().currentText() in cfg['paths']:
					exists = True
					# also just grab the target meta-data too while we are at it
					target = cfg['paths'][self.editTarget.widget().currentText()]
			
			
			if exists:
				ChangeStyle(self.editTarget.widget(), 'EditValid')
				
				# populate other controls with data
				self.editPath.widget().setText(target['disk-path'])
			else:
				ChangeStyle(self.editTarget.widget(), 'EditInvalid')
				
		'''
			More eye-candy...
		'''
		def actionDiskPathChanged(self, text):
			if os.path.exists(text) and os.path.isdir(text):
				ChangeStyle(self.editPath.widget(), 'EditValid')
			else:
				ChangeStyle(self.editPath.widget(), 'EditInvalid')
		
		editAccount.widget().editTextChanged.connect(lambda text: actionAccountTextChanged(self, text))
		editTarget.widget().editTextChanged.connect(lambda text: actionTargetTextChanged(self, text))
		editPath.widget().textChanged.connect(lambda text: actionDiskPathChanged(self, text))
			
		self.show()
		
		self.editAccount = editAccount
		self.editTarget = editTarget
		self.editPath = editPath
		self.listFilter = listFilter
		
		#self.setObjectName('Apple')
		#editAccount.setObjectName('Apple')
		#editAccount.widget().setObjectName('Apple')
		
		fd = open('./media/client.css', 'r')
		cssdata = fd.read()
		fd.close()
		self.setStyleSheet(cssdata)
		
		actionAccountTextChanged(self, editAccount.widget().currentText())
		
		self.style().polish(editAccount.widget())
		
		#style()->unpolish(theWidget);
		#style()->polish(theWidget);
		
	#def resize(self, w, h):
	#	super().resize(w, h)
	#	print('called resize', w, h)
		
	def event(self, e):
		if type(e) is QtGui.QPaintEvent:
			self.lv0.Do()
		return super().event(e)
		# end-of-function
		
class QAccountsAndTargetSystem(QtGui.QFrame):
	def __init__(self, parent):
		QtGui.QFrame.__init__(self, parent)
		self.Create()
	
	def GetTableRow(self, row):
		out = []
		colcnt = self.table.columnCount()
		for x in range(0, colcnt):
			item = self.table.item(row, x)
			out.append(item)
		return out
		
	def SetTableRow(self, table, row, items):
		for x in range(0, len(items)):
			# just skip this column (dont update it)
			if items[x] is None:
				continue
			item = table.item(row, x)
			# this should be an QTableWidgetItem
			if type(items[x]) is not str:
				print('not str')
				# treat it is QTableWidgetItem
				table.setItem(row, x, items[x])
				continue
			if item is None:
				item = QtGui.QTableWidgetItem()
				table.setItem(row, x, item)
			# should be a string type
			item.setText(items[x])
	
	def Create(self):
		accounts = ClientInterface.GetAccounts()
		
		self.panels = {}
	
		table = QtGui.QTableWidget(self)
		self.table = table
		
		table.setObjectName('StatusTable')
		
		split = QtGui.QSplitter(self)
		self.split = split
		
		#DumpObjectTree(self)
		
		# enabled, account, target, path, bytesout, bytesin, status, progress
		table.setColumnCount(5)
		table.setHorizontalHeaderLabels(['Enabled', 'Account', 'Target', 'Path', 'Next Run'])
		
		for account in accounts:
			targets = ClientInterface.GetTargets(account)
			for target in targets:
				cfg = targets[target]
				acctarname = '%s.%s' % (account, target)
				
				scfg = ClientInterface.GetServiceConfig(account)
				if scfg is not None and target in scfg:
					nrt = '8hrs 5min'
				else:
					nrt = 'Manual Only'
				
				table.insertRow(0)
				self.SetTableRow(table, 0, (
					cfg['enabled'],
					account, target,
					cfg['disk-path'],
					nrt
				))
		
		stable = QtGui.QTableWidget(self)
		self.stable = stable
		stable.setObjectName('StatusTable')
		stable.setColumnCount(6)
		stable.setHorizontalHeaderLabels(['User', 'Account', 'Target', 'Queue', 'Up/MB/Sec', 'Complete'])
		stable.setVerticalHeaderLabels(['', ''])
		stable.resizeColumnsToContents()
		
		# disable editing
		table.setEditTriggers(QtGui.QAbstractItemView.NoEditTriggers)
		stable.setEditTriggers(QtGui.QAbstractItemView.NoEditTriggers)
		
		table.setVerticalHeaderLabels(['', ''])
		table.resizeColumnsToContents()
		
		def menuPush(self):
			# push the target on specified account
			python = sys.executable

			account = self.item(self.__row, 1).text()
			target = self.item(self.__row, 2).text()
			
			fnull = open(os.devnull, 'w')
			subprocess.Popen((python, 'backup.py', account, 'push', target), stdout = fnull, stderr = fnull)
			print('executed push with account:%s target:%s' % (account, target))
		
		def menuEdit(self):
			pass
		def menuAddNew(self):
			n = QTargetEditor()
			# create reference or garbage collector will
			# release it and it will disappear
			self.n = n
			# make sure it is displayed
			n.show()
			
			print('created new')
			
		def menuDelete(self):
			pass
		
		def __contextMenuEvent(self, event):
			# i just like the style of building the menu when needed
			if self.menu is None:
				self.menu = QtGui.QMenu(self)
				self.menu.addAction(HandlerAction(QtGui.QIcon(), 'Edit', self.menu, menuEdit, (self,)))
				self.menu.addAction(HandlerAction(QtGui.QIcon(), 'Push (Backup)', self.menu, menuPush, (self,)))
				self.menu.addAction(HandlerAction(QtGui.QIcon(), 'Add New Target', self.menu, menuAddNew, (self,)))
				self.menu.addAction(HandlerAction(QtGui.QIcon(), 'Delete', self.menu, menuDelete, (self,)))
				
				self.menu2 = QtGui.QMenu(self)
				self.menu2.addAction(HandlerAction(QtGui.QIcon(), 'Add New Target', self.menu, None, (self,)))
				
			# get the item then the row
			item = self.itemAt(event.x(), event.y())
			# no item was under cursor so exit
			if item is None:
				# execute menu 2 instead
				self.menu2.exec(event.globalPos())
				return
			self.__row = item.row()
			
			self.menu.exec(event.globalPos())

		table.menu = None
		table.contextMenuEvent = types.MethodType(__contextMenuEvent, table)
		
		split.setOrientation(2)
		split.addWidget(table)
		split.addWidget(stable)
				
		self.show()
		
		scantimer = QtCore.QTimer(self)
		self.scantimer = scantimer
		scantimer.timeout.connect(lambda : QAccountsAndTargetSystem.PeriodicScanUpdate(self))
		scantimer.start(5000)
		
		scanthread = threading.Thread(target = QAccountsAndTargetSystem.PeriodicScanThreadEntry, args = (self,))
		scanthread.daemon = True
		self.scanthread = scanthread
		scanthread.start()
	
	'''
		This uses the data maintained by the periodic scan thread
		to keep the table up to date.
	'''
	def PeriodicScanUpdate(self):
		# access copy of services dict, the thread
		# will create a new dict and set it then
		# never touch it so this should be quite
		# safe and does not need a lock
		services = self.services
		stable = self.stable
		
		for port in services:
			service = services[port]
			title = service['title']
			work = service['work']
			# just ignore it if it does not report the account
			if 'account' not in title:
				continue
			user = title['user']
			account = title['account']
			target = title['target']
			filecount = float(title['filecount'])
			donecount = float(title['filedonecount'])
			
			# find row if it exists and update it
			frow = None
			for row in range(0, stable.rowCount()):
				t_user = stable.item(row, 0).text()
				t_account = stable.item(row, 1).text()
				t_target = stable.item(row, 2).text()
				
				if t_user == user and t_account == account and t_target == target:
					frow = row
					break
			
			# if row does not exist then create it
			if frow is None:
				frow = 0
				stable.insertRow(0)
				self.SetTableRow(stable, 0, (
					user,
					account, target,
					'',				# work item count
					''				# throughput
				))
				
				# create a progress bar for eye candy
				pb = QtGui.QProgressBar()
				pb.setObjectName('StatusCellProgressBar')
				pb.setRange(0.0, 100.0)
				pb.setValue(0.0)
				stable.setCellWidget(0, 5, pb)
				
			workcount = 0
			for wname in work:
				witem = work[wname]
				if 'old' in witem and witem['old'] is False:
					workcount = workcount + 1
					
			stable.item(frow, 3).setText('%s' % workcount)
			stable.item(frow, 4).setText('%.03f:%.03f' % (float(title['outmb']), float(title['totoutmb'])))
			stable.cellWidget(frow, 5).setValue((donecount / filecount) * 100.0)
			# if we are dealing with LOTS of rows this might 
			# get slow and CPU hungry, but I doubt 99% of
			# the things using this will be that hungry..
			stable.resizeColumnsToContents()
		
	def PeriodicScanThreadEntry(self):
		# initial the status query object
		q = status.StatusQuery()
		while True:
			# scan for running services
			#print('scanning')
			services = q.Scan()
			self.services = services
			#print('done scanning')
			# iterate through services found
			for port in services:
				service = services[port]
				title = service['title']
				if 'account' not in title:
					continue
				title = service['title']
				account = title['account']
				target = title['target']
				# try to find the row that matches this running service, we might
				# not find one if it is running under a different user account and
				# if so we can just add a row
				#print(title, account)
			time.sleep(5)
		
	def resizeEvent(self, event):
		#table = self.table	
		#rect = table.visualItemRect(table.item(0, table.columnCount() - 1))
		#w = rect.x() + rect.width() + 20
		#table.resize(self.width(), self.height())
		split = self.split
		
		self.split.resize(self.width(), self.height())
	
	def resize(self, w, h):
		super().resize(w, h)
		
	def show(self):
		super().show()
				
				
class QStatusWindow(QtGui.QMainWindow):
	def resizeEvent(self, event):
		self.fAccountsAndTargets.resize(self.width(), self.height())

	def resize(self, w, h):
		super().resize(w, h)
		
	def __init__(self):
		QtGui.QMainWindow.__init__(self)
		
		fd = open('./media/client.css', 'r')
		cssdata = fd.read()
		fd.close()
		self.setStyleSheet(cssdata)
		
		icon = QtGui.QIcon('./media/book.ico')
		self.setWindowIcon(icon)
	
		self.fAccountsAndTargets = QAccountsAndTargetSystem(self)
		self.fAccountsAndTargets.resize(self.width(), self.height())

		self.resize(700, 340)
		self.move(400, 20)
		self.setWindowTitle('Neophytos Backup Status')
		self.show()
		
def main():
	app = QtGui.QApplication(sys.argv)
	# Cleanlooks
	# Plastique
	# Motfif
	# CDE
	style = QtGui.QStyleFactory.create('Plastique')
	app.setStyle(style)

	w = QStatusWindow()
				
	sys.exit(app.exec_())
	
main()