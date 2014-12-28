"""

EXAMPLE USE:

def handle_sample(sample):
  print(sample.channels)

board = OpenBCIBoard()
board.print_register_settings()
board.start(handle_sample)


"""
import serial
import struct
import numpy as np
import sys
import socket
import time
import argparse
import inspect
import json
import csv
import os
import boto.dynamodb
from os.path import dirname, abspath


SAMPLE_RATE = 250.0  # Hz
START_BYTE = bytes(0xA0)  # start of data packet
END_BYTE = bytes(0xC0)  # end of data packet
ADS1299_Vref = 4.5;  #reference voltage for ADC in ADS1299.  set by its hardware
ADS1299_gain = 24.0;  #assumed gain setting for ADS1299.  set by its Arduino code
scale_fac_uVolts_per_count = ADS1299_Vref/(pow(2,23)-1)/(ADS1299_gain*1000000.);

# command_stop = "s";
# command_startText = "x";
# command_startBinary = "b";
# command_startBinary_wAux = "n";
# command_startBinary_4chan = "v";
# command_activateFilters = "F";
# command_deactivateFilters = "g";
# command_deactivate_channel = {"1", "2", "3", "4", "5", "6", "7", "8"};
# command_activate_channel = {"q", "w", "e", "r", "t", "y", "u", "i"};
# command_activate_leadoffP_channel = {"!", "@", "#", "$", "%", "^", "&", "*"};  //shift + 1-8
# command_deactivate_leadoffP_channel = {"Q", "W", "E", "R", "T", "Y", "U", "I"};   //letters (plus shift) right below 1-8
# command_activate_leadoffN_channel = {"A", "S", "D", "F", "G", "H", "J", "K"}; //letters (plus shift) below the letters below 1-8
# command_deactivate_leadoffN_channel = {"Z", "X", "C", "V", "B", "N", "M", "<"};   //letters (plus shift) below the letters below the letters below 1-8
# command_biasAuto = "`";
# command_biasFixed = "~";

        
class OpenBCIBoard(object):
  """

  Handle a connection to an OpenBCI board.

  Args:
    port: The port to connect to.
    baud: The baud of the serial connection.

  """

  def __init__(self, port=None, baud=115200, filter_data=True):
    if not port:
      port = self.find_port()
      if not port:
        raise OSError('Cannot find OpenBCI port')
        
    self.ser = serial.Serial(port, baud)
    print self.ser
    print("Serial established...")

    #Initialize 32-bit board, doesn't affect 8bit board
    self.ser.write('v');

    #wait for device to be ready 
    time.sleep(1)
    self.print_incoming_text()

    self.streaming = False
    self.filtering_data = filter_data
    self.channels = 8
    self.read_state = 0; 

  def find_port(self):
    import platform, glob

    s = platform.system()
    print "platform.system(): %s\n" % s
    p = glob.glob('/dev/tty.usbserial-DN*')
    print p
    if len(p) >= 1:
      return p[0]
    else:
      return None

  def printBytesIn(self):
    #DEBBUGING: Prints individual incoming bytes 
    if not self.streaming:
      self.ser.write('b')
      self.streaming = True
    while self.streaming:
      print(struct.unpack('B',self.ser.read())[0]);

  def start(self, callback):
    """

    Start handling streaming data from the board. Call a provided callback
    for every single sample that is processed.

    Args:
      callback: A callback function that will receive a single argument of the
          OpenBCISample object captured.
    
    """
    if not self.streaming:
      # print "line %s" % lineno()
      self.ser.write('b')
      self.streaming = True
    # print "line %s" % lineno()
    while self.streaming:
      # print "line %s" % lineno()
      sample = self._read_serial_binary()
      callback(sample)

  """

  Turn streaming off without disconnecting from the board

  """
  def stop(self):
    self.streaming = False

  def disconnect(self):
    self.ser.close()
    self.streaming = False

  """ 

      SETTINGS AND HELPERS 

  """

  def print_incoming_text(self):
    """
    
    When starting the connection, print all the debug data until 
    we get to a line with the end sequence '$$$'.
    
    """
    line = ''
    #Wait for device to send data
    time.sleep(0.5)
    print "line %s" % lineno()
    if self.ser.inWaiting():
      print("-------------------")
      line = ''
      c = ''
     #Look for end sequence $$$
      while '$$$' not in line:
        c = self.ser.read()
        line += c   
      print(line);
      print("-------------------\n")
    else:
      print "line %s" % lineno()

  def print_register_settings(self):
    self.ser.write('?')
    time.sleep(0.5)
    self.print_incoming_text();

  """

  Adds a filter at 60hz to cancel out ambient electrical noise.
  
  """
  def enable_filters(self):
    self.ser.write('f')
    self.filtering_data = True;

  def disable_filters(self):
    self.ser.write('g')
    self.filtering_data = False;

  def warn(self, text):
    print("Warning: ", text)

  """

    Parses incoming data packet into OpenBCISample.
    Incoming Packet Structure:
    Start Byte(1)|Sample ID(1)|Channel Data(24)|Aux Data(6)|End Byte(1)
    0xA0|0-255|8, 3-byte signed ints|3 2-byte signed ints|0xC0

  """
  def _read_serial_binary(self, max_bytes_to_skip=3000):
    def read(n):
      b = self.ser.read(n)
      # print bytes(b)
      return b

    for rep in xrange(max_bytes_to_skip):

      #Looking for start and save id when found
      if self.read_state == 0:
        b = read(1)
        if not b:
          if not self.ser.inWaiting():
              self.warn('Device appears to be stalled. Restarting...')
              self.ser.write('b\n')  # restart if it's stopped...
              time.sleep(.100)
              continue
        if bytes(struct.unpack('B', b)[0]) == START_BYTE:
          if(rep != 0):
            self.warn('Skipped %d bytes before start found' %(rep))
          packet_id = struct.unpack('B', read(1))[0] #packet id goes from 0-255
          
          self.read_state = 1

      elif self.read_state == 1:
        channel_data = []
        for c in xrange(self.channels):

          #3 byte ints
          literal_read = read(3)

          unpacked = struct.unpack('3B', literal_read)

          #3byte int in 2s compliment
          if (unpacked[0] >= 127): 
            pre_fix = '\xFF'
          else:
            pre_fix = '\x00'
          

          literal_read = pre_fix + literal_read; 

          #unpack little endian(>) signed integer(i)
          #also makes unpacking platform independent
          myInt = struct.unpack('>i', literal_read)

          channel_data.append(myInt[0]*scale_fac_uVolts_per_count)
        
        self.read_state = 2;


      elif self.read_state == 2:
        aux_data = []
        for a in xrange(3):

          #short(h) 
          acc = struct.unpack('h', read(2))[0]
          aux_data.append(acc)
    
        self.read_state = 3;


      elif self.read_state == 3:
        val = bytes(struct.unpack('B', read(1))[0])
        if (val == END_BYTE):
          sample = OpenBCISample(packet_id, channel_data, aux_data)
          self.read_state = 0 #read next packet
          return sample
        else:
          self.warn("Warning: Unexpected END_BYTE found <%s> instead of <%s>,\
            discarted packet with id <%d>" 
            %(val, END_BYTE, packet_id))
  

  def _interprate_stream(self, b):
    print ("interprate")

  def set_channel(self, channel, toggle_position):
    #Commands to set toggle to on position
    if toggle_position == 1: 
      if channel is 1:
        self.ser.write('q')
      if channel is 2:
        self.ser.write('w')
      if channel is 3:
        self.ser.write('e')
      if channel is 4:
        self.ser.write('r')
      if channel is 5:
        self.ser.write('t')
      if channel is 6:
        self.ser.write('y')
      if channel is 7:
        self.ser.write('u')
      if channel is 8:
        self.ser.write('i')
    #Commands to set toggle to off position
    elif toggle_position == 0: 
      if channel is 1:
        self.ser.write('1')
      if channel is 2:
        self.ser.write('2')
      if channel is 3:
        self.ser.write('3')
      if channel is 4:
        self.ser.write('4')
      if channel is 5:
        self.ser.write('5')
      if channel is 6:
        self.ser.write('6')
      if channel is 7:
        self.ser.write('7')
      if channel is 8:
        self.ser.write('8')

