# import time
# import numpy as np
# import matplotlib.pyplot as plt
# import matplotlib.animation as animation
# from datetime import datetime, timedelta

# # Sensor Simulation Parameters
# class FarmSensorSimulator:
#     def __init__(self):
#         self.soil_moisture_params = {
#             'base_level': np.random.uniform(20, 35),
#             'daily_variation': np.random.uniform(3, 8),
#             'monthly_variation': np.random.uniform(2, 6),
#             'noise_level': 1.5,
#         }
#         self.soil_temp_params = {
#             'base_temp': np.random.uniform(22, 24),
#             'daily_amplitude': np.random.uniform(1, 2.5),
#             'seasonal_amplitude': np.random.uniform(2, 4),
#             'noise_level': 0.3,
#         }
#         self.soil_ec_params = {
#             'base_level': np.random.uniform(100, 500),
#             'variation': np.random.uniform(30, 100),
#             'noise_level': 10,
#         }
#         self.battery_params = {
#             'initial_level': np.random.uniform(95, 100),
#             'drain_rate': np.random.uniform(0.01, 0.03),
#             'noise_level': 0.5,
#         }

#     def simulate_soil_moisture(self):
#         """Simulate soil moisture with daily and monthly patterns."""
#         hour = datetime.now().hour + datetime.now().minute / 60
#         day_of_year = datetime.now().timetuple().tm_yday
        
#         # Daily pattern (lower during the day, higher at night)
#         daily_pattern = np.sin(2 * np.pi * (hour - 6) / 24) * self.soil_moisture_params['daily_variation']
        
#         # Monthly pattern (seasonal changes)
#         monthly_pattern = np.sin(2 * np.pi * day_of_year / 365) * self.soil_moisture_params['monthly_variation']
        
#         # Add base level, patterns, and noise
#         moisture = (
#             self.soil_moisture_params['base_level'] +
#             daily_pattern +
#             monthly_pattern +
#             np.random.normal(0, self.soil_moisture_params['noise_level'])
#         )
        
#         return round(np.clip(moisture, 0, 45), 2)

#     def simulate_soil_temperature(self):
#         """Simulate soil temperature with daily and seasonal patterns."""
#         hour = datetime.now().hour + datetime.now().minute / 60
#         day_of_year = datetime.now().timetuple().tm_yday
        
#         # Daily pattern (peak at afternoon)
#         daily_pattern = np.sin(2 * np.pi * (hour - 14) / 24) * self.soil_temp_params['daily_amplitude']
        
#         # Seasonal pattern
#         seasonal_pattern = np.sin(2 * np.pi * day_of_year / 365) * self.soil_temp_params['seasonal_amplitude']
        
#         temperature = (
#             self.soil_temp_params['base_temp'] +
#             daily_pattern +
#             seasonal_pattern +
#             np.random.normal(0, self.soil_temp_params['noise_level'])
#         )
        
#         return round(np.clip(temperature, 19, 31), 2)

#     def simulate_soil_electroconductivity(self, soil_moisture):
#         """Simulate soil electroconductivity based on moisture."""
#         base_ec = self.soil_ec_params['base_level']
        
#         # EC correlates with moisture but has its own patterns
#         moisture_effect = (soil_moisture - self.soil_moisture_params['base_level']) * 5
        
#         ec = (
#             base_ec +
#             moisture_effect +
#             np.random.normal(0, self.soil_ec_params['noise_level'])
#         )
        
#         return round(np.clip(ec, 20, 950), 2)

#     def simulate_battery_level(self):
#         """Simulate battery level with realistic drain pattern."""
#         hours_since_start = (datetime.now() - datetime(datetime.now().year, datetime.now().month, datetime.now().day)).total_seconds() / (60 * 60)
        
#         # Simulate battery drain
#         battery_level = (
#             self.battery_params['initial_level'] -
#             hours_since_start * self.battery_params['drain_rate'] +
#             np.random.normal(0, self.battery_params['noise_level'])
#         )
        
#         # Simulate battery replacement if level drops too low
#         if battery_level < 65:
#             battery_level = np.random.uniform(95, 100)
        
