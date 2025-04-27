"""
    PROJECT module customisations for DRKCM

    License: MIT
"""

from gluon import current, IS_EMPTY_OR

from core import IS_ONE_OF

# -------------------------------------------------------------------------
#def project_home():
#    """ Always go to task list """
#
#    from core import s3_redirect_default
#    s3_redirect_default(URL(f="task"))
#

# -------------------------------------------------------------------------
def project_task_resource(r, tablename):
    """
        Restrict list of assignees to just Staff/Volunteers
    """

    db = current.db
    s3db = current.s3db

    # Configure custom form for tasks
    from core import CustomForm
    crud_form = CustomForm("name",
                           "status",
                           "priority",
                           "description",
                           #"source",
                           "pe_id",
                           "date_due",
                           )
    s3db.configure("project_task",
                   crud_form = crud_form,
                   update_realm = True,
                   )

    accessible_query = current.auth.s3_accessible_query

    # Filter assignees to human resources
    htable = s3db.hrm_human_resource
    ptable = s3db.pr_person
    query = accessible_query("read", htable) & \
            (htable.person_id == ptable.id)
    rows = db(query).select(ptable.pe_id)
    pe_ids = set(row.pe_id for row in rows)

    # ...and teams
    gtable = s3db.pr_group
    query = accessible_query("read", gtable) & \
            (gtable.group_type == 3)
    rows = db(query).select(gtable.pe_id)
    pe_ids |= set(row.pe_id for row in rows)

    s3db.project_task.pe_id.requires = IS_EMPTY_OR(
        IS_ONE_OF(db, "pr_pentity.pe_id",
                  s3db.pr_PersonEntityRepresent(show_label = False,
                                                show_type = True,
                                                ),
                  sort = True,
                  filterby = "pe_id",
                  filter_opts = pe_ids,
                  ))

# END =========================================================================
