from functools import lru_cache
import pandas as pd
import pydeck as pdk
import requests


KITCHEN_LOCATION = {
    "name": "Main Kitchen",
    "latitude": 34.0835,
    "longitude": 74.7970,
}

PRIORITY_COLORS = {
    "High": [220, 53, 69],
    "Medium": [255, 193, 7],
    "Low": [25, 135, 84],
}


@lru_cache(maxsize=128)
def fetch_osrm_route(waypoints_tuple):
    """
    Fetch road driving route from public OSRM for given (lon, lat) waypoints.
    
    Returns:
        tuple: (coordinates_list, road_distance_km or None)
        Gracefully returns fallback straight line if network/OSRM fails.
    """
    coords_str = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in waypoints_tuple)
    url = f"https://router.project-osrm.org/route/v1/driving/{coords_str}?overview=full&geometries=geojson"
    try:
        resp = requests.get(url, timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == "Ok" and data.get("routes"):
                route = data["routes"][0]
                coords = route.get("geometry", {}).get("coordinates", [])
                distance_km = round(route.get("distance", 0) / 1000.0, 1)
                if coords:
                    return coords, distance_km
    except Exception:
        pass
    # Fallback to straight line connecting waypoints
    return [list(pt) for pt in waypoints_tuple], None


def build_route_map(redistribution_plan):
    """
    Build an interactive PyDeck map showing kitchen, recipients, and road route.
    
    Args:
        redistribution_plan: DataFrame with recipient locations and allocations
        
    Returns:
        pdk.Deck: Interactive map object ready for st.pydeck_chart()
    """
    if redistribution_plan.empty:
        return None

    recipient_points = redistribution_plan.copy()

    recipient_points["fill_color"] = recipient_points["Priority"].map(
        lambda p: PRIORITY_COLORS.get(p, [108, 117, 125])
    )

    kitchen_data = pd.DataFrame(
        [
            {
                "name": KITCHEN_LOCATION["name"],
                "latitude": KITCHEN_LOCATION["latitude"],
                "longitude": KITCHEN_LOCATION["longitude"],
                "fill_color": [13, 110, 253],
                "type": "kitchen",
            }
        ]
    )

    waypoints = (
        (KITCHEN_LOCATION["longitude"], KITCHEN_LOCATION["latitude"]),
        *(
            (float(row["longitude"]), float(row["latitude"]))
            for _, row in recipient_points.iterrows()
        ),
    )

    # Road-following route via OSRM, with straight-line fallback
    route_path, road_distance_km = fetch_osrm_route(waypoints)

    layers = [
        pdk.Layer(
            "PathLayer",
            data=[{"path": route_path}],
            get_path="path",
            get_color=[22, 121, 77],
            width_min_pixels=4,
            width_max_pixels=8,
            pickable=True,
        ),
        pdk.Layer(
            "ScatterplotLayer",
            data=recipient_points,
            get_position="[longitude, latitude]",
            get_fill_color="fill_color",
            get_radius="Meals allocated * 5 + 50",
            pickable=True,
            highlight_color=[255, 0, 0],
            get_line_color=[0, 0, 0],
            line_width_min_pixels=2,
        ),
        pdk.Layer(
            "ScatterplotLayer",
            data=kitchen_data,
            get_position="[longitude, latitude]",
            get_fill_color="fill_color",
            get_radius=150,
            pickable=True,
            get_line_color=[255, 255, 255],
            line_width_min_pixels=3,
        ),
    ]

    return pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(
            latitude=KITCHEN_LOCATION["latitude"],
            longitude=KITCHEN_LOCATION["longitude"],
            zoom=12,
            pitch=0,
        ),
        tooltip={
            "html": (
                "<b>{Recipient}</b><br/>"
                "Item: {Menu Item}<br/>"
                "Meals: {Meals allocated}<br/>"
                "Priority: {Priority}<br/>"
                "Distance: {Distance (km):.1f} km"
            ),
            "style": {"backgroundColor": "#0f5132", "color": "white", "fontSize": "12px"},
        },
    )


def get_recipient_markers(recipients):
    """
    Convert recipient data to map markers format.
    
    Args:
        recipients: DataFrame with recipient locations
        
    Returns:
        DataFrame suitable for st.map()
    """
    map_data = recipients[["name", "latitude", "longitude", "priority", "capacity"]].copy()
    map_data = map_data.rename(columns={"latitude": "lat", "longitude": "lon"})
    return map_data
