import numpy as np
import pandas as pd
import os
import json
import logging
from shapely.geometry import Point
import geopandas as gpd
from aws_access import awsAccessGOES as aws
from netCDF4 import Dataset

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
    

def get_lightning_data(lat, lon, dist=50):

    lat = float(lat)
    lon = float(lon)

    try:
        file_path = aws.download_aws('2')
    except Exception as e:
        logger.error(f"Error downloading lightning data: {e}")
        return {
            "statusCode": 501,
            "body": json.dumps({"error": "Error downloading lightning data"})
        }

    try:
        file = Dataset(f'{file_path}')
    except Exception as e:
        logger.error(f"Error fetching lightning data: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Error fetching lightning data."})
        }

    lightning_lat = file['flash_lat'][:]
    lightning_lon = file['flash_lon'][:]
    lightning_energy =  file['flash_energy'][:]
    lightning_count = 0
    flash_events = []

    latlon_diff = float(dist)/111

    for i in range(len(lightning_lat)):
        if np.abs(lightning_lat[i] - lat) <= latlon_diff and np.abs(lightning_lon[i] - lon) <= latlon_diff:
            if file['flash_quality_flag'][i] == 0:
                lightning_count += 1
                flash_events.append({"latitude": lightning_lat[i], "longitude": lightning_lon[i], "energy": lightning_energy[i]})

    file.close()

    if (lightning_count > 0):
        response_data = {
            "count": lightning_count,
            "events": flash_events
        }
        logger.info(f"Returning lightning data: {response_data}")
        return response_data
    else:
        return {
            "count": 0,
            "events": []
        }


def get_rain_data(lat, lon):

    lat = float(lat)
    lon = float(lon)

    try:
        file_path = aws.download_aws('1Q')
    except Exception as e:
        logger.error(f"Error downloading rain data: {e}")
        return {
            "statusCode": 501,
            "body": json.dumps({"error": "Error downloading rain data"})
        }

    try:
        file = Dataset(f'./{file_path}')
    except Exception as e:
        logger.error(f"Error fetching rain data: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Error fetching rain data."})
        }

    i, j = aws.geo2grid(lat, lon, file)
    rain_data = int(file['RRQPE'][:][i][j])
    max_rain = file['maximum_rainfall_rate']

    file.close()

    if (rain_data > 0 and rain_data <= max_rain):
        response_data = {
            "count": rain_data
        }
        logger.info(f"Returning rain data: {response_data}")
        return response_data
    else:
        return {
            "count": 0
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
    
    elif path == "/lightning" or raw_path == "/lightning":
        lat = query_params.get("lat")
        lon = query_params.get("lon")
        dist = query_params.get("dist", 10)

        if not lat or not lon:
            logger.warning("Missing lat or lon in request.")
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Missing lat or lon."})
            }

        logger.info(f"Fetching lightning data for lat: {lat} and lon: {lon}.")
        response_data = get_lightning_data(lat, lon, dist)
        return {
            "statusCode": 200,
            "body": json.dumps(response_data)
        }
    
    elif path == "/rain" or raw_path == "/rain":
        lat = query_params.get("lat")
        lon = query_params.get("lon")

        if not lat or not lon:
            logger.warning("Missing lat or lon in request.")
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Missing lat or lon."})
            }

        logger.info(f"Fetching rain data for lat: {lat} and lon: {lon}.")
        response_data = get_rain_data(lat, lon)
        return {
            "statusCode": 200,
            "body": json.dumps(response_data)
        }
        
    logger.error("Invalid route accessed.")

    return {
        "statucCode":404, 
        "body":json.dumps({"error":"Invalid route."})
    }

# A shortcut for local testing −87.775
# handler({"path":"/fire", "queryStringParameters":{"lat":"-22.851692221661406", "lon":"47.1276886499418", "dist":"100"}} , {})
# handler({"path":"/lightning", "queryStringParameters":{"lat":"-22.851692221661406", "lon":"47.1276886499418", "dist":"100"}} , {})
# handler({"path":"/rain","queryStringParameters": {"lat":-22.816532, "lon":-47.072649}} , {})
