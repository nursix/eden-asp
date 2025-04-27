"""
    RLPPTM Test Station Management Extensions

    Copyright: 2022 (c) AHSS

    Permission is hereby granted, free of charge, to any person
    obtaining a copy of this software and associated documentation
    files (the "Software"), to deal in the Software without
    restriction, including without limitation the rights to use,
    copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the
    Software is furnished to do so, subject to the following
    conditions:

    The above copyright notice and this permission notice shall be
    included in all copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
    EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
    OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
    NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
    HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
    WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
    FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
    OTHER DEALINGS IN THE SOFTWARE.
"""

__all__ = ("TestProviderRequirementsModel",
           "TestProviderModel",
           "TestProviderRepresentativeModel",
           "TestStationModel"
           )

import datetime
import os

from gluon import current, Field, URL, IS_EMPTY_OR, IS_IN_SET, DIV
from gluon.storage import Storage

from core import BooleanRepresent, DataModel, DateField, WorkflowOptions, S3Duplicate, \
                 get_form_record_id, represent_file, represent_option, \
                 DateTimeField, CommentsField, s3_comments_widget, \
                 s3_str, s3_text_represent

from ..helpers import PersonRepresentDetails

DEFAULT = lambda: None

# =============================================================================
# Status and Reason Options
#
# Org requirements and approval status
ORG_RQM = WorkflowOptions(("N/A", "not specified", "grey"),
                          ("REVISE", "Completion/Adjustment Required", "red"),
                          ("REVIEW", "Review Pending", "amber"),
                          ("VERIFIED", "verified", "green"),
                          ("ACCEPT", "not required", "green"),
                          selectable = ("REVISE", "VERIFIED"),
                          none = "REVISE",
                          )

VERIFICATION_STATUS = WorkflowOptions(("REVISE", "Completion/Adjustment Required", "red"),
                                      ("READY", "Ready for Review", "amber"),
                                      ("REVIEW", "Review Pending", "amber"),
                                      ("COMPLETE", "complete", "green"),
                                      selectable = ("READY",),
                                      none = "REVISE",
                                      )

# Representative documentation status
DOCUMENTATION_STATUS = WorkflowOptions(("N/A", "not provided", "grey"),
                                       ("REVIEW", "Review Pending", "amber"),
                                       ("APPROVED", "provided / appropriate", "green"),
                                       ("REJECTED", "not up to requirements", "red"),
                                       none = "N/A",
                                       )

# Commission status and reasons
COMMISSION_STATUS = WorkflowOptions(("CURRENT", "current", "green"),
                                    ("SUSPENDED", "suspended", "amber"),
                                    ("REVOKED", "revoked", "black"),
                                    ("EXPIRED", "expired", "grey"),
                                    selectable = ("CURRENT", "SUSPENDED", "REVOKED"),
                                    represent = "status",
                                    )
COMMISSION_REASON = WorkflowOptions(("N/V", "Documentation/Verification incomplete"),
                                    ("OVERRIDE", "set by Administrator"),
                                    selectable = ("OVERRIDE",),
                                    )

# Site requirements and approval status
SITE_RQM = WorkflowOptions(("REVISE", "Completion/Adjustment Required", "red"),
                           ("REVIEW", "Review Pending", "amber"),
                           ("APPROVED", "Approved##actionable", "green"),
                           none = "REVISE",
                           )

APPROVAL_STATUS = WorkflowOptions(("REVISE", "Completion/Adjustment Required", "red"),
                                  ("READY", "Ready for Review", "amber"),
                                  ("REVIEW", "Review Pending", "amber"),
                                  ("APPROVED", "Approved##actionable", "green"),
                                  selectable = ("REVISE", "READY"),
                                  none = "REVISE",
                                  )

# Public-status and reasons
PUBLIC_STATUS = WorkflowOptions(("N", "No", "grey"),
                                ("Y", "Yes", "green"),
                                )
PUBLIC_REASON = WorkflowOptions(("COMMISSION", "Provider not currently commissioned"),
                                ("SUSPENDED", "Commission suspended"),
                                ("REVISE", "Documentation incomplete"),
                                ("REVIEW", "Review pending"),
                                ("OVERRIDE", "set by Administrator"),
                                selectable = ("OVERRIDE",),
                                )

# Audit evidence status
EVIDENCE_STATUS = WorkflowOptions(("N/R", "Not Required", "grey"),
                                  ("REQUIRED", "Required", "lightblue"),
                                  ("REQUESTED", "Requested##demand", "amber"),
                                  ("COMPLETE", "Complete", "green"),
                                  represent = "status",
                                  )

# =============================================================================
class TestProviderRequirementsModel(DataModel):
    """
        Approval characteristics/requirements for types of test providers
    """

    names = ("org_requirements",
             )

    def model(self):

        T = current.T

        flag_represent = BooleanRepresent(icons=True, flag=True)

        # ---------------------------------------------------------------------
        # Requirements
        #
        tablename = "org_requirements"
        self.define_table(tablename,
                          self.org_organisation_type_id(),
                          Field("commercial", "boolean",
                                label = T("Commercial Providers"),
                                default = False,
                                represent = flag_represent,
                                ),
                          Field("natpersn", "boolean",
                                label = T("Natural Persons"),
                                default = False,
                                represent = flag_represent,
                                ),
                          Field("verifreq", "boolean",
                                label = T("Organization Type verification required"),
                                default = False,
                                represent = flag_represent,
                                ),
                          Field("mpavreq", "boolean",
                                label = T("MPAV Qualification verification required"),
                                default = True,
                                represent = flag_represent,
                                ),
                          Field("rinforeq", "boolean",
                                label = T("Representative Information required"),
                                default = False,
                                represent = flag_represent,
                                ),
                          )

        # Table configuration
        self.configure(tablename,
                       deduplicate = S3Duplicate(primary=("organisation_type_id",),
                                                 ),
                       )

