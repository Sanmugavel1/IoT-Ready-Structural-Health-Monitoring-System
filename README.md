# IoT-Ready Structural Health Monitoring System Using MPU6050 for Real-Time Tilt Detection

## Overview

The **IoT-Ready Structural Health Monitoring System** is an embedded systems project designed to monitor the tilt of structures such as buildings, bridges, towers, and other civil infrastructure in real time.

The prototype uses an **Arduino Nano** and an **MPU6050 (Accelerometer + Gyroscope)** sensor to continuously measure the structural orientation. The system calculates **Roll** and **Pitch** angles and classifies the structure into one of three states:

* SAFE
* WARNING
* DANGER

Whenever abnormal tilt is detected, the system immediately activates a **LED indicator** and **buzzer** to provide a local warning.

A Python-based desktop dashboard receives live sensor data over serial communication and provides real-time visualization, live graphs, event logging, and structural health status.

This project is developed as a prototype and is designed for future migration to an **ESP32-based IoT platform** with cloud connectivity and remote monitoring capabilities.

---

# Features

* Real-time Roll and Pitch monitoring
* Structural tilt detection using MPU6050
* SAFE / WARNING / DANGER classification
* Live monitoring through a Python dashboard
* LED and buzzer alert system
* Event logging
* Maximum tilt tracking
* Low-cost embedded prototype
* IoT-ready architecture for future ESP32 integration

---

# Hardware Used

* Arduino Nano
* MPU6050 (Accelerometer & Gyroscope)
* Active Buzzer
* LED
* Breadboard
* Jumper Wires
* USB Cable

---

# Software Used

* Arduino IDE
* Python 3
* PySide6
* PyQtGraph
* PySerial
* Visual Studio Code

---

# Project Structure

```text
IoT-Ready-Structural-Health-Monitoring-System/
│
├── README.md
├── LICENSE
├── .gitignore
├── requirements.txt
│
├── docs/
│   ├── Project_Report.pdf
│   └── Project_Presentation.pdf
│
├── hardware/
│   ├── Arduino_Code/
│   │   └── Structural_Health_Monitor.ino
│   │
│   └── Circuit_Diagram/
│       └── Circuit_Diagram.png
│
└── software/
    ├── main.py
    └── requirements.txt
```



# Installation

Clone the repository

```bash
git clone https://github.com/yourusername/IoT-Ready-Structural-Health-Monitoring-System.git
```

Move into the project folder

```bash
cd IoT-Ready-Structural-Health-Monitoring-System
```

Install Python dependencies

```bash
pip install -r requirements.txt
```

Upload the Arduino code to the Arduino Nano using the Arduino IDE.

Run the dashboard

```bash
python main.py
```

---

# Arduino Serial Data Format

The Arduino transmits one CSV line every 100 ms.

Example

```text
15.23,4.15,31.5,18.7,WARNING,3
```

Format

```text
Roll,Pitch,Temperature,Maximum Tilt,Status,Alert Count
```

---

# Working Principle

1. The MPU6050 continuously measures the orientation of the structure.
2. Arduino Nano processes the sensor data.
3. Roll and Pitch angles are calculated.
4. The structural condition is classified as SAFE, WARNING, or DANGER.
5. LED and buzzer provide immediate local alerts.
6. Sensor data is transmitted to the Python dashboard via USB serial communication.
7. The dashboard displays live graphs, structural status, and event logs.

---

# Future Enhancements

* ESP32 Integration
* Wi-Fi Connectivity
* MQTT Communication
* Firebase Cloud Database
* Remote Web Dashboard
* Mobile Application
* Push Notifications
* Email & SMS Alerts
* Predictive Maintenance using AI

---

# Applications

* Smart Buildings
* Bridges
* Towers
* Industrial Structures
* Construction Site Monitoring
* Infrastructure Health Monitoring
* Educational Demonstrations

---

# Disclaimer

This project is intended as an educational and prototype Structural Health Monitoring (SHM) system.

It is designed for **real-time tilt monitoring and early warning only** and should not be considered a certified structural safety system or a building collapse prediction solution.

---

# Author

**Sanmugavel B**

Electronics and Communication Engineering

GitHub: https://github.com/Sanmugavel1

LinkedIn: https://linkedin.com/in/sanmugavelb

Email: sanmugavelb1@gmail.com

---

## License

This project is released under the MIT License.
