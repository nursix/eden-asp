"""
    RLPPTM Test Station Management Journal

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

__all__ = ("ManagementJournalModel",
           )

from gluon import current, Field, IS_IN_SET, IS_NOT_EMPTY
from gluon.storage import Storage

from core import DataModel, DateTimeField, WorkflowOptions, \
                 CustomForm, InlineComponent, \
                 get_form_record_id, s3_comments_widget, \
                 s3_text_represent

# =============================================================================
# Status Options
#
ISSUE_STATUS = WorkflowOptions(("OPEN", "Open##status", "blue"),
                               ("CLOSED", "Closed##status", "grey"),
                               represent = "status",
                               )

# =============================================================================
class ManagementJournalModel(DataModel):
    """ Simple issue tracker / journal for test station management """

    names = ("jnl_issue",
             "jnl_note",
             )

    def model(self):

        T = current.T

        crud_strings = current.response.s3.crud_strings

        define_table = self.define_table
        configure = self.configure

        # ---------------------------------------------------------------------
        # Issue
        #
        tablename = "jnl_issue"
        define_table(tablename,
                     self.super_link("doc_id", "doc_entity"),
                     self.org_organisation_id(default=None),
                     self.org_site_id(),
                     DateTimeField(default="now"),
                     Field("name",
                           label = T("Subject"),
                           requires = IS_NOT_EMPTY(),
                           ),
                     Field("description", "text",
                           label = T("Description"),
                           widget = s3_comments_widget,
                           represent = s3_text_represent,
                           ),
                     Field("status",
                           label = T("Status"),
                           default = "OPEN",
                           requires = IS_IN_SET(ISSUE_STATUS.selectable(),
                                                sort = False,
                                                zero = None,
                                                ),
                           represent = ISSUE_STATUS.represent,
                           ),
                     DateTimeField("closed_on",
                                   label = T("Closed on"),
                                   writable = False,
                                   ),
                     )

        # Components
        self.add_components(tablename,
                            jnl_note = {"name": "jnl_note",
                                        "joinby": "issue_id",
                                        },
                            )

        # CRUD form
        crud_form = CustomForm(
                        "date",
                        "site_id",
                        "name",
                        "description",
                        "status",
                        InlineComponent(
                            "jnl_note",
                            name = "note",
                            label = T("Notes"),
                            fields = ["date", "note_text"],
                            explicit_add = T("Add note"),
                            ),
                        InlineComponent(
                            "document",
                            name = "file",
                            label = T("Documents"),
                            fields = ["date", "name", "file", "comments"],
                            filterby = {"field": "file",
                                        "options": "",
                                        "invert": True,
                                        },
                            explicit_add = T("Add document"),
                            ),
                        )

        # List fields
        list_fields = ["date",
                       "name",
                       "description",
                       "status",
                       ]

        subheadings = {"date": T("Description"),
                       "notejnl_note": T("Notes"),
                       "filedocument": T("Attachments"),
                       }


        # Table configuration
        configure(tablename,
                  crud_form = crud_form,
                  list_fields = list_fields,
                  onaccept = self.issue_onaccept,
                  orderby = "%s.date desc" % tablename,
                  subheadings = subheadings,
                  super_entity = "doc_entity",
                  )

        # CRUD strings
        crud_strings[tablename] = Storage(
            label_create = T("Create Issue"),
            title_display = T("Issue Details"),
            title_list = T("Issues"),
            title_update = T("Edit Issue"),
            label_list_button = T("List Issues"),
            label_delete_button = T("Delete Issue"),
            msg_record_created = T("Issue added"),
            msg_record_modified = T("Issue updated"),
            msg_record_deleted = T("Issue deleted"),
            msg_list_empty = T("No Issues currently registered"),
            )

        # ---------------------------------------------------------------------
        # Note
        #
        tablename = "jnl_note"
        define_table(tablename,
                     Field("issue_id", "reference jnl_issue",
                           ondelete = "CASCADE",
                           ),
                     DateTimeField(
                            default="now",
                            ),
                     Field("note_text", "text",
                           label = T("Note"),
                           requires = IS_NOT_EMPTY(),
                           represent = s3_text_represent,
                           ),
                     )

        # Table configuration
        configure(tablename,
                  orderby = "%s.date asc" % tablename,
                  )

    #--------------------------------------------------------------------------
    @staticmethod
    def issue_onaccept(form):
        """
            Onaccept of issue:
                - set closed_on date if status != OPEN
        """

        record_id = get_form_record_id(form)
        if not record_id:
            return

        db = current.db
        s3db = current.s3db

        table = s3db.jnl_issue
        query = (table.id == record_id)
        record = db(query).select(table.id,
                                  table.organisation_id,
                                  table.site_id,
                                  table.status,
                                  table.closed_on,
                                  limitby = (0, 1),
                                  ).first()

        if not record:
            return

        update, update_realm = {}, False

        # Add organisation_id if missing
        if record.site_id and not record.organisation_id:
            stable = s3db.org_site
            query = (stable.site_id == record.site_id)
            site = db(query).select(stable.organisation_id,
                                    limitby = (0, 1),
                                    ).first()
            if site:
                update["organisation_id"] = site.organisation_id
                update_realm = True

        # Update closed_on date according to status
        if record.status == "OPEN":
            update["closed_on"] = None
        elif not record.closed_on:
            update["closed_on"] = current.request.utcnow

        if update:
            record.update_record(**update)
        if update_realm:
            current.auth.set_realm_entity(table, record, force_update=True)

# END =========================================================================
