"""
    Resource Data Reader

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

import json

from itertools import chain

from gluon import current
from gluon.html import TAG
from gluon.storage import Storage

from s3dal import Expression, Field, Row, Rows, S3DAL, VirtualCommand
from ..tools import s3_str

from .query import S3Joins

osetattr = object.__setattr__
ogetattr = object.__getattribute__

# =============================================================================
class ResourceData:
    """ Class representing data in a resource """

    def __init__(self,
                 resource,
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
                 raw_data = False
                 ):
        """
            Constructor, extracts (and represents) data from a resource

            Args:
                resource: the resource
                fields: the fields to extract (selector strings)
                start: index of the first record
                limit: maximum number of records
                left: additional left joins required for custom filters
                orderby: orderby-expression for DAL
                groupby: fields to group by (overrides fields!)
                distinct: select distinct rows
                virtual: include mandatory virtual fields
                count: include the total number of matching records
                getids: include the IDs of all matching records
                as_rows: return the rows (don't extract/represent)
                represent: render field value representations
                raw_data: include raw data in the result

            Notes:
                - as_rows / groupby prevent automatic splitting of
                  large multi-table joins, so use with care!
                - with groupby, only the groupby fields will be returned
                  (i.e. fields will be ignored), because aggregates are
                  not supported (yet)
        """

        db = current.db

        # Suppress instantiation of LazySets in rows where we don't need them
        if not as_rows and not groupby:
            rname = db._referee_name
            db._referee_name = None
        else:
            rname = None

        # The resource
        self.resource = resource
        self.table = table = resource.table

        # If postprocessing is required, always include raw data
        postprocess = resource.get_config("postprocess_select")
        if postprocess:
            raw_data = True

        # Dict to collect accessible queries for differential
        # field authorization (each joined table is authorized
        # separately)
        self.aqueries = aqueries = {}

        # Retain the current accessible-context of the parent
        # resource in reverse component joins:
        parent = resource.parent
        if parent and parent.accessible_query is not None:
            method = []
            if parent._approved:
                method.append("read")
            if parent._unapproved:
                method.append("review")
            aqueries[parent.tablename] = parent.accessible_query(method,
                                                                 parent.table,
                                                                 )

        # Joins (inner/left)
        tablename = table._tablename
        self.ijoins = ijoins = S3Joins(tablename)
        self.ljoins = ljoins = S3Joins(tablename)

        # The query
        master_query = query = resource.get_query()

        # Joins from filters
        # NB in components, rfilter is None until after get_query!
        rfilter = resource.rfilter
        filter_tables = set(ijoins.add(rfilter.get_joins(left=False)))
        filter_tables.update(ljoins.add(rfilter.get_joins(left=True)))

        # Left joins from caller
        master_tables = set(ljoins.add(left))
        filter_tables.update(master_tables)

        resolve = resource.resolve_selectors

        # Virtual fields and extra fields required by filter
        virtual_fields = rfilter.get_fields()
        vfields, vijoins, vljoins, d = resolve(virtual_fields, show=False)
        extra_tables = set(ijoins.extend(vijoins))
        extra_tables.update(ljoins.extend(vljoins))
        distinct |= d

        # Display fields (fields to include in the result)
        if fields is None:
            fields = [f.name for f in resource.readable_fields()]
        dfields, dijoins, dljoins, d = resolve(fields, extra_fields=False)
        ijoins.extend(dijoins)
        ljoins.extend(dljoins)
        distinct |= d

        # Primary key
        pkey = str(table._id)

        # Initialize field data and effort estimates
        if not groupby or as_rows:
            self.init_field_data(dfields)
        else:
            self.field_data = self.effort = None

        # Resolve ORDERBY
        orderby, orderby_aggr, orderby_fields, tables = self.resolve_orderby(orderby)
        if tables:
            filter_tables.update(tables)

        # Joins for filter query
        filter_ijoins = ijoins.as_list(tablenames = filter_tables,
                                       aqueries = aqueries,
                                       prefer = ljoins,
                                       )
        filter_ljoins = ljoins.as_list(tablenames = filter_tables,
                                       aqueries = aqueries,
                                       )

        # Virtual fields filter
        vfilter = resource.get_filter()

        # Extra filters
        efilter = rfilter.get_extra_filters()

        # Is this a paginated request?
        pagination = limit is not None or start

        # Subselect?
        subselect = bool(ljoins or ijoins or efilter or vfilter and pagination)

        # Do we need a filter query?
        fq = count_only = False
        if not groupby:
            end_count = (vfilter or efilter) and not pagination
            if count and not end_count:
                fq = True
                count_only = True
            if subselect or \
               getids and pagination or \
               extra_tables and extra_tables != filter_tables:
                fq = True
                count_only = False

        # Shall we use scalability-optimized strategies?
        bigtable = current.deployment_settings.get_base_bigtable()

        # Filter Query:
        # If we need to determine the number and/or ids of all matching
        # records, but not to extract all records, then we run a
        # separate query here to extract just this information:
        ids = page = totalrows = None
        if fq:
            # Execute the filter query
            if bigtable and not vfilter:
                limitby = resource.limitby(start=start, limit=limit)
            else:
                limitby = None
            totalrows, ids = self.filter_query(query,
                                               join = filter_ijoins,
                                               left = filter_ljoins,
                                               getids = not count_only,
                                               orderby = orderby_aggr,
                                               limitby = limitby,
                                               )

        # Simplify the master query if possible
        empty = False
        limitby = None
        orderby_on_limitby = True

        # If we know all possible record IDs from the filter query,
        # then we can simplify the master query so it doesn't need
        # complex joins
        if ids is not None:
            if not ids:
                # No records matching the filter query, so we
                # can skip the master query too
                empty = True
            else:
                # Which records do we need to extract?
                if pagination and (efilter or vfilter):
                    master_ids = ids
                else:
                    if bigtable:
                        master_ids = page = ids
                    else:
                        limitby = resource.limitby(start=start, limit=limit)
                        if limitby:
                            page = ids[limitby[0]:limitby[1]]
                        else:
                            page = ids
                        master_ids = page

                # Simplify master query
                if page is not None and not page:
                    # Empty page, skip the master query
                    empty = True
                    master_query = None
                elif len(master_ids) == 1:
                    # Single record, don't use belongs (faster)
                    master_query = table._id == master_ids[0]
                else:
                    master_query = table._id.belongs(set(master_ids))

                orderby = None
                if not ljoins and not ijoins:
                    # Without joins, there can only be one row per id,
                    # so we can limit the master query (faster)
                    limitby = (0, len(master_ids))
                    # Prevent automatic ordering
                    orderby_on_limitby = False
                else:
                    # With joins, there could be more than one row per id,
                    # so we can not limit the master query
                    limitby = None

        elif pagination and not (efilter or vfilter or count or getids):

            limitby = resource.limitby(start=start, limit=limit)

        if not empty:
            # If we don't use a simplified master_query, we must include
            # all necessary joins for filter and orderby (=filter_tables) in
            # the master query
            if ids is None and (filter_ijoins or filter_ljoins):
                master_tables = filter_tables

            # Determine fields in master query
            if not groupby:
                master_tables.update(extra_tables)
            tables, qfields, mfields, groupby = self.master_fields(dfields,
                                                                   vfields,
                                                                   master_tables,
                                                                   as_rows = as_rows,
                                                                   groupby = groupby,
                                                                   )
            # Additional tables to join?
            if tables:
                master_tables.update(tables)

            # ORDERBY settings
            if groupby:
                distinct = False
                orderby = orderby_aggr
                has_id = pkey in qfields
            else:
                if distinct and orderby:
                    # With DISTINCT, ORDERBY-fields must appear in SELECT
                    # (required by postgresql?)
                    for orderby_field in orderby_fields:
                        fn = str(orderby_field)
                        if fn not in qfields:
                            qfields[fn] = orderby_field

                # Make sure we have the primary key in SELECT
                if pkey not in qfields:
                    qfields[pkey] = resource._id
                has_id = True

            # Execute master query
            db = current.db

            master_fields = list(qfields.keys())
            if not groupby and not pagination and \
               has_id and ids and len(master_fields) == 1:
                # We already have the ids, and master query doesn't select
                # anything else => skip the master query, construct Rows from
                # ids instead
                master_id = table._id.name
                rows = Rows(db,
                            [Row({master_id: record_id}) for record_id in ids],
                            colnames = [pkey],
                            compact = False,
                            )
                # Add field methods (some do work from bare ids)
                try:
                    fields_lazy = [(f.name, f) for f in table._virtual_methods]
                except (AttributeError, TypeError):
                    # Incompatible PyDAL version
                    pass
                else:
                    if fields_lazy:
                        for row in rows:
                            for f, v in fields_lazy:
                                try:
                                    row[f] = (v.handler or VirtualCommand)(v.f, row)
                                except (AttributeError, KeyError):
                                    pass
            else:
                # Joins for master query
                master_ijoins = ijoins.as_list(tablenames = master_tables,
                                               aqueries = aqueries,
                                               prefer = ljoins,
                                               )
                master_ljoins = ljoins.as_list(tablenames = master_tables,
                                               aqueries = aqueries,
                                               )

                # Suspend (mandatory) virtual fields if so requested
                if not virtual:
                    vf = table.virtualfields
                    osetattr(table, "virtualfields", [])

                rows = db(master_query).select(join = master_ijoins,
                                               left = master_ljoins,
                                               distinct = distinct,
                                               groupby = groupby,
                                               orderby = orderby,
                                               limitby = limitby,
                                               orderby_on_limitby = orderby_on_limitby,
                                               cacheable = not as_rows,
                                               *list(qfields.values()))

                # Restore virtual fields
                if not virtual:
                    osetattr(table, "virtualfields", vf)

        else:
            rows = Rows(current.db)

        # Apply any virtual/extra filters, determine the subset
        if not len(rows) and not ids:

            # Empty set => empty subset (no point to filter/count)
            page = []
            ids = []
            totalrows = 0

        elif not groupby:
            if efilter or vfilter:

                # Filter by virtual fields
                shortcut = False
                if vfilter:
                    if pagination and not any((getids, count, efilter)):
                        # Don't need ids or totalrows
                        rows = rfilter(rows, start=start, limit=limit)
                        page = self.getids(rows, pkey)
                        shortcut = True
                    else:
                        rows = rfilter(rows)

                # Extra filter
                if efilter:
                    if vfilter or not ids:
                        ids = self.getids(rows, pkey)
                    if pagination and not (getids or count):
                        limit_ = start + limit
                    else:
                        limit_ = None
                    ids = rfilter.apply_extra_filters(ids, limit = limit_)
                    rows = self.getrows(rows, ids, pkey)

                if pagination:
                    # Subset selection with vfilter/efilter
                    # (=post-filter pagination)
                    if not shortcut:
                        if not efilter:
                            ids = self.getids(rows, pkey)
                        totalrows = len(ids)
                        rows, page = self.subset(rows, ids,
                                                 start = start,
                                                 limit = limit,
                                                 has_id = has_id,
                                                 )
                else:
                    # Unlimited select with vfilter/efilter
                    if not efilter:
                        ids = self.getids(rows, pkey)
                    page = ids
                    totalrows = len(ids)

            elif pagination:

                if page is None:
                    if limitby:
                        # Limited master query without count/getids
                        # (=rows is the subset, only need page IDs)
                        page = self.getids(rows, pkey)
                    else:
                        # Limited select with unlimited master query
                        # (=getids/count without filter query, need subset)
                        if not ids:
                            ids = self.getids(rows, pkey)
                        # Build the subset
                        rows, page = self.subset(rows, ids,
                                                 start = start,
                                                 limit = limit,
                                                 has_id = has_id,
                                                 )
                        totalrows = len(ids)

            elif not ids:
                # Unlimited select without vfilter/efilter
                page = ids = self.getids(rows, pkey)
                totalrows = len(ids)

        # Build the result
        self.rfields = dfields
        self.numrows = 0 if totalrows is None else totalrows
        self.ids = ids

        if groupby or as_rows:
            # Just store the rows, no further queries or extraction
            self.rows = rows

        elif not rows:
            # No rows found => empty list
            self.rows = []

        else:
            # Extract the data from the master rows
            records = self.extract(rows,
                                   pkey,
                                   list(mfields),
                                   join = hasattr(rows[0], tablename),
                                   represent = represent,
                                   )

            # Extract the page record IDs if we don't have them yet
            if page is None:
                if ids is None:
                    self.ids = ids = self.getids(rows, pkey)
                page = ids


            # Execute any joined queries
            joined_fields = self.joined_fields(dfields, qfields)
            joined_query = table._id.belongs(page)

            for jtablename, jfields in joined_fields.items():
                records = self.joined_query(jtablename,
                                            joined_query,
                                            jfields,
                                            records,
                                            represent = represent,
                                            )

            # Re-combine and represent the records
            results = {}

            field_data = self.field_data
            NONE = current.messages["NONE"]

            render = self.render
            for dfield in dfields:

                if represent:
                    # results = {RecordID: {ColumnName: Representation}}
                    results = render(dfield,
                                     results,
                                     none = NONE,
                                     raw_data = raw_data,
                                     show_links = show_links,
                                     )

                else:
                    # results = {RecordID: {ColumnName: Value}}
                    colname = dfield.colname

                    fdata = field_data[colname]
                    frecords = fdata[1]
                    list_type = fdata[3]

                    for record_id in records:
                        if record_id not in results:
                            result = results[record_id] = Storage()
                        else:
                            result = results[record_id]

                        data = list(frecords[record_id].keys())
                        if len(data) == 1 and not list_type:
                            data = data[0]
                        result[colname] = data

            self.rows = [results[record_id] for record_id in page]

        if rname:
            # Restore referee name
            db._referee_name = rname

        # Postprocess data (postprocess_select hook of the resource):
        # Allow the callback to modify the selected data before
        # returning them to the caller, callback receives:
        # - a dict with the data {record_id: row}
        # - the list of resource fields
        # - the represent-flag to indicate represented data
        # - the as_rows-flag to indicate bare Rows in the data dict
        # NB the callback must not remove fields from the rows
        if postprocess:
            postprocess(dict(zip(page, self.rows)),
                        rfields = dfields,
                        represent = represent,
                        as_rows = bool(as_rows or groupby),
                        )

    # -------------------------------------------------------------------------
    def init_field_data(self, rfields):
        """
            Initialize field data and effort estimates for representation

            Field data: allow representation per unique value (rather than
                        record by record), together with bulk-represent this
                        can reduce the total lookup effort per field to a
                        single query

            Effort estimates: if no bulk-represent is available for a
                              list:reference, then a lookup per unique value
                              is only faster if the number of unique values
                              is significantly lower than the number of
                              extracted rows (and the number of values per
                              row), otherwise a per-row lookup is more
                              efficient.

                              E.g. 5 rows with 2 values each,
                                   10 unique values in total
                                   => row-by-row lookup more efficient
                                   (5 queries vs 10 queries)
                              but: 5 rows with 2 values each,
                                   2 unique values in total
                                   => value-by-value lookup is faster
                                   (5 queries vs 2 queries)

                              However: 15 rows with 15 values each,
                                       20 unique values in total
                                       => value-by-value lookup faster
                                       (15 queries á 15 values vs.
                                        20 queries á 1 value)!

                              The required effort is estimated
                              during the data extraction, and then used to
                              determine the lookup strategy for the
                              representation.

            Args:
                rfields: the fields to extract ([S3ResourceField])
        """

        table = self.resource.table
        tablename = table._tablename
        pkey = str(table._id)

        field_data = {pkey: ({}, {}, False, False, False, False)}
        effort = {pkey: 0}
        for dfield in rfields:
            colname = dfield.colname
            effort[colname] = 0
            ftype = dfield.ftype[:4]
            field_data[colname] = ({}, {},
                                   dfield.tname != tablename,
                                   ftype == "list",
                                   dfield.virtual,
                                   ftype == "json",
                                   )

        self.field_data = field_data
        self.effort = effort

        return

    # -------------------------------------------------------------------------
    def resolve_orderby(self, orderby):
        """
            Resolve the ORDERBY expression.

            Args:
                orderby: the orderby expression from the caller

            Returns:
                tuple (expr, aggr, fields, tables):
                        expr: the orderby expression (resolved into Fields)
                        aggr: the orderby expression with aggregations
                        fields: the fields in the orderby
                        tables: the tables required for the orderby

            Note:
                for GROUPBY id (e.g. filter query), all ORDERBY fields
                must appear in aggregation functions, otherwise ORDERBY
                can be ambiguous => use aggr instead of expr
        """

        table = self.resource.table
        tablename = table._tablename
        pkey = str(table._id)

        ljoins = self.ljoins
        ijoins = self.ijoins

        tables = set()
        adapter = S3DAL()

        if orderby:

            db = current.db
            items = self.resolve_expression(orderby)

            expr = []
            aggr = []
            fields = []

            for item in items:

                expression = None

                if type(item) is Expression:
                    f = item.first
                    op = item.op
                    if op == adapter.AGGREGATE:
                        # Already an aggregation
                        expression = item
                    elif isinstance(f, Field) and op == adapter.INVERT:
                        direction = "desc"
                    else:
                        # Other expression - not supported
                        continue
                elif isinstance(item, Field):
                    direction = "asc"
                    f = item
                elif isinstance(item, str):
                    fn, direction = (item.strip().split() + ["asc"])[:2]
                    tn, fn = ([tablename] + fn.split(".", 1))[-2:]
                    try:
                        f = db[tn][fn]
                    except (AttributeError, KeyError):
                        continue
                else:
                    continue

                fname = str(f)
                tname = fname.split(".", 1)[0]

                if tname != tablename:
                    if tname in ljoins or tname in ijoins:
                        tables.add(tname)
                    else:
                        # No join found for this field => skip
                        continue

                fields.append(f)
                if expression is None:
                    expression = f if direction == "asc" else ~f
                    expr.append(expression)
                    direction = direction.strip().lower()[:3]
                    if fname != pkey:
                        expression = f.min() if direction == "asc" else ~(f.max())
                else:
                    expr.append(expression)
                aggr.append(expression)

        else:
            expr = None
            aggr = None
            fields = None

        return expr, aggr, fields, tables

    # -------------------------------------------------------------------------
    def filter_query(self,
                     query,
                     join = None,
                     left = None,
                     getids = False,
                     limitby = None,
                     orderby = None,
                     ):
        """
            Execute a query to determine the number/record IDs of all
            matching rows

            Args:
                query: the filter query
                join: the inner joins for the query
                left: the left joins for the query
                getids: extract the IDs of matching records
                limitby: tuple of indices (start, end) to extract only
                         a limited set of IDs
                orderby: ORDERBY expression for the query

            Returns:
                tuple of (TotalNumberOfRecords, RecordIDs)
        """

        db = current.db

        table = self.table

        # Temporarily deactivate virtual fields
        vf = table.virtualfields
        osetattr(table, "virtualfields", [])

        if getids and limitby:
            # Large result sets expected on average (settings.base.bigtable)
            # => effort almost independent of result size, much faster
            #    for large and very large filter results
            start = limitby[0]
            limit = limitby[1] - start

            # Don't penalize the smallest filter results (=effective filtering)
            if limit:
                maxids = max(limit, 200)
                limitby_ = (start, start + maxids)
            else:
                limitby_ = None

            # Extract record IDs
            field = table._id
            rows = db(query).select(field,
                                    join = join,
                                    left = left,
                                    limitby = limitby_,
                                    orderby = orderby,
                                    groupby = field,
                                    cacheable = True,
                                    )
            pkey = str(field)
            results = rows[:limit] if limit else rows
            ids = [row[pkey] for row in results]

            totalids = len(rows)
            if limit and totalids >= maxids or start != 0 and not totalids:
                # Count all matching records
                cnt = table._id.count(distinct=True)
                row = db(query).select(cnt,
                                       join = join,
                                       left = left,
                                       cacheable = True,
                                       ).first()
                totalrows = row[cnt]
            else:
                # We already know how many there are
                totalrows = start + totalids

        elif getids:
            # Extract all matching IDs, then count them in Python
            # => effort proportional to result size, slightly faster
            #    than counting separately for small filter results
            field = table._id
            rows = db(query).select(field,
                                    join=join,
                                    left=left,
                                    orderby = orderby,
                                    groupby = field,
                                    cacheable = True,
                                    )
            pkey = str(field)
            ids = [row[pkey] for row in rows]
            totalrows = len(ids)

        else:
            # Only count, do not extract any IDs (constant effort)
            field = table._id.count(distinct=True)
            rows = db(query).select(field,
                                    join = join,
                                    left = left,
                                    cacheable = True,
                                    )
            ids = None
            totalrows = rows.first()[field]

        # Restore the virtual fields
        osetattr(table, "virtualfields", vf)

        return totalrows, ids

    # -------------------------------------------------------------------------
    def master_fields(self,
                      dfields,
                      vfields,
                      joined_tables,
                      as_rows = False,
                      groupby = None
                      ):
        """
            Find all tables and fields to retrieve in the master query

            Args:
                dfields: the requested fields (S3ResourceFields)
                vfields: the virtual filter fields
                joined_tables: the tables joined in the master query
                as_rows: whether to produce web2py Rows
                groupby: the GROUPBY expression from the caller

            Returns:
                tuple (tables, fields, extract, groupby):
                        tables: the tables required to join
                        fields: the fields to retrieve
                        extract: the fields to extract from the result
                        groupby: the GROUPBY expression (resolved into Fields)
        """

        db = current.db
        tablename = self.resource.table._tablename

        # Names of additional tables to join
        tables = set()

        # Fields to retrieve in the master query, as dict {ColumnName: Field}
        fields = {}

        # Column names of fields to extract from the master rows
        extract = set()

        if groupby:
            # Resolve the groupby into Fields
            items = self.resolve_expression(groupby)

            groupby = []
            groupby_append = groupby.append
            for item in items:

                # Identify the field
                tname = None
                if isinstance(item, Field):
                    f = item
                elif isinstance(item, str):
                    fn = item.strip()
                    tname, fn = ([tablename] + fn.split(".", 1))[-2:]
                    try:
                        f = db[tname][fn]
                    except (AttributeError, KeyError):
                        continue
                else:
                    continue
                groupby_append(f)

                # Add to fields
                fname = str(f)
                if not tname:
                    tname = f.tablename
                fields[fname] = f

                # Do we need to join additional tables?
                if tname == tablename:
                    # no join required
                    continue
                # Get joins from dfields
                tnames = None
                for dfield in dfields:
                    if dfield.colname == fname:
                        tnames = self.rfield_tables(dfield)
                        break
                if tnames:
                    tables |= tnames
                else:
                    # Join at least the table that holds the fields
                    tables.add(tname)

            # Only extract GROUPBY fields (as we don't support aggregates)
            extract = set(fields.keys())

        else:
            rfields = dfields + vfields
            for rfield in rfields:

                # Is the field in a joined table?
                tname = rfield.tname
                joined = tname == tablename or tname in joined_tables

                if as_rows or joined:
                    colname = rfield.colname
                    if rfield.show:
                        # If show => add to extract
                        extract.add(colname)
                    if rfield.field:
                        # If real field => add to fields
                        fields[colname] = rfield.field
                    if not joined:
                        # Not joined yet? => add all required tables
                        tables |= self.rfield_tables(rfield)

        return tables, fields, extract, groupby

    # -------------------------------------------------------------------------
    def joined_fields(self, all_fields, master_fields):
        """
            Determine which fields in joined tables haven't been
            retrieved in the master query

            Args:
                all_fields: all requested fields (list of S3ResourceFields)
                master_fields: all fields in the master query, a dict
                               {ColumnName: Field}

            Returns:
                a nested dict {TableName: {ColumnName: Field}},
                additionally required left joins are stored per table in the
                inner dict as "_left"
        """

        resource = self.resource
        table = resource.table
        tablename = table._tablename

        fields = {}
        for rfield in all_fields:

            colname = rfield.colname
            if colname in master_fields or rfield.tname == tablename:
                continue
            tname = rfield.tname

            if tname not in fields:
                sfields = fields[tname] = {}
                left = rfield.left
                joins = S3Joins(table)
                for tn in left:
                    joins.add(left[tn])
                sfields["_left"] = joins
            else:
                sfields = fields[tname]

            if colname not in sfields:
                sfields[colname] = rfield.field

        return fields

    # -------------------------------------------------------------------------
    def joined_query(self, tablename, query, fields, records, represent=False):
        """
            Extract additional fields from a joined table: if there are
            fields in joined tables which haven't been extracted in the
            master query, then we perform a separate query for each joined
            table (this is faster than building a multi-table-join)

            Args:
                tablename: name of the joined table
                query: the Query
                fields: the fields to extract
                records: the output dict to update, structure:
                         {RecordID: {ColumnName: RawValues}}
                represent: store extracted data (self.field_data) for
                           fast representation, and estimate lookup
                           efforts (self.effort)

            Returns:
                the output dict
        """

        s3db = current.s3db

        ljoins = self.ljoins
        table = self.resource.table
        pkey = str(table._id)

        # Get the extra fields for subtable
        sresource = s3db.resource(tablename)
        efields, ejoins, l, d = sresource.resolve_selectors([])

        # Get all left joins for subtable
        tnames = ljoins.extend(l) + list(fields["_left"].tables)
        sjoins = ljoins.as_list(tablenames = tnames,
                                aqueries = self.aqueries,
                                )
        if not sjoins:
            return records
        del fields["_left"]

        # Get all fields for subtable query
        extract = list(fields.keys())
        for efield in efields:
            fields[efield.colname] = efield.field
        sfields = [f for f in fields.values() if f]
        if not sfields:
            sfields.append(sresource._id)
        sfields.insert(0, table._id)

        # Retrieve the subtable rows
        # - can't use distinct with native JSON fields
        distinct = not any(f.type == "json" for f in sfields)
        rows = current.db(query).select(left = sjoins,
                                        distinct = distinct,
                                        cacheable = True,
                                        *sfields)

        # Extract and merge the data
        records = self.extract(rows,
                               pkey,
                               extract,
                               records = records,
                               join = True,
                               represent = represent,
                               )

        return records

    # -------------------------------------------------------------------------
    def extract(self,
                rows,
                pkey,
                columns,
                join = True,
                records = None,
                represent = False
                ):
        """
            Extract the data from rows and store them in self.field_data

            Args:
                rows: the rows
                pkey: the primary key
                columns: the columns to extract
                join: the rows are the result of a join query
                records: the records dict to merge the data into
                represent: collect unique values per field and estimate
                           representation efforts for list:types
        """

        field_data = self.field_data
        effort = self.effort

        if records is None:
            records = {}

        def get(key):
            t, f = key.split(".", 1)
            if join:
                def getter(row):
                    return ogetattr(ogetattr(row, t), f)
            else:
                def getter(row):
                    return ogetattr(row, f)
            return getter

        getkey = get(pkey)
        getval = [get(c) for c in columns]

        from itertools import groupby
        for k, g in groupby(rows, key=getkey):
            group = list(g)
            record = records.get(k, {})
            for idx, col in enumerate(columns):
                fvalues, frecords, joined, list_type, virtual, json_type = field_data[col]
                values = record.get(col, {})
                lazy = False
                for row in group:
                    try:
                        value = getval[idx](row)
                    except AttributeError:
                        current.log.warning("Warning CRUDResource.extract: column %s not in row" % col)
                        value = None
                    if lazy or callable(value):
                        # Lazy virtual field
                        value = value()
                        lazy = True
                    if virtual and not list_type and type(value) is list:
                        # Virtual field that returns a list
                        list_type = True
                    if list_type and value is not None:
                        if represent and value:
                            effort[col] += 30 + len(value)
                        for v in value:
                            if v not in values:
                                values[v] = None
                            if represent and v not in fvalues:
                                fvalues[v] = None
                    elif json_type:
                        # Returns unhashable types
                        value = json.dumps(value)
                        if value not in values:
                            values[value] = None
                        if represent and value not in fvalues:
                            fvalues[value] = None
                    else:
                        if value not in values:
                            values[value] = None
                        if represent and value not in fvalues:
                            fvalues[value] = None
                record[col] = values
                if k not in frecords:
                    frecords[k] = record[col]
            records[k] = record

        return records

    # -------------------------------------------------------------------------
    def render(self,
               rfield,
               results,
               none = "-",
               raw_data = False,
               show_links = True
               ):
        """
            Render the representations of the values for rfield in
            all records in the result

            Args:
                rfield: the field (S3ResourceField)
                results: the output dict to update with the representations,
                         structure: {RecordID: {ColumnName: Representation}},
                         the raw data will be a special item "_row" in the
                         inner dict holding a Storage of the raw field values
                none: default representation of None
                raw_data: retain the raw data in the output dict
                show_links: allow representation functions to render
                            links as HTML
        """

        colname = rfield.colname

        fvalues, frecords, joined, list_type = self.field_data[colname][:4]

        # Get the renderer
        renderer = rfield.represent
        if not callable(renderer):
            # @ToDo: Don't convert unformatted numbers to strings
            renderer = lambda v: s3_str(v) if v is not None else none

        # Deactivate linkto if so requested
        if not show_links and hasattr(renderer, "show_link"):
            show_link = renderer.show_link
            renderer.show_link = False
        else:
            show_link = None

        # Use per-row lookup for list:types, unless its a reference type
        # and the estimated lookup effort would exceed bulk-lookup effort
        per_row_lookup = list_type and \
                         (rfield.ftype != "list:reference" or self.effort[colname] < len(fvalues) * 30)

        # Treat even single values as lists?
        # - can be set as class attribute of custom S3Represents
        always_list = hasattr(renderer, "always_list") and renderer.always_list

        # Render all unique values
        if hasattr(renderer, "bulk") and not list_type:
            per_row_lookup = False
            fvalues = renderer.bulk(list(fvalues.keys()), list_type=False)
        elif not per_row_lookup:
            for value in fvalues:
                try:
                    text = renderer(value)
                except:
                    #raise
                    text = s3_str(value)
                fvalues[value] = text

        # Write representations into result
        for record_id in frecords:

            if record_id not in results:
                results[record_id] = Storage() \
                                     if not raw_data \
                                     else Storage(_row=Storage())

            record = frecords[record_id]
            result = results[record_id]

            # List type with per-row lookup?
            if per_row_lookup:
                value = list(record.keys())
                if None in value and len(value) > 1:
                    value = [v for v in value if v is not None]
                try:
                    text = renderer(value)
                except:
                    text = s3_str(value)
                result[colname] = text
                if raw_data:
                    result["_row"][colname] = value

            # Single value (master record)
            elif len(record) == 1 and not always_list or \
                not joined and not list_type:
                value = list(record.keys())[0]
                result[colname] = fvalues[value] \
                                  if value in fvalues else none
                if raw_data:
                    result["_row"][colname] = value
                continue

            # Multiple values (joined or list-type, or explicit always_list)
            else:
                if hasattr(renderer, "render_list"):
                    # Prefer S3Represent's render_list (so it can be customized)
                    data = renderer.render_list(list(record.keys()),
                                                fvalues,
                                                show_link = show_links,
                                                )
                else:
                    # Build comma-separated list of values
                    vlist = []
                    for value in record:
                        if value is None and not list_type:
                            continue
                        value = fvalues[value] \
                                if value in fvalues else none
                        vlist.append(value)

                    if any(hasattr(v, "xml") for v in vlist):
                        data = TAG[""](
                                list(
                                    chain.from_iterable(
                                        [(v, ", ") for v in vlist])
                                    )[:-1]
                                )
                    else:
                        data = ", ".join([s3_str(v) for v in vlist])

                result[colname] = data
                if raw_data:
                    result["_row"][colname] = list(record.keys())

        # Restore linkto
        if show_link is not None:
            renderer.show_link = show_link

        return results

    # -------------------------------------------------------------------------
    def __getitem__(self, key):
        """
            Helper method to access the results as dict items, for
            backwards-compatibility

            Args:
                key: the key

            TODO migrate use-cases to .<key> notation, then deprecate
        """

        if key in ("rfields", "numrows", "ids", "rows"):
            return getattr(self, key)
        else:
            raise AttributeError

    # -------------------------------------------------------------------------
    @staticmethod
    def getids(rows, pkey):
        """
            Extract all unique record IDs from rows, preserving the
            order by first match

            Args:
                rows: the Rows
                pkey: the primary key

            Returns:
                list of unique record IDs
        """

        x = set()
        seen = x.add

        result = []
        append = result.append
        for row in rows:
            row_id = row[pkey]
            if row_id not in x:
                seen(row_id)
                append(row_id)
        return result

    # -------------------------------------------------------------------------
    @staticmethod
    def getrows(rows, ids, pkey):
        """
            Select a subset of rows by their record IDs

            Args:
                rows: the Rows
                ids: the record IDs
                pkey: the primary key

            Returns:
                the subset (Rows)
        """

        if ids:
            ids = set(ids)
            subset = lambda row: row[pkey] in ids
        else:
            subset = lambda row: False
        return rows.find(subset)

    # -------------------------------------------------------------------------
    @staticmethod
    def subset(rows, ids, start=None, limit=None, has_id=True):
        """
            Build a subset [start:limit] from rows and ids

            Args:
                rows: the Rows
                ids: all matching record IDs
                start: start index of the page
                limit: maximum length of the page
                has_id: whether the Rows contain the primary key

            Returns:
                tuple (rows, page), with:
                        rows = the Rows in the subset, in order
                        page = the record IDs in the subset, in order
        """

        if limit and start is None:
            start = 0

        if start is not None and limit is not None:
            rows = rows[start:start+limit]
            page = ids[start:start+limit]

        elif start is not None:
            rows = rows[start:]
            page = ids[start:]

        else:
            page = ids

        return rows, page

    # -------------------------------------------------------------------------
    @staticmethod
    def rfield_tables(rfield):
        """
            Get the names of all tables that need to be joined for a field

            Args:
                rfield: the field (S3ResourceField)

            Returns:
                a set of tablenames
        """

        left = rfield.left
        if left:
            # => add all left joins required for that table
            tablenames = set(j.first._tablename
                             for tn in left for j in left[tn])
        else:
            # => we don't know any further left joins,
            #    but as a minimum we need to add this table
            tablenames = {rfield.tname}

        return tablenames

    # -------------------------------------------------------------------------
    @staticmethod
    def resolve_expression(expr):
        """
            Resolve an orderby or groupby expression into its items

            Args:
                expr: the orderby/groupby expression
        """

        if isinstance(expr, str):
            items = expr.split(",")
        elif not isinstance(expr, (list, tuple)):
            items = [expr]
        else:
            items = expr
        return items

# END =========================================================================
