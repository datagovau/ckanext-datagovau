#!/usr/bin/python
# coding=utf-8
'''
spatial ingestor for data.gov.au
<greg.vonnessi@linkdigital.com.au>
1.0 28/11/2013 initial implementation
1.1 25/03/2014 new create_resource technique for CKAN editing
1.2 08/09/2014 projection guessing, JNDI database connection and better
               modification detection
1.3 24/09/2014 grid raster support
1.4 16/01/2015 unzip files into flat structure, record wms layer
               name for future expansion
'''
from __future__ import print_function

import calendar
import errno
import glob
import grp
import json
import logging
import os
import pwd
import shutil
import subprocess
import sys
import tempfile
import time
import urllib
import urllib2
from datetime import datetime

import ckan.model as model
import lxml.etree as et
import psycopg2
import requests
from ckan.lib import cli
from ckan.plugins import toolkit
from ckan.plugins.toolkit import get_action
from dateutil import parser
from osgeo import osr
from pylons import config

from ckanext.datagovau import ogr2ogr, gdal_retile
opener = urllib2.build_opener()
opener.addheaders = [('Authorization','c3557c21-bfda-44e7-a5c3-c97de603d56b')]
urllib2.install_opener(opener)

reload(sys)
sys.setdefaultencoding('utf8')

logger = logging.getLogger('root')
log_handler = logging.StreamHandler()
log_handler.setFormatter(
    logging.Formatter("%(asctime)s - [%(levelname)8s] - %(message)s")
)
logger.addHandler(log_handler)
logger.setLevel(logging.DEBUG)

logger.info = logger.warn = logger.debug = logger.error = print

# Sometimes the geoserver gets overloaded. So, we re-try a number of times for
# Post/put queries.
sleep_duration = 20  # in seconds
num_retries = 30


class IngestionFail(Exception):
    pass


class IngestionSkip(Exception):
    pass


def _get_dir_from_config(config_param):
    result = config.get(config_param).rstrip()
    if result.endswith('/'):
        result = result[:-1]
    return result


def _get_tmp_path():
    return _get_dir_from_config('ckanext.datagovau.spatialingestor.tmp_dir')


def _get_geoserver_data_dir(native_name=None):
    if native_name:
        return _get_geoserver_data_dir() + '/' + native_name
    else:
        return _get_dir_from_config('ckanext.datagovau.spatialingestor.geoserver.base_dir')


def _mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


def _get_site_url():
    result = config.get('ckan.site_url').rstrip()
    if result.endswith('/'):
        result = result[:-1]
    return result


def _get_geoserver_data():
    geoserver_info = cli.parse_db_config('ckanext.datagovau.spatialingestor.geoserver.url')
    protocol = "http://"

    if geoserver_info.get('db_type') == 'sslgeoserver':
        protocol = "https://"

    geoserver_host = protocol + geoserver_info.get('db_host')

    port = geoserver_info.get('db_port', '')
    if port != '':
        geoserver_host += ':' + port

    geoserver_host += '/' + geoserver_info.get('db_name') + '/'
    return (
        geoserver_host,
        geoserver_info.get('db_user'),
        geoserver_info.get('db_pass'),
        config.get('ckanext.datagovau.spatialingestor.geoserver.public_url')
    )


def _get_db_settings():
    postgis_info = cli.parse_db_config('ckanext.datagovau.spatialingestor.postgis.url')

    db_port = postgis_info.get('db_port', '')
    if db_port == '':
        db_port = None

    return dict(
        dbname=postgis_info.get('db_name'),
        user=postgis_info.get('db_user'),
        password=postgis_info.get('db_pass'),
        host=postgis_info.get('db_host'),
        port=db_port
    )


def _make_request(command, url, **kwargs):
    print(url)
    count = 0
    time_out = _get_request_timeout()
    while count < time_out:
        try:
            r = command(url, **kwargs)
        except Exception,e:
            print(e)
            count += 10
            time.sleep(10)
        else:
            return r

    _failure("Failed to make request {} : {}".format(command, url))
    return None


def _get_db_param_string(db_settings):
    result = 'PG:dbname=\'' + db_settings['dbname'] + '\' host=\'' + db_settings['host'] + '\' user=\'' + db_settings[
        'user'] + '\' password=\'' + db_settings['password'] + '\''

    if db_settings.get('port'):
        result += ' port=\'' + db_settings['port'] + '\''

    return result


def _get_username():
    return config.get('ckanext.datagovau.spatialingestor.username')


def _get_blacklisted_orgs():
    return set(toolkit.aslist(config.get('ckanext.datagovau.spatialingestor.org_blacklist', [])))


def _get_blacklisted_pkgs():
    return set(toolkit.aslist(config.get('ckanext.datagovau.spatialingestor.pkg_blacklist', [])))


def _get_target_formats():
    return set(toolkit.aslist(config.get('ckanext.datagovau.spatialingestor.target_formats', [])))


def _get_source_formats():
    return set(toolkit.aslist(config.get('ckanext.datagovau.spatialingestor.source_formats', [])))


def _get_request_timeout():
    return config.get('ckanext.datagovau.spatialingestor.request_timeout')


def _get_valid_qname(raw_string):
    if any([c.isalpha() for c in raw_string]):
        if not (raw_string == '' or raw_string[0].isalpha()):
            raw_string += '-'
            while not raw_string[0].isalpha():
                first_literal = raw_string[0]
                raw_string = raw_string[1:]
                if first_literal.isdigit():
                    raw_string += first_literal
            if raw_string[-1] == '-':
                raw_string = raw_string[:-1]
    else:
        raw_string = 'ckan-' + raw_string

    return raw_string


