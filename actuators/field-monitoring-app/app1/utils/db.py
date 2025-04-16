from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# SQLALCHEMY_DATABASE_URL = "sqlite:///./control_db.db"  # SQLite database file
SQLALCHEMY_DATABASE_URL = "sqlite:///./control_farm_db.db"  # SQLite database file

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
def initialize_database():
    """Create the database and tables if they don't exist."""
    Base.metadata.create_all(bind=engine)
