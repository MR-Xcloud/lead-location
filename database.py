from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")

if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable not set.")
if not DB_NAME:
    raise ValueError("DB_NAME environment variable not set.")

# Create a new client and connect to the server using the provided sample code structure
client = MongoClient(MONGO_URI, server_api=ServerApi('1'))

# Send a ping to confirm a successful connection (optional, can be done on startup)
try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(f"MongoDB connection ping failed: {e}")
    # Depending on severity, you might want to raise an exception here
    # For now, we'll let the app continue, but operations will fail if connection is truly bad.

db = client[DB_NAME]

# Collections
meetings_collection = db["meetings"]
users_collection = db["users"]

# No explicit index creation function here, as synchronous pymongo doesn't have a direct async startup hook.
# Indexes can be created manually or on first access if not critical for startup.
# For unique email, it's best to create it manually in MongoDB Atlas or ensure it's created on first user insert.
