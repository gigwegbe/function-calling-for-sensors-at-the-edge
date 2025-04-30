# Agentic Farm Monitoring

## Team Member: 
- D’Amour Nsanzimfura  
- Claude Kwizera  
- George Igwegbe  
- Martins Awojide 

## Project Resource: 
- Slide - [Link](#)
- Report - [Link](#)
- Video - [Link](#)


## Project Structure 
- **`cloud-integration/`** – Codebase for the initial cloud setup and deployment.  
- **`llm/`** – Codebase for running the large language model (LLM) components.  
- **`simulated-farm-setup/`** – Code for setting up the simulated farm model and integrating with ThingsBoard.  
- **`farm-eda/`** – Exploratory data analysis (EDA) for the Nyagatare Farm in Eastern Province.

To run the project, first complete the setup for ThingsBoard and the IoT Simulator. Once those are configured, you can proceed to set up the agent services and the Flask integration app.

## Initial Setup (Thingsboard and IoT Simulator)
To get started with the ThingsBoard and IoT Simulator setup, follow the respective instructions below:
- **Thingboard Board Database Setup** - [Instructions](https://github.com/gigwegbe/function-calling-for-sensors-at-the-edge/tree/main/simulated-farm-setup/thingsboard/database) 
- **Thingboard Board Dashboard Configuration** - [Instructions](https://github.com/gigwegbe/function-calling-for-sensors-at-the-edge/tree/main/simulated-farm-setup/thingsboard/dashboard) 
- **IoT Simulator Board Devices Setup** - [Instructions](https://github.com/gigwegbe/function-calling-for-sensors-at-the-edge/tree/main/simulated-farm-setup/thingsboard/devices)


Once you've completed the ThingsBoard and IoT Simulator setup, your environment should resemble the screenshots shown below:

### ThingsBoard Dashboard
![ThingsBoard Dashboard](./assets/thingsboard.png)


### Database Configuration
![IoT Simulator Setup](./assets/iot-simulator.png)


## Agent services and Flask Intergration App. 


### 1. Data contains csv files with real farm data collected over several months.

You can use EDA.ipynb notebook file to play with real farm data to make sense of the farm data

