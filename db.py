import os
import logging
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from dotenv import load_dotenv


# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Get MongoDB URI from environment variables
uri = os.getenv("MONGO_URI")
if not uri:
    raise ValueError("MONGO_URI is not set. Check your .env file.")

# Create a new client and connect to the server
client = MongoClient(uri, server_api=ServerApi('1'))
db = client["auto_emailer"]



# Ping MongoDB to check connection
try:
    client.admin.command('ping')
    logging.info("Connected to MongoDB Atlas successfully!")
except Exception as e:
    logging.error(f"MongoDB connection error: {e}")
    raise ConnectionError("Failed to connect to MongoDB Atlas.")


# Function to get the database
def get_database():
    return db
