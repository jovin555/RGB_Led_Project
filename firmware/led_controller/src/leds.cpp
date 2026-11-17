// WS2812B driver and effects for OUT1-OUT4. See leds.h.

#include "leds.h"
#include <FastLED.h>
#include <Preferences.h>

// ---------------------------------------------------------------- settings

struct Settings {
  uint8_t ver;
  bool on;
  uint8_t bri;        // 0-255, before the power limiter
  uint8_t mode;       // index into EFFECTS
  uint8_t speed;      // 0-255
  uint32_t c1, c2;    // 0xRRGGBB
  uint16_t count[LED_OUTPUTS];
  uint16_t maxMa;     // power limit for all four outputs together
  bool seqOn;         // cycle through presets
  uint16_t seqSec;
  uint8_t seqMask;    // which preset slots the sequence visits
  bool autoOn;        // cycle through effects with fresh colours
  uint16_t autoSec;
  uint16_t autoMask;  // which effects auto cycle visits
};
static const uint8_t SETTINGS_VER = 2;   // v1 had no auto cycle; it loads as defaults

struct Preset {
  char name[16];
  uint8_t used, mode, bri, speed;
  uint32_t c1, c2;
};

// Start dim and well under the 7.5 A fuse: the first power-up of a new strip
// should not be a surprise. Everything here is changeable from the web UI.
// Auto cycle defaults to every effect except "outputs" (index 10), which is a
// wiring check rather than something to look at.
static Settings st = {SETTINGS_VER, true, 64, 2, 128, 0xFF7828, 0x0050FF, {60, 60, 60, 60}, 1500, false, 30, 0,
                      false, 20, 0x03FF};
static Preset presets[LED_PRESETS];

static const char *const EFFECTS[] = {"solid", "gradient", "rainbow", "breathe", "chase", "comet",
                                      "twinkle", "fire",     "wipe",    "colorloop", "outputs"};
static const uint8_t NUM_EFFECTS = sizeof(EFFECTS) / sizeof(EFFECTS[0]);
static const uint16_t MAX_MA_LIMIT = 7000;   // stay under fuse F1 (7.5 A)

static Preferences prefs;
static bool dirty = false;
static uint32_t dirtyAt = 0;

static void markDirty() {
  dirty = true;
  dirtyAt = millis();
}

static void saveNow() {
  prefs.putBytes("st", &st, sizeof st);
  prefs.putBytes("pr", presets, sizeof presets);
  dirty = false;
}

// ---------------------------------------------------------------- strips

static CRGB buf[LED_OUTPUTS][LED_MAX_PER_OUTPUT];
static uint8_t heat[LED_OUTPUTS][LED_MAX_PER_OUTPUT];   // fire effect
static CLEDController *ctl[LED_OUTPUTS];
static uint16_t shown[LED_OUTPUTS];                      // length each controller currently drives

static void applyCounts() {
  // Shrinking a strip: blank the pixels being dropped first, or they would keep
  // their last colour forever because nothing addresses them any more.
  bool blanked = false;
  for (uint8_t o = 0; o < LED_OUTPUTS; o++) {
    if (st.count[o] < shown[o]) {
      fill_solid(buf[o], shown[o], CRGB::Black);
      blanked = true;
    }
  }
  if (blanked) FastLED.show();
  for (uint8_t o = 0; o < LED_OUTPUTS; o++) {
    // A controller with zero LEDs is not something every FastLED back end
    // accepts, so a disabled output keeps one pixel and holds it black.
    uint16_t n = st.count[o] ? st.count[o] : 1;
    ctl[o]->setLeds(buf[o], n);
    shown[o] = n;
    if (!st.count[o]) buf[o][0] = CRGB::Black;
  }
}

static void applyOutputLevel() {
  FastLED.setBrightness(st.on ? st.bri : 0);
  FastLED.setMaxPowerInVoltsAndMilliamps(5, st.maxMa);
}

static void clearAll() {
  for (uint8_t o = 0; o < LED_OUTPUTS; o++) {
    fill_solid(buf[o], LED_MAX_PER_OUTPUT, CRGB::Black);
    memset(heat[o], 0, sizeof heat[o]);
  }
}

// ---------------------------------------------------------------- effects

static uint32_t vt = 0;       // effect time: real ms scaled by speed
static uint32_t vtFrac = 0;

