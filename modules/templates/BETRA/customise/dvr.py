from gluon import current
from core import IS_IN_SET

# -----------------------------------------------------------------------------
def dvr_note_resource(r, tablename):
    T = current.T
    table = current.s3db.dvr_note

    # Make note type optional
    if "note_type_id" in table.fields:
        table.note_type_id.requires = None
        table.note_type_id.notnull = False
        table.note_type_id.label = T("Note Type (optional)")


def dvr_case_activity_resource(r, tablename):
    T = current.T
    s3db = current.s3db
    table = s3db.dvr_case_activity

    for fieldname in ("need_details", ""):
        if fieldname in table.fields:
            table[fieldname].readable = False
            table[fieldname].writable = False


def dvr_task_resource(r, tablename):
    T = current.T
    s3db = current.s3db
    table = s3db.dvr_task

    table.due_date.label = T("Report Date")




