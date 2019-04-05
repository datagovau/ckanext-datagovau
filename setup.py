from setuptools import setup, find_packages

version = '0.1'

setup(
	name='ckanext-datagovau',
	version=version,
	description='Extension for customising CKAN for data.gov.au',
	long_description='',
	classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
	keywords='',
	author='Greg von Nessi',
	author_email='greg.vonnessi@linkdigital.com.au',
	url='',
	license='',
	packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
	namespace_packages=['ckanext', 'ckanext.datagovau'],
	include_package_data=True,
	zip_safe=False,
	install_requires=['requests', 'feedparser', 'pylons', 'python-dateutil'],
	entry_points=\
	"""
        [ckan.plugins]
		datagovau = ckanext.datagovau.plugin:DataGovAuPlugin
		datagovau_hierarchy = ckanext.datagovau.plugin:HierarchyForm

		[paste.paster_command]
		cleanupdatastoregeoserver = ckanext.datagovau.commands:ReconcileGeoserverAndDatastore
        spatial-ingestor = ckanext.datagovau.commands:SpatialIngestor
	""",
)
