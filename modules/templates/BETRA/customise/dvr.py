"""
    DVR module customisations for BETRA

    License: MIT
"""

from gluon import current

# -----------------------------------------------------------------------------
def dvr_note_resource(r, tablename):

    table = current.s3db.dvr_note

    # Remove Note Type field in note adding form
    if "note_type_id" in table.fields:
        table.note_type_id.readable = False
        table.note_type_id.writable = False

# -----------------------------------------------------------------------------
#def dvr_note_type_resource(r, tablename):
#
#    T = current.T
#
#    # Change of label of note type from name to name of note
#    # - for future use if TRATWA will want this functionality
#    table = current.s3db.dvr_note_type
#    table.name.label = T("Name of Note Type")

# -----------------------------------------------------------------------------
# def dvr_case_activity_resource(r, tablename):

    # T = current.T

    # table = current.s3db.dvr_case_activity

    # Removing Initial Situation Details from need adding form
    # - done in config.py using module options (settings.dvr.*)
    # field = table.need_details
    # field.readable = field.writable = False

    # Remove Counseling and Progress fields
    # - done in config.py using module options (settings.dvr.*)

# -----------------------------------------------------------------------------
def dvr_task_resource(r, tablename):

    T = current.T
    s3db = current.s3db

    table = s3db.dvr_task

    # Removing Due Date field from task form
    field = table.due_date
    field.readable = field.writable = False

    # Adding Report Date field to the form
    field = table.date
    field.label = T("Report Date")
    field.readable = field.writable = True

# END =========================================================================
