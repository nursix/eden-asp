"""
    Project Management

    Copyright: 2011-2022 (c) Sahana Software Foundation

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

__all__ = ("ProjectModel",
           "ProjectActivityModel",
           "ProjectActivityDemographicsModel",
           "ProjectActivityTypeModel",
           "ProjectActivityOrganisationModel",
           "ProjectActivitySectorModel",
           "ProjectActivityTagModel",
           "ProjectAnnualBudgetModel",
           "ProjectBeneficiaryModel",
           "ProjectHazardModel",
           "ProjectHRModel",
           "ProjectLocationModel",
           "ProjectMasterKeyModel",
           "ProjectOrganisationModel",
           "ProjectSectorModel",
           "ProjectStatusModel",
           "ProjectTagModel",
           "ProjectThemeModel",
           "ProjectTaskModel",
           "ProjectTaskTagModel",
           "project_ActivityRepresent",
           "project_activity_year_options",
           "project_ckeditor",
           "project_rheader",
           "project_task_controller",
           "project_theme_help_fields",
           "project_hazard_help_fields",
           "project_project_filters",
           "project_project_list_layout",
           "project_activity_list_layout",
           "project_task_list_layout",
           "project_TaskRepresent",
           )

import datetime
import json

from gluon import *
from gluon.storage import Storage

from ..core import *
from core.ui.layouts import PopupLink

# =============================================================================
class ProjectModel(DataModel):
    """
        Project Model

        Note:
            This module can be extended by 2 different modes:
            - '3w': "Who's doing What Where"
                    suitable for use by multinational organisations tracking
                    projects at a high level
                    - sub-mode 'drr':   Disaster Risk Reduction extensions
            - 'task': Suitable for use by a smaller organsiation tracking tasks
                      within projects
    """

    names = ("project_project",
             "project_project_id",
             "project_project_represent",
             )

    def model(self):

        T = current.T
        db = current.db
        auth = current.auth

        settings = current.deployment_settings
        mode_3w = settings.get_project_mode_3w()
        mode_task = settings.get_project_mode_task()
        mode_drr = settings.get_project_mode_drr()
        budget_monitoring = settings.get_project_budget_monitoring()
        multi_budgets = settings.get_project_multiple_budgets()
        use_budget = not multi_budgets and not budget_monitoring
        multi_orgs = settings.get_project_multiple_organisations()
        use_codes = settings.get_project_codes()

        add_components = self.add_components
        configure = self.configure
        crud_strings = current.response.s3.crud_strings
        define_table = self.define_table
        set_method = self.set_method
        super_link = self.super_link

        # ---------------------------------------------------------------------
        # Projects
        #
        LEAD_ROLE = settings.get_project_organisation_lead_role()
        org_label = settings.get_project_organisation_roles()[LEAD_ROLE]

        tablename = "project_project"
        define_table(tablename,
                     super_link("doc_id", "doc_entity"),
                     super_link("budget_entity_id", "budget_entity"),
                     # multi_orgs deployments use the separate project_organisation table
                     # - although Lead Org is still cached here to avoid the need for a virtual field to lookup
                     self.org_organisation_id(
                        default = auth.root_org(),
                        label = org_label,
                        requires = self.org_organisation_requires(
                                    required = True,
                                    # Only allowed to add Projects for Orgs
                                    # that the user has write access to
                                    updateable = True,
                                    ),
                        ),
                     Field("name", unique=True, length=255,
                           label = T("Project Name"),
                           # Require unique=True if using IS_NOT_ONE_OF like here (same table,
                           # no filter) in order to allow both automatic indexing (faster)
                           # and key-based de-duplication (i.e. before field validation)
                           requires = [IS_NOT_EMPTY(error_message=T("Please fill this!")),
                                       IS_LENGTH(255),
                                       IS_NOT_ONE_OF(db, "project_project.name")
                                       ],
                           ),
                     Field("code", length=128,
                           label = T("Short Title / ID"),
                           requires = IS_LENGTH(128),
                           readable = use_codes,
                           writable = use_codes,
                           ),
                     Field("description", "text",
                           label = T("Description"),
                           represent = lambda v: s3_text_represent(v, lines=8),
                           ),
                     self.project_status_id(),
                     # NB There is additional client-side validation for start/end date in the Controller
                     DateField("start_date",
                               label = T("Start Date"),
                               set_min = "#project_project_end_date",
                               ),
                     DateField("end_date",
                               label = T("End Date"),
                               set_max = "#project_project_start_date",
                               #start_field = "project_project_start_date",
                               #default_interval = 12,
                               ),
                     # Free-text field with no validation (used by OCHA template currently)
                     Field("duration",
                           label = T("Duration"),
                           readable = False,
                           writable = False,
                           ),
                     # multi_budgets deployments handle on the Budgets Tab
                     # buget_monitoring deployments handle as inline component
                     Field("budget", "double",
                           label = T("Budget"),
                           represent = lambda v: \
                            IS_FLOAT_AMOUNT.represent(v, precision=2),
                           readable = use_budget,
                           writable = use_budget,
                           ),
                     CurrencyField(readable = use_budget,
                                   writable = use_budget,
                                   ),
                     Field("objectives", "text",
                           label = T("Objectives"),
                           represent = lambda v: s3_text_represent(v, lines=8),
                           readable = mode_3w,
                           writable = mode_3w,
                           ),
                     self.hrm_human_resource_id(label = T("Contact Person"),
                                                ),
                     Field.Method("total_annual_budget",
                                  self.project_total_annual_budget),
                     Field.Method("total_organisation_amount",
                                  self.project_total_organisation_amount),
                     CommentsField(comment=DIV(_class="tooltip",
                                               _title="%s|%s" % (T("Comments"),
                                                                 T("Outcomes, Impact, Challenges"),
                                                                 ),
                                               ),
                                   ),
                     )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Project"),
            title_display = T("Project Details"),
            title_list = T("Projects"),
            title_update = T("Edit Project"),
            title_report = T("Project Report"),
            title_upload = T("Import Projects"),
            label_list_button = T("List Projects"),
            label_delete_button = T("Delete Project"),
            msg_record_created = T("Project added"),
            msg_record_modified = T("Project updated"),
            msg_record_deleted = T("Project deleted"),
            msg_list_empty = T("No Projects currently registered"),
            )

        # Filter widgets
        filter_widgets = project_project_filters(org_label = org_label)

        # Resource Configuration
        if settings.get_project_theme_percentages():
            create_next = URL(c="project", f="project",
                              args = ["[id]", "theme"])
        elif mode_task:
            if settings.get_project_milestones():
                create_next = URL(c="project", f="project",
                                  args = ["[id]", "milestone"])
            else:
                create_next = URL(c="project", f="project",
                                  args = ["[id]", "task"])
        else:
            # Default
            create_next = None

        crud_fields = ["organisation_id"]
        cappend = crud_fields.append

        report_fact_fields = [(T("Number of Projects"), "count(id)"),
                              "count(organisation_id)",
                              "count(location.location_id)",
                              ]
        rappend = report_fact_fields.append
        report_col_default = "location.location_id"
        report_row_default = "organisation_id"
        report_fact_default = "count(id)"

        list_fields = ["id"]
        lappend = list_fields.append
        if use_codes:
            lappend("code")
        cappend("name")
        lappend("name")
        if use_codes:
            cappend("code")
        lappend("organisation_id")

        crud_fields += ["description",
                        "status_id",
                        "start_date",
                        "end_date",
                        ]
        if mode_3w:
            lappend((T("Locations"), "location.location_id"))
        if settings.get_project_sectors():
            cappend(InlineLink("sector",
                               label = T("Sectors"),
                               field = "sector_id",
                               cols = 4,
                               translate = True,
                               ))
            lappend((T("Sectors"), "sector_project.sector_id"))
            rappend("count(sector_project.sector_id)")
            report_row_default = "sector_project.sector_id"
            report_fact_default = "count(organisation_id)"
        if mode_drr and settings.get_project_hazards():
            lappend((T("Hazards"), "hazard_project.hazard_id"))
            cappend(InlineLink("hazard",
                               label = T("Hazards"),
                               field = "hazard_id",
                               help_field = project_hazard_help_fields,
                               cols = 4,
                               translate = True,
                               ))
            rappend("count(hazard_project.hazard_id)")
            report_row_default = "hazard_project.hazard_id"
            report_fact_default = "count(organisation_id)"
        if settings.get_project_themes():
            cappend(InlineLink("theme",
                               label = T("Themes"),
                               field = "theme_id",
                               help_field = project_theme_help_fields,
                               cols = 4,
                               translate = True,
                               # Filter Theme by Sector
                               #match = {
                               #    "theme_id:project_theme_sector.sector_id": "sector_project.sector_id",
                               #    },
                               #script = '''
#$.filterOptionsS3({
# 'trigger':{'alias':'sector','name':'sector_id','inlineType':'link'},
# 'target':{'alias':'theme','name':'theme_id','inlineType':'link'},
# 'lookupPrefix':'project',
# 'lookupResource':'theme',
# 'lookupKey':'theme_id:project_theme_sector.sector_id',
# 'showEmptyField':false,
# 'tooltip':'project_theme_help_fields(id,name)'
#})'''
                               ))
            lappend((T("Themes"), "theme.name"))
            rappend("count(theme.name)")
        if multi_orgs:
            lappend((T("Total Funding Amount"), "total_organisation_amount"))
            rappend("sum(total_organisation_amount)")
            rappend("avg(total_organisation_amount)")
        if budget_monitoring:
            lappend((T("Total Budget"), "budget.total_budget"))
            rappend("sum(budget.total_budget)")
            rappend("avg(budget.total_budget)")
        elif multi_budgets:
            lappend((T("Total Annual Budget"), "total_annual_budget"))
            rappend("sum(total_annual_budget)")
            rappend("avg(total_annual_budget)")
        else:
            crud_fields += ["budget",
                            "currency",
                            ]
            lappend((T("Total Budget"), "budget"))
            rappend("sum(budget)")
            rappend("avg(budget)")
        crud_fields += ["human_resource_id",
                        "comments",
                        ]
        list_fields += ["start_date",
                        "end_date",
                        ]
        if not mode_3w:
            lappend("location.location_id")

        crud_form = CustomForm(*crud_fields)

        report_fields = list_fields

        configure(tablename,
                  context = {"location": "location.location_id",
                             "organisation": "organisation_id",
                             },
                  create_next = create_next,
                  crud_form = crud_form,
                  deduplicate = self.project_project_deduplicate,
                  filter_widgets = filter_widgets,
                  list_fields = list_fields,
                  list_layout = project_project_list_layout,
                  onaccept = self.project_project_onaccept,
                  realm_components = ("human_resource",
                                      "task",
                                      "organisation",
                                      "activity",
                                      "activity_type",
                                      "annual_budget",
                                      "beneficiary",
                                      "location",
                                      "milestone",
                                      "theme_percentage",
                                      "document",
                                      "image",
                                      ),
                  report_options = {
                    "rows": report_fields,
                    "cols": report_fields,
                    "fact": report_fact_fields,
                    "defaults": {
                        "rows": report_row_default,
                        "cols": report_col_default,
                        "fact": report_fact_default,
                        "totals": True,
                        },
                  },
                  super_entity = ("doc_entity", "budget_entity"),
                  update_realm = True,
                  )

        # Foreign Key Template
        if use_codes:
            project_represent = S3Represent(lookup=tablename,
                                            field_sep = ": ",
                                            fields=["code", "name"])
        else:
            project_represent = S3Represent(lookup=tablename)

        project_id = FieldTemplate("project_id", "reference %s" % tablename,
                                   label = T("Project"),
                                   ondelete = "CASCADE",
                                   represent = project_represent,
                                   requires = IS_EMPTY_OR(
                                                IS_ONE_OF(db, "project_project.id",
                                                          project_represent,
                                                          updateable = True,
                                                          )),
                                  sortby = "name",
                                  comment = PopupLink(c = "project",
                                                      f = "project",
                                                      tooltip = T("If you don't see the project in the list, you can add a new one by clicking link 'Create Project'."),
                                                      ),
                                  )

        # Custom Methods
        set_method("project_project",
                   method = "assign",
                   action = self.hrm_AssignMethod(component="human_resource"))

        set_method("project_project",
                   method = "map",
                   action = self.project_map)

        # Components
        add_components(tablename,
                       # Activities
                       project_activity = "project_id",
                       # Activity Types
                       project_activity_type = {"link": "project_activity_type_project",
                                                "joinby": "project_id",
                                                "key": "activity_type_id",
                                                "actuate": "link",
                                                },
                       # Events
                       event_project = "project_id",
                       event_event = {"link": "event_project",
                                      "joinby": "project_id",
                                      "key": "event_id",
                                      "actuate": "link",
                                      },
                       # Milestones
                       project_milestone = "project_id",
                       # Tags
                       project_project_tag = {"name": "tag",
                                              "joinby": "project_id",
                                              },
                       # Tasks
                       project_task = "project_id",
                       # Annual Budgets
                       project_annual_budget = "project_id",
                       # Beneficiaries
                       project_beneficiary = "project_id",
                       # Hazards
                       project_hazard = {"link": "project_hazard_project",
                                         "joinby": "project_id",
                                         "key": "hazard_id",
                                         "actuate": "hide",
                                         },
                       # Human Resources
                       project_human_resource_project = "project_id",
                       hrm_human_resource = {"link": "project_human_resource_project",
                                             "joinby": "project_id",
                                             "key": "human_resource_id",
                                             "actuate": "hide",
                                             },
                       # Locations
                       project_location = "project_id",
                       # Sectors
                       org_sector = {"link": "project_sector_project",
                                     "joinby": "project_id",
                                     "key": "sector_id",
                                     "actuate": "hide",
                                     },
                       # Format needed by S3Filter (unless using $link)
                       project_sector_project = ("project_id",
                                                 {"joinby": "project_id",
                                                  "multiple": False,
                                                  },
                                                 ),
                       # Themes
                       project_theme = {"link": "project_theme_project",
                                        "joinby": "project_id",
                                        "key": "theme_id",
                                        "actuate": "hide",
                                        },
                       # Format needed by S3Filter (unless using $link)
                       project_theme_project = "project_id",

                       # Master Keys
                       project_project_masterkey = "project_id",
                       auth_masterkey = {"link": "project_project_masterkey",
                                         "joinby": "project_id",
                                         "key": "masterkey_id",
                                         "actuate": "replace",
                                         "multiple": False,
                                         },

                       # Project Needs (e.g. Funding, Volunteers)
                       req_project_needs = {"joinby": "project_id",
                                            "multiple": False,
                                            },
                       # Requests
                       req_req = {"link": "req_project_req",
                                  "joinby": "project_id",
                                  "key": "req_id",
                                  "actuate": "hide",
                                  },
                       )

        if multi_orgs:
            add_components(tablename,
                           project_organisation = (# Organisations
                                                   "project_id",
                                                   # Donors
                                                   {"name": "donor",
                                                    "joinby": "project_id",
                                                    "filterby": {
                                                        # Works for IFRC
                                                        "role": 3,
                                                        },
                                                    },
                                                   # Partners
                                                   {"name": "partner",
                                                    "joinby": "project_id",
                                                    "filterby": {
                                                        # Works for IFRC:
                                                        "role": (2, 9),
                                                        },
                                                    },
                                                   ),
                          )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return {"project_project_id": project_id,
                "project_project_represent": project_represent,
                }

    # -------------------------------------------------------------------------
    def defaults(self):
        """ Safe defaults for model-global names if module is disabled """

        return {"project_project_id": FieldTemplate.dummy("project_id"),
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def project_total_annual_budget(row):
        """ Total of all annual budgets for project """

        if not current.deployment_settings.get_project_multiple_budgets():
            return 0
        if "project_project" in row:
            project_id = row["project_project.id"]
        elif "id" in row:
            project_id = row["id"]
        else:
            return 0

        table = current.s3db.project_annual_budget
        query = (table.deleted != True) & \
                (table.project_id == project_id)
        sum_field = table.amount.sum()
        return current.db(query).select(sum_field).first()[sum_field] or \
               current.messages["NONE"]

    # -------------------------------------------------------------------------
    @staticmethod
    def project_total_organisation_amount(row):
        """ Total of project_organisation amounts for project """

        if not current.deployment_settings.get_project_multiple_organisations():
            return 0
        if "project_project" in row:
            project_id = row["project_project.id"]
        elif "id" in row:
            project_id = row["id"]
        else:
            return 0

        table = current.s3db.project_organisation
        query = (table.deleted != True) & \
                (table.project_id == project_id)
        sum_field = table.amount.sum()
        return current.db(query).select(sum_field).first()[sum_field]

    # -------------------------------------------------------------------------
    @staticmethod
    def project_project_onaccept(form):
        """
            After DB I/O tasks for Project records
        """

        settings = current.deployment_settings

        if settings.get_project_multiple_organisations():
            # Create/update project_organisation record from the organisation_id
            # (Not in form.vars if added via component tab)
            form_vars = form.vars
            project_id = form_vars.id
            organisation_id = form_vars.organisation_id or \
                              current.request.post_vars.organisation_id
            if organisation_id:
                lead_role = settings.get_project_organisation_lead_role()

                otable = current.s3db.project_organisation
                query = (otable.project_id == project_id) & \
                        (otable.role == lead_role)

                # Update the lead organisation
                count = current.db(query).update(organisation_id = organisation_id)
                if not count:
                    # If there is no record to update, then create a new one
                    oid = otable.insert(project_id = project_id,
                                        organisation_id = organisation_id,
                                        role = lead_role,
                                        )
                    current.auth.s3_set_record_owner(otable, oid)

    # -------------------------------------------------------------------------
    @staticmethod
    def project_project_deduplicate(item):
        """ Import item de-duplication """

        data = item.data
        # If we have a code, then assume this is unique, however the same
        # project name may be used in multiple locations
        code = data.get("code")
        if code:
            table = item.table
            query = (table.code.lower() == code.lower())
        else:
            name = data.get("name")
            if name:
                table = item.table
                query = (table.name.lower() == name.lower())
            else:
                # Nothing we can work with
                return

        duplicate = current.db(query).select(table.id,
                                             limitby=(0, 1)).first()
        if duplicate:
            item.id = duplicate.id
            item.method = item.METHOD.UPDATE

    # -------------------------------------------------------------------------
    @staticmethod
    def project_map(r, **attr):
        """
            Display a filterable set of Projects on a Map
            - assumes mode_3w
            - currently assumes that theme_percentages=True

            @ToDo: Browse by Year
        """

        if r.representation == "html" and \
           r.name == "project":

            T = current.T

            # Search Widget
            themes_dropdown = SELECT(_multiple = True,
                                     _id = "project_theme_id",
                                     _style = "height:80px",
                                     )
            append = themes_dropdown.append

            ttable = current.s3db.project_theme
            themes = current.db(ttable.deleted == False).select(ttable.id,
                                                                ttable.name,
                                                                orderby = ttable.name,
                                                                )
            for theme in themes:
                append(OPTION(theme.name,
                              _value = theme.id,
                              #_selected = "selected",
                              ))
            form = FORM(themes_dropdown)

            # Map
            # The Layer of Projects to show on the Map
            # @ToDo: Create a URL to the project_polygons custom method & use that
            # @ToDo: Pass through attributes that we don't need for the 1st level of mapping
            #        so that they can be used without a screen refresh
            url = URL(f="location", extension="geojson")
            layer = {"name"      : T("Projects"),
                     "id"        : "projects",
                     "tablename" : "project_location",
                     "url"       : url,
                     "active"    : True,
                     #"marker"   : None,
                     }

            the_map = current.gis.show_map(collapsed = True,
                                           feature_resources = [layer],
                                           )

            output = {"title": T("Projects Map"),
                      "form": form,
                      "map": the_map,
                      }

            # Add Static JS
            response = current.response
            response.s3.scripts.append(URL(c="static",
                                           f="scripts",
                                           args=["S3", "s3.project_map.js"]))
            response.view = "map.html"
        else:
            r.error(405, current.ERROR.BAD_METHOD)

        return output

    # -------------------------------------------------------------------------
    @staticmethod
    def project_polygons(r, **attr):
        """
            Export Projects as GeoJSON Polygons to view on the map
            - currently assumes that theme_percentages=True

            @ToDo: complete
        """

        db = current.db
        s3db = current.s3db
        ptable = s3db.project_project
        ttable = s3db.project_theme
        tptable = s3db.project_theme_project
        pltable = s3db.project_location
        ltable = s3db.gis_location

        #get_vars = r.get_vars

        themes = db(ttable.deleted == False).select(ttable.id,
                                                    ttable.name,
                                                    orderby = ttable.name)

        # Total the Budget spent by Theme for each country
        countries = {}
        query = (ptable.deleted == False) & \
                (tptable.project_id == ptable.id) & \
                (ptable.id == pltable.project_id) & \
                (ltable.id == pltable.location_id)

        #if "theme_id" in get_vars:
        #    query = query & (tptable.id.belongs(get_vars.theme_id))
        projects = db(query).select()
        for project in projects:
            # Only show those projects which are only within 1 country
            # @ToDo
            _countries = project.location_id
            if len(_countries) == 1:
                country = _countries[0]
                if country in countries:
                    budget = project.project_project.total_annual_budget()
                    theme = project.project_theme_project.theme_id
                    percentage = project.project_theme_project.percentage
                    countries[country][theme] += budget * percentage
                else:
                    name = db(ltable.id == country).select(ltable.name).first().name
                    countries[country] = {"name": name}
                    # Init all themes to 0
                    for theme in themes:
                        countries[country][theme.id] = 0
                    # Add value for this record
                    budget = project.project_project.total_annual_budget()
                    theme = project.project_theme_project.theme_id
                    percentage = project.project_theme_project.percentage
                    countries[country][theme] += budget * percentage

        #query = (ltable.id.belongs(countries))
        #locations = db(query).select(ltable.id,
        #                             ltable.wkt)
        #for location in locations:
        #    pass

        # Convert to GeoJSON
        output = json.dumps({})

        current.response.headers["Content-Type"] = "application/json"
        return output

# =============================================================================
class ProjectAnnualBudgetModel(DataModel):
    """ Project Budget Model """

    names = ("project_annual_budget",)

    def model(self):

        T = current.T
        db = current.db

        # ---------------------------------------------------------------------
        # Annual Budgets
        #
        tablename = "project_annual_budget"
        self.define_table(tablename,
                          self.project_project_id(
                                # Override requires so that update access to the projects isn't required
                                requires = IS_ONE_OF(db, "project_project.id",
                                                     self.project_project_represent
                                                     )
                                ),
                          Field("year", "integer", notnull=True,
                                default = None, # make it current year
                                label = T("Year"),
                                requires = IS_INT_IN_RANGE(1950, 3000),
                                ),
                          Field("amount", "double", notnull=True,
                                default = 0.00,
                                label = T("Amount"),
                                #label = T("Amount Budgeted"),
                                requires = IS_FLOAT_AMOUNT(),
                                ),
                          CurrencyField(required=True),
                          )


        # CRUD Strings
        current.response.s3.crud_strings[tablename] = Storage(
            label_create = T("Add Annual Budget"),
            title_display = T("Annual Budget"),
            title_list = T("Annual Budgets"),
            title_update = T("Edit Annual Budget"),
            title_upload = T("Import Annual Budget data"),
            title_report = T("Report on Annual Budgets"),
            label_list_button = T("List Annual Budgets"),
            msg_record_created = T("New Annual Budget created"),
            msg_record_modified = T("Annual Budget updated"),
            msg_record_deleted = T("Annual Budget deleted"),
            msg_list_empty = T("No annual budgets found"),
            )

        self.configure(tablename,
                       list_fields = ["year",
                                      "amount",
                                      "currency",
                                      ],
                       )

        # Pass names back to global scope (s3.*)
        return None

# =============================================================================
class ProjectBeneficiaryModel(DataModel):
    """
        Project Beneficiary Model
        - depends on Stats module
    """

    names = ("project_beneficiary_type",
             "project_beneficiary",
             "project_beneficiary_activity",
             "project_beneficiary_activity_type",
             )

    def model(self):

        if not current.deployment_settings.has_module("stats"):
            current.log.warning("Project Beneficiary Model needs Stats module enabling")
            #return self.defaults()
            return None

        T = current.T
        db = current.db
        s3 = current.response.s3
        settings = current.deployment_settings

        NONE = current.messages["NONE"]

        configure = self.configure
        crud_strings = s3.crud_strings
        define_table = self.define_table
        super_link = self.super_link

        parameter_represent = self.stats_parameter_represent

        # ---------------------------------------------------------------------
        # Project Beneficiary Type
        #
        tablename = "project_beneficiary_type"
        define_table(tablename,
                     super_link("parameter_id", "stats_parameter"),
                     Field("name", length=128, unique=True,
                           label = T("Name"),
                           represent = lambda v: T(v) if v is not None \
                                                      else NONE,
                           requires = [IS_LENGTH(128),
                                       IS_NOT_IN_DB(db,
                                                    "project_beneficiary_type.name"),
                                       ],
                           ),
                     CommentsField("description",
                                   label = T("Description"),
                                   ),
                     # Link to the Beneficiary Type which is the Total, so that we can calculate percentages
                     Field("total_id", self.stats_parameter,
                           label = T("Total"),
                           represent = parameter_represent,
                           requires = IS_EMPTY_OR(
                                        IS_ONE_OF(db, "stats_parameter.parameter_id",
                                                  parameter_represent,
                                                  instance_types = ("project_beneficiary_type",),
                                                  sort=True)),
                           ),
                     )

        # CRUD Strings
        ADD_BNF_TYPE = T("Create Beneficiary Type")
        crud_strings[tablename] = Storage(
            label_create = ADD_BNF_TYPE,
            title_display = T("Beneficiary Type"),
            title_list = T("Beneficiary Types"),
            title_update = T("Edit Beneficiary Type"),
            label_list_button = T("List Beneficiary Types"),
            msg_record_created = T("Beneficiary Type Added"),
            msg_record_modified = T("Beneficiary Type Updated"),
            msg_record_deleted = T("Beneficiary Type Deleted"),
            msg_list_empty = T("No Beneficiary Types Found"),
            )

        # Resource Configuration
        configure(tablename,
                  super_entity = "stats_parameter",
                  )

        # ---------------------------------------------------------------------
        # Project Beneficiary
        #
        # @ToDo: Split project_id & project_location_id to separate Link Tables
        #

        tablename = "project_beneficiary"
        define_table(tablename,
                     # Instance
                     super_link("data_id", "stats_data"),
                     # Link Fields
                     # populated automatically
                     self.project_project_id(readable = False,
                                             writable = False,
                                             ),
                     self.project_location_id(comment = None),
                     # This is a component, so needs to be a super_link
                     # - can't override field name, ondelete or requires
                     super_link("parameter_id", "stats_parameter",
                                empty = False,
                                instance_types = ("project_beneficiary_type",),
                                label = T("Beneficiary Type"),
                                represent = parameter_represent,
                                readable = True,
                                writable = True,
                                comment = PopupLink(c = "project",
                                                    f = "beneficiary_type",
                                                    vars = {"child": "parameter_id"},
                                                    title = ADD_BNF_TYPE,
                                                    tooltip = T("Please record Beneficiary according to the reporting needs of your project"),
                                                    ),
                                ),
                     # Populated automatically from project_location
                     self.gis_location_id(readable = False,
                                          writable = False,
                                          ),
                     Field("value", "integer",
                           label = T("Number"),
                           comment = DIV(_class="tooltip",
                                         _title="%s|%s" % (T("Actual Number of Beneficiaries"),
                                                           T("The number of beneficiaries actually reached by this activity"))
                                                           ),
                           represent = IS_INT_AMOUNT.represent,
                           requires = IS_INT_IN_RANGE(0, None),
                           ),
                     Field("target_value", "integer",
                           label = T("Targeted Number"),
                           comment = DIV(_class="tooltip",
                                         _title="%s|%s" % (T("Targeted Number of Beneficiaries"),
                                                           T("The number of beneficiaries targeted by this activity"))
                                                           ),
                           represent = IS_INT_AMOUNT.represent,
                           requires = IS_EMPTY_OR(IS_INT_IN_RANGE(0, None)),
                           ),
                     DateField("date",
                               #empty = False,
                               label = T("Start Date"),
                               set_min = "#project_beneficiary_end_date",
                               ),
                     DateField("end_date",
                               #empty = False,
                               label = T("End Date"),
                               set_max = "#project_beneficiary_date",
                               #start_field = "project_beneficiary_date",
                               #default_interval = 12,
                               ),
                     Field("year", "list:integer",
                           compute = lambda row: \
                             self.stats_year(row, "project_beneficiary"),
                           label = T("Year"),
                           ),
                     CommentsField(),
                     )

        # CRUD Strings
        ADD_BNF = T("Add Beneficiaries")
        crud_strings[tablename] = Storage(
            label_create = ADD_BNF,
            title_display = T("Beneficiaries Details"),
            title_list = T("Beneficiaries"),
            title_update = T("Edit Beneficiaries"),
            title_report = T("Beneficiary Report"),
            label_list_button = T("List Beneficiaries"),
            msg_record_created = T("Beneficiaries Added"),
            msg_record_modified = T("Beneficiaries Updated"),
            msg_record_deleted = T("Beneficiaries Deleted"),
            msg_list_empty = T("No Beneficiaries Found"),
            )

        # Model options
        sectors = settings.get_project_sectors()
        hazards = settings.get_project_hazards()
        themes = settings.get_project_themes()

        sector_id = "project_id$sector_project.sector_id"
        hazard_id = "project_id$hazard_project.hazard_id"
        theme_id = "project_id$theme_project.theme_id"

        # Which levels of location hierarchy are we using?
        levels = current.gis.get_relevant_hierarchy_levels()

        # Filter Widgets
        filter_widgets = [
            OptionsFilter("parameter_id",
                          label = T("Beneficiary Type"),
                          #hidden = True,
                          ),
            OptionsFilter("year",
                          operator = "anyof",
                          options = lambda: \
                                    self.stats_year_options("project_beneficiary"),
                          hidden = True,
                          ),
            LocationFilter("location_id",
                           levels = levels,
                           #hidden = True,
                           ),
            ]
        if sectors:
            filter_widgets.insert(0, OptionsFilter(sector_id))
        if themes:
            filter_widgets.append(OptionsFilter(theme_id))

        # List fields
        list_fields = ["project_id",
                       (T("Beneficiary Type"), "parameter_id"),
                       "value",
                       "target_value",
                       "year",
                       ]

        # Report axes
        report_fields = [(T("Beneficiary Type"), "parameter_id"),
                         "project_id",
                         #"project_location_id",
                         "year",
                         ]
        add_report_field = report_fields.append
        if sectors:
            add_report_field(sector_id)
        if hazards:
            add_report_field(hazard_id)
        if themes:
            add_report_field(theme_id)

        # Location levels (append to list fields and report axes)
        for level in levels:
            lfield = "location_id$%s" % level
            list_fields.append(lfield)
            add_report_field(lfield)

        if "L0" in levels:
            default_row = "location_id$L0"
        elif "L1" in levels:
            default_row = "location_id$L1"
        else:
            default_row = "project_id"

        # Report options and defaults
        report_options = {"rows": report_fields,
                          "cols": report_fields,
                          "fact": [(T("Number of Beneficiaries"),"sum(value)"),
                                   (T("Number of Beneficiaries Targeted"), "sum(target_value)"),
                                   ],
                          "defaults": {"rows": default_row,
                                       "cols": "parameter_id",
                                       "fact": "sum(value)",
                                       "totals": True,
                                       },
                          }

        # Resource configuration
        configure(tablename,
                  context = {"project": "project_id",
                             },
                  deduplicate = S3Duplicate(primary = ("parameter_id",
                                                       "project_location_id",
                                                       ),
                                            ),
                  filter_widgets = filter_widgets,
                  list_fields = list_fields,
                  onaccept = self.project_beneficiary_onaccept,
                  report_options = report_options,
                  super_entity = "stats_data",
                  )

        # Foreign Key Template
        beneficiary_id = FieldTemplate("beneficiary_id", "reference %s" % tablename,
                                       label = T("Beneficiaries"),
                                       ondelete = "SET NULL",
                                       represent = self.project_beneficiary_represent,
                                       requires = IS_EMPTY_OR(
                                                    IS_ONE_OF(db, "project_beneficiary.id",
                                                              self.project_beneficiary_represent,
                                                              sort = True,
                                                              )),
                                       sortby = "name",
                                       comment = PopupLink(c = "project",
                                                           f = "beneficiary",
                                                           title = ADD_BNF,
                                                           tooltip = T("If you don't see the beneficiary in the list, you can add a new one by clicking link 'Add Beneficiaries'."),
                                                           ),
                                       )

        # Components
        self.add_components(tablename,
                            # Activity Types
                            project_activity_type = {"link": "project_beneficiary_activity_type",
                                                     "joinby": "beneficiary_id",
                                                     "key": "activity_type_id",
                                                     "actuate": "hide",
                                                     },
                            # Format for OptionsFilter
                            project_beneficiary_activity_type = "beneficiary_id",
                            )

        # ---------------------------------------------------------------------
        # Beneficiary <> Activity Link Table
        #
        tablename = "project_beneficiary_activity"
        define_table(tablename,
                     self.project_activity_id(empty = False,
                                              # Default:
                                              #ondelete = "CASCADE",
                                              ),
                     beneficiary_id(empty = False,
                                    ondelete = "CASCADE",
                                    ),
                     #CommentsField(),
                     )

        configure(tablename,
                  deduplicate = S3Duplicate(primary = ("activity_id",
                                                       "beneficiary_id",
                                                       ),
                                            ),
                  )

        # ---------------------------------------------------------------------
        # Beneficiary <> Activity Type Link Table
        #
        tablename = "project_beneficiary_activity_type"
        define_table(tablename,
                     self.project_activity_type_id(empty = False,
                                                   ondelete = "CASCADE",
                                                   ),
                     beneficiary_id(empty = False,
                                    ondelete = "CASCADE",
                                    ),
                     #CommentsField(),
                     )

        configure(tablename,
                  deduplicate = S3Duplicate(primary = ("activity_type_id",
                                                       "beneficiary_id",
                                                       ),
                                            ),
                  )

        # Pass names back to global scope (s3.*)
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def project_beneficiary_represent(record_id, row=None):
        """
            FK representation
            @ToDo: Bulk inc Translation
        """

        if row:
            return row.type
        if not record_id:
            return current.messages["NONE"]

        db = current.db
        table = db.project_beneficiary
        ttable = db.project_beneficiary_type
        query = (table.id == record_id) & \
                (table.parameter_id == ttable.id)
        record = db(query).select(table.value,
                                  ttable.name,
                                  limitby = (0, 1),
                                  ).first()
        try:
            return "%s %s" % (record.project_beneficiary.value,
                              record.project_beneficiary_type.name,
                              )
        except AttributeError:
            return current.messages.UNKNOWN_OPT

    # ---------------------------------------------------------------------
    @staticmethod
    def project_beneficiary_onaccept(form):
        """
            Update project_beneficiary project & location from project_location_id
        """

        db = current.db
        btable = db.project_beneficiary
        ltable = db.project_location

        record_id = form.vars.id
        query = (btable.id == record_id) & \
                (ltable.id == btable.project_location_id)
        project_location = db(query).select(ltable.project_id,
                                            ltable.location_id,
                                            limitby=(0, 1)).first()
        if project_location:
            db(btable.id == record_id).update(
                    project_id = project_location.project_id,
                    location_id = project_location.location_id
                )

# =============================================================================
class ProjectHazardModel(DataModel):
    """ Project Hazard Model """

    names = ("project_hazard",
             "project_hazard_project",
             "project_hazard_id", # Exported for translation
             )

    def model(self):

        T = current.T
        db = current.db

        crud_strings = current.response.s3.crud_strings
        define_table = self.define_table
        NONE = current.messages["NONE"]

        # ---------------------------------------------------------------------
        # Hazard
        #
        tablename = "project_hazard"
        define_table(tablename,
                     Field("name", length=128, notnull=True, unique=True,
                           label = T("Name"),
                           represent = lambda v: T(v) if v is not None \
                                                      else NONE,
                           requires = IS_NOT_EMPTY(),
                           ),
                     CommentsField(
                        represent = lambda v: T(v) if v is not None \
                                                   else NONE,
                        ),
                     )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Hazard"),
            title_display = T("Hazard Details"),
            title_list = T("Hazards"),
            title_update = T("Edit Hazard"),
            title_upload = T("Import Hazards"),
            label_list_button = T("List Hazards"),
            label_delete_button = T("Delete Hazard"),
            msg_record_created = T("Hazard added"),
            msg_record_modified = T("Hazard updated"),
            msg_record_deleted = T("Hazard deleted"),
            msg_list_empty = T("No Hazards currently registered"),
            )

        # Foreign Key Template
        represent = S3Represent(lookup=tablename, translate=True)
        hazard_id = FieldTemplate("hazard_id", "reference %s" % tablename,
                                  sortby = "name",
                                  label = T("Hazards"),
                                  requires = IS_EMPTY_OR(
                                                IS_ONE_OF(db, "project_hazard.id",
                                                          represent,
                                                          sort = True,
                                                          )),
                                  represent = represent,
                                  ondelete = "CASCADE",
                                  )

        # ---------------------------------------------------------------------
        # Projects <> Hazards Link Table
        #
        tablename = "project_hazard_project"
        define_table(tablename,
                     hazard_id(),
                     self.project_project_id(),
                     )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Add Hazard"),
            title_display = T("Hazard"),
            title_list = T("Hazards"),
            title_update = T("Edit Hazard"),
            title_upload = T("Import Hazard data"),
            label_list_button = T("List Hazards"),
            msg_record_created = T("Hazard added to Project"),
            msg_record_modified = T("Hazard updated"),
            msg_record_deleted = T("Hazard removed from Project"),
            msg_list_empty = T("No Hazards found for this Project"),
            )

        self.configure(tablename,
                       deduplicate = S3Duplicate(primary = ("project_id",
                                                            "hazard_id",
                                                            ),
                                                 ),
                       )

        # Pass names back to global scope (s3.*)
        return {"project_hazard_id": hazard_id,
                }

# =============================================================================
class ProjectHRModel(DataModel):
    """ Optionally link Projects <> Human Resources """

    names = ("project_human_resource_project",)

    def model(self):

        T = current.T
        settings = current.deployment_settings

        status_opts = {1: T("Assigned"),
                       #2: T("Standing By"),
                       #3: T("Active"),
                       4: T("Left"),
                       #5: T("Unable to activate"),
                       }

        community_volunteers = settings.get_project_community_volunteers()

        # ---------------------------------------------------------------------
        # Projects <> Human Resources
        #
        tablename = "project_human_resource_project"
        self.define_table(tablename,
                          # Instance table
                          self.super_link("cost_item_id", "budget_cost_item"),
                          self.project_project_id(empty = False,
                                                  ondelete = "CASCADE",
                                                  ),
                          self.project_location_id(ondelete = "CASCADE",
                                                   readable = community_volunteers,
                                                   writable = community_volunteers,
                                                   ),
                          self.hrm_human_resource_id(empty = False,
                                                     ondelete = "CASCADE",
                                                     ),
                          Field("status", "integer",
                                default = 1,
                                label = T("Status"),
                                represent = lambda opt: \
                                       status_opts.get(opt, current.messages.UNKNOWN_OPT),
                                requires = IS_IN_SET(status_opts),
                                ),
                          )

        current.response.s3.crud_strings[tablename] = Storage(
            label_create = T("Assign Human Resource"),
            title_display = T("Human Resource Details"),
            title_list = T("Assigned Human Resources"),
            title_update = T("Edit Human Resource"),
            label_list_button = T("List Assigned Human Resources"),
            label_delete_button = T("Remove Human Resource from this project"),
            msg_record_created = T("Human Resource assigned"),
            msg_record_modified = T("Human Resource Assignment updated"),
            msg_record_deleted = T("Human Resource unassigned"),
            msg_list_empty = T("No Human Resources currently assigned to this project"),
            )

        self.configure(tablename,
                       context = {"project": "project_id",
                             },
                       onvalidation = self.project_human_resource_onvalidation,
                       super_entity = "budget_cost_item",
                       )

        # Pass names back to global scope (s3.*)
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def project_human_resource_onvalidation(form):
        """
            Prevent the same human_resource record being added more than once
        """

        hr = current.s3db.project_human_resource_project

        # Fetch the first row that has the same project and human resource ids
        # (which isn't this record!)
        form_vars = form.request_vars
        query = (hr.human_resource_id == form_vars.human_resource_id) & \
                (hr.project_id == form_vars.project_id) & \
                (hr.id != form_vars.id)
        row = current.db(query).select(hr.id,
                                       limitby=(0, 1)).first()

        if row:
            # We have a duplicate. Return an error to the user.
            form.errors.human_resource_id = current.T("Record already exists")

# =============================================================================
class ProjectLocationModel(DataModel):
    """
        Project Location Model
        - these can simply be ways to display a Project on the Map
          or these can be 'Communities'
    """

    names = ("project_location",
             "project_location_id",
             "project_location_contact",
             "project_location_represent",
             )

    def model(self):

        T = current.T
        db = current.db
        s3 = current.response.s3

        settings = current.deployment_settings
        community = settings.get_project_community()
        mode_3w = settings.get_project_mode_3w()

        messages = current.messages

        add_components = self.add_components
        configure = self.configure
        crud_strings = s3.crud_strings
        define_table = self.define_table

         # Which levels of Hierarchy are we using?
        levels = current.gis.get_relevant_hierarchy_levels()

        # ---------------------------------------------------------------------
        # Project Location ('Community')
        #
        tablename = "project_location"
        define_table(tablename,
                     self.super_link("doc_id", "doc_entity"),
                     # Populated onaccept - used for map popups
                     Field("name",
                           writable = False,
                           ),
                     self.project_project_id(),
                     # Enable in templates which desire this:
                     self.project_status_id(readable = False,
                                            writable = False,
                                            ),
                     self.gis_location_id(
                        represent = self.gis_LocationRepresent(sep=", "),
                        requires = IS_LOCATION(),
                        # LocationSelector doesn't support adding new locations dynamically
                        # - if this isn't required, can set to use this widget in the template
                        widget = S3LocationAutocompleteWidget(),
                        comment = PopupLink(c = "gis",
                                            f = "location",
                                            label = T("Create Location"),
                                            title = T("Location"),
                                            tooltip = messages.AUTOCOMPLETE_HELP,
                                            ),
                     ),
                     # % breakdown by location
                     Field("percentage", "decimal(3,2)",
                           comment = T("Amount of the Project Budget spent at this location"),
                           default = 0,
                           label = T("Percentage"),
                           readable = mode_3w,
                           requires = IS_DECIMAL_IN_RANGE(0, 1),
                           writable = mode_3w,
                           ),
                     CommentsField(),
                     )

        # CRUD Strings
        if community:
            LOCATION = T("Community")
            LOCATION_TOOLTIP = T("If you don't see the community in the list, you can add a new one by clicking link 'Create Community'.")
            ADD_LOCATION = T("Add Community")
            crud_strings[tablename] = Storage(
                label_create = ADD_LOCATION,
                title_display = T("Community Details"),
                title_list = T("Communities"),
                title_update = T("Edit Community Details"),
                title_upload = T("Import Community Data"),
                title_report = T("3W Report"),
                title_map = T("Map of Communities"),
                label_list_button = T("List Communities"),
                msg_record_created = T("Community Added"),
                msg_record_modified = T("Community Updated"),
                msg_record_deleted = T("Community Deleted"),
                msg_list_empty = T("No Communities Found"),
                )
        else:
            LOCATION = T("Location")
            LOCATION_TOOLTIP = T("If you don't see the location in the list, you can add a new one by clicking link 'Create Location'.")
            ADD_LOCATION = T("Add Location")
            crud_strings[tablename] = Storage(
                label_create = ADD_LOCATION,
                title_display = T("Location Details"),
                title_list = T("Locations"),
                title_update = T("Edit Location Details"),
                title_upload = T("Import Location Data"),
                title_report = T("3W Report"),
                title_map = T("Map of Projects"),
                label_list_button = T("List Locations"),
                msg_record_created = T("Location Added"),
                msg_record_modified = T("Location updated"),
                msg_record_deleted = T("Location Deleted"),
                msg_list_empty = T("No Locations Found"),
                )

        # Fields to search by Text
        text_fields = []
        tappend = text_fields.append

        # List fields
        list_fields = ["location_id",
                       ]
        lappend = list_fields.append

        # Report options
        report_fields = []
        rappend = report_fields.append

        for level in levels:
            loc_field = "location_id$%s" % level
            lappend(loc_field)
            rappend(loc_field)
            tappend(loc_field)

        lappend("project_id")
        if settings.get_project_theme_percentages():
            lappend((T("Themes"), "project_id$theme_project.theme_id"))
        elif settings.get_project_activity_types():
            lappend((T("Activity Types"), "activity_type.name"))
        lappend("comments")

        # Filter widgets
        if community:
            filter_widgets = [
                TextFilter(text_fields,
                           label = T("Name"),
                           comment = T("Search for a Project Community by name."),
                           )
                ]
        else:
            text_fields.extend(("project_id$name",
                                "project_id$code",
                                "project_id$description",
                                ))
            filter_widgets = [
                TextFilter(text_fields,
                           label = T("Text"),
                           comment = T("Search for a Project by name, code, location, or description."),
                           )
                ]
        fappend = filter_widgets.append

        if settings.get_project_sectors():
            fappend(OptionsFilter("project_id$sector.name",
                                  label = T("Sector"),
                                  hidden = True,
                                  ))

        # @ToDo: This is only suitable for deployments with a few projects
        #        - read the number here?
        fappend(OptionsFilter("project_id",
                              label = T("Project"),
                              hidden = True,
                              ))

        if settings.get_project_themes():
            fappend(OptionsFilter("project_id$theme_project.theme_id",
                                  label = T("Theme"),
                                  options = lambda: \
                                            get_filter_options("project_theme",
                                                               translate=True),
                                  hidden = True,
                                  ))

        fappend(LocationFilter("location_id",
                               levels = levels,
                               hidden = True,
                               ))

        report_fields.extend(((messages.ORGANISATION, "project_id$organisation_id"),
                              (T("Project"), "project_id"),
                              ))
        if settings.get_project_activity_types():
            rappend((T("Activity Types"), "activity_type.activity_type_id"))
            default_fact = "list(activity_type.activity_type_id)"
        else:
            # Not ideal, but what else?
            default_fact = "list(project_id$organisation_id)"

        # Report options and default
        report_options = {"rows": report_fields,
                          "cols": report_fields,
                          "fact": report_fields,
                          "defaults": {"rows": "location_id$%s" % levels[0], # Highest-level of Hierarchy
                                       "cols": "project_id",
                                       "fact": default_fact,
                                       "totals": True,
                                       },
                          }

        # Resource Configuration
        configure(tablename,
                  context = {"project": "project_id",
                             },
                  create_next = URL(c="project", f="location",
                                    args=["[id]", "beneficiary"]),
                  deduplicate = S3Duplicate(primary = ("project_id",
                                                       "location_id",
                                                       ),
                                            ),
                  filter_widgets = filter_widgets,
                  list_fields = list_fields,
                  onaccept = self.project_location_onaccept,
                  report_options = report_options,
                  super_entity = "doc_entity",
                  )

        # Components
        add_components(tablename,
                       # Activity Types
                       project_activity_type = {"link": "project_activity_type_location",
                                                "joinby": "project_location_id",
                                                "key": "activity_type_id",
                                                "actuate": "hide",
                                                },
                       # Beneficiaries
                       project_beneficiary = "project_location_id",
                       # Contacts
                       pr_person = {"name": "contact",
                                    "link": "project_location_contact",
                                    "joinby": "project_location_id",
                                    "key": "person_id",
                                    "actuate": "hide",
                                    "autodelete": False,
                                    },
                       # Themes
                       project_theme = {"link": "project_theme_location",
                                        "joinby": "project_location_id",
                                        "key": "theme_id",
                                        "actuate": "hide",
                                        },
                      )

        # Foreign Key Template
        project_location_represent = project_LocationRepresent()
        project_location_id = FieldTemplate("project_location_id", "reference %s" % tablename,
                                            label = LOCATION,
                                            ondelete = "CASCADE",
                                            represent = project_location_represent,
                                            requires = IS_EMPTY_OR(
                                                            IS_ONE_OF(db, "project_location.id",
                                                                      project_location_represent,
                                                                      updateable = True,
                                                                      sort = True,
                                                                      )),
                                            comment = PopupLink(ADD_LOCATION,
                                                                c = "project",
                                                                f = "location",
                                                                tooltip = LOCATION_TOOLTIP,
                                                                ),
                                            )

        # ---------------------------------------------------------------------
        # Project Community Contact Person
        #
        tablename = "project_location_contact"
        define_table(tablename,
                     project_location_id(),
                     self.pr_person_id(comment = None,
                                       widget = PersonSelector(controller="pr"),
                                       empty = False,
                                       ),
                     )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Add Contact"), # Better language for 'Select or Create'
            title_display = T("Contact Details"),
            title_list = T("Contacts"),
            title_update = T("Edit Contact Details"),
            label_list_button = T("List Contacts"),
            msg_record_created = T("Contact Added"),
            msg_record_modified = T("Contact Updated"),
            msg_record_deleted = T("Contact Deleted"),
            msg_list_empty = T("No Contacts Found"),
            )

        # Filter Widgets
        filter_widgets = [
            TextFilter(["person_id$first_name",
                        "person_id$middle_name",
                        "person_id$last_name"
                        ],
                       label = T("Name"),
                       comment = T("You can search by person name - enter any of the first, middle or last names, separated by spaces. You may use % as wildcard. Press 'Search' without input to list all persons."),
                       ),
            LocationFilter("project_location_id$location_id",
                           levels = levels,
                           hidden = True,
                           ),
            ]

        # Resource configuration
        configure(tablename,
                  filter_widgets = filter_widgets,
                  list_fields = ["person_id",
                                 (T("Email"), "email.value"),
                                 (T("Mobile Phone"), "phone.value"),
                                 "project_location_id",
                                 (T("Project"), "project_location_id$project_id"),
                                 ],
                  onaccept = self.project_location_contact_onaccept,
                  )

        # Components
        add_components(tablename,
                       # Contact Information
                       pr_contact = (# Email
                                     {"name": "email",
                                      "link": "pr_person",
                                      "joinby": "id",
                                      "key": "pe_id",
                                      "fkey": "pe_id",
                                      "pkey": "person_id",
                                      "filterby": {
                                          "contact_method": "EMAIL",
                                          },
                                      },
                                     # Mobile Phone
                                     {"name": "phone",
                                      "link": "pr_person",
                                      "joinby": "id",
                                      "key": "pe_id",
                                      "fkey": "pe_id",
                                      "pkey": "person_id",
                                      "filterby": {
                                          "contact_method": "SMS",
                                          },
                                      },
                                     ),
                       )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return {"project_location_id": project_location_id,
                "project_location_represent": project_location_represent,
                }

    # -------------------------------------------------------------------------
    def defaults(self):
        """ Safe defaults for model-global names if module is disabled """

        return {"project_location_id": FieldTemplate.dummy("project_location_id"),
                "project_location_represent": lambda v, row=None: "",
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def project_location_onaccept(form):
        """
            Calculate the 'name' field used by Map popups
        """

        form_vars = form.vars
        record_id = form_vars.get("id")
        if form_vars.get("location_id") and form_vars.get("project_id"):
            name = current.s3db.project_location_represent(None, form_vars)
        elif record_id:
            name = current.s3db.project_location_represent(record_id)
        else:
            return

        if len(name) > 512:
            # Ensure we don't break limits of SQL field
            name = name[:509] + "..."
        db = current.db
        db(db.project_location.id == record_id).update(name=name)

    # -------------------------------------------------------------------------
    @staticmethod
    def project_location_contact_onaccept(form):
        """
            If the Contact has no Realm, then set it to that of this record
        """

        db = current.db
        form_vars = form.vars
        person_id = form_vars.get("person_id")
        realm_entity = form_vars.get("realm_entity")
        if not person_id or not realm_entity:
            # Retrieve the record
            table = db.project_location_contact
            record = db(table.id == form_vars.get("id")).select(table.person_id,
                                                                table.realm_entity,
                                                                limitby=(0, 1),
                                                                ).first()
            if not record:
                return
            person_id = record.person_id
            realm_entity = record.realm_entity

        if realm_entity:
            ptable = db.pr_person
            person = db(ptable.id == person_id).select(ptable.id,
                                                       ptable.realm_entity,
                                                       limitby=(0, 1),
                                                       ).first()
            if person and not person.realm_entity:
                person.update_record(realm_entity = realm_entity)

# =============================================================================
class ProjectMasterKeyModel(DataModel):
    """
        Link Projects to Master Keys for Mobile Data Entry
    """

    names = ("project_project_masterkey",
             )

    def model(self):

        #T = current.T

        # ---------------------------------------------------------------------
        # Projects <> Master Keys
        #
        self.define_table("project_project_masterkey",
                          self.project_project_id(empty = False),
                          self.auth_masterkey_id(empty = False),
                          )


        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return None

# =============================================================================
class ProjectOrganisationModel(DataModel):
    """ Project Organisation Model """

    names = ("project_organisation",)

    def model(self):

        T = current.T
        settings = current.deployment_settings

        messages = current.messages
        NONE = messages["NONE"]

        # ---------------------------------------------------------------------
        # Project Organisations (for multi_orgs=True)
        #
        project_organisation_roles = settings.get_project_organisation_roles()

        organisation_help = T("Add all organizations which are involved in different roles in this project")

        tablename = "project_organisation"
        self.define_table(tablename,
                          self.project_project_id(
                            comment = PopupLink(c = "project",
                                                f = "project",
                                                vars = {"prefix": "project"},
                                                tooltip = T("If you don't see the project in the list, you can add a new one by clicking link 'Create Project'."),
                                                ),
                          ),
                          self.org_organisation_id(
                                requires = self.org_organisation_requires(
                                                required=True,
                                                ),
                                widget = None,
                                comment = PopupLink(c = "org",
                                                    f = "organisation",
                                                    label = T("Create Organization"),
                                                    title = messages.ORGANISATION,
                                                    tooltip = organisation_help,
                                                    ),
                          ),
                          Field("role", "integer",
                                label = T("Role"),
                                requires = IS_EMPTY_OR(
                                             IS_IN_SET(project_organisation_roles)
                                           ),
                                represent = lambda opt: \
                                            project_organisation_roles.get(opt,
                                                                           NONE)),
                          Field("amount", "double",
                                requires = IS_EMPTY_OR(
                                             IS_FLOAT_AMOUNT()),
                                represent = lambda v: \
                                            IS_FLOAT_AMOUNT.represent(v, precision=2),
                                widget = IS_FLOAT_AMOUNT.widget,
                                label = T("Funds Contributed")),
                          CurrencyField(),
                          CommentsField(),
                          )

        # CRUD Strings
        current.response.s3.crud_strings[tablename] = Storage(
            label_create = T("Add Organization to Project"),
            title_display = T("Project Organization Details"),
            title_list = T("Project Organizations"),
            title_update = T("Edit Project Organization"),
            title_upload = T("Import Project Organizations"),
            title_report = T("Funding Report"),
            label_list_button = T("List Project Organizations"),
            label_delete_button = T("Remove Organization from Project"),
            msg_record_created = T("Organization added to Project"),
            msg_record_modified = T("Project Organization updated"),
            msg_record_deleted = T("Organization removed from Project"),
            msg_list_empty = T("No Organizations for Project(s)"),
            )

        # Report Options
        report_fields = ["project_id",
                         "organisation_id",
                         "role",
                         "amount",
                         "currency",
                         ]
        report_options = {"rows": report_fields,
                          "cols": report_fields,
                          "fact": report_fields,
                          "defaults": {"rows": "organisation_id",
                                       "cols": "currency",
                                       "fact": "sum(amount)",
                                       "totals": False,
                                       },
                          }

        # Resource Configuration
        self.configure(tablename,
                       context = {"project": "project_id",
                                  },
                       deduplicate = S3Duplicate(primary = ("project_id",
                                                            "organisation_id",
                                                            ),
                                                 ),
                       onaccept = self.project_organisation_onaccept,
                       ondelete = self.project_organisation_ondelete,
                       onvalidation = self.project_organisation_onvalidation,
                       realm_entity = self.project_organisation_realm_entity,
                       report_options = report_options,
                       )

        # Pass names back to global scope (s3.*)
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def project_organisation_onvalidation(form, lead_role=None):
        """ Form validation """

        #settings = current.deployment_settings

        # Ensure only a single Lead Org
        if lead_role is None:
            lead_role = current.deployment_settings.get_project_organisation_lead_role()

        form_vars = form.vars
        project_id = form_vars.project_id
        organisation_id = form_vars.organisation_id
        if str(form_vars.role) == str(lead_role) and project_id:
            db = current.db
            otable = db.project_organisation
            query = (otable.deleted != True) & \
                    (otable.project_id == project_id) & \
                    (otable.role == lead_role) & \
                    (otable.organisation_id != organisation_id)
            row = db(query).select(otable.id,
                                   limitby=(0, 1)).first()
            if row:
                form.errors.role = \
                    current.T("Lead Implementer for this project is already set, please choose another role.")

    # -------------------------------------------------------------------------
    @staticmethod
    def project_organisation_onaccept(form):
        """
            Record creation post-processing

            If the added organisation is the lead role, set the
            project.organisation to point to the same organisation
            & update the realm_entity.
        """

        form_vars = form.vars

        if str(form_vars.role) == \
             str(current.deployment_settings.get_project_organisation_lead_role()):

            # Read the record
            # (safer than relying on vars which might be missing on component tabs)
            db = current.db
            ltable = db.project_organisation
            record = db(ltable.id == form_vars.id).select(ltable.project_id,
                                                         ltable.organisation_id,
                                                         limitby = (0, 1),
                                                         ).first()

            # Set the Project's organisation_id to the new lead organisation
            organisation_id = record.organisation_id
            ptable = db.project_project
            db(ptable.id == record.project_id).update(
                                organisation_id = organisation_id,
                                realm_entity = \
                                    current.s3db.pr_get_pe_id("org_organisation",
                                                              organisation_id)
                                )

    # -------------------------------------------------------------------------
    @staticmethod
    def project_organisation_ondelete(row):
        """
            Executed when a project organisation record is deleted.

            If the deleted organisation is the lead role on this project,
            set the project organisation to None.
        """

        db = current.db
        potable = db.project_organisation
        ptable = db.project_project
        query = (potable.id == row.get("id"))
        deleted_row = db(query).select(potable.deleted_fk,
                                       potable.role,
                                       limitby=(0, 1)).first()

        if str(deleted_row.role) == \
           str(current.deployment_settings.get_project_organisation_lead_role()):
            # Get the project_id
            deleted_fk = json.loads(deleted_row.deleted_fk)
            project_id = deleted_fk["project_id"]

            # Set the project organisation_id to NULL (using None)
            db(ptable.id == project_id).update(organisation_id=None)

    # -------------------------------------------------------------------------
    @staticmethod
    def project_organisation_realm_entity(table, record):
        """ Set the realm entity to the project's realm entity """

        po_id = record.id
        db = current.db
        table = db.project_organisation
        ptable = db.project_project
        query = (table.id == po_id) & \
                (table.project_id == ptable.id)
        project = db(query).select(ptable.realm_entity,
                                   limitby=(0, 1)).first()
        try:
            return project.realm_entity
        except AttributeError:
            return None