# =============================================================================
class TestProviderModel(DataModel):
    """
        Data model extensions for test provider verification and commissioning
    """

    names = ("org_verification",
             "org_commission",
             "org_audit",
             "org_bsnr",
             )

    def model(self):

        T = current.T

        organisation_id = self.org_organisation_id

        configure = self.configure
        define_table = self.define_table

        crud_strings = current.response.s3.crud_strings

        # ---------------------------------------------------------------------
        # Verification details
        #
        tablename = "org_verification"
        define_table(tablename,
                     organisation_id(),
                     # Hidden data hash to detect relevant changes
                     Field("dhash",
                           readable = False,
                           writable = False,
                           ),
                     # Workflow status
                     Field("status",
                           label = T("Processing Status"),
                           default = "REVISE",
                           requires = IS_IN_SET(VERIFICATION_STATUS.selectable(True),
                                                zero = None,
                                                sort = False,
                                                ),
                           represent = VERIFICATION_STATUS.represent,
                           readable = True,
                           writable = False,
                           ),
                     # Whether organisation type is verified
                     Field("orgtype",
                           label = T("Organization Type verification"),
                           default = "N/A",
                           requires = IS_IN_SET(ORG_RQM.selectable(True),
                                                sort = False,
                                                zero = None,
                                                ),
                           represent = ORG_RQM.represent,
                           readable = True,
                           writable = False,
                           ),
                     # Whether organisation is qualified for MPAV
                     Field("mpav",
                           label = T("MPAV Qualification verification"),
                           default = "N/A",
                           requires = IS_IN_SET(ORG_RQM.selectable(True),
                                                sort = False,
                                                zero = None,
                                                ),
                           represent = ORG_RQM.represent,
                           readable = True,
                           writable = False,
                           ),
                     # Whether representative documentation is complete and verified
                     Field("reprinfo",
                           label = T("Representatives Documentation"),
                           default = "N/A",
                           requires = IS_IN_SET(ORG_RQM.selectable(),
                                                sort = False,
                                                zero = None,
                                                ),
                           represent = ORG_RQM.represent,
                           readable = True,
                           writable = False,
                           ),
                     )

        # ---------------------------------------------------------------------
        # Commission
        #
        folder = current.request.folder
        tablename = "org_commission"
        define_table(tablename,
                     organisation_id(empty=False),
                     DateField("date",
                               default = "now",
                               past = 0,
                               set_min = "#org_commission_end_date",
                               ),
                     DateField("end_date",
                               label = T("Valid until"),
                               default = None,
                               set_max="#org_commission_date",
                               ),
                     Field("status",
                           label = T("Status"),
                           default = "CURRENT",
                           requires = IS_IN_SET(COMMISSION_STATUS.selectable(True),
                                                zero = None,
                                                sort = False,
                                                ),
                           represent = COMMISSION_STATUS.represent,
                           readable = True,
                           writable = False,
                           ),
                     Field("prev_status",
                           readable = False,
                           writable = False,
                           ),
                     DateField("status_date",
                               label = T("Status updated on"),
                               writable = False,
                               ),
                     Field("status_reason",
                           label = T("Status Reason"),
                           requires = IS_EMPTY_OR(
                                        IS_IN_SET(COMMISSION_REASON.selectable(True),
                                                  sort = False,
                                                  )),
                           represent = represent_option(dict(COMMISSION_REASON.labels())),
                           ),
                     Field("cnote", "upload",
                           label = T("Commissioning Note"),
                           uploadfolder = os.path.join(folder, "uploads", "commissions"),
                           represent = represent_file("org_commission", "cnote"),
                           writable = False,
                           ),
                     Field("vhash",
                           readable = False,
                           writable = False,
                           ),
                     CommentsField(),
                     )

        # Table configuration
        configure(tablename,
                  insertable = False,
                  editable = False,
                  deletable = False,
                  onvalidation = self.commission_onvalidation,
                  onaccept = self.commission_onaccept,
                  orderby = "%s.date desc" % tablename,
                  )

        # CRUD strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Commission"),
            title_display = T("Commission Details"),
            title_list = T("Commissions"),
            title_update = T("Edit Commission"),
            label_list_button = T("List Commissions"),
            label_delete_button = T("Delete Commission"),
            msg_record_created = T("Commission added"),
            msg_record_modified = T("Commission updated"),
            msg_record_deleted = T("Commission deleted"),
            msg_list_empty = T("No Commissions currently registered"),
            )

        # ---------------------------------------------------------------------
        # Audit
        #
        tablename = "org_audit"
        define_table(tablename,
                     organisation_id(empty=False),
                     Field("evidence_status",
                           label = T("Evidence"),
                           default = "N/R",
                           requires = IS_IN_SET(EVIDENCE_STATUS.selectable(),
                                                zero = None,
                                                sort = False,
                                                ),
                           represent = EVIDENCE_STATUS.represent,
                           ),
                     DateField("evidence_due_date",
                               label = T("Evidence requested by"),
                               ),
                     DateField("evidence_complete_date",
                               label = T("Evidence complete since"),
                               # Set automatically onaccept:
                               writable = False,
                               ),
                     Field("docs_available", "boolean",
                           default = False,
                           label = T("New Documents Available"),
                           writable = False,
                           represent = BooleanRepresent(icons = True,
                                                        colors = True,
                                                        ),
                           ),
                     CommentsField(),
                     )

        configure(tablename,
                  onvalidation = self.audit_onvalidation,
                  onaccept = self.audit_onaccept,
                  )

        # ---------------------------------------------------------------------
        # BSNR
        #
        tablename = "org_bsnr"
        define_table(tablename,
                     organisation_id(empty=False),
                     Field("bsnr",
                           label = T("BSNR"),
                           writable = False,
                           ),
                     Field("taxid",
                           label = T("Tax ID"),
                           writable = False,
                           ),
                     )

        # Table configuration
        configure(tablename,
                  deduplicate = S3Duplicate(primary = ("organisation_id",
                                                       "bsnr",
                                                       ),
                                            ),
                  )

    #--------------------------------------------------------------------------
    @staticmethod
    def commission_onvalidation(form):
        """
            Onvalidation of commission form:
                - make sure end date is after start date
                - prevent overlapping commissions
                - validate status
                - require reason for SUSPENDED-status
        """

        T = current.T
        db = current.db
        s3db = current.s3db

        record_id = get_form_record_id(form)
        ctable = s3db.org_commission

        # Get record data
        form_vars = form.vars
        data = {}
        load = []
        for fn in ("organisation_id", "date", "end_date", "status"):
            if fn in form_vars:
                data[fn] = form_vars[fn]
            else:
                data[fn] = ctable[fn].default
                load.append(fn)
        if load and record_id:
            record = db(ctable.id == record_id).select(*load, limitby=(0, 1)).first()
            for fn in load:
                data[fn] = record[fn]

        organisation_id = data["organisation_id"]
        start = data["date"]
        end = data["end_date"]
        status = data["status"]

        if "end_date" in form_vars:
            # End date must be after start date
            if start and end and end < start:
                form.errors["end_date"] = T("End date must be after start date")
                return

        active_statuses = ("CURRENT", "SUSPENDED")

        if status in active_statuses:
            # Prevent overlapping active commissions
            query = (ctable.status.belongs(active_statuses)) & \
                    (ctable.organisation_id == organisation_id) & \
                    ((ctable.end_date == None) | (ctable.end_date >= start))
            if record_id:
                query = (ctable.id != record_id) & query
            if end:
                query &= (ctable.date <= end)
            query &= (ctable.deleted == False)
            row = db(query).select(ctable.id, limitby=(0, 1)).first()
            if row:
                error = T("Date interval overlaps existing commission")
                if "date" in form_vars:
                    form.errors["date"] = error
                if "end_date" in form_vars:
                    form.errors["end_date"] = error
                if "date" not in form_vars and "end_date" not in form_vars:
                    form.errors["status"] = error
                return

        if "status" in form_vars:
            # CURRENT only allowed when org verification valid
            if status == "CURRENT" and \
               not TestProvider(organisation_id).verified:
                form.errors["status"] = T("Organization not verified")

            # CURRENT/SUSPENDED only allowed before end date
            today = current.request.utcnow.date()
            if end and end < today and status in active_statuses:
                form.errors["status"] = T("Invalid status past end date")
                return

            # SUSPENDED requires a reason
            reason = form_vars.get("status_reason") or ""
            if status == "SUSPENDED" and "status_reason" in form_vars and len(reason.strip()) < 3:
                form.errors["status_reason"] = T("Reason required for suspended-status")
                return

            # SUSPENDED with reason OVERRIDE requires comments
            comments = form_vars.get("comments") if "comments" in form_vars else True
            if status == "SUSPENDED" and reason == "OVERRIDE" and not comments:
                form.errors["comments"] = T("More details required")

    #--------------------------------------------------------------------------
    @staticmethod
    def commission_onaccept(form):
        """
            Onaccept of commission form
                - set status EXPIRED when end date is past
                - set status SUSPENDED when provider not verified
                + when status changed:
                    - set status date and prev_status
                    - trigger facility approval updates
                    - notify commission change
        """

        record_id = get_form_record_id(form)
        if not record_id:
            return

        db = current.db
        s3db = current.s3db

        table = s3db.org_commission
        record = db(table.id == record_id).select(table.id,
                                                  table.organisation_id,
                                                  table.end_date,
                                                  table.prev_status,
                                                  table.status,
                                                  table.status_reason,
                                                  table.cnote,
                                                  table.vhash,
                                                  limitby = (0, 1),
                                                  ).first()
        if not record:
            return

        provider = TestProvider(record.organisation_id)
        today = current.request.utcnow.date()

        update = {}
        if provider.verified:
            if record.end_date and record.end_date < today:
                update["status"] = "EXPIRED"
                update["status_reason"] = None
        elif record.status == "CURRENT":
            update["status"] = "SUSPENDED"
            update["status_reason"] = "N/V"
        if record.status in ("CURRENT", "REVOKED", "EXPIRED"):
            update["status_reason"] = None

        new_status = update.get("status") or record.status
        status_change = new_status != record.prev_status

        if status_change:
            update["status_date"] = today
            update["prev_status"] = new_status

        if update:
            record.update_record(**update)

        # Issue commissioning note
        if record.status == "CURRENT" and not record.vhash:
            from ..commission import ProviderCommission
            ProviderCommission(record.id).issue_note()

        if status_change:
            # Deactivate/reactivate all test stations
            if new_status == "CURRENT":
                public = "Y"
                reason = ("SUSPENDED", "COMMISSION")
            else:
                public = "N"
                reason = "SUSPENDED" if new_status == "SUSPENDED" else "COMMISSION"
            TestStation.update_all(record.organisation_id,
                                   public = public,
                                   reason = reason,
                                   )
            # Notify the provider
            T = current.T
            msg = provider.notify_commission_change(status = new_status,
                                                    reason = record.status_reason,
                                                    commission_ids = [record_id],
                                                    )
            if msg:
                current.response.warning = \
                    T("Test station could not be notified: %(error)s") % {"error": msg}
            else:
                current.response.information = \
                    T("Test station notified")

    #--------------------------------------------------------------------------
    @staticmethod
    def audit_onvalidation(form):
        """
            Onvalidation of org_audit:
                - make sure the evidence due date is recorded when evidence
                  has been requested
        """

        form_vars = form.vars

        evidence_status = form_vars.get("evidence_status")
        due_date = "evidence_due_date"

        if evidence_status == "REQUESTED" and \
           due_date in form_vars and not form_vars[due_date]:
            form.errors[due_date] = current.T("input required")

    #--------------------------------------------------------------------------
    @staticmethod
    def audit_onaccept(form):
        """
            Onaccept of org_audit:
                - set complete-date when evidence is marked as complete
                - remove complete-date when evidence is not marked as complete
                - remove due-date when no more evidence is pending
        """

        record_id = get_form_record_id(form)
        if not record_id:
            return

        db = current.db
        s3db = current.s3db

        table = s3db.org_audit
        record = db(table.id == record_id).select(table.id,
                                                  table.organisation_id,
                                                  table.evidence_status,
                                                  table.evidence_due_date,
                                                  table.evidence_complete_date,
                                                  limitby = (0, 1),
                                                  ).first()
        if not record:
            return

        update = {}
        today = current.request.utcnow.date()

        if record.evidence_status == "COMPLETE":
            if not record.evidence_complete_date:
                update["evidence_complete_date"] = today
        elif record.evidence_complete_date:
            update["evidence_complete_date"] = None

        if record.evidence_status != "REQUESTED" and \
           record.evidence_due_date:
            update["evidence_due_date"] = None

        if update:
            record.update_record(**update)

        if record.organisation_id:
            TestProvider(record.organisation_id).update_audit_status()

# =============================================================================
class TestProviderRepresentativeModel(DataModel):
    """
        Data model extensions for representative vetting/approval workflow
    """

    names = ("org_representative",
             )

    def model(self):

        T = current.T

        crud_strings = current.response.s3.crud_strings

        flag_represent = BooleanRepresent(labels = (T("complete"), T("incomplete")),
                                          icons = True,
                                          colors = True,
                                          )

        # ---------------------------------------------------------------------
        # Representative
        #
        tablename = "org_representative"
        self.define_table(tablename,
                          self.pr_person_id(
                              represent = PersonRepresentDetails(show_email = True,
                                                                 show_phone = True,
                                                                 show_link = False,
                                                                 styleable = True,
                                                                 ),
                              comment = None,
                              readable = False,
                              writable = False,
                              ),
                          self.org_organisation_id(
                              comment = None,
                              readable = False,
                              writable = False,
                              ),
                          self.super_link("doc_id", "doc_entity"),

                          Field("active", "boolean",
                                label = T("Active"),
                                default = False,
                                represent = BooleanRepresent(icons=True),
                                writable = False,
                                ),
                          DateField(label = T("Start Date"),
                                    writable = False,
                                    ),
                          DateField("end_date",
                                    label = T("End Date"),
                                    writable = False,
                                    ),

                          # Hidden data hash to detect relevant changes
                          Field("dhash",
                                readable = False,
                                writable = False,
                                ),
                          Field("status",
                                label = T("Processing Status"),
                                default = "REVISE",
                                requires = IS_IN_SET(APPROVAL_STATUS.selectable(True),
                                                     zero = None,
                                                     sort = False,
                                                     ),
                                represent = APPROVAL_STATUS.represent,
                                readable = True,
                                writable = False,
                                ),

                          Field("person_data", "boolean",
                                label = T("Person Details"),
                                default = False,
                                represent = flag_represent,
                                writable = False,
                                ),
                          Field("contact_data", "boolean",
                                label = T("Contact Information"),
                                default = False,
                                represent = flag_represent,
                                writable = False,
                                ),
                          Field("address_data", "boolean",
                                label = T("Address"),
                                default = False,
                                represent = flag_represent,
                                writable = False,
                                ),
                          Field("user_account", "boolean",
                                label = T("User Account"),
                                default = False,
                                represent = flag_represent,
                                readable = False,
                                writable = False,
                                ),

                          Field("regform",
                                label = T("Signed form for registration"),
                                requires = IS_IN_SET(DOCUMENTATION_STATUS.selectable(True),
                                                     zero = None,
                                                     sort = False,
                                                     ),
                                represent = DOCUMENTATION_STATUS.represent,
                                readable = True,
                                writable = False,
                                ),
                          Field("crc",
                                label = T("Criminal Record Certificate"),
                                requires = IS_IN_SET(DOCUMENTATION_STATUS.selectable(True),
                                                     zero = None,
                                                     sort = False,
                                                     ),
                                represent = DOCUMENTATION_STATUS.represent,
                                readable = True,
                                writable = False,
                                ),
                          Field("scp",
                                label = T("Statement on Pending Criminal Proceedings"),
                                requires = IS_IN_SET(DOCUMENTATION_STATUS.selectable(True),
                                                     zero = None,
                                                     sort = False,
                                                     ),
                                represent = DOCUMENTATION_STATUS.represent,
                                readable = True,
                                writable = False,
                                ),
                          CommentsField(
                              label = T("Advice"),
                              writable = False,
                              comment = None,
                              ),
                          )

        # Table configuration
        self.configure(tablename,
                       insertable = False,
                       deletable = False,
                       onaccept = self.representative_onaccept,
                       super_entity = "doc_entity",
                       )

        # CRUD strings
        crud_strings[tablename] = Storage(
            title_display = T("Representative Details"),
            title_list = T("Representatives"),
            title_update = T("Edit Verification Details"),
            label_list_button = T("List Representatives"),
            msg_record_modified = T("Verification updated"),
            )

        # ---------------------------------------------------------------------
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def representative_onaccept(form):
        """
            Onaccept of representative
                - update verification status
        """

        record_id = get_form_record_id(form)
        if not record_id:
            return

        info, warn = ProviderRepresentative(record_id).update_verification()
        if current.auth.s3_has_role("ORG_GROUP_ADMIN"):
            if info:
                current.response.information = info
            if warn:
                current.response.warning = warn

