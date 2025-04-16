from fastapi import APIRouter, Depends, HTTPException, Body, Query, Path
from sqlalchemy.orm import Session
from app.services.actuator_service import ActuatorService
from app.utils.db import get_db
import threading

router = APIRouter()

@router.post("/actuators/")
async def create_actuator(
    actuator_data: dict = Body(
        ...,
        example={
            "name": "Irrigation Pump",
            "type": "pump",
            "label": "Field Pump",
            "state": False,
            "additionalInfo": {"description": "Controls irrigation"}
        }
    ),
    db: Session = Depends(get_db)
):
    """Create a new actuator."""
    service = ActuatorService(db)
    return service.create_actuator(actuator_data)


@router.get("/actuators/{actuator_id}")
async def get_actuator(
    actuator_id: str = Path(..., example="621f9a80-11b0-11f0-830c-2f566ccd9628"),
    db: Session = Depends(get_db)
):
    """Retrieve an actuator by its ID."""
    service = ActuatorService(db)
    actuator = service.get_actuator(actuator_id)
    if not actuator:
        raise HTTPException(status_code=404, detail="Actuator not found")
    return actuator


@router.get("/actuators/{actuator_id}/subscribed_sensors")
async def get_subscribed_sensors(
    actuator_id: str = Path(..., example="621f9a80-11b0-11f0-830c-2f566ccd9628"),
    db: Session = Depends(get_db)
):
    """Retrieve all sensors subscribed to an actuator."""
    service = ActuatorService(db)
    sensors = service.get_subscribed_sensors(actuator_id)
    if not sensors:
        raise HTTPException(status_code=404, detail="No subscribed sensors found")
    return sensors


@router.delete("/actuators/{actuator_id}/unsubscribe/{sensor_id}")
async def unsubscribe_from_sensor(
    actuator_id: str = Path(..., example="621f9a80-11b0-11f0-830c-2f566ccd9628"),
    sensor_id: str = Path(..., example="721f9a80-11b0-11f0-830c-2f566ccd9628"),
    db: Session = Depends(get_db)
):
    """Unsubscribe an actuator from a sensor."""
    service = ActuatorService(db)
    success = service.unsubscribe_from_sensor(actuator_id, sensor_id)
    if not success:
        raise HTTPException(status_code=404, detail="Actuator or Sensor not found")
    return {"message": "Unsubscribed from sensor successfully"}


@router.put("/actuators/{actuator_id}")
async def update_actuator(
    actuator_id: str = Path(..., example="621f9a80-11b0-11f0-830c-2f566ccd9628"),
    updated_data: dict = Body(
        ...,
        example={
            "name": "Updated Pump",
            "type": "pump",
            "label": "Updated Field Pump",
            "state": True,
            "additionalInfo": {"description": "Updated description"}
        }
    ),
    db: Session = Depends(get_db)
):
    """Update an existing actuator."""
    service = ActuatorService(db)
    actuator = service.update_actuator(actuator_id, updated_data)
    if not actuator:
        raise HTTPException(status_code=404, detail="Actuator not found")
    return actuator


@router.delete("/actuators/{actuator_id}")
async def delete_actuator(
    actuator_id: str = Path(..., example="621f9a80-11b0-11f0-830c-2f566ccd9628"),
    db: Session = Depends(get_db)
):
    """Delete an actuator."""
    service = ActuatorService(db)
    success = service.delete_actuator(actuator_id)
    if not success:
        raise HTTPException(status_code=404, detail="Actuator not found")
    return {"message": "Actuator deleted successfully"}


@router.get("/actuators/")
async def get_all_actuators(db: Session = Depends(get_db)):
    """Retrieve all actuators."""
    service = ActuatorService(db)
    actuators = service.get_all_actuators()
    return actuators


@router.get("/actuators/name/{name}")
async def get_actuator_by_name(
    name: str = Path(..., example="Irrigation Pump"),
    db: Session = Depends(get_db)
):
    """Retrieve an actuator by its name."""
    service = ActuatorService(db)
    actuator = service.get_actuator_by_name(name)
    if not actuator:
        raise HTTPException(status_code=404, detail="Actuator not found")
    return actuator


