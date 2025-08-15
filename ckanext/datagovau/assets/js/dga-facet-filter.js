this.ckan.module('dga-facet-filter', function ($, _) {
    "use strict";
    return {
        options: {
            category: "items",
        },
        initialize: function () {
            $.proxyAll(this, /_on/);

            const ul = this.el.closest('.facet-search-input')[0].nextElementSibling;
            const targetSelector = '#' + ul.id;                       // "#facet-container-…"

            const form = document.querySelector(
                `form[hx-target="${targetSelector}"]`);

            if (!form) {
                console.error('Facet form not found for', targetSelector);
                return;
            }

            const self = this;

            const afterSwapHandler = (e) => {
                if (e.detail.target === ul) {
                    htmx.off("htmx:afterSwap", afterSwapHandler);
                    self.ulElement = ul;
                    self._postFacetInit();
                }
            };

            htmx.on("htmx:afterSwap", afterSwapHandler);
            htmx.trigger(form, "dga:load-facets");
        },


        _postFacetInit: function () {
            this._hideChildren = this._hideChildren.bind(this);
            this._onInputChange = this._onInputChange.bind(this);
            this._checkForHiddenness = this._checkForHiddenness.bind(this);
            this._deleteEmptyEl = this._deleteEmptyEl.bind(this);
            this._showMoreItems = this._showMoreItems.bind(this);
            this._showLessItems = this._showLessItems.bind(this);
            this._countVisibleChildren = this._countVisibleChildren.bind(this);

            this.ulElement = this.el.closest('.facet-search-input')[0].nextElementSibling;
            this.children = this.ulElement.querySelectorAll("li");

            this.showMoreButton = $(this.ulElement).next('.module-footer');
            this.showMoreButton.find('.show-more').on('click', this._showMoreItems);
            this.showMoreButton.find('.show-less').on('click', this._showLessItems);
            this.isShowAll = false;

            this.input = this.el;
            $(this.input).on("input", this._onInputChange);

            this.clearBtn = $(this.input).siblings('.clear-btn');
            this.clearBtn.on('click', this._onClearClick.bind(this));

            this._onInputChange();
        },

        _checkForHiddenness: function () {
            if (this._isAllHidden(this.children)) {
                if (this.ulElement.querySelector("nav.empty")) {
                    return;
                }
                const emptyEl = document.createElement("nav");
                emptyEl.classList.add("py-2", "empty");
                emptyEl.textContent = "There are no " + this.options.category + " that match this search.";
                this.ulElement.appendChild(emptyEl);
            } else {
                this._deleteEmptyEl();
            }
        },

        _isAllHidden: function (children) {
            for (var i = 0; i < children.length; i++) {
                if (!children[i].hidden) {
                    return false;
                }
            }
            return true;
        },

        _deleteEmptyEl: function () {
            const emptyEl = this.ulElement.querySelector("nav.empty");
            if (emptyEl) emptyEl.remove();
        },

        _onInputChange: function () {
            const val = this.input.val().toLowerCase();

            for (var i = 0; i < this.children.length; i++) {
                this.children[i].hidden = !~(
                    this.children[i]
                        .querySelector(".item-label")
                        .textContent.toLowerCase() || ""
                ).indexOf(val);
            }

            var hideOrShow = this._countVisibleChildren() > 10;

            this.showMoreButton.toggleClass('hidden', !hideOrShow);
            this._hideChildren();
        },

        _hideChildren: function () {
            // show only first 10 items if not Show ALL
            for (var i = 0, shownItems = 0; i < this.children.length; i++) {
                if (!this.children[i].hidden) shownItems++;
                if (shownItems > 10 && !this.isShowAll) {
                    this.children[i].hidden = true;
                }
            }
            this._checkForHiddenness();
        },

        _showMoreItems: function () {
            this.isShowAll = true;
            this._onInputChange();
            $(this.input).closest('.facet-nav').addClass('show-all');
        },

        _showLessItems: function () {
            this.isShowAll = false;
            this._onInputChange();
            $(this.input).closest('.facet-nav').removeClass('show-all');

        },

        _countVisibleChildren: function () {
            var counter = 0;
            for (var i = 0; i < this.children.length; i++) {
                if (!this.children[i].hidden) counter++;
            }
            return counter;
        },

        _onClearClick: function () {
            this.input.val('');
            this._onInputChange();
            this.input.focus();
        }
    };
});
