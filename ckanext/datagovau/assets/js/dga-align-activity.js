ckan.module("dga-align-activity", function ($) {
    return {
        initialize: function () {
            this.el.find("li.item").each(function () {
                const $li = $(this);
                $li.children("span")
                    .has("img.user-image")
                    .has("a[href^='/user/'], a[href^='/data/user/']")
                    .contents().unwrap();

                const clone = $li.clone();
                clone.find("span, img, a, br").remove();
                const extractedText = clone.text().trim();

                if (extractedText) {
                    $li.html($li.html().replace(extractedText, "").trim());
                }

                const $userLink = $li.find("a[href^='/user/'], a[href^='/data/user/']").first();
                if ($userLink.length) {
                    const $nextLink = $li.find("a").not($userLink).first();
                    const $span = $('<span class="activity-text"></span>');

                    $span.append($userLink);
                    if (extractedText) {
                        $span.append($('<span></span>').text(" " + extractedText + " "));
                    }
                    if ($nextLink.length) {
                        $span.append($nextLink);
                    }

                    const $avatar = $li.find("img.user-image");
                    $avatar.length ? $avatar.after($span) : $li.prepend($span);
                }
            });
        }
    };
});
