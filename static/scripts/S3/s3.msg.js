/**
 * Used by the Compose function in Messaging (modules/core/msg)
 * This script is in Static to allow caching
 * Dynamic constants (e.g. Internationalised strings) are set in server-generated script
 */

/* Global vars */
//S3.msg = Object();

$(function() {
    var contact_method = $('#msg_outbox_contact_method');
    if (contact_method.val() != 'EMAIL') {
        // SMS don't have subjects
        $('#msg_log_subject__row').hide();
    }
    contact_method.on('change', function() {
        if ($(this).val() == 'EMAIL') {
            // Emails have a Subject
            $('#msg_log_subject__row').show();
        } else {
            $('#msg_log_subject__row').hide();
        }
    });
});