# =============================================================================
class TestStationModel(DataModel):
    """
        Data model for test station approval and approval history
    """

    names = ("org_site_approval",
             "org_site_approval_status",
             )

    def model(self):

        T = current.T

        organisation_id = self.org_organisation_id
        site_id = self.org_site_id

        define_table = self.define_table
        configure = self.configure

        crud_strings = current.response.s3.crud_strings
        css = "approval-workflow"

        # ---------------------------------------------------------------------
        # Current approval details
        #
        tablename = "org_site_approval"
        define_table(tablename,
                     organisation_id(),
                     site_id(),
                     # Hidden data hash to detect relevant changes
                     Field("dhash",
                           readable = False,
                           writable = False,
                           ),
                     # Workflow status
                     Field("status",
                           label = T("Processing Status"),
                           default = "REVISE",
                           requires = IS_IN_SET(APPROVAL_STATUS.selectable(True),
                                                zero = None,
                                                sort = False,
                                                ),
                           represent = APPROVAL_STATUS.represent,
                           readable = True,
                           writable = False,
                           ),
                     # Hygiene concept
                     Field("hygiene",
                           label = T("Hygiene Plan"),
                           default = "REVISE",
                           requires = IS_IN_SET(SITE_RQM.selectable(True),
                                                zero = None,
                                                sort = False,
                                                ),
                           represent = SITE_RQM.represent,
                           readable = True,
                           writable = False,
                           ),
                     # Facility layout
                     Field("layout",
                           label = T("Facility Layout Plan"),
                           default = "REVISE",
                           requires = IS_IN_SET(SITE_RQM.selectable(True),
                                                zero = None,
                                                sort = False,
                                                ),
                           represent = SITE_RQM.represent,
                           readable = True,
                           writable = False,
                           ),
                     # Listed in public registry
                     Field("public",
                           label = T("In Public Registry"),
                           default = "N",
                           requires = IS_IN_SET(PUBLIC_STATUS.selectable(True),
                                                zero = None,
                                                sort = False,
                                                ),
                           represent = PUBLIC_STATUS.represent,
                           readable = True,
                           writable = False,
                           ),
                     Field("public_reason",
                           label = T("Reason for unlisting"),
                           default = "REVISE",
                           requires = IS_EMPTY_OR(
                                        IS_IN_SET(PUBLIC_REASON.selectable(True),
                                                  sort = False,
                                                  zero = None,
                                                  )),
                           represent = represent_option(dict(PUBLIC_REASON.labels())),
                           readable = True,
                           writable = False,
                           ),
                     Field("advice", "text",
                           label = T("Advice"),
                           represent = lambda v, row=None: \
                                       s3_text_represent(v,
                                                         truncate = False,
                                                         _class = ("%s workflow-advice" % css) if v else css,
                                                         ),
                           widget = s3_comments_widget,
                           readable = False,
                           writable = False,
                           ),
                     )

        # Table configuration
        configure(tablename,
                  onvalidation = self.site_approval_onvalidation,
                  onaccept = self.site_approval_onaccept,
                  )

        # ---------------------------------------------------------------------
        # Historic approval statuses
        # - written onaccept of org_site_approval when values change
        #
        tablename = "org_site_approval_status"
        define_table(tablename,
                     site_id(),
                     DateTimeField("timestmp", writable=False),
                     Field("status",
                           label = T("Processing Status"),
                           represent = APPROVAL_STATUS.represent,
                           writable = False,
                           ),
                     # Retained since relevant in historic records:
                     Field("mpav",
                           label = T("MPAV Qualification"),
                           represent = SITE_RQM.represent,
                           readable = False,
                           writable = False,
                           ),
                     Field("hygiene",
                           label = T("Hygiene Plan"),
                           represent = SITE_RQM.represent,
                           writable = False,
                           ),
                     Field("layout",
                           label = T("Facility Layout Plan"),
                           represent = SITE_RQM.represent,
                           writable = False,
                           ),
                     Field("public",
                           label = T("In Public Registry"),
                           represent = PUBLIC_STATUS.represent,
                           writable = False,
                           ),
                     Field("public_reason",
                           label = T("Reason for unlisting"),
                           represent = represent_option(dict(PUBLIC_REASON.labels())),
                           readable = True,
                           writable = False,
                           ),
                     Field("advice", "text",
                           label = T("Advice"),
                           represent = s3_text_represent,
                           writable = False,
                           ),
                     )

        # List fields
        list_fields = ["timestmp",
                       "status",
                       "public",
                       "public_reason",
                       ]

        # Table configuration
        configure(tablename,
                  insertable = False,
                  editable = False,
                  deletable = False,
                  list_fields = list_fields,
                  orderby = "%s.timestmp desc" % tablename,
                  )

        # CRUD strings
        crud_strings[tablename] = Storage(
            title_display = T("Approval Status"),
            title_list = T("Approval History"),
            label_list_button = T("Approval History"),
            msg_list_empty = T("No Approval Statuses currently registered"),
            )

        # ---------------------------------------------------------------------
        # Return additional names to response.s3
        #
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def site_approval_status_fields():
        """
            The fields that constitute the current approval status
        """

        return ("status",
                "hygiene",
                "layout",
                "public",
                "public_reason",
                "advice",
                )

    # -------------------------------------------------------------------------
    @staticmethod
    def site_approval_onvalidation(form):
        """
            Form validation of approval status:
                - require advice for manual override of public-status
        """

        form_vars = form.vars

        public = form_vars.get("public")
        reason = form_vars.get("public_reason")
        advice = form_vars.get("advice") if "advice" in form_vars else True

        if public == "N" and reason == "OVERRIDE" and not advice:
            form.errors["advice"] = current.T("More details required")

    # -------------------------------------------------------------------------
    @classmethod
    def site_approval_onaccept(cls, form):
        """
            Onaccept of site approval:
                - set public_reason if missing
                - set organisation_id
        """

        db = current.db
        s3db = current.s3db

        # Get record ID
        record_id = get_form_record_id(form)
        if not record_id:
            return

        status_fields = cls.site_approval_status_fields()

        # Re-read record
        atable = s3db.org_site_approval
        query = (atable.id == record_id) & \
                (atable.deleted == False)
        fields = [atable[fn] for fn in (("id", "organisation_id", "site_id") + status_fields)]
        record = db(query).select(*fields, limitby=(0, 1)).first()
        if not record:
            return

        update = {}

        # Set/remove public-reason as required
        #if record.public == "N" and not record.public_reason:
        #    update["public_reason"] = "OVERRIDE"
        if record.public == "Y":
            update["public_reason"] = None

        # Set organisation_id if missing
        ts = TestStation(record.site_id)
        if record.organisation_id != ts.organisation_id:
            update["organisation_id"] = ts.organisation_id

        if update:
            record.update_record(**update)

