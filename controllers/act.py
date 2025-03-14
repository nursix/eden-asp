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

        if not r.component:
            # Configure selectable status options
            s3db.act_issue_set_status_opts(r.table,
                                           r.id,
                                           record = r.record,
                                           )

        elif r.component_name == "task":
            # Configure selectable status options
            s3db.act_task_set_status_opts(r.component.table,
                                          r.component_id,
                                          )
        return True
    s3.prep = prep

    return crud_controller(rheader=s3db.act_rheader)

# -----------------------------------------------------------------------------
def task():
    """ Work Orders: CRUD Controller """

    def prep(r):

        record = r.record

        if not r.component:
            # Configure selectable status options
            s3db.act_task_set_status_opts(r.resource.table,
                                          record.id if record else None,
                                          record = record,
                                          )
        return True
    s3.prep = prep

    return crud_controller()

# END =========================================================================
