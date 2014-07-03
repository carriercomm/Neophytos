import os
import sys
import socket
import select
import struct
import shutil
import hashlib
import pprint
import zlib
import ssl
import base64
import traceback
import collections

from io import BytesIO

from lib import output
from lib.pkttypes import *
from lib.misc import *
from lib import pubcrypt

'''
	This helps to cache account info which contains the bytes used. If
	each client opened their own account information and two or more
	clients connected on the same account they might read an old used
	byte quota which would effectively give them free bytes on their
	quotes, and even worse is the ability to save an old used quota.
	
	By connecting one client and not using it. Then connecting others
	and writing data. Then closing the first client connection they
	could erase all bytes used.
	
	So this caches this information. I need to add the ability to flush
	out old entries that are not being used or else this is going to 
	turn into one big memory leak on a long term server.
	
	TODO: remove unused cache entries
'''
class AccountMan:
	# static class and methods
	cache = {}
	
	def LoadAccount(account):
		if account in AccountMan.cache:
			# do not read from disk or else someone could
			# connect a client after a client and get free
			# byte to their quota, so return the currently
			# being used account quota
			return AccountMan.cache[account]
		fd = open('./accounts/%s' % account, 'r')
		info = eval(fd.read())
		fd.close()
		AccountMan.cache[account] = info
		return info
		
	def SaveAccount(account, info):
		fd = open('./accounts/%s' % account, 'w')
		pprint.pprint(info, fd)
		fd.close()
	
# setup standard outputs
output.Configure(tcpserver = False)

class DoubleTypeOrRevException(Exception):
	pass
	
class NodeTypeUnknownException(Exception):
	pass

class DataBufferOverflowException(Exception):
	pass 

# ABCDEFGHIJK


# 0