#         return round(np.clip(battery_level, 50, 100), 2)

# # --- Visualization and Simulation ---

# # Number of sensors
# num_sensors = 3  # Simulate three sensors
# sensor_ids = [f"A20{i+1}" for i in range(num_sensors)]

# # Data sending interval (30 minutes)
# data_interval_minutes = 5
# data_interval_seconds = data_interval_minutes * 60

# # Create subplots for each sensor and each parameter
# fig, axes = plt.subplots(num_sensors, 4, figsize=(16, 6 * num_sensors))
# lines = {}

# # Initialize lines and axes
# parameters = ['soil_moisture', 'soil_temperature', 'soil_electroconductivity', 'battery_level']
# y_labels = {
#     'soil_moisture': 'Soil Moisture',
#     'soil_temperature': 'Soil Temperature',
#     'soil_electroconductivity': 'Soil EC',
#     'battery_level': 'Battery Level'
# }
# y_limits = {
#     'soil_moisture': (0, 45),
#     'soil_temperature': (19, 31),
#     'soil_electroconductivity': (20, 950),
#     'battery_level': (50, 100)
# }

# for i, ax_row in enumerate(axes):
#     sensor_id = sensor_ids[i]
#     lines[sensor_id] = {}
#     for j, param in enumerate(parameters):
#         ax = ax_row[j]
#         ax.set_title(f'Sensor {sensor_id} - {y_labels[param]}')
#         ax.set_xlabel('Time')
#         ax.set_ylabel(y_labels[param])
#         line, = ax.plot([], [], label=y_labels[param])
#         lines[sensor_id][param] = line
#         ax.set_xlim(0, data_interval_seconds)  # X-axis represents the data interval
#         ax.set_ylim(y_limits[param])  # Y-axis limits based on parameter
#         ax.legend()

# # Simulation data
# x_data = {sensor_id: [] for sensor_id in sensor_ids}
# y_data = {sensor_id: {param: [] for param in parameters} for sensor_id in sensor_ids}
# start_time = time.time()
# last_data_time = start_time  # When the last set of data was simulated

# # Animation function
# def update(frame):
#     global start_time, last_data_time  # Declare start_time as a global variable

#     current_time = time.time()

#     # Check if 30 minutes have passed since the last data generation
#     if current_time - last_data_time >= data_interval_seconds:
#         for i, sensor_id in enumerate(sensor_ids):
#             simulator = FarmSensorSimulator()
#             soil_moisture = simulator.simulate_soil_moisture()
#             soil_temperature = simulator.simulate_soil_temperature()
#             soil_electroconductivity = simulator.simulate_soil_electroconductivity(soil_moisture)
#             battery_level = simulator.simulate_battery_level()

#             # Append data to lists
#             x_data[sensor_id].append(current_time - start_time)
#             y_data[sensor_id]['soil_moisture'].append(soil_moisture)
#             y_data[sensor_id]['soil_temperature'].append(soil_temperature)
#             y_data[sensor_id]['soil_electroconductivity'].append(soil_electroconductivity)
#             y_data[sensor_id]['battery_level'].append(battery_level)

#             # Keep only the last 30 minutes of data
#             x_data[sensor_id] = x_data[sensor_id][-1:]
#             for param in parameters:
#                 y_data[sensor_id][param] = y_data[sensor_id][param][-1:]

#             # Update lines
#             lines[sensor_id]['soil_moisture'].set_data(x_data[sensor_id], y_data[sensor_id]['soil_moisture'])
#             lines[sensor_id]['soil_temperature'].set_data(x_data[sensor_id], y_data[sensor_id]['soil_temperature'])
#             lines[sensor_id]['soil_electroconductivity'].set_data(x_data[sensor_id], y_data[sensor_id]['soil_electroconductivity'])
#             lines[sensor_id]['battery_level'].set_data(x_data[sensor_id], y_data[sensor_id]['battery_level'])

#         # Update the last data generation time
#         last_data_time = current_time

