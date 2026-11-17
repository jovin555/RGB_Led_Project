// ESP32-S3 LED controller (rev 0.2): Wi-Fi, web UI, console and the WS2812B driver.
//
// leds.cpp drives OUT1-OUT4; ui_page.h is the single web page. This file is the
// Wi-Fi connection, the shared console, and the HTTP routes.
//
// Credentials never live in the source. They are entered once, either over the
// USB serial console or from a setup page the board serves on its own access
// point, and kept in NVS flash so they survive reboots and re-flashing of the
// app partition.
//
// Behaviour:
//   * Saved credentials  -> join that network as station "ledctrl".
//   * No credentials, or the join has not succeeded within CONNECT_TIMEOUT_MS
//     -> also open the setup access point LEDCTRL-XXXX (station keeps retrying
//     in the background, so a router that was merely slow to boot still wins).
//   * Once connected the setup AP is closed, mDNS answers at ledctrl.local and
//     a status page is served on port 80. Drops are reconnected automatically.

#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <ESPmDNS.h>
#include <Preferences.h>
#include <ArduinoJson.h>
#include "leds.h"
#include "ui_page.h"

static const char *HOSTNAME = "ledctrl";
static const char *AP_PASS = "ledsetup";              // WPA2 needs >= 8 chars
static const uint32_t CONNECT_TIMEOUT_MS = 20000;      // before the setup AP opens
static const uint32_t STATUS_PERIOD_MS = 30000;        // periodic status line

Preferences prefs;
WebServer server(80);
DNSServer dns;

String ssid, pass;          // saved credentials
String apName;
bool apUp = false;
bool mdnsUp = false;
volatile bool gotIp = false;
volatile bool lostIp = false;
uint32_t connectStartMs = 0;
uint32_t lastStatusMs = 0;

// ---------------------------------------------------------------- console
//
// Everything the firmware says goes through `con`, not Serial, so the web
// console sees the same log as the USB monitor. A command run from the web
// also captures its own output so the HTTP reply carries just that.
class Console : public Print {
 public:
  static const size_t LOG_MAX = 6144;
  String log;            // tail of everything printed
  uint32_t seq = 0;      // total bytes ever printed; log ends at seq
  String *capture = nullptr;
  size_t write(uint8_t c) override {
    Serial.write(c);
    if (log.length() >= LOG_MAX) log.remove(0, LOG_MAX / 4);
    log += (char)c;
    seq++;
    if (capture && capture->length() < 8192) *capture += (char)c;
    return 1;
  }
  size_t write(const uint8_t *b, size_t n) override {
    for (size_t i = 0; i < n; i++) write(b[i]);
    return n;
  }
};
Console con;

// ---------------------------------------------------------------- helpers

static String htmlEscape(const String &s) {
  String o;
  o.reserve(s.length());
  for (char c : s) {
    switch (c) {
      case '&': o += "&amp;"; break;
      case '<': o += "&lt;"; break;
      case '>': o += "&gt;"; break;
      case '"': o += "&quot;"; break;
      case '\'': o += "&#39;"; break;
      default: o += c;
    }
  }
  return o;
}

static const char *statusName(wl_status_t s) {
  switch (s) {
    case WL_IDLE_STATUS: return "idle";
    case WL_NO_SSID_AVAIL: return "network not found";
    case WL_CONNECTED: return "connected";
    case WL_CONNECT_FAILED: return "connect failed (wrong password?)";
    case WL_CONNECTION_LOST: return "connection lost";
    case WL_DISCONNECTED: return "disconnected";
    default: return "unknown";
  }
}

static void printStatus() {
  if (WiFi.status() == WL_CONNECTED) {
    con.printf("[wifi] connected to \"%s\"  ip %s  gw %s  rssi %d dBm  ch %d  http://%s.local\n",
                  WiFi.SSID().c_str(), WiFi.localIP().toString().c_str(),
                  WiFi.gatewayIP().toString().c_str(), WiFi.RSSI(), WiFi.channel(), HOSTNAME);
  } else {
    con.printf("[wifi] %s  (saved ssid: %s)\n", statusName(WiFi.status()),
                  ssid.length() ? ("\"" + ssid + "\"").c_str() : "none");
  }
  if (apUp)
    con.printf("[wifi] setup AP \"%s\" (password %s) -> http://%s\n", apName.c_str(), AP_PASS,
                  WiFi.softAPIP().toString().c_str());
}

// ---------------------------------------------------------------- wifi control

