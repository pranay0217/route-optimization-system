import os
import requests
import folium
from folium.plugins import HeatMap
from dotenv import load_dotenv
from typing import List, Dict, Tuple, Optional
import time
import math

load_dotenv()
TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY")

TOMTOM_BASE_URL = "https://api.tomtom.com"
TOMTOM_TRAFFIC_FLOW_VERSION = "4"  

def get_route_bbox(locations: List[Dict]) -> Tuple[float, float, float, float]:
    """
    Calculate bounding box for a list of locations.
    
    Args:
        locations: List of dicts with 'lat' and 'lon' keys
        
    Returns:
        Tuple of (min_lon, min_lat, max_lon, max_lat)
    """
    if not locations:
        return (0, 0, 0, 0)
    
    lats = [loc['lat'] for loc in locations]
    lons = [loc['lon'] for loc in locations]
    
    buffer = 0.1
    return (
        min(lons) - buffer,
        min(lats) - buffer,
        max(lons) + buffer,
        max(lats) + buffer
    )

def fetch_traffic_flow_segment(lat: float, lon: float, zoom: int = 10) -> Optional[Dict]:
    """
    Fetch traffic flow data for a specific point using TomTom Traffic Flow Segment Data.
    
    API Endpoint: Traffic Flow Segment Data
    Documentation: https://developer.tomtom.com/traffic-api/documentation/traffic-flow/flow-segment-data
    
    Args:
        lat: Latitude of the point
        lon: Longitude of the point
        zoom: Zoom level (0-22, where 10 is typical city view)
        
    Returns:
        Traffic flow data or None if request fails
    """
    if not TOMTOM_API_KEY:
        print("[Traffic] Warning: TOMTOM_API_KEY not configured")
        return None
    
    url = f"{TOMTOM_BASE_URL}/traffic/services/{TOMTOM_TRAFFIC_FLOW_VERSION}/flowSegmentData/relative/{zoom}/json"
    
    params = {
        "key": TOMTOM_API_KEY,
        "point": f"{lat},{lon}",
        "unit": "KMPH"  # Speed unit
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"[Traffic] TomTom API error for point ({lat}, {lon}): {e}")
        return None

def fetch_traffic_incidents(bbox: Tuple[float, float, float, float]) -> Optional[Dict]:
    """
    Fetch traffic incidents (accidents, road closures) in a bounding box.
    
    API Endpoint: Traffic Incidents
    Documentation: https://developer.tomtom.com/traffic-api/documentation/traffic-incidents/incident-details
    
    Args:
        bbox: Bounding box (min_lon, min_lat, max_lon, max_lat)
        
    Returns:
        Traffic incidents data or None if request fails
    """
    if not TOMTOM_API_KEY:
        return None
    
    min_lon, min_lat, max_lon, max_lat = bbox
    
    # TomTom Incident Details API
    # Format: /traffic/services/{versionNumber}/incidentDetails
    url = f"{TOMTOM_BASE_URL}/traffic/services/5/incidentDetails"
    
    params = {
        "key": TOMTOM_API_KEY,
        "bbox": f"{min_lon},{min_lat},{max_lon},{max_lat}",
        "fields": "{incidents{type,geometry{type,coordinates},properties{id,iconCategory,magnitudeOfDelay,events{description,code},startTime,endTime}}}",
        "language": "en-US"
    }
    
    try:
        response = requests.get(url, params=params, timeout=10) 
        # if response.status_code == 400:
        #     print(f"TomTom Detail: {response.text}")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"[Traffic] TomTom Incidents API error: {e}")
        return None

# def fetch_all_incidents_dynamic(bbox: Tuple[float, float, float, float]) -> Dict:
#     """
#     Dynamically subdivides the bbox into tiles smaller than 10,000 km^2.
#     """
#     min_lon, min_lat, max_lon, max_lat = bbox
    
#     # 1. Calculate approximate dimensions in kilometers
#     # 1 degree lat is ~111km. 1 degree lon at 27 deg N is ~99km.
#     width_km = abs(max_lon - min_lon) * 99 
#     height_km = abs(max_lat - min_lat) * 111
#     total_area = width_km * height_km
    
#     MAX_ALLOWED_AREA = 9500  # Safety margin under 10,000
    
#     # 2. Determine grid size
#     if total_area <= MAX_ALLOWED_AREA:
#         grid_x = grid_y = 1
#     else:
#         # Calculate how many tiles we need to cover the area
#         ratio = math.ceil(math.sqrt(total_area / MAX_ALLOWED_AREA))
#         grid_x = ratio # Number of horizontal splits
#         grid_y = ratio # Number of vertical splits

#     all_incidents = []
#     seen_ids = set()
    
