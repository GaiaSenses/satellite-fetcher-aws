import numpy as np
import pandas as pd
import os
import json
import logging
from shapely.geometry import Point
from aws_access import awsAccessGOES as aws
from netCDF4 import Dataset

#Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)



def firms_area(lat, lon, dist):
    """Caixa da consulta à FIRMS, no formato "west,south,east,north" da API.

    O Point do shapely recebe (x, y) = (lon, lat). O código antigo passava
    (lat, lon) — invertido — e compensava escrevendo os bounds na ordem trocada
    na URL: dois erros que se cancelavam. Consertar só um deles faria o /fire
    consultar o hemisfério errado e devolver zero focos sem nenhum erro. Por
    isso a conta inteira vive nesta função, com um teste de regressão que fixa
    a saída (tests/test_firms_area.py): quem mexer aqui e trocar o resultado
    fica vermelho na hora.
    """
    point = Point(float(lon), float(lat))
    buffer = point.buffer(float(dist) / 111)
    minx, miny, maxx, maxy = buffer.bounds
    return f"{minx},{miny},{maxx},{maxy}"


def get_fire_data(lat, lon, dist=50, source="VIIRS_NOAA20_NRT"):
    area = firms_area(lat, lon, dist)
    MAP_KEY = os.environ.get("FIRMS_MAP_KEY")
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{source}/{area}/1"
    # The FIRMS key is a path segment of this URL. Logging the URL as-is wrote a
    # live credential to CloudWatch on every /fire call, with 30-day retention.
    logger.info(url.replace(MAP_KEY, "***") if MAP_KEY else url)
    
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
                flash_events.append({"latitude": float(lightning_lat[i]), "longitude": float(lightning_lon[i]), "energy (pJ)": float(lightning_energy[i]/1e-12)})

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
        # `./{file_path}` turned the absolute path download_aws returns into
        # `.//tmp/...`, which resolves against the working directory —
        # /var/task in Lambda — and never exists, so /rain answered 500 to
        # every request. get_lightning_data above already passes the path
        # unchanged; this is the other half of the inconsistency that the
        # commit named "fixing inconsistnt tmp path" left behind.
        file = Dataset(file_path)
    except Exception as e:
        logger.error(f"Error fetching rain data: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Error fetching rain data."})
        }

    i, j = aws.geo2grid(lat, lon, file)

    # `[:][i][j]` read the entire RRQPE grid into memory and then indexed it —
    # a GOES full-disk raster loaded to look at one pixel. It cost 511 MB of the
    # 512 the function has and killed every request with Runtime.OutOfMemory,
    # which is also why the stack used to ask for 1024 MB it did not need.
    # netCDF4 reads lazily when indexed directly, so this fetches one value.
    rain_data = float(file['RRQPE'][i, j])

    # Without the slice this was the netCDF Variable object, not the number in
    # it, so the `rain_data <= max_rain` below compared a float to a variable.
    max_rain = float(file['maximum_rainfall_rate'][:])

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


def _respond(response_data):
    """Wrap data in a 200, and let a failure keep the status it chose.

    Every route used to do `{"statusCode": 200, "body": json.dumps(result)}`
    regardless of what the result was. The get_*_data functions signal failure
    by returning an envelope of their own — `{"statusCode": 500, "body": …}` —
    so a failure came back as HTTP 200 carrying a 500 inside the body.

    That is how /rain went months answering nothing but errors while looking
    healthy: the caller checks `res.ok`, sees 200, and treats the error
    envelope as data. Anything watching status codes — the web app, a future
    alarm, a person running curl — was told the opposite of the truth.

    Success responses are byte-for-byte what they were; only failures change.
    """
    if isinstance(response_data, dict) and "statusCode" in response_data:
        return response_data

    return {
        "statusCode": 200,
        "body": json.dumps(response_data)
    }


DIST_PADRAO = 50
DIST_MAXIMO = 1000


