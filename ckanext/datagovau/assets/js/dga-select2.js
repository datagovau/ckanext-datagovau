ckan.module("dga-select2", function ($) {
    return {
        options: { minimumResultsForSearch: 10 },
        initialize() {
            this.el.select2(this.options);
        },
    };
});
