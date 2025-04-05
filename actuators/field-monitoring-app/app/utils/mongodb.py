from motor.motor_asyncio import AsyncIOMotorClient
from bson.objectid import ObjectId

MONGO_URI = "mongodb://localhost:27017"  # Update with your MongoDB URI
DATABASE_NAME = "field_monitoring"

client = AsyncIOMotorClient(MONGO_URI)
db = client[DATABASE_NAME]

# Helper function to convert MongoDB ObjectId to string
def to_dict(document):
    document["_id"] = str(document["_id"])
    return document