static void renderOutput(uint8_t o, uint16_t n) {
  CRGB *p = buf[o];
  CRGB c1 = CRGB(st.c1), c2 = CRGB(st.c2);
  switch (st.mode) {
    case 0:   // solid
      fill_solid(p, n, c1);
      break;
    case 1:   // gradient c1 -> c2 along the strip
      if (n == 1) p[0] = c1;
      else fill_gradient_RGB(p, n, c1, c2);
      break;
    case 2:   // rainbow moving along the strip, one full wheel per strip
      fill_rainbow(p, n, (uint8_t)(vt / 12), n > 1 ? max(1, 255 / n) : 0);
      break;
    case 3: {   // breathe c1
      uint8_t b = qadd8(sin8((uint8_t)(vt / 10)), 12);
      fill_solid(p, n, c1);
      nscale8(p, n, b);
      break;
    }
    case 4: {   // theater chase: c1 every third pixel over a c2 background
      uint16_t pos = vt / 80;
      CRGB bg = c2;
      bg.nscale8(40);
      for (uint16_t i = 0; i < n; i++) p[i] = ((i + pos) % 3 == 0) ? c1 : bg;
      break;
    }
    case 5: {   // comet bouncing end to end with a fading tail
      fadeToBlackBy(p, n, 48);
      if (n == 1) { p[0] = c1; break; }
      uint32_t span = 2u * (n - 1);
      uint32_t s = (vt / 15) % span;
      uint16_t head = s < (uint32_t)(n - 1) ? s : span - s;
      p[head] = c1;
      break;
    }
    case 6: {   // twinkle c1/c2 sparkles
      fadeToBlackBy(p, n, 10);
      uint8_t chance = 20 + st.speed / 2;
      for (uint8_t k = 0; k < 1 + n / 60; k++)
        if (random8() < chance) p[random16(n)] = random8() & 1 ? c1 : c2;
      break;
    }
    case 7: {   // fire (Fire2012), cooling fixed, sparking follows speed
      uint8_t *h = heat[o];
      const uint8_t cooling = 55;
      uint8_t sparking = 50 + st.speed / 2;
      for (uint16_t i = 0; i < n; i++) h[i] = qsub8(h[i], random8(0, (cooling * 10) / n + 2));
      for (int k = n - 1; k >= 2; k--) h[k] = (h[k - 1] + h[k - 2] + h[k - 2]) / 3;
      if (random8() < sparking) {
        uint8_t y = random8(min<uint16_t>(7, n));
        h[y] = qadd8(h[y], random8(160, 255));
      }
      for (uint16_t i = 0; i < n; i++) p[i] = HeatColor(h[i]);
      break;
    }
    case 8: {   // wipe: fill with c1, then with c2, repeat
      uint32_t step = (vt / 25) % (2u * n);
      bool second = step >= n;
      uint16_t edge = step % n;
      for (uint16_t i = 0; i < n; i++) p[i] = (i <= edge) ? (second ? c2 : c1) : (second ? c1 : c2);
      break;
    }
    case 9:   // colorloop: whole strip one colour, slowly round the wheel
      fill_solid(p, n, CHSV((uint8_t)(vt / 40), 255, 255));
      break;
    case 10: {   // outputs: OUT1 red, OUT2 green, OUT3 blue, OUT4 white - wiring check
      static const CRGB id[LED_OUTPUTS] = {CRGB::Red, CRGB::Green, CRGB::Blue, CRGB::White};
      fill_solid(p, n, id[o]);
      break;
    }
  }
}

// ---------------------------------------------------------------- presets / sequence

static uint32_t seqLast = 0;
static int8_t seqIdx = -1;

static void loadPreset(uint8_t slot) {
  const Preset &pr = presets[slot];
  st.mode = pr.mode < NUM_EFFECTS ? pr.mode : 0;
  st.bri = pr.bri;
  st.speed = pr.speed;
  st.c1 = pr.c1;
  st.c2 = pr.c2;
  clearAll();
  applyOutputLevel();
}

