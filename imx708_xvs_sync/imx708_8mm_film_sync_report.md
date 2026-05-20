# IMX708 (Arducam) × 8mmフィルムカメラ  
## シャッタータイミング同期撮影システム 詳細検討報告

**作成日：** 2026-05-20  
**対象カメラ：** Arducam IMX708 固定フォーカス版（B0308相当）  
**接続先：** Raspberry Pi Zero 2W（MIPIダイレクト接続）

---

## 1. 目的と要件

### 1.1 目的

8mmフィルムカメラをデジタル化（テレシネ）するにあたり、フィルムカメラのシャッター開放タイミングに正確に同期してIMX708でフレームを取得する。

### 1.2 要件定義

| 項目 | 内容 |
|------|------|
| 対象FPS | 8 / 16 / 32fps（設定固定） |
| メカジッター | ±2fps程度（例：32fps設定 → 30〜34fps相当の周期変動） |
| 同期精度 | 8mmシャッター開放中（約15ms@32fps）に確実にキャプチャできること |
| 追従方式 | 外部トリガー信号によるフレームタイミング同期 |
| 構成制約 | Zero 2W + IMX708 MIPI直結、Picoなし |
| 解像度 | IMX708の12MP（4608×2592）またはその縮小モード |

---

## 2. ハードウェア構成

### 2.1 使用機材

```
[8mmフィルムカメラ]
     ↓ シャッター開放（回転板の通過）
[フォトインタラプタ]（TCST2103等、5V→3.3Vレベル変換済み）
     ↓ 3.3Vパルス信号
[Raspberry Pi Zero 2W]
  GPIO18 ← シャッター検出入力（プルアップ、FALLING検出）
  GPIO24 → 電圧ディバイダ → XVS入力
     ↓ 1.8V XVSパルス
[Arducam IMX708 B0308]
  MIPIケーブル（22ピンまたは15ピン）
```

### 2.2 電圧変換回路

IMX708のXVSピンは1.8V系。Zero 2WのGPIOは3.3V系のため電圧ディバイダで対応する。

```
GPIO24(3.3V) ──┬── 10kΩ ──┬── IMX708 XVS
               │           │
              GND       10kΩ
                           │
                          GND

出力電圧: 3.3V × 10k/(10k+10k) = 1.65V
IMX708入力Hi閾値: 0.8 × 1.8V = 1.44V → 1.65V > 1.44V ✓
```

> **注意：** XVSパッドへのアクセスはArducam基板設計に依存する。後述のハードウェア課題を参照。

---

## 3. IMX708センサーのXVS同期機能

### 3.1 Sony IMXセンサーのXVS機能

IMX708はSony Exmor RS系センサーであり、複数センサー間同期のためのXVS（Vertical Sync）ピンを備える。このピンはレジスタ設定によって入力（スレーブ）または出力（マスター）として機能する。

| モード | XVS方向 | 動作 |
|--------|---------|------|
| standalone（0） | 未使用 | 通常の自走動作 |
| source（1） | OUTPUT | 毎フレームXVSパルスを出力（マスター） |
| **sink（2）** | **INPUT** | **外部XVSパルスに同期してフレーム読み出しを開始（スレーブ）** ← 今回の目的 |

**sinkモードの動作：** センサーは内部クロックで連続動作を続けながら、外部XVSパルスが来たタイミングでフレームの読み出し開始タイミングを合わせる。

### 3.2 XVS sinkモードのジッター耐性

IMX477（HQカメラ）での実証データ：
- 設定フレームレートに対して **±12.5%程度の周期変動でも動作確認済み**
- 32fps設定に対する±2fps（±6.25%）の変動は十分吸収可能
- パルスが速すぎる場合：フレームドロップ
- パルスが遅すぎる場合：フレーム間に輝度段差（影響は軽微）
- **推奨：設定FPSをメカ最大FPSより2〜3fps高めに設定**（例：32fps動作なら35fps設定）

### 3.3 「XVS sinkモード」と「真の外部トリガー」の違い

