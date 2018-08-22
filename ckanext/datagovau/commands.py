import glob
import logging
import os
import re
import shutil
import sys

import paste.script
import psycopg2
from ckan import model
from ckan.lib.cli import CkanCommand

from ckanext.datagovau.spatialingestor import do_ingesting, check_if_may_skip, clean_assets, _get_geoserver_data_dir

log = logging.getLogger('ckanext_datagovau')


# No other CKAN imports allowed until _load_config is run,
# or logging is disabled


def get_db_cursor(data):
    db_port = None
    if data.get('db_port', '') != '':
        db_port = data['db_port']

    try:
        connection = psycopg2.connect(
            dbname=data['db_name'],
            user=data['db_user'],
            password=data['db_pass'],
            host=data['db_host'],
            port=db_port)
        connection.set_isolation_level(
            psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        return connection.cursor(), connection
    except Exception, e:
        log.error("Unable to get DB connection")


class SpatialIngestor(CkanCommand):
    """Spatial ingestor management commands.

    Usage::
        paster spatial-ingestor ingest {all,updated,ID}
    """

    summary = __doc__.split('\n')[0]
    usage = __doc__

    parser = paste.script.command.Command.standard_parser(verbose=True)
    parser.add_option(
        '-c',
        '--config',
        dest='config',
        default='development.ini',
        help='Config file to use.')

    def command(self):
        self._load_config()

        if len(self.args) < 2:
            print self.usage
        elif self.args[0] == 'ingest':
            self._ingest(self.args[1])
        elif self.args[0] == 'purge':
            self._purge(self.args[1])
        elif self.args[0] == 'dropuser':
            self._drop_user(self.args[1])

    def _ingest(self, scope):
        if scope in ('all', 'updated'):
            force = True if scope == 'all' else False
            pkg_ids = [
                r[0]
                for r in model.Session.query(
                    model.Package.id).filter_by(state='active').all()
            ]

            total = len(pkg_ids)

            sys.stdout.write(" Found {0} Package IDs".format(total))
            sys.stdout.write("\nIngesting Package ID 0/0")

            for counter, pkg_id in enumerate(pkg_ids):
                sys.stdout.write(
                    "\rIngesting Package ID {0}/{1}".format(counter + 1, total))
                sys.stdout.flush()
                # log.info("Ingesting %s" % dataset.id)
                do_ingesting(pkg_id, force)
        else:
            log.info("Ingesting %s" % scope)
            do_ingesting(scope, True)

    def _purge(self, scope):
        if scope in ['all', 'erroneous']:
            pkg_ids = [
                r[0]
                for r in model.Session.query(model.Package.id).all()
            ]

            total = len(pkg_ids)

            sys.stdout.write(" Found {0} Package IDs".format(total))
            sys.stdout.write("\nPurging Package ID 0/0")

            for counter, pkg_id in enumerate(pkg_ids):
                sys.stdout.write(
                    "\rPurging Package ID {0}/{1}".format(counter + 1, total))
                sys.stdout.flush()
                if scope == 'erroneous':
                    try:
                        check_if_may_skip(pkg_id, True)
                    except:
                        clean_assets(pkg_id)
                else:
                    clean_assets(pkg_id, skip_grids=True)
        else:
            # log.info("Ingesting %s" % scope)
            clean_assets(scope, display=True)

    def _drop_user(self, username):
        user = model.User.get(username)
        if user is None:
            print('User <%s> not found' % username)
            return
        groups = user.get_groups()
        if groups:
            print('User is a member of groups/organizations: %s' % ', '.join(
                [g.title or g.name for g in groups]
            ))
            return
        pkgs = model.Session.query(model.Package).filter_by(
            creator_user_id=user.id)
        if pkgs.count():
            print('There are some(%d) datasets created by this user: %s'
                  % (pkgs.count(), [pkg.name for pkg in pkgs]))
            return
        activities = model.Session.query(model.Activity).filter_by(
            user_id=user.id
        ).filter(model.Activity.activity_type.contains('package'))
        if activities.count():
            print('There are some(%d) activity records that mentions user'
                  % activities.count())
            return
        model.Session.delete(user)
        model.Session.commit()
        print('Done')


class ReconcileGeoserverAndDatastore(CkanCommand):
    """Cleans out old what old spatial ingestor did

    Usage (all packages): paster purgelegacyspatial

    """
    summary = __doc__.split('\n')[0]
    usage = __doc__
    max_args = 1
    min_args = 0

    def command(self):
        self._load_config()

        from datetime import datetime
        from pylons import config
        import requests

        from ckan import model
        from ckan.lib import cli, search
        from ckan.plugins import toolkit

        geoserver_info = cli.parse_db_config('ckanext.datagovau.spatialingestor.geoserver.url')
        postgis_info = cli.parse_db_config('ckanext.datagovau.spatialingestor.postgis.url')
        datastore_info = cli.parse_db_config('ckanext.datagovau.datastore.url')

        active_datastore_tablenames = set()
        active_vector_workspaces = set()
        active_raster_workspaces = set()

        datastore_postgis_same = config.get(
            'ckanext.datagovau.datastore.url') == config.get(
            'ckanext.datagovau.spatialingestor.postgis.url')

        dry_run = (len(self.args) == 1 and self.args[0].lower() == "dry-run")
        clean_all = (len(self.args) == 1
                     and self.args[0].lower() == "clean-all")
        clean_dbs = clean_all or (len(self.args) == 1 and self.args[0].lower() == "clean-dbs-only")
        clean_fs = clean_all or (len(self.args) == 1 and self.args[0].lower() == "clean-fs-only")
        clean_geoserver = clean_all or (len(self.args) == 1 and self.args[0].lower() == "clean-geoserver-only")
        clean_ckan_resources = clean_all or ( len(self.args) == 1 and self.args[0].lower() == "clean-ckan-only")

        sys.stdout.write("\n----------")
        if all([
            not x
            for x in [
                dry_run, clean_all, clean_dbs, clean_geoserver,
                clean_ckan_resources
            ]
        ]):
            sys.stdout.write("\nUsage:")
            sys.stdout.write("\n         paster --plugin=ckanext-datagovau "
                             "cleanupdatastoregeoserver <command>"
                             " --config=/path/to/config.ini")
            sys.stdout.write("\nCommands:")
            sys.stdout.write("\n         help: This message")
            sys.stdout.write(
                "\n         dry-run: Run script to generate a command "
                "line report with no actions taken")
            sys.stdout.write(
                "\n         clean-all: Run script to clean out "
                "unused Geoserver workspaces, DB tables and CKAN Resources")
            sys.stdout.write("\n         clean-dbs-only: Run script "
                             "to clean out only unused DB tables")
            sys.stdout.write("\n         clean-geoserver-only: Run script to "
                             "clean out only unused Geoserver workspaces")
            sys.stdout.write(
                "\n         clean-ckan-only: Run script to clean out "
                "only unused CKAN resources")
            sys.stdout.write(
                "\nNote: Supply no command or anything other than the "
                "above will have the system default to 'help'\n")
            sys.exit(0)

        if clean_all:
            sys.stdout.write(
                "\nRunning in 'clean-all' Mode - Will Delete DB Tables,"
                " Geoserver Workspaces and CKAN Resources")
        elif clean_dbs:
            sys.stdout.write(
                "\nRunning in 'clean-dbs-only' Mode - Will Delete "
                "DB Tables Only")
        elif clean_geoserver:
            sys.stdout.write("\nRunning in 'clean-geoserver-only' Mode - Will "
                             "Delete Geoserver Workspaces Only")
        elif clean_ckan_resources:
            sys.stdout.write("\nRunning in 'clean-ckan-only' Mode - Will "
                             "Delete CKAN Resources Only")
        else:
            sys.stdout.write("\nRunning in 'dry-run' Mode - Will Generate "
                             "A Report Only; No Assets Will Be Deleted")

        # Get datastore tables
        sys.stdout.write("\n----------")
        sys.stdout.write("\nFetching All Datastore Table Names...")
        cursor, connection = get_db_cursor(datastore_info)
        cursor.execute("""select
            c.relname
            from
            pg_class c join pg_roles r on r.oid = c.relowner
            where
            r.rolname = '{0}' and c.relkind = 'r'
            order by
            c.relname""".format(datastore_info['db_user']))
        datastore_tables = [r[0] for r in cursor.fetchall()]
        connection.commit()
        connection.close()
        for sp_tab in ['spatial_ref_sys']:
            if sp_tab in datastore_tables:
                datastore_tables.remove(sp_tab)
        sys.stdout.write(" Found {0} Tables".format(len(datastore_tables)))

        # Get postGIS tables
        if datastore_postgis_same:
            postgis_tables = datastore_tables
        else:
            sys.stdout.write("\n----------")
            sys.stdout.write("\nFetching All Geoserver PostGIS Table Names...")
            cursor, connection = get_db_cursor(postgis_info)
            cursor.execute("""select
                c.relname
                from
                pg_class c join pg_roles r on r.oid = c.relowner
                where
                r.rolname = '{0}' and c.relkind = 'r'
                order by
                c.relname""".format(postgis_info['db_user']))
            postgis_tables = [r[0] for r in cursor.fetchall()]
            connection.commit()
            connection.close()
            for sp_tab in ['spatial_ref_sys']:
                if sp_tab in postgis_tables:
                    postgis_tables.remove(sp_tab)
            sys.stdout.write(" Found {0} Tables".format(len(postgis_tables)))

        # Get filestore directories
        os.chdir(_get_geoserver_data_dir())
        filestore_directories = glob.glob('ckan_*')

        # Get geoserver workspaces
        geoserver_url = 'http://' + geoserver_info['db_host']
        if geoserver_info.get('db_port', '') != '':
            geoserver_url += ':' + geoserver_info['db_port']
        geoserver_url += '/' + geoserver_info['db_name'] + '/'
        sys.stdout.write("\n----------")
        sys.stdout.write(
            "\nFetching All Geoserver Workspace Names From {0}...".format(
                geoserver_url))
        geoserver_credentials = (geoserver_info['db_user'],
                                 geoserver_info['db_pass'])
        geoserver_headers = {'Accept': 'application/json'}
        res = requests.get(
            geoserver_url + 'rest/workspaces',
            headers=geoserver_headers,
            auth=geoserver_credentials)
        geoserver_workspaces = [
            r['name'] for r in res.json()['workspaces']['workspace']
        ]
        sys.stdout.write(
            " Found {0} Workspaces".format(len(geoserver_workspaces)))

        # Test workspace structures in geoserver
        active_geoserver_featuretypes = set()
        active_geoserver_coverages = set()
        total = len(geoserver_workspaces)
        sys.stdout.write("\n----------")
        sys.stdout.write("\nTesting Geoserver Workspace Structures 0/0")
        vector_workspaces = set()
        raster_workspaces = set()
        fts_without_table = set()
        cvgs_without_directory = set()
        ws_without_table = set()
        ws_without_directory = set()
        for counter, ws in enumerate(geoserver_workspaces):
            try:
                sys.stdout.write(
                    "\rTesting Geoserver Workspace Structures {0}/{1}".format(
                        counter + 1, total))
                sys.stdout.flush()

                # Datastore analysis
                res = requests.get(
                    geoserver_url + 'rest/workspaces/' + ws + '/datastores',
                    headers=geoserver_headers,
                    auth=geoserver_credentials)
                datastores = [
                    r['name'] for r in res.json()['dataStores']['dataStore']
                ]
                have_table = True
                for ds in datastores:
                    res = requests.get(
                        geoserver_url + 'rest/workspaces/' + ws +
                        '/datastores/' + ds + '/featuretypes',
                        headers=geoserver_headers,
                        auth=geoserver_credentials)

                    for ft in [
                        r['name']
                        for r in res.json()['featureTypes']['featureType']
                    ]:
                        if ft in postgis_tables:
                            active_geoserver_featuretypes.add(ft)
                        else:
                            have_table = False
                            fts_without_table.add(ft)
                if not have_table:
                    ws_without_table.add(ws)

                vector_workspaces.add(ws)
            except:
                pass

            try:
                # Coveragestore analysis
                res = requests.get(
                    geoserver_url + 'rest/workspaces/' + ws + '/coveragestores',
                    headers=geoserver_headers,
                    auth=geoserver_credentials)
                coveragestores = [
                    r['name'] for r in res.json()['coverageStores']['coverageStore']
                ]
                have_directory = True
                for cs in coveragestores:
                    res = requests.get(
                        geoserver_url + 'rest/workspaces/' + ws +
                        '/coveragestores/' + cs + '/coverages',
                        headers=geoserver_headers,
                        auth=geoserver_credentials)

                    for cvg in [r['name'] for r in res.json()['coverages']['coverage'] ]:
                        if cvg in filestore_directories:
                            active_geoserver_coverages.add(cvg)
                        else:
                            have_directory = False
                            cvgs_without_directory.add(cvg)
                if not have_directory:
                    ws_without_directory.add(ws)

                raster_workspaces.add(ws)
            except:
                pass

        ft_without_table_counter = len(fts_without_table)
        cvg_without_directory_counter = len(cvgs_without_directory)
        ws_without_table_counter = len(ws_without_table)
        ws_without_directory_counter = len(ws_without_directory)
        vector_counter = len(vector_workspaces)
        raster_counter = len(raster_workspaces)

        sys.stdout.write(
            "\nGeoserver Vector Workspaces: {0}".format(vector_counter))
        sys.stdout.write(
            "\nGeoserver Vector Workspaces Without PostGIS Tables: {0}".format(ws_without_table_counter))
        sys.stdout.write(
            "\nGeoserver Feature Types Without PostGIS Tables: {0}".format(ft_without_table_counter))

        sys.stdout.write(
            "\nGeoserver Raster Workspaces: {0}".format(raster_counter))
        sys.stdout.write(
            "\nGeoserver Raster Workspaces Without Filestore Directories: {0}".format(ws_without_directory_counter))
        sys.stdout.write(
            "\nGeoserver Coverages Without Filestore Directories: {0}".format(cvg_without_directory_counter))

        sys.stdout.write("\n----------")
        sys.stdout.write("\nFetching All Active Package IDs...")
        pkg_ids = [
            r[0]
            for r in model.Session.query(
                model.Package.id).filter_by(state='active').all()
        ]

        total = len(pkg_ids)
        sys.stdout.write(" Found {0} Package IDs".format(total))
        sys.stdout.write("\nProcessing Package ID 0/0")
        resources_to_delete = set()
        for counter, pkg_id in enumerate(pkg_ids):
            sys.stdout.write(
                "\rProcessing Package ID {0}/{1}".format(counter + 1, total))
            sys.stdout.flush()
            pkg_dict = model.Package.get(pkg_id).as_dict()
            for res_dict in pkg_dict.get('resources', []):
                res_delete = False
                ws_name = None
                re_res = None
                if 'data.gov.au/geoserver' in res_dict.get('url', ''):
                    re_res = re.search('.*data\.gov\.au\/geoserver\/(.*)\/.*',
                                       res_dict['url'])
                elif 'links.com.au/geoserver' in res_dict.get('url', ''):
                    re_res = re.search('.*links\.com\.au\/geoserver\/(.*)\/.*',
                                       res_dict['url'])

                if re_res:
                    ws_name = re_res.group(1)
                    if all([ws_name in x for x in [ws_without_table, ws_without_directory]]) or not (ws_name in geoserver_workspaces):
                        resources_to_delete.add(res_dict['id'])
                        res_delete = True
                    else:
                        if ws_name in raster_workspaces:
                            active_raster_workspaces.add(ws_name)
                        if ws_name in vector_workspaces:
                            active_vector_workspaces.add(ws_name)

                if not res_delete:
                    new_label = ''
                    if toolkit.asbool(
                            res_dict.get('datastore_active', 'False')):
                        if res_dict['id'] in datastore_tables:
                            active_datastore_tablenames.add(res_dict['id'])
                        else:
                            new_label = 'False'
                    elif res_dict['id'] in datastore_tables:
                        new_label = 'True'

                    if new_label != '':
                        new_label_bool = toolkit.asbool(new_label)
                        sys.stdout.write(
                            "\nCorrecting 'datastore_active' Value For {0}".
                                format(res_dict['id']))
                        try:
                            res_dict['datastore_active'] = new_label_bool
                            if clean_ckan_resources:
                                toolkit.get_action('resource_update')({
                                    'ignore_auth':
                                        True
                                }, res_dict)
                            active_datastore_tablenames.add(res_dict['id'])
                        except:
                            if new_label_bool:
                                sys.stdout.write(
                                    "\nResource {0} Failed Validation; Will Drop Associated Datastore Table".format(res_dict['id']))
                            else:
                                sys.stdout.write(
                                    "\nResource {0} Failed Validation; Marking Resource For Deletion".format(res_dict['id']))
                                resources_to_delete.add(res_dict['id'])
                                if ws_name:
                                    if ws_name in active_raster_workspaces:
                                        active_raster_workspaces.remove(ws_name)
                                    if ws_name in active_vector_workspaces:
                                        active_vector_workspaces.remove(
                                            ws_name)
                        sys.stdout.write("\nProcessing Package ID {0}/{1}".format(counter + 1, total))

        ds_counter = len(active_datastore_tablenames)
        delete_counter = len(resources_to_delete)
        active_raster_counter = len(active_raster_workspaces)
        active_vector_counter = len(active_vector_workspaces)

        sys.stdout.write(
            "\nActive Datastore Resources: {0}".format(ds_counter))
        sys.stdout.write(
            "\nActive Geoserver Resources: {0}.".format(len(active_raster_workspaces & active_vector_workspaces)))
        sys.stdout.write(
            "\nActive Geoserver Raster Resources: {0}".format(active_raster_counter))
        sys.stdout.write(
            "\nActive Geoserver Vector Resources: {0}".format(active_vector_counter))
        sys.stdout.write(
            "\nActive Geoserver Resources With Broken Workspaces: {0}".format(delete_counter))

        # Extract feature types for active geoserver workspaces
        active_geoserver_featuretypes = set()
        total = len(active_vector_workspaces)
        sys.stdout.write("\n----------")
        sys.stdout.write(
            "\nExtracting PostGIS Table Name From Geoserver Workspace 0/0")
        for counter, ws in enumerate(active_vector_workspaces):
            sys.stdout.write(
                "\rExtracting PostGIS Table Name From Geoserver Workspace {0}/{1}".
                    format(counter + 1, total))
            sys.stdout.flush()
            res = requests.get(
                geoserver_url + 'rest/workspaces/' + ws + '/datastores',
                headers=geoserver_headers,
                auth=geoserver_credentials)
            datastores = [
                r['name'] for r in res.json()['dataStores']['dataStore']
            ]
            for ds in datastores:
                res = requests.get(
                    geoserver_url + 'rest/workspaces/' + ws + '/datastores/' +
                    ds + '/featuretypes',
                    headers=geoserver_headers,
                    auth=geoserver_credentials)
                for ft in [
                    r['name']
                    for r in res.json()['featureTypes']['featureType']
                ]:
                    active_geoserver_featuretypes.add(ft)

        postgis_tables_to_drop = []
        sys.stdout.write("\n----------")
        if datastore_postgis_same:
            sys.stdout.write(
                "\nFinding Active Geoserver Feature Types Without A PostGIS Table..."
            )
            geoserver_featuretypes_without_table = active_geoserver_featuretypes - set(
                datastore_tables)
            sys.stdout.write(" Found {0} Feature Types".format(
                len(geoserver_featuretypes_without_table)))

            sys.stdout.write("\nDetermining Which Datastore Tables To Drop...")
            valid_table_names = set(
                active_datastore_tablenames) | active_geoserver_featuretypes
            datastore_tables_to_drop = list(
                set(datastore_tables) - valid_table_names)
            sys.stdout.write(" Will Drop {0} Out Of {1} Tables".format(
                len(datastore_tables_to_drop), len(datastore_tables)))
        else:
            sys.stdout.write(
                "\nFinding Active Geoserver Feature Types Without A PostGIS Table..."
            )
            geoserver_featuretypes_without_table = active_geoserver_featuretypes - set(
                postgis_tables)
            sys.stdout.write(" Found {0} Feature Types".format(
                len(geoserver_featuretypes_without_table)))

            sys.stdout.write("\nDetermining Which PostGIS Tables To Drop...")
            valid_table_names = active_geoserver_featuretypes
            postgis_tables_to_drop = list(
                set(postgis_tables) - valid_table_names)
            sys.stdout.write(" Will Drop {0} Out Of {1} Tables".format(
                len(postgis_tables_to_drop), len(postgis_tables)))

            sys.stdout.write("\nDetermining Which Datastore Tables To Drop...")
            valid_table_names = set(active_datastore_tablenames)
            datastore_tables_to_drop = list(
                set(datastore_tables) - valid_table_names)
            sys.stdout.write(" Will Drop {0} Out Of {1} Tables".format(
                len(datastore_tables_to_drop), len(datastore_tables)))

        # Extract coverages for active geoserver workspaces
        active_geoserver_coverages = set()
        total = len(active_raster_workspaces)
        sys.stdout.write("\n----------")
        sys.stdout.write(
            "\nExtracting Filestore Directory Name From Geoserver Workspace 0/0")
        for counter, ws in enumerate(active_raster_workspaces):
            sys.stdout.write(
                "\rExtracting Filestore Directory Name From Geoserver Workspace {0}/{1}".format(counter + 1, total))
            sys.stdout.flush()
            res = requests.get(
                geoserver_url + 'rest/workspaces/' + ws + '/coveragestores',
                headers=geoserver_headers,
                auth=geoserver_credentials)
            coveragestores = [
                r['name'] for r in res.json()['coverageStores']['coverageStore']
            ]
            for cs in coveragestores:
                res = requests.get(
                    geoserver_url + 'rest/workspaces/' + ws + '/coveragestores/' + cs + '/coverages',
                    headers=geoserver_headers,
                    auth=geoserver_credentials)
                for ft in [r['name'] for r in res.json()['coverages']['coverage']]:
                    active_geoserver_coverages.add(ft)

        sys.stdout.write(
            "\nFinding Active Geoserver Coverages Without A Filestore Directory..."
        )
        geoserver_coverages_without_directory = active_geoserver_coverages - set(filestore_directories)
        sys.stdout.write(" Found {0} Coverages".format(len(geoserver_coverages_without_directory)))

        sys.stdout.write("\nDetermining Which Filestore Directories To Delete...")
        valid_directory_names = active_geoserver_coverages
        filestore_directories_to_delete = list(set(filestore_directories) - valid_directory_names)
        sys.stdout.write(
            " Will Delete {0} Out Of {1} Directories".format(
                len(filestore_directories_to_delete), len(filestore_directories)))

        sys.stdout.write(
            "\nDetermining Which Geoserver Workspaces To Delete...")
        valid_workspaces = active_vector_workspaces | active_raster_workspaces
        workspaces_to_delete = list(
            set(geoserver_workspaces) - valid_workspaces)
        sys.stdout.write(" Will Delete {0} Out Of {1} Workspaces".format(
            len(workspaces_to_delete), len(geoserver_workspaces)))

        sys.stdout.write("\n----------")
        sys.stdout.write(
            "\nTables To Be Dropped From Datastore DB ({0} Out Of {1}):".
                format(len(datastore_tables_to_drop), len(datastore_tables)))
        cursor, connection = get_db_cursor(datastore_info)
        for table_name in datastore_tables_to_drop:
            sys.stdout.write("\nDropping Table {0}".format(table_name))
            if clean_dbs:
                cursor.execute(
                    """DROP TABLE "{0}" CASCADE""".format(table_name))
        connection.commit()
        connection.close()

        if not datastore_postgis_same:
            sys.stdout.write("\n----------")
            sys.stdout.write(
                "\nTables To Be Dropped From PostGIS DB ({0} Out Of {1}):".
                    format(len(postgis_tables_to_drop), len(postgis_tables)))
            cursor, connection = get_db_cursor(postgis_info)
            for table_name in postgis_tables_to_drop:
                sys.stdout.write("\nDropping Table {0}".format(table_name))
                if clean_dbs:
                    cursor.execute(
                        """DROP TABLE "{0}" CASCADE""".format(table_name))
            connection.commit()
            connection.close()

        sys.stdout.write("\n----------")
        sys.stdout.write(
            "\nDirectories To Be Deleted From Filestore ({0} Out Of {1}):".format(
                len(filestore_directories_to_delete), len(filestore_directories)))
        for directory_name in filestore_directories_to_delete:
            sys.stdout.write("\nDeleting Directory {0}".format(directory_name))
            if clean_fs:
                shutil.rmtree(_get_geoserver_data_dir(directory_name))

        sys.stdout.write("\n----------")
        sys.stdout.write(
            "\nGeoserver Workspaces To Be Deleted ({0} Out Of {1}):".format(
                len(workspaces_to_delete), len(geoserver_workspaces)))
        for ws_name in workspaces_to_delete:
            sys.stdout.write(
                "\nRecursively Deleting Workspace {0}".format(ws_name))
            if clean_geoserver:
                requests.delete(
                    geoserver_url + '/rest/workspaces/' + str(ws_name) +
                    '?recurse=true&quietOnNotFound',
                    auth=geoserver_credentials)

        sys.stdout.write("\n----------")
        sys.stdout.write("\nResources To Be Deleted From CKAN ({0}):".format(
            len(resources_to_delete)))
        for res_id in resources_to_delete:
            sys.stdout.write("\nDeleting Resource {0}".format(res_id))
            if clean_ckan_resources:
                try:
                    toolkit.get_action('resource_delete')({
                        'ignore_auth': True
                    }, {
                        'id': res_id
                    })
                except:
                    # Resource or package is failing a validation check,
                    # force the delete
                    del_dict = dict(
                        state='deleted', last_modified=datetime.now())
                    res_dict = model.Resource.get(res_id).as_dict()
                    model.Session.query(model.Resource).filter_by(
                        id=res_id).update(del_dict)
                    if 'package_id' in res_dict:
                        search.rebuild(res_dict['package_id'])

        sys.stdout.write("\n----------")
        sys.stdout.write("\nProcessing Complete!\n")
