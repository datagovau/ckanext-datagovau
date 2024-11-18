###############################################################################
#                             requirements: start                             #
###############################################################################
ckan_tag = ckan-2.11.0
ext_list = dcat officedocs pdfview zippreview spatial cesiumpreview harvest agls xloader flakes googleanalytics charts harvest-basket transmute pygments

remote-agls = https://github.com/DataShades/ckanext-agls.git commit e108d41
remote-cesiumpreview = https://github.com/DataShades/ckanext-cesiumpreview.git commit 2e22150
remote-charts = https://github.com/DataShades/ckanext-charts.git tag c417d21
remote-dcat = https://github.com/ckan/ckanext-dcat.git tag v2.0.0
remote-flakes = https://github.com/DataShades/ckanext-flakes.git tag v0.4.5
remote-harvest = https://github.com/ckan/ckanext-harvest.git commit bf849f1
remote-officedocs = https://github.com/DataShades/ckanext-officedocs.git commit fac01df
remote-pdfview = https://github.com/ckan/ckanext-pdfview.git tag 0.0.8
remote-spatial = https://github.com/ckan/ckanext-spatial.git commit 8a00a2b
remote-xloader = https://github.com/ckan/ckanext-xloader.git commit a96ce28
remote-zippreview = https://github.com/datagovau/ckanext-zippreview commit e48ae35
remote-harvest-basket = https://github.com/mutantsan/ckanext-harvest-basket branch master
remote-transmute = https://github.com/mutantsan/ckanext-transmute branch master
remote-pygments = https://github.com/DataShades/ckanext-pygments commit e947b34

###############################################################################
#                              requirements: end                              #
###############################################################################

_version = master

-include deps.mk

prepare:
	curl -O https://raw.githubusercontent.com/DataShades/ckan-deps-installer/$(_version)/deps.mk


test-config ?= test_config/test.ini
test-server:  ## start server for frontend testing
	yes | ckan -c  $(test-config) db clean
	ckan -c $(test-config) search-index clear
	ckan -c $(test-config) db upgrade
	ckan -c $(test-config) run -t

test-frontend:  ## run e2e tests
	pytest -m playwright
