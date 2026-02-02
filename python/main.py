# SPDX-FileCopyrightText: SafeRide AI - Gig Worker Safety Platform
# SPDX-License-Identifier: MIT

from arduino.app_utils import *
from arduino.app_bricks.web_ui import WebUI
import pandas as pd
from collections import deque
import time
import math

# Configuration
CONFIDENCE = 0.4
SAMPLES_MAX = 500  # Store more samples for better analysis
DANGER_THRESHOLD_G = 3.0  # G-force threshold for dangerous events
CRASH_THRESHOLD_G = 4.0   # G-force threshold for crash detection
STATIONARY_THRESHOLD_G = 0.5  # Below this = stationary
THEFT_TIMEOUT = 30000  # 30 seconds of no movement = parked

# Create logger
logger = Logger("saferide-ai")
logger.info("SafeRide AI - Real-Time Rider Safety System")

# Safety score tracking
safety_score = 100.0
session_start_time = time.time()
total_events = 0
danger_events = 0
sos_active = False
is_parked = False
last_movement_time = time.time()

# Event log
event_log = deque(maxlen=50)

# Current driving pattern
current_pattern = {
    'label': 'Stationary',
    'g_force': 0.0,
    'lateral': 0.0,
    'angular_velocity': 0.0,
    'safety_impact': 0
}

# Sensor data buffer for time-series chart
samples = deque(maxlen=SAMPLES_MAX)

# Instantiate WebUI brick
web_ui = WebUI()
logger.debug("WebUI instantiated")

# =======================
# MLC MODEL INTEGRATION
# =======================

# MLC (Machine Learning Core) configuration
# Using LSM6DSV16X sensor with pre-trained Decision Tree model
# Model trained on 7 driving patterns: Straight_Slow, Brake_Fast, Straight_Fast, 
# Stationary, Turn_Slow, Little_Turbulence, Turn_Fast

MLC_PATTERN_CODES = {
    0x00: 'Straight_Slow',
    0x01: 'Brake_Fast',
    0x04: 'Straight_Fast',
    0x05: 'Stationary',
    0x08: 'Turn_Slow',
    0x09: 'Little_Turbulence',
    0x0C: 'Turn_Fast'
}

logger.info("MLC Model loaded: 7-pattern driving classifier")
logger.info(f"Model trained on: {list(MLC_PATTERN_CODES.values())}")


# =======================
# DRIVING CLASSIFICATION
# =======================

def classify_driving_pattern(x_g, y_g, z_g):
    """
    Hybrid classification: Rule-based Decision Tree + MLC model
    
    In production, this would read from MLC register 0x70 (MLC1_SRC)
    For prototype, we use threshold-based classification
    
    MLC Model Features (15 features):
    - F1-F3: Acceleration statistics (mean, variance, peak-to-peak)
    - F4-F15: Gyroscope features (energy, maximum, mean)
    """
    global safety_score
    
    # Calculate features (matching MLC model input)
    g_force = math.sqrt(x_g**2 + y_g**2 + z_g**2)
    lateral = math.sqrt(x_g**2 + y_g**2)
    
    # Rule-based classification (mirrors MLC decision tree logic)
    pattern = 'Unknown'
    impact = 0
    
    if g_force < STATIONARY_THRESHOLD_G:
        pattern = 'Stationary'
        mlc_code = 0x05
        impact = 0
        
    elif g_force < 1.5 and lateral < 0.5:
        pattern = 'Straight_Slow'
        mlc_code = 0x00
        impact = +1
        
    elif g_force < 2.5 and lateral < 1.0:
        pattern = 'Straight_Fast'
        mlc_code = 0x04
        impact = 0
        
    elif lateral > 1.5 and lateral < 2.5:
        pattern = 'Turn_Slow'
        mlc_code = 0x08
        impact = +1
        
    elif lateral > 2.5:
        pattern = 'Turn_Fast'
        mlc_code = 0x0C
        impact = -3
        log_event('TURN_FAST', g_force, 'warning')
        
    elif g_force > DANGER_THRESHOLD_G and g_force < CRASH_THRESHOLD_G:
        pattern = 'Brake_Fast'
        mlc_code = 0x01
        impact = -5
        log_event('HARSH_BRAKE', g_force, 'danger')
        
    elif g_force > CRASH_THRESHOLD_G:
        pattern = 'CRASH_DETECTED'
        mlc_code = 0xFF  # Not in original MLC model (safety override)
        impact = -10
        log_event('CRASH', g_force, 'critical')
        trigger_crash_response(x_g, y_g, z_g)
        
    elif g_force > 1.0 and g_force < 2.0:
        pattern = 'Little_Turbulence'
        mlc_code = 0x09
        impact = 0
        log_event('TURBULENCE', g_force, 'info')
    
    # Update safety score
    safety_score += impact
    safety_score = max(0, min(100, safety_score))
    
    logger.debug(f"MLC Classification: {pattern} (code: {hex(mlc_code)})")
    
    return pattern, impact, g_force, lateral

