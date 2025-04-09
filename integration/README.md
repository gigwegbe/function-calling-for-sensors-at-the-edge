# 🌱 IoT Farming Project - ThingsBoard MQTT Integration

This project collects **temperature, humidity, and soil moisture data** from multiple IoT sensors and sends it to **ThingsBoard** using MQTT.

## 📌 Features
- 📡 **MQTT-based** data transmission
- 🌡️ **Temperature**
- 💧 **Soil Moisture Measurement**
- 🔄 **Multiple Devices Support**
- 📊 **ThingsBoard Dashboard Integration**


---

## 🛠️ Setup Instructions

### 1️⃣ **Install Requirements**
Ensure you have Python and `paho-mqtt` installed.

```sh
sudo apt update
sudo apt install python3-venv
python3 -m venv thingsboard_env
source thingsboard_env/bin/activate
pip install paho-mqtt
```