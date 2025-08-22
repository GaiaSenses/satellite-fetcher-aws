import os
import datetime
import numpy as np
import boto3
from botocore import UNSIGNED   
from botocore.config import Config


class awsAccessGOES:

    __input_archive = "/tmp"

    '''Ordem dos produtos segue a mesma ordem do site oficial https://www.goes-r.gov/products/overview.html
        products['name'][0] -> Sigla para o produto
        products['name'][1] -> Resolução temporal em minutos
    '''
    __products = {'Aerossol Detection': ['ABI-L2-ADPF', 10],
                  'Aerossol Optical Depth': ['ABI-L2-AODF', 10],
                #   'Aerossol Particle Size': ['ABI-L2-????', ?], # Produto não disponível ainda
                  'Clear Sky Mask': ['ABI-L2-ACMF', 10],
                  'Cloud Layers': ['ABI-L2-CCLF', 60],
                  'Cloud and Moisture': ['ABI-L2-CMIPF', 10],
                  'Multi-Channel Cloud and Moisture': ['ABI-L2-MCMIPF', 10], # Documentado em conjunto com Cloud and Moisture no site
                  'Cloud Optical Depth': ['ABI-L2-CODF', 10],
                  'Cloud Particle Size': ['ABI-L2-CPSF', 10],
                  'Cloud Top Height': ['ABI-L2-ACHAF', 10],
                  'Cloud Top Phase': ['ABI-L2-ACTPF', 10],
                  'Cloud Top Pressure': ['ABI-L2-CTPF', 10],
                  'Cloud Top Temperature': ['ABI-L2-ACHTF', 10],
                  'Wind Direction': ['ABI-L2-DMWF', 60],
                  'Water Vapor Direction': ['ABI-L2-DMWVF', 60], # Documentado em conjunto com Wind Direction no site
                  'Stability Indices': ['ABI-L2-DSIF', 10],
                  'Downward Shortwave Radiation': ['ABI-L2-DSRF', 10],
                  'Firespot': ['ABI-L2-FDCF', 10],
                  'Land Albedo': ['ABI-L2-LSAF', 10],
                  'Land Bidirectional Reflectance': ['ABI-L2-BRFF', 10],
                  'Land Temperature': ['ABI-L2-LSTF', 60],
                  'Moisture Profile': ['ABI-L2-LVMPF', 10],
                  'Temperature Profile': ['ABI-L2-LVTPF', 10],
                  'Radiances': ['ABI-L1b-RadF', 10],
                  'Rainfall Rate': ['ABI-L2-RRQPEF', 10],
                  'Reflected Shortwave Radiation': ['ABI-L2-RSRF', 10],
                  'Ice Age and Thickness': ['ABI-L2-AITAF', 180],
                  'Ice Concentration and Extent': ['ABI-L2-AICEF', 180],
                #   'Ice Motion': ['ABI-L2-?????', ?], # Produto não disponível ainda
                  'Sea Temperature': ['ABI-L2-SSTF', 60],
                  'Snow Cover': ['ABI-L2-FSCF', 60],
                  'Total Precipitable Water': ['ABI-L2-TPWF', 10],
                  'Lightning': ['GLM-L2-LCFA', 1],

                  'Photosynthetically Active Radiation': ['ABI-L2-PARF', 10]} # Validação prevista para 17/abr/2026, ainda não está documentado no site, mas já está disponível para download

    @staticmethod
    def download_aws(key: str, need_CM: bool =False, band: int =0) -> str:

        input_archive = awsAccessGOES.__input_archive

        prefix, cloud_mask = awsAccessGOES.__get_info(key, need_CM, band)

        s3_client = boto3.client('s3', config=Config(signature_version=UNSIGNED))
        s3_result = s3_client.list_objects_v2(Bucket='noaa-goes19', Prefix=prefix, Delimiter = "/")

        key = key.replace(' ', '_')

        if ('Contents' in s3_result):
            if (need_CM):    
                s3_result_CM = s3_client.list_objects_v2(Bucket='noaa-goes19', Prefix=cloud_mask, Delimiter = "/")
                s3_client.download_file('noaa-goes19', s3_result_CM['Contents'][-1]['Key'],f'{input_archive}/{key}_cm.nc')

            if (not os.path.exists(f'{input_archive}/{key}.nc')):
                s3_client.download_file('noaa-goes19', s3_result['Contents'][-1]['Key'],f'{input_archive}/{key}.nc')

            if (os.path.exists(f'{input_archive}/{key}.nc')):
                return f'{input_archive}/{key}.nc'

        return f'{input_archive}/{key}.nc'
    
    @staticmethod
    def __get_info(key: str, need_CM: bool =False, band: int = 0) -> list[str]:
        """Get all the necessary info to find a archive on aws"""
        
        date = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=0)))

        products = awsAccessGOES.__products
        product_name = products[key][0]
        product_time = products[key][1]

        minutes = date.minute
        date -= datetime.timedelta(minutes=(minutes % product_time) + 2*product_time) if product_time < 60 else datetime.timedelta(minutes=minutes)
        
        year = date.year
        hour = date.hour
        minutes = date.minute

        first_day = datetime.datetime(date.year, 1, 1, tzinfo=datetime.timezone(datetime.timedelta(hours=0)))
        day_of_year = (date - first_day).days + 1

        if (band != 0):
            prefix = f'{product_name}/{year}/{day_of_year:03.0f}/{hour:02.0f}/OR_{product_name}-M6C{band:02.0f}_G19_s{year}{day_of_year:03.0f}{hour:02.0f}{minutes:02.0f}'
        else:
            if (key != 'Lightning'):
                prefix = f'{product_name}/{year}/{day_of_year:03.0f}/{hour:02.0f}/OR_{product_name}-M6_G19_s{year}{day_of_year:03.0f}{hour:02.0f}{minutes:02.0f}'
            else:
                prefix = f'{product_name}/{year}/{day_of_year:03.0f}/{hour:02.0f}/OR_{product_name}_G19_s{year}{day_of_year:03.0f}{hour:02.0f}{minutes:02.0f}'

        if (need_CM):
            cloud_mask = f'ABI-L2-ACMF/{year}/{day_of_year:03.0f}/{hour:02.0f}/OR_ABI-L2-ACMF-M6_G19_s{year}{day_of_year:03.0f}{hour:02.0f}{minutes:02.0f}'

        return [prefix, cloud_mask] if need_CM else [prefix, ""]
    
    @staticmethod
    def geo2grid(lat: float, lon: float, nc):
        # Apply scale and offset 
        xscale, xoffset = nc.variables['x'].scale_factor, nc.variables['x'].add_offset
        yscale, yoffset = nc.variables['y'].scale_factor, nc.variables['y'].add_offset
        
        x, y = awsAccessGOES.__latlon2xy(lat, lon)
        col = (x - xoffset)/xscale
        lin = (y - yoffset)/yscale
        return int(lin), int(col)
    
    @staticmethod
    def __latlon2xy(lat: float, lon: float):
        # goes_imagery_projection:semi_major_axis
        req = 6378137 # meters
        #  goes_imagery_projection:inverse_flattening
        invf = 298.257222096
        # goes_imagery_projection:semi_minor_axis
        rpol = 6356752.31414 # meters
        e = 0.0818191910435
        # goes_imagery_projection:perspective_point_height + goes_imagery_projection:semi_major_axis
        H = 42164160 # meters
        # goes_imagery_projection: longitude_of_projection_origin
        lambda0 = -1.308996939

        # Convert to radians
        latRad = lat * (np.pi/180)
        lonRad = lon * (np.pi/180)

        # (1) geocentric latitude
        Phi_c = np.atan(((rpol * rpol)/(req * req)) * np.tan(latRad))
        # (2) geocentric distance to the point on the ellipsoid
        rc = rpol/(np.sqrt(1 - ((e * e) * (np.cos(Phi_c) * np.cos(Phi_c)))))
        # (3) sx
        sx = H - (rc * np.cos(Phi_c) * np.cos(lonRad - lambda0))
        # (4) sy
        sy = -rc * np.cos(Phi_c) * np.sin(lonRad - lambda0)
        # (5)
        sz = rc * np.sin(Phi_c)

        # x,y
        x = np.asin((-sy)/np.sqrt((sx*sx) + (sy*sy) + (sz*sz)))
        y = np.atan(sz/sx)

        return x, y