static void startAp() {
  if (apUp) return;
  WiFi.mode(WIFI_AP_STA);
  WiFi.softAP(apName.c_str(), AP_PASS);
  dns.start(53, "*", WiFi.softAPIP());   // captive portal: every name -> setup page
  apUp = true;
  con.printf("[wifi] setup AP \"%s\" up (password %s), browse to http://%s\n", apName.c_str(),
                AP_PASS, WiFi.softAPIP().toString().c_str());
}

static void stopAp() {
  if (!apUp) return;
  dns.stop();
  WiFi.softAPdisconnect(true);
  WiFi.mode(WIFI_STA);
  apUp = false;
  con.println("[wifi] setup AP closed");
}

static void connectSta() {
  if (!ssid.length()) {
    con.println("[wifi] no saved network - use the setup AP or the 'ssid'/'pass'/'connect' commands");
    startAp();
    return;
  }
  con.printf("[wifi] connecting to \"%s\" ...\n", ssid.c_str());
  WiFi.disconnect(false, false);
  WiFi.begin(ssid.c_str(), pass.c_str());
  connectStartMs = millis();
}

static void saveCredentials(const String &s, const String &p) {
  ssid = s;
  pass = p;
  prefs.putString("ssid", ssid);
  prefs.putString("pass", pass);
  con.printf("[wifi] saved network \"%s\"\n", ssid.c_str());
}

static void onWifiEvent(WiFiEvent_t event, WiFiEventInfo_t info) {
  // Runs on the Wi-Fi task: only set flags here, act on them in loop().
  switch (event) {
    case ARDUINO_EVENT_WIFI_STA_GOT_IP: gotIp = true; break;
    case ARDUINO_EVENT_WIFI_STA_DISCONNECTED:
      lostIp = true;
      break;
    default: break;
  }
}

// ---------------------------------------------------------------- web pages

static const char PAGE_HEAD[] PROGMEM =
    "<!doctype html><html><head><meta charset=utf-8>"
    "<meta name=viewport content='width=device-width,initial-scale=1'>"
    "<title>LED controller Wi-Fi</title><style>"
    "body{font-family:system-ui,sans-serif;max-width:28rem;margin:1.5rem auto;padding:0 1rem}"
    "input,select,button{font-size:1rem;width:100%;padding:.5rem;margin:.25rem 0 .75rem;box-sizing:border-box}"
    "td{padding:.15rem .5rem .15rem 0}</style></head><body><h2>LED controller Wi-Fi</h2>";

static void handleWifi() {
  String h = FPSTR(PAGE_HEAD);
  h += "<table>";
  h += "<tr><td>Status</td><td>" + String(statusName(WiFi.status())) + "</td></tr>";
  if (WiFi.status() == WL_CONNECTED) {
    h += "<tr><td>Network</td><td>" + htmlEscape(WiFi.SSID()) + "</td></tr>";
    h += "<tr><td>IP</td><td>" + WiFi.localIP().toString() + "</td></tr>";
    h += "<tr><td>Signal</td><td>" + String(WiFi.RSSI()) + " dBm</td></tr>";
  }
  h += "<tr><td>MAC</td><td>" + WiFi.macAddress() + "</td></tr>";
  h += "<tr><td>Uptime</td><td>" + String(millis() / 1000) + " s</td></tr></table>";

  h += "<h3>Join a network</h3><form method=post action=/save>";
  int n = WiFi.scanComplete();
  if (n > 0) {
    h += "<select onchange=\"document.getElementById('s').value=this.value\">"
         "<option value=''>-- networks found --</option>";
    for (int i = 0; i < n; i++) {
      String e = htmlEscape(WiFi.SSID(i));
      h += "<option value=\"" + e + "\">" + e + " (" + String(WiFi.RSSI(i)) + " dBm)</option>";
    }
    h += "</select>";
  }
  if (n == WIFI_SCAN_FAILED || n == 0) WiFi.scanNetworks(true);   // refresh for next load
  h += "<input id=s name=ssid placeholder='Network name (SSID)' value=\"" + htmlEscape(ssid) + "\" required>"
       "<input name=pass type=password placeholder='Password (blank if open)'>"
       "<button>Save and connect</button></form>"
       "<p><a href=/wifi>Refresh</a> &middot; <a href=/scan>Rescan</a> &middot; <a href=/>LED controller</a></p></body></html>";
  server.send(200, "text/html", h);
}

