import math
import base64
import struct
import pprint

'''
	This function expects bytes not str.
'''
def toi256(data):
	t = 0
	n = 1
	for b in data:
		b = b
		t = t + (b * n)
		n = n * 256
	return t
	
def toi256r(data):
	t = 0
	n = 1
	i = len(data) - 1
	while i > -1:
		b = data[i]
		t = t + (b * n)
		n = n * 256
		i = i - 1
	return t

def fromi256(i):
	o = []
	m = 1
	while m < i:
		m = m * 256
	if m > i:
		m = divmod(m, 256)[0]
	while i > 0:
		r = divmod(i, m)[0]
		o.insert(0, r)
		i = i - (r * m)
		m = m >> 8
	return bytes(o)
	
def crypt(data, key):
	exp = toi256(key[0])
	pubkey = toi256(key[1])
	
	data = toi256(data)
	
	# value, exponent, modulus
	
	data = pow(data, exp, pubkey)
	return fromi256(data)
	
def decrypt(data, key):
	prikey = toi256(key[0])
	pubkey = toi256(key[1])
	
	data = toi256(data)
	data = pow(data, prikey, pubkey)
	return fromi256(data)

'''
	The cert file contains the certificate and the private key. We only
	want to read our the private key lines in BASE64 and return them.
'''
def readKeyFromCertFile(path):
	fd = open(path, 'r')
	lines = fd.readlines()
	fd.close()
	
	code = []
	inside = False
	
	for line in lines:
		line = line.strip()
		if line.find('--BEGIN PRIVATE KEY--') > -1:
			inside = True
			continue
		if line.find('--END PRIVATE KEY--') > -1:
			code = ''.join(code)
			return base64.b64decode(bytes(code, 'utf8'))
		if inside:
			code.append(line)
			
	# get someone's attention.. do not just return None
	raise Exception('The provided key file [%s] had not private key.' % path)
	
def readPrivateKeyFromCertFile(path):
	data = readKeyFromCertFile(path)
	fields = readASN1Data(data)
	
	data = fields[2][1]
	
	fields = readASN1Data(data)
	
	# [2] modulus
	
	#for field in fields:
		#print('type:%s data-len:%s' % (field[0], len(field[1]) * 8))
		#print('data:%s' % base64.b64encode(field[1])[0:10])
	
	pubk = fields[1][1]
	exp = fields[2][1]
	prik = fields[3][1]

	pubk = fromi256(toi256r(pubk))
	prik = fromi256(toi256r(prik))
	exp = fromi256(toi256r(exp))	
	
	pubkey = (exp, pubk)
	prikey = (prik, pubk)
	
	#msg = b'hello world'
	#coded = crypt(msg, pubkey)
	#plain = decrypt(coded, prikey)
	#if msg == plain:
	#	#print(msg)
	#	#print(plain)
	#	print('@@@@@@ FOUND IT')
	#	print()
	#exit()
	return (pubkey, prikey)
	
def readKeyFile(path):
	fd = open(path, 'r')
	lines = fd.readlines()
	fd.close()
	
	out = []
	for line in lines:
		line = line.strip()
		if line.find(':') < 0 and line.find('-') < 0:
			out.append(line)
	
	out = ''.join(out)
	
	return base64.b64decode(bytes(out, 'utf8'))

def readSSHPublicKey(path):
	# do not ask me.. had lots of trouble digging through openssh
	# source.. building it.. producing different results... LOL..
	# i just gave up and hacked this together
	fd = open(path, 'rb')
	data = fd.read()
	fd.close()
	data = data.split(b' ')
	data = data[1]
	
	data = base64.b64decode(data)
	
	sz = struct.unpack_from('>I', data)[0]
	data = data[4:]
	type = data[0:sz]
	data = data[sz:]
	
	sz = struct.unpack_from('>I', data)[0]
	data = data[4:]
	exp = data[0:sz]
	data = data[sz:]
	
	sz = struct.unpack_from('>I', data)[0]
	data = data[4:]
	mod = data[0:sz]
	
	return (exp, mod)
	
def readSSHPrivateKey(path):
	data = readKeyFile(path)
	return __readSSHPrivateKey(data)
	
def __readSSHPrivateKey(data):
	fields = readASN1Data(data)
	return (fields[3][1], fields[1][1])
	
def readASN1Data(data):
	fields = []
	
	data = data[4:]
	ndx = 0
	
	while len(data) > 0:
		type = data[0]
		data = data[1:]
		
		#print('type:%s' % type)
		
		if type & 0x40 == 0x40:
			raise Exception('ASN.1 Entry Used Indefinite Length')
		
		# read the first length
		sz = data[0]
		data = data[1:]
		
		#print('sz:%s' % sz)
		
		# if bit 7 is set then we use more bytes for the length
		if sz & 0x80 == 0x80:
			# get the length of the length field
			c = sz & 0x7F
			# make sure we are not in over our head and
			# if so then let someone know that we are
			if c != 2:
				raise Exception('ASN.1 Entry Used Length File Not 2 Bytes')
			# read the length of the data
			sz = data[0] << 8 | data[1]
			#print('   2sz:%s' % sz)
			# remove the length
			data = data[2:]
		
		# create field
		field = (type, data[0:sz])
		# drop used data
		data = data[sz:]
		
		# add field
		fields.append(field) 
		fields[ndx] = field
		ndx = ndx + 1
	
	return fields
	
'''
msg = 'hello'

pubkey, prikey = keygen(2**64)
print('pubkey:%s' % pubkey)
print('prikey:%s' % prikey)

coded = crypt(msg, pubkey)
plain = decrypt(coded, prikey, pubkey)
print(msg)
print(plain)
assert(msg == plain)
exit()
'''