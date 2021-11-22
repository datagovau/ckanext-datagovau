# encoding: utf-8
import click
import logging

# Imports from legacy datagovau commands.py
import glob
import os
import re
import shutil
import sys

import psycopg2
from ckan import model

from ckantoolkit import config


log = logging.getLogger('ckanext_datagovau')

# Keep for now--will check before switching to this.
#log = logging.getLogger(__name__)

# Commands this module implements.  For now,
# only spatial_ingestor; purgelegacyspatial is not
# referenced anywhere in the datagovau code base, so
# ignore for now.  Template for including it if required
# is commented out at the end of this module.
def get_commands():
    return [spatial_ingestor]

# datagovau spatial-ingestor command group.
@click.group(u"spatial-ingestor", short_help=u"Ingest spatial data")
def spatial_ingestor():
    pass

# spatial-ingestor ingest subcommand.
@spatial_ingestor.command('ingest')
@click.argument('scope')
def perform_ingest(scope):
    """
    Performs ingest of spatial data for scope of data.

    Usage::
        ckan spatial-ingestor <scope>

        where scope is one of: 'all', 'updated', 'updated-orgs', or <dataset-id>.
    """
    from ckanext.datagovau.spatialingestor import do_ingesting
    if scope in ('all', 'updated', 'updated-orgs'):
        force = True if scope == 'all' else False
        if scope == 'updated-orgs':
            pkg_ids = [ r[0] for r in model.Session.query(model.Package.id).filter_by(state='active').filter(
                model.Package.owner_org.in_(['3965c5cd-d88f-4735-92db-af28d3ad9155', #nntt
                                            'a56f8067-b250-4c32-9609-f2191dc88a3a' #geelong
                                            ])).all()]
        else:
            pkg_ids = [ r[0] for r in model.Session.query(model.Package.id).filter_by(state='active').all()]

            total = len(pkg_ids)

            sys.stdout.write(" Found {0} Package IDs".format(total))
            sys.stdout.write("\nIngesting Package ID 0/0")

        for counter, pkg_id in enumerate(pkg_ids):
            sys.stdout.write(
                "\rIngesting Package ID {0}/{1} ({2})\r".format(counter + 1, total, pkg_id))
            sys.stdout.flush()
            # log.info("Ingesting %s" % dataset.id)
            do_ingesting(pkg_id, force)
    else:
        log.info("Ingesting %s" % scope)
        do_ingesting(scope, True)

# datagovau spatial-ingestor purge subcommand.
@spatial_ingestor.command('purge')
@click.argument('scope')
def perform_purge(scope):
    """
    Performs purge of nominated scope.

    Usage:
        ckan spatial-ingestor purge <scope>

        where scope is one of: 'all' or 'erroneous'.
    """
    from ckanext.datagovau.spatialingestor import check_if_may_skip, clean_assets
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

# datagovau spatial-ingestor dropuser subcommand.
@spatial_ingestor.command('dropuser')
@click.argument('username')
def perform_drop_user(username):
    """
    Deletes nominated user.

    Usage:
        ckan spatial-ingestor dropuser <username>
    """
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
    pkgs = model.Session.query(model.Package).filter_by(creator_user_id=user.id)
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

# Command currently not referenced in any of the DGA
# batch scripts.  Skeleton included in case it is required
# in the future.  This command appears to be something
# of a junkbucked/kludgy solution to a problem that will
# likely need not to be addressed---source code for it is
# in the old commands.py source.
#@click.group('purgelegacyspatial', short_help=u"Cleans out what old spatial ingestor did.")
#def purgelegacyspatial():
#    pass
#
#@purgelegacyspatial.command()
#@click.argument()
#def perform_stuff():
#    """
#    Placeholder for now.
#    """
#    pass