static void handleScan() {
  WiFi.scanDelete();
  WiFi.scanNetworks(true);
  server.sendHeader("Location", "/wifi");
  server.send(303);
}

static void handleSave() {
  String s = server.arg("ssid");
  s.trim();
  if (!s.length() || s.length() > 32 || server.arg("pass").length() > 63) {
    server.send(400, "text/plain", "SSID must be 1-32 characters and the password at most 63.");
    return;
  }
  saveCredentials(s, server.arg("pass"));
  String h = FPSTR(PAGE_HEAD);
  h += "<p>Saved. Connecting to <b>" + htmlEscape(s) + "</b>.</p>"
       "<p>When it succeeds this setup network closes. Rejoin your normal Wi-Fi and open "
       "<a href='http://" + String(HOSTNAME) + ".local'>http://" + HOSTNAME + ".local</a> "
       "(or the IP shown on the serial console).</p></body></html>";
  server.send(200, "text/html", h);
  delay(500);   // let the response leave before the radio retunes
  connectSta();
}

static void handleNotFound() {
  // In setup-AP mode, captive-portal probes from phones land here; send them to
  // the Wi-Fi form. On the home network an unknown path is just a 404.
  if (apUp && server.client().localIP() == WiFi.softAPIP()) {
    server.sendHeader("Location", String("http://") + WiFi.softAPIP().toString() + "/wifi");
    server.send(302);
  } else {
    server.send(404, "text/plain", "not found");
  }
}

// ---------------------------------------------------------------- web console
//
// "/" is the one page: LED controls and preview, live status, the shared log,
// and a command box that runs the same commands as the USB serial console.
// Plain HTTP on the LAN with no login - anyone on the same network can use it,
// same as the serial port to anyone holding the cable.

static void runCommand(const String &line, const char *src);
static bool rebootPending = false;

static void handleUi() { server.send_P(200, "text/html", UI_PAGE); }

// ---------------------------------------------------------------- LED API

static void sendJson(int code, JsonDocument &d) {
  String out;
  serializeJson(d, out);
  server.sendHeader("Cache-Control", "no-store");
  server.send(code, "application/json", out);
}

static void handleLedGet() {
  JsonDocument d;
  ledsStateJson(d);
  sendJson(200, d);
}

static void handleLedPost() {
  JsonDocument in;
  DeserializationError e = deserializeJson(in, server.arg("plain"));
  JsonDocument d;
  if (e) {
    d["error"] = String("bad JSON: ") + e.c_str();
    sendJson(400, d);
    return;
  }
  String err = ledsApplyJson(in.as<JsonVariantConst>());
  if (err.length()) {
    d["error"] = err;
    sendJson(400, d);
    return;
  }
  ledsStateJson(d);
  sendJson(200, d);
}

static void handleFrame() {
  JsonDocument d;
  ledsFrameJson(d);
  sendJson(200, d);
}

static void handleApiStatus() {
  bool up = WiFi.status() == WL_CONNECTED;
  String j = "{\"connected\":" + String(up ? "true" : "false");
  j += ",\"status\":\"" + String(statusName(WiFi.status())) + "\"";
  if (up) {
    String e = WiFi.SSID();
    e.replace("\\", "\\\\");
    e.replace("\"", "\\\"");
    j += ",\"ssid\":\"" + e + "\",\"ip\":\"" + WiFi.localIP().toString() + "\",\"rssi\":" + String(WiFi.RSSI());
  }
  j += ",\"ap\":" + String(apUp ? "true" : "false");
  j += ",\"mac\":\"" + WiFi.macAddress() + "\"";
  j += ",\"uptime_s\":" + String(millis() / 1000);
  j += ",\"heap\":" + String(ESP.getFreeHeap());
  j += ",\"temp_c\":" + String(temperatureRead(), 1) + "}";
  server.send(200, "application/json", j);
}

static void handleApiLog() {
  // Returns log text after byte offset ?since= (everything still buffered if
  // the client fell behind), and the new offset in the X-Seq header.
  uint32_t since = server.arg("since").toInt();
  uint32_t start = con.seq - con.log.length();
  if (since < start || since > con.seq) since = start;
  server.sendHeader("X-Seq", String(con.seq));
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "text/plain", con.log.substring(since - start));
}

// The command body is read raw rather than through server.arg(): `curl --data
// 'status'` sends x-www-form-urlencoded, and the WebServer's form parser silently
// drops any field without an '=', so a bare command would never arrive. The raw
// hook sees every non-multipart body before that parser runs.
static String cmdBody;