def _get_dataset_from_id(dataset_id):
    dataset = None
    try:
        dataset = get_action('package_show')(
            {'model': model, 'user': _get_username(), 'ignore_auth': True},
            {'id': dataset_id})
    except:
        pass

    return dataset


def _clean_dir(tempdir):
    try:
        shutil.rmtree(tempdir, ignore_errors=True)
    except:
        pass


def _get_cursor(db_settings):
    # Connect to an existing database
    try:
        conn = psycopg2.connect(**db_settings)
    except:
        _failure("I am unable to connect to the database.")
    # Open a cursor to perform database operations
    cur = conn.cursor()
    conn.set_isolation_level(0)
    # Execute a command: this creates a new table
    # cur.execute("create extension postgis")
    return cur, conn


def _parse_date(date_str):
    try:
        return calendar.timegm(parser.parse(date_str).utctimetuple())
    except Exception:
        return


def _success():
    logger.info("Completed!")


def _failure(msg):
    logger.error(msg)
    raise IngestionFail(msg)


def _group_resources(dataset):
    shp = []
    kml = []
    tab = []
    tiff = []
    grid = []
    sld = []

    source_formats = map(lambda x: x.lower(), _get_source_formats())

    def _valid_source_format(input_format):
        return any([input_format.lower() in x for x in source_formats])

    if dataset and 'resources' in dataset:
        for resource in dataset['resources']:
            _format = resource['format'].lower()

            if '/geoserver' in resource['url']:
                pass
            elif ("kml" in _format and _valid_source_format("kml")) or (
                            "kmz" in _format and _valid_source_format("kmz")):
                kml.append(resource)
            elif ("shp" in _format and _valid_source_format("shp")) or (
                            "shapefile" in _format and _valid_source_format("shapefile") or ("shz" in _format and _valid_source_format("shz"))):
                shp.append(resource)
            elif "tab" in _format and _valid_source_format("tab"):
                tab.append(resource)
            elif "grid" in _format and _valid_source_format("grid"):
                grid.append(resource)
            elif "geotif" in _format and _valid_source_format("geotif"):
                tiff.append(resource)
            elif "geotiff" in _format and _valid_source_format("geotiff"):
                tiff.append(resource)
            elif "sld" in _format:
                sld.append(resource)

    return shp, kml, tab, tiff, grid, sld


def _clear_old_table(dataset):
    cur, conn = _get_cursor(_get_db_settings())
    table_name = "ckan_" + dataset['id'].replace("-", "_")
    cur.execute('DROP TABLE IF EXISTS "' + table_name + '"')
    cur.close()
    conn.close()
    return table_name


def _create_geoserver_data_dir(native_name):
    data_output_dir = _get_geoserver_data_dir(native_name)
    _mkdir_p(data_output_dir)
    return data_output_dir


def _set_geoserver_ownership(data_dir):
    uid = pwd.getpwnam(config.get('ckanext.datagovau.spatialingestor.geoserver.os_user')).pw_uid
    gid = grp.getgrnam(config.get('ckanext.datagovau.spatialingestor.geoserver.os_group')).gr_gid
    os.chown(data_dir, uid, gid)
    for root, dirs, files in os.walk(data_dir):
        for momo in dirs:
            os.chown(os.path.join(root, momo), uid, gid)
        for momo in files:
            os.chown(os.path.join(root, momo), uid, gid)


def _load_esri_shapefiles(shp_res, table_name, tempdir):
    shp_res['url'] = shp_res['url'].replace('https', 'http')
    logger.debug(
        "Using SHP file " + shp_res['url'])

    if not any([shp_res['url'].lower().endswith(x) for x in ["shp", "shapefile"]]):
        with open("input.zip", "wb") as f:
            f.write(urllib2.urlopen(shp_res['url']).read())
        logger.debug('SHP downloaded')

        subprocess.call(['unzip', '-j', "input.zip"])
        logger.debug('SHP unzipped')
    else:
        urllib.urlretrieve(
            shp_res['url'], "input.shp")
        logger.debug('SHP downloaded')

    shpfiles = glob.glob("*.[sS][hH][pP]")
    prjfiles = glob.glob("*.[pP][rR][jJ]")
    if not shpfiles:
        _failure("No shp files found in zip " + shp_res['url'])
    logger.debug("converting to pgsql " + table_name + " " + shpfiles[0])

    srs_found = False

    if len(prjfiles) > 0:
        prj_txt = open(prjfiles[0], 'r').read()
        sr = osr.SpatialReference()
        sr.ImportFromESRI([prj_txt])

        res = sr.AutoIdentifyEPSG()
        if res == 0:  # success
            native_crs = sr.GetAuthorityName(
                None) + ":" + sr.GetAuthorityCode(None)
            srs_found = True
        else:
            mapping = {
                "EPSG:28356": [
                    "GDA_1994_MGA_Zone_56", "GDA94_MGA_zone_56"],
                "EPSG:28355": [
                    "GDA_1994_MGA_Zone_55", "GDA94_MGA_zone_55"],
                "EPSG:28354": [
                    "GDA_1994_MGA_Zone_54", "GDA94_MGA_zone_54"],
                "EPSG:4283": [
                    "GCS_GDA_1994",
                    'GEOGCS["GDA94",DATUM["D_GDA_1994",SPHEROID["GRS_1980"'],
                "ESRI:102029": ["Asia_South_Equidistant_Conic"],
                "EPSG:3577": ["Australian_Albers_Equal_Area_Conic_WGS_1984"],
                "EPSG:3857": ["WGS_1984_Web_Mercator_Auxiliary_Sphere"],
                "EPSG:4326": [
                    "MapInfo Generic Lat/Long",
                    'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984"']
            }
            for key, values in mapping.items():
                if any([v in prj_txt for v in values]):
                    native_crs = key
                    srs_found = True
                    break
            else:
                native_crs = 'EPSG:4326'
                # failure(
                #    dataset['title'] + " has unknown projection: " + prj_txt)
    else:
        # if wyndham then GDA_1994_MGA_Zone_55 EPSG:28355
        native_crs = "EPSG:4326"

    pargs = [
        ' ',
        '-f', 'PostgreSQL',
        "--config", "PG_USE_COPY", "YES",
        _get_db_param_string(_get_db_settings()),
        tempdir,
        '-lco', 'GEOMETRY_NAME=geom',
        "-lco", "PRECISION=NO",
        '-nln', table_name,
        '-t_srs', native_crs,
        '-nlt', 'PROMOTE_TO_MULTI',
        '-overwrite'
    ]

    if not srs_found:
        pargs = [
            ' ',
            '-f', 'PostgreSQL',
            "--config", "PG_USE_COPY", "YES",
            _get_db_param_string(_get_db_settings()),
            tempdir,
            '-lco', 'GEOMETRY_NAME=geom',
            "-lco", "PRECISION=NO",
            '-nln', table_name,
            '-t_srs', native_crs,
            '-nlt', 'PROMOTE_TO_MULTI',
            '-overwrite'
        ]
	print(pargs)
    res = ogr2ogr.main(pargs)
    if not res:
        _failure("Ogr2ogr: Failed to convert file to PostGIS")

    return native_crs


