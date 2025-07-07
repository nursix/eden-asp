"""
    User Preferences

    Copyright: 2025 (c) Sahana Software Foundation

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

__all__ = ("SavedFilterModel",
           "ColumnConfigModel",
           #"UserPreferencesModel",
           )

from gluon import *
from gluon.storage import Storage

from ..core import *

# =============================================================================
class SavedFilterModel(DataModel):
    """ Saved Filters """

    names = ("usr_filter",
             "usr_filter_id",
             )

    def model(self):

        T = current.T

        # ---------------------------------------------------------------------
        tablename = "usr_filter"
        self.define_table(tablename,
                          self.super_link("pe_id", "pr_pentity"),
                          Field("title"),
                          # Controller/Function/Resource/URL are used just
                          # for Saved Filters
                          Field("controller"),
                          Field("function"),
                          Field("resource"), # tablename
                          Field("url"),
                          Field("description", "text"),
                          # Query is used for both Saved Filters and Subscriptions
                          # Can use a Context to have this work across multiple
                          # resources if a simple selector is insufficient
                          Field("query", "text"),
                          Field("serverside", "json",
                                readable = False,
                                writable = False,
                                ),
                          CommentsField(),
                          )

        represent = S3Represent(lookup=tablename, fields=["title"])
        filter_id = FieldTemplate("filter_id", "reference %s" % tablename,
                                  label = T("Filter"),
                                  ondelete = "SET NULL",
                                  represent = represent,
                                  requires = IS_EMPTY_OR(
                                                IS_ONE_OF(current.db, "usr_filter.id",
                                                          represent,
                                                          orderby="usr_filter.title",
                                                          sort=True,
                                                          )),
                                  )

        self.configure(tablename,
                       listadd = False,
                       list_fields = ["title",
                                      "resource",
                                      "url",
                                      "query",
                                      ],
                       onvalidation = self.filter_onvalidation,
                       orderby = "usr_filter.resource",
                       )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return {"usr_filter_id": filter_id,
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def filter_onvalidation(form):
        """
            Ensure that JSON can be loaded by json.loads()
        """

        query = form.vars.get("query", None)
        if query:
            query = query.replace("'", "\"")
            try:
                json.loads(query)
            except ValueError as e:
                form.errors.query = "%s: %s" % (current.T("Query invalid"), e)
            form.vars.query = query

# =============================================================================
class ColumnConfigModel(DataModel):
    """ Model for saved datatable column configurations """

    names = ("usr_columns",
             )

    def model(self):

        # ---------------------------------------------------------------------
        # Datatable column configuration
        #
        tablename = "usr_columns"
        self.define_table(tablename,
                          Field("user_id", current.auth.settings.table_user),
                          Field("name"),
                          Field("controller"),
                          Field("function"),
                          Field("tablename"),
                          Field("columns", "json"),
                          )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        # return {}

# =============================================================================
# TODO
#class UserPreferencesModel(DataModel):
#    pass
#
# END =========================================================================
