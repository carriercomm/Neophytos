import os
import sys
import socket
import struct
import hashlib
import math
import threading
import zlib
import ssl
import traceback
import base64
import select

from io import BytesIO

from lib import output
from lib import pubcrypt
from lib.pkttypes import *
from lib.misc import *

class UnknownMessageTypeException(Exception):
	pass

class QuotaLimitReachedException(Exception):
	pass
	
class ConnectionDeadException(Exception):
	pass
	
class BadLoginException(Exception):
	pass
		
class Client:
	class IOMode:
		Block 		= 1		# Wait for the results.
		Async 		= 2		# Return, and will check for results.
		Callback 	= 3		# Execute callback on arrival.
		Discard		= 4		# Async, but do not keep results.
		
	def __init__(self, rhost, rport, aid):
		self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.keepresult = {}
		self.callback = {}
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
		
		self.lastpushedlfile = ''
		
		self.conntimeout = 60
		self.lastactivity = time.time()
		
		self.data = BytesIO()
		self.datasz = None
		self.datatosend = []
		self.bytestosend = 0
		
		self.dbgl = time.time()
		self.dbgv = 0
		self.dbgc = 0
	
	def Shutdown(self):
		self.sock.close()
	
	def close(self):
		self.sock.close()
	
	def Connect(self, essl = False):
		# try to establish a connection
		if essl:
			self.sock = ssl.wrap_socket(self.sock, ciphers = 'RC4')
		
		if essl:
			self.sock.connect((self.rhost, self.rport + 1))
			output.SetTitle('ssl-cipher', self.sock.cipher())
		else:
			self.sock.connect((self.rhost, self.rport))
		
		self.ssl = essl
		
		if not self.ssl:
			# get public key
			vector = self.WriteMessage(struct.pack('>B', ClientType.GetPublicKey), Client.IOMode.Async)
			s, v, pubkey = self.HandleMessages(lookfor = vector)
			type, esz = struct.unpack_from('>BH', pubkey)
			e = pubkey[3:3 + esz]
			p = pubkey[3 + esz:]
			self.pubkey = (e, p)
			# kinda been disabled... but still left in
			key = IDGen.gen(10)
			self.crypter = SymCrypt(key)
			self.WriteMessage(struct.pack('>B', ClientType.SetupCrypt) + key, Client.IOMode.Discard)

		data = struct.pack('>B', ClientType.Login) + self.aid
		vector = self.WriteMessage(data, Client.IOMode.Async)
		result = self.HandleMessages(lookfor = vector)
		
		# initialize the time we starting recording the number of bytes sent
		self.bytesoutst = time.time()
		print('login-result', result)
		if result:
			return True
		else:
			raise BadLoginException()

	def GetStoredMessage(self, vector):
		with self.socklockread:
			if vector in self.keepresult and self.keepresult[vector] is not None:
				ret = self.keepresult[vector]
				del self.keepresult[vector]
				return ret
		return None
	
	def waitCount(self):
		return len(self.keepresult) + len(self.callback)

	def dbgdump(self):
		for v in self.keepresult:
			print('keepresult:%s' % v)
		for v in self.callback:
			print('callback:%s' % v)
	
	# processes any incoming messages and exits after specified time
	def HandleMessages(self, timeout = None, lookfor = None):
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
		
		once = False
		while timeout is None or timeout < 0 or et - time.time() > 0 or once is False:
			# at least loop once in the event timeout was too small
			once = True
			
			if timeout is not None:
				to = et - time.time()
				if to < 0:
					to = 0
			else:
				to = None
			#print('reading for message vector:%s' % lookfor)
			sv, v, d = self.ReadMessage(to)
			if sv is None:
				# if we were reading using a time out this can happen
				# which means there was no data to be read in the time
				# specified to read, so lets just continue onward
				continue
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
			# check for callback
			if v in self.callback:
				cb = self.callback[v]
				del self.callback[v]
				cb[0](cb[1], msg, v)
			continue
		self.socklockread.release()
		return
	
	# processes any message and produces output in usable form
	def ProcessMessage(self, svector, vector, data):
		type = data[0]
		
		#print('got type %s' % type)

		print('e-type', type)
		
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
		
		print('u-type', type)

		# set compression level (can be sent by server at any time
		# and client does not *have* to respect it, but the server
		# could kick the client off if it did not)
		if type == ServerType.SetCompressionLevel:
			self.bz2compression = data[0]
			return
		# process message based on type
		if type == ServerType.LoginResult:
			print('login result data:[%s]' % data)
			if data[0] == ord('y'):
				return True
			return False
			
		if type == ServerType.DirList:
			result = struct.unpack_from('>B', data)[0]
			
			# path could not be accessed
			if result == 0:
				return None
			
			data = data[1:]
			
			list = []
			while len(data) > 0:
				# parse header
				fnamesz, ftype = struct.unpack_from('>HB', data)
				# grab out name
				fname = data[3: 3 + fnamesz]
				# decode it back to what we expect
				fname = self.FSDecodeBytes(fname)
				# chop off part we just read
				data = data[3 + fnamesz:]
				# build list
				list.append((fname, ftype))
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
		if type == ServerType.Echo:
			return True
		if type == ServerType.FileSetTime:
			return struct.unpack_from('>B', data)[0]
		if type == ServerType.FileGetStashes:
			parts =  data.split('.')
			out = []
			for part in parts:
				out.append(int(part))
			return out
		raise UnknownMessageTypeException('%s' % type)
	
	def ifDead(self):
		tdelta = (time.time() - self.lastactivity)
		if tdelta > self.conntimeout:
			raise ConnectionDeadException()
	
	def recv(self, sz):
		data = self.data

		#self.sock.settimeout(0)
		
		# keep track of if we have enough data in our buffer
		while data.tell() < sz:
			# calculate how long we can wait
			#tdelta = (time.time() - self.lastactivity)
			#twait = self.conntimeout - tdelta
			#if twait < 0:
			#	raise ConnectionDeadException()
			try:
				# i am using select because settimeout does not
				# seem to work for the recv method.. so this is
				# a workaround to force it to work
				print('waiting for %s more bytes' % (sz - data.tell()))
				ready = select.select([self.sock], [], [], self.sock.gettimeout())
				if ready[0]:
					_data = self.sock.recv(sz)
					if _data is not None and len(_data) > 0:
						self.lastactivity = time.time()
					else:
						# as far as i can tell if receive returns an empty
						# byte string after select signalled it for a read
						# then the connection has closed..
						raise ConnectionDeadException()
				else:
					#self.ifDead()
					return None
			except ssl.SSLError:
				# check if dead..
				#self.ifDead()
				return None
			except socket.error:
				# check if dead..
				#self.ifDead()
				return None
			# save data in buffer
			data.write(_data)
	
		# check if connection is dead
		#self.ifDead()
		
		# only return with data if its of the specified length
		if data.tell() >= sz:
			# read out the data
			data.seek(0)
			_data = data.read(sz)
			self.data = BytesIO()
			self.data.write(data.read())
			return _data
		return None
	
	# read a single message from the stream and exits after specified time
	def ReadMessage(self, timeout = None):
		self.sock.settimeout(timeout)
		
		# if no size set then we need to read the header
		if self.datasz is None:
			data = self.recv(4 + 8 + 8)
			if data is None:
				return None, None, None
			
			sz, svector, vector = struct.unpack('>IQQ', data)
			self.datasz = sz
			self.datasv = svector
			self.datav = vector
			
		# try to read the remaining data
		data = self.recv(self.datasz)
		if data is None:
			# not enough data read
			return None, None, None
		
		# ensure the next reads tries to get the header
		self.datasz = None
		
		print('got message', self.datasv, self.datav, data)

		# return the data
		return self.datasv, self.datav, data
		
	def WriteMessage(self, data, mode, callback = None):
		with self.socklockwrite:
			vector = self.vector
			self.vector = self.vector + 1
		
		# get type
		type = data[0]
		
		# leave get public key and setup crypt unaltered
		if type == ClientType.GetPublicKey:
			# do not encrypt at all
			pass
		else:
			if type == ClientType.SetupCrypt:
				# public key crypt
				if not self.ssl:
					data = data[0:1] + pubcrypt.crypt(data[1:], self.pubkey)
			else:
				# if not SSL then use our built-in encryption
				if False and not self.ssl:
					data = bytes([ClientType.Encrypted]) + self.crypter.crypt(data)
				else:
					# we just pretend its encrypted when really its not, however
					# since we are using SSL the individual messages are not encrypted
					# but the entire socket stream is.. so just prepend this header
					
					# lets encryption the login if we are not using SSL
					if not self.ssl and type == ClientType.Login:
						data = data[0:1] + pubcrypt.crypt(data[1:], self.pubkey)
					data = bytes([ClientType.Encrypted]) + data
		
		# lock to ensure this entire message is placed
		# into the stream, then unlock so any other
		# thread can also place a message into the stream
		#print('waiting at write lock')
		with self.socklockwrite:
			#print('inside write lock')
			# setup to save message so it is not thrown away
			if mode == Client.IOMode.Callback:
				self.callback[vector] = callback
			if mode == Client.IOMode.Async:
				self.keepresult[vector] = None
			
			self.send(struct.pack('>IQ', len(data), vector))
			self.send(data)
			# track the total bytes out
			self.allbytesout = self.allbytesout + 4 + 8 + len(data)
			#print('sent data for vector:%s' % vector)
			
		if mode == Client.IOMode.Block:
			#print('blocking by handling messages')
			#print('blocking for vector:%s' % vector)
			res = self.HandleMessages(None, lookfor = vector)
			#print('	returned with res:%s' % (res,))
			return res
		return vector
	
	def canSend(self):
		return len(self.datatosend) > 0
	
	def getBytesToSend(self):
		return self.bytestosend
	
	def handleOrSend(self):
		# wait until the socket can read or write
		read, write, exp = select.select([self.sock], [self.sock], [])
		
		if read:
			# it will block by default so force
			# it to not block/wait
			self.HandleMessages(0, None)
		if write:
			# dump some of the buffers if any
			self.send()
	
	def send(self, data = None, timeout = 0):
		if data is not None:
			self.datatosend.append(data)
			self.bytestosend = self.bytestosend + len(data)
		
		self.sock.settimeout(timeout)
		
		# check there is data to send
		while len(self.datatosend) > 0:
			# pop from the beginning of the queue
			data = self.datatosend.pop(0)
			
			# try to send it
			totalsent = 0
			while totalsent < len(data):
				try:
					sent = self.sock.send(data[totalsent:])
				except socket.error:
					# non-ssl socket likes to throw this exception instead
					# of returning zero bytes sent it seems
					self.datatosend.insert(0, data[totalsent:])
					return False
				
				if sent == 0:
					# place remaining data back at front of queue and
					# we will try to send it next time
					self.datatosend.insert(0, data[totalsent:])
					return False
				#print('@sent', sent)
				totalsent = totalsent + sent
			self.bytestosend = self.bytestosend - totalsent
		return True
	
	'''
		The client can use any format of a path, but in order to support
		file stashing and any characters in the path we convert it into
		a stashing format and encode the parts. Therefore it makes it possible
		to use any character for a directory name or file name. This function
		however reserves the character `/` and `\x00` as special and neither
		are usable as an or part of a file or directory name.
		
		You can freely reimplement this method as long as the server supports
		the characters you use. The output of the base 64 encoded shall always
		be supported by the server for directory and file names.
	'''
	def GetServerPathForm(self, path):
		# 1. prevent security hole (helps reduce server CPU load if these exist)
		while path.find(b'..') > -1:
			path = path.replace(b'..', b'.')
		# remove duplicate path separators
		while path.find(b'//') > -1:
			path = path.replace(b'//', b'/')
		# 2. convert entries into stash format
		parts = path.split(b'/')
		_parts = []
		for part in parts:
			if len(part) == 0:
				continue
			# see if it is already in stash format
			if part.find(b'\x00') < 0:
				# convert into stash format
				part = b'0.' + part
			else:
				# replace it with a dot
				part = part.replace(b'\x00', b'.')
			# 3. encode it (any stash value can be used)
			part = self.FSEncodeBytes(part)
			_parts.append(part)
		path = b'/'.join(_parts)
		return path
		
	def FSEncodeBytes(self, s):
		out = []
		
		valids = (
			(ord('a'), ord('z')),
			(ord('A'), ord('Z')),
			(ord('0'), ord('9')),
		)
		
		dotord = ord('.')
		dashord = ord('-')
		uscoreord = ord('_')
		
		for c in s:
			was = False
			for valid in valids:
				if c >= valid[0] and c <= valid[1]:
					was = True
					break
			if was or c == dotord or c == dashord or c == uscoreord:
				out.append(c)
				continue
			# encode byte value as %XXX where XXX is decimal value since
			# i think it is faster to decode the decimal value than a hex
			# value even though the hex will look nicer
			out.append(ord('%'))
			v = int(c / 100)
			out.append(ord('0') + v)
			c = c - (v * 100)
			v = int(c / 10)
			out.append(ord('0') + v)
			c = c - (v * 10)
			out.append(ord('0') + c)
		
		return bytes(out)
							
	def FSDecodeBytes(self, s):
		out = []
		
		x = 0
		po = ord('%')
		while x < len(s):
			c = s[x]
			if c != po:
				out.append(c)
				x = x + 1
				continue
			zo = ord('0')
			v = (s[x + 1] - zo) * 100 + (s[x + 2] - zo) * 10 + (s[x + 3] - zo) 
			out.append(v)
			x = x + 4
		
		return bytes(out)
		
	def DirList(self, dir, mode, callback = None):
		dir = self.GetServerPathForm(dir)
		return self.WriteMessage(struct.pack('>B', ClientType.DirList) + dir, mode, callback)
	def FileRead(self, fid, offset, length, mode, callback = None):
		_fid = self.GetServerPathForm(fid)
		print('@@', _fid, fid)
		return self.WriteMessage(struct.pack('>BQQ', ClientType.FileRead, offset, length) + _fid, mode, callback)
	def FileWrite(self, fid, offset, data, mode, callback = None):
		if self.bz2compression > 0:
			data = zlib.compress(data, self.bz2compression)
		fid = self.GetServerPathForm(fid)
		return self.WriteMessage(struct.pack('>BQHB', ClientType.FileWrite, offset, len(fid), self.bz2compression) + fid + data, mode, callback)
	def FileSetTime(self, fid, atime, mtime, mode, callback = None):
		fid = self.GetServerPathForm(fid)
		return self.WriteMessage(struct.pack('>Bdd', ClientType.FileSetTime, atime, mtime) + fid, mode, callback)
	def FileSize(self, fid, mode, callback = None):
		fid = self.GetServerPathForm(fid)
		return self.WriteMessage(struct.pack('>B', ClientType.FileSize) + fid, mode, callback)
	def FileTrun(self, fid, newsize, mode, callback = None):
		fid = self.GetServerPathForm(fid)
		return self.WriteMessage(struct.pack('>BQ', ClientType.FileTrun, newsize) + fid, mode, callback)
	def Echo(self, mode, callback = None):
		return self.WriteMessage(struct.pack('>B', ClientType.Echo), mode, callback)
	def FileDel(self, fid, mode, callback = None):
		fid = self.GetServerPathForm(fid)
		return self.WriteMessage(struct.pack('>B', ClientType.FileDel) + fid, mode, callback)
	def FileCopy(self, srcfid, dstfid, mode, callback = None):
		srcfid = self.GetServerPathForm(srcfid)
		dstfid = self.GetServerPathForm(dstfid)
		return self.WriteMessage(struct.pack('>BH', ClientType.FileCopy, len(srcfid)) + srcfid + dstfid, mode, callback)
	def FileMove(self, srcfid, dstfid, mode, callback = None):
		srcfid = self.GetServerPathForm(srcfid)
		dstfid = self.GetServerPathForm(dstfid)
		return self.WriteMessage(struct.pack('>BH', ClientType.FileMove, len(srcfid)) + srcfid + dstfid, mode, callback)
	def FileHash(self, fid, offset, length, mode, callback = None):
		fid = self.GetServerPathForm(fid)
		return self.WriteMessage(struct.pack('>BQQ', ClientType.FileHash, offset, length) + fid, mode, callback)
	def FileTime(self, fid, mode, callback = None):
		fid = self.GetServerPathForm(fid)
		return self.WriteMessage(struct.pack('>B', ClientType.FileTime) + fid, mode, callback)

