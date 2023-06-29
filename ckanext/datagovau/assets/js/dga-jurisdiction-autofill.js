ckan.module("dga-jurisdiction-autofill", function ($) {
    "use strict";
    return {
        options: {},

        initialize: function () {
            this.jurisdiction_entered_manually = false;
            this.new_dataset = ($('.stages')[0]) ? true : false;
            this.org_field = $('#field-organizations');
            if (this.new_dataset) {
                this._onChange(this);
                this.org_field.on("change", this._onChange.bind(this));
                this.el.on("input", this._checkManualEntering.bind(this));
            }
        },

        _onChange: async function (e) {
            if (!this.jurisdiction_entered_manually) {
                var org_dict = new Promise((ok, fail) => {
                    fetch(this.sandbox.client.call(
                        "GET",
                        "organization_show",
                        "?id=" + this.org_field.val(),
                        data => ok(data.result), fail));
                });
                const dict = await org_dict;
                this.el.val(dict['jurisdiction']);
            }
        },

        _checkManualEntering: function (e) {
            this.jurisdiction_entered_manually = true;
        },
    };
});
