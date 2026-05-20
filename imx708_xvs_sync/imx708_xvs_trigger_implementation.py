#!/usr/bin/env python3
"""
IMX708 XVS trigger_mode 実装・検証ガイド
=========================================

【背景】
8mmフィルムカメラ（8〜32fps、±2fps メカジッター）のシャッター開放タイミングを
検出し、Zero 2WのGPIOからXVSパルスを生成してIMX708のフレーム読み出しを同期させる。

【パッチ方針】
IMX477のtrigger_mode実装を移植。使用レジスタはIMX477と同じアドレスを仮定。

=================================================================
STEP 1: レジスタアドレス検証（実機必須）
=================================================================

Zero 2W上で以下を実行してI2Cトレースを取得:

  # I2Cトレース有効化
  sudo modprobe i2c-dev
  sudo sh -c 'echo 1 > /sys/kernel/debug/tracing/events/i2c/i2c_write/enable'
  sudo sh -c 'cat /sys/kernel/debug/tracing/trace_pipe > /tmp/i2c_trace.txt' &
  TRACE_PID=$!

  # カメラを通常動作で起動・停止
  rpicam-still -t 3000 -o /tmp/test.jpg

  # トレース停止
  kill $TRACE_PID

  # レジスタ書き込みを確認（IMX708のI2Cアドレスは0x1a）
  grep "i2c-1.*#0.*a=01a" /tmp/i2c_trace.txt | head -100

上記でFRM_LENGTH_A(0x0340)等が確認できれば、次に
0x3F0B, 0x3041, 0x3040, 0x4B81 を手動書き込みして動作を確認する。

=================================================================
STEP 2: 手動I2Cテスト（パッチなしでレジスタ検証）
=================================================================
"""

import subprocess
import time

I2C_BUS = 10       # Zero 2WのCSIカメラI2Cバス（要確認: i2cdetect -l）
IMX708_ADDR = 0x1a # IMX708のI2Cアドレス

def i2c_write(bus, addr, reg, val):
    """16bitレジスタアドレス + 8bitデータを書き込む"""
    reg_hi = (reg >> 8) & 0xFF
    reg_lo = reg & 0xFF
    cmd = ['i2ctransfer', '-y', str(bus),
           f'w3@0x{addr:02x}', f'0x{reg_hi:02x}', f'0x{reg_lo:02x}', f'0x{val:02x}']
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0

def i2c_read(bus, addr, reg):
    """16bitレジスタアドレスから8bitデータを読み取る"""
    reg_hi = (reg >> 8) & 0xFF
    reg_lo = reg & 0xFF
    cmd = ['i2ctransfer', '-y', str(bus),
           f'w2@0x{addr:02x}', f'0x{reg_hi:02x}', f'0x{reg_lo:02x}',
           'r1']
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return int(result.stdout.strip(), 16)
    return None

def verify_registers():
    """
    カメラがストリーミング中に実行。
    XVS関連レジスタの現在値を読み取り、書き換えて動作変化を確認。
    """
    print("=== IMX708 XVS レジスタ検証 ===")
    print(f"I2C bus: {I2C_BUS}, addr: 0x{IMX708_ADDR:02x}")
    print()

    regs = {
        0x3F0B: "MC_MODE    (想定: 0=通常, 1=マルチカメラ)",
        0x3041: "MS_SEL     (想定: 0=スレーブ, 1=マスター)",
        0x3040: "XVS_IO_CTRL(想定: 0=INPUT, 1=OUTPUT)",
        0x4B81: "EXTOUT_EN  (想定: 0=無効, 1=有効)",
    }

    print("【現在値読み取り】")
    for reg, desc in regs.items():
        val = i2c_read(I2C_BUS, IMX708_ADDR, reg)
        if val is not None:
            print(f"  0x{reg:04X} ({desc}): 0x{val:02X} = {val}")
        else:
            print(f"  0x{reg:04X} ({desc}): 読み取り失敗")
    print()

    print("【sinkモード設定（test）】")
    print("  ※カメラストリーミング中に実行。XVSピンに1.8Vパルスを入力して動作確認。")

    # sinkモード設定（IMX477と同じ値）
    writes = [
        (0x3F0B, 1, "MC_MODE=1 (マルチカメラON)"),
        (0x3041, 0, "MS_SEL=0 (スレーブ)"),
        (0x3040, 0, "XVS_IO_CTRL=0 (INPUT)"),
        (0x4B81, 0, "EXTOUT_EN=0 (出力無効)"),
    ]
    for reg, val, desc in writes:
        ok = i2c_write(I2C_BUS, IMX708_ADDR, reg, val)
        status = "OK" if ok else "FAILED"
        print(f"  write 0x{reg:04X} = 0x{val:02X} ({desc}): {status}")

    print()
    print("【確認方法】")
    print("  上記書き込み後、XVSピンに1.8Vパルスを入力し:")
    print("  - フレーム読み出しがパルスに同期して変化するか確認")
    print("  - rpicam-vid のフレームタイムスタンプでジッターを観察")


