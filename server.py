import os
import sys
import socket
import select
import struct
import shutil
import hashlib
import pprint
import bz2
from io import BytesIO
import ssl
import status

if status.IsSupported():
	print('STATUS MODULE SUPPORTED ENABLING CURSES')
	status.Init(stdout = 'stdout.server', stderr = 'stderr.server')
else:
	print('STATUS MODULE NOT SUPPORTED')

from pkttypes import *
from misc import *

import pubcrypt

class DoubleTypeOrRevException(Exception):
	pass
	
class NodeTypeUnknownException(Exception):
	pass

class DataBufferOverflowException(Exception):
	pass
	
class ServerClient:
	def GetName(self):
		return '%s:%s' % (self.addr[0], self.addr[1])
		
	def __init__(self, sock, addr, kpub, kpri, server, essl = False):
		self.sock = sock
		self.addr = addr
		self.hdr = b''
		
		self.aid = None
		
		self.ssl = essl
		
		print('HERE')
		if essl:
			print('    wrapping socket with SSL')
			self.sock = ssl.wrap_socket(self.sock, server_side = True, certfile = 'cert.pem', ssl_version = ssl.PROTOCOL_TLSv1)
		
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
			fd = open('./accounts/%s' % self.aid, 'w')
			pprint.pprint(self.info, fd)
			fd.close()
		# close all open file descriptors
		for fpath in self.fdcache:
			c = self.fdcache[fpath]
			c[1].close()
		# just for safety
		self.fdcache = None
		self.__fdcache = None
	
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
		bst = time.time()
		# process data for a message
		while True:
			rst = time.time()
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
			ret = time.time()
			rdt = ret - rst
			if len(self.times_request) > 40:
				self.times_request.pop(0)
			self.times_request.append(rdt)
			
		bet = time.time()
		bdt = bet - bst
		
		# implement a queue (not a stack)
		if len(self.times_buffer) > 40:
			# keep 40 previous times (essentially 40 previous network packets)
			self.times_buffer.pop(0)
		self.times_buffer.append(bdt)
		
	def SanitizePath(self, path):
		while path.find(b'..') > -1:
			path = path.replace(b'..', b'.')
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
			print('got login message', msg)
			aid = msg.decode('utf8', 'ignore')
			# check that account exists
			if os.path.exists('./accounts/%s' % aid) is False:
				print('account does not exist')
				self.WriteMessage(struct.pack('>B', ServerType.LoginResult) + b'n', vector)
				return
			print('loading account')
			# load account information
			self.aid = aid
			fd = open('./accounts/%s' % aid, 'r')
			self.info = eval(fd.read())
			fd.close()
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
			
		# return a list of nodes in directory
		if type == ClientType.DirList:
			# remove any dot dots to prevent backing out of root
			#print('doing directory listing')
			cpath = '%s/%s' % (self.info['disk-path'], self.SanitizePath(msg).decode('utf8', 'ignore'))
			#print('	calling os.listdir(%s)' % cpath)
			nodes = os.listdir(cpath)
			objs = []
			#print('	iterating nodes')
			for node in nodes:
				# add directories in a special way so that they
				# can be interpreted as a directory and not a file
				if os.path.isdir('%s/%s' % (cpath, node)):
					objs.append((bytes(node, 'utf8'), 0xffffffff))
					continue
				# break node into appropriate parts
				frev = int(node[0:node.find('.')])
				fname = bytes(node[node.find('.') + 1:], 'utf8')
				# there should be only one type of each fname
				if (fname, frev) not in objs:
					# store so we can detect duplicates
					objs.append((fname, frev))
					#print('	added fname:%s frev:%s' % (fname, frev))
				else:
					# since were in development stage get our attention!
					raise DoubleTypeOrRevException()
					# remove it before it causes more problems
					os.remove('%s/%s' % (cpath, node))
			# serialize output into list of entries
			#print('	serializing')
			out = []
			for key in objs:
				print('key[0]:[%s]' % key[0])
				out.append(struct.pack('>HI', len(key[0]), key[1]) + key[0])
			out = b''.join(out)
			#print('	writing message')
			self.WriteMessage(struct.pack('>B', ServerType.DirList) + out, vector)	
			return
		if type == ClientType.FileTime:
			return self.FileTime(msg, vector)
		if type == ClientType.FileSize:
			return self.FileSize(msg, vector)
		if type == ClientType.FileTrun:
			return self.FileTrun(msg, vector)
		if type == ClientType.FileRead:
			rev, offset, length = struct.unpack_from('>HQQ', msg)
			fname = self.SanitizePath(msg[2 + 8 + 8:]).decode('utf8', 'ignore')
			
			# maximum read length default is 1MB (anything bigger must be split into separate requests)
			# OR.. we could spawn a special thread that would lock this client and perform the work
			# in parallel with this main thread
			if length > self.info.get('max-read-length', self.maxbuffer):
				self.WriteMessage(struct.pack('>BB', ServerType.FileRead, 2), vector)
				return

			# get path parts
			fbase, fname = self.GetPathParts(fname)
			
			# build full path to file (including revision)
			fpath = '%s/%s/%s.%s' % (self.info['disk-path'], fbase, rev, fname)
			if os.path.exists(fpath) is False:
				# oops.. no such file (lets tell them it failed)
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
			srcrev, dstrev, srclen = struct.unpack_from('>HHH', msg)
			fsrc = self.SanitizePath(msg[2 * 3: 2 * 3 + srclen:]).decode('utf8', 'ignore')
			fdst = self.SanitizePath(msg[2 * 3 + srclen:]).decode('utf8', 'ignore')
			
			fsrcbase, fsrcname = self.GetPathParts(fsrc)
			fdstbase, fdstname = self.GetPathParts(fdst)
			
			fsrcpath = '%s/%s/%s.%s' % (self.info['disk-path'], fsrcbase, srcrev, fsrcname)
			fdstpath = '%s/%s/%s.%s' % (self.info['disk-path'], fdstbase, dstrev, fdstname)
			
			if os.path.exists(fdstpath) is True:
				if type == ClientType.FileCopy:
					self.WriteMessage(struct.pack('>BB', ServerType.FileCopy, 0), vector)
				else:
					self.WriteMessage(struct.pack('>BB', ServerType.FileMove, 0), vector)
				return
			
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
			rev = struct.unpack_from('>H', msg)[0]
			fname = self.SanitizePath(msg[2:]).decode('utf8', 'ignore')
			
			fbase, fname = self.GetPathParts(fname)
			
			fpath = '%s/%s/%s.%s' % (self.info['disk-path'], fbase, rev, fname)
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
			rev, offset, length = struct.unpack_from('>HQQ', msg)
			fname = self.SanitizePath(msg[2 + 8 * 2:]).decode('utf8', 'ignore')
			
			fbase, fname = self.GetPathParts(fname)
			fpath = '%s/%s/%s.%s' % (self.info['disk-path'], fbase, rev, fname)			
			
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
		if type == ClientType.FileStash:
			pass
		if type == ClientType.FileGetStashes:
			pass
		raise Exception('unknown message type:%s' % type)

	def FileSize(self, msg, vector):
		rev = struct.unpack_from('>H', msg)[0]
		fname = self.SanitizePath(msg[2:]).decode('utf8', 'ignore')
		
		fbase, fname = self.GetPathParts(fname)
		
		fpath = '%s/%s/%s.%s' % (self.info['disk-path'], fbase, rev, fname)
		
		if os.path.exists(fpath) is False:
			self.WriteMessage(struct.pack('>BBQ', ServerType.FileSize, 0, 0), vector)
			return
		
		fd = self.GetFileDescriptor(fpath, 'rb')
		fd.seek(0, 2)
		sz = fd.tell()
		#fd.close()
		
		self.WriteMessage(struct.pack('>BBQ', ServerType.FileSize, 1, sz), vector)
		return
		
	def FileTime(self, msg, vector):
		rev = struct.unpack_from('>H', msg)[0]
		fname = self.SanitizePath(msg[2:]).decode('utf8', 'ignore')
		
		fbase, fname = self.GetPathParts(fname)	
		
		fpath = '%s/%s/%s.%s' % (self.info['disk-path'], fbase, rev, fname)
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
		rev, newsize = struct.unpack_from('>HQ', msg)
		fname = self.SanitizePath(msg[2 + 8:]).decode('utf8', 'ignore')
		
		fbase, fname = self.GetPathParts(fname)
		
		# this will either create the file OR change the size of it
		fpath = '%s/%s/%s.%s' % (self.info['disk-path'], fbase, rev, fname)
		#fd = self.GetFileDescriptor(fpath, 'wb')
		#fd.truncate(newsize)
		#fd.close()
		#print('newsize:%s' % newsize)
		# make directories
		dirpath = fpath[0:fpath.rfind('/')]
		if os.path.exists(dirpath) is False:
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
		# add new size back onto used quota
		self.info['disk-used'] = self.info['disk-used'] + newsize
		# save account information
		self.WriteMessage(struct.pack('>BB', ServerType.FileTrun, 1), vector)
		return

	def FileWrite(self, msg, vector):
		rev, offset, fnamesz, compression = struct.unpack_from('>HQHB', msg)
		fname = self.SanitizePath(msg[2 + 8 + 2 + 1:2 + 8 + 2 + 1 + fnamesz]).decode('utf8', 'ignore')
		data = msg[2 + 8 + 2 + 1 + fnamesz:]
		
		# only decompression if it was compressed
		if compression > 0:
			data = bz2.decompress(data)
		
		length = len(data)
		if length > self.info.get('max-write-length', self.maxbuffer):
			self.WriteMessage(struct.pack('>BB', ServerType.FileWrite, 2), vector)
			return
		
		fbase, fname = self.GetPathParts(fname)
		fpath = '%s/%s/%s.%s' % (self.info['disk-path'], fbase, rev, fname)
		
		if os.path.exists(fpath) is False:
			self.WriteMessage(struct.pack('>BB', ServerType.FileWrite, 0), vector)
			return
		
		fd = self.GetFileDescriptor(fpath, 'r+b')
		
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
		load = ae / ac
	
		text = '%.02f/%.02f/%.02f' %  (in_bps / 1024 / 1024, out_bps / 1024 / 1024, load)
	
		status.SetCurrentStatus(self, text)
		
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
		self.sock.sendall(struct.pack('>IQQ', len(data), 0, vector))
		self.sock.sendall(data)
		self.bytes_out_total = self.bytes_out_total + 4 + 8 * 2 + len(data)
		self.UpdateStatus()
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
		self.UpdateStatus()
		
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
			for scaddr in self.sc:
				tsc = self.sc[scaddr]
				input.append(tsc.GetSock())
				#print('appending client:%s sock' % (scaddr,))
		
			readable, writable, exc = select.select(input, [], input)
			
			# every minute dump client statistics, this was mainly intended
			# to give the server administrator a way to diagnose misbehaving
			# clients by seeing how much CPU they are eating up compared to
			# other clients
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
			
			# accept incoming connections (weak encryption connections)
			if self.sock in readable:
				nsock, caddr = self.sock.accept()
				nsc = ServerClient(nsock, caddr, self.keypub, self.keypri, self)
				self.sc[caddr] = nsc
				self.socktosc[nsock] = nsc
				readable.remove(self.sock)
				status.AddWorkingItem(nsc)
				
			# accept incoming connections (SSL encryption connections)
			if self.sslsock in readable:
				print('ACCEPTING SSL CONNECTION')
				nsock, caddr = self.sslsock.accept()
				nsc = ServerClient(nsock, caddr, self.keypub, self.keypri, self, essl = True)
				# the SSL will change the sock
				nsock = nsc.GetSock()
				self.sc[caddr] = nsc
				self.socktosc[nsock] = nsc
				readable.remove(self.sslsock)
				status.AddWorkingItem(nsc)
			
			# read any pending data (and process it)
			for sock in readable:
				sc = self.socktosc[sock]
				if sc.GetBufferSize() < self.maxclientbuffer:
					try:
						data = sock.recv(self.maxclientbuffer - sc.GetBufferSize())
					except ssl.SSLError as e:
						# just ignore it
						continue
					except Exception as e:
						#print(e)
						#raise e
						data = None
						
					if not data:
						# connection closed, drop it
						print('dropped connection %s' % (sc.GetAddr(),))
						sc.Cleanup()
						del self.sc[sc.GetAddr()]
						del self.socktosc[sock]
						status.RemWorkingItem(sc)
					else:
						# for production this should be enabled to
						# keep the server from die-ing a horrible
						# death due to one client problem, for now
						# i am leaving it commented so i can easily
						# find problems by crashing the server
						try:
							sc.HandleData(data)
						except Exception as e:
							#raise e
							# to keep from killing the server and
							# any other clients just kill the client
							# and keep going
							sc.Cleanup()
							del self.sc[sc.GetAddr()]
							del self.socktosc[sc.GetSock()]
							sc.GetSock().close()
							status.RemWorkingItem(sc)

			# handle any exceptions
			for sock in exc:
				sc.Cleanup()
				sc = self.socktosc[sock]
				del self.sc[sc.GetAddr()]
				del self.socktosc[sock]
				status.RemWorkingItem(sc)
				
			# continue main loop
			continue

def main():
	server = Server()
	server.HandleMessages()
	
main()