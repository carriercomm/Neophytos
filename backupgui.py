'''
	This implements a client GUI.
'''
import os
import os.path
import sys
import io
import os.path
import pprint
import status
import threading
import time
import types
import subprocess

from PyQt4 import QtGui
from PyQt4 import QtCore

'''
	These are components that have been separated from our main module here
	in order to keep the line count in this file smaller and develop some
	structure to the program.
'''
from lib.gui.misc import *
from lib.gui.QTargetEditor import QTargetEditor
from lib.gui.QCompactLayout import QCompactLayout
from lib.gui.misc import CloneComboBox
from lib.gui.misc import ChangeStyle
from lib.ClientInterface import ClientInterface
from lib.Backup import Backup
from lib.gui.QRemoteTargetsView import QRemoteTargetsView			
from lib.gui.QMultiTableWidget import QMultiTableWidget		
		
class QTargetAndStatusView(QtGui.QFrame):
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
	
	def refresh(self):
		accounts = ClientInterface.GetAccounts()
	
		# clear the QTableWidget
		while self.table.rowCount() > 0:
			self.table.removeRow(0)
		
		# populate the QTableWidget
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
				
				self.table.insertRow(0)
				self.SetTableRow(self.table, 0, (
					cfg['enabled'],
					account, target,
					cfg['disk-path'],
					nrt
				))
	
	def Create(self):
		
		self.panels = {}
	
		table = QtGui.QTableWidget(self)
		self.table = table
		
		table.setObjectName('StatusTable')
		
		split = QtGui.QSplitter(self)
		self.split = split
		
		# used by the services scan
		self.uidtorow = {}
		# used by the services scan
		self.lastuidupdate = {}
		
		#DumpObjectTree(self)
		
		# enabled, account, target, path, bytesout, bytesin, status, progress
		table.setColumnCount(5)
		table.setHorizontalHeaderLabels(['Enabled', 'Account', 'Target', 'Path', 'Next Run'])
				
		self.refresh()
		
		stable = QMultiTableWidget(self)
		stable.show()
		#stable = QtGui.QTableWidget(self)
		self.stable = stable
		stable.setObjectName('StatusTable')
		#stable.setColumnCount(8)
		#stable.setHorizontalHeaderLabels(['User', 'Account', 'Target', 'Queue', 'Up/MB/Sec', 'Complete', 'Files Done', 'Files Total'])
		#stable.setVerticalHeaderLabels(['', ''])
		#stable.resizeColumnsToContents()
		
		# disable editing
		table.setEditTriggers(QtGui.QAbstractItemView.NoEditTriggers)
		#stable.setEditTriggers(QtGui.QAbstractItemView.NoEditTriggers)
		
		table.setVerticalHeaderLabels(['', ''])
		table.resizeColumnsToContents()
		# place to check for and attach dialog window for
		# editing the accounts and targets
		table.tedit = None			
		table.rtv = None
		
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
			# do not create multiple instances.. use the same one
			if self.tedit is None:
				# set up a callback so when close we can refresh
				# our view of the accounts and targets
				closeCallback = (QTargetAndStatusView.refresh, (self.parent().parent(),))
				self.tedit = QTargetEditor(closeCallback = closeCallback)
			# make sure it is displayed (it hides it's self on save or cancel)
			self.tedit.show()
			
		def menuViewRemoteTargets(self):
			if self.rtv is None:
				print('created')
				self.rtv = QRemoteTargetsView()
			# get the account, populate widget, then show widget
			account = self.item(self.__row, 1).text()
			print('populating')
			self.rtv.Populate(account, caller = self.parent().parent())
			
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
				self.menu.addAction(HandlerAction(QtGui.QIcon(), 'View Remote Targets For Account', self.menu, menuViewRemoteTargets, (self,)))
				
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
		scantimer.timeout.connect(lambda : QTargetAndStatusView.PeriodicScanUpdate(self))
		scantimer.start(5000)
		
		scanthread = threading.Thread(target = QTargetAndStatusView.PeriodicScanThreadEntry, args = (self,))
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
		uidtorow = self.uidtorow
		
		# add active services or update them and track last update time
		ct = time.time()
		for port in services:
			service = services[port]
			# should always exist before connections are accepted
			title = service['title']
			# it is possible that this might not exist
			if 'work' in service:
				work = service['work']
			else:
				work = None
			
			# this should always be set before any connections
			# are accepted
			guid = title['uid']
			
			self.lastuidupdate[guid] = ct
			
			# make a new row if it does not exist
			if guid not in uidtorow:
				row = self.stable.AddRow()
				uidtorow[guid] = row
				print('new row', guid)
			else:
				row = uidtorow[guid]
				print('old row', guid)
			
			try:
				for k in title:
					row.SetCol(k, title[k])
			except:
				# work-around to hard to track down bug
				del uidtorow[guid]
				continue
			row.Ready()
		
		# look for services that have not updated recently
		toremove = []
		for guid in self.lastuidupdate:
			print('GOTGUID', guid)
			if guid not in self.uidtorow:
				toremove.append(guid)
				continue
			row = self.uidtorow[guid]
			delta = time.time() - self.lastuidupdate[guid]
			if delta > 60 * 0.5:
				# color it yellow
				pass
			if delta > 30 * 3.0:
				# remove it so we create a new one next time
				del self.uidtorow[guid]
				# schedule it to drop from it's container object
				row.Drop()
				row.Update()
				toremove.append(guid)
				print('REMOVING', guid)
		
		for guid in toremove:
			del self.lastuidupdate[guid]
			print('REMOVED', guid)
		# <end-of-function>
		
	def PeriodicScanThreadEntry(self):
		# initial the status query object
		q = status.StatusQuery()
		while True:
			# scan for running services
			services = q.Scan()
			# set this so the main thread can read it later
			self.services = services
			time.sleep(5)
		
	def resizeEvent(self, event):
		self.split.resize(self.width(), self.height())
						
class QStatusWindow(QtGui.QMainWindow):
	def resizeEvent(self, event):
		self.fTargetAndStatusView.resize(self.width(), self.height())

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
	
		self.fTargetAndStatusView = QTargetAndStatusView(self)
		self.fTargetAndStatusView.resize(self.width(), self.height())

		self.resize(700, 340)
		self.move(400, 20)
		self.setWindowTitle('Neophytos Backup UI')
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