static void stepSequence() {
  if (!st.seqOn) return;
  uint8_t mask = st.seqMask;
  for (uint8_t i = 0; i < LED_PRESETS; i++)
    if (!presets[i].used) mask &= ~(1 << i);
  if (!mask) return;
  if (seqIdx >= 0 && millis() - seqLast < (uint32_t)st.seqSec * 1000) return;
  for (uint8_t k = 1; k <= LED_PRESETS; k++) {
    uint8_t i = (seqIdx + k + LED_PRESETS) % LED_PRESETS;
    if (mask & (1 << i)) {
      seqIdx = i;
      break;
    }
  }
  seqLast = millis();
  loadPreset(seqIdx);   // not persisted: a sequence step is not a settings change
}

static uint32_t autoLast = 0;
static int8_t autoIdx = -1;

static uint32_t rgbOf(const CHSV &hsv) {
  CRGB c;
  hsv2rgb_rainbow(hsv, c);
  return ((uint32_t)c.r << 16) | ((uint32_t)c.g << 8) | c.b;
}

static void stepAuto() {
  if (!st.autoOn) return;
  uint16_t mask = st.autoMask & ((1u << NUM_EFFECTS) - 1);
  if (!mask) return;
  if (autoIdx >= 0 && millis() - autoLast < (uint32_t)st.autoSec * 1000) return;
  for (uint8_t k = 1; k <= NUM_EFFECTS; k++) {
    uint8_t i = (autoIdx + k + NUM_EFFECTS) % NUM_EFFECTS;
    if (mask & (1u << i)) {
      autoIdx = i;
      break;
    }
  }
  autoLast = millis();
  // A fresh pair each step: a random main hue, and a second colour that is
  // either its complement, a triad partner, or a near neighbour, so two-colour
  // effects (gradient, chase, twinkle, wipe) always have some contrast.
  static const uint8_t offsets[] = {128, 85, 171, 32, 224};
  // esp_random() is the hardware RNG: random8() is unseeded, so it would
  // replay the same colours after every boot.
  uint32_t r = esp_random();
  uint8_t h = r & 0xFF;
  st.c1 = rgbOf(CHSV(h, 255, 255));
  st.c2 = rgbOf(CHSV(h + offsets[(r >> 8) % sizeof offsets], 255, 255));
  st.mode = autoIdx;
  clearAll();   // not persisted, for the same reason as a sequence step
}

// ---------------------------------------------------------------- lifecycle

void ledsBegin() {
  prefs.begin("leds", false);
  Settings saved;
  if (prefs.getBytes("st", &saved, sizeof saved) == sizeof saved && saved.ver == SETTINGS_VER) st = saved;
  if (prefs.getBytes("pr", presets, sizeof presets) != sizeof presets) memset(presets, 0, sizeof presets);

  ctl[0] = &FastLED.addLeds<WS2812B, 4, GRB>(buf[0], 1);   // OUT1 / J4
  ctl[1] = &FastLED.addLeds<WS2812B, 5, GRB>(buf[1], 1);   // OUT2 / J5
  ctl[2] = &FastLED.addLeds<WS2812B, 6, GRB>(buf[2], 1);   // OUT3 / J7
  ctl[3] = &FastLED.addLeds<WS2812B, 7, GRB>(buf[3], 1);   // OUT4 / J8
  for (uint8_t o = 0; o < LED_OUTPUTS; o++) shown[o] = 1;
  // Dithering assumes a steady frame rate; Wi-Fi traffic makes ours uneven and
  // dithering then shows up as flicker at low brightness.
  FastLED.setDither(0);
  random16_set_seed(esp_random());   // twinkle/fire patterns differ per boot
  clearAll();
  applyCounts();
  applyOutputLevel();
}

void ledsLoop() {
  static uint32_t last = 0;
  uint32_t now = millis();
  if (now - last < 16) return;   // ~60 fps
  uint32_t dt = now - last;
  last = now;
  if (dt > 100) dt = 100;        // after a long stall, don't jump the animation

  vtFrac += dt * (st.speed + 16);
  vt += vtFrac / 96;
  vtFrac %= 96;

  stepSequence();
  stepAuto();
  for (uint8_t o = 0; o < LED_OUTPUTS; o++)
    if (st.count[o]) renderOutput(o, st.count[o]);
  FastLED.show();

  if (dirty && now - dirtyAt > 2000) saveNow();
}

// ---------------------------------------------------------------- JSON

static String hexColor(uint32_t c) {
  char b[8];
  snprintf(b, sizeof b, "#%06lX", (unsigned long)(c & 0xFFFFFF));
  return b;
}

