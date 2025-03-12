// Soil Temp

function custom(ruleState, sessionState, deviceName) {
    // Get the current date and time
    var now = new Date();
    var hour = now.getHours(); // Current hour (0-23)
    var day = now.getDate(); // Current day of the month (1-31)
    var month = now.getMonth() + 1; // Current month (1-12), getMonth() returns 0-11
    var weekday = now.getDay(); // Current day of the week (0-6), 0 is Sunday

    // Calculate soil temperature using the model equation
    var soil_temperature = 15.71 + (0.09 * hour) + (0.02 * day) + (0.70 * month) + (-0.04 * weekday);

    // Return the calculated soil temperature
    return soil_temperature;
}



// Soil Moisture

function customSoilMoisture(ruleState, sessionState, deviceName) {
    // Get the current date and time
    var now = new Date();
    var hour = now.getHours(); // Current hour (0-23)
    var day = now.getDate(); // Current day of the month (1-31)
    var month = now.getMonth() + 1; // Current month (1-12), getMonth() returns 0-11
    var weekday = now.getDay(); // Current day of the week (0-6), 0 is Sunday

    // Calculate soil moisture using the model equation
    var soil_moisture = 12.35 + (0.00 * hour) + (0.03 * day) + (1.48 * month) + (0.01 * weekday);

    // Return the calculated soil moisture
    return soil_moisture;
}



// Soil Electroconductivity

function customSoilElectroconductivity(ruleState, sessionState, deviceName) {
    // Get the current date and time
     var now = new Date();
     var hour = now.getHours(); // Current hour (0-23)
     var day = now.getDate(); // Current day of the month (1-31)
     var month = now.getMonth() + 1; // Current month (1-12), getMonth() returns 0-11
     var weekday = now.getDay(); // Current day of the week (0-6), 0 is Sunday
 
     // Calculate soil electroconductivity using the model equation
     var soil_electroconductivity = 173.12 + (0.13 * hour) + (0.16 * day) + (3.87 * month) + (0.32 * weekday);
 
     // Return the calculated soil electroconductivity
     return soil_electroconductivity;
 }
 


// Battery level

function customBatteryLevel(ruleState, sessionState, deviceName) {
    // Get the current date and time
    var now = new Date();
    var hour = now.getHours(); // Current hour (0-23)
    var day = now.getDate(); // Current day of the month (1-31)
    var month = now.getMonth() + 1; // Current month (1-12), getMonth() returns 0-11
    var weekday = now.getDay(); // Current day of the week (0-6), 0 is Sunday

    // Calculate battery level using the model equation
    var battery_level = 126.86 + (-0.12 * hour) + (-0.08 * day) + (-3.30 * month) + (-0.07 * weekday);

    // Return the calculated battery level
    return battery_level;
}


