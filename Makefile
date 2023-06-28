###############################################################################
#                             requirements: start                             #
###############################################################################
ckan_tag = ckan-2.9.7
ext_list = dcat officedocs pdfview zippreview spatial cesiumpreview harvest agls xloader flakes googleanalytics charts


remote-xloader = https://github.com/ckan/ckanext-xloader.git branch master
remote-harvest = https://github.com/ckan/ckanext-harvest.git branch master
remote-dcat = https://github.com/ckan/ckanext-dcat.git branch master
remote-officedocs = https://github.com/DataShades/ckanext-officedocs.git branch py3
remote-pdfview = https://github.com/ckan/ckanext-pdfview.git branch master
remote-zippreview = https://github.com/datagovau/ckanext-zippreview branch Develop
remote-spatial = https://github.com/ckan/ckanext-spatial.git tag v1.1.0
remote-cesiumpreview = https://github.com/DataShades/ckanext-cesiumpreview.git branch py3
remote-agls = https://github.com/DataShades/ckanext-agls.git branch py3
remote-flakes = https://github.com/DataShades/ckanext-flakes.git branch master
remote-googleanalytics = https://github.com/ckan/ckanext-googleanalytics.git master
remote-charts = https://github.com/DataShades/ckanext-charts.git master

# removed
remote-odata = https://github.com/DataShades/ckanext-odata.git branch py3
remote-sentry = https://github.com/okfn/ckanext-sentry.git branch master
remote-ga-report = https://github.com/DataShades/ckanext-ga-report.git branch py3
remote-dga-stats = https://github.com/DataShades/ckanext-dsa-stats.git branch py3
remote-metaexport = https://github.com/DataShades/ckanext-metaexport.git branch py3


###############################################################################
#                              requirements: end                              #
###############################################################################

_version = master

-include deps.mk

prepare:
	curl -O https://raw.githubusercontent.com/DataShades/ckan-deps-installer/$(_version)/deps.mk
