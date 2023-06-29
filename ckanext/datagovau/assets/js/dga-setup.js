ckan.module("dga-setup", function ($) {
  "use strict";

  function insertRequiredNoteBeforeForm() {
    $(".form-group").first().before($(".control-required-message"));
  }

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
          .addClass(old)
      );
    });
  }

  insertRequiredNoteBeforeForm();
  correctNums();
});
