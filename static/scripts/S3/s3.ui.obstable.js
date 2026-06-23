/**
 * jQuery UI Widget for ObsTable
 *
 * @copyright 2026 (c) Sahana Software Foundation
 * @license MIT
 */

/* jshint esversion: 6 */

(function($, undefined) {

    "use strict";
    var obsTableID = 0;

    /**
     * obsTable
     */
    $.widget('s3.obsTable', {

        /**
         * Default options
         *
         * @todo document options
         */
        options: {

        },

        /**
         * Create the widget
         */
        _create: function() {

            this.id = obsTableID;
            obsTableID += 1;

            this.eventNamespace = '.obsTable';
        },

        /**
         * Update the widget options
         */
        _init: function() {

            this.refresh();
        },

        /**
         * Remove generated elements & reset other changes
         */
        _destroy: function() {

            $.Widget.prototype.destroy.call(this);
        },

        /**
         * Redraw contents
         */
        refresh: function() {

            this._unbindEvents();

            this._bindEvents();
        },

        /**
         * Bind events to generated elements (after refresh)
         */
        _bindEvents: function() {

            let $el = $(this.element),
                ns = this.eventNamespace,
                self = this;

            return true;
        },

        /**
         * Unbind events (before refresh)
         */
        _unbindEvents: function() {

            let $el = $(this.element),
                ns = this.eventNamespace;

            return true;
        }
    });
})(jQuery);