"""
=================================================================
STEP 3: 完全パッチの適用手順（Zero 2W上でのビルド）
=================================================================

# 1. カーネルソースとビルドツール取得
sudo apt install -y git bc bison flex libssl-dev make
git clone --depth=1 --branch rpi-6.12.y \
    https://github.com/raspberrypi/linux ~/linux-rpi

# 2. 現在のカーネル設定を引き継ぐ
cd ~/linux-rpi
KERNEL=kernel_2712   # Pi Zero 2W用
make bcm2711_defconfig  # Zero 2W = bcm2711系
zcat /proc/config.gz > .config  # 現在の設定を引き継ぎ

# 3. IMX708ドライバーを手動編集
nano drivers/media/i2c/imx708.c
# 以下の4か所を追加:

## 3a. includeの後、既存#defineの近くに追加:
#define IMX708_REG_MC_MODE     0x3F0B
#define IMX708_REG_MS_SEL      0x3041
#define IMX708_REG_XVS_IO_CTRL 0x3040
#define IMX708_REG_EXTOUT_EN   0x4B81

static int trigger_mode;
module_param(trigger_mode, int, 0644);
MODULE_PARM_DESC(trigger_mode,
    "XVS trigger: 0=standalone, 1=source, 2=sink(for shutter sync)");

## 3b. struct imx708 に追加:
    int trigger_mode_of;  /* from DT, -1 = use module param */

## 3c. imx708_probe() の最後あたりに追加:
    if (of_property_read_s32(client->dev.of_node, "trigger-mode",
                             &imx708->trigger_mode_of))
        imx708->trigger_mode_of = -1;

## 3d. imx708_start_streaming() 内、__v4l2_ctrl_handler_setup() の
##    呼び出し直後、MODE_SELECT書き込みの直前に追加:
    {
        int tm = (imx708->trigger_mode_of >= 0) ?
                  imx708->trigger_mode_of : trigger_mode;
        if (tm > 0) {
            imx708_write_reg(imx708, IMX708_REG_MC_MODE,
                             IMX708_REG_VALUE_08BIT, 1);
            imx708_write_reg(imx708, IMX708_REG_MS_SEL,
                             IMX708_REG_VALUE_08BIT, (tm <= 1) ? 1 : 0);
            imx708_write_reg(imx708, IMX708_REG_XVS_IO_CTRL,
                             IMX708_REG_VALUE_08BIT, (tm == 1) ? 1 : 0);
            ret = imx708_write_reg(imx708, IMX708_REG_EXTOUT_EN,
                                   IMX708_REG_VALUE_08BIT, (tm == 1) ? 1 : 0);
            if (ret) goto err_rpm_put;
        }
    }

# 4. モジュールのみビルド（フルビルド不要）
make -j4 M=drivers/media/i2c modules

# 5. モジュール差し替え
sudo cp drivers/media/i2c/imx708.ko \
    /lib/modules/$(uname -r)/kernel/drivers/media/i2c/
sudo depmod -a
sudo modprobe -r imx708
sudo modprobe imx708 trigger_mode=2


=================================================================
STEP 4: Picoなし・Zero 2W GPIOでの外部XVSトリガー
=================================================================
"""

import RPi.GPIO as GPIO
import time

SHUTTER_IN = 18   # フォトインタラプタ from 8mm camera (3.3V対応)
XVS_OUT    = 24   # → 電圧ディバイダ(10kΩ+10kΩ) → IMX708 XVS pin

GPIO.setmode(GPIO.BCM)
GPIO.setup(SHUTTER_IN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(XVS_OUT, GPIO.OUT, initial=GPIO.HIGH)  # XVSはActiveHigh待機

_pulse_count = 0

def shutter_callback(channel):
    """
    フォトインタラプタがシャッター開放を検出したら即座にXVSパルスを生成。
    Linux GPIOコールバックのジッター: ~100μs〜500μs
    8mmシャッター開放時間(32fps): ~15ms
    → ジッターは許容範囲内
    """
    global _pulse_count
    _pulse_count += 1

    # XVSパルス生成: Lowパルス（IMX477実績: 40ns〜フレーム周期）
    # GPIO経由なので実際は~1μs以上になる（問題なし）
    GPIO.output(XVS_OUT, GPIO.LOW)
    time.sleep(0.0001)  # 100μs Low
    GPIO.output(XVS_OUT, GPIO.HIGH)

    if _pulse_count % 100 == 0:
        print(f"  {_pulse_count} frames triggered")

def main():
    print("IMX708 XVS Shutter Sync")
    print(f"  Listening on GPIO{SHUTTER_IN} (shutter input)")
    print(f"  Pulsing   GPIO{XVS_OUT} (XVS output, via voltage divider)")
    print()
    print("Hardware:")
    print("  GPIO24 (3.3V) → 10kΩ → XVS node → 10kΩ → GND")
    print("  XVS node → IMX708 XVS pin")
    print("  Result voltage: ~1.65V (IMX708 threshold: 0.8*1.8V = 1.44V OK)")
    print()

    # imx708をsinkモードで起動する必要あり:
    # echo 2 | sudo tee /sys/module/imx708/parameters/trigger_mode
    # その後 rpicam-vid を起動

    GPIO.add_event_detect(
        SHUTTER_IN,
        GPIO.FALLING,         # シャッター開放 = LOW
        callback=shutter_callback,
        bouncetime=5          # 5ms チャタリング除去
    )

    try:
        print("Press Ctrl+C to stop")
        while True:
            time.sleep(1)
            fps_est = _pulse_count  # 1秒間のカウント
            print(f"  ~{fps_est} fps detected")
            _pulse_count = 0  # type: ignore  # reset for next second
    except KeyboardInterrupt:
        print("Stopped")
    finally:
        GPIO.cleanup()

if __name__ == "__main__":
    verify_registers()
