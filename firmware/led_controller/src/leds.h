// WS2812B driver for OUT1-OUT4 (GPIO4-7 through the 74AHCT125 level shifter).
//
// One effect drives every output; each output is its own strip with its own
// length. Settings persist in NVS namespace "leds", written a couple of seconds
// after the last change so dragging a slider does not wear the flash.
#pragma once
#include <Arduino.h>
#include <ArduinoJson.h>

static const uint8_t LED_OUTPUTS = 4;
static const uint16_t LED_MAX_PER_OUTPUT = 300;
static const uint8_t LED_PRESETS = 8;

void ledsBegin();
void ledsLoop();

// JSON state for the web UI (settings, effect list, presets, live power estimate).
void ledsStateJson(JsonDocument &doc);
// Apply any subset of the keys ledsStateJson emits, plus preset actions.
// Returns an error message, or empty on success.
String ledsApplyJson(JsonVariantConst in);
// Current pixel colours for the web preview: one hex string per output.
void ledsFrameJson(JsonDocument &doc);

// "led ..." console command (serial and web console).
void ledsCommand(const String &args, Print &out);
