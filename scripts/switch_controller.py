#!/usr/bin/python

# open a microphone in pyAudio and listen for taps
#Obtained most source from http://stackoverflow.com/questions/4160175/detect-tap-with-pyaudio-from-live-mic

import pyaudio
import struct
import math
import time

class TapDetector(object):
    TAP_THRESHOLD = 0.20
    FORMAT = pyaudio.paInt16 
    SHORT_NORMALIZE = (1.0/32768.0)
    RATE = 44100  
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

    def tapDetected(self):
        if self.hasCooledDown:
            self.communicator.tapDetected()
        self.hasCooledDown = False

    def noTapDetected(self):
        self.hasCooledDown = True
        self.communicator.noTapDetected()

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
            self.tapDetected()
        else:
            self.noTapDetected()

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
            sum_squares += n*n

        return math.sqrt( sum_squares / count )

class Communicator(object):
    WAIT_THRESHOLD = 0.5
    NEXT_THRESHOLD = 1
    SELECT_THRESHOLD = 2

    def __init__(self, ui):
        self.last_tap = time.time() - 100
        self.current_time = time.time()
        self.states = {"select": "3\n", "next": "2\n", "none": "1\n"}

        self.ui = ui

    def tapDetected(self):
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

    def noTapDetected(self):
        current_tap = time.time()
        time_since_last_tap = current_tap - self.last_tap
        if 0 <= time_since_last_tap <= self.WAIT_THRESHOLD:
            self.ui.waitingForInput()
        elif self.WAIT_THRESHOLD < time_since_last_tap <= self.NEXT_THRESHOLD:
            self.ui.registeringNext()
        elif self.NEXT_THRESHOLD < time_since_last_tap <= self.SELECT_THRESHOLD:
            self.ui.registeringSelect()
        else: #Waiting for tap
            self.ui.waitingForInput()

    def submitNext(self):
        print("Submitting next")
        self.resetLastTap()

    def submitSelect(self):
        print("Submitting select")
        self.resetLastTap()

    def initialTap(self):
        print("Initial tap")
        self.updateLastTap()

    def updateLastTap(self):
        self.last_tap = time.time()

    def resetLastTap(self):
        self.last_tap = time.time() - self.SELECT_THRESHOLD


class UserInterface(object):
    def __init__(self):
        pass

    def registeringNext(self):
        pass
        # print("Registering next")
    def registeringSelect(self):
        pass
        # print("Registering select")
    def waitingForInput(self):
        pass
        # print("Waiting for input")

if __name__ == "__main__":
    ui = UserInterface()
    communicator = Communicator(ui)
    tt = TapDetector(communicator)

    while True:
        tt.listen()