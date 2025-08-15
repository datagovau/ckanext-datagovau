ckan.module("dga-scroll-to-top", function ($) {
    "use strict";

    return {
        initialize: function () {
            $.proxyAll(this, /_/);

            this.el.on("click", this._scrollToTop);
            $(window).on("scroll", this._toggleVisibility);

            this._toggleVisibility();
        },

        _scrollToTop: function (e) {
            if (
                e.type === 'keydown' &&
                e.keyCode !== 13 /*enter*/ &&
                e.keyCode !== 32 /*space*/
            ) {
                return;
            }

            e.preventDefault();

            $('body, html').animate({ scrollTop: 0 }, 400);
        },

        _toggleVisibility: function (e) {
            if ($(document).scrollTop() > 150) {
                this.el.fadeIn();
            } else {
                this.el.fadeOut();
            }
        },
    };
});
