"""
    PROJECT module customisations for DRK

    License: MIT
"""

from gluon import current

from core import IS_ONE_OF

# -------------------------------------------------------------------------
def project_task_resource(r, tablename):
    """
        Restrict list of assignees to just Staff/Volunteers
    """

    T = current.T
    db = current.db
    s3db = current.s3db

    # Configure custom form for tasks
    from core import CustomForm, InlineLink
    crud_form = CustomForm("name",
                           "status",
                           "priority",
                           "description",
                           "source",
                           InlineLink("shelter_inspection_flag",
                                      field="inspection_flag_id",
                                      label=T("Shelter Inspection"),
                                      readonly=True,
                                      render_list=True,
                                      ),
                           "pe_id",
                           "date_due",
                           )
    s3db.configure("project_task",
                   crud_form = crud_form,
                   )

    # Filter assignees to human resources
    htable = s3db.hrm_human_resource
    ptable = s3db.pr_person
    query = (htable.deleted == False) & \
            (htable.person_id == ptable.id)
    rows = db(query).select(ptable.pe_id)
    pe_ids = set(row.pe_id for row in rows)

    # ...and teams
    gtable = s3db.pr_group
    query = (gtable.group_type == 3) & \
            (gtable.deleted == False)
    rows = db(query).select(gtable.pe_id)
    pe_ids |= set(row.pe_id for row in rows)

    from gluon import IS_EMPTY_OR
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
