"""
    DOC module customisations for DIRECT

    License: MIT
"""

from gluon import current, IS_NOT_EMPTY

from core import represent_file

# -------------------------------------------------------------------------
def doc_image_resource(r, tablename):

    T = current.T

    s3db = current.s3db
    table = s3db.doc_image

    # Disable author-field
    field = table.person_id
    field.readable = field.writable = False

    # Hide URL field
    field = table.url
    field.readable = field.writable = False

    # Custom label for name-field, make mandatory
    field = table.name
    field.label = T("Title")
    field.requires = [IS_NOT_EMPTY(), field.requires]

    # Set default organisation_id
    doc_set_default_organisation(r, table=table)

# -------------------------------------------------------------------------
def document_onaccept(form):

    try:
        record_id = form.vars.id
    except AttributeError:
        return

    db = current.db
    #s3db = current.s3db

    table = db.doc_document
    row = db(table.id == record_id).select(table.id,
                                           table.name,
                                           table.file,
                                           limitby=(0, 1),
                                           ).first()
    if row and not row.name and row.file:
        # Use the original file name as title
        prop = table.file.retrieve_file_properties(row.file)
        name = prop.get("filename")
        if name:
            row.update_record(name=name)

# -------------------------------------------------------------------------
def doc_document_resource(r, tablename):

    s3db = current.s3db
    table = s3db.doc_document

    T = current.T

    s3 = current.response.s3

    if r.component_name == "template":
        #table.is_template.default = True
        s3.crud_strings["doc_document"].label_create = T("Add Document Template")
    else:
        #table.is_template.default = False
        s3.crud_strings["doc_document"].label_create = T("Add Document")

    # Custom label for date-field, default not writable
    field = table.date
    field.label = T("Uploaded on")
    field.writable = False

    # Hide URL field
    field = table.url
    field.readable = field.writable = False

    # Custom label for name-field, make mandatory
    field = table.name
    field.label = T("Title")
    field.requires = [IS_NOT_EMPTY(), field.requires]

    # Represent as symbol+size rather than file name
    field = table.file
    field.represent = represent_file()

    # Set default organisation_id
    doc_set_default_organisation(r, table=table)

    # List fields
    list_fields = ["name",
                   "file",
                   "date",
                   "comments",
                   ]
    s3db.configure("doc_document",
                   list_fields = list_fields,
                   )

    # Custom onaccept to make sure the document has a title
    s3db.add_custom_callback("doc_document",
                             "onaccept",
                             document_onaccept,
                             )

# -------------------------------------------------------------------------
def doc_document_controller(**attr):

    current.deployment_settings.ui.export_formats = None

    attr["dtargs"] = {"dt_text_maximum_len": 36,
                      "dt_text_condense_len": 36,
                      }

    return attr

# -------------------------------------------------------------------------
def doc_set_default_organisation(r, table=None):
    """
        Sets the correct default organisation_id for documents/images from
        the upload context (e.g. activity, shelter, organisation)

        Args:
            r - the current CRUDRequest
    """

    if table is None:
        table = current.s3db.doc_document

    organisation_id = None

    record = r.record
    if record:
        fields = {"act_activity": "organisation_id",
                  "cr_shelter": "organisation_id",
                  "org_organisation": "id",
                  }
        fieldname = fields.get(r.resource.tablename)
        if fieldname:
            organisation_id = record[fieldname]

    if organisation_id:
        table.organisation_id.default = organisation_id

# END =========================================================================
