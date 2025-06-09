"""
    DOC module customisations for MRCMS

    License: MIT
"""

from gluon import current, IS_NOT_EMPTY

from core import represent_file, GenerateDocument, IS_ONE_OF, FS

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
def doc_customise_documents(r, table):

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

# -------------------------------------------------------------------------
def doc_document_resource(r, tablename):

    s3db = current.s3db
    table = s3db.doc_document

    doc_customise_documents(r, table)

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
def dvr_document_prep(r):

    T = current.T

    db = current.db
    s3db = current.s3db
    auth = current.auth

    settings = current.deployment_settings

    table = r.table

    viewing = r.viewing
    if viewing:
        vtablename, record_id = viewing
    else:
        return False

    ctable = s3db.dvr_case
    has_permission = auth.s3_has_permission
    accessible_query = auth.s3_accessible_query

    if vtablename == "pr_person":
        if not has_permission("read", "pr_person", record_id):
            r.unauthorised()
        include_activity_docs = settings.get_dvr_case_include_activity_docs()
        include_group_docs = settings.get_dvr_case_include_group_docs()
        query = accessible_query("read", ctable) & \
                (ctable.person_id == record_id) & \
                (ctable.deleted == False)

    elif vtablename == "dvr_case":
        include_activity_docs = False
        include_group_docs = False
        query = accessible_query("read", ctable) & \
                (ctable.id == record_id) & \
                (ctable.deleted == False)
    else:
        # Unsupported
        return False

    # Get the case doc_id
    doc_ids = []
    case = db(query).select(ctable.doc_id,
                            ctable.organisation_id,
                            limitby = (0, 1),
                            orderby = ~ctable.modified_on,
                            ).first()
    if not case:
        # No case found
        r.error(404, "Case not found")
    elif case.doc_id:
        doc_ids.append(case.doc_id)

    # Set default organisation_id to case org
    table.organisation_id.default = case.organisation_id

    # Include case groups
    if include_group_docs:

        # Look up relevant case groups
        mtable = s3db.pr_group_membership
        gtable = s3db.pr_group
        join = gtable.on((gtable.id == mtable.group_id) & \
                         (gtable.group_type == 7))
        query = accessible_query("read", mtable) & \
                (mtable.person_id == record_id) & \
                (mtable.deleted == False)
        rows = db(query).select(gtable.doc_id,
                                join = join,
                                orderby = ~mtable.created_on,
                                )

        # Append the doc_ids
        for row in rows:
            if row.doc_id:
                doc_ids.append(row.doc_id)

    # Include case activities
    # - to be able to limit access to activity attachments, they must be accessed
    #   through counsel-controller (and thus, user must have counsel controller permission)
    if include_activity_docs and r.controller == "counsel":

        # Look up relevant case activities
        atable = s3db.dvr_case_activity
        query = accessible_query("read", atable) & \
                (atable.person_id == record_id) & \
                (atable.deleted == False)
        rows = db(query).select(atable.doc_id,
                                orderby = ~atable.created_on,
                                )

        # Append the doc_ids
        for row in rows:
            if row.doc_id:
                doc_ids.append(row.doc_id)

    field = r.table.doc_id
    if include_activity_docs or include_group_docs:

        # Representation of doc_id
        subject_type = settings.get_dvr_case_activity_subject_type()
        field.represent = s3db.dvr_DocEntityRepresent(
                                show_link = True,
                                use_sector = False,
                                use_need = subject_type in ("need", "both"),
                                use_subject = subject_type in ("subject", "both"),
                                case_group_label = T("Family"),
                                activity_label = T("Need"),
                                linkto_controller = r.controller,
                                )

        # Make doc_id readable and visible in table
        field.label = T("Attachment of")
        field.readable = True
        s3db.configure("doc_document",
                        list_fields = ["id",
                                       "date",
                                       (T("Attachment of"), "doc_id"),
                                       "name",
                                       "file",
                                       "comments",
                                       ],
                        orderby = "doc_document.date desc",
                        )

    # Apply filter and defaults
    if len(doc_ids) == 1:
        # Single doc_id => set default, hide field
        doc_id = doc_ids[0]
        field.default = doc_id
        r.resource.add_filter(FS("doc_id") == doc_id)
    else:
        # Multiple doc_ids => default to case, make selectable
        field.default = doc_ids[0]
        field.readable = field.writable = True
        field.requires = IS_ONE_OF(db, "doc_entity.doc_id",
                                   field.represent,
                                   filterby = "doc_id",
                                   filter_opts = doc_ids,
                                   orderby = "instance_type",
                                   sort = False,
                                   )
        r.resource.add_filter(FS("doc_id").belongs(doc_ids))

    return True

# -------------------------------------------------------------------------
def doc_document_controller(**attr):

    s3db = current.s3db
    s3 = current.response.s3

    current.deployment_settings.ui.export_formats = None

    if current.request.controller in ("dvr", "counsel", "med"):

        # Use custom rheader for case perspective
        from ..rheaders import dvr_rheader
        attr["rheader"] = dvr_rheader

        # Set contacts-method to retain the tab
        s3db.set_method("pr_person",
                        method = "contacts",
                        action = s3db.pr_Contacts,
                        )

        from .pr import configure_person_tags
        configure_person_tags()

    # Custom prep
    standard_prep = s3.prep
    def custom_prep(r):
        if r.controller in ("dvr", "counsel"):
            result = dvr_document_prep(r)
        else:
            # Call standard prep
            result = standard_prep(r) if callable(standard_prep) else True
        return result
    s3.prep = custom_prep

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

# -------------------------------------------------------------------------
class GenerateCaseDocument(GenerateDocument):
    """
        Custom version of GenerateDocument that uses the case organisation
        rather than the user organisation for template lookup
    """

    @staticmethod
    def template_query(r):

        person = r.record

        if r.tablename != "pr_person" or not person:
            return super().template_query(r)

        s3db = current.s3db

        # Look up the case organisation
        organisation_id = s3db.dvr_case_organisation(person.id)

        table = s3db.doc_document
        query = (table.organisation_id == organisation_id) & \
                (table.is_template == True) & \
                (table.deleted == False)

        return query

# END =========================================================================
