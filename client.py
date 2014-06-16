import os
import sys
import socket
import struct
import hashlib
import math
import threading
import bz2
import ssl
import traceback
from io import BytesIO

from lib import output
from lib import pubcrypt
from lib.pkttypes import *
from lib.misc import *

class UnknownMessageTypeException(Exception):
	pass

class QuotaLimitReachedException(Exception):
	pass
	
class Client:
	def __init__(self, rhost, rport, aid):
		self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.keepresult = {}
		self.vector = 0
		self.rhost = rhost
		self.rport = rport
		self.aid = aid
		self.sockreadgate = threading.Condition()
		self.socklockread = threading.Lock()
		self.socklockwrite = threading.Lock()
		self.bytesout = 0					# includes just actual data bytes
		self.bytesoutst = time.time()
		self.bz2compression = 9
		self.allbytesout = 0				# includes control bytes and data
		self.workerfailure = False
		self.workeralivecount = 0
		self.lasttitleupdated = 0
		self.workerpool = None
		self.workpool = None
		
		self.dbgl = time.time()
		self.dbgv = 0
		self.dbgc = 0
	
	def Connect(self, essl = False):
		# try to establish a connection
		if essl:
			self.sock = ssl.wrap_socket(self.sock)
		
		if essl:
			self.sock.connect((self.rhost, self.rport + 1))
		else:
			self.sock.connect((self.rhost, self.rport))
		
		self.ssl = essl
		
		if not self.ssl:
			# get public key
			#print('requesting public key')
			self.WriteMessage(struct.pack('>B', ClientType.GetPublicKey), False, True)
			# wait for packet
			s, v, pubkey = self.ReadMessage()
			type, esz = struct.unpack_from('>BH', pubkey)
			#print('esz:%s' % (esz))
			e = pubkey[3:3 + esz]
			p = pubkey[3 + esz:]
			self.pubkey = (e, p)
			#print(self.pubkey)
			# setup encryption
			key = IDGen.gen(10)
			#print('key:%s' % key)
			self.crypter = SymCrypt(key)
			self.WriteMessage(struct.pack('>B', ClientType.SetupCrypt) + key, False, True)
			# wait for reply
			#print('waiting for setup crypt reply')
			self.ReadMessage()
			#print('logging into the system')

		# do this even with SSL
		data = struct.pack('>B', ClientType.Login) + self.aid
		#print('writing-message:[%s]' % data)
		self.WriteMessage(data, False, True)
		#print('waiting for login reply')
		result = self.ProcessMessage(0, 0, self.ReadMessage()[2])
		if result:
			print('login good')
			return True
		else:
			print('login bad')
			exit() 
			return False
	# processes any incoming messages and exits after specified time
	def HandleMessages(self, timeout, lookfor = None):
		# while we wait for the lock keep an eye out for
		# out response to arrive
		while not self.socklockread.acquire(False):
			# check if vector has arrived
			if lookfor in self.keepresult and self.keepresult[lookfor] is not None:
				# okay return it and release the lock
				ret = self.keepresult[lookfor]
				# remove it
				del self.keepresult[lookfor]
				#print('GOTGOT')
				return ret
			time.sleep(0.001)
	
		if timeout is not None:
			st = time.time()
			et = st + timeout
		while timeout is None or timeout < 0 or et - time.time() > 0:
			if timeout is not None:
				to = et - time.time()
				if to < 0:
					to = 0
			else:
				to = None
			#print('reading for message vector:%s' % lookfor)
			sv, v, d = self.ReadMessage(to)
			msg = self.ProcessMessage(sv, v, d)
			#print('got msg vector:%s' % v)
			#print('processed message sc:%s v:%s lookfor:%s msg:%s' % (sv, v, lookfor, msg))
			if lookfor == v:
				#print('thread:%s FOUND MSG' % threading.currentThread())
				if v in self.keepresult:
					del self.keepresult[v]
				self.socklockread.release()
				return msg
			# either store it or throw it away
			if v in self.keepresult:
				self.keepresult[v] = msg
			continue
		self.socklockread.release()
		return
		
	# processes any message and produces output in usable form
	def ProcessMessage(self, svector, vector, data):
		type = data[0]
		
		#print('got type %s' % type)
		
		# only process encrypted messages
		if type != ServerType.Encrypted:
			#print('NOT ENCRYPTED')
			return None
			
		# decrypt message (drop off encrypted type field)
		if False and not self.ssl:
			#print('DECRYPTING')
			data = self.crypter.decrypt(data[1:])
		else:
			#print('NOT DECRYPTING')
			data = data[1:]
			
		type = data[0]
		data = data[1:]
		
		# set compression level (can be sent by server at any time
		# and client does not *have* to respect it, but the server
		# could kick the client off if it did not)
		if type == ServerType.SetCompressionLevel:
			self.bz2compression = data[0]
			return
		# process message based on type
		if type == ServerType.LoginResult:
			#print('login result data:[%s]' % data)
			if data[0] == ord('y'):
				return True
			return False
		if type == ServerType.DirList:
			# i hate to chop strings but...later make more efficient
			#print('parsing DirList results')
			list = []
			while len(data) > 0:
				# parse header
				fnamesz, frev = struct.unpack_from('>HI', data)
				# grab out name
				fname = data[2 + 4: 2 + 4 + fnamesz]
				# chop off part we just read
				data = data[2 + 4 + fnamesz:]
				# build list
				list.append((fname, frev))
			# return list
			return list
		if type == ServerType.FileTime:
			return struct.unpack_from('>Q', data)[0]
		if type == ServerType.FileRead:
			return (struct.unpack_from('>B', data)[0], data[1:])
		if type == ServerType.FileWrite:
			return struct.unpack_from('>B', data)[0]
		if type == ServerType.FileSize:
			return struct.unpack_from('>BQ', data)
		if type == ServerType.FileTrun:
			code = struct.unpack_from('>B', data)[0]
			# this is a special situation where they have reached their quota
			if code == 9:
				# i want to force this to be handled which is unhandled
				# should terminate the client ending the push to the server
				# which will get the users attention; do not want this to
				# end up silently happening and the users not noticing or
				# the developer who modified the client accidentally ignoring
				# it since it is an issue that needs to be addressed
				print('WARNING: QUOTA LIMIT REACHED THROWING EXCEPTION')
				raise QuotaLimitReachedException()
			return code
		if type == ServerType.FileDel:
			return struct.unpack_from('>B', data)[0]
		if type == ServerType.FileCopy:
			return struct.unpack_from('>B', data)[0]
		if type == ServerType.FileMove:
			return struct.unpack_from('>B', data)[0]
		if type == ServerType.FileHash:
			return (struct.unpack_from('>B', data)[0], data[1:])
		if type == ServerType.FileStash:
			return struct.unpack_from('>B', data)[0]
		if type == ServerType.FileGetStashes:
			parts =  data.split('.')
			out = []
			for part in parts:
				out.append(int(part))
			return out
		raise UnknownMessageTypeException('%s' % type)
	
	def recv(self, sz):
		_sz = sz
		data = BytesIO()
		while sz > 0:
			_data = self.sock.recv(sz)
			sz = sz - len(_data)
			data.write(_data)
		data.seek(0)
		data = data.read()
		assert(len(data) == _sz)
		return data
	
	# read a single message from the stream and exits after specified time
	def ReadMessage(self, timeout = None):
		#print('reading message')
		self.sock.settimeout(timeout)
		sz, svector, vector = struct.unpack('>IQQ', self.recv(4 + 8 + 8))
		#print('read header')
		data = self.recv(sz)
		#print('read data', data)
		return svector, vector, data
		
	def WriteMessage(self, data, block, discard):
		with self.socklockwrite:
			vector = self.vector
			self.vector = self.vector + 1
			
		# little sanity here.. if were blocking for
		# a reply for a vector then we dont want to
		# have it discarded by another thread if we
		# are using multiple threads... SO..
		if block:
			discard = False
			
		# get type
		type = data[0]
		
		# leave get public key and setup crypt unaltered
		if type == ClientType.GetPublicKey:
			# do not encrypt at all
			pass
		else:
			if type == ClientType.SetupCrypt:
				# public key crypt
				data = data[0:1] + pubcrypt.crypt(data[1:], self.pubkey)
			else:
				# if not SSL then use our built-in encryption
				if False and not self.ssl:
					data = bytes([ClientType.Encrypted]) + self.crypter.crypt(data)
				else:
					# we just pretend its encrypted when really its not, however
					# since we are using SSL the individual messages are not encrypted
					# but the entire socket stream is.. so just prepend this header
					data = bytes([ClientType.Encrypted]) + data
		
		# lock to ensure this entire message is placed
		# into the stream, then unlock so any other
		# thread can also place a message into the stream
		#print('waiting at write lock')
		with self.socklockwrite:
			#print('inside write lock')
			# setup to save message so it is not thrown away
			if discard is False:
				self.keepresult[vector] = None
				#print('    keeping result for vector:%s' % vector)
			self.send(struct.pack('>IQ', len(data), vector))
			self.send(data)
			# track the total bytes out
			self.allbytesout = self.allbytesout + 4 + 8 + len(data)
			#print('sent data for vector:%s' % vector)
			
		if block:
			#print('blocking by handling messages')
			#print('blocking for vector:%s' % vector)
			res = self.HandleMessages(None, lookfor = vector)
			#print('	returned with res:%s' % (res,))
			return res
		return vector
	
	def send(self, data):
		#self.sock.sendall(data)
		totalsent = 0
		while totalsent < len(data):
			sent = self.sock.send(data[totalsent:])
			if sent == 0:
				raise RuntimeError("socket connection broken")
			totalsent = totalsent + sent
	
	def DirList(self, dir, block = True, discard = False):
		return self.WriteMessage(struct.pack('>B', ClientType.DirList) + dir, block, discard)
	def FileRead(self, fid, offset, length, block = True, discard = False):
		return self.WriteMessage(struct.pack('>BHQQ', ClientType.FileRead, fid[1], offset, length) + fid[0], block, discard)
	def FileWrite(self, fid, offset, data, block = True, discard = False):
		#print('compresslevel:%s' % self.bz2compression)
		if self.bz2compression > 0:
			data = bz2.compress(data, compresslevel=self.bz2compression)
		#bz = bz2.BZ2Compressor(compresslevel=self.bz2compression)
		#out = []
		#out.append(bz.compress(data))
		#out.append(bz.flush())
		#data = b''.join(out)
		return self.WriteMessage(struct.pack('>BHQHB', ClientType.FileWrite, fid[1], offset, len(fid[0]), self.bz2compression) + fid[0] + data, block, discard)
	def FileSize(self, fid, block = True, discard = False):
		return self.WriteMessage(struct.pack('>BH', ClientType.FileSize, fid[1]) + fid[0], block, discard)
	def FileTrun(self, fid, newsize, block = True, discard = False):
		return self.WriteMessage(struct.pack('>BHQ', ClientType.FileTrun, fid[1], newsize) + fid[0], block, discard)
	def FileDel(self, fid, block = True, discard = False):
		return self.WriteMessage(struct.pack('>BH', ClientType.FileDel, fid[1]) + fid[0], block, discard)
	def FileCopy(self, srcfid, dstfid, block = True, discard = False):
		return self.WriteMessage(struct.pack('>BHHH', ClientType.FileCopy, srcfid[1], dstfid[1], len(srcfid[0])) + srcfid[0] + dstfid[0], block, discard)
	def FileMove(self, fid, newfile, block = True, discard = False):
		return self.WriteMessage(struct.pack('>BHHH', ClientType.FileMove, srcfid[1], dstfid[1], len(srcfid[0])) + srcfid[0] + dstfid[0], block, discard)
	def FileHash(self, fid, offset, length, block = True, discard = False):
		return self.WriteMessage(struct.pack('>BHQQ', ClientType.FileHash, fid[1], offset, length) + fid[0], block, discard)
	def FileStash(self, fid, block = True, discard = False):
		return self.WriteMessage(struct.pack('>BH', ClientType.FileStash, fid[1]) + fid[0])
	def FileGetStashes(self, fid, block = True, discard = False):
		return self.WriteMessage(struct.pack('>BH', ClientType.FileGetStashes, fid[1]) + fid[0])
	def FileTime(self, fid, block = True, discard = False):
		return self.WriteMessage(struct.pack('>BH', ClientType.FileTime, fid[1]) + fid[0], block, discard)