def _load_kml_resources(kml_res, table_name):
    kml_res['url'] = kml_res['url'].replace('https', 'http')
    logger.debug(
        "Using KML file " + kml_res['url'])
    native_crs = 'EPSG:4326'
    # if kml ogr2ogr http://gis.stackexchange.com/questions/33102
    # /how-to-import-kml-file-with-custom-data-to-postgres-postgis-database
    if kml_res['format'] == "kmz" or 'kmz' in kml_res['url'].lower():
        with open("input.zip", "wb") as f:
            f.write(urllib2.urlopen(kml_res['url']).read())
        subprocess.call(['unzip', '-j', "input.zip"])
        logger.debug("KMZ unziped")
        kmlfiles = glob.glob("*.[kK][mM][lL]")
        if len(kmlfiles) == 0:
            _failure("No kml files found in zip " + kml_res['url'])
        else:
            kml_file = kmlfiles[0]
    else:
        filepath, headers = urllib.urlretrieve(kml_res['url'], "input.kml")
        kml_file = "input.kml"

    logger.debug("Changing kml folder name in " + kml_file)
    tree = et.parse(kml_file)
    element = tree.xpath(
        '//kml:Folder/kml:name',
        namespaces={'kml': "http://www.opengis.net/kml/2.2"})
    if 0 in element:
        element[0].text = table_name
    else:
        logger.debug('No kml:Folder tag found')
    find = et.ETXPath(
        '//{http://www.opengis.net/kml/2.2}Folder'
        '/{http://www.opengis.net/kml/2.2}name'
    )
    element = find(tree)
    if len(element):
        for x in range(0, len(element)):
            logger.debug(element[x].text)
            element[x].text = table_name
    else:
        logger.debug('no Folder tag found')
    find = et.ETXPath(
        '//{http://earth.google.com/kml/2.1}Folder'
        '/{http://earth.google.com/kml/2.1}name'
    )
    element = find(tree)
    if len(element):
        for x in range(0, len(element)):
            # print(element[x].text)
            element[x].text = table_name
    else:
        logger.debug('no Folder tag found')
    with open(table_name + ".kml", "w") as ofile:
        ofile.write(et.tostring(tree))
    logger.debug("converting to pgsql " + table_name + ".kml")

    pargs = [
        '',
        '-f', 'PostgreSQL',
        "--config", "PG_USE_COPY", "YES",
        _get_db_param_string(_get_db_settings()),
        table_name + ".kml",
        '-lco', 'GEOMETRY_NAME=geom',
        "-lco", "PRECISION=NO",
        '-nln', table_name,
        '-nlt', 'PROMOTE_TO_MULTI',
        '-t_srs', native_crs,
        '-overwrite'
    ]

    res = ogr2ogr.main(pargs)
    if not res:
        _failure("Ogr2ogr: Failed to convert file to PostGIS")

    return native_crs


def _load_tab_resources(tab_res, table_name):
    url = tab_res['url'].replace('https', 'http')
    logger.debug("using TAB file " + url)
    filepath, headers = urllib.urlretrieve(url, "input.zip")
    logger.debug("TAB archive downlaoded")

    subprocess.call(['unzip', '-j', filepath])
    logger.debug("TAB unziped")

    tabfiles = glob.glob("*.[tT][aA][bB]")
    if len(tabfiles) == 0:
        _failure("No tab files found in zip " + tab_res['url'])

    tab_file = tabfiles[0]

    native_crs = 'EPSG:4326'

    pargs = [
        '',
        '-f', 'PostgreSQL',
        "--config", "PG_USE_COPY", "YES",
        _get_db_param_string(_get_db_settings()),
        tab_file,
        '-nln', table_name,
        '-lco', 'GEOMETRY_NAME=geom',
        "-lco", "PRECISION=NO",
        '-t_srs', native_crs,
        '-nlt', 'PROMOTE_TO_MULTI',
        '-overwrite'
    ]

    res = ogr2ogr.main(pargs)
    if not res:
        _failure("Ogr2ogr: Failed to convert file to PostGIS")

    return native_crs


