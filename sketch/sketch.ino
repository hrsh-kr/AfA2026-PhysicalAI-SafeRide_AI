// SPDX-FileCopyrightText: SafeRide AI - Gig Worker Safety Platform
// SPDX-License-Identifier: MIT

#include <Arduino_Modulino.h>
#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>

// ======================
// HARDWARE CONFIGURATION
// ======================

ModulinoMovement movement;
ArduinoLEDMatrix matrix;

// Pin definitions
const int SOS_BUTTON_PIN = 2;      // SOS emergency button
const int LED_BUILTIN_PIN = LED_BUILTIN;

// Sensor reading configuration
const long SENSOR_INTERVAL = 100;  // Read every 100ms (10Hz)
unsigned long previousMillis = 0;

// Accelerometer values in g-units
float x_accel, y_accel, z_accel;

// Button state tracking
bool last_button_state = HIGH;
bool sos_active = false;

// Vehicle state
bool is_parked = false;
unsigned long last_movement_time = 0;
const unsigned long PARK_TIMEOUT = 30000;  // 30 seconds no movement = parked


// ======================
// LED MATRIX ANIMATIONS
// ======================

// Happy face (normal operation)
const uint32_t happy_face[] = {
  0x19819819,
  0x80000981,
  0x98190000
};

// Alert face (warning)
const uint32_t alert_face[] = {
  0x0c6319ce,
  0x73186318,
  0xc0000000
};

// SOS pattern (emergency)
const uint32_t sos_pattern[] = {
  0xffffffff,
  0xffffffff,
  0xffffffff
};

// Theft alarm pattern
const uint32_t theft_pattern[] = {
  0xaaaaaaaa,
  0x55555555,
  0xaaaaaaaa
};


// ======================
// SETUP
// ======================

void setup() {
  Serial.begin(115200);
  
  // Wait for serial (optional, for debugging)
  // while (!Serial) { delay(10); }
  
  Serial.println("===========================================");
  Serial.println("SafeRide AI - Real-Time Rider Safety");
  Serial.println("===========================================");
  
  // Initialize Bridge communication
  Bridge.begin();
  Serial.println("✓ Bridge initialized");
  
  // Initialize Modulino I2C
  Modulino.begin(Wire1);
  Serial.println("✓ Modulino I2C initialized");
  
  // Connect to Movement sensor
  Serial.print("Connecting to Movement sensor...");
  while (!movement.begin()) {
    Serial.print(".");
    delay(1000);
  }
  Serial.println(" ✓ Connected");
  
  // Initialize LED Matrix
  matrix.begin();
  matrix.loadFrame(happy_face);
  Serial.println("✓ LED Matrix initialized");
  
  // Setup SOS button
  pinMode(SOS_BUTTON_PIN, INPUT_PULLUP);
  pinMode(LED_BUILTIN_PIN, OUTPUT);
  Serial.println("✓ SOS button configured (Pin 2)");
  
  // Register RPC handlers (called from Python)
  Bridge.provide("emergency_crash_alert", emergency_crash_alert);
  Bridge.provide("theft_alarm", theft_alarm);
  Serial.println("✓ RPC handlers registered");
  
  Serial.println("===========================================");
  Serial.println("System Ready - Monitoring Started");
  Serial.println("===========================================\n");
  
  // Visual feedback: startup complete
  digitalWrite(LED_BUILTIN_PIN, HIGH);
  delay(500);
  digitalWrite(LED_BUILTIN_PIN, LOW);
}


// ======================
// MAIN LOOP
// ======================

void loop() {
  unsigned long currentMillis = millis();
  
  // Read sensors at regular interval
  if (currentMillis - previousMillis >= SENSOR_INTERVAL) {
    previousMillis = currentMillis;
    
    // Update movement sensor
    if (movement.update()) {
      // Read acceleration values (in g-units)
      x_accel = movement.getX();
      y_accel = movement.getY();
      z_accel = movement.getZ();
      
      // Send to Python processor for AI analysis
      Bridge.notify("record_sensor_movement", x_accel, y_accel, z_accel);
      
      // Check for movement (for parking detection)
      float total_accel = sqrt(x_accel*x_accel + y_accel*y_accel + z_accel*z_accel);
      
      if (total_accel > 0.5) {
        last_movement_time = currentMillis;
        if (is_parked) {
          is_parked = false;
          Serial.println("Vehicle status: DRIVING");
        }
      } else {
        // Check if should mark as parked
        if (!is_parked && (currentMillis - last_movement_time > PARK_TIMEOUT)) {
          is_parked = true;
          Serial.println("Vehicle status: PARKED - Theft detection ACTIVE");
          matrix.loadFrame(alert_face);
          delay(500);
          matrix.loadFrame(happy_face);
        }
      }
    }
  }
  
  // Check SOS button
  check_sos_button();
  
  // Small delay for stability
  delay(10);
}


// ======================
// SOS BUTTON HANDLER
// ======================

void check_sos_button() {
  bool current_state = digitalRead(SOS_BUTTON_PIN);
  
  // Detect button press (falling edge with debouncing)
  if (last_button_state == HIGH && current_state == LOW) {
    delay(50);  // Debounce delay
    current_state = digitalRead(SOS_BUTTON_PIN);
    
    if (current_state == LOW) {  // Still pressed after debounce
      Serial.println("\n🚨🚨🚨 SOS BUTTON PRESSED 🚨🚨🚨");
      trigger_sos_alert();
    }
  }
  
  last_button_state = current_state;
}


void trigger_sos_alert() {
  sos_active = true;
  
  // Visual alarm sequence
  for (int i = 0; i < 5; i++) {
    matrix.loadFrame(sos_pattern);
    digitalWrite(LED_BUILTIN_PIN, HIGH);
    delay(300);
    
    matrix.loadFrame(happy_face);
    digitalWrite(LED_BUILTIN_PIN, LOW);
    delay(200);
  }
  
  // Notify Python processor
  Bridge.call("trigger_sos");
  
  Serial.println("SOS alert sent to Python processor");
  Serial.println("Actions: Dashcam started, GPS logged, Emergency contacts alerted\n");
}


// ======================
// RPC HANDLERS (Called from Python)
// ======================

void emergency_crash_alert() {
  Serial.println("\n🚨 CRASH DETECTED BY AI - Emergency Response Activated");
  
  // Rapid flash pattern
  for (int i = 0; i < 10; i++) {
    matrix.loadFrame(alert_face);
    digitalWrite(LED_BUILTIN_PIN, HIGH);
    delay(100);
    
    digitalWrite(LED_BUILTIN_PIN, LOW);
    delay(100);
  }
  
  matrix.loadFrame(happy_face);
  Serial.println("Crash alert complete\n");
}


void theft_alarm() {
  Serial.println("\n🚨 THEFT ALERT - Vehicle Moving While Parked!");
  
  // Continuous alarm pattern
  for (int i = 0; i < 20; i++) {
    matrix.loadFrame(theft_pattern);
    digitalWrite(LED_BUILTIN_PIN, HIGH);
    delay(200);
    
    digitalWrite(LED_BUILTIN_PIN, LOW);
    delay(100);
  }
  
  matrix.loadFrame(happy_face);
  Serial.println("Theft alarm complete\n");
}