from sqlalchemy import Column, String, Float, ForeignKey, Table, JSON
from sqlalchemy.orm import relationship
from app.utils.db import Base

class Sensor(Base):
    __tablename__ = 'sensors'

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False, unique=True)  # Name of the sensor
    type = Column(String, nullable=False)  # Type of the sensor
    unit = Column(String, nullable=True)  # Unit of measurement
    threshold = Column(Float, nullable=True)  # Threshold value for triggering actions
    label = Column(String, nullable=True)  # Label for the sensor
    additionalInfo = Column(JSON, nullable=True)  # Additional information about the sensor as a JSON field

    # Many-to-many relationship with actuators
    actuators = relationship("Actuator", secondary="actuator_sensor", back_populates="sensors")

    def __repr__(self):
        return f"<Sensor(id={self.id}, name={self.name}, type={self.type}, unit={self.unit}, threshold={self.threshold})>"