import os
import requests
import random
import json
from dotenv import load_dotenv

load_dotenv()
ORS_API = os.getenv("ORS_API_KEY")

# ======================================================================
# CONFIGURATION
# ======================================================================
POPULATION_SIZE = 60
GENERATIONS = 200
MUTATION_RATE = 0.20
ALPHA = 1.0  # Weight for Distance
BETA  = 1.0  # Weight for Duration
SEQUENCE_PENALTY = 100000  # Massive penalty for breaking user order

# ======================================================================
# DATA FETCHING (MATRIX API)
# ======================================================================
def get_distance_matrix(locations):
    """
    locations: List of dicts [{'lat': x, 'lon': y}, ...]
    Returns: distance_matrix, duration_matrix
    """
    coords = [[loc['lon'], loc['lat']] for loc in locations]
    
    url = "https://api.openrouteservice.org/v2/matrix/driving-car"
    headers = {
        "Authorization": ORS_API,
        "Content-Type": "application/json"
    }
    body = {
        "locations": coords,
        "metrics": ["distance", "duration"]
    }

    try:
        response = requests.post(url, json=body, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data["distances"], data["durations"]
    except Exception as e:
        print(f"Error fetching matrix: {e}")
        return [], []

# ======================================================================
# GENETIC ALGORITHM CORE
# ======================================================================

def calculate_route_metrics(route, dist_matrix, dur_matrix):
    """Calculates pure distance and time without penalties."""
    total_dist = 0
    total_time = 0
    for i in range(len(route)-1):
        u, v = route[i], route[i+1]
        total_dist += dist_matrix[u][v]
        total_time += dur_matrix[u][v]
    return total_dist, total_time

def check_sequence_violations(route, constraints):
    """
    Checks if the route violates the user's requested order.
    
    Rule:
    If City A has Sequence X and City B has Sequence Y, and X < Y,
    then City A MUST appear before City B in the route.
    
    If X == Y, their relative order does NOT matter (GA helps optimized).
    """
    violations = 0
    
    # Create a map: City Index -> Sequence Number
    # Default to 0 if not found (though all should be mapped)
    seq_map = {}
    for i, meta in enumerate(constraints):
        # We use the index in the original constraints list to map to the route
        seq_map[i] = meta.get('visit_sequence', 2) 

    # Iterate through every pair in the calculated route
    # Route is a list of indices, e.g., [0, 3, 1, 2]
    for i in range(len(route)):
        for j in range(i + 1, len(route)):
            city_a_idx = route[i]
            city_b_idx = route[j]
            
            seq_a = seq_map.get(city_a_idx, 2)
            seq_b = seq_map.get(city_b_idx, 2)
            
            # CASE: We are visiting A before B (because i < j)
            # VIOLATION if: A is supposed to be visited AFTER B (Seq A > Seq B)
            if seq_a > seq_b:
                violations += 1
                
    return violations

def cost_function(route, dist_matrix, dur_matrix, location_metadata):
    dist, time = calculate_route_metrics(route, dist_matrix, dur_matrix)
    
    # Base Cost
    base_cost = (ALPHA * dist) + (BETA * time)
    
    # Penalty Cost
    violations = check_sequence_violations(route, location_metadata)
    penalty_cost = violations * SEQUENCE_PENALTY
    
    return base_cost + penalty_cost

# -------------------------------
# GA HELPERS
# -------------------------------
def create_initial_population(num_cities, source_index=0):
    population = []
    # Exclude source from shuffling
    remaining = list(range(num_cities))
    remaining.remove(source_index)

    for _ in range(POPULATION_SIZE):
        random.shuffle(remaining)
        individual = [source_index] + remaining[:]
        population.append(individual)
    return population

def tournament_selection(population, dist_mat, dur_mat, meta, k=3):
    selected = random.sample(population, k)
    # Select best based on minimized cost (including penalty)
    selected.sort(key=lambda r: cost_function(r, dist_mat, dur_mat, meta))
    return selected[0]

def crossover(parent1, parent2):
    # Order Crossover (OX1) logic to preserve sequence traits
    p1 = parent1[1:] # Skip fixed source
    p2 = parent2[1:]
    n = len(p1)
    a, b = sorted(random.sample(range(n), 2))
    
    child_p = [None] * n
    child_p[a:b] = p1[a:b]
    
    fill_pos = b
    for item in p2:
        if item not in child_p:
            if fill_pos >= n: fill_pos = 0
            child_p[fill_pos] = item
            fill_pos += 1
            
    return [parent1[0]] + child_p

def mutate(route):
    if random.random() < MUTATION_RATE:
        # Swap two cities (excluding source at index 0)
        idx_range = range(1, len(route))
        if len(idx_range) >= 2:
            a, b = random.sample(idx_range, 2)
            route[a], route[b] = route[b], route[a]
    return route

# ======================================================================
# MAIN OPTIMIZER ENTRY POINT
# ======================================================================
def solve_route(locations_data):
    """
    Main function called by API.
    locations_data: List of dicts containing 'lat', 'lon', 'visit_sequence', 'name'
    """
    print(f"Starting optimization for {len(locations_data)} locations...")
    
    # 1. Get Matrix
    dist_matrix, dur_matrix = get_distance_matrix(locations_data)
    if not dist_matrix:
        return {"error": "Failed to fetch matrix from ORS"}

    # 2. Run GA
    population = create_initial_population(len(locations_data), source_index=0)
    
    global_best_route = None
    global_best_cost = float('inf')

    # Evolution Loop
    for gen in range(GENERATIONS):
        new_pop = []
        
        # Elitism: Keep best 2
        population.sort(key=lambda r: cost_function(r, dist_matrix, dur_matrix, locations_data))
        new_pop.extend(population[:2])
        
        while len(new_pop) < POPULATION_SIZE:
            p1 = tournament_selection(population, dist_matrix, dur_matrix, locations_data)
            p2 = tournament_selection(population, dist_matrix, dur_matrix, locations_data)
            child = crossover(p1, p2)
            child = mutate(child)
            new_pop.append(child)
            
        population = new_pop
        
        # Track Global Best
        current_best = population[0] # Sorted above
        current_cost = cost_function(current_best, dist_matrix, dur_matrix, locations_data)
        
        if current_cost < global_best_cost:
            global_best_cost = current_cost
            global_best_route = current_best

    # 3. Format Output for API
    final_dist, final_time = calculate_route_metrics(global_best_route, dist_matrix, dur_matrix)
    violations = check_sequence_violations(global_best_route, locations_data)
    
    optimized_order = []
    for city_idx in global_best_route:
        loc = locations_data[city_idx]
        optimized_order.append({
            "name": loc["name"],
            "lat": loc["lat"],
            "lon": loc["lon"],
            "original_sequence_req": loc.get("visit_sequence")
        })

    return {
        "status": "success",
        "total_distance_km": round(final_dist / 1000, 2),
        "total_duration_min": round(final_time / 60, 2),
        "sequence_violations": violations,
        "optimized_route": optimized_order
    }

# For testing manually
if __name__ == "__main__":
    test_data = [
        {"name": "Delhi", "lat": 28.61, "lon": 77.20, "visit_sequence": 1},
        {"name": "Bangalore", "lat": 12.97, "lon": 77.59, "visit_sequence": 2},
        {"name": "Jaipur", "lat": 26.91, "lon": 75.78, "visit_sequence": 2}, 
        {"name": "Mumbai", "lat": 19.07, "lon": 72.87, "visit_sequence": 2}
    ]
    result = solve_route(test_data)
    print(json.dumps(result, indent=2))