# Intelligent Soft Drink Consumption Manager (by Group 42)

The Intelligent Soft Drink Consumption Manager is an IoT-based system designed to help users monitor and control their soft drink intake. By integrating hardware components such as sensors and a solenoid lock with a web-based interface, the system provides real-time feedback on consumption, enforces limits, and promotes healthier drinking habits.

## Made by:

Janki Prafulbhai Rangani (24095031) 

Daivik Anil (22987816) 

Wangyanlin Li (24212962) 

Arjun Kang (22984924) 

Winky Loong (24037833) 

## Hardware setup:

![Screenshot 2024-10-20 192031](https://github.com/user-attachments/assets/09dc5e27-4bac-46bd-9e13-b2d0342aa7ea)

![Image](https://github.com/user-attachments/assets/2ba56ab6-a7d6-4fe3-93a4-dc03f7d22221)

![Image (1)](https://github.com/user-attachments/assets/2569634d-f0bd-446d-a44f-76c2e4c94a91)

## Hardware coding setup:

In your arduino software, download following libraries:
WebSockets library 

ezButton library

ArduinoJson library

Paste the code of ESP32Client.ino in your file.

Change the wifi settings in the file.

Choose the board as esp32 firebeetle v1 and port of your connection.

Verify and upload it.

## software setup:

Clone this Repository to your device.

Ensure ESP32 device is connected to the same wifi and uses the local IP address of the app.

To run the Flask app:
1) Install requirements using "pip install -r requirements.txt"
2) Start up a virtual environment and activate scripts:
    "python -m venv myenv"
    "myenv\Scripts\activate"
3) Run "python app.py" in the terminal
4) Click on the host link to view the app