| | XVS sinkモード（IMX708で可能） | 真の外部トリガー（IMX296専用） |
|--|------|------|
| センサー動作 | 連続ストリーミング継続 | 静止待機→パルスで1枚撮影 |
| 任意タイミングの1枚撮影 | △（連続の中でタイミング同期） | ◎ |
| 8mmテレシネ用途 | ✓（実用的に問題なし） | ◎（理想的） |
| IMX708での実現 | **本パッチで対応** | センサー仕様上不可 |

8mmテレシネ用途では、フィルムは常に一定周期で動いており「連続の中でタイミング同期」で十分対応できる。

---

## 4. ドライバー解析と移植計画

### 4.1 IMX477 trigger_mode実装の解析

公式`imx477.c`（rpi-6.12.y）から取得した実装：

```c
/* imx477.c より */
#define IMX477_REG_MC_MODE     CCI_REG8(0x3F0B)  /* マルチカメラモード有効化 */
#define IMX477_REG_MS_SEL      CCI_REG8(0x3041)  /* マスター/スレーブ選択   */
#define IMX477_REG_XVS_IO_CTRL CCI_REG8(0x3040)  /* XVSピン入出力方向       */
#define IMX477_REG_EXTOUT_EN   CCI_REG8(0x4B81)  /* 外部出力イネーブル       */

/* imx477_start_streaming() 内 */
/* Set vsync trigger mode: 0=standalone, 1=source, 2=sink */
tm = (imx477->trigger_mode_of >= 0) ? imx477->trigger_mode_of : trigger_mode;
cci_write(regmap, IMX477_REG_EXTOUT_EN, (tm == 1) ? 1 : 0, &ret);
cci_write(regmap, IMX477_REG_MS_SEL,   (tm <= 1) ? 1 : 0, &ret);
cci_write(regmap, IMX477_REG_XVS_IO_CTRL, (tm == 1) ? 1 : 0, &ret);
cci_write(regmap, IMX477_REG_MC_MODE,  (tm > 0)  ? 1 : 0, &ret);
```

sink（tm=2）時の設定値まとめ：

| レジスタ | アドレス | sink時の値 | 意味 |
|---------|---------|-----------|------|
| MC_MODE | 0x3F0B | **1** | マルチカメラモードON |
| MS_SEL | 0x3041 | **0** | スレーブ（外部XVS受信） |
| XVS_IO_CTRL | 0x3040 | **0** | XVSピンをINPUT方向 |
| EXTOUT_EN | 0x4B81 | **0** | 外部出力無効 |

### 4.2 IMX708ドライバーの現状

`imx708.c`（rpi-6.12.y）にはtrigger_mode関連のコードが**一切存在しない**。  
公式ラズパイエンジニア（6by9）も「IMX708モジュールはXVSを外部に出していないため対応しない」と表明済み。

### 4.3 IMX708への移植：レジスタアドレスの仮定

IMX708はIMX477と同じSony Exmor RS系ファミリーであるため、内部レジスタ体系が共通の可能性が高い。ただしIMX708のデータシートは非公開（リークなし）のため、以下は**仮定**であり実機検証が必須。

```
【仮定するレジスタアドレス（IMX477と同じ）】
IMX708_REG_MC_MODE     = 0x3F0B
IMX708_REG_MS_SEL      = 0x3041
IMX708_REG_XVS_IO_CTRL = 0x3040
IMX708_REG_EXTOUT_EN   = 0x4B81
```

### 4.4 imx708.cへの追加コード

以下4箇所の修正が必要：

**① レジスタ定義とモジュールパラメータ追加**
```c
#define IMX708_REG_MC_MODE     0x3F0B
#define IMX708_REG_MS_SEL      0x3041
#define IMX708_REG_XVS_IO_CTRL 0x3040
#define IMX708_REG_EXTOUT_EN   0x4B81

static int trigger_mode;
module_param(trigger_mode, int, 0644);
MODULE_PARM_DESC(trigger_mode,
    "XVS trigger: 0=standalone, 1=source, 2=sink(shutter sync)");
```