# =============================================================================
class ProjectSectorModel(DataModel):
    """
        Project Sector Model
    """

    names = ("project_sector_project",)

    def model(self):

        T = current.T

        # ---------------------------------------------------------------------
        # Projects <> Sectors Link Table
        #
        tablename = "project_sector_project"
        self.define_table(tablename,
                          self.org_sector_id(empty = False,
                                             ondelete = "CASCADE",
                                             ),
                          self.project_project_id(empty = False,
                                                  ondelete = "CASCADE",
                                                  ),
                          )

        # CRUD Strings
        current.response.s3.crud_strings[tablename] = Storage(
            label_create = T("Add Sector"),
            title_display = T("Sector"),
            title_list = T("Sectors"),
            title_update = T("Edit Sector"),
            title_upload = T("Import Sector data"),
            label_list_button = T("List Sectors"),
            msg_record_created = T("Sector added to Project"),
            msg_record_modified = T("Sector updated"),
            msg_record_deleted = T("Sector removed from Project"),
            msg_list_empty = T("No Sectors found for this Project"),
            )

        # Pass names back to global scope (s3.*)
        return None

# =============================================================================
class ProjectStatusModel(DataModel):
    """
        Project Status Model
        - used by both Projects & Activities
    """

    names = ("project_status",
             "project_status_id",
             )

    def model(self):

        T = current.T

        # ---------------------------------------------------------------------
        # Project Statuses
        #
        tablename = "project_status"
        self.define_table(tablename,
                          Field("name", length=128, notnull=True, unique=True,
                                label = T("Name"),
                                requires = [IS_NOT_EMPTY(),
                                            IS_LENGTH(128),
                                            ],
                                ),
                          CommentsField(),
                          )

        # CRUD Strings
        ADD_STATUS = T("Create Status")
        current.response.s3.crud_strings[tablename] = Storage(
            label_create = ADD_STATUS,
            title_display = T("Status Details"),
            title_list = T("Statuses"),
            title_update = T("Edit Status"),
            #title_upload = T("Import Statuses"),
            label_list_button = T("List Statuses"),
            label_delete_button = T("Delete Status"),
            msg_record_created = T("Status added"),
            msg_record_modified = T("Status updated"),
            msg_record_deleted = T("Status deleted"),
            msg_list_empty = T("No Statuses currently defined"),
            )

        # Foreign Key Template
        represent = S3Represent(lookup=tablename, translate=True)
        status_id = FieldTemplate("status_id", "reference %s" % tablename,
                                  comment = PopupLink(title = ADD_STATUS,
                                                      c = "project",
                                                      f = "status",
                                                      ),
                                  label = T("Status"),
                                  ondelete = "SET NULL",
                                  represent = represent,
                                  requires = IS_EMPTY_OR(
                                                IS_ONE_OF(current.db, "project_status.id",
                                                          represent,
                                                          sort = True,
                                                          )),
                                  sortby = "name",
                                  )

        # Pass names back to global scope (s3.*)
        return {"project_status_id": status_id,
                }

    # -------------------------------------------------------------------------
    def defaults(self):
        """
            Safe defaults for model-global names in case module is disabled
        """

        return {"project_status_id": FieldTemplate.dummy("status_id"),
                }

