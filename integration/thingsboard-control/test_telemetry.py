import os
import random
from typing import Dict
from joblib import load
import numpy as np
import pandas as pd

# Load the model and scalers
models = load('./models.joblib')
scalers_X = load('./scalers_X.joblib')
scalers_y = load('./scalers_y.joblib')

# Print all keys in the models dictionary for debugging
print("Available model keys:", list(models.keys()))

def generate_telemetry(device_name: str, metrics: list[Dict[str, str]]) -> Dict[str, float]:
    """Generate telemetry data using the trained model"""
    telemetry_data = {}

    for metric in metrics:
        parameter = metric['name']
        model_key = f"{device_name}_{parameter}"
        print(f"Processing model key: {model_key}")  # Debugging statement
        if model_key not in models:
            print(f"Model key {model_key} not found in models")  # Debugging statement
            continue

        # Generate features for the current time
        current_time = pd.Timestamp.now()
        features = pd.DataFrame({
            'hour': [current_time.hour],
            'day': [current_time.day],
            'month': [current_time.month],
            'day_of_week': [current_time.dayofweek],
            'lag_1': [50],  # Replace with actual lag values
            'lag_2': [50],  # Replace with actual lag values
            'lag_3': [50],  # Replace with actual lag values
            'rolling_mean_3': [50],  # Replace with actual rolling mean
            'rolling_std_3': [5]  # Replace with actual rolling std
        })

        print(f"Generated features: {features}")  # Debugging statement

        scaled_features = scalers_X[model_key].transform(features)
        scaled_prediction = models[model_key].predict(scaled_features)
        prediction = scalers_y[model_key].inverse_transform(scaled_prediction.reshape(-1, 1))[0][0]

        noise = np.random.normal(0, 0.5)
        prediction = max(0, prediction + noise)

        telemetry_data[parameter] = round(prediction, 2)

    return telemetry_data

# Example usage
device_name = "A201"  # Use a valid sensor ID from the available model keys
metrics = [{"name": "soil_moisture", "unit": "%"}]

telemetry_data = generate_telemetry(device_name, metrics)
print(telemetry_data)