#     # Flatten the dictionary of lines into a single list for blit
#     all_lines = [line for sensor in lines.values() for line in sensor.values()]
#     return all_lines

# # Create animation
# ani = animation.FuncAnimation(fig, update, blit=True, interval=100)  # Update every 0.1 second

# plt.tight_layout()
# plt.show()


#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

# import time
# import numpy as np
# from datetime import datetime

# # Sensor Simulation Parameters
# class FarmSensorSimulator:
#     def __init__(self):
#         self.soil_moisture_params = {
#             'base_level': np.random.uniform(20, 35),
#             'daily_variation': np.random.uniform(3, 8),
#             'monthly_variation': np.random.uniform(2, 6),
#             'noise_level': 1.5,
#         }
#         self.soil_temp_params = {
#             'base_temp': np.random.uniform(22, 24),
#             'daily_amplitude': np.random.uniform(1, 2.5),
#             'seasonal_amplitude': np.random.uniform(2, 4),
#             'noise_level': 0.3,
#         }
#         self.soil_ec_params = {
#             'base_level': np.random.uniform(100, 500),
#             'variation': np.random.uniform(30, 100),
#             'noise_level': 10,
#         }
#         self.battery_params = {
#             'initial_level': np.random.uniform(95, 100),
#             'drain_rate': np.random.uniform(0.01, 0.03),
#             'noise_level': 0.5,
#         }

#     def simulate_soil_moisture(self):
#         """Simulate soil moisture with daily and monthly patterns."""
#         hour = datetime.now().hour + datetime.now().minute / 60
#         day_of_year = datetime.now().timetuple().tm_yday
        
#         # Daily pattern (lower during the day, higher at night)
#         daily_pattern = np.sin(2 * np.pi * (hour - 6) / 24) * self.soil_moisture_params['daily_variation']
        
#         # Monthly pattern (seasonal changes)
#         monthly_pattern = np.sin(2 * np.pi * day_of_year / 365) * self.soil_moisture_params['monthly_variation']
        
#         # Add base level, patterns, and noise
#         moisture = (
#             self.soil_moisture_params['base_level'] +
#             daily_pattern +
#             monthly_pattern +
#             np.random.normal(0, self.soil_moisture_params['noise_level'])
#         )
        
#         return round(np.clip(moisture, 0, 45), 2)

#     def simulate_soil_temperature(self):
#         """Simulate soil temperature with daily and seasonal patterns."""
#         hour = datetime.now().hour + datetime.now().minute / 60
#         day_of_year = datetime.now().timetuple().tm_yday
        
#         # Daily pattern (peak at afternoon)
#         daily_pattern = np.sin(2 * np.pi * (hour - 14) / 24) * self.soil_temp_params['daily_amplitude']
        
#         # Seasonal pattern
#         seasonal_pattern = np.sin(2 * np.pi * day_of_year / 365) * self.soil_temp_params['seasonal_amplitude']
        
#         temperature = (
#             self.soil_temp_params['base_temp'] +
#             daily_pattern +
#             seasonal_pattern +
#             np.random.normal(0, self.soil_temp_params['noise_level'])
#         )
        
#         return round(np.clip(temperature, 19, 31), 2)

#     def simulate_soil_electroconductivity(self, soil_moisture):
#         """Simulate soil electroconductivity based on moisture."""
#         base_ec = self.soil_ec_params['base_level']
        
#         # EC correlates with moisture but has its own patterns
#         moisture_effect = (soil_moisture - self.soil_moisture_params['base_level']) * 5
        
#         ec = (
#             base_ec +
#             moisture_effect +
#             np.random.normal(0, self.soil_ec_params['noise_level'])
#         )
        
#         return round(np.clip(ec, 20, 950), 2)

#     def simulate_battery_level(self):
#         """Simulate battery level with realistic drain pattern."""
#         hours_since_start = (datetime.now() - datetime(datetime.now().year, datetime.now().month, datetime.now().day)).total_seconds() / (60 * 60)
        