# =============================================================================
class TestProvider:
    """
        Service functions for the provider verification/commissioning workflow
    """

    def __init__(self, organisation_id):
        """
            Args:
                organisation_id: the org_organisation record ID
        """

        self.organisation_id = organisation_id

        self._record = None
        self._verification = None
        self._commission = None

        self._types = None

    # -------------------------------------------------------------------------
    # Instance properties
    # -------------------------------------------------------------------------
    @property
    def record(self):
        """
            The current organisation record

            Returns:
                - org_organisation Row
        """

        record = self._record
        if not record:
            table = current.s3db.org_organisation
            query = (table.id == self.organisation_id) & \
                    (table.deleted == False)
            record = current.db(query).select(table.id,
                                              table.name,
                                              limitby = (0, 1),
                                              ).first()
            self._record = record

        return record

    # -------------------------------------------------------------------------
    @property
    def verification(self):
        """
            The current verification record for this organisation

            Returns:
                - org_verification Row
        """

        verification = self._verification

        if not verification:
            verification = self.lookup_verification()
            if not verification:
                verification = self.add_verification_defaults()

            self._verification = verification

        return verification

    # -------------------------------------------------------------------------
    @property
    def verified(self):
        """
            Whether the verification of this provider is complete

            Returns:
                bool
        """

        return self.verification.status == "COMPLETE"

    # -------------------------------------------------------------------------
    @property
    def current_commission(self):
        """
            The current commission record, i.e.
                - with status CURRENT and valid for the current date

            Returns:
                - org_commission Row
        """

        commission = self._commission
        if not commission:
            table = current.s3db.org_commission
            today = current.request.utcnow.date()

            query = (table.organisation_id == self.organisation_id) & \
                    (table.status == "CURRENT") & \
                    ((table.date == None) | (table.date <= today)) & \
                    ((table.end_date == None) | (table.end_date >= today)) & \
                    (table.deleted == False)
            row = current.db(query).select(table.id,
                                           table.date,
                                           table.end_date,
                                           table.status,
                                           limitby = (0, 1),
                                           orderby = ~table.date,
                                           ).first()
            if row:
                commission = self._commission = row

        return commission

    # -------------------------------------------------------------------------
    @property
    def types(self):
        """
            The organisation types and corresponding requirements for this provider

            Returns:
                dict {type_id: requirements}
        """

        types = self._types
        if types is None:

            types = {}

            db = current.db
            s3db = current.s3db

            ltable = s3db.org_organisation_organisation_type
            rtable = s3db.org_requirements

            left = rtable.on((rtable.organisation_type_id == ltable.organisation_type_id) & \
                             (rtable.deleted == False))
            query = (ltable.organisation_id == self.organisation_id) & \
                    (ltable.deleted == False)
            rows = db(query).select(ltable.organisation_type_id,
                                    rtable.id,
                                    rtable.commercial,
                                    rtable.rinforeq,
                                    rtable.mpavreq,
                                    rtable.verifreq,
                                    left=left,
                                    )

            # Default provider requirements
            defaults = Storage(commercial = False,
                               rinforeq = False,
                               verifreq = False,
                               mpavreq = True,
                               )

            for row in rows:
                requirements = row[rtable]
                if requirements.id:
                    types[row[ltable].organisation_type_id] = requirements
                else:
                    types[row[ltable].organisation_type_id] = defaults

            self._types = types

        return types

    # -------------------------------------------------------------------------
    @property
    def commercial(self):
        """
            Whether this is a commercial provider

            Returns:
                bool
        """

        types = self.types
        return any(types[t].commercial for t in types)

    # -------------------------------------------------------------------------
    @property
    def verifreq(self):
        """
            Whether organisation type verification is required for this provider

            Returns:
                bool
        """

        types = self.types
        return any(types[t].verifreq for t in types)

    # -------------------------------------------------------------------------
    @property
    def mpavreq(self):
        """
            Whether MPAV qualification verification is required for this provider

            Returns:
                bool
        """

        types = self.types
        return any(types[t].mpavreq for t in types)

    # -------------------------------------------------------------------------
    @property
    def rinforeq(self):
        """
            Whether representative documentation is required for this provider

            Returns:
                bool
        """

        types = self.types
        return any(types[t].rinforeq for t in types)

    # -------------------------------------------------------------------------
    # Instance methods
    # -------------------------------------------------------------------------
    def lookup_verification(self, query=None):
        """
            Looks up the current verification status of this provider

            Args:
                query: the query to use for the lookup (optional)

            Returns:
                org_verification Row
        """

        table = current.s3db.org_verification

        if query is None:
            query = (table.organisation_id == self.organisation_id) & \
                    (table.deleted == False)

        verification = current.db(query).select(table.id,
                                                table.dhash,
                                                table.status,
                                                table.orgtype,
                                                table.mpav,
                                                table.reprinfo,
                                                limitby = (0, 1),
                                                ).first()
        return verification

    # -------------------------------------------------------------------------
    @staticmethod
    def status(values):
        """
            Determines overall verification status from tag values

            Args:
                values: the tag values

            Returns:
                the overall verification status
        """

        if all(v in ("VERIFIED", "ACCEPT") for v in values):
            status = "COMPLETE"
        elif any(v == "REVIEW" for v in values):
            status = "REVIEW"
        else:
            status = "REVISE"

        return status

    # -------------------------------------------------------------------------
    def verification_defaults(self):
        """
            Gets defaults for the verification record for this provider
                - defaults depend on organisation type

            Returns:
                dict {fieldname: value}
        """

        if self.types:
            orgtype = "REVISE" if self.verifreq else "ACCEPT"
            mpav = "REVISE" if self.mpavreq else "ACCEPT"
        else:
            orgtype = "N/A"
            mpav = "REVISE"

        reprinfo = self.check_reprinfo() if self.rinforeq else "ACCEPT"

        status = self.status((orgtype, mpav, reprinfo))

        return {"status": status,
                "orgtype": orgtype,
                "mpav": mpav,
                "reprinfo": reprinfo,
                }

    # -----------------------------------------------------------------------------
    def add_default_tags(self):
        """
            Adds default tags for this provider (DELIVERY and OrgID)

            Notes:
                - to be called create-onaccept of organisations
        """

        db = current.db
        s3db = current.s3db

        # Look up current tags
        otable = s3db.org_organisation
        ttable = s3db.org_organisation_tag
        dttable = ttable.with_alias("delivery")
        ittable = ttable.with_alias("orgid")

        left = [dttable.on((dttable.organisation_id == otable.id) & \
                           (dttable.tag == "DELIVERY") & \
                           (dttable.deleted == False)),
                ittable.on((ittable.organisation_id == otable.id) & \
                           (ittable.tag == "OrgID") & \
                           (ittable.deleted == False)),
                ]
        query = (otable.id == self.organisation_id)
        row = db(query).select(otable.id,
                               otable.uuid,
                               dttable.id,
                               ittable.id,
                               left = left,
                               limitby = (0, 1),
                               ).first()
        if row:
            # Add default tags as required
            org = row.org_organisation

            # Add DELIVERY-tag
            dtag = row.delivery
            if not dtag.id:
                ttable.insert(organisation_id = org.id,
                              tag = "DELIVERY",
                              value = "DIRECT",
                              )
            # Add OrgID-tag
            itag = row.orgid
            if not itag.id:
                try:
                    uid = int(org.uuid[9:14], 16)
                except (TypeError, ValueError):
                    import uuid
                    uid = int(uuid.uuid4().urn[9:14], 16)
                value = "%06d%04d" % (uid, org.id)
                ttable.insert(organisation_id = org.id,
                              tag = "OrgID",
                              value = value,
                              )

    # -------------------------------------------------------------------------
    def add_verification_defaults(self):
        """
            Adds the default verification status for this provider

            Returns:
                org_verification Row

            Notes:
                - should be called during organisation post-process, not
                  onaccept (because type links are written only after onaccept)
                - required both during registration approval and manual
                  creation of organisation
        """

        data = self.verification_defaults()
        data["organisation_id"] = self.organisation_id

        table = current.s3db.org_verification
        record_id = table.insert(**data)
        current.auth.s3_set_record_owner(table, record_id)

        return self.lookup_verification(table.id == record_id)

    # -------------------------------------------------------------------------
    def vhash(self):
        """
            Produces a data hash for this provider, to be stored in the
            verification record for detection of verification-relevant
            data changes

            Returns:
                tuple (update, vhash), where
                - update is a dict with updates for the verification record
                - hash is the (updated) data hash
        """

        # Compute the vhash
        types = "|".join(str(x) for x in sorted(self.types))
        vhash = get_dhash([types])

        verification = self.verification

        # Check the current hash to detect relevant changes
        if vhash != verification.dhash:
            # Relevant data have changed

            # Determine default statuses
            update = self.verification_defaults()

            # Update statuses for manually approved requirements
            is_org_group_admin = current.auth.s3_has_role("ORG_GROUP_ADMIN")
            for tag in ("orgtype", "mpav"): # reprinfo determined by own workflow
                if update[tag] in ("N/A", "ACCEPT", "VERIFIED"):
                    continue # reset unconditionally
                current_value = verification[tag]
                if is_org_group_admin:
                    if current_value == "ACCEPT":
                        update[tag] = "REVIEW"
                    else:
                        update[tag] = current_value
                else:
                    if verification.status == "READY" or current_value == "REVIEW":
                        update[tag] = "REVIEW"
                    else:
                        update[tag] = "REVISE"

            # Determine overall status
            tags = ("orgtype", "mpav", "reprinfo")
            update["status"] = self.status(update[t] for t in tags)
            update["dhash"] = vhash
        else:
            update = None

        return update, vhash

    # -------------------------------------------------------------------------
    def check_reprinfo(self):
        """
            Checks whether this provider has at least one verified and
            active representative

            Returns:
                status N/A|REVISE|REVIEW|VERIFIED

            Notes:
                - does not evaluate whether representative info is required
        """

        db = current.db
        s3db = current.s3db

        rtable = s3db.org_representative
        htable = s3db.hrm_human_resource

        join = htable.on((htable.person_id == rtable.person_id) & \
                         (htable.organisation_id == rtable.organisation_id) & \
                         (htable.org_contact == True) & \
                         (htable.status == 1) & \
                         (htable.deleted == False))

        query = (rtable.organisation_id == self.organisation_id)
        rows = db(query).select(rtable.status, join=join)

        if not rows:
            return "N/A"
        elif any(row.status == "APPROVED" for row in rows):
            return "VERIFIED"
        elif any(row.status == "REVIEW" for row in rows):
            return "REVIEW"
        else:
            return "REVISE"

    # -------------------------------------------------------------------------
    def update_verification(self):
        """
            Updates the verification status of this provider, to be called
            whenever relevant details change:
                - organisation form post-process
                - staff record, person record, contact details
                - org type tags regarding verification requirements
        """

        verification = self.verification

        update, vhash = self.vhash()
        if update:
            if "status" in update:
                status = update["status"]
        else:
            if vhash != verification.dhash:
                update = {"dhash": vhash}
            else:
                update = {}
            status = verification.status

            # Update orgtype
            orgtype = verification.orgtype
            if self.verifreq:
                if orgtype == "ACCEPT":
                    orgtype = "REVIEW"
            else:
                orgtype = "ACCEPT"
            if orgtype == "REVISE" and status == "READY":
                orgtype = "REVIEW"
            if orgtype != verification.orgtype:
                update["orgtype"] = orgtype

            # Update mpav
            mpav = verification.mpav
            if self.mpavreq:
                if mpav == "ACCEPT":
                    mpav = "REVIEW"
            else:
                mpav = "ACCEPT"
            if mpav == "REVISE" and status == "READY":
                mpav = "REVIEW"
            if mpav != verification.mpav:
                update["mpav"] = mpav

            # Update reprinfo
            reprinfo = self.check_reprinfo() if self.rinforeq else "ACCEPT"
            if reprinfo != verification.reprinfo:
                update["reprinfo"] = reprinfo

            # Determine overall status
            status = self.status((orgtype, mpav, reprinfo))
            if status != verification.status:
                update["status"] = status

        if update:
            verification.update_record(**update)

        if status == "COMPLETE":
            info, warn = self.reinstate_commission("N/V")
        else:
            info, warn = self.suspend_commission("N/V")

        return info, warn

    # -------------------------------------------------------------------------
    def suspend_commission(self, reason):
        """
            Suspends all current commissions of this provider

            Args:
                reason: the reason code for suspension (required)
        """

        if not reason:
            raise RuntimeError("reason required")

        info, warn = None, None

        db = current.db
        s3db = current.s3db

        table = s3db.org_commission
        query = (table.organisation_id == self.organisation_id) & \
                (table.status == "CURRENT") & \
                (table.deleted == False)
        rows = db(query).select(table.id)
        if rows:
            T = current.T
            commission_ids = [row.id for row in rows]
            query = (table.id.belongs(commission_ids))
            db(query).update(status = "SUSPENDED",
                             status_date = current.request.utcnow.date(),
                             status_reason = reason,
                             prev_status = "SUSPENDED",
                             modified_by = table.modified_by,
                             modified_on = table.modified_on,
                             )

            msg = self.notify_commission_change(status = "SUSPENDED",
                                                reason = reason,
                                                commission_ids = commission_ids,
                                                )
            if msg is None:
                info = "%s - %s" % (T("Commission suspended"), T("Test station notified"))
                warn = None
            elif msg:
                info = T("Commission suspended")
                warn = T("Test station could not be notified: %(error)s") % {"error": msg}

        TestStation.update_all(self.organisation_id,
                               public = "N",
                               reason = "SUSPENDED",
                               )

        return info, warn

    # -------------------------------------------------------------------------
    def reinstate_commission(self, reason):
        """
            Reinstates commissions of this provider that have previously
            been suspended for the given reason(s)

            Args:
                reason: the reason code, or a list of codes (required)
        """

        if not reason:
            raise RuntimeError("reason required")

        info, warn = None, None

        db = current.db
        s3db = current.s3db

        table = s3db.org_commission
        query = (table.organisation_id == self.organisation_id) & \
                (table.status == "SUSPENDED")
        if isinstance(reason, (tuple, list, set)):
            query &= (table.status_reason.belongs(reason))
        else:
            query &= (table.status_reason == reason)
        today = datetime.datetime.utcnow().date()
        query &= ((table.end_date == None) | (table.end_date >= today)) & \
                 (table.deleted == False)
        rows = db(query).select(table.id)
        if rows:
            T = current.T
            commission_ids = [row.id for row in rows]
            query = (table.id.belongs(commission_ids))
            db(query).update(status = "CURRENT",
                             status_date = current.request.utcnow.date(),
                             status_reason = None,
                             prev_status = "CURRENT",
                             modified_by = table.modified_by,
                             modified_on = table.modified_on,
                             )

            # Issue any missing commissioning notes
            from ..commission import ProviderCommission
            for commission_id in commission_ids:
                ProviderCommission(commission_id).issue_note()

            msg = self.notify_commission_change(status = "CURRENT",
                                                reason = reason,
                                                commission_ids = commission_ids,
                                                )
            if msg is None:
                info = "%s - %s" % (T("Commission reinstated"), T("Test station notified"))
                warn = None
            elif msg:
                info = T("Commission reinstated")
                warn = T("Test station could not be notified: %(error)s") % {"error": msg}

        self._commission = None

        if self.current_commission:
            TestStation.update_all(self.organisation_id,
                                   public = "Y",
                                   reason = ("SUSPENDED", "COMMISSION"),
                                   )

        return info, warn

    # -------------------------------------------------------------------------
    def expire_commission(self):
        """
            Deactivate all current/suspended commissions of this provider
            which have expired
        """

        db = current.db
        s3db = current.s3db

        today = datetime.datetime.utcnow().date()

        # Look up all expired commissions
        table = s3db.org_commission
        query = (table.organisation_id == self.organisation_id) & \
                (table.status.belongs("CURRENT", "SUSPENDED")) & \
                (table.end_date != None) & \
                (table.end_date < today) & \
                (table.deleted == False)
        rows = db(query).select(table.id,
                                table.status,
                                )
        commission_ids = [row.id for row in rows]
        if commission_ids:
            # Mark them as expired
            query = (table.id.belongs(commission_ids))
            db(query).update(prev_status = table.status,
                             status = "EXPIRED",
                             status_date = today,
                             status_reason = None,
                             )

            # If there is no current commission, de-list all test stations
            # and notify the organisation
            self._commission = None
            if not self.current_commission:
                TestStation.update_all(self.organisation_id,
                                       public = "N",
                                       reason = "COMMISSION",
                                       )
                self.notify_commission_change(status = "EXPIRED",
                                              commission_ids = commission_ids,
                                              )

    # -------------------------------------------------------------------------
    def notify_commission_change(self,
                                 status = None,
                                 reason = None,
                                 commission_ids = None,
                                 force = False,
                                 ):
        """
            Notifies the OrgAdmin of this provider about the status change
            of their commission

            Args:
                status: the new commission status
                reason: the reason for the status (if SUSPENDED)
                commission_ids: the affected commissions
                force: notify suspension even if the provider still has
                       a current commission

            Returns:
                error message on error, else None
        """

        if not commission_ids:
            return False
        if status != "CURRENT" and self.current_commission and not force:
            return False

        # Get the organisation ID
        organisation_id = self.organisation_id
        if not organisation_id:
            return "Organisation not found"

        # Find the OrgAdmin email addresses
        from ..helpers import get_role_emails
        email = get_role_emails("ORG_ADMIN",
                                organisation_id = organisation_id,
                                )
        if not email:
            return "No Organisation Administrator found"

        # Lookup email address of current user
        from ..notifications import CMSNotifications
        auth = current.auth
        if auth.user:
            cc = CMSNotifications.lookup_contact(auth.user.pe_id)
        else:
            cc = None

        # Data for the notification email
        app_url = current.deployment_settings.get_base_app_url()
        org_data = {"name": self.record.name,
                    "url": "%s/org/organisation/%s/commission" % (app_url, organisation_id)
                    }

        template = {"CURRENT": "CommissionIssued",
                    "SUSPENDED": "CommissionSuspended",
                    "REVOKED": "CommissionRevoked",
                    "EXPIRED": "CommissionExpired",
                    }.get(status)
        if not template:
            template = "CommissionStatusChanged"

        reason_labels = dict(COMMISSION_REASON.labels())

        db = current.db
        s3db = current.s3db

        table = s3db.org_commission

        error = "No commission found"
        for commission_id in commission_ids:

            # Get the commission record
            query = (table.id == commission_id)
            commission = db(query).select(table.id,
                                          table.date,
                                          table.end_date,
                                          table.status_date,
                                          table.status_reason,
                                          table.comments,
                                          limitby = (0, 1),
                                          ).first()

            if not commission:
                continue

            if not reason:
                reason = commission.status_reason
            if reason:
                requirements = {"N/V": "TestProviderRequirements",
                                }.get(reason)
                reason = reason_labels.get(reason)
            else:
                requirements = None
                reason = "-"

            data = {"start": table.date.represent(commission.date),
                    "end": table.end_date.represent(commission.end_date),
                    "status_date": table.status_date.represent(commission.status_date),
                    "reason": reason,
                    "comments": commission.comments,
                    "explanation": "",
                    }
            data.update(org_data)

            # Add a requirements hint, if available
            if requirements:
                ctable = s3db.cms_post
                ltable = s3db.cms_post_module
                join = ltable.on((ltable.post_id == ctable.id) & \
                                 (ltable.module == "org") & \
                                 (ltable.resource == "commission") & \
                                 (ltable.deleted == False))
                query = (ctable.name == requirements) & \
                        (ctable.deleted == False)
                row = db(query).select(ctable.body,
                                       join = join,
                                       limitby = (0, 1),
                                       ).first()
                if row:
                    data["explanation"] = row.body

            error = CMSNotifications.send(email,
                                          template,
                                          data,
                                          module = "org",
                                          resource = "commission",
                                          cc = cc,
                                          )
        return error

    # -------------------------------------------------------------------------
    def add_audit_status(self):
        """
            Adds the audit status for this provider, if it doesn't exist
        """

        table = current.s3db.org_audit
        organisation_id = self.organisation_id

        query = (table.organisation_id == organisation_id)
        audit = current.db(query).select(table.id, limitby=(0, 1)).first()
        if not audit and organisation_id:
            record_id = table.insert(organisation_id = organisation_id)
            current.auth.s3_set_record_owner(table, record_id)
        else:
            record_id = None
        return record_id

    # -------------------------------------------------------------------------
    def update_audit_status(self):
        """
            Updates the audit status of the provider:
                - sets org_audit.docs_available
        """

        db = current.db
        s3db = current.s3db

        dtable = s3db.doc_document
        atable = s3db.org_audit

        organisation_id = self.organisation_id

        query = (dtable.organisation_id == organisation_id) & \
                (dtable.status == "NEW") & \
                (dtable.deleted == False)
        new_documents = db(query).select(dtable.id, limitby=(0, 1)).first()

        query = (atable.organisation_id == organisation_id) & \
                (atable.deleted == False)
        db(query).update(docs_available = bool(new_documents),
                         modified_by = atable.modified_by,
                         modified_on = atable.modified_on,
                         )

    # -------------------------------------------------------------------------
    # Configuration helpers
    # -------------------------------------------------------------------------
    @staticmethod
    def add_components():
        """
            Adds org_organisation components for verification/commission
        """

        current.s3db.add_components("org_organisation",
                                    org_verification = {"joinby": "organisation_id",
                                                        "multiple": False,
                                                        },
                                    org_audit = {"joinby": "organisation_id",
                                                 "multiple": False,
                                                 },
                                    org_representative = "organisation_id",
                                    org_commission = "organisation_id",
                                    org_bsnr = "organisation_id",
                                    jnl_issue = "organisation_id",
                                    )

    # -------------------------------------------------------------------------
    @classmethod
    def configure_verification(cls, resource, role="applicant", record_id=None):
        """
            Configures the verification subform for CRUD

            Args:
                resource: the org_organisation resource
                role: applicant|approver
                record_id: the org_organisation record ID
        """

        component = resource.components.get("verification")
        if not component:
            return None
        table = component.table

        visible = []

        if record_id:
            is_approver = role == "approver"

            provider = cls(record_id)

            # Overall status
            field = table.status
            current_value = provider.verification.status
            if current_value == "REVISE":
                options = VERIFICATION_STATUS.selectable(True, current_value=current_value)
                field.requires = IS_IN_SET(options, sort=False, zero=None)
                field.writable = not is_approver
            else:
                field.writable = False

            # Organisation type verification (if required)
            field = table.orgtype
            if provider.verifreq:
                current_value = provider.verification.orgtype
                options = ORG_RQM.selectable(True, current_value=current_value)
                field.requires = IS_IN_SET(options, sort=False, zero=None)
                field.writable = is_approver
            else:
                field.readable = False

            # MPAV Qualification verification (if required)
            field = table.mpav
            if provider.mpavreq:
                current_value = provider.verification.mpav
                options = ORG_RQM.selectable(True, current_value=current_value)
                field.requires = IS_IN_SET(options, sort=False, zero=None)
                field.writable = is_approver
            else:
                field.readable = False

            # Representative Info (if required, always read-only)
            field = table.reprinfo
            if not provider.rinforeq:
                field.readable = False

            for fn in ("status", "orgtype", "mpav", "reprinfo"):
                field = table[fn]
                if field.readable or field.writable:
                    visible.append("verification.%s" % fn)
        else:
            for fn in ("status", "orgtype", "mpav", "reprinfo"):
                field = table[fn]
                field.readable = field.writable = False

        return visible if visible else None

    # -------------------------------------------------------------------------
    @staticmethod
    def configure_commission(resource,
                             role = "applicant",
                             record_id = None,
                             commission_id = None,
                             ):
        """
            Configures the commission resource and form for CRUD

            Args:
                resource: the org_commission resource
                role: applicant|provider
                record_id: the org_organisation record ID
                commission_id: the org_commission record ID
        """

        table = resource.table

        if role == "approver":
            if commission_id:
                # Get the record
                query = (table.id == commission_id) & \
                        (table.deleted == False)
                commission = current.db(query).select(table.status,
                                                      table.date,
                                                      limitby = (0, 1),
                                                      ).first()
            else:
                commission = None

            # Has the provider verification been accepted?
            if record_id:
                accepted = TestProvider(record_id).verified
            else:
                accepted = False

            # Determine whether commission is editable
            editable = False
            if commission:
                # Existing commission, editable if current or suspended
                editable = commission.status in ("CURRENT", "SUSPENDED")

                # Dates are not editable once commission has been issued
                field = table.date
                field.writable = False
                field = table.end_date
                field.writable = False

                # Allow to keep the original commission date
                #field = table.date
                #field.requires = IS_UTC_DATE(minimum=commission.date)
                #field.widget.minimum = commission.date
            else:
                # List view or new commission, always editable
                editable = True
            resource.configure(insertable = True,
                               editable = editable,
                               )

            if accepted:
                status = True, "CURRENT"
                reason = ("OVERRIDE",), None
            else:
                status = ("SUSPENDED", "REVOKED"), "SUSPENDED"
                reason = ("N/V", "OVERRIDE"), "N/V"

            # Configure status field
            options, default = status
            field = table.status
            field.writable = editable
            field.requires = IS_IN_SET(COMMISSION_STATUS.selectable(options),
                                       sort = False,
                                       zero = None,
                                       )
            field.default = default

            # Configure reason field
            options, default = reason
            field = table.status_reason
            field.requires = IS_EMPTY_OR(
                                IS_IN_SET(COMMISSION_REASON.selectable(options),
                                          sort = False,
                                          zero = None,
                                          ))
            field.default = default

        else:
            # Render read-only
            for fn in table.fields:
                field = table[fn]
                field.writable = False
            #resource.configure(editable = False) # is the model default