#     lon_step = (max_lon - min_lon) / grid_x
#     lat_step = (max_lat - min_lat) / grid_y

#     for i in range(grid_x):
#         for j in range(grid_y):
#             tile_bbox = (
#                 min_lon + (i * lon_step),
#                 min_lat + (j * lat_step),
#                 min_lon + ((i + 1) * lon_step),
#                 min_lat + ((j + 1) * lat_step)
#             )
            
#             data = fetch_traffic_incidents(tile_bbox)            
#             if data and 'incidents' in data:
#                 for incident in data['incidents']:
#                     inc_id = incident.get('properties', {}).get('id')
#                     if inc_id not in seen_ids:
#                         all_incidents.append(incident)
#                         seen_ids.add(inc_id)
            
#             time.sleep(0.2)
            
#     return {"incidents": all_incidents}

def fetch_incidents_for_route_stops(locations: List[Dict], buffer: float = 0.4) -> Dict:
    """
    Fetches incidents specifically around each stop on the route.
    
    Args:
        locations: List of dicts with 'lat' and 'lon'
        buffer: Size in degrees around each point
        
    Returns:
        Combined incidents dictionary
    """
    all_combined_incidents = []
    seen_ids = set()

    print(f"[Traffic] Fetching incidents for {len(locations)} stop areas...")

    for loc in locations:
        lat, lon = loc['lat'], loc['lon']
        stop_bbox = (
            lon - buffer, 
            lat - buffer, 
            lon + buffer, 
            lat + buffer  
        )
        
        data = fetch_traffic_incidents(stop_bbox)
        
        if data and 'incidents' in data:
            for incident in data['incidents']:
                incident_id = incident.get('properties', {}).get('id')
                if incident_id not in seen_ids:
                    all_combined_incidents.append(incident)
                    seen_ids.add(incident_id)
        
        time.sleep(0.2)

    return {"incidents": all_combined_incidents}

def analyze_traffic_flow(flow_data: Dict) -> Dict:
    """
    Analyze traffic flow data to determine congestion level.
    
    Args:
        flow_data: Raw traffic flow data from TomTom API
        
    Returns:
        Analysis with congestion level and metrics
    """
    if not flow_data or 'flowSegmentData' not in flow_data:
        return {
            "congestion_level": "unknown",
            "current_speed": 0,
            "free_flow_speed": 0,
            "delay_factor": 0,
            "confidence": 0
        }
    
    segment = flow_data['flowSegmentData']
    
    # Extract metrics
    current_speed = segment.get('currentSpeed', 0)
    free_flow_speed = segment.get('freeFlowSpeed', 50) 
    current_travel_time = segment.get('currentTravelTime', 0)
    free_flow_travel_time = segment.get('freeFlowTravelTime', 0)
    confidence = segment.get('confidence', 0)
    
    # delay_factor: 0 = no delay, 1+ = delayed
    if free_flow_travel_time > 0:
        delay_factor = current_travel_time / free_flow_travel_time
    elif free_flow_speed > 0:
        delay_factor = free_flow_speed / max(current_speed, 1)
    else:
        delay_factor = 0
    
    # Calculate speed ratio (0-1, where 1 is free flow)
    speed_ratio = current_speed / max(free_flow_speed, 1)
    
    # Determine congestion level based on speed ratio
    if speed_ratio >= 0.8:
        congestion_level = "free_flow"
        color = "green"
    elif speed_ratio >= 0.6:
        congestion_level = "light"
        color = "yellow"
    elif speed_ratio >= 0.4:
        congestion_level = "moderate"
        color = "orange"
    elif speed_ratio >= 0.2:
        congestion_level = "heavy"
        color = "red"
    else:
        congestion_level = "severe"
        color = "darkred"
    
    return {
        "congestion_level": congestion_level,
        "color": color,
        "current_speed": current_speed,
        "free_flow_speed": free_flow_speed,
        "speed_ratio": speed_ratio,
        "delay_factor": delay_factor,
        "confidence": confidence,
        "coordinates": segment.get('coordinates', {})
    }

