// This module includes logic for auto submitting the search form when clicking
// on the `include_children` checkbox implemented from `hierarchy` extension

ckan.module("dga-include-children", function ($) {
    "use strict";
    return {
        options: {},

        initialize: function () {
            this.el.on("click", this._onClick);
        },

        _onClick: function (e) {
            if ($("#include_children").is(":checked")) {
                $("#organization-datasets-search-form").submit();
            } else {
                const url = new URL(window.location.href);
                const param = "include_children"
                if (url.searchParams.has(param)) {
                    url.searchParams.delete(param);
                    window.history.pushState({}, '', url);
                    window.location.reload();
                }
            }
        },
    };
});
