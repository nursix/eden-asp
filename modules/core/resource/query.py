"""
    S3 Query Construction

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

__all__ = ("FS",
           "S3FieldSelector",
           "S3Joins",
           "S3ResourceField",
           "S3ResourceQuery",
           "S3URLQuery",
           "S3URLQueryParser",
           "URLQueryJSON",
           )

import datetime
import json
import re
import sys

from functools import reduce
from urllib import parse as urlparse

from gluon import current, IS_EMPTY_OR, IS_IN_SET
from gluon.storage import Storage

from s3dal import Field, Row

from ..tools import S3RepresentLazy, S3TypeConverter, s3_get_foreign_key, s3_str

ogetattr = object.__getattribute__

TEXTTYPES = ("string", "text")

# =============================================================================
class S3FieldSelector:
    """ Helper class to construct a resource query """

    LOWER = "lower"
    UPPER = "upper"

    OPERATORS = [LOWER, UPPER]

    def __init__(self, name, type=None):

        if not isinstance(name, str) or not name:
            raise SyntaxError("name required")
        self.name = str(name)
        self.type = type

        self.op = None

    # -------------------------------------------------------------------------
    def __lt__(self, value):
        return S3ResourceQuery(S3ResourceQuery.LT, self, value)

    # -------------------------------------------------------------------------
    def __le__(self, value):
        return S3ResourceQuery(S3ResourceQuery.LE, self, value)

    # -------------------------------------------------------------------------
    def __eq__(self, value):
        return S3ResourceQuery(S3ResourceQuery.EQ, self, value)

    # -------------------------------------------------------------------------
    def __ne__(self, value):
        return S3ResourceQuery(S3ResourceQuery.NE, self, value)

    # -------------------------------------------------------------------------
    def __ge__(self, value):
        return S3ResourceQuery(S3ResourceQuery.GE, self, value)

    # -------------------------------------------------------------------------
    def __gt__(self, value):
        return S3ResourceQuery(S3ResourceQuery.GT, self, value)

    # -------------------------------------------------------------------------
    def like(self, value):
        return S3ResourceQuery(S3ResourceQuery.LIKE, self, value)

    # -------------------------------------------------------------------------
    def belongs(self, value):
        return S3ResourceQuery(S3ResourceQuery.BELONGS, self, value)

    # -------------------------------------------------------------------------
    def contains(self, value):
        return S3ResourceQuery(S3ResourceQuery.CONTAINS, self, value)

    # -------------------------------------------------------------------------
    def anyof(self, value):
        return S3ResourceQuery(S3ResourceQuery.ANYOF, self, value)

    # -------------------------------------------------------------------------
    def typeof(self, value):
        return S3ResourceQuery(S3ResourceQuery.TYPEOF, self, value)

    # -------------------------------------------------------------------------
    def intersects(self, value):
        return S3ResourceQuery(S3ResourceQuery.INTERSECTS, self, value)

    # -------------------------------------------------------------------------
    def lower(self):
        self.op = self.LOWER
        return self

    # -------------------------------------------------------------------------
    def upper(self):
        self.op = self.UPPER
        return self

    # -------------------------------------------------------------------------
    def expr(self, val):

        ret = val

        if self.op and val is not None:
            if self.op == self.LOWER and \
               hasattr(val, "lower") and callable(val.lower) and \
               (not isinstance(val, Field) or val.type in TEXTTYPES):
                ret = val.lower()
            elif self.op == self.UPPER and \
                 hasattr(val, "upper") and callable(val.upper) and \
                 (not isinstance(val, Field) or val.type in TEXTTYPES):
                ret = val.upper()

        return ret

    # -------------------------------------------------------------------------
    def represent(self, resource):

        try:
            rfield = S3ResourceField(resource, self.name)
        except (SyntaxError, AttributeError):
            colname = None
        else:
            colname = rfield.colname
        if colname:
            if self.op is not None:
                return "%s.%s()" % (colname, self.op)
            else:
                return colname
        else:
            return "(%s?)" % self.name

    # -------------------------------------------------------------------------
    @classmethod
    def extract(cls, resource, row, field):
        """
            Extract a value from a Row

            Args:
                resource: the resource
                row: the Row
                field: the field

            Returns:
                field if field is not a Field/S3FieldSelector instance,
                the value from the row otherwise
        """

        error = lambda fn: KeyError("Field not found: %s" % fn)

        t = type(field)

        if isinstance(field, Field):
            colname = str(field)
            tname, fname = colname.split(".", 1)

        elif t is S3FieldSelector:
            rfield = S3ResourceField(resource, field.name)
            colname = rfield.colname
            if not colname:
                # unresolvable selector
                raise error(field.name)
            fname = rfield.fname
            tname = rfield.tname

        elif t is S3ResourceField:
            colname = field.colname
            if not colname:
                # unresolved selector
                return None
            fname = field.fname
            tname = field.tname

        else:
            return field

        if type(row) is Row:
            try:
                if tname in row.__dict__:
                    value = ogetattr(ogetattr(row, tname), fname)
                else:
                    value = ogetattr(row, fname)
            except AttributeError:
                try:
                    value = row[colname]
                except (KeyError, AttributeError):
                    raise error(colname)
        elif fname in row:
            value = row[fname]
        elif colname in row:
            value = row[colname]
        elif tname is not None and \
             tname in row and fname in row[tname]:
            value = row[tname][fname]
        else:
            raise error(colname)

        if callable(value):
            # Lazy virtual field
            try:
                value = value()
            except:
                t, m = sys.exc_info()[:2]
                current.log.error("%s.%s: %s" % (tname, fname, str(m) or t.__name__))
                value = None

        if hasattr(field, "expr"):
            return field.expr(value)
        return value

    # -------------------------------------------------------------------------
    def resolve(self, resource):
        """
            Resolve this field against a resource

            Args:
                resource: the resource
        """

        return S3ResourceField(resource, self.name)

# =============================================================================
# Short name for the S3FieldSelector class
#
FS = S3FieldSelector

# =============================================================================
class S3FieldPath:
    """ Helper class to parse field selectors """

    # -------------------------------------------------------------------------
    @classmethod
    def resolve(cls, resource, selector, tail=None):
        """
            Resolve a selector (=field path) against a resource

            Args:
                resource: the CRUDResource to resolve against
                selector: the field selector string
                tail: tokens to append to the selector

            The general syntax for a selector is:

            selector = {[alias].}{[key]$}[field|selector]

            (Parts in {} are optional, | indicates alternatives)

            * Alias can be:

            ~           refers to the resource addressed by the
                        preceding parts of the selector (=last
                        resource)
            component   alias of a component of the last resource
            linktable   alias of a link table of the last resource
            table       name of a table that has a foreign key for
                        the last resource (auto-detect the key)
            key:table   same as above, but specifying the foreign key

            * Key can be:

            key         the name of a foreign key in the last resource
            context     a context expression

            * Field can be:

            fieldname   the name of a field or virtual field of the
                        last resource
            context     a context expression

            A "context expression" is a name enclosed in parentheses:

            (context)

            During parsing, context expressions get replaced by the
            string which has been configured for this name for the
            last resource with:

            s3db.configure(tablename, context = dict(name = "string"))

            With context expressions, the same selector can be used
            for different resources, each time resolving into the
            specific field path. However, the field addressed must
            be of the same type in all resources to form valid
            queries.

            If a context name can not be resolved, resolve() will
            still succeed - but the S3FieldPath returned will have
            colname=None and ftype="context" (=unresolvable context).
        """

        if not selector:
            raise SyntaxError("Invalid selector: %s" % selector)
        tokens = re.split(r"(\.|\$)", selector)
        if tail:
            tokens.extend(tail)
        parser = cls(resource, None, tokens)
        parser.original = selector
        return parser

    # -------------------------------------------------------------------------
    def __init__(self, resource, table, tokens):
        """
            Constructor - not to be called directly, use resolve() instead

            Args:
                resource: the CRUDResource
                table: the table
                tokens: the tokens as list
        """

        s3db = current.s3db

        if table is None:
            table = resource.table

        # Initialize
        self.original = None
        tname = self.tname = table._tablename
        self.fname = None
        self.field = None
        self.method = None
        self.ftype = None
        self.virtual = False
        self.colname = None

        self.joins = {}

        self.distinct = False
        self.multiple = True

        head = tokens.pop(0)
        tail = None

        if head and head[0] == "(" and head[-1] == ")":

            # Context expression
            head = head.strip("()")
            self.fname = head
            self.ftype = "context"

            if not resource:
                resource = s3db.resource(table, components=[])
            context = resource.get_config("context")
            if context and head in context:
                tail = self.resolve(resource, context[head], tail=tokens)
            else:
                # unresolvable
                pass

        elif tokens:

            # Resolve the tail
            op = tokens.pop(0)
            if tokens:

                if op == ".":
                    # head is a component or linktable alias, and tokens is
                    # a field expression in the component/linked table
                    if not resource:
                        resource = s3db.resource(table, components=[])
                    ktable, join, m, d = self._resolve_alias(resource, head)
                    self.multiple = m
                    self.distinct = d
                else:
                    # head is a foreign key in the current table and tokens is
                    # a field expression in the referenced table
                    ktable, join = self._resolve_key(table, head)
                    self.distinct = True

                if join is not None:
                    self.joins[ktable._tablename] = join
                tail = S3FieldPath(None, ktable, tokens)

            else:
                raise SyntaxError("trailing operator")

        if tail is None:

            # End of the expression
            if self.ftype != "context":
                # Expression is resolved, head is a field name:
                field, method = self._resolve_field(table, head)
                if not field:
                    self.virtual = True
                    self.field = None
                    self.method = method
                    self.ftype = "virtual"
                else:
                    self.virtual = False
                    self.field = field
                    self.method = None
                    self.ftype = str(field.type)
                self.fname = head
                self.colname = "%s.%s" % (tname, head)
        else:
            # Read field data from tail
            self.tname = tail.tname
            self.fname = tail.fname
            self.field = tail.field
            self.method = tail.method
            self.ftype = tail.ftype
            self.virtual = tail.virtual
            self.colname = tail.colname

            self.distinct |= tail.distinct
            self.multiple |= tail.multiple

            self.joins.update(tail.joins)

    # -------------------------------------------------------------------------
    @staticmethod
    def _resolve_field(table, fieldname):
        """
            Resolve a field name against the table, recognizes "id" as
            table._id.name, and "uid" as current.xml.UID.

            Args:
                table: the Table
                fieldname: the field name

            Returns:
                tuple (Field, Field.Method)
        """

        method = None

        if fieldname == "uid":
            fieldname = current.xml.UID

        if fieldname == "id":
            field = table._id
        elif fieldname in table.fields:
            field = ogetattr(table, fieldname)
        else:
            # Virtual Field
            field = None
            try:
                method = ogetattr(table, fieldname)
            except AttributeError:
                # not yet defined, skip
                pass

        return field, method

    # -------------------------------------------------------------------------
    @staticmethod
    def _resolve_key(table, fieldname):
        """
            Resolve a foreign key into the referenced table and the
            join and left join between the current table and the
            referenced table

            Args:
                table: the current Table
                fieldname: the fieldname of the foreign key

            Returns:
                tuple of (referenced table, join, left join)

            Raises:
                AttributeError: if either the field or the referended table
                                are not found
                SyntaxError: if the field is not a foreign key
        """

        if fieldname in table.fields:
            f = table[fieldname]
        else:
            raise AttributeError("key not found: %s" % fieldname)

        ktablename, pkey = s3_get_foreign_key(f, m2m=False)[:2]

        if not ktablename:
            raise SyntaxError("%s is not a foreign key" % f)

        ktable = current.s3db.table(ktablename,
                                    AttributeError("undefined table %s" % ktablename),
                                    db_only=True)

        pkey = ktable[pkey] if pkey else ktable._id
        join = [ktable.on(f == pkey)]

        return ktable, join

    # -------------------------------------------------------------------------
    @staticmethod
    def _resolve_alias(resource, alias):
        """
            Resolve a table alias into the linked table (component, linktable
            or free join), and the joins and left joins between the current
            resource and the linked table.

            Args:
                resource: the current CRUDResource
                alias: the alias

            Returns:
                tuple of (linked table, joins, left joins, multiple, distinct),
                the two latter being flags to indicate possible ambiguous query
                results (needed by the query builder)

            Raises:
                AttributeError: if one of the key fields or tables cannot
                                be found
                SyntaxError: if the alias can not be resolved (e.g. because
                             one of the keys isn't a foreign key, points to
                             the wrong table or is ambiguous)
        """

        # Alias for this resource?
        if alias in ("~", resource.alias):
            return resource.table, None, False, False

        multiple = True

        linked = resource.linked
        if linked and linked.alias == alias:

            # It's the linked table
            linktable = resource.table

            ktable = linked.table
            join = [ktable.on(ktable[linked.fkey] == linktable[linked.rkey])]

            return ktable, join, multiple, True

        component = resource.components.get(alias)
        if component:
            # Component alias
            ktable = component.table
            join = component._join()
            multiple = component.multiple
        else:
            s3db = current.s3db
            tablename = resource.tablename
            calias = s3db.get_alias(tablename, alias)
            if calias:
                # Link alias
                component = resource.components.get(calias)
                link = component.link
                ktable = link.table
                join = link._join()
            elif "_" in alias:
                # Free join
                pkey = fkey = None

                # Find the table
                fkey, kname = (alias.split(":") + [None])[:2]
                if not kname:
                    fkey, kname = kname, fkey
                ktable = s3db.table(kname,
                                    AttributeError("table not found: %s" % kname),
                                    db_only=True,
                                    )

                if fkey is None:
                    # Autodetect left key
                    for fname in ktable.fields:
                        tn, key = s3_get_foreign_key(ktable[fname], m2m=False)[:2]
                        if not tn:
                            continue
                        if tn == tablename:
                            if fkey is not None:
                                raise SyntaxError("ambiguous foreign key in %s" % alias)
                            fkey = fname
                            if key:
                                pkey = key
                    if fkey is None:
                        raise SyntaxError("no foreign key for %s in %s" %
                                          (tablename, kname))

                else:
                    # Check left key
                    if fkey not in ktable.fields:
                        raise AttributeError("no field %s in %s" % (fkey, kname))

                    tn, pkey = s3_get_foreign_key(ktable[fkey], m2m=False)[:2]
                    if tn and tn != tablename:
                        raise SyntaxError("%s.%s is not a foreign key for %s" %
                                          (kname, fkey, tablename))
                    elif not tn:
                        raise SyntaxError("%s.%s is not a foreign key" %
                                          (kname, fkey))

                # Default primary key
                table = resource.table
                if pkey is None:
                    pkey = table._id.name

                # Build join
                query = (table[pkey] == ktable[fkey])
                DELETED = current.xml.DELETED
                if DELETED in ktable.fields:
                    query &= ktable[DELETED] == False
                join = [ktable.on(query)]

            else:
                raise SyntaxError("Invalid tablename: %s" % alias)

        return ktable, join, multiple, True

# =============================================================================
class S3ResourceField:
    """ Helper class to resolve a field selector against a resource """

    # -------------------------------------------------------------------------
    def __init__(self, resource, selector, label=None):
        """
            Args:
                resource: the resource
                selector: the field selector (string)
        """

        self.resource = resource
        self.selector = selector

        lf = S3FieldPath.resolve(resource, selector)

        self.tname = lf.tname
        self.fname = lf.fname
        self.colname = lf.colname

        self._joins = lf.joins

        self.distinct = lf.distinct
        self.multiple = lf.multiple

        self._join = None

        self.field = lf.field

        self.virtual = False
        self.represent = s3_str
        self.requires = None

        if self.field is not None:
            field = self.field
            self.ftype = str(field.type)
            if resource.linked is not None and self.ftype == "id":
                # Always represent the link-table's ID as the
                # linked record's ID => needed for data tables
                self.represent = lambda i, resource=resource: \
                                           resource.component_id(None, i)
            else:
                self.represent = field.represent
            self.requires = field.requires
        elif self.colname:
            self.virtual = True
            self.ftype = "virtual"
            # Check whether the fieldmethod handler has a
            # representation method (s3_fieldmethod)
            method = lf.method
            if hasattr(method, "handler"):
                handler = method.handler
                if hasattr(handler, "represent"):
                    self.represent = handler.represent
                if hasattr(handler, "search_field"):
                    self.search_field = handler.search_field
        else:
            self.ftype = "context"

        # Fall back to the field label
        if label is None:
            fname = self.fname
            if fname in ["L1", "L2", "L3", "L3", "L4", "L5"]:
                try:
                    label = current.gis.get_location_hierarchy(fname)
                except:
                    label = None
            elif fname == "L0":
                label = current.messages.COUNTRY
            if label is None:
                f = self.field
                if f:
                    label = f.label
                elif fname:
                    label = " ".join([s.strip().capitalize()
                                      for s in fname.split("_") if s])
                else:
                    label = None

        self.label = label
        self.show = True

        # Field type category flags
        self._is_numeric = None
        self._is_lookup = None
        self._is_string = None
        self._is_datetime = None
        self._is_reference = None
        self._is_list = None

    # -------------------------------------------------------------------------
    def __repr__(self):
        """ String representation of this instance """

        return "<S3ResourceField " \
               "selector='%s' " \
               "label='%s' " \
               "table='%s' " \
               "field='%s' " \
               "type='%s'>" % \
               (self.selector, self.label, self.tname, self.fname, self.ftype)

    # -------------------------------------------------------------------------
    @property
    def join(self):
        """
            Implicit join (Query) for this field, for backwards-compatibility
        """

        if self._join is not None:
            return self._join

        join = self._join = {}
        for tablename, joins in self._joins.items():
            query = None
            for expression in joins:
                if query is None:
                    query = expression.second
                else:
                    query &= expression.second
            if query:
                join[tablename] = query
        return join

    # -------------------------------------------------------------------------
    @property
    def left(self):
        """
            The left joins for this field, for backwards-compability
        """

        return self._joins

    # -------------------------------------------------------------------------
    def extract(self, row, represent=False, lazy=False):
        """
            Extract the value for this field from a row

            Args:
                row: the Row
                represent: render a text representation for the value
                lazy: return a lazy representation handle if available
        """

        tname = self.tname
        fname = self.fname
        colname = self.colname
        error = "Field not found in Row: %s" % colname

        if type(row) is Row:
            try:
                if tname in row.__dict__:
                    value = ogetattr(ogetattr(row, tname), fname)
                else:
                    value = ogetattr(row, fname)
            except AttributeError:
                try:
                    value = row[colname]
                except (KeyError, AttributeError):
                    raise KeyError(error)
        elif fname in row:
            value = row[fname]
        elif colname in row:
            value = row[colname]
        elif tname is not None and \
             tname in row and fname in row[tname]:
            value = row[tname][fname]
        else:
            raise KeyError(error)

        if callable(value):
            # Lazy virtual field
            try:
                value = value()
            except:
                current.log.error(sys.exc_info()[1])
                value = None

        if represent:
            renderer = self.represent
            if callable(renderer):
                if lazy and hasattr(renderer, "bulk"):
                    return S3RepresentLazy(value, renderer)
                else:
                    return renderer(value)
            else:
                return s3_str(value)
        else:
            return value

    # -------------------------------------------------------------------------
    @property
    def is_lookup(self):
        """
            Check whether the field type is a fixed set lookup (IS_IN_SET)

            Returns:
                True if field type is a fixed set lookup, else False
        """

        is_lookup = self._is_lookup
        if is_lookup is None:

            is_lookup = False

            field = self.field

            if field:
                requires = field.requires
                if requires:
                    if not isinstance(requires, (list, tuple)):
                        requires = [requires]
                    requires = requires[0]
                    if isinstance(requires, IS_EMPTY_OR):
                        requires = requires.other
                    if isinstance(requires, IS_IN_SET):
                        is_lookup = True
                if is_lookup and requires and self.ftype == "integer":
                    # Discrete numeric values?
                    options = requires.options(zero=False)
                    if all(k == v for k, v in options):
                        is_lookup = False
            self._is_lookup = is_lookup
        return is_lookup

    # -------------------------------------------------------------------------
    @property
    def is_numeric(self):
        """
            Check whether the field type is numeric (lazy property)

            Returns:
                True if field type is integer or double, else False
        """

        is_numeric = self._is_numeric
        if is_numeric is None:

            ftype = self.ftype

            if ftype == "integer" and self.is_lookup:
                is_numeric = False
            else:
                is_numeric = ftype in ("integer", "double")
            self._is_numeric = is_numeric
        return is_numeric

    # -------------------------------------------------------------------------
    @property
    def is_string(self):
        """
            Check whether the field type is a string type (lazy property)

            Returns:
                True if field type is string or text, else False
        """

        is_string = self._is_string
        if is_string is None:
            is_string = self.ftype in ("string", "text")
            self._is_string = is_string
        return is_string

    # -------------------------------------------------------------------------
    @property
    def is_datetime(self):
        """
            Check whether the field type is date/time (lazy property)

            Returns:
                True if field type is datetime, date or time, else False
        """

        is_datetime = self._is_datetime
        if is_datetime is None:
            is_datetime = self.ftype in ("datetime", "date", "time")
            self._is_datetime = is_datetime
        return is_datetime

    # -------------------------------------------------------------------------
    @property
    def is_reference(self):
        """
            Check whether the field type is a reference (lazy property)

            Returns:
                True if field type is a reference, else False
        """

        is_reference = self._is_reference
        if is_reference is None:
            is_reference = self.ftype[:9] == "reference"
            self._is_reference = is_reference
        return is_reference

    # -------------------------------------------------------------------------
    @property
    def is_list(self):
        """
            Check whether the field type is a list (lazy property)

            Returns:
                True if field type is a list, else False
        """

        is_list = self._is_list
        if is_list is None:
            is_list = self.ftype[:5] == "list:"
            self._is_list = is_list
        return is_list

# =============================================================================
class S3Joins:
    """ A collection of joins """

    def __init__(self, tablename, joins=None):
        """
            Args:
                tablename: the name of the master table
                joins: list of joins
        """

        self.tablename = tablename
        self.joins = {}
        self.tables = set()

        self.add(joins)

    # -------------------------------------------------------------------------
    def __iter__(self):
        """
            Iterate over the names of all joined tables in the collection
        """

        return self.joins.__iter__()

    # -------------------------------------------------------------------------
    def __getitem__(self, tablename):
        """
            Get the list of joins for a table

            Args:
                tablename: the tablename
        """

        return self.joins.__getitem__(tablename)

    # -------------------------------------------------------------------------
    def __setitem__(self, tablename, joins):
        """
            Update the joins for a table

            Args:
                tablename: the tablename
                joins: the list of joins for this table
        """

        master = self.tablename
        joins_dict = self.joins

        tables = current.db._adapter.tables

        joins_dict[tablename] = joins
        if len(joins) > 1:
            for join in joins:
                try:
                    tname = join.first._tablename
                except AttributeError:
                    tname = str(join.first)
                if tname not in joins_dict and \
                   master in tables(join.second):
                    joins_dict[tname] = [join]
        self.tables.add(tablename)
        return

    # -------------------------------------------------------------------------
    def __len__(self):
        """
            Return the number of tables in the join, for boolean
            test of this instance ("if joins:")
        """

        return len(self.tables)

    # -------------------------------------------------------------------------
    def keys(self):
        """
            Get a list of names of all joined tables
        """

        return list(self.joins.keys())

    # -------------------------------------------------------------------------
    def items(self):
        """
            Get a list of tuples (tablename, [joins]) for all joined tables
        """

        return list(self.joins.items())

    # -------------------------------------------------------------------------
    def values(self):
        """
            Get a list of joins for all joined tables

            Returns:
                a nested list like [[join, join, ...], ...]
        """

        return list(self.joins.values())

    # -------------------------------------------------------------------------
    def add(self, joins):
        """
            Add joins to this collection

            Args:
                joins: a join or a list/tuple of joins

            Returns:
                the list of names of all tables for which joins have been
                added to the collection
        """

        tablenames = set()
        if joins:
            if not isinstance(joins, (list, tuple)):
                joins = [joins]
            for join in joins:
                tablename = join.first._tablename
                self[tablename] = [join]
                tablenames.add(tablename)
        return list(tablenames)

    # -------------------------------------------------------------------------
    def extend(self, other):
        """
            Extend this collection with the joins from another collection

            Args:
                other: the other collection (S3Joins), or a dict like
                       {tablename: [join, join]}

            Returns:
                the list of names of all tables for which joins have been
                added to the collection
        """

        if type(other) is S3Joins:
            add = self.tables.add
        else:
            add = None
        joins = self.joins if type(other) is S3Joins else self
        for tablename in other:
            if tablename not in self.joins:
                joins[tablename] = other[tablename]
                if add:
                    add(tablename)
        return list(other.keys())

    # -------------------------------------------------------------------------
    def __repr__(self):
        """
            String representation of this collection
        """

        return "<S3Joins %s>" % str([str(j) for j in self.as_list()])

    # -------------------------------------------------------------------------
    def as_list(self, tablenames=None, aqueries=None, prefer=None):
        """
            Return joins from this collection as list

            Args:
                tablenames: the names of the tables for which joins
                            shall be returned, defaults to all tables
                            in the collection. Dependencies will be
                            included automatically (if available)
                aqueries: dict of accessible-queries {tablename: query}
                          to include in the joins; if there is no entry
                          for a particular table, then it will be looked
                          up from current.auth and added to the dict.
                          To prevent differential authorization of a
                          particular joined table, set {<tablename>: None}
                          in the dict
                prefer: If any table or any of its dependencies would be
                        joined by this S3Joins collection, then skip this
                        table here (and enforce it to be joined by the
                        preferred collection), to prevent duplication of
                        left joins as inner joins:
                        join = inner_joins.as_list(prefer=left_joins)
                        left = left_joins.as_list()

            Returns:
                a list of joins, ordered by their interdependency, which
                can be used as join/left parameter of Set.select()
        """

        accessible_query = current.auth.s3_accessible_query

        if tablenames is None:
            tablenames = self.tables
        else:
            tablenames = set(tablenames)

        skip = set()
        if prefer:
            preferred_joins = prefer.as_list(tablenames=tablenames)
            for join in preferred_joins:
                try:
                    tname = join.first._tablename
                except AttributeError:
                    tname = str(join.first)
                skip.add(tname)
        tablenames -= skip

        joins = self.joins

        # Resolve dependencies
        required_tables = set()
        get_tables = current.db._adapter.tables
        for tablename in tablenames:
            if tablename not in joins or \
               tablename == self.tablename or \
               tablename in skip:
                continue

            join_list = joins[tablename]
            preferred = False
            dependencies = set()
            for join in join_list:
                join_tables = set(get_tables(join.second))
                if join_tables:
                    if any((tname in skip for tname in join_tables)):
                        preferred = True
                    dependencies |= join_tables
            if preferred:
                skip.add(tablename)
                skip |= dependencies
                prefer.extend({tablename: join_list})
            else:
                required_tables.add(tablename)
                required_tables |= dependencies

        # Collect joins
        joins_dict = {}
        for tablename in required_tables:
            if tablename not in joins or tablename == self.tablename:
                continue
            for join in joins[tablename]:
                j = join
                table = j.first
                tname = table._tablename
                if aqueries is not None and tname in tablenames:
                    if tname not in aqueries:
                        aquery = accessible_query("read", table)
                        aqueries[tname] = aquery
                    else:
                        aquery = aqueries[tname]
                    if aquery is not None:
                        j = join.first.on(join.second & aquery)
                joins_dict[tname] = j

        # Sort joins (if possible)
        try:
            return self.sort(list(joins_dict.values()))
        except RuntimeError:
            return list(joins_dict.values())

    # -------------------------------------------------------------------------
    @classmethod
    def sort(cls, joins):
        """
            Sort a list of left-joins by their interdependency

            Args:
                joins: the list of joins
        """

        if len(joins) <= 1:
            return joins
        r = list(joins)

        tables = current.db._adapter.tables

        append = r.append
        head = None
        while r:
            head = join = r.pop(0)
            tablenames = tables(join.second)
            for j in r:
                try:
                    tn = j.first._tablename
                except AttributeError:
                    tn = str(j.first)
                if tn in tablenames:
                    head = None
                    break
            if head is not None:
                break
            else:
                append(join)
        if head is not None:
            return [head] + cls.sort(r)
        else:
            raise RuntimeError("circular join dependency")

# =============================================================================
class S3ResourceQuery:
    """
        Helper class representing a resource query
        - unlike DAL Query objects, these can be converted to/from URL filters
    """

    # Supported operators
    NOT = "not"
    AND = "and"
    OR = "or"
    LT = "lt"
    LE = "le"
    EQ = "eq"
    NE = "ne"
    GE = "ge"
    GT = "gt"
    LIKE = "like"
    BELONGS = "belongs"
    CONTAINS = "contains"
    ANYOF = "anyof"
    TYPEOF = "typeof"
    INTERSECTS = "intersects"

    COMPARISON = [LT, LE, EQ, NE, GE, GT,
                  LIKE, BELONGS, CONTAINS, ANYOF, TYPEOF, INTERSECTS]

    OPERATORS = [NOT, AND, OR] + COMPARISON

    # -------------------------------------------------------------------------
    def __init__(self, op, left=None, right=None):

        if op not in self.OPERATORS:
            raise SyntaxError("Invalid operator: %s" % op)

        self.op = op

        self.left = left
        self.right = right

    # -------------------------------------------------------------------------
    def __and__(self, other):
        """ AND """

        return S3ResourceQuery(self.AND, self, other)

    # -------------------------------------------------------------------------
    def __or__(self, other):
        """ OR """

        return S3ResourceQuery(self.OR, self, other)

    # -------------------------------------------------------------------------
    def __invert__(self):
        """ NOT """

        if self.op == self.NOT:
            return self.left
        else:
            return S3ResourceQuery(self.NOT, self)

    # -------------------------------------------------------------------------
    def _joins(self, resource, left=False):

        op = self.op
        l = self.left
        r = self.right

        if op in (self.AND, self.OR):
            if isinstance(l, S3ResourceQuery):
                ljoins, ld = l._joins(resource, left=left)
            else:
                ljoins, ld = {}, False
            if isinstance(r, S3ResourceQuery):
                rjoins, rd = r._joins(resource, left=left)
            else:
                rjoins, rd = {}, False

            ljoins = dict(ljoins)
            ljoins.update(rjoins)

            return (ljoins, ld or rd)

        elif op == self.NOT:
            if isinstance(l, S3ResourceQuery):
                return l._joins(resource, left=left)
            else:
                return {}, False

        joins, distinct = {}, False

        if isinstance(l, S3FieldSelector):
            try:
                rfield = l.resolve(resource)
            except (SyntaxError, AttributeError):
                pass
            else:
                distinct = rfield.distinct
                if distinct and left or not distinct and not left:
                    joins = rfield._joins

        return (joins, distinct)

    # -------------------------------------------------------------------------
    def fields(self):
        """ Get all field selectors involved with this query """

        op = self.op
        l = self.left
        r = self.right

        if op in (self.AND, self.OR):
            lf = l.fields()
            rf = r.fields()
            return lf + rf
        elif op == self.NOT:
            return l.fields()
        elif isinstance(l, S3FieldSelector):
            return [l.name]
        else:
            return []

    # -------------------------------------------------------------------------
    def split(self, resource):
        """
            Split this query into a real query and a virtual one (AND)

            Args:
                resource: the CRUDResource

            Returns:
                tuple (DAL-translatable sub-query, virtual filter),
                both S3ResourceQuery instances
        """

        op = self.op
        l = self.left
        r = self.right

        if op == self.AND:
            lq, lf = l.split(resource) \
                     if isinstance(l, S3ResourceQuery) else (l, None)
            rq, rf = r.split(resource) \
                     if isinstance(r, S3ResourceQuery) else (r, None)
            q = lq
            if rq is not None:
                if q is not None:
                    q &= rq
                else:
                    q = rq
            f = lf
            if rf is not None:
                if f is not None:
                    f &= rf
                else:
                    f = rf
            return q, f
        elif op == self.OR:
            lq, lf = l.split(resource) \
                     if isinstance(l, S3ResourceQuery) else (l, None)
            rq, rf = r.split(resource) \
                     if isinstance(r, S3ResourceQuery) else (r, None)
            if lf is not None or rf is not None:
                return None, self
            else:
                q = lq
                if rq is not None:
                    if q is not None:
                        q |= rq
                    else:
                        q = rq
                return q, None
        elif op == self.NOT:
            if isinstance(l, S3ResourceQuery):
                if l.op == self.OR:
                    i = (~(l.left)) & (~(l.right))
                    return i.split(resource)
                else:
                    q, f = l.split(resource)
                    if q is not None and f is not None:
                        return None, self
                    elif q is not None:
                        return ~q, None
                    elif f is not None:
                        return None, ~f
            else:
                return ~l, None

        l = self.left
        try:
            if isinstance(l, S3FieldSelector):
                lfield = l.resolve(resource)
            else:
                lfield = S3ResourceField(resource, l)
        except (SyntaxError, AttributeError):
            lfield = None
        if not lfield or lfield.field is None:
            return None, self
        else:
            return self, None

    # -------------------------------------------------------------------------
    def transform(self, resource):
        """
            Placeholder for transformation method

            Args:
                resource: the CRUDResource
        """

        # @todo: implement
        return self

    # -------------------------------------------------------------------------
    def query(self, resource):
        """
            Convert this S3ResourceQuery into a DAL query, ignoring virtual
            fields (the necessary joins for this query can be constructed
            with the joins() method)

            Args:
                resource: the resource to resolve the query against
        """

        op = self.op
        l = self.left
        r = self.right

        # Resolve query components
        if op == self.AND:
            l = l.query(resource) if isinstance(l, S3ResourceQuery) else l
            r = r.query(resource) if isinstance(r, S3ResourceQuery) else r
            if l is None or r is None:
                return None
            elif l is False or r is False:
                return l if r is False else r if l is False else False
            else:
                return l & r
        elif op == self.OR:
            l = l.query(resource) if isinstance(l, S3ResourceQuery) else l
            r = r.query(resource) if isinstance(r, S3ResourceQuery) else r
            if l is None or r is None:
                return None
            elif l is False or r is False:
                return l if r is False else r if l is False else False
            else:
                return l | r
        elif op == self.NOT:
            l = l.query(resource) if isinstance(l, S3ResourceQuery) else l
            if l is None:
                return None
            elif l is False:
                return False
            else:
                return ~l

        # Resolve the fields
        if isinstance(l, S3FieldSelector):
            try:
                rfield = S3ResourceField(resource, l.name)
            except (SyntaxError, AttributeError):
                return None
            if rfield.virtual:
                return None
            elif not rfield.field:
                return False
            lfield = l.expr(rfield.field)
        elif isinstance(l, Field):
            lfield = l
        else:
            return None # not a field at all
        if isinstance(r, S3FieldSelector):
            try:
                rfield = S3ResourceField(resource, r.name)
            except (SyntaxError, AttributeError):
                return None
            rfield = rfield.field
            if rfield.virtual:
                return None
            elif not rfield.field:
                return False
            rfield = r.expr(rfield.field)
        else:
            rfield = r

        # Resolve the operator
        invert = False
        query_bare = self._query_bare
        ftype = str(lfield.type)
        if isinstance(rfield, (list, tuple)) and ftype[:4] != "list":
            if op == self.EQ:
                op = self.BELONGS
            elif op == self.NE:
                op = self.BELONGS
                invert = True
            elif op not in (self.BELONGS, self.TYPEOF):
                query = None
                for v in rfield:
                    q = query_bare(op, lfield, v)
                    if q is not None:
                        if query is None:
                            query = q
                        else:
                            query |= q
                return query

        # Convert date(time) strings
        if ftype in ("date", "datetime") and isinstance(rfield, str):
            to_type = datetime.date if ftype == "date" else datetime.datetime
            rfield = S3TypeConverter.convert(to_type, rfield)

        # Catch invalid data types for primary/foreign keys (PyDAL doesn't)
        if op == self.EQ and rfield is not None and \
           (ftype == "id" or ftype[:9] == "reference"):
            try:
                rfield = int(rfield)
            except (ValueError, TypeError):
                # Right argument is an invalid key
                # => treat as 0 to prevent crash in SQL expansion
                rfield = 0

        query = query_bare(op, lfield, rfield)
        if invert and query is not None:
            query = ~query
        return query

    # -------------------------------------------------------------------------
    def _query_bare(self, op, l, r):
        """
            Translate a filter expression into a DAL query

            Args:
                op: the operator
                l: the left operand
                r: the right operand
        """

        if op == self.CONTAINS:
            q = l.contains(r, all=True)
        elif op == self.ANYOF:
            # NB str/int doesn't matter here
            q = l.contains(r, all=False)
        elif op == self.BELONGS:
            q = self._query_belongs(l, r)
        elif op == self.TYPEOF:
            q = self._query_typeof(l, r)
        elif op == self.LIKE:
            if current.deployment_settings.get_database_airegex():
                q = S3AIRegex.like(l, r)
            else:
                q = l.like(s3_str(r))
        elif op == self.INTERSECTS:
            q = self._query_intersects(l, r)
        elif op == self.LT:
            q = l < r
        elif op == self.LE:
            q = l <= r
        elif op == self.EQ:
            q = l == r
        elif op == self.NE:
            q = l != r
        elif op == self.GE:
            q = l >= r
        elif op == self.GT:
            q = l > r
        else:
            q = None
        return q

    # -------------------------------------------------------------------------
    def _query_typeof(self, l, r):
        """
            Translate TYPEOF into DAL expression

            Args:
                l: the left operand
                r: the right operand
        """

        hierarchy, field, nodeset, none = self._resolve_hierarchy(l, r)
        if not hierarchy:
            # Not a hierarchical query => use simple belongs
            return self._query_belongs(l, r)
        if not field:
            # Field does not exist (=>skip subquery)
            return None

        # Construct the subquery
        list_type = str(field.type)[:5] == "list:"
        if nodeset:
            if list_type:
                q = (field.contains(list(nodeset)))
            elif len(nodeset) > 1:
                q = (field.belongs(nodeset))
            else:
                q = (field == tuple(nodeset)[0])
        else:
            q = None

        if none:
            # None needs special handling with older DAL versions
            if not list_type:
                if q is None:
                    q = (field == None)
                else:
                    q |= (field == None)
        if q is None:
            # Values not resolvable (=subquery always fails)
            q = field.belongs(set())

        return q

    # -------------------------------------------------------------------------
    @classmethod
    def _resolve_hierarchy(cls, l, r):
        """
            Resolve the hierarchical lookup in a typeof-query

            Args:
                l: the left operand
                r: the right operand
        """

        from ..tools import S3Hierarchy

        tablename = l.tablename

        # Connect to the hierarchy
        hierarchy = S3Hierarchy(tablename)
        if hierarchy.config is None:
            # Reference to a hierarchical table?
            ktablename, key = s3_get_foreign_key(l)[:2]
            if ktablename:
                hierarchy = S3Hierarchy(ktablename)
        else:
            key = None

        list_type = str(l.type)[:5] == "list:"
        if hierarchy.config is None and not list_type:
            # No hierarchy configured and no list:reference
            return False, None, None, None

        field, keys = l, r

        if not key:

            s3db = current.s3db

            table = s3db[tablename]
            if l.name != table._id.name:
                # Lookup-field rather than primary key => resolve it

                # Build a filter expression for the lookup table
                fs = S3FieldSelector(l.name)
                if list_type:
                    expr = fs.contains(r)
                else:
                    expr = cls._query_belongs(l, r, field = fs)

                # Resolve filter expression into subquery
                resource = s3db.resource(tablename)
                if expr is not None:
                    subquery = expr.query(resource)
                else:
                    subquery = None
                if not subquery:
                    # Field doesn't exist
                    return True, None, None, None

                # Execute query and retrieve the lookup table IDs
                DELETED = current.xml.DELETED
                if DELETED in table.fields:
                    subquery &= table[DELETED] == False
                rows = current.db(subquery).select(table._id)

                # Override field/keys
                field = table[hierarchy.pkey.name]
                keys = {row[table._id.name] for row in rows}

        nodeset, none = None, False
        if keys:
            # Lookup all descendant types from the hierarchy
            none = False
            if not isinstance(keys, (list, tuple, set)):
                keys = {keys}
            nodes = set()
            for node in keys:
                if node is None:
                    none = True
                else:
                    try:
                        node_id = int(node)
                    except ValueError:
                        continue
                    nodes.add(node_id)
            if hierarchy.config is not None:
                nodeset = hierarchy.findall(nodes, inclusive=True)
            else:
                nodeset = nodes

        elif keys is None:
            none = True

        return True, field, nodeset, none

    # -------------------------------------------------------------------------
    @staticmethod
    def _query_belongs(l, r, field=None):
        """
            Resolve BELONGS into a DAL expression (or S3ResourceQuery if
            field is an S3FieldSelector)

            Args:
                l: the left operand
                r: the right operand
                field: alternative left operand
        """

        if field is None:
            field = l

        expr = None
        none = False

        if not isinstance(r, (list, tuple, set)):
            items = [r]
        else:
            items = r
        if None in items:
            none = True
            items = [item for item in items if item is not None]

        wildcard = False

        if str(l.type) in ("string", "text"):
            for item in items:
                if isinstance(item, str):
                    if "*" in item and "%" not in item:
                        s = item.replace("*", "%")
                    else:
                        s = item
                else:
                    s = s3_str(item)

                if "%" in s:
                    wildcard = True
                    _expr = (field.like(s))
                else:
                    _expr = (field == s)

                if expr is None:
                    expr = _expr
                else:
                    expr |= _expr

        if not wildcard:
            if len(items) == 1:
                # Don't use belongs() for single value
                expr = (field == tuple(items)[0])
            elif items:
                expr = (field.belongs(items))

        if none:
            # None needs special handling with older DAL versions
            if expr is None:
                expr = (field == None)
            else:
                expr |= (field == None)
        elif expr is None:
            expr = field.belongs(set())

        return expr

    # -------------------------------------------------------------------------
    def _query_intersects(self, l, r):
        """
            Resolve INTERSECTS into a DAL expression;
            will be ignored for non-spatial DBs

            Args:
                l: the left operand (Field)
                r: the right operand
        """

        if current.deployment_settings.get_gis_spatialdb():

            expr = None

            if str(l.type)[:3] == "geo":

                if isinstance(r, str):

                    # Assume WKT => validate it before constructing the query
                    #from shapely.geos import ReadingError as GEOSReadingError
                    from shapely.wkt import loads as wkt_loads
                    try:
                        wkt_loads(r)
                    except Exception: #GEOSReadingError:
                        # Invalid WKT => log and let default
                        # NB This will fail CIRCULARSTRING so maybe convert 1st:
                        # https://gis.stackexchange.com/questions/256123/how-to-convert-curved-features-into-geojson
                        current.log.error("INTERSECTS: %s" % sys.exc_info()[1])
                    else:
                        expr = l.st_intersects(r)

                elif hasattr(r, type) and str(r.type)[:3] == "geo":

                    expr = l.st_intersects(r)

            if expr is None:
                # Invalid operand => fail by default
                return l.belongs(set())

        else:
            # Ignore sub-query for non-spatial DB
            expr = False

        return expr

    # -------------------------------------------------------------------------
    def __call__(self, resource, row, virtual=True):
        """
            Probe whether the row matches the query

            Args:
                resource: the resource to resolve the query against
                row: the DB row
                virtual: execute only virtual queries
        """

        if self.op == self.AND:
            l = self.left(resource, row, virtual=False)
            r = self.right(resource, row, virtual=False)
            if l is None:
                return r
            if r is None:
                return l
            return l and r
        elif self.op == self.OR:
            l = self.left(resource, row, virtual=False)
            r = self.right(resource, row, virtual=False)
            if l is None:
                return r
            if r is None:
                return l
            return l or r
        elif self.op == self.NOT:
            l = self.left(resource, row)
            if l is None:
                return None
            else:
                return not l

        real = False
        left = self.left
        if isinstance(left, S3FieldSelector):
            try:
                lfield = left.resolve(resource)
            except (AttributeError, KeyError, SyntaxError):
                return None
            if lfield.field is not None:
                real = True
            elif not lfield.virtual:
                # Unresolvable expression => skip
                return None
        else:
            lfield = left
            if isinstance(left, Field):
                real = True
        right = self.right
        if isinstance(right, S3FieldSelector):
            try:
                rfield = right.resolve(resource)
            except (AttributeError, KeyError, SyntaxError):
                return None
            if rfield.virtual:
                real = False
            elif rfield.field is None:
                # Unresolvable expression => skip
                return None
        else:
            rfield = right
        if virtual and real:
            return None

        extract = lambda f: S3FieldSelector.extract(resource, row, f)
        try:
            l = extract(lfield)
            r = extract(rfield)
        except (KeyError, SyntaxError):
            current.log.error(sys.exc_info()[1])
            return None

        if isinstance(left, S3FieldSelector):
            l = left.expr(l)
        if isinstance(right, S3FieldSelector):
            r = right.expr(r)

        op = self.op
        invert = False
        probe = self._probe
        if isinstance(rfield, (list, tuple)) and \
           not isinstance(lfield, (list, tuple)):
            if op == self.EQ:
                op = self.BELONGS
            elif op == self.NE:
                op = self.BELONGS
                invert = True
            elif op != self.BELONGS:
                for v in r:
                    try:
                        r = probe(op, l, v)
                    except (TypeError, ValueError):
                        r = False
                    if r:
                        return True
                return False
        try:
            r = probe(op, l, r)
        except (TypeError, ValueError):
            return False
        if invert and r is not None:
            return not r
        else:
            return r

    # -------------------------------------------------------------------------
    def _probe(self, op, l, r):
        """
            Probe whether the value pair matches the query

            Args:
                l: the left value
                r: the right value
        """

        result = False
        convert = S3TypeConverter.convert

        # Fallbacks for TYPEOF
        if op == self.TYPEOF:
            if isinstance(l, (list, tuple, set)):
                op = self.ANYOF
            elif isinstance(r, (list, tuple, set)):
                op = self.BELONGS
            else:
                op = self.EQ

        if op == self.CONTAINS:
            r = convert(l, r)
            result = self._probe_contains(l, r)

        elif op == self.ANYOF:
            if not isinstance(r, (list, tuple, set)):
                r = [r]
            for v in r:
                if isinstance(l, (list, tuple, set, str)):
                    if self._probe_contains(l, v):
                        return True
                elif l == v:
                    return True
            return False

        elif op == self.BELONGS:
            if not isinstance(r, (list, tuple, set)):
                r = [r]
            r = convert(l, r)
            result = self._probe_contains(r, l)

        elif op == self.LIKE:
            # @todo: apply AIRegex if configured
            pattern = re.escape(str(r)).replace("\\%", ".*").replace(".*.*", "\\%")
            return re.match(pattern, str(l)) is not None

        else:
            r = convert(l, r)
            if op == self.LT:
                result = l < r
            elif op == self.LE:
                result = l <= r
            elif op == self.EQ:
                result = l == r
            elif op == self.NE:
                result = l != r
            elif op == self.GE:
                result = l >= r
            elif op == self.GT:
                result = l > r

        return result

    # -------------------------------------------------------------------------
    @staticmethod
    def _probe_contains(a, b):
        """
            Probe whether a contains b
        """

        if a is None:
            return False

        if isinstance(a, str):
            return s3_str(b) in s3_str(a)

        if isinstance(a, (list, tuple, set)):
            if isinstance(b, (list, tuple, set)):
                convert = S3TypeConverter.convert
                found = True
                for b_item in b:
                    if b_item not in a:
                        found = False
                        for a_item in a:
                            try:
                                if convert(a_item, b_item) == a_item:
                                    found = True
                                    break
                            except (TypeError, ValueError):
                                continue
                    if not found:
                        break
                return found
            else:
                return b in a
        else:
            return s3_str(b) in s3_str(a)

    # -------------------------------------------------------------------------
    def represent(self, resource):
        """
            Represent this query as a human-readable string.

            Args:
                resource: the resource to resolve the query against
        """

        op = self.op
        l = self.left
        r = self.right
        if op == self.AND:
            l = l.represent(resource) \
                if isinstance(l, S3ResourceQuery) else str(l)
            r = r.represent(resource) \
                if isinstance(r, S3ResourceQuery) else str(r)
            return "(%s and %s)" % (l, r)
        elif op == self.OR:
            l = l.represent(resource) \
                if isinstance(l, S3ResourceQuery) else str(l)
            r = r.represent(resource) \
                if isinstance(r, S3ResourceQuery) else str(r)
            return "(%s or %s)" % (l, r)
        elif op == self.NOT:
            l = l.represent(resource) \
                if isinstance(l, S3ResourceQuery) else str(l)
            return "(not %s)" % l
        else:
            if isinstance(l, S3FieldSelector):
                l = l.represent(resource)
            elif isinstance(l, str):
                l = '"%s"' % l
            if isinstance(r, S3FieldSelector):
                r = r.represent(resource)
            elif isinstance(r, str):
                r = '"%s"' % r
            if op == self.CONTAINS:
                return "(%s in %s)" % (r, l)
            elif op == self.BELONGS:
                return "(%s in %s)" % (l, r)
            elif op == self.ANYOF:
                return "(%s contains any of %s)" % (l, r)
            elif op == self.TYPEOF:
                return "(%s is a type of %s)" % (l, r)
            elif op == self.LIKE:
                return "(%s like %s)" % (l, r)
            elif op == self.LT:
                return "(%s < %s)" % (l, r)
            elif op == self.LE:
                return "(%s <= %s)" % (l, r)
            elif op == self.EQ:
                return "(%s == %s)" % (l, r)
            elif op == self.NE:
                return "(%s != %s)" % (l, r)
            elif op == self.GE:
                return "(%s >= %s)" % (l, r)
            elif op == self.GT:
                return "(%s > %s)" % (l, r)
            else:
                return "(%s ?%s? %s)" % (l, op, r)

    # -------------------------------------------------------------------------
    def serialize_url(self, resource=None):
        """
            Serialize this query as URL query

            Returns:
                a Storage of URL variables
        """

        op = self.op
        l = self.left
        r = self.right

        url_query = Storage()
        def _serialize(n, o, v, invert):
            try:
                quote = lambda s: s if "," not in s else '"%s"' % s
                if isinstance(v, list):
                    v = ",".join([quote(S3TypeConverter.convert(str, val))
                                  for val in v])
                else:
                    v = quote(S3TypeConverter.convert(str, v))
            except:
                return
            if "." not in n:
                if resource is not None:
                    n = "~.%s" % n
                else:
                    return url_query
            if o == self.LIKE:
                v = v.replace("%", "*")
            if o == self.EQ:
                operator = ""
            else:
                operator = "__%s" % o
            if invert:
                operator = "%s!" % operator
            key = "%s%s" % (n, operator)
            if key in url_query:
                url_query[key] = "%s,%s" % (url_query[key], v)
            else:
                url_query[key] = v
            return url_query
        if op == self.AND:
            lu = l.serialize_url(resource=resource)
            url_query.update(lu)
            ru = r.serialize_url(resource=resource)
            url_query.update(ru)
        elif op == self.OR:
            sub = self._or()
            if sub is None:
                # This OR-subtree is not serializable
                return url_query
            n, o, v, invert = sub
            _serialize(n, o, v, invert)
        elif op == self.NOT:
            lu = l.serialize_url(resource=resource)
            for k in lu:
                url_query["%s!" % k] = lu[k]
        elif isinstance(l, S3FieldSelector):
            _serialize(l.name, op, r, False)
        return url_query

    # -------------------------------------------------------------------------
    def _or(self):
        """
            Helper method to URL-serialize an OR-subtree in a query in
            alternative field selector syntax if they all use the same
            operator and value (this is needed to URL-serialize an
            S3SearchSimpleWidget query).
        """

        op = self.op
        l = self.left
        r = self.right

        if op == self.AND:
            return None
        elif op == self.NOT:
            lname, lop, lval, linv = l._or()
            return (lname, lop, lval, not linv)
        elif op == self.OR:
            lvars = l._or()
            rvars = r._or()
            if lvars is None or rvars is None:
                return None
            lname, lop, lval, linv = lvars
            rname, rop, rval, rinv = rvars
            if lop != rop or linv != rinv:
                return None
            if lname == rname:
                return (lname, lop, [lval, rval], linv)
            elif lval == rval:
                return ("%s|%s" % (lname, rname), lop, lval, linv)
            else:
                return None
        else:
            return (l.name, op, r, False)

# =============================================================================
class S3URLQuery:
    """ URL Query Parser """

    FILTEROP = re.compile(r"__(?!link\.)([_a-z\!]+)$")

    # -------------------------------------------------------------------------
    @classmethod
    def parse(cls, resource, get_vars):
        """
            Construct a Storage of S3ResourceQuery from a Storage of get_vars

            Args:
                resource: the CRUDResource
                get_vars: the get_vars

            Returns:
                Storage of S3ResourceQuery like {alias: query}, where
                alias is the alias of the component the query concerns
        """

        query = Storage()

        if resource is None or not get_vars:
            return query

        subquery = cls._subquery
        allof = lambda l, r: l if r is None else r if l is None else r & l

        for key, value in get_vars.items():

            if not key:
                continue

            if key == "$filter":
                # Instantiate the advanced filter parser
                parser = S3URLQueryParser()
                if parser.parser is None:
                    # not available
                    continue

                # Multiple $filter expressions?
                expressions = value if type(value) is list else [value]

                # Default alias (=master)
                default_alias = resource.alias

                # Parse all expressions
                for expression in expressions:
                    parsed = parser.parse(expression)
                    for alias in parsed:
                        q = parsed[alias]
                        qalias = alias if alias is not None else default_alias
                        if qalias not in query:
                            query[qalias] = [q]
                        else:
                            query[qalias].append(q)

                # Stop here
                continue

            if key[0] == "_" or not("." in key or key[0] == "(" and ")" in key):
                # Not a filter expression
                continue

            # Process old-style filters
            selectors, op, invert = cls.parse_expression(key)

            if type(value) is list:
                # Multiple queries with the same selector (AND)
                q = reduce(allof,
                           [subquery(selectors, op, invert, v) for v in value],
                           None)
            else:
                q = subquery(selectors, op, invert, value)

            if q is None:
                continue

            # Append to query
            if len(selectors) > 1:
                aliases = [s.split(".", 1)[0] for s in selectors]
                if len(set(aliases)) == 1:
                    alias = aliases[0]
                else:
                    alias = resource.alias
                #alias = resource.alias
            else:
                alias = selectors[0].split(".", 1)[0]
            if alias == "~":
                alias = resource.alias
            if alias not in query:
                query[alias] = [q]
            else:
                query[alias].append(q)

        return query

    # -------------------------------------------------------------------------
    @staticmethod
    def parse_url(url):
        """
            Parse a URL query into get_vars

            Args:
                query: the URL query string

            Returns:
                the get_vars (Storage)
        """

        if not url:
            return Storage()
        elif "?" in url:
            query = url.split("?", 1)[1]
        elif "=" in url:
            query = url
        else:
            return Storage()

        dget = urlparse.parse_qsl(query, keep_blank_values=1)

        get_vars = Storage()
        for (key, value) in dget:
            if key in get_vars:
                if type(get_vars[key]) is list:
                    get_vars[key].append(value)
                else:
                    get_vars[key] = [get_vars[key], value]
            else:
                get_vars[key] = value
        return get_vars

    # -------------------------------------------------------------------------
    @classmethod
    def parse_key(cls, key):
        """
            Parse a URL filter key

            Args:
                key: the filter key

            Returns:
                tuple (selector, operator, invert)
        """

        if key[-1] == "!":
            invert = True
        else:
            invert = False

        fs = key.rstrip("!")
        op = None

        # Find the operator
        m = cls.FILTEROP.search(fs)
        if m:
            op = m.group(0).strip("_")
            fs = fs[:m.span(0)[0]]
        else:
            fs = fs.rstrip("_")
        if not op:
            op = "eq"

        return fs, op, invert

    # -------------------------------------------------------------------------
    @classmethod
    def parse_expression(cls, key):
        """
            Parse a URL filter key, separating multiple field selectors
            if the key specifies alternatives

            Args:
                key: the filter key

            Returns:
                tuple ([field selectors], operator, invert)
        """

        fs, op, invert = cls.parse_key(key)

        if "|" in fs:
            selectors = [s for s in fs.split("|") if s]
        else:
            selectors = [fs]

        return selectors, op, invert

    # -------------------------------------------------------------------------
    @staticmethod
    def parse_value(value):
        """
            Parse a URL query value

            Args:
                value: the value

            Returns:
                the parsed value
        """

        uquote = lambda w: w.replace('\\"', '\\"\\') \
                            .strip('"') \
                            .replace('\\"\\', '"')
        NONE = ("NONE", "None")
        if type(value) is not list:
            value = [value]
        vlist = []
        for item in value:
            w = ""
            quote = False
            ignore_quote = False
            for c in s3_str(item):
                if c == '"' and not ignore_quote:
                    w += c
                    quote = not quote
                elif c == "," and not quote:
                    if w in NONE:
                        w = None
                    else:
                        w = s3_str(uquote(w))
                    vlist.append(w)
                    w = ""
                else:
                    w += c
                if c == "\\":
                    ignore_quote = True
                else:
                    ignore_quote = False
            if w in NONE:
                w = None
            else:
                w = s3_str(uquote(w))
            vlist.append(w)
        if len(vlist) == 1:
            return vlist[0]
        return vlist

    # -------------------------------------------------------------------------
    @classmethod
    def _subquery(cls, selectors, op, invert, value):
        """
            Construct a sub-query from URL selectors, operator and value

            Args:
                selectors: the selector(s)
                op: the operator
                invert: invert the query
                value: the value
        """

        v = cls.parse_value(value)

        # Auto-lowercase, escape, and replace wildcards
        like = lambda s: s3_str(s).lower() \
                                  .replace("%", "\\%") \
                                  .replace("_", "\\_") \
                                  .replace("?", "_") \
                                  .replace("*", "%")
        q = None

        # Don't repeat LIKE-escaping for multiple selectors
        escaped = False

        for fs in selectors:

            if op == S3ResourceQuery.LIKE:
                f = S3FieldSelector(fs).lower()
                if not escaped:
                    if isinstance(v, str):
                        v = like(v)
                    elif isinstance(v, list):
                        v = [like(s) for s in v if s is not None]
                    escaped = True
            else:
                f = S3FieldSelector(fs)

            rquery = None
            try:
                rquery = S3ResourceQuery(op, f, v)
            except SyntaxError:
                current.log.error("Invalid URL query operator: %s (sub-query ignored)" % op)
                q = None
                break

            # Invert operation
            if invert:
                rquery = ~rquery

            # Add to subquery
            if q is None:
                q = rquery
            elif invert:
                q &= rquery
            else:
                q |= rquery

        return q

# =============================================================================
class S3AIRegex:
    """
        Helper class to construct quasi-accent-insensitive text search
        queries based on SQL regular expressions (REGEXP).

        Important: This will return complete nonsense if the REGEXP
                   implementation of the DBMS is not multibyte-safe,
                   so it must be suppressed for those cases (see also
                   modules/s3config.py)!
    """

    # Groups with diacritic variants of the same character
    GROUPS = (
        "aăâåãáàẩắằầảẳẵẫấạặậǻ",
        "äæ",
        "cçćĉ",
        "dđð",
        "eêèềẻểẽễéếẹệë",
        "gǵĝ",
        "hĥ",
        "iìỉĩíịîï\u0131\u0130",
        "jĵ",
        "kḱ",
        "lĺ",
        "mḿ",
        "nñńǹ",
        "oôơòồờỏổởõỗỡóốớọộợ",
        "öøǿ",
        "pṕ",
        "rŕ",
        "sśŝ",
        "tẗ",
        "uưùừủửũữúứụựứüǘûǜ",
        "wẃŵẁ",
        "yỳỷỹýỵÿŷ",
        "zźẑ",
    )

    ESCAPE = ".*$^[](){}\\+?"

    # -------------------------------------------------------------------------
    @classmethod
    def like(cls, l, r):
        """
            Query constructor

            Args:
                l: the left operand
                r: the right operand (string)
        """

        string = cls.translate(r)
        if string:
            return l.lower().regexp("^%s$" % string)
        else:
            return l.like(r)

    # -------------------------------------------------------------------------
    @classmethod
    def translate(cls, string):
        """
            Helper method to translate the search string into a regular
            expression

            Args:
                string: the search string
        """

        if not string:
            return None

        match = False
        output = []
        append = output.append

        GROUPS = cls.GROUPS
        ESCAPE = cls.ESCAPE

        escaped = False
        for character in s3_str(string):

            if character != "\u0130": # "İ".lower() gives two characters!!
                character = character.lower()

            result = None

            # Translate any unescaped wildcard characters
            if not escaped:
                if character == "\\":
                    escaped = True
                    continue
                elif character == "%":
                    result = ".*"
                elif character == "_":
                    result = "."

            if result is None:
                if character in ESCAPE:
                    result = "\\%s" % character
                else:
                    result = character
                    for group in GROUPS:
                        if character in group:
                            match = True
                            result = "[%s%s]{1}" % (group, group.upper())
                            break

            # Don't swallow backslashes that do not escape wildcards
            if escaped and character not in ("%", "_"):
                result = "\\%s" % result

            escaped = False
            append(result)

        return "".join(output) if match else None

# =============================================================================
# Helper to combine multiple queries using AND
#
combine = lambda x, y: x & y if x is not None else y

# =============================================================================
class S3URLQueryParser:
    """ New-style URL Filter Parser """

    def __init__(self):
        """ Constructor """

        self.parser = None
        self.ParseResults = None
        self.ParseException = None

        self._parser()

    # -------------------------------------------------------------------------
    def _parser(self):
        """ Import PyParsing and define the syntax for filter expressions """

        # PyParsing available?
        try:
            import pyparsing as pp
        except ImportError:
            current.log.error("Advanced filter syntax requires pyparsing, $filter ignored")
            return False

        # Selector Syntax
        context = lambda s, l, t: t[0].replace("[", "(").replace("]", ")")
        selector = pp.Word(pp.alphas + "[]~", pp.alphanums + "_.$:[]")
        selector.setParseAction(context)

        keyword = lambda x, y: x | pp.Keyword(y) if x else pp.Keyword(y)

        # Expression Syntax
        function = reduce(keyword, S3FieldSelector.OPERATORS)
        expression = function + \
                     pp.Literal("(").suppress() + \
                     selector + \
                     pp.Literal(")").suppress()

        # Comparison Syntax
        comparison = reduce(keyword, S3ResourceQuery.COMPARISON)

        # Value Syntax
        number = pp.Regex(r"[+-]?\d+(:?\.\d*)?(:?[eE][+-]?\d+)?")
        value = number | \
                pp.Keyword("NONE") | \
                pp.quotedString | \
                pp.Word(pp.alphanums + pp.printables)
        qe = pp.Group(pp.Group(expression | selector) +
                      comparison +
                      pp.originalTextFor(pp.delimitedList(value, combine=True)))

        parser = pp.infixNotation(qe, [("not", 1, pp.opAssoc.RIGHT, ),
                                       ("and", 2, pp.opAssoc.LEFT, ),
                                       ("or", 2, pp.opAssoc.LEFT, ),
                                       ])

        self.parser = parser
        self.ParseResults = pp.ParseResults
        self.ParseException = pp.ParseException

        return True

    # -------------------------------------------------------------------------
    def parse(self, expression):
        """
            Parse a string expression and convert it into a dict
            of filters (S3ResourceQueries).

            Args:
                expression: the filter expression as string

            Returns:
                a dict of {component_alias: filter_query}
        """

        query = {}

        parser = self.parser
        if not expression or parser is None:
            return query

        try:
            parsed = parser.parseString(expression)
        except self.ParseException:
            current.log.error("Invalid URL Filter Expression: '%s'" %
                              expression)
        else:
            if parsed:
                query = self.convert_expression(parsed[0])
        return query

    # -------------------------------------------------------------------------
    def convert_expression(self, expression):
        """
            Convert a parsed filter expression into a dict of
            filters (S3ResourceQueries)

            Args:
                expression: the parsed filter expression (ParseResults)

            Returns:
                dict of {component_alias: filter_query}
        """

        ParseResults = self.ParseResults
        convert = self.convert_expression

        if isinstance(expression, ParseResults):
            first, op, second = ([None, None, None] + list(expression))[-3:]

            if isinstance(first, ParseResults):
                first = convert(first)
            if isinstance(second, ParseResults):
                second = convert(second)

            if op == "not":
                return self._not(second)
            elif op == "and":
                return self._and(first, second)
            elif op == "or":
                return self._or(first, second)
            elif op in S3ResourceQuery.COMPARISON:
                return self._query(op, first, second)
            elif op in S3FieldSelector.OPERATORS and second:
                selector = S3FieldSelector(second)
                selector.op = op
                return selector
            elif op is None and second:
                return S3FieldSelector(second)
        else:
            return None

    # -------------------------------------------------------------------------
    def _and(self, first, second):
        """
            Conjunction of two query {component_alias: filter_query} (AND)

            Args:
                first: the first dict
                second: the second dict

            Returns:
                the combined dict
        """

        if not first:
            return second
        if not second:
            return first

        result = dict(first)

        for alias, subquery in second.items():
            if alias not in result:
                result[alias] = subquery
            else:
                result[alias] &= subquery
        return result

    # -------------------------------------------------------------------------
    def _or(self, first, second):
        """
            Disjunction of two query dicts {component_alias: filter_query} (OR)

            Args:
                first: the first query dict
                second: the second query dict

            Returns:
                the combined dict
        """

        if not first:
            return second
        if not second:
            return first

        if len(first) > 1:
            first = {None: reduce(combine, first.values())}
        if len(second) > 1:
            second = {None: reduce(combine, second.values())}

        falias = list(first.keys())[0]
        salias = list(second.keys())[0]

        alias = falias if falias == salias else None
        return {alias: first[falias] | second[salias]}

    # -------------------------------------------------------------------------
    def _not(self, query):
        """
            Negation of a query dict

            Args:
                query: the query dict {component_alias: filter_query}
        """

        if query is None:
            return None

        if len(query) == 1:

            alias, sub = list(query.items())[0]

            if sub.op == S3ResourceQuery.OR and alias is None:

                lalias = self._alias(sub.left.left)
                ralias = self._alias(sub.right.left)

                if lalias == ralias:
                    return {alias: ~sub}
                else:
                    # not(A or B) => not(A) and not(B)
                    return {lalias: ~sub.left, ralias: ~sub.right}
            else:
                if sub.op == S3ResourceQuery.NOT:
                    return {alias: sub.left}
                else:
                    return {alias: ~sub}
        else:
            return {None: ~reduce(combine, query.values())}

    # -------------------------------------------------------------------------
    def _query(self, op, first, second):
        """
            Create an S3ResourceQuery

            Args:
                op: the operator
                first: the first operand (=S3FieldSelector)
                second: the second operand (=value)
        """

        if not isinstance(first, S3FieldSelector):
            return {}

        selector = first

        alias = self._alias(selector)

        value = S3URLQuery.parse_value(second.strip())
        if op == S3ResourceQuery.LIKE:
            selector.lower()
            if isinstance(value, str):
                value = value.replace("*", "%").lower()
            elif isinstance(value, list):
                value = [x.replace("*", "%").lower() for x in value if x is not None]

        return {alias: S3ResourceQuery(op, selector, value)}

    # -------------------------------------------------------------------------
    @staticmethod
    def _alias(selector):
        """
            Get the component alias from an S3FieldSelector (DRY Helper)

            Args:
                selector: the S3FieldSelector

            Returns:
                the alias as string or None for the master resource
        """

        alias = None
        if selector and isinstance(selector, S3FieldSelector):
            prefix = selector.name.split("$", 1)[0]
            if "." in prefix:
                alias = prefix.split(".", 1)[0]
            if alias in ("~", ""):
                alias = None
        return alias

# =============================================================================
class URLQueryJSON:
    """
        Helper class to render a human-readable representation of a
        filter query, as representation method of JSON-serialized
        queries in saved filters.
    """

    def __init__(self, resource, query):
        """
            Constructor

            Args:
                query: the URL query (list of key-value pairs or a
                          string with such a list in JSON)
        """

        if type(query) is not list:
            try:
                self.query = json.loads(query)
            except ValueError:
                self.query = []
        else:
            self.query = query

        get_vars = {}
        for k, v in self.query:
            if v is not None:
                key = resource.prefix_selector(k)
                if key in get_vars:
                    value = get_vars[key]
                    if type(value) is list:
                        value.append(v)
                    else:
                        get_vars[key] = [value, v]
                else:
                    get_vars[key] = v

        self.resource = resource
        self.get_vars = get_vars

    # -------------------------------------------------------------------------
    def represent(self):
        """ Render the query representation for the given resource """

        default = ""

        get_vars = self.get_vars
        resource = self.resource
        if not get_vars:
            return default
        else:
            queries = S3URLQuery.parse(resource, get_vars)

        # Get alternative field labels
        labels = {}
        get_config = resource.get_config
        prefix = resource.prefix_selector
        for config in ("list_fields", "notify_fields"):
            fields = get_config(config, set())
            for f in fields:
                if type(f) is tuple:
                    labels[prefix(f[1])] = f[0]

        # Iterate over the sub-queries
        render = self._render
        substrings = []
        append = substrings.append
        for alias, subqueries in queries.items():

            for subquery in subqueries:
                s = render(resource, alias, subquery, labels=labels)
                if s:
                    append(s)

        if substrings:
            result = substrings[0]
            T = current.T
            for s in substrings[1:]:
                result = T("%s AND %s") % (result, s)
            return result
        else:
            return default

    # -------------------------------------------------------------------------
    @classmethod
    def _render(cls, resource, alias, query, invert=False, labels=None):
        """
            Recursively render a human-readable representation of a
            S3ResourceQuery.

            Args:
                resource: the CRUDResource
                query: the S3ResourceQuery
                invert: invert the query
        """

        T = current.T

        if not query:
            return None

        op = query.op

        l = query.left
        r = query.right
        render = lambda q, r=resource, a=alias, invert=False, labels=labels: \
                        cls._render(r, a, q, invert=invert, labels=labels)

        if op == query.AND:
            # Recurse AND
            l = render(l)
            r = render(r)
            if l is not None and r is not None:
                if invert:
                    result = T("NOT %s OR NOT %s") % (l, r)
                else:
                    result = T("%s AND %s") % (l, r)
            else:
                result = l if l is not None else r
        elif op == query.OR:
            # Recurse OR
            l = render(l)
            r = render(r)
            if l is not None and r is not None:
                if invert:
                    result = T("NOT %s AND NOT %s") % (l, r)
                else:
                    result = T("%s OR %s") % (l, r)
            else:
                result = l if l is not None else r
        elif op == query.NOT:
            # Recurse NOT
            result = render(l, invert=not invert)
        else:
            # Resolve the field selector against the resource
            try:
                rfield = l.resolve(resource)
            except (AttributeError, SyntaxError):
                return None

            # Convert the filter values into the field type
            try:
                values = cls._convert(rfield, r)
            except (TypeError, ValueError):
                values = r

            # Alias
            selector = l.name
            if labels and selector in labels:
                rfield.label = labels[selector]
            # @todo: for duplicate labels, show the table name
            #else:
                #tlabel = " ".join(s.capitalize() for s in rfield.tname.split("_")[1:])
                #rfield.label = "(%s) %s" % (tlabel, rfield.label)

            # Represent the values
            if values is None:
                values = T("None")
            else:
                list_type = rfield.ftype[:5] == "list:"
                renderer = rfield.represent
                if not callable(renderer):
                    renderer = s3_str
                if hasattr(renderer, "linkto"):
                    #linkto = renderer.linkto
                    renderer.linkto = None
                #else:
                #    #linkto = None

                is_list = type(values) is list

                try:
                    if is_list and hasattr(renderer, "bulk") and not list_type:
                        fvalues = renderer.bulk(values, list_type=False)
                        values = [fvalues[v] for v in values if v in fvalues]
                    elif list_type:
                        if is_list:
                            values = renderer(values)
                        else:
                            values = renderer([values])
                    else:
                        if is_list:
                            values = [renderer(v) for v in values]
                        else:
                            values = renderer(values)
                except:
                    values = s3_str(values)

            # Translate the query
            result = cls._translate_query(query, rfield, values, invert=invert)

        return result

    # -------------------------------------------------------------------------
    @classmethod
    def _convert(cls, rfield, value):
        """
            Convert a filter value according to the field type
            before representation

            Args:
                rfield: the S3ResourceField
                value: the value
        """

        if value is None:
            return value

        ftype = rfield.ftype
        if ftype[:5] == "list:":
            if ftype[5:8] in ("int", "ref"):
                ftype = int
            else:
                ftype = str
        elif ftype == "id" or ftype [:9] == "reference":
            ftype = int
        elif ftype == "integer":
            ftype = int
        elif ftype == "date":
            ftype = datetime.date
        elif ftype == "time":
            ftype = datetime.time
        elif ftype == "datetime":
            ftype = datetime.datetime
        elif ftype == "double":
            ftype = float
        elif ftype == "boolean":
            ftype = bool
        else:
            ftype = str

        convert = S3TypeConverter.convert
        if type(value) is list:
            output = []
            append = output.append
            for v in value:
                try:
                    append(convert(ftype, v))
                except (TypeError, ValueError):
                    continue
        else:
            try:
                output = convert(ftype, value)
            except (TypeError, ValueError):
                output = None
        return output

    # -------------------------------------------------------------------------
    @classmethod
    def _translate_query(cls, query, rfield, values, invert=False):
        """
            Translate the filter query into human-readable language

            Args:
                query: the S3ResourceQuery
                rfield: the S3ResourceField the query refers to
                values: the filter values
                invert: invert the operation
        """

        T = current.T

        # Value list templates
        vor = T("%s or %s")
        vand = T("%s and %s")

        # Operator templates
        otemplates = {
            query.LT: (query.GE, vand, "%(label)s < %(values)s"),
            query.LE: (query.GT, vand, "%(label)s <= %(values)s"),
            query.EQ: (query.NE, vor, T("%(label)s is %(values)s")),
            query.GE: (query.LT, vand, "%(label)s >= %(values)s"),
            query.GT: (query.LE, vand, "%(label)s > %(values)s"),
            query.NE: (query.EQ, vor, T("%(label)s != %(values)s")),
            query.LIKE: ("notlike", vor, T("%(label)s like %(values)s")),
            query.BELONGS: (query.NE, vor, T("%(label)s = %(values)s")),
            query.CONTAINS: ("notall", vand, T("%(label)s contains %(values)s")),
            query.ANYOF: ("notany", vor, T("%(label)s contains any of %(values)s")),
            "notall": (query.CONTAINS, vand, T("%(label)s does not contain %(values)s")),
            "notany": (query.ANYOF, vor, T("%(label)s does not contain %(values)s")),
            "notlike": (query.LIKE, vor, T("%(label)s not like %(values)s"))
        }

        # Quote values as necessary
        ftype = rfield.ftype
        if ftype in ("string", "text") or \
           ftype[:9] == "reference" or \
           ftype[:5] == "list:" and ftype[5:8] in ("str", "ref"):
            if type(values) is list:
                values = ['"%s"' % v for v in values]
            elif values is not None:
                values = '"%s"' % values
            else:
                values = current.messages["NONE"]

        # Render value list template
        def render_values(template=None, values=None):
            if not template or type(values) is not list:
                return str(values)
            elif not values:
                return "()"
            elif len(values) == 1:
                return values[0]
            else:
                return template % (", ".join(values[:-1]), values[-1])

        # Render the operator template
        op = query.op
        if op in otemplates:
            inversion, vtemplate, otemplate = otemplates[op]
            if invert:
                inversion, vtemplate, otemplate = otemplates[inversion]
            return otemplate % {"label": rfield.label,
                                "values":render_values(vtemplate, values),
                                }
        else:
            # Fallback to simple representation
            return query.represent(rfield.resource)

# END =========================================================================
