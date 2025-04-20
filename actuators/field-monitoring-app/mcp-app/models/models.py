from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, JSON, create_engine, Table, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.sql import func

Base = declarative_base()

# Association tables remain the same
field_resource_association = Table(
    'field_resource_association', Base.metadata,
    Column('field_id', String, ForeignKey('fields.id')),
    Column('resource_id', String, ForeignKey('resources.id'))
)

actuator_resource_association = Table(
    'actuator_resource_association', Base.metadata,
    Column('actuator_id', String, ForeignKey('actuators.id')),
    Column('resource_id', String, ForeignKey('resources.id'))
)

pump_valve_association = Table(
    'pump_valve_association', Base.metadata,
    Column('pump_id', String, ForeignKey('actuators.id')),
    Column('valve_id', String, ForeignKey('actuators.id'))
)

# Farm and Field models remain unchanged
class Farm(Base):
    __tablename__ = 'farm'
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    address = Column(String)
    gps_lat = Column(Float)
    gps_long = Column(Float)
    total_area = Column(String)
    created_at = Column(DateTime, default=func.now())
    modified_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    fields = relationship("Field", back_populates="farm", lazy="joined")
    
    def to_dict(self, include_related=True):
        result = {
            "id": self.id,
            "name": self.name,
            "address": self.address,
            "gps": {"lat": self.gps_lat, "long": self.gps_long},
            "total_area": self.total_area,
            "created_at": self.created_at,
            "modified_at": self.modified_at
        }
        
        if include_related:
            result.update({
                "fields": [field.to_dict(include_related=True) for field in self.fields]
            })
        
        return result

class Field(Base):
    __tablename__ = 'fields'
    
    id = Column(String, primary_key=True)
    farm_id = Column(String, ForeignKey('farm.id'))
    name = Column(String, nullable=False)
    crop = Column(String)
    area = Column(String)
    boundary_gps = Column(JSON)
    created_at = Column(DateTime, default=func.now())
    modified_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    farm = relationship("Farm", back_populates="fields")
    sensors = relationship("Sensor", back_populates="field", lazy="joined")
    actuators = relationship("Actuator", back_populates="field", lazy="joined")
    resources = relationship("Resource", secondary=field_resource_association, back_populates="fields", lazy="joined")
    
    def to_dict(self, include_related=True):
        result = {
            "id": self.id,
            "name": self.name,
            "crop": self.crop,
            "area": self.area,
            "boundary_gps": self.boundary_gps,
            "farm_id": self.farm_id,
            "created_at": self.created_at,
            "modified_at": self.modified_at
        }
        
        if include_related:
            result.update({
                "sensors": [sensor.to_dict(include_related=False) for sensor in self.sensors],
                "actuators": [actuator.to_dict(include_related=False) for actuator in self.actuators],
                "resources": [resource.to_dict(include_related=False) for resource in self.resources]
            })
        
        return result

class Sensor(Base):
    __tablename__ = 'sensors'
    
    id = Column(String, primary_key=True)
    thingsboard_id = Column(String, nullable=True)
    field_id = Column(String, ForeignKey('fields.id'))
    type = Column(String, nullable=False)
    status = Column(String)
    unit = Column(String)
    gps_lat = Column(Float)
    gps_long = Column(Float)
    created_at = Column(DateTime, default=func.now())
    modified_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    field = relationship("Field", back_populates="sensors")
    
    def to_dict(self, include_related=True):
        result = {
            "id": self.id,
            "thingsboard_id": self.thingsboard_id,
            "field_id": self.field_id,
            "type": self.type,
            "status": self.status,
            "unit": self.unit,
            "gps": {"lat": self.gps_lat, "long": self.gps_long},
            "created_at": self.created_at,
            "modified_at": self.modified_at
        }
        
        if include_related and self.field:
            result.update({
                "field": {"id": self.field.id, "name": self.field.name}
            })
        
        return result

class Actuator(Base):
    __tablename__ = 'actuators'
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    thingsboard_id = Column(String, nullable=True)
    field_id = Column(String, ForeignKey('fields.id'))
    type = Column(String, nullable=False)
    subtype = Column(String)
    operation_type = Column(String)
    status = Column(String)
    # Changed from String to Float to properly handle flow rate calculations
    base_speed = Column(JSON)  
    # Added to track when the actuator was last opened or closed
    last_state_change = Column(DateTime)
    created_at = Column(DateTime, default=func.now())
    modified_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    field = relationship("Field", back_populates="actuators")
    resources = relationship("Resource", secondary=actuator_resource_association, back_populates="actuators", lazy="joined")
    linked_valves = relationship(
        "Actuator", 
        secondary=pump_valve_association,
        primaryjoin=id==pump_valve_association.c.pump_id,
        secondaryjoin=id==pump_valve_association.c.valve_id,
        backref="linked_pumps",
        lazy="joined"
    )
    
    def to_dict(self, include_related=True):
        result = {
            "id": self.id,
            "thingsboard_id": self.thingsboard_id,
            "field_id": self.field_id,
            "name": self.name,
            "type": self.type,
            "subtype": self.subtype,
            "operation_type": self.operation_type,
            "status": self.status,
            "base_speed": self.base_speed,
            "last_state_change": self.last_state_change,
            "created_at": self.created_at,
            "modified_at": self.modified_at
        }
        
        if include_related:
            result.update({
                "resources": [{"id": resource.id, "name": resource.name} for resource in self.resources],
                "linked_valves": [{"id": valve.id, "name": valve.name} for valve in self.linked_valves],
                "linked_pumps": [{"id": pump.id, "name": pump.name} for pump in self.linked_pumps] if hasattr(self, 'linked_pumps') else []
            })
        
        return result

class Resource(Base):
    __tablename__ = 'resources'
    
    id = Column(String, primary_key=True)
    farm_id = Column(String, ForeignKey('farm.id'))
    field_id = Column(String, ForeignKey('fields.id'))
    thingsboard_id = Column(String, nullable=True)
    name = Column(String, nullable=False)
    # Changed from String to Float for numerical operations
    capacity = Column(JSON, nullable=True)  
    current_level = Column(JSON, nullable=True)
    content = Column(String)
    created_at = Column(DateTime, default=func.now())
    modified_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    field = relationship("Field", back_populates="resources")
    fields = relationship("Field", secondary=field_resource_association, back_populates="resources")
    actuators = relationship("Actuator", secondary=actuator_resource_association, back_populates="resources", lazy="joined")
    
    def to_dict(self, include_related=True):
        result = {
            "id": self.id,
            "thingsboard_id": self.thingsboard_id,
            "field_id": self.field_id,
            "farm_id": self.farm_id,
            "name": self.name,
            "capacity": self.capacity,
            "current_level": self.current_level,
            "content": self.content,
            "created_at": self.created_at,
            "modified_at": self.modified_at
        }
        
        if include_related:
            result.update({
                "actuators": [{"id": actuator.id, "name": actuator.name, "type": actuator.type} for actuator in self.actuators]
            })
        
        return result
    
# Database initialization function
def init_db(db_path="farm_control.db"):
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    return engine

# Create session factory
def get_session_factory(engine):
    return sessionmaker(bind=engine)