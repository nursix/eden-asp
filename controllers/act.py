"""
    Activity Management - Controllers
"""

module = request.controller
resourcename = request.function

if not settings.has_module(module):
    raise HTTP(404, body="Module disabled: %s" % module)

# =============================================================================
def index():
    """ Module's Home Page """

    return s3db.cms_index(module, alt_function="index_alt")

# -----------------------------------------------------------------------------
def index_alt():
    """
        Module homepage for non-Admin users when no CMS content found
    """

    # Just redirect to the list of activities
    s3_redirect_default(URL(f="activity"))

# =============================================================================
def activity_type():
    """ Activity Types: CRUD Controller """

    return crud_controller()

# -----------------------------------------------------------------------------
def activity():
    """ Activities: CRUD Controller """

    def prep(r):
        record = r.record
        if record:
            type_id = record.type_id
            if type_id:
                # Allow current type and all non-obsolete types
                ttable = s3db.act_activity_type
                dbset = db((ttable.id == type_id) | (ttable.obsolete == False))
                table = r.resource.table
                field = table.type_id
                field.requires = IS_ONE_OF(dbset, "act_activity_type.id",
                                           field.represent,
                                           )
        return True
    s3.prep = prep

    return crud_controller(rheader=s3db.act_rheader)

# =============================================================================
# Issue reports and work orders
#
def issue():
    """ Issue Reports: CRUD Controller """

    def prep(r):

        resource = r.resource
        record = r.record

        if not r.component:
            # Configure the issue form
            s3db.act_issue_configure_form(resource.table,
                                          r.id,
                                          issue = record,
                                          site_type = settings.get_act_issue_site_type(),
                                          )

            # Configure selectable status options
            s3db.act_issue_set_status_opts(resource.table,
                                           r.id,
                                           record = record,
                                           )

            # Closed records cannot be modified
            if record and record.status == "CLOSED":
                resource.configure(editable=False)

            # Can only delete NEW records
            if not r.record or record.status != "NEW":
                resource.configure(deletable=False)

        elif r.component_name == "task":
            # Configure task form
            s3db.act_task_configure_form(r.component.table,
                                         r.component_id,
                                         issue = record,
                                         site_type = settings.get_act_issue_site_type(),
                                         )

            # Configure selectable status options
            s3db.act_task_set_status_opts(r.component.table,
                                          r.component_id,
                                          )
        return True
    s3.prep = prep

    return crud_controller(rheader=s3db.act_rheader)

# -----------------------------------------------------------------------------
def task_prep(r):

    resource = r.resource
    record = r.record

    if not r.component:
        table = resource.table

        # Configure extended issue representation
        if record:
            field = table.issue_id
            field.represent = s3db.act_IssueRepresent(full_text=True)

        # Configure task form
        s3db.act_task_configure_form(resource.table,
                                     r.id,
                                     task = record,
                                     site_type = settings.get_act_issue_site_type(),
                                     )

        # Configure selectable status options
        s3db.act_task_set_status_opts(resource.table,
                                      record.id if record else None,
                                      record = record,
                                      )

        # Configure list fields for perspective
        list_fields = ["date",
                       "issue_id",
                       "name",
                       "human_resource_id",
                       "status",
                       "comments",
                       ]
        resource.configure(list_fields = list_fields)

    return True

# -----------------------------------------------------------------------------
def task():
    """ Work Orders: CRUD Controller """

    def prep(r):
        result = task_prep(r)
        return result
    s3.prep = prep

    return crud_controller(rheader=s3db.act_rheader)

# -----------------------------------------------------------------------------
def my_open_tasks():
    """ Work Orders: filtered CRUD Controller """

    def prep(r):
        result = task_prep(r)

        resource = r.resource

        # Filter tasks to user
        hr_id = auth.s3_logged_in_human_resource()
        if hr_id:
            query = FS("human_resource_id") == hr_id
        else:
            query = FS("human_resource_id") == 0
        resource.add_filter(query)

        # Filter to actionable statuses
        query = FS("status").belongs(("PENDING", "STARTED", "FEEDBACK"))
        resource.add_filter(query)

        # Reconfigure resource
        resource.configure(#insertable = False,
                           deletable = False,
                           )

        return result
    s3.prep = prep

    return crud_controller("act", "task", rheader=s3db.act_rheader)

# END =========================================================================