static void handleApiCmdRaw() {
  HTTPRaw &raw = server.raw();
  if (raw.status == RAW_START) cmdBody = "";
  else if (raw.status == RAW_WRITE && cmdBody.length() < 512) cmdBody.concat((const char *)raw.buf, raw.currentSize);
}

static String urlDecode(const String &s) {
  String o;
  for (size_t i = 0; i < s.length(); i++) {
    char c = s[i];
    if (c == '+') o += ' ';
    else if (c == '%' && i + 2 < s.length()) {
      o += (char)strtol(s.substring(i + 1, i + 3).c_str(), nullptr, 16);
      i += 2;
    } else o += c;
  }
  return o;
}

static void handleApiCmd() {
  // Accepted forms:
  //   text/plain body "status"             (the console page)
  //   form body "cmd=status"               (curl -d 'cmd=status', HTML forms)
  //   form body "status"                   (curl --data 'status')
  String line = cmdBody;
  cmdBody = "";
  if (server.header("Content-Type").startsWith("application/x-www-form-urlencoded")) {
    if (line.startsWith("cmd=")) line = line.substring(4);
    line = urlDecode(line);
  }
  line.trim();
  if (!line.length() || line.length() > 160) {
    server.send(400, "text/plain", "send one command line in the body");
    return;
  }
  String out;
  con.capture = &out;
  runCommand(line, "web");
  con.capture = nullptr;
  server.send(200, "text/plain", out);
}

// ---------------------------------------------------------------- serial console

static void printHelp() {
  con.println(
      "commands:\n"
      "  status          show connection state\n"
      "  scan            list nearby networks\n"
      "  ssid <name>     set network name (spaces allowed)\n"
      "  pass <password> set password (empty for an open network)\n"
      "  connect         save and connect with the ssid/pass above\n"
      "  forget          erase saved network\n"
      "  ap              open the setup access point\n"
      "  info            chip, memory and firmware details\n"
      "  echo <text>     print text back\n"
      "  led ...         LED control - type 'led help'\n"
      "  reboot");
}

static String pendingSsid, pendingPass;
static bool pendingPassSet = false;

static void handleCommand(String line) {
  line.trim();
  if (!line.length()) return;
  int sp = line.indexOf(' ');
  String cmd = sp < 0 ? line : line.substring(0, sp);
  String arg = sp < 0 ? "" : line.substring(sp + 1);
  cmd.toLowerCase();

  if (cmd == "help" || cmd == "?") printHelp();
  else if (cmd == "status") printStatus();
  else if (cmd == "scan") {
    con.println("[wifi] scanning...");
    int n = WiFi.scanNetworks();
    for (int i = 0; i < n; i++)
      con.printf("  %2d  %4d dBm  ch %2d  %s  %s\n", i + 1, WiFi.RSSI(i), WiFi.channel(i),
                    WiFi.encryptionType(i) == WIFI_AUTH_OPEN ? "open  " : "secure", WiFi.SSID(i).c_str());
    if (n <= 0) con.println("  no networks found");
  } else if (cmd == "ssid") {
    pendingSsid = arg;
    con.printf("ssid set to \"%s\" - now 'pass <password>' then 'connect'\n", arg.c_str());
  } else if (cmd == "pass") {
    pendingPass = arg;
    pendingPassSet = true;
    con.printf("password set (%u chars) - now 'connect'\n", (unsigned)arg.length());
  } else if (cmd == "connect") {
    if (pendingSsid.length()) {
      saveCredentials(pendingSsid, pendingPassSet ? pendingPass : String(""));
      pendingSsid = ""; pendingPass = ""; pendingPassSet = false;
    }
    connectSta();
  } else if (cmd == "forget") {
    prefs.clear();
    ssid = ""; pass = "";
    WiFi.disconnect(false, true);
    con.println("[wifi] saved network erased");
    startAp();
  } else if (cmd == "ap") startAp();
  else if (cmd == "info") {
    con.printf("chip %s rev %d, %d cores @ %lu MHz, flash %lu KB, psram %lu KB\n", ESP.getChipModel(),
               ESP.getChipRevision(), ESP.getChipCores(), (unsigned long)ESP.getCpuFreqMHz(),
               (unsigned long)(ESP.getFlashChipSize() / 1024), (unsigned long)(ESP.getPsramSize() / 1024));
    con.printf("heap free %lu / %lu bytes, chip temp %.1f C, uptime %lu s\n", (unsigned long)ESP.getFreeHeap(),
               (unsigned long)ESP.getHeapSize(), temperatureRead(), (unsigned long)(millis() / 1000));
    con.printf("firmware built %s %s, sdk %s, mac %s\n", __DATE__, __TIME__, ESP.getSdkVersion(),
               WiFi.macAddress().c_str());
  } else if (cmd == "echo") con.println(arg);
  else if (cmd == "led") ledsCommand(arg, con);
  else if (cmd == "reboot") {
    con.println("rebooting...");
    rebootPending = true;   // after the reply has been sent
  }
  else con.printf("unknown command '%s' - type 'help'\n", cmd.c_str());
}