class Client2(Client):
	def __init__(self, rhost, rport, aid):
		Client.__init__(self, rhost, rport, aid)
		self.maxbuffer = 1024 * 1024 * 8
		self.workers = []

	def __HashLocalFile(self, fd, offset, length):
		fd.seek(offset)
		data = fd.read(length)
		
		return hashlib.sha512(data).digest()

	def UploadFile(self, fid, fd, lsz, name):
		max = self.maxbuffer
		x = 0
		c = math.ceil(lsz / max)
		fd.seek(0)
		while x < c:
			if x * max + max > lsz:
				_sz = lsz - (x * max)
			else:
				_sz = max
			off = x * max
			#print('  uploading offset:%x/%x size:%x' % (off, lsz, _sz))
			self.FileWrite(fid, off, fd.read(_sz), block = False, discard = True)
			output.SetCurrentProgress(name, x / c)
			x = x + 1
			#print('$')
		output.SetCurrentProgress(name, x / c)
		
	def __FilePatch(self, lfd, rfd, offset, sz, match, info, depth = 0):
		tfsz = info['total-size']
		unet = info.get('net-traffic', 0)
		gbytes = info.get('good-bytes', 0)
		
		# at this point it is completely pointless to continue
		# as we have already consumed enough net traffic to have
		# uploading the file whole (so we are just wasting time
		# and bandwidth to continue onward)
		if unet >= tfsz - gbytes:
			return
			
		# at this point in time we should likely consider giving
		# up and exclude the good range we have found if ny
		#if unet >= (tfsz - gbytes) / 4:
		if unet >= tfsz / 4:
			return
		
		# dont do larger than 1MB chunk
		divide = int(sz / self.maxbuffer)
		# change it up if we have less than 20
		#if divide < 20:
		#	divide = 20
			# if the size is less than 4096 then change that
			# to a minimum of 4096
		#	if sz / divide < 4096:
		#		divide = math.ceil(sz / 4096)
		
		# calculate actual chunk size to hash and count
		# with remainder either as a separate chunk or
		# combined with last
		
		if divide == 0:
			pasz = 0
		else:
			pasz = sz / divide
			pasz = math.floor(pasz)
		rem = sz - (pasz * divide)
		
		go = []
		# build the primary checks
		x = 0
		while x < divide - 1:
			go.append((offset + x * pasz, pasz))
			x = x + 1
		if rem > pasz / 2:
			# split it into two separate checks
			go.append((offset + x * pasz, pasz))
			go.append((offset + x * pasz + pasz, rem))
		else:
			# combine into one
			go.append((offset + x * pasz, pasz + rem))
		
		# iterate through checks
		for c in go:
			rhash = self.FileHash(rfd, c[0], c[1])[1]
			lhash = self.__HashLocalFile(lfd, c[0], c[1])
			info['net-traffic'] = info.get('net-traffic', 0) + 200
			
			# debug message
			#print('    unet:%x gbytes:%x hashing offset:%x length:%x' % (unet, gbytes, c[0], c[1]))
			
			# should we go deeper
			if c[1] < 4096:
				continue
				
			if rhash != lhash:
				# go deeper
				self.__FilePatch(lfd, rfd, c[0], c[1], match, info, depth = depth + 1)
			else:
				# record parts that do not need to be updated
				info['good-bytes'] = info.get('good-bytes', 0) + sz
				match.append((offset, sz))
				#print('found good area offset:%s sz:%s' % (c[0], c[1]))
			x = x + 1
		return
	
	def FilePull(self, lfile, fid):
		return self.__FileSync(fid, lfile, synclocal = True)
	
	'''
		@sdescription:		Will upload or update the remote file with this local
							file by delta-copy or whole file upload.
	'''
	def FilePush(self, fid, lfile):
		# if failure of worker thread
		if self.workerfailure:
			# oops.. we got a problem.. lets shut everything down
			raise Exception('Worker Thread Crashed')
			
		# keep title updated
		if time.time() - self.lasttitleupdated > 2:
			self.lasttitleupdated = time.time()
			self.__UpdateTitle()
		'''
		# just wait until some workers die off
		while self.workeralivecount > 128:
			time.sleep(0.1)

		# create thread that performs the file sync operation
		thread = threading.Thread(target = Client2.WorkerThreadEntry, args = (self, fid, lfile, False))
		self.workeralivecount = self.workeralivecount + 1
		# store the worker in the list
		self.workers.append(thread)
		thread.start()
		'''
		
		if self.workpool is None:
			self.workpool = []
			self.workhere = threading.Condition()
			self.workpoolguard = threading.Lock()
			self.workersdie = False
		
		if self.workerpool is None:
			# fill worker pool with workers
			self.workerpool = []
			for x in range(0, 64):
				thread = threading.Thread(target = Client2.WorkerPoolEntry, args = (self, x))
				thread.daemon = True
				thread.start()
				self.workerpool.append(thread)
						
		self.dbgc = self.dbgc + 1
		# add work item
		self.workpool.append((fid, lfile, False))
		
		# @TODO:THREADED IFFY
		# i think it is fairly safe to check the length
		# even *if* another thread is modifying it..
		if len(self.workpool) > 128:
			# apparently things are not getting done so
			# lets wait around and keep signalling the
			# condition in hopes a thread finally releases
			# and services the job queue
			while len(self.workpool) > 128:
				time.sleep(0.1)
		# this should release a thread only if
		# one was waiting, so if none were waiting
		# then hopefully the worker's time out on
		# its wait method will kick in and allow it
		# to service jobs after it is done
		self.workhere.acquire()
		self.workhere.notify()
		self.workhere.release()		
		
	def WaitUntilWorkersFinish(self):
		print('[master] waiting on workers to complete')
		self.workersdie = True
		while len(self.workpool) > 0:
			time.sleep(0.1)
			self.__UpdateTitle()
			output.Update()
		
	def WorkerPoolEntry(self, myid):
		while True:
			if self.workersdie:
				return
			# wait on lock
			self.workhere.acquire()
			#
			print('[worker:%x] waiting' % myid)
			self.workhere.wait(1)
			print('[worker:%x] looking' % myid)
			# there could have been more than one
			# thread release when the lock was signalled
			# or when the time out occurs.. the docs
			# state an optimized implementation of
			# the Condition object could allow more than
			# one to release on notify occasionally
			with self.workpoolguard:
				if len(self.workpool) < 1:
					print('[worker:%x] no work' % myid)
					self.workhere.release()
					continue
				print('[worker:%x] getting work' % myid)
				workitem = self.workpool.pop(0)
			self.workhere.release()
			# work on the job
			print('[worker:%x] working' % myid)
			self.WorkerThreadEntry(workitem[0], workitem[1], workitem[2])
		
	def __UpdateTitle(self):
		c = 0
		for worker in self.workers:
			if worker.isAlive():
				c = c + 1
				
		d = time.time() - self.dbgl
		d = self.dbgc / d
		self.dbgc = 0
		self.dbgl = time.time()
				
		if self.workpool is not None:
			wpc = len(self.workpool)
		else:
			wpc = 'None'

		# new title styles handles individual indication rather
		# than a solid string which allows programs reading our
		# output to make better usage of the output
		output.SetTitle('outmb', self.bytesout  / 1024 / 1024)
		output.SetTitle('totoutmb', self.allbytesout / 1024 / 1024)
		output.SetTitle('wpc', wpc)
		output.SetTitle('c', c)
		output.SetTitle('areqs', len(self.keepresult))
		output.SetTitle('d', d)
		#output.SetTitle('%s %s tc:%s wpool:%s areqs:%s tpw:%s' % (outkb[0:20], totoutkb[0:20], wpc, c, len(self.keepresult), d))
		
	def WorkerThreadEntry(self, fid, lfile, synclocal):
		try:
			self.__FileSync(fid, lfile, synclocal)
		except:
			traceback.print_exc(file = sys.stdout)
			# flag to the main thread that we have run
			# into some trouble and require help
			self.workerfailure = True
		self.workeralivecount = self.workeralivecount - 1
		
	def __FileSync(self, fid, lfile, synclocal = False):
		output.AddWorkingItem(lfile)
		try:
			if synclocal:
				#print('SYNCLOCAL', lfile)
				# make sure the file is created
				if os.path.exists(lfile) is False:
					fd = open(lfile, 'wb')
					fd.close()
			if synclocal:
				fd = open(lfile, 'r+b')
			else:
				fd = open(lfile, 'rb')
		except IOError as e:
			# for some reason we are unable to access
			# the file so just print an exception and
			# skip this file
			raise e
			print('    skipping %s' % lfile)
			output.RemWorkingItem(lfile)
			return
		#	print(e)
		#	exit()
		#	return 
		# get length of local file
		fd.seek(0, 2)
		lsz = fd.tell()
		fd.seek(0)
		#print('patching remote file %s with local file %s' % (fid[0], lfile))
		#print('	setup')
		# get length of remote file if it exists
		#print('fid', fid)
		output.SetCurrentStatus(lfile, 'QUERY FILE SIZE')
		rsz = self.FileSize(fid)[1]
		# either make remote smaller or bigger
		#print('rsz:%s lsz:%s' % (rsz, lsz)
		
		mode, ino, dev, nlink, uid, gid, size, atime, mtime, ctime = os.stat(lfile)
		
		output.SetCurrentStatus(lfile, 'QUERY FILE TIME')
		rmtime = self.FileTime(fid)
		
		if lsz == rsz and mtime <= rmtime:
			# remote file is same size and is same time or newer so dont overwrite or push to it
			# or even worry about checking the hash
			output.SetCurrentStatus(lfile, 'NOT MODIFIED')
			if mtime < rmtime:
				print('NEWER[%s]' % lfile)
				output.RemWorkingItem(lfile)
				return
			if mtime == rmtime:
				print('SAME[%s]' % lfile)
				output.RemWorkingItem(lfile)
				return
			return
		
		print('rmtime:%s mtime:%s' % (rmtime, mtime))
		
		# if syncing to remote truncate remote file
		if rsz != lsz:
			if synclocal is False:
				# if syncing remote to local then truncate remote
				self.FileTrun(fid, lsz)
			else:
				# if syncing local to remote then truncate local
				fd.close()
				fd = os.open(lfile, os.O_RDWR)
				os.ftruncate(fd, rsz)
				os.close(fd)
				fd = open(lfile, 'r+b')

		if synclocal is False:
			if rsz < lsz / 2:
				# just upload it whole
				print('UPLOAD[%s]' % lfile)
				output.SetCurrentStatus(lfile, 'UPLOAD')
				self.UploadFile(fid, fd, lsz, lfile)
				output.SetCurrentStatus(lfile, 'UPLOADED')
				fd.close()
				self.bytesout = self.bytesout + lsz
				output.RemWorkingItem(lfile)
				return
		else:
			if lsz < rsz / 2:
				output.SetCurrentStatus(lfile, 'DOWNLOAD')
				self.DownloadFile(fid, fs, rsz, lfile)
				fd.close()
				output.SetCurrentStatus(lfile, 'DOWNLOADED')
				output.RemWorkingItem(lfile)
				return
				
		#self.FileWrite(fid, 0, b'hello world')
		#exit()
			
		#rhash = self.FileHash(fid, 25, 25)[1]
		#lhash = self.__HashLocalFile(fd, 25, 25)
		#print(rhash)
		#print(lhash)
		
		#print(self.FileRead(fid, 25, 25))
		#exit()
			
		if synclocal is False:
			tsz = lsz
		else:
			tsz = rsz
			
		# prepare structures
		match = []
		info = {
			'total-size':		tsz
		}
		# build match list
		#print(' hash scanning')
		
		# break it into maximum sized chunks
		# in order to prevent oversized buffer
		# on the server (done on server to prevent
		# some DoS attacks)
		
		print('PATCHING[%s]' % lfile)
		output.SetCurrentStatus(lfile, 'PATCHING')
		
		max = self.maxbuffer
		pcnt = math.ceil(tsz / max)
		x = 0
		while x < pcnt:
			#print('?')
			if x * max + max > tsz:
				_sz = tsz - (x * max)
			else:
				_sz = max
			off = x * max
				
			self.__FilePatch(fd, fid, off, _sz, match, info)
			x = x + 1
		# we need to invert the match list to
		# determine what regions we need to write
		# to bring the file up to date
		#print('	inverting')
		invert = []
		invert.append((0, info['total-size']))
		for good in match:
			#print('@')
			gx = good[0]
			gw = good[1]
			for bad in invert:
				bx = bad[0]
				bw = bad[1]
				chg = False
				if gx == bx and gx + gw == bx + bw:
					#print('whole')
					bw = 0
					chg = True
				else:
					if gx == bx and gx + gw < bx + bw:
						#print('left side')
						# left side
						bx = gx + gw
						bw = bw - gw
						chg = True
					if gx > bx and gx + gw == bx + bw:
						# right side
						#print('right side')
						bw = bw - gw
						chg = True
					if gx > bx and gx + gw < bx + bw:
						# middle (left side)
						#print('middle')
						_bw = bw
						bw = gx - bx
						# middle (right side)
						_bx = gx + gw
						_bw = _bw - (bw + gw)
						invert.append((_bx, _bw))
						chg = True
				if chg:
					# remove old one and add new one
					invert.remove(bad)
					if bw > 0:
						invert.append((bx, bw))
					# exit out if found it
					break
			# invert iteration
		# match iteration
	
		# now only upload the bad parts
		cx = 0
		for bad in invert:
			bx = bad[0]
			bw = bad[1]
			# cut it into max sized pieces
			divide = math.floor(bw / self.maxbuffer)
			rem = int(bw - (divide * self.maxbuffer))
			
			x = 0
			while x < divide:
				#print('.')
				o = x * self.maxbuffer
				fd.seek(bx + o)
				#print('writing bad (%s:%s)' % (bx + o, self.maxbuffer))
				if synclocal is False:
					data = fd.read(self.maxbuffer)
					self.FileWrite(fid, bx + o, data, block = False, discard = True)
					self.bytesout = self.bytesout + len(data)
				else:
					data = self.FileRead(self.maxbuffer)[1]
					fd.write(data)			
				x = x + 1
				
			if rem > 0:
				o = x * self.maxbuffer
				fd.seek(bx + o)
				#print('writing bad (%s:%s)' % (bx + o, rem))
				if synclocal is False:
					data = fd.read(rem)
					self.FileWrite(fid, bx + o, data, block = False, discard = True)
					self.bytesout = self.bytesout + len(data)
				else:
					data = self.FileRead(fid, bx + o, rem)[1]
					fd.write(data)
			output.SetCurrentStatus(lfile, 'PATCHING (%x/%s)' % (bx, bw))
			output.SetCurrentProgress(lfile, cx / len(invert))
			cx = cx + 1
		fd.close()
		output.SetCurrentStatus(lfile, 'PATCHED')
		output.RemWorkingItem(lfile)
		
def main():
	client = Client2('localhost', 4322, b'Kdje493FMncSxZs')
	#print('setup connection')
	client.Connect()
	#print('	setup connection done')
	
	'''
	print('requesting directory list')
	list = client.DirList(b'/')
	
	print('truncating file')
	result = client.FileTrun((b'test', 0), 1024)
	print('FileTrun.result:%s' % result)
	
	result = client.FileWrite((b'test', 0), 0, b'hello world')
	print('FileWrite.result:%s' % result)
	
	result = client.FileRead((b'test', 0), 0, 11)
	print('FileRead.result:%s' % (result,))
	
	result = client.FileHash((b'test', 0), 0, 11)
	print('SZ', len(result[1]))
	'''
	
	#result = client.FilePatch((b'sample', 0), './sample')
	
	while True:
		continue

if __name__ == '__main__':
	main()