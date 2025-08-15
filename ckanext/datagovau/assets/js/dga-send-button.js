ckan.module('dga-send-button', function ($) {
    return {
        initialize: function () {
            const $btn = this.el;
            const $form = $btn.closest('form');

            $form.one('submit', function () {
                $btn.prop('disabled', true).text('Sending…');
            });
        }
    };
});