**② struct imx708にフィールド追加**
```c
struct imx708 {
    /* ... 既存フィールド ... */
    int trigger_mode_of;  /* Device Treeから取得、-1=モジュールパラメータを使用 */
};
```

**③ imx708_probe()にDT読み取りを追加**
```c
if (of_property_read_s32(client->dev.of_node, "trigger-mode",
                         &imx708->trigger_mode_of))
    imx708->trigger_mode_of = -1;
```

**④ imx708_start_streaming()にtrigger_mode設定を追加**  
（`__v4l2_ctrl_handler_setup()` の後、`IMX708_MODE_STREAMING` 書き込みの直前）
```c
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
        dev_info(&client->dev, "imx708: XVS trigger_mode=%d (%s)\n",
                 tm, tm == 1 ? "source" : "sink");
    }
}
```

---

## 5. ハードウェア課題：XVSパッドへのアクセス

### 5.1 Arducam固定フォーカス版（B0308）の構造上の問題

```
[公式ラズパイ Camera Module 3 Sensor Assembly]
      ← IMX708チップ + レンズ + 受動部品を一体パッケージ化
      ← XVSはパッケージ内部で配線されており、外部コネクタに出ていない
         （ラズパイ社エンジニア 6by9 が明言）
      ↓ 22ピンまたは15ピン FPCコネクタ
[Arducam キャリア基板（薄い）]
      ← ラズパイのSensor Assemblyをそのまま搭載
      ← 独自の再配線は行っていない
      ↓ 15ピン FFCケーブル
[Raspberry Pi Zero 2W]
```

**結論：Arducam固定フォーカス版（B0308）のXVSパッドへのアクセスは困難。**

### 5.2 Arducam AF版（B0311/B0312）の可能性

AF版はArducamがIMX708チップを独自基板に直接実装しており、4レーンMIPIに対応するなど独自配線を行っている。Arducamのクアッドキット（B0484）で複数台のIMX708をI2Cブロードキャスト＋クロック共有で同期させているのも、この独自設計基板があるからである。

**AF版シングルカメラ（B0311）にXVSパッドが露出しているかどうかは基板の実物確認が必要。**  
クアッドキットのカメラモジュール単体（HATなし）を入手して観察するのが最短の確認手段。

### 5.3 現実的な選択肢の比較

| 手段 | XVSアクセス | ドライバー | 解像度 | コスト | 推奨度 |
|------|------------|-----------|--------|--------|--------|
| B0308（固定F）パッケージ改造 | △ 困難 | 要改造 | 12MP | 低 | ✗ |
| **B0311（AF版）基板確認** | **△ 要確認** | **要改造** | **12MP** | **中** | **◎** |
| B0484クアッドキット単体使用 | ○ 高可能性 | 要改造 | 12MP | 高 | ○ |
| **Arducamへカスタム依頼** | **◎ 確実** | **◎ 対応可** | **12MP** | **要見積** | **◎** |
| IMX477（HQカメラ）に変更 | ◎ XVSパッド公式あり | ◎ 標準対応 | 12.3MP | 低 | ◎ |
| IMX296（GS Camera）に変更 | ◎ XTRIG公式対応 | ◎ 標準対応 | 1.6MP | 低 | △（低解像度） |

---

## 6. ビルド・導入手順

### 6.1 カーネルモジュールのビルド（Zero 2W上）

```bash
# 依存パッケージ
sudo apt install -y git bc bison flex libssl-dev make raspberrypi-kernel-headers

# カーネルソース取得（モジュールビルドのみなので--depth=1で可）
git clone --depth=1 --branch rpi-6.12.y \
    https://github.com/raspberrypi/linux ~/linux-rpi
cd ~/linux-rpi

# 現在のカーネル設定を引き継ぎ
zcat /proc/config.gz > .config
make ARCH=arm oldconfig

# imx708.cを編集（前節4.4の修正を適用）
nano drivers/media/i2c/imx708.c

# モジュールのみビルド（Full buildは不要）
make -j4 M=drivers/media/i2c modules

# 差し替え
sudo cp drivers/media/i2c/imx708.ko \
    /lib/modules/$(uname -r)/kernel/drivers/media/i2c/imx708.ko
sudo depmod -a
```

