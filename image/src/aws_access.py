import os
import datetime
import numpy as np
import boto3
from botocore import UNSIGNED   
from botocore.config import Config


class awsAccessGOES:

    __input_archive = "samples"; os.makedirs("samples", exist_ok=True)

    __products = {'11': 'ABI-L1b-RadF',
                  '12': 'ABI-L2-CMIPF', 
                  '13': 'ABI-L2-MCMIPF',
                  '14': 'ABI-L2-ACHAF',
                  '15': 'ABI-L2-ACF',
                  '16': 'ABI-L2-ACMF',
                  '17': 'ABI-L2-ACTPF',
                  '18': 'ABI-L2-CTPF',
                  '19': 'ABI-L2-CODF',
                  '1A': 'ABI-L2-CPSF',
                  '1C': 'ABI-L2-ADPF',
                  '1D': 'ABI-L2-AODF',
                  '1E': 'ABI-L2-BRFF',
                  '1F': 'ABI-L2-DMWF',
                  '1G': 'ABI-L2-DMWVF',
                  '1H': 'ABI-L2-TPWF',
                  '1I': 'ABI-L2-DSIF',
                  '1J': 'ABI-L2-LVMPF',
                  '1K': 'ABI-L2-LVTPF',
                  '1L': 'ABI-L2-DSRF',
                  '1M': 'ABI-L2-FDCF',
                  '1N': 'ABI-L2-FSCF',
                  '1O': 'ABI-L2-LSAF',
                  '1P': 'ABI-L2-LSTF',
                  '1Q': 'ABI-L2-RRQPEF',
                  '1R': 'ABI-L2-RSRF',
                  '1S': 'ABI-L2-SSTF',
                  '2': 'GLM-L2-LCFA'}

    __days_in_yearA = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    __days_in_yearB = [0, 31, 60, 91, 121, 152, 182, 213, 243, 274, 305, 335]

    __date = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=0)))

    @staticmethod
    def download_aws(key: str, need_CM: bool =False, band: int =0) -> str:

        input_archive = awsAccessGOES.__input_archive

        prefix, cloud_mask = awsAccessGOES.__get_info(key, need_CM, band)

        s3_client = boto3.client('s3', config=Config(signature_version=UNSIGNED))
        s3_result = s3_client.list_objects_v2(Bucket='noaa-goes19', Prefix=prefix, Delimiter = "/")
        s3_result_CM = s3_client.list_objects_v2(Bucket='noaa-goes19', Prefix=cloud_mask, Delimiter = "/")

        if ('Contents' in s3_result):
            if (need_CM):
                s3_client.download_file('noaa-goes19', s3_result_CM['Contents'][0]['Key'],f'{input_archive}/{key}_cm.nc')

            if (not os.path.exists(f'{input_archive}/{key}.nc')):
                s3_client.download_file('noaa-goes19', s3_result['Contents'][0]['Key'],f'{input_archive}/{key}.nc')

            if (os.path.exists(f'{input_archive}/{key}.nc')):
                return f'{input_archive}/{key}.nc'

        return f'{input_archive}/{key}.nc'
    
    @staticmethod
    def __get_info(key: str, need_CM: bool =False, band: int = 0) -> list[str]:
        """Get all the necessary info to find a archive on aws"""
        
        products = awsAccessGOES.__products
        days_in_yearA = awsAccessGOES.__days_in_yearA
        days_in_yearB = awsAccessGOES.__days_in_yearB
        date = awsAccessGOES.__date

        product_name = products[key]

        minutes = date.minute
        date = date - datetime.timedelta(minutes=(minutes % 10) + 10)

        year = date.year
        month = date.month
        day = date.day
        hour = date.hour
        minutes = date.minute
        day = 25
        hour = 11
        minute = 30

        month -= 1

        days_in_year = days_in_yearB[:] if (year % 4 == 0) else days_in_yearA[:]
        day_of_year = days_in_year[month] + day

        if (band != 0):
            prefix = f'{product_name}/{year}/{day_of_year:03.0f}/{hour:02.0f}/OR_{product_name}-M6C{band:02.0f}_G19_s{year}{day_of_year:03.0f}{hour:02.0f}{minutes:02.0f}'
        else:
            if (key == '2'):
                prefix = f'{product_name}/{year}/{day_of_year:03.0f}/{hour:02.0f}/OR_{product_name}_G19_s{year}{day_of_year:03.0f}{hour:02.0f}{minutes:02.0f}'
            else:
                prefix = f'{product_name}/{year}/{day_of_year:03.0f}/{hour:02.0f}/OR_{product_name}-M6_G19_s{year}{day_of_year:03.0f}{hour:02.0f}{minutes:02.0f}'

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
