/* Module for handling the spatial querying
 */
ckan.module("dga-spatial-query", function ($, _) {
    L.Control.Zoom.prototype.options.position = "bottomright";
    L.drawLocal.draw.toolbar.buttons.rectangle = "";

    function _startDrawingRect(map) {
        $(map.getContainer()).find(".leaflet-draw-draw-rectangle")[0].click();
    }

    var base_style = {
        weight: 2,
        opacity: 1,
        fillColor: "#FFFFFF",
        fillOpacity: 0.5,
        clickable: false,
    };

    // Reset map view
    function resetMap(map) {
        L.Util.requestAnimFrame(map.invalidateSize, map, !1, map._container);
    }

    const ExpandButton = L.Control.extend({
        onAdd: function (map) {
            const bar = L.DomUtil.create("div", "leaflet-bar");
            const btn = L.DomUtil.create("a", "leaflet-dga-expand", bar);
            btn.setAttribute("href", "#");
            btn.setAttribute("aria-label", "Expand map");
            L.DomEvent.on(btn, "mousedown keydown", this._handleClick, this);

            return bar;
        },

        onRemove: function (map) {
            // Nothing to do here
        },

        _handleClick(event) {
            if (event.type === "keydown" && event.code !== "Enter") {
                return;
            }

            this._container
                .closest(".dataset-map")
                .classList.toggle("dga-expanded-map");
            event.stopPropagation();
            event.preventDefault();
            resetMap(this._map);
        },
    });

    var patch = {
        options: {
            mapContainerId: "dataset-map-container",
            zoomControl: true,
            i18n: {},
            style: $.extend({ color: "#92C3CB" }, base_style),
            green_style: $.extend({ color: "#92C3CB" }, base_style),
            default_extent: [
                [-29, 140.5],
                [-36, 152],
            ],
        },
        _onReady: function () {
            var module = this;
            var map;
            var extentLayer;
            var is_expanded = false;
            var should_zoom = true;
            var previous_extent = null;
            var featureGroup = new L.FeatureGroup();
            var form = $("#dataset-search-form");
            var client = this.sandbox.client;

            // in this order coordinates are specified in BBox. Keep it
            // unchanged because `fillForm` takes segments from BBox by position
            // and assing thems into corresponding field.
            var aFields = ["west-lng", "south-lat", "east-lng", "north-lat"];
            var aForm = [];
            for (var f in aFields) {
                aForm.push($("#" + aFields[f]));
            }

            var jqaForm = $(); // empty jQuery object
            $.each(aForm, function (i, o) {
                jqaForm = jqaForm.add(o);
            });

            // Add necessary fields to the search form if not already created
            $(["ext_bbox", "ext_bbox_lga"]).each(function (index, item) {
                if ($("#" + item).length === 0) {
                    $('<input type="hidden" />')
                        .attr({ id: item, name: item })
                        .appendTo(form);
                }
            });

            // OK map time
            this.options.map_config.attribution = "";

            map = ckan.commonLeafletMap(
                module.options.mapContainerId,
                this.options.map_config,
                {
                    attributionControl: false,
                    drawControlTooltips: false,
                    zoomControl: module.options.zoomControl,
                },
            );
            map._layersMaxZoom = 18;
            map._layersMinZoom = 1;

            map.on("load", function (e) {
                var container = $(e.target.getContainer());
                container
                    .find(".leaflet-draw-draw-rectangle")
                    .attr(
                        "data-label",
                        "Drag a rectangle to search for datasets in that region",
                    )
                    .attr(
                        "title",
                        "Drag a rectangle to search for datasets in that region",
                    );
            });

            $("#dataset-map").on("focusout", function (e) {
                setTimeout(function () {
                    if (!$("#dataset-map").find($(":focus")).length) {
                        $(".dataset-map-controls .map-apply").focus();
                    }
                }, 10);
            });

            $("#facet-collapse-map").on("shown.bs.collapse", _refreshMapView);
            $(".show-filters").on("click", _refreshMapView);

            // Initialize the draw control

            map.addControl(
                new L.Control.Draw({
                    position: "topright",
                    edit: {
                        featureGroup: featureGroup,
                        remove: false,
                    },
                    draw: {
                        polyline: false,
                        polygon: false,
                        circle: false,
                        circlemarker: false,
                        marker: false,
                        rectangle: {shapeOptions: module.options.style},
                    },
                }),
            );

            map.addControl(new ExpandButton({position: "topleft"}));

            function _refreshMapView() {
                if (map) {
                    setTimeout(function () {
                        map.invalidateSize();
                        map.fitBounds(module.options.default_extent); // Adjust map size after container becomes visible
                    }, 50); // Delay may be adjusted based on UI behavior
                }
            }

            function _resetInputs(disable = true) {
                $(".coordinates-block input").each(function (_, el) {
                    el.value = "";
                    el.disabled = disable;
                });
            }

            function _resetPoints() {
                $("#lga-select").val("");
                $("#ext_bbox").val("");
                $("#ext_bbox_lga").val("");
                apply_switch(false);
                _resetInputs(false);
                if (extentLayer) {
                    featureGroup.removeLayer(extentLayer);
                    map.removeLayer(extentLayer);
                    extentLayer = null;
                    map.fitBounds(module.options.default_extent);
                }
            }

            $(".dga-lga-reset .btn").on("click", function () {
                _resetPoints();
            });

            $(".dataset-map-controls .map-cancel").on("click", function () {
                _resetPoints();
                _applySelection();
            });

            function _applySelection() {
                map._container
                    .closest(".dataset-map")
                    .classList.remove("dga-expanded-map");

                is_expanded = false;
                resetMap(map);
                // Eugh, hacky hack.
                setTimeout(function () {
                    if (extentLayer) {
                        map.fitBounds(extentLayer.getBounds());
                    }
                    submitForm();
                }, 200);
            }

            // Handle the apply expanded action
            $(".dataset-map-controls .map-apply").on("click", submitForm);

            $("#west-lng, #south-lat, #east-lng, #north-lat").on(
                "change",
                function () {
                    var c = [];
                    for (var i in aForm) {
                        c.push(aForm[i].val());
                    }
                    if (
                        c.every(function (e) {
                            return e.length;
                        })
                    ) {
                        // unlike BBox with order WSEN, rectangles are created
                        // using `L.LatLngBounds` which expect SWNE order
                        var rect = getRectFromCoordinates([
                            [c[1], c[0]],
                            [c[3], c[2]],
                        ]);
                        drawRect(rect);
                    } else {
                        apply_switch(false);
                    }
                },
            );

            $("#lga-select").on("change", function (e) {
                var lgaName = e.target.value;
                if (extentLayer) {
                    _resetPoints();
                }
                $("#lga-select").val(lgaName);
                client.call(
                    "GET",
                    "dga_lga_geometry_show",
                    "?lga_name=" + lgaName,
                    function (data) {
                        drawBBox(data.result.geometry);
                    },
                    function (error) {
                        console.log(error);
                    },
                );
            });

            var redrawLayer;
            map.on("draw:editmove draw:editresize", function (e) {
                redrawLayer = e.layer;
            });
            map.on("draw:drawstart", function (e) {
                var container = $(e.target.getContainer());
                container
                    .find(".leaflet-draw-draw-rectangle")
                    .attr(
                        "data-label",
                        "Drag a rectangle to search for datasets in that region",
                    );
                container
                    .removeClass("draw-completed")
                    .addClass("draw-started");
            });
            map.on("mousedown", function (e) {
                var container = $(e.target.getContainer());
                container.addClass("draw-in-progress");
            });
            map.on("mouseup", function (e) {
                var container = $(e.target.getContainer());
                container.removeClass("draw-in-progress");
                if (redrawLayer) {
                    drawRect(redrawLayer);
                    redrawLayer = null;
                }
            });
            map.on("draw:drawstop", function (e) {
                if (
                    !map._container
                        .closest(".dataset-map")
                        .classList.contains("dga-expanded-map")
                ) {
                    submitForm();
                }
            });

            var rct = $(map.getContainer())[0];
            var box = rct.getBoundingClientRect();
            var rInitTop = box.top;
            var rInitBottom = box.bottom;
            var windowHeight = window.innerHeight;
            var targetOffset = null;
            if (rInitTop < 0) {
                targetOffset = window.pageYOffset + rInitTop;
            } else {
                targetOffset = rInitBottom - windowHeight;
            }

            function _isRectangleInViewport(el) {
                if (rInitTop < 0) {
                    return window.pageYOffset <= targetOffset;
                } else {
                    return window.pageYOffset >= targetOffset;
                }
            }

            function _inViewPort() {
                if (_isRectangleInViewport(rct)) {
                    document.removeEventListener("scroll", _scrollHandler);
                    window.removeEventListener("resize", _resizeHandler);
                }
            }

            function _scrollHandler() {
                _inViewPort();
            }

            function _resizeHandler() {
                if (rInitTop < 0) {
                    targetOffset = window.pageYOffset + rInitTop;
                } else {
                    windowHeight = window.innerHeight;
                    targetOffset = rInitBottom - windowHeight;
                }
                _inViewPort();
            }

            document.addEventListener("scroll", _scrollHandler);
            window.addEventListener("resize", _resizeHandler);

            function loadTheMap() {
                event.preventDefault();
                if (!is_expanded) {
                    map._container
                        .closest(".dataset-map")
                        .classList.add("dga-expanded-map");

                    if (should_zoom) {
                        map.zoomIn();
                    }
                    resetMap(map);
                    is_expanded = true;

                    if (extentLayer) {
                        previous_extent = extentLayer;
                        map.fitBounds(extentLayer.getBounds());
                    }
                }
            }

            map.on("draw:created", function (e) {
                setTimeout(function () {
                    drawRect(e.layer);
                }, 300);
                apply_switch(true);
            });

            // OK, when we expand we shouldn't zoom then
            map.on("zoomstart", function (e) {
                should_zoom = false;
            });

            function getRectFromCoordinates(c) {
                return new L.Rectangle(
                    new L.LatLngBounds(L.latLng(c[0]), L.latLng(c[1])),
                    module.options.style,
                );
            }

            function drawRect(rect) {
                if (extentLayer) {
                    featureGroup.removeLayer(extentLayer);
                    map.removeLayer(extentLayer);
                }
                var bbox = rect.getBounds().toBBoxString();
                bbox = bbox
                    .split(",")
                    .map(function (n) {
                        return Number(n).toFixed(1);
                    })
                    .join(",");
                drawBBox(bbox);
            }

            function fillForm(bounds) {
                if (bounds === null) {
                    $(".extended-map-form input").val("");
                    $("#ext_bbox").val("");
                    return;
                }
                var b = $.map(bounds.split(","), function (e) {
                    return parseFloat(e).toFixed(1);
                });
                for (var i in b) {
                    if (aForm[i].val() != parseFloat(b[i])) {
                        aForm[i].val(b[i]).trigger("change");
                    }
                }
            }

            function apply_switch(state) {
                $(".dataset-map-controls .map-apply").prop("disabled", !state);
            }

            function _drawExtentFromCoords(xmin, ymin, xmax, ymax) {
                if ($.isArray(xmin)) {
                    var coords = xmin;
                    xmin = coords[0];
                    ymin = coords[1];
                    xmax = coords[2];
                    ymax = coords[3];
                }
                if (is_expanded) {
                    return new L.Rectangle(
                        [
                            [ymin, xmin],
                            [ymax, xmax],
                        ],
                        module.options.style,
                    );
                }
                return new L.Rectangle(
                    [
                        [ymin, xmin],
                        [ymax, xmax],
                    ],
                    module.options.green_style,
                );
            }

            function drawBBox(bbox) {
                extentLayer = _drawExtentFromCoords(bbox.split(","));
                $("#ext_bbox").val(bbox);
                $("#ext_bbox_lga").val($("#lga-select option:selected").val());
                fillForm(bbox);
                map.addLayer(extentLayer);
                setTimeout(function () {
                    map.fitBounds(extentLayer.getBounds());
                }, 300);
                setTimeout(function () {
                    if (is_expanded) {
                        featureGroup.addLayer(extentLayer);
                    }
                }, 300);
                apply_switch(true);
            }

            // Add the loading class and submit the form
            function submitForm() {
                setTimeout(function () {
                    form.submit();
                }, 800);
            }

            // Ok setup the default state for the map
            let previous_bbox = module._getParameterByName("ext_bbox");

            if (previous_bbox) {
                drawBBox(previous_bbox);
            } else {
                fillForm(null);
            }

            let previous_lga = module._getParameterByName("ext_bbox_lga");
            if (previous_lga) {
                $("#lga-select").val(previous_lga).select2();
            }

            if (extentLayer) {
                map.fitBounds(extentLayer.getBounds());
            } else {
                map.fitBounds(module.options.default_extent);
            }
        },
    };
    L.EditToolbar.prototype.options.edit.selectedPathOptions =
        patch.options.style;
    return $.extend({}, ckan.module.registry["spatial-query"].prototype, patch);
});
