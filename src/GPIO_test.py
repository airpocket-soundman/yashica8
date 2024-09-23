#import cv2
#import os
#import subprocess
import time
#import datetime
import RPi.GPIO as GPIO
#import sys
#from picamera2 import Picamera2
#import threading
#import shutil
#import re
#from multiprocessing import Process

"""
# motocamera
pin_shutter         = 23    # shutter timing picup 
pin_led_red         = 24
pin_led_green       = 25
pin_shutdown        =  8
pin_dip1            =  7
pin_dip2            =  1
pin_dip3            = 12
pin_dip4            = 16
pin_dip5            = 20
pin_dip6            = 21
"""
# Bolex
pin_shutter         = 25    # shutter timing picup 
pin_led_red         = 15
pin_led_green       = 18
pin_shutdown        = 14
pin_dip1            =  8
pin_dip2            =  7
pin_dip3            =  1
pin_dip4            = 12
pin_dip5            = 16
pin_dip6            = 20

# GPIO設定
GPIO.setmode(GPIO.BCM)
GPIO.setup(pin_shutter,     GPIO.IN, pull_up_down = GPIO.PUD_UP)
GPIO.setup(pin_shutdown,    GPIO.IN, pull_up_down = GPIO.PUD_UP)
GPIO.setup(pin_dip1,        GPIO.IN, pull_up_down = GPIO.PUD_UP)
GPIO.setup(pin_dip2,        GPIO.IN, pull_up_down = GPIO.PUD_UP)
GPIO.setup(pin_dip3,        GPIO.IN, pull_up_down = GPIO.PUD_UP)
GPIO.setup(pin_dip4,        GPIO.IN, pull_up_down = GPIO.PUD_UP)
GPIO.setup(pin_dip5,        GPIO.IN, pull_up_down = GPIO.PUD_UP)
GPIO.setup(pin_dip6,        GPIO.IN, pull_up_down = GPIO.PUD_UP)
GPIO.setup(pin_led_red,     GPIO.OUT)
GPIO.setup(pin_led_green,   GPIO.OUT)


def on_shutter_open(channel):
    print("shutterd", channel)

def on_shutdown_button_pressed(channel):
    print("shutdown button", channel)

def read_mode(channel):
    print(channel, GPIO.input(pin_dip1), GPIO.input(pin_dip2), GPIO.input(pin_dip3), GPIO.input(pin_dip4), GPIO.input(pin_dip5), GPIO.input(pin_dip6))
# メイン
if __name__ == "__main__":

    # LED点灯初期化
    GPIO.output(pin_led_green, True)
    GPIO.output(pin_led_red, True)

        # シャッター動作検出時のコールバック関数
    GPIO.add_event_detect(pin_shutter,  GPIO.RISING,    callback = on_shutter_open, bouncetime = 5)
    # リセットボタン検出時のコールバック関数
    GPIO.add_event_detect(pin_shutdown, GPIO.FALLING,   callback = on_shutdown_button_pressed, bouncetime = 100)
    # dipswitchが切り替わった時のコールバック関数
    GPIO.add_event_detect(pin_dip1,     GPIO.BOTH,    callback = read_mode, bouncetime = 5)
    GPIO.add_event_detect(pin_dip2,     GPIO.BOTH,    callback = read_mode, bouncetime = 5)
    GPIO.add_event_detect(pin_dip3,     GPIO.BOTH,    callback = read_mode, bouncetime = 5)
    GPIO.add_event_detect(pin_dip4,     GPIO.BOTH,    callback = read_mode, bouncetime = 5)
    GPIO.add_event_detect(pin_dip5,     GPIO.BOTH,    callback = read_mode, bouncetime = 5)
    GPIO.add_event_detect(pin_dip6,     GPIO.BOTH,    callback = read_mode, bouncetime = 5)
    
    while(True):
        time.sleep(1)
        print(GPIO.input(pin_shutter))