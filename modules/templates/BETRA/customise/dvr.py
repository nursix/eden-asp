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


 # Change of label    
def dvr_note_type_resource(r, tablename):
    T = current.T
    table = current.s3db.dvr_note_type

    table.name.label = T("Nazwa")


    #removing fields
def dvr_case_activity_resource(r, tablename):
    T = current.T
    table = current.s3db.dvr_case_activity


    if "need_details" in table.fields:
        table.need_details.readable = True
        table.need_details.writable = True
        table.need_details.label = T("Comment") #how to change tha label bc I dont have idea? i tried different approaches and didnt make it


#change of label in task from due date to report date 
def dvr_task_resource(r, tablename):
    T = current.T
    s3db = current.s3db
    table = s3db.dvr_task

    table.due_date.label = T("Report Date")