def collect_traffic_data_for_route(locations: List[Dict]) -> Tuple[List, Dict]:
    """
    Collect traffic data for all segments in a route.
    
    Args:
        locations: List of location dicts with 'lat', 'lon', 'name'
        
    Returns:
        Tuple of (heatmap_data, analysis_summary)
    """
    heatmap_data = []
    segment_analyses = []
    total_delays = 0
    severe_segments = 0
    
    print(f"[Traffic] Collecting traffic data for {len(locations)} locations...")
    
    for i, location in enumerate(locations):
        # Get traffic at this point
        flow_data = fetch_traffic_flow_segment(location['lat'], location['lon'])
        
        if flow_data:
            analysis = analyze_traffic_flow(flow_data)
            
            # Add to heatmap
            # Intensity: 0 (green/free flow) to 1 (red/severe)
            intensity = 1 - analysis['speed_ratio']
            heatmap_data.append([
                location['lat'],
                location['lon'],
                intensity
            ])
            
            # Track severe segments
            if analysis['congestion_level'] in ['heavy', 'severe']:
                severe_segments += 1
            
            total_delays += analysis['delay_factor']
            
            segment_analyses.append({
                "location": location['name'],
                "congestion": analysis['congestion_level'],
                "current_speed": analysis['current_speed'],
                "delay_factor": round(analysis['delay_factor'], 2)
            })
        
        time.sleep(0.2)
    
    # Calculate overall status
    avg_delay = total_delays / len(locations) if locations else 0
    
    if severe_segments > len(locations) * 0.3:
        overall_status = "Severe"
    elif severe_segments > len(locations) * 0.15:
        overall_status = "Moderate"
    else:
        overall_status = "Normal"
    
    analysis_summary = {
        "overall_status": overall_status,
        "total_segments": len(locations),
        "severe_segments": severe_segments,
        "average_delay_factor": round(avg_delay, 2),
        "segment_details": segment_analyses
    }
    
    return heatmap_data, analysis_summary