def _load_tiff_resources(tiff_res, table_name):
    url = tiff_res['url'].replace('https', 'http')
    logger.debug("using GeoTIFF file " + url)

    if not any([url.lower().endswith(x) for x in ['tif', 'tiff']]):
        filepath, headers = urllib.urlretrieve(url, "input.zip")
        logger.debug("GeoTIFF archive downlaoded")

        subprocess.call(['unzip', '-j', filepath])
        logger.debug("GeoTIFF unziped")
    else:
        urllib.urlretrieve(url, "input.tiff")

    tifffiles = glob.glob("*.[tT][iI][fF]") + glob.glob("*.[tT][iI][fF][fF]")
    if len(tifffiles) == 0:
        _failure("No TIFF files found in " + tiff_res['url'])

    native_crs = 'EPSG:4326'

    large_file = os.stat(tifffiles[0]).st_size > long(
        config.get('ckanext.datagovau.spatialingestor.large_file_threshold'))

    if large_file:
        pargs = [
            'gdal_translate',
            '-ot', 'Byte',
            tifffiles[0],
            table_name + "_temp.tiff"
        ]

        subprocess.call(pargs)

        pargs = [
            'gdalwarp',
            '--config', 'GDAL_CACHEMAX', '500',
            '-wm', '500',
            '-multi',
            '-t_srs', native_crs,
            '-of', 'GTiff',
            '-co', 'TILED=YES',
            '-co', 'TFW=YES',
            '-co', 'BIGTIFF=YES',
            '-co', 'COMPRESS=CCITTFAX4',
            '-co', 'NBITS=1',
            table_name + "_temp.tiff",
            table_name + ".tiff"
        ]
    else:
        pargs = [
            'gdalwarp',
            '--config', 'GDAL_CACHEMAX', '500',
            '-wm', '500',
            '-multi',
            '-t_srs', native_crs,
            '-of', 'GTiff',
            '-co', 'TILED=YES',
            '-co', 'TFW=YES',
            '-co', 'BIGTIFF=YES',
            '-co', 'COMPRESS=PACKBITS',
            tifffiles[0],
            table_name + ".tiff"
        ]

    subprocess.call(pargs)

    data_output_dir = _create_geoserver_data_dir(table_name)

    if large_file:
        pargs = [
            '',
            '-v',
            '-r', 'near',
            '-levels', '3',
            '-ps', '1024', '1024',
            '-co', 'TILED=YES',
            '-co', 'COMPRESS=CCITTFAX4',
            '-co', 'NBITS=1',
            '-targetDir', data_output_dir,
            table_name + ".tiff"
        ]
    else:
        pargs = [
            '',
            '-v',
            '-r', 'near',
            '-levels', '3',
            '-ps', '1024', '1024',
            '-co', 'TILED=YES',
            '-co', 'COMPRESS=PACKBITS',
            '-targetDir', data_output_dir,
            table_name + ".tiff"
        ]

    gdal_retile.main(pargs)

    _set_geoserver_ownership(data_output_dir)
    return native_crs


def _load_grid_resources(grid_res, table_name, tempdir):
    grid_res['url'] = grid_res['url'].replace('https', 'http')
    logger.debug("Using ArcGrid file " + grid_res['url'])

    filepath, headers = urllib.urlretrieve(grid_res['url'], "input.zip")
    logger.debug("ArcGrid downlaoded")

    subprocess.call(['unzip', '-j', filepath])
    logger.debug('ArcGrid unzipped')

    native_crs = 'EPSG:4326'

    pargs = [
        'gdalwarp',
        '--config', 'GDAL_CACHEMAX', '500',
        '-wm', '500',
        '-multi',
        '-t_srs', native_crs,
        '-of', 'GTiff',
        '-co', 'TILED=YES',
        '-co', 'TFW=YES',
        '-co', 'BIGTIFF=YES',
        '-co', 'COMPRESS=PACKBITS',
        tempdir,
        table_name + "_temp1.tiff"
    ]

    subprocess.call(pargs)

    large_file = os.stat(table_name + "_temp1.tiff").st_size > long(
        config.get('ckanext.datagovau.spatialingestor.large_file_threshold'))

    if large_file:
        pargs = [
            'gdal_translate',
            '-ot', 'Byte',
            table_name + "_temp1.tiff",
            table_name + "_temp2.tiff"
        ]

        subprocess.call(pargs)

        pargs = [
            'gdalwarp',
            '--config', 'GDAL_CACHEMAX', '500',
            '-wm', '500',
            '-multi',
            '-t_srs', native_crs,
            '-of', 'GTiff',
            '-co', 'TILED=YES',
            '-co', 'TFW=YES',
            '-co', 'BIGTIFF=YES',
            '-co', 'COMPRESS=CCITTFAX4',
            '-co', 'NBITS=1',
            table_name + "_temp2.tiff",
            table_name + ".tiff"
        ]
    else:
        pargs = [
            'gdalwarp',
            '--config', 'GDAL_CACHEMAX', '500',
            '-wm', '500',
            '-multi',
            '-t_srs', native_crs,
            '-of', 'GTiff',
            '-co', 'TILED=YES',
            '-co', 'TFW=YES',
            '-co', 'BIGTIFF=YES',
            '-co', 'COMPRESS=PACKBITS',
            table_name + "_temp1.tiff",
            table_name + ".tiff"
        ]

    subprocess.call(pargs)

    data_output_dir = _create_geoserver_data_dir(table_name)

    if large_file:
        pargs = [
            '',
            '-v',
            '-r', 'near',
            '-levels', '3',
            '-ps', '1024', '1024',
            '-co', 'TILED=YES',
            '-co', 'COMPRESS=CCITTFAX4',
            '-co', 'NBITS=1',
            '-targetDir', data_output_dir,
            table_name + ".tiff"
        ]
    else:
        pargs = [
            '',
            '-v',
            '-r', 'near',
            '-levels', '3',
            '-ps', '1024', '1024',
            '-co', 'TILED=YES',
            '-co', 'COMPRESS=PACKBITS',
            '-targetDir', data_output_dir,
            table_name + ".tiff"
        ]

    gdal_retile.main(pargs)

    _set_geoserver_ownership(data_output_dir)
    return native_crs


