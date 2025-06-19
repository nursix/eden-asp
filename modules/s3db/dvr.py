"""
    Disaster Victim Registration Model

    Copyright: 2012-2022 (c) Sahana Software Foundation

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

__all__ = ("DVRCaseModel",
           "DVRCaseFlagModel",
           "DVRCaseFlagDistributionModel",
           "DVRCaseActivityModel",
           "DVRCaseAllowanceModel",
           "DVRCaseAppointmentModel",
           "DVRResidenceStatusModel",
           "DVRCaseEventModel",
           "DVRNeedsModel",
           "DVRNotesModel",
           "DVRTaskModel",
           "DVRReferralModel",
           "DVRResponseModel",
           "DVRVulnerabilityModel",
           "DVRServiceContactModel",
           "DVRGrantModel",

           "dvr_CaseActivityRepresent",
           "dvr_DocEntityRepresent",
           "dvr_ResponseActionThemeRepresent",
           "dvr_ResponseThemeRepresent",
           "dvr_VulnerabilityRepresent",

           "dvr_get_case",
           "dvr_case_organisation",
           "dvr_case_default_status",
           "dvr_case_status_filter_opts",

           "dvr_configure_vulnerability_types",
           "dvr_configure_case_vulnerabilities",
           "dvr_configure_case_tasks",

           "dvr_case_activity_default_status",
           "dvr_case_activity_form",

           "dvr_response_status_colors",
           "dvr_response_default_type",
           "dvr_response_default_status",
           "dvr_set_response_action_defaults",
           "dvr_configure_case_responses",
           "dvr_configure_inline_responses",

           "dvr_get_household_size",
           "dvr_case_household_size",
           "dvr_group_membership_onaccept",
           "dvr_due_followups",
           "dvr_get_flag_instructions",
           "dvr_rheader",
           "dvr_update_last_seen",
           )

import datetime

from collections import OrderedDict

from gluon import *
from gluon.storage import Storage

from ..core import *

DEFAULT = lambda: None

# =============================================================================
class DVRCaseModel(DataModel):
    """
        Model for DVR Cases

        Allow an individual or household to register to receive
        compensation and/or distributions of relief items
    """

    names = ("dvr_case",
             "dvr_case_id",
             "dvr_case_language",
             "dvr_case_details",
             "dvr_case_status",
             "dvr_case_status_id",
             )

    def model(self):

        T = current.T
        db = current.db
        settings = current.deployment_settings

        crud_strings = current.response.s3.crud_strings
        NONE = current.messages["NONE"]

        configure = self.configure
        define_table = self.define_table
        person_id = self.pr_person_id

        beneficiary = settings.get_dvr_label() # If we add more options in future then == "Beneficiary"
        manage_transferability = settings.get_dvr_manage_transferability()

        # ---------------------------------------------------------------------
        # Case Statuses
        #
        tablename = "dvr_case_status"
        define_table(tablename,
                     Field("workflow_position", "integer",
                           default = 1,
                           label = T("Workflow Position"),
                           requires = IS_INT_IN_RANGE(1, None),
                           comment = DIV(_class = "tooltip",
                                         _title = "%s|%s" % (T("Workflow Position"),
                                                             T("Rank when ordering cases by status"),
                                                             ),
                                         ),
                           ),
                     Field("code", length=64, notnull=True, unique=True,
                           label = T("Status Code"),
                           requires = [IS_NOT_EMPTY(),
                                       IS_LENGTH(64, minsize=1),
                                       IS_NOT_ONE_OF(db,
                                                     "%s.code" % tablename,
                                                     ),
                                       ],
                           comment = DIV(_class = "tooltip",
                                         _title = "%s|%s" % (T("Status Code"),
                                                             T("A unique code to identify the status"),
                                                             ),
                                         ),
                           ),
                     Field("name",
                           label = T("Status"),
                           # Removed to allow single column imports of Cases
                           #requires = IS_NOT_EMPTY(),
                           ),
                     Field("is_default", "boolean",
                           default = False,
                           label = T("Default Status"),
                           represent = s3_yes_no_represent,
                           comment = DIV(_class = "tooltip",
                                         _title = "%s|%s" % (T("Default Status"),
                                                             T("This status applies for new cases unless specified otherwise"),
                                                             ),
                                         ),
                           ),
                     Field("is_closed", "boolean",
                           default = False,
                           label = T("Case Closed"),
                           represent = s3_yes_no_represent,
                           comment = DIV(_class="tooltip",
                                         _title="%s|%s" % (T("Case Closed"),
                                                           T("Cases with this status are closed"),
                                                           ),
                                         ),
                           ),
                     Field("is_not_transferable", "boolean",
                           default = False,
                           label = T("Not Transferable"),
                           represent = s3_yes_no_represent,
                           readable = manage_transferability,
                           writable = manage_transferability,
                           comment = DIV(_class = "tooltip",
                                         _title = "%s|%s" % (T("Not Transferable"),
                                                             T("Cases with this status are not transferable"),
                                                             ),
                                         ),
                           ),
                     CommentsField(
                           comment = DIV(_class = "tooltip",
                                         _title = "%s|%s" % (T("Comments"),
                                                             T("Describe the meaning, reasons and potential consequences of this status"),
                                                             ),
                                         ),
                           ),
                     )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Case Status"),
            title_display = T("Case Status"),
            title_list = T("Case Statuses"),
            title_update = T("Edit Case Status"),
            label_list_button = T("List Case Statuses"),
            label_delete_button = T("Delete Case Status"),
            msg_record_created = T("Case Status added"),
            msg_record_modified = T("Case Status updated"),
            msg_record_deleted = T("Case Status deleted"),
            msg_list_empty = T("No Case Statuses currently registered")
            )

        # Table configuration
        configure(tablename,
                  deduplicate = S3Duplicate(primary = ("code",),
                                            nomatch_require = ("name",),
                                            ignore_deleted = True,
                                            ),
                  onaccept = self.case_status_onaccept,
                  )

        # Foreign Key Template
        represent = S3Represent(lookup=tablename, translate=True)
        status_id = FieldTemplate("status_id", "reference %s" % tablename,
                                  label = T("Status"),
                                  ondelete = "RESTRICT",
                                  represent = represent,
                                  requires = IS_EMPTY_OR(
                                                IS_ONE_OF(db, "dvr_case_status.id",
                                                          represent,
                                                          orderby = "dvr_case_status.workflow_position",
                                                          sort = False,
                                                          )),
                                  sortby = "workflow_position",
                                  )

        # ---------------------------------------------------------------------
        # Cases
        #

        # Case priority options
        # => tuple list to enforce widget order
        # => numeric key so it can be sorted by
        case_priority_opts = ((3, T("High")),
                              (2, T("Medium")),
                              (1, T("Low")),
                              )

        # Consent flag options
        consent_opts = {"N/A": T("n/a"),
                        "Y": T("yes"),
                        "N": T("no"),
                        }

        SITE = settings.get_org_site_label()
        site_represent = self.org_SiteRepresent(show_link=False)

        # Defaults for case assignment
        default_organisation = settings.get_org_default_organisation()
        default_site = settings.get_org_default_site()
        permitted_facilities = current.auth.permitted_facilities(redirect_on_error=False)

        # Household size tracking
        household_size = settings.get_dvr_household_size()
        household_size_writable = household_size and household_size != "auto"

        # Transfer origin/destination tracking
        track_transfer_sites = settings.get_dvr_track_transfer_sites()
        transfer_site_types = settings.get_dvr_transfer_site_types()
        transfer_site_requires = IS_EMPTY_OR(
                                    IS_ONE_OF(db, "org_site.site_id",
                                              site_represent,
                                              sort = True,
                                              filterby = "instance_type",
                                              filter_opts = transfer_site_types,
                                              not_filterby = "obsolete",
                                              not_filter_opts = (True,),
                                              ))
        transfer_site_id = FieldTemplate("transfer_site_id", "reference org_site",
                                         ondelete = "RESTRICT",
                                         requires = transfer_site_requires,
                                         represent = site_represent,
                                         # Enable in template if required
                                         readable = track_transfer_sites,
                                         writable = track_transfer_sites,
                                         )

        tablename = "dvr_case"
        define_table(tablename,
                     self.super_link("doc_id", "doc_entity"),

                     # The primary case beneficiary
                     person_id(represent = self.pr_PersonRepresent(show_link=True),
                               widget = PersonSelector(controller="dvr"),
                               empty = False,
                               ),

                     # Case reference number
                     # - for use in communication with authorities
                     # - if required in addition to primary person ID label
                     Field("reference",
                           label = T("Case Number"),
                           represent = lambda v, row=None: v if v else "-",
                           ),

                     # Case priority and status
                     status_id(empty=False),
                     Field("priority", "integer",
                           default = 2,
                           label = T("Priority"),
                           represent = represent_option(dict(case_priority_opts)),
                           requires = IS_IN_SET(case_priority_opts,
                                                sort = False,
                                                zero = None,
                                                ),
                           ),
                     Field("disclosure_consent", "string", length=8,
                           label = T("Consenting to Data Disclosure"),
                           requires = IS_EMPTY_OR(IS_IN_SET(consent_opts)),
                           represent = represent_option(consent_opts),
                           readable = False,
                           writable = False,
                           ),
                     Field("archived", "boolean",
                           default = False,
                           label = T("Archived"),
                           represent = s3_yes_no_represent,
                           # Enabled in controller:
                           readable = False,
                           writable = False,
                           ),

                     # Case assignment
                     self.org_organisation_id(
                            default = default_organisation,
                            empty = False,
                            comment = None,
                            readable = not default_organisation,
                            writable = not default_organisation,
                            ),
                     self.project_project_id(
                            ondelete = "SET NULL",
                            # Enable in template as required:
                            readable = False,
                            writable = False,
                            ),
                     self.super_link("site_id", "org_site",
                            default = default_site,
                            filterby = "site_id",
                            filter_opts = permitted_facilities,
                            label = SITE,
                            readable = not default_site,
                            writable = not default_site,
                            represent = site_represent,
                            updateable = True,
                            ),
                     self.hrm_human_resource_id(
                            label = T("Assigned to"),
                            comment = None,
                            widget = None,
                            readable = False,
                            writable = False,
                            ),

                     # Basic date fields
                     DateField(label = T("Registration Date"),
                               default = "now",
                               empty = False,
                               ),
                     DateField("closed_on",
                               label = T("Case closed on"),
                               # Automatically set onaccept
                               writable = False,
                               ),

                     # Extended date fields
                     DateField("valid_until",
                               label = T("Valid until"),
                               # Enable in template if required
                               readable = False,
                               writable = False,
                               ),
                     DateField("stay_permit_until",
                               label = T("Stay Permit until"),
                               # Enable in template if required
                               readable = False,
                               writable = False,
                               ),
                     DateTimeField("last_seen_on",
                                   label = T("Last seen on"),
                                   # Enable in template if required
                                   readable = False,
                                   writable = False,
                                   ),

                     # Household size tracking
                     Field("household_size", "integer",
                           default = 1,
                           label = T("Household Size"),
                           requires = IS_EMPTY_OR(IS_INT_IN_RANGE(1, None)),
                           readable = household_size,
                           writable = household_size_writable,
                           comment = DIV(_class="tooltip",
                                         _title="%s|%s" % (T("Household Size"),
                                                           T("Number of persons belonging to the same household"),
                                                           ),
                                         ),
                           ),

                     # Case transfer management
                     transfer_site_id("origin_site_id",
                                      label = T("Admission from"),
                                      ),
                     transfer_site_id("destination_site_id",
                                      label = T("Transfer to"),
                                      ),
                     # "transferable" indicates whether this case is
                     # ready for transfer (=workflow is complete)
                     Field("transferable", "boolean",
                           default = False,
                           label = T("Transferable"),
                           represent = s3_yes_no_represent,
                           readable = manage_transferability,
                           writable = manage_transferability,
                           ),
                     # "household transferable" indicates whether all
                     # open cases in the case group are ready for transfer
                     Field("household_transferable", "boolean",
                           default = False,
                           label = T("Household Transferable"),
                           represent = s3_yes_no_represent,
                           readable = manage_transferability,
                           writable = manage_transferability,
                           ),

                     # Standard comments and meta fields
                     CommentsField(),
                     )

        # CRUD Strings
        if beneficiary:
            label = T("Beneficiary")
            crud_strings[tablename] = Storage(
                label_create = T("Create Beneficiary"),
                title_display = T("Beneficiary Details"),
                title_list = T("Beneficiaries"),
                title_update = T("Edit Beneficiary"),
                label_list_button = T("List Beneficiaries"),
                label_delete_button = T("Delete Beneficiary"),
                msg_record_created = T("Beneficiary added"),
                msg_record_modified = T("Beneficiary updated"),
                msg_record_deleted = T("Beneficiary deleted"),
                msg_list_empty = T("No Beneficiaries found"),
                )

        else:
            label = T("Case")
            crud_strings[tablename] = Storage(
                label_create = T("Create Case"),
                title_display = T("Case Details"),
                title_list = T("Cases"),
                title_update = T("Edit Case"),
                label_list_button = T("List Cases"),
                label_delete_button = T("Delete Case"),
                msg_record_created = T("Case added"),
                msg_record_modified = T("Case updated"),
                msg_record_deleted = T("Case deleted"),
                msg_list_empty = T("No Cases found"),
                )

        # Components
        self.add_components(tablename,
                            dvr_case_activity = "case_id",
                            dvr_case_details = {"joinby": "case_id",
                                                "multiple": False,
                                                },
                            dvr_case_event = "case_id",
                            dvr_need =  {"link": "dvr_case_need",
                                         "joinby": "case_id",
                                         "key": "need_id",
                                         },
                            )

        # Table configuration
        configure(tablename,
                  deduplicate = S3Duplicate(primary=("person_id",),
                                            secondary=("organisation_id",),
                                            ),
                  #report_options = report_options,
                  onvalidation = self.case_onvalidation,
                  create_onaccept = self.case_create_onaccept,
                  update_onaccept = self.case_onaccept,
                  super_entity = ("doc_entity",),
                  )

        # Foreign Key Template
        represent = S3Represent(lookup=tablename, fields=("reference",))
        case_id = FieldTemplate("case_id", "reference %s" % tablename,
                                label = label,
                                ondelete = "RESTRICT",
                                represent = represent,
                                requires = IS_EMPTY_OR(
                                                IS_ONE_OF(db, "dvr_case.id",
                                                          represent,
                                                          )),
                                )

        # ---------------------------------------------------------------------
        # Case Language: languages that can be used to communicate with
        #                a case beneficiary
        #
        languages = settings.get_dvr_case_languages()

        # Quality/Mode of communication:
        lang_quality_opts = (("N", T("native")),
                             ("F", T("fluent")),
                             ("S", T("simplified/slow")),
                             ("W", T("written-only")),
                             ("I", T("interpreter required")),
                             )

        tablename = "dvr_case_language"
        define_table(tablename,
                     person_id(empty = False,
                               ondelete = "CASCADE",
                               ),
                     LanguageField(select=languages),
                     Field("quality",
                           default = "N",
                           label = T("Quality/Mode"),
                           represent = represent_option(dict(lang_quality_opts)),
                           requires = IS_IN_SET(lang_quality_opts,
                                                sort = False,
                                                zero = None,
                                                ),
                           ),
                     CommentsField(),
                     )

        # ---------------------------------------------------------------------
        # Case Details: extended attributes for DVR cases
        #
        tablename = "dvr_case_details"
        define_table(tablename,
                     case_id(empty = False,
                             ondelete = "CASCADE",
                             ),
                     person_id(empty = False,
                               ondelete = "CASCADE",
                               ),
                     Field("registered", "boolean",
                           default = True,
                           label = T("Officially Registered"),
                           represent = s3_yes_no_represent,
                           ),
                     Field("enrolled_in_school", "boolean",
                           default = False,
                           label = T("Enrolled in Public School"),
                           represent = s3_yes_no_represent,
                           ),
                     DateField("arrival_date",
                               label = T("Arrival Date"),
                               ),
                     Field("lodging", length=128,
                           label = T("Lodging"),
                           represent = lambda v: v if v else NONE,
                           requires = IS_LENGTH(128),
                           ),
                     DateField("on_site_from",
                               label = T("On-site from"),
                               ),
                     DateField("on_site_until",
                               label = T("On-site until"),
                               ),
                     Field("referred_by", length=128,
                           label = T("Referred by"),
                           represent = lambda v: v if v else NONE,
                           requires = IS_LENGTH(128),
                           ),
                     Field("referred_to", length=128,
                           label = T("Referred to"),
                           represent = lambda v: v if v else NONE,
                           requires = IS_LENGTH(128),
                           ),
                     self.dvr_referral_type_id(),
                     self.dvr_referral_type_id(
                         "activity_referral_type_id",
                         label = T("Referred to Group Activities by"),
                         ),
                     )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return {"dvr_case_id": case_id,
                "dvr_case_status_id": status_id,
                }

    # -------------------------------------------------------------------------
    def defaults(self):
        """ Safe defaults for names in case the module is disabled """

        dummy = FieldTemplate.dummy

        return {"dvr_case_id": dummy("case_id"),
                "dvr_case_status_id": dummy("status_id"),
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def case_status_onaccept(form):
        """
            Onaccept routine for case statuses:
            - only one status can be the default

            Args:
                form: the FORM
        """

        form_vars = form.vars
        try:
            record_id = form_vars.id
        except AttributeError:
            record_id = None
        if not record_id:
            return

        # If this status is the default, then set is_default-flag
        # for all other statuses to False:
        if "is_default" in form_vars and form_vars.is_default:
            table = current.s3db.dvr_case_status
            db = current.db
            db(table.id != record_id).update(is_default = False)

    # -------------------------------------------------------------------------
    @staticmethod
    def case_onvalidation(form):
        """
            Case form validation:
                - make sure case numbers are unique within the (root) organisation

            Args:
                form: the FORM
        """

        db = current.db
        s3db = current.s3db
        settings = current.deployment_settings

        # Read form data
        record_id = get_form_record_id(form)

        try:
            reference = form.vars.reference
        except AttributeError:
            reference = None

        if reference and settings.get_dvr_case_reference_unique():

            # Make sure the case reference is unique within the (root) organisation
            table = s3db.dvr_case
            data = get_form_record_data(form, table, ["organisation_id"])
            organisation_id = data.get("organisation_id")

            # Use root organisation for cases of all branches
            if current.deployment_settings.get_org_branches():
                otable = s3db.org_organisation
                query = (otable.id == organisation_id)
                row = db(query).select(otable.root_organisation,
                                       limitby = (0, 1),
                                       ).first()
                root_org = row.root_organisation if row else organisation_id
                if root_org:
                    organisation_id = root_org

            # Case duplicate query
            dquery = (table.reference == reference)
            if record_id:
                dquery &= (table.id != record_id)
            dquery &= (table.organisation_id == organisation_id) & \
                      (table.deleted == False)

            # Is there a record with the same reference?
            row = db(dquery).select(table.id, limitby=(0, 1)).first()
            if row:
                msg = current.T("This Case Number is already in use")
                form.errors.reference = msg

    # -------------------------------------------------------------------------
    @classmethod
    def case_create_onaccept(cls, form):
        """
            Wrapper for case_onaccept when called during create
            rather than update

            Args:
                form: the FORM
        """

        cls.case_onaccept(form, create=True)

    # -------------------------------------------------------------------------
    @staticmethod
    def case_onaccept(form, create=False):
        """
            Case onaccept routine:
                - set/remove closed-on date according to status
                - auto-create active appointments
                - count household size for new cases

            Args:
                form: the FORM
                create: perform additional actions for new cases
        """

        db = current.db
        s3db = current.s3db

        settings = current.deployment_settings

        # Read form data
        form_vars = form.vars
        if "id" in form_vars:
            record_id = form_vars.id
        elif hasattr(form, "record_id"):
            record_id = form.record_id
        else:
            return

        # Get the case
        ctable = s3db.dvr_case
        stable = s3db.dvr_case_status
        left = stable.on(stable.id == ctable.status_id)
        query = (ctable.id == record_id)
        row = db(query).select(ctable.id,
                               ctable.organisation_id,
                               ctable.person_id,
                               ctable.closed_on,
                               stable.is_closed,
                               left = left,
                               limitby = (0, 1),
                               ).first()
        if not row:
            return
        case = row.dvr_case

        # Update the realm entity for the person
        # NOTE this is required because necessarily, the person record
        #      is written before the case record; so it cannot inherit
        #      the case realm unless we explicitly force an update here:
        current.auth.set_realm_entity(s3db.pr_person,
                                      case.person_id,
                                      force_update = True,
                                      )

        # Update closed_on date when status is closed
        if row.dvr_case_status.is_closed:
            if not case.closed_on:
                case.update_record(closed_on = current.request.utcnow.date())
        elif case.closed_on:
            case.update_record(closed_on = None)

        person_id = case.person_id
        organisation_id = case.organisation_id

        # Auto-create appointments
        org_specific = settings.get_dvr_appointment_types_org_specific()
        if not org_specific or org_specific and organisation_id:

            # Get types for which there is no appointment in this case yet
            atable = s3db.dvr_case_appointment
            ttable = s3db.dvr_case_appointment_type
            left = atable.on((atable.type_id == ttable.id) &
                             (atable.person_id == person_id) &
                             (atable.deleted == False))
            query = (atable.id == None) & (ttable.autocreate == True)
            if org_specific:
                query &= (ttable.organisation_id == organisation_id)
            query &= (ttable.deleted == False)
            rows = db(query).select(ttable.id, left=left)

            # Create the missing appointments with defaults
            set_record_owner = current.auth.s3_set_record_owner
            for row in rows:
                appointment = {"case_id": case.id,
                               "person_id": person_id,
                               "type_id": row.id,
                               }
                appointment["id"] = atable.insert(**appointment)
                s3db.update_super(atable, appointment)
                set_record_owner(atable, appointment)
                s3db.onaccept(atable, appointment, method="create")

        if create and \
           current.deployment_settings.get_dvr_household_size() == "auto":
            # Count household size for newly created cases, in order
            # to catch pre-existing case group memberships
            gtable = s3db.pr_group
            mtable = s3db.pr_group_membership
            query = ((mtable.person_id == person_id) & \
                     (mtable.deleted == False) & \
                     (gtable.id == mtable.group_id) & \
                     (gtable.group_type == 7))
            rows = db(query).select(gtable.id)
            for row in rows:
                dvr_case_household_size(row.id)

# =============================================================================
class DVRCaseFlagModel(DataModel):
    """ Model for Case Flags """

    names = ("dvr_case_flag",
             "dvr_case_flag_case",
             "dvr_case_flag_id",
             )

    def model(self):

        T = current.T
        db = current.db
        settings = current.deployment_settings

        crud_strings = current.response.s3.crud_strings

        configure = self.configure
        define_table = self.define_table

        flags_org_specific = settings.get_dvr_case_flags_org_specific()
        manage_transferability = settings.get_dvr_manage_transferability()

        # ---------------------------------------------------------------------
        # Case Flags
        #
        tablename = "dvr_case_flag"
        define_table(tablename,
                     self.org_organisation_id(
                         comment = None,
                         readable = flags_org_specific,
                         writable = flags_org_specific,
                         ),
                     Field("name",
                           label = T("Name"),
                           requires = [IS_NOT_EMPTY(), IS_LENGTH(512, minsize=1)],
                           ),
                     # TODO rename into advise_at_reception
                     Field("advise_at_check_in", "boolean",
                           default = False,
                           label = T("Advice at Check-in"),
                           represent = s3_yes_no_represent,
                           comment = DIV(_class = "tooltip",
                                         _title = "%s|%s" % (T("Advice at Check-in"),
                                                             T("Show handling instructions at check-in"),
                                                             ),
                                         ),
                           ),
                     # TODO deprecate in favor of single field
                     Field("advise_at_check_out", "boolean",
                           default = False,
                           label = T("Advice at Check-out"),
                           represent = s3_yes_no_represent,
                           comment = DIV(_class = "tooltip",
                                         _title = "%s|%s" % (T("Advice at Check-out"),
                                                             T("Show handling instructions at check-out"),
                                                             ),
                                         ),
                           ),
                     # TODO rename into advice_at_checkpoint
                     Field("advise_at_id_check", "boolean",
                           default = False,
                           label = T("Advice at ID Check"),
                           represent = s3_yes_no_represent,
                           comment = DIV(_class = "tooltip",
                                         _title = "%s|%s" % (T("Advice at ID Check"),
                                                             T("Show handling instructions at ID checks (e.g. for event registration, payments)"),
                                                             ),
                                         ),
                           ),
                     Field("instructions", "text",
                           label = T("Instructions"),
                           represent = s3_text_represent,
                           comment = DIV(_class = "tooltip",
                                         _title = "%s|%s" % (T("Instructions"),
                                                             T("Instructions for handling of the case"),
                                                             ),
                                         ),
                           ),
                     # TODO rename into deny_entry
                     Field("deny_check_in", "boolean",
                           default = False,
                           label = T("Deny Check-in"),
                           represent = s3_yes_no_represent,
                           comment = DIV(_class = "tooltip",
                                         _title = "%s|%s" % (T("Deny Check-in"),
                                                             T("Deny the person to check-in when this flag is set"),
                                                             ),
                                         ),
                           ),
                     # TODO rename into deny_leaving
                     Field("deny_check_out", "boolean",
                           default = False,
                           label = T("Deny Check-out"),
                           represent = s3_yes_no_represent,
                           comment = DIV(_class = "tooltip",
                                         _title = "%s|%s" % (T("Deny Check-out"),
                                                             T("Deny the person to check-out when this flag is set"),
                                                             ),
                                         ),
                           ),
                     # TODO rename into payments_suspended
                     Field("allowance_suspended", "boolean",
                           default = False,
                           label = T("Allowance Suspended"),
                           represent = s3_yes_no_represent,
                           # TODO setting to control this field
                           readable = False,
                           writable = False,
                           comment = DIV(_class = "tooltip",
                                         _title = "%s|%s" % (T("Allowance Suspended"),
                                                             T("Person shall not receive allowance payments when this flag is set"),
                                                             ),
                                         ),
                           ),
                     # TODO deprecate
                     Field("is_not_transferable", "boolean",
                           default = False,
                           label = T("Not Transferable"),
                           represent = s3_yes_no_represent,
                           readable = manage_transferability,
                           writable = manage_transferability,
                           comment = DIV(_class = "tooltip",
                                         _title = "%s|%s" % (T("Not Transferable"),
                                                             T("Cases with this flag are not transferable"),
                                                             ),
                                         ),
                           ),
                     Field("is_external", "boolean",
                           default = False,
                           label = T("External"),
                           represent = s3_yes_no_represent,
                           comment = DIV(_class = "tooltip",
                                         _title = "%s|%s" % (T("External"),
                                                             T("This flag indicates that the person is currently accommodated/being held externally (e.g. in Hospital or with Police)"),
                                                             ),
                                         ),
                           ),
                     Field("color",
                           requires = IS_EMPTY_OR(IS_HTML_COLOUR()),
                           widget = S3ColorPickerWidget(),
                           # TODO Disabled until represent method is ready
                           readable = False,
                           writable = False,
                           ),
                     # TODO Ambiguous field - deprecate or move into relevant template
                     Field("nostats", "boolean",
                           default = False,
                           label = T("Exclude from Reports"),
                           represent = s3_yes_no_represent,
                           readable = False,
                           writable = False,
                           comment = DIV(_class = "tooltip",
                                         _title = "%s|%s" % (T("Exclude from Reports"),
                                                             T("Exclude cases with this flag from certain reports"),
                                                             ),
                                         ),
                           ),
                     CommentsField(),
                     )

        # List fields
        list_fields = ["id",
                       #"organisation_id",
                       "name",
                       "advise_at_check_in",
                       "advise_at_check_out",
                       "advise_at_id_check",
                       "deny_check_in",
                       "deny_check_out",
                       "is_external",
                       "comments",
                       ]
        if flags_org_specific:
            list_fields.insert(1, "organisation_id")

        # Filter widgets
        filter_widgets = [TextFilter(["name",
                                      "instructions",
                                      "comments",
                                      ],
                                     label = T("Search"),
                                     ),
                           OptionsFilter("organisation_id",
                                         hidden = True,
                                         ),
                          ]

        # Table configuration
        configure(tablename,
                  filter_widgets = filter_widgets,
                  list_fields = list_fields,
                  update_realm = True,
                  deduplicate = S3Duplicate(primary = ("name",),
                                            secondary = ("organisation_id",),
                                            ignore_deleted = True,
                                            ),
                  )

        # CRUD Strings
        ADD_FLAG = T("Create Case Flag")
        crud_strings[tablename] = Storage(
            label_create = ADD_FLAG,
            title_display = T("Case Flag Details"),
            title_list = T("Case Flags"),
            title_update = T("Edit Case Flag"),
            label_list_button = T("List Case Flags"),
            label_delete_button = T("Delete Case Flag"),
            msg_record_created = T("Case Flag added"),
            msg_record_modified = T("Case Flag updated"),
            msg_record_deleted = T("Case Flag deleted"),
            msg_list_empty = T("No Case Flags found"),
            )

        # Foreign Key Template
        represent = S3Represent(lookup=tablename, translate=True)
        flag_id = FieldTemplate("flag_id", "reference %s" % tablename,
                                label = T("Case Flag"),
                                ondelete = "RESTRICT",
                                represent = represent,
                                requires = IS_EMPTY_OR(
                                                IS_ONE_OF(db, "dvr_case_flag.id",
                                                          represent,
                                                          )),
                                comment=PopupLink(c = "dvr",
                                                  f = "case_flag",
                                                  title = ADD_FLAG,
                                                  tooltip = T("Choose the flag from the drop-down, or click the link to create a new flag"),
                                                  ),
                                )

        # ---------------------------------------------------------------------
        # Link table Case <=> Flag
        #
        tablename = "dvr_case_flag_case"
        define_table(tablename,
                     self.pr_person_id(empty = False,
                                       ondelete = "CASCADE",
                                       ),
                     flag_id(empty = False,
                             ondelete = "CASCADE",
                             ),
                     )

        # Table configuration
        configure(tablename,
                  deduplicate = S3Duplicate(primary = ("person_id",
                                                       "flag_id",
                                                       ),
                                            ),
                  )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return {"dvr_case_flag_id": flag_id,
                }

    # -------------------------------------------------------------------------
    def defaults(self):
        """ Safe defaults for names in case the module is disabled """

        return {"dvr_case_flag_id": FieldTemplate.dummy("flag_id"),
                }

# =============================================================================
class DVRCaseFlagDistributionModel(DataModel):
    """
        Model to control applicability of supply item distribution sets
        by case flags
    """

    names = ("dvr_distribution_flag_debarring",
             "dvr_distribution_flag_required",
             )

    def model(self):

        define_table = self.define_table

        case_flag_id = self.dvr_case_flag_id
        distribution_set_id = self.supply_distribution_set_id

        # ---------------------------------------------------------------------
        # Flags required for a distribution set
        #
        tablename = "dvr_distribution_flag_required"
        define_table(tablename,
                     distribution_set_id(),
                     case_flag_id(
                         empty = False,
                         ondelete = "CASCADE",
                         comment = None,
                         ),
                     )

        # ---------------------------------------------------------------------
        # Flags debarring from a distribution set
        #
        tablename = "dvr_distribution_flag_debarring"
        define_table(tablename,
                     distribution_set_id(),
                     case_flag_id(
                         empty = False,
                         ondelete = "CASCADE",
                         comment = None,
                         ),
                     )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        #return {}

# =============================================================================
class DVRNeedsModel(DataModel):
    """ Model for Needs """

    names = ("dvr_need",
             "dvr_need_id",
             "dvr_case_need",
             )

    def model(self):

        T = current.T
        db = current.db

        crud_strings = current.response.s3.crud_strings

        define_table = self.define_table
        configure = self.configure

        # ---------------------------------------------------------------------
        # Needs
        #
        tablename = "dvr_need"
        define_table(tablename,
                     Field("name",
                           label = T("Name"),
                           requires = [IS_NOT_EMPTY(), IS_LENGTH(512, minsize=1)],
                           ),
                     Field("code",
                           label = T("Code"),
                           requires = IS_EMPTY_OR(IS_LENGTH(64, minsize=1)),
                           represent = lambda v, row=None: v if v else "-",
                           # Enable in template as required:
                           readable = False,
                           writable = False,
                           ),
                     # Activate in template as needed:
                     self.org_organisation_id(readable = False,
                                              writable = False,
                                              ),
                     Field("protection", "boolean",
                           default = False,
                           label = T("Protection Need"),
                           represent = s3_yes_no_represent,
                           readable = False,
                           writable = False,
                           ),
                     CommentsField(),
                     )

        # Table configuration
        configure(tablename,
                  deduplicate = S3Duplicate(primary = ("name",),
                                            secondary = ("organisation_id",),
                                            ),
                  )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Need Type"),
            title_display = T("Need Type Details"),
            title_list = T("Need Types"),
            title_update = T("Edit Need Type"),
            label_list_button = T("List Need Types"),
            label_delete_button = T("Delete Need Type"),
            msg_record_created = T("Need Type added"),
            msg_record_modified = T("Need Type updated"),
            msg_record_deleted = T("Need Type deleted"),
            msg_list_empty = T("No Need Types found"),
            )

        # Foreign Key Template
        represent = S3Represent(lookup=tablename, translate=True)
        need_id = FieldTemplate("need_id", "reference %s" % tablename,
                                label = T("Need Type"),
                                ondelete = "RESTRICT",
                                represent = represent,
                                requires = IS_EMPTY_OR(
                                                IS_ONE_OF(db, "dvr_need.id",
                                                          represent,
                                                          )),
                                )

        # ---------------------------------------------------------------------
        # Link table Case <=> Need
        #
        tablename = "dvr_case_need"
        define_table(tablename,
                     self.dvr_case_id(empty = False,
                                      ondelete = "CASCADE",
                                      ),
                     need_id(empty = False,
                             ondelete = "CASCADE",
                             ),
                     )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return {"dvr_need_id": need_id,
                }

    # -------------------------------------------------------------------------
    def defaults(self):
        """ Safe defaults for names in case the module is disabled """

        return {"dvr_need_id": FieldTemplate.dummy("need_id"),
                }

# =============================================================================
class DVRTaskModel(DataModel):
    """ To-Do-lists for case files """

    names = ("dvr_task",
             "dvr_task_category",
             "dvr_task_status",
             )

    def model(self):

        T = current.T
        #db = current.db

        crud_strings = current.response.s3.crud_strings

        define_table = self.define_table

        # ---------------------------------------------------------------------
        # Task Status
        #
        task_status = (("NEW", T("Pending")),
                       ("PROC", T("In Progress")),
                       ("NA", T("Not Actionable")),
                       ("DONE", T("Done")),
                       ("DEF", T("Deferred")),
                       ("OBS", T("Obsolete")),
                       )

        status_represent = S3PriorityRepresent(task_status,
                                               {"NEW": "lightblue",
                                                "PROC": "amber",
                                                "NA": "red",
                                                "DONE": "green",
                                                "DEF": "grey",
                                                "OBS": "black",
                                                }).represent

        # ---------------------------------------------------------------------
        # Task Category
        #
        task_category = {"A": T("Administrative"),
                         "C": T("Counseling"),
                         "S": T("Supply"),
                         "H": T("Health"),
                         }

        # ---------------------------------------------------------------------
        # Tasks
        #
        tablename = "dvr_task"
        define_table(tablename,
                     self.pr_person_id(
                         comment = False,
                         writable = False,
                         ),
                     self.dvr_case_id(
                         readable = False,
                         writable = False,
                         ),
                     self.org_organisation_id(
                         readable = False,
                         writable = False,
                         ),
                     DateField(
                         default = "now",
                         label = T("Date"),
                         # Enable in template if/as required:
                         readable = False,
                         writable = False,
                         ),
                     Field("category",
                           label = T("Category"),
                           default = "A",
                           requires = IS_IN_SET(task_category, zero=None),
                           represent = represent_option(task_category),
                           readable = False,
                           writable = False,
                           ),
                     Field("name",
                           label = T("Subject"),
                           requires = IS_NOT_EMPTY(),
                           represent = lambda v, row=None: v if v else "-",
                           ),
                     CommentsField("description",
                                   label = T("Details"),
                                   comment = None,
                                   ),
                     Field("status",
                           default = "NEW",
                           requires = IS_IN_SET(task_status,
                                                sort = False,
                                                zero = None,
                                                ),
                           represent = status_represent,
                           ),
                     self.hrm_human_resource_id(
                         label = T("Contact Person for Inquiries"),
                         ),
                     DateField("due_date",
                               label = T("Date Due"),
                               represent = self.due_date_represent,
                               ),
                     # Priority ranking (see task_ondefine.due_date_dt_orderby)
                     Field("rank", "integer",
                           default = 1,
                           # set automatically onaccept
                           readable = False,
                           writable = False,
                           ),
                     DateTimeField("status_date",
                                   readable = False,
                                   writable = False,
                                   ),
                     Field("previous_status",
                           readable = False,
                           writable = False,
                           ),
                     DateTimeField("closed_on",
                                   readable = False,
                                   writable = False,
                                   ),
                     CommentsField(),
                     on_define = self.task_ondefine,
                     )

        # Table configuration
        self.configure(tablename,
                       onaccept = self.task_onaccept,
                       )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Task"),
            title_display = T("Task Details"),
            title_list = T("Tasks"),
            title_update = T("Edit Task"),
            label_list_button = T("List Tasks"),
            label_delete_button = T("Delete Task"),
            msg_record_created = T("Task added"),
            msg_record_modified = T("Task updated"),
            msg_record_deleted = T("Task deleted"),
            msg_list_empty = T("No Tasks found"),
            )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return {"dvr_task_category": task_category,
                "dvr_task_status": task_status,
                }

    # -------------------------------------------------------------------------
    def defaults(self):
        """ Safe defaults for names in case the module is disabled """

        return {"dvr_task_category": {},
                "dvr_task_status": {},
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def task_ondefine(table):
        """
            Ondefine-routine for task table:
            - configure special datatable orderby-rule for due date

            Args:
                table: the dvr_task table
        """

        def due_date_dt_orderby(field, direction, orderby, left_joins):
            """
                Sorting the datatable by due-date maintains a constant
                order of status groupings (using the sorting priority
                which is set onaccept)
            """

            sorting = {"table": field.tablename,
                       "direction": direction,
                       }
            orderby.append("%(table)s.rank asc,%(table)s.due_date%(direction)s,%(table)s.created_on%(direction)s" % sorting)

        table.due_date.represent.dt_orderby = due_date_dt_orderby

    # -------------------------------------------------------------------------
    @staticmethod
    def task_onaccept(form):
        """
            Onaccept-routine for tasks
            - detect status change and set status_date / closed_on
            - set case_id and organisation_id
            - set sorting priority (combined ranking by status+due-date)
        """

        # Get form record ID
        record_id = get_form_record_id(form)
        if not record_id:
            return

        db = current.db
        s3db = current.s3db

        # Re-read record
        table = s3db.dvr_task
        query = (table.id == record_id) & \
                (table.deleted == False)
        record = db(query).select(table.id,
                                  table.person_id,
                                  table.case_id,
                                  table.organisation_id,
                                  table.status,
                                  table.due_date,
                                  table.previous_status,
                                  table.status_date,
                                  table.closed_on,
                                  limitby = (0, 1),
                                  ).first()
        if not record:
            return

        update = {"previous_status": record.status,
                  # System-side update
                  "modified_on": table.modified_on,
                  "modified_by": table.modified_by,
                  }

        # Set transition dates
        now = current.request.utcnow
        if record.status != record.previous_status:
            update["status_date"] = now
        if record.status == "DONE":
            if not record.closed_on:
                update["closed_on"] = now
        elif record.closed_on:
            update["closed_on"] = None

        # Set case and organisation
        if not record.case_id:
            case = dvr_get_case(record.person_id, archived=False)
            update["case_id"] = case.id
            update["organisation_id"] = case.organisation_id
        elif not record.organisation_id:
            ctable = s3db.dvr_case
            case = db(ctable.id==record.case_id).select(ctable.id,
                                                        ctable.organisation_id,
                                                        limitby = (0, 1),
                                                        ).first()
            update["organisation_id"] = case.organisation_id

        # Set priority ranking (1=top)
        # - actionable tasks first, closed tasks last
        status_priority = {"NEW": 1,
                           "PROC": 1,
                           "NA": 3,
                           "DONE": 5,
                           "DEF": 7,
                           "OBS": 7,
                           }
        rank = status_priority.get(record.status, 9)
        # - tasks with due-date rank higher than those without
        if not record.due_date:
            rank += 1
        update["rank"] = rank

        record.update_record(**update)

    # -------------------------------------------------------------------------
    @staticmethod
    def due_date_represent(value, row=None):
        """
            Represent due-date with color marking indicating how close
            the due date is

            Args:
                value: the field value
                row: the Row (unused, for framework compatibility)

            Returns:
                SPAN.due-date
        """

        due = None
        if value:
            dtstr = S3DateTime.date_represent(value, utc=True)
            distance = value - datetime.datetime.utcnow().date()
            if distance.days <= 1:
                due = "due-now"
            elif distance.days <= 4:
                due = "due-next"
            elif distance.days <= 8:
                due = "due-soon"
        else:
            dtstr = "-"

        output = SPAN(dtstr, _class="due-date")
        if due:
            output.add_class(due)
        return output

# =============================================================================
class DVRNotesModel(DataModel):
    """
        Simple notes for case files
    """

    names = ("dvr_note_type",
             "dvr_note",
             )

    def model(self):

        T = current.T
        db = current.db

        crud_strings = current.response.s3.crud_strings

        define_table = self.define_table

        # ---------------------------------------------------------------------
        # Note Types
        #
        tablename = "dvr_note_type"
        define_table(tablename,
                     Field("name", length=128, unique=True,
                           label = T("Name"),
                           requires = [IS_NOT_EMPTY(),
                                       IS_LENGTH(128, minsize=1),
                                       IS_NOT_ONE_OF(db,
                                                     "dvr_note_type.name",
                                                     ),
                                       ],
                           ),
                     Field("is_task", "boolean",
                           label = T("Is Task"),
                           default = False,
                           ),
                     CommentsField(),
                     )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Note Type"),
            title_display = T("Note Type Details"),
            title_list = T("Note Types"),
            title_update = T("Edit Note Type"),
            label_list_button = T("List Note Types"),
            label_delete_button = T("Delete Note Type"),
            msg_record_created = T("Note Type added"),
            msg_record_modified = T("Note Type updated"),
            msg_record_deleted = T("Note Type deleted"),
            msg_list_empty = T("No Note Types found"),
            )

        # Table configuration
        #self.configure(tablename,
        #               # Not needed as unique=True
        #               deduplicate = S3Duplicate(),
        #               )

        # Foreign Key Template
        represent = S3Represent(lookup=tablename, translate=True)
        note_type_id = FieldTemplate("note_type_id", "reference %s" % tablename,
                                     label = T("Note Type"),
                                     ondelete = "RESTRICT",
                                     represent = represent,
                                     requires = IS_EMPTY_OR(
                                                    IS_ONE_OF(db, "dvr_note_type.id",
                                                              represent,
                                                              )),
                                     )

        # ---------------------------------------------------------------------
        # Notes
        #
        note_status = (("CUR", T("Current")),
                       ("OBS", T("Obsolete")),
                       )
        status_represent = S3PriorityRepresent(note_status,
                                               {"CUR": "lightblue",
                                                "OBS": "grey",
                                                }).represent
        tablename = "dvr_note"
        define_table(tablename,
                     # Uncomment if needed for the Case perspective
                     #self.dvr_case_id(empty = False,
                     #                 ondelete = "CASCADE",
                     #                 ),
                     self.pr_person_id(empty = False,
                                       ondelete = "CASCADE",
                                       ),
                     note_type_id(empty=False),
                     DateField(default = "now",
                               ),
                     CommentsField("note",
                                   label = T("Note"),
                                   comment = None,
                                   ),
                     Field("status",
                           label = T("Status"),
                           default = "CUR",
                           requires = IS_IN_SET(note_status, sort=False, zero=None),
                           represent = status_represent,
                           readable = False,
                           writable = False,
                           ),
                     )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Note"),
            title_display = T("Note Details"),
            title_list = T("Notes"),
            title_update = T("Edit Note"),
            label_list_button = T("List Notes"),
            label_delete_button = T("Delete Note"),
            msg_record_created = T("Note added"),
            msg_record_modified = T("Note updated"),
            msg_record_deleted = T("Note deleted"),
            msg_list_empty = T("No Notes found"),
            )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        # return {}

# =============================================================================
class DVRReferralModel(DataModel):
    """
        Data model for case referrals (both incoming and outgoing)
    """

    names = ("dvr_referral_type",
             "dvr_referral_type_id",
             )

    def model(self):

        T = current.T
        db = current.db

        crud_strings = current.response.s3.crud_strings

        # ---------------------------------------------------------------------
        # Referral Types (how cases are admitted)
        #
        tablename = "dvr_referral_type"
        self.define_table(tablename,
                          Field("name",
                                label = T("Name"),
                                requires = [IS_NOT_EMPTY(), IS_LENGTH(512, minsize=1)],
                                ),
                          CommentsField(),
                          )

        # Table configuration
        self.configure(tablename,
                       deduplicate = S3Duplicate(),
                       )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Referral Type"),
            title_display = T("Referral Type Details"),
            title_list = T("Referral Types"),
            title_update = T("Edit Referral Type"),
            label_list_button = T("List Referral Types"),
            label_delete_button = T("Delete Referral Type"),
            msg_record_created = T("Referral Type added"),
            msg_record_modified = T("Referral Type updated"),
            msg_record_deleted = T("Referral Type deleted"),
            msg_list_empty = T("No Referral Types found"),
            )

        # Foreign Key Template
        represent = S3Represent(lookup=tablename, translate=True)
        referral_type_id = FieldTemplate("referral_type_id",
                                         "reference %s" % tablename,
                                         label = T("Type of Referral"),
                                         ondelete = "RESTRICT",
                                         represent = represent,
                                         requires = IS_EMPTY_OR(
                                                        IS_ONE_OF(db,
                                                                  "%s.id" % tablename,
                                                                  represent,
                                                                  )),
                                         )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return {"dvr_referral_type_id": referral_type_id,
                }

    # -------------------------------------------------------------------------
    def defaults(self):
        """ Safe defaults for names in case the module is disabled """

        return {"dvr_referral_type_id": FieldTemplate.dummy("referral_type_id"),
                }

# =============================================================================
class DVRResponseModel(DataModel):
    """ Model representing responses to case needs """

    names = ("dvr_response_action",
             "dvr_response_action_id",
             "dvr_response_action_theme",
             "dvr_response_status",
             "dvr_response_theme",
             "dvr_response_type",
             )

    def model(self):

        T = current.T

        db = current.db
        s3 = current.response.s3
        settings = current.deployment_settings

        crud_strings = s3.crud_strings

        define_table = self.define_table
        configure = self.configure

        hierarchical_response_types = settings.get_dvr_response_types_hierarchical()

        themes_per_org = settings.get_dvr_response_themes_org_specific()
        themes_sectors = settings.get_dvr_response_themes_sectors()
        themes_needs = settings.get_dvr_response_themes_needs()

        case_activity_id = self.dvr_case_activity_id

        NONE = current.messages["NONE"]

        # ---------------------------------------------------------------------
        # Response Themes
        #
        tablename = "dvr_response_theme"
        define_table(tablename,
                     self.org_organisation_id(readable = themes_per_org,
                                              writable = themes_per_org,
                                              comment = None,
                                              ),
                     Field("name",
                           label = T("Theme"),
                           requires = [IS_NOT_EMPTY(), IS_LENGTH(512, minsize=1)],
                           ),
                     self.dvr_need_id(readable = themes_needs,
                                      writable = themes_needs,
                                      ),
                     self.org_sector_id(readable = themes_sectors,
                                        writable = themes_sectors,
                                        ),
                     Field("obsolete", "boolean",
                           default = False,
                           label = T("Obsolete"),
                           represent = s3_yes_no_represent,
                           ),
                     CommentsField(),
                     )

        # Table configuration
        configure(tablename,
                  deduplicate = S3Duplicate(primary = ("name",),
                                            secondary = ("organisation_id",
                                                         "sector_id",
                                                         "need_id",
                                                         ),
                                            ),
                  ondelete_cascade = self.response_theme_ondelete_cascade,
                  )

        # CRUD strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Response Theme"),
            title_display = T("Response Theme Details"),
            title_list = T("Response Themes"),
            title_update = T("Edit Response Theme"),
            label_list_button = T("List Response Themes"),
            label_delete_button = T("Delete Response Theme"),
            msg_record_created = T("Response Theme created"),
            msg_record_modified = T("Response Theme updated"),
            msg_record_deleted = T("Response Theme deleted"),
            msg_list_empty = T("No Response Themes currently defined"),
        )

        # Foreign Key Template
        themes_represent = dvr_ResponseThemeRepresent(multiple = True,
                                                      translate = True,
                                                      )
        requires = IS_ONE_OF(db, "%s.id" % tablename,
                             themes_represent,
                             multiple = True,
                             not_filterby = "obsolete",
                             not_filter_opts = (True,),
                             )
        if settings.get_dvr_response_themes_org_specific():
            root_org = current.auth.root_org()
            if root_org:
                requires.set_filter(filterby = "organisation_id",
                                    filter_opts = (root_org,),
                                    )
        response_theme_ids = FieldTemplate(
                                "response_theme_ids",
                                "list:reference %s" % tablename,
                                label = T("Themes"),
                                ondelete = "RESTRICT",
                                represent = themes_represent,
                                requires = IS_EMPTY_OR(requires),
                                sortby = "name",
                                widget = S3MultiSelectWidget(header = False,
                                                             ),
                                )

        # ---------------------------------------------------------------------
        # Response Types
        #
        tablename = "dvr_response_type"
        define_table(tablename,
                     Field("name",
                           requires = [IS_NOT_EMPTY(), IS_LENGTH(512, minsize=1)],
                           ),
                     Field("code",
                           label = T("Code"),
                           requires = IS_EMPTY_OR(IS_LENGTH(64, minsize=1)),
                           represent = lambda v, row=None: v if v else "-",
                           # Enable in template as required:
                           readable = False,
                           writable = False,
                           ),
                     # This form of hierarchy may not work on all databases:
                     Field("parent", "reference dvr_response_type",
                           label = T("Subtype of"),
                           ondelete = "RESTRICT",
                           represent = S3Represent(lookup = tablename,
                                                   translate = True,
                                                   hierarchy = True,
                                                   ),
                           readable = hierarchical_response_types,
                           writable = hierarchical_response_types,
                           ),
                     Field("is_default", "boolean",
                           label = T("Default?"),
                           default = False,
                           represent = s3_yes_no_represent,
                           ),
                     Field("is_consultation", "boolean",
                           label = T("Consultation"),
                           default = False,
                           represent = s3_yes_no_represent,
                           ),
                     CommentsField(),
                     )

        # Hierarchy
        if hierarchical_response_types:
            hierarchy = "parent"
            widget = S3HierarchyWidget(multiple = False,
                                       leafonly = True,
                                       )
        else:
            hierarchy = None
            widget = None

        # Table configuration
        configure(tablename,
                  deduplicate = S3Duplicate(primary = ("name",),
                                            secondary = ("parent",),
                                            ),
                  hierarchy = hierarchy,
                  onaccept = self.response_type_onaccept,
                  )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Response Type"),
            title_display = T("Response Type Details"),
            title_list = T("Response Types"),
            title_update = T("Edit Response Type"),
            label_list_button = T("List Response Types"),
            label_delete_button = T("Delete Response Type"),
            msg_record_created = T("Response Type created"),
            msg_record_modified = T("Response Type updated"),
            msg_record_deleted = T("Response Type deleted"),
            msg_list_empty = T("No Response Types currently defined"),
        )

        # Foreign Key Template
        represent = S3Represent(lookup=tablename, translate=True)
        response_type_id = FieldTemplate(
                                "response_type_id",
                                "reference %s" % tablename,
                                label = T("Response Type"),
                                represent = represent,
                                requires = IS_EMPTY_OR(
                                            IS_ONE_OF(db, "%s.id" % tablename,
                                                      represent,
                                                      )),
                                sortby = "name",
                                widget = widget,
                                )

        # ---------------------------------------------------------------------
        # Response action status
        #
        tablename = "dvr_response_status"
        define_table(tablename,
                     Field("name",
                           requires = [IS_NOT_EMPTY(), IS_LENGTH(512, minsize=1)],
                           ),
                     Field("workflow_position", "integer",
                           label = T("Workflow Position"),
                           requires = IS_INT_IN_RANGE(0, None),
                           ),
                     Field("is_default", "boolean",
                           default = False,
                           label = T("Default Initial Status"),
                           represent = BooleanRepresent(),
                           ),
                     Field("is_closed", "boolean",
                           default = False,
                           label = T("Closes Response Action"),
                           represent = BooleanRepresent(),
                           ),
                     Field("is_canceled", "boolean",
                           default = False,
                           label = T("Indicates Cancelation"),
                           represent = BooleanRepresent(),
                           ),
                     Field("is_default_closure", "boolean",
                           default = False,
                           label = T("Default Closure Status"),
                           represent = BooleanRepresent(),
                           ),
                     Field("is_indirect_closure", "boolean",
                           default = False,
                           label = T("Indirect Closure Status"),
                           represent = BooleanRepresent(),
                           ),
                     Field("color",
                           requires = IS_HTML_COLOUR(),
                           represent = IS_HTML_COLOUR.represent,
                           widget = S3ColorPickerWidget(),
                           ),
                     CommentsField(),
                     )

        # Table Configuration
        configure(tablename,
                  deduplicate = S3Duplicate(),
                  onaccept = self.response_status_onaccept,
                  )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Response Status"),
            title_display = T("Response Status Details"),
            title_list = T("Response Statuses"),
            title_update = T("Edit Response Status"),
            label_list_button = T("List Response Statuses"),
            label_delete_button = T("Delete Response Status"),
            msg_record_created = T("Response Status created"),
            msg_record_modified = T("Response Status updated"),
            msg_record_deleted = T("Response Status deleted"),
            msg_list_empty = T("No Response Statuses currently defined"),
        )

        # Foreign Key Template
        represent = S3Represent(lookup=tablename, translate=True)
        response_status_id = FieldTemplate(
                                "status_id",
                                "reference %s" % tablename,
                                label = T("Status"),
                                represent = represent,
                                requires = IS_ONE_OF(db, "%s.id" % tablename,
                                                     represent,
                                                     orderby = "workflow_position",
                                                     sort = False,
                                                     zero = None,
                                                     ),
                                sortby = "workflow_position",
                                )

        # ---------------------------------------------------------------------
        # Response action
        # - is a specific measure taken to address a particular need
        # - usually linked to a case activity that documents the need
        # - counseling will typically refer to this as a counseling session
        #
        case_label = settings.get_dvr_label()
        if case_label: # If we add more options in future then == "Beneficiary"
            CASE = T("Beneficiary")
        else:
            CASE = T("Case")

        use_response_types = settings.get_dvr_response_types()
        use_response_themes = settings.get_dvr_response_themes()

        response_themes_details = settings.get_dvr_response_themes_details()
        response_themes_efforts = settings.get_dvr_response_themes_efforts()

        use_due_date = settings.get_dvr_response_due_date()
        DATE = T("Date Actioned") if use_due_date else T("Date")

        use_time = settings.get_dvr_response_use_time()

        tablename = "dvr_response_action"
        define_table(tablename,
                     # Beneficiary and Case Activity
                     self.pr_person_id(
                         label = CASE,
                         widget = S3PersonAutocompleteWidget(controller="dvr"),
                         empty = False,
                         ),
                     case_activity_id(
                         empty = False,
                         label = T("Activity"),
                         ondelete = "CASCADE",
                         writable = False,
                         readable = False,
                         ),

                     # Response action type and themes
                     response_type_id(
                         empty = not use_response_types,
                         label = T("Action Type"),
                         ondelete = "RESTRICT",
                         readable = use_response_types,
                         writable = use_response_types,
                         ),
                     response_theme_ids(
                         ondelete = "RESTRICT",
                         readable = use_response_themes,
                         writable = use_response_themes,
                         ),

                     # Date/Time
                     DateField("date_due",
                               label = T("Date Due"),
                               readable = use_due_date,
                               writable = use_due_date,
                               ),
                     # For backwards-compatibility:
                     DateField(label = DATE,
                               default = None if use_due_date else "now",
                               readable = False,
                               writable = False,
                               ),
                     DateTimeField("start_date",
                                   label = DATE,
                                   default = None if use_due_date else "now",
                                   widget = None if use_time else "date",
                                   ),
                     DateTimeField("end_date",
                                   label = T("End"),
                                   widget = None if use_time else "date",
                                   readable = False,
                                   writable = False,
                                   ),

                     # Responsibility
                     self.hrm_human_resource_id(
                         widget = None,
                         comment = None,
                         ),

                     # Status
                     response_status_id(),

                     # Efforts in hours
                     # - read-only and computed onaccept when reporting efforts
                     #   per theme
                     Field("hours", "double",
                           label = T("Effort (Hours)"),
                           requires = IS_EMPTY_OR(IS_FLOAT_IN_RANGE(0.0, None)),
                           represent = lambda hours: "%.2f" % hours if hours else NONE,
                           widget = S3HoursWidget(precision=2),
                           writable = not response_themes_efforts,
                           ),
                     CommentsField(label = T("Details"),
                                   comment = None,
                                   represent = lambda v: s3_text_represent(v, lines=8),
                                   ),
                     )

        # Components
        self.add_components(tablename,
                            dvr_response_action_theme = "action_id",
                            dvr_vulnerability = {"link": "dvr_vulnerability_response_action",
                                                 "joinby": "action_id",
                                                 "key": "vulnerability_id",
                                                 },
                            )

        # List_fields
        list_fields = ["start_date"]
        if not response_themes_details or \
           not settings.get_dvr_response_activity_autolink():
            list_fields.append("case_activity_id")
        if use_response_types:
            list_fields.append("response_type_id")
        if use_response_themes:
            if response_themes_details:
                list_fields.append((T("Themes"), "response_action_theme.theme_id"))
            else:
                list_fields.extend(["response_theme_ids", "comments"])
        else:
            list_fields.append("comments")
        list_fields.extend(["human_resource_id",
                            "hours",
                            "status_id",
                            ])
        if use_due_date:
            list_fields.insert(-3, "date_due")

        # Filter widgets
        filter_widgets = [TextFilter(["case_activity_id$person_id$pe_label",
                                      "case_activity_id$person_id$first_name",
                                      "case_activity_id$person_id$middle_name",
                                      "case_activity_id$person_id$last_name",
                                      "comments",
                                      ],
                                     label = T("Search"),
                                     ),
                          OptionsFilter("status_id",
                                        options = lambda: \
                                                  get_filter_options("dvr_response_status"),
                                        cols = 3,
                                        translate = True,
                                        ),
                          #due_filter,
                          #response_type_filter,
                          ]
        if use_due_date:
            filter_widgets.append(DateFilter("date_due"))

        if use_response_types:
            if hierarchical_response_types:
                response_type_filter = HierarchyFilter(
                                            "response_type_id",
                                            lookup = "dvr_response_type",
                                            hidden = True,
                                            )
            else:
                response_type_filter = OptionsFilter(
                                            "response_type_id",
                                            options = lambda: \
                                                      get_filter_options("dvr_response_type"),
                                            hidden = True,
                                            )
            filter_widgets.append(response_type_filter)

        # CRUD Form
        type_field = "response_type_id" if use_response_types else None
        details_field = "comments"

        postprocess = None
        if use_response_themes:
            if response_themes_details or response_themes_efforts:
                fields = ["theme_id"]
                if response_themes_details:
                    fields.append("comments")
                    details_field = None
                else:
                    details_field = "comments"
                if response_themes_efforts:
                    fields.append("hours")
                    postprocess = self.response_action_postprocess
                themes_field = InlineComponent("response_action_theme",
                                               fields = fields,
                                               label = T("Themes"),
                                               )
            else:
                themes_field = "response_theme_ids"
        else:
            themes_field = None

        if settings.get_dvr_response_vulnerabilities():
            vulnerabilities = InlineLink("vulnerability",
                                         field = "vulnerability_id",
                                         header = False,
                                         label = T("Vulnerabilities"),
                                         comment = T("Vulnerabilities addressed by this action"),
                                         )
        else:
            vulnerabilities = None

        due_field = "date_due" if use_due_date else None

        crud_form = CustomForm("person_id",
                               "case_activity_id",
                               type_field,
                               themes_field,
                               details_field,
                               vulnerabilities,
                               "human_resource_id",
                               # TODO investigate if anything uses due_date
                               #      => make custom-only otherwise
                               due_field,
                               "start_date",
                               "status_id",
                               "hours",
                               postprocess = postprocess,
                               )

        # Table Configuration
        configure(tablename,
                  crud_form = crud_form,
                  filter_widgets = filter_widgets,
                  list_fields = list_fields,
                  onaccept = self.response_action_onaccept,
                  ondelete = self.response_action_ondelete,
                  orderby = "%s.start_date desc" % tablename,
                  )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Action"),
            title_display = T("Action Details"),
            title_list = T("Actions"),
            title_update = T("Edit Action"),
            label_list_button = T("List Actions"),
            label_delete_button = T("Delete Action"),
            msg_record_created = T("Action created"),
            msg_record_modified = T("Action updated"),
            msg_record_deleted = T("Action deleted"),
            msg_list_empty = T("No Actions currently registered"),
        )

        action_represent = dvr_ResponseActionRepresent()
        response_action_id = FieldTemplate("action_id", "reference dvr_response_action",
                                           label = T("Action"),
                                           represent = action_represent,
                                           requires = IS_ONE_OF(db, "dvr_response_action.id",
                                                                action_represent,
                                                                ),
                                           )

        # ---------------------------------------------------------------------
        # Response Action <=> Theme link table
        #   - for filtering/reporting by extended theme attributes
        #   - exposed directly as sub-form of response actions when recording
        #     details/efforts per theme (most commonly in counseling)
        #   - if not exposed directly, links will be established onaccept
        #     from dvr_response_action.response_theme_ids
        #
        theme_represent = dvr_ResponseThemeRepresent(show_need=themes_needs)

        tablename = "dvr_response_action_theme"
        define_table(tablename,
                     response_action_id(ondelete = "CASCADE"),
                     Field("theme_id", "reference dvr_response_theme",
                           ondelete = "RESTRICT",
                           label = T("Theme"),
                           represent = theme_represent,
                           requires = IS_ONE_OF(db, "dvr_response_theme.id",
                                                theme_represent,
                                                not_filterby = "obsolete",
                                                not_filter_opts = (True,),
                                                ),
                           ),
                     Field("hours", "double",
                           label = T("Effort (Hours)"),
                           requires = IS_EMPTY_OR(IS_FLOAT_IN_RANGE(0.0, None)),
                           represent = lambda hours: "%.2f" % hours if hours else NONE,
                           widget = S3HoursWidget(precision=2),
                           readable = response_themes_efforts,
                           writable = response_themes_efforts,
                           ),
                     case_activity_id(ondelete = "SET NULL",
                                      readable = False,
                                      writable = False,
                                      ),
                     CommentsField(label = T("Details"),
                                   comment = None,
                                   represent = lambda v: s3_text_represent(v, lines=8),
                                   ),
                     )

        configure(tablename,
                  onaccept = self.response_action_theme_onaccept,
                  ondelete = self.response_action_theme_ondelete,
                  )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return {"dvr_response_action_id": response_action_id,
                }

    # -------------------------------------------------------------------------
    def defaults(self):
        """ Safe defaults for names in case the module is disabled """

        dummy = FieldTemplate.dummy

        return {"dvr_response_action_id": dummy("action_id"),
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def response_type_onaccept(form):
        """
            Onaccept routine for response types:
                - only one type can be the default

            Args:
                form: the FORM
        """

        form_vars = form.vars
        try:
            record_id = form_vars.id
        except AttributeError:
            record_id = None
        if not record_id:
            return

        table = current.s3db.dvr_response_type

        # If this status is the default, then set is_default-flag
        # for all other types to False:
        if form_vars.get("is_default"):
            query = (table.is_default == True) & \
                    (table.id != record_id)
            current.db(query).update(is_default = False)

    # -------------------------------------------------------------------------
    @staticmethod
    def response_status_onaccept(form):
        """
            Onaccept routine for response statuses:
                - only one status can be the default

            Args:
                form: the FORM
        """

        form_vars = form.vars
        try:
            record_id = form_vars.id
        except AttributeError:
            record_id = None
        if not record_id:
            return

        table = current.s3db.dvr_response_status
        db = current.db

        # If this status is the default, then set is_default-flag
        # for all other statuses to False:
        if form_vars.get("is_default"):
            query = (table.is_default == True) & \
                    (table.id != record_id)
            db(query).update(is_default = False)

        # If this status is the default closure, then enforce is_closed,
        # and set is_default_closure for all other statuses to False
        if form_vars.get("is_default_closure"):
            db(table.id == record_id).update(is_closed = True)
            query = (table.is_default_closure == True) & \
                    (table.id != record_id)
            db(query).update(is_default_closure = False)

        # If this status means canceled, then enforce is_closed
        if form_vars.get("is_canceled"):
            db(table.id == record_id).update(is_closed = True)

    # -------------------------------------------------------------------------
    @staticmethod
    def response_theme_ondelete_cascade(row):
        """
            Explicit deletion cascade for response theme list:references
            (which are not caught by standard cascade), action depending
            on "ondelete" setting of response_theme_ids:
                - RESTRICT  => block deletion cascade
                - otherwise => clean up the list:reference

            Args:
                row: the dvr_response_theme Row to be deleted
        """

        db = current.db

        theme_id = row.id

        # Table with list:reference dvr_response_theme
        atable = current.s3db.dvr_response_action
        reference = atable.response_theme_ids

        # Referencing rows
        query = (reference.contains(theme_id)) & \
                (atable.deleted == False)
        if reference.ondelete == "RESTRICT":
            referenced_by = db(query).select(atable.id, limitby=(0, 1)).first()
            if referenced_by:
                # Raise to stop deletion cascade
                raise RuntimeError("Attempt to delete a theme that is referenced by a response")
        else:
            referenced_by = db(query).select(atable.id, reference)
            for rrow in referenced_by:
                # Clean up reference list
                theme_ids = rrow[reference]
                rrow.update_record(response_theme_ids = \
                    [tid for tid in theme_ids if tid != theme_id])

    # -------------------------------------------------------------------------
    @staticmethod
    def get_case_activity_by_need(person_id, need_id, hr_id=None):
        """
            DRY helper to find or create a case activity matching a need_id

            Args:
                person_id: the beneficiary person ID
                need_id: the need ID (or a list of need IDs)
                human_resource_id: the HR responsible

            Returns:
                a dvr_case_activity record ID
        """

        if not person_id:
            return None

        s3db = current.s3db
        table = s3db.dvr_case_activity

        # Look up a matching case activity for this beneficiary
        query = (table.person_id == person_id)
        if isinstance(need_id, (list, tuple)):
            need = need_id[0] if len(need_id) == 1 else None
            query &= (table.need_id.belongs(need_id))
        else:
            need = need_id
            query &= (table.need_id == need_id)
        query &= (table.deleted == False)

        # If using status, exclude closed activities
        if current.deployment_settings.get_dvr_case_activity_status():
            stable = s3db.dvr_case_activity_status
            join = stable.on((stable.id == table.status_id) & \
                             (stable.is_closed == False) & \
                             (stable.deleted == False))
        else:
            join = None

        activity = current.db(query).select(table.id,
                                            join = join,
                                            orderby = ~table.start_date,
                                            limitby = (0, 1),
                                            ).first()
        if activity:
            # Use this activity
            activity_id = activity.id

        elif need is not None:
            # Create a new activity for the case
            activity = {"person_id": person_id,
                        "need_id": need,
                        "start_date": current.request.utcnow,
                        "human_resource_id": hr_id,
                        "status_id": dvr_case_activity_default_status(),
                        }
            activity_id = activity["id"] = table.insert(**activity)

            s3db.update_super(table, activity)
            auth = current.auth
            auth.s3_set_record_owner(table, activity_id)
            auth.s3_make_session_owner(table, activity_id)
            s3db.onaccept("dvr_case_activity", activity, method="create")

        else:
            activity_id = None

        return activity_id

    # -------------------------------------------------------------------------
    @classmethod
    def response_action_postprocess(cls, form):

        record_id = get_form_record_id(form)
        if not record_id:
            return

        db = current.db
        s3db = current.s3db
        settings = current.deployment_settings

        if settings.get_dvr_response_themes_details() and \
           settings.get_dvr_response_themes_efforts():

            # Look up the record
            atable = s3db.dvr_response_action
            query = (atable.id == record_id)
            record = db(query).select(atable.id,
                                      atable.hours,
                                      limitby = (0, 1),
                                      ).first()
            if not record:
                return

            # Calculate total effort from individual theme links
            ltable = s3db.dvr_response_action_theme
            query = (ltable.action_id == record_id) & \
                    (ltable.deleted == False)
            rows = db(query).select(ltable.hours)
            hours = [row.hours for row in rows if row.hours is not None]
            effort = sum(hours) if hours else None
            if effort is None and (record.hours is None or not rows):
                # Default total if nothing provided
                effort = 0.0

            # Update the record
            if effort is not None:
                record.update_record(hours=effort)

    # -------------------------------------------------------------------------
    @classmethod
    def response_action_onaccept(cls, form):
        """
            Onaccept routine for response actions
                - inherit the person ID from case activity if created inline
                - link to case activity if created on person tab and
                  configured for autolink
                - update theme links from inline response_theme_ids
                - update last-seen-on
        """

        form_vars = form.vars
        try:
            record_id = form_vars.id
        except AttributeError:
            record_id = None
        if not record_id:
            return

        db = current.db
        s3db = current.s3db

        # Get the record
        atable = s3db.dvr_response_action
        query = (atable.id == record_id)
        record = db(query).select(atable.id,
                                  atable.person_id,
                                  atable.case_activity_id,
                                  atable.response_theme_ids,
                                  atable.human_resource_id,
                                  atable.start_date,
                                  atable.end_date,
                                  atable.hours,
                                  limitby = (0, 1),
                                  ).first()
        if not record:
            return

        settings = current.deployment_settings
        themes_details = settings.get_dvr_response_themes_details()

        theme_ids = record.response_theme_ids
        if not theme_ids:
            theme_ids = []

        if not record.person_id:
            # Inherit the person_id (beneficiary) from the case activity
            case_activity_id = record.case_activity_id
            if case_activity_id:
                catable = s3db.dvr_case_activity
                query = (catable.id == case_activity_id)
                case_activity = db(query).select(catable.person_id,
                                                 limitby = (0, 1),
                                                 ).first()
                if case_activity:
                    record.update_record(person_id = case_activity.person_id)

        elif settings.get_dvr_response_activity_autolink() and not themes_details:
            # Automatically link the response action to a case activity
            # (using matching needs)

            # Get all needs of the response
            ttable = s3db.dvr_response_theme
            if theme_ids:
                query = ttable.id.belongs(theme_ids)
                themes = db(query).select(ttable.need_id,
                                          groupby = ttable.need_id,
                                          )
                need_ids = set(theme.need_id for theme in themes)
            else:
                need_ids = None

            if not need_ids:
                # Response is not linked to any needs
                # => Remove activity link
                activity_id = None

            else:
                catable = s3db.dvr_case_activity

                activity_id = record.case_activity_id
                if activity_id:
                    # Verify that the case activity's need matches person+theme
                    query = (catable.id == activity_id) & \
                            (catable.person_id == record.person_id) & \
                            (catable.deleted == False)
                    activity = db(query).select(catable.need_id,
                                                limitby = (0, 1),
                                                ).first()
                    if not activity or activity.need_id not in need_ids:
                        activity_id = None

                if not activity_id:
                    # Find or create a matching case activity
                    activity_id = cls.get_case_activity_by_need(
                                        record.person_id,
                                        need_ids,
                                        hr_id = record.human_resource_id,
                                        )

            # Update the activity link
            record.update_record(case_activity_id = activity_id)

        if not themes_details:
            # Get all selected themes
            selected = set(theme_ids)

            # Get all linked themes
            ltable = s3db.dvr_response_action_theme
            query = (ltable.action_id == record_id) & \
                    (ltable.deleted == False)
            links = db(query).select(ltable.theme_id)
            linked = set(link.theme_id for link in links)

            # Remove obsolete theme links
            obsolete = linked - selected
            if obsolete:
                query &= ltable.theme_id.belongs(obsolete)
                db(query).delete()

            # Add links for newly selected themes
            added = selected - linked
            for theme_id in added:
                ltable.insert(action_id = record_id,
                              theme_id = theme_id,
                              )

        # Calculate end_date
        start_date = record.start_date
        end_date = record.end_date
        if start_date:

            if "end_date" not in form_vars:
                new_end_date = None
                hours = record.hours
                if hours:
                    duration = datetime.timedelta(hours=hours)
                else:
                    duration = datetime.timedelta(hours=0.5)
                orig_start_date = None
                if hasattr(form, "record"):
                    try:
                        orig_start_date = form.record.start_date
                    except AttributeError:
                        pass
                if not end_date or not orig_start_date:
                    new_end_date = start_date + duration
                else:
                    delta = end_date - orig_start_date
                    if hours and delta != duration:
                        delta = duration
                        duration_changed = True
                    else:
                        duration_changed = False
                    if start_date != orig_start_date or duration_changed:
                        new_end_date = start_date + delta
                if new_end_date:
                    record.update_record(end_date = new_end_date)

        elif end_date:
            record.update_record(end_date = None)

        # Update last-seen-on
        dvr_update_last_seen(record.person_id)

    # -------------------------------------------------------------------------
    @staticmethod
    def response_action_ondelete(row):
        """
            Ondelete of response action:
                - update last-seen-on
        """

        person_id = row.person_id
        if person_id:
            dvr_update_last_seen(person_id)

    # -------------------------------------------------------------------------
    @classmethod
    def response_action_theme_onaccept(cls, form):
        """
            Onaccept routine for response action theme links
                - update response_theme_ids in response action record
                - link to case activity if required
        """

        form_vars = form.vars
        try:
            record_id = form_vars.id
        except AttributeError:
            record_id = None
        if not record_id:
            return

        db = current.db
        s3db = current.s3db

        # Look up the record
        table = s3db.dvr_response_action_theme
        query = (table.id == record_id)
        record = db(query).select(table.id,
                                  table.action_id,
                                  table.theme_id,
                                  table.comments,
                                  table.hours,
                                  limitby = (0, 1),
                                  ).first()
        if not record:
            return

        settings = current.deployment_settings
        if settings.get_dvr_response_themes_details():

            # Look up the response action
            action_id = record.action_id
            if action_id:
                atable = s3db.dvr_response_action
                query = (atable.id == action_id)
                action = db(query).select(atable.id,
                                          atable.person_id,
                                          atable.human_resource_id,
                                          limitby = (0, 1),
                                          ).first()
            else:
                action = None

            if action:
                theme_id = record.theme_id

                if theme_id:
                    # Merge duplicate action<=>theme links
                    query = (table.id != record.id) & \
                            (table.action_id == action_id) & \
                            (table.theme_id == record.theme_id) & \
                            current.auth.s3_accessible_query("delete", table) & \
                            (table.deleted == False)
                    rows = db(query).select(table.id,
                                            table.hours,
                                            table.comments,
                                            orderby = table.created_on,
                                            )

                    duplicates, details, hours = [], [], []
                    for row in rows:
                        duplicates.append(row.id)
                        if row.comments:
                            details.append(row.comments.strip())
                        if row.hours is not None:
                            hours.append(row.hours)

                    if record.comments:
                        details.append(record.comments.strip())
                    if record.hours is not None:
                        hours.append(record.hours)

                    record.update_record(comments = "\n\n".join(c for c in details if c),
                                         hours = sum(hours) if hours else None,
                                         )
                    s3db.resource("dvr_response_action_theme", id=duplicates).delete()

                # Update response_theme_ids in response action
                query = (table.action_id == action_id) & \
                        (table.deleted == False)
                rows = db(query).select(table.theme_id)
                theme_ids = [row.theme_id for row in rows if row.theme_id]
                action.update_record(response_theme_ids=theme_ids)

                # Auto-link to case activity
                if settings.get_dvr_response_themes_needs() and \
                   settings.get_dvr_response_activity_autolink():

                    # Look up the theme's need_id
                    ttable = s3db.dvr_response_theme
                    query = (ttable.id == record.theme_id)
                    theme = db(query).select(ttable.need_id,
                                             limitby = (0, 1),
                                             ).first()
                    if theme:
                        activity_id = cls.get_case_activity_by_need(
                                                action.person_id,
                                                theme.need_id,
                                                hr_id = action.human_resource_id,
                                                )
                        record.update_record(case_activity_id=activity_id)

    # -------------------------------------------------------------------------
    @staticmethod
    def response_action_theme_ondelete(row):
        """
            On-delete actions for response_action_theme links
                - update response_theme_ids in action record
        """

        db = current.db
        s3db = current.s3db

        action_id = row.action_id
        if action_id:
            atable = s3db.dvr_response_action
            query = (atable.id == action_id) & \
                    (atable.deleted == False)
            action = db(query).select(atable.id,
                                      #atable.person_id,
                                      #atable.human_resource_id,
                                      limitby = (0, 1),
                                      ).first()
        else:
            action = None

        if action:
            # Update response theme ids in response action
            table = s3db.dvr_response_action_theme
            query = (table.action_id == action_id) & \
                    (table.deleted == False)
            rows = db(query).select(table.theme_id)
            theme_ids = [row.theme_id for row in rows if row.theme_id]
            action.update_record(response_theme_ids = theme_ids)

# =============================================================================
class DVRCaseActivityModel(DataModel):
    """ Model for Case Activities """

    names = ("dvr_case_activity",
             "dvr_case_activity_id",
             "dvr_case_activity_status",
             "dvr_case_activity_update",
             "dvr_case_activity_update_type",
             "dvr_provider_type",
             "dvr_termination_type",
             )

    def model(self):

        T = current.T
        db = current.db

        settings = current.deployment_settings
        crud_strings = current.response.s3.crud_strings

        configure = self.configure
        define_table = self.define_table

        service_type = settings.get_dvr_case_activity_use_service_type()
        case_activity_sectors = settings.get_dvr_case_activity_sectors()

        service_id = self.org_service_id
        project_id = self.project_project_id
        organisation_id = self.org_organisation_id
        human_resource_id = self.hrm_human_resource_id

        # ---------------------------------------------------------------------
        # Provider Type
        #
        tablename = "dvr_provider_type"
        define_table(tablename,
                     Field("name", notnull=True,
                           label = T("Type"),
                           requires = [IS_NOT_EMPTY(), IS_LENGTH(512, minsize=1)],
                           ),
                     CommentsField(),
                     )

        # Table configuration
        configure(tablename,
                  deduplicate = S3Duplicate(),
                  )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Provider Type"),
            title_display = T("Provider Type Details"),
            title_list = T("Provider Types"),
            title_update = T("Edit Provider Type"),
            label_list_button = T("List Provider Types"),
            label_delete_button = T("Delete Provider Type"),
            msg_record_created = T("Provider Type added"),
            msg_record_modified = T("Provider Type updated"),
            msg_record_deleted = T("Provider Type deleted"),
            msg_list_empty = T("No Provider Types currently defined"),
            )

        # Foreign Key Template
        represent = S3Represent(lookup=tablename)
        provider_type_id = FieldTemplate("provider_type_id", "reference %s" % tablename,
                                         label = T("Provider Type"),
                                         ondelete = "CASCADE",
                                         represent = represent,
                                         requires = IS_EMPTY_OR(
                                                        IS_ONE_OF(db, "%s.id" % tablename,
                                                                  represent,
                                                                  sort = True,
                                                                  )),
                                         sortby = "name",
                                         )

        # ---------------------------------------------------------------------
        # Termination Types (=how a case activity ended)
        #
        tablename = "dvr_termination_type"
        define_table(tablename,
                     service_id(label = T("Service Type"),
                                ondelete = "CASCADE",
                                readable = service_type,
                                writable = service_type,
                                ),
                     Field("name", notnull=True,
                           label = T("Name"),
                           requires = [IS_NOT_EMPTY(), IS_LENGTH(512, minsize=1)],
                           ),
                     CommentsField(),
                     )

        # Table configuration
        configure(tablename,
                  deduplicate = S3Duplicate(primary = ("name",),
                                            secondary = ("service_id",),
                                            ),
                  )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Termination Type"),
            title_display = T("Termination Type Details"),
            title_list = T("Termination Types"),
            title_update = T("Edit Termination Type"),
            label_list_button = T("List Termination Types"),
            label_delete_button = T("Delete Termination Type"),
            msg_record_created = T("Termination Type added"),
            msg_record_modified = T("Termination Type updated"),
            msg_record_deleted = T("Termination Type deleted"),
            msg_list_empty = T("No Termination Types currently defined"),
            )

        # Foreign Key Template
        represent = S3Represent(lookup=tablename)
        termination_type_id = FieldTemplate("termination_type_id", "reference %s" % tablename,
                                            label = T("Termination Type"),
                                            ondelete = "CASCADE",
                                            represent = represent,
                                            requires = IS_EMPTY_OR(
                                                            IS_ONE_OF(db, "%s.id" % tablename,
                                                                      represent,
                                                                      sort = True,
                                                                      )),
                                            sortby = "name",
                                            )

        # ---------------------------------------------------------------------
        # Case Activity Status
        #
        tablename = "dvr_case_activity_status"
        define_table(tablename,
                     Field("name",
                           requires = [IS_NOT_EMPTY(), IS_LENGTH(512, minsize=1)],
                           ),
                     Field("workflow_position", "integer",
                           label = T("Workflow Position"),
                           requires = IS_INT_IN_RANGE(0, None),
                           ),
                     Field("is_default", "boolean",
                           default = False,
                           label = T("Default Status"),
                           ),
                     Field("is_closed", "boolean",
                           default = False,
                           label = T("Closes Activity"),
                           ),
                     CommentsField(),
                     )

        # Table Configuration
        configure(tablename,
                  deduplicate = S3Duplicate(),
                  onaccept = self.case_activity_status_onaccept,
                  )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Activity Status"),
            title_display = T("Activity Status Details"),
            title_list = T("Activity Statuses"),
            title_update = T("Edit Activity Status"),
            label_list_button = T("List Activity Statuses"),
            label_delete_button = T("Delete Activity Status"),
            msg_record_created = T("Activity Status created"),
            msg_record_modified = T("Activity Status updated"),
            msg_record_deleted = T("Activity Status deleted"),
            msg_list_empty = T("No Activity Statuses currently defined"),
        )

        # Foreign Key Template
        represent = S3Represent(lookup=tablename, translate=True)
        activity_status_id = FieldTemplate("status_id",
                                           "reference %s" % tablename,
                                           label = T("Status"),
                                           represent = represent,
                                           requires = IS_ONE_OF(db, "%s.id" % tablename,
                                                                represent,
                                                                orderby = "workflow_position",
                                                                sort = False,
                                                                zero = None,
                                                                ),
                                           sortby = "workflow_position",
                                           )

        # ---------------------------------------------------------------------
        # Case Activity
        # - is a container to record a concrete need situation of the case,
        #   any measures taken to address it, and the outcome
        #
        twoweeks = current.request.utcnow + datetime.timedelta(days=14)

        subject_type = settings.get_dvr_case_activity_subject_type()
        use_subject = subject_type in ("subject", "both")
        use_need = subject_type in ("need", "both")

        need_details = settings.get_dvr_case_activity_need_details()
        response_details = settings.get_dvr_case_activity_response_details()

        use_emergency = settings.get_dvr_case_activity_emergency()

        use_status = settings.get_dvr_case_activity_status()
        use_outcome = settings.get_dvr_case_activity_outcome()
        use_achievement = settings.get_dvr_case_activity_achievement()

        follow_up = settings.get_dvr_case_activity_follow_up()

        # Priority options
        priority_opts = [#(0, T("Urgent")),
                         (1, T("High")),
                         (2, T("Normal")),
                         (3, T("Low")),
                         ]

        # Achievement options
        achievement_opts = [("INCR", T("Increased in severity")),
                            ("SAME", T("At same level")),
                            ("DECR", T("Decreased in severity")),
                            ("RSLV", T("Completely resolved")),
                            ]

        tablename = "dvr_case_activity"
        define_table(tablename,
                     self.super_link("doc_id", "doc_entity"),
                     self.dvr_case_id(comment = None,
                                      empty = False,
                                      label = T("Case Number"),
                                      ondelete = "CASCADE",
                                      writable = False,
                                      ),
                     # Beneficiary
                     self.pr_person_id(comment = None,
                                       empty = False,
                                       ondelete = "CASCADE",
                                       writable = False,
                                       ),

                     # Type of need, subject and details
                     self.dvr_need_id(readable = use_need,
                                      writable = use_need,
                                      ),
                     Field("subject",
                           label = T("Subject / Occasion"),
                           readable = use_subject,
                           writable = use_subject,
                           represent = s3_text_represent,
                           ),
                     Field("need_details", "text",
                           label = T("Need Details"),
                           represent = s3_text_represent,
                           widget = s3_comments_widget,
                           readable = need_details,
                           writable = need_details,
                           ),

                     # Dates
                     DateField("start_date",
                               label = T("Registered on"),
                               default = "now",
                               set_min = "#dvr_case_activity_end_date",
                               ),
                     DateField("end_date",
                               label = T("Completed on"),
                               readable = use_status,
                               writable = False, # set onaccept
                               set_max = "#dvr_case_activity_start_date",
                               ),

                     # Priority
                     # - normally, a simple distinction between emergencies
                     #   and non-emergency needs is all that can be expected:
                     Field("emergency", "boolean",
                           default = False,
                           label = T("Emergency"),
                           represent = s3_yes_no_represent,
                           readable = use_emergency,
                           writable = use_emergency,
                           ),
                     # - a more differential prioritisation is often desired,
                     #   but hard to define and thus not very practical, so
                     #   this is optional:
                     Field("priority", "integer",
                           label = T("Priority"),
                           represent = represent_option(dict(priority_opts)),
                           requires = IS_IN_SET(priority_opts, sort=False),
                           default = 2, # normal
                           readable = False,
                           writable = False,
                           ),

                     # Responsibilities (activate in template as needed)
                     human_resource_id(label = T("Assigned to"),
                                       comment = None,
                                       widget = None,
                                       readable = False,
                                       writable = False,
                                       ),

                     # Categories (activate in template as needed)
                     self.org_sector_id(readable = case_activity_sectors,
                                        writable = case_activity_sectors,
                                        ),
                     service_id(label = T("Service Type"),
                                ondelete = "RESTRICT",
                                readable = service_type,
                                writable = service_type,
                                ),
                     project_id(ondelete = "SET NULL",
                                readable = False,
                                writable = False,
                                ),

                     # Free-text alternative for response actions:
                     Field("activity_details", "text",
                           label = T("Support provided"),
                           represent = s3_text_represent,
                           widget = s3_comments_widget,
                           readable = response_details,
                           writable = response_details,
                           ),

                     # Support received by the beneficiary independently
                     # of the managed activity:
                     Field("outside_support", "text",
                           label = T("Outside Support"),
                           represent = s3_text_represent,
                           widget = s3_comments_widget,
                           readable = False,
                           writable = False,
                           ),

                     # Referrals (incoming/outgoing)
                     organisation_id(label = T("Referral Agency"),
                                     readable = False,
                                     writable = False,
                                     ),
                     provider_type_id(label = T("Referred to"),
                                      ondelete = "RESTRICT",
                                      readable = False,
                                      writable = False,
                                      ),

                     # Follow-up
                     Field("followup", "boolean",
                           default = True if follow_up else None,
                           label = T("Follow up"),
                           represent = s3_yes_no_represent,
                           readable = follow_up,
                           writable = follow_up,
                           ),
                     DateField("followup_date",
                               default = twoweeks if follow_up else None,
                               label = T("Date for Follow-up"),
                               readable = follow_up,
                               writable = follow_up,
                               ),

                     # Status
                     activity_status_id(readable = use_status,
                                        writable = use_status,
                                        ),

                     # Termination and Outcomes
                     termination_type_id(ondelete = "RESTRICT",
                                         readable = False,
                                         writable = False,
                                         ),
                     Field("outcome", "text",
                           label = T("Outcome"),
                           represent = s3_text_represent,
                           widget = s3_comments_widget,
                           readable = use_outcome,
                           writable = use_outcome,
                           ),
                     Field("achievement",
                           label = T("Change achieved"),
                           comment = DIV(_class="tooltip",
                                         _title="%s|%s" % (T("Change achieved"),
                                                           T("What change in the severity of the problem has so far been achieved by this activity?"),
                                                           ),
                                         ),
                           represent = represent_option(dict(achievement_opts)),
                           requires = IS_EMPTY_OR(
                                            IS_IN_SET(achievement_opts,
                                                      sort = False,
                                                      )),
                           readable = use_achievement,
                           writable = use_achievement,
                           ),
                     CommentsField(),
                     )

        # Components
        self.add_components(tablename,
                            dvr_response_action = "case_activity_id",
                            dvr_response_action_theme = "case_activity_id",
                            dvr_case_activity_update = "case_activity_id",
                            dvr_vulnerability = {"link": "dvr_vulnerability_case_activity",
                                                 "joinby": "case_activity_id",
                                                 "key": "vulnerability_id",
                                                 },
                            )

        # List fields
        list_fields = ["start_date"]
        if use_need:
            list_fields.append("need_id")
        if use_subject:
            list_fields.append("subject")
        if need_details:
            list_fields.append("need_details")
        if use_emergency:
            list_fields.append("emergency")
        if response_details:
            list_fields.append("activity_details")
        if use_status:
            list_fields.append("status_id")
        if follow_up:
            list_fields.extend(["followup", "followup_date"])

        # Filter widgets
        filter_widgets = [TextFilter(["person_id$pe_label",
                                      "person_id$first_name",
                                      "person_id$last_name",
                                      "case_id$reference",
                                      "need_details",
                                      "activity_details",
                                      ],
                                     label = T("Search"),
                                     ),
                          # TODO make optional by setting
                          OptionsFilter("emergency",
                                        options = {True: T("Yes"),
                                                   False: T("No"),
                                                   },
                                        cols = 2,
                                        ),
                          # TODO make optional by setting
                          OptionsFilter("need_id",
                                        options = lambda: get_filter_options("dvr_need",
                                                                             translate = True,
                                                                             ),
                                        ),
                          # TODO replace by status filter
                          #OptionsFilter("completed",
                          #              default = False,
                          #              options = {True: T("Yes"),
                          #                         False: T("No"),
                          #                         },
                          #              cols = 2,
                          #              ),
                          ]
        if follow_up:
            filter_widgets.extend([OptionsFilter("followup",
                                                 label = T("Follow-up required"),
                                                 options = {True: T("Yes"),
                                                            False: T("No"),
                                                            },
                                                 cols = 2,
                                                 hidden = True,
                                                 ),
                                   DateFilter("followup_date",
                                              cols = 2,
                                              hidden = True,
                                              ),
                                   ])

        if service_type:
            filter_widgets.insert(3, OptionsFilter("service_id"))

        # Report options
        # TODO adjust after settings
        axes = ["need_id",
                (T("Case Status"), "case_id$status_id"),
                "emergency",
                "completed",
                ]
        if follow_up:
            axes.insert(-1, "followup")
        if service_type:
            axes.insert(2, "service_id")

        facts = [(T("Number of Activities"), "count(id)"),
                 (T("Number of Cases"), "count(case_id)"),
                 ]
        report_options = {"rows": axes,
                          "cols": axes,
                          "fact": facts,
                          "defaults": {"rows": "need_id",
                                       "cols": "completed",
                                       "fact": facts[0],
                                       "totals": True,
                                       "chart": "barchart:rows",
                                       },
                          }

        # Table configuration
        configure(tablename,
                  filter_widgets = filter_widgets,
                  list_fields = list_fields,
                  onaccept = self.case_activity_onaccept,
                  onvalidation = self.case_activity_onvalidation,
                  orderby = "dvr_case_activity.start_date desc",
                  report_options = report_options,
                  super_entity = "doc_entity",
                  )

        # CRUD Strings
        if settings.get_dvr_manage_response_actions():
            # Case activities represent needs, responses are separate
            crud_strings[tablename] = Storage(
                label_create = T("Add Need"),
                title_display = T("Need Details"),
                title_list = T("Needs"),
                title_update = T("Edit Need"),
                label_list_button = T("List Needs"),
                label_delete_button = T("Delete Need"),
                msg_record_created = T("Need added"),
                msg_record_modified = T("Need updated"),
                msg_record_deleted = T("Need deleted"),
                msg_list_empty = T("No Needs currently registered"),
                )
        else:
            # Case activites represent both needs and responses
            crud_strings[tablename] = Storage(
                label_create = T("Create Activity"),
                title_display = T("Activity Details"),
                title_list = T("Activities"),
                title_update = T("Edit Activity"),
                label_list_button = T("List Activities"),
                label_delete_button = T("Delete Activity"),
                msg_record_created = T("Activity added"),
                msg_record_modified = T("Activity updated"),
                msg_record_deleted = T("Activity deleted"),
                msg_list_empty = T("No Activities currently registered"),
                )

        # Foreign Key Template
        represent = dvr_CaseActivityRepresent(show_link=True)
        case_activity_id = FieldTemplate("case_activity_id",
                                         "reference %s" % tablename,
                                         ondelete = "CASCADE",
                                         represent = represent,
                                         requires = IS_EMPTY_OR(
                                                        IS_ONE_OF(db, "%s.id" % tablename,
                                                                  represent,
                                                                  )),
                                         )

        # ---------------------------------------------------------------------
        # Case Activity Update Types
        #
        tablename = "dvr_case_activity_update_type"
        define_table(tablename,
                     Field("name",
                           label = T("Name"),
                           requires = [IS_NOT_EMPTY(), IS_LENGTH(512, minsize=1)],
                           ),
                     CommentsField(),
                     )

        # Table configuration
        configure(tablename,
                  deduplicate = S3Duplicate(),
                  )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Update Type"),
            title_display = T("Update Type Details"),
            title_list = T("Update Types"),
            title_update = T("Edit Update Type"),
            label_list_button = T("List Update Types"),
            label_delete_button = T("Delete Update Type"),
            msg_record_created = T("Update Type added"),
            msg_record_modified = T("Update Type updated"),
            msg_record_deleted = T("Update Type deleted"),
            msg_list_empty = T("No Update Types currently defined"),
            )

        # Foreign Key Template
        represent = S3Represent(lookup=tablename, translate=True)
        update_type_id = FieldTemplate("update_type_id",
                                       "reference %s" % tablename,
                                       label = T("Update Type"),
                                       represent = represent,
                                       requires = IS_EMPTY_OR(
                                                    IS_ONE_OF(db, "%s.id" % tablename,
                                                              represent,
                                                              )),
                                       sortby = "name",
                                       )

        # ---------------------------------------------------------------------
        # Case Activity Updates
        #
        tablename = "dvr_case_activity_update"
        define_table(tablename,
                     case_activity_id(),
                     DateField(default = "now",
                               ),
                     update_type_id(),
                     human_resource_id(comment = None,
                                       widget = None,
                                       ),
                     CommentsField(label = T("Details"),
                                   ),
                     )

        # Table configuration
        configure(tablename,
                  orderby = "%s.date" % tablename,
                  )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return {"dvr_case_activity_id": case_activity_id,
                }

    # -------------------------------------------------------------------------
    def defaults(self):
        """ Safe defaults for names in case the module is disabled """

        dummy = FieldTemplate.dummy

        return {"dvr_case_activity_id": dummy("case_activity_id"),
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def case_activity_status_onaccept(form):
        """
            Onaccept routine for case activity statuses:
                - only one status can be the default

            Args:
                form: the FORM
        """

        form_vars = form.vars
        try:
            record_id = form_vars.id
        except AttributeError:
            record_id = None
        if not record_id:
            return

        # If this status is the default, then set is_default-flag
        # for all other statuses to False:
        if "is_default" in form_vars and form_vars.is_default:
            table = current.s3db.dvr_case_activity_status
            db = current.db
            db(table.id != record_id).update(is_default = False)

    # -------------------------------------------------------------------------
    @staticmethod
    def case_activity_onvalidation(form):
        """
            Validate case activity form:
                - end date must be after start date
        """

        T = current.T

        form_vars = form.vars
        try:
            start = form_vars.start_date
            end = form_vars.end_date
        except AttributeError:
            return

        if start and end and end < start:
            form.errors["end_date"] = T("End date must be after start date")

    # -------------------------------------------------------------------------
    @staticmethod
    def case_activity_close_responses(case_activity_id):
        """
            Close all open response actions in a case activity

            Args:
                case_activity_id: the case activity record ID
        """

        db = current.db
        s3db = current.s3db

        rtable = s3db.dvr_response_action
        stable = s3db.dvr_response_status

        # Get all response actions for this case activity
        # that have an open-status (or no status at all):
        left = stable.on((stable.id == rtable.status_id) & \
                         (stable.deleted == False))
        query = (rtable.case_activity_id == case_activity_id) & \
                (rtable.deleted == False) & \
                ((stable.is_closed == False) | (stable.id == None))
        rows = db(query).select(rtable.id, left=left)

        if rows:

            # Get the default closure status,
            # (usually something like "obsolete")
            query = (stable.is_default_closure == True) & \
                    (stable.deleted == False)
            closure_status = db(query).select(stable.id,
                                              limitby = (0, 1),
                                              ).first()

            # Update all open response actions for this
            # case activity to the default closure status:
            if closure_status:
                response_ids = set(row.id for row in rows)
                query = rtable.id.belongs(response_ids)
                db(query).update(status_id = closure_status.id)

    # -------------------------------------------------------------------------
    @classmethod
    def case_activity_onaccept(cls, form):
        """
            Onaccept-callback for case activites:
                - set end date when marked as completed
                - close any open response actions when marked as completed
        """

        db = current.db
        s3db = current.s3db

        settings = current.deployment_settings

        # Read form data
        form_vars = form.vars
        if "id" in form_vars:
            record_id = form_vars.id
        elif hasattr(form, "record_id"):
            record_id = form.record_id
        else:
            return

        # Get current status and end_date of the record
        atable = s3db.dvr_case_activity
        stable = s3db.dvr_case_activity_status

        left = stable.on(atable.status_id == stable.id)
        query = (atable.id == record_id)
        row = db(query).select(atable.id,
                                atable.end_date,
                                stable.is_closed,
                                left = left,
                                limitby = (0, 1),
                                ).first()
        if not row:
            return
        activity = row.dvr_case_activity

        if row.dvr_case_activity_status.is_closed:

            # Cancel follow-ups for closed activities
            data = {"followup": False,
                    "followup_date": None,
                    }

            # Set end-date if not already set
            if not activity.end_date:
                data["end_date"] = current.request.utcnow.date()

            activity.update_record(**data)

            # Close any open response actions in this activity:
            if settings.get_dvr_manage_response_actions():
                cls.case_activity_close_responses(activity.id)

        elif activity.end_date:

            # Remove end-date if present
            activity.update_record(end_date = None)

# =============================================================================
class DVRCaseAppointmentModel(DataModel):
    """ Model for Case Appointments """

    names = ("dvr_case_appointment",
             "dvr_case_appointment_type",
             "dvr_appointment_type_id",
             "dvr_appointment_status_opts",
             )

    def model(self):

        T = current.T
        db = current.db
        settings = current.deployment_settings

        crud_strings = current.response.s3.crud_strings

        configure = self.configure
        define_table = self.define_table

        use_time = settings.get_dvr_appointments_use_time()
        appointment_types_org_specific = settings.get_dvr_appointment_types_org_specific()
        mandatory_appointments = settings.get_dvr_mandatory_appointments()
        update_case_status = settings.get_dvr_appointments_update_case_status()
        update_last_seen_on = settings.get_dvr_appointments_update_last_seen_on()

        # ---------------------------------------------------------------------
        # Case Appointment Type
        #
        mandatory_comment = DIV(_class="tooltip",
                                _title="%s|%s" % (T("Mandatory Appointment"),
                                                  T("This appointment is mandatory before transfer"),
                                                  ),
                                )

        tablename = "dvr_case_appointment_type"
        define_table(tablename,
                     self.org_organisation_id(
                         comment = None,
                         readable = appointment_types_org_specific,
                         writable = appointment_types_org_specific,
                         ),
                     Field("name", length=64,
                           requires = [IS_NOT_EMPTY(), IS_LENGTH(64, minsize=1)],
                           ),
                     Field("autocreate", "boolean",
                           default = False,
                           label = T("Create automatically"),
                           represent = s3_yes_no_represent,
                           comment = DIV(_class = "tooltip",
                                         _title = "%s|%s" % (T("Create automatically"),
                                                             T("Automatically create this appointment for new cases"),
                                                             ),
                                         ),
                           ),
                     Field("mandatory_children", "boolean",
                           default = False,
                           label = T("Mandatory for Children"),
                           represent = s3_yes_no_represent,
                           readable = mandatory_appointments,
                           writable = mandatory_appointments,
                           comment = mandatory_comment,
                           ),
                     Field("mandatory_adolescents", "boolean",
                           default = False,
                           label = T("Mandatory for Adolescents"),
                           represent = s3_yes_no_represent,
                           readable = mandatory_appointments,
                           writable = mandatory_appointments,
                           comment = mandatory_comment,
                           ),
                     Field("mandatory_adults", "boolean",
                           default = False,
                           label = T("Mandatory for Adults"),
                           represent = s3_yes_no_represent,
                           readable = mandatory_appointments,
                           writable = mandatory_appointments,
                           comment = mandatory_comment,
                           ),
                     Field("presence_required", "boolean",
                           default = True,
                           label = T("Presence required"),
                           represent = s3_yes_no_represent,
                           readable = update_last_seen_on,
                           writable = update_last_seen_on,
                           comment = DIV(_class = "tooltip",
                                         _title = "%s|%s" % (T("Presence required"),
                                                             T("This appointment requires the presence of the person concerned"),
                                                             ),
                                         ),
                           ),
                     self.dvr_case_status_id(
                        label = T("Case Status upon Completion"),
                        readable = update_case_status,
                        writable = update_case_status,
                        ),
                     CommentsField(),
                     )

        # Filter widgets
        filter_widgets = [TextFilter(["name",
                                      "comments",
                                      ],
                                     label = T("Search"),
                                     ),
                           OptionsFilter("organisation_id",
                                         hidden = True,
                                         ),
                          ]

        # Table configuration
        configure(tablename,
                  filter_widgets = filter_widgets,
                  update_realm = True,
                  deduplicate = S3Duplicate(primary = ("name",),
                                            secondary = ("organisation_id",),
                                            ignore_deleted = True,
                                            ),
                  )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Appointment Type"),
            title_display = T("Appointment Type Details"),
            title_list = T("Appointment Types"),
            title_update = T("Edit Appointment Type"),
            label_list_button = T("List Appointment Types"),
            label_delete_button = T("Delete Appointment Type"),
            msg_record_created = T("Appointment Type added"),
            msg_record_modified = T("Appointment Type updated"),
            msg_record_deleted = T("Appointment Type deleted"),
            msg_list_empty = T("No Appointment Types currently registered"),
            )

        # Foreign Key Template
        represent = S3Represent(lookup=tablename, translate=True)
        appointment_type_id = FieldTemplate("type_id", "reference %s" % tablename,
                                            label = T("Appointment Type"),
                                            ondelete = "RESTRICT",
                                            represent = represent,
                                            requires = IS_EMPTY_OR(
                                                            IS_ONE_OF(db, "dvr_case_appointment_type.id",
                                                                      represent,
                                                                      )),
                                            )

        # ---------------------------------------------------------------------
        # Case Appointments
        #
        appointment_status_opts = {1: T("Required"),
                                   2: T("Planned"),
                                   #3: T("In Progress"),
                                   4: T("Completed##appointment"),
                                   5: T("Missed"),
                                   6: T("Cancelled"),
                                   7: T("Not Required"),
                                   }

        tablename = "dvr_case_appointment"
        define_table(tablename,
                     self.dvr_case_id(comment = None,
                                      # @ToDo: Populate this onaccept from imports
                                      #empty = False,
                                      label = T("Case Number"),
                                      ondelete = "CASCADE",
                                      readable = False,
                                      writable = False,
                                      ),
                     # Beneficiary (component link):
                     # @todo: populate from case and hide in case perspective
                     self.pr_person_id(comment = None,
                                       empty = False,
                                       ondelete = "CASCADE",
                                       writable = False,
                                       ),
                     appointment_type_id(empty = False,
                                         ),

                     # Date/Time
                     DateField(label = T("Planned on"),
                               readable = not use_time,
                               writable = not use_time,
                               ),
                     DateTimeField("start_date",
                                   label = T("Date"),
                                   set_min = "#dvr_case_appointment_end_date",
                                   readable = use_time,
                                   writable = use_time,
                                   ),
                     DateTimeField("end_date",
                                   label = T("End"),
                                   set_max = "#dvr_case_appointment_start_date",
                                   readable = use_time,
                                   writable = use_time,
                                   ),

                     # Activate in template as needed:
                     self.hrm_human_resource_id(comment = None,
                                                widget = None,
                                                readable = False,
                                                writable = False,
                                                ),
                     Field("status", "integer",
                           default = 1, # Planning
                           requires = IS_IN_SET(appointment_status_opts,
                                                zero = None,
                                                ),
                           represent = represent_option(appointment_status_opts),
                           ),
                     CommentsField(),
                     )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Appointment"),
            title_display = T("Appointment Details"),
            title_list = T("Appointments"),
            title_update = T("Edit Appointment"),
            label_list_button = T("List Appointments"),
            label_delete_button = T("Delete Appointment"),
            msg_record_created = T("Appointment added"),
            msg_record_modified = T("Appointment updated"),
            msg_record_deleted = T("Appointment deleted"),
            msg_list_empty = T("No Appointments currently registered"),
            )

        # Custom methods
        self.set_method("dvr_case_appointment",
                        method = "manage",
                        action = DVRManageAppointments,
                        )

        configure(tablename,
                  deduplicate = S3Duplicate(primary = ("person_id",
                                                       "type_id",
                                                       ),
                                            ),
                  onaccept = self.case_appointment_onaccept,
                  ondelete = self.case_appointment_ondelete,
                  onvalidation = self.case_appointment_onvalidation,
                  )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return {"dvr_appointment_status_opts": appointment_status_opts,
                "dvr_appointment_type_id": appointment_type_id,
                }

    # -------------------------------------------------------------------------
    def defaults(self):
        """ Safe defaults for names in case the module is disabled """

        return {"dvr_appointment_status_opts": {},
                "dvr_appointment_type_id": FieldTemplate.dummy("type_id"),
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def case_appointment_onvalidation(form):
        """
            Validate appointment form
                - Start date must be before end date
                - Future appointments can not be set to completed
                - Undated appointments can not be set to completed

            Args:
                form: the FORM
        """

        T = current.T

        use_time = current.deployment_settings.get_dvr_appointments_use_time()
        if use_time:
            fields = ["start_date", "end_date", "status"]
        else:
            fields = ["date", "status"]

        table = current.s3db.dvr_case_appointment
        data = get_form_record_data(form, table, fields)
        status = data["status"]
        now = current.request.utcnow

        if use_time:
            start, end = data["start_date"], data["end_date"]
            if start and end and start >= end:
                if "end_date" in form.vars:
                    form.errors.end_date = T("End date must be after start date")
                else:
                    form.errors.start_date = T("Start date must be before end date")
            date = start
            date_field = "start_date"
        else:
            date = data["date"]
            date_field = "date"
            now = now.date()

        if str(status) == "4":
            if date is None:
                form.errors[date_field] = T("Date is required when marking the appointment as completed")
            elif date > now:
                form.errors["status"] = T("Appointments with future dates can not be marked as completed")

    # -------------------------------------------------------------------------
    @staticmethod
    def case_appointment_onaccept(form):
        """
            Actions after creating/updating appointments
                - Fix status+date to plausible combinations
                - Update last_seen_on in the corresponding case(s)
                - Update the case status if configured to do so

            Args:
                form: the FORM
        """

        # Read form data
        record_id = get_form_record_id(form)
        if not record_id:
            return

        db = current.db
        s3db = current.s3db
        settings = current.deployment_settings
        use_time = settings.get_dvr_appointments_use_time()

        # Reload the record
        table = s3db.dvr_case_appointment
        record = db(table.id == record_id).select(table.id,
                                                  table.case_id,
                                                  table.person_id,
                                                  table.date,
                                                  table.start_date,
                                                  table.end_date,
                                                  table.status,
                                                  limitby = (0, 1),
                                                  ).first()

        person_id = record.person_id
        case_id = record.case_id

        # Fix status/date to plausible combinations
        now = current.request.utcnow
        today = now.date()
        time_window = AppointmentEvent.time_window

        status = record.status
        update = {}

        if use_time:
            start, end = record.start_date, record.end_date
            if end and not start:
                end = update["end_date"] = None
            if start and not end:
                end = update["end_date"] = time_window(start, duration=60)[1]
            date = start.date() if start else None
            future = (start > now) if start else False
        else:
            date = record.date
            future = (date > today) if date else False

        fix_date = False
        if status == 3: # in progress
            fix_date = True
        elif date:
            if status == 7: # not required
                update["date"] = update["start_date"] = update["end_date"] = None
            elif status == 1: # required
                update["status"] = 2
            elif status == 4 and future: # completed
                update["status"] = 2
        elif status == 2: # planned
            update["status"] = 1
        elif status == 4: # completed
            fix_date = True

        if fix_date:
            if use_time:
                window = time_window(now)
                if not start or start > now:
                    start = update["start_date"] = window[0]
                if not end or end < now:
                    end = update["end_date"] = window[1]
            else:
                date = update["date"] = today

        if use_time:
            # Always set date
            update["date"] = start.date() if start else None
        if update:
            record.update_record(**update)

        # Update last-seen-on date when appointment gets updated
        if settings.get_dvr_appointments_update_last_seen_on() and person_id:
            dvr_update_last_seen(person_id)

        # Update the case status if appointment is completed
        # NB appointment status "completed" must be set by this form
        if settings.get_dvr_appointments_update_case_status() and \
           s3_str(form.vars.get("status")) == "4":

            # Get the case status to be set for the last completed
            # appointment of this client
            ttable = s3db.dvr_case_appointment_type
            join = ttable.on((ttable.id == table.type_id) & \
                             (ttable.status_id != None))
            query = (table.person_id == person_id) & \
                    (table.status == 4) & \
                    (table.deleted == False)
            if case_id:
                query = (table.case_id == case_id) & query
            orderby = ~table.start_date if use_time else ~table.date
            row = db(query).select(ttable.status_id,
                                   join = join,
                                   orderby = orderby,
                                   limitby = (0, 1),
                                   ).first()
            status_id = row.status_id if row else None

            if status_id:
                # Get open case statuses
                stable = s3db.dvr_case_status
                open_status = db(stable.is_closed == False)._select(stable.id)

                # All open cases of this client that do not have this status
                ctable = s3db.dvr_case
                query = current.auth.s3_accessible_query("update", ctable) & \
                        (ctable.person_id == person_id) & \
                        (ctable.archived == False) & \
                        (ctable.deleted == False) & \
                        (ctable.status_id != status_id) & \
                        (ctable.status_id.belongs(open_status))
                if case_id:
                    query = (ctable.id == case_id) & query

                # Update cases
                cases = db(query).select(ctable.id)
                if cases:
                    r = CRUDRequest("dvr", "case",
                                    current.request,
                                    args = [],
                                    get_vars = {},
                                    )
                    r.customise_resource("dvr_case")
                    for case in cases:
                        case.update_record(status_id = status_id)
                        s3db.onaccept(ctable, case, method="update")

    # -------------------------------------------------------------------------
    @staticmethod
    def case_appointment_ondelete(row):
        """
            Actions after deleting appointments
                - Update last_seen_on in the corresponding case(s)

            Args:
                row: the deleted Row
        """

        if current.deployment_settings.get_dvr_appointments_update_last_seen_on():

            # Update last_seen_on
            person_id = row.person_id
            if person_id:
                dvr_update_last_seen(person_id)

# =============================================================================
class DVRResidenceStatusModel(DataModel):
    """ Models to document the residence status of a client """

    names = ("dvr_residence_status_type",
             "dvr_residence_permit_type",
             "dvr_residence_status",
             )

    def model(self):

        T = current.T

        db = current.db
        s3 = current.response.s3

        define_table = self.define_table
        crud_strings = s3.crud_strings

        # ---------------------------------------------------------------------
        # Residence Status Types
        #
        tablename = "dvr_residence_status_type"
        define_table(tablename,
                     Field("name",
                           requires = [IS_NOT_EMPTY(), IS_LENGTH(512, minsize=1)],
                           ),
                     CommentsField(),
                     )

        # Table Configuration
        self.configure(tablename,
                       deduplicate = S3Duplicate(),
                       )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Residence Status Type"),
            title_display = T("Residence Status Type Details"),
            title_list = T("Residence Status Types"),
            title_update = T("Edit Residence Status Type"),
            label_list_button = T("List Residence Status Types"),
            label_delete_button = T("Delete Residence Status Type"),
            msg_record_created = T("Residence Status Type created"),
            msg_record_modified = T("Residence Status Type updated"),
            msg_record_deleted = T("Residence Status Type deleted"),
            msg_list_empty = T("No Residence Status Types currently defined"),
            )

        # Foreign Key Template
        represent = S3Represent(lookup=tablename, translate=True)
        status_type_id = FieldTemplate("status_type_id",
                                       "reference %s" % tablename,
                                       label = T("Residence Status"),
                                       represent = represent,
                                       requires = IS_EMPTY_OR(
                                                    IS_ONE_OF(db, "%s.id" % tablename,
                                                              represent,
                                                              )),
                                       sortby = "name",
                                       )

        # ---------------------------------------------------------------------
        # Residence Permit Types
        #
        tablename = "dvr_residence_permit_type"
        define_table(tablename,
                     Field("name",
                           requires = [IS_NOT_EMPTY(), IS_LENGTH(512, minsize=1)],
                           ),
                     CommentsField(),
                     )

        # Table Configuration
        self.configure(tablename,
                       deduplicate = S3Duplicate(),
                       )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Residence Permit Type"),
            title_display = T("Residence Permit Type Details"),
            title_list = T("Residence Permit Types"),
            title_update = T("Edit Residence Permit Type"),
            label_list_button = T("List Residence Permit Types"),
            label_delete_button = T("Delete Residence Permit Type"),
            msg_record_created = T("Residence Permit Type created"),
            msg_record_modified = T("Residence Permit Type updated"),
            msg_record_deleted = T("Residence Permit Type deleted"),
            msg_list_empty = T("No Residence Permit Types currently defined"),
            )

        # Foreign Key Template
        represent = S3Represent(lookup=tablename, translate=True)
        permit_type_id = FieldTemplate("permit_type_id",
                                       "reference %s" % tablename,
                                       label = T("Residence Permit Type"),
                                       represent = represent,
                                       requires = IS_EMPTY_OR(
                                                    IS_ONE_OF(db, "%s.id" % tablename,
                                                              represent,
                                                              )),
                                       sortby = "name",
                                       )

        # ---------------------------------------------------------------------
        # Residence Status
        #
        tablename = "dvr_residence_status"
        define_table(tablename,
                     self.pr_person_id(),
                     status_type_id(),
                     permit_type_id(),
                     Field("reference",
                           label = T("ID/Ref.No."),
                           ),
                     DateField("valid_from",
                               label = T("Valid From"),
                               ),
                     DateField("valid_until",
                               label = T("Valid Until"),
                               ),
                     #Field("obsolete", "boolean",
                     #      default = False,
                     #      ),
                     CommentsField(),
                     )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Residence Status"),
            title_display = T("Residence Status Details"),
            title_list = T("Residence Statuses"),
            title_update = T("Edit Residence Status"),
            label_list_button = T("List Residence Statuses"),
            label_delete_button = T("Delete Residence Status"),
            msg_record_created = T("Residence Status created"),
            msg_record_modified = T("Residence Status updated"),
            msg_record_deleted = T("Residence Status deleted"),
            msg_list_empty = T("No Residence Statuses currently defined"),
            )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        # return {}

# =============================================================================
class DVRCaseAllowanceModel(DataModel):
    """ Model for Allowance Management """

    names = ("dvr_allowance",
             )

    def model(self):

        T = current.T

        crud_strings = current.response.s3.crud_strings

        configure = self.configure
        define_table = self.define_table
        set_method = self.set_method

        # ---------------------------------------------------------------------
        # Allowance Information
        #
        allowance_status_opts = {1: T("pending"),
                                 2: T("paid"),
                                 3: T("refused"),
                                 4: T("missed"),
                                 }
        amount_represent = lambda v: IS_FLOAT_AMOUNT.represent(v,
                                                               precision = 2,
                                                               fixed = True,
                                                               )

        tablename = "dvr_allowance"
        define_table(tablename,
                     # Beneficiary (component link):
                     # @todo: populate from case and hide in case perspective
                     self.pr_person_id(comment = None,
                                       empty = False,
                                       ondelete = "CASCADE",
                                       ),
                     self.dvr_case_id(# @ToDo: Populate this onaccept from imports
                                      #empty = False,
                                      label = T("Case Number"),
                                      ondelete = "CASCADE",
                                      ),
                     DateField("entitlement_period",
                               label = T("Entitlement Period"),
                               ),
                     DateField(default="now",
                               label = T("Planned on"),
                               ),
                     DateTimeField("paid_on",
                                   label = T("Paid on"),
                                   future = 0,
                                   ),
                     Field("amount", "double",
                           label = T("Amount"),
                           requires = IS_EMPTY_OR(IS_FLOAT_AMOUNT(minimum=0.0)),
                           represent = amount_represent,
                           ),
                     CurrencyField(),
                     Field("status", "integer",
                           default = 1, # pending
                           requires = IS_IN_SET(allowance_status_opts,
                                                zero = None,
                                                ),
                           represent = represent_option(allowance_status_opts),
                           widget = S3GroupedOptionsWidget(cols = 4,
                                                           multiple = False,
                                                           ),
                           ),
                     CommentsField(),
                     )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Allowance Information"),
            title_display = T("Allowance Information"),
            title_list = T("Allowance Information"),
            title_update = T("Edit Allowance Information"),
            label_list_button = T("List Allowance Information"),
            label_delete_button = T("Delete Allowance Information"),
            msg_record_created = T("Allowance Information added"),
            msg_record_modified = T("Allowance Information updated"),
            msg_record_deleted = T("Allowance Information deleted"),
            msg_list_empty = T("No Allowance Information currently registered"),
            )

        # Custom list fields
        list_fields = ["person_id",
                       "entitlement_period",
                       "date",
                       "currency",
                       "amount",
                       "status",
                       "paid_on",
                       "comments",
                       ]

        # Table configuration
        configure(tablename,
                  deduplicate = S3Duplicate(primary = ("person_id",
                                                       "entitlement_period",
                                                       ),
                                            ),
                  list_fields = list_fields,
                  onaccept = self.allowance_onaccept,
                  ondelete = self.allowance_ondelete,
                  onvalidation = self.allowance_onvalidation,
                  )

        set_method("dvr_allowance",
                   method = "register",
                   action = DVRRegisterPayment,
                   )
        set_method("dvr_allowance",
                   method = "manage",
                   action = DVRManageAllowance,
                   )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return {"dvr_allowance_status_opts": allowance_status_opts,
                }

    # -------------------------------------------------------------------------
    def defaults(self):
        """ Safe defaults for names in case the module is disabled """

        return {"dvr_allowance_status_opts": {},
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def allowance_onvalidation(form):
        """
            Validate allowance form
                - Status paid requires paid_on date

            Args:
                form: the FORM
        """

        formvars = form.vars

        date = formvars.get("paid_on")
        status = formvars.get("status")

        if str(status) == "2" and not date:
            form.errors["paid_on"] = current.T("Date of payment required")

    # -------------------------------------------------------------------------
    @staticmethod
    def allowance_onaccept(form):
        """
            Actions after creating/updating allowance information
                - update last_seen_on
        """

        if current.deployment_settings.get_dvr_payments_update_last_seen_on():

            # Read form data
            form_vars = form.vars
            if "id" in form_vars:
                record_id = form_vars.id
            elif hasattr(form, "record_id"):
                record_id = form.record_id
            else:
                record_id = None
            if not record_id:
                return

            if current.response.s3.bulk and "status" not in form_vars:
                # Import without status change won't affect last_seen_on,
                # so we can skip this check for better performance
                return

            # Get the person ID
            table = current.s3db.dvr_allowance
            row = current.db(table.id == record_id).select(table.person_id,
                                                           limitby = (0, 1),
                                                           ).first()
            # Update last_seen_on
            if row:
                dvr_update_last_seen(row.person_id)

    # -------------------------------------------------------------------------
    @staticmethod
    def allowance_ondelete(row):
        """
            Actions after deleting allowance information
                - Update last_seen_on in the corresponding case(s)

            Args:
                row: the deleted Row
        """

        if current.deployment_settings.get_dvr_payments_update_last_seen_on():

            # Get the deleted keys
            table = current.s3db.dvr_allowance
            row = current.db(table.id == row.id).select(table.deleted_fk,
                                                        limitby = (0, 1),
                                                        ).first()
            if row and row.deleted_fk:

                # Get the person ID
                try:
                    deleted_fk = json.loads(row.deleted_fk)
                except (ValueError, TypeError):
                    person_id = None
                else:
                    person_id = deleted_fk.get("person_id")

                # Update last_seen_on
                if person_id:
                    dvr_update_last_seen(person_id)

# =============================================================================
class DVRCaseEventModel(DataModel):
    """ Model representing monitoring events for cases """

    names = ("dvr_case_event_type",
             "dvr_case_event",
             )

    def model(self):

        T = current.T

        db = current.db
        s3 = current.response.s3
        settings = current.deployment_settings

        crud_strings = s3.crud_strings

        configure = self.configure
        define_table = self.define_table

        # ---------------------------------------------------------------------
        # Case Event Types
        #
        role_table = str(current.auth.settings.table_group)
        role_represent = S3Represent(lookup=role_table, fields=("role",))

        event_types_org_specific = settings.get_dvr_case_event_types_org_specific()
        close_appointments = settings.get_dvr_case_events_close_appointments()
        register_activities = settings.get_dvr_case_events_register_activities()

        event_classes = {#"A": T("Administrative"),
                         "B": T("Activity"),
                         "C": T("Checkpoint"),
                         #"D": T("NFI Distribution"),
                         "F": T("Food Distribution"),
                         #"P": T("Payment"),
                         }

        tablename = "dvr_case_event_type"
        define_table(tablename,
                     self.org_organisation_id(
                         comment = None,
                         readble = event_types_org_specific,
                         writable = event_types_org_specific,
                         ),
                     Field("event_class",
                           label = T("Event Class"),
                           default = "C",
                           requires = IS_IN_SET(event_classes, zero=None),
                           represent = represent_option(event_classes),
                           ),
                     Field("code", length=64,
                           label = T("Code"),
                           requires = [IS_NOT_EMPTY(),
                                       IS_LENGTH(64, minsize=1),
                                       # uniqueness only required within organisation
                                       #IS_NOT_ONE_OF(db, "dvr_case_event_type.code"),
                                       ],
                           comment = T("A unique code for this event type"),
                           ),
                     Field("name",
                           label = T("Name"),
                           requires = [IS_NOT_EMPTY(), IS_LENGTH(512, minsize=1)],
                           ),
                     Field("is_inactive", "boolean",
                           default = False,
                           label = T("Inactive"),
                           represent = BooleanRepresent(icons = (BooleanRepresent.NEG,
                                                                 BooleanRepresent.POS,
                                                                 ),
                                                        labels = False,
                                                        flag = True,
                                                        ),
                           comment = T("This event type can not currently be registered"),
                           ),
                     Field("is_default", "boolean",
                           default = False,
                           label = T("Default Event Type"),
                           represent = BooleanRepresent(icons = True,
                                                        labels = False,
                                                        flag = True,
                                                        ),
                           comment = T("Assume this event type if no type was specified for an event"),
                           ),
                     Field("register_multiple", "boolean",
                           label = T("Allow registration for family members"),
                           default = False,
                           represent = BooleanRepresent(icons=True, colors=True),
                           comment = T("Allow registration of the same event for multiple family members with a single ID"),
                           ),
                     Field("residents_only", "boolean",
                           label = T("Current residents only"),
                           default = False,
                           represent = BooleanRepresent(icons=True, colors=True),
                           comment = T("Registration requires that the person is checked-in at a shelter"),
                           ),
                     Field("role_required", "reference %s" % role_table,
                           label = T("User Role Required"),
                           ondelete = "SET NULL",
                           represent = role_represent,
                           requires = IS_EMPTY_OR(IS_ONE_OF(db,
                                                            "%s.id" % role_table,
                                                            role_represent,
                                                            )),
                           comment = T("User role required to register events of this type"),
                           ),
                     self.dvr_appointment_type_id(
                            "appointment_type_id",
                            label = T("Appointment Type"),
                            readable = close_appointments,
                            writable = close_appointments,
                            comment = T("The type of appointments which are completed with this type of event"),
                            ),
                     self.act_activity_id(
                            label = T("Activity"),
                            ondelete = "SET NULL",
                            readable = register_activities,
                            writable = register_activities,
                            comment = T("The activity to register participation for with this type of event"),
                            ),
                     Field("min_interval", "double",
                           label = T("Minimum Interval (Hours)"),
                           comment = T("Minimum interval between two consecutive registrations of this event type for the same person"),
                           requires = IS_EMPTY_OR(IS_FLOAT_IN_RANGE(0.0, None)),
                           ),
                     Field("max_per_day", "integer",
                           label = T("Maximum Number per Day"),
                           comment = T("Maximum number of occurences of this event type for the same person on the same day"),
                           requires = IS_EMPTY_OR(IS_INT_IN_RANGE(0, None)),
                           ),
                     Field("presence_required", "boolean",
                           default = True,
                           label = T("Presence required"),
                           represent = s3_yes_no_represent,
                           comment = T("This event type requires the presence of the person concerned"),
                           ),
                     CommentsField(),
                     )

        # Components
        self.add_components(tablename,
                            dvr_case_event = {"name": "excluded_by",
                                              "link": "dvr_case_event_exclusion",
                                              "joinby": "type_id",
                                              "key": "excluded_by_id",
                                              },
                            )

        # Filter widgets
        filter_widgets = [TextFilter(["name",
                                      "code",
                                      "comments",
                                      ],
                                     label = T("Search"),
                                     ),
                           OptionsFilter("event_class",
                                         options = event_classes,
                                         hidden = True,
                                         ),
                           OptionsFilter("organisation_id",
                                         hidden = True,
                                         ),
                          ]

        # Table Configuration
        configure(tablename,
                  deduplicate = S3Duplicate(primary = ("code", "name"),
                                            secondary = ("organisation_id",),
                                            ignore_deleted = True,
                                            ),
                  filter_widgets = filter_widgets,
                  onvalidation = self.case_event_type_onvalidation,
                  onaccept = self.case_event_type_onaccept,
                  )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Event Type"),
            title_display = T("Event Type Details"),
            title_list = T("Event Types"),
            title_update = T("Edit Event Type"),
            label_list_button = T("List Event Types"),
            label_delete_button = T("Delete Event Type"),
            msg_record_created = T("Event Type created"),
            msg_record_modified = T("Event Type updated"),
            msg_record_deleted = T("Event Type deleted"),
            msg_list_empty = T("No Event Types currently defined"),
        )

        # Foreign Key Template
        represent = S3Represent(lookup=tablename, translate=True)
        event_type_id = FieldTemplate("type_id", "reference %s" % tablename,
                                      label = T("Event Type"),
                                      ondelete = "RESTRICT",
                                      represent = represent,
                                      requires = IS_ONE_OF(db, "%s.id" % tablename,
                                                           represent,
                                                           ),
                                      sortby = "name",
                                      comment = PopupLink(c = "dvr",
                                                          f = "case_event_type",
                                                          tooltip = T("Create a new event type"),
                                                          ),
                                      )

        # ---------------------------------------------------------------------
        # Case Event Types, Impermissible Combinations
        #
        tablename = "dvr_case_event_exclusion"
        define_table(tablename,
                     event_type_id(comment = None,
                                   ondelete = "CASCADE",
                                   ),
                     event_type_id("excluded_by_id",
                                   comment = None,
                                   label = T("Not Combinable With"),
                                   ondelete = "CASCADE",
                                   ),
                     )

        # Table Configuration
        configure(tablename,
                  deduplicate = S3Duplicate(primary = ("type_id",
                                                       "excluded_by_id",
                                                       ),
                                            ),
                  )

        # ---------------------------------------------------------------------
        # Case Events
        #
        tablename = "dvr_case_event"
        define_table(tablename,
                     self.dvr_case_id(comment = None,
                                      empty = False,
                                      label = T("Case Number"),
                                      ondelete = "CASCADE",
                                      readable = False,
                                      writable = False,
                                      ),
                     # Beneficiary (component link):
                     # @todo: populate from case and hide in case perspective
                     self.pr_person_id(comment = None,
                                       empty = False,
                                       ondelete = "CASCADE",
                                       writable = False,
                                       ),
                     event_type_id(comment = None,
                                   ondelete = "CASCADE",
                                   # Not user-writable as this is for automatic
                                   # event registration, override in template if
                                   # required:
                                   writable = False,
                                   ),
                     DateTimeField(label = T("Date/Time"),
                                   default = "now",
                                   empty = False,
                                   future = 0,
                                   writable = False,
                                   ),
                     Field("present", "boolean",
                           default = False,
                           readable = False,
                           writable = False,
                           ),
                     # Field for quantitative recording of case events
                     # for statistical purposes (without linking them to
                     # individual cases)
                     Field("quantity", "integer",
                           label = T("Quantity"),
                           default = 1,
                           requires = IS_EMPTY_OR(IS_INT_IN_RANGE(0, None)),
                           # activate in template as required
                           readable = False,
                           writable = False,
                           ),
                     CommentsField(),
                     )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Event"),
            title_display = T("Event Details"),
            title_list = T("Events"),
            title_update = T("Edit Event"),
            label_list_button = T("List Events"),
            label_delete_button = T("Delete Event"),
            msg_record_created = T("Event added"),
            msg_record_modified = T("Event updated"),
            msg_record_deleted = T("Event deleted"),
            msg_list_empty = T("No Events currently registered"),
            )

        # Filter Widgets
        filter_widgets = [TextFilter(["person_id$pe_label",
                                      "person_id$first_name",
                                      "person_id$middle_name",
                                      "person_id$last_name",
                                      "created_by$email",
                                      "comments",
                                      ],
                                     label = T("Search"),
                                     ),
                          OptionsFilter("type_id",
                                        options = lambda: get_filter_options("dvr_case_event_type",
                                                                             translate = True,
                                                                             ),
                                        ),
                          DateFilter("date"),
                          ]

        # Table Configuration
        configure(tablename,
                  create_onaccept = self.case_event_create_onaccept,
                  deduplicate = S3Duplicate(primary = ("person_id",
                                                       "type_id",
                                                       ),
                                            ),
                  filter_widgets = filter_widgets,
                  # Not user-insertable as this is for automatic
                  # event registration, override in template if
                  # required:
                  insertable = False,
                  list_fields = ["person_id",
                                 "date",
                                 "type_id",
                                 (T("Registered by"), "created_by"),
                                 "comments",
                                 ],
                  ondelete = self.case_event_ondelete,
                  orderby = "%s.date desc" % tablename,
                  )

        # Custom method for event registration
        self.set_method("dvr_case_event",
                        method = "register",
                        action = Checkpoint,
                        )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        # return {}

    # -------------------------------------------------------------------------
    @staticmethod
    def case_event_type_onvalidation(form):
        """
            Form validation of case event types
                - code must be unique (within the organisation)
                - multiple-registration excluded when presence required

            Args:
                form: the FORM
        """

        T = current.T

        table = current.s3db.dvr_case_event_type
        data = get_form_record_data(form, table, ["code",
                                                  "organisation_id",
                                                  "register_multiple",
                                                  "presence_required",
                                                  ])
        code = data.get("code")
        if code:
            # Check that code is unique for the organisation
            query = (table.code == code) & \
                    (table.organisation_id == data.get("organisation_id")) & \
                    (table.deleted == False)
            record_id = get_form_record_id(form)
            if record_id:
                query &= (table.id != record_id)
            if current.db(query).select(table.id, limitby=(0, 1)).first():
                form.errors.code = T("Code must be unique")

        presence_required = data.get("presence_required")
        register_multiple = data.get("register_multiple")
        if presence_required and register_multiple:
            msg = T("Presence required excludes multiple-registration")
            form.errors.register_multiple = msg

    # -------------------------------------------------------------------------
    @staticmethod
    def case_event_type_onaccept(form):
        """
            Onaccept routine for case event types:
                - only one type within the event class can be the default

            Args:
                form: the FORM
        """

        settings = current.deployment_settings

        record_id = get_form_record_id(form)
        if not record_id:
            return

        table = current.s3db.dvr_case_event_type
        fields = ["organisation_id", "event_class"]
        data = get_form_record_data(form, table, fields)

        # If this type is the default, then set is_default-flag
        # for all other types of the same event class to False:
        form_vars = form.vars
        if "is_default" in form_vars and form_vars.is_default:
            query = (table.id != record_id) & \
                    (table.event_class == data.get("event_class"))
            if settings.get_dvr_case_event_types_org_specific():
                # ...within the same organisation
                query &= (table.organisation_id == data.get("organisation_id"))
            current.db(query).update(is_default = False)

    # -------------------------------------------------------------------------
    @staticmethod
    def case_event_create_onaccept(form):
        """
            Actions after creation of a case event:
                - update last_seen_on in the corresponding cases
                - close appointments if configured to do so

            Args:
                form: the FORM
        """

        db = current.db
        s3db = current.s3db
        settings = current.deployment_settings

        record_id = get_form_record_id(form)
        if not record_id:
            return

        table = s3db.dvr_case_event
        fields = ("person_id", "type_id")
        form_data = get_form_record_data(form, table, fields)

        person_id = form_data["person_id"]
        if not person_id:
            return

        # Get the event type
        type_id = form_data["type_id"]
        ttable = s3db.dvr_case_event_type
        query = (ttable.id == type_id) & \
                (ttable.deleted == False)
        event_type = db(query).select(ttable.presence_required,
                                      ttable.appointment_type_id,
                                      ttable.activity_id,
                                      limitby = (0, 1),
                                      ).first()
        if not event_type:
            return

        # Update last_seen (if event type requires personal presence)
        if event_type.presence_required:
            db(table.id == record_id).update(present=True)
            dvr_update_last_seen(person_id)

        # Close appointment
        if event_type.appointment_type_id and \
           settings.get_dvr_case_events_close_appointments():
            try:
                appointment_id = AppointmentEvent(record_id).close()
            except S3PermissionError:
                current.log.error("Not permitted to close appointment for event %s" % record_id)
            else:
                if not appointment_id:
                    current.log.error("Could not close appointment for event %s" % record_id)

        # Register activity
        if event_type.activity_id and \
           settings.get_dvr_case_events_register_activities():
            try:
                beneficiary_id = ActivityEvent(record_id).register()
            except S3PermissionError:
                current.log.error("Not permitted to register activity for event %s" % record_id)
            else:
                if not beneficiary_id:
                    current.log.error("Could not register activity for event %s" % record_id)

    # -------------------------------------------------------------------------
    @staticmethod
    def case_event_ondelete(row):
        """
            Actions after deleting a case event:
                - update last_seen_on in the corresponding cases

            Args:
                row: the deleted Row
        """

        # Get the deleted keys
        table = current.s3db.dvr_case_event
        row = current.db(table.id == row.id).select(table.deleted_fk,
                                                    limitby = (0, 1),
                                                    ).first()
        if row and row.deleted_fk:

            # Get the person ID
            try:
                deleted_fk = json.loads(row.deleted_fk)
            except (ValueError, TypeError):
                person_id = None
            else:
                person_id = deleted_fk.get("person_id")

            # Update last_seen_on
            if person_id:
                dvr_update_last_seen(person_id)

# =============================================================================
class DVRVulnerabilityModel(DataModel):
    """ Specific vulnerabilities of a client """

    names = ("dvr_vulnerability_type",
             "dvr_vulnerability_type_sector",
             "dvr_vulnerability",
             "dvr_vulnerability_response_action",
             "dvr_vulnerability_case_activity",
             )

    def model(self):

        T = current.T
        db = current.db

        s3 = current.response.s3
        crud_strings = s3.crud_strings

        define_table = self.define_table

        # ---------------------------------------------------------------------
        # Vulnerability Types
        #
        tablename = "dvr_vulnerability_type"
        define_table(tablename,
                     Field("name",
                           label = T("Vulnerability Type"),
                           requires = [IS_NOT_EMPTY(), IS_LENGTH(512, minsize=1)],
                           ),
                     Field("code", length=64, unique=True,
                           label = T("Code"),
                           represent = lambda v, row=None: v if v else "",
                           requires = IS_EMPTY_OR([
                                            IS_LENGTH(64),
                                            IS_NOT_ONE_OF(db, "dvr_vulnerability_type.code"),
                                            ]),
                           ),
                     Field("obsolete", "boolean",
                           label = T("Obsolete"),
                           default = False,
                           represent = BooleanRepresent(labels = False,
                                                        # Reverse icons semantics
                                                        icons = (BooleanRepresent.NEG,
                                                                 BooleanRepresent.POS,
                                                                 ),
                                                        flag = True,
                                                        ),
                           ),
                     CommentsField(),
                     )

        # Components
        self.add_components(tablename,
                            org_sector = {"link": "dvr_vulnerability_type_sector",
                                          "joinby": "vulnerability_type_id",
                                          "key": "sector_id",
                                          },
                            )

        # CRUD form with embedded sector link
        crud_form = CustomForm("name",
                               "code",
                               InlineLink("sector",
                                          field = "sector_id",
                                          label = T("Sectors"),
                                          ),
                               "obsolete",
                               "comments",
                               )

        # List fields to include sectors
        list_fields = ["name",
                       "code",
                       "vulnerability_type_sector.sector_id",
                       "obsolete",
                       ]

        self.configure(tablename,
                       crud_form = crud_form,
                       list_fields = list_fields,
                       deduplicate = S3Duplicate(primary = ("name",),
                                                 secondary = ("code",),
                                                 ),
                       )

        # CRUD strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Vulnerability Type"),
            title_display = T("Vulnerability Type Details"),
            title_list = T("Vulnerability Types"),
            title_update = T("Edit Vulnerability Type"),
            label_list_button = T("List Vulnerability Types"),
            label_delete_button = T("Delete Vulnerability Type"),
            msg_record_created = T("Vulnerability Type created"),
            msg_record_modified = T("Vulnerability Type updated"),
            msg_record_deleted = T("Vulnerability Type deleted"),
            msg_list_empty = T("No Vulnerability Types currently defined"),
        )

        # Field template
        represent = S3Represent(lookup=tablename, translate=True)
        vulnerability_type_id = FieldTemplate("vulnerability_type_id",
                                              "reference %s" % tablename,
                                              label = T("Vulnerability Type"),
                                              ondelete = "RESTRICT",
                                              represent = represent,
                                              requires = IS_EMPTY_OR(
                                                            IS_ONE_OF(db, "dvr_vulnerability_type.id",
                                                                      represent,
                                                                      sort=True,
                                                                      not_filterby = "obsolete",
                                                                      not_filter_opts = (True,),
                                                                      )),
                                              sortby = "name",
                                              )

        # ---------------------------------------------------------------------
        # Link vulnerability type<=>sector
        #
        tablename = "dvr_vulnerability_type_sector"
        define_table(tablename,
                     vulnerability_type_id(ondelete="CASCADE"),
                     self.org_sector_id(ondelete = "CASCADE",
                                        comment = None,
                                        ),
                     )

        # ---------------------------------------------------------------------
        # Vulnerability
        # - a situation or attribute of the beneficiary that makes certain
        #   risks more likely or more severe, and can trigger or moderate
        #   specific needs (e.g. protection) or rights
        #
        tablename = "dvr_vulnerability"
        define_table(tablename,
                     # Person affected
                     self.pr_person_id(),
                     vulnerability_type_id(empty = False,
                                           ),
                     Field("description", "text",
                           label = T("Details"),
                           represent = s3_text_represent,
                           ),
                     DateField(default = "now",
                               empty = False,
                               label = T("Established on"),
                               future = 0,
                               set_min = "#dvr_vulnerability_end_date",
                               ),
                     DateField("end_date",
                               label = T("Relevant until"),
                               set_max = "#dvr_vulnerability_date",
                               ),
                     # Enable in template as-required:
                     self.hrm_human_resource_id(
                         label = T("Established by"),
                         comment = None,
                         widget = None,
                         readable = False,
                         writable = False,
                         ),
                     CommentsField(),
                     )

        # List fields
        list_fields = ["person_id",
                       "vulnerability_type_id",
                       "date",
                       "end_date",
                       ]

        # Table configuration
        self.configure(tablename,
                       list_fields = list_fields,
                       onvalidation = self.vulnerability_onvalidation,
                       )

        # CRUD strings
        crud_strings[tablename] = Storage(
            label_create = T("Add Vulnerability"),
            title_display = T("Vulnerability Details"),
            title_list = T("Vulnerabilities"),
            title_update = T("Edit Vulnerability"),
            label_list_button = T("List Vulnerabilities"),
            label_delete_button = T("Delete Vulnerability"),
            msg_record_created = T("Vulnerability added"),
            msg_record_modified = T("Vulnerability updated"),
            msg_record_deleted = T("Vulnerability deleted"),
            msg_list_empty = T("No Vulnerabilities currently registered"),
        )

        # Field template
        represent = dvr_VulnerabilityRepresent()
        vulnerability_id = FieldTemplate("vulnerability_id", "reference %s" % tablename,
                                         label = T("Vulnerability"),
                                         ondelete = "RESTRICT",
                                         represent = represent,
                                         requires = IS_EMPTY_OR(
                                                        IS_ONE_OF(db, "dvr_vulnerability.id",
                                                                  represent,
                                                                  sort=True,
                                                                  )),
                                         sortby = "date",
                                         )

        # ---------------------------------------------------------------------
        # Link vulnerability<=>case activity
        #
        tablename = "dvr_vulnerability_case_activity"
        define_table(tablename,
                     vulnerability_id(ondelete="CASCADE"),
                     self.dvr_case_activity_id(ondelete="CASCADE"),
                     )

        # ---------------------------------------------------------------------
        # Link vulnerability<=>response_action
        #
        tablename = "dvr_vulnerability_response_action"
        define_table(tablename,
                     vulnerability_id(ondelete="CASCADE"),
                     self.dvr_response_action_id(ondelete="CASCADE"),
                     )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        # return {}

    # -------------------------------------------------------------------------
    @staticmethod
    def vulnerability_onvalidation(form):
        """
            Vulnerability form validation
                - prevent duplicate vulnerability registration

            Args:
                form: the FORM
        """

        T = current.T

        record_id = get_form_record_id(form)
        if not record_id:
            return

        table = current.s3db.dvr_vulnerability

        # Look up form record data to validate
        fields = ("person_id", "vulnerability_type_id", "date", "end_date")
        form_data = get_form_record_data(form, table, fields)
        if not all(fn in form_data for fn in fields):
            return

        person_id = form_data["person_id"]
        type_id = form_data["vulnerability_type_id"]
        start = form_data["date"]
        end = form_data["end_date"]

        if person_id and type_id:
            # Check for duplicate
            query = (table.person_id == person_id) & \
                    (table.vulnerability_type_id == type_id)
            if start:
                query &= (table.end_date == None) | (table.end_date >= start)
            else:
                query &= (table.end_date == None)
            if end:
                query &= (table.date == None) | (table.date <= end)
            query &= (table.deleted == False)
            if record_id:
                query = (table.id != record_id) & query
            duplicate = current.db(query).select(table.id, limitby=(0, 1)).first()
            if duplicate:
                error = T("This vulnerability is already registered for this person")
                form.errors.vulnerability_type_id = error

# =============================================================================
class DVRServiceContactModel(DataModel):
    """ Model to track external service contacts of beneficiaries """

    names = ("dvr_service_contact",
             "dvr_service_contact_type",
             )

    def model(self):

        T = current.T

        db = current.db
        s3 = current.response.s3

        crud_strings = s3.crud_strings

        define_table = self.define_table
        configure = self.configure

        # ---------------------------------------------------------------------
        # Service Contact Types
        #
        tablename = "dvr_service_contact_type"
        define_table(tablename,
                     Field("name",
                           label = T("Name"),
                           requires = [IS_NOT_EMPTY(), IS_LENGTH(512, minsize=1)],
                           ),
                     CommentsField(),
                     )

        # Table configuration
        configure(tablename,
                  deduplicate = S3Duplicate(),
                  )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Service Contact Type"),
            title_display = T("Service Contact Type"),
            title_list = T("Service Contact Types"),
            title_update = T("Edit Service Contact Types"),
            label_list_button = T("List Service Contact Types"),
            label_delete_button = T("Delete Service Contact Type"),
            msg_record_created = T("Service Contact Type added"),
            msg_record_modified = T("Service Contact Type updated"),
            msg_record_deleted = T("Service Contact Type deleted"),
            msg_list_empty = T("No Service Contact Types currently defined"),
            )

        # Foreign Key Template
        represent = S3Represent(lookup=tablename, translate=True)
        type_id = FieldTemplate("type_id", "reference %s" % tablename,
                                label = T("Service Contact Type"),
                                ondelete = "RESTRICT",
                                represent = represent,
                                requires = IS_EMPTY_OR(
                                                IS_ONE_OF(db, "%s.id" % tablename,
                                                          represent,
                                                          )),
                                sortby = "name",
                                )

        # ---------------------------------------------------------------------
        # Service Contacts of Beneficiaries
        #
        AGENCY = T("Providing Agency")

        tablename = "dvr_service_contact"
        define_table(tablename,
                     # Beneficiary (component link):
                     self.pr_person_id(empty = False,
                                       ondelete = "CASCADE",
                                       ),
                     type_id(),
                     #self.dvr_need_id(),

                     self.org_organisation_id(label = AGENCY,
                                              ),
                     # Alternative free-text field:
                     Field("organisation",
                           label = AGENCY,
                           readable = False,
                           writable = False,
                           ),
                     Field("reference",
                           label = T("Ref.No."),
                           comment = DIV(_class = "tooltip",
                                         _title = "%s|%s" % (T("Ref.No."),
                                                             T("Customer number, file reference or other reference number"),
                                                             ),
                                         ),
                           ),
                     # Enable in template as needed:
                     Field("contact",
                           label = T("Contact Person"),
                           ),
                     Field("phone",
                           label = T("Phone"),
                           ),
                     Field("email",
                           label = T("Email"),
                           ),
                     CommentsField(),
                     )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Add Service Contact"),
            title_display = T("Service Contact Details"),
            title_list = T("Service Contacts"),
            title_update = T("Edit Service Contacts"),
            label_list_button = T("List Service Contacts"),
            label_delete_button = T("Delete Service Contact"),
            msg_record_created = T("Service Contact added"),
            msg_record_modified = T("Service Contact updated"),
            msg_record_deleted = T("Service Contact deleted"),
            msg_list_empty = T("No Service Contacts currently registered"),
            )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        # return {}

# =============================================================================
class DVRGrantModel(DataModel):
    """ Model for Beneficiary Grants """

    names = ("dvr_grant_type",
             "dvr_grant",
             "dvr_grant_history",
             )

    def model(self):

        T = current.T
        db = current.db
        s3 = current.response.s3

        crud_strings = s3.crud_strings

        amount_represent = lambda v, row=None: \
                           IS_FLOAT_AMOUNT.represent(v, precision=2, fixed=False)

        # ---------------------------------------------------------------------
        # Grant Type
        #
        aid_types = {"CASH": T("Cash"),
                     "SUPPLY": T("Supplies"),
                     "WORK": T("Work"),
                     "COUNSEL": T("Counsel"),
                     "SHELTER": T("Shelter"),
                     "OTHER": T("Other"),
                     }

        tablename = "dvr_grant_type"
        self.define_table(tablename,
                          Field("name", length=128, notnull=True, unique=True,
                                label = T("Title"),
                                requires = [IS_NOT_EMPTY(),
                                            IS_LENGTH(128, minsize=1),
                                            IS_NOT_ONE_OF(db, "%s.name" % tablename),
                                            ],
                                ),
                          CommentsField("description",
                                        label = T("Description"),
                                        ),
                          Field("granting_entity",
                                label = T("Granting Entity"),
                                ),
                          Field("aid_type",
                                label = T("Type of Aid"),
                                default = "CASH",
                                requires = IS_IN_SET(aid_types, zero=None),
                                represent = represent_option(aid_types),
                                ),
                          Field("um", length=64,
                                label = T("Unit of Measure"),
                                requires = IS_LENGTH(64, minsize=1),
                                represent = lambda v, row=None: v if v else "-"
                                ),
                          Field("relative", "boolean",
                                label = T("Relative Amount"),
                                default = True,
                                represent = BooleanRepresent(flag=True),
                                comment = T("Granted amounts are relative (e.g. percentage of costs)"),
                                ),
                          Field("total_beneficiaries", "integer",
                                label = T("Total Beneficiaries"),
                                default = 0,
                                represent = lambda v, row=None: v if v is not None else "-",
                                readable = False,
                                writable = False,
                                ),
                          Field("total_amount_granted", "double",
                                label = T("Total Amount Granted"),
                                default = 0.0,
                                represent = amount_represent,
                                readable = False,
                                writable = False,
                                ),
                          Field("total_amount_delivered", "double",
                                label = T("Total Amount Delivered"),
                                default = 0.0,
                                represent = amount_represent,
                                readable = False,
                                writable = False,
                                ),
                          Field("obsolete", "boolean",
                                label = T("Obsolete"),
                                default = False,
                                represent = BooleanRepresent(labels = False,
                                                             # Reverse icons semantics
                                                             icons = (BooleanRepresent.NEG,
                                                                      BooleanRepresent.POS,
                                                                      ),
                                                             flag = True,
                                                             ),
                                ),
                          CommentsField(),
                          )

        # Components
        self.add_components(tablename,
                            dvr_grant = "type_id",
                            )

        # CRUD strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Grant Type"),
            title_display = T("Grant Type Details"),
            title_list = T("Grant Types"),
            title_update = T("Edit Grant Type"),
            label_list_button = T("List Grant Types"),
            label_delete_button = T("Delete Grant Type"),
            msg_record_created = T("Grant Type added"),
            msg_record_modified = T("Grant Type updated"),
            msg_record_deleted = T("Grant Type deleted"),
            msg_list_empty = T("No Grant Types currently registered"),
            )

        # Foreign key template
        represent = S3Represent(lookup=tablename)
        grant_type_id = FieldTemplate("type_id", "reference %s" % tablename,
                                      label = T("Grant Type"),
                                      ondelete = "CASCADE",
                                      represent = represent,
                                      requires = IS_EMPTY_OR(
                                                    IS_ONE_OF(db, "%s.id" % tablename,
                                                              represent,
                                                              )),
                                      )

        # ---------------------------------------------------------------------
        # Grant
        # TODO expose in BETRA (tab or inline?)
        #
        grant_status = (("REQ", T("Requested")),
                        ("APR", T("Approved")),
                        ("RCV", T("Received")),
                        ("DCL", T("Declined")),
                        ("SSP", T("Suspended")),
                        ("RSC", T("Rescinded")),
                        )
        status_represent = S3PriorityRepresent(grant_status,
                                               {"REQ": "lightblue",
                                                "APR": "lightgreen",
                                                "RCV": "green",
                                                "DCL": "red",
                                                "SSP": "grey",
                                                "RSC": "black",
                                                }).represent
        tablename = "dvr_grant"
        self.define_table(tablename,
                          DateField(
                              label = T("Date"),
                              default="now",
                              empty = False,
                              ),
                          self.pr_person_id( # beneficiary
                              empty = False,
                              ondelete = "RESTRICT",
                              comment = None,
                              # TODO should not be updateable => prep
                              # writable = False,
                              ),
                          Field("refno", length=128,
                                label = T("Ref.No."),
                                requires = IS_EMPTY_OR([
                                                IS_LENGTH(128, minsize=1),
                                                IS_NOT_ONE_OF(db, "%s.refno" % tablename,
                                                              error_message = T("A grant with this reference number is already registered"),
                                                              ),
                                                ]),
                                represent = lambda v, row=None: v if v else "-",
                                ),
                          grant_type_id(
                              empty = False,
                              ondelete = "RESTRICT",
                              # TODO should not be updateable => prep
                              # writable = False,
                              ),
                          Field("amount_granted", "double",
                                label = T("Amount granted"),
                                default = 0.0,
                                requires = IS_FLOAT_AMOUNT(minimum=0.0),
                                represent = amount_represent,
                                ),
                          Field("amount_received", "double",
                                label = T("Amount received"),
                                default = 0.0,
                                requires = IS_FLOAT_AMOUNT(minimum=0.0),
                                represent = amount_represent,
                                ),
                          Field("status", length=16,
                                label = T("Status"),
                                default = "APPROVED",
                                requires = IS_IN_SET(grant_status,
                                                     sort = False,
                                                     zero = None,
                                                     ),
                                represent = status_represent,
                                ),
                          Field("vhash",
                                readable = False,
                                writable = False,
                                ),
                          CommentsField(),
                          )

        # Components
        self.add_components(tablename,
                            dvr_grant_history = {"name": "history",
                                                 "joinby": "grant_id",
                                                 },
                            )

        # Table configuration
        self.configure(tablename,
                       onvalidation = self.grant_onvalidation,
                       onaccept = self.grant_onaccept,
                       ondelete = self.grant_ondelete,
                       )

        # CRUD strings
        crud_strings[tablename] = Storage(
            label_create = T("Register Grant"),
            title_display = T("Grant Details"),
            title_list = T("Grants"),
            title_update = T("Edit Grant"),
            label_list_button = T("List Grants"),
            label_delete_button = T("Delete Grant"),
            msg_record_created = T("Grant registered"),
            msg_record_modified = T("Grant updated"),
            msg_record_deleted = T("Grant deleted"),
            msg_list_empty = T("No Grants currently registered"),
            )

        # ---------------------------------------------------------------------
        # History trail of a grant
        # - written automatically onaccept
        #
        tablename = "dvr_grant_history"
        self.define_table(tablename,
                          Field("grant_id", "reference dvr_grant",
                                ondelete = "CASCADE",
                                readable = False,
                                writable = False,
                                ),
                          DateTimeField(
                              label = T("Date"),
                              writable = False,
                              ),
                          self.pr_person_id( # beneficiary
                              empty = False,
                              ondelete = "CASCADE",
                              comment = None,
                              writable = False,
                              ),
                          grant_type_id(
                              empty = False,
                              ondelete = "RESTRICT",
                              writable = False,
                              ),
                          Field("refno",
                                label = T("Ref.No."),
                                writable = False,
                                ),
                          Field("amount_granted", "double",
                                label = T("Amount granted"),
                                represent = amount_represent,
                                writable = False,
                                ),
                          Field("amount_received", "double",
                                label = T("Amount received"),
                                represent = amount_represent,
                                writable = False,
                                ),
                          Field("status", length=16,
                                label = T("Status"),
                                represent = status_represent,
                                writable = False
                                ),
                          )

        # Table configuration
        self.configure(tablename,
                       insertable = False,
                       editable = False,
                       deletable = False,
                       )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        # return {}

    # -------------------------------------------------------------------------
    @staticmethod
    def update_grant_type_totals(grant_type_id):
        """
            Updates the totals of a grant type

            Args:
                grant_type_id: the grant type record ID
        """

        db = current.db
        s3db = current.s3db

        table = s3db.dvr_grant_type
        query = (table.id == grant_type_id) & (table.deleted == False)
        grant_type = db(query).select(table.id,
                                      table.relative,
                                      limitby=(0, 1),
                                      ).first()

        if not grant_type:
            return
        absolute = not grant_type.relative

        gtable = s3db.dvr_grant
        query = (gtable.type_id == grant_type.id) & \
                (gtable.status.belongs({"APR", "RCV", "SSP"})) & \
                (gtable.deleted == False)
        total_beneficiaries = gtable.person_id.count(distinct=True)
        totals = [total_beneficiaries]

        if absolute:
            total_amount_granted = gtable.amount_granted.sum()
            total_amount_received = gtable.amount_received.sum()
            totals.extend([total_amount_granted, total_amount_received])

        row = db(query).select(*totals).first()
        update = {"total_beneficiaries": row[total_beneficiaries],
                  "total_amount_granted": None,
                  "total_amount_delivered": None,
                  }
        if absolute:
            update["total_amount_granted"] = row[total_amount_granted]
            update["total_amount_delivered"] = row[total_amount_received]

        grant_type.update_record(**update)

    # -------------------------------------------------------------------------
    @staticmethod
    def grant_onvalidation(form):
        """
            Form validation of grants
            - amount_received must be less or equal amount_granted
            - any other status than requested|declined requires a ref.no
        """

        table = current.s3db.dvr_grant
        data = get_form_record_data(form, table, ["amount_granted",
                                                  "amount_received",
                                                  "refno",
                                                  "status",
                                                  ])
        granted = data.get("amount_granted")
        received = data.get("amount_received")
        if granted is not None and received is not None and granted < received:
            form.errors.amount_received = current.T("Amount received must not exceed the amount granted")

        refno = data.get("refno")
        status = data.get("status")
        if status not in ("REQ", "DCL") and not refno:
            form.errors.refno = current.T("Ref.no. required for status")

    # -------------------------------------------------------------------------
    @classmethod
    def grant_onaccept(cls, form):
        """
            Onaccept-routine for grants:
            - check if record has changed => write history entry, if so
            - update grant type totals as necessary

            Args:
                form: the FORM
        """

        db = current.db
        s3db = current.s3db
        auth = current.auth

        record_id = get_form_record_id(form)
        if not record_id:
            return

        table = s3db.dvr_grant
        query = (table.id == record_id) & (table.deleted == False)
        record = db(query).select(table.id,
                                  table.type_id,
                                  table.person_id,
                                  table.refno,
                                  table.amount_granted,
                                  table.amount_received,
                                  table.status,
                                  table.vhash,
                                  limitby = (0, 1),
                                  ).first()
        if not record:
            return

        # Compute vhash
        values = [record.type_id,
                  record.person_id,
                  record.refno,
                  "%0.2f" % record.amount_granted,
                  "%0.2f" % record.amount_received,
                  record.status,
                  ]
        vhash = datahash(values)
        if vhash != record.vhash:
            htable = s3db.dvr_grant_history

            # Get last history entry
            query = (htable.grant_id == record.id) & \
                    (htable.deleted == False)
            last_entry = db(query).select(htable.id,
                                          htable.type_id,
                                          limitby = (0, 1),
                                          orderby = ~htable.id,
                                          ).first()
            if last_entry and last_entry.type_id != record.type_id:
                # Update totals for the original type, too
                cls.update_grant_type_totals(last_entry.type_id)

            # Write new history entry
            entry = {"grant_id": record.id,
                     "date": current.request.utcnow,
                     "type_id": record.type_id,
                     "person_id": record.person_id,
                     "refno": record.refno,
                     "amount_granted": record.amount_granted,
                     "amount_received": record.amount_received,
                     "status": record.status,
                     }
            entry["id"] = entry_id = htable.insert(**entry)
            if entry_id:
                s3db.update_super(htable, entry)
                auth.s3_set_record_owner(htable, entry_id)
                auth.s3_make_session_owner(htable, entry_id)
                s3db.onaccept(htable, entry, method="create")

            # Update vhash
            record.update_record(vhash=vhash)

        # Update grant type totals
        cls.update_grant_type_totals(record.type_id)

    # -------------------------------------------------------------------------
    @classmethod
    def grant_ondelete(cls, row):
        """
            Ondelete-routine for grants:
            - update grant type totals
        """

        cls.update_grant_type_totals(row.type_id)

# =============================================================================
def dvr_get_case(person_id, archived=None):
    """
        Looks up the latest (open) case for a person

        Args:
            person_id: the person ID
            archived: True|False to exclude valid|invalid cases

        Returns:
            the case (dvr_case Row)
    """

    db = current.db
    s3db = current.s3db

    # Lookup the latest open case
    ctable = s3db.dvr_case
    stable = s3db.dvr_case_status

    left = stable.on(stable.id == ctable.status_id)
    query = (ctable.person_id == person_id) & \
            (ctable.deleted == False)
    if archived is not None:
        query &= (ctable.archived == archived)
    rows = db(query).select(ctable.id,
                            ctable.organisation_id,
                            ctable.reference,
                            stable.is_closed,
                            left = left,
                            orderby = ~ctable.date,
                            )
    case = None
    if rows:
        for row in rows:
            if not row.dvr_case_status.is_closed:
                case = row.dvr_case
                break
        if not case:
            case = rows.first().dvr_case

    return case

# -----------------------------------------------------------------------------
def dvr_case_organisation(person_id):
    """
        Looks up the case organisation for a person

        Args:
            person_id: the person ID

        Returns:
            the organisation ID
    """

    case = dvr_get_case(person_id)

    return case.organisation_id if case else None

# -----------------------------------------------------------------------------
def dvr_case_default_status():
    """
        Helper to get/set the default status for case records

        Returns:
            the default status_id
    """

    s3db = current.s3db

    ctable = s3db.dvr_case
    field = ctable.status_id

    default = field.default
    if default:
        # Already set
        return default

    # Look up the default status
    stable = s3db.dvr_case_status
    query = (stable.is_default == True) & \
            (stable.deleted != True)
    row = current.db(query).select(stable.id, limitby=(0, 1)).first()

    if row:
        # Set as field default in case table
        ctable = s3db.dvr_case
        default = field.default = row.id

    return default

# -----------------------------------------------------------------------------
def dvr_case_status_filter_opts(closed=None):
    """
        Get filter options for case status, ordered by workflow position

        Returns:
            OrderedDict of options

        Note:
            set sort=False for filter widget to retain this order
    """

    table = current.s3db.dvr_case_status
    query = (table.deleted != True)
    if closed is not None:
        if closed:
            query &= (table.is_closed == True)
        else:
            query &= ((table.is_closed == False) | (table.is_closed == None))
    rows = current.db(query).select(table.id,
                                    table.name,
                                    orderby = "workflow_position",
                                    )

    if not rows:
        return {}

    T = current.T
    t_ = lambda v: T(v) if isinstance(v, str) else "-"

    return OrderedDict((row.id, t_(row.name)) for row in rows)

# =============================================================================
def dvr_configure_vulnerability_types(organisation_id, vulnerability_id=None):
    # TODO docstring

    if not current.deployment_settings.get_org_sector():
        # Organisations not using sectors
        return

    db = current.db
    s3db = current.s3db

    vtable = s3db.dvr_vulnerability
    ttable = s3db.dvr_vulnerability_type
    ltable = s3db.dvr_vulnerability_type_sector

    stable = s3db.org_sector_organisation

    if organisation_id:

        # Sectors of this organisation
        subquery = (stable.organisation_id == organisation_id)
        sectors = db(subquery)._select(stable.sector_id)

        # Vulnerability types linked to these sectors
        subquery = (ltable.sector_id.belongs(sectors))
        types = db(subquery)._select(ltable.vulnerability_type_id)

        if vulnerability_id:
            # Look up current value
            query = (vtable.id == vulnerability_id)
            row = db(query).select(vtable.vulnerability_type_id,
                                   limitby = (0, 1),
                                   ).first()
            current_value = row.vulnerability_type_id if row else None
        else:
            current_value = None

        query = (ttable.id.belongs(types))
        if current_value:
            query = (ttable.id == current_value) | query
        dbset = db(query)

        field = vtable.vulnerability_type_id
        field.requires = IS_ONE_OF(dbset, "dvr_vulnerability_type.id",
                                   field.represent,
                                   )

# -------------------------------------------------------------------------
def dvr_configure_case_vulnerabilities(person_id):
    # TODO docstring

    s3db = current.s3db

    vtable = s3db.dvr_vulnerability
    dbset = current.db(vtable.person_id == person_id)

    for tn in ("dvr_vulnerability_case_activity",
               "dvr_vulnerability_response_action",
               ):
        table = s3db[tn]
        field = table.vulnerability_id
        field.requires = IS_ONE_OF(dbset, "dvr_vulnerability.id",
                                   field.represent,
                                   )

# -----------------------------------------------------------------------------
def dvr_configure_case_tasks(r, categories=False, default_category=None):
    """
        Configures case tasks; to be called from prep()

        Args:
            r: the CRUDRequest
            categories: list|set|tuple of categories to use,
                        True to use all categories, False to use none
            default_category: the default task category when using multiple

        Note:
            When using multiple task categories, the field will be exposed
            in the form and list, and a category filter will be added. When
            not using categories, all tasks will fall into the default
            category (see DVRTaskModel).
    """

    T = current.T

    db = current.db
    s3db = current.s3db

    record = r.record
    organisation_id = None

    if r.tablename == "dvr_task":
        on_tab = False
        resource = r.resource
        if record:
            # Use the task organisation
            organisation_id = record.organisation_id
    elif r.component_name == "case_task":
        on_tab = True
        resource = r.component
        if r.component_id:
            # Look up the task organisation
            ttable = s3db.dvr_task
            query = (ttable.id == r.component_id)
            row = db(query).select(ttable.organisation_id, limitby=(0, 1)).first()
            organisation_id = row.organisation_id if row else None
        elif record:
            # Look up the case organisation
            organisation_id = s3db.dvr_case_organisation(record.id)
    else:
        return

    table = resource.table

    if organisation_id:
        field = table.human_resource_id

        # Limit contact person selection to case organisation
        htable = s3db.hrm_human_resource
        dbset = db((htable.organisation_id==organisation_id) & \
                   (htable.status == 1))
        field.requires = IS_EMPTY_OR(IS_ONE_OF(dbset,
                                               "hrm_human_resource.id",
                                               field.represent,
                                               ))

        # Default contact person to current user, if they are
        # staff member of the case organisation
        query = (htable.person_id == current.auth.s3_logged_in_person()) & \
                (htable.organisation_id == organisation_id) & \
                (htable.status == 1) & \
                (htable.deleted == False)
        row = db(query).select(htable.id, limitby=(0, 1)).first()
        if row:
            field.default = row.id

    # Hide person_id from form (shown in rheader instead), show as link to ToDo-tab
    field = table.person_id
    field.readable = field.writable = False
    field.represent = s3db.pr_PersonRepresent(linkto = URL(c = r.controller,
                                                           f = "person",
                                                           args = ["[id]", "case_task"],
                                                           extension = "",
                                                           ),
                                               show_link = True,
                                               )

    if on_tab:
        text_search_fields = ["name",
                              "description",
                              "comments",
                              ]
        list_fields = ["due_date",
                       "name",
                       "description",
                       "human_resource_id",
                       "status",
                       "comments",
                       ]

    else:
        text_search_fields = ["person_id$pe_label",
                              "person_id$first_name",
                              "person_id$middle_name",
                              "person_id$last_name",
                              "name",
                              "description",
                              "comments"
                              ]
        list_fields = ["due_date",
                       (T("ID"), "person_id$pe_label"),
                       (T("Name"), "person_id"),
                       "name",
                       "human_resource_id",
                       "status",
                       "comments",
                       ]

    # Filter widgets
    task_status = s3db.dvr_task_status
    filter_widgets = [TextFilter(text_search_fields,
                                 label = T("Search"),
                                 ),
                      OptionsFilter("status",
                                    options = OrderedDict(task_status),
                                    default = ["NEW", "PROC", "NA"],
                                    cols = 3,
                                    orientation = "rows",
                                    sort = False,
                                    ),
                      ]

    # Expose category?
    if categories:
        hide_category = False

        if categories is True:
            task_category = s3db.dvr_task_category
        else:
            task_category = {k: v for k, v in s3db.dvr_task_category.items() if k in categories}
            categories = list(task_category.keys())
            if len(categories) == 1:
                default_category = categories[0]
                hide_category = True
                resource.add_filter(FS("category") == default_category)
            else:
                resource.add_filter(FS("category").belongs(categories))

        field = table.category
        field.requires = IS_IN_SET(task_category, zero=None)

        if default_category and default_category in task_category:
            field.default = default_category

        if not hide_category:
            field.readable = field.writable = True
            filter_widgets.append(OptionsFilter("category",
                                                label = T("Category"),
                                                options = task_category,
                                                ))
            list_fields.insert(1, "category")

    resource.configure(filter_widgets = filter_widgets,
                       list_fields = list_fields,
                       )

# =============================================================================
def dvr_case_activity_default_status():
    """
        Helper to get/set the default status for case activities

        Returns:
            the default status_id
    """

    s3db = current.s3db

    rtable = s3db.dvr_case_activity
    field = rtable.status_id

    default = field.default
    if not default:

        # Look up the default status
        stable = s3db.dvr_case_activity_status
        query = (stable.is_default == True) & \
                (stable.deleted != True)
        row = current.db(query).select(stable.id, limitby=(0, 1)).first()

        if row:
            # Set as field default in case activity table
            default = field.default = row.id

    return default

# -------------------------------------------------------------------------
def dvr_case_activity_form(r):
    """
        Configure the case activity form, applying all settings

        Args:
            r: the CRUDRequest

        Returns:
            CustomForm
    """

    T = current.T
    s3db = current.s3db

    settings = current.deployment_settings

    #configure person_id depending on perspective:
    #- readonly on update with label+name in standalone perspective
    #- selector of persons with active cases on create in standalone perspective
    #- hidden on component tab of person

    crud_fields = ["person_id"]

    # Need details
    need = ["need_id",
            "subject",
            "emergency",
            "need_details",
            ]
    if settings.get_dvr_case_activity_vulnerabilities():
        need.append(InlineLink("vulnerability",
                               field = "vulnerability_id",
                               header = False,
                               label = T("Vulnerabilities"),
                               comment = T("Vulnerabilities relevant for this need"),
                               ))
    need.append("start_date")

    # Action details
    actions = ["human_resource_id"]
    if settings.get_dvr_manage_response_actions():
        actions.append(s3db.dvr_configure_inline_responses(r))
    actions.append("activity_details")

    # Inline Updates
    if settings.get_dvr_case_activity_updates():
        # When using updates, need details describe initial situation
        table = s3db.dvr_case_activity
        field = table.need_details
        field.label = T("Initial Situation Details")

        # Set default for human_resource_id
        utable = s3db.dvr_case_activity_update
        field = utable.human_resource_id
        field.default = current.auth.s3_logged_in_human_resource()

        # Configure inline sub-form
        actions.append(InlineComponent("case_activity_update",
                                       label = T("Progress"),
                                       fields = ["date",
                                                 (T("Occasion"), "update_type_id"),
                                                 "human_resource_id",
                                                 "comments",
                                                 ],
                                       layout = SubFormLayoutVertical,
                                       explicit_add = T("Add Entry"),
                                       ))

    # Follow-up
    followup = ["followup", "followup_date"]

    # Categories
    # TODO investigate if anything uses this, make custom-only otherwise
    categories = ["sector_id",
                  "service_id",
                  ]

    status = ["status_id",
              "end_date",
              "outcome",
              "achievement",
              ]

    # Inline documents
    if settings.get_dvr_case_activity_documents():
        documents = [InlineComponent("document",
                                     name = "file",
                                     label = T("Attachments"),
                                     fields = ["file", "comments"],
                                     filterby = {"field": "file",
                                                 "options": "",
                                                 "invert": True,
                                                 },
                                     ),
                      ]
    else:
        documents = []

    crud_fields += need  + actions + followup + categories+ status + documents

    if settings.get_dvr_case_activity_comments():
        crud_fields.append("comments")

    return CustomForm(*crud_fields)

# =============================================================================
def dvr_response_status_colors(resource, selector):
    """
        Get colors for response statuses

        Args:
            resource: the CRUDResource the caller is looking at
            selector: the Field selector (usually "status_id")

        Returns:
            a dict with colors {field_value: "#RRGGBB", ...}
    """

    table = current.s3db.dvr_response_status
    query = (table.color != None)

    rows = current.db(query).select(table.id,
                                    table.color,
                                    )
    return {row.id: ("#%s" % row.color) for row in rows if row.color}

# =============================================================================
def dvr_response_default_type():
    """
        Helper to get/set the default type for response records

        Returns:
            the default response_type_id
    """

    s3db = current.s3db

    rtable = s3db.dvr_response_action
    field = rtable.response_type_id

    default = field.default
    if not default:

        # Look up the default status
        ttable = s3db.dvr_response_type
        query = (ttable.is_default == True) & \
                (ttable.deleted != True)
        row = current.db(query).select(ttable.id,
                                       cache = s3db.cache,
                                       limitby = (0, 1),
                                       ).first()

        if row:
            # Set as field default in responses table
            default = field.default = row.id

    return default

# -----------------------------------------------------------------------------
def dvr_response_default_status():
    """
        Helper to get/set the default status for response records

        Returns:
            the default status_id
    """

    s3db = current.s3db

    rtable = s3db.dvr_response_action
    field = rtable.status_id

    default = field.default
    if not default:

        stable = s3db.dvr_response_status

        if current.deployment_settings.get_dvr_response_planning():
            # Actions are planned ahead, so initial status by default
            query = (stable.is_default == True)
        else:
            # Actions are documented in hindsight, so closed by default
            query = (stable.is_default_closure == True)

        # Look up the default status
        query = query & (stable.deleted != True)
        row = current.db(query).select(stable.id,
                                       cache = s3db.cache,
                                       limitby = (0, 1),
                                       ).first()

        if row:
            # Set as field default in responses table
            default = field.default = row.id

    return default

# -----------------------------------------------------------------------------
def dvr_set_response_action_defaults():
    """
        DRY Helper to set defaults for response actions
    """

    if current.deployment_settings.get_dvr_response_types():
        dvr_response_default_type()

    dvr_response_default_status()

    # HR in charge defaults to current user
    table = current.s3db.dvr_response_action
    field = table.human_resource_id
    field.default = current.auth.s3_logged_in_human_resource()

# -----------------------------------------------------------------------------
def dvr_configure_case_responses(organisation_id):
    # TODO docstring

    db = current.db
    s3db = current.s3db

    settings = current.deployment_settings

    ttable = s3db.dvr_response_theme
    atable = s3db.dvr_response_action
    ltable = s3db.dvr_response_action_theme

    field = atable.case_activity_id
    if not settings.get_dvr_response_themes_details() or \
       not settings.get_dvr_response_activity_autolink():
        field.readable = field.writable = True

    theme_id = ltable.theme_id
    theme_ids = atable.response_theme_ids

    dbset = db # default
    if organisation_id:
        if settings.get_dvr_response_themes_org_specific():
            # Filter selectable themes by case organisation
            dbset = db(ttable.organisation_id == organisation_id)

        elif settings.get_org_sector() and \
             settings.get_dvr_response_themes_sectors():
            # Filter selectable themes by case org sectors
            stable = s3db.org_sector_organisation
            sectors = db(stable.organisation_id == organisation_id)._select(stable.sector_id)
            dbset = db(ttable.sector_id.belongs(sectors))

    if dbset is not None:
        theme_id.requires = IS_ONE_OF(dbset, "dvr_response_theme.id",
                                      theme_id.represent,
                                      not_filterby = "obsolete",
                                      not_filter_opts = (True,),
                                      )

        theme_ids.requires = IS_EMPTY_OR(
                                IS_ONE_OF(dbset, "dvr_response_theme.id",
                                          theme_ids.represent,
                                          multiple = True,
                                          not_filterby = "obsolete",
                                          not_filter_opts = (True,),
                                          ))

# -----------------------------------------------------------------------------
def dvr_configure_inline_responses(r):
    """
        Configure sub-form for inline response actions (in case activity)

        Args:
            r: the CRUDRequest
        Returns:
            InlineComponent
    """

    T = current.T
    db = current.db
    s3db = current.s3db
    settings = current.deployment_settings

    rtable = s3db.dvr_response_action

    resource = r.resource
    record = r.record

    # Get person_id
    person_id = None
    if record:
        if resource.tablename == "pr_person":
            person_id = record.id
        elif "person_id" in record:
            person_id = record.person_id
    else:
        person_id = None
    if not person_id:
        # Cannot embed responses without a person_id
        return None

    use_theme = settings.get_dvr_response_themes()
    if use_theme and settings.get_dvr_response_themes_details():
        # Filter action_id in inline response_themes to same beneficiary
        ltable = s3db.dvr_response_action_theme
        field = ltable.action_id
        dbset = db(rtable.person_id == person_id) if person_id else db
        field.requires = IS_EMPTY_OR(IS_ONE_OF(dbset, "dvr_response_action.id",
                                               field.represent,
                                               orderby = ~rtable.start_date,
                                               sort = False,
                                               ))

        # Expose response_action_theme inline
        inline_responses = InlineComponent(
                                "response_action_theme",
                                fields = ["action_id",
                                          "theme_id",
                                          "comments",
                                          ],
                                label = T("Counseling"),
                                orderby = "action_id",
                                readonly = settings.get_dvr_response_themes_efforts(),
                                )
    else:
        # Set the person_id for inline responses (does not not happen
        # automatically since using case_activity_id as component key)
        if person_id:
            field = rtable.person_id
            field.default = person_id

        # Expose response_action inline
        response_theme_ids = "response_theme_ids" if use_theme else None
        response_action_fields = ["start_date",
                                  response_theme_ids,
                                  "comments",
                                  "human_resource_id",
                                  "status_id",
                                  "hours",
                                  ]
        if settings.get_dvr_response_due_date():
            response_action_fields.insert(-2, "date_due")
        if settings.get_dvr_response_types():
            response_action_fields.insert(1, "response_type_id")

        inline_responses = InlineComponent(
                                "response_action",
                                fields = response_action_fields,
                                label = T("Actions"),
                                layout = SubFormLayoutVertical,
                                explicit_add = T("Add Action"),
                                )
    return inline_responses

# =============================================================================
def dvr_case_household_size(group_id):
    """
        Update the household_size for all cases in the given case group,
        taking into account that the same person could belong to multiple
        case groups. To be called onaccept of pr_group_membership if automatic
        household size is enabled

        Args:
            group_id: the group_id of the case group (group_type == 7)
    """

    db = current.db
    s3db = current.s3db
    ptable = s3db.pr_person
    gtable = s3db.pr_group
    mtable = s3db.pr_group_membership

    # Get all persons related to this group_id, make sure this is a case group
    join = [mtable.on((mtable.group_id == gtable.id) &
                      (mtable.deleted != True)),
            ptable.on(ptable.id == mtable.person_id)
            ]
    query = (gtable.id == group_id) & \
            (gtable.group_type == 7) & \
            (gtable.deleted != True)
    rows = db(query).select(ptable.id, join=join)
    person_ids = {row.id for row in rows}

    if person_ids:
        # Get case group members for each of these person_ids
        ctable = s3db.dvr_case
        rtable = ctable.with_alias("member_cases")
        otable = mtable.with_alias("case_members")
        join = ctable.on(ctable.person_id == mtable.person_id)
        left = [otable.on((otable.group_id == mtable.group_id) &
                          (otable.deleted != True)),
                rtable.on(rtable.person_id == otable.person_id),
                ]
        query = (mtable.person_id.belongs(person_ids)) & \
                (mtable.deleted != True) & \
                (rtable.id != None)
        rows = db(query).select(ctable.id,
                                otable.person_id,
                                join = join,
                                left = left,
                                )

        # Count heads
        CASE = str(ctable.id)
        MEMBER = str(otable.person_id)
        groups = {}
        for row in rows:
            member_id = row[MEMBER]
            case_id = row[CASE]
            if case_id not in groups:
                groups[case_id] = {member_id}
            else:
                groups[case_id].add(member_id)

        # Update the related cases
        for case_id, members in groups.items():
            number_of_members = len(members)
            db(ctable.id == case_id).update(household_size = number_of_members)

# -----------------------------------------------------------------------------
def dvr_get_household_size(person_id, dob=False, formatted=True):
    """
        Helper function to calculate the household size
        (counting only members with active cases)

        Args:
            person_id: the person record ID
            dob: the date of birth of that person (if known)
            formatted: return household size info as string

        Returns:
            household size info as string if formatted=True,
            otherwise tuple (number_of_adults, number_of_children)
    """

    db = current.db

    s3db = current.s3db
    ptable = s3db.pr_person
    gtable = s3db.pr_group
    mtable = s3db.pr_group_membership
    ctable = s3db.dvr_case
    stable = s3db.dvr_case_status

    from dateutil.relativedelta import relativedelta
    now = current.request.utcnow.date()

    # Default result
    adults, children, children_u1 = 1, 0, 0

    # Count the person in question
    if dob is False:
        query = (ptable.id == person_id)
        row = db(query).select(ptable.date_of_birth,
                               limitby = (0, 1),
                               ).first()
        if row:
            dob = row.date_of_birth
    if dob:
        age = relativedelta(now, dob).years
        if age < 18:
            adults, children = 0, 1
            if age < 1:
                children_u1 = 1

    # Household members which have already been counted
    members = {person_id}
    counted = members.add

    # Get all case groups this person belongs to
    query = ((mtable.person_id == person_id) & \
            (mtable.deleted != True) & \
            (gtable.id == mtable.group_id) & \
            (gtable.group_type == 7))
    rows = db(query).select(gtable.id)
    group_ids = set(row.id for row in rows)

    if group_ids:
        join = [ptable.on(ptable.id == mtable.person_id),
                ctable.on((ctable.person_id == ptable.id) & \
                          (ctable.archived != True) & \
                          (ctable.deleted != True)),
                ]
        left = [stable.on(stable.id == ctable.status_id),
                ]
        query = (mtable.group_id.belongs(group_ids)) & \
                (mtable.deleted != True) & \
                (stable.is_closed != True)
        rows = db(query).select(ptable.id,
                                ptable.date_of_birth,
                                join = join,
                                left = left,
                                )

        for row in rows:
            person, dob = row.id, row.date_of_birth
            if person not in members:
                age = relativedelta(now, dob).years if dob else None
                if age is not None and age < 18:
                    children += 1
                    if age < 1:
                        children_u1 += 1
                else:
                    adults += 1
                counted(person)

    if not formatted:
        return adults, children, children_u1

    T = current.T
    template = "%(number)s %(label)s"
    details = []
    if adults:
        label = T("Adults") if adults != 1 else T("Adult")
        details.append(template % {"number": adults,
                                   "label": label,
                                   })
    if children:
        label = T("Children") if children != 1 else T("Child")
        details.append(template % {"number": children,
                                   "label": label,
                                   })
    details = ", ".join(details)

    if children_u1:
        if children_u1 == 1:
            label = T("Child under 1 year")
        else:
            label = T("Children under 1 year")
        details = "%s (%s)" % (details,
                               template % {"number": children_u1,
                                           "label": label,
                                           },
                               )

    return details

# =============================================================================
def dvr_group_membership_onaccept(record, group, group_id, person_id):
    """
        Onaccept of a case group
            - update household size
            - add case records for new group members

        Args:
            record: the pr_group_membership record
            group: the pr_group Row (including id and group_type)
            group_id: the pr_group record ID (if the group was deleted)
            person_id: the person ID (if the group membership was deleted)
    """

    db = current.db
    s3db = current.s3db

    table = s3db.pr_group_membership
    ctable = s3db.dvr_case
    gtable = s3db.pr_group

    settings = current.deployment_settings
    response = current.response
    s3 = response.s3

    if s3.purge_case_groups:
        return

    # Get the group
    if group.id is None and group_id:
        query = (gtable.id == group_id) & (gtable.deleted == False)
        group = db(query).select(gtable.id,
                                 gtable.group_type,
                                 limitby = (0, 1),
                                 ).first()
    if not group or group.group_type != 7:
        return

    # Case groups should only have one group head
    if not record.deleted and record.group_head:
        query = (table.group_id == group_id) & \
                (table.id != record.id) & \
                (table.group_head == True)
        db(query).update(group_head=False)

    update_household_size = settings.get_dvr_household_size() == "auto"
    recount = dvr_case_household_size

    if update_household_size and record.deleted and person_id:
        # Update the household size for removed group member
        query = (table.person_id == person_id) & \
                (table.group_id != group_id) & \
                (table.deleted != True) & \
                (gtable.id == table.group_id) & \
                (gtable.group_type == 7)
        row = db(query).select(table.group_id, limitby=(0, 1)).first()
        if row:
            # Person still belongs to other case groups, count properly:
            recount(row.group_id)
        else:
            # No further case groups, so household size is 1
            cquery = (ctable.person_id == person_id)
            db(cquery).update(household_size = 1)

    if not s3.bulk:
        # Get number of (remaining) members in this group
        query = (table.group_id == group_id) & \
                (table.deleted != True)
        rows = db(query).select(table.id, limitby=(0, 2))

        if len(rows) < 2: # Single member

            # Update the household size for remaining member
            # (they could still belong to other case groups)
            if update_household_size:
                recount(group_id)
                update_household_size = False

            # Remove the case group
            s3.purge_case_groups = True
            resource = s3db.resource("pr_group", id=group_id)
            resource.delete()
            s3.purge_case_groups = False

        elif not record.deleted:
            # Either added or updated a group member
            # ...make sure there is a case record for them

            query = (ctable.person_id == person_id) & \
                    (ctable.deleted != True)
            row = db(query).select(ctable.id, limitby=(0, 1)).first()
            if not row:
                # Customise case resource
                r = CRUDRequest("dvr", "case", current.request)
                r.customise_resource("dvr_case")

                # Get the default case status from database
                s3db.dvr_case_default_status()

                # Create a case
                cresource = s3db.resource("dvr_case")
                try:
                    # Using resource.insert for proper authorization
                    # and post-processing (=audit, ownership, realm,
                    # onaccept)
                    cresource.insert(person_id=person_id)
                except S3PermissionError:
                    # Unlikely (but possible) that this situation
                    # is deliberate => issue a warning
                    response.warning = current.T("No permission to create a case record for new group member")

    # Update the household size for current group members
    if update_household_size:
        recount(group_id)

# =============================================================================
def dvr_due_followups(human_resource_id=None):
    """
        Number of activities due for follow-up

        Args:
            human_resource_id: count only activities assigned to this HR
    """

    # Generate a request for case activities and customise it
    r = CRUDRequest("dvr", "case_activity",
                    args = ["count_due_followups"],
                    get_vars = {},
                    )
    r.customise_resource()
    resource = r.resource

    # Filter for due follow-ups
    query = (FS("followup") == True) & \
            (FS("followup_date") <= datetime.datetime.utcnow().date()) & \
            (FS("status_id$is_closed") == False) & \
            (FS("person_id$dvr_case.archived") == False)

    if human_resource_id:
        query &= (FS("human_resource_id") == human_resource_id)

    resource.add_filter(query)

    return resource.count()

# =============================================================================
class dvr_ResponseActionRepresent(S3Represent):
    """ Representation of response actions """

    def __init__(self, show_hr=True, show_link=True):
        """
            Args:
                show_hr: include the staff member name
        """

        super().__init__(lookup = "dvr_response_action",
                         show_link = show_link,
                         )

        self.show_hr = show_hr

    # -------------------------------------------------------------------------
    def lookup_rows(self, key, values, fields=None):
        """
            Custom rows lookup

            Args:
                key: the key Field
                values: the values
                fields: list of fields to look up (unused)
        """

        show_hr = self.show_hr

        count = len(values)
        if count == 1:
            query = (key == values[0])
        else:
            query = key.belongs(values)

        table = self.table

        fields = [table.id, table.start_date, table.person_id]
        if show_hr:
            fields.append(table.human_resource_id)

        rows = current.db(query).select(limitby=(0, count), *fields)
        self.queries += 1

        # Bulk-represent human_resource_ids
        if show_hr:
            hr_ids = [row.human_resource_id for row in rows]
            table.human_resource_id.represent.bulk(hr_ids)

        return rows

    # -------------------------------------------------------------------------
    def represent_row(self, row):
        """
            Represent a row

            Args:
                row: the Row
        """

        table = self.table
        date = table.start_date.represent(row.start_date)

        if self.show_hr:
            hr = table.human_resource_id.represent(row.human_resource_id,
                                                   show_link = False,
                                                   )
            reprstr = "[%s] %s" % (date, hr)
        else:
            reprstr = date

        return reprstr

    # -------------------------------------------------------------------------
    def link(self, k, v, row=None):
        """
            Represent a (key, value) as hypertext link

            Args:
                k: the key (dvr_case_activity.id)
                v: the representation of the key
                row: the row with this key
        """

        try:
            person_id = row.person_id
        except AttributeError:
            return v

        url = URL(c = "dvr",
                  f = "person",
                  args = [person_id, "response_action", k],
                  extension = "",
                  )

        return A(v, _href = url)

# =============================================================================
class dvr_ResponseActionThemeRepresent(S3Represent):
    """ Representation of response action theme links """

    def __init__(self, paragraph=False, details=False):
        """
            Args:
                paragraph: render as HTML paragraph
                details: include details in paragraph
        """

        super().__init__(lookup="dvr_response_action_theme")

        self.paragraph = paragraph
        self.details = details

    # -------------------------------------------------------------------------
    def lookup_rows(self, key, values, fields=None):
        """
            Custom rows lookup

            Args:
                key: the key Field
                values: the values
                fields: list of fields to look up (unused)
        """

        count = len(values)
        if count == 1:
            query = (key == values[0])
        else:
            query = key.belongs(values)

        table = self.table

        fields = [table.id, table.action_id, table.theme_id]
        if self.details:
            fields.append(table.comments)

        rows = current.db(query).select(limitby=(0, count), *fields)
        self.queries += 1

        # Bulk-represent themes
        theme_ids = [row.theme_id for row in rows]
        table.theme_id.represent.bulk(theme_ids)

        return rows

    # -------------------------------------------------------------------------
    def represent_row(self, row):
        """
            Represent a row

            Args:
                row: the Row
        """

        table = self.table

        theme = table.theme_id.represent(row.theme_id)

        if self.paragraph:
            # CSS class to allow styling
            css = "dvr-response-action-theme"
            if self.details:
                comments = table.comments.represent(row.comments)
                reprstr = DIV(H6(theme), comments, _class=css)
            else:
                reprstr = P(theme, _class=css)
        else:
            reprstr = theme

        return reprstr

    # -------------------------------------------------------------------------
    def render_list(self, value, labels, show_link=True):
        """
            Render list-type representations from bulk()-results.

            Args:
                value: the list
                labels: the labels as returned from bulk()
                show_link: render references as links, should
                           be the same as used with bulk()
        """

        if self.paragraph:
            reprstr = TAG[""]([labels[v] if v in labels else self.default
                               for v in value
                               ])
        else:
            reprstr = super().render_list(value, labels, show_link=show_link)
        return reprstr

# =============================================================================
class dvr_ResponseThemeRepresent(S3Represent):
    """ Representation of response themes """

    def __init__(self, multiple=False, translate=True, show_need=False):

        super().__init__(lookup = "dvr_response_theme",
                         multiple = multiple,
                         translate = translate,
                         )
        self.show_need = show_need

    # -------------------------------------------------------------------------
    def lookup_rows(self, key, values, fields=None):
        """
            Custom rows lookup

            Args:
                key: the key Field
                values: the values
                fields: unused (retained for API compatibility)
        """

        table = self.table

        count = len(values)
        if count == 1:
            query = (key == values[0])
        else:
            query = key.belongs(values)

        if self.show_need:
            ntable = current.s3db.dvr_need
            left = ntable.on(ntable.id == table.need_id)
            rows = current.db(query).select(table.id,
                                            table.name,
                                            ntable.id,
                                            ntable.name,
                                            left = left,
                                            limitby = (0, count),
                                            )
        else:
            rows = current.db(query).select(table.id,
                                            table.name,
                                            limitby = (0, count),
                                            )
        self.queries += 1

        return rows

    # -------------------------------------------------------------------------
    def represent_row(self, row):
        """
            Represent a row

            Args:
                row: the Row
        """

        T = current.T
        translate = self.translate

        if self.show_need:

            theme = row.dvr_response_theme.name
            if theme:
                theme = T(theme) if translate else theme
            else:
                theme = self.none

            need = row.dvr_need.name
            if need:
                need = T(need) if translate else need

            if need:
                reprstr = "%s: %s" % (need, theme)
            else:
                reprstr = theme
        else:
            theme = row.name
            if theme:
                reprstr = T(theme) if translate else theme
            else:
                reprstr = self.none

        return reprstr

# =============================================================================
class dvr_CaseActivityRepresent(S3Represent):
    """ Representation of case activity IDs """

    def __init__(self, *,
                 show_as = None,
                 fmt = None,
                 show_link = False,
                 show_date = False,
                 show_subject = False,
                 linkto = DEFAULT,
                 ):
        """
            Args:
                show_as: alternative representations:
                         "beneficiary"|"need"|"subject"
                fmt: string format template for person record
                show_link: show representation as clickable link
                show_date: include date when showing as need or subject
                show_subject: include subject when showing as need
                linkto: URL template for links
        """

        super().__init__(lookup = "dvr_case_activity",
                         show_link = show_link,
                         linkto = linkto,
                         )

        if show_as is None:
            self.show_as = "beneficiary"
        else:
            self.show_as = show_as

        if fmt:
            self.fmt = fmt
        else:
            self.fmt = "%(first_name)s %(last_name)s"

        self.show_date = show_date
        self.show_subject = show_subject

    # -------------------------------------------------------------------------
    def lookup_rows(self, key, values, fields=None):
        """
            Custom rows lookup

            Args:
                key: the key Field
                values: the values
                fields: unused (retained for API compatibility)
        """

        table = self.table

        count = len(values)
        if count == 1:
            query = (key == values[0])
        else:
            query = key.belongs(values)

        ptable = current.s3db.pr_person
        left = [ptable.on(ptable.id == table.person_id)]

        show_as = self.show_as
        fields = [table.id, ptable.id]
        if show_as == "beneficiary":
            fields.extend([ptable.pe_label,
                           ptable.first_name,
                           ptable.middle_name,
                           ptable.last_name,
                           ])

        elif show_as == "need":
            ntable = current.s3db.dvr_need
            left.append(ntable.on(ntable.id == table.need_id))
            fields.extend([table.start_date,
                           ntable.name,
                           ])
            if self.show_subject:
                fields.append(table.subject)

        else:
            fields.append(table.subject)

        rows = current.db(query).select(*fields,
                                        left = left,
                                        limitby = (0, count),
                                        )
        self.queries += 1

        return rows

    # -------------------------------------------------------------------------
    def represent_row(self, row):
        """
            Represent a row

            Args:
                row: the Row
        """

        show_as = self.show_as
        if show_as == "beneficiary":
            beneficiary = dict(row.pr_person)

            # Do not show "None" for no label
            if beneficiary.get("pe_label") is None:
                beneficiary["pe_label"] = ""

            return self.fmt % beneficiary

        elif show_as == "need":

            need = row.dvr_need.name
            if self.translate:
                need = current.T(need) if need else self.none
            if self.show_subject:
                subject = row.dvr_case_activity.subject
                repr_str = ("%s: %s" % (need, subject)) if subject else need
            else:
                repr_str = need

        else:
            repr_str = row.dvr_case_activity.subject

        if self.show_date:
            date = row.dvr_case_activity.start_date
            if date:
                date = current.calendar.format_date(date, local=True)
                repr_str = "[%s] %s" % (date, repr_str)

        return repr_str

    # -------------------------------------------------------------------------
    def link(self, k, v, row=None):
        """
            Represent a (key, value) as hypertext link

            Args:
                k: the key (dvr_case_activity.id)
                v: the representation of the key
                row: the row with this key
        """

        if self.linkto is not DEFAULT:
            k = s3_str(k)
            return A(v, _href=self.linkto.replace("[id]", k).replace("%5Bid%5D", k))

        try:
            beneficiary = row.pr_person
        except AttributeError:
            return v

        url = URL(c = "dvr",
                  f = "person",
                  args = [beneficiary.id, "case_activity", k],
                  extension = "",
                  )

        return A(v, _href = url)

# =============================================================================
class dvr_DocEntityRepresent(S3Represent):
    """ Module context-specific representation of doc-entities """

    def __init__(self, *,
                 case_label = None,
                 case_group_label = None,
                 activity_label = None,
                 use_sector = True,
                 use_need = False,
                 use_subject = True,
                 show_link = False,
                 linkto_controller = "dvr",
                 ):
        """
            Args:
                case_label: label for cases (default: "Case")
                case_group_label: label for case groups (default: "Case Group")
                activity_label: label for case activities
                                (default: "Activity")
                use_sector: use sector if available instead of activity label
                use_need: represent activities as need type
                use_subject: include subject when representing activities
                             as need type
                show_link: show representation as clickable link
                linkto_controller: controller to link to
        """

        super().__init__(lookup = "doc_entity",
                         show_link = show_link,
                         )

        T = current.T

        if case_label:
            self.case_label = case_label
        else:
            self.case_label = T("Case")

        if case_group_label:
            self.case_group_label = case_group_label
        else:
            self.case_group_label = T("Case Group")

        if activity_label:
            self.activity_label = activity_label
        else:
            self.activity_label = T("Activity")

        self.use_sector = use_sector
        self.use_need = use_need
        self.use_subject = use_subject or not use_need
        self.linkto_controller = linkto_controller

    # -------------------------------------------------------------------------
    def lookup_rows(self, key, values, fields=None):
        """
            Custom rows lookup

            Args:
                key: the key Field
                values: the values
                fields: unused (retained for API compatibility)
        """

        db = current.db
        s3db = current.s3db

        table = self.table
        ptable = s3db.pr_person

        count = len(values)
        if count == 1:
            query = (key == values[0])
        else:
            query = key.belongs(values)

        rows = db(query).select(table.doc_id,
                                table.instance_type,
                                limitby = (0, count),
                                orderby = table.instance_type,
                                )
        self.queries += 1

        # Sort by instance type
        doc_ids = {}
        for row in rows:
            doc_id = row.doc_id
            instance_type = row.instance_type
            if instance_type not in doc_ids:
                doc_ids[instance_type] = {doc_id: row}
            else:
                doc_ids[instance_type][doc_id] = row

        need_ids = set()
        sector_ids = set()
        for instance_type in ("dvr_case", "dvr_case_activity", "pr_group"):

            doc_entities = doc_ids.get(instance_type)
            if not doc_entities:
                continue

            # The instance table
            itable = s3db[instance_type]

            # Look up person and instance data
            query = itable.doc_id.belongs(set(doc_entities.keys()))
            if instance_type == "pr_group":
                mtable = s3db.pr_group_membership
                left = [mtable.on((mtable.group_id == itable.id) & \
                                  (mtable.deleted == False)),
                        ptable.on(ptable.id == mtable.person_id),
                        ]
            else:
                left = ptable.on(ptable.id == itable.person_id)
            fields = [itable.id,
                      itable.doc_id,
                      ptable.id,
                      ptable.first_name,
                      ptable.middle_name,
                      ptable.last_name,
                      ]
            if instance_type == "dvr_case_activity":
                fields.extend((itable.sector_id,
                               itable.subject,
                               itable.need_id,
                               ))
            if instance_type == "pr_group":
                fields.extend((itable.name,
                               itable.group_type,
                               ))
            irows = db(query).select(left=left, *fields)
            self.queries += 1

            # Add the person+instance data to the entity rows
            for irow in irows:
                instance = irow[instance_type]
                entity = doc_entities[instance.doc_id]

                if hasattr(instance, "sector_id"):
                    sector_ids.add(instance.sector_id)
                if hasattr(instance, "need_id"):
                    need_ids.add(instance.need_id)

                entity[instance_type] = instance
                entity.pr_person = irow.pr_person

            # Bulk represent any sector ids
            if sector_ids and "sector_id" in itable.fields:
                represent = itable.sector_id.represent
                if represent and hasattr(represent, "bulk"):
                    represent.bulk(list(sector_ids))

            # Bulk represent any need ids
            if need_ids and "need_id" in itable.fields:
                represent = itable.need_id.represent
                if represent and hasattr(represent, "bulk"):
                    represent.bulk(list(need_ids))

        return rows

    # -------------------------------------------------------------------------
    def represent_row(self, row):
        """
            Represent a row

            Args:
                row: the Row
        """

        reprstr = self.default

        instance_type = row.instance_type
        if hasattr(row, "pr_person"):

            if instance_type == "dvr_case":

                person = row.pr_person
                title = s3_fullname(person)
                label = self.case_label

            elif instance_type == "dvr_case_activity":

                table = current.s3db.dvr_case_activity
                activity = row.dvr_case_activity

                title = activity.subject if activity.subject else "-"
                if self.use_need:
                    need_id = activity.need_id
                    if need_id:
                        represent = table.need_id.represent
                        if self.use_subject and title:
                            title = "%s: %s" % (represent(need_id), title)
                        else:
                            title = represent(need_id)

                label = self.activity_label
                if self.use_sector:
                    sector_id = activity.sector_id
                    if sector_id:
                        represent = table.sector_id.represent
                        label = represent(sector_id)

            elif instance_type == "pr_group":

                group = row.pr_group

                if group.group_type == 7:
                    label = self.case_group_label
                    if group.name:
                        title = group.name
                    else:
                        person = row.pr_person
                        title = s3_fullname(person)
                else:
                    label = current.T("Group")
                    title = group.name or self.default
            else:
                title = None
                label = None

            if title:
                reprstr = "%s (%s)" % (s3_str(title), s3_str(label))

        return reprstr

    # -------------------------------------------------------------------------
    def link(self, k, v, row=None):
        """
            Represent a (key, value) as hypertext link

            Args:
                k: the key (doc_entity.doc_id)
                v: the representation of the key
                row: the row with this key
        """

        link = v

        if row:
            if row.instance_type == "dvr_case_activity":
                try:
                    person_id = row.pr_person.id
                    case_activity_id = row.dvr_case_activity.id
                except AttributeError:
                    pass
                else:
                    url = URL(c = self.linkto_controller,
                              f = "person",
                              args = [person_id,
                                      "case_activity",
                                      case_activity_id,
                                      ],
                              extension="",
                              )
                    link = A(v, _href=url)

        return link

# =============================================================================
class dvr_VulnerabilityRepresent(S3Represent):
    """ Representation of vulnerabilities """

    def __init__(self):

        super().__init__(lookup="dvr_vulnerability")

        self.vulnerability_types = {}

    # -------------------------------------------------------------------------
    def lookup_rows(self, key, values, fields=None):
        """
            Custom rows lookup

            Args:
                key: the key Field
                values: the values
                fields: unused (retained for API compatibility)
        """

        db = current.db
        s3db = current.s3db

        table = self.table

        count = len(values)
        if count == 1:
            query = (key == values[0])
        else:
            query = key.belongs(values)

        rows = db(query).select(table.id,
                                table.date,
                                table.vulnerability_type_id,
                                limitby = (0, count),
                                )
        self.queries += 1

        # Determine unknown type IDs
        type_ids = {row.vulnerability_type_id for row in rows}
        type_ids -= set(self.vulnerability_types.keys())
        type_ids.discard(None)

        if type_ids:
            # Look up the names for unknown type IDs
            ttable = s3db.dvr_vulnerability_type
            query = (ttable.id.belongs(type_ids))
            types = db(query).select(ttable.id, ttable.name)
            self.queries += 1

            # Store the type names
            self.vulnerability_types.update({t.id: t.name for t in types})

        return rows

    # -------------------------------------------------------------------------
    def represent_row(self, row):
        """
            Represent a row

            Args:
                row: the Row
        """

        try:
            type_id = row.vulnerability_type_id
        except AttributeError:
            type_id = None
        type_name = self.vulnerability_types.get(type_id, self.none)

        return "[%s] %s" % (self.table.date.represent(row.date), type_name)

# =============================================================================
class AppointmentEvent:
    """ Closing of appointments by case events """

    def __init__(self, event_id):
        """
            Args:
                event_id: the dvr_case_event record ID
        """

        self.event_id = event_id

        self._event = None
        self._event_type = None
        self._appointment_type = None

    # -------------------------------------------------------------------------
    @property
    def event(self):
        """
            The event (lazy property)

            Returns:
                dvr_case_event Row
        """

        event = self._event
        if event is None:

            s3db = current.s3db
            etable = s3db.dvr_case_event
            ttable = s3db.dvr_case_event_type

            left = ttable.on(ttable.id == etable.type_id)
            query = (etable.id == self.event_id)
            row = current.db(query).select(etable.id,
                                           etable.person_id,
                                           etable.case_id,
                                           etable.date,
                                           ttable.id,
                                           ttable.appointment_type_id,
                                           left = left,
                                           limitby = (0, 1),
                                           ).first()
            if row:
                self._event_type = row.dvr_case_event_type
                event = self._event = row.dvr_case_event

        return event

    # -------------------------------------------------------------------------
    @property
    def event_type(self):
        """
            The event type (lazy property)

            Returns:
                dvr_case_event_type Row
        """

        return self._event_type if self.event else None

    # -------------------------------------------------------------------------
    @property
    def appointment_type_id(self):
        """
            The appointment type ID (lazy property)

            Returns:
                dvr_case_appointment_type record ID
        """

        event_type = self.event_type

        return event_type.appointment_type_id if event_type else None

    # -------------------------------------------------------------------------
    def appointment(self):
        """
            Finds the appointment to be closed

            Returns:
                dvr_case_appointment Row
        """

        db = current.db
        s3db = current.s3db

        appointment_type_id = self.appointment_type_id
        if not appointment_type_id:
            return None

        event = self.event

        # Appointments of the same case
        atable = s3db.dvr_case_appointment
        base_query = (atable.person_id == event.person_id)
        if event.case_id:
            base_query &= (atable.case_id == event.case_id)

        # The event date
        event_date = event.date
        if not event_date:
            event_date = current.request.utcnow.replace(microsecond=0)

        # Identify the appointment
        appointment = None
        fields = (atable.id,
                  atable.type_id,
                  atable.date,
                  atable.start_date,
                  atable.end_date,
                  atable.status,
                  )

        use_time = current.deployment_settings.get_dvr_appointments_use_time()
        if use_time:
            # The last appointment preceding the event on that day
            day_start = event_date.replace(hour=0, minute=0, second=0)
            query = base_query & \
                    (atable.start_date != None) & \
                    (atable.start_date >= day_start) & \
                    (atable.start_date <= event_date) & \
                    (atable.deleted == False)
            preceding = (db(query), ~atable.start_date)

            # The first appointment following the event on that day
            day_end = day_start + datetime.timedelta(days=1)
            query = base_query & \
                    (atable.start_date != None) & \
                    (atable.start_date > event_date) & \
                    (atable.start_date < day_end) & \
                    (atable.deleted == False)
            following = (db(query), atable.start_date)

            # The first of the two that matches the type and has status 2|4
            for t in (preceding, following):
                dbset, orderby = t
                row = dbset.select(*fields,
                                   orderby = orderby,
                                   limitby = (0, 1),
                                   ).first()
                if row and row.type_id == appointment_type_id and row.status in (2, 4):
                    appointment = row
                    break
        else:
            # The first pending appointment of that type on the same day,
            # or otherwise any completed appointment of that type on the day
            for status in (2, 4):
                query = base_query & \
                        (atable.date == event_date.date()) & \
                        (atable.type_id == appointment_type_id) & \
                        (atable.status == status) & \
                        (atable.deleted == False)
                row = db(query).select(*fields,
                                       orderby = atable.created_on,
                                       limitby = (0, 1),
                                       ).first()
                if row:
                    appointment = row
                    break

        if not appointment:
            # The oldest undated appointment with this type and status 1
            if use_time:
                query = base_query & (atable.start_date == None)
            else:
                query = base_query & (atable.date == None)
            query &= (atable.type_id == appointment_type_id) & \
                     (atable.status == 1) & \
                     (atable.deleted == False)
            appointment = db(query).select(*fields,
                                           orderby = atable.created_on,
                                           limitby = (0, 1),
                                           ).first()

        return appointment

    # -------------------------------------------------------------------------
    def close(self):
        """
            Closes a matching appointment for the event

            Returns:
                True|False for success

            Raises:
                S3PermissionError if operation not permitted
        """

        if current.deployment_settings.get_dvr_case_events_close_appointments():

            appointment = self.appointment()
            if appointment:
                appointment_id = self._close(appointment)
            else:
                appointment_id = self._create()
            return bool(appointment_id)
        else:
            return True

    # -------------------------------------------------------------------------
    def _close(self, appointment):
        """
            Adjusts its time frame to include the event (if using time), and
            closes the appointment

            Args:
                appointment: the dvr_case_appointment Row

            Returns:
                dvr_case_appointment record ID
        """

        s3db = current.s3db

        if not current.auth.s3_has_permission("update",
                                              "dvr_case_appointment",
                                              record_id = appointment.id,
                                              ):
            raise S3PermissionError()

        event_date = self.event.date

        update = {}
        if current.deployment_settings.get_dvr_appointments_use_time():
            window = self.time_window(event_date)
            start, end = appointment.start_date, appointment.end_date
            if not start or start > event_date:
                start = update["start_date"] = window[0]
            if not end or end < event_date:
                update["end_date"] = window[1]
            date = start.date()
        else:
            date = event_date.date()

        if appointment.status != 4:
            update["status"] = 4
        if appointment.date != date:
            update["date"] = date

        if update:
            atable = s3db.dvr_case_appointment
            success = appointment.update_record(**update)
            if success:
                s3db.onaccept(atable, appointment, method="update")
        else:
            success = True

        return appointment.id if success else None

    # -------------------------------------------------------------------------
    def _create(self):
        """
            Creates a new closed appointment from the event

            Returns:
                dvr_case_appointment record ID
        """

        s3db = current.s3db
        auth = current.auth

        if not auth.s3_has_permission("create", "dvr_case_appointment"):
            raise S3PermissionError()

        event = self.event
        event_date = event.date

        # Prepare data
        appointment = {"person_id": event.person_id,
                       "type_id": self.appointment_type_id,
                       "status": 4, # closed
                       }
        if current.deployment_settings.get_dvr_appointments_use_time():
            window = self.time_window(event_date)
            appointment["start_date"] = window[0]
            appointment["end_date"] = window[1]
            appointment["date"] = window[0].date()
        else:
            appointment["date"] = event_date.date()

        # Create new appointment
        atable = s3db.dvr_case_appointment
        appointment_id = appointment["id"] = atable.insert(**appointment)
        if appointment_id:
            s3db.update_super(atable, appointment)
            auth.s3_set_record_owner(atable, appointment_id)
            auth.s3_make_session_owner(atable, appointment_id)
            s3db.onaccept(atable, appointment, method="create")

        return appointment_id

    # -------------------------------------------------------------------------
    @staticmethod
    def time_window(dt, duration=15):
        """
            Computes a suitable time window that includes dt

            Args:
                dt: a datetime
                duration: the minimum duration in minutes

            Returns:
                tuple (start, end) of datetime
        """

        p = 15 # Quarter hour point
        q = lambda minute: minute // p * p

        # The quarter point preceding dt
        start = dt.replace(minute=q(dt.minute), microsecond=0)

        # The quarter point following dt + duration
        delta = p + duration - 1
        end = dt + datetime.timedelta(minutes=delta)
        end = end.replace(minute=q(end.minute), microsecond=0)

        return (start, end - datetime.timedelta(seconds=1))

# =============================================================================
class ActivityEvent:
    """ Activity (beneficiary) registration through a case event """

    def __init__(self, event_id):
        """
            Args:
                event_id: the dvr_case_event record ID
        """

        self.event_id = event_id

        self._event = None
        self._activity = None
        self._beneficiary = None

    # -------------------------------------------------------------------------
    @property
    def event(self):
        """
            The case event (lazy property)

            Returns:
                dvr_case_event Row
        """

        event = self._event
        if event is None:
            table = current.s3db.dvr_case_event
            query = (table.id == self.event_id) & \
                    (table.deleted == False)
            event = self._event = current.db(query).select(table.id,
                                                           table.type_id,
                                                           table.person_id,
                                                           table.date,
                                                           limitby = (0, 1),
                                                           ).first()
        return event

    # -------------------------------------------------------------------------
    @property
    def activity(self):
        """
            The target activity specified by the event type (lazy property)

            Returns:
                act_activity Row
        """

        activity, event = self._activity, self.event
        if activity is None and event:
            s3db = current.s3db
            atable = s3db.act_activity
            ttable = s3db.dvr_case_event_type

            join = ttable.on((ttable.activity_id == atable.id) & \
                             (ttable.id == event.type_id))
            query = (atable.deleted == False)
            event_date = event.date
            if event_date:
                event_date = event_date.date()
                query = ((atable.date == None) |
                         (atable.date <= event_date)) & \
                        ((atable.end_date == None) |
                         (atable.end_date >= event_date)) & \
                        query

            activity = current.db(query).select(atable.id,
                                                atable.date,
                                                atable.end_date,
                                                join = join,
                                                limitby = (0, 1),
                                                ).first()
            self._activity = activity

        return activity

    # -------------------------------------------------------------------------
    @property
    def beneficiary(self):
        """
            The act_beneficiary record matching the event (lazy property)

            Returns:
                act_beneficiary Row
        """

        beneficiary = self._beneficiary
        if not beneficiary:
            event, activity = self.event, self.activity
            if not event or not activity:
                return None

            btable = current.s3db.act_beneficiary
            query = (btable.person_id == event.person_id) & \
                    (btable.activity_id == activity.id) & \
                    (btable.date == event.date) & \
                    (btable.deleted == False)
            beneficiary = current.db(query).select(btable.id,
                                                   limitby = (0, 1),
                                                   ).first()
            self._beneficiary = beneficiary
        return beneficiary

    # -------------------------------------------------------------------------
    def register(self):
        """
            Registers the client as beneficiary of the activity

            Returns:
                act_beneficiary record ID
        """

        beneficiary = self.beneficiary
        if not beneficiary:
            event = self.event
            if event and event.date and self.activity:
                beneficiary_id = self._register()
            else:
                beneficiary_id = None
        else:
            beneficiary_id = beneficiary.id

        return beneficiary_id

    # -------------------------------------------------------------------------
    def _register(self):
        """
            Beneficiary registration subroutine

            Returns:
                act_beneficiary record ID
        """

        s3db = current.s3db
        auth = current.auth

        btable = s3db.act_beneficiary

        event = self.event
        beneficiary = {"person_id": event.person_id,
                       "activity_id": self.activity.id,
                       "date": event.date,
                       }
        beneficiary_id = beneficiary["id"] = btable.insert(**beneficiary)
        if beneficiary_id:
            s3db.update_super(btable, beneficiary)
            auth.s3_set_record_owner(btable, beneficiary_id)
            auth.s3_make_session_owner(btable, beneficiary_id)
            s3db.onaccept(btable, beneficiary, method="create")

        return beneficiary_id

# =============================================================================
class DVRManageAppointments(CRUDMethod):
    """ Custom method to bulk-manage appointments """

    # -------------------------------------------------------------------------
    def apply_method(self, r, **attr):

        T = current.T
        s3db = current.s3db

        get_vars = r.get_vars
        response = current.response

        output = None

        if not self._permitted("update"):
            r.unauthorised()

        if r.http == "POST" and r.representation != "aadata":

            count = 0

            base_query = (FS("person_id$case.archived") == None) | \
                         (FS("person_id$case.archived") == False)

            post_vars = r.post_vars
            if "selected" in post_vars and "mode" in post_vars and \
               any(n in post_vars for n in ("completed", "cancelled")):

                selected = post_vars.selected
                if selected:
                    selected = selected.split(",")
                else:
                    selected = []

                db = current.db
                atable = s3db.dvr_case_appointment

                # Handle exclusion filter
                if post_vars.mode == "Exclusive":
                    if "filterURL" in post_vars:
                        filters = S3URLQuery.parse_url(post_vars.filterURL)
                    else:
                        filters = None
                    query = ~(FS("id").belongs(selected)) & base_query

                    aresource = s3db.resource("dvr_case_appointment",
                                              filter = query,
                                              vars =  filters,
                                              )
                    rows = aresource.select(["id"], as_rows=True)
                    selected = [str(row.id) for row in rows]

                if selected:
                    query = (atable.id.belongs(selected)) & \
                            (atable.deleted != True)
                    if "completed" in post_vars:
                        count = db(query).update(status=4) # Completed
                    elif "cancelled" in post_vars:
                        count = db(query).update(status=6) # Cancelled

            current.session.confirmation = T("%(count)s Appointments updated") % \
                                           {"count": count}
            redirect(URL(f="case_appointment", args=["manage"], vars={}))

        elif r.http == "GET" or r.representation == "aadata":
            resource = r.resource

            # Filter widgets
            filter_widgets = resource.get_config("filter_widgets")

            # List fields
            list_fields = ["id",
                           (T("ID"), "person_id$pe_label"),
                           "person_id",
                           "type_id",
                           "date",
                           "status",
                           ]

            # Data table
            totalrows = resource.count()
            if "pageLength" in get_vars:
                display_length = get_vars["pageLength"]
                if display_length == "None":
                    display_length = None
                else:
                    display_length = int(display_length)
            else:
                display_length = 25
            if display_length:
                limit = 4 * display_length
            else:
                limit = None

            # Sorting by person_id requires introspection => use datatable_filter
            if r.representation != "aadata":
                get_vars = dict(get_vars)
                dt_sorting = {"iSortingCols": "1",
                              "bSortable_0": "false",
                              "iSortCol_0": "1",
                              "sSortDir_0": "asc",
                              }
                get_vars.update(dt_sorting)
            dtfilter, orderby, left = resource.datatable_filter(list_fields,
                                                                get_vars,
                                                                )
            resource.add_filter(dtfilter)
            data = resource.select(list_fields,
                                   start = 0,
                                   limit = limit,
                                   orderby = orderby,
                                   left = left,
                                   count = True,
                                   represent = True,
                                   )
            filteredrows = data["numrows"]
            dt = DataTable(data["rfields"], data["rows"], "datatable", orderby=orderby)

            # Bulk actions
            dt_bulk_actions = [(T("Completed"), "completed"),
                               (T("Cancelled"), "cancelled"),
                               ]

            if r.representation == "html":
                # Page load
                resource.configure(deletable = False)

                BasicCRUD.action_buttons(r)
                response.s3.no_formats = True

                # Data table (items)
                items = dt.html(totalrows,
                                filteredrows,
                                dt_pageLength = display_length,
                                dt_ajax_url = URL(c = "dvr",
                                                  f = "case_appointment",
                                                  args = ["manage"],
                                                  vars = {},
                                                  extension = "aadata",
                                                  ),
                                dt_searching = False,
                                dt_pagination = True,
                                dt_bulk_actions = dt_bulk_actions,
                                )

                # Filter form
                if filter_widgets:

                    # Where to retrieve filtered data from:
                    _vars = CRUDMethod._remove_filters(r.get_vars)
                    filter_submit_url = r.url(vars=_vars)

                    # Where to retrieve updated filter options from:
                    filter_ajax_url = URL(f = "case_appointment",
                                          args = ["filter.options"],
                                          vars = {},
                                          )

                    get_config = resource.get_config
                    filter_clear = get_config("filter_clear", True)
                    filter_formstyle = get_config("filter_formstyle", None)
                    filter_submit = get_config("filter_submit", True)
                    filter_form = FilterForm(filter_widgets,
                                             clear = filter_clear,
                                             formstyle = filter_formstyle,
                                             submit = filter_submit,
                                             ajax = True,
                                             url = filter_submit_url,
                                             ajaxurl = filter_ajax_url,
                                             _class = "filter-form",
                                             _id = "datatable-filter-form",
                                             )
                    fresource = current.s3db.resource(resource.tablename)
                    alias = resource.alias if r.component else None
                    ff = filter_form.html(fresource,
                                          r.get_vars,
                                          target = "datatable",
                                          alias = alias,
                                          )
                else:
                    ff = ""

                output = {"items": items,
                          "title": T("Manage Appointments"),
                          "list_filter_form": ff,
                          }

                response.view = "list_filter.html"

            elif r.representation == "aadata":

                # Ajax refresh
                if "draw" in get_vars:
                    echo = int(get_vars["draw"])
                else:
                    echo = None
                output = dt.json(totalrows,
                                 filteredrows,
                                 echo,
                                 dt_bulk_actions = dt_bulk_actions,
                                 )
                response.headers["Content-Type"] = "application/json"

            else:
                r.error(415, current.ERROR.BAD_FORMAT)
        else:
            r.error(405, current.ERROR.BAD_METHOD)

        return output

# =============================================================================
class DVRManageAllowance(CRUDMethod):
    """ Method handler to bulk-update allowance payments status """

    # -------------------------------------------------------------------------
    def apply_method(self, r, **attr):
        """
            Main entry point for REST interface.

            Args:
                r: the CRUDRequest instance
                attr: controller parameters
        """

        # User must be permitted to update allowance information
        permitted = self._permitted("update")
        if not permitted:
            r.unauthorised()

        output = None

        if r.representation in ("html", "iframe"):
            if r.http in ("GET", "POST"):
                output = self.bulk_update_status(r, **attr)
            else:
                r.error(405, current.ERROR.BAD_METHOD)
        else:
            r.error(415, current.ERROR.BAD_FORMAT)

        return output

    # -------------------------------------------------------------------------
    def bulk_update_status(self, r, **attr):
        """
            Method to bulk-update status of allowance payments

            Args:
                r: the CRUDRequest instance
                attr: controller parameters
        """

        T = current.T
        s3db = current.s3db

        settings = current.deployment_settings
        response = current.response

        output = {"title": T("Update Allowance Status"),
                  }

        status_opts = dict(s3db.dvr_allowance_status_opts)

        # Can not bulk-update from or to status "paid"
        del status_opts[2]

        # Form fields
        formfields = [DateField("from_date",
                                label = T("Planned From"),
                                set_min = "#allowance_to_date",
                                ),
                      DateField("to_date",
                                default = "now",
                                label = T("Planned Until"),
                                set_max = "#allowance_from_date",
                                empty = False,
                                ),
                      Field("current_status", "integer",
                            default = 1, # pending
                            label = T("Current Status"),
                            requires = IS_IN_SET(status_opts),
                            ),
                      Field("new_status", "integer",
                            default = 4, # missed
                            label = T("New Status"),
                            requires = IS_IN_SET(status_opts),
                            ),
                      ]

        # Form buttons
        submit_btn = INPUT(_class = "tiny primary button",
                           _name = "submit",
                           _type = "submit",
                           _value = T("Update"),
                           )
        cancel_btn = A(T("Cancel"),
                       _href = r.url(id=None, method=""),
                       _class = "action-lnk",
                       )
        buttons = [submit_btn, cancel_btn]

        # Generate the form and add it to the output
        resourcename = r.resource.name
        formstyle = settings.get_ui_formstyle()
        form = SQLFORM.factory(record = None,
                               showid = False,
                               formstyle = formstyle,
                               table_name = resourcename,
                               buttons = buttons,
                               *formfields)
        output["form"] = form

        # Process the form
        formname = "%s/manage" % resourcename
        if form.accepts(r.post_vars,
                        current.session,
                        formname = formname,
                        onvalidation = self.validate,
                        keepvalues = False,
                        hideerror = False,
                        ):

            formvars = form.vars

            current_status = formvars.current_status
            new_status = formvars.new_status

            table = s3db.dvr_allowance
            query = current.auth.s3_accessible_query("update", table) & \
                    (table.status == current_status) & \
                    (table.deleted != True)
            from_date = formvars.from_date
            if from_date:
                query &= table.date >= from_date
            to_date = formvars.to_date
            if to_date:
                query &= table.date <= to_date

            result = current.db(query).update(status=int(new_status))
            if result:
                response.confirmation = T("%(number)s records updated") % \
                                        {"number": result}
            else:
                response.warning = T("No records found")

        response.view = self._view(r, "update.html")
        return output

    # -------------------------------------------------------------------------
    @staticmethod
    def validate(form):
        """
            Update form validation

            Args:
                form: the FORM
        """

        T = current.T

        formvars = form.vars
        errors = form.errors

        # Must not update from status "paid"
        if str(formvars.current_status) == "2":
            errors.current_status = T("Bulk update from this status not allowed")

        # Must not update to status "paid"
        if str(formvars.new_status) == "2":
            errors.new_status = T("Bulk update to this status not allowed")

        # To-date must be after from-date
        from_date = formvars.from_date
        to_date = formvars.to_date
        if from_date and to_date and from_date > to_date:
            errors.to_date = T("Date until must be after date from")

# =============================================================================
class DVRRegisterCaseEvent(CRUDMethod):
    """ Method handler to register case events """

    # Action to check flag restrictions for
    ACTION = "id-check"

    # -------------------------------------------------------------------------
    def apply_method(self, r, **attr):
        """
            Main entry point for REST interface.

            Args:
                r: the CRUDRequest instance
                attr: controller parameters
        """

        if not self.permitted():
            current.auth.permission.fail()

        output = {}
        representation = r.representation

        if representation == "html":
            if r.http in ("GET", "POST"):
                output = self.registration_form(r, **attr)
            else:
                r.error(405, current.ERROR.BAD_METHOD)

        elif representation == "json":
            if r.http == "POST":
                output = self.registration_ajax(r, **attr)
            else:
                r.error(405, current.ERROR.BAD_METHOD)

        else:
            r.error(415, current.ERROR.BAD_FORMAT)

        return output

    # -------------------------------------------------------------------------
    def registration_form(self, r, **attr):
        """
            Render and process the registration form

            Args:
                r: the CRUDRequest instance
                attr: controller parameters
        """

        T = current.T

        response = current.response
        settings = current.deployment_settings

        output = {}

        http = r.http
        request_vars = r.get_vars

        check = True
        label = None

        if http == "POST":
            # Form submission
            request_vars = r.post_vars
            if "check" in request_vars:
                # Only check ID label, don't register an event
                label = request_vars.get("label")
            else:
                # Form has been submitted with "Register"
                check = False
        else:
            # Coming from external scan app (e.g. Zxing), or from a link
            label = request_vars.get("label")

        scanner = request_vars.get("scanner")

        person = None
        pe_label = None

        if label is not None:
            # Identify the person
            person = self.get_person(label)
            if person is None:
                if http == "GET":
                    response.error = T("No person found with this ID number")
            else:
                pe_label = person.pe_label
                request_vars["label"] = pe_label

        # Get person details, waiting intervals, flag and permission info
        flags = []
        intervals = {}
        if person:
            # Person details
            person_details = self.person_details(person)
            profile_picture = self.profile_picture(person)

            # Blocking periods for events
            event_types = self.get_event_types()
            blocked = self.get_blocked_events(person.id)
            for type_id, info in blocked.items():
                event_type = event_types.get(type_id)
                if not event_type:
                    continue
                code = event_type.code
                msg, dt = info
                intervals[code] = (s3_str(msg),
                                   "%sZ" % s3_encode_iso_datetime(dt),
                                   )

            # Flag info
            flag_info = dvr_get_flag_instructions(person.id,
                                                  action = self.ACTION,
                                                  )
            permitted = flag_info["permitted"]
            if check:
                info = flag_info["info"]
                for flagname, instructions in info:
                    flags.append({"n": s3_str(T(flagname)),
                                  "i": s3_str(T(instructions)),
                                  })
        else:
            person_details = ""
            profile_picture = None
            permitted = False

        # Identify the event type
        event_code = request_vars.get("event")
        event_type = self.get_event_type(event_code)
        if not event_type:
            # Fall back to default event type
            event_type = self.get_event_type()
        event_code = event_type.code if event_type else None

        # Whether the event registration is actionable
        actionable = event_code is not None

        label_input = self.label_input
        # TODO fix discrepancy between self.parse_code and QRInput
        use_qr_code = settings.get_org_site_presence_qrcode()
        if use_qr_code:
            if use_qr_code is True:
                label_input = S3QRInput()
            elif isinstance(use_qr_code, tuple):
                pattern, index = use_qr_code[:2]
                label_input = S3QRInput(pattern=pattern, index=index)

        # Standard form fields and data
        formfields = [Field("label",
                            label = T("ID"),
                            requires = [IS_NOT_EMPTY(error_message=T("Enter or scan an ID")),
                                        IS_LENGTH(512, minsize=1),
                                        ],
                            widget = label_input,
                            ),
                      Field("person",
                            label = "",
                            writable = False,
                            default = "",
                            ),
                      Field("flaginfo",
                            label = "",
                            writable = False,
                            ),
                      ]

        data = {"id": "",
                "label": pe_label,
                "person": person_details,
                "flaginfo": "",
                }

        # Hidden fields to store event type, scanner, flag info and permission
        hidden = {"event": event_code,
                  "scanner": scanner,
                  "actionable": json.dumps(actionable),
                  "permitted": json.dumps(permitted),
                  "flags": json.dumps(flags),
                  "intervals": json.dumps(intervals),
                  "image": profile_picture,
                  }

        # Additional form data
        widget_id, submit = self.get_form_data(person,
                                               formfields,
                                               data,
                                               hidden,
                                               permitted = permitted,
                                               )

        # Form buttons
        check_btn = INPUT(_class = "small secondary button check-btn",
                          _name = "check",
                          _type = "submit",
                          _value = T("Check ID"),
                          )
        submit_btn = INPUT(_class = "small primary button submit-btn",
                           _name = "submit",
                           _type = "submit",
                           _value = submit,
                           )

        # Toggle buttons (active button first, otherwise pressing Enter
        # hits the disabled button so requiring an extra tab step)
        actionable = hidden.get("actionable") == "true"
        if person and actionable and permitted:
            check_btn["_disabled"] = "disabled"
            check_btn.add_class("hide")
            buttons = [submit_btn, check_btn]
        else:
            submit_btn["_disabled"] = "disabled"
            submit_btn.add_class("hide")
            buttons = [check_btn, submit_btn]

        # Add the cancel-action
        buttons.append(A(T("Cancel"), _class = "cancel-action cancel-form-btn action-lnk"))

        resourcename = r.resource.name

        # Generate the form and add it to the output
        formstyle = settings.get_ui_formstyle()
        form = SQLFORM.factory(record = data if check else None,
                               showid = False,
                               formstyle = formstyle,
                               table_name = resourcename,
                               buttons = buttons,
                               hidden = hidden,
                               _id = widget_id,
                               *formfields)
        output["form"] = form

        # Process the form
        formname = "%s/registration" % resourcename
        if form.accepts(r.post_vars,
                        current.session,
                        onvalidation = self.validate,
                        formname = formname,
                        keepvalues = False,
                        hideerror = False,
                        ):

            if not check:
                self.accept(r, form, event_type=event_type)

        header = self.get_header(event_type)
        output.update(header)

        # ZXing Barcode Scanner Launch Button
        #output["zxing"] = self.get_zxing_launch_button(event_code)
        output["zxing"] = ""

        # Custom view
        response.view = self._view(r, "dvr/register_case_event.html")

        # Show profile picture by default or only on demand?
        show_picture = settings.get_ui_checkpoint_show_picture()

        # Inject JS
        options = {"tablename": resourcename,
                   "ajaxURL": r.url(None,
                                    method = "register",
                                    representation = "json",
                                    ),
                   "showPicture": show_picture,
                   "showPictureText": s3_str(T("Show Picture")),
                   "hidePictureText": s3_str(T("Hide Picture")),
                   }
        self.inject_js(widget_id, options)

        return output

    # -------------------------------------------------------------------------
    @staticmethod
    def label_input(field, value, **attributes):
        """
            Custom widget for label input, providing a clear-button
            (for ease of use on mobile devices where no ESC exists)

            Args:
                field: the Field
                value: the current value
                attributes: HTML attributes

            Note:
                expects Foundation theme
        """

        from gluon.sqlhtml import StringWidget

        default = {"value": (value is not None and str(value)) or ""}
        attr = StringWidget._attributes(field, default, **attributes)

        placeholder = current.T("Enter or scan ID")
        attr["_placeholder"] = placeholder

        postfix = ICON("fa fa-close")

        widget = DIV(DIV(INPUT(**attr),
                         _class="small-11 columns",
                         ),
                     DIV(SPAN(postfix, _class="postfix clear-btn"),
                         _class="small-1 columns",
                         ),
                     _class="row collapse",
                     )

        return widget

    # -------------------------------------------------------------------------
    # Configuration
    # -------------------------------------------------------------------------
    def permitted(self):
        """
            Helper function to check permissions

            Returns:
                True if permitted to use this method, else False
        """

        # User must be permitted to create case events
        return self._permitted("create")

    # -------------------------------------------------------------------------
    def get_event_type(self, code=None):
        """
            Get a case event type for an event code

            Args:
                code: the type code (using default event type if None)

            Returns:
                the dvr_case_event_type Row, or None if not found
        """

        event_types = self.get_event_types()

        event_type = None
        if code is None:
            event_type = event_types.get("_default")
        else:
            code = s3_str(code)
            for value in event_types.values():
                if value.code == code:
                    event_type = value
                    break

        return event_type

    # -------------------------------------------------------------------------
    def validate(self, form):
        """
            Validate the event registration form

            Args:
                form: the FORM
        """

        T = current.T

        formvars = form.vars

        pe_label = formvars.get("label").strip()
        person = self.get_person(pe_label)
        if person is None:
            form.errors["label"] = T("No person found with this ID number")
            permitted = False
        else:
            person_id = person.id
            formvars.person_id = person_id
            flag_info = dvr_get_flag_instructions(person_id,
                                                  action = self.ACTION,
                                                  )
            permitted = flag_info["permitted"]
        formvars.permitted = permitted

        # Validate the event type (if not default)
        type_id = None
        try:
            request_vars = form.request_vars
        except AttributeError:
            event_code = None
        else:
            event_code = request_vars.get("event")
        if event_code:
            event_type = self.get_event_type(event_code)
            if not event_type:
                form.errors["event"] = \
                current.response.error = T("Invalid event code")
            else:
                type_id = event_type.id
        formvars.type_id = type_id

        # Check whether event type is blocked for this person
        if person and type_id:
            blocked = self.get_blocked_events(person.id,
                                              type_id = type_id,
                                              )
            if type_id in blocked:
                msg = blocked[type_id][0]
                form.errors["event"] = current.response.error = msg

    # -------------------------------------------------------------------------
    def accept(self, r, form, event_type=None):
        """
            Helper function to process the form

            Args:
                r: the CRUDRequest
                form: the FORM
                event_type: the event_type (Row)
        """

        T = current.T
        response = current.response

        formvars = form.vars
        person_id = formvars.person_id

        success = False

        if not formvars.get("permitted"):
            response.error = T("Event registration not permitted")

        elif person_id:
            event_type_id = event_type.id if event_type else None
            success = self.register_event(person_id, event_type_id)
            if success:
                success = True
                response.confirmation = T("Event registered")
            else:
                response.error = T("Could not register event")

        else:
            response.error = T("Person not found")

        return success

    # -------------------------------------------------------------------------
    def registration_ajax(self, r, **attr):
        """
            Ajax response method, expects a JSON input like:

                {l: the PE label (from the input field),
                 c: boolean to indicate whether to just check
                    the PE label or to register payments
                 t: the event type code
                 }

            Args:
                r: the CRUDRequest instance
                attr: controller parameters

            Returns:
                JSON response, structure:

                    {l: the actual PE label (to update the input field),
                     p: the person details,
                     d: the family details,
                     f: [{n: the flag name
                          i: the flag instructions
                          },
                         ...],
                     b: profile picture URL,
                     i: {<event_code>: [<msg>, <blocked_until_datetime>]},

                     s: whether the action is permitted or not

                     e: form error (for label field)

                     a: error message
                     w: warning message
                     m: success message
                     }
        """

        T = current.T

        # Load JSON data from request body
        s = r.body
        s.seek(0)
        try:
            data = json.load(s)
        except (ValueError, TypeError):
            r.error(400, current.ERROR.BAD_REQUEST)


        # Initialize processing variables
        output = {}

        error = None

        alert = None
        message = None
        warning = None

        permitted = False
        flags = []

        # Identify the person
        pe_label = data.get("l")
        person = self.get_person(pe_label)

        if person is None:
            error = s3_str(T("No person found with this ID number"))

        else:
            # Get flag info
            flag_info = dvr_get_flag_instructions(person.id,
                                                  action = "id-check",
                                                  )
            permitted = flag_info["permitted"]

            check = data.get("c")
            if check:
                # Person details
                person_details = self.person_details(person)
                profile_picture = self.profile_picture(person)

                output["p"] = s3_str(person_details)
                output["l"] = person.pe_label
                output["b"] = profile_picture

                # Family details
                details = dvr_get_household_size(person.id,
                                                 dob = person.date_of_birth,
                                                 )
                if details:
                    output["d"] = {"d": details}

                # Flag Info
                info = flag_info["info"]
                for flagname, instructions in info:
                    flags.append({"n": s3_str(T(flagname)),
                                  "i": s3_str(T(instructions)),
                                  })

                # Blocking periods for events
                event_types = self.get_event_types()
                blocked = self.get_blocked_events(person.id)
                intervals = {}
                for type_id, info in blocked.items():
                    event_type = event_types.get(type_id)
                    if not event_type:
                        continue
                    code = event_type.code
                    msg, dt = info
                    intervals[code] = (s3_str(msg),
                                       "%sZ" % s3_encode_iso_datetime(dt),
                                       )
                output["i"] = intervals
            else:
                # Check event code and permission
                type_id = None
                event_code = data.get("t")
                if not event_code:
                    alert = T("No event type specified")
                elif not permitted:
                    alert = T("Event registration not permitted")
                else:
                    event_type = self.get_event_type(event_code)
                    if not event_type:
                        alert = T("Invalid event type: %s") % event_code
                    else:
                        type_id = event_type.id

                if type_id:
                    # Check whether event type is blocked for this person
                    person_id = person.id
                    blocked = self.get_blocked_events(person_id,
                                                      type_id = type_id,
                                                      )
                    if type_id in blocked:
                        # Event type is currently blocked for this person
                        alert = blocked[type_id][0]
                    else:
                        # Ok - register the event
                        success = self.register_event(person.id, type_id)
                        if success:
                            message = T("Event registered")
                        else:
                            alert = T("Could not register event")

        # Add messages to output
        if alert:
            output["a"] = s3_str(alert)
        if error:
            output["e"] = s3_str(error)
        if message:
            output["m"] = s3_str(message)
        if warning:
            output["w"] = s3_str(warning)

        # Add flag info to output
        output["s"] = permitted
        output["f"] = flags

        current.response.headers["Content-Type"] = "application/json"
        return json.dumps(output)

    # -------------------------------------------------------------------------
    @classmethod
    def get_form_data(cls, person, formfields, data, hidden, *, permitted=False):
        """
            Helper function to extend the form

            Args:
                person: the person (Row)
                formfields: list of form fields (Field)
                data: the form data (dict)
                hidden: hidden form fields (dict)
                permitted: whether the action is permitted

            Returns:
                tuple (widget_id, submit_label)
        """

        T = current.T

        # Extend form with household size info
        if person:
            details = dvr_get_household_size(person.id,
                                             dob = person.date_of_birth,
                                             )
        else:
            details = ""
        formfields.extend([Field("details",
                                 label = T("Family"),
                                 writable = False,
                                 ),
                           ])
        data["details"] = details

        widget_id = "case-event-form"
        submit = current.T("Register")

        return widget_id, submit

    # -------------------------------------------------------------------------
    def get_header(self, event_type=None):
        """
            Helper function to construct the event type header

            Args:
                event_type: the event type (Row)

            Returns:
                dict of view items
        """

        T = current.T

        output = {}

        # Event type header
        if event_type:
            event_type_name = T(event_type.name)
            name_class = "event-type-name"
        else:
            event_type_name = T("Please select an event type")
            name_class = "event-type-name placeholder"

        event_type_header = DIV(H4(SPAN(T(event_type_name),
                                        _class = name_class,
                                        ),
                                   SPAN(ICON("settings"),
                                        _class = "event-type-setting",
                                        ),
                                   _class = "event-type-toggle",
                                   _id = "event-type-toggle",
                                   ),
                                _class = "event-type-header",
                                )
        output["event_type"] = event_type_header

        # Event type selector
        event_types = self.get_event_types()
        buttons = []
        for k, v in event_types.items():
            if k != "_default":
                button = A(T(v.name),
                           _class = "secondary button event-type-selector",
                           data = {"code": s3_str(v.code),
                                   "name": s3_str(T(v.name)),
                                   },
                           )
                buttons.append(button)
        output["event_type_selector"] = DIV(buttons,
                                            _class="button-group stacked hide event-type-selector",
                                            _id="event-type-selector",
                                            )

        return output

    # -------------------------------------------------------------------------
    # Class-specific functions
    # -------------------------------------------------------------------------
    @staticmethod
    def register_event(person_id, type_id):
        """
            Register a case event

            Args:
                person_id: the person record ID
                type:id: the event type record ID
        """

        s3db = current.s3db

        ctable = s3db.dvr_case
        etable = s3db.dvr_case_event

        # Get the case ID for the person_id
        query = (ctable.person_id == person_id) & \
                (ctable.deleted != True)
        case = current.db(query).select(ctable.id,
                                        limitby=(0, 1),
                                        ).first()
        if case:
            case_id = case.id
        else:
            case_id = None

        # Customise event resource
        r = CRUDRequest("dvr", "case_event",
                        current.request,
                        args = [],
                        get_vars = {},
                        )
        r.customise_resource("dvr_case_event")

        data = {"person_id": person_id,
                "case_id": case_id,
                "type_id": type_id,
                "date": current.request.utcnow,
                }
        record_id = etable.insert(**data)
        if record_id:
            # Set record owner
            auth = current.auth
            auth.s3_set_record_owner(etable, record_id)
            auth.s3_make_session_owner(etable, record_id)
            # Execute onaccept
            data["id"] = record_id
            s3db.onaccept(etable, data, method="create")

        return record_id

    # -------------------------------------------------------------------------
    def get_event_types(self):
        """
            Lazy getter for case event types

            Returns:
                a dict {id: Row} for dvr_case_event_type, with an
                additional key "_default" for the default event type
        """

        if not hasattr(self, "event_types"):

            event_types = {}
            table = current.s3db.dvr_case_event_type

            # Active event types
            query = (table.is_inactive == False) & \
                    (table.deleted == False)

            # Excluded event codes
            excluded = current.deployment_settings \
                              .get_dvr_event_registration_exclude_codes()
            if excluded:
                for code in excluded:
                    if "*" in code:
                        query &= (~(table.code.like(code.replace("*", "%"))))
                    else:
                        query &= (table.code != code)

            # Roles required
            sr = current.auth.get_system_roles()
            roles = current.session.s3.roles
            if sr.ADMIN not in roles:
                query &= (table.role_required == None) | \
                         (table.role_required.belongs(roles))

            rows = current.db(query).select(table.id,
                                            table.code,
                                            table.name,
                                            table.is_default,
                                            table.min_interval,
                                            table.max_per_day,
                                            table.comments,
                                            )
            for row in rows:
                event_types[row.id] = row
                if row.is_default:
                    event_types["_default"] = row
            self.event_types = event_types

        return self.event_types

    # -------------------------------------------------------------------------
    def check_intervals(self, person_id, type_id=None):
        """
            Check minimum intervals between consecutive registrations
            of the same event type

            Args:
                person_id: the person record ID
                type_id: check only this event type (rather than all types)

            Returns:
                a dict with blocked event types
                    {type_id: (error_message, blocked_until_datetime)}
        """

        T = current.T

        db = current.db
        s3db = current.s3db

        now = current.request.utcnow
        day_start = now.replace(hour=0,
                                minute=0,
                                second=0,
                                microsecond=0,
                                )
        next_day = day_start + datetime.timedelta(days=1)

        output = {}

        table = s3db.dvr_case_event
        event_type_id = table.type_id

        # Get event types to check
        event_types = self.get_event_types()

        # Check for impermissible combinations
        etable = s3db.dvr_case_event_exclusion
        query = (table.person_id == person_id) & \
                (table.date >= day_start) & \
                (table.deleted == False) & \
                (etable.excluded_by_id == table.type_id) & \
                (etable.deleted == False)
        if type_id and event_types.get(type_id):
            query &= etable.type_id == type_id

        rows = db(query).select(etable.type_id,
                                etable.excluded_by_id,
                                )
        excluded = {}
        for row in rows:
            tid = row.type_id
            if tid in excluded:
                excluded[tid].append(row.excluded_by_id)
            else:
                excluded[tid] = [row.excluded_by_id]

        for tid, excluded_by_ids in excluded.items():
            event_type = event_types.get(tid)
            if not event_type:
                continue
            excluded_by_names = []
            seen = set()
            for excluded_by_id in excluded_by_ids:
                if excluded_by_id in seen:
                    continue
                seen.add(excluded_by_id)
                excluded_by_type = event_types.get(excluded_by_id)
                if not excluded_by_type:
                    continue
                excluded_by_names.append(s3_str(T(excluded_by_type.name)))
            if excluded_by_names:
                msg = T("%(event)s already registered today, not combinable") % \
                        {"event": ", ".join(excluded_by_names)
                         }
                output[tid] = (msg, next_day)

        # Helper function to build event type sub-query
        def type_query(items):
            if len(items) == 1:
                return (event_type_id == items[0])
            elif items:
                return (event_type_id.belongs(set(items)))
            else:
                return None

        # Check maximum occurences per day
        q = None
        if type_id:
            event_type = event_types.get(type_id)
            if event_type and \
               event_type.max_per_day and \
               type_id not in output:
                q = type_query((type_id,))
        else:
            check = [tid for tid, row in event_types.items()
                     if row.max_per_day and \
                        tid != "_default" and tid not in output
                     ]
            q = type_query(check)

        if q is not None:

            # Get number of events per type for this person today
            cnt = table.id.count()
            query = (table.person_id == person_id) & q & \
                    (table.date >= day_start) & \
                    (table.deleted != True)
            rows = db(query).select(event_type_id,
                                    cnt,
                                    groupby = event_type_id,
                                    )

            # Check limit
            for row in rows:

                number = row[cnt]

                tid = row[event_type_id]
                event_type = event_types[tid]
                limit = event_type.max_per_day

                if number >= limit:
                    if number > 1:
                        msg = T("%(event)s already registered %(number)s times today") % \
                                {"event": T(event_type.name),
                                 "number": number,
                                 }
                    else:
                        msg = T("%(event)s already registered today") % \
                                {"event": T(event_type.name),
                                 }
                    output[tid] = (msg, next_day)

        # Check minimum intervals
        q = None
        if type_id:
            event_type = event_types.get(type_id)
            if event_type and \
               event_type.min_interval and \
               type_id not in output:
                q = type_query((type_id,))
        else:
            check = [tid for tid, row in event_types.items()
                     if row.min_interval and \
                        tid != "_default" and tid not in output
                     ]
            q = type_query(check)

        if q is not None:

            # Get the last events for these types for this person
            query = (table.person_id == person_id) & q & \
                    (table.deleted != True)
            timestamp = table.date.max()
            rows = db(query).select(event_type_id,
                                    timestamp,
                                    groupby = event_type_id,
                                    )

            # Check intervals
            represent = table.date.represent
            for row in rows:

                latest = row[timestamp]

                tid = row[event_type_id]
                event_type = event_types[tid]
                interval = event_type.min_interval

                if latest:
                    earliest = latest + datetime.timedelta(hours=interval)
                    if earliest > now:
                        msg = T("%(event)s already registered on %(timestamp)s") % \
                                    {"event": T(event_type.name),
                                     "timestamp": represent(latest),
                                     }
                        output[tid] = (msg, earliest)

        return output

    # -------------------------------------------------------------------------
    # Common methods
    # -------------------------------------------------------------------------
    @classmethod
    def get_person(cls, pe_label):
        """
            Get the person record for a PE Label (or ID code), search only
            for persons with an open DVR case.

            Args:
                pe_label: the PE label (or a scanned ID code as string)
        """

        s3db = current.s3db
        person = None

        # Fields to extract
        fields = ["id",
                  "pe_id",
                  "pe_label",
                  "first_name",
                  "middle_name",
                  "last_name",
                  "date_of_birth",
                  "gender",
                  ]

        data = cls.parse_code(pe_label)

        def person_(label):
            """ Helper function to find a person by pe_label """

            query = (FS("pe_label") == pe_label) & \
                    (FS("dvr_case.id") != None) & \
                    (FS("dvr_case.archived") != True) & \
                    (FS("dvr_case.status_id$is_closed") != True)
            presource = s3db.resource("pr_person",
                                      components = ["dvr_case"],
                                      filter = query,
                                      )
            rows = presource.select(fields,
                                    start = 0,
                                    limit = 1,
                                    as_rows = True,
                                    )
            return rows[0] if rows else None

        pe_label = data["label"].strip()
        if pe_label:
            person = person_(pe_label)
        if person:
            data_match = True
        else:
            family = data.get("family")
            if family:
                # Get the head of family
                person = person_(family)
                data_match = False

        if person:

            first_name, last_name = None, None
            if "first_name" in data:
                first_name = s3_str(data["first_name"]).lower()
                if s3_str(person.first_name).lower() != first_name:
                    data_match = False
            if "last_name" in data:
                last_name = s3_str(data["last_name"]).lower()
                if s3_str(person.last_name).lower() != last_name:
                    data_match = False

            if not data_match:
                # Family member? => search by names/DoB
                ptable = s3db.pr_person
                query = current.auth.s3_accessible_query("read", ptable)

                gtable = s3db.pr_group
                mtable = s3db.pr_group_membership
                otable = mtable.with_alias("family")
                ctable = s3db.dvr_case
                stable = s3db.dvr_case_status

                left = [gtable.on((gtable.id == mtable.group_id) & \
                                  (gtable.group_type == 7)),
                        otable.on((otable.group_id == gtable.id) & \
                                  (otable.person_id != mtable.person_id) & \
                                  (otable.deleted != True)),
                        ptable.on((ptable.id == otable.person_id) & \
                                  (ptable.pe_label != None)),
                        ctable.on((ctable.person_id == otable.person_id) & \
                                  (ctable.archived != True)),
                        stable.on((stable.id == ctable.status_id)),
                        ]
                query &= (mtable.person_id == person.id) & \
                         (ctable.id != None) & \
                         (stable.is_closed != True) & \
                         (mtable.deleted != True) & \
                         (ptable.deleted != True)
                if first_name:
                    query &= (ptable.first_name.lower() == first_name)
                if last_name:
                    query &= (ptable.last_name.lower() == last_name)

                if "date_of_birth" in data:
                    # Include date of birth
                    dob, error = IS_UTC_DATE()(data["date_of_birth"])
                    if not error and dob:
                        query &= (ptable.date_of_birth == dob)

                fields_ = [ptable[fn] for fn in fields]
                rows = current.db(query).select(left=left,
                                                limitby = (0, 2),
                                                *fields_)
                if len(rows) == 1:
                    person = rows[0]

        elif "first_name" in data and "last_name" in data:

            first_name = s3_str(data["first_name"]).lower()
            last_name = s3_str(data["last_name"]).lower()

            # Search by names
            query = (FS("pe_label") != None)
            if first_name:
                query &= (FS("first_name").lower() == first_name)
            if last_name:
                query &= (FS("last_name").lower() == last_name)

            if "date_of_birth" in data:
                # Include date of birth
                dob, error = IS_UTC_DATE()(data["date_of_birth"])
                if not error and dob:
                    query &= (FS("date_of_birth") == dob)

            # Find only open cases
            query &= (FS("dvr_case.id") != None) & \
                     (FS("dvr_case.archived") != True) & \
                     (FS("dvr_case.status_id$is_closed") != True)

            presource = s3db.resource("pr_person",
                                      components = ["dvr_case"],
                                      filter = query,
                                      )
            rows = presource.select(fields,
                                    start = 0,
                                    limit = 2,
                                    as_rows = True,
                                    )
            if len(rows) == 1:
                person = rows[0]

        return person

    # -------------------------------------------------------------------------
    @staticmethod
    def person_details(person):
        """
            Format the person details

            Args:
                person: the person record (Row)
        """

        T = current.T
        settings = current.deployment_settings

        name = s3_fullname(person)
        dob = person.date_of_birth
        if dob:
            dob = S3DateTime.date_represent(dob)
            details = "%s (%s %s)" % (name, T("Date of Birth"), dob)
        else:
            details = name

        output = SPAN(details,
                      _class = "person-details",
                      )

        if settings.get_dvr_event_registration_checkin_warning():

            table = current.s3db.cr_shelter_registration
            if table:
                # Person counts as checked-out when checked-out
                # somewhere and not checked-in somewhere else
                query = (table.person_id == person.id) & \
                        (table.deleted != True)
                cnt = table.id.count()
                status = table.registration_status
                rows = current.db(query).select(status,
                                                cnt,
                                                groupby = status,
                                                )
                checked_in = checked_out = 0
                for row in rows:
                    s = row[status]
                    if s == 2:
                        checked_in = row[cnt]
                    elif s == 3:
                        checked_out = row[cnt]

                if checked_out and not checked_in:
                    output = TAG[""](output,
                                     SPAN(ICON("hint"),
                                          T("not checked-in!"),
                                          _class = "check-in-warning",
                                          ),
                                     )
        return output

    # -------------------------------------------------------------------------
    @staticmethod
    def profile_picture(person):
        """
            Get the profile picture URL for a person

            Args:
                person: the person record (Row)

            Returns:
                the profile picture URL (relative URL), or None if
                no profile picture is available for that person
        """

        try:
            pe_id = person.pe_id
        except AttributeError:
            return None

        table = current.s3db.pr_image
        query = (table.pe_id == pe_id) & \
                (table.profile == True) & \
                (table.deleted != True)
        row = current.db(query).select(table.image, limitby=(0, 1)).first()

        if row:
            return URL(c="default", f="download", args=row.image)
        else:
            return None

    # -------------------------------------------------------------------------
    def get_blocked_events(self, person_id, type_id=None):
        """
            Check minimum intervals for event registration and return
            all currently blocked events

            Args:
                person_id: the person record ID
                type_id: check only this event type (rather than all)

            Returns:
                a dict of blocked event types:
                    {type_id: (reason, blocked_until)}
        """

        check_intervals = self.check_intervals
        if check_intervals and callable(check_intervals):
            blocked = check_intervals(person_id, type_id=type_id)
        else:
            blocked = {}
        return blocked

    # -------------------------------------------------------------------------
    @staticmethod
    def parse_code(code):
        """
            Parse a scanned ID code (QR Code)

            Args:
                code: the scanned ID code (string)

            Returns:
                a dict {"label": the PE label,
                        "first_name": optional first name,
                        "last_name": optional last name,
                        "date_of_birth": optional date of birth,
                        }
        """

        data = {"label": code}

        pattern = current.deployment_settings.get_dvr_id_code_pattern()
        if pattern and code:
            import re
            pattern = re.compile(pattern)
            m = pattern.match(code)
            if m:
                data.update(m.groupdict())

        return data

    # -------------------------------------------------------------------------
    @staticmethod
    def get_zxing_launch_button(event_code):
        """
            Renders the button to launch the Zxing barcode scanner app

            Args:
                event_code: the current event code

            Returns:
                the Zxing launch button
        """

        T = current.T

        # URL template
        template = "zxing://scan/?ret=%s&SCAN_FORMATS=Code 128,UPC_A,EAN_13"

        # Query variables for return URL
        scan_vars = {"label": "{CODE}",
                     "scanner": "zxing",
                     "event": "{EVENT}",
                     }

        # Return URL template
        tmp = URL(args = ["register"],
                  vars = scan_vars,
                  host = True,
                  )
        tmp = str(tmp).replace("&", "%26")

        # Current return URL
        if event_code:
            # must double-escape ampersands:
            scan_vars["event"] = event_code.replace("&", "%2526")
        ret = URL(args = ["register"],
                  vars = scan_vars,
                  host = True,
                  )
        ret = str(ret).replace("&", "%26")

        # Construct button
        return A(T("Scan with Zxing"),
                 _href = template % ret,
                 _class = "small primary button zxing-button",
                 data = {"tmp": template % tmp,
                         },
                 )

    # -------------------------------------------------------------------------
    @staticmethod
    def inject_js(widget_id, options):
        """
            Helper function to inject static JS and instantiate
            the eventRegistration widget

            Args:
                widget_id: the node ID where to instantiate the widget
                options: dict of widget options (JSON-serializable)
        """

        s3 = current.response.s3
        appname = current.request.application

        # Static JS
        scripts = s3.scripts
        if s3.debug:
            script = "/%s/static/scripts/S3/s3.dvr.js" % appname
        else:
            script = "/%s/static/scripts/S3/s3.dvr.min.js" % appname
        scripts.append(script)

        # Instantiate widget
        scripts = s3.jquery_ready
        script = '''$('#%(id)s').eventRegistration(%(options)s)''' % \
                 {"id": widget_id, "options": json.dumps(options)}
        if script not in scripts:
            scripts.append(script)

# =============================================================================
class DVRRegisterPayment(DVRRegisterCaseEvent):
    """ Method handler to register case events """

    # Action to check flag restrictions for
    ACTION = "payment"

    # Do not check minimum intervals for consecutive registrations
    check_intervals = False

    # -------------------------------------------------------------------------
    # Configuration
    # -------------------------------------------------------------------------
    def permitted(self):
        """
            Helper function to check permissions

            Returns:
                True if permitted to use this method, else False
        """

        # User must be permitted to update allowance records
        return self._permitted("update")

    # -------------------------------------------------------------------------
    def get_event_type(self, code=None):
        """
            Get a case event type for an event code

            Args:
                code: the type code (using default event type if None)

            Returns:
                the dvr_case_event_type Row, or None if not found
        """

        # Only one type of event
        return Storage(id=None, code="PAYMENT")

    # -------------------------------------------------------------------------
    def accept(self, r, form, event_type=None):
        """
            Helper function to process the form

            Args:
                r: the CRUDRequest
                form: the FORM
                event_type: the event_type (Row)
        """

        T = current.T
        response = current.response

        formvars = form.vars
        person_id = formvars.person_id

        success = False

        if not formvars.get("permitted"):
            response.error = T("Payment registration not permitted")

        elif person_id:
            # Get payment data from hidden input
            payments = r.post_vars.get("actions")
            if payments:

                # @todo: read date from formvars (utcnow as fallback)
                date = r.utcnow
                comments = formvars.get("comments")

                updated, failed = self.register_payments(person_id,
                                                         payments,
                                                         date = date,
                                                         comments = comments,
                                                         )
                response.confirmation = T("%(number)s payment(s) registered") % \
                                        {"number": updated}
                if failed:
                    response.warning = T("%(number)s payment(s) not found") % \
                                       {"number": failed}
            else:
                response.error = T("No payments specified")
        else:
            response.error = T("Person not found")

        return success

    # -------------------------------------------------------------------------
    def registration_ajax(self, r, **attr):
        """
            Ajax response method, expects a JSON input like:

                {l: the PE label (from the input field),
                 c: boolean to indicate whether to just check
                    the PE label or to register payments
                 d: the payment data (raw data, which payments to update)
                 }

            Args:
                r: the CRUDRequest instance
                attr: controller parameters

            Returns:
                JSON response, structure:

                    {l: the actual PE label (to update the input field),
                     p: the person details,
                     f: [{n: the flag name
                          i: the flag instructions
                          },
                         ...],

                     u: whether there are any actionable data
                     s: whether the action is permitted or not

                     d: {t: time stamp
                         h: payment details (raw data)
                         d: payment details (HTML)
                         }

                     e: form error (for label field)

                     a: error message
                     w: warning message
                     m: success message
                     }
        """

        T = current.T

        # Load JSON data from request body
        s = r.body
        s.seek(0)
        try:
            data = json.load(s)
        except (ValueError, TypeError):
            r.error(400, current.ERROR.BAD_REQUEST)


        # Initialize processing variables
        output = {}
        alert = None
        error = None
        warning = None
        message = None
        permitted = False
        flags = []

        # Identify the person
        pe_label = data.get("l")
        person = self.get_person(pe_label)

        if person is None:
            error = s3_str(T("No person found with this ID number"))

        else:
            # Get flag info
            flag_info = dvr_get_flag_instructions(person.id,
                                                  action = self.ACTION,
                                                  )
            permitted = flag_info["permitted"]

            check = data.get("c")
            if check:
                # Person details
                person_details = self.person_details(person)
                profile_picture = self.profile_picture(person)

                output["p"] = s3_str(person_details)
                output["l"] = person.pe_label
                output["b"] = profile_picture

                info = flag_info["info"]
                for flagname, instructions in info:
                    flags.append({"n": s3_str(T(flagname)),
                                  "i": s3_str(T(instructions)),
                                  })

                if permitted:
                    payments = self.get_payment_data(person.id)
                else:
                    payments = []
                date = S3DateTime.datetime_represent(current.request.utcnow,
                                                     utc = True,
                                                     )
                output["d"] = {"d": s3_str(self.payment_data_represent(payments)),
                               "t": s3_str(date),
                               "h": payments,
                               }
                output["u"] = bool(payments)
            else:
                if not permitted:
                    alert = T("Payment registration not permitted")
                else:
                    # Get payment data from JSON
                    payments = data.get("d")
                    if payments:

                        # @todo: read date from JSON data (utcnow as fallback)
                        date = r.utcnow
                        comments = data.get("c")

                        updated, failed = self.register_payments(
                                                    person.id,
                                                    payments,
                                                    date = date,
                                                    comments = comments,
                                                    )
                        message = T("%(number)s payment(s) registered") % \
                                  {"number": updated}
                        if failed:
                            warning = T("%(number)s payment(s) not found") % \
                                      {"number": failed}
                    else:
                        alert = T("No payments specified")

        # Add messages to output
        if alert:
            output["a"] = s3_str(alert)
        if error:
            output["e"] = s3_str(error)
        if message:
            output["m"] = s3_str(message)
        if warning:
            output["w"] = s3_str(warning)

        # Add flag info to output
        output["s"] = permitted
        output["f"] = flags

        current.response.headers["Content-Type"] = "application/json"
        return json.dumps(output)

    # -------------------------------------------------------------------------
    @classmethod
    def get_form_data(cls, person, formfields, data, hidden, *, permitted=False):
        """
            Helper function to extend the form

            Args:
                person: the person (Row)
                formfields: list of form fields (Field)
                data: the form data (dict)
                hidden: hidden form fields (dict)
                permitted: whether the action is permitted

            Returns:
                tuple (widget_id, submit_label)
        """

        T = current.T

        if person and permitted:
            payments = cls.get_payment_data(person.id)
        else:
            payments = []

        date = S3DateTime.datetime_represent(current.request.utcnow,
                                             utc = True,
                                             )

        # Additional form fields for payments
        formfields.extend([Field("details",
                                 label = T("Pending Payments"),
                                 writable = False,
                                 represent = cls.payment_data_represent,
                                 ),
                           Field("date",
                                 label = T("Payment Date"),
                                 writable = False,
                                 default = date,
                                 ),
                           Field("comments",
                                 label = T("Comments"),
                                 widget = s3_comments_widget,
                                 ),
                           ])

        # Additional data for payments
        data["date"] = s3_str(date)
        data["details"] = payments
        data["comments"] = ""

        # Add payments JSON to hidden form fields, update actionable info
        hidden["actions"] = json.dumps(payments)
        if not payments:
            hidden["actionable"] = "false"

        widget_id = "payment-form"
        submit = current.T("Register")

        return widget_id, submit

    # -------------------------------------------------------------------------
    def get_header(self, event_type=None):
        """
            Helper function to construct the event type header

            Args:
                event_type: the event type (Row)

            Returns:
                dict of view items
        """

        # Simple title, no selector/toggle
        event_type_header = DIV(H4(SPAN(current.T("Allowance Payment"),
                                        _class = "event-type-name",
                                        ),
                                   ),
                                _class = "event-type-header",
                                )

        output = {"event_type": event_type_header,
                  "event_type_selector": "",
                  }

        return output

    # -------------------------------------------------------------------------
    # Class-specific functions
    # -------------------------------------------------------------------------
    @staticmethod
    def get_payment_data(person_id):
        """
            Helper function to extract currently pending allowance
            payments for the person_id.

            Args:
                person_id: the person record ID

            Returns:
                a list of dicts [{i: record_id,
                                  d: date,
                                  c: currency,
                                  a: amount,
                                  }, ...]
        """

        query = (FS("person_id") == person_id) & \
                (FS("status") == 1) & \
                (FS("date") <= current.request.utcnow.date())

        resource = current.s3db.resource("dvr_allowance",
                                         filter = query,
                                         )
        data = resource.select(["id",
                                "date",
                                "currency",
                                "amount",
                                ],
                                orderby = "dvr_allowance.date",
                                represent = True,
                               )

        payments = []
        append = payments.append
        for row in data.rows:
            payment_details = {"r": row["dvr_allowance.id"],
                               "d": row["dvr_allowance.date"],
                               "c": row["dvr_allowance.currency"],
                               "a": row["dvr_allowance.amount"],
                               }
            append(payment_details)

        return payments

    # -------------------------------------------------------------------------
    @staticmethod
    def register_payments(person_id, payments, date=None, comments=None):
        """
            Helper function to register payments

            Args:
                person_id: the person record ID
                payments: the payments as sent from form
                date: the payment date (default utcnow)
                comments: comments for the payments

            Returns:
                tuple (updated, failed), number of records
        """

        if isinstance(payments, str):
            try:
                payments = json.loads(payments)
            except (ValueError, TypeError):
                payments = []

        if not date:
            date = current.request.utcnow

        # Data to write
        data = {"status": 2,
                "paid_on": date,
                }
        if comments:
            data["comments"] = comments

        atable = current.s3db.dvr_allowance

        updated = 0
        failed = 0

        # Customise allowance resource
        r = CRUDRequest("dvr", "allowance",
                        current.request,
                        args = [],
                        get_vars = {},
                        )
        r.customise_resource("dvr_allowance")
        onaccept = current.s3db.onaccept

        db = current.db
        accessible = current.auth.s3_accessible_query("update", atable)
        for payment in payments:
            record_id = payment.get("r")
            query = accessible & \
                    (atable.id == record_id) & \
                    (atable.person_id == person_id) & \
                    (atable.status != 2) & \
                    (atable.deleted != True)
            success = db(query).update(**data)
            if success:
                record = {"id": record_id, "person_id": person_id}
                record.update(data)
                onaccept(atable, record, method="update")
                updated += 1
            else:
                failed += 1

        return updated, failed

    # -------------------------------------------------------------------------
    @staticmethod
    def payment_data_represent(data):
        """
            Representation method for the payment details field

            Args:
                data: the payment data (from get_payment_data)
        """

        if data:
            output = TABLE(_class="payment-details")
            for payment in data:
                details = TR(TD(payment["d"], _class="payment-date"),
                             TD(payment["c"], _class="payment-currency"),
                             TD(payment["a"], _class="payment-amount"),
                             )
                output.append(details)
        else:
            output = current.T("No pending payments")

        return output

# =============================================================================
def dvr_get_flag_instructions(person_id, action=None, organisation_id=None):
    """
        Get handling instructions if flags are set for a person

        Args:
            person_id: the person ID
            action: the action for which instructions are needed:
                    - check-in|check-out|payment|id-check
            organisation_id: check for flags of this organisation

        Returns:
            dict {"permitted": whether the action is permitted
                  "info": list of tuples (flagname, instructions)
                  }
    """

    s3db = current.s3db

    ftable = s3db.dvr_case_flag
    ltable = s3db.dvr_case_flag_case

    join = ltable.on((ltable.flag_id == ftable.id) & \
                     (ltable.person_id == person_id) & \
                     (ltable.deleted == False))

    if not current.deployment_settings.get_dvr_case_flags_org_specific():
        organisation_id = None
    query = (ftable.organisation_id == organisation_id)

    if action == "check-in":
        query &= (ftable.advise_at_check_in == True) | \
                 (ftable.deny_check_in == True)
    elif action == "check-out":
        query &= (ftable.advise_at_check_out == True) | \
                 (ftable.deny_check_out == True)
    elif action == "payment":
        query &= (ftable.advise_at_id_check == True) | \
                 (ftable.allowance_suspended == True)
    else:
        query &= (ftable.advise_at_id_check == True)
    query &= (ftable.deleted == False)

    flags = current.db(query).select(ftable.name,
                                     ftable.deny_check_in,
                                     ftable.deny_check_out,
                                     ftable.allowance_suspended,
                                     ftable.advise_at_check_in,
                                     ftable.advise_at_check_out,
                                     ftable.advise_at_id_check,
                                     ftable.instructions,
                                     join = join,
                                     )

    info = []
    permitted = True
    for flag in flags:
        advise = False
        if action == "check-in":
            if flag.deny_check_in:
                permitted = False
            advise = flag.advise_at_check_in
        elif action == "check-out":
            if flag.deny_check_out:
                permitted = False
            advise = flag.advise_at_check_out
        elif action == "payment":
            if flag.allowance_suspended:
                permitted = False
            advise = flag.advise_at_id_check
        else:
            advise = flag.advise_at_id_check
        if advise:
            instructions = flag.instructions
            if instructions is not None:
                instructions = instructions.strip()
            if not instructions:
                instructions = current.T("No instructions for this flag")
            info.append((flag.name, instructions))

    return {"permitted": permitted,
            "info": info,
            }

# =============================================================================
def dvr_update_last_seen(person_id):
    """
        Helper function for automatic updates of dvr_case.last_seen_on

        Args:
            person_id: the person ID
    """

    db = current.db
    s3db = current.s3db
    settings = current.deployment_settings

    now = current.request.utcnow
    last_seen_on = None

    if not person_id:
        return

    # Get event types that require presence
    ettable = s3db.dvr_case_event_type
    query = (ettable.presence_required == True) & \
            (ettable.deleted == False)
    types = db(query).select(ettable.id, cache=s3db.cache)
    type_ids = set(t.id for t in types)

    # Get the last case event that required presence
    etable = s3db.dvr_case_event
    query = (etable.person_id == person_id) & \
            (etable.type_id.belongs(type_ids)) & \
            (etable.date != None) & \
            (etable.date <= now) & \
            (etable.deleted == False)
    event = db(query).select(etable.date,
                             orderby = ~etable.date,
                             limitby = (0, 1),
                             ).first()
    if event:
        last_seen_on = event.date

    if settings.get_dvr_response_types() and settings.get_dvr_response_use_time():
        # Check consultations for newer entries
        rtable = s3db.dvr_response_action
        ttable = s3db.dvr_response_type
        stable = s3db.dvr_response_status
        join = [ttable.on((ttable.id == rtable.response_type_id) & \
                          (ttable.is_consultation == True)),
                stable.on((stable.id == rtable.status_id) & \
                          (stable.is_closed == True) & \
                          (stable.is_canceled == False))
                ]
        query = (rtable.person_id == person_id) & \
                (rtable.deleted == False)
        if last_seen_on is not None:
            query &= rtable.start_date > last_seen_on
        entry = db(query).select(rtable.start_date,
                                 join = join,
                                 limitby = (0, 1),
                                 orderby = ~rtable.start_date,
                                 ).first()
        if entry:
            last_seen_on = entry.start_date

    # Check site presence events for newer entries
    etable = s3db.org_site_presence_event
    query = (etable.person_id == person_id) & \
            (etable.event_type.belongs("IN", "OUT", "SEEN")) & \
            (etable.date != None) & \
            (etable.deleted == False)
    if last_seen_on is not None:
        query &= etable.date > last_seen_on
    entry = db(query).select(etable.date,
                             orderby = ~etable.date,
                             limitby = (0, 1),
                             ).first()
    if entry:
        last_seen_on = entry.date

    # Case appointments to update last_seen_on?
    if settings.get_dvr_appointments_update_last_seen_on():

        use_time = settings.get_dvr_appointments_use_time()

        # Get appointment types that require presence
        attable = s3db.dvr_case_appointment_type
        query = (attable.presence_required == True) & \
                (attable.deleted == False)
        types = db(query)._select(attable.id)

        # Get last appointment that required presence
        atable = s3db.dvr_case_appointment
        if use_time:
            query = (atable.start_date != None) & \
                    (atable.start_date <= now)
            if last_seen_on is not None:
                query &= (atable.start_date > last_seen_on)
        else:
            query = (atable.date != None) & \
                    (atable.date <= now.date())
            if last_seen_on is not None:
                query &= (atable.date > last_seen_on.date())

        query = (atable.person_id == person_id) & \
                (atable.type_id.belongs(types)) & \
                (atable.status == 4) & \
                query & \
                (atable.deleted == False)
        appointment = db(query).select(atable.date,
                                       atable.start_date,
                                       orderby = (~atable.date, ~atable.start_date),
                                       limitby = (0, 1),
                                       ).first()
        if appointment:
            if use_time:
                date = appointment.start_date
            else:
                date = appointment.date
                # Default to 08:00 local time (...unless that would be in the future)
                try:
                    date = datetime.datetime.combine(date, datetime.time(8, 0, 0))
                except TypeError:
                    pass
                date = min(now, S3DateTime.to_utc(date))
            last_seen_on = date

    # Allowance payments to update last_seen_on?
    if settings.get_dvr_payments_update_last_seen_on():

        atable = s3db.dvr_allowance
        query = (atable.person_id == person_id) & \
                (atable.paid_on != None) & \
                (atable.status == 2) & \
                (atable.deleted == False)
        if last_seen_on is not None:
            query &= atable.paid_on > last_seen_on
        payment = db(query).select(atable.paid_on,
                                   orderby = ~atable.paid_on,
                                   limitby = (0, 1),
                                   ).first()
        if payment:
            last_seen_on = payment.paid_on

    # Update last_seen_on
    ctable = s3db.dvr_case
    query = (ctable.person_id == person_id) & \
            (ctable.archived == False) & \
            (ctable.deleted == False)
    db(query).update(last_seen_on = last_seen_on,
                     # Don't change author stamp for
                     # system-controlled record update:
                     modified_on = ctable.modified_on,
                     modified_by = ctable.modified_by,
                     )

# =============================================================================
def dvr_rheader(r, tabs=None):
    """ DVR module resource headers """

    if r.representation != "html":
        # Resource headers only used in interactive views
        return None

    tablename, record = s3_rheader_resource(r)
    if tablename != r.tablename:
        resource = current.s3db.resource(tablename, id=record.id if record else None)
    else:
        resource = r.resource

    rheader = None
    rheader_fields = []

    if record:
        T = current.T

        if tablename == "pr_person":

            if not tabs:
                tabs = [(T("Basic Details"), None),
                        (T("Identity"), "identity"),
                        (T("Activities"), "case_activity"),
                        ]

            rheader_fields = [[(T("ID"), "pe_label")],
                              ["date_of_birth"],
                              ]
            rheader_title = s3_fullname

        elif tablename == "dvr_case":

            if not tabs:
                tabs = [(T("Basic Details"), None),
                        (T("Activities"), "case_activity"),
                        ]

            rheader_fields = [["status_id"],
                              ]
            rheader_title = "reference"

        elif tablename == "dvr_task":

            if not tabs:
                tabs = [(T("Basic Details"), None),
                        ]

            rheader_fields = [["person_id"],
                              ["status"],
                              ]
            rheader_title = "name"

        elif tablename == "dvr_grant_type":

            if not tabs:
                tabs = [(T("Basic Details"), None),
                        (T("Beneficiaries"), "grant"),
                        ]
            rheader_fields = [["aid_type"],
                              ["granting_entity"],
                              ]
            rheader_title = "name"

        else:
            return None

        rheader = S3ResourceHeader(rheader_fields, tabs, title=rheader_title)
        rheader = rheader(r, table=resource.table, record=record)

    return rheader

# END =========================================================================
