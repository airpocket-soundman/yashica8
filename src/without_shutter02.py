# GPIOをトリガーにビデオモードで撮影する。
# シャッター除去モデル使用、シャッターシンクロはしない。
# IMX708をビデオモードで撮影
# IMX708 ビデオモード仕様 1080P 50FPS, 720p 100FPS, 480p 120FPS
# 1080P 1920 x 1080 / 720P /480P 640 x 480 or 854 x 480
# ※要画角変化 1920 x 1080はstill の最大画角と同じ。
# ※stillmode では、最大4608x2592 2304x1296までは画角同じ。
# 


import cv2
import os
import time
import RPi.GPIO as GPIO
import sys
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FfmpegOutput
import libcamera
import numpy as np
import re
import shutil


number_cut              = 0         # 動画ファイルの連番を格納
number_still            = 0         # 静止画ファイルの連番を格納

# Bolex/yashica
pin_shutter             = 25    # shutter timing pickup

# GPIO設定
GPIO.setmode(GPIO.BCM)
GPIO.setup(pin_shutter,     GPIO.IN, pull_up_down = GPIO.PUD_UP)


is_recording            = False     #録画中フラグ
max_record_sec          = 45        # 最大撮影時間
record_fps              = 16        # MP4へ変換する際のFPS設定値
temp_folder_path        = "/tmp/"
share_folder_path       = "/home/cinecamera/share/"
device_name             = "yashica"
codec                   = cv2.VideoWriter_fourcc(*'avc1')
last_shutter_time       = 0
shutter_release_threshold_time = 400        #msec シャッター開放判定の閾値
recording_start_time    = 0

# shareフォルダの動画と静止画のファイル番号を読み取る
def find_max_number_in_share_folder():
    global number_still, number_cut
    # ファイル名の数字部分を抽出する正規表現パターン
    pattern_mp4 = re.compile(r'{}(\d{{3}})\.mp4$'.format(device_name))
    pattern_jpg = re.compile(r'{}(\d{{3}})\.jpg$'.format(device_name))
    number_cut   = -1  # 存在する数字の中で最も大きいものを保持する変数
    number_still = -1
    # 指定されたフォルダ内のすべてのファイルに対してループ
    for filename in os.listdir(share_folder_path):
        match_mp4 = pattern_mp4.match(filename)
        match_jpg = pattern_jpg.match(filename)
        if match_mp4:
            # ファイル名から抽出した数字を整数として取得
            number = int(match_mp4.group(1))
            # 現在の最大値と比較して、必要に応じて更新
            if number > number_cut:
                number_cut = number
        if match_jpg:
            number = int(match_jpg.group(1))
            if number > number_still:
                number_still = number
    
    number_still += 1
    number_cut   += 1

def init_camera():
    global camera, encoder
    camera = Picamera2()
    encoder = H264Encoder(bitrate=10000000)
    """
    video_config = camera.create_video_configuration(
        main={"size": (1920, 1080), "format": "YUV420"},
        controls={
            #"ExposureTime": 20000,
            #"AnalogueGain": 1.0,
            #"AwbMode": "auto",
            "Brightness": 50,
            "Contrast": 15,
            "Saturation": 20,
            "Sharpness": 10,
            #"NoiseReductionMode": "high",
            "FrameRate": 16
        }
    )
    """
    video_config = camera.create_video_configuration(
        main={"size": (1920, 1080)},
        #controls={
        #    "ExposureTime"      :50000,
        #    "AnalogueGain"      :1.0,
        #    "AwbMode"           :False,
        #    "Brightness"        :0.0,
        #    "Contrast"          :1.0,
        #    "Saturation"        :1.0,
        #    "Sharpness"         :1.0,
        #    "NoiseReductionMode":1,
        #    #"ColourGains"       :(0.0, 0.0, 0),      
        #    "FrameRate"         :16
        #},
        transform       = libcamera.Transform(hflip=1, vflip=1),
        buffer_count    = 8
    )
    

    camera.configure(video_config)
    camera.start()

def shutter_detected(channel):
    global last_shutter_time, recording_start_time, is_recording
    current_time = int(time.perf_counter() * 1000)
    #print("detect")
    if not is_recording:
        print("start recording")
        movie_file_path = temp_folder_path + device_name + "{:03}".format(number_cut) + ".mp4"
        output = FfmpegOutput(movie_file_path)
        camera.start_recording(encoder, output)
        is_recording = True
        recording_start_time = current_time
        
    last_shutter_time = current_time

def check_recording_status():
    global is_recording, number_cut
    if is_recording:
        current_time = int(time.perf_counter() * 1000)
        print(str(current_time-last_shutter_time))
        if current_time - last_shutter_time > shutter_release_threshold_time or current_time - recording_start_time > max_record_sec * 1000:
            camera.stop_recording()
            #camera.stop()
            
            print("stop recording")
            print("start:" + str(recording_start_time) + "  diff: " + str(current_time-last_shutter_time) + "  video: " + str(current_time - recording_start_time)) 
            temp_file_path = temp_folder_path + device_name + "{:03}".format(number_cut) + ".mp4"
            save_file_path = share_folder_path + device_name + "{:03}".format(number_cut) + ".mp4"
            
            #cut_first_8_frames(temp_file_path, save_file_path)
            #os.remove(temp_file_path)
            
            shutil.move(temp_file_path, save_file_path)

            is_recording = False
            number_cut   += 1
            #camera.start()


def cut_first_8_frames(input_path, output_path):
    # ビデオキャプチャを開始
    cap = cv2.VideoCapture(input_path)

    # 出力ビデオの設定
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    # 最初の8フレームをスキップ
    for _ in range(8):
        cap.read()

    # 残りのフレームを読み込み、出力ビデオに書き込む
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        out.write(frame)

    # リソースの解放
    cap.release()
    out.release()
    print("finish cut")

if __name__ == "__main__":
    # shareフォルダ内の動画、静止画ファイルの最大番号を取得
    find_max_number_in_share_folder()       
    init_camera()
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(25, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.add_event_detect(pin_shutter, GPIO.FALLING, callback=shutter_detected, bouncetime=200)

    try:
        while True:
            check_recording_status()
            time.sleep(0.1)
    finally:
        camera.stop()
        GPIO.cleanup()