def _apply_sld(name, workspace, layer_name, url=None, filepath=None):
    geo_addr, geo_user, geo_pass, geo_public_addr = _get_geoserver_data()

    style_url = geo_addr + 'rest/workspaces/' + workspace + '/styles/' + name

    if url:
        r = _make_request(
            requests.get,
            url, headers={'Authorization': 'c3557c21-bfda-44e7-a5c3-c97de603d56b'})
        if r and r.ok:
            with open("input.sld", "wb") as f:
                f.write(r.text)
            filepath="input.sld"
        else:
            logger.error("error downloading SLD")
            return
    elif filepath:
        logger.info("sld downloaded")
        pass
    else:
        logger.error("error accessing SLD")
        return

    payload = open(filepath, 'rb')

    r = _make_request(
        requests.get,
        style_url,
        params={'quietOnNotFound': True},
        auth=(geo_user, geo_pass))

    if r and r.ok:
        url = style_url

        logger.info("Delete out old style in workspace")
        r = _make_request(
            requests.delete,
            url,
            auth=(geo_user, geo_pass))

    url = geo_addr + 'rest/workspaces/' + workspace + '/styles'

    r = _make_request(
        requests.post,
        url,
        data=json.dumps({
            'style': {
                'name': name,
                'filename': name + '.sld'
            }
        }),
        headers={'Content-type': 'application/json'},
        auth=(geo_user, geo_pass))

    sld_text = open(filepath, 'r').read()
    mapping = {
        "application/vnd.ogc.sld+xml": "www.opengis.net/sld",
        "application/vnd.ogc.se+xml": "www.opengis.net/se",
    }
    for key, value in mapping.items():
        if value in sld_text:
            content_type = key
            break
    else:
        logger.error("couldn't pick a sld content type")
        return
    logger.info("sld content type: "+content_type)
    r = _make_request(
        requests.put,
        url + '/' + name+"?raw=true",
        data=payload,
        headers={'Content-type': content_type},
        auth=(geo_user, geo_pass))

    if r.status_code == 400:
        logger.info("Delete out old style in workspace")
        r = _make_request(
            requests.delete,
            style_url,
            auth=(geo_user, geo_pass))
        r = _make_request(
            requests.put,
            url + '/' + name,
            data=payload,
            headers={'Content-type': content_type},
            auth=(geo_user, geo_pass))

    r = _make_request(
        requests.put,
        geo_addr + 'rest/layers/' + layer_name,
        data=json.dumps({
            'layer': {
                'defaultStyle': {
                    'name': name,
                    'workspace': workspace
                }
            }
        }),
        headers={'Content-type': 'application/json'},
        auth=(geo_user, geo_pass))


def _apply_sld_resources(sld_res, workspace, layer_name):
    # Procedure for updating layer to use default style comes from
    # http://docs.geoserver.org/stable/en/user/rest/examples/curl.html that
    # explains the below steps in the 'Changing a layer style' section

    name = os.path.splitext(os.path.basename(sld_res['url']))[0]

    r = _make_request(
        requests.get,
        sld_res['url'], headers={'Authorization': 'c3557c21-bfda-44e7-a5c3-c97de603d56b'})

    if r and r.ok:
        _apply_sld(name, workspace, layer_name, url=sld_res['url'], filepath=None)
    else:
        logger.error("could not download SLD resource")

def _convert_resources(table_name, temp_dir, shp_resources, kml_resources, tab_resources, tiff_resources,
                       grid_resources):
    using_kml = False
    using_grid = False
    native_crs = ''

    if len(shp_resources):
        native_crs = _load_esri_shapefiles(shp_resources[0], table_name, temp_dir)
    elif len(kml_resources):
        using_kml = True
        native_crs = _load_kml_resources(kml_resources[0], table_name)
    elif len(tab_resources):
        native_crs = _load_tab_resources(tab_resources[0], table_name)
    elif len(tiff_resources):
        using_grid = True
        native_crs = _load_tiff_resources(tiff_resources[0], table_name)
    elif len(grid_resources):
        using_grid = True
        native_crs = _load_grid_resources(grid_resources[0], table_name, temp_dir)

    return using_kml, using_grid, native_crs


def _get_geojson(using_kml, table_name):
    cur, conn = _get_cursor(_get_db_settings())
    if using_kml:
        try:
            cur.execute(
                ('alter table "{}" DROP "description" RESTRICT, '
                 'DROP timestamp RESTRICT, DROP begin RESTRICT, '
                 'DROP "end" RESTRICT, DROP altitudemode RESTRICT, '
                 'DROP tessellate RESTRICT, DROP extrude RESTRICT, '
                 'DROP visibility RESTRICT, DROP draworder RESTRICT, '
                 'DROP icon RESTRICT;').format(table_name)
            )
        except Exception:
            logger.error('KML error', exc_info=True)
    select_query = (
        'SELECT ST_Extent(geom) as box,'
        'ST_Extent(ST_Transform(geom,4326)) as latlngbox, '
        'ST_AsGeoJSON(ST_Extent(ST_Transform(geom,4326))) as geojson '
        'from "{}"').format(table_name)
    cur.execute(select_query)
    # logger.debug(select_query)

    bbox, latlngbbox, bgjson = cur.fetchone()
    cur.close()
    conn.close()
    return bbox, latlngbbox, bgjson