### 6.2 trigger_modeの有効化

```bash
# モジュール再ロード（sinkモード=2で起動）
sudo modprobe -r imx708
sudo modprobe imx708 trigger_mode=2

# または /etc/modprobe.d/imx708.conf に永続設定
echo "options imx708 trigger_mode=2" | sudo tee /etc/modprobe.d/imx708.conf
```

### 6.3 起動シーケンス

XVS sinkモードでは、**外部XVSパルスが来ないとカメラがフレームを出力できず
タイムアウトになる**ため、起動順序が重要：

```
1. imx708 trigger_mode=2 でロード
2. rpicam-vid（sinkカメラ）を起動
3. 8mmカメラを回す（フォトインタラプタからXVSパルスが流れ始める）
4. キャプチャ開始
```

---

## 7. レジスタアドレス検証手順

### 7.1 I2Cトレースによる検証

パッチ適用前に実機でレジスタアドレスを確認する：

```bash
# トレース有効化
sudo sh -c 'echo 1 > /sys/kernel/debug/tracing/events/i2c/i2c_write/enable'
sudo sh -c 'cat /sys/kernel/debug/tracing/trace_pipe > /tmp/i2c_trace.txt' &
TRACE_PID=$!

# カメラ起動
rpicam-still -t 3000 -o /tmp/test.jpg

kill $TRACE_PID

# IMX708アドレス(0x1a)への書き込みを確認
grep "a=01a" /tmp/i2c_trace.txt | head -50
```

### 7.2 手動I2C書き込みで動作確認

カメラストリーミング中に直接レジスタを書き込んで動作変化を観察：

```bash
# MC_MODE=1（0x3F0B）を書き込む
i2ctransfer -y 10 w3@0x1a 0x3F 0x0B 0x01

# MS_SEL=0（0x3041）
i2ctransfer -y 10 w3@0x1a 0x30 0x41 0x00

# XVS_IO_CTRL=0（0x3040）
i2ctransfer -y 10 w3@0x1a 0x30 0x40 0x00

# EXTOUT_EN=0（0x4B81）
i2ctransfer -y 10 w3@0x1a 0x4B 0x81 0x00
```

上記書き込み後にXVSピンに1.8Vパルスを入力し、フレームタイムスタンプの変化を観察。

---

## 8. GPIO制御コード（Python）

```python
#!/usr/bin/env python3
"""
8mmフィルムカメラ シャッター同期 - XVSトリガー生成
Zero 2W + IMX708 構成、Picoなし
"""
import RPi.GPIO as GPIO
import time

SHUTTER_IN = 18    # フォトインタラプタ入力（FALLING = シャッター開放）
XVS_OUT    = 24    # XVS出力（→電圧ディバイダ→1.65V→IMX708 XVS）

GPIO.setmode(GPIO.BCM)
GPIO.setup(SHUTTER_IN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(XVS_OUT, GPIO.OUT, initial=GPIO.HIGH)

frame_count = 0
last_time = time.time()

def shutter_callback(channel):
    global frame_count, last_time
    frame_count += 1

    # XVSパルス生成（Low active、約100μs幅）
    # Linux GPIOのジッター: ~100〜500μs
    # 8mmシャッター開放時間@32fps: ~15ms  → 余裕あり
    GPIO.output(XVS_OUT, GPIO.LOW)
    time.sleep(0.0001)       # 100μs
    GPIO.output(XVS_OUT, GPIO.HIGH)

    # FPS計測（デバッグ用）
    now = time.time()
    if frame_count % 32 == 0:
        elapsed = now - last_time
        fps = 32 / elapsed if elapsed > 0 else 0
        print(f"Detected: {fps:.1f} fps  (frame #{frame_count})")
        last_time = now

GPIO.add_event_detect(
    SHUTTER_IN,
    GPIO.FALLING,
    callback=shutter_callback,
    bouncetime=5             # 5ms チャタリング除去
)

print("IMX708 XVS Shutter Sync - waiting for 8mm camera...")
print("Hardware: GPIO24 -> 10kΩ -> XVS -> 10kΩ -> GND")
print()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print(f"\nTotal frames: {frame_count}")
finally:
    GPIO.cleanup()
```

