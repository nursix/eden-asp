"""
    Datatable Column Configurations Manager

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

__all__ = ("ColumnConfigManager",
           )

import json

from gluon import current

from ..tools import JSONERRORS, JSONSEPARATORS

from .base import CRUDMethod

# =============================================================================
class ColumnConfigManager(CRUDMethod):
    """ Back-end method to manage datatable column configurations """

    def apply_method(self, r, **attr):
        """
            Entry point for CRUDController

            Args:
                r: the CRUDRequest
                **attr: controller parameters

            Returns:
                JSON
        """

        output = None

        if r.representation == "json":

            http = r.http

            if http == "GET":
                if "load" in r.get_vars:
                    output = self.load(r, **attr)
                else:
                    output = self.configs(r, **attr)

            elif http == "DELETE" or \
                 http == "POST" and "delete" in r.get_vars:
                output = self.delete(r, **attr)

            elif http in ("PUT", "POST"):
                output = self.save(r, **attr)

            else:
                r.error(405, current.ERROR.BAD_METHOD)
        else:
            r.error(415, current.ERROR.BAD_FORMAT)

        current.response.headers["Content-Type"] = "application/json"
        return output

    # -------------------------------------------------------------------------
    def save(self, r, **attr):
        """
            Saves a column configuration; requires a JSON request body
            in the format {"name": "ConfigName", "columns": ["selector", ...]}

            Args:
                r: the CRUDRequest
                **attr: controller parameters

            Returns:
                JSON message, containing created=ID or updated=ID
            Raises:
                HTTP400 for invalid parameters

            Note:
                If a configuration with the same name exists for the
                request context, it will be updated instead of creating
                a new one
        """

        c, f, t, user_id = self.get_context(r)
        if not user_id:
            r.unauthorised()

        # Read+parse body JSON
        s = r.body
        s.seek(0)
        try:
            data = json.load(s)
        except JSONERRORS:
            data = None
        if not isinstance(data, dict):
            r.error(400, "Invalid request parameters")

        # Get configuration name
        name = data.get("name")
        if not name:
            r.error(400, "Missing name")
        name = str(name).strip()

        # Get the column configuration
        columns = data.get("columns")
        if not columns or not isinstance(columns, list):
            r.error(400, "Missing or invalid columns list")
        selectors = [str(sel) for sel in columns if sel]

        s3db = current.s3db

        # Look up existing record
        table = s3db.usr_columns
        query = (table.controller == c) & \
                (table.function == f) & \
                (table.tablename == t) & \
                (table.user_id == user_id) & \
                (table.name == name) & \
                (table.deleted == False)
        record = current.db(query).select(table.id, limitby=(0, 1)).first()

        data = {"controller": c,
                "function": f,
                "tablename": self.resource.tablename,
                "user_id": user_id,
                "name": name,
                "columns": {"columns": selectors},
                }
        if record:
            # Update existing record
            method = "update"
            record_id = data["id"] = record.id
            record.update_record(**data)
            msg = {"updated": record_id}
        else:
            # Create new record
            method = "create"
            record_id = data["id"] = table.insert(**data)
            msg = {"created": record_id}

        # Postprocess create|update
        s3db.update_super(table, data)
        if method == "create":
            current.auth.s3_set_record_owner(table, record_id)
        s3db.onaccept(table, data, method=method)

        # Audit?
        #current.audit(method, "usr", "columns", record=record_id, representation="json")

        return current.xml.json_message(**msg)

    # -------------------------------------------------------------------------
    def configs(self, r, **attr):
        """
            Returns a list of saved column configurations for the context

            Args:
                r: the CRUDRequest
                **attr: controller parameters

            Returns:
                JSON string {"configs": [{"id": recordID, "name": "configName"}, ...]}
        """

        c, f, t, user_id = self.get_context(r)
        if not user_id:
            r.unauthorised()

        table = current.s3db.usr_columns
        query = (table.controller == c) & \
                (table.function == f) & \
                (table.tablename == t) & \
                (table.user_id == user_id) & \
                (table.deleted == False)
        rows = current.db(query).select(table.id, table.name)

        # Audit?
        #current.audit("read", "usr", "columns", representation="json")

        configs = [{"id": row.id, "name": row.name} for row in rows if row.name.strip()]

        return json.dumps({"configs": configs}, separators=JSONSEPARATORS)

    # -------------------------------------------------------------------------
    def load(self, r, **attr):
        """
            Loads a column configuration; requires ?load=ID query

            Args:
                r: the CRUDRequest
                **attr: controller parameters

            Returns:
                JSON string {"name": "configName", "columns": ["selector", ...]}
            Raises:
                HTTP400 for invalid parameters
                HTTP404 if the record doesn't exist within the request context
        """

        c, f, t, user_id = self.get_context(r)
        if not user_id:
            r.unauthorised()

        record_id = r.get_vars.get("load")
        try:
            record_id = int(record_id)
        except (ValueError, TypeError):
            r.error(400, "Invalid request parameters")

        table = current.s3db.usr_columns
        query = (table.id == record_id) & \
                (table.controller == c) & \
                (table.function == f) & \
                (table.tablename == t) & \
                (table.user_id == user_id) & \
                (table.deleted == False)
        record = current.db(query).select(table.id,
                                          table.name,
                                          table.columns,
                                          limitby = (0, 1),
                                          ).first()
        if record:
            output = {"id": record.id,
                      "name": record.name,
                      "columns": record.columns.get("columns"),
                      }
        else:
            output = None
            r.error(404, current.ERROR.BAD_RECORD)

        # Audit?
        #current.audit("read", "usr", "columns", record=record.id, representation="json")

        return json.dumps(output, separators=JSONSEPARATORS)

    # -------------------------------------------------------------------------
    def delete(self, r, **attr):
        """
            Deletes a column configuration; requires ?delete=ID query

            Args:
                r: the CRUDRequest
                **attr: controller parameters

            Returns:
                JSON message, containing deleted=ID
            Raises:
                HTTP400 for invalid parameters
                HTTP404 if the record doesn't exist within the request context

            Note:
                Record will be (hard-)deleted, not archived
        """

        c, f, t, user_id = self.get_context(r)
        if not user_id:
            r.unauthorised()

        # Get the record ID
        record_id = r.get_vars.get("delete", 0)
        try:
            record_id = int(record_id)
        except (ValueError, TypeError):
            r.error(400, "Invalid request parameters")

        # Look up the record by ID + context
        table = current.s3db.usr_columns
        query = (table.id == record_id) & \
                (table.controller == c) & \
                (table.function == f) & \
                (table.tablename == t) & \
                (table.user_id == user_id) & \
                (table.deleted == False)
        record = current.db(query).select(table.id, limitby=(0, 1)).first()

        # Delete the record
        msg = {}
        if record:
            msg["deleted"] = record.id
            record.delete_record()
        else:
            r.error(404, current.ERROR.BAD_RECORD)

        # Audit?
        #current.audit("delete", "usr", "columns", record=record.id, representation="json")

        return current.xml.json_message(**msg)

    # -------------------------------------------------------------------------
    def get_context(self, r):
        """
            Returns the request context controller/function/tablename/user

            Args:
                r: the CRUDRequest

            Returns:
                tuple (controller, function, tablename, user_id)
        """

        resource = self.resource

        auth = current.auth
        if auth.s3_logged_in():
            user_id = auth.user.id
        else:
            user_id = None

        return (r.controller, r.function, resource.tablename, user_id)

# END =========================================================================
