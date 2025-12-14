import os
import json
import requests
from typing import List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import google.generativeai as genai
from route import solve_route

# 1. SETUP
load_dotenv()
ORS_API_KEY = os.getenv("ORS_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is missing")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

app = FastAPI(title="AI Logistics Optimizer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. UPDATED DATA MODELS
class LogisticsQuery(BaseModel):
    request_text: str 

class LocationPoint(BaseModel):
    name: str
    lat: float
    lon: float
    visit_sequence: int 

class RouteResponse(BaseModel):
    parsed_locations: List[LocationPoint]

# 3. HELPER: GEOCODING 
def get_coords_from_ors(location_name: str):
    try:
        url = f"https://api.openrouteservice.org/geocode/search?api_key={ORS_API_KEY}&text={location_name}"
        r = requests.get(url)
        if r.status_code == 200:
            data = r.json()
            if data['features']:
                coords = data['features'][0]['geometry']['coordinates']
                return coords[1], coords[0] # lat, lon
    except Exception as e:
        print(f"Geocoding error: {e}")
    return None, None

# 4. CORE AI LOGIC: SEQUENCE EXTRACTION
def parse_logistics_intent(text: str):
    prompt = f"""
    You are a Logistics Dispatcher. Analyze this request: "{text}"
    
    Task:
    1. Identify all locations.
    2. Determine the VISITING ORDER / SEQUENCE.
       - Source City: Always assign visit_sequence = 1.
       - Fixed Destination (e.g. "end at Mumbai"): Assign highest sequence (e.g., 10).
       - Intermediate Stops:
         * If the user says "then", "after", "first", "second": Assign increasing sequence numbers (2, 3, 4...).
         * If the user just lists cities ("visit A, B, and C"): Assign the SAME sequence number to all of them (e.g., all are 2).
    
    Return a raw JSON array. Each object must have:
    - "location_name": str
    - "visit_sequence": int (1-based index)
    
    Do not use markdown. Return only JSON.
    """
    
    try:
        response = model.generate_content(prompt)
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)
    except Exception as e:
        print(f"LLM Parsing failed: {e}")
        return []

@app.post("/extract-sequence", response_model=RouteResponse)
async def extract_sequence(query: LogisticsQuery):
    extracted_data = parse_logistics_intent(query.request_text)
    
    if not extracted_data:
        raise HTTPException(status_code=400, detail="No locations found in text.")

    final_locations = []
    
    for item in extracted_data:
        lat, lon = get_coords_from_ors(item["location_name"])
        
        if lat and lon:
            final_locations.append(LocationPoint(
                name=item["location_name"],
                lat=lat,
                lon=lon,
                visit_sequence=item.get("visit_sequence", 999),
            ))
            
    final_locations.sort(key=lambda x: x.visit_sequence)

    return RouteResponse(parsed_locations=final_locations)

@app.post("/optimize-route")
async def optimize_route(data: RouteResponse):
    """
    Takes the output of /extract-sequence and runs the GA
    """
    locations_list = [loc.dict() for loc in data.parsed_locations]    
    result = solve_route(locations_list)
    return result