### 8.1 rpicam-vidの起動コマンド例

```bash
# 32fps設定（センサーFPSを実際より少し高めに設定してXVS側が律速になるようにする）
rpicam-vid \
  --framerate 35 \
  --shutter 20000 \
  --awbgains 1.5,1.5 \
  --gain 2.0 \
  --width 4608 --height 2592 \
  -t 0 \
  -o film_capture.h264
```

---

## 9. IMX219との比較・解析チームへの参考情報

### 9.1 IMX219外部トリガーとの関係

解析チームがIMX219で確認済みの外部トリガー機能について、IMX708への転用の観点から：

| 項目 | IMX219 | IMX477 | IMX708（推定） |
|------|--------|--------|--------------|
| センサー世代 | Exmor R | Exmor RS | Exmor RS |
| XVSピン | あり（GPO I/O兼用） | あり（A2ピン、双方向） | あり（推定） |
| MC_MODEレジスタ | 未調査 | 0x3F0B | **0x3F0B（仮定）** |
| MS_SELレジスタ | 未調査 | 0x3041 | **0x3041（仮定）** |
| ドライバー対応 | なし | あり（公式） | **本パッチで追加予定** |

IMX219での解析で特定したレジスタアドレスをIMX708と比較することで、IMX708の対応アドレスを推定できる可能性がある。特に `MC_MODE` に相当するレジスタが一致するかが重要。

---

## 10. 未解決課題と今後のアクション

### 10.1 優先度高

| # | 課題 | アクション | 担当 |
|---|------|-----------|------|
| 1 | **XVSパッドの物理的アクセス** | Arducam B0311（AF版）基板を実物確認。XVSテストパッドの有無を目視 | ハードウェア |
| 2 | **レジスタアドレスの実機検証** | I2Cトレースで0x3F0B等への書き込み効果を確認 | ソフトウェア |
| 3 | **パッチのビルドと動作確認** | Zero 2WでIMX708モジュールをビルドし、trigger_mode=2 で起動 | ソフトウェア |

### 10.2 優先度中

| # | 課題 | アクション |
|---|------|-----------|
| 4 | 露光時間の最適化 | 8mmフィルムの照明条件に合わせた `--shutter` 値調整 |
| 5 | フレームドロップ検出 | タイムスタンプを記録してドロップを検出するコード追加 |
| 6 | IMX219解析結果との照合 | 解析チームの結果でアドレス仮定を検証 |

### 10.3 フォールバック計画

XVSアクセスが不可能だった場合：

1. **Arducamへカスタム設計依頼**：XVSを外部コネクタに引き出した版の製作（`support@arducam.com`）
2. **IMX477（HQカメラ）への切替**：XVSパッドが公式に露出、trigger_mode=2が標準ドライバーで動作、解像度はほぼ同等（12.3MP）

---

## 11. 関連ファイル

| ファイル | 内容 |
|---------|------|
| `0001-imx708-add-trigger-mode-XVS-sink.patch` | imx708.cへの差分パッチ（適用前にレジスタ検証要） |
| `imx708_xvs_trigger_implementation.py` | 検証スクリプト・ビルド手順・GPIO制御コード一式 |

---

## 12. 参考情報

- IMX477 trigger_mode実装：`raspberrypi/linux` `rpi-6.12.y` `drivers/media/i2c/imx477.c`
- IMX708レジスタリバースエンジニアリング：`github.com/Hermann-SW/imx708_regs_annotated`
- ラズパイ公式エンジニア（6by9）のコメント：IMX708のXVSはモジュール内部で止まっており外部に出ていない（2024年2月）
- Arducamカスタム設計サービス：`support@arducam.com`
- I2Cトレース手法：`forums.raspberrypi.com/viewtopic.php?t=345763`
- 8mmテレシネでのIMX477 XVS活用実例：IMX477シンクモードで40nsパルスによる任意タイミングキャプチャを確認した実績あり
