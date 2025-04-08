import requests
import folium
from folium import LayerControl
from flask import Flask, render_template, request
from datetime import datetime
import os
from gtfs_functions import Feed

app = Flask(__name__)

url = "https://gtfs.sts.qc.ca:8443/gtfsrt/vehiclePositions.txt"

# Charger les données GTFS
gtfs_path = r'GTFS.zip'  # adapte le chemin si besoin
feed = Feed(gtfs_path, time_windows=[0, 6, 10, 12, 16, 19, 24])

# Récupérer les données des routes, arrêts et shapes
routes = feed.routes
stops = feed.stops
shapes = feed.shapes

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

# Fonction de formatage pour l'heure
@app.template_filter('datetimeformat')
def datetimeformat(value):
    return datetime.fromtimestamp(value).strftime("%H:%M:%S")

# Générer la carte avec les icônes personnalisées et les arrêts
def generate_map(vehicles, show_stops=True, show_routes=True, show_vehicles=True):
    m = folium.Map(location=[45.4, -71.9], zoom_start=12)

    # Icône personnalisée pour les bus
    icon_path = os.path.join(app.root_path, 'static', 'images', 'bus.png')

    # Ajouter les arrêts à la carte
    stop_layer = folium.FeatureGroup(name="Arrêts")
    if show_stops:
        for _, stop in stops.iterrows():
            stop_lat = stop['stop_lat']
            stop_lon = stop['stop_lon']
            stop_name = stop['stop_name']

            folium.CircleMarker(
                location=[stop_lat, stop_lon],
                radius=4,
                color='blue',
                fill=True,
                fill_color='blue',
                fill_opacity=0.6,
                popup=f"Arrêt : {stop_name}"
            ).add_to(stop_layer)
    stop_layer.add_to(m)

    # Ajouter chaque shape à la carte (lignes)
    route_layer = folium.FeatureGroup(name="Lignes")
    if show_routes:
        for _, row in shapes.iterrows():
            folium.GeoJson(row.geometry).add_to(route_layer)
    route_layer.add_to(m)

    # Ajouter les bus à la carte
    vehicle_layer = folium.FeatureGroup(name="Véhicules")
    if show_vehicles:
        for vehicle in vehicles:
            icon = folium.CustomIcon(icon_path, icon_size=(32, 32), icon_anchor=(16, 16))
            time_str = datetime.fromtimestamp(vehicle['timestamp']).strftime("%H:%M:%S")

            folium.Marker(
                location=[vehicle['lat'], vehicle['lon']],
                popup=f"Véhicule {vehicle['vehicle_id']} (Ligne {vehicle['route_id']})<br>Heure: {time_str}",
                icon=icon
            ).add_to(vehicle_layer)
    vehicle_layer.add_to(m)

    # Ajouter un contrôle pour activer/désactiver les couches
    LayerControl().add_to(m)

    m.save("static/map.html")

# Page principale
@app.route('/', methods=['GET'])
def index():
    selected_route = request.args.get('route_id')
    if selected_route == "":
        selected_route = None

    show_stops = request.args.get('show_stops', 'true') == 'true'
    show_routes = request.args.get('show_routes', 'true') == 'true'
    show_vehicles = request.args.get('show_vehicles', 'true') == 'true'

    vehicles = get_vehicle_positions(route_filter=selected_route)
    generate_map(vehicles, show_stops=show_stops, show_routes=show_routes, show_vehicles=show_vehicles)

    # Liste triée des lignes disponibles
    all_vehicles = get_vehicle_positions()
    routes = sorted(set(v['route_id'] for v in all_vehicles), key=lambda r: int(r) if r.isdigit() else r)

    return render_template('index.html', routes=routes, selected_route=request.args.get('route_id', ''),
                           show_stops=show_stops, show_routes=show_routes, show_vehicles=show_vehicles, vehicles=vehicles)

if __name__ == '__main__':
    app.run(debug=True)
