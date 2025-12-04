"""
    DOC module customisations for RLPPTM

    License: MIT
"""

from gluon import current, IS_EMPTY_OR, IS_IN_SET

from core import get_form_record_id, WorkflowOptions

# -------------------------------------------------------------------------
# Status for uploaded documents
DOC_STATUS = WorkflowOptions(("NEW", "New", "lightblue"),
                             ("EVIDENCE", "Audit Evidence", "red"),
                             ("RELEASED", "Released", "lightgreen"),
                             selectable = ("NEW", "EVIDENCE", "RELEASED"),
                             represent = "status",
                             none = "NEW",
                             )

# -------------------------------------------------------------------------
def doc_document_resource(r, tablename):

    T = current.T

    db = current.db
    s3db = current.s3db
    table = s3db.doc_document

    # Custom label for date-field, default not writable
    field = table.date
    field.label = T("Uploaded on")
    field.writable = False

    # Hide URL field
    field = table.url
    field.readable = field.writable = False

    # Custom label for name-field
    field = table.name
    field.label = T("Title")

    # Set default organisation_id
    doc_set_default_organisation(r)

    # Add custom onaccept
    s3db.add_custom_callback("doc_document", "onaccept", doc_document_onaccept)
    s3db.add_custom_callback("doc_document", "ondelete", doc_document_ondelete)

    if r.controller == "org" or r.function == "organisation":

        # Configure status-field
        field = table.status
        if current.auth.s3_has_role("AUDITOR"):
            field.readable = field.writable = True
            field.requires = IS_IN_SET(DOC_STATUS.selectable(True),
                                       zero = None,
                                       sort = False,
                                       )
            field.represent = DOC_STATUS.represent
            status = "status"
        else:
            field.readable = field.writable = False
            status = None

        # Configure site_id-field
        if r.name == "organisation" and r.record and r.component_name == "document":

            if r.component_id:
                query = (table.id == r.component_id) & \
                        (table.deleted == False)
                row = db(query).select(table.doc_id, limitby=(0, 1)).first()
            else:
                row = None

            if row and row.doc_id:
                selectable = None
            else:
                ftable = s3db.org_facility
                query = (ftable.organisation_id == r.id) & \
                        (ftable.deleted == False)
                sites = db(query).select(ftable.site_id, ftable.name)
                selectable = {site.site_id: site.name for site in sites}

            field = table.site_id
            if selectable:
                field.readable = field.writable = True
                field.label = T("Facility")
                field.represent = s3db.org_SiteRepresent(show_type=False)
                field.requires = IS_EMPTY_OR(IS_IN_SET(selectable))
            else:
                field.readable = field.writable = False

        # List fields
        list_fields = ["name",
                       "file",
                       "date",
                       "site_id",
                       status,
                       "comments",
                       ]
        s3db.configure("doc_document",
                       list_fields = list_fields,
                       )

# -------------------------------------------------------------------------
def doc_document_onaccept(form):
    """
        Custom onaccept routine for documents:
            - alter ownership according to status
            - update document availability in the audit status of the org
    """

    record_id = get_form_record_id(form)
    if not record_id:
        return

    db = current.db
    s3db = current.s3db

    table = s3db.doc_document

    row = db(table.id == record_id).select(table.id,
                                           table.doc_id,
                                           table.organisation_id,
                                           table.site_id,
                                           table.status,
                                           table.created_by,
                                           table.owned_by_user,
                                           limitby = (0, 1),
                                           ).first()
    if row:
        update = {}

        # Alter ownership according to evidence status
        if row.status == "EVIDENCE":
            AUDITOR = current.auth.get_role_id("AUDITOR")
            update = {"owned_by_user": None,
                      "owned_by_group": AUDITOR,
                      }
        else:
            ORG_ADMIN = current.auth.get_system_roles().ORG_ADMIN
            if not row.owned_by_user:
                update["owned_by_user"] = table.created_by
            update["owned_by_group"] = ORG_ADMIN

        # If the document is super-linked to a facility,
        # use that facility for site_id (unconditionally)
        if row.doc_id:
            ftable = s3db.org_facility
            query = (ftable.doc_id == row.doc_id) & \
                    (ftable.deleted == False)
            facility = db(query).select(ftable.site_id,
                                        limitby = (0, 1),
                                        ).first()
            if facility:
                update["site_id"] = facility.site_id

        if update:
            row.update_record(**update)

        # Update the audit status of the organisation
        if row.organisation_id:
            from ..models.org import TestProvider
            TestProvider(row.organisation_id).update_audit_status()

# -------------------------------------------------------------------------
def doc_document_ondelete(row):
    """
        Custom ondelete routine for documents:
            - update document availability in the audit status of the org
    """

    if row.organisation_id:
        from ..models.org import TestProvider
        TestProvider(row.organisation_id).update_audit_status()

# -------------------------------------------------------------------------
def doc_set_default_organisation(r):
    """
        Sets the correct default organisation_id for doc_document from
        the upload context (e.g. organisation or facility)

        Args:
            r - the current CRUDRequest
    """

    table = current.s3db.doc_document

    organisation_id = None
    if r.controller == "org":
        record = r.record
        if record:
            if r.tablename == "org_organisation":
                organisation_id = record.id
            elif r.tablename == "org_facility":
                organisation_id = record.organisation_id

    if organisation_id:
        table.organisation_id.default = organisation_id

# END =========================================================================
