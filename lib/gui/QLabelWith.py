'''
	This implements a custom Qt widget that pairs a label and another
	widget of choice together. This made it easier for me to work
	with my QCompactLayout and any other layout.
'''
from PyQt4 import QtGui
from PyQt4 import QtCore

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
