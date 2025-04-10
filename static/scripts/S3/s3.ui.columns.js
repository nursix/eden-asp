/**
 * jQuery UI Widget to control variable columns in dataTableS3
 *
 * @copyright 2025 (c) Sahana Software Foundation
 * @license MIT
 */
(function($, undefined) {

    "use strict";

    var variableColumnsID = 0;

    /**
     * s3.anonymize
     */
    $.widget('s3.variableColumns', {

        /**
         * Default options
         */
        options: {

        },

        /**
         * Create the widget
         */
        _create: function() {

            this.id = variableColumnsID;
            variableColumnsID += 1;

            this.eventNamespace = '.variableColumns';
        },

        /**
         * Update the widget options
         */
        _init: function() {

            const $el = $(this.element),
                  outerForm = $el.closest('form.dt-wrapper');

            this.availableColumns = $('.column-selector', outerForm);

            this.refresh();
        },

        /**
         * Remove generated elements & reset other changes
         */
        _destroy: function() {

        },

        /**
         * Redraw contents
         */
        refresh: function() {

            this._unbindEvents();

            this._bindEvents();
        },

        /**
         * Opens the column selection dialog
         */
        _openDialog: function() {

            const availableColumns = this.availableColumns;
            if (!availableColumns.length) {
                return;
            }

            // Render the dialog
            const container = $('<div>').hide().appendTo($('body')),
                  form = document.createElement('form'),
                  $form = $(form).appendTo(container),
                  ns = this.eventNamespace,
                  self = this;

            form.method = 'post';
            form.enctype = 'multipart/form-data';

            availableColumns.first().clone().removeClass('hide').show().appendTo($form);

            const dialog = container.show().dialog({
                title: i18n.selectColumns,
                autoOpen: false,
                minHeight: 480,
                maxHeight: 640,
                minWidth: 320,
                modal: true,
                closeText: '',
                open: function( /* event, ui */ ) {
                    // Clicking outside of the popup closes it
                    $('.ui-widget-overlay').off(ns).on('click' + ns, function() {
                        dialog.dialog('close');
                    });
                    // Any cancel-form-btn button closes the popup
                    $('.cancel-form-btn', $form).off(ns).on('click' + ns, function() {
                        dialog.dialog('close');
                    });
                    // Submit button updates the form and submits it
                    $('.submit-form-btn', $form).off(ns).on('click' + ns, function() {
                        if ($('.column-select:checked', container).length) {
                            self._applyColumnSelection(form);
                            dialog.dialog('close');
                        }
                    });
                    // Reset button restores the default
                    $('.reset-form-btn', $form).off(ns).on('click' + ns, function() {
                        self._applyColumnSelection(form, true);
                    });
                    // Make columns sortable
                    $('.column-options', $form).sortable({
                        placeholder: "sortable-placeholder",
                        forcePlaceholderSize: true
                    });
                    // Alternative if drag&drop not available
                    $('.column-left', $form).off(ns).on('click' + ns, function() {
                        const row = $(this).closest('tr');
                        row.insertBefore(row.prev());
                    });
                    $('.column-right', $form).off(ns).on('click' + ns, function() {
                        const row = $(this).closest('tr');
                        row.insertAfter(row.next());
                    });
                    // Select/deselect all
                    $('.column-select-all', $form).off(ns).on('change' + ns, function() {
                        let status = $(this).prop('checked');
                        $('.column-select', $form).prop('checked', status);
                    });
                    $('.column-select', $form).off(ns).on('change' + ns, function() {
                        let deselected = $('.column-select:not(:checked)', container).length;
                        $('.column-select-all', $form).prop('checked', !deselected);
                    });
                },
                close: function() {
                    // Hide + remove the container
                    $('.column-options', $form).sortable('destroy');
                    container.hide().remove();
                }
            });

            dialog.dialog('open');
        },

        /**
         * Reloads the page, applying the column selection
         */
        _applyColumnSelection: function(form, reset) {

            // Get a link to the current page
            const link = document.createElement('a');
            link.href = window.location.href;

            const params = new URLSearchParams(link.search);
            params.delete('aCols');

            if (!reset) {
                // Get selected columns indices from form
                const selected = [];
                $('.column-select:checked', form).each(function() {
                    selected.push($(this).data('index'));
                });
                if (selected.length) {
                    params.append('aCols', selected.join(','));
                }
            }

            // Reload the page
            link.search = params.toString();
            window.location.href = link.href;
        },

        /**
         * Bind events to generated elements (after refresh)
         */
        _bindEvents: function() {

            const self = this,
                  ns = this.eventNamespace;

            $(this.element).on('click' + ns, function() {
                self._openDialog();
            });

            return true;
        },

        /**
         * Unbind events (before refresh)
         */
        _unbindEvents: function() {

            const ns = this.eventNamespace;

            $(this.element).off(ns);

            return true;
        }
    });
})(jQuery);
