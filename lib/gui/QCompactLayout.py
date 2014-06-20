'''
	This implements an object that can manage the layout of multiple widgets.
'''
from PyQt4 import QtGui
from PyQt4 import QtCore

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
