# ESP32 WS2812B Controller — Programming Guide

Oct 30, 2026 · Board rev 0.2 · ESP32-S3-WROOM-1 (N8 or N8R8)

## Summary

You program the board over its USB-C port with a normal USB-C data cable. You don't need a separate programmer. The ESP32-S3's built-in USB connects straight to the port (D+/D− on GPIO20/GPIO19). The RST and BOOT buttons put the chip into download mode when needed.

There are two ways to run the board:

- **WLED (recommended):** ready-made LED firmware you install from a web browser and control from a phone app or web page. You don't write any code.
- **Your own code:** Arduino IDE or PlatformIO with the FastLED or Adafruit NeoPixel library.

## Board reference

### LED outputs

| Terminal | Lid label | GPIO | Level shifter (74AHCT125) |
| --- | --- | --- | --- |
| J4 | OUT1 | GPIO4 | U3 unit 1 |
| J5 | OUT2 | GPIO5 | U3 unit 2 |
| J7 | OUT3 | GPIO6 | U3 unit 3 |
| J8 | OUT4 | GPIO7 | U3 unit 4 |

On each output terminal, pin 1 is **+5V**, pin 2 is **DATA** and pin 3 is **GND**. The level shifter's enable pins are tied to GND, so all four outputs are always active and need no setup in firmware.

### Buttons and programming pins

| Part | Function | Signal |
| --- | --- | --- |
| SW1 (RST on the lid) | Reset | EN |
| SW2 (BOOT on the lid) | Hold during reset to enter download mode | GPIO0 |
| J6 USB-C | Programming, serial log, logic power | Native USB on GPIO19/20 |
| J3 (5-pin header) | Backup UART: 1 GND, 2 TXD0, 3 RXD0, 4 EN, 5 IO0 | UART0 |
| TP7 / TP8 | Probe pads for EN and BOOT | |

### Power

| Source | What it powers |
| --- | --- |
| USB-C only | ESP32 and level shifter. **The LEDs stay off.** |
| 5 V into J1 or J2 | Everything, including the LEDs through fuse F1 (7.5 A) |
| Both at once | Safe: diodes D1/D2 keep the two supplies apart. Use both when testing LEDs while programming |

## Download mode

A brand-new module may need to be put into download mode by hand. After the first flash, the tools can usually reset the chip themselves.

1. Hold **BOOT**.
2. Tap **RST**.
3. Release **BOOT**.

With the enclosure closed, press the two printed pins on the lid labelled RST and BOOT.

After flashing, tap **RST** to start the new firmware.

## Linux setup (one time)

The board shows up as `/dev/ttyACM0`, labelled *USB JTAG/serial debug unit*. To use it without root:

```
sudo usermod -aG dialout $USER
```

Log out and back in for the change to take effect. To check the board is detected, plug it in and run `ls /dev/ttyACM*`.

## Option A: WLED (recommended)

### Install from the browser

1. Connect the board to your PC over USB-C.
2. Enter download mode (see above).
3. Open **https://install.wled.me** in **Chrome or Edge**. Firefox can't access serial ports.
4. Click **Install**, select the board's port, and confirm.
5. Wait for it to finish, then tap **RST**.

### Install with esptool (if the web installer has no ESP32-S3 build)

1. Download the ESP32-S3 `.bin` from the WLED releases page (github.com/wled/WLED/releases). Pick the build that matches your module:
   - **N8** (8 MB flash, no PSRAM): the plain 8 MB ESP32-S3 build.
   - **N8R8** (8 MB flash, 8 MB PSRAM): the build marked for octal PSRAM (`opi`).
2. Flash it:

```
pip install esptool
esptool.py --chip esp32s3 --port /dev/ttyACM0 erase_flash
esptool.py --chip esp32s3 --port /dev/ttyACM0 write_flash 0x0 WLED_<version>_ESP32-S3_<variant>.bin
```

3. Tap **RST**.

### First-time setup

1. On a phone or laptop, join the Wi-Fi network **WLED-AP** (password `wled1234`). The setup page usually opens by itself; if not, go to `http://4.3.2.1`.
2. Open **Config → Wi-Fi Setup**, enter your home network name and password, and save. The board reboots onto your network.
3. Find the board in the **WLED app** (Android or iOS), in your router's device list, or at `http://wled.local`.

### LED settings

Open **Config → LED Preferences** and add one entry per output you use:

| Setting | Value |
| --- | --- |
| Type | WS281x |
| Colour order | GRB |
| Data GPIO | 4, 5, 6 or 7 (OUT1–OUT4) |
| Length | Number of LEDs on that output |

Also set these:

- **Automatic brightness limiter (ABL):** turn it on and set the maximum current to **7000 mA or less**, below fuse F1's 7.5 A rating. If your power supply delivers less, use its rating minus about 10%.
- **LED current:** about 55 mA per LED, the WS2812B default.

Click **Save**. Test each output with a solid colour at low brightness first.

### Updating WLED later

You don't need USB for updates. Download the new `.bin` from the WLED releases page, open **Config → Security & Updates → Manual OTA update**, and upload it. Use the same build variant (`opi` or plain) as before.

## Option B: Your own code (Arduino IDE)