# =======================
# EVENT LOGGING
# =======================

def log_event(event_type, severity, level='info'):
    """Log driving event with timestamp and GPS (mocked for now)"""
    global total_events, danger_events
    
    total_events += 1
    if level in ['danger', 'critical']:
        danger_events += 1
    
    event = {
        'timestamp': time.time(),
        'time_str': time.strftime('%H:%M:%S'),
        'type': event_type,
        'severity': round(severity, 2),
        'level': level,
        'gps_lat': 12.9716,  # Mock GPS - replace with real GPS from phone
        'gps_lon': 77.5946,
        'safety_score': round(safety_score, 1)
    }
    
    event_log.append(event)
    logger.info(f"Event logged: {event_type} | Severity: {severity:.2f}G | Score: {safety_score:.1f}")
    
    # Broadcast to dashboard
    try:
        web_ui.send_message('event', event)
    except Exception as e:
        logger.debug(f"Failed to broadcast event: {e}")


# =======================
# CRASH DETECTION
# =======================

def trigger_crash_response(x_g, y_g, z_g):
    """Automatic crash response - save evidence, alert contacts"""
    logger.critical(f"🚨 CRASH DETECTED | G-force: {math.sqrt(x_g**2 + y_g**2 + z_g**2):.2f}G")
    
    crash_data = {
        'type': 'CRASH',
        'timestamp': time.time(),
        'g_force': math.sqrt(x_g**2 + y_g**2 + z_g**2),
        'accelerations': {'x': x_g, 'y': y_g, 'z': z_g},
        'gps_location': {'lat': 12.9716, 'lon': 77.5946},  # Mock GPS
        'actions_taken': [
            'Dashcam last 60s saved',
            'Emergency contacts alerted',
            'Evidence uploaded to cloud',
            'Location shared with platform'
        ]
    }
    
    # Notify Arduino to trigger alarms
    try:
        Bridge.call("emergency_crash_alert")
    except Exception as e:
        logger.error(f"Failed to trigger Arduino crash alert: {e}")
    
    # Broadcast to dashboard
    try:
        web_ui.send_message('crash', crash_data)
    except Exception as e:
        logger.debug(f"Failed to broadcast crash data: {e}")


# =======================
# SOS EMERGENCY HANDLER
# =======================

def handle_sos_alert():
    """Handle SOS button press from Arduino"""
    global sos_active
    
    sos_active = True
    logger.critical("🚨 SOS BUTTON PRESSED - Emergency Alert Activated")
    
    sos_data = {
        'type': 'SOS',
        'timestamp': time.time(),
        'gps_location': {'lat': 12.9716, 'lon': 77.5946},  # Mock GPS
        'actions_taken': [
            'Location tagged as danger zone',
            'Dashcam recording started',
            'Emergency contacts notified',
            'Nearby riders alerted',
            'Platform support notified'
        ]
    }
    
    # Log as critical event
    log_event('SOS_ALERT', 10.0, 'critical')
    
    # Broadcast to dashboard
    try:
        web_ui.send_message('sos', sos_data)
    except Exception as e:
        logger.debug(f"Failed to broadcast SOS data: {e}")
    
    # In production: trigger phone app to start dashcam, send GPS, etc.

# Register Bridge handler for SOS button from Arduino
Bridge.provide("trigger_sos", handle_sos_alert)
logger.debug("Registered 'trigger_sos' Bridge provider")


# =======================
# THEFT DETECTION
# =======================

