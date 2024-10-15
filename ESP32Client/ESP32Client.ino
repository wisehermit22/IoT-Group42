#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <ezButton.h>
 
// WiFi credentials
const char* ssid = "Yeah";
const char* password = "Password";
 
// WebSocket server details
const char* websocket_server = "192.168.110.1";
const int websocket_port = 8765;
 
#define RELAY_PIN 26
#define REED_SWITCH_PIN 17
#define INITIAL_DRINK_LIMIT 2
#define INITIAL_CYCLE_DURATION 30000 // 30 seconds in milliseconds
#define PENALTY_DURATION 10000
 
int drinkCount = 0;
int totalAddCount = 0;
 
int totalAddCount2 = 0;
 
int totalRemCount = 0;
 
int totalRemCount2 = 0;
 
bool lockState = false;
bool lidClosed = false;
 
int drinkLimit = INITIAL_DRINK_LIMIT;
unsigned long cycleDuration = INITIAL_CYCLE_DURATION;
unsigned long cycleStartTime = 0;
unsigned long lockDuration = INITIAL_CYCLE_DURATION;
unsigned long lastUpdateTime = 0;
const unsigned long UPDATE_INTERVAL = 1000; // Send updates every 1 second
 
ezButton limitSwitch1(18);
ezButton limitSwitch2(23);
ezButton limitSwitch3(19);
ezButton limitSwitch4(22);
ezButton reedSwitch(REED_SWITCH_PIN);
 
WebSocketsClient webSocket;
 
void setup() {
  Serial.begin(115200);
 
  // Connect to WiFi
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.println("Connecting to WiFi...");
  }
  Serial.println("Connected to WiFi");
 
  // Initialize WebSocket connection
  webSocket.begin(websocket_server, websocket_port, "/");
  webSocket.onEvent(webSocketEvent);
  webSocket.setReconnectInterval(5000);
 
  pinMode(RELAY_PIN, OUTPUT);
  pinMode(REED_SWITCH_PIN, INPUT_PULLUP);
  digitalWrite(RELAY_PIN, LOW);
 
  limitSwitch1.setDebounceTime(50);
  limitSwitch2.setDebounceTime(50);
  limitSwitch3.setDebounceTime(50);
  limitSwitch4.setDebounceTime(50);
  reedSwitch.setDebounceTime(50);
 
  Serial.println("Solenoid Lock Control");
  Serial.println("Initial status: Unlocked");
  Serial.println("Initial drink limit per cycle: " + String(drinkLimit));
  Serial.println("Initial cycle duration: " + String(cycleDuration / 1000) + " seconds");
  cycleStartTime = millis();
}
 
void loop() {
  webSocket.loop();
 
  limitSwitch1.loop();
  limitSwitch2.loop();
  limitSwitch3.loop();
  limitSwitch4.loop();
  reedSwitch.loop();
 
  checkLidStatus();
 
  int oldCount = drinkCount;
  int consumed = 0;
  consumed += handleSwitch(limitSwitch1, "1");
  consumed += handleSwitch(limitSwitch2, "2");
  consumed += handleSwitch(limitSwitch3, "3");
  consumed += handleSwitch(limitSwitch4, "4");
 
 
  drinkCount = totalAddCount2 - totalRemCount2;
 
  if (consumed != 0) {
    drinkCount += consumed;
    totalRemCount += consumed;
 
    totalRemCount2 += consumed;
    Serial.println("Current drinks: " + String(totalAddCount2 - totalRemCount2));
    Serial.println("Total drinks inserted: " + String(totalAddCount));
    Serial.println("Total drinks consumed: " + String(totalRemCount));
 
    if (totalRemCount >= drinkLimit && lidClosed && !lockState) {
      lockDoor();
      Serial.println("Drink limit reached and lid closed. Container locked.");
    }
 
    if (totalRemCount > drinkLimit) {
      lockDuration += PENALTY_DURATION;
      Serial.println("Penalty applied. Lock duration extended to " + String(lockDuration / 1000) + " seconds.");
    }
  }
 
  if (millis() - cycleStartTime >= lockDuration) {
    startNewCycle();
  }
 
  // Send updates to server
  if (millis() - lastUpdateTime >= UPDATE_INTERVAL) {
    sendStatusUpdate();
    lastUpdateTime = millis();
  }
}
 