def _perform_workspace_requests(datastore, workspace, table_name=None):
    if not table_name:
        dsdata = json.dumps({
            'dataStore': {
                'name': datastore,
                'connectionParameters': {
                    'dbtype': 'postgis',
                    "encode functions": "false",
                    "jndiReferenceName": "java:comp/env/jdbc/postgres",
                    # jndi name you have setup in tomcat http://docs.geoserver.org
                    # /stable/en/user/tutorials/tomcat-jndi/tomcat-jndi.html
                    # #configuring-a-postgresql-connection-pool
                    "Support on the fly geometry simplification": "true",
                    "Expose primary keys": "false",
                    "Estimated extends": "false"
                }
            }
        })
    else:
        dsdata = json.dumps({
            'coverageStore': {
                'name': datastore,
                'type': 'ImagePyramid',
                'enabled': True,
                'url': 'file:data/' + table_name,
                'workspace': workspace
            }
        })

    # logger.debug(dsdata)

    geo_addr, geo_user, geo_pass, geo_public_addr = _get_geoserver_data()
    # POST creates, PUT updates
    _base_url = geo_addr + 'rest/workspaces/' + workspace
    if table_name:
        _base_url += '/coveragestores'
    else:
        _base_url += '/datastores'

    r = _make_request(
        requests.post,
        _base_url,
        data=dsdata,
        headers={'Content-type': 'application/json'},
        auth=(geo_user, geo_pass))

    if not r or not r.ok:
        _failure("Failed to create Geoserver store {}: {}".format(_base_url, r.content))


def _update_package_with_bbox(bbox, latlngbbox, ftdata,
                              dataset, native_crs, bgjson):
    def _clear_box(string):
        return string.replace(
            "BOX", "").replace("(", "").replace(
            ")", "").replace(",", " ").split(" ")

    minx, miny, maxx, maxy = _clear_box(bbox)
    bbox_obj = {
        'minx': minx,
        'maxx': maxx,
        'miny': miny,
        'maxy': maxy,
        'crs': native_crs}

    llminx, llminy, llmaxx, llmaxy = _clear_box(latlngbbox)
    llbbox_obj = {
        'minx': llminx,
        'maxx': llmaxx,
        'miny': llminy,
        'maxy': llmaxy,
        'crs': 'EPSG:4326'
    }

    ftdata['featureType']['nativeBoundingBox'] = bbox_obj
    ftdata['featureType']['latLonBoundingBox'] = llbbox_obj
    update = False
    if float(llminx) < -180 or float(llmaxx) > 180:
        _failure(dataset['title'] + " has invalid automatic projection:" +
                 native_crs)
    else:
        ftdata['featureType']['srs'] = native_crs
        # logger.debug('bgjson({}), llbox_obj({})'.format(bgjson, llbbox_obj))
        if 'spatial' not in dataset or dataset['spatial'] != bgjson:
            dataset['spatial'] = bgjson
            update = True
    if update:
        get_action('package_update')(
            {'user': _get_username(), 'model': model}, dataset)
    return bbox_obj


def _create_resources_from_formats(
        ws_addr, layer_name, bbox_obj, existing_formats, dataset, using_grid):
    bbox_str = "&bbox=" + bbox_obj['minx'] + "," + bbox_obj['miny'] + "," + bbox_obj['maxx'] + "," + bbox_obj[
        'maxy'] if bbox_obj else ''

    for _format in _get_target_formats():  # ['kml', 'image/png']:
        url = (
            ws_addr + "wms?request=GetMap&layers=" +
            layer_name + bbox_str + "&width=512&height=512&format=" +
            urllib.quote(_format))
        if _format == "image/png" and _format not in existing_formats:
            logger.debug("Creating PNG Resource")
            get_action('resource_create')(
                {'model': model, 'user': _get_username()}, {
                    "package_id": dataset['id'],
                    "name": dataset['title'] + " Preview Image",
                    "description": "View overview image of this dataset",
                    "format": _format,
                    "url": url,
                    "last_modified": datetime.now().isoformat()
                })
        elif _format == "kml":
            if _format not in existing_formats:
                logger.debug("Creating KML Resource")
                get_action('resource_create')(
                    {'user': _get_username(), 'model': model}, {
                        "package_id": dataset['id'],
                        "name": dataset['title'] + " KML",
                        "description": (
                            "View a map of this dataset in web "
                            "and desktop spatial data tools"
                            " including Google Earth"),
                        "format": _format,
                        "url": url,
                        "last_modified": datetime.now().isoformat()
                    })
        elif _format in ["wms", "wfs"] and _format not in existing_formats:
            if _format == "wms":
                logger.debug("Creating WMS API Endpoint Resource")
                get_action('resource_create')(
                    {'model': model, 'user': _get_username()}, {
                        "package_id": dataset['id'],
                        "name": dataset['title'] + " - Preview this Dataset (WMS)",
                        "description": ("View the data in this "
                                        "dataset online via an online map"),
                        "format": "wms",
                        "url": ws_addr + "wms?request=GetCapabilities",
                        "wms_layer": layer_name,
                        "last_modified": datetime.now().isoformat()
                    })
            else:
                logger.debug("Creating WFS API Endpoint Resource")
                get_action('resource_create')(
                    {'model': model, 'user': _get_username()}, {
                        "package_id": dataset['id'],
                        "name": dataset['title'] + " Web Feature Service API Link",
                        "description": "WFS API Link for use in Desktop GIS tools",
                        "format": "wfs",
                        "url": ws_addr + "wfs",
                        "wfs_layer": layer_name,
                        "last_modified": datetime.now().isoformat()
                    })
        elif _format in ['json', 'geojson'] and not using_grid:
            url = (ws_addr + "wfs?request=GetFeature&typeName=" +
                   layer_name + "&outputFormat=" + urllib.quote('json'))
            if not any([x in existing_formats for x in ["json", "geojson"]]):
                logger.debug("Creating GeoJSON Resource")
                get_action('resource_create')(
                    {'model': model, 'user': _get_username()}, {
                        "package_id": dataset['id'],
                        "name": dataset['title'] + " GeoJSON",
                        "description": ("For use in web-based data "
                                        "visualisation of this collection"),
                        "format": "geojson",
                        "url": url,
                        "last_modified": datetime.now().isoformat()
                    })


