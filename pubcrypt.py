import math
import base64
import struct

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
	
	fields = []
	
	data = data[4:]
	ndx = 0
	
	while len(data) > 0:
		type = data[0]
		data = data[1:]
		
		sz = data[0]
		data = data[1:]
		
		if sz == 0x82:
			sz = data[0] << 8 | data[1]
			data = data[2:]
		
		# create field
		field = (type, data[0:sz])
		# drop used data
		data = data[sz:]
		
		# add field
		fields.append(field) 
		fields[ndx] = field
		ndx = ndx + 1
		
	return (fields[3][1], fields[1][1])
	
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