void webSocketEvent(WStype_t type, uint8_t * payload, size_t length) {
  switch(type) {
    case WStype_DISCONNECTED:
      Serial.println("[WebSocket] Disconnected!");
      break;
    case WStype_CONNECTED:
      Serial.println("[WebSocket] Connected!");
      // Add this line to request initial status from server
      webSocket.sendTXT("{\"action\":\"get_initial_status\"}");
      break;
    case WStype_TEXT:
      handleWebSocketMessage(payload, length);
      break;
  }
}
 
void handleWebSocketMessage(uint8_t * payload, size_t length) {
  DynamicJsonDocument doc(1024);
  DeserializationError error = deserializeJson(doc, payload, length);
 
  if (error) {
    Serial.print(F("deserializeJson() failed: "));
    Serial.println(error.f_str());
    return;
  }
 

  if (doc.containsKey("action")) {
    String action = doc["action"];
    if (action == "reset") {
      startNewCycle();
    } else if (action == "unlock") {
      unlockDoor();
    } else if (action == "lock") {
      lockDoor();
    } else if (action == "update_settings") {
      if (doc.containsKey("drink_limit") && doc.containsKey("cycle_duration")) {
        drinkLimit = doc["drink_limit"].as<int>();
        cycleDuration = doc["cycle_duration"].as<long>() * 1000; // Convert seconds to milliseconds
        Serial.println("Updated settings - Drink limit: " + String(drinkLimit) + ", Cycle duration: " + String(cycleDuration / 1000) + " seconds");
      }
    } else if (action == "initial_status") {
      // Handle initial status from server
      if (doc.containsKey("consumption_count") && doc.containsKey("lock_status")) {
        totalRemCount = doc["consumption_count"].as<int>();
        lockState = doc["lock_status"].as<bool>();
        // Update other relevant variables as needed
        Serial.println("Received initial status from server");
      }
    }
  }
}
 
 
void sendStatusUpdate() {
  DynamicJsonDocument doc(1024);
  doc["totalAddCount"] = totalAddCount;
  doc["totalRemCount"] = totalRemCount;
  doc["drinkCount"] = totalAddCount2 - totalRemCount2;
  doc["lockState"] = lockState;
  doc["lidClosed"] = lidClosed;
 
  String output;
  serializeJson(doc, output);
  webSocket.sendTXT(output);
}
 
int handleSwitch(ezButton &limitSwitch, String label) {
  if (limitSwitch.isPressed()) {
    Serial.println("A drink in slot " + label + " was added.");
    totalAddCount += 1;
 
    totalAddCount2 += 1;
    return 0;
  }
  if (limitSwitch.isReleased()) {
    Serial.println("A drink in slot " + label + " was removed.");
    return 1;
  }
  return 0;
}
 
void checkLidStatus() {
  bool newLidStatus = (reedSwitch.getState() == LOW);
  if (newLidStatus != lidClosed) {
    lidClosed = newLidStatus;
    Serial.println(lidClosed ? "Lid closed" : "Lid opened");
    if (totalRemCount >= drinkLimit && lidClosed && !lockState) {
      lockDoor();
      Serial.println("Drink limit reached and lid closed. Container locked.");
    }
  }
}
 
void lockDoor() {
  digitalWrite(RELAY_PIN, HIGH);
  delay(100);
  Serial.println("Door locked");
  lockState = true;
}
 
void unlockDoor() {
  digitalWrite(RELAY_PIN, LOW);
  delay(100);
  Serial.println("Door unlocked");
  lockState = false;
}
 
void startNewCycle() {
  cycleStartTime = millis();
  totalRemCount = 0;
  totalAddCount = 0; // Reset this as well
  drinkCount = 0; // Reset this as well
  lockDuration = cycleDuration;
  if (lockState) {
    unlockDoor();
  }
  Serial.println("New cycle started. All counters reset.");
}