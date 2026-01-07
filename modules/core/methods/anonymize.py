"""
    Record Anonymizing

    Copyright: 2018-2022 (c) Sahana Software Foundation

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

from collections import OrderedDict

from gluon import current, redirect, A, BUTTON, DIV, FORM, INPUT, LABEL, P, SCRIPT, TAG

from s3dal import original_tablename

from ..resource import FS
from ..tools import JSONERRORS, FormKey, s3_str

from .base import CRUDMethod

__all__ = ("Anonymize",
           "AnonymizeWidget",
           "anonymous_address",
           "obscure_dob",
           )

# =============================================================================
class Anonymize(CRUDMethod):
    """
        REST Method to Anonymize a Record
        - usually pr_person
    """

    # -------------------------------------------------------------------------
    def apply_method(self, r, **attr):
        """
            Entry point for REST API

            Args:
                r: the CRUDRequest instance
                attr: controller parameters

            Returns:
                output data (JSON)
        """

        output = {}

        rules = self.resource.get_config("anonymize")
        if not rules:
            r.error(405, "Anonymizing not configured for resource")

        if r.http == "POST":
            if r.ajax or r.representation == "json":
                if self.record_id:
                    output = self.anonymize(r, **attr)
                else:
                    output = self.anonymize_bulk(r, **attr)
            elif r.representation == "html":
                output = self.anonymize_bulk(r, **attr)
            else:
                r.error(415, current.ERROR.BAD_FORMAT)
        else:
            r.error(405, current.ERROR.BAD_METHOD)

        return output

    # -------------------------------------------------------------------------
    def anonymize(self, r, **attr):
        """
            Handle POST (anonymize-request), i.e. anonymize the target record

            Args:
                r: the CRUDRequest
                table: the target Table
                record_id: the target record ID

            Returns:
                JSON message
        """

        resource = self.resource
        record_id = self.record_id

        table = resource.table

        # Read+parse body JSON
        s = r.body
        s.seek(0)
        try:
            options = json.load(s)
        except JSONERRORS:
            options = None
        if not isinstance(options, dict):
            r.error(400, "Invalid request options")

        # Verify submitted form key against session (CSRF protection)
        form_name = "%s-%s-anonymize" % (table, record_id)
        form_key = FormKey(form_name)
        if not form_key.verify(options):
            r.error(400, "Invalid action key (form reopened in another tab?)")

        # Authorize the action
        if not self.permitted(table, record_id):
            r.unauthorised()

        # Get the available rules from settings
        rules, names = self.get_rules(table)

        # Get selected rules from options
        selected = options.get("apply")
        if not isinstance(selected, list):
            r.error(400, "Invalid request options")

        # Validate selected rules
        for name in selected:
            if name not in names:
                r.error(400, "Invalid rule: %s" % name)

        # Apply selected rules
        cleanup, cascade = self.merge(rules, selected)
        if cleanup or cascade:
            rules = {"fields": cleanup,
                     "cascade": cascade,
                     }

            # NB will raise (+roll back) if configuration is invalid
            self.cascade(table, (record_id,), rules)

            # Audit anonymize
            prefix, name = original_tablename(table).split("_", 1)
            current.audit("anonymize", prefix, name,
                          record = record_id,
                          representation = "html",
                          )

            output = current.xml.json_message(updated=record_id)
        else:
            output = current.xml.json_message(msg="No applicable rules found")

        # Set Content Type
        current.response.headers["Content-Type"] = "application/json"

        return output

    # -------------------------------------------------------------------------
    def anonymize_bulk(self, r, **attr):
        """
            Generates a rule selection and confirmation dialog for bulk-action

            Args:
                r: the CRUDRequest
                table: the target table

            Returns:
                a JSON object with the dialog HTML as string
        """

        resource = self.resource
        table = resource.table

        if any(key not in r.post_vars for key in ("selected", "mode")):
            r.error(400, "Missing selection parameters")

        # Get the rules
        rules, names = self.get_rules(table)
        if not rules:
            r.error(501, current.ERROR.NOT_IMPLEMENTED)

        # Form to choose rules for anonymization
        form_name = "%s-anonymize" % table
        form = AnonymizeWidget.form(form_name, rules, ajax=False, plural=True)
        form["_action"] = r.url(representation="")

        output = None
        if r.ajax or r.representation == "json":
            # Dialog request
            # => generate a JSON object with form and control script
            script = '''var submitButton=$('.anonymize-submit');$('input[name="anonymize_confirm"]').off('.anonymize').on('click.anonymize',function(){if ($(this).prop('checked')){submitButton.prop('disabled',false);}else{submitButton.prop('disabled',true);}});'''
            dialog = TAG[""](form, SCRIPT(script, _type='text/javascript'))
            current.response.headers["Content-Type"] = "application/json"
            output = json.dumps({"dialog": s3_str(dialog.xml())})

        elif form.accepts(r.vars, current.session, formname=form_name):
            # Dialog submission
            # => process the form, set up, authorize and perform the action

            T = current.T
            pkey = table._id.name
            post_vars = r.post_vars

            # Selected records
            selected_ids = post_vars.get("selected", [])
            if isinstance(selected_ids, str):
                selected_ids = {item for item in selected_ids.split(",") if item.strip()}
            query = FS(pkey).belongs(selected_ids)

            # Selection mode
            mode = post_vars.get("mode")
            if mode == "Exclusive":
                if selected_ids:
                    query = ~query
                else:
                    query = None
            elif mode != "Inclusive":
                r.error(400, T("Invalid select mode"))

            # Add selection filter to resource
            if query is not None:
                resource.add_filter(query)

            # Get all selected IDs from resource
            rows = resource.select([pkey], as_rows=True)
            record_ids = {row[pkey] for row in rows}

            # Verify permission for all selected record
            query = (table._id.belongs(record_ids)) & \
                    (table._id.belongs(self.permitted_set(table)))
            permitted = current.db(query).select(table._id)
            failed = len(record_ids) - len(permitted)
            if failed > 0:
                record_ids = {row[pkey] for row in permitted}

            # Selected rules from form.vars
            form_vars = form.vars
            selected_rules = [n for n in names if form_vars.get(n) == "on"]

            # Apply selected rules
            cleanup, cascade = self.merge(rules, selected_rules)
            if cleanup or cascade:
                rules = {"fields": cleanup,
                        "cascade": cascade,
                        }

                # NB will raise (+roll back) if configuration is invalid
                self.cascade(table, record_ids, rules)
                updated = len(record_ids)

                # Audit anonymize
                audit = current.audit
                prefix, name = original_tablename(table).split("_", 1)
                for record_id in record_ids:
                    audit("anonymize", prefix, name,
                        record = record_id,
                        representation = "html",
                        )
                msg = T("%(number)s records updated") % {"number": updated}
                if failed:
                    msg = "%s - %s" % (msg, T("%(number)s failed") % {"number": failed})
                current.session.confirmation = msg
            else:
                current.session.error = T("No applicable rules found")

            redirect(r.url(method="select", representation="", vars={}))

        else:
            r.error(400, current.ERROR.BAD_REQUEST)

        return output

    # -------------------------------------------------------------------------
    def get_target_id(self):
        """
            Determine the target table and record ID

            Returns:
                tuple (table, record_id)
        """

        resource = self.resource

        rules = resource.get_config("anonymize")
        if not rules:
            return None, None

        return resource.table, self.record_id

    # -------------------------------------------------------------------------
    @staticmethod
    def get_rules(table):
        """
            Returns all anonymizer rules for a table, and their names

            Args:
                table: the Table

            Returns:
                tuple of two lists (rules, names)
        """

        rules = current.s3db.get_config(table, "anonymize")

        if isinstance(rules, (tuple, list)):
            # List of rules
            keys = OrderedDict.fromkeys(rule.get("name") for rule in rules)
            keys.pop(None, None)
            names = list(keys)

        elif isinstance(rules, dict):
            # Single rule
            rules["name"] = "default"
            rules, names = [rules], ["default"]

        else:
            rules, names = [], []

        return rules, names

    # -------------------------------------------------------------------------
    @staticmethod
    def merge(rules, selected_rules):
        """
            Merges the selected rules

            Args:
                rules: the configured rules
                selected_rules: list of names of selected rules

            Returns:
                tuple ({cleanup}, [cascade])
        """

        cleanup, cascade = {}, []
        for rule in rules:
            name = rule.get("name")
            if not name or name not in selected_rules:
                continue
            field_rules = rule.get("fields")
            if field_rules:
                cleanup.update(field_rules)
            cascade_rules = rule.get("cascade")
            if cascade_rules:
                cascade.extend(cascade_rules)

        return cleanup, cascade

    # -------------------------------------------------------------------------
    @staticmethod
    def permitted(table, record_id):
        """
            Check permissions to anonymize

            Args:
                table: the target Table
                record_id: the target record ID (or None for any record in the table)

            Returns:
                True|False
        """

        has_permission = current.auth.s3_has_permission

        return has_permission("update", table, record_id=record_id) and \
               has_permission("delete", table, record_id=record_id)

    # -------------------------------------------------------------------------
    @staticmethod
    def permitted_set(table):
        """
            Returns a sub-query for the records the user is permitted
            to anonymize

            Args:
                table: the Table

            Returns:
                subquery (a SQL string)
        """

        accessible = current.auth.s3_accessible_query

        return current.db(accessible("update", table) & \
                          accessible("delete", table))._select(table._id)

    # -------------------------------------------------------------------------
    @classmethod
    def cascade(cls, table, record_ids, rules):
        """
            Apply cascade of rules to anonymize records

            Args:
                table: the Table
                record_ids: a set of record IDs
                rules: the rules for this Table

            Raises:
                Exception: if the cascade failed due to DB constraints
                           or invalid rules; callers should roll back
                           the transaction if an exception is raised
        """

        from ..resource import FS, S3Joins

        s3db = current.s3db

        pkey = table._id.name

        cascade = rules.get("cascade")
        if cascade:

            fieldnames = set(rule.get("match", pkey) for _, rule in cascade)
            if pkey not in fieldnames:
                fieldnames.add(pkey)
            fields = [table[fn] for fn in fieldnames]

            db = current.db
            rows = db(table._id.belongs(record_ids)).select(*fields)

            for tablename, rule in cascade:

                lookup = rule.get("lookup")
                if lookup:
                    # Explicit look-up function, call with master table+rows,
                    # as well as the name of the related table; should return
                    # a set/tuple/list of record ids in the related table
                    ids = lookup(table, rows, tablename)
                else:
                    key = rule.get("key")
                    if not key:
                        continue

                    field = rule.get("match", pkey)
                    match = set(row[field] for row in rows)

                    # Resolve key and construct query
                    resource = s3db.resource(tablename, components=[])
                    rq = FS(key).belongs(match)
                    query = rq.query(resource)

                    # Construct necessary joins
                    joins = S3Joins(tablename)
                    joins.extend(rq._joins(resource)[0])
                    joins = joins.as_list()

                    # Extract the target table IDs
                    target_rows = db(query).select(resource._id,
                                                   join = joins,
                                                   )
                    ids = set(row[resource._id.name] for row in target_rows)

                # Recurse into related table
                if ids:
                    cls.cascade(resource.table, ids, rule)

        # Apply field rules
        field_rules = rules.get("fields")
        if field_rules:
            cls.apply_field_rules(table, record_ids, field_rules)

        # Apply deletion rules
        if rules.get("delete"):
            resource = s3db.resource(table, id=list(record_ids))
            resource.delete(cascade=True)

    # -------------------------------------------------------------------------
    @staticmethod
    def apply_field_rules(table, record_ids, rules):
        """
            Apply field rules on a set of records in a table

            Args:
                table: the Table
                record_ids: the record IDs
                rules: the rules

            Raises:
                Exception: if the field rules could not be applied
                           due to DB constraints or invalid rules;
                           callers should roll back the transaction
                           if an exception is raised
        """

        fields = [table[fn] for fn in rules if fn in table.fields]
        if table._id.name not in rules:
            fields.insert(0, table._id)

        # Select the records
        query = table._id.belongs(record_ids)
        rows = current.db(query).select(*fields)

        pkey = table._id.name

        s3db = current.s3db
        update_super = s3db.update_super
        onaccept = s3db.onaccept

        for row in rows:
            data = {}
            for fieldname, rule in rules.items():

                if fieldname in table.fields:
                    field = table[fieldname]
                else:
                    continue

                if rule == "remove":
                    # Set to None
                    if field.notnull:
                        raise ValueError("Cannot remove %s - must not be NULL" % field)
                    else:
                        data[fieldname] = None

                elif rule == "reset":
                    # Reset to the field's default value
                    default = field.default
                    if default is None and field.notnull:
                        raise ValueError("Cannot reset %s - default value None violates notnull-constraint")
                    data[fieldname] = default

                elif callable(rule):
                    # Callable rule to procude a new value
                    new_value = rule(row[pkey], field, row[field])
                    if fieldname != table._id.name:
                        data[fieldname] = new_value

                elif type(rule) is tuple:
                    method, value = rule
                    if method == "set":
                        # Set a fixed value
                        data[fieldname] = value

            if data:
                success = row.update_record(**data)
                if not success:
                    raise ValueError("Could not clean %s record" % table)

                update_super(table, row)

                data[pkey] = row[pkey]
                onaccept(table, data, method="update")

# =============================================================================
class AnonymizeWidget:
    """ UI Elements for Anonymize """

    # -------------------------------------------------------------------------
    @classmethod
    def widget(cls,
               r,
               label = "Anonymize",
               ajax_url = None,
               _class = "action-lnk",
               ):
        """
            Render an action item (link or button) to anonymize the
            target record of an CRUDRequest, which can be embedded in
            the record view

            Args:
                r: the CRUDRequest
                label: The label for the action item
                ajax_url: The URL for the AJAX request
                _class: HTML class for the action item

            Returns:
                the action item (a HTML helper instance), or an empty
                string if no anonymize-rules are configured for the
                target table, no target record was specified or the
                user is not permitted to anonymize it
        """

        T = current.T

        default = ""

        # Determine target table
        if r.component:
            resource = r.component
            if resource.link and not r.actuate_link():
                resource = resource.link
        else:
            resource = r.resource
        table = resource.table

        # Determine target record
        record_id = Anonymize._record_id(r)
        if not record_id:
            return default

        # Check if target is configured for anonymize
        rules = resource.get_config("anonymize")
        if not rules:
            return default
        if not isinstance(rules, (tuple, list)):
            # Single rule
            rules["name"] = "default"
            rules = [rules]

        # Check permissions to anonymize
        if not Anonymize.permitted(table, record_id):
            return default

        # Determine widget ID (to attach script)
        widget_id = "%s-anonymize" % table

        # Inject script
        if ajax_url is None:
            ajax_url = r.url(method = "anonymize",
                             representation = "json",
                             )
        script_options = {"ajaxURL": ajax_url,
                          }
        next_url = resource.get_config("anonymize_next")
        if next_url:
            script_options["nextURL"] = next_url
        cls.inject_script(widget_id, script_options)

        # Action button
        translated_label = T(label)
        action_button = A(translated_label, _class="anonymize-btn")
        if _class:
            action_button.add_class(_class)

        # Form to select rules and confirm the action
        form_name = "%s-%s-anonymize" % (table, record_id)
        form = cls.form(form_name, rules)

        # Dialog to show the form
        dialog = DIV(form,
                     DIV(P(T("Action successful - please wait...")),
                         _class = "hide anonymize-success",
                         ),
                     _class = "anonymize-dialog hide",
                     _title = translated_label,
                     )

        # Return the widget
        return DIV(action_button, dialog, _class="s3-anonymize", _id=widget_id)

    # -------------------------------------------------------------------------
    @classmethod
    def form(cls, form_name, rules, ajax=True, plural=False):
        """
            Produces the form to select rules and confirm the action

            Args:
                form_name: the form name (for CSRF protection)
                rules: the rules the user can choose
                ajax: whether the form is processed client-side (True)
                      or server-side (False)
                plural: use plural for info text and confirmation challenge
        """

        T = current.T

        # Dialog and Form
        if plural:
            INFO = T("The following information will be deleted from the selected records")
        else:
            INFO = T("The following information will be deleted from the record")
        CONFIRM = T("Are you sure you want to delete the selected details?")

        form = FORM(P("%s:" % INFO),
                    cls.selector(rules),
                    P(CONFIRM),
                    DIV(INPUT(value = "anonymize_confirm",
                              _name = "anonymize_confirm",
                              _type = "checkbox",
                              ),
                    LABEL(T("Yes, delete the selected details")),
                          _class = "anonymize-confirm",
                          ),
                    cls.buttons(ajax=ajax),
                    _class = "anonymize-form",
                    hidden = {"_formkey": FormKey(form_name).generate(),
                              "_formname": form_name,
                              },
                    )

        return form

    # -------------------------------------------------------------------------
    @staticmethod
    def selector(rules):
        """
            Generate the rule selector for anonymize-form

            Args:
                rules: the list of configured rules

            Returns:
                the selector (DIV)
        """

        T = current.T

        selector = DIV(_class = "anonymize-select",
                       )

        for rule in rules:

            name = rule.get("name")
            if not name:
                continue

            title = T(rule.get("title", name))

            selector.append(DIV(INPUT(value = "on",
                                      _name = s3_str(name),
                                      _type = "checkbox",
                                      _class = "anonymize-rule",
                                      ),
                                LABEL(title),
                                _class = "anonymize-option",
                                ))

        return selector

    # -------------------------------------------------------------------------
    @staticmethod
    def buttons(ajax=True):
        """
            Generate the submit/cancel buttons for the anonymize-form

            Args:
                ajax: whether the form is processed client-side (True)
                      or server-side (False)
            Returns:
                the buttons row (DIV)
        """

        T = current.T

        return DIV(BUTTON(T("Submit"),
                          _class = "small alert button anonymize-submit",
                          _disabled = "disabled",
                          _type = "button" if ajax else "submit",
                          ),
                   A(T("Cancel"),
                     _class = "cancel-form-btn action-lnk anonymize-cancel",
                     _href = "javascript:void(0)",
                     ),
                   _class = "anonymize-buttons",
                   )

    # -------------------------------------------------------------------------
    @staticmethod
    def inject_script(widget_id, options):
        """
            Inject the necessary JavaScript for the UI dialog

            Args:
                widget_id: the widget ID
                options: JSON-serializable dict of widget options
        """

        request = current.request
        s3 = current.response.s3

        # Static script
        if s3.debug:
            script = "/%s/static/scripts/S3/s3.ui.anonymize.js" % \
                     request.application
        else:
            script = "/%s/static/scripts/S3/s3.ui.anonymize.min.js" % \
                     request.application
        scripts = s3.scripts
        if script not in scripts:
            scripts.append(script)

        # Widget options
        opts = {}
        if options:
            opts.update(options)

        # Widget instantiation
        script = '''$('#%(widget_id)s').anonymize(%(options)s)''' % \
                 {"widget_id": widget_id,
                  "options": json.dumps(opts),
                  }
        jquery_ready = s3.jquery_ready
        if script not in jquery_ready:
            jquery_ready.append(script)

# =============================================================================
def anonymous_address(record_id, field, value):
    """
        Helper to anonymize a pr_address location; removes street and
        postcode details, but retains Lx ancestry for statistics

        Args:
            record_id: the pr_address record ID
            field: the location_id Field
            value: the location_id

        Returns:
            the location_id

        Example:
            Use like this in anonymise rules:
            ("pr_address", {"key": "pe_id",
                            "match": "pe_id",
                            "fields": {"location_id": anonymize_address,
                                       "comments": "remove",
                                       },
                            }),
    """

    db = current.db
    s3db = current.s3db

    # Get the location
    if value:
        ltable = s3db.gis_location
        row = db(ltable.id == value).select(ltable.id,
                                            ltable.level,
                                            limitby = (0, 1),
                                            ).first()
        if not row.level:
            # Specific location => remove address details
            data = {"addr_street": None,
                    "addr_postcode": None,
                    "gis_feature_type": 0,
                    "lat": None,
                    "lon": None,
                    "wkt": None,
                    }
            # Doesn't work - PyDAL doesn't detect the None value:
            #if "the_geom" in ltable.fields:
            #    data["the_geom"] = None
            row.update_record(**data)
            if "the_geom" in ltable.fields:
                db.executesql("UPDATE gis_location SET the_geom=NULL WHERE id=%s" % row.id)

    return value

# =============================================================================
def obscure_dob(record_id, field, value):
    """
        Helper to obscure a date of birth; maps to the first day of
        the quarter, thus retaining the approximate age for statistics

        Args:
            record_id: the record ID
            field: the Field
            value: the field value

        Returns:
            the new field value
    """

    if value:
        month = int((value.month - 1) / 3) * 3 + 1
        value = value.replace(month=month, day=1)

    return value

# END =========================================================================