static bool parseColor(String s, uint32_t &out) {
  s.trim();
  s.toLowerCase();
  static const struct { const char *n; uint32_t c; } named[] = {
      {"red", 0xFF0000},    {"green", 0x00FF00}, {"blue", 0x0000FF},   {"white", 0xFFFFFF},
      {"warm", 0xFF9A40},   {"orange", 0xFF6000}, {"yellow", 0xFFC000}, {"purple", 0x8000FF},
      {"pink", 0xFF2080},   {"cyan", 0x00FFFF},  {"off", 0x000000},    {"black", 0x000000}};
  for (auto &n : named)
    if (s == n.n) { out = n.c; return true; }
  if (s.startsWith("#")) s = s.substring(1);
  if (s.length() != 6) return false;
  for (char ch : s)
    if (!isxdigit((unsigned char)ch)) return false;
  out = strtoul(s.c_str(), nullptr, 16);
  return true;
}

static int effectIndex(const String &s) {
  for (uint8_t i = 0; i < NUM_EFFECTS; i++)
    if (s.equalsIgnoreCase(EFFECTS[i])) return i;
  if (s.length() && isdigit((unsigned char)s[0]) && s.toInt() < NUM_EFFECTS) return s.toInt();
  return -1;
}

static uint32_t estimateMa(bool &limited) {
  uint32_t mw = 0;
  for (uint8_t o = 0; o < LED_OUTPUTS; o++)
    if (st.count[o]) mw += calculate_unscaled_power_mW(buf[o], st.count[o]);
  uint8_t target = st.on ? st.bri : 0;
  uint8_t actual = calculate_max_brightness_for_power_mW(target, (uint32_t)st.maxMa * 5);
  limited = actual < target;
  return (uint64_t)mw * actual / 255 / 5;
}

void ledsStateJson(JsonDocument &doc) {
  doc["on"] = st.on;
  doc["bri"] = st.bri;
  doc["mode"] = st.mode;
  doc["speed"] = st.speed;
  doc["c1"] = hexColor(st.c1);
  doc["c2"] = hexColor(st.c2);
  JsonArray cnt = doc["count"].to<JsonArray>();
  for (uint8_t o = 0; o < LED_OUTPUTS; o++) cnt.add(st.count[o]);
  doc["max_per_output"] = LED_MAX_PER_OUTPUT;
  doc["maxma"] = st.maxMa;
  doc["maxma_limit"] = MAX_MA_LIMIT;
  bool limited;
  doc["est_ma"] = estimateMa(limited);
  doc["limited"] = limited;
  JsonArray m = doc["modes"].to<JsonArray>();
  for (uint8_t i = 0; i < NUM_EFFECTS; i++) m.add(EFFECTS[i]);
  JsonObject sq = doc["seq"].to<JsonObject>();
  sq["on"] = st.seqOn;
  sq["sec"] = st.seqSec;
  sq["mask"] = st.seqMask;
  sq["current"] = st.seqOn ? seqIdx : -1;
  JsonObject au = doc["auto"].to<JsonObject>();
  au["on"] = st.autoOn;
  au["sec"] = st.autoSec;
  au["mask"] = st.autoMask;
  au["current"] = st.autoOn ? autoIdx : -1;
  JsonArray pr = doc["presets"].to<JsonArray>();
  for (uint8_t i = 0; i < LED_PRESETS; i++) {
    if (!presets[i].used) { pr.add(nullptr); continue; }
    JsonObject p = pr.add<JsonObject>();
    p["name"] = presets[i].name;
    p["mode"] = presets[i].mode;
    p["c1"] = hexColor(presets[i].c1);
    p["c2"] = hexColor(presets[i].c2);
  }
}

