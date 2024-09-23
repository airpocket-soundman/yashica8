from flask import render_template, Flask, Response
import cv2
from picamera2 import Picamera2
import time
import numpy as np
from typing import List

app = Flask(__name__, template_folder='templates')   #templates_folderはデフォルトで'templates'なので本来定義は不要

CAP_WIDTH   = 640                   #出力動画の幅
CAP_HEIGHT  = 480                   #出力動画の高さ
LAW_WIDTH   = 1640                  #カメラ内のraw画像の幅
LAW_HEIGHT  = 1232                  #カメラ内のraw画像の高さ

image_sensor = "IMX708"             #IMX219/IMX708
folder_path ="/tmp/img"
movie_length = 100                  #撮影するフレーム数
time_list = []
exposure_time = 5000                #イメージセンサの露出時間
analog_gain = 20.0                  #イメージセンサのgain

def gen_frames():
    print("gen_frames")
    count = 0

    # init camera
    cap = Picamera2()
    config = cap.create_still_configuration(main={"size":(CAP_WIDTH, CAP_HEIGHT)},raw={"size":(LAW_WIDTH,LAW_HEIGHT)}) 
    cap.configure(config)
    cap.set_controls({"ExposureTime":exposure_time, "AnalogueGain": analog_gain})
    cap.start()

    while True:
        print("count = ",count)
        start_time_frame = time.perf_counter()

        frame = cap.capture_array()
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame = cv2.flip(frame,-1)

        #フレームデータをjpgに圧縮
        ret, buffer = cv2.imencode('.jpg',frame)
        # bytesデータ化
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

        elapsed_time_frame = time.perf_counter() - start_time_frame
        print("frame_number = " + str(count) + " / time = " + str(elapsed_time_frame))
        count +=1

@app.route('/video_feed')
def video_feed():
    #imgタグに埋め込まれるResponseオブジェクトを返す
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/')
@app.route('/index')
def index():
   
    user = {'username'      : 'Raspberry Pi zero2 W',
            'image sensor'  : image_sensor,
            'lens'          : ""}
    return render_template('index.html', title='home', user=user)