class ServerClient:
	def GetName(self):
		return '%s:%s' % (self.addr[0], self.addr[1])
		
	def __init__(self, sock, addr, kpub, kpri, server, essl = False):
		self.sock = sock
		self.addr = addr
		self.hdr = b''
		
		self.aid = None
		
		self.ssl = essl
		
		self.bytestosend = 0
		self.datatosend = collections.deque()
		
		if essl:
			#ciphers = ('AES25-SHA', 'TLSv1/SSLv3', 256)
			
			# at the moment AES25 seems to eat CPU like candy
			# so I have dropped down to RC4 and I have much
			# better CPU usage (around 3% on my test machine
			# versus 100% using AES)
			ciphers = 'RC4'
			ciphers = 'AES'
			ciphers = None
			self.sock = ssl.wrap_socket(self.sock, server_side = True, certfile = 'cert.pem', ssl_version = ssl.PROTOCOL_TLSv1, ciphers = ciphers)
		
		self.server = server
		
		self.kpub = kpub
		self.kpri = kpri
		
		self.wsz = None
		self.wmsg = b''
		
		#self.data = b''
		self.data = BytesIO()
		
		self.info = None
		
		self.sock.settimeout(0)
		
		# i might like to make this dynamic.. per client
		# and also dynamic in the way that the client can
		# query this value and adjust locally also
		# TODO: implement the above
		self.maxbuffer = 1024 * 1024 * 8
		
		# used to aid in diagnosing server slow downs
		# by recording the last few packet handling
		# times which can be used to produce statistical
		# information or compare one client to others to
		# determine if they are the problem; basically to
		# help diagnose DoS attacks at the application layer
		# when the server is unable to prevent the
		self.times_buffer = []
		self.times_request = []
	
		self.fdcache = {}
		self.__fdcache = []
		
		self.bytes_in_start = time.time()
		self.bytes_in_total = 0
		
		self.bytes_out_start = time.time()
		self.bytes_out_total = 0
	
	def Cleanup(self):
		if self.aid is not None:
			# opted to write it all on cleanup (even though server
			# failure could give clients more disk space we can
			# always go in and correct this)
			AccountMan.SaveAccount(self.aid, self.info)
		# close all open file descriptors
		for fpath in self.fdcache:
			c = self.fdcache[fpath]
			c[1].close()
		# just for safety
		self.fdcache = None
		self.__fdcache = None
	
	def CloseFileDescriptor(self, fpath):
		if fpath in self.fdcache:
			ci = self.fdcache[fpath]
			ci[1].close()
			del self.fdcache[fpath]
			self.__fdcache.remove(fpath)
			return
			
	def GetFileDescriptor(self, fpath, mode):
		if len(self.fdcache) > 100:
			# we need to close one.. we will close the oldest
			_fpath = self.__fdcache.pop(0)
			self.fdcache[_fpath][1].close()
			del self.fdcache[_fpath]
	
		if fpath in self.fdcache:
			ci = self.fdcache[fpath]
			if ci[0] == mode:
				#print('cached fd:%s' % ci[1])
				return ci[1]
			else:
				#print('closing fd:%s' % ci[1])
				# close it because we are about to reopen it in a different mode
				ci[1].close()
				# remove it from the dict
				del self.fdcache[fpath]
				self.__fdcache.remove(fpath)
		
		fd = open(fpath, mode)
		#print('opened fd:%s' % fd)
		self.fdcache[fpath] = (mode, fd)
		self.__fdcache.append(fpath)
		return fd
	
	def GetAddr(self):
		return self.addr
	
	def GetSock(self):
		return self.sock
		
	def HandleData(self, data):
		#bst = time.time()
		# process data for a message
		while True:
			#rst = time.time()
			# the second and so forth time this is called
			# we pass in None for data and just check for
			# additional messages in the buffer
			msg, vector = self.ProcessData(data)
			# on next call dont pass in any data
			data = None
			
			# exit if no message
			if msg is None:
				break
				
			#print('type-vector', type(vector))
				
			# process the message
			self.ProcessMessage(msg, vector)
			
			# track the times on the past requests, this might
			# show were a single client is using a lot of CPU
			# time which could be effecting other clients
			#ret = time.time()
			#rdt = ret - rst
			#if len(self.times_request) > 40:
			#	self.times_request.pop(0)
			#self.times_request.append(rdt)
			
		#bet = time.time()
		#bdt = bet - bst
		
		# implement a queue (not a stack)
		#if len(self.times_buffer) > 40:
		#	# keep 40 previous times (essentially 40 previous network packets)
		#	self.times_buffer.pop(0)
		#self.times_buffer.append(bdt)
	
	'''
		This ensures the path does not reference outside the root directory.
	'''
	def SanitizePath(self, path):
		while path.find(b'/..') > -1:
			path = path.replace(b'/..', b'.')
		while path.find(b'../') > -1:
			path = path.replace('b../', b'.')
		return path
		
	def GetPathParts(self, fname):
		# break out base path if specified otherwise consider in root
		pos = fname.rfind('/')
		if pos < 0:
			fbase = '/'
		else:
			fbase = fname[0:pos]
			fname = fname[pos + 1:]
		return fbase, fname
			
	def ProcessMessage(self, msg, vector):
		type = msg[0]
		msg = msg[1:]
		
		# unencrypted messages
		if type == ClientType.GetPublicKey:
			self.WriteMessage(struct.pack('>BH', ServerType.PublicKey, len(self.kpub[0])) + self.kpub[0] + self.kpub[1], vector)
			print('len(kpub[0]):%s' % (len(self.kpub[0])))
			return
		if type == ClientType.SetupCrypt:
			key = pubcrypt.decrypt(msg, self.kpri)
			print('key:%s' % key)
			self.crypter = SymCrypt(key)
			self.WriteMessage(struct.pack('>B', ServerType.SetupCrypt), vector)
			return
			
		# anything else must be encrypted
		if type != ClientType.Encrypted:
			#print('NOT ENCRYPTED MESSAGE')
			raise Exception('message not encrypted but has type:%s' % type)
			return
		
		#print('processing encrypted message')
		
		# decrypt message if NOT SSL
		if False and not self.ssl:
			#print('NON-SSL MESSAGE')
			msg = self.crypter.decrypt(msg)
			
		type = msg[0]
		msg = msg[1:]
		
		#print('	type:%s' % type)
		#print('	msg:%s' % msg)
		
		# will associate client with an account
		if type == ClientType.Login:
			print('got login message')
			# decrypt account ID if we are going over non-SSL link
			if not self.ssl:
				msg = pubcrypt.decrypt(msg, self.kpri)
			aid = msg.decode('utf8', 'ignore')
			# check that account exists
			if os.path.exists('./accounts/%s' % aid) is False:
				print('account does not exist')
				self.WriteMessage(struct.pack('>B', ServerType.LoginResult) + b'n', vector)
				return
			print('loading account')
			# load account information
			self.info = AccountMan.LoadAccount(aid)
			self.aid = aid
			# ensure directory exists
			diskpath = self.info['disk-path']
			if os.path.exists(diskpath) is False:
				os.makedirs(diskpath)
			print('login good')
			self.WriteMessage(struct.pack('>B', ServerType.LoginResult) + b'y', vector)
			
			# debugging compression level
			self.WriteMessage(struct.pack('>BB', ServerType.SetCompressionLevel, 9), 0)
			return
			
		# anything past this point needs to
		# be logged into the system
		if self.info is None:
			self.WriteMessage(struct.pack('>B', ServerType.LoginRequired), vector)
			return
		# used to ensure elements have been processed preceding this
		if type == ClientType.Echo:
			self.WriteMessage(struct.pack('>B', ServerType.Echo), vector)
			return
		if type == ClientType.FileSetTime:
			atime, mtime = struct.unpack_from('>dd', msg)
			fname = self.SanitizePath(msg[8 * 2:]).decode('utf8', 'ignore')

			# get path parts
			fbase, fname = self.GetPathParts(fname)
			
			# build full path to file (including revision)
			fpath = '%s/%s/%s' % (self.info['disk-path'], fbase, fname)
			if os.path.exists(fpath) is False:
				# oops.. no such file (lets tell them it failed)
				self.WriteMessage(struct.pack('>BB', ServerType.FileSetTime, 0), vector)
				return

			self.CloseFileDescriptor(fpath)
			
			os.utime(fpath, (atime, mtime))
			
			self.WriteMessage(struct.pack('>BB', ServerType.FileSetTime, 1), vector)
			return
			
		# return a list of nodes in directory
		if type == ClientType.DirList:
			# remove any dot dots to prevent backing out of root
			#print('doing directory listing')
			cpath = '%s/%s' % (self.info['disk-path'], self.SanitizePath(msg).decode('utf8', 'ignore'))
			#print('	calling os.listdir(%s)' % cpath)
			if os.path.exists(cpath) is False:
				self.WriteMessage(struct.pack('>BB', ServerType.DirList, 0), vector)
				return
				
			nodes = os.listdir(cpath)
			objs = []
			#print('	iterating nodes')
			for node in nodes:
				# add directories in a special way so that they
				# can be interpreted as a directory and not a file
				if os.path.isdir('%s/%s' % (cpath, node)):
					objs.append((bytes(node, 'utf8'), 1))
					continue
				# break node into appropriate parts
				objs.append((bytes(node, 'utf8'), 0))
				
			# serialize output into list of entries
			#print('	serializing')
			out = []
			for key in objs:
				out.append(struct.pack('>HB', len(key[0]), key[1]) + key[0])
			out = b''.join(out)
			#print('	writing message')
			self.WriteMessage(struct.pack('>BB', ServerType.DirList, 1) + out, vector)
			return
		if type == ClientType.FileTime:
			return self.FileTime(msg, vector)
		if type == ClientType.FileSize:
			return self.FileSize(msg, vector)
		if type == ClientType.FileTrun:
			return self.FileTrun(msg, vector)
		if type == ClientType.FileRead:
			offset, length = struct.unpack_from('>QQ', msg)
			fname = self.SanitizePath(msg[8 + 8:]).decode('utf8', 'ignore')
			
			# maximum read length default is 1MB (anything bigger must be split into separate requests)
			# OR.. we could spawn a special thread that would lock this client and perform the work
			# in parallel with this main thread
			if length > self.info.get('max-read-length', self.maxbuffer):
				self.WriteMessage(struct.pack('>BB', ServerType.FileRead, 2), vector)
				return

			# get path parts
			fbase, fname = self.GetPathParts(fname)
			
			# build full path to file (including revision)
			fpath = '%s/%s/%s' % (self.info['disk-path'], fbase, fname)
			if os.path.exists(fpath) is False:
				# oops.. no such file (lets tell them it failed)
				print('badpath', fpath)
				self.WriteMessage(struct.pack('>BB', ServerType.FileRead, 0), vector)
				return
			# okay open the file and read from it
			# later.. i might want to cache file descriptors to increase performance (or even mmap files actually)
			fd = self.GetFileDescriptor(fpath, 'rb')
			fd.seek(offset)
			data = fd.read(length)
			#fd.close()
			
			self.WriteMessage(struct.pack('>BB', ServerType.FileRead, 1) + data, vector)
			return
		if type == ClientType.FileCopy or type == ClientType.FileMove:
			srclen = struct.unpack_from('>H', msg)[0]
			fsrc = msg[2:2 + srclen]
			fdst = msg[2 + srclen:]
			
			fsrc = self.SanitizePath(fsrc).decode('utf8', 'ignore')
			fdst = self.SanitizePath(fdst).decode('utf8', 'ignore')
			
			fsrcbase, fsrcname = self.GetPathParts(fsrc)
			fdstbase, fdstname = self.GetPathParts(fdst)
			
			fsrcpath = '%s/%s/%s' % (self.info['disk-path'], fsrcbase, fsrcname)
			fdstpath = '%s/%s/%s' % (self.info['disk-path'], fdstbase, fdstname)
			
			print('fsrcpath:%s' % fsrcpath)
			print('fdstpath:%s' % fdstpath)
			
			if type == ClientType.FileMove:
				# handles move across different file systems (or uses rename)
				shutil.move(fsrcpath, fdstpath)
				self.WriteMessage(struct.pack('>BB', ServerType.FileMove, 1), vector)
			else:
				# handles copy across different file systems
				shutil.copyfile(fsrcpath, fdstpath)
				self.WriteMessage(struct.pack('>BB', ServerType.FileCopy, 1), vector)
			return
			
		if type == ClientType.FileDel:
			fname = self.SanitizePath(msg).decode('utf8', 'ignore')
			
			fbase, fname = self.GetPathParts(fname)
			
			fpath = '%s/%s/%s' % (self.info['disk-path'], fbase, fname)
			if os.path.exists(fpath) is False:
				self.WriteMessage(struct.pack('>BB', ServerType.FileDel, 0), vector)
				return
			os.remove(fpath)
			# get the base path (without file name part)
			base = fpath[0:fpath.rfind('/')]
			# start deleting directories if they are empty
			while True:
				# figure out how much is in this directory
				nodes = os.listdir(base)
				# if zero nodes then the directory is empty and
				# no reason to let directories pile up on the
				# server side for no reason
				if len(nodes) > 0:
					break
				# should be safe as it will only delete a
				# directory if it is empty
				os.remove(base)
				# drop down again
				base = base[0:base.rfind('/')]
			
			self.WriteMessage(struct.pack('>BB', ServerType.FileDel, 1), vector)
			return
		if type == ClientType.FileHash:
			offset, length = struct.unpack_from('>QQ', msg)
			fname = self.SanitizePath(msg[8 * 2:]).decode('utf8', 'ignore')
			
			fbase, fname = self.GetPathParts(fname)
			fpath = '%s/%s/%s' % (self.info['disk-path'], fbase, fname)			
			
			if os.path.exists(fpath) is False:
				self.WriteMessage(struct.pack('>BB', ServerType.FileHash, 0), vector)
				return
			
			fd = self.GetFileDescriptor(fpath, 'r+b')
			fd.seek(offset)
			data = fd.read(length)
			#fd.close()
			
			#print('rdata', data)
			
			# hash the data and return the hash
			data = hashlib.sha512(data).digest()
			
			self.WriteMessage(struct.pack('>BB', ServerType.FileHash, 1) + data, vector)
			return
		if type == ClientType.FileWrite:
			return self.FileWrite(msg, vector)
		raise Exception('unknown message type:%s' % type)

	def FileSize(self, msg, vector):
		fname = self.SanitizePath(msg).decode('utf8', 'ignore')
		
		fbase, fname = self.GetPathParts(fname)
		
		fpath = '%s/%s/%s' % (self.info['disk-path'], fbase, fname)
		
		if os.path.exists(fpath) is False or os.path.isdir(fpath) is True:
			self.WriteMessage(struct.pack('>BBQ', ServerType.FileSize, 0, 0), vector)
			return
		
		fd = self.GetFileDescriptor(fpath, 'rb')
		fd.seek(0, 2)
		sz = fd.tell()
		#fd.close()
		
		self.WriteMessage(struct.pack('>BBQ', ServerType.FileSize, 1, sz), vector)
		return
		
	def FileTime(self, msg, vector):
		fname = self.SanitizePath(msg).decode('utf8', 'ignore')
		
		fbase, fname = self.GetPathParts(fname)	
		
		fpath = '%s/%s/%s' % (self.info['disk-path'], fbase, fname)
		if os.path.exists(fpath) is False:
			self.WriteMessage(struct.pack('>BQ', ServerType.FileTime, 0), vector)
			return
		
		mode, ino, dev, nlink, uid, gid, size, atime, mtime, ctime = os.stat(fpath)
		
		# just use which ever is greater to be safe
		if ctime > mtime:
			mtime = ctime
		
		self.WriteMessage(struct.pack('>BQ', ServerType.FileTime, mtime), vector)
		return

		
	def FileTrun(self, msg, vector):
		newsize = struct.unpack_from('>Q', msg)[0]
		fname = self.SanitizePath(msg[8:]).decode('utf8', 'ignore')
		
		fbase, fname = self.GetPathParts(fname)
		
		# this will either create the file OR change the size of it
		fpath = '%s/%s/%s' % (self.info['disk-path'], fbase, fname)
		#fd = self.GetFileDescriptor(fpath, 'wb')
		#fd.truncate(newsize)
		#fd.close()
		#print('newsize:%s' % newsize)
		# make directories
		dirpath = fpath[0:fpath.rfind('/')]
		#print('trun', dirpath)
		if os.path.exists(dirpath) is False:
			#print('making dirs', dirpath)
			os.makedirs(dirpath)
		# make file if needed
		if os.path.exists(fpath) is False:
			# make file
			#print('created')
			fd = os.open(fpath, os.O_CREAT)
			os.close(fd)
			# track disk space used per file
			if self.info['disk-used'] + self.info['disk-used-perfile'] > self.info['disk-quota']:
				# this prevent someone from creating too many small files as it accounts for
				# roughly the amount of disk space used per file, but since it is configuration
				# specific for account it can be changed if needed for some reason
				self.WriteMessage(struct.pack('>BB', ServerType.FileTrun, 9), vector)
				return
			self.info['disk-used'] = self.info['disk-used'] + self.info['disk-used-perfile']
			
		# get current size (maybe zero if newly created)
		fd = self.GetFileDescriptor(fpath, 'r+b')
		fd.seek(0, 2)
		csz = fd.tell()
		#fd.close()
		#fd.close()
		
		# subtract current size (will add new size later)
		self.info['disk-used'] = self.info['disk-used'] - csz
		
		if self.info['disk-used'] + newsize > self.info['disk-quota']:
			# they will go over their quota
			self.WriteMessage(struct.pack('>BB', ServerType.FileTrun, 9), vector)
			return
		
		# open existing
		#print('open existing')
		fd = os.open(fpath, os.O_RDWR)
		#print('fd:%s newsize:%s' % (fd, newsize))
		os.ftruncate(fd, newsize)
		os.close(fd)
		# make it look like it has never been updated
		os.utime(fpath, (0, 0))
		# add new size back onto used quota
		self.info['disk-used'] = self.info['disk-used'] + newsize
		# save account information
		self.WriteMessage(struct.pack('>BB', ServerType.FileTrun, 1), vector)
		return

	def FileWrite(self, msg, vector):
		offset, fnamesz, compression = struct.unpack_from('>QHB', msg)
		fname = self.SanitizePath(msg[8 + 2 + 1:8 + 2 + 1 + fnamesz]).decode('utf8', 'ignore')
		data = msg[8 + 2 + 1 + fnamesz:]
		
		# only decompression if it was compressed
		if compression > 0:
			data = zlib.decompress(data)
		
		length = len(data)
		if length > self.info.get('max-write-length', self.maxbuffer):
			self.WriteMessage(struct.pack('>BB', ServerType.FileWrite, 2), vector)
			return
		
		fbase, fname = self.GetPathParts(fname)
		fpath = '%s/%s/%s' % (self.info['disk-path'], fbase, fname)
		
		if os.path.exists(fpath) is False:
			self.WriteMessage(struct.pack('>BB', ServerType.FileWrite, 0), vector)
			return
		
		fd = self.GetFileDescriptor(fpath, 'r+b')
		# set accessed and modified time to zero (so it is not considered up to date)
		os.utime(fpath, (0, 0))
		
		fd.seek(0, 2)
		max = fd.tell()
		if offset + len(data) > max:
			# you can not write past end of the file (use truncate command)
			self.WriteMessage(struct.pack('>BB', ServerType.FileWrite, 2), vector)
			return
		
		#print('WRITING-data', data)
		fd.seek(offset)
		fd.write(data)
		#fd.close()
		self.WriteMessage(struct.pack('>BB', ServerType.FileWrite, 1), vector)
		return			

	def UpdateStatus(self):
		ct = time.time()
		in_bps = self.bytes_in_total / (ct - self.bytes_in_start)
		out_bps = self.bytes_out_total / (ct - self.bytes_out_start)

		ae = 0
		ac = 0
		for e in self.times_buffer:
			ae = ae + e
			ac = ac + 1
		if ac == 0:
			load = 0
		else:
			load = ae / ac
	
		text = '%.02f/%.02f/%.02f' %  (in_bps / 1024 / 1024, out_bps / 1024 / 1024, load)
	
		#output.SetCurrentStatus(self, text)
	
	def canSend(self):
		return self.bytestosend
	
	# non-blocking dump of data buffers
	def send(self, data = None, timeout = 0):
		if data is not None:
			#self.datatosend.append(data)
			self.datatosend.append(data)
			self.bytestosend = self.bytestosend + len(data)
		
		self.sock.settimeout(timeout)
		
		# check there is data to send
		while len(self.datatosend) > 0:
			# pop from the beginning of the queue
			#data = self.datatosend.pop(0)
			# grab from beginning of the queue
			data = self.datatosend.popleft()
			
			# try to send it
			totalsent = 0
			while totalsent < len(data):
				sent = 0
				try:
					sent = self.sock.send(data[totalsent:])
				except socket.error:
					# non-ssl socket likes to throw this exception instead
					# of returning zero bytes sent it seems
					#self.datatosend.insert(0, data[totalsent:])
					# place remaining back
					self.datatosend.appendleft(data[totalsent:])
					self.bytestosend = self.bytestosend - (totalsent + sent)
					return False
				
				if sent == 0:
					# place remaining data back at front of queue and
					# we will try to send it next time
					#self.datatosend.insert(0, data[totalsent:])
					# place remaining back
					self.datatosend.appendleft(data[totalsent:])
					self.bytestosend = self.bytestosend - (totalsent + sent)
					return False
				#print('@sent', sent)
				totalsent = totalsent + sent
			
			# we are done with it.. remove it (expensive operation)
			#self.datatosend.pop(0)
			
			self.bytestosend = self.bytestosend - totalsent
		return True
	
	def WriteMessage(self, data, vector):		
		# get type
		type = data[0]
		
		# leave get public key and setup crypt unaltered
		if type == ServerType.PublicKey:
			pass
		else:
			# if not SSL then do our own encryption
			if False and not self.ssl:
				data = bytes((ServerType.Encrypted,)) + self.crypter.crypt(data)
			else:
				# pretend its encrypted
				data = bytes((ServerType.Encrypted,)) + data
		# at the moment i do not use server-vector
		# so it is hard coded as zero
		self.send(struct.pack('>IQQ', len(data), 0, vector))
		self.send(data)
		self.bytes_out_total = self.bytes_out_total + 4 + 8 * 2 + len(data)
		#self.UpdateStatus()
		return
	
	def GetBufferSize(self):
		return len(self.wmsg)
	
	def ProcessData(self, data):
		if data is not None:
			self.data.write(data)
		#self.data = self.data + data
		
		#print('tell', self.data.tell())
		
		if self.data.tell() > 1024 * 1024 * 10:
			print('client buffer too big - dropping client')
			raise DataBufferOverflowException()
		
		#print('processing data', len(self.data))
		# do we need to read a message header and can we?
		if self.wsz is None and self.data.tell() >= 8 + 4:
			#print('reading sz and vector')
			self.data.seek(0)
			sz, vector = struct.unpack_from('>IQ', self.data.read(4 + 8))
			#print('sz:%s vector:%x' % (sz, vector))
			self.wsz = sz
			self.wvector = vector
			# compensate for this
			#self.data = self.data[8 + 4:]
			#print('reading for vector:%s' % vector)
			self.data.seek(0, 2)
		
		#print('checking for enough data (%s of %s)' % (len(self.data), self.wsz))
		# not enough data to read message portion
		#print('..tell', self.data.tell())
		if self.wsz is None or self.data.tell() - (8 + 4) < self.wsz:
			return (None, None)
		#print('reading message')
		# get message and leave remaining data
		# in the buffer for the next call
		#_ret = self.data[0:self.wsz]
		#self.data = self.data[self.wsz:]
		
		#print('got vector:%s' % self.wvector)
		# place remaining data into new buffer
		self.data.seek(8 + 4)
		_ret = self.data.read(self.wsz)
		ndata = BytesIO()
		ndata.write(self.data.read())
		self.data = ndata
		
		self.bytes_in_total = self.bytes_in_total + 8 + 4 + len(_ret)
		#self.UpdateStatus()
		
		# return the message and vector
		self.wsz = None
		return (_ret, self.wvector)
		