class Client2(Client):
	def __init__(self, rhost, rport, aid, maxthread = 128):
		Client.__init__(self, rhost, rport, aid)
		self.maxbuffer = 1024 * 1024 * 8
		self.workers = []
		self.maxthread = maxthread

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
			# i feel bad using this lock.. but trying to debug
			# some crazy numbers..
			with self.socklockwrite:
				self.bytesout = self.bytesout + lsz
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
			
		print('FilePush: %s' % lfile)
			
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
			for x in range(0, self.maxthread):
				thread = threading.Thread(target = Client2.WorkerPoolEntry, args = (self, x))
				thread.daemon = True
				thread.start()
				self.workerpool.append(thread)

		# we use this when updating the title (to kind
		# of give the status output some indication of
		# what is kind of going on
		self.__lastpushedlfile = lfile
				
		self.dbgc = self.dbgc + 1
		# add work item
		self.workpool.append((fid, lfile, False))
		
		# @TODO:THREADED IFFY
		# i think it is fairly safe to check the length
		# even *if* another thread is modifying it..
		if len(self.workpool) > self.maxthread:
			# apparently things are not getting done so
			# lets wait around and keep signalling the
			# condition in hopes a thread finally releases
			# and services the job queue
			while len(self.workpool) > self.maxthread:
				time.sleep(0.1)
				print('workpool > %s' % self.maxthread)
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
			print('workpool > 0')
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
			#print('[worker:%x] waiting' % myid)
			self.workhere.wait(1)
			#print('[worker:%x] looking' % myid)
			# there could have been more than one
			# thread release when the lock was signalled
			# or when the time out occurs.. the docs
			# state an optimized implementation of
			# the Condition object could allow more than
			# one to release on notify occasionally
			with self.workpoolguard:
				if len(self.workpool) < 1:
					#print('[worker:%x] no work' % myid)
					self.workhere.release()
					continue
				#print('[worker:%x] getting work' % myid)
				workitem = self.workpool.pop(0)
			self.workhere.release()
			# work on the job
			#print('[worker:%x] working' % myid)
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
		dt = time.time() - self.bytesoutst
		
		outdata = '%.03f' % (self.bytesout / 1024 / 1024 / dt)
		outcontrol = '%.03f' % ((self.allbytesout - self.bytesout) / 1024 / 1024 / dt)
		
		output.SetTitle('DataOutMB', outdata)
		output.SetTitle('ControlOutMB', outcontrol)
		output.SetTitle('WorkPoolCount', wpc)
		output.SetTitle('Threads', c)
		output.SetTitle('ActiveRequests', len(self.keepresult))
		output.SetTitle('RecentFile', self.lastpushedlfile)
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