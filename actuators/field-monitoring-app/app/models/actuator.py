from sqlalchemy import Column, Boolean, String, Table, ForeignKey
from sqlalchemy.orm import relationship
from app.utils.db import Base
from sqlalchemy.dialects.postgresql import JSON

# Association table for many-to-many relationship
actuator_sensor_association = Table(
    'actuator_sensor',
    Base.metadata,
    Column('actuator_id', ForeignKey('actuators.id'), primary_key=True),
    Column('sensor_id', ForeignKey('sensors.id'), primary_key=True)
)

class Actuator(Base):
    __tablename__ = 'actuators'

    id = Column(String, primary_key=True)
    state = Column(Boolean, default=False)  # ON/OFF state
    name = Column(String, nullable=False, unique=True)  # Name of the actuator
    type = Column(String, nullable=False)  # Type of the actuator
    label = Column(String, nullable=True)
    additionalInfo = Column(JSON, nullable=True)  # Additional information about the actuator as a JSON field

    # Many-to-many relationship with sensors
    sensors = relationship("Sensor", secondary=actuator_sensor_association, back_populates="actuators")

    def __repr__(self):
        return f"<Actuator(id={self.id}, name={self.name}, type={self.type}, state={self.state}, label={self.label})>"