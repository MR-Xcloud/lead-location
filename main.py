import hashlib
from datetime import datetime
from typing import Optional, List
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Body, status, Depends
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from bson import ObjectId # For MongoDB _id
from database import users_collection, meetings_collection # Import MongoDB collections
import gspread
from google.oauth2.service_account import Credentials
import os
import jwt # PyJWT

print("[DEBUG] Starting FastAPI app initialization...")
app = FastAPI()

# JWT settings
SECRET_KEY = os.getenv("SECRET_KEY", "your-super-secret-key") # Use environment variable for production
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440 # Increased to 24 hours for easier testing

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# Allow CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173","http://localhost:8041","http://18.188.184.213:8040","http://18.188.184.213:8041","https://staging.webmobrildemo.com/lead-location-frontend"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Google Sheets setup
SHEET_NAME = "Loan-Lead-Sheet"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
worksheet = None

try:
    print("[DEBUG] Loading service account from file")
    SERVICE_ACCOUNT_FILE = "service_account.json"
    # print("p9-9=----------===============",SERVICE_ACCOUNT_FILE)
    
    # Check if file exists
    import os
    print(f"[DEBUG] Current working directory: {os.getcwd()}")
    print(f"[DEBUG] Files in current directory: {os.listdir('.')}")
    
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        print(f"[ERROR] Service account file not found: {SERVICE_ACCOUNT_FILE}")
        raise FileNotFoundError(f"Service account file not found: {SERVICE_ACCOUNT_FILE}")
    
    if os.path.isdir(SERVICE_ACCOUNT_FILE):
        print(f"[ERROR] {SERVICE_ACCOUNT_FILE} is a directory, not a file!")
        print("[ERROR] This usually happens when Docker COPY fails")
        raise ValueError(f"{SERVICE_ACCOUNT_FILE} is a directory, not a file")
    
    print(f"[DEBUG] Service account file found: {SERVICE_ACCOUNT_FILE}")
    
    # Read and fix the service account JSON
    import json
    with open(SERVICE_ACCOUNT_FILE, 'r') as f:
        service_account_info = json.load(f)
        print(f"[DEBUG] Private Key ID: {service_account_info.get('private_key_id', 'NOT_FOUND')}")
        print(f"[DEBUG] Client Email: {service_account_info.get('client_email', 'NOT_FOUND')}")
    
    # Fix the private key formatting - replace literal \n with actual newlines
    if 'private_key' in service_account_info:
        original_key = service_account_info['private_key']
        fixed_key = original_key.replace('\\n', '\n')
        service_account_info['private_key'] = fixed_key
        print(f"[DEBUG] Private key formatting fixed. Original length: {len(original_key)}, Fixed length: {len(fixed_key)}")
        print(f"[DEBUG] Private key starts with: {fixed_key[:50]}...")
    
    # Create credentials from the fixed JSON
    creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
    
    print("[DEBUG] Service account loaded successfully.")
    
    # Test the credentials with a simple API call
    try:
        print("[DEBUG] Testing credentials with Google Sheets API...")
        gc = gspread.authorize(creds)
        print("[DEBUG] GSpread authorization successful")
        
        # Try to list available spreadsheets first
        available_sheets = gc.openall()
        print(f"[DEBUG] Found {len(available_sheets)} available spreadsheets")
        
        # Print all available sheet names for debugging
        if len(available_sheets) > 0:
            print("[DEBUG] Available sheet names:")
            for sheet in available_sheets:
                print(f"  - {sheet.title}")
        else:
            print("[DEBUG] No sheets available - service account needs access")
        
        print(f"[DEBUG] Attempting to open Google Sheet: {SHEET_NAME}")
        sh = gc.open(SHEET_NAME)
        worksheet = sh.sheet1
        print("[DEBUG] Google Sheet opened and worksheet loaded.")
    except Exception as e:
        print(f"[ERROR] Failed to access Google Sheets: {e}")
        raise e
except Exception as e:
    worksheet = None
    print(f"[ERROR] Google Sheets setup failed: {e}")
    import traceback
    print(f"[ERROR] Full traceback: {traceback.format_exc()}")


# --- Models ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class UserInDB(BaseModel):
    id: str
    name: str
    email: str
    password: str

class MeetingEntry(BaseModel):
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
@app.post("/login", response_model=Token)
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
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user_in_db["email"], "name": user_in_db["name"]}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# --- JWT Utility Functions ---
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(token: str = Depends(oauth2_scheme)):
    print(f"[DEBUG] get_current_user called. Received token: {token[:30]}...") # Print first 30 chars
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        print(f"[DEBUG] Token decoded. Payload: {payload}")
        email: str = payload.get("sub")
        if email is None:
            print("[DEBUG] Email (sub) not found in token payload.")
            raise credentials_exception
        token_data = TokenData(email=email)
        print(f"[DEBUG] Extracted email from token: {email}")
    except jwt.ExpiredSignatureError:
        print("[ERROR] Token has expired.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        print(f"[ERROR] Invalid token: {e}")
        raise credentials_exception
    except Exception as e:
        print(f"[ERROR] Unexpected error during token decoding: {e}")
        raise credentials_exception
        
    user = users_collection.find_one({"email": token_data.email})
    if user is None:
        print(f"[DEBUG] User not found in DB for email: {token_data.email}")
        raise credentials_exception
    print(f"[DEBUG] User found in DB: {user['email']}")
    user["id"] = str(user["_id"])
    return UserInDB(**user)

# --- API Endpoints ---
@app.post("/meetings", response_model=MeetingInDB, status_code=status.HTTP_201_CREATED)
def add_meeting(entry: MeetingEntry, current_user: UserInDB = Depends(get_current_user)):
    print("[DEBUG] Received POST /meetings request.")
    # print(f"[DEBUG] Entry data: {entry}")
    
    meeting_data = entry.dict()
    meeting_data["userid"] = current_user.id # Add userid from authenticated user
    
    try:
        # Save to MongoDB
        result = meetings_collection.insert_one(meeting_data)
        new_meeting = meetings_collection.find_one({"_id": result.inserted_id})
        
        print("[DEBUG] Meeting saved to MongoDB.")
        
        # Conditionally generate image URL
        image_url = ""
        if entry.photo: # Only generate URL if photo data exists
            image_url = f"https://staging.webmobrildemo.com/loan-lead-backend/image/{str(new_meeting['_id'])}"
        
        # Save meeting info in Google Sheet, with image URL
        if worksheet is None:
            print("[INFO] Google Sheets integration not available - meeting saved to MongoDB only")
            print("[INFO] This could be due to missing service_account.json or sheet access issues")
        else:
            try:
                worksheet.append_row([
                    current_user.name, # User's Name (from authenticated user)
                    entry.customerName, # Client Name
                    entry.meetingStartDate, # Date
                    entry.source, # Source
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
def get_meetings(current_user: UserInDB = Depends(get_current_user)):
    print(f"[DEBUG] GET /meetings for user: {current_user.email}")
    
    # Always filter by the authenticated user's ID
    query = {"userid": current_user.id}
    
    meetings_cursor = meetings_collection.find(query)
    meetings_list = []
    for meeting in meetings_cursor:
        meeting["id"] = str(meeting["_id"])
        meetings_list.append(MeetingInDB(**meeting))
        
    return meetings_list

@app.get("/")
def root():
    return {"message": "Client Meeting Tracking Backend is running."}