# =============================================================================
class ProviderRepresentative:
    """ Service functions for provider representative verification """

    # Data requirements for representatives
    place_of_birth_required = True
    email_required = True
    phone_required = True
    address_required = True
    account_required = False
    role_required = False

    def __init__(self, record_id=None):
        """
            Args:
                record_id: the org_representative record ID
        """

        self.record_id = record_id
        self._record = None

    # -------------------------------------------------------------------------
    @property
    def record(self):
        """
            The org_representative record (lazy property)

            Returns:
                Row
        """

        record = self._record
        if not record and self.record_id:
            table = current.s3db.org_representative
            query = (table.id == self.record_id) & \
                    (table.deleted == False)
            record = current.db(query).select(table.id,
                                              table.person_id,
                                              table.organisation_id,
                                              table.doc_id,
                                              table.active,
                                              table.date,
                                              table.end_date,
                                              table.dhash,
                                              table.status,
                                              table.person_data,
                                              table.contact_data,
                                              table.address_data,
                                              table.user_account,
                                              table.regform,
                                              table.crc,
                                              table.scp,
                                              #table.comments,
                                              limitby = (0, 1),
                                              ).first()
            self._record = record

        return record

    # -------------------------------------------------------------------------
    def vhash(self):
        """
            Generate and verify a verification hash for this record

            Returns:
                tuple (update, vhash)
                - update: a dict {field: value} with required updates
                - vhash: the (new) verification hash
        """

        record = self.record
        if not record:
            return None, None

        # Get person record
        ptable = current.s3db.pr_person
        query = (ptable.id == record.person_id) & \
                (ptable.deleted == False)
        person = current.db(query).select(ptable.id,
                                          ptable.first_name,
                                          ptable.last_name,
                                          ptable.date_of_birth,
                                          limitby = (0, 1),
                                          ).first()
        if not person:
            return None, None

        dob = person.date_of_birth
        if dob:
            dob = dob.isoformat()

        vhash = get_dhash(record.organisation_id,
                          record.person_id,
                          person.first_name,
                          person.last_name,
                          dob,
                          )

        update = {}
        if record.dhash and record.dhash != vhash and \
           not current.auth.s3_has_role("ORG_GROUP_ADMIN"):
            for fn in ("regform", "crc", "scp"):
                if record[fn] == "APPROVED":
                    update[fn] = "REVIEW"

        return update, vhash

    # -------------------------------------------------------------------------
    def update_verification(self, show_errors=False):
        """
            Update the verification status (also checks for required data)

            Args:
                show_errors: set interactive error messages (response.error)

            Returns:
                tuple (info, warn) with messages about notification success
        """

        record = self.record
        if not record:
            return None, None

        # Have data changed?
        update, vhash = self.vhash()

        # Check completeness of data
        accepted, errors = self.check_data(record = record,
                                           update = update,
                                           show_errors = show_errors,
                                           )

        # Report errors if/as requested
        if show_errors and errors:
            msg = current.T("Data incomplete (%(details)s)") % {"details": ", ".join(errors)}
            current.response.warning = msg

        # Initialize missing tags
        tags = ["regform", "crc", "scp"]
        for tag in tags:
            if tag not in update and record[tag] is None:
                update[tag] = "N/A"

        # Process tags and determine overall processing status
        status = record.status
        value = lambda t: update.get(t) or record[t]

        if status == "READY":
            if all(value(tag) == "APPROVED" for tag in tags):
                for tag in tags:
                    update[tag] = "REVIEW"
            else:
                for tag in tags:
                    if value(tag) in ("N/A", "REJECTED"):
                        update[tag] = "REVIEW"

        if accepted:
            if all(value(tag) == "APPROVED" for tag in tags):
                status = "APPROVED"
            elif any(value(tag) == "REVIEW" for tag in tags):
                status = "REVIEW"
            else:
                status = "REVISE"
        else:
            status = "REVISE"

        if status != record.status:
            update["status"] = status

        # Update or remove dhash as required
        if status != "APPROVED" and record.dhash:
            update["dhash"] = None
        elif status == "APPROVED" and record.dhash != vhash:
            update["dhash"] = vhash

        # Determine active status and start/end dates
        active = self.check_active() and status == "APPROVED"
        if active != record.active:
            update["active"] = active

        today = current.request.utcnow.date()
        if active:
            if not record.date:
                update["date"] = today
            if record.end_date:
                update["end_date"] = None
        elif not record.end_date:
            update["end_date"] = today

        # Update record and trigger provider status update
        if update:
            record.update_record(**update)
            info, warn = TestProvider(record.organisation_id).update_verification()
        else:
            info, warn = None, None

        return info, warn

    # -------------------------------------------------------------------------
    @classmethod
    def check_data(cls, person_id=None, record=None, update=None, show_errors=True):
        """
            Check completeness of data

            Args:
                person_id: the person ID
                record: the org_representative record (overrides person_id)
                update: dict with updates for representative record
                show_errors: which errors to report (True for all)

            Returns:
                tuple (accepted, missing)
                - accepted: whether data can be accepted for verification
                - missing: string specifying which data are missing
        """

        if record:
            person_id = record.person_id

        errors = []
        append = errors.append

        def check(flag, method):
            acceptable, missing = method(person_id)
            complete = not bool(missing)
            if update is not None and record and record[flag] != complete:
                update[flag] = complete
            if missing and show_errors is True or show_errors == flag:
                append(missing)
            return acceptable

        accepted = check("person_data", cls.check_person_data)
        accepted &= check("contact_data", cls.check_contact_data)
        accepted &= check("address_data", cls.check_address_data)
        accepted &= check("user_account", cls.check_account)

        return accepted, errors

    # -------------------------------------------------------------------------
    @classmethod
    def check_person_data(cls, person_id):
        """
            Check whether person data are complete/acceptable

            Args:
                person_id: the person record ID

            Returns:
                tuple (acceptable, missing)
        """

        T = current.T

        db = current.db
        s3db = current.s3db

        # Get the person record
        ptable = s3db.pr_person
        query = (ptable.id == person_id) & (ptable.deleted == False)
        row = db(query).select(ptable.first_name,
                               ptable.last_name,
                               ptable.date_of_birth,
                               limitby = (0, 1),
                               ).first()
        if not row:
            return False, s3_str(T("record not found"))

        # Validate details
        acceptable = True
        missing = []
        append = missing.append

        if not row.first_name or not row.last_name:
            acceptable = False
            append(T("first or last name"))
        if not row.date_of_birth:
            acceptable = False
            append(T("date of birth"))

        dtable = s3db.pr_person_details
        query = (dtable.person_id == person_id) & (dtable.deleted == False)
        row = db(query).select(dtable.place_of_birth,
                               limitby = (0, 1),
                               ).first()
        if not row or not row.place_of_birth:
            if cls.place_of_birth_required:
                acceptable = False
            append(T("place of birth"))

        if missing:
            missing = ", ".join(s3_str(detail) for detail in missing)
        else:
            missing = None

        return acceptable, missing

    # -------------------------------------------------------------------------
    @classmethod
    def check_contact_data(cls, person_id):
        """
            Check whether contact information is complete/acceptable

            Args:
                person_id: the person record ID

            Returns:
                tuple (acceptable, missing)
        """

        T = current.T

        db = current.db
        s3db = current.s3db

        ptable = s3db.pr_person
        ctable = s3db.pr_contact

        join = ptable.on(ptable.pe_id == ctable.pe_id)

        phone = email = True
        missing = []
        append = missing.append

        # Check email address
        query = (ptable.id == person_id) & \
                (ctable.contact_method == "EMAIL") & \
                (ctable.value != None) & \
                (ctable.deleted == False)
        if not db(query).select(ctable.id, join=join, limitby=(0, 1)).first():
            append(T("email address"))
            email = False

        # Check phone number
        query = (ptable.id == person_id) & \
                (ctable.contact_method.belongs("SMS", "HOME_PHONE", "WORK_PHONE")) & \
                (ctable.value != None) & \
                (ctable.deleted == False)
        if not db(query).select(ctable.id, join=join, limitby=(0, 1)).first():
            append(T("phone number"))
            phone = False

        # At least one contact detail must be provided,
        # as well as any required detail
        acceptable = (email or phone) & \
                     (email or not cls.email_required) & \
                     (phone or not cls.phone_required)
        if missing:
            missing = ", ".join(s3_str(detail) for detail in missing)
        else:
            missing = None

        return acceptable, missing

    # -------------------------------------------------------------------------
    @classmethod
    def check_address_data(cls, person_id):
        """
            Check whether address information is complete/acceptable

            Args:
                person_id: the person record ID

            Returns:
                tuple (acceptable, missing)
        """

        T = current.T

        db = current.db
        s3db = current.s3db

        ptable = s3db.pr_person
        atable = s3db.pr_address
        ltable = s3db.gis_location

        join = [ptable.on(ptable.pe_id == atable.pe_id),
                ltable.on(ltable.id == atable.location_id),
                ]

        # Check email address
        query = (ptable.id == person_id) & \
                (atable.type.belongs((1, 2))) & \
                (atable.deleted == False) & \
                (ltable.addr_street != None) & \
                (ltable.addr_postcode != None)
        if not db(query).select(atable.id, join=join, limitby=(0, 1)).first():
            acceptable, missing = not cls.address_required, s3_str(T("address"))
        else:
            acceptable, missing = True, None

        return acceptable, missing

    # -------------------------------------------------------------------------
    @classmethod
    def check_account(cls, person_id):
        """
            Check whether user account and roles are complete/acceptable

            Args:
                person_id: the person record ID

            Returns:
                tuple (acceptable, missing)
        """

        T = current.T

        db = current.db
        s3db = current.s3db
        auth = current.auth

        sr = auth.get_system_roles()
        required_role = sr.ORG_ADMIN
        alternative_role = sr.ADMIN

        acceptable, missing = True, None

        # Look up user account
        ptable = s3db.pr_person
        ltable = s3db.pr_person_user
        utable = auth.settings.table_user
        mtable = auth.settings.table_membership

        join = [ltable.on((ltable.pe_id == ptable.pe_id) & \
                          (ltable.deleted == False)),
                utable.on((utable.id == ltable.user_id) & \
                          (utable.deleted == False)),
                ]
        query = (ptable.id == person_id) & \
                ((utable.registration_key == None) | \
                 (utable.registration_key == ""))
        user = db(query).select(utable.id,
                                join = join,
                                limitby = (0, 1),
                                ).first()

        if user:
            # Check for required role
            query = (mtable.user_id == user.id) & \
                    (mtable.group_id.belongs((required_role, alternative_role))) & \
                    (mtable.deleted == False)
            if not db(query).select(mtable.id, limitby=(0, 1)).first():
                missing = s3_str(T("user role"))
                acceptable = not cls.role_required
        else:
            missing = s3_str(T("user account"))
            acceptable = not cls.account_required

        return acceptable, missing

    # -------------------------------------------------------------------------
    def check_active(self):
        """
            Check if the representative is an active staff member and
            currently marked as org contact

            Returns:
                bool
        """

        record = self.record
        if not record:
            return False

        htable = current.s3db.hrm_human_resource
        query = (htable.person_id == record.person_id) & \
                (htable.organisation_id == record.organisation_id) & \
                (htable.status == 1) & \
                (htable.org_contact == True) & \
                (htable.deleted == False)
        row = current.db(query).select(htable.id, limitby=(0, 1)).first()
        return bool(row)

    # -------------------------------------------------------------------------
    @staticmethod
    def configure(r):
        """
            Configure the verification form and representatives list,
            depending on user role and current status

            Args:
                r: the CRUDRequest
        """

        T = current.T

        s3db = current.s3db

        record = None

        if r.tablename == "org_representative":
            resource = r.resource
            table = resource.table
            record = r.record

        elif r.component and r.component.tablename == "org_representative":
            resource = r.component
            table = resource.table

            from core import CRUDMethod
            record_id = CRUDMethod._record_id(r)

            if record_id:
                query = (table.id == record_id)
                record = current.db(query).select(table.status,
                                                  limitby=(0, 1),
                                                  ).first()
        else:
            return

        is_org_group_admin = current.auth.s3_has_role("ORG_GROUP_ADMIN")
        if is_org_group_admin:
            # Document status and advice writable
            for fn in ("regform", "crc", "scp", "comments"):
                field = table[fn]
                field.readable = field.writable = True

            # Documents readonly
            documents_readonly = True

        else:
            # Status writable except when in REVIEW
            field = table.status
            if record and record.status != "REVIEW":
                field.writable = True
                options = APPROVAL_STATUS.selectable(["READY"],
                                                     current_value = record.status,
                                                     )
                field.requires = IS_IN_SET(options, zero=None, sort=False)

            # Documents writable
            documents_readonly = False

        active = None
        if r.controller == "org":
            # Show person_id
            field = table.person_id
            field.readable = True
            if not record:
                # Represent as name + link to staff view
                linkto = URL(c = "hrm",
                             f = "person",
                             args = ["[id]"],
                             vars = {"group": "staff"},
                             extension = "",
                             )
                field.represent = s3db.pr_PersonRepresent(show_link = True,
                                                          linkto = linkto,
                                                          )
            else:
                field.label = T("Personal Data")
            active = "active"

        elif r.controller == "hrm":

            if is_org_group_admin:
                table.organisation_id.readable = True

            for fn in ("active", "date", "end_date"):
                field = table[fn]
                field.readable = False

        else:
            # Show both person_id and organisation_id
            table.person_id.readable = True
            table.organisation_id.readable = True

        from core import CustomForm, InlineComponent
        crud_form = CustomForm(
                        "person_id",
                        active,
                        "organisation_id",
                        # --- Documentation ---
                        "person_data",
                        "contact_data",
                        "address_data",
                        InlineComponent(
                            "document",
                            name = "file",
                            label = T("Documents"),
                            fields = ["name", "file", "comments"],
                            filterby = {"field": "file",
                                        "options": "",
                                        "invert": True,
                                        },
                            readonly = documents_readonly,
                            ),

                        # --- Account status ---
                        "user_account",

                        # --- Verification ---
                        "status",
                        "regform",
                        "crc",
                        "scp",
                        "comments",
                        )

        subheadings = {"person_id": T("Staff"),
                       "organisation_id": T("Organization"),
                       "person_data": T("Documentation"),
                       "user_account": T("Account Status"),
                       "status": T("Verification"),
                       }

        list_fields = ["organisation_id",
                       "person_id",
                       "active",
                       "date",
                       "end_date",
                       "status",
                       ]

        resource.configure(crud_form = crud_form,
                           list_fields = list_fields,
                           subheadings = subheadings,
                           )

