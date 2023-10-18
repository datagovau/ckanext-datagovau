###############################################################################
#                             requirements: start                             #
###############################################################################
ckan_tag = ckan-2.10.1
ext_list = dcat officedocs pdfview zippreview spatial cesiumpreview harvest agls xloader flakes googleanalytics charts


remote-xloader = https://github.com/ckan/ckanext-xloader.git commit c062f54
remote-harvest = https://github.com/ckan/ckanext-harvest.git tag v1.5.3
remote-dcat = https://github.com/ckan/ckanext-dcat.git tag v1.4.0
remote-officedocs = https://github.com/DataShades/ckanext-officedocs.git commit fac01df
remote-pdfview = https://github.com/ckan/ckanext-pdfview.git tag v0.0.8
remote-zippreview = https://github.com/datagovau/ckanext-zippreview commit e48ae35
remote-spatial = https://github.com/ckan/ckanext-spatial.git tag v2.0.0
remote-cesiumpreview = https://github.com/DataShades/ckanext-cesiumpreview.git commit 2e22150
remote-agls = https://github.com/DataShades/ckanext-agls.git commit 880c133
remote-flakes = https://github.com/DataShades/ckanext-flakes.git tag v0.3.8
remote-charts = https://github.com/DataShades/ckanext-charts.git tag 2b9107c

# removed
#remote-odata = https://github.com/DataShades/ckanext-odata.git branch py3
#remote-sentry = https://github.com/okfn/ckanext-sentry.git branch master
#remote-ga-report = https://github.com/DataShades/ckanext-ga-report.git branch py3
#remote-dga-stats = https://github.com/DataShades/ckanext-dsa-stats.git branch py3
#remote-metaexport = https://github.com/DataShades/ckanext-metaexport.git branch py3


###############################################################################
#                              requirements: end                              #
###############################################################################

_version = master

-include deps.mk

prepare:
	curl -O https://raw.githubusercontent.com/DataShades/ckan-deps-installer/$(_version)/deps.mk
