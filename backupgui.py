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

def CloneComboBox(w):
	n = QtGui.QComboBox()
	for i in range(0, w.count()):
		text = w.itemText(i)
		# insert onto end of list to maintain same index
		n.insertItem(n.count(), text)
	# select the same item as the original
	n.setCurrentIndex(w.currentIndex())
	return n
	
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
		self.dbg = False
	
	def SetParent(self, parent):
		# if we had a parent set...
		if self.parent is not None:
			# if our parent had us set as the layout..
			if self.parent.xlayout is self:
				# remove ourselves..
				self.parent.xlayout = None
		self.parent = parent
		parent.xlayout = self
	
	def rhcolor(self):
		import random
		r = random.randint(0, 255)
		g = random.randint(0, 255)
		b = random.randint(0, 255)
		
		return '%02x%02x%02x' % (r, g, b)
	
	def AddLayout(self, layout):
		dframe = QtGui.QFrame(self.parent)
		self.AddWidget(dframe)
		layout.SetParent(dframe)
		layout.MigrateWidgetsTo(dframe)
		
	def GetLayoutParent(self):
		return self.parent
		
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
		# BUG: work around for a bug.. i think it sets it to like 1800
		#      at first then later sets it to the correct value, but for
		#      some reason the window gets stuck -- this might be because
		#      this function is being called from the event loop...
		if mx > 1000:
			mx = 1000
		if self.dbg:
			pass
			#	print('@@@@ mx:%s type:%s' % (mx, type(mx)))
			#mx = 650
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
		
		self.editRemoteHost = QLabelWith(self, 'Remote-Host:', QtGui.QLineEdit())
		self.editRemoteHost.widget().setFixedWidth(100)
		self.editRemotePort = QLabelWith(self, 'Remote-Port:', QtGui.QLineEdit())
		self.editRemotePort.widget().setFixedWidth(50)
		self.editSSL = QLabelWith(self, 'SSL:', QtGui.QComboBox())
		self.editEnabled = QLabelWith(self, 'Enabled:', QtGui.QComboBox())
		
		self.editEnabled.widget().insertItem(0, 'True')
		self.editEnabled.widget().insertItem(1, 'False')
		self.editEnabled.widget().setMinimumContentsLength(10)
		
		self.editSSL.widget().insertItem(0, 'True')
		self.editSSL.widget().insertItem(1, 'False')
		self.editSSL.widget().setMinimumContentsLength(10)
		
		editTarget = QLabelWith(self, 'Target:', QtGui.QComboBox())
		editTarget.widget().setMinimumContentsLength(20)
		editTarget.widget().setEditable(True)

		editPath = QLabelWith(self, 'Path:', QtGui.QLineEdit())
		editPath.widget().setFixedWidth(150)
		btnPath = QtGui.QPushButton(self)					# display path selection dialog
		btnPath.setText('Browse For Path')
		
		def actionPathButtonClicked(self):
			folder = QtGui.QFileDialog.getExistingDirectory()
			self.editPath.widget().setText(folder)
		
		btnPath.clicked.connect(lambda : actionPathButtonClicked(self))
		#labelFilter = QtGui.QLabel('Filter:', self)
		#labelFilterTest = QtGui.QLineEdit(self) 			# on change re-test with filter
		
		editFilterTest = QLabelWith(self, 'Test:', QtGui.QLineEdit())
		editFilterTest.widget().setFixedWidth(250)
		
		btnFilterTest = QtGui.QPushButton(self)
		btnFilterTest.setText('Browse For Test File')
		
		def actionFilterTestButtonClicked(self):
			file = QtGui.QFileDialog.getOpenFileName()
			self.editFilterTest.widget().setText(file)
		
		btnFilterTest.clicked.connect(lambda : actionFilterTestButtonClicked(self))
		
		listFilter = QtGui.QTableWidget(self)				# on change re-test the test string
		listFilter.setObjectName('FilterTable')		
		
		btnSave = QtGui.QPushButton(self)
		btnSave.setText('Save')
		btnCancel = QtGui.QPushButton(self)
		btnCancel.setText('Cancel')
		
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
		
		lh4 = QCompactLayout(horizontal = True)
		lh4.AddWidget(editFilterTest)
		lh4.AddWidget(btnFilterTest)
		lh4.AddWidget(self.editSSL)
		
		lh3 = QCompactLayout(horizontal = True)
		lh3.AddWidget(listFilter)
		#lh3.AddLayout(lv2)
		
		lh5 = QCompactLayout(horizontal = True)
		lh5.AddWidget(btnSave)
		lh5.AddWidget(btnCancel)
		
		lh6 = QCompactLayout(horizontal = True)
		lh6.AddWidget(self.editRemoteHost)
		lh6.AddWidget(self.editRemotePort)
		lh6.AddWidget(self.editEnabled)
		
		lv0.AddLayout(lh1)
		lv0.AddLayout(lh6)
		lv0.AddLayout(lh2)
		lv0.AddLayout(lh4)
		lv0.AddLayout(lh3)
		lv0.AddLayout(lh5)
		#lv0.dbg = True
		
		#lh6.GetLayoutParent().setStyleSheet('border-style: inset;')
		
		lv0.Do()
		
		self.lv0 = lv0
		
		def menuAdd(self):
			ftable = self.listFilter
			
			row = ftable.rowCount()
			ftable.setRowCount(row + 1)
			
			self.listFilter.init = True
			
			# provide the choice of inversion
			w = QtGui.QComboBox()
			w.currentIndexChanged.connect(lambda text: actionFilterTestTextChanged(self, None))
			w.insertItem(0, 'False')
			w.insertItem(0, 'True')
			ftable.setCellWidget(row, 0, w)
			
			# provide the choice of type
			w = QtGui.QComboBox()
			w.currentIndexChanged.connect(lambda text: actionFilterTestTextChanged(self, None))
			for ftype in ('repattern', 'sizegreater', 'sizelesser', 'mode'):
				w.insertItem(0, ftype)
			ftable.setCellWidget(row, 1, w)
			
			# set the expression
			item = QtGui.QTableWidgetItem()
			item.setText('%s' % '^$')
			ftable.setItem(row, 2, item)
			self.listFilter.init = False
			
		def menuDelete(self):
			self.listFilter.removeRow(self.listFilter.__row)
			
		def menuUp(self, up = True):
			saved = []
			row = self.listFilter.__row
			for col in range(0, self.listFilter.columnCount()):
				w = self.listFilter.cellWidget(row, col)
				if w is not None:
					#self.listFilter.setCellWidget(row, col, QtGui.QWidget())
					saved.append((0, CloneComboBox(w)))
					continue
				i = self.listFilter.item(row, col)
				if i is None:
					saved.append((3, None))
					continue
				i = i.text()
				saved.append((1, i))
			self.listFilter.removeRow(self.listFilter.__row)
			
			if up:
				row = row - 1
			else:
				row = row + 1
				
			self.listFilter.insertRow(row)
			for col in range(0, len(saved)):
				if saved[col][0] == 0:
					print('setting widget row:%s col:%s widget:%s' % (row, col, saved[col][1]))
					self.listFilter.setCellWidget(row, col, saved[col][1])
					continue
				print('setting item row:%s col:%s item:%s' % (row, col, saved[col][1]))
				i = QtGui.QTableWidgetItem()
				i.setText(saved[col][1])
				self.listFilter.setItem(row, col, i)
			
			# this will cause the filter to be reapplied
			actionFilterTestTextChanged(self)
			
		def menuDown(self):
			menuUp(self, up = False)

		def __contextMenuEvent(self, event):
			# i just like the style of building the menu when needed
			if self.listFilter.menu is None:
				self.listFilter.menu = QtGui.QMenu(self)
				self.listFilter.menu.addAction(HandlerAction(QtGui.QIcon(), 'Add New', self.listFilter.menu, menuAdd, (self,)))
				self.listFilter.menu.addAction(HandlerAction(QtGui.QIcon(), 'Delete', self.listFilter.menu, menuDelete, (self,)))
				self.listFilter.menu.addAction(HandlerAction(QtGui.QIcon(), 'Move Up', self.listFilter.menu, menuUp, (self,)))
				self.listFilter.menu.addAction(HandlerAction(QtGui.QIcon(), 'Move Down', self.listFilter.menu, menuDown, (self,)))
				
				self.listFilter.menu2 = QtGui.QMenu(self)
				self.listFilter.menu2.addAction(HandlerAction(QtGui.QIcon(), 'Add New', self.listFilter.menu, menuAdd, (self,)))
				
			# get the item then the row
			item = self.listFilter.itemAt(event.x(), event.y())
			# no item was under cursor so exit
			if item is None:
				# execute menu 2 instead
				self.listFilter.menu2.exec(event.globalPos())
				return
			self.listFilter.__row = item.row()
			self.listFilter.menu.exec(event.globalPos())

		listFilter.menu = None
		listFilter.contextMenuEvent = types.MethodType(__contextMenuEvent, self)
		
		listFilter.setColumnCount(3)
		listFilter.setHorizontalHeaderLabels(['Invert', 'Type', 'Expression'])
		
		listFilter.resize(575, 500)
		
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
			
			# remove all items in target combobox
			while self.editTarget.widget().count() > 0:
				self.editTarget.widget().removeItem(0)
			
			cfg = bku.LoadConfig(account = text)
				
			paths = cfg['paths']
						
			# set authorization code so it can be modified if desired
			self.editAuth.widget().setText(cfg['storage-auth-code'])
			
			if cfg['ssl']:
				self.editSSL.widget().setCurrentIndex(0)
			else:
				self.editSSL.widget().setCurrentIndex(1)
				
			self.editRemoteHost.widget().setText(cfg['remote-host'])
			self.editRemotePort.widget().setText('%s' % cfg['remote-port'])
						
			# add new targets
			for path in paths:
				self.editTarget.widget().insertItem(0, path)
			
			actionTargetTextChanged(self, self.editTarget.widget().currentText())
			
		def actionButtonSave(self):
			account = self.editAccount.widget().currentText()
			
			bku = self.bku
			cpath = bku.GetConfigPath(account = account)
				
			cfg = bku.LoadConfig(account = account)
			
			if 'paths' not in cfg:
				cfg['paths'] = {}
			
			# update any of the major parameters that were changed
			cfg['storage-auth-code'] = self.editAuth.widget().text()
			cfg['remote-host'] = self.editRemoteHost.widget().text()
			try:
				cfg['remote-port'] = int(self.editRemotePort.widget().text())
			except:
				QtGui.QMessageBox.critical(self, 'Remote-Port Problem', 'The remote-port value was [%s] which is not a valid integer!' % self.editRemotePort.widget().text()).exec()
				return
			cfg['ssl'] = self.editSSL.widget().currentText() == 'True'
			
			target = self.editTarget.widget().currentText()
			
			# create the target
			path = {}
			cfg['paths'][target] = path
			
			path['disk-path'] = self.editPath.widget().text()
			path['enabled'] = self.editEnabled.widget().currentText() == 'True'
			
			# create the filter list
			filter = []
			path['filter'] = filter
			
			# open the file and write the output
			fd = open(cpath, 'w')
			pprint.pprint(cfg, fd)
			fd.close()
			return
			
		btnSave.clicked.connect(lambda : actionButtonSave(self))
		btnCancel.clicked.connect(lambda : self.hide())
			
		def actionTargetTextChanged(self, text):
			print('target', self, text)
			
			bku = self.bku
			
			account = self.editAccount.widget().currentText()
			
			exists = False
			
			cfg = bku.LoadConfig(account = account)
			
			if self.editTarget.widget().currentText() in cfg['paths']:
				exists = True
				# also just grab the target meta-data too while we are at it
				target = cfg['paths'][self.editTarget.widget().currentText()]
			
			if exists:
				self.listFilter.init = True
				ChangeStyle(self.editTarget.widget(), 'EditValid')
				
				# populate other controls with data
				self.editPath.widget().setText(target['disk-path'])
				
				if target['enabled']:
					self.editEnabled.widget().setCurrentIndex(0)
				else:
					self.editEnabled.widget().setCurrentIndex(1)
				
				ftable = self.listFilter
				
				# clear the filter table
				ftable.setRowCount(0)
				
				# populate filter table
				filter = target['filter']
				ftable.setRowCount(len(filter))
				for x in range(0, len(filter)):
					fitem = filter[x]

					# provide the choice of inversion
					w = QtGui.QComboBox()
					w.currentIndexChanged.connect(lambda text: actionFilterTestTextChanged(self, None))
					w.insertItem(0, 'True')
					w.insertItem(0, 'False')
					if fitem[0]:
						w.setCurrentIndex(1)
					else:
						w.setCurrentIndex(0)
					ftable.setCellWidget(x, 0, w)
					
					# provide the choice of type
					w = QtGui.QComboBox()
					w.currentIndexChanged.connect(lambda text: actionFilterTestTextChanged(self, None))
					i = 0
					for ftype in ('repattern', 'sizegreater', 'sizelesser', 'mode'):
						w.insertItem(0, ftype)
						if ftype == fitem[1]:
							si = i
						i = i + 1
					w.setCurrentIndex(w.count() - (si + 1))
					
					ftable.setCellWidget(x, 1, w)
					
					# set the expression
					item = QtGui.QTableWidgetItem()
					item.setText('%s' % fitem[2])
					ftable.setItem(x, 2, item)
				self.listFilter.init = False
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
		
		def actionItemChanged(self, item):
			# we can not do anything if old is set to None
			if self.listFilter.old is None:
				return
				
			# force this to run and check against the test file
			actionFilterTestTextChanged(self, None)
				
			#self.listFilter.item(row, col).setText(self.listFilter.old)
		
		def actionItemClicked(self, item):
			if hasattr(item, 'text'):
				print('saved-old', item.text())
				self.listFilter.old = item.text()
		
		
		def actionFilterTestTextChanged(self, text = None):
			# run the filter on this..
			bku = self.bku
			
			if self.listFilter.init:
				return
			
			print('re-running filter')
			
			if text is None:
				text = self.editFilterTest.widget().text()
			
			# take the filters from the table and compile them into a list
			filter = []
			for row in range(0, self.listFilter.rowCount()):
				finvert = self.listFilter.cellWidget(row, 0).currentText()
				ftype = self.listFilter.cellWidget(row, 1).currentText()
				fexp = self.listFilter.item(row, 2).text()
				print(finvert, ftype, fexp)
				
				if finvert == 'True':
					finvert = True
				else:
					finvert = False
				
				fentry = (finvert, ftype, fexp)
				print(fentry)
				filter.append(fentry)
				
			
			if bku.dofilters(filter, text, allownonexistant = True):
				# it matched
				ChangeStyle(self.editFilterTest.widget(), 'EditValid')
			else:
				# it did not match
				ChangeStyle(self.editFilterTest.widget(), 'EditInvalid')
		
		listFilter.old = None
		listFilter.itemChanged.connect(lambda item: actionItemChanged(self, item))
		listFilter.itemClicked.connect(lambda item: actionItemClicked(self, item))
		
		editFilterTest.widget().textChanged.connect(lambda text: actionFilterTestTextChanged(self, text))
		editAccount.widget().editTextChanged.connect(lambda text: actionAccountTextChanged(self, text))
		editTarget.widget().editTextChanged.connect(lambda text: actionTargetTextChanged(self, text))
		editPath.widget().textChanged.connect(lambda text: actionDiskPathChanged(self, text))
			
		self.show()
		
		self.editAccount = editAccount
		self.editTarget = editTarget
		self.editPath = editPath
		self.listFilter = listFilter
		self.editAuth = editAuth
		self.editFilterTest = editFilterTest
		
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
		
	def resize(self, w, h):
		super().resize(w, h)
	
	def event(self, e):
		if type(e) is QtGui.QPaintEvent:
			self.lv0.Do()
		return super().event(e)
		# end-of-function
		
class QAccountsAndTargetSystem(QtGui.QFrame):
	def __init__(self, parent):
		QtGui.QFrame.__init__(self, parent)
		self.Create()
		self.tedit = None
	
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
		# place to check for and attach dialog window for
		# editing the accounts and targets
		table.tedit = None			
		
		def menuPush(self):
			# push the target on specified account
			python = sys.executable

			account = self.item(self.__row, 1).text()
			target = self.item(self.__row, 2).text()
			
			fnull = open(os.devnull, 'w')
			subprocess.Popen((python, 'backup.py', account, 'push', target), stdout = fnull, stderr = fnull)
			print('executed push with account:%s target:%s' % (account, target))
		
		def menuEdit(self):
			menuAddNew(self)
			
		def menuAddNew(self):
			# dont create multiple instances.. use the same one
			if self.tedit is None:
				self.tedit = QTargetEditor()
			# make sure it is displayed
			self.tedit.show()
			
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
				self.menu2.addAction(HandlerAction(QtGui.QIcon(), 'Add New Target', self.menu, menuAddNew, (self,)))
				
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