# =============================================================================
class TestStation:
    """
        Service functions for the test station approval/publication workflow
    """

    def __init__(self, site_id=None, facility_id=None):
        """
            Args:
                site_id: the site ID
                facility_id: the facility record ID, alternatively

            Notes:
                - facility_id will be ignored when site_id is given
        """

        self._approval = None

        if site_id:
            self._site_id = site_id
            self._facility_id = None
        else:
            self._site_id = None
            self._facility_id = facility_id

        self._record = None

    # -------------------------------------------------------------------------
    # Instance properties
    # -------------------------------------------------------------------------
    @property
    def site_id(self):
        """
            The site ID of this test station

            Returns:
                - site ID
        """

        site_id = self._site_id
        if not site_id:
            record = self.record
            site_id = record.site_id if record else None

        return site_id

    # -------------------------------------------------------------------------
    @property
    def facility_id(self):
        """
            The facility record ID of this test station

            Returns:
                - the record ID
        """

        facility_id = self._facility_id
        if not facility_id:
            record = self.record
            facility_id = record.id if record else None

        return facility_id

    # -------------------------------------------------------------------------
    @property
    def organisation_id(self):
        """
            The record ID of the organisation this test station belongs to

            Returns:
                - the organisation record ID
        """

        record = self.record

        return record.organisation_id if record else None

    # -------------------------------------------------------------------------
    @property
    def record(self):
        """
            The current org_facility record

            Returns:
                org_facility Row
        """

        record = self._record
        if not record:
            table = current.s3db.org_facility
            site_id, facility_id = self._site_id, self._facility_id
            if site_id:
                query = (table.site_id == site_id)
            else:
                query = (table.id == facility_id)
            query &= (table.deleted == False)
            record = current.db(query).select(table.id,
                                              table.uuid,
                                              table.code,
                                              table.name,
                                              table.site_id,
                                              table.organisation_id,
                                              table.location_id,
                                              limitby = (0, 1),
                                              ).first()
            if record:
                self._record = record
                self._facility_id = record.id
                self._site_id = record.site_id

        return record

    # -------------------------------------------------------------------------
    @property
    def approval(self):
        """
            The current approval status record

            Returns:
                - org_site_approval Row
        """

        approval = self._approval
        if not approval:
            approval = self.lookup_approval()
            if not approval:
                # Create approval status record with defaults
                approval = self.add_approval_defaults()
            self._approval = approval

        return approval

    # -------------------------------------------------------------------------
    # Instance methods
    # -------------------------------------------------------------------------
    def lookup_approval(self, query=None):
        """
            Looks up the current approval status of this test station

            Args:
                query: the query to use for the lookup (override)

            Returns:
                org_site_approval Row
        """

        table = current.s3db.org_site_approval

        if query is None:
            query = (table.site_id == self.site_id) & \
                    (table.deleted == False)

        return current.db(query).select(table.id,
                                        table.dhash,
                                        table.status,
                                        table.hygiene,
                                        table.layout,
                                        table.public,
                                        table.public_reason,
                                        table.advice,
                                        limitby = (0, 1),
                                        ).first()

    # -------------------------------------------------------------------------
    def add_approval_defaults(self):
        """
            Adds the default approval status for this test station

            Returns:
                org_site_approval Row
        """

        table = current.s3db.org_site_approval

        record_id = table.insert(site_id = self.site_id,
                                 organisation_id = self.organisation_id,
                                 public = "N",
                                 public_reason = "REVISE",
                                 )

        self._approval = self.lookup_approval(table.id == record_id)

        return self._approval

    # -------------------------------------------------------------------------
    def set_facility_type(self):
        """
            Link this test station to the default facility type, if it
            does not have a type yet
        """

        site_id = self.site_id

        db = current.db
        s3db = current.s3db

        fttable = s3db.org_facility_type
        tltable = s3db.org_site_facility_type

        query = (tltable.site_id == site_id) & \
                (tltable.deleted == False)
        if not db(query).select(tltable.id, limitby=(0, 1)).first():
            query = (fttable.name == "Infection Test Station") & \
                    (fttable.deleted == False)
            facility_type = db(query).select(fttable.id, limitby=(0, 1)).first()
            if facility_type:
                tltable.insert(site_id = site_id,
                               facility_type_id = facility_type.id,
                               )


    # -------------------------------------------------------------------------
    def add_facility_code(self):
        """
            Adds a facility code (Test Station ID) for this test station

            returns:
                the facility code
        """

        facility = self.record

        if not facility or facility.code:
            return None

        try:
            uid = int(facility.uuid[9:14], 16) % 1000000
        except (TypeError, ValueError):
            import uuid
            uid = int(uuid.uuid4().urn[9:14], 16) % 1000000

        # Generate code
        import random
        suffix = "".join(random.choice("ABCFGHKLNPRSTWX12456789") for _ in range(3))
        code = "%06d-%s" % (uid, suffix)

        facility.update_record(code=code)

        return code

    # -------------------------------------------------------------------------
    def vhash(self):
        """
            Computes and checks the verification hash for facility details

            Returns:
                tuple (update, vhash), where
                - update is a dict with workflow tag updates
                - vhash is the computed verification hash

            Notes:
                - the verification hash encodes certain facility details, so
                  if those details are changed after approval, then the hash
                  becomes invalid and any previous approval is overturned
                  (=reduced to review-status)
                - if the user is OrgGroupAdmin or Admin, the approval workflow
                  status is kept as-is (i.e. Admins can change details without
                  that impacting the current workflow status)
        """

        db = current.db
        s3db = current.s3db

        approval = self.approval

        # Extract the location, and compute the hash
        ltable = s3db.gis_location
        query = (ltable.id == self.record.location_id) & \
                (ltable.deleted == False)
        location = db(query).select(ltable.id,
                                    ltable.parent,
                                    ltable.addr_street,
                                    ltable.addr_postcode,
                                    limitby = (0, 1),
                                    ).first()
        if location:
            vhash = get_dhash(location.id,
                              location.parent,
                              location.addr_street,
                              location.addr_postcode,
                              )
        else:
            vhash = get_dhash(None, None, None, None)

        # Check against the current dhash
        dhash = approval.dhash
        status = approval.status
        if status == "APPROVED" and dhash and dhash != vhash and \
           not current.auth.s3_has_role("ORG_GROUP_ADMIN"):

            # Relevant data have changed

            # Remove from public list, pending revision/review
            update = {"public": "N"}

            # Status update:
            # - details that were previously approved, must be reviewed
            status = approval.status
            for t in ("hygiene", "layout"):
                value = approval[t]
                if value == "APPROVED":
                    update[t] = "REVIEW"
                    status = "REVIEW"
            if status != approval.status:
                update["status"] = status
        else:
            update = None

        return update, vhash

    # -----------------------------------------------------------------------------
    def approval_workflow(self):
        """
            Determines which site approval tags to update after status change
            by OrgGroupAdmin

            Returns:
                tuple (update, notify)
                    update: dict {tag: value} for update
                    notify: boolean, whether to notify the OrgAdmin
        """

        tags = self.approval
        update, notify = {}, False

        SITE_REVIEW = ("hygiene", "layout")
        all_tags = lambda v: all(tags[k] == v for k in SITE_REVIEW)
        any_tags = lambda v: any(tags[k] == v for k in SITE_REVIEW)

        status = tags.status
        if status == "REVISE":
            if all_tags("APPROVED"):
                update["public"] = "Y"
                update["status"] = "APPROVED"
                notify = True
            elif any_tags("REVIEW"):
                update["public"] = "N"
                update["status"] = "REVIEW"
            else:
                update["public"] = "N"
                # Keep status REVISE

        elif status == "READY":
            update["public"] = "N"
            if all_tags("APPROVED"):
                for k in SITE_REVIEW:
                    update[k] = "REVIEW"
            else:
                for k in SITE_REVIEW:
                    if tags[k] == "REVISE":
                        update[k] = "REVIEW"
            update["status"] = "REVIEW"

        elif status == "REVIEW":
            if all_tags("APPROVED"):
                update["public"] = "Y"
                update["status"] = "APPROVED"
                notify = True
            elif any_tags("REVIEW"):
                update["public"] = "N"
                # Keep status REVIEW
            elif any_tags("REVISE"):
                update["public"] = "N"
                update["status"] = "REVISE"
                notify = True

        elif status == "APPROVED":
            if any_tags("REVIEW"):
                update["public"] = "N"
                update["status"] = "REVIEW"
            elif any_tags("REVISE"):
                update["public"] = "N"
                update["status"] = "REVISE"
                notify = True

        return update, notify

    # -------------------------------------------------------------------------
    def update_approval(self, commissioned=None):
        """
            Updates facility approval workflow tags after status change by
            OrgGroupAdmin, and notify the OrgAdmin of the site when needed

            Args:
                commissioned: whether the organisation has a current
                              commission (will be looked up if omitted)
        """

        approval = self.approval

        # Check if organisation has a current commission
        if commissioned is None:
            organisation_id = self.record.organisation_id
            if organisation_id:
                commissioned = bool(TestProvider(organisation_id).current_commission)

        # Verify record integrity and compute the verification hash
        update, vhash = self.vhash()

        notify = False
        if not update:
            # Integrity check okay => proceed to workflow status
            update, notify = self.approval_workflow()

        # Set/unset reason for public-status
        update_public = update.get("public")
        if update_public == "N":
            # Determine reason from status
            status = update.get("status") or approval.status
            if status == "REVISE":
                update["public_reason"] = "REVISE"
            else:
                update["public_reason"] = "REVIEW"

        elif update_public == "Y" or \
             update_public is None and approval.public == "Y":
            # Check if organisation has a current commission
            if commissioned:
                update["public_reason"] = None
                update["advice"] = None
            else:
                update["public"] = "N"
                update["public_reason"] = "COMMISSION"
                notify = False # commission change already notified

        # Public=N with non-automatic reason must not be overwritten
        if approval.public == "N" and \
           approval.public_reason not in (None, "COMMISSION", "REVISE", "REVIEW"):
            update.pop("public", None)
            update.pop("public_reason", None)
            notify = False # no change happening

        # Detect public-status change
        public_changed = "public" in update and update["public"] != approval.public

        # Set data hash when approved (to detect relevant data changes)
        status = update["status"] if "status" in update else approval.status
        update["dhash"] = vhash if status == "APPROVED" else None

        # Update the record
        if update:
            approval.update_record(**update)
            self.update_approval_history()

        T = current.T

        # Screen message on status change
        if public_changed:
            if approval.public == "Y":
                msg = T("Facility added to public registry")
            else:
                table = current.s3db.org_site_approval
                field = table.public_reason
                msg = T("Facility removed from public registry (%(reason)s)") % \
                      {"reason": field.represent(approval.public_reason)}
            current.response.information = msg

        # Send Notifications
        if notify:
            msg = self.notify_approval_change()
            if msg:
                current.response.warning = \
                    T("Test station could not be notified: %(error)s") % {"error": msg}
            else:
                current.response.flash = \
                    T("Test station notified")

    # -------------------------------------------------------------------------
    def update_approval_history(self):
        """
            Updates site approval history
                - to be called when approval record is updated
        """

        db = current.db
        s3db = current.s3db

        site_id = self.site_id
        approval = self.approval

        htable = s3db.org_site_approval_status
        status_fields = TestStationModel.site_approval_status_fields()

        # Get last entry of history
        htable = s3db.org_site_approval_status
        query = (htable.site_id == site_id) & \
                (htable.deleted == False)
        fields = [htable[fn] for fn in (("id", "timestmp") + status_fields)]
        prev = db(query).select(*fields,
                                limitby = (0, 1),
                                orderby = ~htable.timestmp,
                                ).first()

        # If status has changed...
        if not prev or any(prev[fn] != approval[fn] for fn in status_fields):

            update = {fn: approval[fn] for fn in status_fields}
            update["site_id"] = site_id

            # Update existing history entry or add a new one
            timestmp = current.request.utcnow
            if prev and prev.timestmp == timestmp:
                prev.update_record(**update)
            else:
                update["timestmp"] = timestmp
                htable.insert(**update)

    # -------------------------------------------------------------------------
    def notify_approval_change(self):
        """
            Notifies the OrgAdmin of a test station about the status of
            the review

            Args:
                site_id: the test facility site ID
                tags: the current workflow tags

            Returns:
                error message on error, else None
        """

        db = current.db
        s3db = current.s3db

        # Lookup the facility
        facility = self.record
        if not facility:
            return "Facility not found"

        # Get the organisation ID
        organisation_id = facility.organisation_id
        if not organisation_id:
            return "Organisation not found"

        # Find the OrgAdmin email addresses
        from ..helpers import get_role_emails
        email = get_role_emails("ORG_ADMIN",
                                organisation_id = organisation_id,
                                )
        if not email:
            return "No Organisation Administrator found"

        # Data for the notification email
        app_url = current.deployment_settings.get_base_app_url()
        data = {"name": facility.name,
                "url": "%s/org/organisation/%s/facility/%s" % \
                       (app_url, organisation_id, facility.id),
                }

        approval = self.approval
        status = approval.status

        if status == "REVISE":
            template = "FacilityReview"

            # Add advice
            advice = approval.advice
            data["advice"] = advice if advice else "-"

            # Add explanations for relevant requirements
            review = (("hygiene", "FacilityHygienePlanRequirements"),
                      ("layout", "FacilityLayoutRequirements"),
                      )
            ctable = s3db.cms_post
            ltable = s3db.cms_post_module
            join = ltable.on((ltable.post_id == ctable.id) & \
                             (ltable.module == "org") & \
                             (ltable.resource == "facility") & \
                             (ltable.deleted == False))
            explanations = []
            for tag, requirements in review:
                if approval[tag] == "REVISE":
                    query = (ctable.name == requirements) & \
                            (ctable.deleted == False)
                    row = db(query).select(ctable.body,
                                           join = join,
                                           limitby = (0, 1),
                                           ).first()
                    if row:
                        explanations.append(row.body)
            data["explanations"] = "\n\n".join(explanations) if explanations else "-"

        elif status == "APPROVED":
            template = "FacilityApproved"

        else:
            # No notifications for this status
            return "invalid status"

        # Lookup email address of current user
        from ..notifications import CMSNotifications
        auth = current.auth
        if auth.user:
            cc = CMSNotifications.lookup_contact(auth.user.pe_id)
        else:
            cc = None

        # Send CMS Notification FacilityReview
        return CMSNotifications.send(email,
                                     template,
                                     data,
                                     module = "org",
                                     resource = "facility",
                                     cc = cc,
                                     )

    # -------------------------------------------------------------------------
    # Class methods
    # -------------------------------------------------------------------------
    @classmethod
    def update_all(cls, organisation_id, public=None, reason=None):
        """
            Updates the public-status for all test stations of an
            organisation, to be called when commission status changes

            Args:
                organisation_id: the organisation ID
                public: the new public-status ("Y" or "N")
                reason: the reason(s) for the "N"-status (code|list of codes)

            Notes:
                - can only update those to "Y" which are fully approved
                  and where public_reason matches the given reason(s)
                - reason is required for update to "N"-status
        """

        if public == "N" and not reason:
            raise RuntimeError("reason required")

        db = current.db

        table = current.s3db.org_site_approval
        query = (table.organisation_id == organisation_id) & \
                (table.public != public)

        if public == "Y":
            # Update only to "Y" if fully approved
            for tag in ("status", "hygiene", "layout"):
                query &= (table[tag] == "APPROVED")
            # Update only those which match the specified reason
            if isinstance(reason, (tuple, list, set)):
                query &= (table.public_reason.belongs(reason))
            else:
                query &= (table.public_reason == reason)
            update = {"public": "Y", "public_reason": None}
        else:
            update = {"public": "N", "public_reason": reason}
        query &= (table.deleted == False)

        rows = db(query).select(table.site_id)

        # Update the matching facilities
        num_updated = db(query).update(**update)

        # Update approval histories
        for row in rows:
            cls(row.site_id).update_approval_history()

        return num_updated

    # -------------------------------------------------------------------------
    # Configuration helpers
    # -------------------------------------------------------------------------
    @staticmethod
    def add_site_approval():
        """
            Configures approval workflow as component of org_site
                - for embedding in form
        """

        s3db = current.s3db

        s3db.add_components("org_site",
                            org_site_approval = {"name": "approval",
                                                "joinby": "site_id",
                                                "multiple": False,
                                                },
                            org_site_approval_status = "site_id",
                            jnl_issue = "site_id",
                            )

    # -------------------------------------------------------------------------
    @staticmethod
    def configure_site_approval(resource, role="applicant", record_id=None):
        """
            Configures the approval workflow subform

            Args:
                resource: the org_facility resource
                role: the user's role in the workflow (applicant|approver)
                record_id: the facility record ID

            Returns:
                the list of visible workflow tags [(label, selector)]
        """

        visible_tags = []

        component = resource.components.get("approval")
        if not component:
            return None
        ctable = component.table

        if record_id:
            # Get the current approval status and public-tag
            db = current.db
            s3db = current.s3db
            ftable = s3db.org_facility
            atable = s3db.org_site_approval
            join = ftable.on((ftable.site_id == atable.site_id) & \
                             (ftable.id == record_id))
            query = (atable.deleted == False)
            row = db(query).select(atable.status,
                                   atable.public,
                                   atable.public_reason,
                                   join = join,
                                   limitby = (0, 1),
                                   ).first()

            # Has the site ever been approved?
            htable = s3db.org_site_approval_status
            join = ftable.on((ftable.site_id == htable.site_id) & \
                             (ftable.id == record_id))
            query = (htable.status.belongs("APPROVED", "REVIEW")) & \
                    (htable.deleted == False)
            applied_before = bool(db(query).select(htable.id,
                                                   join = join,
                                                   limitby = (0, 1),
                                                   ).first())
        else:
            row = None
            applied_before = False

        # Configure status-field
        review_tags_visible = False
        if role == "applicant" and row:
            field = ctable.status
            field.readable = True

            visible_tags.append("approval.status")

            # Determine selectable values from current status
            status = row.status
            if status == "REVISE":
                field.writable = True
                # This is the default:
                #field.requires = IS_IN_SET(APPROVAL_STATUS.selectable(True),
                #                           zero = None,
                #                           sort = False,
                #                           )
                review_tags_visible = True
            elif status == "REVIEW":
                field.writable = False
                review_tags_visible = True

            # Once the site has applied for approval, prevent further changes
            # to certain details (must be done by administrator after considering
            # the reasons for the change)
            if applied_before:
                for fn in ("name", "location_id"):
                    ftable[fn].writable = False

        is_approver = role == "approver"

        # Configure review-tags
        review_tags = ("hygiene", "layout")
        for fn in review_tags:
            field = ctable[fn]
            field.default = "REVISE"
            if is_approver:
                field.readable = field.writable = True
            else:
                field.readable = review_tags_visible
                field.writable = False
            if field.readable:
                visible_tags.append("approval.%s" % fn)

        # Configure public-tag
        field = ctable.public
        field.writable = is_approver

        field = ctable.public_reason
        if row and is_approver:
            field.writable = True
            selectable = PUBLIC_REASON.selectable(True,
                                                  current_value = row.public_reason,
                                                  )
            field.requires = IS_EMPTY_OR(IS_IN_SET(selectable,
                                                   sort=False,
                                                   ))

        # Configure advice
        field = ctable.advice
        if is_approver:
            T = current.T
            field.readable = field.writable = True
            field.comment = DIV(_class="tooltip",
                                _title="%s|%s" % (T("Advice"),
                                                  T("Instructions/advice for the test station how to proceed with regard to authorization"),
                                                  ),
                                )
        elif row and row.public != "Y":
            field.readable = True

        visible_tags.extend(["approval.public",
                             "approval.public_reason",
                             "approval.advice",
                             ])

        return visible_tags

# =============================================================================
def get_dhash(*values):
    """
        Produce a data verification hash from the values

        Args:
            values: an (ordered) iterable of values
        Returns:
            the verification hash as string
    """

    import hashlib
    dstr = "#".join([str(v) if v else "***" for v in values])

    return hashlib.sha256(dstr.encode("utf-8")).hexdigest().lower()

# END =========================================================================
