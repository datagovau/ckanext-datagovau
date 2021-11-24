ckan.module("dga-breadcrumbs", function ($) {
  "use strict";
  return {
    initialize: function () {
      this.$(".breadcrumb li a").each(function () {
        if (this.innerText && this.innerHTML) {
          this.innerHTML = '<h3 class="nav-styled">' + this.innerHTML + "</h3>";
        } else {
          $(this).html($('<h3 class="nav-styled">').html($(this).html()));
        }
      });
    },
  };
});