# =============================================================================
class ProjectTagModel(DataModel):
    """ Project Tags """

    names = ("project_project_tag",)

    def model(self):

        T = current.T

        # ---------------------------------------------------------------------
        # Project Tags
        #
        tablename = "project_project_tag"
        self.define_table(tablename,
                          self.project_project_id(empty = False),
                          # key is a reserved word in MySQL
                          Field("tag",
                                label = T("Key"),
                                ),
                          Field("value",
                                label = T("Value"),
                                ),
                          CommentsField(),
                          )

        self.configure(tablename,
                       deduplicate = S3Duplicate(primary = ("project_id",
                                                            "tag",
                                                            ),
                                                 ),
                       )

        # Pass names back to global scope (s3.*)
        return None

# =============================================================================
class ProjectThemeModel(DataModel):
    """ Project Theme Model """

    names = ("project_theme",
             "project_theme_id",
             "project_theme_sector",
             "project_theme_project",
             "project_theme_activity",
             "project_theme_location",
             )

    def model(self):

        T = current.T
        db = current.db

        add_components = self.add_components
        configure = self.configure
        crud_strings = current.response.s3.crud_strings
        define_table = self.define_table
        theme_percentages = current.deployment_settings.get_project_theme_percentages()

        NONE = current.messages["NONE"]

        # ---------------------------------------------------------------------
        # Themes
        #
        tablename = "project_theme"
        define_table(tablename,
                     Field("name", length=128, notnull=True, unique=True,
                           label = T("Name"),
                           represent = lambda v: T(v) if v is not None \
                                                      else NONE,
                           requires = [IS_NOT_EMPTY(),
                                       IS_LENGTH(128),
                                       ],
                           ),
                     CommentsField(
                        represent = lambda v: T(v) if v is not None \
                                                   else NONE,
                        ),
                     )

        # CRUD Strings
        ADD_THEME = T("Create Theme")
        crud_strings[tablename] = Storage(
            label_create = ADD_THEME,
            title_display = T("Theme Details"),
            title_list = T("Themes"),
            title_update = T("Edit Theme"),
            #title_upload = T("Import Themes"),
            label_list_button = T("List Themes"),
            label_delete_button = T("Delete Theme"),
            msg_record_created = T("Theme added"),
            msg_record_modified = T("Theme updated"),
            msg_record_deleted = T("Theme deleted"),
            msg_list_empty = T("No Themes currently registered"),
            )

        # Foreign Key Template
        represent = S3Represent(lookup=tablename, translate=True)
        theme_id = FieldTemplate("theme_id", "reference %s" % tablename,
                                 label = T("Theme"),
                                 ondelete = "CASCADE",
                                 represent = represent,
                                 requires = IS_EMPTY_OR(
                                                IS_ONE_OF(db, "project_theme.id",
                                                          represent,
                                                          sort = True,
                                                          )),
                                 sortby = "name",
                                 )

        # Components
        add_components(tablename,
                       # Projects
                       project_theme_project = "theme_id",
                       # Sectors
                       project_theme_sector = "theme_id",
                       # For Sync Filter
                       org_sector = {"link": "project_theme_sector",
                                     "joinby": "theme_id",
                                     "key": "sector_id",
                                     },
                       )

        crud_form = CustomForm(
                        "name",
                        # Project Sectors
                        InlineComponent(
                            "theme_sector",
                            label = T("Sectors to which this Theme can apply"),
                            fields = ["sector_id"],
                        ),
                        "comments"
                    )

        configure(tablename,
                  crud_form = crud_form,
                  list_fields = ["id",
                                 "name",
                                 (T("Sectors"), "theme_sector.sector_id"),
                                 "comments",
                                 ],
                  )

        # ---------------------------------------------------------------------
        # Theme <> Sector Link Table
        #
        tablename = "project_theme_sector"
        define_table(tablename,
                     theme_id(empty = False,
                              ondelete = "CASCADE",
                              ),
                     self.org_sector_id(label = "",
                                        empty = False,
                                        ondelete = "CASCADE",
                                        ),
                     )

        crud_strings[tablename] = Storage(
            label_create = T("Add Sector"),
            title_display = T("Sector"),
            title_list = T("Sectors"),
            title_update = T("Edit Sector"),
            title_upload = T("Import Sector data"),
            label_list_button = T("List Sectors"),
            msg_record_created = T("Sector added to Theme"),
            msg_record_modified = T("Sector updated"),
            msg_record_deleted = T("Sector removed from Theme"),
            msg_list_empty = T("No Sectors found for this Theme"),
            )

        # ---------------------------------------------------------------------
        # Theme <> Project Link Table
        #
        tablename = "project_theme_project"
        define_table(tablename,
                     theme_id(empty = False,
                              ondelete = "CASCADE",
                              ),
                     self.project_project_id(empty = False,
                                             ondelete = "CASCADE",
                                             ),
                     # % breakdown by theme (sector in IATI)
                     Field("percentage", "integer",
                           default = 0,
                           label = T("Percentage"),
                           requires = IS_INT_IN_RANGE(0, 101),
                           readable = theme_percentages,
                           writable = theme_percentages,
                           ),
                     )

        crud_strings[tablename] = Storage(
            label_create = T("Add Theme"),
            title_display = T("Theme"),
            title_list = T("Themes"),
            title_update = T("Edit Theme"),
            #title_upload = T("Import Theme data"),
            label_list_button = T("List Themes"),
            msg_record_created = T("Theme added to Project"),
            msg_record_modified = T("Theme updated"),
            msg_record_deleted = T("Theme removed from Project"),
            msg_list_empty = T("No Themes found for this Project"),
            )

        configure(tablename,
                  deduplicate = S3Duplicate(primary = ("project_id",
                                                       "theme_id",
                                                       ),
                                            ),
                  onaccept = self.project_theme_project_onaccept,
                  )

        # ---------------------------------------------------------------------
        # Theme <> Activity Link Table
        #
        tablename = "project_theme_activity"
        define_table(tablename,
                     theme_id(empty = False,
                              ondelete = "CASCADE",
                              ),
                     self.project_activity_id(empty = False,
                                              ondelete = "CASCADE",
                                              ),
                     )

        crud_strings[tablename] = Storage(
            label_create = T("New Theme"),
            title_display = T("Theme"),
            title_list = T("Themes"),
            title_update = T("Edit Theme"),
            #title_upload = T("Import Theme data"),
            label_list_button = T("List Themes"),
            msg_record_created = T("Theme added to Activity"),
            msg_record_modified = T("Theme updated"),
            msg_record_deleted = T("Theme removed from Activity"),
            msg_list_empty = T("No Themes found for this Activity"),
            )

        configure(tablename,
                  deduplicate = S3Duplicate(primary = ("activity_id",
                                                       "theme_id",
                                                       ),
                                            ),
                  )

        # ---------------------------------------------------------------------
        # Theme <> Project Location Link Table
        #
        tablename = "project_theme_location"
        define_table(tablename,
                     theme_id(empty = False,
                              ondelete = "CASCADE",
                              ),
                     self.project_location_id(empty = False,
                                              ondelete = "CASCADE",
                                              ),
                     # % breakdown by theme (sector in IATI)
                     Field("percentage", "integer",
                           default = 0,
                           label = T("Percentage"),
                           requires = IS_INT_IN_RANGE(0, 101),
                           readable = theme_percentages,
                           writable = theme_percentages,
                           ),
                     )

        crud_strings[tablename] = Storage(
            label_create = T("New Theme"),
            title_display = T("Theme"),
            title_list = T("Themes"),
            title_update = T("Edit Theme"),
            title_upload = T("Import Theme data"),
            label_list_button = T("List Themes"),
            msg_record_created = T("Theme added to Project Location"),
            msg_record_modified = T("Theme updated"),
            msg_record_deleted = T("Theme removed from Project Location"),
            msg_list_empty = T("No Themes found for this Project Location"),
            )

        # Pass names back to global scope (s3.*)
        return {"project_theme_id": theme_id,
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def project_theme_project_onaccept(form):
        """
            Record creation post-processing

            Update the percentages of all the Project's Locations.
        """

        # Check for prepop
        project_id = form.vars.get("project_id", None)
        if not project_id and form.request_vars:
            # Interactive form
            project_id = form.request_vars.get("project_id", None)
        if not project_id:
            return

        # Calculate the list of Percentages for this Project
        percentages = {}
        db = current.db
        table = db.project_theme_project
        query = (table.deleted == False) & \
                (table.project_id == project_id)
        rows = db(query).select(table.theme_id,
                                table.percentage)
        for row in rows:
            percentages[row.theme_id] = row.percentage

        # Update the Project's Locations
        s3db = current.s3db
        table = s3db.project_location
        ltable = s3db.project_theme_location
        update_or_insert = ltable.update_or_insert
        query = (table.deleted == False) & \
                (table.project_id == project_id)
        rows = db(query).select(table.id)
        for row in rows:
            for theme_id in percentages:
                update_or_insert(project_location_id = row.id,
                                 theme_id = theme_id,
                                 percentage = percentages[theme_id])

# =============================================================================
class ProjectActivityModel(DataModel):
    """
        Project Activity Model
        - holds the specific Activities for Projects
        - currently used in mode_task but not mode_3w
    """

    names = ("project_activity",
             "project_activity_id",
             "project_activity_activity_type",
             )

    def model(self):

        T = current.T
        db = current.db
        s3 = current.response.s3

        add_components = self.add_components
        configure = self.configure
        crud_strings = s3.crud_strings
        define_table = self.define_table

        settings = current.deployment_settings
        mode_task = settings.get_project_mode_task()

        # ---------------------------------------------------------------------
        # Project Activity
        #

        represent = project_ActivityRepresent()

        tablename = "project_activity"
        define_table(tablename,
                     # Instance
                     self.super_link("doc_id", "doc_entity"),
                     # Component (each Activity can link to a single Project)
                     self.project_project_id(),
                     Field("name",
                           label = T("Description"),
                           # Activity can simply be a Distribution
                           #requires = IS_NOT_EMPTY(),
                           ),
                     self.project_status_id(),
                     # An Activity happens at a single Location
                     self.gis_location_id(readable = not mode_task,
                                          writable = not mode_task,
                                          ),
                     DateField(#"date", # default
                               label = T("Start Date"),
                               set_min = "#project_activity_end_date",
                               ),
                     DateField("end_date",
                               label = T("End Date"),
                               set_max = "#project_activity_date",
                               #start_field = "project_activity_date",
                               #default_interval = 12,
                               ),
                     # Which contact is this?
                     # Implementing Org should be a human_resource_id
                     # Beneficiary could be a person_id
                     # Either way label should be clear
                     self.pr_person_id(label = T("Contact Person"),
                                       widget = PersonSelector(controller="pr"),
                                       ),
                     Field("time_estimated", "double",
                           label = "%s (%s)" % (T("Time Estimate"),
                                                T("hours")),
                           readable = mode_task,
                           writable = mode_task,
                           ),
                     Field("time_actual", "double",
                           label = "%s (%s)" % (T("Time Taken"),
                                                T("hours")),
                           readable = mode_task,
                           # Gets populated from constituent Tasks
                           writable = False,
                           ),
                     # @ToDo: Move to compute using stats_year
                     Field.Method("year", self.project_activity_year),
                     CommentsField(),
                     )

        # CRUD Strings
        ACTIVITY_TOOLTIP = T("If you don't see the activity in the list, you can add a new one by clicking link 'Create Activity'.")
        ADD_ACTIVITY = T("Create Activity")
        crud_strings[tablename] = Storage(
            label_create = ADD_ACTIVITY,
            title_display = T("Activity Details"),
            title_list = T("Activities"),
            title_update = T("Edit Activity"),
            title_upload = T("Import Activity Data"),
            title_report = T("Activity Report"),
            label_list_button = T("List Activities"),
            msg_record_created = T("Activity Added"),
            msg_record_modified = T("Activity Updated"),
            msg_record_deleted = T("Activity Deleted"),
            msg_list_empty = T("No Activities Found"),
            )

        # Search Method
        filter_widgets = [OptionsFilter("status_id",
                                        label = T("Status"),
                                        cols = 3,
                                        ),
                          ]

        # Resource Configuration
        use_projects = settings.get_project_projects()
        crud_fields = ["name",
                       "status_id",
                       (T("Date"), "date"),
                       "location_id",
                       #"person_id",
                       "comments",
                       ]

        list_fields = ["name",
                       "comments",
                       ]

        default_row = "project_id"
        default_col = "name"
        default_fact = "count(id)"
        report_fields = [(T("Activity"), "name"),
                         (T("Year"), "year"),
                         ]
        rappend = report_fields.append

        fact_fields = [(T("Number of Activities"), "count(id)"),
                       ]

        crud_index = 3
        list_index = 1
        if settings.get_project_activity_sectors():
            crud_fields.insert(crud_index,
                               InlineLink("sector",
                                          field = "sector_id",
                                          label = T("Sectors"),
                                          widget = "groupedopts",
                                          ))
            crud_index += 1
            list_fields.insert(list_index,
                               (T("Sectors"), "sector_activity.sector_id"))
            list_index += 1
            rappend("sector_activity.sector_id")
            default_col = "sector_activity.sector_id"
            filter_widgets.append(OptionsFilter("sector_activity.sector_id"))
        if settings.get_project_activity_types():
            crud_fields.insert(crud_index,
                               InlineLink("activity_type",
                                          field = "activity_type_id",
                                          label = T("Activity Types"),
                                          widget = "groupedopts",
                                          ))
            crud_index += 1
            list_fields.insert(list_index,
                               (T("Activity Types"), "activity_activity_type.activity_type_id"))
            list_index += 1
            rappend((T("Activity Type"), "activity_activity_type.activity_type_id"))
            default_col = "activity_activity_type.activity_type_id"
            filter_widgets.append(
                OptionsFilter("activity_activity_type.activity_type_id",
                              label = T("Type"),
                              ))
        if use_projects:
            crud_fields.insert(0, "project_id")
            list_fields.insert(0, "project_id")
            rappend((T("Project"), "project_id"))
            filter_widgets.insert(1,
                OptionsFilter("project_id",
                              represent = "%(name)s",
                              ))
        if settings.get_project_themes():
            rappend("theme_activity.theme_id")
            filter_widgets.append(
                OptionsFilter("theme_activity.theme_id"))

        if settings.get_project_activity_beneficiaries():
            rappend("beneficiary.parameter_id")
            filter_widgets.append(
                    OptionsFilter("beneficiary.parameter_id"))

        if settings.get_project_activity_filter_year():
            filter_widgets.append(
                OptionsFilter("year",
                              label = T("Year"),
                              options = project_activity_year_options,
                              ),
                )

        if use_projects and settings.get_project_mode_drr():
            rappend(("project_id$hazard_project.hazard_id"))
        if mode_task:
            list_fields.insert(list_index, "time_estimated")
            list_index += 1
            list_fields.insert(list_index, "time_actual")
            list_index += 1
            rappend((T("Time Estimated"), "time_estimated"))
            rappend((T("Time Actual"), "time_actual"))
            default_fact = "sum(time_actual)"
        else:
            # Which levels of Hierarchy are we using?
            levels = current.gis.get_relevant_hierarchy_levels()

            filter_widgets.insert(0,
                LocationFilter("location_id",
                               levels = levels,
                               ))

            for level in levels:
                lfield = "location_id$%s" % level
                list_fields.insert(list_index, lfield)
                report_fields.append(lfield)
                list_index += 1

            # Highest-level of Hierarchy
            default_row = "location_id$%s" % levels[0]

        crud_form = CustomForm(*crud_fields)

        report_options = {"rows": report_fields,
                          "cols": report_fields,
                          "fact": fact_fields,
                          "defaults": {"rows": default_row,
                                       "cols": default_col,
                                       "fact": default_fact,
                                       "totals": True,
                                       },
                          }

        configure(tablename,
                  # Leave these workflows for Templates
                  #create_next = create_next,
                  crud_form = crud_form,
                  deduplicate = S3Duplicate(primary = ("name",
                                                       ),
                                            secondary = ("location_id",
                                                         "date",
                                                         "project_id",
                                                         ),
                                            ),
                  filter_widgets = filter_widgets,
                  list_fields = list_fields,
                  list_layout = project_activity_list_layout,
                  realm_entity = self.project_activity_realm_entity,
                  report_options = report_options,
                  super_entity = "doc_entity",
                  update_realm = True,
                  )

        # Foreign Key Template
        activity_id = FieldTemplate("activity_id", "reference %s" % tablename,
                                    comment = PopupLink(ADD_ACTIVITY,
                                                        c = "project",
                                                        f = "activity",
                                                        tooltip = ACTIVITY_TOOLTIP,
                                                        ),
                                    label = T("Activity"),
                                    ondelete = "CASCADE",
                                    represent = represent,
                                    requires = IS_EMPTY_OR(
                                                    IS_ONE_OF(db, "project_activity.id",
                                                              represent,
                                                              sort = True,
                                                              )),
                                    sortby="name",
                                    )

        # Components
        add_components(tablename,
                       # Activity Types
                       project_activity_type = {"link": "project_activity_activity_type",
                                                "joinby": "activity_id",
                                                "key": "activity_type_id",
                                                "actuate": "replace",
                                                "autocomplete": "name",
                                                "autodelete": False,
                                                },
                       # Format for InlineComponent/filter_widget
                       project_activity_activity_type = "activity_id",
                       # Beneficiaries (Un-named Stats)
                       project_beneficiary = {"link": "project_beneficiary_activity",
                                              "joinby": "activity_id",
                                              "key": "beneficiary_id",
                                              "actuate": "replace",
                                              },
                       # Format for InlineComponent/filter_widget
                       project_beneficiary_activity = "activity_id",
                       # Data
                       project_activity_data = "activity_id",
                       # Demographic
                       project_activity_demographic = "activity_id",
                       # Events
                       event_event = {"link": "event_activity",
                                      "joinby": "activity_id",
                                      "key": "event_id",
                                      "actuate": "hide",
                                      },
                       # Organisations
                       org_organisation = {"link": "project_activity_organisation",
                                           "joinby": "activity_id",
                                           "key": "organisation_id",
                                           "actuate": "hide",
                                           },
                       # Format for InlineComponent/filter_widget
                       project_activity_organisation = "activity_id",
                       # Sectors
                       org_sector = {"link": "project_sector_activity",
                                     "joinby": "activity_id",
                                     "key": "sector_id",
                                     "actuate": "hide",
                                     },
                       # Format for InlineComponent/filter_widget
                       project_sector_activity = "activity_id",
                       # Tags
                       project_activity_tag = {"name": "tag",
                                               "joinby": "activity_id",
                                               },
                       # Tasks
                       project_task = "activity_id",

                       # Themes
                       project_theme = {"link": "project_theme_activity",
                                        "joinby": "activity_id",
                                        "key": "theme_id",
                                        "actuate": "hide",
                                        },
                       # Format for InlineComponent/filter_widget
                       project_theme_activity = "activity_id",
                       # Needs
                       req_need = {"link": "req_need_activity",
                                   "joinby": "activity_id",
                                   "key": "need_id",
                                   "actuate": "hide",
                                   },
                       )

        # ---------------------------------------------------------------------
        # Activity Type - Activity Link Table
        #
        tablename = "project_activity_activity_type"
        define_table(tablename,
                     activity_id(empty = False,
                                 #ondelete = "CASCADE",
                                 ),
                     self.project_activity_type_id(empty = False,
                                                   ondelete = "CASCADE",
                                                   ),
                     )

        crud_strings[tablename] = Storage(
            label_create = T("Add Activity Type"),
            title_display = T("Activity Type"),
            title_list = T("Activity Types"),
            title_update = T("Edit Activity Type"),
            title_upload = T("Import Activity Type data"),
            label_list_button = T("List Activity Types"),
            msg_record_created = T("Activity Type added to Activity"),
            msg_record_modified = T("Activity Type Updated"),
            msg_record_deleted = T("Activity Type removed from Activity"),
            msg_list_empty = T("No Activity Types found for this Activity"),
            )

        if (settings.get_project_mode_3w() and \
            use_projects):
            configure(tablename,
                      onaccept = self.project_activity_activity_type_onaccept,
                      )

        # Pass names back to global scope (s3.*)
        return {"project_activity_id": activity_id,
                }

    # -------------------------------------------------------------------------
    def defaults(self):
        """ Safe defaults for model-global names if module is disabled """

        return {"project_activity_id": FieldTemplate.dummy("activity_id"),
                }

    # ---------------------------------------------------------------------
    @staticmethod
    def project_activity_year(row):
        """
            Virtual field for the project_activity table
            @ToDo: Deprecate: replace with computed field
        """

        if hasattr(row, "project_activity"):
            row = row.project_activity

        try:
            activity_id = row.id
        except AttributeError:
            return []

        if hasattr(row, "date"):
            start_date = row.date
        else:
            start_date = False
        if hasattr(row, "end_date"):
            end_date = row.end_date
        else:
            end_date = False

        if start_date is False or end_date is False:
            s3db = current.s3db
            table = s3db.project_activity
            activity = current.db(table.id == activity_id).select(table.date,
                                                                  table.end_date,
                                                                  cache=s3db.cache,
                                                                  limitby=(0, 1)
                                                                  ).first()
            if activity:
                start_date = activity.date
                end_date = activity.end_date

        if not start_date and not end_date:
            return []
        elif not end_date:
            return [start_date.year]
        elif not start_date:
            return [end_date.year]
        else:
            return list(range(start_date.year, end_date.year + 1))

    # ---------------------------------------------------------------------
    @staticmethod
    def project_activity_activity_type_onaccept(form):
        """
            Ensure the Activity Location is a Project Location with the
            Activity's Activity Types in (as a minimum).

            @ToDo: deployment_setting to allow project Locations to be
                   read-only & have data editable only at the Activity level
        """

        db = current.db

        form_vars_get = form.vars.get
        activity_id = form_vars_get("activity_id")

        # Find the Project & Location
        atable = db.project_activity
        activity = db(atable.id == activity_id).select(atable.project_id,
                                                       atable.location_id,
                                                       limitby=(0, 1)
                                                       ).first()
        try:
            project_id = activity.project_id
            location_id = activity.location_id
        except AttributeError:
            # Nothing we can do
            return

        if not project_id or not location_id:
            # Nothing we can do
            return

        # Find the Project Location
        s3db = current.s3db
        ltable = s3db.project_location
        query = (ltable.project_id == project_id) &\
                (ltable.location_id == location_id)
        location = db(query).select(ltable.id,
                                    limitby=(0, 1)
                                    ).first()

        if location:
            pl_id = location.id
        else:
            # Create it
            pl_id = ltable.insert(project_id = project_id,
                                  location_id = location_id,
                                  )

        # Ensure we have the Activity Type in
        activity_type_id = form_vars_get("activity_type_id")
        latable = s3db.project_activity_type_location
        query = (latable.project_location_id == pl_id) &\
                (latable.activity_type_id == activity_type_id)
        exists = db(query).select(latable.id,
                                  limitby=(0, 1)
                                  ).first()
        if not exists:
            # Create it
            latable.insert(project_location_id = pl_id,
                           activity_type_id = activity_type_id,
                           )

    # -------------------------------------------------------------------------
    @staticmethod
    def project_activity_realm_entity(table, record):
        """ Set the realm entity to the project's realm entity """

        activity_id = record.id
        db = current.db
        table = db.project_activity
        ptable = db.project_project
        query = (table.id == activity_id) & \
                (table.project_id == ptable.id)
        project = db(query).select(ptable.realm_entity,
                                   limitby=(0, 1)).first()
        try:
            return project.realm_entity
        except AttributeError:
            return None

# =============================================================================
class ProjectActivityTypeModel(DataModel):
    """
        Project Activity Type Model
        - holds the Activity Types for Projects
        - it is useful where we don't have the details on the actual Activities,
          but just this summary of Types
    """

    names = ("project_activity_type",
             "project_activity_type_location",
             "project_activity_type_project",
             "project_activity_type_sector",
             "project_activity_type_id",
             )

    def model(self):

        T = current.T
        db = current.db

        NONE = current.messages["NONE"]

        crud_strings = current.response.s3.crud_strings
        define_table = self.define_table

        # ---------------------------------------------------------------------
        # Activity Types
        #
        tablename = "project_activity_type"
        define_table(tablename,
                     Field("name", length=128, notnull=True, unique=True,
                           label = T("Name"),
                           represent = lambda v: T(v) if v is not None \
                                                      else NONE,
                           requires = [IS_NOT_EMPTY(),
                                       IS_LENGTH(128),
                                       ],
                           ),
                     CommentsField(),
                     )

        # CRUD Strings
        ADD_ACTIVITY_TYPE = T("Create Activity Type")
        crud_strings[tablename] = Storage(
            label_create = ADD_ACTIVITY_TYPE,
            title_display = T("Activity Type"),
            title_list = T("Activity Types"),
            title_update = T("Edit Activity Type"),
            label_list_button = T("List Activity Types"),
            msg_record_created = T("Activity Type Added"),
            msg_record_modified = T("Activity Type Updated"),
            msg_record_deleted = T("Activity Type Deleted"),
            msg_list_empty = T("No Activity Types Found"),
            )

        # Foreign Key Templates
        represent = S3Represent(lookup=tablename, translate=True)
        activity_type_id = FieldTemplate("activity_type_id", "reference %s" % tablename,
                                         label = T("Activity Type"),
                                         ondelete = "SET NULL",
                                         represent = represent,
                                         requires = IS_EMPTY_OR(
                                                        IS_ONE_OF(db, "project_activity_type.id",
                                                                  represent,
                                                                  sort = True,
                                                                  )),
                                         sortby = "name",
                                         comment = PopupLink(title = ADD_ACTIVITY_TYPE,
                                                             c = "project",
                                                             f = "activity_type",
                                                             tooltip = T("If you don't see the type in the list, you can add a new one by clicking link 'Create Activity Type'."),
                                                             ),
                                         )

        if current.deployment_settings.get_project_sectors():
            # Component (for Custom Form)
            self.add_components(tablename,
                                project_activity_type_sector = "activity_type_id",
                                )

            crud_form = CustomForm(
                            "name",
                            # Sectors
                            InlineComponent(
                                "activity_type_sector",
                                label=T("Sectors to which this Activity Type can apply"),
                                fields=["sector_id"],
                            ),
                            "comments",
                        )

            self.configure(tablename,
                           crud_form = crud_form,
                           list_fields = ["id",
                                          "name",
                                          (T("Sectors"), "activity_type_sector.sector_id"),
                                          "comments",
                                          ],
                           )

        # ---------------------------------------------------------------------
        # Activity Type <> Sector Link Table
        #
        tablename = "project_activity_type_sector"
        define_table(tablename,
                     activity_type_id(empty = False,
                                      ondelete = "CASCADE",
                                      ),
                     self.org_sector_id(label = "",
                                        empty = False,
                                        ondelete = "CASCADE",
                                        ),
                     )

        # ---------------------------------------------------------------------
        # Activity Type <> Project Location Link Table
        #
        tablename = "project_activity_type_location"
        define_table(tablename,
                     activity_type_id(empty = False,
                                      ondelete = "CASCADE",
                                      ),
                     self.project_location_id(empty = False,
                                              ondelete = "CASCADE",
                                              ),
                     )

        # ---------------------------------------------------------------------
        # Activity Type <> Project Link Table
        #
        tablename = "project_activity_type_project"
        define_table(tablename,
                     activity_type_id(empty = False,
                                      ondelete = "CASCADE",
                                      ),
                     self.project_project_id(empty = False,
                                             ondelete = "CASCADE",
                                             ),
                     )

        crud_strings[tablename] = Storage(
            label_create = T("Add Activity Type"),
            title_display = T("Activity Type"),
            title_list = T("Activity Types"),
            title_update = T("Edit Activity Type"),
            title_upload = T("Import Activity Type data"),
            label_list_button = T("List Activity Types"),
            msg_record_created = T("Activity Type added to Project Location"),
            msg_record_modified = T("Activity Type Updated"),
            msg_record_deleted = T("Activity Type removed from Project Location"),
            msg_list_empty = T("No Activity Types found for this Project Location"),
            )

        # Pass names back to global scope (s3.*)
        return {"project_activity_type_id": activity_type_id,
                }

# =============================================================================
class ProjectActivityOrganisationModel(DataModel):
    """ Project Activity Organisation Model """

    names = ("project_activity_organisation",
             )

    def model(self):

        T = current.T

        NONE = current.messages["NONE"]

        # ---------------------------------------------------------------------
        # Activities <> Organisations - Link table
        #
        project_organisation_roles = current.deployment_settings.get_project_organisation_roles()

        tablename = "project_activity_organisation"
        self.define_table(tablename,
                          self.project_activity_id(empty = False,
                                                   # Default:
                                                   #ondelete = "CASCADE",
                                                   ),
                          self.org_organisation_id(empty = False,
                                                   ondelete = "CASCADE",
                                                   ),
                          Field("role", "integer",
                                default = 1, # Lead
                                label = T("Role"),
                                requires = IS_EMPTY_OR(
                                            IS_IN_SET(project_organisation_roles)
                                            ),
                                represent = lambda opt: \
                                            project_organisation_roles.get(opt,
                                                                           NONE)),
                          )

        # CRUD Strings
        current.response.s3.crud_strings[tablename] = Storage(
            label_create = T("Add Organization to Activity"),
            title_display = T("Activity Organization"),
            title_list = T("Activity Organizations"),
            title_update = T("Edit Activity Organization"),
            label_list_button = T("List Activity Organizations"),
            msg_record_created = T("Activity Organization Added"),
            msg_record_modified = T("Activity Organization Updated"),
            msg_record_deleted = T("Activity Organization Deleted"),
            msg_list_empty = T("No Activity Organizations Found"),
            )

        self.configure(tablename,
                       deduplicate = S3Duplicate(primary = ("activity_id",
                                                            "organisation_id",
                                                            "role",
                                                            ),
                                                 ),
                       )

        # Pass names back to global scope (s3.*)
        return None

# =============================================================================
class ProjectActivityDemographicsModel(DataModel):
    """
        Project Activity Demographics Model
        - activities Target Beneficiaries
        - alternate, simpler, model to project_beneficiary_activity
    """

    names = ("project_activity_demographic",)

    def model(self):

        T = current.T

        from .req import req_timeframe

        # ---------------------------------------------------------------------
        # Project Activities <> Demographics Link Table
        #
        if current.s3db.table("stats_demographic"):
            title = current.response.s3.crud_strings["stats_demographic"].label_create
            parameter_id_comment = PopupLink(c = "stats",
                                             f = "demographic",
                                             vars = {"child": "parameter_id"},
                                             title = title,
                                             )
        else:
            parameter_id_comment = None

        tablename = "project_activity_demographic"
        self.define_table(tablename,
                          self.project_activity_id(empty = False,
                                                   # Default:
                                                   #ondelete = "CASCADE",
                                                   ),
                          self.super_link("parameter_id", "stats_parameter",
                                          instance_types = ("stats_demographic",),
                                          label = T("Demographic"),
                                          represent = self.stats_parameter_represent,
                                          readable = True,
                                          writable = True,
                                          empty = False,
                                          comment = parameter_id_comment,
                                          ),
                          req_timeframe(),
                          Field("target_value", "integer",
                                label = T("Target Value"),
                                represent = IS_INT_AMOUNT.represent,
                                requires = IS_EMPTY_OR(IS_INT_IN_RANGE(0, None)),
                                ),
                          Field("value", "integer",
                                label = T("Actual Value"),
                                represent = IS_INT_AMOUNT.represent,
                                requires = IS_EMPTY_OR(IS_INT_IN_RANGE(0, None)),
                                ),
                          )

        self.configure(tablename,
                       deduplicate = S3Duplicate(primary = ("activity_id",
                                                            "parameter_id",
                                                            ),
                                                 ),
                       )

        # Pass names back to global scope (s3.*)
        return None

# =============================================================================
class ProjectActivitySectorModel(DataModel):
    """
        Project Activity Sector Model
        - an Activity can be classified to 1 or more Sectors
    """

    names = ("project_sector_activity",)

    def model(self):

        # ---------------------------------------------------------------------
        # Project Activities <> Sectors Link Table
        #
        # @ToDo: When Activity is linked to a Project, ensure these stay in sync
        #
        tablename = "project_sector_activity"
        self.define_table(tablename,
                          self.org_sector_id(empty = False,
                                             ondelete = "CASCADE",
                                             ),
                          self.project_activity_id(empty = False,
                                                   # Default:
                                                   #ondelete = "CASCADE",
                                                   ),
                          )

        self.configure(tablename,
                       deduplicate = S3Duplicate(primary = ("activity_id",
                                                            "sector_id",
                                                            ),
                                                 ),
                       )

        # Pass names back to global scope (s3.*)
        return None

# =============================================================================
class ProjectActivityTagModel(DataModel):
    """ Activity Tags """

    names = ("project_activity_tag",)

    def model(self):

        T = current.T

        # ---------------------------------------------------------------------
        # Activity Tags
        #
        tablename = "project_activity_tag"
        self.define_table(tablename,
                          self.project_activity_id(),
                          # key is a reserved word in MySQL
                          Field("tag",
                                label = T("Key"),
                                ),
                          Field("value",
                                label = T("Value"),
                                ),
                          CommentsField(),
                          )

        self.configure(tablename,
                       deduplicate = S3Duplicate(primary = ("activity_id",
                                                            "tag",
                                                            ),
                                                 ),
                       )

        # Pass names back to global scope (s3.*)
        return None

# =============================================================================
class ProjectTaskModel(DataModel):
    """ Project Task Model """

    names = ("project_milestone",
             "project_task",
             "project_task_id",
             "project_time",
             "project_comment",
             "project_task_represent_project",
             "project_task_active_statuses",
             "project_task_project_opts",
             )

    def model(self):

        db = current.db
        T = current.T
        auth = current.auth
        request = current.request
        s3 = current.response.s3
        settings = current.deployment_settings

        project_id = self.project_project_id

        messages = current.messages
        NONE = messages["NONE"]

        add_components = self.add_components
        configure = self.configure
        crud_strings = s3.crud_strings
        define_table = self.define_table
        set_method = self.set_method
        super_link = self.super_link

        # ---------------------------------------------------------------------
        # Project Milestone
        #
        tablename = "project_milestone"
        define_table(tablename,
                     # Stage Report
                     super_link("doc_id", "doc_entity"),
                     project_id(),
                     Field("name",
                           label = T("Short Description"),
                           requires = IS_NOT_EMPTY()
                           ),
                     DateField(),
                     CommentsField(),
                     )

        # CRUD Strings
        ADD_MILESTONE = T("Create Milestone")
        crud_strings[tablename] = Storage(
            label_create = ADD_MILESTONE,
            title_display = T("Milestone Details"),
            title_list = T("Milestones"),
            title_update = T("Edit Milestone"),
            #title_upload = T("Import Milestones"),
            label_list_button = T("List Milestones"),
            msg_record_created = T("Milestone Added"),
            msg_record_modified = T("Milestone Updated"),
            msg_record_deleted = T("Milestone Deleted"),
            msg_list_empty = T("No Milestones Found"),
            )

        # Foreign Key Template
        represent = S3Represent(lookup=tablename,
                                fields=["name", "date"],
                                labels="%(name)s: %(date)s",
                                )
        milestone_id = FieldTemplate("milestone_id", "reference %s" % tablename,
                                     label = T("Milestone"),
                                     ondelete = "RESTRICT",
                                     represent = represent,
                                     requires = IS_EMPTY_OR(
                                                    IS_ONE_OF(db, "project_milestone.id",
                                                              represent,
                                                              )),
                                     sortby = "name",
                                     comment = PopupLink(c = "project",
                                                         f = "milestone",
                                                         title = ADD_MILESTONE,
                                                         tooltip = T("A project milestone marks a significant date in the calendar which shows that progress towards the overall objective is being made."),
                                                         ),
                                     )

        configure(tablename,
                  deduplicate = S3Duplicate(primary = ("name",),
                                            secondary = ("project_id",),
                                            ),
                  orderby = "project_milestone.date",
                  )

        # ---------------------------------------------------------------------
        # Tasks
        #
        # Tasks can be linked to Activities or directly to Projects
        # - they can also be used by the Event/Scenario modules
        #
        use_projects = settings.get_project_projects()
        use_activities = settings.get_project_activities()
        use_milestones = use_projects and settings.get_project_milestones()

        project_task_priority_opts = settings.get_project_task_priority_opts()
        project_task_status_opts = settings.get_project_task_status_opts()
        # Which options for the Status for a Task count as the task being 'Active'
        project_task_active_statuses = [2, 3, 4, 11]
        assignee_represent = self.pr_PersonEntityRepresent(show_label = False,
                                                           show_type = False)
        staff = auth.is_logged_in()

        tablename = "project_task"
        define_table(tablename,
                     super_link("doc_id", "doc_entity"),
                     Field("template", "boolean",
                           default = False,
                           readable = False,
                           writable = False,
                           ),
                     self.project_project_id(
                        readable = use_projects,
                        writable = use_projects,
                        ),
                     self.project_activity_id(
                        readable = use_activities,
                        writable = use_activities,
                        ),
                     milestone_id(
                        readable = use_milestones,
                        writable = use_milestones,
                        ),
                     Field("name", length=100, notnull=True,
                           label = T("Short Description"),
                           requires = [IS_NOT_EMPTY(),
                                       IS_LENGTH(100),
                                       ]
                           ),
                     Field("description", "text",
                           label = T("Detailed Description"),
                           comment = DIV(_class="tooltip",
                                         _title="%s|%s" % (T("Detailed Description"),
                                                           T("Please provide as much detail as you can, including any URL(s) for more information."))),
                           ),
                     self.org_site_id(),
                     self.gis_location_id(
                            readable = False,
                            writable = False
                            ),
                     Field("source",
                           label = T("Source"),
                           ),
                     Field("source_url",
                           label = T("Source Link"),
                           represent = s3_url_represent,
                           requires = IS_EMPTY_OR(IS_URL()),
                           # Can be enabled & labelled within a Template as-required
                           readable = False,
                           writable = False
                           ),
                     Field("priority", "integer",
                           default = 3,
                           label = T("Priority"),
                           represent = represent_option(project_task_priority_opts),
                           requires = IS_IN_SET(project_task_priority_opts,
                                                zero = None),
                           ),
                     # Could be a Person, Team or Organisation
                     super_link("pe_id", "pr_pentity",
                                readable = staff,
                                writable = staff,
                                label = T("Assigned to"),
                                filterby = "instance_type", # Not using instance_types as not a Super-Entity
                                filter_opts = ("pr_person", "pr_group", "org_organisation"),
                                represent = assignee_represent,
                                ),
                     DateTimeField("date_due",
                                   label = T("Date Due"),
                                   represent = "date",
                                   readable = staff,
                                   writable = staff,
                                   ),
                     Field("time_estimated", "double",
                           label = "%s (%s)" % (T("Time Estimate"),
                                                T("hours")),
                           represent = lambda v: NONE if not v else \
                                IS_FLOAT_AMOUNT.represent(v, precision=2),
                           requires = IS_EMPTY_OR(
                                        IS_FLOAT_AMOUNT(0, None)
                                        ),
                           readable = staff,
                           writable = staff,
                           ),
                     Field("time_actual", "double",
                           label = "%s (%s)" % (T("Time Taken"),
                                                T("hours")),
                           represent = lambda v: NONE if not v else \
                                IS_FLOAT_AMOUNT.represent(v, precision=2),
                           requires = IS_EMPTY_OR(
                                        IS_FLOAT_AMOUNT(0, None)
                                        ),
                           readable = staff,
                           # This comes from the Time component
                           writable = False,
                           ),
                     Field("status", "integer",
                           default = 2,
                           label = T("Status"),
                           represent = represent_option(project_task_status_opts),
                           requires = IS_IN_SET(project_task_status_opts,
                                                zero = None),
                           readable = staff,
                           writable = staff,
                           ),
                     Field.Method("task_id", self.project_task_task_id),
                     CommentsField(),
                     on_define = lambda table: \
                        [table.created_on.set_attributes(represent = lambda dt: \
                            S3DateTime.date_represent(dt, utc=True)),
                         ]
                     )

        # CRUD Strings
        ADD_TASK = T("Create Task")
        crud_strings[tablename] = Storage(
            label_create = ADD_TASK,
            title_display = T("Task Details"),
            title_list = T("All Tasks"),
            title_update = T("Edit Task"),
            title_upload = T("Import Tasks"),
            label_list_button = T("List Tasks"),
            msg_record_created = T("Task added"),
            msg_record_modified = T("Task updated"),
            msg_record_deleted = T("Task deleted"),
            msg_list_empty = T("No tasks currently registered"),
            )

        # Basic list fields, filter widgets and CRUD fields for tasks
        list_fields = ["id",
                       (T("ID"), "task_id"),
                       "priority",
                       ]
        lappend = list_fields.append

        filter_widgets = [TextFilter(["name",
                                      "description",
                                      ],
                                     label = T("Search"),
                                     _class = "filter-search",
                                     ),
                          OptionsFilter("priority",
                                        options = project_task_priority_opts,
                                        cols = 4,
                                        ),
                          ]
        fappend = filter_widgets.append

        crud_fields = []
        cappend = crud_fields.append
        cextend = crud_fields.extend

        jquery_ready_append = s3.jquery_ready.append

        # Category fields (project, activity, tags)
        if use_projects and current.request.function != "project":
            lappend("project_id")
            fappend(OptionsFilter("project_id",
                                  options = self.project_task_project_opts,
                                  ))
            cappend("project_id")

        if use_activities and current.request.function != "activity":
            lappend("activity_id")
            fappend(OptionsFilter("activity_id",
                                  options = self.project_task_activity_opts,
                                  ))
            cappend("activity_id")
            if use_projects:
                # Filter Activity List to just those for the Project
                options = {"trigger": "project_id",
                           "target": "activity_id",
                           "lookupPrefix": "project",
                           "lookupResource": "activity",
                           "optional": True,
                           }
                jquery_ready_append('''$.filterOptionsS3(%s)''' % \
                                    json.dumps(options, separators=JSONSEPARATORS))

        # Basic workflow fields
        cextend(("name",
                 "description",
                 "source",
                 "priority",
                 "pe_id",
                 "date_due",
                 ))

        # Additional fields when using milestones
        if use_milestones:
            # Use the field in this format to get the custom represent
            lappend("milestone_id")
            fappend(OptionsFilter("milestone_id",
                                  options = self.project_task_milestone_opts,
                                  ))
            cappend("milestone_id")
            if use_projects:
                # Filter Milestone List to just those for the Project
                options = {"trigger": "project_id",
                           "target": "milestone_id",
                           "lookupPrefix": "project",
                           "lookupResource": "milestone",
                           "optional": True,
                           }
                jquery_ready_append('''$.filterOptionsS3(%s)''' % \
                                    json.dumps(options, separators=JSONSEPARATORS))

        # Remaining standard filter widgets for tasks
        filter_widgets.extend((OptionsFilter("pe_id",
                                             label = T("Assigned To"),
                                             none = T("Unassigned"),
                                             ),
                               OptionsFilter("status",
                                             options = project_task_status_opts,
                                             ),
                               OptionsFilter("created_by",
                                             label = T("Created By"),
                                             hidden = True,
                                             ),
                               DateFilter("created_on",
                                          label = T("Date Created"),
                                          hide_time = True,
                                          hidden = True,
                                          ),
                               DateFilter("date_due",
                                          hide_time = True,
                                          hidden = True,
                                          ),
                               DateFilter("modified_on",
                                          label = T("Date Modified"),
                                          hide_time = True,
                                          hidden = True,
                                          ),
                               ))

        # Additional fields for time logging and workflow
        task_time = settings.get_project_task_time()
        if task_time:
            workflow_fields = ("name",
                               "pe_id",
                               "date_due",
                               "time_estimated",
                               "time_actual",
                               (T("Created On"), "created_on"),
                               "status",
                               )
        else:
            workflow_fields = ("name",
                               "pe_id",
                               "date_due",
                               (T("Created On"), "created_on"),
                               "status",
                               )

        list_fields.extend(workflow_fields)

        # CRUD fields for hours logging
        if task_time:
            cextend(("time_estimated",
                     "status",
                     InlineComponent("time",
                                     label = T("Time Log"),
                                     fields = ["date",
                                               "person_id",
                                               "hours",
                                               "comments"
                                               ],
                                     orderby = "date"
                                     ),
                     "time_actual",
                     "comments",
                     ))
        else:
            cextend(("status",
                     "comments",
                     ))

        # Custom Form
        crud_form = CustomForm(*crud_fields)

        report_options = {"rows": list_fields,
                          "cols": list_fields,
                          "fact": list_fields,
                          "defaults": {"rows": "project_id",
                                       "cols": "task.pe_id",
                                       "fact": "sum(task.time_estimated)",
                                       "totals": True,
                                       },
                          }

        # Resource Configuration
        configure(tablename,
                  context = {"incident": "incident.incident_id",
                             "location": "location_id",
                             # Assignee instead?
                             "organisation": "created_by$organisation_id",
                             "scenario": "scenario.scenario_id",
                             },
                  copyable = True,
                  #create_next = URL(f="task", args=["[id]"]),
                  create_onaccept = self.project_task_create_onaccept,
                  crud_form = crud_form,
                  extra = "description",
                  extra_fields = ["id"],
                  filter_widgets = filter_widgets,
                  list_fields = list_fields,
                  list_layout = project_task_list_layout,
                  onvalidation = self.project_task_onvalidation,
                  orderby = "project_task.priority,project_task.date_due asc",
                  realm_entity = self.project_task_realm_entity,
                  report_options = report_options,
                  super_entity = "doc_entity",
                  update_onaccept = self.project_task_update_onaccept,
                  )

        # Foreign Key Template
        represent = project_TaskRepresent(show_link=True)
        task_id = FieldTemplate("task_id", "reference %s" % tablename,
                                label = T("Task"),
                                ondelete = "CASCADE",
                                represent = represent,
                                requires = IS_EMPTY_OR(
                                                IS_ONE_OF(db, "project_task.id",
                                                          represent,
                                                          )),
                                sortby = "name",
                                comment = PopupLink(c = "project",
                                                    f = "task",
                                                    title = ADD_TASK,
                                                    tooltip = T("A task is a piece of work that an individual or team can do in 1-2 days."),
                                                    ),
                                )

        # Representation with project name, for time log form
        task_represent_project = project_TaskRepresent(show_project=True)

        # Custom Methods
        set_method("project_task",
                   method = "dispatch",
                   action = self.project_task_dispatch)

        # Components
        add_components(tablename,
                       # Format for InlineComponent & Context
                       event_task = {"name": "incident",
                                     "joinby": "task_id",
                                     },
                       event_scenario_task = {"name": "scenario",
                                              "joinby": "task_id",
                                              },
                       # Members
                       project_member = "task_id",
                       # Requests
                       req_req = {"link": "req_task_req",
                                  "joinby": "task_id",
                                  "key": "req_id",
                                  "actuate": "embed",
                                  "autocomplete": "request_number",
                                  "autodelete": False,
                                  },
                       # Tags
                       project_task_tag = {"name": "tag",
                                           "joinby": "task_id",
                                           },
                       # Time
                       project_time = "task_id",
                       # Comments (for imports))
                       project_comment = "task_id",
                       # Shelter Inspections
                       cr_shelter_inspection_flag = {"link": "cr_shelter_inspection_task",
                                                     "joinby": "task_id",
                                                     "key": "inspection_flag_id",
                                                     "actuate": "link",
                                                     "autodelete": False,
                                                     }
                       )

        # ---------------------------------------------------------------------
        # Project comment
        #
        # Parent field allows us to:
        #  * easily filter for top-level threads
        #  * easily filter for next level of threading
        #  * hook a new reply into the correct location in the hierarchy
        #
        tablename = "project_comment"
        define_table(tablename,
                     Field("parent", "reference project_comment",
                           readable = False,
                           requires = IS_EMPTY_OR(IS_IN_DB(db, "%s.id" % tablename)),
                           ),
                     task_id(empty = False,
                             ondelete = "CASCADE",
                             ),
                     Field("body", "text", notnull=True,
                           label = T("Comment"),
                           requires = IS_NOT_EMPTY(),
                           ),
                     )

        # Resource Configuration
        configure(tablename,
                  list_fields = ["id",
                                 "task_id",
                                 "created_by",
                                 "modified_on"
                                 ],
                  )

        # ---------------------------------------------------------------------
        # Project Time
        # - used to Log hours spent on a Task
        #
        tablename = "project_time"
        define_table(tablename,
                     task_id(
                       requires = IS_ONE_OF(db, "project_task.id",
                                            task_represent_project,
                                            ),
                     ),
                     self.pr_person_id(default=auth.s3_logged_in_person(),
                                       widget = SQLFORM.widgets.options.widget
                                       ),
                     DateTimeField(default = "now",
                                   past = 8760, # Hours, so 1 year
                                   future = 0
                                   ),
                     Field("hours", "double",
                           label = T("Effort (Hours)"),
                           represent = lambda v: NONE if not v else \
                                IS_FLOAT_AMOUNT.represent(v, precision=2),
                           requires = IS_EMPTY_OR(
                                        IS_FLOAT_AMOUNT(0, None)
                                        ),
                           widget = S3HoursWidget(precision = 2,
                                                  ),
                           ),
                     Field.Method("day", project_time_day),
                     Field.Method("week", project_time_week),
                     CommentsField(),
                     )

        # CRUD Strings
        crud_strings[tablename] = Storage(
            label_create = T("Log Time Spent"),
            title_display = T("Logged Time Details"),
            title_list = T("Logged Time"),
            title_update = T("Edit Logged Time"),
            title_upload = T("Import Logged Time data"),
            title_report = T("Project Time Report"),
            label_list_button = T("List Logged Time"),
            msg_record_created = T("Time Logged"),
            msg_record_modified = T("Time Log Updated"),
            msg_record_deleted = T("Time Log Deleted"),
            msg_list_empty = T("No Time Logged"),
            )
        if "rows" in request.get_vars and request.get_vars.rows == "project":
            crud_strings[tablename].title_report = T("Project Time Report")

        list_fields = ["id",
                       "project_id",
                       "activity_id",
                       "task_id",
                       "person_id",
                       "date",
                       "hours",
                       "comments",
                       ]

        filter_widgets = [
            OptionsFilter("person_id",
                          ),
            OptionsFilter("task_id$project_id",
                          options = self.project_task_project_opts,
                          ),
            OptionsFilter("task_id$activity_id",
                          options = self.project_task_activity_opts,
                          hidden = True,
                          ),
            DateFilter("date",
                       hide_time = True,
                       hidden = True,
                       ),
            ]

        if settings.get_project_milestones():
            list_fields.insert(3, (T("Milestone"), "task_id$milestone_id"))
            filter_widgets.insert(3, OptionsFilter("task_id$milestone_id",
                                                   #label = T("Milestone"),
                                                   hidden = True,
                                                   ))

        report_fields = list_fields + \
                        [(T("Day"), "day"),
                         (T("Week"), "week")]

        if settings.get_project_sectors():
            report_fields.insert(3, (T("Sector"),
                                     "task_id$project_id$sector_project.sector_id"))
            filter_widgets.insert(1, OptionsFilter("task_id$project_id$sector_project.sector_id",
                                                   ))

        report_options = {"rows": report_fields,
                          "cols": report_fields,
                          "fact": report_fields,
                          "defaults": {"rows": "task_id$project_id",
                                       "cols": "person_id",
                                       "fact": "sum(hours)",
                                       "totals": True,
                                       },
                          }

        configure(tablename,
                  filter_widgets = filter_widgets,
                  list_fields = list_fields,
                  onaccept = self.project_time_onaccept,
                  ondelete = self.project_time_ondelete,
                  report_fields = ["date"],
                  report_options = report_options,
                  )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return {"project_task_id": task_id,
                "project_task_active_statuses": project_task_active_statuses,
                "project_task_represent_project": task_represent_project,
                "project_task_project_opts": self.project_task_project_opts,
                }

    # -------------------------------------------------------------------------
    def defaults(self):
        """ Safe defaults for model-global names if module is disabled """

        return {"project_task_id": FieldTemplate.dummy("task_id"),
                "project_task_active_statuses": [],
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def project_task_task_id(row):
        """ The record ID of a task as separate column in the data table """

        if hasattr(row, "project_task"):
            row = row.project_task
        try:
            return row.id
        except AttributeError:
            return None

    # -------------------------------------------------------------------------
    @staticmethod
    def project_task_project_opts():
        """
            Provide the options for the Project search filter
            - all Projects with Tasks
        """

        db = current.db
        ptable = db.project_project
        ttable = db.project_task
        join = ttable.on((ttable.project_id == ptable.id) & \
                         (ttable.deleted == False))
        query = ptable.deleted == False
        rows = db(query).select(ptable.id, ptable.name, join=join)
        return {row.id: row.name for row in rows}

    # -------------------------------------------------------------------------
    @staticmethod
    def project_task_activity_opts():
        """
            Provide the options for the Activity search filter
            - all Activities with Tasks
        """

        db = current.db
        atable = db.project_activity
        ttable = db.project_task
        join = ttable.on((ttable.project_id == atable.id) & \
                         (ttable.deleted == False))
        query = atable.deleted == False
        rows = db(query).select(atable.id, atable.name, join=join)
        return {row.id: row.name for row in rows}

    # -------------------------------------------------------------------------
    @staticmethod
    def project_task_milestone_opts():
        """
            Provide the options for the Milestone search filter
            - all Milestones with Tasks
        """

        db = current.db
        mtable = db.project_milestone
        ttable = db.project_task
        join = ttable.on((ttable.project_id == mtable.id) & \
                         (ttable.deleted == False))
        query = mtable.deleted == False
        rows = db(query).select(mtable.id, mtable.name, join=join)
        return {row.id: row.name for row in rows}

    # -------------------------------------------------------------------------
    @staticmethod
    def project_task_realm_entity(table, record):
        """ Set the task realm entity to the project's realm entity """

        task_id = record.id
        db = current.db
        ptable = db.project_project
        ttable = db.project_task
        join = ptable.on((ptable.id == ttable.project_id) & \
                         (ptable.deleted == False))
        query = (ttable.id == task_id)
        project = db(query).select(ptable.realm_entity, join=join, limitby=(0, 1)).first()
        if project:
            return project.realm_entity
        else:
            return None

    # -------------------------------------------------------------------------
    @staticmethod
    def project_task_onvalidation(form):
        """ Task form validation """

        form_vars = form.vars
        if str(form_vars.status) == "3" and not form_vars.pe_id:
            form.errors.pe_id = \
                current.T("Status 'assigned' requires the %(fieldname)s to not be blank") % \
                    {"fieldname": current.db.project_task.pe_id.label}
        elif form_vars.pe_id and str(form_vars.status) == "2":
            # Set the Status to 'Assigned' if left at default 'New'
            form_vars.status = 3

    # -------------------------------------------------------------------------
    @staticmethod
    def project_task_create_onaccept(form):
        """
            When a Task is created:
                * inherit the project_id from activity if task is created
                  under activity
                * notify assignee
        """

        db = current.db
        s3db = current.s3db

        form_vars = form.vars
        try:
            record_id = form_vars.id
        except AttributeError:
            record_id = None
        if not record_id:
            return

        table = s3db.project_task

        project_id = form_vars.get("project_id")
        if not project_id:
            project_id = table.project_id.default

        if not project_id:
            activity_id = form_vars.get("activity_id")
            if not activity_id:
                activity_id = table.activity_id.default

            if activity_id:
                atable = s3db.project_activity
                activity = db(atable.id == activity_id).select(atable.project_id,
                                                               limitby = (0, 1),
                                                               ).first()
                if activity and activity.project_id:
                    db(table.id == record_id).update(project_id=project_id)

        # Notify Assignee
        task_notify(form)

    # -------------------------------------------------------------------------
    @staticmethod
    def project_task_update_onaccept(form):
        """
            * Process the additional fields: Project/Activity/Milestone
            * Log changes as comments
            * If the task is assigned to someone then notify them
        """

        db = current.db
        s3db = current.s3db

        form_vars = form.vars
        task_id = form_vars.id
        record = form.record

        table = db.project_task

        if record: # Not True for a record merger
            changed = {}
            for var in form_vars:
                vvar = form_vars[var]
                if isinstance(vvar, Field):
                    # modified_by/modified_on
                    continue
                rvar = record[var]
                if vvar != rvar:
                    type_ = table[var].type
                    if type_ == "integer" or \
                       type_.startswith("reference"):
                        if vvar:
                            vvar = int(vvar)
                        if vvar == rvar:
                            continue
                    represent = table[var].represent
                    if not represent:
                        represent = lambda o: o
                    if rvar:
                        changed[var] = "%s changed from %s to %s" % \
                            (table[var].label, represent(rvar), represent(vvar))
                    else:
                        changed[var] = "%s changed to %s" % \
                            (table[var].label, represent(vvar))

            if changed:
                table = db.project_comment
                text = s3db.auth_UserRepresent(show_link = False)(current.auth.user.id)
                for var in changed:
                    text = "%s\n%s" % (text, changed[var])
                table.insert(task_id = task_id,
                             body = text,
                             )

        # Notify Assignee
        task_notify(form)

        # Resolve shelter inspection flags linked to this task
        if current.deployment_settings.get_cr_shelter_inspection_tasks():
            s3db.cr_resolve_shelter_flags(task_id)

    # -------------------------------------------------------------------------
    @staticmethod
    def project_task_dispatch(r, **attr):
        """
            Send a Task Dispatch notice from a Task
            - if a location is supplied, this will be formatted as an OpenGeoSMS
        """

        if r.representation == "html" and \
           r.name == "task" and r.id and not r.component:

            record = r.record
            text = "%s: %s" % (record.name, record.description)

            # Encode the message as an OpenGeoSMS
            msg = current.msg
            message = msg.prepare_opengeosms(record.location_id,
                                             code = "ST",
                                             map = "google",
                                             text = text)

            # URL to redirect to after message sent
            url = URL(c="project", f="task", args=r.id)

            # Create the form
            if record.pe_id:
                opts = {"recipient": record.pe_id}
            else:
                opts = {"recipient_type": "pr_person"}
            output = msg.compose(type = "SMS",
                                 message = message,
                                 url = url,
                                 **opts)

            # Maintain RHeader for consistency
            if "rheader" in attr:
                rheader = attr["rheader"](r)
                if rheader:
                    output["rheader"] = rheader

            output["title"] = current.T("Send Task Notification")
            current.response.view = "msg/compose.html"

        else:
            r.error(405, current.ERROR.BAD_METHOD)

        return output

    # -------------------------------------------------------------------------
    @classmethod
    def project_time_onaccept(cls, form):
        """
            When a project_time entry is newly created or updated:
                - updates the total hours in both task and activity

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

        task_id = form_vars.get("task_id")
        if not task_id:
            table = current.s3db.project_time
            row = current.db(table.id == record_id).select(table.task_id,
                                                           limitby = (0, 1),
                                                           ).first()
            if row:
                task_id = row.task_id

        if task_id:
            cls.update_total_hours(task_id)

    # -------------------------------------------------------------------------
    @classmethod
    def project_time_ondelete(cls, row):
        """
            When a project_time entry is deleted:
                - updates the total hours in both task and activity

            Args:
                row: the deleted project_time Row
        """

        if row.task_id:
            cls.update_total_hours(row.task_id)

    # -------------------------------------------------------------------------
    @staticmethod
    def update_total_hours(task_id):
        """
            Updates the total hours in both task and corresponding activity

            Args:
                task_id: the project_task record ID
        """

        db = current.db
        s3db = current.s3db

        htable = s3db.project_time
        ttable = s3db.project_task
        atable = s3db.project_activity

        # Look up the task
        query = ttable.id == task_id
        task = db(query).select(ttable.id,
                                ttable.activity_id,
                                limitby = (0, 1),
                                ).first()

        # Update the total hours of the task
        query = (htable.task_id == task_id) & \
                (htable.deleted == False)
        total_hours = htable.hours.sum()
        row = db(query).select(total_hours).first()
        task.update_record(time_actual = row[total_hours])

        # Update the total hours of the activity
        activity_id = task.activity_id
        if activity_id:
            join = htable.on((htable.task_id == ttable.id) & \
                             (htable.deleted == False))
            query = (ttable.activity_id == activity_id) & \
                    (ttable.deleted == False)
            row = db(query).select(total_hours, join=join).first()
            db(atable.id == activity_id).update(time_actual=row[total_hours])

# =============================================================================
class ProjectTaskTagModel(DataModel):
    """ Task Tags """

    names = ("project_task_tag",)

    def model(self):

        T = current.T

        # ---------------------------------------------------------------------
        # Task Tags
        #
        tablename = "project_task_tag"
        self.define_table(tablename,
                          self.project_task_id(empty = False),
                          # key is a reserved word in MySQL
                          Field("tag",
                                label = T("Key"),
                                ),
                          Field("value",
                                label = T("Value"),
                                ),
                          CommentsField(),
                          )

        self.configure(tablename,
                       deduplicate = S3Duplicate(primary = ("task_id",
                                                            "tag",
                                                            ),
                                                 ),
                       )

        # Pass names back to global scope (s3.*)
        return None

# =============================================================================
class project_LocationRepresent(S3Represent):
    """ Representation of Project Locations """

    def __init__(self, translate=False, show_link=False, multiple=False):

        settings = current.deployment_settings

        self.community = settings.get_project_community()
        self.multi_country = len(settings.get_gis_countries()) != 1
        self.use_codes = settings.get_project_codes()

        super().__init__(lookup = "project_location",
                         show_link = show_link,
                         translate = translate,
                         multiple = multiple,
                         )

    # -------------------------------------------------------------------------
    def lookup_rows(self, key, values, fields=None):
        """
            Custom lookup method for organisation rows, does a join with the
            projects and locations.

            Args:
                values: the project_location IDs
        """

        db = current.db
        ltable = current.s3db.project_location
        gtable = db.gis_location
        fields = [ltable.id,    # pkey is needed for the cache
                  gtable.name,
                  gtable.level,
                  gtable.L0,
                  gtable.L1,
                  gtable.L2,
                  gtable.L3,
                  gtable.L4,
                  gtable.L5,
                  ]

        if len(values) == 1:
            query = (ltable.id == values[0]) & \
                    (ltable.location_id == gtable.id)
            limitby = (0, 1)
        else:
            query = (ltable.id.belongs(values)) & \
                    (ltable.location_id == gtable.id)
            limitby = None

        if not self.community:
            ptable = db.project_project
            query &= (ltable.project_id == ptable.id)
            fields.append(ptable.name)
            if self.use_codes:
                fields.append(ptable.code)

        rows = db(query).select(*fields, limitby=limitby)
        self.queries += 1

        return rows

    # -------------------------------------------------------------------------
    def represent_row(self, row):
        """
            Represent a single Row

            Args:
                row: the joined Row
        """

        lrow = row.gis_location

        name = lrow.name
        level = lrow.level
        if level == "L0":
            location = name
        else:
            levels = ["L5", "L4", "L3", "L2", "L1"]
            if self.multi_country:
                levels.append("L0")
            names = [lrow[level] for level in levels if lrow[level]]
            if name and (not names or names[0] != name):
                names[0:0] = [name]
            location = ", ".join(names)

        if self.community:
            return s3_str(location)
        else:
            prow = row.project_project
            if self.use_codes and prow.code:
                project =  "%s: %s" % (prow.code, prow.name)
            else:
                project = prow.name
            name = "%s (%s)" % (project, location)
            return s3_str(name)

# =============================================================================
class project_ActivityRepresent(S3Represent):
    """ Representation of Project Activities """

    def __init__(self,
                 translate = False,
                 show_link = False,
                 multiple = False,
                 ):

        if current.deployment_settings.get_project_projects():
            # Need a custom lookup
            self.code = True
            self.lookup_rows = self.custom_lookup_rows
            fields = ["project_activity.name",
                      "project_project.code",
                      ]
        else:
            # Can use standard lookup of fields
            self.code = False
            fields = ["name"]

        super().__init__(lookup = "project_activity",
                         fields = fields,
                         show_link = show_link,
                         translate = translate,
                         multiple = multiple,
                         )

    # -------------------------------------------------------------------------
    def custom_lookup_rows(self, key, values, fields=None):
        """
            Custom lookup method for activity rows, does a left join with
            the parent project.

            Args:
                values: the activity IDs
        """

        s3db = current.s3db
        atable = s3db.project_activity
        ptable = s3db.project_project

        left = ptable.on(ptable.id == atable.project_id)

        qty = len(values)
        if qty == 1:
            query = (atable.id == values[0])
            limitby = (0, 1)
        else:
            query = (atable.id.belongs(values))
            limitby = (0, qty)

        rows = current.db(query).select(atable.id,
                                        atable.name,
                                        ptable.code,
                                        left=left,
                                        limitby=limitby)
        self.queries += 1
        return rows

    # -------------------------------------------------------------------------
    def represent_row(self, row):
        """
            Represent a single Row

            Args:
                row: the project_activity Row
        """

        if self.code:
            # Custom Row (with the project left-joined)
            name = row["project_activity.name"]
            code = row["project_project.code"]
            if not name:
                return row["project_activity.id"]
        else:
            # Standard row (from fields)
            name = row["name"]
            if not name:
                return row["id"]

        if self.code and code:
            name = "%s > %s" % (code, name)
        return s3_str(name)

# =============================================================================
class project_TaskRepresent(S3Represent):
    """ Representation of project tasks """

    def __init__(self,
                 show_link=False,
                 show_project=False,
                 project_first=True):
        """
            Args:
                show_link: render representation as link to the task
                show_project: show the project name in the representation
                project_first: show the project name before the task name
        """

        task_url = URL(c="project", f="task", args=["[id]"])

        super().__init__(lookup = "project_task",
                         show_link = show_link,
                         linkto = task_url,
                         )

        self.show_project = show_project
        if show_project:
            self.project_represent = S3Represent(lookup = "project_project")

        self.project_first = project_first

    # -------------------------------------------------------------------------
    def lookup_rows(self, key, values, fields=None):
        """
            Custom rows lookup

            Args:
                key: the key Field
                values: the values
                fields: unused (retained for API compatibility)
        """

        s3db = current.s3db

        ttable = s3db.project_task
        fields = [ttable.id, ttable.name]

        show_project = self.show_project
        if show_project:
            fields.append(ttable.project_id)

        if len(values) == 1:
            query = (key == values[0])
        else:
            query = key.belongs(values)
        rows = current.db(query).select(*fields)
        self.queries += 1

        if show_project and rows:
            # Bulk-represent the project_ids
            project_ids = [row.project_id for row in rows]
            if project_ids:
                self.project_represent.bulk(project_ids)

        return rows

    # -------------------------------------------------------------------------
    def represent_row(self, row):
        """
            Represent a row

            Args:
                row: the Row
        """

        output = row["project_task.name"]

        if self.show_project:

            project_id = row["project_task.project_id"]
            if self.project_first:
                if project_id:
                    strfmt = "%(project)s: %(task)s"
                else:
                    strfmt = "- %(task)s"
            else:
                if project_id:
                    strfmt = "%(task)s (%(project)s)"
                else:
                    strfmt = "%(task)s"

            output = strfmt % {"task": s3_str(output),
                               "project": self.project_represent(project_id),
                               }

        return output

# =============================================================================
def project_activity_year_options():
    """
        returns a dict of the options for the year virtual field
        used by the search widget

        orderby needed for postgres

        @ToDo: Migrate to stats_year_options()
    """

    db = current.db
    table = current.s3db.project_activity
    query = (table.deleted == False)
    min_field = table.date.min()
    start_date_min = db(query).select(min_field,
                                      orderby=min_field,
                                      limitby=(0, 1)
                                      ).first()[min_field]
    if start_date_min:
        start_year = start_date_min.year
    else:
        start_year = None

    max_field = table.end_date.max()
    end_date_max = db(query).select(max_field,
                                    orderby=max_field,
                                    limitby=(0, 1)
                                    ).first()[max_field]
    if end_date_max:
        end_year = end_date_max.year
    else:
        end_year = None

    if not start_year or not end_year:
        return {start_year:start_year} or {end_year:end_year}
    years = {}
    for year in range(start_year, end_year + 1):
        years[year] = year
    return years

# =============================================================================
# project_time virtual fields
#
def project_time_day(row):
    """
        Virtual field for project_time - abbreviated string format for
        date, allows grouping per day instead of the individual datetime,
        used for project time report. Requires "date" to be in the additional
        report_fields

        Args:
            row: the Row
    """

    try:
        thisdate = row["project_time.date"]
    except AttributeError:
        return current.messages["NONE"]
    if not thisdate:
        return current.messages["NONE"]

    return thisdate.date().strftime("%d %B %y")

# =============================================================================
def project_time_week(row):
    """
        Virtual field for project_time - returns the date of the Monday
        (=first day of the week) of this entry, used for project time report.
        Requires "date" to be in the additional report_fields

        Args:
            row: the Row
    """

    try:
        thisdate = row["project_time.date"]
    except AttributeError:
        return current.messages["NONE"]
    if not thisdate:
        return current.messages["NONE"]

    day = thisdate.date()
    monday = day - datetime.timedelta(days=day.weekday())

    return monday

# =============================================================================
def project_ckeditor():
    """ Load the Project Comments JS """

    s3 = current.response.s3

    ckeditor = URL(c="static", f="ckeditor", args="ckeditor.js")
    s3.scripts.append(ckeditor)
    adapter = URL(c="static", f="ckeditor", args=["adapters", "jquery.js"])
    s3.scripts.append(adapter)

    # Toolbar options: http://docs.cksource.com/CKEditor_3.x/Developers_Guide/Toolbar
    # @ToDo: Move to Static
    js = "".join((
'''i18n.reply="''', str(current.T("Reply")), '''"
var img_path=S3.Ap.concat('/static/img/jCollapsible/')
var ck_config={toolbar:[['Bold','Italic','-','NumberedList','BulletedList','-','Link','Unlink','-','Smiley','-','Source','Maximize']],toolbarCanCollapse:false,removePlugins:'elementspath'}
function comment_reply(id){
 $('#project_comment_task_id__row').hide()
 $('#project_comment_task_id__row1').hide()
 $('#comment-title').html(i18n.reply)
 $('#project_comment_body').ckeditorGet().destroy()
 $('#project_comment_body').ckeditor(ck_config)
 $('#comment-form').insertAfter($('#comment-'+id))
 $('#project_comment_parent').val(id)
 var task_id = $('#comment-'+id).attr('task_id')
 $('#project_comment_task_id').val(task_id)
}'''))

    s3.js_global.append(js)

# =============================================================================
def project_rheader(r):
    """ Project Resource Headers - used in Project & Budget modules """

    if r.representation != "html":
        # RHeaders only used in interactive views
        return None

    # Need to use this as otherwise demographic_data?viewing=project_location.x
    # doesn't have an rheader
    tablename, record = s3_rheader_resource(r)
    if not record:
        return None
    s3db = current.s3db
    table = s3db.table(tablename)

    resourcename = r.name

    T = current.T
    settings = current.deployment_settings

    attachments_label = settings.get_ui_label_attachments()
    if resourcename == "project":
        mode_3w = settings.get_project_mode_3w()
        mode_task = settings.get_project_mode_task()

        tabs = [(T("Basic Details"), None)]
        append = tabs.append
        if settings.get_project_multiple_organisations():
            append((T("Organizations"), "organisation"))
        if settings.get_project_community():
            append((T("Communities"), "location"))
        elif mode_3w:
            append((T("Locations"), "location"))

        if settings.get_project_theme_percentages():
            append((T("Themes"), "theme"))
        if mode_3w:
            append((T("Beneficiaries"), "beneficiary"))
        if settings.get_project_milestones():
            append((T("Milestones"), "milestone"))
        if settings.get_project_activities():
            append((T("Activities"), "activity"))
        if mode_task:
            append((T("Tasks"), "task"))
        if settings.get_project_budget_monitoring():
            append((T("Budget Monitoring"), "monitoring"))
        elif settings.get_project_multiple_budgets():
            append((T("Annual Budgets"), "annual_budget"))
        if mode_3w:
            append((T("Documents"), "document"))
        else:
            append((attachments_label, "document"))
        if settings.get_hrm_show_staff():
            STAFF = settings.get_hrm_staff_label()
            append((STAFF, "human_resource"))
            if settings.get_project_assign_staff_tab() and \
               current.auth.s3_has_permission("create", "project_human_resource_project"):
                append((T("Assign %(staff)s") % {"staff": STAFF}, "assign"))

        rheader_fields = [["code", "name"],
                          ["organisation_id"],
                          ["start_date", "end_date"]
                          ]
        rheader = S3ResourceHeader(rheader_fields, tabs)(r)

    elif resourcename in ("location", "demographic_data"):
        tabs = [(T("Details"), None),
                (T("Beneficiaries"), "beneficiary"),
                ]
        if settings.get_project_demographics():
            tabs.append((T("Demographics"), "demographic_data/"))
        tabs.append((T("Contact People"), "contact"))
        rheader_fields = []
        if record.project_id is not None:
            rheader_fields.append(["project_id"])
        rheader_fields.append(["location_id"])
        rheader = S3ResourceHeader(rheader_fields, tabs)(r,
                                                         record = record,
                                                         table = table)

    elif resourcename == "activity":
        tabs = [(T("Details"), None),
                (T("Contact People"), "contact"),
                ]
        if settings.get_project_mode_task():
            tabs.append((T("Tasks"), "task"))
            tabs.append((attachments_label, "document"))
        else:
            tabs.append((T("Documents"), "document"))

        rheader_fields = []
        if record.project_id is not None:
            rheader_fields.append(["project_id"])
        rheader_fields.append(["name"])
        rheader_fields.append(["location_id"])
        rheader = S3ResourceHeader(rheader_fields, tabs)(r)

    elif resourcename == "task":
        # Tabs
        tabs = [(T("Details"), None)]
        append = tabs.append
        append((attachments_label, "document"))
        if settings.has_module("msg") and \
           current.auth.permission.has_permission("update", c="msg"):
            append((T("Notify"), "dispatch"))

        rheader_tabs = s3_rheader_tabs(r, tabs)

        # RHeader
        db = current.db
        if record.project_id:
            project = s3db.project_project_represent(record.project_id)
            project = TR(TH("%s: " % T("Project")),
                         project,
                         )
        else:
            project = ""

        atable = s3db.project_activity
        query = (atable.id == record.activity_id)
        activity = db(query).select(atable.name,
                                    limitby=(0, 1)).first()
        if activity:
            activity = TR(TH("%s: " % T("Activity")),
                          activity.name
                          )
        else:
            activity = ""

        if record.description:
            description = TR(TH("%s: " % table.description.label),
                             record.description
                             )
        else:
            description = ""

        if record.site_id:
            facility = TR(TH("%s: " % table.site_id.label),
                          table.site_id.represent(record.site_id),
                          )
        else:
            facility = ""

        if record.location_id:
            location = TR(TH("%s: " % table.location_id.label),
                          table.location_id.represent(record.location_id),
                          )
        else:
            location = ""

        if record.created_by:
            creator = TR(TH("%s: " % T("Created By")),
                         s3db.auth_UserRepresent(show_link = False)(record.created_by),
                         )
        else:
            creator = ""

        if record.time_estimated:
            time_estimated = TR(TH("%s: " % table.time_estimated.label),
                                record.time_estimated
                                )
        else:
            time_estimated = ""

        if record.time_actual:
            time_actual = TR(TH("%s: " % table.time_actual.label),
                             record.time_actual
                             )
        else:
            time_actual = ""

        rheader = DIV(TABLE(project,
                            activity,
                            TR(TH("%s: " % table.name.label),
                               record.name,
                               ),
                            description,
                            facility,
                            location,
                            creator,
                            time_estimated,
                            time_actual,
                            #comments,
                            ), rheader_tabs)

    return rheader

# =============================================================================
def project_task_controller():
    """
        Tasks Controller, defined in the model for use from
        multiple controllers for unified menus
    """

    T = current.T
    s3db = current.s3db
    auth = current.auth
    s3 = current.response.s3
    get_vars = current.request.get_vars

    # Pre-process
    def prep(r):
        tablename = "project_task"
        table = s3db.project_task
        statuses = s3.project_task_active_statuses
        crud_strings = s3.crud_strings[tablename]

        if r.record:
            if r.interactive:
                # Put the Comments in the RFooter
                project_ckeditor()
                s3.rfooter = LOAD("project", "comments.load",
                                  args=[r.id],
                                  ajax=True)

        if r.method == "datalist":
            # Set list_fields for renderer (project_task_list_layout)
            list_fields = ["name",
                           "description",
                           "location_id",
                           "date_due",
                           "pe_id",
                           "status",
                           #"organisation_id$logo",
                           "modified_by",
                           ]
            if current.deployment_settings.get_project_projects():
                list_fields.insert(5, (T("Project"), "project_id"))
            s3db.configure("project_task",
                           list_fields = list_fields,
                           )

        elif r.method in ("create", "create.popup"):
            project_id = r.get_vars.get("project_id", None)
            if project_id:
                # Coming from a profile page
                s3db.project_task.project_id.default = project_id
                # Can't do this for an inline form
                #field.readable = field.writable = False

        elif "mine" in get_vars:
            # Show open tasks assigned to the current user

            # Show only open tasks
            query = (FS("status").belongs(statuses))

            if auth.user:
                hide_fields = ("pe_id", "status")
                if current.deployment_settings \
                          .get_project_my_tasks_include_team_tasks():
                    # Include tasks assigned to the current user's teams

                    # Look up all teams the current user is member of
                    mtable = s3db.pr_group_membership
                    gtable = s3db.pr_group
                    gquery = (mtable.person_id == auth.s3_logged_in_person()) & \
                             (mtable.deleted == False) & \
                             (gtable.id == mtable.group_id) & \
                             (gtable.group_type == 3)
                    groups = current.db(gquery).select(gtable.pe_id)

                    # Filter query
                    pe_ids = set(group.pe_id for group in groups)
                    if pe_ids:
                        # Show assignee if teams are included
                        hide_fields = ("status",)
                        pe_ids.add(auth.user.pe_id)
                        query &= (FS("pe_id").belongs(pe_ids))
                    else:
                        query &= (FS("pe_id") == auth.user.pe_id)

                else:
                    # Filter by user pe_id
                    query &= (FS("pe_id") == auth.user.pe_id)

                # No need for assignee (always us) or status (always "assigned"
                # or "reopened") in list fields:
                list_fields = s3db.get_config(tablename, "list_fields")
                if list_fields:
                    list_fields[:] = (fn for fn in list_fields
                                         if fn not in hide_fields)

                # Adapt CRUD strings
                crud_strings.title_list = T("My Open Tasks")
                crud_strings.msg_list_empty = T("No Tasks Assigned")

            else:
                # Not logged-in, showing all open tasks
                crud_strings.title_list = T("Open Tasks")

            r.resource.add_filter(query)

            # Can not add tasks in this list
            s3db.configure(tablename,
                           copyable = False,
                           listadd = False,
                           )

        elif "project" in get_vars:
            # Show Open Tasks for this Project
            project = get_vars.project
            ptable = s3db.project_project
            try:
                name = current.db(ptable.id == project).select(ptable.name,
                                                               limitby=(0, 1)
                                                               ).first().name
            except AttributeError:
                current.session.error = T("Project not Found")
                redirect(URL(args=None, vars=None))
            query = (FS("project_id") == project) & \
                    (FS("status").belongs(statuses))
            r.resource.add_filter(query)
            crud_strings.title_list = T("Open Tasks for %(project)s") % {"project": name}
            crud_strings.msg_list_empty = T("No Open Tasks for %(project)s") % {"project": name}
            # Add Activity
            list_fields = s3db.get_config(tablename,
                                          "list_fields")
            try:
                # Hide the project column since we know that already
                list_fields.remove((T("Project"), "project_id"))
            except ValueError:
                # Already removed
                pass
            s3db.configure(tablename,
                           copyable = False,
                           deletable = False,
                           # Block Add until we get the injectable component lookups
                           insertable = False,
                           list_fields = list_fields,
                           )
        elif "open" in get_vars:
            # Show Only Open Tasks
            crud_strings.title_list = T("All Open Tasks")
            r.resource.add_filter(table.status.belongs(statuses))

        if r.component:
            if r.component_name == "req":
                if current.deployment_settings.has_module("hrm"):
                    r.component.table.type.default = 3
                if r.method not in {"update", "read"}:
                    # Hide fields which don't make sense in a Create form
                    s3db.req_create_form_mods()
            elif r.component_name == "human_resource":
                r.component.table.type.default = 2
        else:
            if not auth.s3_has_role("STAFF"):
                # Hide fields to avoid confusion (both of inputters & recipients)
                table = r.table
                field = table.time_actual
                field.readable = field.writable = False
        return True
    s3.prep = prep

    # Post-process
    def postp(r, output):
        if r.interactive:
            if not r.component and r.method != "import":
                # Maintain vars: why?
                update_url = URL(args=["[id]"], vars=get_vars)
                BasicCRUD.action_buttons(r, update_url=update_url)
        return output
    s3.postp = postp

    if "mine" in get_vars or "project" in get_vars:
        # Show no filters in pre-filtered views
        hide_filter = True
    else:
        hide_filter = None

    return current.crud_controller("project", "task",
                                   hide_filter = hide_filter,
                                   rheader = s3db.project_rheader,
                                   )

# =============================================================================
def project_theme_help_fields(options):
    """
        Provide the tooltips for the Theme filter

        Args:
            options: the options to generate tooltips for, from
                     S3GroupedOptionsWidget: list of tuples (key, represent)
    """

    table = current.s3db.project_theme
    keys = set(dict(options).keys())
    rows = current.db(table.id.belongs(keys)).select(table.id,
                                                     table.comments)
    T = current.T
    translated = lambda string: T(string) if string else ""
    tooltips = {}
    for row in rows:
        tooltips[row.id] = translated(row.comments)
    return tooltips

# =============================================================================
def project_hazard_help_fields(options):
    """
        Provide the tooltips for the Hazard filter

        Args:
            options: the options to generate tooltips for, from
                     S3GroupedOptionsWidget: list of tuples (key, represent)
    """

    table = current.s3db.project_hazard
    keys = set(dict(options).keys())
    rows = current.db(table.id.belongs(keys)).select(table.id,
                                                     table.comments)

    T = current.T
    translated = lambda string: T(string) if string else ""
    tooltips = {}
    for row in rows:
        tooltips[row.id] = translated(row.comments)
    return tooltips

# =============================================================================
def project_project_filters(org_label):
    """
        Filter widgets for project_project

        Args:
            org_label: the label to use for organisation_id
    """

    T = current.T
    settings = current.deployment_settings

    filter_widgets = [
        TextFilter(["name",
                    "code",
                    "description",
                    ],
                   label = T("Search"),
                   comment = T("Search for a Project by name, code, or description."),
                   ),
        OptionsFilter("status_id",
                      label = T("Status"),
                      cols = 4,
                      ),
        OptionsFilter("organisation_id",
                      label = org_label,
                      # Can be unhidden in customise_xx_resource if there is a need to use a default_filter
                      hidden = True,
                      ),
        LocationFilter("location.location_id",
                       # Default should introspect
                       #levels = ("L0", "L1", "L2"),
                       hidden = True,
                       ),
        ]

    append_filter = filter_widgets.append

    if settings.get_project_sectors():
        append_filter(OptionsFilter("sector_project.sector_id",
                                    label = T("Sector"),
                                    location_filter = True,
                                    none = True,
                                    hidden = True,
                                    ))

    mode_drr = settings.get_project_mode_drr()
    if mode_drr and settings.get_project_hazards():
        append_filter(OptionsFilter("hazard_project.hazard_id",
                                    label = T("Hazard"),
                                    help_field = project_hazard_help_fields,
                                    cols = 4,
                                    hidden = True,
                                    ))

    if settings.get_project_mode_3w() and \
       settings.get_project_themes():
        append_filter(OptionsFilter("theme_project.theme_id",
                                    label = T("Theme"),
                                    help_field = project_theme_help_fields,
                                    cols = 4,
                                    hidden = True,
                                    ))

    if settings.get_project_multiple_organisations():
        append_filter(OptionsFilter("partner.organisation_id",
                                    label = T("Partners"),
                                    hidden = True,
                                    ))
        append_filter(OptionsFilter("donor.organisation_id",
                                    label = T("Donors"),
                                    hidden = True,
                                    ))

    return filter_widgets

# =============================================================================
def project_project_list_layout(list_id, item_id, resource, rfields, record,
                                icon="tasks"):
    """
        Default dataList item renderer for Projects on Profile pages

        Args:
            list_id: the HTML ID of the list
            item_id: the HTML ID of the item
            resource: the CRUDResource to render
            rfields: the S3ResourceFields to render
            record: the record as dict
    """

    raw = record._row
    record_id = raw["project_project.id"]
    item_class = "thumbnail"

    author = record["project_project.modified_by"]
    #date = record["project_project.modified_on"]

    name = record["project_project.name"]
    description = record["project_project.description"]
    start_date = record["project_project.start_date"]

    organisation = record["project_project.organisation_id"]
    organisation_id = raw["project_project.organisation_id"]
    location = record["project_location.location_id"]

    org_url = URL(c="org", f="organisation", args=[organisation_id, "profile"])
    org_logo = raw["org_organisation.logo"]
    if org_logo:
        org_logo = A(IMG(_src=URL(c="default", f="download", args=[org_logo]),
                         _class="media-object",
                         ),
                     _href=org_url,
                     _class="pull-left",
                     )
    else:
        # @ToDo: use a dummy logo image
        org_logo = A(IMG(_class="media-object"),
                     _href=org_url,
                     _class="pull-left",
                     )

    # Edit Bar
    # @ToDo: Consider using S3NavigationItem to hide the auth-related parts
    permit = current.auth.s3_has_permission
    table = current.db.project_project
    if permit("update", table, record_id=record_id):
        edit_btn = A(ICON("edit"),
                     _href=URL(c="project", f="project",
                               args=[record_id, "update.popup"]
                               ),
                     _class="s3_modal",
                     _title=get_crud_string(resource.tablename,
                                            "title_update"),
                     )
    else:
        edit_btn = ""
    if permit("delete", table, record_id=record_id):
        delete_btn = A(ICON("delete"),
                       _class="dl-item-delete",
                       _title=get_crud_string(resource.tablename,
                                              "label_delete_button"),
                       )
    else:
        delete_btn = ""
    edit_bar = DIV(edit_btn,
                   delete_btn,
                   _class="edit-bar fright",
                   )

    # Render the item
    item = DIV(DIV(ICON(icon),
                   SPAN(A(name,
                          _href =  URL(c="project", f="project",
                                       args=[record_id, "profile"])),
                        _class="card-title"),
                   SPAN(location, _class="location-title"),
                   SPAN(start_date, _class="date-title"),
                   edit_bar,
                   _class="card-header",
                   ),
               DIV(org_logo,
                   DIV(DIV((description or ""),
                           DIV(author or "",
                               " - ",
                               A(organisation,
                                 _href=org_url,
                                 _class="card-organisation",
                                 ),
                               _class="card-person",
                               ),
                           _class="media",
                           ),
                       _class="media-body",
                       ),
                   _class="media",
                   ),
               #docs,
               _class=item_class,
               _id=item_id,
               )

    return item

# =============================================================================
def project_activity_list_layout(list_id, item_id, resource, rfields, record,
                                 icon="activity"):
    """
        Default dataList item renderer for Incidents on Profile pages

        Args:
            list_id: the HTML ID of the list
            item_id: the HTML ID of the item
            resource: the CRUDResource to render
            rfields: the S3ResourceFields to render
            record: the record as dict
    """

    raw = record._row
    record_id = raw["project_activity.id"]
    item_class = "thumbnail"

    author = record["project_activity.modified_by"]
    #date = record["project_activity.modified_on"]

    name = record["project_activity.name"]
    description = record["project_activity.comments"]
    start_date = record["project_activity.date"]

    location = record["project_activity.location_id"]

    organisation_id = raw["project_activity_organisation.organisation_id"]
    if organisation_id:
        organisation = record["project_activity_organisation.organisation_id"]
        org_url = URL(c="org", f="organisation", args=[organisation_id, "profile"])
        org_logo = raw["org_organisation.logo"]
        if org_logo:
            org_logo = A(IMG(_src=URL(c="default", f="download", args=[org_logo]),
                             _class="media-object",
                             ),
                         _href=org_url,
                         _class="pull-left",
                         )
        else:
            # @ToDo: use a dummy logo image
            org_logo = A(IMG(_class="media-object"),
                         _href=org_url,
                         _class="pull-left",
                         )
        organisation = A(organisation,
                         _href=org_url,
                         _class="card-organisation",
                         )
    else:
        organisation = ""

    # Edit Bar
    # @ToDo: Consider using S3NavigationItem to hide the auth-related parts
    permit = current.auth.s3_has_permission
    table = current.db.project_activity
    if permit("update", table, record_id=record_id):
        edit_btn = A(ICON("edit"),
                     _href=URL(c="project", f="activity",
                               args=[record_id, "update.popup"],
                               vars={"refresh": list_id,
                                     "record": record_id},
                               ),
                     _class="s3_modal",
                     _title=get_crud_string(resource.tablename,
                                               "title_update"),
                     )
    else:
        edit_btn = ""
    if permit("delete", table, record_id=record_id):
        delete_btn = A(ICON("delete"),
                       _class="dl-item-delete",
                       _title=get_crud_string(resource.tablename,
                                                 "label_delete_button"),
                       )
    else:
        delete_btn = ""
    edit_bar = DIV(edit_btn,
                   delete_btn,
                   _class="edit-bar fright",
                   )

    # Render the item
    item = DIV(DIV(ICON(icon),
                   SPAN(location, _class="location-title"),
                   SPAN(start_date, _class="date-title"),
                   edit_bar,
                   _class="card-header",
                   ),
               DIV(DIV(A(name,
                          _href=URL(c="project", f="activity",
                                    args=[record_id, "profile"])),
                        _class="card-title"),
                   DIV(DIV((description or ""),
                           DIV(author or "",
                               " - ",
                               organisation,
                               _class="card-person",
                               ),
                           _class="media",
                           ),
                       _class="media-body",
                       ),
                   _class="media",
                   ),
               #docs,
               _class=item_class,
               _id=item_id,
               )

    return item

# =============================================================================
def project_task_list_layout(list_id, item_id, resource, rfields, record,
                             icon="tasks"):
    """
        Default dataList item renderer for Tasks on Profile pages

        Args:
            list_id: the HTML ID of the list
            item_id: the HTML ID of the item
            resource: the CRUDResource to render
            rfields: the S3ResourceFields to render
            record: the record as dict
    """

    raw = record._row
    record_id = raw["project_task.id"]
    item_class = "thumbnail"

    author = record["project_task.modified_by"]

    name = record["project_task.name"]
    assigned_to = record["project_task.pe_id"] or ""
    description = record["project_task.description"]
    date_due = record["project_task.date_due"]
    source_url = raw["project_task.source_url"]
    status = raw["project_task.status"]
    priority = raw["project_task.priority"]

    project_id = raw["project_task.project_id"]
    if project_id:
        project = record["project_task.project_id"]
        project = SPAN(A(project,
                         _href = URL(c="project", f="project",
                                     args=[project_id, "profile"])
                         ),
                       " > ",
                       _class="task_project_title"
                       )
    else:
        project = ""

    if priority in (1, 2):
        # Urgent / High
        priority_icon = DIV(ICON("exclamation"),
                            _class="task_priority")
    elif priority == 4:
        # Low
        priority_icon = DIV(ICON("arrow-down"),
                            _class="task_priority")
    else:
        priority_icon = ""
    # @ToDo: Support more than just the Wrike/MCOP statuses
    status_icon_colour = {2:  "#AFC1E5",
                          6:  "#C8D571",
                          7:  "#CEC1FF",
                          12: "#C6C6C6",
                          }
    active_statuses = current.s3db.project_task_active_statuses
    status_icon  = DIV(ICON("active" if status in active_statuses else "inactive"),
                       _class="task_status",
                       _style="background-color:%s" % (status_icon_colour.get(status, "none"))
                       )

    location = record["project_task.location_id"]

    org_logo = ""
    #org_url = URL(c="org", f="organisation", args=[organisation_id, "profile"])
    #org_logo = raw["org_organisation.logo"]
    #if org_logo:
    #    org_logo = A(IMG(_src=URL(c="default", f="download", args=[org_logo]),
    #                     _class="media-object",
    #                     ),
    #                 _href=org_url,
    #                 _class="pull-left",
    #                 )
    #else:
    #    # @ToDo: use a dummy logo image
    #    org_logo = A(IMG(_class="media-object"),
    #                 _href=org_url,
    #                 _class="pull-left",
    #                 )

    # Edit Bar
    # @ToDo: Consider using S3NavigationItem to hide the auth-related parts
    permit = current.auth.s3_has_permission
    table = current.db.project_task
    if permit("update", table, record_id=record_id):
        edit_btn = A(ICON("edit"),
                     _href=URL(c="project", f="task",
                               args=[record_id, "update.popup"],
                               vars={"refresh": list_id,
                                     "record": record_id},
                               ),
                     _class="s3_modal",
                     _title=get_crud_string(resource.tablename,
                                               "title_update"),
                     )
    else:
        edit_btn = ""
    if permit("delete", table, record_id=record_id):
        delete_btn = A(ICON("delete"),
                       _class="dl-item-delete",
                       _title=get_crud_string(resource.tablename,
                                                 "label_delete_button"),
                       )
    else:
        delete_btn = ""

    if source_url:
        source_btn =  A(ICON("link"),
                       _title=source_url,
                       _href=source_url,
                       _target="_blank"
                       )
    else:
        source_btn = ""

    edit_bar = DIV(edit_btn,
                   delete_btn,
                   source_btn,
                   _class="edit-bar fright",
                   )

    # Render the item
    item = DIV(DIV(ICON(icon),
                   SPAN(location, _class="location-title"),
                   SPAN(date_due, _class="date-title"),
                   edit_bar,
                   _class="card-header",
                   ),
               DIV(org_logo,
                   priority_icon,
                   DIV(project,
                        name, _class="card-title task_priority"),
                   status_icon,
                   DIV(DIV((description or ""),
                           DIV(author,
                               " - ",
                               assigned_to,
                               #A(organisation,
                               #  _href=org_url,
                               #  _class="card-organisation",
                               #  ),
                               _class="card-person",
                               ),
                           _class="media",
                           ),
                       _class="media-body",
                       ),
                   _class="media",
                   ),
               #docs,
               _class=item_class,
               _id=item_id,
               )

    return item

# =============================================================================
def task_notify(form):
    """
        If the task is assigned to someone then notify them
    """

    form_vars = form.vars
    record = form.record

    pe_id = form_vars.pe_id
    if not pe_id:
        # Not assigned to anyone
        return

    user = current.auth.user
    if user and user.pe_id == pe_id:
        # Don't notify the user when they assign themselves tasks
        return

    status = form_vars.status
    if status is not None:
        status = int(status)
    else:
        if record and "status" in record:
            status = record.status
        else:
            table = current.s3db.project_task
            status = table.status.default

    if status not in current.response.s3.project_task_active_statuses:
        # No need to notify about closed tasks
        return

    if record is None or (int(pe_id) != record.pe_id):
        # Assignee has changed
        settings = current.deployment_settings

        if settings.has_module("msg"):
            # Notify assignee
            subject = "%s: Task assigned to you" % settings.get_system_name_short()
            url = "%s%s" % (settings.get_base_public_url(),
                            URL(c="project", f="task", args=[form_vars.id]))

            priority = form_vars.priority
            if priority is not None:
                priority = current.s3db.project_task.priority.represent(int(priority))
            else:
                priority = "unknown"

            message = "You have been assigned a Task:\n\n%s\n\n%s\n\n%s\n\n%s" % \
                            (url,
                             "%s priority" % priority,
                             form_vars.name,
                             form_vars.description or "")

            current.msg.send_by_pe_id(pe_id, subject, message)

# END =========================================================================

