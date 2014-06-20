'''
	This implements an editor that can edit the accounts and targets under the current user.
'''
import os
from PyQt4 import QtGui
from PyQt4 import QtCore

import types

from lib.gui.misc import *
from lib.Backup import Backup
from lib.gui.QLabelWith import QLabelWith
from lib.gui.QCompactLayout import QCompactLayout

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
		self.bku = Backup()
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
