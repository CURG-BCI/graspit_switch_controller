#!/usr/bin/python

# open a microphone in pyAudio and listen for taps
#Obtained most source from http://stackoverflow.com/questions/4160175/detect-tap-with-pyaudio-from-live-mic
from __future__ import print_function

import pyaudio
import struct
import math
import time
import sys
import socket

#http://stackoverflow.com/questions/287871/print-in-terminal-with-colors-using-python
class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class TapDetector(object):
    TAP_THRESHOLD = 0.6
    FORMAT = pyaudio.paInt16 
    SHORT_NORMALIZE = (1.0/32768.0)
    RATE = 8000  
    INPUT_BLOCK_TIME = 0.05
    INPUT_FRAMES_PER_BLOCK = int(RATE*INPUT_BLOCK_TIME)             
    CHANNELS = 2
    MAX_TAP_BLOCKS = 0.15/INPUT_BLOCK_TIME

    def __init__(self, communicator):
        self.pa = pyaudio.PyAudio()
        self.stream = self.open_mic_stream()
        self.errorcount = 0
        self.communicator = communicator
        self.hasCooledDown = True

    def stop(self):
        self.stream.close()

    def tapDetected(self, amplitude):
        if self.hasCooledDown:
            self.communicator.tapDetected(amplitude)
        self.hasCooledDown = False
        
    def noTapDetected(self, amplitude):
        self.hasCooledDown = True
        self.communicator.noTapDetected(amplitude)

    def open_mic_stream( self ):
        stream = self.pa.open(   format = self.FORMAT,
                                 channels = self.CHANNELS,
                                 rate = self.RATE,
                                 input = True,
                                 frames_per_buffer = self.INPUT_FRAMES_PER_BLOCK)

        return stream

    def listen(self):
        try:
            block = self.stream.read(self.INPUT_FRAMES_PER_BLOCK)
        except IOError, e:
            self.errorcount += 1
            print( "(%d) Error recording: %s" % (self.errorcount,e) )
            return

        amplitude = self.get_rms( block )
        if amplitude > self.TAP_THRESHOLD:
            self.tapDetected(amplitude)
        else:
            self.noTapDetected(amplitude)

        return block

    def get_rms( self, block ):
        # RMS amplitude is defined as the square root of the 
        # mean over time of the square of the amplitude.
        # so we need to convert this string of bytes into 
        # a string of 16-bit samples...

        # we will get one short out for each 
        # two chars in the string.
        count = len(block)/2
        format = "%dh"%(count)
        shorts = struct.unpack( format, block )

        # iterate over the block.
        sum_squares = 0.0
        for sample in shorts:
            # sample is a signed short in +/- 32768. 
            # normalize it to 1.0
            n = sample * self.SHORT_NORMALIZE
            sum_squares += n * n

        return math.sqrt( sum_squares / count )
        # return sum_squares/count