#         # Simulate battery drain
#         battery_level = (
#             self.battery_params['initial_level'] -
#             hours_since_start * self.battery_params['drain_rate'] +
#             np.random.normal(0, self.battery_params['noise_level'])
#         )
        
#         # Simulate battery replacement if level drops too low
#         if battery_level < 65:
#             battery_level = np.random.uniform(95, 100)
        
#         return round(np.clip(battery_level, 50, 100), 2)

# # --- Simulation ---

# # Number of sensors
# num_sensors = 3  # Simulate three sensors
# sensor_ids = [f"A20{i+1}" for i in range(num_sensors)]

# # Data sending interval (30 minutes)
# data_interval_minutes = 30
# data_interval_seconds = data_interval_minutes * 60

# # Main simulation loop
# if __name__ == "__main__":
#     start_time = time.time()
#     last_data_time = start_time

#     while True:
#         current_time = time.time()

#         # Check if 30 minutes have passed since the last data generation
#         if current_time - last_data_time >= data_interval_seconds:
#             print(f"--- {datetime.now()} ---")  # Print timestamp of data generation

#             for sensor_id in sensor_ids:
#                 simulator = FarmSensorSimulator()
#                 soil_moisture = simulator.simulate_soil_moisture()
#                 soil_temperature = simulator.simulate_soil_temperature()
#                 soil_electroconductivity = simulator.simulate_soil_electroconductivity(soil_moisture)
#                 battery_level = simulator.simulate_battery_level()

#                 print(f"Sensor {sensor_id}:")
#                 print(f"  Soil Moisture: {soil_moisture}")
#                 print(f"  Soil Temperature: {soil_temperature}")
#                 print(f"  Soil EC: {soil_electroconductivity}")
#                 print(f"  Battery Level: {battery_level}")
#                 print("-" * 20)

#             last_data_time = current_time  # Update the last data generation time

#         time.sleep(1)  # Check every 1 second to minimize resource usage




import time
import numpy as np
from datetime import datetime

