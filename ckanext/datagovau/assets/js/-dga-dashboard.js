///////////////////////////////////////////////////////////////////////////////
//      Prevent scroll-to-top when activity filter is opened on dashboard     //
///////////////////////////////////////////////////////////////////////////////
ckan.module("-dga-dashboard", function ($) {
    const origin = ckan.module.registry["dashboard"];
    if (!origin) {
        console.warn("CKAN `dashboard` module cannot be found.");
        return;
    }

    // Override initialize to disable Popover creation
    origin.prototype.initialize = function () {
        $.proxyAll(this, /_on/);

        this.button = $('#followee-filter .btn')
            .on('click', this._onShowFolloweeDropdown);
        // Removed Popover setup here
    };

    // Original function calls `input.focus()` in the end which causes page
    // scroll. This is undesired behavior, so we are not focusing on the input.
    origin.prototype._onInitSearch = function () {
        var input = $("input", this.popover);
        if (!input.hasClass("inited")) {
            input.on("keyup", this._onSearchKeyUp).addClass("inited");
        }
    }
});
