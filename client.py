# Echo client program
import socket
import sys
import json
import numpy as np


HOST = 'localhost'    # The remote host
PORT = 5007              # The same port as used by the server
s = None
for res in socket.getaddrinfo(HOST, PORT, socket.AF_UNSPEC, socket.SOCK_STREAM):
    af, socktype, proto, canonname, sa = res
    try:
	   s = socket.socket(af, socktype, proto)
    except socket.error, msg:
	   s = None
	   continue
    try:
	   s.connect(sa)
    except socket.error, msg:
	   s.close()
	   s = None
	   continue
    break
if s is None:
    print 'could not open socket'
    sys.exit(1)
# s.send('Hello, world')
win = []
while 1:
    data = s.recv(1024)
    print type(data)
    # print data
    print data
    data_dic = json.loads(data)
    # if data_dic['id'] == 0:
    #     win = [data_dic]
    # elif data_dic['id'] == 255:
    #     print np.shape(win)
    # else:
    #     win.append(data_dic)
    # print 'Received', repr(data)
s.close()