String ledsApplyJson(JsonVariantConst in) {
  bool effectChanged = false;
  if (in["on"].is<bool>()) st.on = in["on"];
  if (in["bri"].is<int>()) st.bri = constrain(in["bri"].as<int>(), 0, 255);
  if (in["speed"].is<int>()) st.speed = constrain(in["speed"].as<int>(), 0, 255);
  if (!in["mode"].isNull()) {
    int m = in["mode"].is<int>() ? in["mode"].as<int>() : effectIndex(in["mode"].as<String>());
    if (m < 0 || m >= NUM_EFFECTS) return "unknown effect";
    if (m != st.mode) clearAll();
    st.mode = m;
    effectChanged = true;
  }
  for (const char *k : {"c1", "c2"}) {
    if (in[k].isNull()) continue;
    uint32_t c;
    if (!parseColor(in[k].as<String>(), c)) return String("bad colour for ") + k;
    (k[1] == '1' ? st.c1 : st.c2) = c;
    effectChanged = true;
  }
  if (in["count"].is<JsonArrayConst>()) {
    JsonArrayConst a = in["count"];
    for (uint8_t o = 0; o < LED_OUTPUTS && o < a.size(); o++)
      st.count[o] = constrain(a[o].as<int>(), 0, (int)LED_MAX_PER_OUTPUT);
    applyCounts();
  }
  if (in["maxma"].is<int>()) st.maxMa = constrain(in["maxma"].as<int>(), 100, (int)MAX_MA_LIMIT);
  if (in["seq"].is<JsonObjectConst>()) {
    JsonObjectConst s = in["seq"];
    if (s["sec"].is<int>()) st.seqSec = constrain(s["sec"].as<int>(), 2, 3600);
    if (s["mask"].is<int>()) st.seqMask = s["mask"].as<int>() & 0xFF;
    if (s["on"].is<bool>()) {
      st.seqOn = s["on"];
      seqIdx = -1;   // start from the first selected preset now
      if (st.seqOn) st.autoOn = false;
    }
  }
  if (in["auto"].is<JsonObjectConst>()) {
    JsonObjectConst a = in["auto"];
    if (a["sec"].is<int>()) st.autoSec = constrain(a["sec"].as<int>(), 2, 3600);
    if (a["mask"].is<int>()) st.autoMask = a["mask"].as<int>() & ((1u << NUM_EFFECTS) - 1);
    if (a["on"].is<bool>()) {
      st.autoOn = a["on"];
      autoIdx = -1;   // switch to the first selected effect now
      if (st.autoOn) st.seqOn = false;
    }
  }
  if (effectChanged && in["seq"].isNull() && in["auto"].isNull()) {
    // Picking an effect or colour by hand ends whichever cycle was running.
    st.seqOn = false;
    st.autoOn = false;
  }
  if (in["preset"].is<JsonObjectConst>()) {
    JsonObjectConst p = in["preset"];
    int slot = p["slot"] | -1;
    if (slot < 0 || slot >= LED_PRESETS) return "preset slot must be 0-7";
    String act = p["action"] | "";
    if (act == "save") {
      Preset &pr = presets[slot];
      String name = p["name"] | "";
      name.trim();
      if (!name.length()) name = String(EFFECTS[st.mode]);
      strlcpy(pr.name, name.c_str(), sizeof pr.name);
      pr.used = 1; pr.mode = st.mode; pr.bri = st.bri; pr.speed = st.speed; pr.c1 = st.c1; pr.c2 = st.c2;
    } else if (act == "load") {
      if (!presets[slot].used) return "preset slot is empty";
      st.seqOn = false;
      st.autoOn = false;
      loadPreset(slot);
    } else if (act == "delete") {
      presets[slot].used = 0;
      st.seqMask &= ~(1 << slot);
    } else {
      return "preset action must be save, load or delete";
    }
  }
  applyOutputLevel();
  markDirty();
  return "";
}

void ledsFrameJson(JsonDocument &doc) {
  static const char hx[] = "0123456789abcdef";
  JsonArray outs = doc["px"].to<JsonArray>();
  for (uint8_t o = 0; o < LED_OUTPUTS; o++) {
    uint16_t n = st.count[o];
    String s;
    s.reserve(n * 6);
    for (uint16_t i = 0; i < n; i++) {
      // What the strip is told, before brightness and the power limit: the
      // preview is for seeing the pattern, so it is shown at full colour.
      CRGB c = st.on ? buf[o][i] : CRGB::Black;
      for (uint8_t v : {c.r, c.g, c.b}) { s += hx[v >> 4]; s += hx[v & 15]; }
    }
    outs.add(s);
  }
}

// ---------------------------------------------------------------- console