static void runCommand(const String &line, const char *src) {
  // Echo into the shared log so both consoles see who did what; never echo a password.
  String shown = line;
  if (shown.startsWith("pass ") || shown.startsWith("PASS ")) shown = "pass ********";
  con.printf("%s> %s\n", src, shown.c_str());
  handleCommand(line);
}

static void pollSerial() {
  static String buf;
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r' || c == '\n') {
      if (buf.length()) runCommand(buf, "usb");
      buf = "";
    } else if (buf.length() < 128) {
      buf += c;
    }
  }
}

// ---------------------------------------------------------------- setup / loop

void setup() {
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);   // never stall the firmware when no USB host is reading
  uint32_t t0 = millis();
  while (!Serial && millis() - t0 < 2000) delay(10);
  con.println("\n=== ESP32-S3 LED controller ===  (type 'help')");

  prefs.begin("wifi", false);
  ssid = prefs.getString("ssid", "");
  pass = prefs.getString("pass", "");

  uint8_t mac[6];
  WiFi.macAddress(mac);
  char name[20];
  snprintf(name, sizeof name, "LEDCTRL-%02X%02X", mac[4], mac[5]);
  apName = name;

  WiFi.onEvent(onWifiEvent);
  WiFi.setHostname(HOSTNAME);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);   // NVS "wifi" namespace is ours; don't let the IDF keep a second copy

  server.on("/", handleUi);
  server.on("/api/led", HTTP_GET, handleLedGet);
  server.on("/api/led", HTTP_POST, handleLedPost);
  server.on("/api/frame", handleFrame);
  server.on("/wifi", handleWifi);
  server.on("/api/status", handleApiStatus);
  server.on("/api/log", handleApiLog);
  server.on("/api/cmd", HTTP_POST, handleApiCmd, handleApiCmdRaw);
  server.on("/scan", handleScan);
  server.on("/save", HTTP_POST, handleSave);
  server.onNotFound(handleNotFound);
  static const char *hdrs[] = {"Content-Type"};   // only collected headers are readable
  server.collectHeaders(hdrs, 1);
  server.begin();

  ledsBegin();
  connectSta();
}

void loop() {
  pollSerial();
  server.handleClient();
  if (rebootPending) { delay(300); ESP.restart(); }
  ledsLoop();
  if (apUp) dns.processNextRequest();

  if (gotIp) {
    gotIp = false;
    printStatus();
    if (!mdnsUp && MDNS.begin(HOSTNAME)) {
      MDNS.addService("http", "tcp", 80);
      mdnsUp = true;
    }
    stopAp();
  }

  if (lostIp) {
    lostIp = false;
    if (mdnsUp) { MDNS.end(); mdnsUp = false; }
    if (WiFi.status() != WL_CONNECTED && ssid.length() && connectStartMs == 0) {
      // A drop after a good connection: restart the timeout window for the AP fallback.
      con.printf("[wifi] disconnected (%s), reconnecting...\n", statusName(WiFi.status()));
      connectStartMs = millis();
    }
  }

  if (WiFi.status() == WL_CONNECTED) {
    connectStartMs = 0;
  } else if (connectStartMs && millis() - connectStartMs > CONNECT_TIMEOUT_MS) {
    con.printf("[wifi] could not join \"%s\" within %lus (%s)\n", ssid.c_str(),
                  (unsigned long)(CONNECT_TIMEOUT_MS / 1000), statusName(WiFi.status()));
    connectStartMs = 0;
    startAp();
    WiFi.begin(ssid.c_str(), pass.c_str());   // keep trying in the background
  }

  if (millis() - lastStatusMs > STATUS_PERIOD_MS) {
    lastStatusMs = millis();
    printStatus();
  }
}
