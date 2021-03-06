function viewErrorHide() {
    $('.data-viewer-error [data-toggle="collapse"]').attr('data-toggle', '').on('click', function (e) {
        $('#data-view-error').toggleClass('collapse');
    })
}

function addAltToAvatar() {
    var name = $('span.username').text();
    var user = $('img.gravatar');
    _updateAttribute(user, 'alt', (name || 'User' ) + ' profile image')
}

function addTitleToSearch() {
    var search = $('input.search');
    _updateAttribute(search, 'title', 'Search:')

    search = $('input#field-sitewide-search');
    _updateAttribute(search, 'title', 'Sitewidth search:')
}

function addTextToI() {
    _addReaderTextToButtons('i.icon-remove', 'Remove item');
    _addReaderTextToButtons('form.site-search  i.icon-search', 'Search');
}

function insertRequiredNoteBeforeForm() {
    $('.control-group').first().before($('.control-required-message'));
}

function textAfterDropdown() {
    var icon = $('.resource-item .dropdown-toggle i');
    icon.after($('<span>').addClass('visually-hidden').text(' show below'))
    $('.resource-item .dropdown').on('click', _onDropClick)
}

function correctNums() {
    _repTag('dl', 'p');
    _repTag('dt', 'span');
    _repTag('dd', 'span');
}

function navigationInH3() {
    $('.nav-tabs>li>a, .breadcrumb li a').each(function () {
        if (this.innerText && this.innerHTML) {
            this.innerHTML = '<h3 class="nav-styled">' + this.innerHTML + '</h3>'
        }
        else {
            $(this).html($('<h3 class="nav-styled">').html($(this).html()))
        }
    })
}


function _updateAttribute(element, attr, value) {
    element.attr(attr, element.attr(attr) || value)
}

function _addReaderTextToButtons(selector, text) {
    var self = $(selector);
    $(selector).html('<img src="" class="visually-hidden" alt="' + text + '"/>');
    if (self.next().is('span')) return;
    self.after($('<span>').addClass('visually-hidden').text(text));
}

function _onDropClick(event) {
    var self = $(this);
    var target = $(event.target).find('.visually-hidden');
    if (self.hasClass('open')) {
        if (target.innerText) target.innerText = ' show below';
        else target.text(' show below');
    } else {
        if (target.innerText) target.innerText = ' hide below';
        else target.text(' hide below');
    }
}

function _repTag(old, updated) {
    $(old).each(function () {
        $(this).replaceWith($('<' + updated + '>').html($(this).html()).addClass(old))
    });
}

function gazSearch(gazURL) {
    if (gazURL != undefined && gazURL.trim().substring(0, 1) == "{") {
        // geojson
        $('#spatial').val(gazURL.replace("\n", ""));
    } else {
        var re = new RegExp("submit1=(.*\\d)(&|$)");
        var m = re.exec(gazURL);
        if (m != null) {
            gazID = m[1];
            $.getJSON("/api/2/util/gazetteer/latlon?q=" + gazID, function (data) {
                if (data.geojson != undefined) {
                    $('#spatial').val(data.geojson);
                }
            })
        } else {
            var re2 = new RegExp("[a-zA-Z].*\\d");
            var m2 = re2.exec(gazURL);
            if (m2 != null) {
                gazID = m2[0];
                $.getJSON("/api/2/util/gazetteer/latlon?q=" + gazID, function (data) {
                    if (data.geojson != undefined) {
                        $('#spatial').val(data.geojson);
                    }
                })
            }
        }
    }
}

var dga_prev_handler = window.onload;
window.onload = function () {
    if (dga_prev_handler) {
        dga_prev_handler();
    }
    addAltToAvatar();
    addTextToI();
    addTitleToSearch();
    insertRequiredNoteBeforeForm();
    textAfterDropdown();
    correctNums();
    navigationInH3();
    viewErrorHide();


    $("#field-spatial_coverage").change(function (e) {
        gazURL = e.target.value;
        gazSearch(gazURL);
    });


    if (!Date.prototype.toCKANString) {
        Date.prototype.toCKANString = function () {
            function pad(n) {
                return n < 10 ? '0' + n : n
            }

            return this.getUTCFullYear() + '-'
                + pad(this.getUTCMonth() + 1) + '-'
                + pad(this.getUTCDate()) + 'T'
                + pad(this.getUTCHours()) + ':'
                + pad(this.getUTCMinutes()) + ':'
                + pad(this.getUTCSeconds());
        };
    }
    $("#field-image-url").on('change', function () {
        if ($("#zip_extract")[0].checked) {
            $("#field-last_modified").val(new Date().toCKANString());
        }
    });
    $("#zip_extract").on('change', function () {
        if (this.checked) {
            $("#field-last_modified").val(new Date().toCKANString());
        }
    });
    $("#field-format").change(function (e) {
        if (e.target.value.toLowerCase() == 'wms') {
            $("#wms_layer").show();
        } else {
            $("#wms_layer").hide();
        }
    });

    if (typeof $("#field-format").val() !== 'undefined' && $("#field-format").val().toLowerCase() == 'wms') {
        $("#wms_layer").show();
    } else {
        $("#wms_layer").hide();
    }

    gazSearch($("#field-spatial_coverage").val());
    $(function () {
        $("#field-temporal_coverage-from").datepicker();
        $("#field-temporal_coverage-to").datepicker();
        $("#field-last_modified").datepicker();
    });
    if (typeof rssfeedsetup !== "undefined") {
        rssfeedsetup();
    }
}

