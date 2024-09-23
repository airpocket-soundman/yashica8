from picamera2.encoders import H264Encoder
from picamera2.outputs import FfmpegOutput
from picamera2 import Picamera2
import time


"""
おそらくコントローラブルなパラメータ(min,max,defo)
'FrameDurationLimits': (1000, 1000000000, 0),
'ColourCorrectionMatrix': (-16.0, 16.0, 0),
'NoiseReductionMode': (0, 4, 0),
'Contrast': (0.0, 32.0, 1.0),
'AwbMode': (0, 7, 0),
'ScalerCrop': ((0, 0, 0, 0), (65535, 65535, 65535, 65535), (0, 0, 0, 0)),
'AwbEnable': (False, True, 0),
'ExposureValue': (-8.0, 8.0, 0.0),
'ColourGains': (0.0, 32.0, 0),
'AeExposureMode': (0, 3, 0),
'Sharpness': (0.0, 16.0, 1.0),
'Brightness': (-1.0, 1.0, 0.0),
'AeConstraintMode': (0, 3, 0),
'AeMeteringMode': (0, 3, 0),
'AnalogueGain': (1.0, 32.0, 0),
'Saturation': (0.0, 32.0, 1.0),
'ExposureTime': (0, 999999, 0),
'AeEnable': (False, True, 0)


"""


width           = 1920
height          = 1080
frame_rate      = 16
frame_buffer    = 8

picam2 = Picamera2()
#video_config = picam2.create_video_configuration()
video_config = picam2.create_video_configuration(
    main={"size": (width, height)},
    controls={
        "ExposureTime"      :2000,
        "AnalogueGain"      :1.0,
        "AwbMode"           :False,
        "Brightness"        :0.0,
        "Contrast"          :1.0,
        "Saturation"        :1.5,
        "Sharpness"         :1.0,
        "NoiseReductionMode":1,
        #"ColourGains"       :(0.0, 0.0, 0),      
        "FrameRate"         :frame_rate
    },
    buffer_count    = frame_buffer
)


picam2.configure(video_config)

picam2.start()
for i in range(4):  # 例として30フレーム破棄
    
    frame = picam2.capture_array()
    #print(i)
    time.sleep(0.01)  # フレーム取得間の遅延

encoder = H264Encoder(bitrate=10000000)
output = FfmpegOutput("test.mp4")




#picam2.start_recording(encoder, "/dev/null")
#time.sleep(frame_buffer/frame_rate)
#picam2.stop_recording()

picam2.start_recording(encoder, output)

for i in range(10):
    print(10 - i)
    time.sleep(1)
picam2.stop_recording()
print("finish recording")