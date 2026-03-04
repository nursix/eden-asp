"""
    DOC module customisations for DRKCM

    License: MIT
"""

from gluon import current, IS_EMPTY_OR

from core import IS_ONE_OF

from ..uioptions import get_ui_options

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

    if r.controller == "dvr" or r.function == "organisation":

        T = current.T
        s3db = current.s3db

        table = s3db.doc_document

        # Hide URL field
        field = table.url
        field.readable = field.writable = False

        # Custom label for date-field
        field = table.date
        field.label = T("Date") #T("Uploaded on")
        field.default = r.utcnow.date()
        field.writable = False

        # Custom label for name-field
        field = table.name
        field.label = T("Title")

        # Custom Representation for file
        if r.interactive or r.representation == "aadata":
            from ..helpers import file_represent
            field = table.file
            field.represent = file_represent

        # List fields
        list_fields = ["date",
                       "name",
                       "file",
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

    T = current.T
    s3db = current.s3db
    s3 = current.response.s3

    current.deployment_settings.ui.export_formats = None

    if current.request.controller == "dvr":

        # Use custom rheader for case perspective
        from ..rheaders import dvr_rheader
        attr["rheader"] = dvr_rheader

        # Set contacts-method to retain the tab
        s3db.set_method("pr_person",
                        method = "contacts",
                        action = s3db.pr_Contacts,
                        )

        from .pr import configure_person_components
        configure_person_components()

    # Custom prep
    standard_prep = s3.prep
    def custom_prep(r):

        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True
        if not result:
            return False

        if r.controller == "dvr" and \
           (r.interactive or r.representation == "aadata"):

            from .pr import configure_person_tags

            configure_person_tags()

            table = r.table
            field = table.doc_id

            # Representation of doc entity
            ui_opts_get = get_ui_options().get
            subject_type = ui_opts_get("activity_subject_type")
            if subject_type in ("need", "both"):
                use_need = True
                activity_label = T("Counseling Reason")
            else:
                use_need = False
                activity_label = None
            field.represent = s3db.dvr_DocEntityRepresent(
                                    show_link = True,
                                    use_sector = ui_opts_get("activity_use_sector"),
                                    use_need = use_need,
                                    use_subject = subject_type in ("subject", "both"),
                                    case_group_label = T("Family"),
                                    activity_label = activity_label,
                                    )

            # Also update requires with this represent
            # => retain viewing-filters from standard prep
            requires = field.requires
            if isinstance(requires, IS_EMPTY_OR):
                requires = requires.other
            if hasattr(requires, "filterby"):
                filterby = requires.filterby
                filter_opts = requires.filter_opts
            else:
                filterby = filter_opts = None
            field.requires = IS_ONE_OF(current.db, "doc_entity.doc_id",
                                       field.represent,
                                       filterby = filterby,
                                       filter_opts = filter_opts,
                                       orderby = "instance_type",
                                       sort = False,
                                       )

            r.resource.configure(list_fields = ["id",
                                                "date",
                                                (T("Attachment of"), "doc_id"),
                                                "name",
                                                "file",
                                                "comments",
                                                ],
                                 orderby = "doc_document.date desc",
                                 )
        return result
    s3.prep = custom_prep

    attr["dtargs"] = {"dt_text_maximum_len": 36,
                      "dt_text_condense_len": 36,
                      }

    return attr

# END =========================================================================
