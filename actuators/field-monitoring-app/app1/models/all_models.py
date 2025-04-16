from sqlalchemy import Column, String, Float, Boolean, DateTime, ForeignKey, Table, JSON
from sqlalchemy.orm import relationship
from app.utils.db import Base
from datetime import datetime
import uuid

# Association table for many-to-many relationship between actuators and sensors
actuator_sensor_association = Table(
    'actuator_sensor',
    Base.metadata,
    Column('actuator_id', ForeignKey('actuators.id'), primary_key=True),
    Column('sensor_id', ForeignKey('sensors.id'), primary_key=True),
    extend_existing=True
)

class Actuator(Base):
    __tablename__ = 'actuators'
    __table_args__ = {'extend_existing': True}

    id = Column(String, primary_key=True)
    state = Column(Boolean, default=False)
    name = Column(String, nullable=False, unique=True)
    type = Column(String, nullable=False)
    label = Column(String, nullable=True)
    additionalInfo = Column(JSON, nullable=True)
    flow_rate = Column(Float, nullable=True)  # New column for actuator flow rate
    # Add the location column
    location = Column(String, nullable=True)  # New column for actuator location
    power_consumption = Column(Float, nullable=True)  # New column for actuator power consumption

    monitoring_active = Column(Boolean, default=True)
    last_state_change = Column(DateTime, default=datetime.utcnow)
    last_monitoring_change = Column(DateTime, default=datetime.utcnow)

    # Relationships
    sensors = relationship("Sensor", secondary=actuator_sensor_association, back_populates="actuators")
    resources = relationship("ActuatorResource", back_populates="actuator")

    def __repr__(self):
        return f"<Actuator(id='{self.id}', name='{self.name}', state={self.state})>"
class Sensor(Base):
    __tablename__ = 'sensors'
    __table_args__ = {'extend_existing': True}

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    type = Column(String, nullable=False)
    unit = Column(String, nullable=True)
    threshold = Column(Float, nullable=True)
    label = Column(String, nullable=True)
    additionalInfo = Column(JSON, nullable=True)
    keys = Column(JSON, nullable=True)

    # Relationships
    actuators = relationship("Actuator", secondary=actuator_sensor_association, back_populates="sensors")

    def __repr__(self):
        return f"<Sensor(id='{self.id}', name='{self.name}', type='{self.type}')>"

class Resource(Base):
    __tablename__ = 'resources'
    __table_args__ = {'extend_existing': True}

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, unique=True)
    type = Column(String, nullable=False)
    current_level = Column(Float, default=0.0)
    capacity = Column(Float, default=0.0)
    units = Column(String, default="liters")
    refill_threshold = Column(Float, default=20.0)
    last_updated = Column(DateTime, default=datetime.utcnow)
    external_id = Column(String, nullable=False, unique=True)

    # Relationships
    actuators = relationship("ActuatorResource", back_populates="resource")

    def __init__(self, id=None, **kwargs):
        if id:
            self.id = id
        super().__init__(**kwargs)

    def __repr__(self):
        return f"<Resource(id='{self.id}', name='{self.name}', type='{self.type}')>"

class ActuatorResource(Base):
    __tablename__ = "actuator_resources"
    __table_args__ = {'extend_existing': True}

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    actuator_id = Column(String, ForeignKey("actuators.id"))
    resource_id = Column(String, ForeignKey("resources.id"))
    relationship_type = Column(String)

    # Relationships
    actuator = relationship("Actuator", back_populates="resources")
    resource = relationship("Resource", back_populates="actuators")

    def __repr__(self):
        return f"<ActuatorResource(id='{self.id}', actuator_id='{self.actuator_id}', resource_id='{self.resource_id}')>"

class SystemEvent(Base):
    __tablename__ = 'system_events'
    __table_args__ = {'extend_existing': True}

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_type = Column(String, nullable=False)
    description = Column(String, nullable=True)
    severity = Column(String, default="info")
    timestamp = Column(DateTime, default=datetime.utcnow)
    resolved = Column(Boolean, default=False)
    resource_id = Column(String, ForeignKey('resources.id'), nullable=True)
    actuator_id = Column(String, ForeignKey('actuators.id'), nullable=True)

    def __repr__(self):
        return f"<SystemEvent(id='{self.id}', event_type='{self.event_type}', severity='{self.severity}')>"

class IrrigationSession(Base):
    __tablename__ = 'irrigation_sessions'
    __table_args__ = {'extend_existing': True}

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    duration_minutes = Column(Float, nullable=True)
    water_used = Column(Float, default=0.0)
    source_tank_id = Column(String, ForeignKey('resources.id'))
    primary_pump_id = Column(String, ForeignKey('actuators.id'))
    status = Column(String, default="active")
    notes = Column(String, nullable=True)

    def __repr__(self):
        return f"<IrrigationSession(id='{self.id}', status='{self.status}', water_used={self.water_used})>"