def _parse_consulta(query_params, com_dist=True):
    """Valida lat/lon/dist e devolve (lat, lon, dist, erro_400_ou_None).

    As conversões float() viviam fora dos try dos handlers: ?lat=abc levantava
    ValueError não tratado e o Gateway respondia 502 — erro de servidor para um
    erro de cliente. É a mesma família do defeito já corrigido para query
    string ausente; faltava o caso do valor inválido.

    dist tinha dois defaults divergentes (10 no handler, 50 na função de raios)
    e nenhum teto: ?dist=100000 virava um buffer de ~900° e uma caixa absurda
    enviada à FIRMS. Agora: um default só (50 km) e teto de 1000 km — acima
    disso é 400, porque um raio continental é sempre engano do chamador.
    """
    def _erro(msg):
        return {"statusCode": 400, "body": json.dumps({"error": msg})}

    bruto_lat = query_params.get("lat")
    bruto_lon = query_params.get("lon")
    if not bruto_lat or not bruto_lon:
        logger.warning("Missing lat or lon in request.")
        return None, None, None, _erro("Missing lat or lon.")
    try:
        lat = float(bruto_lat)
        lon = float(bruto_lon)
    except (TypeError, ValueError):
        return None, None, None, _erro("lat and lon must be numbers.")
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return None, None, None, _erro("lat must be in [-90, 90] and lon in [-180, 180].")

    dist = DIST_PADRAO
    if com_dist:
        bruto_dist = query_params.get("dist", DIST_PADRAO)
        try:
            dist = float(bruto_dist)
        except (TypeError, ValueError):
            return None, None, None, _erro("dist must be a number (km).")
        if not (0 < dist <= DIST_MAXIMO):
            return None, None, None, _erro(f"dist must be in (0, {DIST_MAXIMO}] km.")

    return lat, lon, dist, None


def handler(event, context):

    # Never log the raw proxy event: it carries every request header, including
    # the x-api-key the Gateway just validated, plus the caller's source IP.
    # Logging it put a live credential and personal data into CloudWatch on every
    # request. Log only what debugging actually uses.
    logger.info(
        "Received request: path=%s query=%s",
        event.get("rawPath") or event.get("path", "/"),
        event.get("queryStringParameters"),
    )

    raw_path = event.get("rawPath", "/")
    path = event.get("path", "/")
    # `.get(key, {})` only falls back when the key is missing, and API Gateway
    # sends `"queryStringParameters": null` when a request carries none. The
    # default never applied, `None.get("lat")` raised, and a request with no
    # parameters came back as 502 Internal server error instead of the 400 the
    # code below is written to return. `or {}` covers both null and absent.
    query_params = event.get("queryStringParameters") or {}

    if path == "/fire" or raw_path == "/fire":
        lat, lon, dist, erro = _parse_consulta(query_params)
        if erro:
            return erro

        logger.info(f"Fetching fire data for lat: {lat} and lon: {lon}.")
        response_data = get_fire_data(lat, lon, dist)
        return _respond(response_data)
    
    elif path == "/lightning" or raw_path == "/lightning":
        lat, lon, dist, erro = _parse_consulta(query_params)
        if erro:
            return erro

        logger.info(f"Fetching lightning data for lat: {lat} and lon: {lon}.")
        response_data = get_lightning_data(lat, lon, dist)
        return _respond(response_data)
    
    elif path == "/rain" or raw_path == "/rain":
        lat, lon, _dist, erro = _parse_consulta(query_params, com_dist=False)
        if erro:
            return erro

        logger.info(f"Fetching rain data for lat: {lat} and lon: {lon}.")
        response_data = get_rain_data(lat, lon)
        return _respond(response_data)
        
    logger.error("Invalid route accessed.")

    return {
        "statusCode": 404,
        "body": json.dumps({"error": "Invalid route."})
    }

# A shortcut for local testing −87.775
# handler({"path":"/fire", "queryStringParameters":{"lat":"-22.851692221661406", "lon":"47.1276886499418", "dist":"100"}} , {})
# handler({"path":"/lightning", "queryStringParameters":{"lat":"-22.851692221661406", "lon":"47.1276886499418", "dist":"100"}} , {})
# handler({"path":"/rain","queryStringParameters": {"lat":-22.816532, "lon":-47.072649}} , {})
