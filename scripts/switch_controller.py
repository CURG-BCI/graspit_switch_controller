#!/usr/bin/python

# open a microphone in pyAudio and listen for taps
#Obtained most source from http://stackoverflow.com/questions/4160175/detect-tap-with-pyaudio-from-live-mic
from __future__ import print_function

# import pyaudio
import struct
import math
import time
import sys
import socket

import tkinter as tk

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

class Tap:
    PRESS = 1
    RELEASE = 2
    COOLINGDOWN = 3
    NOTHING = 4

class Msg:
    NEXT_MSG = "2\n"
    SELECT_MSG = "3\n"
    WAITING_FOR_MSG = "4\n"

class TapDetector(object):
    TAP_THRESHOLD = 0.6
    # FORMAT = pyaudio.paInt16 
    SHORT_NORMALIZE = (1.0/32768.0)
    RATE = 8000  
    INPUT_BLOCK_TIME = 0.05
    INPUT_FRAMES_PER_BLOCK = int(RATE*INPUT_BLOCK_TIME)             
    CHANNELS = 2
    MAX_TAP_BLOCKS = 0.15/INPUT_BLOCK_TIME

    def __init__(self):
        # self.pa = pyaudio.PyAudio()
        self.stream = self.open_mic_stream()
        self.hasCooledDown = True

    def stop(self):
        self.stream.close()

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
        except(IOError, e):
            return Tap.NOTHING

        amplitude = self.get_rms( block )

        result = Tap.PRESS if amplitude > self.TAP_THRESHOLD else \
                 Tap.RELEASE if amplitude < -self.TAP_THRESHOLD else \
                 Tap.NOTHING

        if result is Tap.NOTHING:
            self.hasCooledDown = True
            return result
        elif self.hasCooledDown:
            self.hasCooledDown = False
            return result
        else:
            return Tap.COOLINGDOWN

    def get_rms( self, block ):
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
            sum_squares += n

        return sum_squares / count
        # return sum_squares/count

class Communicator(object):
    WAIT_THRESHOLD = 0.1
    NEXT_THRESHOLD = 1
    SELECT_THRESHOLD = 3

    def __init__(self):
        self.last_tap = time.time() - 100
        self.current_time = time.time()

        self.init_client_socket()

    def init_client_socket(self, ip='localhost', port=4775):
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((ip, port))
            return True
        except(socket.timeout, IOError):
            print("Could not connect to server")
            return False

    def handleInput(self, tap):
        if tap is Tap.PRESS:
            self.initiateCommand()
        elif tap is Tap.RELEASE:
            self.executeCommand()
        elif tap is Tap.COOLINGDOWN or tap is Tap.NOTHING:
            self.updateTime()

    def updateTime(self):
        self.current_time = time.time()

    def initiateCommand(self):
        self.last_tap = time.time()
        self.updateTime()

    def executeCommand(self):
        state, x = self.readState()
        if state is not Msg.WAITING_FOR_MSG:
            self.submitMessage(state)
        return state

    def readState(self):
        self.updateTime()
        time_since_last_tap = self.current_time - self.last_tap
        # print(time_since_last_tap)
        if 0 <= time_since_last_tap <= self.WAIT_THRESHOLD:
            msg = Msg.WAITING_FOR_MSG
        elif self.WAIT_THRESHOLD < time_since_last_tap <= self.NEXT_THRESHOLD:
            msg = Msg.NEXT_MSG
        elif self.NEXT_THRESHOLD < time_since_last_tap <= self.SELECT_THRESHOLD:
            msg = Msg.SELECT_MSG
        else: #Took too long on tap
            msg = Msg.WAITING_FOR_MSG
        return msg, time_since_last_tap

    def submitMessage(self, msg):
        self.resetLastTap()
        try:
            self.client_socket.send(msg.encode())
        except:
            connected = self.init_client_socket()
            if connected:
                self.client_socket.send(msg)
            else:
                print("Failed to send msg: %s" % msg)

    def resetLastTap(self):
        self.last_tap = time.time() - self.SELECT_THRESHOLD

