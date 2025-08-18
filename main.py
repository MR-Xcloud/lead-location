import hashlib
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Body, status
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId # For MongoDB _id
from database import users_collection, meetings_collection # Import MongoDB collections
import gspread
from google.oauth2.service_account import Credentials
import os

print("[DEBUG] Starting FastAPI app initialization...")
app = FastAPI()

# Allow CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173","http://18.188.184.213:8040"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Google Sheets setup
SERVICE_ACCOUNT_FILE = "service_account.json"
SHEET_NAME = "Loan-Lead-Sheet"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
worksheet = None
try:
    print(f"[DEBUG] Attempting to load service account file: {SERVICE_ACCOUNT_FILE}")
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    print("[DEBUG] Service account loaded successfully.")
    gc = gspread.authorize(creds)
    print(f"[DEBUG] Attempting to open Google Sheet: {SHEET_NAME}")
    sh = gc.open(SHEET_NAME)
    worksheet = sh.sheet1
    print("[DEBUG] Google Sheet opened and worksheet loaded.")
except Exception as e:
    worksheet = None
    print(f"[ERROR] Google Sheets setup failed: {e}")


# --- Models ---
class UserInDB(BaseModel):
    id: str # Changed from PyObjectId to str for simpler handling with synchronous pymongo
    name: str
    email: str
    password: str

class MeetingEntry(BaseModel):
    userId: str
    customerName: str
    photo: str = ""
    meetingStartDate: str
    meetingStartTimestamp: str
    location: str
    address: str = ""
    source: str = ""
    phoneNumber: str = ""
    loanExpected: str = ""
    product: str = ""
    status: str = ""
    remark2: str = ""

class MeetingInDB(MeetingEntry):
    id: str # Changed from PyObjectId to str

print("[DEBUG] FastAPI app initialization complete. Ready for requests.")

# --- Signup Endpoint ---
@app.post("/signup", response_model=UserInDB)
def signup(payload: dict = Body(...)):
    name = payload.get("name")
    email = payload.get("email")
    password = payload.get("password")
    if not (name and email and password):
        raise HTTPException(status_code=400, detail="Missing fields")
    
    existing_user = users_collection.find_one({"email": email})
    if existing_user:
        raise HTTPException(status_code=409, detail="Email already registered")
    
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    user_data = {"name": name, "email": email, "password": hashed_password}
    
    result = users_collection.insert_one(user_data)
    new_user = users_collection.find_one({"_id": result.inserted_id})
    
    new_user["id"] = str(new_user["_id"])
    return UserInDB(**new_user)

# --- Login Endpoint ---
@app.post("/login", response_model=UserInDB)
def login(payload: dict = Body(...)):
    email = payload.get("email")
    password = payload.get("password")
    if not email:
        raise HTTPException(status_code=400, detail="Missing email")
    
    user_in_db = users_collection.find_one({"email": email})
    if not user_in_db:
        raise HTTPException(status_code=401, detail="User not found")
    
    if password:
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        if user_in_db["password"] != hashed_password:
            raise HTTPException(status_code=401, detail="Incorrect password")
    
    user_in_db["id"] = str(user_in_db["_id"])
    return UserInDB(**user_in_db)

# --- API Endpoints ---
@app.post("/meetings", response_model=MeetingInDB, status_code=status.HTTP_201_CREATED)
def add_meeting(entry: MeetingEntry):
    print("[DEBUG] Received POST /meetings request.")
    print(f"[DEBUG] Entry data: {entry}")
    
    meeting_data = entry.dict()
    
    try:
        # Save to MongoDB
        result = meetings_collection.insert_one(meeting_data)
        new_meeting = meetings_collection.find_one({"_id": result.inserted_id})
        
        print("[DEBUG] Meeting saved to MongoDB.")
        
        # Conditionally generate image URL
        image_url = ""
        if entry.photo: # Only generate URL if photo data exists
            image_url = f"http://localhost:8000/image/{str(new_meeting['_id'])}"
        
        # Save meeting info in Google Sheet, with image URL
        if worksheet is None:
            print("[ERROR] Worksheet is None. Google Sheet not available.")
            # Do not raise HTTPException here, allow MongoDB save to succeed
            # You might want to log this error more prominently or send a notification
        else:
            try:
                worksheet.append_row([
                    entry.userId, # UserId
                    entry.customerName, # Client Name
                    entry.meetingStartDate, # Date
                    entry.source, # Source
                    entry.customerName, # Customer Name (Duplicate, consider if needed)
                    entry.phoneNumber, # Phone Number
                    entry.location, # Customer Location
                    entry.product, # Product
                    entry.loanExpected, # Loan Expected
                    image_url, # Photo (will be empty string if no photo)
                    entry.status, # Remark1
                    entry.remark2 # Remark2
                ])
                print("[DEBUG] Row appended to Google Sheet.")
            except Exception as e:
                print(f"[ERROR] Failed to append row to Google Sheet: {e}")
                # Log the error but don't prevent MongoDB save from returning success
        
        new_meeting["id"] = str(new_meeting["_id"])
        return MeetingInDB(**new_meeting)
    except Exception as e:
        print(f"[ERROR] Exception while saving meeting: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/image/{meeting_id}")
def get_image(meeting_id: str):
    if not ObjectId.is_valid(meeting_id):
        raise HTTPException(status_code=400, detail="Invalid Meeting ID format.")

    meeting = meetings_collection.find_one({"_id": ObjectId(meeting_id)})
    
    if not meeting or not meeting.get("photo"):
        raise HTTPException(status_code=404, detail="Image not found")
    
    photo_data = meeting["photo"]
    
    # If photo is a URL, redirect
    if photo_data.startswith("http://") or photo_data.startswith("https://"):
        return RedirectResponse(photo_data)
    
    # Otherwise, assume base64 and show in HTML img tag
    try:
        img_src = f"{photo_data}"
        html = f"""
        <html><body style='margin:0;padding:0;text-align:center;background:#f8f8f8;'>
        <img src='{img_src}' style='max-width:90vw;max-height:90vh;border-radius:12px;box-shadow:0 2px 8px #0002;' />
        </body></html>
        """
        return HTMLResponse(content=html)
    except Exception:
        return HTMLResponse(content="<h2>Could not display image.</h2>")

@app.get("/meetings", response_model=List[MeetingInDB])
def get_meetings(userId: Optional[str] = None):
    print(f"[DEBUG] GET /meetings for userId={userId}")
    
    query = {}
    if userId:
        query["userId"] = userId
    
    meetings_cursor = meetings_collection.find(query)
    meetings_list = []
    for meeting in meetings_cursor:
        meeting["id"] = str(meeting["_id"])
        meetings_list.append(MeetingInDB(**meeting))
        
    return meetings_list

@app.get("/")
def root():
    return {"message": "Client Meeting Tracking Backend is running."}
