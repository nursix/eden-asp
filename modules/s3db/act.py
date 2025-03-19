"""
    Activity Management

    Copyright: 2024-2024 (c) Sahana Software Foundation

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

__all__ = ("ActivityModel",
           "ActivityBeneficiaryModel",
           "ActivityIssueModel",
           "ActivityTaskModel",
           "ActivityChecklistModel",
           "act_IssueRepresent",
           "act_issue_set_status_opts",
           "act_issue_configure_form",
           "act_task_is_manager",
           "act_task_set_status_opts",
           "act_task_configure_form",
           "act_rheader",
           )

import datetime

from collections import OrderedDict

from gluon import *
from gluon.storage import Storage

from ..core import *

# =============================================================================
class ActivityModel(DataModel):
    """ Data Model for activities of an organisation """

    names = ("act_activity",
             "act_activity_id",
             "act_activity_type",
             )

    def model(self):

        T = current.T
        db = current.db

        s3 = current.response.s3
        crud_strings = s3.crud_strings

        define_table = self.define_table
        configure = self.configure

        # ---------------------------------------------------------------------
        # Activity Type
        #
        tablename = "act_activity_type"
        define_table(tablename,
                     Field("name",
                           label = T("Name"),
                           requires = IS_NOT_EMPTY(),
                           ),
                     Field("code", length=64,
                           label = T("Code"),
                           requires = IS_LENGTH(64, minsize=2),
                           ),
                     Field("obsolete", "boolean",
                           label = T("Obsolete"),
                           default = False,
                           represent = BooleanRepresent(icons=True, colors=True, flag=True),
                           ),
                     CommentsField(),
                     )

        # Table configuration
        configure(tablename,
                  deduplicate = S3Duplicate(primary = ("code",)),
                  )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Add Activity Type"),
            title_display = T("Activity Type"),
            title_list = T("Activity Types"),
            title_update = T("Edit Activity Type"),
            label_list_button = T("List Activity Types"),
            label_delete_button = T("Delete Activity Type"),
            msg_record_created = T("Activity Type added"),
            msg_record_modified = T("Activity Type updated"),
            msg_record_deleted = T("Activity Type deleted"),
            msg_list_empty = T("No Activity Types currently defined"),
            )

        # Field Template
        represent = S3Represent(lookup="act_activity_type")
        activity_type_id = FieldTemplate("type_id", "reference %s" % tablename,
                                         label = T("Activity Type"),
                                         ondelete = "RESTRICT",
                                         represent = represent,
                                         requires = IS_EMPTY_OR(
                                                        IS_ONE_OF(db, "%s.id" % tablename,
                                                                  represent,
                                                                  filterby = "obsolete",
                                                                  filter_opts = (False,),
                                                                  )),
                                         sortby = "name",
                                         )

        # ---------------------------------------------------------------------
        # Activities
        #
        tablename = "act_activity"
        define_table(tablename,
                     self.super_link("doc_id", "doc_entity"),
                     self.org_organisation_id(comment=False),
                     activity_type_id(empty=False),
                     Field("name",
                           label = T("Title"),
                           requires = IS_NOT_EMPTY(),
                           ),
                     # TODO Description?
                     DateField(label = T("Start Date"),
                               empty = False,
                               default = "now",
                               set_min = "#act_activity_end_date",
                               ),
                     # TODO Frequency (single occasion, regular activity)
                     DateField("end_date",
                               label = T("End Date"),
                               set_max = "#act_activity_date",
                               ),
                     # TODO Time formula? Separate event table?
                     Field("time_info",
                           label = T("Time"),
                           represent = lambda v, row=None: v if v else "-",
                           ),
                     # TODO Alternatives: location_id, site_id?
                     Field("place",
                           label = T("Place"),
                           represent = lambda v, row=None: v if v else "-",
                           ),
                     # TODO Total Effort (Hours)
                     # TODO Total Costs + Currency
                     # TODO Link to financing sector
                     # TODO Link to financing project/program?
                     CommentsField(),
                     )

        # Components
        self.add_components(tablename,
                            act_beneficiary = "activity_id",
                            )

        # Filter widgets
        # TODO Custom DateFilter (needs special interval filter)
        filter_widgets = [TextFilter(["name",
                                      "place",
                                      "time_info",
                                      "comments",
                                      ],
                                     label = T("Search"),
                                     ),
                          OptionsFilter("type_id"),
                          ]

        # Table configuration
        configure(tablename,
                  filter_widgets = filter_widgets,
                  onvalidation = self.activity_onvalidation,
                  super_entity = ("doc_entity",)
                  )

        # Field Template
        # TODO represent including date? place? time_info? sector?
        represent = S3Represent(lookup="act_activity")
        activity_id = FieldTemplate("activity_id", "reference %s" % tablename,
                                    label = T("Activity"),
                                    ondelete = "RESTRICT",
                                    represent = represent,
                                    requires = IS_EMPTY_OR(
                                                IS_ONE_OF(db, "%s.id" % tablename,
                                                          represent,
                                                          )),
                                    sortby = "name",
                                    )

        # CRUD Strings
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

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return {"act_activity_id": activity_id,
                }

    # -------------------------------------------------------------------------
    def defaults(self):
        """ Safe defaults for names in case the module is disabled """

        return {"act_activity_id": FieldTemplate.dummy("activity_id"),
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def activity_onvalidation(form):
        """
            Form validation of activity
                - Date interval must include all registered beneficiaries
        """

        T = current.T
        db = current.db
        s3db = current.s3db

        table = s3db.act_activity

        record_id = get_form_record_id(form)
        if record_id:
            fields = ["date", "end_date"]
            data = get_form_record_data(form, table, fields)

            btable = s3db.act_beneficiary
            base = (btable.activity_id == record_id) & \
                   (btable.deleted == False)

            start = data.get("date")
            if start:
                earliest = datetime.datetime.combine(start, datetime.time(0))
                query = base & (btable.date < earliest)
                if db(query).select(btable.id, limitby=(0, 1)).first():
                    form.errors.date = T("There are beneficiaries registered before that date")

            end = data.get("end_date")
            if end:
                latest = datetime.datetime.combine(end + datetime.timedelta(days=1), datetime.time(0))
                query = base & (btable.date >= latest)
                if db(query).select(btable.id, limitby=(0, 1)).first():
                    form.errors.end_date = T("There are beneficiaries registered after that date")

# =============================================================================
class ActivityBeneficiaryModel(DataModel):
    """ Data Model to record beneficiaries of activities """

    names = ("act_beneficiary",
             )

    def model(self):

        T = current.T

        s3 = current.response.s3
        crud_strings = s3.crud_strings

        # ---------------------------------------------------------------------
        # Beneficiary (targeted by an activity at a certain date+time)
        #
        tablename = "act_beneficiary"
        self.define_table(tablename,
                          self.pr_person_id(label = T("Beneficiary"),
                                            empty = False,
                                            ondelete = "CASCADE",
                                            ),
                          self.act_activity_id(empty=False,
                                               ),
                          DateTimeField(default = "now",
                                        empty = False,
                                        future = 0,
                                        ),
                          CommentsField(),
                          )

        # List fields
        list_fields = ["activity_id",
                       "date",
                       "person_id",
                       "comments",
                       ]

        # Table configuration
        self.configure(tablename,
                       list_fields = list_fields,
                       orderby = "%s.date desc" % tablename,
                       onvalidation = self.beneficiary_onvalidation,
                       )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Add Beneficiary"),
            title_display = T("Beneficiary Details"),
            title_list = T("Beneficiaries"),
            title_update = T("Edit Beneficiary"),
            label_list_button = T("List Beneficiaries"),
            label_delete_button = T("Delete Beneficiary"),
            msg_record_created = T("Beneficiary added"),
            msg_record_modified = T("Beneficiary updated"),
            msg_record_deleted = T("Beneficiary deleted"),
            msg_list_empty = T("No Beneficiaries currently registered"),
            )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def beneficiary_onvalidation(form):
        """
            Form validation of beneficiary
                - Date must match activity date interval
        """

        T = current.T
        db = current.db
        s3db = current.s3db

        table = s3db.act_beneficiary

        fields = ["activity_id", "date"]
        data = get_form_record_data(form, table, fields)

        date = data.get("date")
        activity_id = data.get("activity_id")

        if date and activity_id:
            # Verify that date matches activity date interval
            error = None
            date = date.date()
            atable = s3db.act_activity
            query = (atable.id == activity_id)
            activity = db(query).select(atable.date,
                                        atable.end_date,
                                        limitby = (0, 1),
                                        ).first()
            if activity:
                start, end = activity.date, activity.end_date
                if start is not None and start > date:
                    error = T("Activity started only after that date")
                elif end is not None and end < date:
                    error = T("Activity ended before that date")
            if error:
                form.errors.date = error

# =============================================================================
class ActivityIssueModel(DataModel):
    """
        Data Model for Issue Reports (e.g. when managing sites or assets)
    """

    names = ("act_issue",
             "act_issue_id",
             "act_issue_status_opts",
             "act_issue_resolution_opts",
             )

    def model(self):

        T = current.T
        db = current.db

        s3 = current.response.s3
        crud_strings = s3.crud_strings

        define_table = self.define_table
        configure = self.configure

        # ---------------------------------------------------------------------
        # Issue status
        #
        issue_status = (("NEW", T("New")),
                        ("PLANNED", T("Work Planned")),
                        ("PROGRESS", T("In Progress")),
                        ("REVIEW", T("Review")),
                        ("ONHOLD", T("On Hold")),
                        ("CLOSED", T("Closed##status")),
                        )

        status_represent = S3PriorityRepresent(issue_status,
                                               {"NEW": "lightblue",
                                                "PLANNED": "blue",
                                                "PROGRESS": "lightgreen",
                                                "REVIEW": "amber",
                                                "ONHOLD": "red",
                                                "CLOSED": "green",
                                                }).represent

        # ---------------------------------------------------------------------
        # Issue resolution
        #
        issue_resolution = (("PENDING", "-"),
                            ("DEFER", T("No Action")),
                            ("RESOLVED", T("Resolved")),
                            ("OBSOLETE", T("Obsolete")),
                            ("N/A", T("Not Actionable")),
                            ("DUPLICATE", T("Duplicate")),
                            ("INVALID", T("Invalid")),
                            )

        # ---------------------------------------------------------------------
        # Issue
        #
        tablename = "act_issue"
        define_table(tablename,
                     DateTimeField(
                         default = "now",
                         writable = False,
                         ),
                     self.org_organisation_id(comment=None),
                     self.org_site_id(),
                     # TODO asset_id?
                     # TODO priority
                     Field("name",
                           label = T("Subject"),
                           requires = IS_NOT_EMPTY(),
                           ),
                     CommentsField("description",
                                   label = T("Details"),
                                   comment = None,
                                   ),
                     Field("status",
                           label = T("Status"),
                           default = "NEW",
                           requires = IS_IN_SET(issue_status, zero=None, sort=False),
                           represent = status_represent,
                           ),
                     Field("resolution",
                           label = T("Resolution#issue"),
                           default = "PENDING",
                           requires = IS_IN_SET(issue_resolution, zero=None, sort=False),
                           represent = represent_option(dict(issue_resolution)),
                           ),
                     CommentsField(),
                     )

        # Components
        self.add_components(tablename,
                            act_task = "issue_id",
                            )

        # Table configuration
        configure(tablename,
                  onvalidation = self.issue_onvalidation,
                  onaccept = self.issue_onaccept,
                  orderby = "%s.date desc" % tablename,
                  realm_components = ["task",],
                  update_realm = True,
                  )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Issue Report"),
            title_display = T("Issue Report"),
            title_list = T("Issue Reports"),
            title_update = T("Edit Issue Report"),
            label_list_button = T("List Issue Reports"),
            label_delete_button = T("Delete Issue Report"),
            msg_record_created = T("Issue Report added"),
            msg_record_modified = T("Issue Report updated"),
            msg_record_deleted = T("Issue Report deleted"),
            msg_list_empty = T("No Issue Reports currently registered"),
            )

        # Field Template
        represent = act_IssueRepresent()
        issue_id = FieldTemplate("issue_id", "reference %s" % tablename,
                                 label = T("Issue"),
                                 #ondelete = "RESTRICT",
                                 represent = represent,
                                 requires = IS_EMPTY_OR(
                                                IS_ONE_OF(db, "%s.id" % tablename,
                                                          represent,
                                                          )),
                                 #sortby = "name",
                                 )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return {"act_issue_id": issue_id,
                "act_issue_status_opts": issue_status,
                "act_issue_resolution_opts": issue_resolution,
                }

    # -------------------------------------------------------------------------
    def defaults(self):
        """ Safe defaults for names in case the module is disabled """

        return {"act_issue_id": FieldTemplate.dummy("issue_id"),
                "act_issue_status_opts": [],
                "act_issue_resolution_opts": [],
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def issue_onvalidation(form):
        """
            Form validation for issues
            - closing an issue requires a resolution
        """

        T = current.T
        table = current.s3db.act_issue

        data = get_form_record_data(form, table, ["status", "resolution"])

        status = data.get("status")
        resolution = data.get("resolution")

        if status == "CLOSED" and resolution in (None, "PENDING"):
            form.errors.resolution = T("Resolution required##issue")

    # -------------------------------------------------------------------------
    @staticmethod
    def issue_onaccept(form):
        """
            Onaccept-routine for issues
            - update tasks when issue is closed or put on hold
            - otherwise, update issue status from statuses of related tasks
            - remove the resolution when the issue is not closed
        """

        db = current.db
        s3db = current.s3db

        record_id = get_form_record_id(form)
        if not record_id:
            return

        # Get the current record
        table = s3db.act_issue
        record = db(table.id == record_id).select(table.id,
                                                  table.organisation_id,
                                                  table.site_id,
                                                  table.status,
                                                  limitby = (0, 1),
                                                  ).first()
        if not record:
            return

        update = {}
        if record.status != "CLOSED":
            update["resolution"] = "PENDING"

        ttable = s3db.act_task
        related_tasks = (ttable.issue_id == record_id)

        # Update organisation/site ID in all related tasks
        if record.organisation_id:
            query = (ttable.organisation_id == None) | (ttable.organisation_id != record.organisation_id)
        else:
            query = (ttable.organisation_id != None)
        if record.site_id:
            query |= (ttable.site_id == None) | (ttable.site_id != record.site_id)
        else:
            query |= (ttable.site_id != None)
        query = related_tasks & query & (ttable.deleted == False)
        db(query).update(organisation_id = record.organisation_id,
                         site_id = record.site_id,
                         )

        # Status update
        status = record.status
        if status in ("ONHOLD", "CLOSED"):
            # Update status of all related tasks
            # TODO refactor for task status history
            task_open = ("PENDING", "STARTED", "FEEDBACK")
            new_status = "ONHOLD" if status == "ONHOLD" else "OBSOLETE"
            query = related_tasks & \
                    (ttable.status.belongs(task_open)) & \
                    (ttable.deleted == False)
            db(query).update(status=new_status)
        else:
            # Update issue status based on task status
            act_issue_update_status(record_id)

        # TODO status history
        # - if status has changed, add history entry
        # - record previous status

        # Update record, if required
        if update:
            record.update_record(**update)

# =============================================================================
class ActivityTaskModel(DataModel):
    """
        Model to track work orders in connection with issue reports
    """


    names = ("act_task",
             "act_task_status_opts",
             )

    def model(self):

        T = current.T
        # db = current.db

        s3 = current.response.s3
        crud_strings = s3.crud_strings

        define_table = self.define_table
        configure = self.configure

        # ---------------------------------------------------------------------
        # Task Status
        #
        task_status = (("PENDING", T("Pending")),
                       ("STARTED", T("Started")),
                       ("FEEDBACK", T("Feedback")),
                       ("ONHOLD", T("On Hold")),
                       ("DONE", T("Done")),
                       ("CANCELED", T("Canceled")),
                       ("OBSOLETE", T("Obsolete")),
                       )

        status_represent = S3PriorityRepresent(task_status,
                                               {"PENDING": "lightblue",
                                                "STARTED": "lightgreen",
                                                "FEEDBACK": "amber",
                                                "DONE": "green",
                                                "ONHOLD": "red",
                                                "CANCELED": "black",
                                                "OBSOLETE": "grey",
                                                }).represent

        # ---------------------------------------------------------------------
        # Task
        #
        tablename = "act_task"
        define_table(tablename,
                     DateTimeField(
                         default = "now",
                         writable = False,
                         ),
                     self.org_organisation_id(comment=None),
                     self.org_site_id(),
                     # TODO asset_id?
                     self.act_issue_id(
                         ondelete = "RESTRICT",
                         writable = False,
                         ),
                     Field("name",
                           label = T("Task"),
                           requires = IS_NOT_EMPTY(),
                           ),
                     CommentsField("details",
                                   label = T("Instructions"),
                                   comment = None,
                                   ),
                     Field("status",
                           default = "NEW",
                           label = T("Status"),
                           requires = IS_IN_SET(task_status, zero=None, sort=False),
                           represent = status_represent,
                           ),
                     self.hrm_human_resource_id(),
                     CommentsField(),
                     )

        # TODO Components

        # List fields (on tab of issue)
        list_fields = ["date",
                       "name",
                       "status",
                       "human_resource_id",
                       "comments",
                       ]

        # Filter widgets
        # TODO alter options for status filter on my_open_tasks
        filter_widgets = [TextFilter(["name",
                                      # "details",
                                      ],
                                     label = T("Search"),
                                     ),
                          OptionsFilter("status",
                                        options = OrderedDict(task_status),
                                        default = ["PENDING", "STARTED", "FEEDBACK", "ONHOLD"],
                                        cols = 4,
                                        orientation = "rows",
                                        sort = False,
                                        ),
                          DateFilter("date",
                                     hidden = True,
                                     ),
                          ]

        # Table configuration
        configure(tablename,
                  deletable = False,
                  filter_widgets = filter_widgets,
                  list_fields = list_fields,
                  onaccept = self.task_onaccept,
                  ondelete = self.task_ondelete,
                  orderby = "%s.date desc" % tablename,
                  )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Work Order"),
            title_display = T("Work Order"),
            title_list = T("Work Orders"),
            title_update = T("Edit Work Order"),
            label_list_button = T("List Work Orders"),
            label_delete_button = T("Delete Work Order"),
            msg_record_created = T("Work Order added"),
            msg_record_modified = T("Work Order updated"),
            msg_record_deleted = T("Work Order deleted"),
            msg_list_empty = T("No Work Orders currently registered"),
            )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return {"act_task_status_opts": task_status,
                }

    # -------------------------------------------------------------------------
    def defaults(self):
        """ Safe defaults for names in case the module is disabled """

        return {"act_task_status_opts": [],
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def task_onaccept(form):
        """
            Onaccept-routine for tasks
            - inherit organisation/site IDs from issue
            - update issue status

            Args:
                form: the FORM
        """

        db = current.db
        s3db = current.s3db

        # Get the record ID
        record_id = get_form_record_id(form)
        if not record_id:
            return

        # Get the current record data
        table = s3db.act_task
        record = db(table.id == record_id).select(table.id,
                                                  table.issue_id,
                                                  table.organisation_id,
                                                  table.site_id,
                                                  limitby = (0, 1),
                                                  ).first()
        if not record:
            return

        update = {}

        issue_id = record.issue_id
        if issue_id:
            itable = s3db.act_issue
            issue = db(itable.id == issue_id).select(itable.id,
                                                     itable.organisation_id,
                                                     itable.site_id,
                                                     limitby = (0, 1),
                                                     ).first()
            for fn in ("organisation_id", "site_id"):
                if record[fn] != issue[fn]:
                    update[fn] = issue[fn]

            # Update the issue status
            # TODO refactor for issue status history
            act_issue_update_status(issue_id)

        # TODO status history
        # - if status has changed, write a history entry
        # - record last status

        if update:
            record.update_record(**update)

    # -------------------------------------------------------------------------
    @staticmethod
    def task_ondelete(row):
        """
            On-delete actions for tasks:
            - update status of context issue
        """

        if row.issue_id:
            act_issue_update_status(row.issue_id)

# =============================================================================
class ActivityChecklistModel(DataModel):
    """
        Model for checklists, for use in work orders
    """

    # TODO implement
    pass

# =============================================================================
class act_IssueRepresent(S3Represent):
    """ Representation of Issues """

    def __init__(self,
                 full_text=False,
                 show_link=True,
                 ):

        super().__init__(lookup="act_issue", show_link=show_link)

        self.full_text = full_text

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

        fields = [table.id, table.date, table.name]
        if self.full_text:
            fields.append(table.description)

        rows = db(query).select(*fields, limitby=(0, count))
        self.queries += 1

        return rows

    # -------------------------------------------------------------------------
    def represent_row(self, row):
        """
            Represent a row

            Args:
                row: the Row
        """

        table = self.table

        date = SPAN(table.date.represent(row.date), _class="issue-date")

        subject = row.name
        if self.show_link:
            if not current.auth.permission.has_permission("read", c="act", f="issue"):
                self.show_link = False
        if self.show_link:
            subject = A(subject, _href=URL(c="act", f="issue", args=[row.id]))

        if self.full_text:
            issue_repr = DIV(H4(date, subject), _class="issue-full")

            description = row.description
            if description:
                description = s3_text_represent(description)
                description.add_class("issue-description")
                issue_repr.append(description)
        else:
            issue_repr = DIV(date, subject, _class="issue-brief")

        return issue_repr

    # -------------------------------------------------------------------------
    def link(self, k, v, row=None):

        return v

# =============================================================================
def act_configure_org_site(table, record_id, site_type=None, hide_single_choice=True):
    """
        Configure organisation/site selection for act_issue or act_task

        Args:
            table: the target Table (act_issue or act_task)
            record_id: the current record_id
            site_type: the tablename of the selectable sites (e.g. "cr_shelter")
            hide_single_choice: whether to hide selectors when there only is
                                a single choice
    """

    from s3dal import original_tablename
    tablename = original_tablename(table)

    db = current.db
    s3db = current.s3db
    auth = current.auth

    s3 = current.response.s3

    # Get the organisation the user is permitted to create records in this table for
    otable = s3db.org_organisation
    permitted_realms = auth.permission.permitted_realms(tablename, "create")
    query = (otable.deleted == False)
    if permitted_realms is not None:
        query = (otable.pe_id.belongs(permitted_realms)) & query
    orgs = db(query).select(otable.id)
    organisation_ids = [o.id for o in orgs]

    # Configure organisation_id
    field = table.organisation_id
    dbset = db(otable.id.belongs(organisation_ids))
    field.requires = IS_ONE_OF(dbset, "org_organisation.id", field.represent)
    if len(organisation_ids) > 1:
        # Multiple choices => expose selector
        field.readable = field.writable = True
    else:
        # No or single permitted organisation => default + set read-only
        field.default = organisation_ids[0] if organisation_ids else None
        field.readable = not hide_single_choice
        field.writable = False

    # Configure site_id
    field = table.site_id
    stable = s3db.table(site_type) if site_type else None
    if stable:
        # Check if there are no, one or multiple sites managed
        # by the permitted organisations
        query = (stable.organisation_id != None) & \
                (stable.organisation_id.belongs(organisation_ids))
        sites = db(query).select(stable.site_id, limitby=(0, 2))

        # Configure requires to match this dbset
        field.requires = IS_EMPTY_OR(
                            IS_ONE_OF(db(query), "%s.site_id" % site_type,
                                      field.represent,
                                      ))
        if not len(sites):
            # No selectable sites at all
            field.default = None
            field.readable = field.writable = False
        elif len(organisation_ids) > 1:
            # Multiple organisations => configure filterOptionsS3
            prefix, name = site_type.split("_", 1)
            script = '''
$.filterOptionsS3({
    'trigger':'organisation_id',
    'target':'site_id',
    'lookupPrefix':'%s',
    'lookupResource':'%s',
    'lookupField': 'site_id',
    'optional': true
})''' % (prefix, name)
            if script not in s3.jquery_ready:
                s3.jquery_ready.append(script)
            field.readable = field.writable = True
        elif len(sites) == 1:
            # Single site => default + set read-only
            field.default = sites.first().site_id
            field.readable = not hide_single_choice
            field.writable = False
        else:
            # Multiple sites for this organisation => expose selector
            field.readable = field.writable = True
    else:
        # Site not used (i.e. site_type is either None or invalid)
        field.default = None
        field.readable = field.writable = False

    # Limit human_resource_id too, if present
    if "human_resource_id" in table.fields:

        field = table.human_resource_id
        htable = s3db.hrm_human_resource
        if len(organisation_ids) == 1:
            # Limit to staff of this organisation
            dbset = db(htable.organisation_id == organisation_ids[0])
        elif not organisation_ids:
            # Can't set or change staff assignment
            field.writable = False
        else:
            # Configure filterOptionsS3
            dbset = db(htable.organisation_id.belongs(organisation_ids))
            script = '''
$.filterOptionsS3({
    'trigger':'organisation_id',
    'target':'human_resource_id',
    'lookupPrefix':'hrm',
    'lookupResource':'human_resource',
    'fncRepresent':function(record){return record.person_id;},
    'optional': true
})'''
            if script not in s3.jquery_ready:
                s3.jquery_ready.append(script)

        field.requires = IS_EMPTY_OR(
                            IS_ONE_OF(dbset, "hrm_human_resource.id",
                                      field.represent,
                                      ))

# =============================================================================
def act_issue_set_status_opts(table, issue_id, record=None):
    """
        Configures the selectable status options for an issue depending
        on its current status

        Args:
            table: the act_issue table (or aliased pendant)
            issue_id: the issue ID
            record: the act_issue record, if available (must contain status)

        Returns:
            the selectable options (as ordered tuple of option tuples)
    """

    db = current.db
    s3db = current.s3db

    field = table.status

    if not record and issue_id:
        record = db(table.id==issue_id).select(table.status,
                                               limitby = (0, 1),
                                               ).first()

    status_opts = s3db.act_issue_status_opts
    if record:
        status = record.status
        if status == "CLOSED":
            # Cannot change status, except by updating tasks
            field.writable = False
        else:
            # Can change to ONHOLD|CLOSED from any status
            selectable = {"ONHOLD", "CLOSED"}
            selectable.add(status)
            status_opts = {k: v for k, v in status_opts if k in selectable}
    else:
        # New issues always have status NEW
        field.default = "NEW"
        field.writable = False

    field.requires = IS_IN_SET(status_opts, zero=None, sort=False)

    return status_opts

# =============================================================================
def act_issue_configure_form(table, issue_id, issue=None, site_type=None, hide_single_choice=True):
    """
        Configure the issue form

        Args:
            table: the Table (act_issue)
            issue_id: the issue ID (can be None when creating a new issue)
            issue: the issue Row (must contain status)
            site_type: the tablename of the selectable sites
            hide_single_choice: hide organisation/site selectors when there is only
                                one choice
    """

    db = current.db
    # s3db = current.s3db

    if not issue and issue_id:
        # Look up the issue
        issue = db(table.id == issue_id).select(table.id,
                                                table.status,
                                                limitby = (0, 1),
                                                ).first()

    # Configure organisation_id/site_id choices
    act_configure_org_site(table,
                           issue_id,
                           site_type = site_type,
                           hide_single_choice = hide_single_choice,
                           )

    # Configure status options
    act_issue_set_status_opts(table, issue_id, record=issue)

    # Configure other fields
    if not act_task_is_manager():
        readonly = ("status", "resolution")
        status = issue.status if issue else "NEW"
        if status != "NEW":
            readonly += ("organisation_id", "site_id", "name", "description")
        if status == "CLOSED":
            readonly += ("comments",)
        for fn in readonly:
            field = table[fn]
            field.writable = False
            field.comment = None

# =============================================================================
def act_issue_update_status(issue_id):
    """
        Updates the status of an issue depending on the statuses of
        any related tasks; to be called onaccept

        Args:
            issue_id: the issue ID
    """

    db = current.db
    s3db = current.s3db

    # Look up the current issue status
    itable = s3db.act_issue
    query = (itable.id == issue_id) & (itable.deleted == False)
    issue = db(query).select(itable.id,
                             itable.status,
                             limitby = (0, 1),
                             ).first()
    if not issue:
        return

    ttable = s3db.act_task
    query = (ttable.issue_id == issue_id) & (ttable.deleted == False)
    rows = db(query).select(ttable.status, distinct=True)
    task_status = {row.status for row in rows}

    # NOTE new_issue_status cannot be CLOSED (closing requires a resolution)
    if "STARTED" in task_status:
        new_issue_status = "PROGRESS"
    elif "PENDING" in task_status:
        new_issue_status = "PLANNED"
    elif "ONHOLD" in task_status:
        new_issue_status = "ONHOLD"
    elif issue.status != "CLOSED":
        new_issue_status = "REVIEW" if len(rows) else "NEW"

    if issue.status != new_issue_status:
        # TODO set status date, and possibly previous status
        issue.update_record(status = new_issue_status,
                            resolution = None,
                            )

# =============================================================================
def act_task_is_manager():
    """
        Checks whether the current user can manage issues/tasks

        Returns:
            boolean
    """

    # TODO make configurable in settings
    is_manager = current.auth.s3_has_permission("create", "act_task")

    return is_manager

# =============================================================================
def act_task_set_status_opts(table, task_id, record=None):
    """
        Configures the selectable status options for a task, depending
        on its current status

        Args:
            table: the act_task table (or aliased pendant)
            task_id: the task ID
            record: the task record, if available (must contain status)

        Returns:
            the selectable options (as ordered tuple of option tuples)
    """

    db = current.db
    s3db = current.s3db

    field = table.status

    all_statuses = s3db.act_task_status_opts
    if not task_id and not record:
        # Set default status for new records
        status_opts = all_statuses
        field.default = "PENDING"
        field.writable = False

    else:
        # Is the user a task manager?
        is_manager = act_task_is_manager()

        # Get the current record status
        if not record:
            query = (table.id == task_id) & \
                    (table.deleted == False)
            record = db(query).select(field, limitby=(0, 1)).first()
        status = record[field] if record else None

        # Determine the next status options
        actionable = ("PENDING", "STARTED", "FEEDBACK")
        closed = ("DONE", "CANCELED", "OBSOLETE")

        if status in actionable or status not in dict(all_statuses):
            if is_manager:
                next_status = None # any status
            else:
                next_status = actionable + ("DONE",)
        elif is_manager and status in ("ONHOLD",) + closed:
            next_status = ("PENDING", "ONHOLD") + closed
        else:
            next_status = (status,)
            field.writable = False

        if next_status:
            status_opts = [(k, v) for k, v in all_statuses if k in next_status]
        else:
            status_opts = all_statuses

    field.requires = IS_IN_SET(status_opts, zero=None, sort=False)
    return status_opts

# =============================================================================
def act_task_configure_form(table, task_id, task=None, issue=None, site_type=None, hide_single_choice=True):
    """
        Configure the act_task form

        Args:
            table: the Table (act_task, or aliased instance)
            task_id: the task ID, if known
            task: the task Row (must contain issue_id and status)
            issue: the context issue Row, if on component tab
                   (must contain organisation_id, site_id and status)
            site_type: the tablename of the selectable sites (e.g. "cr_shelter")
            hide_single_choice: hide org/site selectors if there is only a single choice
    """

    db = current.db
    s3db = current.s3db

    on_tab = bool(issue)

    if not task and task_id:
        # Look up the task
        task = db(table.id == task_id).select(table.id,
                                              table.issue_id,
                                              table.status,
                                              limitby = (0, 1),
                                              ).first()

    if not issue and task and task.issue_id:
        # Look up the context issue
        itable = s3db.act_issue
        issue = db(itable.id == task.issue_id).select(itable.id,
                                                      itable.organisation_id,
                                                      itable.site_id,
                                                      itable.status,
                                                      limitby = (0, 1),
                                                      ).first()

    # Configure org/site/staff selectors
    if issue:
        # Set read-only + hide on tab
        for fn in ("organisation_id", "site_id"):
            field = table[fn]
            if on_tab:
                field.readable = False
            field.writable = False

        organisation_id = issue.organisation_id

        # Filter human_resource_id
        htable = s3db.hrm_human_resource
        dbset = db(htable.organisation_id == issue.organisation_id)
        field = table.human_resource_id
        field.requires = IS_EMPTY_OR(
                            IS_ONE_OF(dbset, "hrm_human_resource.id",
                                      field.represent,
                                      ))
        field.readable = field.writable = bool(organisation_id)
    else:
        act_configure_org_site(table,
                               task_id,
                               site_type = site_type,
                               hide_single_choice = hide_single_choice,
                               )

    # Configure status selector
    act_task_set_status_opts(table, task_id, record=task)

    # Configure other fields
    if on_tab or not issue:
        # Hide issue_id
        field = table.issue_id
        field.readable = field.writable = False
    if task:
        if act_task_is_manager():
            if task.status != "PENDING":
                table.name.writable = False
            if task.status not in ("PENDING", "FEEDBACK", "ONHOLD"):
                table.details.writable = False
                table.human_resource_id.writable = False
        else:
            for fn in ("name", "details", "human_resource_id"):
                field = table[fn]
                field.writable = False

# =============================================================================
def act_rheader(r, tabs=None):
    """ ACT resource headers """

    if r.representation != "html":
        # Resource headers only used in interactive views
        return None

    tablename, record = s3_rheader_resource(r)
    if tablename != r.tablename:
        resource = current.s3db.resource(tablename, id=record.id)
    else:
        resource = r.resource

    rheader = None
    rheader_fields = []

    if record:

        T = current.T

        if tablename == "act_activity":
            if not tabs:
                tabs = [(T("Basic Details"), None),
                        (T("Beneficiaries"), "beneficiary"),
                        (T("Documents"), "document"),
                        ]
            rheader_fields = [["type_id", "date"],
                              ["place"],
                              ["time_info"],
                              ]
            rheader_title = "name"

            rheader = S3ResourceHeader(rheader_fields, tabs, title=rheader_title)
            rheader = rheader(r, table=resource.table, record=record)

        elif tablename == "act_issue":
            if not tabs:
                tabs = [(T("Basic Details"), None),
                        (T("Work Orders"), "task"),
                        ]

            rheader_fields = [["date", "organisation_id"],
                              ["status"],
                              ["resolution"],
                              ]
            rheader_title = "name"


            rheader = S3ResourceHeader(rheader_fields, tabs, title=rheader_title)
            rheader = rheader(r, table=resource.table, record=record)

    return rheader

# END =========================================================================
