import click

from .spatialingestor import spatial_ingestor
from . import maintain

def get_commands():
    return [
        spatial_ingestor,
        dga,
    ]

@click.group(short_help="DGA CLI")
def dga():
    pass


dga.add_command(maintain.maintain)
