# weather_utils.py
import requests
from datetime import datetime
from config import OPENWEATHERMAP_API_KEY

def weather_search(query: str) -> dict:
    """
    Search for weather data using the OpenWeather API.
    """
    api_key = OPENWEATHERMAP_API_KEY
    if not api_key:
        return {"error": "OpenWeatherMap API key not found in environment variables."}

    base_url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        'q': query,
        'appid': api_key,
        'units': 'metric'  # Use 'imperial' for Fahrenheit
    }

    response = requests.get(base_url, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        return {
            "error": f"Failed to fetch weather data: {response.status_code}",
            "details": response.json()
        }


def get_weather_forecast(city):
    """
    Fetch a 5-day weather forecast (in 3-hour intervals) for a given city
    using the OpenWeatherMap API.

    Args:
        city (str): The name of the city to retrieve the forecast for.

    Returns:
        list[dict]: A list of dictionaries containing datetime, weather description,
                    and temperature for each forecast entry.
                    Returns an empty list if the API request fails.
    """
    api_key = OPENWEATHERMAP_API_KEY
    url = "http://api.openweathermap.org/data/2.5/forecast"
    params = {
        'q': city,
        'appid': api_key,
        'units': 'metric',
        'cnt': 10  # Number of forecast entries
    }

    response = requests.get(url, params=params)

    if response.status_code == 200:
        data = response.json()
        forecast = data['list']

        result = []
        for entry in forecast:
            dt = datetime.utcfromtimestamp(entry['dt'])
            date_time = dt.strftime('%Y-%m-%d %H:%M:%S')
            temp = entry['main']['temp']
            weather = entry['weather'][0]['description']
            result.append({
                'datetime': date_time,
                'weather': weather,
                'temperature_celsius': temp
            })
        return result
    else:
        return []