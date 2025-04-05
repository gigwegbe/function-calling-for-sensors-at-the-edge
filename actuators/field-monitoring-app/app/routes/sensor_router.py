from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.services.sensor_service import SensorService
from app.utils.db import get_db

router = APIRouter()

@router.post("/sensors/")
async def create_sensor(sensor_data: dict, db: Session = Depends(get_db)):
    service = SensorService(db)
    return service.create_sensor(sensor_data)

@router.get("/sensors/{sensor_id}")
async def get_sensor(sensor_id: str, db: Session = Depends(get_db)):
    service = SensorService(db)
    sensor = service.get_sensor(sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return sensor

@router.put("/sensors/{sensor_id}")
async def update_sensor(sensor_id: str, updated_data: dict, db: Session = Depends(get_db)):
    service = SensorService(db)
    sensor = service.update_sensor(sensor_id, updated_data)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return sensor

@router.delete("/sensors/{sensor_id}")
async def delete_sensor(sensor_id: str, db: Session = Depends(get_db)):
    service = SensorService(db)
    success = service.delete_sensor(sensor_id)
    if not success:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return {"message": "Sensor deleted successfully"}

@router.get("/sensors/")
async def get_all_sensors(db: Session = Depends(get_db)):
    service = SensorService(db)
    sensors = service.get_all_sensors()
    return sensors

@router.get("/sensors/name/{name}")
async def get_sensor_by_name(name: str, db: Session = Depends(get_db)):
    service = SensorService(db)
    sensor = service.get_sensor_by_name(name)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return sensor

@router.get("/sensors/{sensor_id}/status")
async def get_sensor_status(sensor_id: str, db: Session = Depends(get_db)):
    service = SensorService(db)
    sensor = service.get_sensor(sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return {"status": sensor.status}

@router.get("/sensors/state/{state}")
async def get_sensors_by_state(state: str, db: Session = Depends(get_db)):
    service = SensorService(db)
    sensors = service.get_sensors_by_state(state)
    if not sensors:
        raise HTTPException(status_code=404, detail="No sensors found with the specified state")
    return sensors