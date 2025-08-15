ckan.module("dga-resource-show-more", function ($) {
    "use strict";
    return {
        options: {},

        initialize: function () {
            var self = this;
            this.$("#show-more-resources").click(function () {
                $(".resource-more").each(function () {
                    $(this).toggleClass('d-none');
                });
                $(this).toggleClass('show-more');
                if ($(this).hasClass("show-more")) {
                    $(this).text(self._('Show more'));
                } else {
                    $(this).text(self._('Show less'));
                }
            });
        },
    };
});