class Communicator(object):
    WAIT_THRESHOLD = 0.1
    NEXT_THRESHOLD = 1
    SELECT_THRESHOLD = 3

    NEXT_MSG = "2\n"
    SELECT_MSG = "3\n"

    def __init__(self, ui):
        self.last_tap = time.time() - 100
        self.current_time = time.time()

        self.client_socket = self.init_client_socket()

        self.ui = ui

    def init_client_socket(self, ip='localhost', port=4775):
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client_socket.connect((ip, port))
        return self.client_socket

    def tapDetected(self, amplitude):
        current_tap = time.time()
        time_since_last_tap = current_tap - self.last_tap
        if 0 <= time_since_last_tap <= self.WAIT_THRESHOLD:
            self.initialTap()
        elif self.WAIT_THRESHOLD < time_since_last_tap <= self.NEXT_THRESHOLD:
            self.submitNext()
        elif self.NEXT_THRESHOLD < time_since_last_tap <= self.SELECT_THRESHOLD:
            self.submitSelect()
        else: #Took too long on tap
            self.initialTap()

    def noTapDetected(self, amplitude):
        current_tap = time.time()
        time_since_last_tap = current_tap - self.last_tap
        if 0 <= time_since_last_tap <= self.WAIT_THRESHOLD:
            self.ui.bufferPeriod(amplitude, time_since_last_tap)
        elif self.WAIT_THRESHOLD < time_since_last_tap <= self.NEXT_THRESHOLD:
            self.ui.registeringNext(amplitude, time_since_last_tap)
        elif self.NEXT_THRESHOLD < time_since_last_tap <= self.SELECT_THRESHOLD:
            self.ui.registeringSelect(amplitude, time_since_last_tap)
        else: #Waiting for tap
            self.ui.waitingForInput(amplitude, time_since_last_tap)

    def submitNext(self):
        self.ui.submittingNext()
        self.resetLastTap()
        self.client_socket.send(self.NEXT_MSG)

    def submitSelect(self):
        self.ui.submittingSelect()
        self.resetLastTap()
        self.client_socket.send(self.SELECT_MSG)

    def initialTap(self):
        self.ui.initialTap()
        self.updateLastTap()

    def updateLastTap(self):
        self.last_tap = time.time()

    def resetLastTap(self):
        self.last_tap = time.time() - self.SELECT_THRESHOLD


class UserInterface(object):
    def __init__(self):
        self.size_str = 0

    def info(self):
        print("This program controls Graspit! using an assistive controller with a 3.5mm jack input")
        print(bcolors.OKBLUE + "Blue color designates that the output is going to send a NEXT signal" + bcolors.ENDC)
        print(bcolors.WARNING + "Yellow color designates that the output is going to send a SELECT signal" + bcolors.ENDC)
        print(bcolors.HEADER + "Purple color designates that the output is waiting for user input" + bcolors.ENDC)
        print(bcolors.OKGREEN + "Green color designates that a signal was sent" + bcolors.ENDC)
        print("Hold the switch for %0.2f to %0.2f second(s) if you want to send a NEXT signal" % (Communicator.WAIT_THRESHOLD, Communicator.NEXT_THRESHOLD))
        print("Hold the switch for %0.2f to %0.2f second(s) if you want to send a SELECT signal" % (Communicator.NEXT_THRESHOLD, Communicator.SELECT_THRESHOLD))
        print()

    def registeringNext(self, amplitude, time):
        self.print_output((bcolors.OKBLUE + "Registering next (%fs passed, %f amplitude)" + bcolors.ENDC) % (time, amplitude))

    def registeringSelect(self, amplitude, time):
        self.print_output((bcolors.WARNING + "Registering select (%fs passed, %f amplitude)" + bcolors.ENDC) % (time, amplitude))

    def waitingForInput(self, amplitude, time):
        self.print_output((bcolors.HEADER + "Waiting for input (%fs passed, %f amplitude)" + bcolors.ENDC) % (time, amplitude))

    def bufferPeriod(self, amplitude, time):
        self.print_output("Buffering input (%fs passed, %f amplitude)" % (time, amplitude))

    def print_output(self, msg):
        output = "%s%s" % (msg, " " * (self.size_str - len(msg)))
        self.size_str = len(output)
        print(output, end='\r')
        sys.stdout.flush()

    def submittingNext(self):
        print(bcolors.OKGREEN + "\nSubmitting next" + bcolors.ENDC)
        self.size_str = 0

    def submittingSelect(self):
        print(bcolors.OKGREEN + "\nSubmitting select" + bcolors.ENDC)
        self.size_str = 0

    def initialTap(self):
        print(bcolors.OKGREEN + "\nInitial tap" + bcolors.ENDC)
        self.size_str = 0


if __name__ == "__main__":
    ui = UserInterface()
    ui.info()
    communicator = Communicator(ui)
    tt = TapDetector(communicator)

    while True:
        block = tt.listen()
        # DO NOT SLEEP
        # The length of time required to record a block is enough of a wait