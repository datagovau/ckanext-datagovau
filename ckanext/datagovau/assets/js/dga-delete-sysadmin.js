ckan.module("dga-delete-sysadmin", function ($) {
    return {
        initialize: function () {
            const modal = document.getElementById("deleteSysadminModal");
            if (!modal) return;

            this.el.find(".btn-danger").each(function () {
                const $button = $(this);
                const $form = $button.closest("form");

                modal.addEventListener("show.bs.modal", function (event) {
                    if (event.relatedTarget === $button[0]) {
                        const $confirmButton = $(modal).find("#confirmDelete");
                        $confirmButton.attr("form", $form.attr("id"));
                        console.log($confirmButton)
                    }
                });
            });
        }
    };
});