def generate_traffic_map(locations: List[Dict], route_sequence: Optional[List[Dict]] = None) -> Dict:
    """
    Generate an interactive HTML map with traffic conditions.
    
    Args:
        locations: List of location dicts with 'name', 'lat', 'lon'
        route_sequence: Optional ordered sequence for route visualization
        
    Returns:
        Dict with map_file path, congestion status, and details
    """
    if not locations:
        return {
            "map_file": None,
            "congestion_status": "unknown",
            "details": "No locations provided"
        }
        
    avg_lat = sum(loc['lat'] for loc in locations) / len(locations)
    avg_lon = sum(loc['lon'] for loc in locations) / len(locations)
    bbox = get_route_bbox(locations)
    
    heatmap_data, analysis_summary = collect_traffic_data_for_route(locations)
    incidents_data = fetch_incidents_for_route_stops(locations, buffer=0.4)    
    
    m = folium.Map(
        location=[avg_lat, avg_lon],
        zoom_start=8,
        tiles='OpenStreetMap'
    )
    
    # Add traffic heatmap layer
    if heatmap_data:
        HeatMap(
            heatmap_data,
            min_opacity=0.3,
            max_opacity=0.8,
            radius=15,
            blur=20,
            gradient={
                0.0: 'green',    # Free flow
                0.25: 'yellow',  # Light traffic
                0.5: 'orange',   # Moderate traffic
                0.75: 'red',     # Heavy traffic
                1.0: 'darkred'   # Severe congestion
            }
        ).add_to(m)
    
    for i, loc in enumerate(locations):
        if i < len(analysis_summary['segment_details']):
            segment = analysis_summary['segment_details'][i]
            congestion = segment['congestion']
            
            if congestion in ['severe', 'heavy']:
                marker_color = 'red'
                icon = 'exclamation-triangle'
            elif congestion == 'moderate':
                marker_color = 'orange'
                icon = 'exclamation-circle'
            else:
                marker_color = 'green'
                icon = 'check-circle'
            
            popup_html = f"""
            <div style='min-width: 200px'>
                <h4><b>{loc['name']}</b></h4>
                <p><b>Status:</b> {congestion.upper()}</p>
                <p><b>Current Speed:</b> {segment['current_speed']} km/h</p>
                <p><b>Delay Factor:</b> {segment['delay_factor']}x</p>
            </div>
            """
        else:
            marker_color = 'blue'
            icon = 'info-sign'
            popup_html = f"<b>{loc['name']}</b><br>Stop #{i+1}"
        
        folium.Marker(
            location=[loc['lat'], loc['lon']],
            popup=folium.Popup(popup_html, max_width=250),
            icon=folium.Icon(
                color=marker_color,
                icon=icon,
                prefix='fa'
            ),
            tooltip=f"{i+1}. {loc['name']}"
        ).add_to(m)
    
    if route_sequence:
        points = [[loc['lat'], loc['lon']] for loc in route_sequence]
        folium.PolyLine(
            points,
            color='blue',
            weight=3,
            opacity=0.7,
            popup='Planned Route'
        ).add_to(m)
    
    # Add traffic incidents as markers
    if incidents_data and 'incidents' in incidents_data:
        incident_count = 0
        for incident in incidents_data['incidents']:
            try:
                # Extract incident details
                props = incident.get('properties', {})
                geometry = incident.get('geometry', {})
                
                if geometry.get('type') == 'Point':
                    coords = geometry.get('coordinates', [])
                    if len(coords) >= 2:
                        # TomTom uses [lon, lat] format
                        incident_lat, incident_lon = coords[1], coords[0]
                        
                        # Get incident type
                        icon_category = props.get('iconCategory', 0)
                        magnitude = props.get('magnitudeOfDelay', 0)
                        
                        # Determine icon and color
                        if icon_category in [1, 2, 3]:  # Accident
                            icon = 'car-crash'
                            color = 'red'
                        elif icon_category in [4, 5]:  # Road closure
                            icon = 'ban'
                            color = 'darkred'
                        else:
                            icon = 'exclamation'
                            color = 'orange'
                        
                        # Get description
                        events = props.get('events', [])
                        description = events[0].get('description', 'Traffic incident') if events else 'Traffic incident'
                        
                        folium.Marker(
                            location=[incident_lat, incident_lon],
                            popup=f"<b>INCIDENT</b><br>{description}<br>Delay: {magnitude} min",
                            icon=folium.Icon(color=color, icon=icon, prefix='fa'),
                            tooltip="Traffic Incident"
                        ).add_to(m)
                        
                        incident_count += 1
            except Exception as e:
                print(f"[Traffic] Error processing incident: {e}")
                continue
        
        print(f"[Traffic] Added {incident_count} traffic incidents to map")
    
    # Add legend
    legend_html = '''
    <div style="position: fixed; 
                bottom: 50px; left: 50px; width: 220px; height: auto; 
                background-color: white; z-index:9999; font-size:14px;
                border:2px solid grey; border-radius: 5px; padding: 10px">
        <p style="margin:0; font-weight:bold; text-align:center">Traffic Status Legend</p>
        <hr style="margin: 5px 0">
        <p style="margin:3px 0"><span style="color:green">●</span> Free Flow / Light</p>
        <p style="margin:3px 0"><span style="color:orange">●</span> Moderate Traffic</p>
        <p style="margin:3px 0"><span style="color:red">●</span> Heavy Congestion</p>
        <p style="margin:3px 0"><span style="color:darkred">●</span> Severe / Blocked</p>
        <hr style="margin: 5px 0">
        <p style="margin:0; font-size:11px; color:grey">Data: TomTom Traffic API</p>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))
    
    output_file = "traffic_map.html"
    m.save(output_file)
    
    print(f"[Traffic] Map saved to {output_file}")
    
    return {
        "map_file": output_file,
        "congestion_status": analysis_summary['overall_status'],
        "details": f"Generated map with {len(heatmap_data)} traffic data points. "
                  f"{analysis_summary['severe_segments']}/{analysis_summary['total_segments']} segments with heavy traffic.",
        "analysis": analysis_summary
    }

def check_traffic_for_segment(start_loc: Dict, end_loc: Dict) -> Dict:
    """
    Check traffic conditions for a specific route segment.
    
    Args:
        start_loc: Starting location dict with 'name', 'lat', 'lon'
        end_loc: Ending location dict with 'name', 'lat', 'lon'
        
    Returns:
        Dict with traffic analysis for the segment
    """
    # Check traffic at midpoint
    mid_lat = (start_loc['lat'] + end_loc['lat']) / 2
    mid_lon = (start_loc['lon'] + end_loc['lon']) / 2
    
    flow_data = fetch_traffic_flow_segment(mid_lat, mid_lon)
    
    if not flow_data:
        return {
            "status": "unknown",
            "message": "Could not fetch traffic data",
            "from": start_loc['name'],
            "to": end_loc['name']
        }
    
    analysis = analyze_traffic_flow(flow_data)
    
    return {
        "status": "success",
        "from": start_loc['name'],
        "to": end_loc['name'],
        "congestion_level": analysis['congestion_level'],
        "current_speed": analysis['current_speed'],
        "free_flow_speed": analysis['free_flow_speed'],
        "delay_factor": analysis['delay_factor'],
        "recommendation": get_traffic_recommendation(analysis)
    }

def get_traffic_recommendation(analysis: Dict) -> str:
    """
    Generate traffic recommendation based on analysis.
    
    Args:
        analysis: Traffic analysis dict
        
    Returns:
        Recommendation string
    """
    congestion = analysis['congestion_level']
    delay_factor = analysis['delay_factor']
    
    if congestion == 'severe':
        return "Severe congestion. Consider alternative route or wait for conditions to improve."
    elif congestion == 'heavy':
        return f"Heavy traffic. Expected delay: {int((delay_factor - 1) * 60)} minutes. Alternative route recommended."
    elif congestion == 'moderate':
        return f"Moderate traffic. Minor delays expected (~{int((delay_factor - 1) * 30)} min). Proceed with caution."
    elif congestion == 'light':
        return "Light traffic. Proceed as planned."
    else:
        return "Clear roads. Good driving conditions."