// Imports header files.
#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <ezButton.h>
 
// Initialises the WiFi details.
const char* ssid = "Yeah";
const char* password = "Password";
 
// Initialises the websocket details.
const char* websocket_server = "192.168.110.1";
const int websocket_port = 8765;
 
// Defines constants for execution.
#define RELAY_PIN 26
#define REED_SWITCH_PIN 17
#define INITIAL_DRINK_LIMIT 2 // Default drink limit. TODO
#define INITIAL_CYCLE_DURATION 30000 // 30 seconds
#define PENALTY_DURATION 10000 // 10 seconds
 
// Initialises several variables for execution.
int drinkCount = 0; // The current number of drinks in the container.

int totalAddCount = 0; // The total number of drinks added into the container, for one cycle. This is reset per cycle.
int totalAddCount2 = 0; // The total number of drinks added into the container, for all cycles.

int totalRemCount = 0; // The total number of drinks added into the container, for one cycle. This is reset per cycle.
int totalRemCount2 = 0; // The tota number of drinks added into the container, for all cycles.
 
bool lockState = false; // The current state of the lock - false is unlocked.
bool lidClosed = false; // The current state of the lid - false is open.

// Defines certain variables based off the constants. 
int drinkLimit = INITIAL_DRINK_LIMIT;
unsigned long cycleDuration = INITIAL_CYCLE_DURATION;
unsigned long cycleStartTime = 0;
unsigned long lockDuration = INITIAL_CYCLE_DURATION;
unsigned long lastUpdateTime = 0;
const unsigned long UPDATE_INTERVAL = 1000; // 1 second
 
// Initialises the four limit switches and the reed switch based on defined pin numbers.
ezButton limitSwitch1(18);
ezButton limitSwitch2(23);
ezButton limitSwitch3(19);
ezButton limitSwitch4(22);
ezButton reedSwitch(REED_SWITCH_PIN);
 
// Initialises the websocket client.
WebSocketsClient webSocket;

// Runs the setup function for the ESP32.
void setup() {
  // Begins serial output at 115200.
  Serial.begin(115200);
 
  // Connects to the WiFi details provided.
  WiFi.begin(ssid, password);
  Serial.println("** Connecting to WiFi **");
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.print(".");
  }
  Serial.println("** Connected to WiFi. **");
 
  // Initialises the websocket connection.
  webSocket.begin(websocket_server, websocket_port, "/");
  webSocket.onEvent(webSocketEvent);
  webSocket.setReconnectInterval(5000); // Reconnects if disconnected every 5 seconds.
 
  // Sets the default modes for several components.
  pinMode(RELAY_PIN, OUTPUT);
  pinMode(REED_SWITCH_PIN, INPUT_PULLUP);
  digitalWrite(RELAY_PIN, LOW);
 
  // Initialises the debounce time for the limit switches and the reed switch.
  limitSwitch1.setDebounceTime(50);
  limitSwitch2.setDebounceTime(50);
  limitSwitch3.setDebounceTime(50);
  limitSwitch4.setDebounceTime(50);
  reedSwitch.setDebounceTime(50);
 
  // Prints out the initial details before looping.
  Serial.println("Solenoid Lock Control");
  Serial.println("Initial status: Unlocked");
  Serial.println("Initial drink limit per cycle: " + String(drinkLimit));
  Serial.println("Initial cycle duration: " + String(cycleDuration / 1000) + " seconds");
  cycleStartTime = millis();
}
 
// Runs the loop function for the ESP32.
void loop() {
  // Loops for several components/functions.
  webSocket.loop();
  limitSwitch1.loop();
  limitSwitch2.loop();
  limitSwitch3.loop();
  limitSwitch4.loop();
  reedSwitch.loop();
 
  // Checks the status of the lid and updates it if required.
  checkLidStatus();
 
  // Stores the number of consumed drinks per cycle (number of removed drinks).
  // The variable totalAddCount(2) is updated in these functions when a drink is added.
  int consumed = 0;
  consumed += handleSwitch(limitSwitch1, "1");
  consumed += handleSwitch(limitSwitch2, "2");
  consumed += handleSwitch(limitSwitch3, "3");
  consumed += handleSwitch(limitSwitch4, "4");
 
  // If more than one drink has been removed in this loop, perform some prints, calculations and so on.
  if (consumed != 0) {
    // Increases the removed drink count by the number of removed in this loop.
    totalRemCount += consumed;
    totalRemCount2 += consumed;

    // Prints out the current drink values for this loop.
    Serial.println("Current drinks: " + String(totalAddCount2 - totalRemCount2));
    Serial.println("Total drinks inserted: " + String(totalAddCount));
    Serial.println("Total drinks consumed: " + String(totalRemCount));
 
    // If the total amount of removed drinks exceeds the limit (for this cycle) and the lid is closed, and the lock is unlocked, lock the lock. (commented out temporarily)
    // if (totalRemCount >= drinkLimit && lidClosed && !lockState) {
    //   lockDoor();
    //   Serial.println("Drink limit reached and lid closed. Container locked.");
    // }
 
    // If the total number of
    if (totalRemCount > drinkLimit) {
      lockDuration += PENALTY_DURATION;
      Serial.println("Penalty applied. Lock duration extended to " + String(lockDuration / 1000) + " seconds.");
    }
  }

    // Defines the drink count as the number of added drinks (in total) minus the number of removed drinks (in total). This is not affected by cycles.
  drinkCount = totalAddCount2 - totalRemCount2;
 
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
      break;
    case WStype_TEXT:
      handleWebSocketMessage(payload, length);
      break;
  }
}
 
// 
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
 
 
// Sends a status update to the websocket server, with specific variable details, in a JSON format.
void sendStatusUpdate() {
  // Stores the variables required into a JSON format.
  DynamicJsonDocument doc(1024);
  doc["totalAddCount"] = totalAddCount;
  doc["totalRemCount"] = totalRemCount;
  doc["drinkCount"] = totalAddCount2 - totalRemCount2;
  doc["lockState"] = lockState;
  doc["lidClosed"] = lidClosed;
 
  // Serialises the output as a JSON string.
  String output;
  serializeJson(doc, output);
  webSocket.sendTXT(output);
}
 
// TODO
int handleSwitch(ezButton &limitSwitch, String label) {
  if (limitSwitch.isPressed()) {

    totalAddCount += 1;
    totalAddCount2 += 1;
    
    // Prints..
    Serial.println("A drink in slot " + label + " was added.");
    return 0;
  }
  if (limitSwitch.isReleased()) {
    Serial.println("A drink in slot " + label + " was removed.");
    return 1;
  }
  return 0;
}
 
// Checks the status of the lid, if the reed
void checkLidStatus() {
  // If reed switch is closed, newLidStatus is set to True.
  bool newLidStatus = (reedSwitch.getState() == LOW);

  // If the lid status has changed, update it and print the new lid state.
  if (newLidStatus != lidClosed) {
    lidClosed = newLidStatus;
    Serial.println(lidClosed ? "Lid Status: Closed" : "Lid Status: Opened");
  }
}
 
// Locks the locking mechanism.
void lockDoor() {
  digitalWrite(RELAY_PIN, HIGH);
  delay(100);
  
  // Prints and updates the lock's status if required.
  if (lockState != true) {
    Serial.println("Lock Status: Locked");
  }
  lockState = true;
}
 
// Unlocks the locking mechanism.
void unlockDoor() {
  digitalWrite(RELAY_PIN, LOW);
  delay(100);

  // Prints and updates the lock's status if required.
  if (lockState != false) {
    Serial.println("Lock Status: Unlocked");
  }
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