class Server:
	def __init__(self):
		self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		self.sock.bind(('0.0.0.0', 4322))
		self.sock.listen(20)
		
		self.sslsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.sslsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		self.sslsock.bind(('0.0.0.0', 4323))
		self.sslsock.listen(20)
		
		self.sc = {}
		self.socktosc = {}
		self.maxclientbuffer = 4096
		
		# we just use a cert file generated by openssl
		# openssl req -new -x509 -days 365 -nodes -out cert.pem -keyout cert.pem --newkey rsa:8192
		self.keypub, self.keypri = pubcrypt.readPrivateKeyFromCertFile('cert.pem')
	
	def HandleMessages(self):
		# client, addr = sock.accept()
		
		ddst = time.time()
		
		while True:
			input = [self.sock, self.sslsock]
			winput = []
			for scaddr in self.sc:
				sc = self.sc[scaddr]
				# place client that have pending output data in their
				# application level buffer into the writable check
				if sc.canSend() > 0:
					winput.append(sc.GetSock())
				# place all client sockets to be check for readability
				input.append(sc.GetSock())
		
			readable, writable, exc = select.select(input, winput, input)
			
			# [ACCEPT] incoming connections (weak encryption connections)
			if self.sock in readable:
				nsock, caddr = self.sock.accept()
				nsock.settimeout(0)
				nsc = ServerClient(nsock, caddr, self.keypub, self.keypri, self)
				self.sc[caddr] = nsc
				self.socktosc[nsock] = nsc
				readable.remove(self.sock)
				#output.AddWorkingItem(nsc)
				
			# [ACCEPT] incoming connections (SSL encryption connections)
			if self.sslsock in readable:
				nsock, caddr = self.sslsock.accept()
				nsc = ServerClient(nsock, caddr, self.keypub, self.keypri, self, essl = True)
				# the SSL will change the sock
				nsock = nsc.GetSock()
				nsock.settimeout(0)
				self.sc[caddr] = nsc
				self.socktosc[nsock] = nsc
				readable.remove(self.sslsock)
				#output.AddWorkingItem(nsc)
			
			# try to push some data out that has been stored in
			# our application level buffer, the next check below
			# will remove the socket from reading any data if
			# we do not get it lower if it is too high
			for sock in writable:
				sc = self.socktosc[sock]
				# if must have had data to have been placed for
				# a writable check
				sc.send()
			
			# this will keep us from reading in more data only to
			# be unable to process it because our output buffers
			# are too full; so anything with a buffer that is too
			# large is just skipped out of the readable list by
			# creating a new list
			_readable = []
			for sock in readable:
				sc = self.socktosc[sock]
				# if the out going application level buffers are too
				# full then we will refuse to read anything from the
				# socket until they are lower
				if sc.canSend() < 1024 * 1024 * 10:
					_readable.append(sock)
			readable = _readable
					
			# every minute dump client statistics, this was mainly intended
			# to give the server administrator a way to diagnose misbehaving
			# clients by seeing how much CPU they are eating up compared to
			# other clients
			'''
			ddet = time.time()
			if ddet - ddst > 60:
				fd = open('clientdiag', 'w')
				ddst = ddet
				for scaddr in self.sc:
					sc = self.sc[scaddr]
					fd.write('client-object:%s address:%s\n' % (sc, scaddr))
					# this are the times spent on individual messages and
					# can help narrow down the problem represented by the
					# chunk times output
					fd.write('  REQUEST-TIMES\n')
					x = 0
					while x < len(sc.times_request):
						t = sc.times_request[x]
						fd.write('    [%02i]: %s\n' % (x, t))
						x = x + 1
					# the chunk times represent the time spent per buffer
					# processing which includes the process of all individual
					# messages; this better represents the amount of continuous
					# time spent per client before processing the next client
					# which if is long can represent effectively a DoS
					fd.write('  CHUNK-TIMES\n')
					x = 0
					while x < len(sc.times_buffer):
						t = sc.times_buffer[x]
						fd.write('    [%02i]: %s\n' % (x, t))
						x = x + 1
				fd.close()
			'''
			# read any pending data (and process it)
			for sock in readable:
				sc = self.socktosc[sock]
				try:
					data = sock.recv(self.maxclientbuffer - sc.GetBufferSize())
				except ssl.SSLError as e:
					# just ignore it
					continue
				except Exception as e:
					#print(e)
					#raise e
					traceback.print_exc(file = sys.stdout)
					data = None
					
				if not data:
					# connection closed, drop it
					print('dropped connection %s' % (sc.GetAddr(),))
					sc.Cleanup()
					del self.sc[sc.GetAddr()]
					del self.socktosc[sock]
					#output.RemWorkingItem(sc)
				else:
					# for production this should be enabled to
					# keep the server from die-ing a horrible
					# death due to one client problem, for now
					# i am leaving it commented so i can easily
					# find problems by crashing the server
					try:
						sc.HandleData(data)
					except Exception as e:
						traceback.print_exc(file = sys.stdout)
						#raise e
						# to keep from killing the server and
						# any other clients just kill the client
						# and keep going
						sc.Cleanup()
						del self.sc[sc.GetAddr()]
						del self.socktosc[sc.GetSock()]
						sc.GetSock().close()
						#output.RemWorkingItem(sc)

			# handle any exceptions
			for sock in exc:
				sc.Cleanup()
				sc = self.socktosc[sock]
				del self.sc[sc.GetAddr()]
				del self.socktosc[sock]
				#output.RemWorkingItem(sc)
				
			# continue main loop
			continue

import cProfile
import time


#print "Wall time:"
#p = cProfile.Profile()
#p.runcall(target)
#p.print_stats()

#print "CPU time:"
			
def main():
	server = Server()
	server.HandleMessages()

main()
	
#p = cProfile.Profile(time.clock)
#try:
#	p.runcall(main)
#except:
#	p.print_stats()