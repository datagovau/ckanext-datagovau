ckan.module("dga-about-preview", function ($) {
    "use strict";
    return {
        options: {
            fullText: ""
        },

        initialize: function () {
            var self = this;
            let paragraph = self.$(".about-preview");
            let fullText = self.options.fullText;
            let shortText = fullText.substring(0, 30) + "...";
            paragraph.html(shortText);

            this.$(".about-read-more").click(function () {
                if ($(this).hasClass("show-less")) {
                    paragraph.html(shortText);
                    $(this).text(self._("Show More"));
                } else {
                    paragraph.html(fullText);
                    $(this).text(self._("Show Less"));
                }
                $(this).toggleClass("show-less")
            });
        },
    };
});
