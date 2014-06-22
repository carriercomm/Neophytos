'''
	This will display all the remote targets on the server, which may or may not
	match the local configuration. There may be missing targets on the remote that
	exist locally, or targets on the remote that exist locally.
'''

from PyQt4 import QtGui
from PyQt4 import QtCore

import lib.Backup as Backup
import threading
import time
import random

class QProcessing(QtGui.QDialog):
	def __init__(self):
		super().__init__()
		
		self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowSystemMenuHint)
		
		# create controls needed
		self.resize(100, 100)
		
		#mask = QtGui.QRegion(self.width() / 2, self.height() / 2, 80, 80, QtGui.QRegion.Ellipse)
		#self.setMask(mask)
		self.t = 0
		
		c = random.randint(1, 16)
		
		self.spinners = []
		for x in range(0, c):
			r = random.randint(0, 255)
			g = random.randint(0, 255)
			b = random.randint(0, 255)
			a = random.randint(0, 255)
			color = QtGui.QColor(r, g, b, a)
			initial = random.randint(0, 360)
			step = random.randint(0, 40)
			self.spinners.append([initial, color, step])
	
	def tick(self):
		self.t = self.t + 1
		self.update()
	
	def paintEvent(self, event):
		print('paint')
		p = QtGui.QPainter()
		p.begin(self)
		p.setFont(QtGui.QFont('Arial', 10))
		p.setRenderHint(QtGui.QPainter.Antialiasing)
		#p.scale(1.0, 1.0)
		#p.setPen(QtCore.Qt.NoPen)
		#p.setBrush(QtGui.QColor(127, 0, 127, 255))
		for x in range(0, len(self.spinners)):
			spinner = self.spinners[x]
			initial = spinner[0]
			color = spinner[1]
			step = spinner[2]
		
			p.save()
			p.translate(self.width() / 2, self.height() / 2)
			p.rotate(self.t * step + initial)
			p.setPen(color)
			
			#p.drawText(event.rect(), QtCore.Qt.AlignCenter, 'hello')
			
			poly = QtGui.QPolygon([
				QtCore.QPoint(7, 8),
				QtCore.QPoint(-7, 8),
				QtCore.QPoint(0, -40)
			])
			
			p.drawConvexPolygon(poly)
			p.restore()
		
		p.setPen(QtGui.QColor(0, 0, 0))
		p.drawText(0, 10, 'PROCESSING..')
		
		p.end()
		
		#p.restore()
		
	def SetThreadToWaitOn(self, thread, finish, parent):
		parent.setDisabled(True)
		# setup timer to animate waiting window and
		# also to check if thread is dead yet and if
		# so then we can let the user continue
		wt = QtCore.QTimer()
		self.wt = wt
		wt.setInterval(125)
		def __wtick():
			# tick animation
			self.tick()
			# if thread is alive exit
			if thread.isAlive():
				return
			# if thread is dead hide waiting window
			self.hide()
			# stop the timer
			wt.stop()
			# enable the widget
			parent.setDisabled(False)
			parent.show()
			# process result
			finish()
			
		# set timeout method
		wt.timeout.connect(__wtick)
		# start timer
		wt.start()


class QTable(QtGui.QTableWidget):
	def SetHeader(self, items):
		if self.columnCount() < len(items):
			self.setColumnCount(len(items))
		self.setHorizontalHeaderLabels(items)
		
	def InsertRow(self, row, colitems = None):
		# call native
		super().insertRow(row)
		
		# adjust the number of columns
		if self.columnCount() < len(colitems):
			self.setColumnCount(len(colitems))
		
		if colitems is None:
			return
		
		# set the strings and widgets
		for col in range(0, len(colitems)):
			colitem = colitems[col]
			
			if isinstance(colitem, str):
				ti = QtGui.QTableWidgetItem()
				ti.setText(colitem)
				self.setItem(row, col, ti)
				continue
				
			if isinstance(colitem, QtGui.QWidget):
				self.setCellWidget(row, col, colitem)
				continue
				
			raise Exception('Unknown Column Item [%s]' % type(colitem))
			
class QRemoteTargetsView(QtGui.QDialog):
	def __init__(self, parent = None):
		super().__init__(parent)
		self.CreateControls()
		
		icon = QtGui.QIcon('./media/stack.ico')
		self.setWindowIcon(icon)

		fd = open('./media/client.css', 'r')
		cssdata = fd.read()
		fd.close()
		self.setStyleSheet(cssdata)
		
		self.setWindowTitle('Target Viewer')
	
	def resizeEvent(self, event):
		self.table.resize(self.width(), self.height())
	
	def CreateControls(self):
		# QTableWidget
		table = QTable(self)
		table.SetHeader(('Account',))
		table.setObjectName('RemoteTargetTable')
		self.table = table
		table.resize(150, 400)
		self.resize(150, 400)
		
	def Populate(self, account, caller = None):
		targets = []
		print('populate')
		
		#if caller is not None:
		#	caller.setDiabled(True)
		
		# hide main window (so it does not cover up waiting window..[workaround])
		self.hide()
		
		# display processing widget
		pw = QProcessing()
		pw.show()
		
		# we have to maintain a reference to it, or the garbage collector
		# seems to delete it since it is a top-level window
		self.pw = pw
		
		# create thread to handle work
		thread = threading.Thread(target = QRemoteTargetsView.GetRemoteTargets, args = (account, targets))
		thread.start()
		
		def __finish():
			for node in targets:
				self.table.InsertRow(0, (node.decode('utf8', 'ignore'),))
		
		pw.SetThreadToWaitOn(thread = thread, finish = __finish, parent = self)
		return
	
	def GetRemoteTargets(account, targets):
		# get a connected client for the specified account
		try:
			c = Backup.GetClientForAccount(account)
		except Exception as e:
			print('exception')
			raise e
			#QtGui.QMessageBox.critical(self, 'Problem Getting Client For Account', 'The following error has occured: [%s]' % e)
			return False
		# get a directory listing for the base directory
		nodes = c.DirList(b'/')
		# the graceful way to terminate the connection
		c.Shutdown()
		
		# iterate through nodes
		for node in nodes:
			# check if it is not a directory
			if node[1] != 0xffffffff:
				continue
			targets.append(node[0])
		return 

