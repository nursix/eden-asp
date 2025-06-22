/**
 * Form control script for MED module
 *
 * @copyright 2025 (c) Sahana Software Foundation
 * @license MIT
 */
(function($, undefined) {

    "use strict";

    // Event name space
    const ns = '.med';

    /**
     * Toggles visibility of form rows
     *
     * @param {string} tableName: the table name
     * @param {Array} fieldNames: array of field names to toggle
     * @param {boolean} on: whether to show (true) or hide (false, default) the rows
     */
    var toggleRows = function(tableName, fieldNames, on) {

        fieldNames.forEach(function(fieldName) {
            let rowID = '#' + tableName + '_' + fieldName + '__row';
            if (on) {
                $(rowID).removeClass('hide').show();
                $(rowID + '1').removeClass('hide').show();
            } else {
                $(rowID).hide();
                $(rowID + '1').hide();
            }
        });
    };

    // ------------------------------------------------------------------------
    // DOCUMENT-READY

    // Actions when document ready
    $(function() {

        // If this is a patient form that contains an unregistered-Checkbox,
        // toggle "person" field dependent on the checkbox' status
        let unregisteredCheckbox = $('input#med_patient_unregistered[type="checkbox"]');
        if (unregisteredCheckbox.length) {
            unregisteredCheckbox.off(ns).on('change' + ns, function() {
                toggleRows("med_patient", ["person"], unregisteredCheckbox.prop('checked'));
            });
            toggleRows("med_patient", ["person"], unregisteredCheckbox.prop('checked'));
        }
    });

    // END --------------------------------------------------------------------

})(jQuery);
