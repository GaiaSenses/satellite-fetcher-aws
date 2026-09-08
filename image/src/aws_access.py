import os
import datetime
import numpy as np
import boto3
from botocore import UNSIGNED   
from botocore.config import Config


class awsAccessGOES:

    __input_archive = "/tmp"
    #os.makedirs("tmp", exist_ok=True)

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

    @staticmethod
    def __local_path(key: str, object_key: str, suffix: str = "") -> str:
        """Local name for one S3 object, derived from the object itself.

        The name used to be `{key}.nc` — the same string for every granule of a
        product. Combined with the "download only if absent" check below, that
        meant a warm container kept serving whichever granule it happened to
        download first, forever. Naming the file after the S3 object makes the
        cache say what it actually holds, so a new granule is a new file and
        the check does what it reads like it does.
        """
        name = os.path.basename(object_key)
        return f'{awsAccessGOES.__input_archive}/{key}{suffix}__{name}'

    @staticmethod
    def __drop_stale(key: str, keep: str, suffix: str = "") -> None:
        """Remove earlier granules of this product from /tmp.

        Lambda gives 512 MB of /tmp and reuses it across invocations. Caching
        per granule without ever deleting would fill it over a container's
        life, and then every request fails on a full disk instead of on
        anything to do with satellites.
        """
        archive = awsAccessGOES.__input_archive
        marker = f'{key}{suffix}__'
        for name in os.listdir(archive):
            if name.startswith(marker) and os.path.join(archive, name) != keep:
                try:
                    os.remove(os.path.join(archive, name))
                except OSError:
                    # Best effort. A file we cannot remove is not a reason to
                    # fail a request that has the data it needs.
                    pass

    @staticmethod
    def download_aws(key: str, need_CM: bool =False, band: int =0) -> str:

        s3_client = boto3.client('s3', config=Config(signature_version=UNSIGNED))

        # O slot calculado é o mais recente que DEVERIA existir — mas a NOAA
        # publica com minutos de atraso variável, e um slot ainda vazio é
        # condição transitória e rotineira, não erro. Antes, essa condição
        # virava FileNotFoundError e o usuário recebia 501 por um dado que
        # existiria de novo dali a minutos. Agora recua-se até 3 janelas de
        # 10 min: dado de meia hora atrás é melhor do que erro nenhum dado,
        # e o log diz quando o fallback valeu.
        prefixos_tentados = []
        for slots_atras in range(4):
            prefix, cloud_mask = awsAccessGOES.__get_info(key, need_CM, band, slots_atras)
            s3_result = s3_client.list_objects_v2(Bucket='noaa-goes19', Prefix=prefix, Delimiter = "/")
            if ('Contents' in s3_result):
                if slots_atras > 0:
                    print(f'fallback: slot atual sem granule; usando {slots_atras} janela(s) de 10 min atrás ({prefix})')
                break
            prefixos_tentados.append(prefix)
        else:
            # Returning a path to a file that was never written pushed the
            # failure downstream, where it surfaced as "error reading the
            # file" — which sends whoever is debugging to the parser instead
            # of to the empty listing that actually caused it.
            raise FileNotFoundError(
                f'no object under any of {len(prefixos_tentados)} prefixes in noaa-goes19: {prefixos_tentados}'
            )

        object_key = s3_result['Contents'][0]['Key']
        path = awsAccessGOES.__local_path(key, object_key)

        if (not os.path.exists(path)):
            s3_client.download_file('noaa-goes19', object_key, path)
        awsAccessGOES.__drop_stale(key, path)

        if (need_CM):
            # This listing used to run on every call, including the ones that
            # do not want a cloud mask — and with an empty prefix, which asks
            # S3 to enumerate the root of the bucket. /lightning never needs
            # it, and /lightning is the endpoint called most.
            s3_result_CM = s3_client.list_objects_v2(
                Bucket='noaa-goes19', Prefix=cloud_mask, Delimiter="/"
            )
            if ('Contents' not in s3_result_CM):
                raise FileNotFoundError(
                    f'no cloud mask under prefix {cloud_mask} in noaa-goes19'
                )

            cm_object_key = s3_result_CM['Contents'][0]['Key']
            cm_path = awsAccessGOES.__local_path(key, cm_object_key, "_cm")
            if (not os.path.exists(cm_path)):
                s3_client.download_file('noaa-goes19', cm_object_key, cm_path)
            awsAccessGOES.__drop_stale(key, cm_path, "_cm")

        return path

    @staticmethod
    def __get_info(key: str, need_CM: bool =False, band: int = 0, slots_atras: int = 0) -> list[str]:
        """Get all the necessary info to find a archive on aws.

        slots_atras recua janelas inteiras de 10 min além do recuo base — é o
        que permite ao download_aws tentar o granule anterior quando o slot
        calculado ainda não foi publicado pela NOAA (atraso transitório e
        rotineiro que antes virava 501 para o usuário).
        """
        
        products = awsAccessGOES.__products

        # Read the clock now, on every call.
        #
        # This used to be a class attribute, evaluated once when the module was
        # imported — that is, once per cold start. Every later request in the
        # same container rebuilt the same S3 prefix from a timestamp frozen
        # minutes or hours earlier, and since the cache was keyed by product
        # rather than by granule, it kept answering with the same flashes. A
        # warm container served a snapshot of whenever it happened to start.
        date = datetime.datetime.now(datetime.timezone.utc)

        product_name = products[key]

        # Rewind to a granule that has certainly been published: GOES uploads
        # are minutes behind real time, and asking for the current slot returns
        # an empty listing.
        date = date - datetime.timedelta(minutes=(date.minute % 10) + 10 + 10 * slots_atras)

        year = date.year
        hour = date.hour
        minutes = date.minute

        # tm_yday is the day of the year the calendar already knows how to
        # compute. The two hand-written month tables it replaces decided leap
        # years with `year % 4 == 0`, which is wrong in 2100 and, more to the
        # point, is arithmetic nobody needs to own.
        day_of_year = date.timetuple().tm_yday

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
