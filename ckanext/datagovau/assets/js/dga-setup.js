ckan.module("dga-setup", function ($) {
    "use strict";
    function correctNums() {
        _repTag("dl", "p");
        _repTag("dt", "span");
        _repTag("dd", "span");
    }
    function _repTag(old, updated) {
        $(old).each(function () {
            $(this).replaceWith(
                $("<" + updated + ">")
                    .html($(this).html())
                    .addClass(old),
            );
        });
    }
    correctNums();

    document
        .querySelectorAll('[data-module="tooltip"]')
        .forEach((el) => bootstrap.Tooltip.getOrCreateInstance(el));
});
