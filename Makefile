###############################################################################
#                             requirements: start                             #
###############################################################################
ckan_tag = ckan-2.11.3
ext_list = security dcat officedocs pdfview zippreview spatial harvest \
	agls xloader flakes googleanalytics charts harvest-basket transmute \
	pygments check-link collection \
	search-tweaks composite-search search-autocomplete \
	drupal-api admin-panel hierarchy mailcraft metaexport

remote-agls = https://github.com/DataShades/ckanext-agls.git tag v0.1.0
remote-charts = https://github.com/DataShades/ckanext-charts.git tag c417d21
remote-dcat = https://github.com/ckan/ckanext-dcat.git tag v2.0.0
remote-flakes = https://github.com/DataShades/ckanext-flakes.git tag v0.4.5
remote-harvest = https://github.com/DataShades/ckanext-harvest.git branch fix-migrations
remote-officedocs = https://github.com/DataShades/ckanext-officedocs.git commit fac01df
remote-pdfview = https://github.com/ckan/ckanext-pdfview.git tag 0.0.8
remote-spatial = https://github.com/ckan/ckanext-spatial.git tag v2.2.0
remote-xloader = https://github.com/ckan/ckanext-xloader.git tag 2.0.0
remote-zippreview = https://github.com/datagovau/ckanext-zippreview commit e48ae35
remote-harvest-basket = https://github.com/DataShades/ckanext-harvest-basket tag v1.5.3
remote-transmute = https://github.com/DataShades/ckanext-transmute branch master
remote-pygments = https://github.com/DataShades/ckanext-pygments commit e947b34
remote-check-link = https://github.com/DataShades/ckanext-check-link tag v0.3.1
remote-collection = https://github.com/DataShades/ckanext-collection tag v0.3.0
remote-search-tweaks = https://github.com/DataShades/ckanext-search-tweaks.git tag v1.0.0
remote-composite-search = https://github.com/DataShades/ckanext-composite-search tag v0.3.3
remote-search-autocomplete = https://github.com/DataShades/ckanext-search-autocomplete tag v0.1.2
remote-drupal-api = https://github.com/DataShades/ckanext-drupal-api.git commit 42db9b7
remote-admin-panel = https://github.com/DataShades/ckanext-admin-panel commit bde95ee
remote-hierarchy = https://github.com/ckan/ckanext-hierarchy tag v1.2.1
remote-mailcraft = https://github.com/DataShades/ckanext-mailcraft.git tag v0.2.2
remote-metaexport = https://github.com/DataShades/ckanext-metaexport.git tag v0.1.1
remote-security = https://github.com/DataShades/ckanext-security branch ckan-2.11
remote-googleanalytics = https://github.com/ckan/ckanext-googleanalytics tag v2.5.1

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


test-config ?= test_config/test.ini
test-server:  ## start server for frontend testing
	yes | ckan -c  $(test-config) db clean
	ckan -c $(test-config) search-index clear
	ckan -c $(test-config) db upgrade
	ckan -c $(test-config) run -t

test-frontend:  ## run e2e tests
	pytest -m playwright