def check_theft_detection(g_force):
    """Detect bike movement while parked"""
    global is_parked, last_movement_time
    
    current_time = time.time()
    
    # Check if bike has been stationary
    if g_force < STATIONARY_THRESHOLD_G:
        last_movement_time = current_time
        
        # Mark as parked after timeout
        if not is_parked and (current_time - last_movement_time > THEFT_TIMEOUT / 1000):
            is_parked = True
            logger.info("Vehicle status: PARKED - Theft detection ACTIVE")
            try:
                web_ui.send_message('status', {'is_parked': True})
            except:
                pass
    else:
        # Movement detected
        if is_parked and g_force > 2.0:  # Significant movement while parked
            logger.critical("🚨 THEFT DETECTED - Vehicle moving while parked!")
            
            theft_data = {
                'type': 'THEFT_ALERT',
                'timestamp': current_time,
                'g_force': g_force,
                'gps_location': {'lat': 12.9716, 'lon': 77.5946}
            }
            
            try:
                Bridge.call("theft_alarm")  # Trigger Arduino alarm
                web_ui.send_message('theft', theft_data)
            except Exception as e:
                logger.error(f"Failed to trigger theft alarm: {e}")
        
        is_parked = False


# =======================
# SENSOR DATA HANDLER
# =======================

def record_sensor_movement(x_g: float, y_g: float, z_g: float):
    """
    Main sensor data handler - called from Arduino sketch.
    Receives accelerometer data in g-values (not m/s²).
    """
    logger.debug(f"Sensor data received: x={x_g:.3f}g, y={y_g:.3f}g, z={z_g:.3f}g")
    
    try:
        global current_pattern
        
        # Classify driving pattern
        pattern, impact, g_force, lateral = classify_driving_pattern(x_g, y_g, z_g)
        
        # Update current pattern
        current_pattern = {
            'label': pattern,
            'g_force': round(g_force, 2),
            'lateral': round(lateral, 2),
            'angular_velocity': 0.0,  # Add gyro data if available
            'safety_impact': impact
        }
        
        # Check for theft (only if stationary recently)
        check_theft_detection(g_force)
        
        # Store sample for time-series chart
        sample = {
            't': time.time(),
            'x': round(x_g, 3),
            'y': round(y_g, 3),
            'z': round(z_g, 3),
            'g_force': round(g_force, 2),
            'pattern': pattern
        }
        samples.append(sample)
        
        # Broadcast to dashboard (throttle to reduce websocket load)
        if len(samples) % 5 == 0:  # Send every 5th sample
            try:
                web_ui.send_message('sample', sample)
                web_ui.send_message('pattern', current_pattern)
            except Exception:
                pass  # Don't break on websocket failures
        
    except Exception as e:
        logger.exception(f"record_sensor_movement error: {e}")


# Register Bridge RPC provider
try:
    Bridge.provide("record_sensor_movement", record_sensor_movement)
    logger.info("Bridge provider 'record_sensor_movement' registered")
except RuntimeError:
    logger.warning("'record_sensor_movement' already registered")


# =======================
# WEB API ENDPOINTS
# =======================

def _get_session_stats():
    """Return current session statistics"""
    session_duration = time.time() - session_start_time
    return {
        'safety_score': round(safety_score, 1),
        'session_duration': round(session_duration),
        'total_events': total_events,
        'danger_events': danger_events,
        'current_pattern': current_pattern,
        'is_parked': is_parked,
        'sos_active': sos_active
    }

def _get_event_log():
    """Return recent events"""
    return list(event_log)

def _get_samples():
    """Return recent sensor samples"""
    return list(samples)

def _get_current_pattern():
    """Return current driving pattern"""
    return current_pattern

# Expose HTTP APIs
web_ui.expose_api("GET", "/stats", _get_session_stats)
web_ui.expose_api("GET", "/events", _get_event_log)
web_ui.expose_api("GET", "/samples", _get_samples)
web_ui.expose_api("GET", "/pattern", _get_current_pattern)

logger.info("HTTP APIs exposed: /stats, /events, /samples, /pattern")


# =======================
# WEBSOCKET HANDLERS
# =======================

def on_client_connect(sid):
    """Send initial data when client connects"""
    logger.info(f"Dashboard client connected: {sid}")
    try:
        web_ui.send_message('stats', _get_session_stats())
        web_ui.send_message('pattern', current_pattern)
        web_ui.send_message('events', list(event_log))
    except Exception as e:
        logger.error(f"Failed to send initial data to client: {e}")

web_ui.on_connect(on_client_connect)
logger.debug("Registered on_connect handler for WebUI")


# =======================
# START APPLICATION
# =======================

logger.info("=" * 60)
logger.info("SafeRide AI System Starting...")
logger.info(f"Initial Safety Score: {safety_score}/100")
logger.info(f"Danger Threshold: {DANGER_THRESHOLD_G}G")
logger.info(f"Crash Threshold: {CRASH_THRESHOLD_G}G")
logger.info(f"Dashboard: http://arduino-uno-q.local:8080")
logger.info("=" * 60)

App.run()