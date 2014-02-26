#!/usr/bin/env python
from serial import *
import binascii
import struct
import pyttsx
import datetime
import random

#constants
COM_PORT = 'COM40'
STX = 0x02
ETX = 0x03
MSG_ID_HXM = 0x26
MIN_DLC = 0x37

#options
AUDIO_FEEDBACK_ON = True
AUDIO_FEEDBACK_INTERVAL = datetime.timedelta(seconds=5)
TARGET_HR_ENABLE = True
TARGET_HR_BPM = 120

#dev flags:
SPOOF_RX = False
EXIT_AFTER_ONE_PACKET = False

class HxMPacket:
    def __init__(self, dlc, payload, crc):
        assert len(payload) == dlc and dlc >= MIN_DLC
        self.dlc = dlc
        self.payload = payload
        self.crc = crc
        
        #read payload
        offset = 0
        
        #Firmware ID
        fmt = '<H'
        self.fw_id = struct.unpack_from(fmt, payload, offset)[0]
        offset += struct.calcsize(fmt)
        print 'fw_id:', self.fw_id
        
        #Firmware Version
        fmt = 'cc'
        self.fw_ver = ''.join(struct.unpack_from(fmt, payload, offset))
        offset += struct.calcsize(fmt)
        print 'fw_ver:', self.fw_ver
        
        #Hardware ID
        fmt = '<H'
        self.hw_id = struct.unpack_from(fmt, payload, offset)[0]
        offset += struct.calcsize(fmt)
        print 'hw_id:', self.hw_id
        
        #Hardware Version
        fmt = 'cc'
        self.hw_ver = ''.join(struct.unpack_from(fmt, payload, offset))
        offset += struct.calcsize(fmt)
        print 'hw_ver:', self.hw_ver
        
        #Battery Charge Indicator
        fmt = 'B'
        self.battery = struct.unpack_from(fmt, payload, offset)[0]
        offset += struct.calcsize(fmt)
        print 'battery: {0}%'.format(self.battery)
        
        #Heart Rate
        fmt = 'B'
        self.heart_rate = struct.unpack_from(fmt, payload, offset)[0]
        offset += struct.calcsize(fmt)
        print 'heart_rate: {0} bpm'.format(self.heart_rate)
        
        #Heart Beat Number
        fmt = 'B'
        self.heart_beat_num = struct.unpack_from(fmt, payload, offset)[0]
        offset += struct.calcsize(fmt)
        print 'heart_beat_num:', self.heart_beat_num
        
        #Heart Beat Timestamp (1 to 15)
        self.heart_beat_timestamps = []
        for i in range(1, 16):
            fmt = '<H'
            ts = struct.unpack_from(fmt, payload, offset)[0]
            offset += struct.calcsize(fmt)
            print 'heart_beat_ts_{0}: {1} ms'.format(i, ts)
            self.heart_beat_timestamps.append(ts)
            
        #Reserved
        offset += 6
        
        #Distance
        fmt = '<H'
        self.distance = struct.unpack_from(fmt, payload, offset)[0] / 16.0
        offset += struct.calcsize(fmt)
        print 'distance: {0} m'.format(self.distance)
        
        #Instantaneous speed
        fmt = '<H'
        self.inst_speed = struct.unpack_from(fmt, payload, offset)[0] / 256.0
        offset += struct.calcsize(fmt)
        print 'inst_speed: {0} m/s'.format(self.inst_speed)
        
        #Strides
        fmt = 'B'
        self.strides = struct.unpack_from(fmt, payload, offset)[0]
        offset += struct.calcsize(fmt)
        print 'strides:', self.strides
        
        #Reserved
        offset += 3
        
        assert offset == MIN_DLC

