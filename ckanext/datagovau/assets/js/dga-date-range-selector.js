ckan.module("dga-date-range-selector", function ($) {
    return {
        options: {
            startDate: null,
            endDate: null,
            startYear: new Date().getFullYear(),
            endYear: new Date().getFullYear(),
        },

        initialize: function () {
            $.proxyAll(this, /_on/);

            this.el.on("click", "#date-trigger", this._onTriggerClick);
            this.el.on("click", ".month-btn", this._onMonthSelect);
            this.el.on("click", "#clear-btn", this._onClear);
            this.el.on("click", "#apply-btn", this._onApply);
            this.el.on("click", ".year-nav", this._onYearChange);

            this._initFromUrl();
            this._updateYearDisplays();
            this._updateDateDisplay();
            this._updateSelectedMonths();
            this._updateApplyButtonState();
            this._updateAvailability();
        },

        _onTriggerClick: function (e) {
            e.stopPropagation();
            this.el.find("#calendar-dropdown").toggleClass("active");
        },

        _onYearChange: function (e) {
            const $btn = $(e.target).closest(".year-nav");
            const isStart = $btn.attr("data-calendar") === "start";
            const increment = $btn.hasClass("next-year") ? 1 : -1;
            const currentYear = new Date().getFullYear();
            const yearOption = isStart ? "startYear" : "endYear";
            const dateOption = isStart ? "startDate" : "endDate";

            if (this.options[yearOption] === currentYear && increment === 1)
                return;

            this.options[yearOption] += increment;
            if (this.options[dateOption]) {
                const oldDate = this.options[dateOption];
                this.options[dateOption] = new Date(
                    this.options[yearOption],
                    oldDate.getMonth() + (isStart ? 0 : 1),
                    isStart ? 1 : 0,
                );
            }

            this._updateYearDisplays();
            this._updateDateDisplay();
            this._updateSelectedMonths();
            this._validateDateRange();
            this._updateAvailability();
        },

        _onMonthSelect: function (e) {
            const $btn = $(e.target);
            const monthIndex = $btn.index();
            const isStartCalendar = $btn.closest("#start-calendar").length > 0;
            const selectedYear = isStartCalendar
                ? this.options.startYear
                : this.options.endYear;
            const dateOption = isStartCalendar ? "startDate" : "endDate";

            if (isStartCalendar) {
                this.options[dateOption] = new Date(
                    selectedYear,
                    monthIndex,
                    1,
                );
            } else {
                this.options[dateOption] = new Date(
                    selectedYear,
                    monthIndex + 1,
                    0,
                );
            }

            if (
                this.options.startDate &&
                this.options.endDate &&
                this.options.startDate > this.options.endDate
            ) {
                this.options.endDate = null;
            } else if (
                this.options.endDate &&
                this.options.startDate &&
                this.options.endDate < this.options.startDate
            ) {
                this.options.endDate = null;
            }

            this._updateSelectedMonths();
            this._updateDateDisplay();
            this._updateApplyButtonState();
            this._updateAvailability();
        },

        _onClear: function () {
            this.options.startDate = null;
            this.options.endDate = null;
            this.options.startYear = new Date().getFullYear();
            this.options.endYear = new Date().getFullYear();

            this._updateYearDisplays();
            this._updateSelectedMonths();
            this._updateDateDisplay();
            this._updateApplyButtonState();

            const url = this._updateUrlParams(null, null);
            window.history.replaceState({}, "", url.toString());
            window.location.reload();
        },

        _onApply: function () {
            if (!this.options.startDate || !this.options.endDate) return;

            const url = this._updateUrlParams(
                this._formatDate(this.options.startDate),
                this._formatDate(this.options.endDate),
            );
            this.el.find("#calendar-dropdown").removeClass("active");
            window.location.href = url.toString();
        },

        _updateUrlParams: function (startDate, endDate) {
            const url = new URL(window.location.href);

            // Remove page parameter when changing date filters
            url.searchParams.delete("page");

            if (startDate) {
                url.searchParams.set("ext_startdate", startDate);
            } else {
                url.searchParams.delete("ext_startdate");
            }
            if (endDate) {
                url.searchParams.set("ext_enddate", endDate);
            } else {
                url.searchParams.delete("ext_enddate");
            }
            return url;
        },

        _updateYearDisplays: function () {
            this.el.find("#start-year").text(this.options.startYear);
            this.el.find("#end-year").text(this.options.endYear);
        },

        _updateSelectedMonths: function () {
            this.el.find(".month-btn").removeClass("selected");

            [
                { date: this.options.startDate, calendar: "#start-calendar" },
                { date: this.options.endDate, calendar: "#end-calendar" },
            ].forEach(({ date, calendar }) => {
                if (date) {
                    const month = date.getMonth();
                    this.el
                        .find(`${calendar} .month-btn:eq(${month})`)
                        .addClass("selected");
                    this.el.find(".month-btn").addClass("active");
                    this.el.find(".current-year").addClass("active");
                }
            });
        },

        _updateDateDisplay: function () {
            const formatDate = (date) =>
                date
                    ? date.toLocaleDateString("en-US", {
                          year: "numeric",
                          month: "short",
                      })
                    : "";
            const startDateText =
                formatDate(this.options.startDate) || "Start date";
            const endDateText = formatDate(this.options.endDate) || "End date";

            this.el.find("#date-display-start").text(startDateText);
            this.el.find("#date-display-end").html(`
                <span id="date-display-end">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <g clip-path="url(#clip0_3090_6506)">
                            <rect width="16" height="16" transform="translate(-0.00195312)" fill="white" fill-opacity="0.01"/>
                            <path fill-rule="evenodd" clip-rule="evenodd" d="M3.99805 8C3.99805 7.86739 4.05073 7.74021 4.14449 7.64645C4.23826 7.55268 4.36544 7.5 4.49805 7.5H10.291L8.14405 5.354C8.05016 5.26011 7.99742 5.13277 7.99742 5C7.99742 4.86722 8.05016 4.73989 8.14405 4.646C8.23793 4.55211 8.36527 4.49937 8.49805 4.49937C8.63082 4.49937 8.75816 4.55211 8.85205 4.646L11.852 7.646C11.8986 7.69244 11.9356 7.74762 11.9608 7.80836C11.986 7.86911 11.9989 7.93423 11.9989 8C11.9989 8.06577 11.986 8.13089 11.9608 8.19163C11.9356 8.25238 11.8986 8.30755 11.852 8.354L8.85205 11.354C8.75816 11.4479 8.63082 11.5006 8.49805 11.5006C8.36527 11.5006 8.23793 11.4479 8.14405 11.354C8.05016 11.2601 7.99742 11.1328 7.99742 11C7.99742 10.8672 8.05016 10.7399 8.14405 10.646L10.291 8.5H4.49805C4.36544 8.5 4.23826 8.44732 4.14449 8.35355C4.05073 8.25978 3.99805 8.13261 3.99805 8Z" fill="#757575"/>
                        </g>
                        <defs>
                            <clipPath id="clip0_3090_6506">
                                <rect width="16" height="16" fill="white" transform="translate(-0.00195312)"/>
                            </clipPath>
                        </defs>
                    </svg>
                    ${endDateText}
                </span>
            `);
        },

        _validateDateRange: function () {
            if (
                this.options.startDate &&
                this.options.endDate &&
                this.options.startDate > this.options.endDate
            ) {
                this.options.endDate = null;
                this._updateSelectedMonths();
                this._updateDateDisplay();
                this._updateApplyButtonState();
            }
        },

        _updateApplyButtonState: function () {
            const hasDates = this.options.startDate && this.options.endDate;
            this.el
                .find("#apply-btn, #clear-btn")
                .prop("disabled", !hasDates)
                .toggleClass("disabled", !hasDates);
        },

        _formatDate: function (date) {
            return date.toLocaleDateString("en-CA", {
                year: "numeric",
                month: "2-digit",
                day: "2-digit",
            });
        },

        _initFromUrl: function () {
            const urlParams = new URLSearchParams(window.location.search);
            const urlStartDate = urlParams.get("ext_startdate");
            const urlEndDate = urlParams.get("ext_enddate");

            if (urlStartDate) {
                this.options.startDate = new Date(urlStartDate);
                this.options.startYear = this.options.startDate.getFullYear();
            }

            if (urlEndDate) {
                this.options.endDate = new Date(urlEndDate);
                this.options.endYear = this.options.endDate.getFullYear();
            }
        },

        _updateAvailability() {
            const now = new Date();

            const startYear = this.el.find("#start-year");
            const endYear = this.el.find("#end-year");

            const startCalendar = this.el.find("#start-calendar");
            const endCalendar = this.el.find("#end-calendar");

            startYear
                .next()
                .prop("disabled", startYear.text() >= endYear.text());

            endYear.prev().prop("disabled", startYear.text() >= endYear.text());

            endYear
                .next()
                .prop("disabled", endYear.text() >= now.getFullYear());

            if (startYear.text() === endYear.text()) {
                if (this.options.startDate) {
                    const buttons = endCalendar.find(".month-btn");
                    const split = this.options.startDate.getMonth();
                    buttons.slice(0, split).prop("disabled", true);
                    buttons.slice(split).prop("disabled", false);
                }

                if (this.options.endDate) {
                    const buttons = startCalendar.find(".month-btn");
                    const split = this.options.endDate.getMonth() + 1;
                    buttons.slice(0, split).prop("disabled", false);
                    buttons.slice(split).prop("disabled", true);
                }
            } else {
                startCalendar
                    .add(endCalendar)
                    .find(".month-btn")
                    .prop("disabled", false);
            }
        },
    };
});
