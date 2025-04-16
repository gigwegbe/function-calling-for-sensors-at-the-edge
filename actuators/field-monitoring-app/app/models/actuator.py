# from sqlalchemy import Column, Boolean, String, Table, ForeignKey, DateTime
# from sqlalchemy.orm import relationship
# from app.utils.db import Base
# from sqlalchemy.dialects.postgresql import JSON
# from datetime import datetime

# # Association table for many-to-many relationship
# actuator_sensor_association = Table(
#     'actuator_sensor',
#     Base.metadata,
#     Column('actuator_id', ForeignKey('actuators.id'), primary_key=True),
#     Column('sensor_id', ForeignKey('sensors.id'), primary_key=True)
# )

# # Association table for many-to-many relationship between actuators and resources
# actuator_resource_association = Table(
#     'actuator_resource',
#     Base.metadata,
#     Column('actuator_id', ForeignKey('actuators.id'), primary_key=True),
#     Column('resource_id', ForeignKey('resources.id'), primary_key=True)
# )

# class Actuator(Base):
#     __tablename__ = 'actuators'
    
#     id = Column(String, primary_key=True)
#     state = Column(Boolean, default=False)  # ON/OFF state
#     name = Column(String, nullable=False, unique=True)  # Name of the actuator
#     type = Column(String, nullable=False)  # Type of the actuator
#     label = Column(String, nullable=True)
#     additionalInfo = Column(JSON, nullable=True)  # Additional information about the actuator as a JSON field
    
#     # New fields for monitoring state
#     monitoring_active = Column(Boolean, default=True)  # Whether monitoring is active
#     last_state_change = Column(DateTime, default=datetime.utcnow)  # When the state was last changed
#     last_monitoring_change = Column(DateTime, default=datetime.utcnow)  # When monitoring was last toggled
#     resources = relationship("Resource", secondary=actuator_resource_association, back_populates="actuators")
    
    
#     # Many-to-many relationship with sensors
#     sensors = relationship("Sensor", secondary=actuator_sensor_association, back_populates="actuators")
    
#     def __repr__(self):
#         return f"<Actuator(id='{self.id}', name='{self.name}', state={self.state}, monitoring_active={self.monitoring_active})>"