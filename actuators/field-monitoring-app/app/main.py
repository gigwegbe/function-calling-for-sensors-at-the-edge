from fastapi import FastAPI
from app.routes.sensor_router import router as sensor_router
from app.routes.actuator_router import router as actuator_router
from fastapi.middleware.cors import CORSMiddleware
from app.utils.db import initialize_database

app = FastAPI(
    title="Field Monitoring API",
    description="API for managing fields, devices, sensors, and actuators",
    version="1.0.0"
)

# CORS Middleware (optional, configure as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update this to restrict origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database initialization on startup
@app.on_event("startup")
async def startup_event():
    initialize_database()

# Include routers
app.include_router(sensor_router, prefix="/api/sensors", tags=["Sensors"])
app.include_router(actuator_router, prefix="/api/actuators", tags=["Actuators"])