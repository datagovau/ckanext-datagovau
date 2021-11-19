from setuptools import find_packages, setup

version = "1.0.0a"
# Keep in case we still need pylons...Just use the line below in place
# of the install_requires argument in the call to setup().
# install_requires=['requests', 'feedparser', 'pylons', 'python-dateutil'],
setup(
    name="ckanext-datagovau",
    version=version,
    description="Extension for customising CKAN for data.gov.au",
    long_description="",
    classifiers=[],  # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
    keywords="",
    author="Greg von Nessi",
    author_email="greg.vonnessi@linkdigital.com.au",
    url="",
    license="",
    packages=find_packages(exclude=["ez_setup", "examples", "tests"]),
    namespace_packages=["ckanext", "ckanext.datagovau"],
    include_package_data=True,
    zip_safe=False,
    install_requires=[],
    entry_points="""
        [ckan.plugins]
		datagovau = ckanext.datagovau.plugin:DataGovAuPlugin
	""",
)