@router.get("/actuators/{actuator_id}/status")
async def get_actuator_status(
    actuator_id: str = Path(..., example="621f9a80-11b0-11f0-830c-2f566ccd9628"),
    db: Session = Depends(get_db)
):
    """Retrieve the status of an actuator."""
    service = ActuatorService(db)
    actuator = service.get_actuator(actuator_id)
    if not actuator:
        raise HTTPException(status_code=404, detail="Actuator not found")
    return {"status": actuator.state}


@router.get("/actuators/state/{state}")
async def get_actuators_by_state(
    state: bool = Path(..., example=True),
    db: Session = Depends(get_db)
):
    """Retrieve actuators by their state."""
    service = ActuatorService(db)
    actuators = service.get_actuators_by_state(state)
    return actuators


@router.get("/actuators/type/{actuator_type}")
async def get_actuators_by_type(
    actuator_type: str = Path(..., example="pump"),
    db: Session = Depends(get_db)
):
    """Retrieve actuators by their type."""
    service = ActuatorService(db)
    actuators = service.get_actuators_by_type(actuator_type)
    return actuators


@router.post("/actuators/{actuator_id}/override")
async def override_actuator_state(
    actuator_id: str = Path(..., example="621f9a80-11b0-11f0-830c-2f566ccd9628"),
    state: bool = Body(..., example=True),
    db: Session = Depends(get_db)
):
    """
    Override the state of an actuator and pause monitoring for this actuator.
    """
    service = ActuatorService(db)

    # Pause monitoring for this actuator
    service.pause_actuator(actuator_id)

    # Set the actuator state
    success = service.override_actuator_state(actuator_id, state)
    if not success:
        raise HTTPException(status_code=404, detail="Actuator not found")

    return {"message": f"Actuator {actuator_id} state overridden successfully. Monitoring is paused for this actuator."}

@router.post("/actuators/{actuator_id}/resume")
async def resume_monitoring(
    actuator_id: str = Path(..., example="621f9a80-11b0-11f0-830c-2f566ccd9628"),
    db: Session = Depends(get_db)
):
    """
    Resume monitoring for a specific actuator.
    """
    service = ActuatorService(db)

    # Resume monitoring for this actuator
    service.resume_actuator(actuator_id)

    return {"message": f"Monitoring resumed for actuator {actuator_id}."}

@router.post("/actuators/{actuator_id}/subscribe/{sensor_id}")
async def subscribe_to_sensor(
    actuator_id: str = Path(..., example="621f9a80-11b0-11f0-830c-2f566ccd9628"),
    sensor_id: str = Path(..., example="721f9a80-11b0-11f0-830c-2f566ccd9628"),
    db: Session = Depends(get_db)
):
    """Subscribe an actuator to a sensor."""
    service = ActuatorService(db)
    success = service.subscribe_to_sensor(actuator_id, sensor_id)
    if not success:
        raise HTTPException(status_code=404, detail="Actuator or Sensor not found")
    return {"message": "Actuator subscribed to sensor successfully"}


@router.post("/actuators/{actuator_id}/monitor")
async def monitor_and_control(
    actuator_id: str = Path(..., example="e774f740-119f-11f0-943d-25e65dea434a"),
    thresholds: dict = Body(
        ...,
        example={
        "on_threshold": {
            "temperature": 18,
            "soil_moisture": 40
        },
        "off_threshold": {
            "temperature": 10,
            "soil_moisture": 30
        }
        }
    ),
    db: Session = Depends(get_db)
):
    """Monitor sensor data and control the actuator in a separate thread."""
    service = ActuatorService(db)
    
    # Check if actuator exists before starting the thread
    actuator = service.get_actuator(actuator_id)
    if not actuator:
        raise HTTPException(status_code=404, detail="Actuator not found")

    def monitor_task():
        # Create a new database session for this thread
        from app.utils.db import SessionLocal
        db_thread = SessionLocal()
        try:
            # Create a new service instance with the thread-local session
            thread_service = ActuatorService(db_thread)
            thread_service.monitor_and_control(actuator_id, thresholds)
        finally:
            db_thread.close()

    # Run the monitoring task in a separate thread
    thread = threading.Thread(target=monitor_task, daemon=True)
    thread.start()

    return {"message": "Monitoring and control job submitted successfully"}
