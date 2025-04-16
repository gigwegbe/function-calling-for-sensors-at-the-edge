from fastapi import APIRouter, Depends, HTTPException, Body, Path
from sqlalchemy.orm import Session
from app.services.sensor_service import SensorService
from app.utils.db import get_db

router = APIRouter()

@router.post("/sensors/")
async def create_sensor(
    sensor_data: dict = Body(
        ...,
        example={
            "name": "Soil Temperature Sensor",
            "type": "temperature",
            "unit": "celsius",
            "threshold": 30.0,
            "label": "Field Sensor",
            "keys": ["humidity", "temperature"],
            "additionalInfo": {"description": "Measures temperature levels"}
        }
    ),
    db: Session = Depends(get_db)
):
    """Create a new sensor."""
    service = SensorService(db)
    return service.create_sensor(sensor_data)

@router.get("/sensors/{sensor_id}")
async def get_sensor(
    sensor_id: str = Path(..., example="721f9a80-11b0-11f0-830c-2f566ccd9628"),
    db: Session = Depends(get_db)
):
    """Retrieve a sensor by its ID."""
    service = SensorService(db)
    sensor = service.get_sensor(sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return sensor

@router.put("/sensors/{sensor_id}")
async def update_sensor(
    sensor_id: str = Path(..., example="721f9a80-11b0-11f0-830c-2f566ccd9628"),
    updated_data: dict = Body(
        ...,
        example={
            "name": "Updated Temperature Sensor",
            "type": "temperature",
            "unit": "celsius",
            "threshold": 25.0,
            "label": "Updated Field Sensor",
            "keys": ["humidity", "temperature"],
            "additionalInfo": {"description": "Updated description"}
        }
    ),
    db: Session = Depends(get_db)
):
    """Update an existing sensor."""
    service = SensorService(db)
    sensor = service.update_sensor(sensor_id, updated_data)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return sensor

@router.delete("/sensors/{sensor_id}")
async def delete_sensor(
    sensor_id: str = Path(..., example="721f9a80-11b0-11f0-830c-2f566ccd9628"),
    db: Session = Depends(get_db)
):
    """Delete a sensor."""
    service = SensorService(db)
    success = service.delete_sensor(sensor_id)
    if not success:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return {"message": "Sensor deleted successfully"}

@router.get("/sensors/")
async def get_all_sensors(db: Session = Depends(get_db)):
    """Retrieve all sensors."""
    service = SensorService(db)
    sensors = service.get_all_sensors()
    return sensors

@router.get("/sensors/name/{name}")
async def get_sensor_by_name(
    name: str = Path(..., example="Soil Moisture Sensor"),
    db: Session = Depends(get_db)
):
    """Retrieve a sensor by its name."""
    service = SensorService(db)
    sensor = service.get_sensor_by_name(name)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return sensor

@router.get("/sensors/{sensor_id}/status")
async def get_sensor_status(
    sensor_id: str = Path(..., example="721f9a80-11b0-11f0-830c-2f566ccd9628"),
    db: Session = Depends(get_db)
):
    """Retrieve the status of a sensor."""
    service = SensorService(db)
    sensor = service.get_sensor(sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return {"status": sensor.status}

@router.get("/sensors/state/{state}")
async def get_sensors_by_state(
    state: str = Path(..., example="active"),
    db: Session = Depends(get_db)
):
    """Retrieve sensors by their state."""
    service = SensorService(db)
    sensors = service.get_sensors_by_state(state)
    if not sensors:
        raise HTTPException(status_code=404, detail="No sensors found with the specified state")
    return sensors