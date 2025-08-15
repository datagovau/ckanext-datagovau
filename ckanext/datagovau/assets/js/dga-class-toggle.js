ckan.module("dga-class-toggle", function ($) {
    return {
        options: {
            event: "click",
            className: "active",
        },
        initialize() {
            this.el.on(this.options.event, () =>
                this.el.toggleClass(this.options.className),
            );
        },
    };
});
