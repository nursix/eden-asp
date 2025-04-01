from gluon import current
from core import IS_IN_SET

# Make note type optional and free to type yourself
def dvr_note_resource(r, tablename):
    T = current.T
    table = current.s3db.dvr_note

    
    if "note_type_id" in table.fields:
        table.note_type_id.requires = None
        table.note_type_id.notnull = False
        table.note_type_id.label = T("Note Type (optional)")


 # Change of label of note type from name and surname to name of note
def dvr_note_type_resource(r, tablename):
    T = current.T
    table = current.s3db.dvr_note_type

    table.name.label = T("Name of note")


#removing fields or changing labels (depends)
def dvr_case_activity_resource(r, tablename):
    T = current.T
    table = current.s3db.dvr_case_activity


    if "need_details" in table.fields:
        table.need_details.readable = False
        table.need_details.writable = False
        # table.need_details.label = T("Comment") --------> how to change tha label bc I dont have idea? i tried different approaches and didnt make it


#change of label in task from due date to report date 
def dvr_task_resource(r, tablename):
    T = current.T
    s3db = current.s3db
    table = s3db.dvr_task
    table.due_date.label = T("Report Date")