class HxMListener:
    def __init__(self):
        self.engine = None
        self.positive_feedback = []
        self.negative_feedback = []
        self._load_feedback_strings()
        if AUDIO_FEEDBACK_ON:
            self.engine = pyttsx.init()
            self.last_feedback_ts = datetime.datetime.now() - AUDIO_FEEDBACK_INTERVAL
    
    def _load_feedback_strings(self):
        with open('positive_feedback.txt', 'r') as file:
            lines = file.readlines()
            lines = [line.strip() for line in lines]
            lines = [line for line in lines if line != '']
            self.positive_feedback += lines
        print 'positive feedback:'
        for feedback in self.positive_feedback:
            print feedback
        with open('negative_feedback.txt', 'r') as file:
            lines = file.readlines()
            lines = [line.strip() for line in lines]
            lines = [line for line in lines if line != '']
            self.negative_feedback += lines
        print 'negative feedback:'
        for feedback in self.negative_feedback:
            print feedback
            
    def audio_feedback(self, pkt):
        self.engine.say('heart rate {0}'.format(pkt.heart_rate))
        if TARGET_HR_ENABLE:
            if pkt.heart_rate < TARGET_HR_BPM:
                feedback = random.choice(self.negative_feedback)
                self.engine.say(feedback)
            else:
                feedback = random.choice(self.positive_feedback)
                self.engine.say(feedback)
        self.engine.runAndWait()
    
    def hxm_pkt_ready(self, pkt):
        print 'heart_rate: ', pkt.heart_rate
        if AUDIO_FEEDBACK_ON:
            now = datetime.datetime.now()
            if now - self.last_feedback_ts >= AUDIO_FEEDBACK_INTERVAL:
                self.audio_feedback(pkt)
                self.last_feedback_ts = now
        
    def rx_hxm_pkt(self, ser):
        """Receives everything between STX and ETX"""
        pkt = ''
        print 'rx_hxm_pkt'
        #(assumes Byte 0 - STX has already been received)
                
        #Byte 1 - Msg Id
        c = ser.read()
        if ord(c) != MSG_ID_HXM:
            print 'Error: Expected MSG_ID_HXM, received', hex(ord(c))
            return False
        else:
            print 'Rx Msg ID HxM'
        
        #Byte 2 - DLC
        c = ser.read()
        dlc = ord(c)
        if dlc < MIN_DLC:
            print 'Error: DLC is shorter than expected', dlc
            return False
        else:
            print 'DLC:', hex(ord(c))
        
        #Rx payload - bytes 3-57+
        payload = ''
        for i in range(dlc):
            c = ser.read()
            payload += c    
        print 'payload:', binascii.hexlify(payload)
        
        #Byte 58 OR len(PAYLOAD)+1 - CRC 
        c = ser.read()
        crc = ord(c)
        print 'CRC:', hex(crc)
                
        return (dlc, payload, crc)
        
    def listen(self):
        if SPOOF_RX:
            #use a dummy packet
            result = (0x37, binascii.unhexlify(\
            '1a00316650003164643d5d51ee7dea' \
            '6de67de2c1de41dbc9d705d425d049' \
            'cc75c86dc451c031bc1db800000000' \
            '0000e30400003f000000'), 0x1f)
            dlc, payload, crc = result
            pkt = HxMPacket(dlc, payload, crc)
            print repr(pkt)
        else:
            #read a packet off the wire
            with Serial(
                port=COM_PORT, 
                baudrate=9600, 
                bytesize=EIGHTBITS, 
                parity=PARITY_NONE, 
                stopbits=STOPBITS_ONE, 
                timeout=None, 
                xonxoff=False, 
                rtscts=False, 
                writeTimeout=None, 
                dsrdtr=False, 
                interCharTimeout=None
            ) as ser:
                print 'Serial Open:', ser.isOpen()
                while True:
                    #read until STX
                    c = ser.read()
                    while ord(c) != STX:
                        c = ser.read()
                    assert ord(c) == STX
                    print 'Rx STX'
                    
                    result = self.rx_hxm_pkt(ser)
                    if result:
                        dlc, payload, crc = result
                        pkt = HxMPacket(dlc, payload, crc)
                        self.hxm_pkt_ready(pkt)
                        
                    #read until ETX
                    c = ser.read()
                    while ord(c) != ETX:
                        c = ser.read()
                    assert ord(c) == ETX
                    print 'Rx ETX'
                    if EXIT_AFTER_ONE_PACKET:
                        break
    
if __name__ == '__main__':
    listener = HxMListener()
    listener.listen()

    