class UserInterfaceFrame(tk.Frame):
    BUFFER_MSG = "Buffering input (%fs passed)"
    WAITING_FOR_INPUT_MSG = (bcolors.HEADER + "Waiting for input (%fs passed)" + bcolors.ENDC)
    REGISTERING_SELECT_MSG = (bcolors.WARNING + "Registering select (%fs passed)" + bcolors.ENDC)
    REGISTERING_NEXT_MSG = (bcolors.OKBLUE + "Registering next (%fs passed)" + bcolors.ENDC)
    SUBMITTING_SELECT_MSG = bcolors.OKGREEN + "\nSubmitting select" + bcolors.ENDC
    SUBMITTING_NEXT_MSG = bcolors.OKGREEN + "\nSubmitting next" + bcolors.ENDC
    INITIAL_TAP_MSG = bcolors.OKGREEN + "\nInitial tap" + bcolors.ENDC

    def __init__(self, parent, communicator, listener):
        tk.Frame.__init__(self, parent)

        self.communicator = communicator
        self.listener = listener
        self.size_str = 0

        buttonFrame = tk.Frame(self)

        pressButton = tk.Button(buttonFrame, text="Press Switch", command=self.pressSwitch, font=36)
        releaseButton = tk.Button(buttonFrame, text="Release Switch", command=self.releaseSwitch, font=36)

        pressButton.pack(side="top", fill="x")
        releaseButton.pack(side="top", fill="x")

        buttonFrame.pack(side="left", fill="y")

        self.current_status_label = tk.Label(self, text='Waiting for User Input', font=36)
        self.current_status_label.pack(side="left", fill="both")

        self.info()

        self.manage_queue()

    def info(self):
        print("This program controls Graspit! using an assistive controller with a 3.5mm jack input")
        print(bcolors.OKBLUE + "Blue color designates that the output is going to send a NEXT signal" + bcolors.ENDC)
        print(bcolors.WARNING + "Yellow color designates that the output is going to send a SELECT signal" + bcolors.ENDC)
        print(bcolors.HEADER + "Purple color designates that the output is waiting for user input" + bcolors.ENDC)
        print(bcolors.OKGREEN + "Green color designates that a signal was sent" + bcolors.ENDC)
        print("Hold the switch for %0.2f to %0.2f second(s) if you want to send a NEXT signal" % (Communicator.WAIT_THRESHOLD, Communicator.NEXT_THRESHOLD))
        print("Hold the switch for %0.2f to %0.2f second(s) if you want to send a SELECT signal" % (Communicator.NEXT_THRESHOLD, Communicator.SELECT_THRESHOLD))
        print()

    def print_output(self, msg):
        output = "%s%s" % (msg, " " * (self.size_str - len(msg)))
        self.size_str = len(output)
        print(output, end='\r')
        sys.stdout.flush()

    def pressSwitch(self):
        communicator.handleInput(Tap.PRESS)

    def releaseSwitch(self):
        val = communicator.handleInput(Tap.RELEASE)
        if val is Msg.NEXT_MSG:
            self.print_output(self.SUBMITTING_NEXT_MSG)
        elif val is Msg.SELECT_MSG:
            self.print_output(self.SUBMITTING_SELECT_MSG)

    def manage_queue(self):
        state, t = communicator.readState()

        if state is Msg.NEXT_MSG:
            self.current_status_label.config(text="Going to send NEXT")
            self.print_output(self.REGISTERING_NEXT_MSG % t)
        elif state is Msg.SELECT_MSG:
            self.current_status_label.config(text="Going to send SELECT")
            self.print_output(self.REGISTERING_SELECT_MSG % t)
        else:
            self.current_status_label.config(text="Waiting for user input")
            self.print_output(self.WAITING_FOR_INPUT_MSG % t)

        # repeat again in 1 millisecond
        self.after(1, self.manage_queue)

if __name__ == "__main__":
    communicator = Communicator()
    # listener = TapDetector()
    root = tk.Tk()
    UserInterfaceFrame(root, communicator, None).pack(fill="both", expand=True)
    root.mainloop()

# if __name__ == "__main__":
#     ui = UserInterface()
#     ui.info()
#     communicator = Communicator()
#     tt = TapDetector()

#     while True:
#         block = tt.listen()
        # DO NOT SLEEP
        # The length of time required to record a block is enough of a wait


#http://stackoverflow.com/questions/21667713/tkinter-background-while-loop
# import Tkinter as tk
# import Queue as queue
#
# class Example(tk.Frame):
#     def __init__(self, parent):
#         tk.Frame.__init__(self, parent)
#
#         self.queue = queue.Queue()
#
#         buttonFrame = tk.Frame(self)
#         for i in range(10):
#             b = tk.Button(buttonFrame, text=str(i),
#                           command=lambda button=i: self.press(button))
#             b.pack(side="top", fill="x")
#         self.lb = tk.Listbox(self, width=60, height=20)
#         self.vsb = tk.Scrollbar(self, command=self.lb.yview)
#         self.lb.configure(yscrollcommand=self.vsb.set)
#
#         buttonFrame.pack(side="left", fill="y")
#         self.vsb.pack(side="right", fill="y")
#         self.lb.pack(side="left", fill="both", expand=True)
#
#         self.manage_queue()
#
#     def press(self, i):
#         '''Add a button to the queue'''
#         item = "Button %s" % i
#         self.queue.put(item)
#         self.log("push", item)
#
#     def log(self, action, item):
#         '''Display an action in the listbox'''
#         message = "pushed to queue" if action == "push" else "popped from queue"
#         message += " '%s' (queue size %s)" % (item, self.queue.qsize())
#         self.lb.insert("end", message)
#         self.lb.see("end")
#
#     def manage_queue(self):
#         '''pull an item off the queue and act on it'''
#         try:
#             item = self.queue.get_nowait()
#             self.log("pop", item)
#         except queue.Empty:
#             pass
#
#         # repeat again in 1 second
#         self.after(1000, self.manage_queue)
#
# if __name__ == "__main__":
#     root = tk.Tk()
#     Example(root).pack(fill="both", expand=True)
#     root.mainloop()