class OpenBCISample(object):
  """Object encapulsating a single sample from the OpenBCI board."""
  def __init__(self, packet_id, channel_data, aux_data):
    self.id = packet_id;
    self.channel_data = channel_data;
    self.aux_data = aux_data;

def lineno():
  return inspect.currentframe().f_back.f_lineno

class DataHandler(object):
  # ip, port, receiver, receiver_port, json, user
  def __init__(self):
    # self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # self.ip = ''
    # self.receiver = ''
    # self.receiver_port = ''
    # self.port = ''
    # self.json = ''
    # self.server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # self.user = ''
    self.put_count = 0
    self.count = 0
    self.data_pack = []
    self.ch_data = []
    self.sock_server()
    self.table_name = "Testing"
    self.subject = 'testing'
    self.dynamo_conn = boto.dynamodb.connect_to_region('us-west-2',
                                                        aws_access_key_id='',
                                                        aws_secret_access_key='')
    self.obci_csv_dir = '/Users/ziqipeng/Dropbox/bci/x/data/openbci/csv/'
    self.obci_txt_dir = '/Users/ziqipeng/Dropbox/bci/x/data/openbci/txt/'
    self.csv_fname = ''
    self.txt_fname = ''

  # streaming data using socket, client is in client.py 
  def sock_server(self):
    self.host = ''
    self.port = 5007
    s = None
    for res in socket.getaddrinfo(self.host, self.port, socket.AF_UNSPEC, socket.SOCK_STREAM, 0, socket.AI_PASSIVE):
      af, socketype, proto, canonname, sa = res
      try:
        s = socket.socket(af, socketype, proto)
      except socket.error, msg:
        s = None
        continue
      try:
        s.bind(sa)
        s.listen(1)
      except socket.error, msg:
        s.close()
        s = None
        continue
      break
    if s is None:
      print 'could not open socket'
      sys.exit(1)
    self.conn, addr = s.accept()
    print 'Connected by', addr
    # while 1:
    #   conn.send("hello from server")

  # save to local csv
  def csv_handler(self, col, val):
    if self.csv_fname == '' or self.csv_fname == None:
      tstamp = val[0]
      subj = val[2]
      self.csv_fname = subj + '_' + str(tstamp) + '.csv'
      self.csv_path = self.obci_csv_dir + self.csv_fname
      self.obci_csv = open(self.csv_path, 'wb')
      self.obci_csv_writer = csv.writer(self.obci_csv)
      values = col
    else:
      values = val
      # open(self.csv_path, 'w').close()
    # with open(self.csv_path, 'a') as f:
    print type(values)
    print "-----------------values: ", values
    self.obci_csv_writer.writerow(values)
      # to do

  # save to local txt file
  def file_handler(self, col, val):
    if self.txt_fname == '' or self.txt_fname == None:
      tstamp = val[0]
      subj = val[2]
      self.txt_fname = subj + '_' + str(tstamp) + '.txt'
      self.txt_path = self.obci_txt_dir + self.txt_fname
      self.obci_txt = open(self.txt_path, 'a')
      values = col
    else:
      values = val
    print "line %d\n" % lineno()
    self.obci_txt.writelines("%s," % value for value in values)

  # streaming data to dynamo db
  def dynamo_handler(self, packet):
    # try:
    #   self.dynamo_conn
    # except NameError:
    #   self.dynamo_conn = boto.dynamodb.connect_to_region('us-west-2',
    #           aws_access_key_id='',
    #           aws_secret_access_key='')
    # else:
    #   pass
    table_name = "OpenBCI" + self.table_name
    tables = self.dynamo_conn.list_tables()
    if table_name not in tables:
      from boto.dynamodb.schema import Schema
      openbci_table_schema = self.dynamo_conn.create_schema(hash_key_name='timestamp', 
                                                hash_key_proto_value=int, 
                                                range_key_name='subject', 
                                                range_key_proto_value=str)
      table = self.dynamo_conn.create_table(name=table_name,
                                            schema=openbci_table_schema,
                                            read_units=350,
                                            write_units=350)
    table = self.dynamo_conn.get_table(table_name)
    tstamp = packet['timestamp']
    subj = packet['subject']
    del packet['timestamp']
    del packet['subject']
    # print "pack_dic.keys: ", pack_dic.keys()
    item = table.new_item(hash_key=int(tstamp), 
                          range_key=subj, 
                          attrs=packet)
    item.put()
    self.put_count += 1
    print '--------------------put_count: %d' % self.put_count

  # opt = 0 send using TCP socket, opt = 1 send to Dynamo db, opt = 2 save to local excel, opt = 4 save to local text file
  def handle_sample(self, sample, opt=3):
    if self.count == int(SAMPLE_RATE):
      # print "send!!!"
      # print np.shape(self.data_pack)
      # packet = json.dumps(self.data_pack)
      # print packet
      # self.conn.send()
      # self.sock.sendto(packet, (self,receiver, self.receiver_port))
      self.data_pack = []
      self.count = 0
    timestamp = time.time()
    # print type(timestamp)
    timestamp = int(timestamp*1000)
    # print "timestamp.type %d:" % timestamp
    # print type(timestamp)
    # print "sample.id: " + str(sample.id)
    # print type(sample.id)
    # print "sample.channel_data: " + str(sample.channel_data)
    # print type(sample.channel_data)
    channel0_value = sample.channel_data[0]
    channel1_value = sample.channel_data[1]
    channel2_value = sample.channel_data[2]
    channel3_value = sample.channel_data[3]
    channel4_value = sample.channel_data[4]
    channel5_value = sample.channel_data[5]
    channel6_value = sample.channel_data[6]
    channel7_value = sample.channel_data[7]
    self.ch_data = sample.channel_data
    self.ch_data.append(timestamp)
    self.data_pack.append(self.ch_data)
    # print "sample.aux_data: " + str(sample.aux_data)
    self.count += 1
    all_channels = ', '.join(map(str, sample.channel_data))
    pack_dic = {'id': sample.id, 
                'subject': self.subject, 
                'timestamp': timestamp, 
                'channel_values': all_channels, 
                'channel0_value': channel0_value,
                'channel1_value': channel1_value,
                'channel2_value': channel2_value,
                'channel3_value': channel3_value,
                'channel4_value': channel4_value,
                'channel5_value': channel5_value,
                'channel6_value': channel6_value,
                'channel7_value': channel7_value}
    packet = json.dumps({'id': sample.id, 
                          'subject': self.subject, 
                          'timestamp': timestamp, 
                          'channel_values': sample.channel_data, 
                          'channel0_value': channel0_value,
                          'channel1_value': channel1_value,
                          'channel2_value': channel2_value,
                          'channel3_value': channel3_value,
                          'channel4_value': channel4_value,
                          'channel5_value': channel5_value,
                          'channel6_value': channel6_value,
                          'channel7_value': channel7_value})
    # print 'pack_dic.keys(): ', pack_dic.keys()
    # print 'pack_dic.values(): ', pack_dic.values()
    if opt in [2, 3]:
      val_seq = []
      val_col = ['timestamp', 'id', 'subject', 'channel0_value', 'channel1_value', 'channel2_value', 'channel3_value', 'channel4_value', 'channel5_value', 'channel6_value', 'channel7_value']
      for i in xrange(11):
        val_seq.append(pack_dic[val_col[i]])
    # print 'opt: %d' % opt
    # print '==================val_seq: ', val_seq
    if opt == 0:
      self.conn.send(packet)
    elif opt == 1:
      self.dynamo_handler(pack_dic)
    elif opt == 2:
      self.csv_handler(val_col, val_seq)
    elif opt == 3:
      self.file_handler(val_col, val_seq)

if __name__ == "__main__":
  obci = OpenBCIBoard()
  obci.print_register_settings()
  dh = DataHandler()
  obci.start(dh.handle_sample)

