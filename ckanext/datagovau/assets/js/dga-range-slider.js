ckan.module("dga-range-slider", function ($) {
    return {
        options: {
            reflect: null,
        },
        initialize() {
            const reflect = $(this.options.reflect);

            console.log(this.el, reflect);
            this.el.on("change", (e) => reflect.val(e.target.value || 0));
            reflect.on("input", (e) => this.el.val(e.target.value || 0));
        },
    };
});
