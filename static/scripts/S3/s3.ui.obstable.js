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

            const $el = $(this.element),
                  widgetID = $el.attr('id'),
                  dataInput = $('#' + widgetID + '-data');

            // Read+parse initial data
            self.data = {};
            if (dataInput.length) {
                try {
                    self.data = JSON.parse(dataInput.val());
                } catch(e) {
                    // pass
                }
            }

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

            this._renderTable(self.data);

            this._bindEvents();
        },

        _renderTable: function(data) {

            const $el = $(this.element);

            const head = this._renderHeader(data),
                  body = this._renderBody(data),
                  foot = this._renderFooter(data);

            $el.empty()
               .append(head)
               .append(body)
               .append(foot);

            head.show();
            foot.show();
            body.show();
        },

        _renderHeader: function(data) {

            const head = $('<thead>').hide(),
                  row = $('<tr>').appendTo(head),
                  label = data.label || '',
                  slots = data.slots || [];

            $('<th scope="col">').addClass('fixed').text(label).appendTo(row);
            slots.forEach(function(slot) {
                var slotLabel = slot[2] || '??';
                $('<th scope="col">').text(slotLabel).appendTo(row);
            });

            return this._renderSlots(head, data);
        },

        _renderBody: function(data) {

            const body = $('<tbody>').hide(),
                  slots = data.slots || [],
                  params = data.params || [];

            params.forEach(function(param) {

                var row = $('<tr>').appendTo(body),
                    label = $('<div class="obstable-param">').text(param.name || '??'),
                    range = $('<div class="obstable-range">').text(param.range || '??'),
                    values = param.values;

                $('<th class="fixed">').append(label).append(range).appendTo(row);
                slots.forEach(function(slot) {
                    var slotID = slot[0],
                        cell = $('<td>').appendTo(row),
                        cellData = values[slotID];
                    if (cellData) {
                        var value = cellData[0] || '***',
                            status = cellData[1],
                            outOfRange = cellData[2],
                            invalid = cellData[3];

                        // TODO process status, range excess and inalid
                        cell.text(value);
                    }
                });
            });

            return body;
        },

        _renderFooter: function(data) {

            const foot = $('<tfoot>').hide();

            return this._renderSlots(foot, data);
        },

        _renderSlots: function(container, data) {

            const row = $('<tr>').appendTo(container),
                  label = data.label || '',
                  slots = data.slots || [];

            $('<th scope="col">').addClass('fixed').text(label).appendTo(row);
            slots.forEach(function(slot) {
                var slotLabel = slot[2] || '??';
                $('<th scope="col">').text(slotLabel).appendTo(row);
            });

            return container;
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