### Setup

1. Install **Arduino IDE 2**.
2. Open **Tools → Board → Boards Manager** and install **esp32 by Espressif Systems**.
3. Open **Tools → Manage Libraries** and install **FastLED**.
4. Under **Tools**, choose these settings:

| Setting | Value |
| --- | --- |
| Board | ESP32S3 Dev Module |
| Port | /dev/ttyACM0 |
| USB CDC On Boot | Enabled (sends `Serial` output to the USB-C port) |
| Flash Size | 8MB (64Mb) |
| PSRAM | OPI PSRAM for N8R8; Disabled for N8 |
| Partition Scheme | 8M with spiffs (or default) |
| Upload Mode | UART0 / Hardware CDC |

### Example: drive all four outputs

```cpp
#include <FastLED.h>

#define LEDS_PER_OUTPUT 60    // change to your strip length
#define BRIGHTNESS      64    // 0-255; start low

CRGB out1[LEDS_PER_OUTPUT], out2[LEDS_PER_OUTPUT];
CRGB out3[LEDS_PER_OUTPUT], out4[LEDS_PER_OUTPUT];

void setup() {
  Serial.begin(115200);
  FastLED.addLeds<WS2812B, 4, GRB>(out1, LEDS_PER_OUTPUT);  // OUT1 / J4
  FastLED.addLeds<WS2812B, 5, GRB>(out2, LEDS_PER_OUTPUT);  // OUT2 / J5
  FastLED.addLeds<WS2812B, 6, GRB>(out3, LEDS_PER_OUTPUT);  // OUT3 / J7
  FastLED.addLeds<WS2812B, 7, GRB>(out4, LEDS_PER_OUTPUT);  // OUT4 / J8
  FastLED.setMaxPowerInVoltsAndMilliamps(5, 7000);          // stay under the 7.5 A fuse
  FastLED.setBrightness(BRIGHTNESS);
  Serial.println("LED controller started");
}

void loop() {
  static uint8_t hue = 0;
  fill_rainbow(out1, LEDS_PER_OUTPUT, hue, 4);
  fill_solid(out2, LEDS_PER_OUTPUT, CRGB::Red);
  fill_solid(out3, LEDS_PER_OUTPUT, CRGB::Green);
  fill_solid(out4, LEDS_PER_OUTPUT, CRGB::Blue);
  FastLED.show();
  hue++;
  delay(20);
}
```

Click **Upload**. If it stops at "Connecting...", use the download-mode button sequence, then upload again. Open **Tools → Serial Monitor** at 115200 baud to see the log.

### PlatformIO

If you use PlatformIO, the matching `platformio.ini` is:

```ini
[env:esp32s3]
platform = espressif32
board = esp32-s3-devkitc-1
framework = arduino
board_build.flash_size = 8MB
; for N8R8 modules, uncomment:
; board_build.arduino.memory_type = qio_opi
build_flags = -DARDUINO_USB_CDC_ON_BOOT=1
lib_deps = fastled/FastLED
monitor_speed = 115200
```

## Backup: flashing through the J3 header

Use this if USB is damaged or the native USB has been turned off in firmware. You need a **3.3 V** USB-to-serial adapter (CP2102, CH340 or FT232). A 5 V adapter can damage the ESP32.

| J3 pin | Signal | Connect to |
| --- | --- | --- |
| 1 | GND | Adapter GND |
| 2 | TXD0 | Adapter RX |
| 3 | RXD0 | Adapter TX |
| 4 | EN | Adapter RTS (optional, for automatic reset) |
| 5 | IO0 | Adapter DTR (optional, for automatic download mode) |

J3 has no 3.3 V pin, so the board must be powered from USB-C or the 5 V input. If you connect only GND, TX and RX, use the BOOT and RST buttons to enter download mode. Then flash with esptool or the Arduino IDE, using the adapter's port (for example `/dev/ttyUSB0`).

## Troubleshooting

| Symptom | Likely cause and fix |
| --- | --- |
| No port appears | The cable may be charge-only, so try another one. Enter download mode. Check `dmesg` right after plugging in |
| "Permission denied" on /dev/ttyACM0 | Add yourself to the `dialout` group, then log out and back in |
| Upload stops at "Connecting..." | Enter download mode by hand (hold BOOT, tap RST, release BOOT) |
| Port disappears during upload | Normal on native USB when the chip resets. The tools reconnect. If it fails, tap RST and retry |
| Flashing worked but nothing runs | Tap RST. A new module may stay in download mode until it's reset |
| ESP32 runs but the LEDs stay dark | No 5 V on J1/J2 (USB doesn't power the LEDs), F1 has blown, or the wrong GPIO is set |
| First LED flickers or shows wrong colours | The colour order should be GRB. Make sure the strip's GND is connected to terminal pin 3 |
| WLED-AP doesn't appear | Wait 30 s after reset. If it still doesn't appear, the firmware isn't running, so reflash |
| Board resets when the LEDs get bright | The 5 V supply is too weak or its wires are too thin. Lower the ABL limit or use a bigger supply |
| Can't find WLED on the network | Check your router's device list, or hold BOOT for more than 10 s to restart WLED's own access point (WLED-AP) |
