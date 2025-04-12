from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from datetime import datetime
import folium
from folium import FeatureGroup
from gtfs_functions import Feed
import zipfile
import pandas as pd
import requests

app = Flask(__name__)
app.secret_key = 'supersecretkey'

url = "https://gtfs.sts.qc.ca:8443/gtfsrt/vehiclePositions.txt"
gtfs_path = r'GTFS.zip'
feed = Feed(gtfs_path, time_windows=[0, 6, 10, 12, 16, 19, 24])

routes = feed.routes
stops = feed.stops
shapes = feed.shapes

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

@app.template_filter('datetimeformat')
def datetimeformat(value):
    return datetime.fromtimestamp(value).strftime("%H:%M:%S")

@app.route('/get_vehicle_positions', methods=['GET'])
def vehicle_positions():
    route_id = request.args.get('route_id')
    vehicles = get_vehicle_positions(route_filter=route_id)
    return jsonify(vehicles)

@app.route('/', methods=['GET'])
def index():
    selected_route = request.args.get('route_id', '')
    vehicles = get_vehicle_positions(route_filter=selected_route if selected_route else None)

    all_vehicles = get_vehicle_positions()
    route_list = sorted(set(v['route_id'] for v in all_vehicles), key=lambda r: int(r) if r.isdigit() else r)

    return render_template(
        'index.html',
        routes=route_list,
        selected_route=selected_route,
        vehicles=vehicles,
        stops=stops,
        shapes=shapes,
        session=session
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == 'admin' and password == '1234':
            session['user'] = {'name': 'Admin'}
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="Nom d'utilisateur ou mot de passe incorrect.")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))

@app.route('/carte', methods=['GET'])
def carte():
    selected_route_short_name = request.args.get('route_short_name')
    selected_route_long_name = request.args.get('route_long_name')

    # Obtenir les coordonnées de la boîte englobante
    bounding_box = feed.get_bbox()
    coordinates = [[lat, lon] for lon, lat in bounding_box['coordinates'][0]]
    center_lat = sum(p[0] for p in coordinates) / len(coordinates)
    center_lon = sum(p[1] for p in coordinates) / len(coordinates)

    # Créer la carte Folium
    m = folium.Map(location=[center_lat, center_lon], zoom_start=12, tiles=None)
    folium.TileLayer('OpenStreetMap', name="Classique").add_to(m)
    folium.TileLayer('CartoDB positron', name="Clair").add_to(m)

    # Lire les fichiers GTFS
    with zipfile.ZipFile(gtfs_path, 'r') as z:
        shapes_df = pd.read_csv(z.open('shapes.txt'))
        routes_df = pd.read_csv(z.open('routes.txt'))
        trips_df = pd.read_csv(z.open('trips.txt'))
        stops_df = pd.read_csv(z.open('stops.txt'))

    # Convertir les types de données
    shapes_df['shape_id'] = shapes_df['shape_id'].astype(str)
    routes_df['route_id'] = routes_df['route_id'].astype(str)
    routes_df['route_short_name'] = routes_df['route_short_name'].astype(str)
    routes_df['route_long_name'] = routes_df['route_long_name'].astype(str)
    trips_df['shape_id'] = trips_df['shape_id'].astype(str)
    trips_df['route_id'] = trips_df['route_id'].astype(str)

    # Filtrer les routes à afficher
    routes_df = routes_df[~routes_df['route_short_name'].isin(["HLP", "Entree", "Sortie"])]

    # Trier les routes par route_short_name de manière numérique
    routes_df['route_short_name'] = pd.to_numeric(routes_df['route_short_name'], errors='coerce')
    routes_df = routes_df.sort_values(by='route_short_name', na_position='last')
    routes_df['route_short_name'] = routes_df['route_short_name'].astype(str)

    # Filtrer selon les critères de la requête GET (route_short_name et route_long_name)
    if selected_route_short_name:
        routes_df = routes_df[routes_df['route_short_name'] == selected_route_short_name]
    if selected_route_long_name:
        routes_df = routes_df[routes_df['route_long_name'] == selected_route_long_name]

    routes = routes_df.to_dict(orient='records')
    routes_to_display = routes_df

    for _, route in routes_to_display.iterrows():
        route_id = route['route_id']
        route_name = route.get('route_short_name', 'Unnamed')
        route_long_name = route.get('route_long_name', '')
        route_color = f"#{route['route_color']}" if pd.notna(route.get('route_color')) else 'red'

        trip_shapes = trips_df[trips_df['route_id'] == route_id][['shape_id']].drop_duplicates()

        route_group = FeatureGroup(name=f"Ligne {route_name} ({route_long_name})")

        for _, trip in trip_shapes.iterrows():
            shape_id = trip['shape_id']
            shape_points = shapes_df[shapes_df['shape_id'] == shape_id].sort_values('shape_pt_sequence')
            coords = shape_points[['shape_pt_lat', 'shape_pt_lon']].values.tolist()

            if coords:
                folium.PolyLine(
                    coords,
                    color=route_color,
                    weight=4,
                    opacity=0.8,
                    popup=f"Ligne {route_name}<br>{route_long_name}"
                ).add_to(route_group)

        route_group.add_to(m)

    # Ajouter les arrêts à la carte
    stops_group = FeatureGroup(name="Arrêts")
    for _, stop in stops_df.iterrows():
        folium.CircleMarker(
            location=[stop['stop_lat'], stop['stop_lon']],
            radius=4,
            color='blue',
            fill=True,
            fill_color='blue',
            fill_opacity=0.7,
            popup=stop['stop_name']
        ).add_to(stops_group)
    stops_group.add_to(m)

    # Ajouter la boîte englobante à la carte
    bbox_group = FeatureGroup(name="Étendue géographique")
    folium.Polygon(
        locations=coordinates,
        color='blue',
        fill=True,
        fill_color='blue',
        fill_opacity=0.3,
        popup="Étendue des données GTFS"
    ).add_to(bbox_group)
    bbox_group.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)

    # Enregistrer la carte
    map_path = 'static/carte.html'
    m.save(map_path)

    # Liste des noms de lignes (pour afficher dans le formulaire)
    short_names = routes_df['route_short_name'].unique().tolist()

    return render_template('carte.html',
                           map_path=map_path,
                           routes=routes,
                           short_names=short_names,
                           selected_route_short_name=selected_route_short_name,
                           selected_route_long_name=selected_route_long_name)

if __name__ == '__main__':
    app.run(debug=True)
