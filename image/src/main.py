import numpy as np
import pandas as pd
import os
import json
import logging
from shapely.geometry import Point
import geopandas as gpd

#Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)



def get_fire_data(lat, lon, dist=10, source="VIIRS_NOAA20_NRT"):
    point = Point(float(lat),float(lon))
    buffer = point.buffer(float(dist) / 111)

    minx, miny, maxx, maxy = buffer.bounds
    MAP_KEY = os.environ.get("FIRMS_MAP_KEY")
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{source}/{miny},{minx},{maxy},{maxx}/1"
    logger.info(url)
    
    try:
        df_area = pd.read_csv(url)
        logger.info(df_area.head())
    except Exception as e:
        logger.error(f"Error fetching fire data: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Error fetching fire data."})
        }
    if(df_area.shape[0] > 0):
        response_data = {
            "count": df_area.shape[0],
            "events":df_area[["latitude", "longitude", "bright_ti4"]].to_dict(orient="records")
        }
        logger.info(f"Returning fire data: {response_data}")
        return response_data
    else:
        return {
            "count": 0,
            "events": []
        }
    

def handler(event, context):
    
    logger.info(f"Received event: {json.dumps(event, indent=2)}")

    raw_path = event.get("rawPath", "/")
    path = event.get("path", "/")
    query_params = event.get("queryStringParameters", {})

    if path == "/fire" or raw_path == "/fire":
        lat = query_params.get("lat")
        lon = query_params.get("lon")
        dist = query_params.get("dist", 10)

        if not lat or not lon:
            logger.warning("Missing lat or lon in request.")
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Missing lat or lon."})
            }

        logger.info(f"Fetching fire data for lat: {lat} and lon: {lon}.")
        response_data = get_fire_data(lat, lon, dist)
        return {
            "statusCode": 200,
            "body": json.dumps(response_data)
        }
        
    logger.error("Invalid route accessed.")

    return {
        "statucCode":404, 
        "body":json.dumps({"error":"Invalid route."})
    }

# A shortcut for local testing
#handler({"path":"/fire", "queryStringParameters":{"lat":"-22.851692221661406", "lon":"47.1276886499418", "dist":"100"}} , {})