"""
    CRUD Resource

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

__all__ = ("CRUDResource",
           "MAXDEPTH",
           )

import json

from functools import reduce
from lxml import etree

from gluon import current
from gluon.html import A
from gluon.validators import IS_EMPTY_OR
from gluon.storage import Storage
from gluon.tools import callback

from s3dal import Row, Rows, Table, original_tablename
from ..tools import IS_ONE_OF, get_last_record_id, remove_last_record_id, \
                    s3_format_datetime, s3_has_foreign_key, s3_str
from ..ui import DataTable, S3DataList
from ..model import META_FIELD_NAMES

from .components import S3Components
from .query import FS, S3ResourceField, S3Joins
from .rfilter import S3ResourceFilter
from .data import ResourceData

#osetattr = object.__setattr__
ogetattr = object.__getattribute__

MAXDEPTH = 10
DEFAULT = lambda: None

# =============================================================================
class CRUDResource:
    """
        API for resources.

        A "resource" is a set of records in a database table including their
        references in certain related resources (components). A resource can
        be defined like:

            resource = CRUDResource(table)

        A resource defined like this would include all records in the table.
        Further parameters for the resource constructor as well as methods
        of the resource instance can be used to filter for particular subsets.

        This API provides extended standard methods to access and manipulate
        data in resources while respecting current authorization and other
        S3 framework rules.
    """

    def __init__(self,
                 tablename,
                 id = None,
                 prefix = None,
                 uid = None,
                 filter = None,
                 vars = None,
                 parent = None,
                 linked = None,
                 linktable = None,
                 alias = None,
                 components = None,
                 filter_component = None,
                 include_deleted = False,
                 approved = True,
                 unapproved = False,
                 extra_filters = None
                 ):
        """
            Args:
                tablename: tablename, Table, or a CRUDResource instance
                prefix: prefix to use for the tablename

                id: record ID (or list of record IDs)
                uid: record UID (or list of record UIDs)

                filter: filter query
                vars: dictionary of URL query variables

                components: list of component aliases
                            to load for this resource
                filter_component: alias of the component the URL filters
                                  apply for (filters for this component
                                  must be handled separately)

                alias: the alias for this resource (internal use only)
                parent: the parent resource (internal use only)
                linked: the linked resource (internal use only)
                linktable: the link table (internal use only)

                include_deleted: include deleted records (used for
                                 synchronization)

                approved: include approved records
                unapproved: include unapproved records
                extra_filters: extra filters (to be applied on
                               pre-filtered subsets), as list of
                               tuples (method, expression)
        """

        s3db = current.s3db
        auth = current.auth

        # Names ---------------------------------------------------------------

        table = None
        table_alias = None

        if prefix is None:
            if not isinstance(tablename, str):
                if isinstance(tablename, Table):
                    table = tablename
                    table_alias = table._tablename
                    tablename = original_tablename(table)
                elif isinstance(tablename, CRUDResource):
                    table = tablename.table
                    table_alias = table._tablename
                    tablename = tablename.tablename
                else:
                    error = "%s is not a valid type for a tablename" % tablename
                    raise SyntaxError(error)
            if "_" in tablename:
                prefix, name = tablename.split("_", 1)
            else:
                raise SyntaxError("invalid tablename: %s" % tablename)
        else:
            name = tablename
            tablename = "%s_%s" % (prefix, name)

        self.tablename = tablename

        # Module prefix and resource name
        self.prefix = prefix
        self.name = name

        # Resource alias defaults to tablename without module prefix
        if not alias:
            alias = name
        self.alias = alias

        # Table ---------------------------------------------------------------

        if table is None:
            table = s3db[tablename]

        # Set default approver
        auth.permission.set_default_approver(table)

        if parent is not None:
            if parent.tablename == self.tablename:
                # Component table same as parent table => must use table alias
                table_alias = "%s_%s_%s" % (prefix, alias, name)
                table = s3db.get_aliased(table, table_alias)

        self.table = table
        self._alias = table_alias or tablename

        self.fields = table.fields
        self._id = table._id

        self.defaults = None

        # Hooks ---------------------------------------------------------------

        # Authorization hooks
        self.accessible_query = auth.s3_accessible_query

        # Filter --------------------------------------------------------------

        # Default query options
        self.include_deleted = include_deleted
        self._approved = approved
        self._unapproved = unapproved

        # Component Filter
        self.filter = None

        # Resource Filter
        self.rfilter = None

        # Rows ----------------------------------------------------------------

        self._rows = None
        self._rowindex = None
        self.rfields = None
        self.dfields = None
        self._ids = None
        self._uids = None
        self._length = None

        # Request attributes --------------------------------------------------

        self.vars = None # set during build_query
        self.lastid = None
        self.files = Storage()

        # Components ----------------------------------------------------------

        # Initialize component properties (will be set during _attach)
        self.link = None
        self.linktable = None
        self.actuate = None
        self.lkey = None
        self.rkey = None
        self.pkey = None
        self.fkey = None
        self.multiple = True

        self.parent = parent # the parent resource
        self.linked = linked # the linked resource

        self.components = S3Components(self, components)
        self.links = self.components.links

        if parent is None:
            # Build query
            self.build_query(id = id,
                             uid = uid,
                             filter = filter,
                             vars = vars,
                             extra_filters = extra_filters,
                             filter_component = filter_component,
                             )

        # Component - attach link table
        elif linktable is not None:
            # This is a link-table component - attach the link table
            link_alias = "%s__link" % self.alias
            self.link = CRUDResource(linktable,
                                     alias = link_alias,
                                     parent = self.parent,
                                     linked = self,
                                     include_deleted = self.include_deleted,
                                     approved = self._approved,
                                     unapproved = self._unapproved,
                                     )

        # Export meta data ----------------------------------------------------

        self.muntil = None      # latest mtime of the exported records
        self.results = None     # number of exported records

        # Errors --------------------------------------------------------------

        self.error = None

    # -------------------------------------------------------------------------
    # Query handling
    # -------------------------------------------------------------------------
    def build_query(self,
                    id = None,
                    uid = None,
                    filter = None,
                    vars = None,
                    extra_filters = None,
                    filter_component = None,
                    ):
        """
            Query builder

            Args:
                id: record ID or list of record IDs to include
                uid: record UID or list of record UIDs to include
                filter: filtering query (DAL only)
                vars: dict of URL query variables
                extra_filters: extra filters (to be applied on
                               pre-filtered subsets), as list of
                               tuples (method, expression)
                filter_component: the alias of the component the URL
                                  filters apply for (filters for this
                                  component must be handled separately)
        """

        # Reset the rows counter
        self._length = None

        self.rfilter = S3ResourceFilter(self,
                                        id = id,
                                        uid = uid,
                                        filter = filter,
                                        vars = vars,
                                        extra_filters = extra_filters,
                                        filter_component = filter_component,
                                        )
        return self.rfilter

    # -------------------------------------------------------------------------
    def add_filter(self, f=None, c=None):
        """
            Extend the current resource filter

            Args:
                f: a Query or a S3ResourceQuery instance
                c: alias of the component this filter concerns,
                   automatically adds the respective component join
                   (not needed for S3ResourceQuery instances)
        """

        if f is None:
            return

        self.clear()

        if self.rfilter is None:
            self.rfilter = S3ResourceFilter(self)

        self.rfilter.add_filter(f, component=c)

    # -------------------------------------------------------------------------
    def add_component_filter(self, alias, f=None):
        """
            Extend the resource filter of a particular component, does
            not affect the master resource filter (as opposed to add_filter)

            Args:
                alias: the alias of the component
                f: a Query or a S3ResourceQuery instance
        """

        if f is None:
            return

        if self.rfilter is None:
            self.rfilter = S3ResourceFilter(self)

        self.rfilter.add_filter(f, component=alias, master=False)

    # -------------------------------------------------------------------------
    def add_extra_filter(self, method, expression):
        """
            And an extra filter (to be applied on pre-filtered subsets)

            Args:
                method: a name of a known filter method, or a
                        callable filter method
                expression: the filter expression (string)
        """

        self.clear()

        if self.rfilter is None:
            self.rfilter = S3ResourceFilter(self)

        self.rfilter.add_extra_filter(method, expression)

    # -------------------------------------------------------------------------
    def set_extra_filters(self, filters):
        """
            Replace the current extra filters

            Args:
                filters: list of tuples (method, expression), or None
                         to remove all extra filters
        """

        self.clear()

        if self.rfilter is None:
            self.rfilter = S3ResourceFilter(self)

        self.rfilter.set_extra_filters(filters)

    # -------------------------------------------------------------------------
    def get_query(self):
        """
            Get the effective query

            Returns:
                a Query
        """

        if self.rfilter is None:
            self.build_query()

        return self.rfilter.get_query()

    # -------------------------------------------------------------------------
    def get_filter(self):
        """
            Get the effective virtual filter

            Returns:
                a S3ResourceQuery
        """

        if self.rfilter is None:
            self.build_query()

        return self.rfilter.get_filter()

    # -------------------------------------------------------------------------
    def clear_query(self):
        """
            Remove the current query (does not remove the set!)
        """

        self.rfilter = None

        for component in self.components.loaded.values():
            component.clear_query()

    # -------------------------------------------------------------------------
    # Data access (new API)
    # -------------------------------------------------------------------------
    def count(self, left=None, distinct=False):
        """
            Get the total number of available records in this resource

            Args:
                left: left outer joins, if required
                distinct: only count distinct rows
        """

        if self.rfilter is None:
            self.build_query()
        if self._length is None:
            self._length = self.rfilter.count(left = left,
                                              distinct = distinct)
        return self._length

    # -------------------------------------------------------------------------
    def select(self,
               fields,
               start = 0,
               limit = None,
               left = None,
               orderby = None,
               groupby = None,
               distinct = False,
               virtual = True,
               count = False,
               getids = False,
               as_rows = False,
               represent = False,
               show_links = True,
               raw_data = False,
               ):
        """
            Extract data from this resource

            Args:
                fields: the fields to extract (selector strings)
                start: index of the first record
                limit: maximum number of records
                left: additional left joins required for filters
                orderby: orderby-expression for DAL
                groupby: fields to group by (overrides fields!)
                distinct: select distinct rows
                virtual: include mandatory virtual fields
                count: include the total number of matching records
                getids: include the IDs of all matching records
                as_rows: return the rows (don't extract)
                represent: render field value representations
                raw_data: include raw data in the result
        """

        data = ResourceData(self,
                            fields,
                            start = start,
                            limit = limit,
                            left = left,
                            orderby = orderby,
                            groupby = groupby,
                            distinct = distinct,
                            virtual = virtual,
                            count = count,
                            getids = getids,
                            as_rows = as_rows,
                            represent = represent,
                            show_links = show_links,
                            raw_data = raw_data,
                            )
        if as_rows:
            return data.rows
        else:
            return data

    # -------------------------------------------------------------------------
    def insert(self, **fields):
        """
            Insert a record into this resource

            Args:
                fields: dict of field/value pairs to insert
        """

        table = self.table
        tablename = self.tablename

        # Check permission
        authorised = current.auth.s3_has_permission("create", tablename)
        if not authorised:
            from ..errors import S3PermissionError
            raise S3PermissionError("Operation not permitted: INSERT INTO %s" %
                                    tablename)

        # Insert new record
        record_id = self.table.insert(**fields)

        # Post-process create
        if record_id:

            # Audit
            current.audit("create", self.prefix, self.name, record=record_id)

            record = Storage(fields)
            record.id = record_id

            # Update super
            s3db = current.s3db
            s3db.update_super(table, record)

            # Record owner
            auth = current.auth
            auth.s3_set_record_owner(table, record_id)
            auth.s3_make_session_owner(table, record_id)

            # Execute onaccept
            s3db.onaccept(tablename, record, method="create")

        return record_id

    # -------------------------------------------------------------------------
    def update(self):
        """
            TODO Bulk updater
        """

        raise NotImplementedError

    # -------------------------------------------------------------------------
    def delete(self,
               format = None,
               cascade = False,
               replaced_by = None,
               log_errors = False,
               ):
        """
            Delete all records in this resource

            Args:
                format: the representation format of the request (optional)
                cascade: this is a cascade delete (prevents commits)
                replaced_by: used by record merger
                log_errors: log errors even when cascade=True

            Returns:
                number of records deleted

            Note:
                skipping undeletable rows is no longer the default behavior,
                process will now fail immediately for any error; use DeleteProcess
                directly if skipping of undeletable rows is desired
        """

        from .delete import DeleteProcess

        delete = DeleteProcess(self, representation=format)
        result = delete(cascade = cascade,
                        replaced_by = replaced_by,
                        #skip_undeletable = False,
                        )

        if log_errors and cascade:
            # Call log_errors explicitly if suppressed by cascade
            delete.log_errors()

        return result

    # -------------------------------------------------------------------------
    def approve(self, components=(), approve=True, approved_by=None):
        """
            Approve all records in this resource

            Args:
                components: list of component aliases to include, None
                            for no components, empty list or tuple to
                            approve all components (default)
                approve: set to approved (False to reset to unapproved)
                approved_by: set approver explicitly, a valid auth_user.id
                             or 0 for approval by system authority
        """

        if "approved_by" not in self.fields:
            # No approved_by field => treat as approved by default
            return True

        auth = current.auth
        if approve:
            if approved_by is None:
                user = auth.user
                if user:
                    user_id = user.id
                else:
                    return False
            else:
                user_id = approved_by
        else:
            # Reset to unapproved
            user_id = None

        db = current.db
        table = self._table

        # Get all record_ids in the resource
        pkey = self._id.name
        rows = self.select([pkey], limit=None, as_rows=True)
        if not rows:
            # No records to approve => exit early
            return True

        # Collect record_ids and clear cached permissions
        record_ids = set()
        add = record_ids.add
        forget_permissions = auth.permission.forget
        for record in rows:
            record_id = record[pkey]
            forget_permissions(table, record_id)
            add(record_id)

        # Set approved_by for each record in the set
        dbset = db(table._id.belongs(record_ids))
        try:
            success = dbset.update(approved_by = user_id)
        except:
            # DB error => raise in debug mode to produce a proper ticket
            if current.response.s3.debug:
                raise
            success = False
        if not success:
            db.rollback()
            return False

        # Invoke onapprove-callback for each updated record
        onapprove = self.get_config("onapprove", None)
        if onapprove:
            rows = dbset.select(limitby=(0, len(record_ids)))
            for row in rows:
                callback(onapprove, row, tablename=self.tablename)

        # Return early if no components to approve
        if components is None:
            return True

        # Determine which components to approve
        # NB: Components are pre-filtered with the master filter, too
        if components:
            # FIXME this is probably wrong => should load
            #       the components which are to be approved
            cdict = self.components.exposed
            components = [cdict[k] for k in cdict if k in components]
        else:
            # Approve all currently attached components
            # FIXME use exposed.values()
            components = self.components.values()

        for component in components:
            success = component.approve(components = None,
                                        approve = approve,
                                        approved_by = approved_by,
                                        )
            if not success:
                return False

        return True

    # -------------------------------------------------------------------------
    def reject(self, cascade=False):
        """ Reject (delete) all records in this resource """

        db = current.db
        s3db = current.s3db

        define_resource = s3db.resource
        DELETED = current.xml.DELETED

        INTEGRITY_ERROR = current.ERROR.INTEGRITY_ERROR
        tablename = self.tablename
        table = self.table
        pkey = table._id.name

        # Get hooks configuration
        get_config = s3db.get_config
        ondelete = get_config(tablename, "ondelete")
        onreject = get_config(tablename, "onreject")
        ondelete_cascade = get_config(tablename, "ondelete_cascade")

        # Get all rows
        if "uuid" in table.fields:
            rows = self.select([table._id.name, "uuid"], as_rows=True)
        else:
            rows = self.select([table._id.name], as_rows=True)
        if not rows:
            return True

        delete_super = s3db.delete_super

        if DELETED in table:

            references = table._referenced_by

            for row in rows:

                error = self.error
                self.error = None

                # On-delete-cascade
                if ondelete_cascade:
                    callback(ondelete_cascade, row, tablename=tablename)

                # Automatic cascade
                for ref in references:
                    tn, fn = ref.tablename, ref.name
                    rtable = db[tn]
                    rfield = rtable[fn]
                    query = (rfield == row[pkey])
                    # Ignore RESTRICTs => reject anyway
                    if rfield.ondelete in ("CASCADE", "RESTRICT"):
                        rresource = define_resource(tn, filter=query, unapproved=True)
                        rresource.reject(cascade=True)
                        if rresource.error:
                            break
                    elif rfield.ondelete == "SET NULL":
                        try:
                            db(query).update(**{fn:None})
                        except:
                            self.error = INTEGRITY_ERROR
                            break
                    elif rfield.ondelete == "SET DEFAULT":
                        try:
                            db(query).update(**{fn:rfield.default})
                        except:
                            self.error = INTEGRITY_ERROR
                            break

                if not self.error and not delete_super(table, row):
                    self.error = INTEGRITY_ERROR

                if self.error:
                    db.rollback()
                    raise RuntimeError("Reject failed for %s.%s" %
                                      (tablename, row[table._id]))
                else:
                    # Pull back prior error status
                    self.error = error
                    error = None

                    # On-reject hook
                    if onreject:
                        callback(onreject, row, tablename=tablename)

                    # Park foreign keys
                    fields = {"deleted": True}
                    if "deleted_fk" in table:
                        record = table[row[pkey]]
                        fk = {}
                        for f in table.fields:
                            if record[f] is not None and \
                               s3_has_foreign_key(table[f]):
                                fk[f] = record[f]
                                fields[f] = None
                            else:
                                continue
                        if fk:
                            fields.update(deleted_fk=json.dumps(fk))

                    # Update the row, finally
                    db(table._id == row[pkey]).update(**fields)

                    # Clear session
                    if get_last_record_id(tablename) == row[pkey]:
                        remove_last_record_id(tablename)

                    # On-delete hook
                    if ondelete:
                        callback(ondelete, row, tablename=tablename)

        else:
            # Hard delete
            for row in rows:

                # On-delete-cascade
                if ondelete_cascade:
                    callback(ondelete_cascade, row, tablename=tablename)

                # On-reject
                if onreject:
                    callback(onreject, row, tablename=tablename)

                try:
                    del table[row[pkey]]
                except:
                    # Row is not deletable
                    self.error = INTEGRITY_ERROR
                    db.rollback()
                    raise

                # Clear session
                if get_last_record_id(tablename) == row[pkey]:
                    remove_last_record_id(tablename)

                # Delete super-entity
                delete_super(table, row)

                # On-delete
                if ondelete:
                    callback(ondelete, row, tablename=tablename)

        return True

    # -------------------------------------------------------------------------
    def merge(self,
              original_id,
              duplicate_id,
              replace = None,
              update = None,
              main = True,
              ):
        """
            Merge two records; see MergeProcess.merge
        """

        from .merge import MergeProcess
        return MergeProcess.merge(self,
                                  original_id,
                                  duplicate_id,
                                  replace = replace,
                                  update = update,
                                  main = main,
                                  )

    # -------------------------------------------------------------------------
    # Exports
    # -------------------------------------------------------------------------
    def datatable(self,
                  fields = None,
                  start = 0,
                  limit = None,
                  left = None,
                  orderby = None,
                  distinct = False,
                  list_id = None,
                  ):
        """
            Generate a data table of this resource

            Args:
                fields: list of fields to include (field selector strings)
                start: index of the first record to include
                limit: maximum number of records to include
                left: additional left joins for DB query
                orderby: orderby for DB query
                distinct: distinct-flag for DB query
                list_id: the datatable ID

            Returns:
                tuple (DataTable, numrows), where numrows represents
                the total number of rows in the table that match the query
        """

        # Choose fields
        if fields is None:
            fields = [f.name for f in self.readable_fields()]
        selectors = list(fields)

        table = self.table

        # Automatically include the record ID
        table_id = table._id
        pkey = table_id.name
        if pkey not in selectors:
            fields.insert(0, pkey)
            selectors.insert(0, pkey)

        # Skip representation of IDs in data tables
        id_repr = table_id.represent
        table_id.represent = None

        # Extract the data
        data = self.select(selectors,
                           start = start,
                           limit = limit,
                           orderby = orderby,
                           left = left,
                           distinct = distinct,
                           count = True,
                           getids = False,
                           represent = True,
                           )

        rows = data.rows

        # Restore ID representation
        table_id.represent = id_repr

        # Generate the data table
        rfields = data.rfields
        dt = DataTable(rfields, rows, list_id, orderby=orderby)

        return dt, data.numrows

    # -------------------------------------------------------------------------
    def datalist(self,
                 fields = None,
                 start = 0,
                 limit = None,
                 left = None,
                 orderby = None,
                 distinct = False,
                 list_id = None,
                 layout = None,
                 ):
        """
            Generate a data list of this resource

            Args:
                fields: list of fields to include (field selector strings)
                start: index of the first record to include
                limit: maximum number of records to include
                left: additional left joins for DB query
                orderby: orderby for DB query
                distinct: distinct-flag for DB query
                list_id: the list identifier
                layout: custom renderer function (see S3DataList.render)

            Returns:
                tuple (S3DataList, numrows, ids), where numrows represents
                the total number of rows in the table that match the query
        """

        # Choose fields
        if fields is None:
            fields = [f.name for f in self.readable_fields()]
        selectors = list(fields)

        table = self.table

        # Automatically include the record ID
        pkey = table._id.name
        if pkey not in selectors:
            fields.insert(0, pkey)
            selectors.insert(0, pkey)

        # Extract the data
        data = self.select(selectors,
                           start = start,
                           limit = limit,
                           orderby = orderby,
                           left = left,
                           distinct = distinct,
                           count = True,
                           getids = False,
                           raw_data = True,
                           represent = True,
                           )

        # Generate the data list
        numrows = data.numrows
        dl = S3DataList(self,
                        fields,
                        data.rows,
                        list_id = list_id,
                        start = start,
                        limit = limit,
                        total = numrows,
                        layout = layout,
                        )

        return dl, numrows

    # -------------------------------------------------------------------------
    def json(self,
             fields = None,
             start = 0,
             limit = None,
             left = None,
             distinct = False,
             orderby = None,
             ):
        """
            Export a JSON representation of the resource.

            Args:
                fields: list of field selector strings
                start: index of the first record
                limit: maximum number of records
                left: list of (additional) left joins
                distinct: select only distinct rows
                orderby: Orderby-expression for the query

            Returns:
                the JSON (as string), representing a list of dicts
                with {"tablename.fieldname":"value"}
        """

        data = self.select(fields = fields,
                           start = start,
                           limit = limit,
                           orderby = orderby,
                           left = left,
                           distinct = distinct,
                           )

        return json.dumps(data.rows)

    # -------------------------------------------------------------------------
    # Data Object API
    # -------------------------------------------------------------------------
    def load(self,
             fields = None,
             skip = None,
             start = None,
             limit = None,
             orderby = None,
             virtual = True,
             cacheable = False,
             ):
        """
            Loads records from the resource, applying the current filters,
            and stores them in the instance.

            Args:
                fields: list of field names to include
                skip: list of field names to skip
                start: the index of the first record to load
                limit: the maximum number of records to load
                orderby: orderby-expression for the query
                virtual: whether to load virtual fields or not
                cacheable: don't define Row actions like update_record
                           or delete_record (faster, and the record can
                           be cached)

            Returns:
                the records as list of Rows
        """


        table = self.table
        tablename = self.tablename

        UID = current.xml.UID
        load_uids = hasattr(table, UID)

        if not skip:
            skip = ()

        if fields or skip:
            s3 = current.response.s3
            if "all_meta_fields" in s3:
                meta_fields = s3.all_meta_fields
            else:
                meta_fields = s3.all_meta_fields = META_FIELD_NAMES
            s3db = current.s3db
            superkeys = s3db.get_super_keys(table)
        else:
            meta_fields = superkeys = None

        # Field selection
        qfields = ([table._id.name, UID])
        append = qfields.append
        for f in table.fields:

            if f in ("wkt", "the_geom"):
                if tablename == "gis_location":
                    if f == "the_geom":
                        # Filter out bulky Polygons
                        continue
                    fmt = current.auth.permission.format
                    if fmt == "cap":
                        # Include WKT
                        pass
                    elif fmt == "xml" and current.deployment_settings.get_gis_xml_wkt():
                        # Include WKT
                        pass
                    else:
                        # Filter out bulky Polygons
                        continue
                elif tablename.startswith("gis_layer_shapefile_"):
                    # Filter out bulky Polygons
                    continue

            if fields or skip:

                # Must include all meta-fields
                if f in meta_fields:
                    append(f)
                    continue

                # Must include the fkey if component
                if self.parent and not self.link and f == self.fkey:
                    append(f)
                    continue

                # Must include all super-keys
                if f in superkeys:
                    append(f)
                    continue

            if f in skip:
                continue
            if not fields or f in fields:
                qfields.append(f)

        fields = list(set(fn for fn in qfields if hasattr(table, fn)))

        if self._rows is not None:
            self.clear()

        pagination = limit is not None or start

        rfilter = self.rfilter
        multiple = rfilter.multiple if rfilter is not None else True
        if not multiple and self.parent and self.parent.count() == 1:
            start = 0
            limit = 1

        rows = self.select(fields,
                           start = start,
                           limit = limit,
                           orderby = orderby,
                           virtual = virtual,
                           as_rows = True,
                           )

        ids = self._ids = []
        new_id = ids.append

        self._uids = []
        self._rows = []

        if rows:
            new_uid = self._uids.append
            new_row = self._rows.append
            pkey = table._id.name
            for row in rows:
                if hasattr(row, tablename):
                    _row = ogetattr(row, tablename)
                    if type(_row) is Row:
                        row = _row
                record_id = ogetattr(row, pkey)
                if record_id not in ids:
                    new_id(record_id)
                    new_row(row)
                    if load_uids:
                        new_uid(ogetattr(row, UID))

        # If this is an unlimited load, or the first page with no
        # rows, then the result length is equal to the total number
        # of matching records => store length for subsequent count()s
        length = len(self._rows)
        if not pagination or not start and not length:
            self._length = length

        return self._rows

    # -------------------------------------------------------------------------
    def clear(self):
        """ Removes the records currently stored in this instance """

        self._rows = None
        self._rowindex = None
        self._length = None
        self._ids = None
        self._uids = None
        self.files = Storage()

        for component in self.components.loaded.values():
            component.clear()

    # -------------------------------------------------------------------------
    def records(self, fields=None):
        """
            Get the current set as Rows instance

            Args:
                fields: the fields to include (list of Fields)
        """

        if fields is None:
            if self.tablename == "gis_location":
                fields = [f for f in self.table
                          if f.name not in ("wkt", "the_geom")]
            else:
                fields = [f for f in self.table]

        if self._rows is None:
            return Rows(current.db)
        else:
            colnames = [str(f) for f in fields]
            return Rows(current.db, self._rows, colnames=colnames)

    # -------------------------------------------------------------------------
    def __getitem__(self, key):
        """
            Find a record currently stored in this instance by its record ID

            Args:
                key: the record ID

            Returns:
                a Row

            Raises:
                IndexError: if the record is not currently loaded
        """

        index = self._rowindex
        if index is None:
            _id = self._id.name
            rows = self._rows
            if rows:
                index = Storage([(str(row[_id]), row) for row in rows])
            else:
                index = Storage()
            self._rowindex = index
        key = str(key)
        if key in index:
            return index[key]
        raise IndexError

    # -------------------------------------------------------------------------
    def __iter__(self):
        """
            Iterate over the records currently stored in this instance
        """

        if self._rows is None:
            self.load()
        rows = self._rows
        for i in range(len(rows)):
            yield rows[i]
        return

    # -------------------------------------------------------------------------
    def get(self, key, component=None, link=None):
        """
            Get component records for a record currently stored in this
            instance.

            Args:
                key: the record ID
                component: the name of the component
                link: the name of the link table

            Returns:
                a Row (if component is None) or a list of rows
        """

        if not key:
            raise KeyError("Record not found")
        if self._rows is None:
            self.load()
        try:
            master = self[key]
        except IndexError as e:
            raise KeyError("Record not found") from e

        if not component and not link:
            return master
        elif link:
            if link in self.links:
                c = self.links[link]
            else:
                calias = current.s3db.get_alias(self.tablename, link)
                if calias:
                    c = self.components[calias].link
                else:
                    raise AttributeError("Undefined link %s" % link)
        else:
            try:
                c = self.components[component]
            except KeyError as e:
                raise AttributeError("Undefined component %s" % component) from e

        rows = c._rows
        if rows is None:
            rows = c.load()
        if not rows:
            return []
        pkey, fkey = c.pkey, c.fkey
        if pkey in master:
            master_id = master[pkey]
            if c.link:
                lkey, rkey = c.lkey, c.rkey
                lids = [r[rkey] for r in c.link if master_id == r[lkey]]
                rows = [record for record in rows if record[fkey] in lids]
            else:
                try:
                    rows = [record for record in rows if master_id == record[fkey]]
                except AttributeError as e:
                    # Most likely need to tweak static/formats/geoson/export.xsl
                    raise AttributeError("Component %s records are missing fkey %s" % (component, fkey)) from e
        else:
            rows = []
        return rows

    # -------------------------------------------------------------------------
    def get_id(self):
        """ Get the IDs of all records currently stored in this instance """

        if self._ids is None:
            self.__load_ids()

        if not self._ids:
            return None
        elif len(self._ids) == 1:
            return self._ids[0]
        else:
            return self._ids

    # -------------------------------------------------------------------------
    def get_uid(self):
        """ Get the UUIDs of all records currently stored in this instance """

        if current.xml.UID not in self.table.fields:
            return None
        if self._ids is None:
            self.__load_ids()

        if not self._uids:
            return None
        elif len(self._uids) == 1:
            return self._uids[0]
        else:
            return self._uids

    # -------------------------------------------------------------------------
    def __len__(self):
        """
            The number of currently loaded rows
        """

        if self._rows is not None:
            return len(self._rows)
        else:
            return 0

    # -------------------------------------------------------------------------
    def __load_ids(self):
        """ Loads the IDs/UIDs of all records matching the current filter """

        table = self.table
        UID = current.xml.UID

        pkey = table._id.name

        if UID in table.fields:
            has_uid = True
            fields = (pkey, UID)
        else:
            has_uid = False
            fields = (pkey, )

        rfilter = self.rfilter
        multiple = rfilter.multiple if rfilter is not None else True
        if not multiple and self.parent and self.parent.count() == 1:
            start = 0
            limit = 1
        else:
            start = limit = None

        rows = self.select(fields,
                           start=start,
                           limit=limit)["rows"]

        if rows:
            ID = str(table._id)
            self._ids = [row[ID] for row in rows]
            if has_uid:
                uid = str(table[UID])
                self._uids = [row[uid] for row in rows]
        else:
            self._ids = []

        return

    # -------------------------------------------------------------------------
    # Representation
    # -------------------------------------------------------------------------
    def __repr__(self):
        """
            String representation of this resource
        """

        pkey = self.table._id.name

        if self._rows:
            ids = [r[pkey] for r in self]
            return "<CRUDResource %s %s>" % (self.tablename, ids)
        else:
            return "<CRUDResource %s>" % self.tablename

    # -------------------------------------------------------------------------
    def __contains__(self, item):
        """
            Tests whether this resource contains a (real) field.

            Args:
                item: the field selector or Field instance
        """

        fn = str(item)
        if "." in fn:
            tn, fn = fn.split(".", 1)
            if tn == self.tablename:
                item = fn
        try:
            rf = self.resolve_selector(str(item))
        except (SyntaxError, AttributeError):
            return 0
        if rf.field is not None:
            return 1
        else:
            return 0

    # -------------------------------------------------------------------------
    def __bool__(self):
        """ Boolean test of this resource """

        return self is not None

    def __nonzero__(self):
        """ Python-2.7 backwards-compatibility """

        return self is not None

    # -------------------------------------------------------------------------
    # XML Export
    # -------------------------------------------------------------------------
    def export_xml(self,
                   start = None,
                   limit = None,
                   msince = None,
                   fields = None,
                   dereference = True,
                   maxdepth = MAXDEPTH,
                   mcomponents = DEFAULT,
                   rcomponents = None,
                   references = None,
                   mdata = False,
                   stylesheet = None,
                   as_tree = False,
                   as_json = False,
                   maxbounds = False,
                   filters = None,
                   pretty_print = False,
                   location_data = None,
                   map_data = None,
                   target = None,
                   **args):
        """
            Export this resource as S3XML

            Args:
                start: index of the first record to export (slicing)
                limit: maximum number of records to export (slicing)

                msince: export only records which have been modified
                        after this datetime

                fields: data fields to include (default: all)

                dereference: include referenced resources
                maxdepth: maximum depth for reference exports

                mcomponents: components of the master resource to
                             include (list of aliases), empty list
                             for all available components
                rcomponents: components of referenced resources to
                             include (list of "tablename:alias")

                references: foreign keys to include (default: all)
                mdata: mobile data export
                       (=>reduced field set, lookup-only option)
                stylesheet: path to the XSLT stylesheet (if required)
                as_tree: return the ElementTree (do not convert into string)
                as_json: represent the XML tree as JSON
                maxbounds: include lat/lon boundaries in the top
                           level element (off by default)
                filters: additional URL filters (Sync), as dict
                         {tablename: {url_var: string}}
                pretty_print: insert newlines/indentation in the output
                location_data: dictionary of location data which has been
                               looked-up in bulk ready for xml.gis_encode()
                map_data: dictionary of options which can be read by the map
                target: alias of component targetted (or None to target master resource)
                args: dict of arguments to pass to the XSLT stylesheet
        """

        xml = current.xml

        output = None
        args = Storage(args)

        from ..formats import S3XMLFormat
        xmlformat = S3XMLFormat(stylesheet) if stylesheet else None

        if mcomponents is DEFAULT:
            mcomponents = []

        # Export as element tree
        from .rtb import S3ResourceTree
        rtree = S3ResourceTree(self,
                               location_data = location_data,
                               map_data = map_data,
                               )

        tree = rtree.build(start = start,
                           limit = limit,
                           msince = msince,
                           fields = fields,
                           dereference = dereference,
                           maxdepth = maxdepth,
                           mcomponents = mcomponents,
                           rcomponents = rcomponents,
                           references = references,
                           sync_filters = filters,
                           mdata = mdata,
                           maxbounds = maxbounds,
                           xmlformat = xmlformat,
                           target = target,
                           )

        # XSLT transformation
        if tree and xmlformat is not None:
            import uuid
            args.update(domain = xml.domain,
                        base_url = current.response.s3.base_url,
                        prefix = self.prefix,
                        name = self.name,
                        utcnow = s3_format_datetime(),
                        msguid = uuid.uuid4().urn,
                        )
            tree = xmlformat.transform(tree, **args)

        # Convert into the requested format
        # NB Content-Type headers are to be set by caller
        if tree:
            if as_tree:
                output = tree
            elif as_json:
                output = xml.tree2json(tree, pretty_print=pretty_print)
            else:
                output = xml.tostring(tree, pretty_print=pretty_print)

        return output

    # -------------------------------------------------------------------------
    # XML Import
    # -------------------------------------------------------------------------
    def import_xml(self,
                   source,
                   source_type = "xml",
                   stylesheet = None,
                   extra_data = None,
                   files = None,
                   record_id = None,
                   commit = True,
                   ignore_errors = False,
                   job_id = None,
                   select_items = None,
                   strategy = None,
                   sync_policy = None,
                   **args):
        """
            Import data

            Args:
                source: the data source
                str source_type: the source type (xml|json|csv|xls|xlsx)
                stylesheet: transformation stylesheet
                extra_data: extra columns to add to spreadsheet rows
                files: attached files
                record_id: target record ID
                commit: commit the import, if False, the import will be
                        rolled back and the job stored for later commit
                ignore_errors: ignore any errors, import whatever is valid
                job_id: a previous import job to restore and commit
                select_items: items of the previous import job to select
                strategy: allowed import methods
                SyncPolicy sync_policy: the synchronization policy
                args: arguments for the transformation stylesheet
        """

        # Check permission
        has_permission = current.auth.s3_has_permission
        authorised = has_permission("create", self.table) and \
                     has_permission("update", self.table)
        if not authorised:
            raise IOError("Insufficient permissions")

        self.job_id = None
        tablename = self.tablename

        from .importer import XMLImporter
        tree = None
        if source:
            tree = XMLImporter.parse_source(tablename,
                                            source,
                                            source_type = source_type,
                                            stylesheet = stylesheet,
                                            extra_data = extra_data,
                                            **args)
        elif not commit:
            raise ValueError("Source required for trial import")
        elif not job_id:
            raise ValueError("Source or Job ID required")

        return XMLImporter.import_tree(tablename,
                                       tree,
                                       files = files,
                                       record_id = record_id,
                                       components = self.components.exposed_aliases,
                                       commit = commit,
                                       ignore_errors = ignore_errors,
                                       job_id = job_id if tree is None else None,
                                       select_items = select_items,
                                       strategy = strategy,
                                       sync_policy = sync_policy,
                                       )

    # -------------------------------------------------------------------------
    # XML introspection
    # -------------------------------------------------------------------------
    def export_options(self,
                       component = None,
                       fields = None,
                       only_last = False,
                       show_uids = False,
                       hierarchy = False,
                       as_json = False,
                       ):
        """
            Export field options of this resource as element tree

            Args:
                component: name of the component which the options are
                           requested of, None for the primary table
                fields: list of names of fields for which the options
                        are requested, None for all fields (which have
                        options)
                as_json: convert the output into JSON
                only_last: obtain only the latest record
        """

        if component is not None:
            c = self.components.get(component)
            if c:
                tree = c.export_options(fields = fields,
                                        only_last = only_last,
                                        show_uids = show_uids,
                                        hierarchy = hierarchy,
                                        as_json = as_json,
                                        )
                return tree
            else:
                # If we get here, we've been called from the back-end,
                # otherwise the request would have failed during parse.
                # So it's safe to raise an exception:
                raise AttributeError
        else:
            if as_json and only_last and len(fields) == 1:
                # Identify the field
                default = {"option":[]}
                try:
                    field = self.table[fields[0]]
                except AttributeError:
                    # Can't raise an exception here as this goes
                    # directly to the client
                    return json.dumps(default)

                # Check that the validator has a lookup table
                requires = field.requires
                if not isinstance(requires, (list, tuple)):
                    requires = [requires]
                requires = requires[0]
                if isinstance(requires, IS_EMPTY_OR):
                    requires = requires.other
                from ..tools import IS_LOCATION
                if not isinstance(requires, (IS_ONE_OF, IS_LOCATION)):
                    # Can't raise an exception here as this goes
                    # directly to the client
                    return json.dumps(default)

                # Identify the lookup table
                db = current.db
                lookuptable = requires.ktable
                lookupfield = db[lookuptable][requires.kfield]

                # Fields to extract
                fields = [lookupfield]
                h = None
                if hierarchy:
                    from ..tools import S3Hierarchy
                    h = S3Hierarchy(lookuptable)
                    if not h.config:
                        h = None
                    elif h.pkey.name != lookupfield.name:
                        # Also extract the node key for the hierarchy
                        fields.append(h.pkey)

                # Get the latest record
                # NB: this assumes that the lookupfield is auto-incremented
                row = db().select(orderby = ~lookupfield,
                                  limitby = (0, 1),
                                  *fields).first()

                # Represent the value and generate the output JSON
                if row:
                    value = row[lookupfield]
                    widget = field.widget
                    if hasattr(widget, "represent") and widget.represent:
                        # Prefer the widget's represent as options.json
                        # is usually called to Ajax-update the widget
                        represent = widget.represent(value)
                    elif field.represent:
                        represent = field.represent(value)
                    else:
                        represent = s3_str(value)
                    if isinstance(represent, A):
                        represent = represent.components[0]

                    item = {"@value": value, "$": represent}
                    if h:
                        parent = h.parent(row[h.pkey])
                        if parent:
                            item["@parent"] = str(parent)
                    result = [item]
                else:
                    result = []
                return json.dumps({'option': result})

            xml = current.xml
            tree = xml.get_options(self.table,
                                   fields = fields,
                                   show_uids = show_uids,
                                   hierarchy = hierarchy,
                                   )

            if as_json:
                return xml.tree2json(tree, pretty_print=False, native=True)
            else:
                return xml.tostring(tree, pretty_print=False)

    # -------------------------------------------------------------------------
    def export_fields(self, component=None, as_json=False):
        """
            Export a list of fields in the resource as element tree

            Args:
                component: name of the component to lookup the fields
                           (None for primary table)
                as_json: convert the output XML into JSON
        """

        if component is not None:
            try:
                c = self.components[component]
            except KeyError:
                raise AttributeError("Undefined component %s" % component)
            return c.export_fields(as_json=as_json)
        else:
            xml = current.xml
            tree = xml.get_fields(self.prefix, self.name)
            if as_json:
                return xml.tree2json(tree, pretty_print=True)
            else:
                return xml.tostring(tree, pretty_print=True)

    # -------------------------------------------------------------------------
    def export_struct(self,
                      meta = False,
                      options = False,
                      references = False,
                      stylesheet = None,
                      as_json = False,
                      as_tree = False,
                      ):
        """
            Get the structure of the resource

            Args:
                options: include option lists in option fields
                references: include option lists even for reference fields
                stylesheet: the stylesheet to use for transformation
                as_json: convert into JSON after transformation
        """

        xml = current.xml

        # Get the structure of the main resource
        root = etree.Element(xml.TAG.root)
        main = xml.get_struct(self.prefix, self.name,
                              alias = self.alias,
                              parent = root,
                              meta = meta,
                              options = options,
                              references = references,
                              )

        # Include the exposed components
        for component in self.components.exposed.values():
            prefix = component.prefix
            name = component.name
            xml.get_struct(prefix, name,
                           alias = component.alias,
                           parent = main,
                           meta = meta,
                           options = options,
                           references = references,
                           )

        # Transformation
        tree = etree.ElementTree(root)
        if stylesheet is not None:
            args = {"domain": xml.domain,
                    "base_url": current.response.s3.base_url,
                    "prefix": self.prefix,
                    "name": self.name,
                    "utcnow": s3_format_datetime(),
                    }

            tree = xml.transform(tree, stylesheet, **args)
            if tree is None:
                return None

        # Return tree if requested
        if as_tree:
            return tree

        # Otherwise string-ify it
        if as_json:
            return xml.tree2json(tree, pretty_print=True)
        else:
            return xml.tostring(tree, pretty_print=True)

    # -------------------------------------------------------------------------
    # Data Model Helpers
    # -------------------------------------------------------------------------
    @classmethod
    def original(cls, table, record, mandatory=None):
        """
            Find the original record for a possible duplicate:
                - if the record contains a UUID, then only that UUID is used
                  to match the record with an existing DB record
                - otherwise, if the record contains some values for unique
                  fields, all of them must match the same existing DB record

            Args:
                table: the table
                record: the record as dict or S3XML Element
        """

        db = current.db
        xml = current.xml
        xml_decode = xml.xml_decode

        VALUE = xml.ATTRIBUTE["value"]
        UID = xml.UID
        ATTRIBUTES_TO_FIELDS = xml.ATTRIBUTES_TO_FIELDS

        # Get primary keys
        pkeys = [f for f in table.fields if table[f].unique]
        pvalues = Storage()

        # Get the values from record
        get = record.get
        if type(record) is etree._Element: #isinstance(record, etree._Element):
            xpath = record.xpath
            xexpr = "%s[@%s='%%s']" % (xml.TAG["data"],
                                       xml.ATTRIBUTE["field"])
            for f in pkeys:
                v = None
                if f == UID or f in ATTRIBUTES_TO_FIELDS:
                    v = get(f, None)
                else:
                    child = xpath(xexpr % f)
                    if child:
                        child = child[0]
                        v = child.get(VALUE, xml_decode(child.text))
                if v:
                    pvalues[f] = v
        elif isinstance(record, dict):
            for f in pkeys:
                v = get(f, None)
                if v:
                    pvalues[f] = v
        else:
            raise TypeError

        # Build match query
        query = None
        for f in pvalues:
            if f == UID:
                continue
            _query = (table[f] == pvalues[f])
            if query is not None:
                query = query | _query
            else:
                query = _query

        fields = cls.import_fields(table, pvalues, mandatory=mandatory)

        # Try to find exactly one match by non-UID unique keys
        if query is not None:
            original = db(query).select(limitby=(0, 2), *fields)
            if len(original) == 1:
                return original.first()

        # If no match, then try to find a UID-match
        if UID in pvalues:
            uid = xml.import_uid(pvalues[UID])
            query = (table[UID] == uid)
            original = db(query).select(limitby=(0, 1), *fields).first()
            if original:
                return original

        # No match or multiple matches
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def import_fields(table, data, mandatory=None):

        fnames = set(META_FIELD_NAMES)
        fnames.add(table._id.name)
        if mandatory:
            fnames |= set(mandatory)
        for fn in data:
            fnames.add(fn)
        return [table[fn] for fn in fnames if fn in table.fields]

    # -------------------------------------------------------------------------
    def readable_fields(self, subset=None):
        """
            Get a list of all readable fields in the resource table

            Args:
                subset: list of fieldnames to limit the selection to
        """

        fkey = None
        table = self.table

        parent = self.parent
        linked = self.linked

        if parent and linked is None:
            component = parent.components.get(self.alias)
            if component:
                fkey = component.fkey
        elif linked is not None:
            component = linked
            if component:
                fkey = component.lkey

        if subset:
            return [ogetattr(table, f) for f in subset
                    if f in table.fields and \
                       ogetattr(table, f).readable and f != fkey]
        else:
            return [ogetattr(table, f) for f in table.fields
                    if ogetattr(table, f).readable and f != fkey]

    # -------------------------------------------------------------------------
    def resolve_selectors(self,
                          selectors,
                          skip_components = False,
                          extra_fields = True,
                          show = True,
                          ):
        """
            Resolve a list of field selectors against this resource

            Args:
                selectors: the field selectors
                skip_components: skip fields in components
                extra_fields: automatically add extra_fields of all virtual
                              fields in this table
                show: default for S3ResourceField.show

            Returns:
                tuple of (fields, joins, left, distinct)
        """

        prefix = lambda s: "~.%s" % s \
                           if "." not in s.split("$", 1)[0] else s

        display_fields = set()
        add = display_fields.add

        # Store field selectors
        for item in selectors:
            if not item:
                continue
            if type(item) is tuple:
                item = item[-1]
            if isinstance(item, str):
                selector = item
            elif isinstance(item, S3ResourceField):
                selector = item.selector
            elif isinstance(item, FS):
                selector = item.name
            else:
                continue
            add(prefix(selector))

        slist = list(selectors)

        # Collect extra fields from virtual tables
        if extra_fields:
            extra = self.get_config("extra_fields")
            if extra:
                append = slist.append
                for selector in extra:
                    s = prefix(selector)
                    if s not in display_fields:
                        append(s)

        joins = {}
        left = {}

        distinct = False

        columns = set()
        add_column = columns.add

        rfields = []
        append = rfields.append

        for s in slist:

            # Allow to override the field label
            if type(s) is tuple:
                label, selector = s
            else:
                label, selector = None, s

            # Resolve the selector
            if isinstance(selector, str):
                selector = prefix(selector)
                try:
                    rfield = S3ResourceField(self, selector, label=label)
                except (AttributeError, SyntaxError):
                    continue
            elif isinstance(selector, FS):
                try:
                    rfield = selector.resolve(self)
                except (AttributeError, SyntaxError):
                    continue
            elif isinstance(selector, S3ResourceField):
                rfield = selector
            else:
                continue

            # Unresolvable selector?
            if rfield.field is None and not rfield.virtual:
                continue

            # De-duplicate columns
            colname = rfield.colname
            if colname in columns:
                continue
            add_column(colname)

            # Replace default label
            if label is not None:
                rfield.label = label

            # Skip components
            if skip_components:
                head = rfield.selector.split("$", 1)[0]
                if "." in head and head.split(".")[0] not in ("~", self.alias):
                    continue

            # Resolve the joins
            if rfield.distinct:
                left.update(rfield._joins)
                distinct = True
            elif rfield.join:
                joins.update(rfield._joins)

            rfield.show = show and rfield.selector in display_fields
            append(rfield)

        return (rfields, joins, left, distinct)

    # -------------------------------------------------------------------------
    def resolve_selector(self, selector):
        """
            Wrapper for S3ResourceField, retained for backward compatibility
        """

        return S3ResourceField(self, selector)

    # -------------------------------------------------------------------------
    def split_fields(self, skip=DEFAULT, data=None, references=None):
        """
            Split the readable fields in the resource table into
            reference and non-reference fields.

            Args:
                skip: list of field names to skip
                data: data fields to include (None for all)
                references: foreign key fields to include (None for all)
        """

        if skip is DEFAULT:
            skip = []

        rfields = self.rfields
        dfields = self.dfields

        if rfields is None or dfields is None:
            if self.tablename == "gis_location":
                settings = current.deployment_settings
                if "wkt" not in skip:
                    fmt = current.auth.permission.format
                    if fmt == "cap":
                        # Include WKT
                        pass
                    elif fmt == "xml" and settings.get_gis_xml_wkt():
                        # Include WKT
                        pass
                    else:
                        # Skip bulky WKT fields
                        skip.append("wkt")
                if "the_geom" not in skip and settings.get_gis_spatialdb():
                    skip.append("the_geom")

            xml = current.xml
            UID = xml.UID
            IGNORE_FIELDS = xml.IGNORE_FIELDS
            FIELDS_TO_ATTRIBUTES = xml.FIELDS_TO_ATTRIBUTES

            show_ids = current.xml.show_ids
            rfields = []
            dfields = []
            table = self.table
            pkey = table._id.name
            for f in table.fields:

                if f == UID or f in skip or f in IGNORE_FIELDS:
                    # Skip (show_ids=True overrides this for pkey)
                    if f != pkey or not show_ids:
                        continue

                # Meta-field? => always include (in dfields)
                meta = f in FIELDS_TO_ATTRIBUTES

                if s3_has_foreign_key(table[f]) and not meta:
                    # Foreign key => add to rfields unless excluded
                    if references is None or f in references:
                        rfields.append(f)

                elif data is None or f in data or meta:
                    # Data field => add to dfields
                    dfields.append(f)

            self.rfields = rfields
            self.dfields = dfields

        return (rfields, dfields)

    # -------------------------------------------------------------------------
    # Utility functions
    # -------------------------------------------------------------------------
    def configure(self, **settings):
        """
            Update configuration settings for this resource

            Args:
                settings: configuration settings for this resource
                          as keyword arguments
        """

        current.s3db.configure(self.tablename, **settings)

    # -------------------------------------------------------------------------
    def get_config(self, key, default=None):
        """
            Get a configuration setting for the current resource

            Args:
                key: the setting key
                default: the default value to return if the setting
                         is not configured for this resource
        """

        return current.s3db.get_config(self.tablename, key, default=default)

    # -------------------------------------------------------------------------
    def clear_config(self, *keys):
        """
            Clear configuration settings for this resource

            Args:
                keys: keys to remove (can be multiple)

            Note:
                No keys specified removes all settings for this resource
        """

        current.s3db.clear_config(self.tablename, *keys)

    # -------------------------------------------------------------------------
    @staticmethod
    def limitby(start=0, limit=0):
        """
            Convert start+limit parameters into a limitby tuple
                - limit without start => start = 0
                - start without limit => limit = ROWSPERPAGE
                - limit 0 (or less)   => limit = 1
                - start less than 0   => start = 0

            Args:
                start: index of the first record to select
                limit: maximum number of records to select
        """

        if limit is None:
            return None

        if start is None:
            start = 0
        if limit == 0:
            limit = current.response.s3.ROWSPERPAGE

        if limit <= 0:
            limit = 1
        if start < 0:
            start = 0

        return (start, start + limit)

    # -------------------------------------------------------------------------
    def _join(self, implicit=False, reverse=False):
        """
            Get a join for this component

            Args:
                implicit: return a subquery with an implicit join rather
                          than an explicit join
                reverse: get the reverse join (joining master to component)

            Returns:
                a Query if implicit=True, otherwise a list of joins
        """

        if self.parent is None:
            # This isn't a component
            return None
        else:
            ltable = self.parent.table

        rtable = self.table
        pkey = self.pkey
        fkey = self.fkey

        DELETED = current.xml.DELETED

        if self.linked:
            return self.linked._join(implicit=implicit, reverse=reverse)

        elif self.linktable:
            linktable = self.linktable
            lkey = self.lkey
            rkey = self.rkey
            lquery = (ltable[pkey] == linktable[lkey])
            if DELETED in linktable:
                lquery &= (linktable[DELETED] == False)
            if self.filter is not None and not reverse:
                rquery = (linktable[rkey] == rtable[fkey]) & self.filter
            else:
                rquery = (linktable[rkey] == rtable[fkey])
            if reverse:
                join = [linktable.on(rquery), ltable.on(lquery)]
            else:
                join = [linktable.on(lquery), rtable.on(rquery)]

        else:
            lquery = (ltable[pkey] == rtable[fkey])
            if DELETED in rtable and not reverse:
                lquery &= (rtable[DELETED] == False)
            if self.filter is not None:
                lquery &= self.filter
            if reverse:
                join = [ltable.on(lquery)]
            else:
                join = [rtable.on(lquery)]

        if implicit:
            query = None
            for expression in join:
                if query is None:
                    query = expression.second
                else:
                    query &= expression.second
            return query
        else:
            return join

    # -------------------------------------------------------------------------
    def get_join(self, reverse=False):
        """ Get join for this component """

        return self._join(implicit=True, reverse=reverse)

    # -------------------------------------------------------------------------
    def get_left_join(self, reverse=False):
        """ Get a left join for this component """

        return self._join(reverse=reverse)

    # -------------------------------------------------------------------------
    def link_id(self, master_id, component_id):
        """
            Helper method to find the link table entry ID for
            a pair of linked records.

            Args:
                master_id: the ID of the master record
                component_id: the ID of the component record
        """

        if self.parent is None or self.linked is None:
            return None

        join = self.get_join()
        ltable = self.table
        mtable = self.parent.table
        ctable = self.linked.table
        query = join & \
                (mtable._id == master_id) & \
                (ctable._id == component_id)
        row = current.db(query).select(ltable._id, limitby=(0, 1)).first()
        if row:
            return row[ltable._id.name]
        else:
            return None

    # -------------------------------------------------------------------------
    def component_id(self, master_id, link_id):
        """
            Helper method to find the component record ID for
            a particular link of a particular master record

            Args:
                link: the link (CRUDResource)
                master_id: the ID of the master record
                link_id: the ID of the link table entry
        """

        if self.parent is None or self.linked is None:
            return None

        join = self.get_join()
        ltable = self.table
        mtable = self.parent.table
        ctable = self.linked.table
        query = join & (ltable._id == link_id)
        if master_id is not None:
            # master ID is redundant, but can be used to check negatives
            query &= (mtable._id == master_id)
        row = current.db(query).select(ctable._id, limitby=(0, 1)).first()
        if row:
            return row[ctable._id.name]
        else:
            return None

    # -------------------------------------------------------------------------
    def update_link(self, master, record):
        """
            Create a new link in a link table if it doesn't yet exist.
            This function is meant to also update links in "embed"
            actuation mode once this gets implemented, therefore the
            method name "update_link".

            Args:
                master: the master record
                record: the new component record to be linked
        """

        if self.parent is None or self.linked is None:
            return None

        # Find the keys
        resource = self.linked
        pkey = resource.pkey
        lkey = resource.lkey
        rkey = resource.rkey
        fkey = resource.fkey
        if pkey not in master:
            return None
        _lkey = master[pkey]
        if fkey not in record:
            return None
        _rkey = record[fkey]
        if not _lkey or not _rkey:
            return None

        ltable = self.table
        ltn = ltable._tablename

        # Create the link if it does not already exist
        query = ((ltable[lkey] == _lkey) &
                 (ltable[rkey] == _rkey))
        row = current.db(query).select(ltable._id, limitby=(0, 1)).first()
        if not row:
            s3db = current.s3db
            onaccept = s3db.get_config(ltn, "create_onaccept")
            if onaccept is None:
                onaccept = s3db.get_config(ltn, "onaccept")
            data = {lkey:_lkey, rkey:_rkey}
            link_id = ltable.insert(**data)
            data[ltable._id.name] = link_id
            s3db.update_super(ltable, data)
            current.auth.s3_set_record_owner(ltable, data)
            if link_id and onaccept:
                callback(onaccept, Storage(vars=Storage(data)))
        else:
            link_id = row[ltable._id.name]
        return link_id

    # -------------------------------------------------------------------------
    def datatable_filter(self, fields, get_vars):
        """
            Parse datatable search/sort vars into a tuple of
            query, orderby and left joins

            Args:
                fields: list of field selectors representing
                        the order of fields in the datatable (list_fields)
                get_vars: the datatable GET vars

            Returns:
                tuple of (query, orderby, left joins)
        """

        db = current.db
        get_aliased = current.s3db.get_aliased

        left_joins = S3Joins(self.tablename)

        sSearch = "sSearch"
        iColumns = "iColumns"
        iSortingCols = "iSortingCols"

        parent = self.parent
        fkey = self.fkey

        # Skip joins for linked tables
        if self.linked is not None:
            skip = self.linked.tablename
        else:
            skip = None

        # Resolve the list fields
        rfields = self.resolve_selectors(fields)[0]

        # FILTER --------------------------------------------------------------

        searchq = None
        if sSearch in get_vars and iColumns in get_vars:

            # Build filter
            text = get_vars[sSearch]
            words = text.lower().split()

            if words:
                try:
                    numcols = int(get_vars[iColumns])
                except ValueError:
                    numcols = 0

                flist = []
                for i in range(numcols):
                    try:
                        rfield = rfields[i]
                        field = rfield.field
                    except (KeyError, IndexError):
                        continue
                    if field is None:
                        # Virtual
                        if hasattr(rfield, "search_field"):
                            field = db[rfield.tname][rfield.search_field]
                        else:
                            # Cannot search
                            continue
                    ftype = str(field.type)

                    # Add left joins
                    left_joins.extend(rfield.left)

                    if ftype[:9] == "reference" and \
                       hasattr(field, "sortby") and field.sortby:
                        # For foreign keys, we search through their sortby

                        # Get the lookup table
                        tn = ftype[10:]
                        if parent is not None and \
                           parent.tablename == tn and field.name != fkey:
                            alias = "%s_%s_%s" % (parent.prefix,
                                                  "linked",
                                                  parent.name)
                            ktable = get_aliased(db[tn], alias)
                            ktable._id = ktable[ktable._id.name]
                            tn = alias
                        elif tn == field.tablename:
                            prefix, name = field.tablename.split("_", 1)
                            alias = "%s_%s_%s" % (prefix, field.name, name)
                            ktable = get_aliased(db[tn], alias)
                            ktable._id = ktable[ktable._id.name]
                            tn = alias
                        else:
                            ktable = db[tn]

                        # Add left join for lookup table
                        if tn != skip:
                            left_joins.add(ktable.on(field == ktable._id))

                        if isinstance(field.sortby, (list, tuple)):
                            flist.extend([ktable[f] for f in field.sortby
                                                    if f in ktable.fields])
                        else:
                            if field.sortby in ktable.fields:
                                flist.append(ktable[field.sortby])

                    else:
                        # Otherwise, we search through the field itself
                        flist.append(field)

            # Build search query
            opts = Storage()
            queries = []
            for w in words:

                wqueries = []
                for field in flist:
                    ftype = str(field.type)
                    options = None
                    fname = str(field)
                    if fname in opts:
                        options = opts[fname]
                    elif ftype[:7] in ("integer",
                                       "list:in",
                                       "list:st",
                                       "referen",
                                       "list:re",
                                       "string"):
                        requires = field.requires
                        if not isinstance(requires, (list, tuple)):
                            requires = [requires]
                        if requires:
                            r = requires[0]
                            if isinstance(r, IS_EMPTY_OR):
                                r = r.other
                            if hasattr(r, "options"):
                                try:
                                    options = r.options()
                                except:
                                    options = []
                    if options is None and ftype in ("string", "text"):
                        wqueries.append(field.lower().like("%%%s%%" % w))
                    elif options is not None:
                        opts[fname] = options
                        vlist = [v for v, t in options
                                   if s3_str(t).lower().find(s3_str(w)) != -1]
                        if vlist:
                            wqueries.append(field.belongs(vlist))
                if len(wqueries):
                    queries.append(reduce(lambda x, y: x | y \
                                                 if x is not None else y,
                                          wqueries))
            if len(queries):
                searchq = reduce(lambda x, y: x & y \
                                        if x is not None else y, queries)

        # ORDERBY -------------------------------------------------------------

        orderby = []
        if iSortingCols in get_vars:

            # Sorting direction
            def direction(i):
                sort_dir = get_vars["sSortDir_%s" % str(i)]
                return " %s" % sort_dir if sort_dir else ""

            # Get the fields to order by
            try:
                numcols = int(get_vars[iSortingCols])
            except:
                numcols = 0

            columns = []
            pkey = str(self._id)
            for i in range(numcols):
                try:
                    iSortCol = int(get_vars["iSortCol_%s" % i])
                except (AttributeError, KeyError):
                    # iSortCol_x not present in get_vars => ignore
                    columns.append(Storage(field=None))
                    continue

                # Map sortable-column index to the real list_fields
                # index: for every non-id non-sortable column to the
                # left of sortable column subtract 1
                for j in range(iSortCol):
                    if get_vars.get("bSortable_%s" % j, "true") == "false":
                        try:
                            if rfields[j].colname != pkey:
                                iSortCol -= 1
                        except KeyError:
                            break

                try:
                    rfield = rfields[iSortCol]
                except IndexError:
                    # iSortCol specifies a non-existent column, i.e.
                    # iSortCol_x>=numcols => ignore
                    columns.append(Storage(field=None))
                else:
                    columns.append(rfield)

            # Process the orderby-fields
            for i in range(len(columns)):
                rfield = columns[i]
                field = rfield.field
                if field is None:
                    continue
                ftype = str(field.type)

                represent = field.represent
                if ftype == "json":
                    # Can't sort by JSON fields
                    # => try using corresponding id column to maintain some
                    #    fake yet consistent sort order:
                    tn = field.tablename
                    try:
                        orderby.append("%s%s" % (db[tn]._id, direction(i)))
                    except AttributeError:
                        continue
                elif not hasattr(represent, "skip_dt_orderby") and \
                   hasattr(represent, "dt_orderby"):
                    # Custom orderby logic in field.represent
                    field.represent.dt_orderby(field,
                                               direction(i),
                                               orderby,
                                               left_joins)

                elif ftype[:9] == "reference" and \
                   hasattr(field, "sortby") and field.sortby:
                    # Foreign keys with sortby will be sorted by sortby

                    # Get the lookup table
                    tn = ftype[10:]
                    if parent is not None and \
                       parent.tablename == tn and field.name != fkey:
                        alias = "%s_%s_%s" % (parent.prefix, "linked", parent.name)
                        ktable = get_aliased(db[tn], alias)
                        ktable._id = ktable[ktable._id.name]
                        tn = alias
                    elif tn == field.tablename:
                        prefix, name = field.tablename.split("_", 1)
                        alias = "%s_%s_%s" % (prefix, field.name, name)
                        ktable = get_aliased(db[tn], alias)
                        ktable._id = ktable[ktable._id.name]
                        tn = alias
                    else:
                        ktable = db[tn]

                    # Add left joins for lookup table
                    if tn != skip:
                        left_joins.extend(rfield.left)
                        left_joins.add(ktable.on(field == ktable._id))

                    # Construct orderby from sortby
                    if not isinstance(field.sortby, (list, tuple)):
                        orderby.append("%s.%s%s" % (tn, field.sortby, direction(i)))
                    else:
                        orderby.append(", ".join(["%s.%s%s" %
                                                  (tn, fn, direction(i))
                                                  for fn in field.sortby]))

                else:
                    # Otherwise, we sort by the field itself
                    orderby.append("%s%s" % (field, direction(i)))

        if orderby:
            orderby = ", ".join(orderby)
        else:
            orderby = None

        left_joins = left_joins.as_list(tablenames=list(left_joins.joins.keys()))
        return (searchq, orderby, left_joins)

    # -------------------------------------------------------------------------
    def prefix_selector(self, selector):
        """
            Helper method to ensure consistent prefixing of field selectors

            Args:
                selector: the selector
        """

        head = selector.split("$", 1)[0]
        if "." in head:
            prefix = head.split(".", 1)[0]
            if prefix == self.alias:
                return selector.replace("%s." % prefix, "~.")
            else:
                return selector
        else:
            return "~.%s" % selector

    # -------------------------------------------------------------------------
    def list_fields(self, key="list_fields", id_column=0, request=None):
        """
            Get the list_fields for this resource

            Args:
                key: alternative key for the table configuration
                id_column: - False to exclude the record ID
                           - True to include it if it is configured
                           - 0 to make it the first column regardless
                             whether it is configured or not
        """

        if key == "list_fields":
            list_fields = self.active_list_fields(request) if request else None
        else:
            list_fields = self.get_config(key)
        if not list_fields:
            list_fields = self.get_config("list_fields")
        if not list_fields:
            list_fields = [f.name for f in self.readable_fields()]

        id_field = pkey = self._id.name

        # Do not include the parent key for components
        if self.parent and not self.link and \
           not current.response.s3.component_show_key:
            fkey = self.fkey
        else:
            fkey = None

        fields = []
        append = fields.append
        selectors = set()
        seen = selectors.add
        for f in list_fields:
            selector = f[1] if type(f) is tuple else f
            if fkey and selector == fkey:
                continue
            if selector == pkey and not id_column:
                id_field = f
            elif selector not in selectors:
                seen(selector)
                append(f)

        if id_column is not False and id_column == 0:
            fields.insert(0, id_field)

        return fields

    # -------------------------------------------------------------------------
    def active_list_fields(self, request):
        """
            Uses the aCols URL parameter to determine the active list_fields
            and their order in variable-columns data tables and exports

            Args:
                request: the (CRUD)Request to read the aCols parameter from

            Returns:
                list_fields configuration (a list) or None if aCols is not applicable
        """

        available = self.get_config("available_list_fields")
        if available:
            available = [f for f in available if f]

        active = None
        if available and "aCols" in request.get_vars:
            try:
                selected = request.get_vars.aCols.split(",")
                selected = [int(index) for index in selected]
            except (TypeError, ValueError):
                pass
            else:
                try:
                    active = [available[i] for i in selected]
                except IndexError:
                    pass

        return active

    # -------------------------------------------------------------------------
    def get_defaults(self, master, defaults=None, data=None):
        """
            Get implicit defaults for new component records

            Args:
                master: the master record
                defaults: any explicit defaults
                data: any actual values for the new record

            Returns:
                a dict of {fieldname: values} with the defaults
        """

        values = {}

        parent = self.parent
        if not parent:
            # Not a component
            return values

        # Implicit defaults from component filters
        hook = current.s3db.get_component(parent.tablename, self.alias)
        filterby = hook.get("filterby")
        if filterby:
            for (k, v) in filterby.items():
                if not isinstance(v, (tuple, list)):
                    values[k] = v

        # Explicit defaults from component hook
        if self.defaults:
            values.update(self.defaults)

        # Explicit defaults from caller
        if defaults:
            values.update(defaults)

        # Actual record values
        if data:
            values.update(data)

        # Check for values to look up from master record
        lookup = {}
        for (k, v) in list(values.items()):
            # Skip nonexistent fields
            if k not in self.fields:
                del values[k]
                continue
            # Resolve any field selectors
            if isinstance(v, FS):
                try:
                    rfield = v.resolve(parent)
                except (AttributeError, SyntaxError):
                    continue
                field = rfield.field
                if not field or field.table != parent.table:
                    continue
                if field.name in master:
                    values[k] = master[field.name]
                else:
                    del values[k]
                    lookup[field.name] = k

        # Do we need to reload the master record to look up values?
        if lookup:
            row = None
            parent_id = parent._id
            record_id = master.get(parent_id.name)
            if record_id:
                fields = [parent.table[f] for f in lookup]
                row = current.db(parent_id == record_id).select(limitby = (0, 1),
                                                                *fields).first()
            if row:
                for (k, v) in lookup.items():
                    if k in row:
                        values[v] = row[k]

        return values

    # -------------------------------------------------------------------------
    @property
    def _table(self):
        """
            Get the original Table object (without SQL Alias), this
            is required for SQL update (DAL doesn't detect the alias
            and uses the wrong tablename).
        """

        if self.tablename != self._alias:
            return current.s3db[self.tablename]
        else:
            return self.table

# END =========================================================================