def _delete_resources(dataset):
    geoserver_resources = filter(
        lambda x: any(
            [old_urls in x['url'] and '/geoserver' in x['url'] for old_urls in ['dga.links.com.au', 'data.gov.au']]),
        dataset['resources'])

    for res in geoserver_resources:
        get_action('resource_delete')(
            {'model': model, 'user': _get_username(), 'ignore_auth': True}, res)

    return _get_dataset_from_id(dataset['id'])


def _prepare_everything(
        dataset,
        shp_resources, kml_resources, tab_resources, tiff_resources, grid_resources,
        tempdir):
    # clear old data table
    table_name = _clear_old_table(dataset)

    # clear out old filestore
    _clean_dir(_get_geoserver_data_dir(table_name))

    # download resource to tmpfile
    os.chdir(tempdir)
    logger.debug(tempdir + " created")
    using_kml, using_grid, native_crs = \
        _convert_resources(
            table_name,
            tempdir,
            shp_resources, kml_resources, tab_resources, tiff_resources, grid_resources)

    # create geoserver workspace/layers http://boundlessgeo.com
    # /2012/10/adding-layers-to-geoserver-using-the-rest-api/
    # name workspace after dataset
    geo_addr, geo_user, geo_pass, geo_public_addr = _get_geoserver_data()
    workspace = _get_valid_qname(dataset['name'])

    _base_url = geo_addr + 'rest/workspaces'
    _ws_url = _base_url + '/' + workspace

    r = _make_request(
        requests.head,
        _ws_url,
        auth=(geo_user, geo_pass))

    if r and r.ok:
        url = _ws_url + '?recurse=true&quietOnNotFound'
        r = _make_request(
            requests.delete,
            url,
            auth=(geo_user, geo_pass))

    r = _make_request(
        requests.post,
        _base_url,
        data=json.dumps({
            'workspace': {
                'name': workspace
            }
        }),
        headers={'Content-type': 'application/json'},
        auth=(geo_user, geo_pass))

    if not r or not r.ok:
        _failure("Failed to create Geoserver workspace {}: {}".format(_base_url, r.content))

    # load bounding boxes from database
    return using_kml, using_grid, table_name, workspace, native_crs


def check_if_may_skip(dataset_id, force=False):
    dataset = _get_dataset_from_id(dataset_id)

    """Skip blacklisted orgs, datasets and datasets, updated by bot
    """

    if not dataset:
        raise IngestionSkip("No package found to ingest")

    if not dataset.get('organization', None) or 'name' not in dataset['organization']:
        raise IngestionSkip("Package must be associate with valid organization to be ingested")

    org_name = dataset['organization']['name']
    if org_name in _get_blacklisted_orgs():
        raise IngestionSkip(org_name + " in omitted_orgs blacklist")

    if dataset['name'] in _get_blacklisted_pkgs():
        raise IngestionSkip(dataset['name'] + " in omitted_pkgs blacklist")

    if dataset.get('harvest_source_id', '') != '' or str(dataset.get('spatial_harvester', False)).lower()[0] == 't':
        raise IngestionSkip('Harvested datasets are not eligible for ingestion')

    if str(dataset.get('private', False)).lower()[0] == 't' and org_name not in ('infrastructure-australia'):
        raise IngestionSkip('Private datasets are not eligible for ingestion')

    if dataset.get('state', '') != 'active':
        raise IngestionSkip('Dataset must be active to ingest')

    (shp_resources, kml_resources, tab_resources, tiff_resources, grid_resources, sld_resources) = _group_resources(
        dataset)

    grouped_resources = (shp_resources, kml_resources, tab_resources, tiff_resources, grid_resources)
    all_resources = (shp_resources, kml_resources, tab_resources, tiff_resources, grid_resources, sld_resources)

    if not any(grouped_resources):
        raise IngestionSkip("No geodata format files detected")
    if any([len(x) > 1 for x in grouped_resources]):
        raise IngestionSkip("Can not determine unique spatial file to ingest")

    if force:
        return dataset, all_resources

    activity_list = get_action('package_activity_list')(
        {'user': _get_username(), 'model': model},
        {'id': dataset['id']})

    user = get_action('user_show')(
        {'user': _get_username(), 'model': model, 'ignore_auth': True},
        {'id': _get_username()})

    if activity_list and activity_list[0]['user_id'] == user['id']:
        raise IngestionSkip('Not updated since last ingest')

    return dataset, all_resources


