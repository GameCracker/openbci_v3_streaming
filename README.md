openbci_v3_streaming
====================

Scripting to streaming data from 32-bit 8 channel OpenBCI v3 board, sending to DynamoDB on AWS, or using Socket to send to a client, or save to a local .csv or .txt file.

- The Socket client is in 'client.py'. Socket server running on 'localhost:5007' by default, change port/host in 'open_bci_v3.py' (line 351, line 352) and 'client.py' (line 8, 9). After running "python open_bci_v3.py" and connecting to board, run "python client.py" to start streaming.

- Comment out 'open_bci_v3.py' (line 338) in 'open_bci_v3.py' if you don't need Socket streaming in above step. 

- In function 'handle_sample(sample, opt=3)' in 'open_bci_v3.py' (line 446), change the 'opt' parameter to 0 - TCP socket, 1 - Dynamo DB, 2 - local .csv file, 4 - local text file.

- Modify csv and txt file saved directory on local computer in 'open_bci_v3.py' (line 344, 345). 

Data format to .txt, .csv: 

'timestamp', 'id', 'subject', 'channel0_value', 'channel1_value', 'channel2_value', 'channel3_value', 'channel4_value', 'channel5_value', 'channel6_value', 'channel7_value'

Data format to socket(json) and Dynamo DB:

{'id': sample.id, 
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
 'channel7_value': channel7_value}
 

