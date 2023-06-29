import click

from .geoserveringestor import geoserver_ingestor
from .googleanalytics import stats
from .maintain import maintain
from .spatialingestor import spatial_ingestor

__all__ = [
    "dga",
    "geoserver_ingestor",
    "spatial_ingestor",
]


@click.group(short_help="DGA CLI")
@click.help_option("-h", "--help")
def dga():
    pass


dga.add_command(maintain)
dga.add_command(stats)
