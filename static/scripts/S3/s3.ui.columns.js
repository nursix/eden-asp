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

            this.columnConfigs = {};
        },

        /**
         * Update the widget options
         */
        _init: function() {

            const $el = $(this.element),
                  outerForm = $el.closest('form.dt-wrapper'),
                  availableColumns = $('.column-selector', outerForm);

            this.availableColumns = availableColumns;
            this.configsURL = availableColumns.data('url');

            this.refresh();
        },

        /**
         * Remove generated elements & reset other changes
         */
        _destroy: function() {

            this._unbindEvents();
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
            const container = $('<div class="column-select-container">').hide().appendTo($('body')),
                  ns = this.eventNamespace,
                  self = this;

            availableColumns.first().clone().removeClass('hide').show().appendTo(container);

            const dialog = container.show().dialog({
                title: i18n.selectColumns,
                autoOpen: false,
                minHeight: 480,
                maxHeight: 640,
                minWidth: 320,
                modal: true,
                closeText: '',
                open: function( /* event, ui */ ) {
                    // Bind column selection events
                    self._bindDialogEvents(dialog, container);

                    // Make columns sortable
                    $('.column-options', container).sortable({
                        placeholder: "sortable-placeholder",
                        forcePlaceholderSize: true
                    });

                    // Initialize configuration manager
                    self._initConfigManager(container);
                },
                close: function() {
                    // Remove event handlers
                    self._removeDialogEvents(container);

                    // Destroy secondary widget instances
                    $('.column-options', container).sortable('destroy');

                    // Hide + remove the container
                    container.hide().remove();
                }
            });

            dialog.dialog('open');
        },

        /**
         * Reloads the page, applying the column selection
         */
        _applyColumnSelection: function(container, reset) {

            // Get a link to the current page
            const link = document.createElement('a');
            link.href = window.location.href;

            const params = new URLSearchParams(link.search);
            params.delete('aCols');

            if (!reset) {
                // Get selected columns indices
                const selected = [];
                $('.column-select:checked', container).each(function() {
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
         * Programmatically changes the column arrangement in the dialog
         * - e.g. when loading a saved configuration
         *
         * @param {jQuery} container - the container
         * @param {object} config - the column arrangement as an object like
         *                          {"columns": ["field selector", ...]}
         */
        _updateColumnSelection: function(container, config) {

            const selection = $('tbody.column-options', container),
                  selectors = $('tr', selection),
                  detached = {},
                  fieldSelectors = Array.from(config.columns);

            var lastRow;

            const insertDetached = function(currentRow) {
                lastRow = currentRow;
                while(fieldSelectors.length && detached.hasOwnProperty(fieldSelectors[0])) {
                    let fieldSelector = fieldSelectors[0],
                        detachedRow = detached[fieldSelector];
                    detachedRow.insertAfter(lastRow);
                    lastRow = detachedRow;
                    delete detached[fieldSelector];
                    fieldSelectors.splice(0, 1);
                }
            };

            selectors.each(function() {

                let currentRow = $(this),
                    checkbox = $('input.column-select', currentRow),
                    fieldSelector = checkbox.data('selector'),
                    pos = fieldSelectors.indexOf(fieldSelector);

                lastRow = currentRow;

                if (pos == -1) {
                    checkbox.prop('checked', false);
                } else if (pos == 0) {
                    checkbox.prop('checked', true);
                    fieldSelectors.splice(0, 1);
                    insertDetached(currentRow);
                } else {
                    checkbox.prop('checked', true);
                    currentRow.detach();
                    detached[fieldSelector] = currentRow;
                }
            });

            insertDetached(lastRow);
        },

        /**
         * Initializes the config manager
         *
         * @param {jQuery} container - the container
         */
        _initConfigManager: function(container) {

            var configsURL = this.configsURL;
            if (!configsURL) {
                return;
            }

            // TODO cache available configurations
            //      - do not load configs again while on the same page

            // Look up available saved column configurations
            const configOptions = $('.cfg-select-options', container),
                  throbber = $('.cfg-select-throbber', container).show(),
                  self = this;
            $.ajaxS3({
                'url': configsURL,
                'type': 'GET',
                'dataType': 'json',
                'retryLimit': 0, // only try once
                'success': function(data) {
                    const configs = data.configs,
                          savedConfigsLabel = i18n.savedConfigurations || 'Saved Configurations...';
                    if (configs && configs.length) {
                        // Remove existing options
                        configOptions.empty();
                        // Append empty option (not selectable)
                        $('<option>').val('')
                                     .text(savedConfigsLabel)
                                     .prop('disabled', true)
                                     .prop('selected', true)
                                     .appendTo(configOptions);
                        // Append selectable options
                        configs.forEach(function(config) {
                            $('<option>').val(config.id).text(config.name).appendTo(configOptions);
                        });
                    }
                },
                'always': function() {
                    throbber.hide();
                },
            });

            this._bindConfigManagerEvents(container);
        },

        /**
         * Loads a column arrangement from the server, and updates
         * the column arrangement in dialog accordingly
         *
         * @param {jQuery} container - the container
         * @param {integer} configID - the config ID
         */
        _loadConfig: function(container, configID) {

            // Check cache first
            const columnConfigs = this.columnConfigs;
            if (columnConfigs.hasOwnProperty(configID)) {
                this._updateColumnSelection(container, columnConfigs[configID]);
                return;
            }

            // Get Ajax-URL
            const configsURL = this.configsURL;
            if (!configsURL) {
                return;
            }

            // Load configuration from server
            const throbber = $('.cfg-select-throbber', container).show(),
                  self = this;
            $.ajaxS3({
                'url': configsURL + '?load=' + configID,
                'type': 'GET',
                'dataType': 'json',
                'retryLimit': 0,
                'success': function(data) {
                    // Cache column configuration
                    columnConfigs[data.id] = data;

                    // Update column arrangement in dialog
                    self._updateColumnSelection(container, data);

                    throbber.hide();
                },
                'always': function() {
                    throbber.hide();
                },
            });

        },

        /**
         * Deletes the currently selected column configuration
         *
         * @param {jQuery} container - the container
         */
        _deleteConfig: function(container) {

            const configsURL = this.configsURL;
            if (!configsURL) {
                return;
            }

            const configOptions = $('.cfg-select-options', container),
                  selectedOption = $('option:selected', configOptions),
                  configID = selectedOption.val(),
                  configName = selectedOption.text().trim();
            if (!configID || !configName) {
                return;
            }

            if (confirm('Delete "' + configName + '"?')) {
                const throbber = $('.cfg-select-throbber', container).show(),
                      url = configsURL + '?delete=' + configID,
                      self = this;
                $.ajaxS3({
                    'url': url,
                    'type': 'DELETE',
                    'dataType': 'json',
                    'retryLimit': 0,
                    'success': function(data) {
                        // Remove option from selector
                        configOptions.val('');
                        selectedOption.remove();

                        // Remove config from cache
                        delete self.columnConfigs[configID];
                    },
                    'always': function() {
                        throbber.hide();
                    },
                });
            }
        },

        /**
         * Toggles the configuration manager between Select-mode and Save-mode
         *
         * @param {jQuery} container: the container
         * @param {boolean} on: switch to Save-mode (true), or Select-mode (false)
         */
        _toggleConfigSave: function(container, on) {

            const selectGroup = $('.cfg-select', container),
                  saveGroup = $('.cfg-save', container),
                  configOptions = $('.cfg-select-options', container),
                  nameInput = $('input.cfg-save-name', container);

            if (on) {
                // Get the selected config name
                let selectedOption = $('option:selected', configOptions),
                    configName = '',
                    nameLength = 0;
                if (configOptions.val()) {
                    configName = selectedOption.text().trim();
                    nameLength = configName.length * 2;
                }

                // Hide select group, show save group
                selectGroup.hide();
                saveGroup.removeClass('hide').show();

                // Populate name input, set focus and cursor
                nameInput.val(configName).focus();
                nameInput[0].setSelectionRange(nameLength, nameLength);
            } else {
                // Clear name input
                nameInput.val('');

                // Hide save group, show select group
                saveGroup.hide();
                selectGroup.removeClass('hide').show();
            }
        },

        /**
         * Saves the column arrangement from the dialog
         * - this can be both, create or update (by name match)
         * - called when Save-icon is clicked
         *
         * @param {jQuery} container - the container
         */
        _saveConfig: function(container) {

            // Get the Ajax URL
            const configsURL = this.configsURL;
            if (!configsURL) {
                return;
            }

            // Read+trim name from name input
            const nameInput = $('input.cfg-save-name', container),
                  configName = nameInput.val().trim();
            if (!configName) {
                return;
            }

            // Get the field selectors for the columns (ordered Array)
            const selected = [];
            $('.column-select:checked', container).each(function() {
                selected.push($(this).data('selector'));
            });
            if (!selected.length) {
                return;
            }

            // Submit to server
            const columnConfigs = this.columnConfigs,
                  configOptions = $('.cfg-select-options', container),
                  throbber = $('.cfg-select-throbber', container).show(),
                  data = {'name': configName, 'columns': selected},
                  self = this;
            $.ajaxS3({
                'url': configsURL,
                'type': 'POST',
                'data': JSON.stringify(data),
                'dataType': 'json',
                'retryLimit': 0,
                'success': function(data) {
                    // Update config selector and config cache
                    var configID = data.updated || data.created;
                    if (configID) {
                        columnConfigs[configID] = {
                            columns: selected,
                            id: configID,
                            name: configName
                        };
                        var selectedConfig = $('option[value="' + configID + '"]', configOptions);
                        if (selectedConfig.length) {
                            selectedConfig.prop('selected', true);
                        } else {
                            $('<option>').val(configID)
                                         .text(configName)
                                         .appendTo(configOptions)
                                         .prop('selected', true);
                        }
                        configOptions.val(configID);
                    }
                },
                'always': function() {
                    throbber.hide();
                    self._toggleConfigSave(container, false);
                },
            });
        },

        /**
         * Binds event handlers to dialog
         *
         * @param {jQuery.widget} dialog: the dialog instance
         * @param {jQuery} container: the container
         */
        _bindDialogEvents: function(dialog, container) {

            const ns = this.eventNamespace,
                  self = this;

            // Clicking outside of the popup closes it
            $('.ui-widget-overlay').off(ns).on('click' + ns, function() {
                dialog.dialog('close');
            });

            // Any cancel-form-btn button closes the popup
            $('.cancel-form-btn', container).off(ns).on('click' + ns, function() {
                dialog.dialog('close');
            });
            // Submit button applies the column arrangement and closes the dialog
            $('.submit-form-btn', container).off(ns).on('click' + ns, function() {
                if ($('.column-select:checked', container).length) {
                    self._applyColumnSelection(container);
                    dialog.dialog('close');
                }
            });
            // Reset button restores the default
            $('.reset-form-btn', container).off(ns).on('click' + ns, function() {
                self._applyColumnSelection(container, true);
            });

            // Alternative if drag&drop not available
            $('.column-left', container).off(ns).on('click' + ns, function() {
                $(this).closest('tr').insertBefore(row.prev());
            });
            $('.column-right', container).off(ns).on('click' + ns, function() {
                $(this).closest('tr').insertAfter(row.next());
            });

            // Select/deselect all
            $('.column-select-all', container).off(ns).on('change' + ns, function() {
                let status = $(this).prop('checked');
                $('.column-select', container).prop('checked', status);
            });
            $('.column-select', container).off(ns).on('change' + ns, function() {
                let deselected = $('.column-select:not(:checked)', container).length;
                $('.column-select-all', container).prop('checked', !deselected);
            });
        },

        /**
         * Binds event handlers to configuration manager elements
         *
         * @param {jQuery} container - the container
         */
        _bindConfigManagerEvents: function(container) {

            const ns = this.eventNamespace,
                  self = this;

            // Configuration selection
            $('.cfg-select-options', container).off(ns).on('change' + ns, function() {
                let configID = $(this).val();
                if (configID) {
                    self._loadConfig(container, configID - 0);
                }
            });
            $('.cfg-select-save', container).off(ns).on('click' + ns, function() {
                self._toggleConfigSave(container, true);
            });
            $('.cfg-select-delete', container).off(ns).on('click' + ns, function() {
                self._deleteConfig(container);
            });

            // Save-Group
            $('.cfg-save-name', container).off(ns).on('keyup' + ns, function(e) {
                e.preventDefault();
                e.stopPropagation();
                switch(e.which) {
                    case 13:
                        self._saveConfig(container);
                        break;
                    case 27:
                        self.toogleConfigSave(container, false);
                        break;
                    default:
                        break;
                }
            });
            $('.cfg-save-submit', container).off(ns).on('click' + ns, function() {
                self._saveConfig(container);
            });
            $('.cfg-save-cancel', container).off(ns).on('click' + ns, function() {
                self._toggleConfigSave(container, false);
            });
        },

        /**
         * Removes all event handlers from the dialog
         *
         * @param {jQuery} container: the container
         */
        _removeDialogEvents: function(container) {

            const ns = this.eventNamespace,
                  self = this;

            // Form events
            $('.ui-widget-overlay').off(ns);
            $('.cancel-form-btn, .submit-form-btn, .reset-form-button', container).off(ns);

            // Column selection/arrangement events
            $('.column-left, .column-right', container).off(ns);
            $('.column-select, .column-select-all', container).off(ns);

            // Configuration manager events
            $('.cfg-select-options, .cfg-select-save, .cfg-select-delete', container).off(ns);
            $('.cfg-save-name, .cfg-save-submit, .cfg-save-cancel', container).off(ns);
        },

        /**
         * Binds overall page events
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
         * Removes all added events
         */
        _unbindEvents: function() {

            const self = this,
                  ns = this.eventNamespace;

            self._removeDialogEvents($('.column-select-container'));

            $(this.element).off(ns);

            return true;
        },
    });
})(jQuery);
