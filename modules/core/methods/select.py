"""
    Bulk-action Datatable

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

from gluon import current, redirect

from ..filters import FilterForm
from ..tools import FormKey, get_crud_string

from .base import CRUDMethod
from .crud import BasicCRUD

__all__ = ("Select",
           )

# =============================================================================
class Select(CRUDMethod):
    """
        CRUD method to select and perform actions on multiple records
    """

    # -------------------------------------------------------------------------
    def apply_method(self, r, **attr):
        """
            Entry point for REST API

            Args:
                r: the CRUDRequest
                attr: dict of controller parameters

            Returns:
                output data for view
        """

        if r.http == "GET":
            output = self.select(r, **attr)
        elif r.http == "POST":
            if r.ajax or r.representation == "json":
                output = self.submit_ajax(r, **attr)
            else:
                output = self.submit(r, **attr)
        else:
            r.error(405, current.ERROR.BAD_METHOD)

        return output

    # -------------------------------------------------------------------------
    def select(self, r, **attr):
        """
            Filterable datatable with select-option

            Args:
                r: the CRUDRequest
                attr: dict of controller parameters
        """

        # Check permission to read in this table
        authorised = self._permitted()
        if not authorised:
            r.unauthorised()

        resource = self.resource

        get_config = resource.get_config

        representation = r.representation
        if representation in ("html", "aadata"):

            hide_filter = self.hide_filter
            filter_widgets = get_config("filter_widgets", None)

            # Handle default filters
            show_filter_form = False
            if filter_widgets and not hide_filter and \
               representation not in ("aadata", "dl"):
                show_filter_form = True
                # Apply filter defaults (before rendering the data!)
                from ..filters import FilterForm
                default_filters = FilterForm.apply_filter_defaults(r, resource)
            else:
                default_filters = None

            get_vars = r.get_vars
            attr = dict(attr)

            dtargs = attr.get("dtargs", {})

            # Configure bulk selection and actions
            actions = self.actions(resource)
            if actions:
                dtargs["dt_bulk_actions"] = actions
            else:
                # Render the select column in any case
                dtargs["dt_bulk_actions"] = True

            # Generate XSRF token
            formkey = FormKey("select/%s" % resource.tablename)
            dtargs["dt_formkey"] = formkey.generate()

            # Configure filter behavior
            if filter_widgets and not hide_filter:
                # Hide datatable filter box if we have a filter form
                if "dt_searching" not in dtargs:
                    dtargs["dt_searching"] = False
                # Set Ajax URL
                ajax_vars = dict(get_vars)
                if default_filters:
                    ajax_vars.update(default_filters)
                dtargs["dt_ajax_url"] = r.url(representation="aadata", vars=ajax_vars)

            attr["dtargs"] = dtargs

            # Render the datatable
            output = self._datatable(r, **attr)

            if representation == "aadata":
                # Done here if responding to Ajax-update request
                return output

            # ----- Page rendering only -----

            # Set list type (using list_filter.html view template)
            output["list_type"] = "datatable"

            # Page title
            if r.component:
                title = get_crud_string(r.tablename, "title_display")
            else:
                title = get_crud_string(self.tablename, "title_list")
            output["title"] = title

            # Filter-form
            if show_filter_form:
                output["list_filter_form"] = self.filters(r, **attr)
            else:
                # Render as empty string to avoid the exception in the view
                output["list_filter_form"] = ""

            # Inject static scripts for bulk actions as required
            if actions:
                self.inject_scripts(actions)

        else:
            r.error(415, current.ERROR.BAD_FORMAT)

        return output

    # -------------------------------------------------------------------------
    @classmethod
    def actions(cls, resource):
        """
            Returns the bulk action configuration for the datatable
        """

        return resource.get_config("bulk_actions")

    # -------------------------------------------------------------------------
    @classmethod
    def inject_scripts(cls, actions):
        """
            Injects any static JavaScript required by the bulk actions

            Args:
                actions - the bulk action configuration (list)
        """

        scripts = current.response.s3.scripts

        for action in actions:

            if not isinstance(action, dict):
                continue

            # Get the list of script URLs required for this action
            script_urls = action.get("script")
            if not script_urls:
                continue
            if not isinstance(script_urls, (tuple, list)):
                script_urls = [script_urls]

            # Inject the scripts
            for script_url in script_urls:
                if isinstance(script_url, str) and script_url not in scripts:
                    scripts.append(script_url)

    # -------------------------------------------------------------------------
    def submit(self, r, **attr):
        """
            Handles bulk-action requested via Ajax; to be implemented in subclass

            Args:
                r: the CRUDRequest
                attr: dict of controller parameters
        """

        # Resource comes in pre-filtered
        resource = self.resource

        # Read action-specific key/value, mode, and selected from post_vars
        #post_vars = r.post_vars
        #value = post_vars[key]          # an action-specific key/value-pair
        #mode = post_vars.mode           # "Exclusive"|"Inclusive"
        #selected = post_vars.selected   # Comma-separated string with record IDs

        # Verify the XSRF token
        # => the datatable form key [formname="select/<tablename>"]
        #    for mode=submit, or mode=ajax without dialog
        # => the dialog form key
        #    for mode=ajax with dialog, if the dialog has its own form key
        #    otherwise the datatable form key [formname="select/<tablename>"]
        #formkey = FormKey("select/%s" % resource.tablename)
        #if not formkey.verify(r.post_vars):
        #    r.unauthorised()

        # Execute the bulk action
        #pass

        # Redirect (to select view)
        redirect(r.url(vars={}))

    # -------------------------------------------------------------------------
    def submit_ajax(self, r, **attr):
        """
            Handles bulk-action requested via Ajax; to be implemented in subclass

            Args:
                r: the CRUDRequest
                attr: dict of controller parameters
        """

        # Resource comes in pre-filtered
        resource = self.resource

        # Read+parse body JSON
        #import json
        #from ..tools import JSONERRORS
        #s = r.body
        #s.seek(0)
        #try:
        #    options = json.load(s)
        #except JSONERRORS:
        #    options = None
        #if not isinstance(options, dict):
        #    r.error(400, "Invalid request options")

        # Read action-specific key/value, mode, and selected from options
        #value = options[key]             # an action-specific key/value-pair
        #mode = options["mode"]           # "Exclusive"|"Inclusive"
        #selected = options["selected"]   # Comma-separated string with record IDs

        # --- for direct execution of the action ---

        # Verify the XSRF token (with formname="select/<tablename>")
        #formkey = FormKey("select/%s" % resource.tablename)
        #if not formkey.verify(options, invalidate=False):
        #    r.unauthorised()

        # Execute the bulk action
        #pass

        # Return a JSON message
        return current.xml.json_message()

        # --- for using a dialog for additional user input ---

        # Construct a FORM for the dialog
        #from gluon import FORM, BUTTON, INPUT
        #formkey = FormKey("bulkaction/%s" % resource.tablename)
        #form = FORM(BUTTON("Submit", _type="submit", _class="primary button action-btn"),
        #            # Can add a _formkey hidden input here to authorize the actual action
        #            # - otherwise the select/<tablename> form key is used when submitting the dialog
        #            INPUT(_type="hidden", _name="_formkey", _value=formkey.generate()),
        #            # Can override the URL to which the dialog is submitted
        #            _action = r.url(vars={}, representation=""),
        #            )

        # Produce a JSON output with the dialog contents HTML as string
        #output = {"dialog": form.xml()}

        # Set Content Type
        #current.response.headers["Content-Type"] = "application/json"

        # Return JSON output
        #return json.dumps(output)

    # -------------------------------------------------------------------------
    def filters(self, r, **attr):
        """
            Generates a filter form for the data table

            Args:
                r: the CRUDRequest
                attr: dict of controller parameters
        """

        get_vars = r.get_vars

        resource = self.resource
        get_config = resource.get_config

        filter_ajax = True
        filter_widgets = get_config("filter_widgets")
        target = attr.get("list_id", "datatable")

        # Where to retrieve filtered data from:
        filter_submit_url = attr.get("filter_submit_url")
        if not filter_submit_url:
            get_vars_ = self._remove_filters(get_vars)
            filter_submit_url = r.url(vars=get_vars_)

        # Where to retrieve updated filter options from:
        filter_ajax_url = attr.get("filter_ajax_url")
        if filter_ajax_url is None:
            filter_ajax_url = r.url(method = "filter",
                                    vars = {},
                                    representation = "options",
                                    )
        filter_clear = get_config("filter_clear",
                                    current.deployment_settings.get_ui_filter_clear())
        filter_formstyle = get_config("filter_formstyle", None)
        filter_submit = get_config("filter_submit", True)
        filter_form = FilterForm(filter_widgets,
                                 clear = filter_clear,
                                 formstyle = filter_formstyle,
                                 submit = filter_submit,
                                 ajax = filter_ajax,
                                 url = filter_submit_url,
                                 ajaxurl = filter_ajax_url,
                                 _class = "filter-form",
                                 _id = "%s-filter-form" % target
                                 )
        fresource = current.s3db.resource(resource.tablename) # Use a clean resource
        if resource.parent and r.record:
            # We're on a component tab: filter by primary record so that
            # option lookups are limited to relevant component entries
            pkey = resource.parent.table._id
            join = (pkey == r.record[pkey]) & resource.get_join(reverse=True)
            fresource.add_filter(join)

        alias = resource.alias if r.component else None

        return filter_form.html(fresource,
                                get_vars,
                                target = target,
                                alias = alias
                                )

    # -------------------------------------------------------------------------
    def _datatable(self, r, **attr):
        """
            Produces the data table

            Args:
                r: the CRUDRequest
                attr: parameters for the method handler
        """

        resource = self.resource
        get_config = resource.get_config

        # Get table-specific parameters
        linkto = get_config("linkto", None)

        # List ID
        list_id = attr.get("list_id", "datatable")

        # List fields
        list_fields = resource.list_fields()

        # Default orderby
        orderby = get_config("orderby", None)

        response = current.response
        s3 = response.s3
        representation = r.representation

        # Pagination
        get_vars = self.request.get_vars
        if representation == "aadata":
            start, limit = self._limits(get_vars)
        else:
            # Initial page request always uses defaults (otherwise
            # filtering and pagination would have to be relative to
            # the initial limits, but there is no use-case for that)
            start = None
            limit = None if s3.no_sspag else 0

        # Initialize output
        output = {}

        # Linkto
        if not linkto:
            linkto = BasicCRUD._linkto(r)

        left = []
        dtargs = attr.get("dtargs", {})

        if r.interactive:

            # How many records per page?
            settings = current.deployment_settings
            display_length = settings.get_ui_datatables_pagelength()

            # Server-side pagination?
            if not s3.no_sspag:
                dt_pagination = True
                if not limit:
                    limit = 2 * display_length if display_length >= 0 else None
                current.session.s3.filter = get_vars
                if orderby is None:
                    dt_sorting = {"iSortingCols": "1",
                                  "sSortDir_0": "asc"
                                  }

                    if len(list_fields) > 1:
                        dt_sorting["bSortable_0"] = "false"
                        dt_sorting["iSortCol_0"] = "1"
                    else:
                        dt_sorting["bSortable_0"] = "true"
                        dt_sorting["iSortCol_0"] = "0"

                    orderby, left = resource.datatable_filter(list_fields,
                                                              dt_sorting,
                                                              )[1:3]
            else:
                dt_pagination = False

            # Get the data table
            dt, totalrows = resource.datatable(fields = list_fields,
                                               start = start,
                                               limit = limit,
                                               left = left,
                                               orderby = orderby,
                                               distinct = False,
                                               list_id = list_id,
                                               )
            displayrows = totalrows

            dtargs["dt_pagination"] = dt_pagination
            dtargs["dt_pageLength"] = display_length
            dtargs["dt_base_url"] = r.url(method="", vars={})
            dtargs["dt_list_url"] = r.url(method="", vars={})
            datatable = dt.html(totalrows, displayrows, **dtargs)

            # View + data
            response.view = self._view(r, "list_filter.html")
            output["items"] = datatable

        elif representation == "aadata":

            # Apply datatable filters
            searchq, orderby, left = resource.datatable_filter(list_fields,
                                                               get_vars)
            if searchq is not None:
                totalrows = resource.count()
                resource.add_filter(searchq)
            else:
                totalrows = None

            # Orderby fallbacks
            if orderby is None:
                orderby = get_config("orderby", None)

            # Get a data table
            if totalrows != 0:
                dt, displayrows = resource.datatable(fields = list_fields,
                                                     start = start,
                                                     limit = limit,
                                                     left = left,
                                                     orderby = orderby,
                                                     distinct = False,
                                                     list_id = list_id,
                                                     )
            else:
                dt, displayrows = None, 0
            if totalrows is None:
                totalrows = displayrows

            # Echo
            draw = int(get_vars.get("draw", 0))

            # Representation
            if dt is not None:
                output = dt.json(totalrows, displayrows, draw, **dtargs)
            else:
                output = '{"recordsTotal":%s,' \
                         '"recordsFiltered":0,' \
                         '"draw":%s,' \
                         '"data":[]}' % (totalrows, draw)

        else:
            r.error(415, current.ERROR.BAD_FORMAT)

        return output


# END =========================================================================
