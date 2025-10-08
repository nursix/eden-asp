"""
    Extensible Generic CRUD Controller

    Copyright: 2009-2022 (c) Sahana Software Foundation

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

__all__ = ("CRUDRequest",
           "crud_request",
           "crud_controller",
           )

import json
import os
import sys

from io import StringIO

from gluon import current, redirect, A, HTTP, URL
from gluon.storage import Storage

from .resource import CRUDResource
from .tools import get_crud_string, s3_get_extension, s3_keep_messages, \
                   set_last_record_id, s3_str

HTTP_METHODS = ("GET", "PUT", "POST", "DELETE")

# =============================================================================
class CRUDRequest:
    """
        Class to handle CRUD requests
    """

    INTERACTIVE_FORMATS = ("html", "iframe", "popup", "dl")
    DEFAULT_REPRESENTATION = "html"

    # -------------------------------------------------------------------------
    def __init__(self,
                 prefix = None,
                 name = None,
                 r = None,
                 c = None,
                 f = None,
                 args = None,
                 vars = None,
                 extension = None,
                 get_vars = None,
                 post_vars = None,
                 http = None,
                 ):
        """
            Args:
                prefix: the table name prefix
                name: the table name
                c: the controller prefix
                f: the controller function
                args: list of request arguments
                vars: dict of request variables
                extension: the format extension (representation)
                get_vars: the URL query variables (overrides vars)
                post_vars: the POST variables (overrides vars)
                http: the HTTP method (GET, PUT, POST, or DELETE)

            Note:
                All parameters fall back to the attributes of the current
                web2py request object.
        """

        # XSLT Paths
        self.XSLT_PATH = "static/formats"
        self.XSLT_EXTENSION = "xsl"

        # Allow override of controller/function
        self.controller = c or self.controller
        self.function = f or self.function

        # Format extension
        request = current.request
        if "." in self.function:
            self.function, ext = self.function.split(".", 1)
            if extension is None:
                extension = ext
        self.extension = extension or request.extension

        # Check permission
        auth = current.auth
        if c or f:
            if not auth.permission.has_permission("read",
                                                  c = self.controller,
                                                  f = self.function):
                auth.permission.fail()


        # HTTP method
        self.http = http or request.env.request_method

        # Attached files
        self.files = Storage()

        # Allow override of request args/vars
        if args is not None:
            self.args = args if isinstance(args, (list, tuple)) else [args]

        if get_vars is not None or post_vars is not None:

            self.vars = request_vars = Storage()

            if get_vars is not None:
                self.get_vars = Storage(get_vars)
            request_vars.update(self.get_vars)

            if post_vars is not None:
                self.post_vars = Storage(post_vars)
            request_vars.update(self.post_vars)

        elif vars is not None:

            self.vars = self.get_vars = Storage(vars)
            self.post_vars = Storage()

        # Target table prefix/name
        if r is not None:
            if not prefix:
                prefix = r.prefix
            if not name:
                name = r.name
        self.prefix = prefix or self.controller
        self.name = name or self.function

        # Session filters
        self._search_id = None
        self.suppress_default_filters = False

        # Parse the request
        self.__parse()
        self.custom_action = None

        # Interactive representation format?
        self.interactive = self.representation in self.INTERACTIVE_FORMATS

        get_vars = self.get_vars

        # Show information on deleted records?
        include_deleted = False
        if self.representation == "xml" and "include_deleted" in get_vars:
            include_deleted = True

        # Which components to load?
        component_name = self.component_name
        if not component_name:
            if "components" in get_vars:
                cnames = get_vars["components"]
                if isinstance(cnames, list):
                    cnames = ",".join(cnames)
                cnames = cnames.split(",")
                if len(cnames) == 1 and cnames[0].lower() == "none":
                    cnames = []
                components = cnames
            else:
                components = None
        else:
            components = component_name

        # Append component ID to the URL query
        url_query = dict(get_vars)
        component_id = self.component_id
        if component_name and component_id:
            varname = "%s.id" % component_name
            if varname in get_vars:
                var = url_query[varname]
                if not isinstance(var, (list, tuple)):
                    var = [var]
                var.append(component_id)
                url_query[varname] = var
            else:
                url_query[varname] = component_id

        tablename = "%s_%s" % (self.prefix, self.name)

        # Handle approval settings
        if not current.deployment_settings.get_auth_record_approval():
            # Record Approval is off
            approved, unapproved = True, False
        elif self.method == "review":
            approved, unapproved = False, True
        elif auth.s3_has_permission("review", tablename, self.id):
            # Approvers should be able to edit records during review
            # @ToDo: deployment_setting to allow Filtering out from
            #        multi-record methods even for those with Review permission
            approved, unapproved = True, True
        else:
            approved, unapproved = True, False

        # Instantiate resource
        self.resource = CRUDResource(tablename,
                                     id = self.id,
                                     filter = current.response.s3.filter,
                                     vars = url_query,
                                     components = components,
                                     approved = approved,
                                     unapproved = unapproved,
                                     include_deleted = include_deleted,
                                     filter_component = component_name,
                                     )

        resource = self.resource
        self.tablename = resource.tablename
        table = self.table = resource.table

        # Try to load the master record
        self.record = None
        uid = self.vars.get("%s.uid" % self.name)
        if self.id or uid and not isinstance(uid, (list, tuple)):
            # Single record expected
            resource.load()
            if len(resource) == 1:
                self.record = resource.records().first()
                self.id = self.record[table._id.name]
                set_last_record_id(self.tablename, self.id)
            else:
                raise KeyError(current.ERROR.BAD_RECORD)

        # Identify the component
        self.component = component = None
        if component_name:
            c = resource.components.get(component_name)
            if c:
                self.component = component = c
            else:
                error = "%s not a component of %s" % \
                        (self.component_name, self.tablename)
                raise AttributeError(error)

        # Identify link table and link ID
        link = link_id = None
        if component is not None:
            link = component.link
        if link and self.id and self.component_id:
            link_id = link.link_id(self.id, self.component_id)
            if link_id is None:
                raise KeyError(current.ERROR.BAD_RECORD)
        self.link = link
        self.link_id = link_id

        # Initialize default methods
        self._default_methods = None

        # Initialize next-URL
        self.next = None

    # -------------------------------------------------------------------------
    # Request Parser
    # -------------------------------------------------------------------------
    def __parse(self):
        """ Parses the web2py request object """

        self.id = None
        self.component_name = None
        self.component_id = None
        self.method = None

        # Get the names of all components
        tablename = "%s_%s" % (self.prefix, self.name)

        # Map request args, catch extensions
        f = []
        append = f.append
        args = self.args
        if len(args) > 4:
            args = args[:4]
        method = self.name
        for arg in args:
            if "." in arg:
                arg, representation = arg.rsplit(".", 1)
            if method is None:
                method = arg
            elif arg.isdigit():
                append((method, arg))
                method = None
            else:
                append((method, None))
                method = arg
        if method:
            append((method, None))

        self.id = f[0][1]

        # Sort out component name and method
        l = len(f)
        if l > 1:
            m = f[1][0].lower()
            i = f[1][1]
            components = current.s3db.get_components(tablename, names=[m])
            if components and m in components:
                self.component_name = m
                self.component_id = i
            else:
                self.method = m
                if not self.id:
                    self.id = i
        if self.component_name and l > 2:
            self.method = f[2][0].lower()
            if not self.component_id:
                self.component_id = f[2][1]

        representation = s3_get_extension(self)
        if representation:
            self.representation = representation
        else:
            self.representation = self.DEFAULT_REPRESENTATION

        # Check for special URL variable $search, indicating that
        # the request explicitly specifies filters:
        search_mode = self.get_vars.pop("$search", None)
        if search_mode:
            # Apply filter expressions from POST data or session?
            if self.http == "POST" or search_mode == "session":
                self.__search(search_mode)
            # Suppress default filters in this case
            self.suppress_default_filters = True

    # -------------------------------------------------------------------------
    def __search(self, mode):
        """
            Applies filter expressions
            - from session with $search=session
            - from POST vars (if urlencoded), or
            - from JSON request body (if $search=ajax or not multipart)
            - from POST vars (if multipart)

            Note:
                Overrides CRUDRequest method as GET (r.http) to trigger
                the correct method handlers, but will not change
                current.request.env.request_method.
        """

        # Get session filters and search ID
        session = current.session
        session_filters = session.s3.filters
        if not session_filters:
            session_filters = session.s3.filters = {}
        search_id = self.search_id

        get_vars = self.get_vars
        content_type = self.env.get("content_type") or ""

        action = get_vars.pop("$action", None)

        # Override request method (unless marked as submit-action)
        if mode and action != "submit":
            self.http = "GET"

        # Retrieve filters
        if mode == "session":
            # Restore previous filters from session
            filters = session_filters.get(search_id)
            decode = None

        elif content_type == "application/x-www-form-urlencoded":
            # Read POST vars (e.g. from S3.gis.refreshLayer)
            filters = self.post_vars
            decode = None

        elif mode == "ajax" or content_type[:10] != "multipart/":
            # Read body JSON (e.g. from $.searchS3)
            body = self.body
            body.seek(0)
            # Decode request body (=bytes stream) into a str
            # - minor performance advantage by avoiding the need for
            #   json.loads to detect the encoding
            s = body.read().decode("utf-8")
            try:
                filters = json.loads(s)
            except ValueError:
                filters = None
            if not isinstance(filters, dict):
                filters = None
            decode = None

        else:
            # Read POST vars JSON (e.g. from $.searchDownloadS3)
            filters = self.post_vars
            decode = json.loads

        if filters is None:
            # No filters found
            return

        # Retrieve filter expressions
        get_vars = Storage(get_vars)
        post_vars = Storage(self.post_vars)
        filter_vars = {}
        for k, v in filters.items():
            k0 = k[0]
            if k == "$filter" or k[0:2] == "$$" or k == "bbox" or \
               k0 != "_" and ("." in k or k0 == "(" and ")" in k):
                try:
                    value = decode(v) if decode else v
                except ValueError:
                    continue
                # Catch any non-str values
                if isinstance(value, list):
                    value = [s3_str(item)
                             if not isinstance(item, str) else item
                             for item in value
                             ]
                elif not isinstance(value, str):
                    value = s3_str(value)

                filter_vars[s3_str(k)] = value
                # Remove filter expression from POST vars
                if k in post_vars:
                    del post_vars[k]

        # Move filter expressions into GET vars
        get_vars.update(filter_vars)

        # Store filters in session
        if search_id:
            session_filters[search_id] = filter_vars

        # Override self.get_vars and self.post_vars
        self.get_vars = get_vars
        self.post_vars = post_vars

        # Update combined vars
        self.vars = get_vars.copy()
        self.vars.update(self.post_vars)

    # -------------------------------------------------------------------------
    @property
    def search_id(self):
        """
            The search ID for this request (lazy property);
            the search ID can be used to restore previous filters applied
            to this page, using $search=session

            Returns:
                the search ID (str)
        """

        search_id = self._search_id
        if not search_id:
            array = [self.controller, self.function]
            if self.args:
                # Drop format extensions from args
                array.extend(arg.rsplit(".", 1)[0] for arg in self.args)

            string = "#".join(array)
            import hashlib
            self._search_id = search_id = hashlib.md5(string.encode("utf-8")).hexdigest()

        return search_id

    # -------------------------------------------------------------------------
    # Method handlers
    # -------------------------------------------------------------------------
    @property
    def default_methods(self):
        """
            Default method handlers as dict {method: handler}
        """

        methods = self._default_methods

        if not methods:
            from .methods import RESTful, FilterManager, ColumnConfigManager, \
                                 S3GroupedItemsReport, S3HierarchyCRUD, S3Map, \
                                 S3Merge, S3MobileCRUD, S3Organizer, S3Profile, \
                                 S3Report, S3Summary, S3XForms, \
                                 Select, SpreadsheetImporter, TimePlot

            methods = {"columns": ColumnConfigManager,
                       "deduplicate": S3Merge,
                       "fields": RESTful,
                       "filter": FilterManager,
                       "grouped": S3GroupedItemsReport,
                       "hierarchy": S3HierarchyCRUD,
                       "import": SpreadsheetImporter,
                       "map": S3Map,
                       "mform": S3MobileCRUD,
                       "options": RESTful,
                       "organize": S3Organizer,
                       "profile": S3Profile,
                       "report": S3Report,
                       "select": Select,
                       "summary": S3Summary,
                       "sync": current.sync,
                       "timeplot": TimePlot,
                       "xform": S3XForms,
                       }

            methods["copy"] = lambda r, **attr: redirect(URL(args = "create",
                                                             vars = {"from_record": r.id},
                                                             ))

            from .msg import S3Compose
            methods["compose"] = S3Compose

            from .ui import search_ac
            methods["search_ac"] = search_ac

            try:
                from s3db.cms import S3CMS
            except ImportError:
                current.log.error("S3CMS default method not found")
            else:
                methods["cms"] = S3CMS

            self._default_methods = methods

        return methods

    # -------------------------------------------------------------------------
    def get_widget_handler(self, method):
        """
            Get the widget handler for a method

            Args:
                r: the CRUDRequest
                method: the widget method
        """

        handler = None

        if method:
            handler = current.s3db.get_method(self.tablename,
                                              component = self.component_name,
                                              method = method,
                                              )
        if handler is None:
            if self.http == "GET" and not method:
                component = self.component
                if component:
                    resource = component.link if component.link else component
                else:
                    resource = self.resource
                method = "read" if resource.count() == 1 else "list"
            handler = self.default_methods.get(method)

        if handler is None:
            from .methods import BasicCRUD
            handler = BasicCRUD()

        return handler() if isinstance(handler, type) else handler

    # -------------------------------------------------------------------------
    # Controller
    # -------------------------------------------------------------------------
    def __call__(self, **attr):
        """
            Execute this request

            Args:
                attr: Controller parameters
        """

        response = current.response
        s3 = response.s3
        self.next = None

        bypass = False
        output = None
        preprocess = None
        postprocess = None

        representation = self.representation

        # Enforce primary record ID
        if not self.id and representation == "html":
            if self.component or self.method in ("read", "profile", "update"):
                count = self.resource.count()
                if self.vars is not None and count == 1:
                    self.resource.load()
                    self.record = self.resource._rows[0]
                    self.id = self.record.id
                else:
                    #current.session.error = current.ERROR.BAD_RECORD
                    redirect(URL(r=self, c=self.prefix, f=self.name))

        # Pre-process
        if s3 is not None:
            preprocess = s3.get("prep")
        if preprocess:
            pre = preprocess(self)
            # Re-read representation after preprocess:
            representation = self.representation
            if not pre:
                self.error(400, current.ERROR.BAD_REQUEST)
            elif isinstance(pre, dict):
                bypass = pre.get("bypass", False) is True
                output = pre.get("output")
                success = pre.get("success", True)
                if not bypass and not success:
                    if representation == "html" and output:
                        if isinstance(output, dict):
                            output["r"] = self
                        return output
                    status = pre.get("status", 400)
                    message = pre.get("message", current.ERROR.BAD_REQUEST)
                    self.error(status, message)

        # Default view
        if representation not in ("html", "popup"):
            response.view = "xml.html"

        # Content type
        response.headers["Content-Type"] = s3.content_type.get(representation,
                                                               "text/html")

        # Custom action?
        custom_action = self.custom_action
        if not custom_action:
            custom_action = current.s3db.get_method(self.tablename,
                                                    component = self.component_name,
                                                    method = self.method,
                                                    )
            self.custom_action = custom_action

        # Method handling
        http, method = self.http, self.method
        handler = None
        if not bypass:
            if custom_action:
                handler = custom_action
            else:
                handler = self.default_methods.get(method)
                if not handler:
                    m = "import" if http in ("PUT", "POST") else None
                    if not method and \
                       (http not in ("GET", "POST") or self.transformable(method=m)):
                        from .methods import RESTful
                        handler = RESTful
                    elif http in HTTP_METHODS:
                        from .methods import BasicCRUD
                        handler = BasicCRUD
                    else:
                        self.error(405, current.ERROR.BAD_METHOD)
            if isinstance(handler, type):
                handler = handler()
            output = handler(self, **attr)

        # Post-process
        if s3 is not None:
            postprocess = s3.get("postp")
        if postprocess is not None:
            output = postprocess(self, output)
        if output is not None and isinstance(output, dict):
            # Put a copy of r into the output for the view
            # to be able to make use of it
            output["r"] = self

        # Redirection
        # NB must re-read self.http/method here in case the have
        # been changed during prep, method handling or postp
        if self.next is not None and \
           (self.http != "GET" or self.method == "clear"):
            if isinstance(output, dict):
                form = output.get("form")
                if form:
                    if not hasattr(form, "errors"):
                        # Form embedded in a DIV together with other components
                        form = form.elements("form", first_only=True)
                        form = form[0] if form else None
                    if form and form.errors:
                        return output

            s3_keep_messages()
            redirect(self.next)

        return output

    # -------------------------------------------------------------------------
    # Tools
    # -------------------------------------------------------------------------
    def factory(self, **args):
        """
            Generate a new request for the same resource

            Args:
                args: arguments for request constructor
        """

        return crud_request(r=self, **args)

    # -------------------------------------------------------------------------
    def __getattr__(self, key):
        """
            Called upon CRUDRequest.<key> - looks up the value for the <key>
            attribute. Falls back to current.request if the attribute is
            not defined in this CRUDRequest.

            Args:
                key: the key to lookup
        """

        if key in self.__dict__:
            return self.__dict__[key]

        sentinel = object()
        value = getattr(current.request, key, sentinel)
        if value is sentinel:
            raise AttributeError
        return value

    # -------------------------------------------------------------------------
    def transformable(self, method=None):
        """
            Check the request for a transformable format

            Args:
                method: "import" for import methods, otherwise None
        """

        if self.representation in ("html", "aadata", "popup", "iframe"):
            return False

        stylesheet = self.stylesheet(method=method, skip_error=True)

        if not stylesheet and self.representation != "xml":
            return False
        else:
            return True

    # -------------------------------------------------------------------------
    def actuate_link(self, component_id=None):
        """
            Determine whether to actuate a link or not

            Args:
                component_id: the component_id (if not self.component_id)
        """

        if not component_id:
            component_id = self.component_id
        if self.component:
            single = component_id != None
            component = self.component
            if component.link:
                actuate = self.component.actuate
                if "linked" in self.get_vars:
                    linked = self.get_vars.get("linked", False)
                    linked = linked in ("true", "True")
                    if linked:
                        actuate = "replace"
                    else:
                        actuate = "hide"
                if actuate == "link":
                    if self.method != "delete" and self.http != "DELETE":
                        return single
                    else:
                        return not single
                elif actuate == "replace":
                    return True
                #elif actuate == "embed":
                    #raise NotImplementedError
                else:
                    return False
            else:
                return True
        else:
            return False

    # -------------------------------------------------------------------------
    @staticmethod
    def unauthorised():
        """ Action upon unauthorised request """

        current.auth.permission.fail()

    # -------------------------------------------------------------------------
    def error(self, status, message, tree=None, next=None):
        """
            Action upon error

            Args:
                status: HTTP status code
                message: the error message
                tree: the tree causing the error
        """

        if self.ajax or self.representation != "html":

            current.log.error(message)

            headers = {"Content-Type":"application/json"}
            body = current.xml.json_message(success = False,
                                            statuscode = status,
                                            message = message,
                                            tree = tree,
                                            )
            raise HTTP(status, body=body, web2py_error=message, **headers)

        current.session.error = message
        if next is not None:
            redirect(next)
        else:
            redirect(URL(r=self, f="index"))

    # -------------------------------------------------------------------------
    def url(self,
            id = None,
            component = None,
            component_id = None,
            target = None,
            method = None,
            representation = None,
            vars = None,
            host = None,
            ):
        """
            Returns the URL of this request, use parameters to override
            current requests attributes:
                - None to keep current attribute (default)
                - 0 or "" to set attribute to NONE
                - value to use explicit value

            Args:
                id: the master record ID
                component: the component name
                component_id: the component ID
                target: the target record ID (choose automatically)
                method: the URL method
                representation: the representation for the URL
                vars: the URL query variables
                host: string to force absolute URL with host (True means http_host)

            Notes:
                - changing the master record ID resets the component ID
                - removing the target record ID sets the method to None
                - removing the method sets the target record ID to None
                - [] as id will be replaced by the "[id]" wildcard
        """

        if vars is None:
            vars = self.get_vars
        elif vars and isinstance(vars, str):
            # We've come from a dataTable_vars which has the vars as
            # a JSON string, but with the wrong quotation marks
            vars = json.loads(vars.replace("'", "\""))

        if "format" in vars:
            del vars["format"]

        args = []

        cname = self.component_name

        # target
        if target is not None:
            if cname and (component is None or component == cname):
                component_id = target
            else:
                id = target

        # method
        default_method = False
        if method is None:
            default_method = True
            method = self.method
        elif method == "":
            # Switch to list? (= method="" and no explicit target ID)
            if component_id is None:
                if self.component_id is not None:
                    component_id = 0
                elif not self.component:
                    if id is None:
                        if self.id is not None:
                            id = 0
            method = None

        # id
        if id is None:
            id = self.id
        elif id in (0, ""):
            id = None
        elif id in ([], "[id]", "*"):
            id = "[id]"
            component_id = 0
        elif str(id) != str(self.id):
            component_id = 0

        # component
        if component is None:
            component = cname
        elif component == "":
            component = None
        if cname and cname != component or not component:
            component_id = 0

        # component_id
        if component_id is None:
            component_id = self.component_id
        elif component_id == 0:
            component_id = None
            if self.component_id and default_method:
                method = None

        if id is None and self.id and \
           (not component or not component_id) and default_method:
            method = None

        if id:
            args.append(id)
        if component:
            args.append(component)
        if component_id:
            args.append(component_id)
        if method:
            args.append(method)

        # representation
        if representation is None:
            representation = self.representation
        elif representation == "":
            representation = self.DEFAULT_REPRESENTATION
        f = self.function
        if not representation == self.DEFAULT_REPRESENTATION:
            if len(args) > 0:
                args[-1] = "%s.%s" % (args[-1], representation)
            else:
                f = "%s.%s" % (f, representation)

        return URL(r=self,
                   c=self.controller,
                   f=f,
                   args=args,
                   vars=vars,
                   host=host)

    # -------------------------------------------------------------------------
    def target(self):
        """
            Get the target table of the current request

            Returns:
                tuple of (prefix, name, table, tablename) of the target
                resource of this request

            TODO update for link table support
        """

        component = self.component
        if component is not None:
            link = self.component.link
            if link and not self.actuate_link():
                return(link.prefix,
                       link.name,
                       link.table,
                       link.tablename)
            return (component.prefix,
                    component.name,
                    component.table,
                    component.tablename)
        else:
            return (self.prefix,
                    self.name,
                    self.table,
                    self.tablename)

    # -------------------------------------------------------------------------
    @property
    def viewing(self):
        """
            Parse the "viewing" URL parameter, frequently used for
            perspective discrimination and processing in prep

            Returns:
                tuple (tablename, record_id) if "viewing" is set,
                otherwise None
        """

        get_vars = self.get_vars
        if "viewing" in get_vars:
            try:
                tablename, record_id = get_vars.get("viewing").split(".")
            except (AttributeError, ValueError):
                return None
            try:
                record_id = int(record_id)
            except (TypeError, ValueError):
                return None
            return tablename, record_id

        return None

    # -------------------------------------------------------------------------
    def has_form_error(self):
        """
            Checks for form errors in this request

            Returns:
                boolean
        """

        return (self.http == "POST" or self.env.request_method == "POST") and \
               bool(current.response.s3.form_error)

    # -------------------------------------------------------------------------
    def is_delete(self):
        """
            Checks whether this request is a deletion request

            Returns:
                boolean
        """

        http = self.http

        return self.method == "delete" or \
               http == "DELETE" or \
               http in ("POST", "DELETE") and self.representation == "dl" and "delete" in self.get_vars

    # -------------------------------------------------------------------------
    def stylesheet(self, method=None, skip_error=False):
        """
            Find the XSLT stylesheet for this request

            Args:
                method: "import" for data imports, else None
                skip_error: do not raise an HTTP error status
                            if the stylesheet cannot be found
        """

        representation = self.representation

        # Native S3XML?
        if representation == "xml":
            return None

        # External stylesheet specified?
        if "transform" in self.vars:
            return self.vars["transform"]

        component = self.component
        resourcename = component.name if component else self.name

        # Stylesheet attached to the request?
        extension = self.XSLT_EXTENSION
        filename = "%s.%s" % (resourcename, extension)
        if filename in self.post_vars:
            p = self.post_vars[filename]
            if hasattr(p, "file") and hasattr(p, "filename") and p.filename:
                return p.file

        # Look for stylesheet in file system
        folder = self.folder
        if method != "import":
            method = "export"
        stylesheet = None

        # Custom transformation stylesheet in template?
        if not stylesheet:
            formats = current.deployment_settings.get_xml_formats()
            if isinstance(formats, dict) and representation in formats:
                stylesheets = formats[representation]
                if isinstance(stylesheets, str) and stylesheets:
                    stylesheets = stylesheets.split("/") + ["formats"]
                    path = os.path.join("modules", "templates", *stylesheets)
                    filename = "%s.%s" % (method, extension)
                    stylesheet = os.path.join(folder, path, representation, filename)

        # Transformation stylesheet at standard location?
        if not stylesheet:
            path = self.XSLT_PATH
            filename = "%s.%s" % (method, extension)
            stylesheet = os.path.join(folder, path, representation, filename)

        if not os.path.exists(stylesheet):
            if not skip_error:
                self.error(501, "%s: %s" % (current.T("XSLT stylesheet not found"),
                                            stylesheet,
                                            ))
            stylesheet = None

        return stylesheet

    # -------------------------------------------------------------------------
    def read_body(self):
        """ Read data from request body """

        self.files = Storage()
        content_type = self.env.get("content_type")

        source = []
        if content_type and content_type.startswith("multipart/"):
            ext = ".%s" % self.representation
            post_vars = self.post_vars
            for v in post_vars:
                p = post_vars[v]
                is_upload = hasattr(p, "file") and hasattr(p, "filename")
                if is_upload and p.filename:
                    self.files[p.filename] = p.file
                    if p.filename.endswith(ext):
                        source.append((v, p.file))
                elif v.endswith(ext):
                    if is_upload:
                        source.append((v, p.value))
                    elif isinstance(p, str):
                        source.append((v, StringIO(p)))
        else:
            s = self.body
            s.seek(0)
            source.append(s)

        return source

    # -------------------------------------------------------------------------
    def customise_resource(self, tablename=None):
        """
            Invoke the customization callback for a resource.

            Args:
                tablename: the tablename of the resource; if called
                           without tablename it will invoke the callbacks
                           for the target resources of this request:
                            - master
                            - active component
                            - active link table
                              (in this order)

            Example:
                Resource customization functions can be defined like:

                def customise_resource_my_table(r, tablename):

                    current.s3db.configure(tablename,
                                           my_custom_setting = "example")

                settings.customise_resource_my_table = \
                                        customise_resource_my_table

            Notes:
                - the hook itself can call r.customise_resource in order
                  to cascade customizations as necessary
                - if a table is customised that is not currently loaded,
                  then it will be loaded for this process
        """

        if tablename is None:
            # Customise the current target resource(s)
            customise = self.customise_resource

            customise(self.resource.tablename)
            if self.component:
                customise(self.component.tablename)
            if self.link:
                customise(self.link.tablename)

            return

        s3db = current.s3db

        # Note: must load the model first, otherwise it would override
        #       the custom settings when loaded later
        if not s3db.customised(tablename) and s3db.table(tablename, db_only=True):

            customise = current.deployment_settings.customise_resource(tablename)
            if customise:
                customise(self, tablename)
            s3db.customised(tablename, True)

# =============================================================================
def crud_request(*args, **kwargs):
    """
        Helper function to generate CRUDRequest instances

        Args:
            args: arguments for the CRUDRequest
            kwargs: keyword arguments for the CRUDRequest

        Keyword Args:
            catch_errors: if set to False, errors will be raised
                          instead of returned to the client, useful
                          for optional sub-requests, or if the caller
                          implements fallbacks
    """

    catch_errors = kwargs.pop("catch_errors", True)

    error = None
    try:
        r = CRUDRequest(*args, **kwargs)
    except (AttributeError, SyntaxError):
        if catch_errors is False:
            raise
        error, message = 400, sys.exc_info()[1]
    except KeyError:
        if catch_errors is False:
            raise
        error, message = 404, sys.exc_info()[1]
    if error:
        if hasattr(message, "message"):
            message = message.message
        elif hasattr(message, "args"):
            message = message.args[0] if message.args else None
        message = s3_str(message) if message else "Unknown Error (%s)" % error
        if current.auth.permission.format == "html":
            current.session.error = message
            redirect(URL(f="index"))
        else:
            headers = {"Content-Type":"application/json"}
            current.log.error(message)
            raise HTTP(error,
                       body = current.xml.json_message(success = False,
                                                       statuscode = error,
                                                       message = message,
                                                       ),
                       web2py_error = message,
                       **headers)
    return r

# -----------------------------------------------------------------------------
def crud_controller(prefix=None, resourcename=None, **attr):
    """
        Helper function to apply CRUD methods

        Args:
            prefix: the application prefix
            resourcename: the resource name (without prefix)
            attr: additional keyword parameters

        Keyword Args:
            Any keyword parameters will be copied into the output dict (provided
            that the output is a dict). If a keyword parameter is callable, then
            it will be invoked, and its return value will be added to the output
            dict instead. The callable receives the CRUDRequest as its first and
            only parameter.

        CRUD can be configured per table using:

            s3db.configure(tablename, **attr)

        *** Redirection:

        create_next             URL to redirect to after a record has been created
        update_next             URL to redirect to after a record has been updated
        delete_next             URL to redirect to after a record has been deleted

        *** Form configuration:

        list_fields             list of names of fields to include into list views
        subheadings             Sub-headings (see separate documentation)
        listadd                 Enable/Disable add-form in list views

        *** CRUD configuration:

        editable                Allow/Deny record updates in this table
        deletable               Allow/Deny record deletions in this table
        insertable              Allow/Deny record insertions into this table
        copyable                Allow/Deny record copying within this table

        *** Callbacks:

        create_onvalidation     Function for additional record validation on create
        create_onaccept         Function after successful record insertion

        update_onvalidation     Function for additional record validation on update
        update_onaccept         Function after successful record update

        onvalidation            Fallback for both create_onvalidation and update_onvalidation
        onaccept                Fallback for both create_onaccept and update_onaccept
        ondelete                Function after record deletion
    """

    auth = current.auth
    s3db = current.s3db

    request = current.request
    response = current.response
    s3 = response.s3
    settings = current.deployment_settings

    # Parse the request
    dynamic = attr.get("dynamic")
    if dynamic:
        # Dynamic table controller
        c = request.controller
        f = request.function
        attr = settings.customise_controller("%s_%s" % (c, f), **attr)
        from core import DYNAMIC_PREFIX, s3_get_extension
        r = crud_request(DYNAMIC_PREFIX,
                         dynamic,
                         f = "%s/%s" % (f, dynamic),
                         args = request.args[1:],
                         extension = s3_get_extension(request),
                         )
    else:
        # Customise Controller from Template
        attr = settings.customise_controller(
                    "%s_%s" % (prefix or request.controller,
                               resourcename or request.function,
                               ),
                    **attr)
        r = crud_request(prefix, resourcename)

    # Customize target resource(s) from Template
    r.customise_resource()

    # List of methods rendering datatables with default action buttons
    dt_methods = (None, "datatable", "datatable_f", "select", "summary", "list")

    # List of methods rendering datatables with custom action buttons,
    # => for these, s3.actions must not be touched, see below
    # (defining here allows postp to add a custom method to the list)
    s3.action_methods = ("import",
                         "review",
                         "approve",
                         "reject",
                         "select",
                         "deduplicate",
                         )

    # Execute the request
    output = r(**attr)

    method = r.method
    if isinstance(output, dict) and method in dt_methods:

        if s3.actions is None:

            # Add default action buttons
            prefix, name, table, tablename = r.target()
            authorised = auth.s3_has_permission("update", tablename)

            # If a component has components itself, then action buttons
            # can be forwarded to the native controller by setting native=True
            if r.component and s3db.has_components(table):
                native = output.get("native", False)
            else:
                native = False

            # Get table config
            get_config = s3db.get_config
            listadd = get_config(tablename, "listadd", True)
            deletable = get_config(tablename, "deletable", True)
            copyable = get_config(tablename, "copyable", False)

            # Which is the standard open-action?
            from .methods import BasicCRUD
            editable = BasicCRUD._default_editable(table)

            # URL to open the resource
            open_url = BasicCRUD._linkto(r,
                                         authorised = authorised,
                                         update = editable,
                                         native = native)("[id]")

            # Add action buttons for Open/Delete/Copy as appropriate
            BasicCRUD.action_buttons(r,
                                     deletable = deletable,
                                     copyable = copyable,
                                     editable = editable,
                                     read_url = open_url,
                                     update_url = open_url
                                     # To use modals
                                     #update_url = "%s.popup?refresh=list" % open_url
                                     )

            # Override Add-button, link to native controller and put
            # the primary key into get_vars for automatic linking
            if native and not listadd and \
               auth.s3_has_permission("create", tablename):
                label = get_crud_string(tablename, "label_create")
                component = r.resource.components[name]
                fkey = "%s.%s" % (name, component.fkey)
                get_vars_copy = request.get_vars.copy()
                get_vars_copy.update({fkey: r.record[component.fkey]})
                url = URL(prefix, name,
                          args = ["create"],
                          vars = get_vars_copy,
                          )
                add_btn = A(label,
                            _href = url,
                            _class = "action-btn",
                            )
                output.update(add_btn = add_btn)

    elif method not in s3.action_methods:
        s3.actions = None

    return output

# END =========================================================================
