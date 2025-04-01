"""
    DVR module customisations for BETRA

    License: MIT
"""

from gluon import current
from core import IS_IN_SET

# Remove Note Type field in note adding form 
def dvr_note_resource(r, tablename):
    T = current.T
    table = current.s3db.dvr_note
 
    if "note_type_id" in table.fields:
     table.note_type_id.readable = False
     table.note_type_id.writable = False
     


"""
Change of label of note type from name and surname to name of note (for future use if TRATWA will want this functionality ) 
def dvr_note_type_resource(r, tablename):
    T = current.T
    table = current.s3db.dvr_note_type
    table.name.label = T("Name of Note Type")
    table.name.requires = True
"""   


#Removing Initial Situation Details from need adding form
def dvr_case_activity_resource(r, tablename):
    T = current.T
    table = current.s3db.dvr_case_activity


    if "need_details" in table.fields:
        table.need_details.readable = False
        table.need_details.writable = False

    #TODO remove Counseling nad Progress fields


def dvr_task_resource(r, tablename):
    T = current.T
    s3db = current.s3db
    table = s3db.dvr_task
    field = table.date

#Removing Due Date field from task form
    table.due_date.readbale = False
    table.due_date.writable = False

#Adding Report Date field to the form 
    field.label = T("Report Date")
    field.readable = True
    field.writable = True







