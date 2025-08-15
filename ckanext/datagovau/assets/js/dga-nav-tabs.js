ckan.module("dga-nav-tabs", function ($) {
    return {
        initialize: function () {
            const module = this;

            const adjustFlexContainerClasses = function () {
                const $container = module.el;
                const $items = $container.children();
                if (!$items.length) return;

                let rowCount = 1;
                let prevOffsetTop = $items.eq(0).offset().top;

                $items.each(function (i) {
                    if (i === 0) return;
                    const currentOffsetTop = $(this).offset().top;
                    if (currentOffsetTop !== prevOffsetTop) {
                        rowCount++;
                        prevOffsetTop = currentOffsetTop;
                    }
                });

                if (rowCount > 1) {
                    $container.addClass("mb-2");
                } else {
                    $container.removeClass("mb-2");
                }
            };

            adjustFlexContainerClasses();
            $(window).on("resize", adjustFlexContainerClasses);
        }
    };
});