# Sensor Simulation Parameters
class FarmSensorSimulator:
    def __init__(self, soil_type="sandy"):
        self.soil_type = soil_type  # "sandy" or "loam"
        
        # Parameters for sandy soil
        if self.soil_type == "sandy":
            self.soil_moisture_params = {
                'base_level': np.random.uniform(20, 35),
                'daily_variation': np.random.uniform(3, 8),
                'monthly_variation': np.random.uniform(2, 6),
                'noise_level': 1.5,
            }
        # Parameters for loam soil (retains moisture longer)
        elif self.soil_type == "loam":
            self.soil_moisture_params = {
                'base_level': np.random.uniform(30, 45),  # Higher base moisture level
                'daily_variation': np.random.uniform(1, 4),  # Smaller daily variation
                'monthly_variation': np.random.uniform(1, 3),  # Smaller monthly variation
                'noise_level': 1.0,  # Less noise due to stable moisture retention
            }

        self.soil_temp_params = {
            'base_temp': np.random.uniform(22, 24),
            'daily_amplitude': np.random.uniform(1, 2.5),
            'seasonal_amplitude': np.random.uniform(2, 4),
            'noise_level': 0.3,
        }
        self.soil_ec_params = {
            'base_level': np.random.uniform(100, 500),
            'variation': np.random.uniform(30, 100),
            'noise_level': 10,
        }
        self.battery_params = {
            'initial_level': np.random.uniform(95, 100),
            'drain_rate': np.random.uniform(0.01, 0.03),
            'noise_level': 0.5,
        }

    def simulate_soil_moisture(self):
        """Simulate soil moisture with daily and monthly patterns."""
        hour = datetime.now().hour + datetime.now().minute / 60
        day_of_year = datetime.now().timetuple().tm_yday
        
        # Daily pattern (lower during the day, higher at night)
        daily_pattern = np.sin(2 * np.pi * (hour - 6) / 24) * self.soil_moisture_params['daily_variation']
        
        # Monthly pattern (seasonal changes)
        monthly_pattern = np.sin(2 * np.pi * day_of_year / 365) * self.soil_moisture_params['monthly_variation']
        
        # Add base level, patterns, and noise
        moisture = (
            self.soil_moisture_params['base_level'] +
            daily_pattern +
            monthly_pattern +
            np.random.normal(0, self.soil_moisture_params['noise_level'])
        )
        
        return round(np.clip(moisture, 0, 45), 2)

    def simulate_soil_temperature(self):
        """Simulate soil temperature with daily and seasonal patterns."""
        hour = datetime.now().hour + datetime.now().minute / 60
        day_of_year = datetime.now().timetuple().tm_yday
        
        # Daily pattern (peak at afternoon)
        daily_pattern = np.sin(2 * np.pi * (hour - 14) / 24) * self.soil_temp_params['daily_amplitude']
        
        # Seasonal pattern
        seasonal_pattern = np.sin(2 * np.pi * day_of_year / 365) * self.soil_temp_params['seasonal_amplitude']
        
        temperature = (
            self.soil_temp_params['base_temp'] +
            daily_pattern +
            seasonal_pattern +
            np.random.normal(0, self.soil_temp_params['noise_level'])
        )
        
        return round(np.clip(temperature, 19, 31), 2)

    def simulate_soil_electroconductivity(self, soil_moisture):
        """Simulate soil electroconductivity based on moisture."""
        base_ec = self.soil_ec_params['base_level']
        
        # EC correlates with moisture but has its own patterns
        moisture_effect = (soil_moisture - self.soil_moisture_params['base_level']) * 5
        
        ec = (
            base_ec +
            moisture_effect +
            np.random.normal(0, self.soil_ec_params['noise_level'])
        )
        
        return round(np.clip(ec, 20, 950), 2)

    def simulate_battery_level(self):
        """Simulate battery level with realistic drain pattern."""
        hours_since_start = (datetime.now() - datetime(datetime.now().year, datetime.now().month, datetime.now().day)).total_seconds() / (60 * 60)
        
        # Simulate battery drain
        battery_level = (
            self.battery_params['initial_level'] -
            hours_since_start * self.battery_params['drain_rate'] +
            np.random.normal(0, self.battery_params['noise_level'])
        )
        
        # Simulate battery replacement if level drops too low
        if battery_level < 65:
            battery_level = np.random.uniform(95, 100)
        
        return round(np.clip(battery_level, 50, 100), 2)

# --- Simulation ---

# Number of sensors
sensor_ids_sandy = [f"A20{i+1}" for i in range(3)]   # Sandy soil sensors: A201-A203
sensor_ids_loam = ["C9", "C10"]                      # Loam soil sensors: C9 and C10
sensor_ids = sensor_ids_sandy + sensor_ids_loam      # Combine all sensor IDs

# Data sending interval (30 minutes)
data_interval_minutes = 30
data_interval_seconds = data_interval_minutes * 60

# Main simulation loop
if __name__ == "__main__":
    start_time = time.time()
    last_data_time = start_time

    while True:
        current_time = time.time()

        # Check if the data interval has passed since the last data generation
        if current_time - last_data_time >= data_interval_seconds:
            print(f"--- {datetime.now()} ---")   # Print timestamp of data generation

            for sensor_id in sensor_ids:
                # Determine soil type based on sensor ID
                soil_type = "sandy" if sensor_id in sensor_ids_sandy else "loam"
                
                simulator = FarmSensorSimulator(soil_type=soil_type)
                soil_moisture = simulator.simulate_soil_moisture()
                soil_temperature = simulator.simulate_soil_temperature()
                soil_electroconductivity = simulator.simulate_soil_electroconductivity(soil_moisture)
                battery_level = simulator.simulate_battery_level()

                print(f"Sensor {sensor_id} ({soil_type.capitalize()} Soil):")
                print(f"  Soil Moisture: {soil_moisture}")
                print(f"  Soil Temperature: {soil_temperature}")
                print(f"  Soil EC: {soil_electroconductivity}")
                print(f"  Battery Level: {battery_level}")
                print("-" * 20)

            last_data_time = current_time   # Update the last data generation time

        time.sleep(1)   # Check every second to minimize resource usage
