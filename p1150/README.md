# P1150 IV step test: ESP32 LED board +5V_IN

This test checks the board's +5V_IN rail for shorts or excess current. The
P1150 (S/N `EB144494`) powers TP1/TP2 one voltage step at a time, with a
current limit.

## Setup

1. Connect the P1150 output to **TP1/TP2** (+5V_IN) on the board.
2. Plug the P1150 into USB. It shows up as `0483:a430 STMicroelectronics
   "STM32 Sistemi ComPort"` on `/dev/ttyACM0` (`lsusb`, `ls /dev/ttyACM*`).
   Your user must be in the `dialout` group.
3. Close the P1150 web GUI and stop the P1150 MCP server. Only one program
   can own the instrument at a time.

## Run

```bash
/home/eva/workspace/P1150/.venv/bin/python p1150/iv_step.py p1150/iv_step_$(date +%F).csv
```

[iv_step.py](iv_step.py) uses the driver in `/home/eva/workspace/P1150`.
The test settings are at the top of the script:

| Setting | Value | Meaning |
|---|---|---|
| `STEPS_MV` | 500 → 5000, step 500 | Voltage steps (mV) |
| `OVC_MA` | 500 | Hardware over-current cutoff (mA) |
| `HOLD_S` | 3.3 | Hold time per step (s) |

**Confirm the voltage and current limit before every run.** The P1150 puts
the set voltage straight onto the board with no clamp, and its range goes up
to 17 V.

The script works in this order:

1. Sets the OVC and connects the probe at 0.5 V.
2. Steps up the voltage.
3. Averages the P1150's 1 s ammeter readings, using only readings taken
   entirely after each step change.
4. Stops at the first OVC trip or the first reading above `OVC_MA`.

The probe is always disconnected on exit. The script writes one CSV row per
step, with the average, first and last current. If the current rises between
the first and last reading of a step, the board is heating.

## Results

| Date | Result | Files |
|---|---|---|
| 2026-11-15 | **Fault.** 175 mA at 1.5 V. At 2.5 V the current rose from 615 to 861 mA (heating). Tripped the 500 mA limit at 2.0 V and the 1 A limit at 3.0 V. | [iv_step_test.png](iv_step_test.png) |
| 2026-11-17 | **Fixed.** No trip up to 5.0 V. Current flat at about 22 mA from 3.5 V upward. | [iv_step_2026-11-17.png](iv_step_2026-11-17.png), [CSV](iv_step_2026-11-17.csv) |

2026-11-17 readings (1 s average):

| V | 0.5 | 1.0 | 1.5 | 2.0 | 2.5 | 3.0 | 3.5 | 4.0 | 4.5 | 5.0 |
|---|---|---|---|---|---|---|---|---|---|---|
| mA | 0.005 | 0.007 | 0.021 | 0.023 | 0.91 | 8.9 | 21.1 | 21.8 | 22.0 | 22.0 |

The "before" curve in the 2026-11-17 plot was read off the 2026-11-15 image,
so its values are approximate.
