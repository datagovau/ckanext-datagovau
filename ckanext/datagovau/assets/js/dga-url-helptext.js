ckan.module('dga-url-helptext', function ($, _) {
    return {
        initialize: function () {
            const $urlField = $('#field-name');
            if (!$urlField.length) return;

            const $urlGroup = $urlField.closest('.form-group');
            const $helpBlock = $urlGroup.find('.info-block');
            if (!$helpBlock.length) return;

            const $originalParent = $helpBlock.parent();

            function updatePlacement() {
                const isHidden = $urlGroup.is(':hidden');
                const inTempWrapper = $helpBlock.parent('.url-helptext-wrapper').length;

                if (isHidden && !inTempWrapper) {
                    const $wrapper = $('<div>', {
                        class: 'form-group url-helptext-wrapper'
                    });
                    $helpBlock.appendTo($wrapper);
                    $urlGroup.after($wrapper);
                }

                if (!isHidden && inTempWrapper) {
                    console.log("here")
                    $helpBlock.parent('.url-helptext-wrapper').remove();
                    $helpBlock.appendTo($originalParent);
                }
            }

            updatePlacement();

            const observer = new MutationObserver(updatePlacement);
            observer.observe($urlGroup[0], {
                attributes: true, attributeFilter: ['style', 'class']
            });

            this.el.data('dga-url-help-text-observer', observer);
        },
    };
});