static void printState(Print &out) {
  bool limited;
  uint32_t ma = estimateMa(limited);
  out.printf("led %s  effect %s  bri %u  speed %u  c1 %s  c2 %s\n", st.on ? "on" : "off", EFFECTS[st.mode],
             st.bri, st.speed, hexColor(st.c1).c_str(), hexColor(st.c2).c_str());
  out.printf("    counts OUT1 %u  OUT2 %u  OUT3 %u  OUT4 %u   limit %u mA  est %lu mA%s\n", st.count[0],
             st.count[1], st.count[2], st.count[3], st.maxMa, (unsigned long)ma,
             limited ? " (power-limited)" : "");
  if (st.seqOn) out.printf("    sequence on, every %u s, slots mask 0x%02X\n", st.seqSec, st.seqMask);
  if (st.autoOn) out.printf("    auto cycle on, every %u s, effects mask 0x%03X\n", st.autoSec, st.autoMask);
}

void ledsCommand(const String &args, Print &out) {
  String a = args;
  a.trim();
  int sp = a.indexOf(' ');
  String sub = sp < 0 ? a : a.substring(0, sp);
  String rest = sp < 0 ? "" : a.substring(sp + 1);
  rest.trim();
  sub.toLowerCase();

  JsonDocument d;
  if (sub == "" || sub == "status") { printState(out); return; }
  else if (sub == "on" || sub == "off") d["on"] = (sub == "on");
  else if (sub == "bri") d["bri"] = rest.toInt();
  else if (sub == "speed") d["speed"] = rest.toInt();
  else if (sub == "mode" || sub == "effect") d["mode"] = rest;
  else if (sub == "c1" || sub == "color" || sub == "colour") d["c1"] = rest;
  else if (sub == "c2") d["c2"] = rest;
  else if (sub == "maxma") d["maxma"] = rest.toInt();
  else if (sub == "count") {
    // "count 60" sets all four; "count 2 144" sets OUT2 only
    int sp2 = rest.indexOf(' ');
    JsonArray c = d["count"].to<JsonArray>();
    for (uint8_t o = 0; o < LED_OUTPUTS; o++) c.add(st.count[o]);
    if (sp2 < 0) {
      for (uint8_t o = 0; o < LED_OUTPUTS; o++) c[o] = rest.toInt();
    } else {
      int o = rest.substring(0, sp2).toInt();
      if (o < 1 || o > 4) { out.println("output must be 1-4"); return; }
      c[o - 1] = rest.substring(sp2 + 1).toInt();
    }
  } else if (sub == "list") {
    out.print("effects:");
    for (uint8_t i = 0; i < NUM_EFFECTS; i++) out.printf(" %s", EFFECTS[i]);
    out.println();
    return;
  } else if (sub == "seq") {
    JsonObject s = d["seq"].to<JsonObject>();
    if (rest.startsWith("on")) {
      s["on"] = true;
      int sec = rest.substring(2).toInt();
      if (sec > 0) s["sec"] = sec;
      if (!st.seqMask) {   // nothing chosen yet: visit every saved preset
        uint8_t m = 0;
        for (uint8_t i = 0; i < LED_PRESETS; i++) if (presets[i].used) m |= 1 << i;
        s["mask"] = m;
      }
    } else s["on"] = false;
  } else if (sub == "auto") {
    JsonObject s = d["auto"].to<JsonObject>();
    s["on"] = rest.startsWith("on");
    int sec = rest.substring(2).toInt();
    if (s["on"] && sec > 0) s["sec"] = sec;
  } else if (sub == "preset") {
    // preset save <1-8> [name] | load <1-8> | del <1-8>
    int sp2 = rest.indexOf(' ');
    String act = sp2 < 0 ? rest : rest.substring(0, sp2);
    String tail = sp2 < 0 ? "" : rest.substring(sp2 + 1);
    int sp3 = tail.indexOf(' ');
    JsonObject p = d["preset"].to<JsonObject>();
    p["action"] = act == "del" ? "delete" : act;
    p["slot"] = (sp3 < 0 ? tail : tail.substring(0, sp3)).toInt() - 1;
    if (sp3 >= 0) p["name"] = tail.substring(sp3 + 1);
  } else {
    out.println("led [status] | on | off | bri 0-255 | speed 0-255 | mode <name> | list\n"
                "    color <#rrggbb|name> | c2 <colour> | count [1-4] <n> | maxma <mA>\n"
                "    preset save|load|del <1-8> [name] | seq on [seconds] | seq off\n"
                "    auto on [seconds] | auto off   (cycle effects with new colours)");
    return;
  }
  String err = ledsApplyJson(d.as<JsonVariantConst>());
  if (err.length()) out.printf("error: %s\n", err.c_str());
  else printState(out);
}
