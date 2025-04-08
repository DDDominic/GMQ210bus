import requests
import folium
from flask import Flask, render_template, request
from datetime import datetime
import os

app = Flask(__name__)

url = "https://gtfs.sts.qc.ca:8443/gtfsrt/vehiclePositions.txt"

# Récupérer les positions des bus, avec la position la plus récente par véhicule
def get_vehicle_positions(route_filter=None):
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        vehicle_dict = {}

        if 'Entities' in data:
            for entity in data['Entities']:
                if 'Vehicle' in entity and 'Position' in entity['Vehicle']:
                    vehicle = entity['Vehicle']
                    position = vehicle['Position']
                    lat = position.get('Latitude')
                    lon = position.get('Longitude')
                    route_id = vehicle['Trip']['RouteId']
                    vehicle_id = vehicle['Vehicle']['Id']
                    timestamp = vehicle.get('Timestamp', 0)

                    if lat and lon:
                        if route_filter is None or route_id == route_filter:
                            # Ne garder que la dernière position connue
                            if vehicle_id not in vehicle_dict or timestamp > vehicle_dict[vehicle_id]['timestamp']:
                                vehicle_dict[vehicle_id] = {
                                    'vehicle_id': vehicle_id,
                                    'lat': lat,
                                    'lon': lon,
                                    'route_id': route_id,
                                    'timestamp': timestamp
                                }

        return list(vehicle_dict.values())

    except requests.exceptions.RequestException as e:
        print(f"Erreur lors de la récupération des données : {e}")
        return []

# Générer la carte avec les icônes personnalisées
def generate_map(vehicles):
    m = folium.Map(location=[45.4, -71.9], zoom_start=12)

    # Chemin absolu vers l’image sur disque
    icon_path = os.path.join(app.root_path, 'static', 'images', 'bus.png')

    for vehicle in vehicles:
        icon = folium.CustomIcon(icon_path, icon_size=(32, 32), icon_anchor=(16, 16))
        time_str = datetime.fromtimestamp(vehicle['timestamp']).strftime("%H:%M:%S")

        folium.Marker(
            location=[vehicle['lat'], vehicle['lon']],
            popup=f"Véhicule {vehicle['vehicle_id']} (Ligne {vehicle['route_id']})<br>Heure: {time_str}",
            icon=icon
        ).add_to(m)

    m.save("static/map.html")

# Page principale
@app.route('/', methods=['GET'])
def index():
    selected_route = request.args.get('route_id')
    vehicles = get_vehicle_positions(route_filter=selected_route)
    generate_map(vehicles)

    # Liste triée des lignes disponibles
    all_vehicles = get_vehicle_positions()
    routes = sorted(set(v['route_id'] for v in all_vehicles), key=lambda r: int(r) if r.isdigit() else r)

    return render_template('index.html', routes=routes, selected_route=selected_route)

if __name__ == '__main__':
    app.run(debug=True)