def clean_assets(dataset_id, skip_grids=False, display=False):
    dataset = _get_dataset_from_id(dataset_id)

    if display:
        logger.debug("\nCleaning out assets for dataset: {}".format(dataset_id))

    if dataset:
        # Skip cleaning datasets that may have a manually ingested grid
        if 'resources' in dataset and skip_grids and (
                    any(['grid' in x['format'].lower() for x in dataset['resources']]) or any(
                    ['geotif' in x['format'].lower() for x in dataset['resources']])):
            return

        # clear old data table
        table_name = _clear_old_table(dataset)

        # clear rasterised directory
        _clean_dir(_get_geoserver_data_dir(table_name))

        # create geoserver workspace/layers http://boundlessgeo.com
        # /2012/10/adding-layers-to-geoserver-using-the-rest-api/
        # name workspace after dataset
        geo_addr, geo_user, geo_pass, geo_public_addr = _get_geoserver_data()
        workspace = _get_valid_qname(dataset['name'])

        _base_url = geo_addr + 'rest/workspaces'
        _ws_url = _base_url + '/' + workspace

        r = _make_request(
            requests.head,
            _ws_url,
            auth=(geo_user, geo_pass))

        if r and r.ok:
            url = _ws_url + '?recurse=true&quietOnNotFound'
            r = _make_request(
                requests.delete,
                url,
                auth=(geo_user, geo_pass))

        _delete_resources(dataset)

    if display:
        logger.debug("Done cleaning out assets!")


def do_ingesting(dataset_id, force):
    tempdir = None
    try:
        dataset, grouped_resources = check_if_may_skip(dataset_id, force)

        (shp_resources, kml_resources, tab_resources, tiff_resources, grid_resources, sld_resources) = grouped_resources

        logger.info("\nIngesting {}".format(dataset['id']))

        # if geoserver api link does not exist or api
        # link is out of date with data, continue
        tempdir = tempfile.mkdtemp(suffix=dataset['id'], dir=_get_tmp_path())

        # clear old data table
        (using_kml, using_grid,
         table_name,
         workspace, native_crs) = _prepare_everything(
            dataset,
            shp_resources, kml_resources, tab_resources, tiff_resources, grid_resources,
            tempdir)

        # load bounding boxes from database
        bbox = None
        if not using_grid:
            bbox, latlngbbox, bgjson = _get_geojson(
                using_kml, table_name)
            # logger.debug(bbox)

        datastore = workspace
        if using_grid:
            datastore += 'cs'
        else:
            datastore += 'ds'

        _perform_workspace_requests(datastore, workspace, table_name if using_grid else None)

        geo_addr, geo_user, geo_pass, geo_public_addr = _get_geoserver_data()

        # name layer munged from resource id
        layer_name = table_name

        if using_grid:
            layer_data = {
                'coverage': {
                    'name': layer_name,
                    'nativeName': table_name,
                    'title': dataset['title'],
                    'srs': native_crs,
                    'coverageParameters': {
                        'AllowMultithreading': False,
                        'SUGGESTED_TILE_SIZE': '1024,1024',
                        'USE_JAI_IMAGEREAD': False
                    }
                }
            }
            _layer_base_url = geo_addr + 'rest/workspaces/' + workspace + '/coveragestores/' + datastore + "/coverages"
        else:
            layer_data = {
                'featureType': {
                    'name': layer_name,
                    'nativeName': table_name,
                    'title': dataset['title'],
                    'srs': native_crs,
                    'datastore': datastore
                }
            }
            _layer_base_url = geo_addr + 'rest/workspaces/' + workspace + '/datastores/' + datastore + "/featuretypes"

        bbox_obj = _update_package_with_bbox(bbox, latlngbbox, layer_data, dataset, native_crs,
                                             bgjson) if bbox and not using_grid else None

        r = _make_request(
            requests.post,
            _layer_base_url,
            data=json.dumps(layer_data),
            headers={'Content-Type': 'application/json'},
            auth=(geo_user, geo_pass))

        if not r and not r.ok:
            _failure("Failed to create Geoserver layer {}: {}".format(_layer_base_url, r.content))

        sldfiles = glob.glob("*.[sS][lL][dD]")
        if len(sldfiles):
            _apply_sld(
                os.path.splitext(
                    os.path.basename(sldfiles[0]))[0],
                workspace,
                layer_name,
                url=None,
                filepath=sldfiles[0])
        else:
            logger.info("no sld file in package")
        # With layers created, we can apply any SLDs
        if len(sld_resources):
            _apply_sld_resources(sld_resources[0], workspace, layer_name)
        else:
            logger.info("no sld resources")

        # Move on to creating CKAN assets
        ws_addr = geo_public_addr + _get_valid_qname(dataset['name']) + "/"

        # Delete out all geoserver resources before rebuilding (this simplifies update logic)
        dataset = _delete_resources(dataset)

        existing_formats = []
        for resource in dataset['resources']:
            existing_formats.append(resource['format'].lower())

        _create_resources_from_formats(
            ws_addr, layer_name, bbox_obj, existing_formats, dataset, using_grid)

        _success()
    except IngestionSkip as e:
        logger.info('{}: {}'.format(type(e), e))
        pass  # logger.info('{}: {}'.format(type(e), e))
    except IngestionFail as e:
        logger.info('{}: {}'.format(type(e), e))
        clean_assets(dataset_id)
    except Exception as e:
        logger.error("failed to ingest {0} with error {1}".format(dataset_id, e))
        clean_assets(dataset_id, display=True)
    finally:
        if tempdir:
            _clean_dir(tempdir)
