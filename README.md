# function-calling-for-sensors-at-the-edge

### 1. Data contains csv files with real farm data collected over several months.

You can use EDA.ipynb notebook file to play with real farm data to make sense of the farm data

## Setup on AWS Instance

### Thingsboard

Ensure the thingsboard image is started using port 1883 within the container mapped to 1884 in the external VM using the code below:

```bash
sudo docker run -it -p 8080:9090 -p 7070:7070 -p 1883:1884 -p 5683-5688:5683-5688/udp -v ~/.mytb-data:/data -v ~/.mytb-logs:/var/log/thingsboard --name mytb --restart always thingsboard/tb-postgres
```

### IoT-Data-Simulator

Ensure the Target System is sending data via MQTT using port 1884 e.g. <aws_private_ip>:1884
