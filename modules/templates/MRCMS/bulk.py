"""
    Bulk Methods for MRCMS

    License: MIT
"""

import datetime
import json

from gluon import current, redirect, IS_EMPTY_OR, \
                  A, BUTTON, DIV, FORM, INPUT, LABEL, P, SCRIPT, TAG
from gluon.sqlhtml import OptionsWidget
from gluon.storage import Storage

from s3dal import Field

from core import CRUDMethod, FS, FormKey, s3_str, \
                 IS_ONE_OF, IS_UTC_DATETIME, S3CalendarWidget, S3DateTime

# =============================================================================
class CheckoutResidents(CRUDMethod):
    """ Bulk checkout method """

    # -------------------------------------------------------------------------
    def apply_method(self, r, **attr):
        """
            Entry point for CRUD controller

            Args:
                r: the CRUDRequest instance
                attr: controller parameters

            Returns:
                output data (JSON)
        """

        output = {}

        if r.http == "POST":
            if r.ajax or r.representation in ("json", "html"):
                output = self.checkout(r, **attr)
            else:
                r.error(415, current.ERROR.BAD_FORMAT)
        else:
            r.error(405, current.ERROR.BAD_METHOD)

        return output

    # -------------------------------------------------------------------------
    def checkout(self, r, **attr):
        """
            Provide a dialog to confirm the check-out, and upon submission,
            check-out the residents and close their cases (if requested).

            Args:
                r: the CRUDRequest
                table: the target table

            Returns:
                a JSON object with the dialog HTML as string

            Note:
                redirects to /select upon completion
        """

        resource = self.resource
        table = resource.table

        get_vars = r.get_vars

        # Select-URL for redirections (retain closed/archived flags)
        select_vars = {"$search": "session"}
        select_vars.update({k:get_vars[k] for k in get_vars.keys() & {"closed", "archived"}})
        select_url = r.url(method="select", representation="", vars=select_vars)

        if any(key not in r.post_vars for key in ("selected", "mode")):
            r.error(400, "Missing selection parameters", next=select_url)

        # Form to choose closure status
        form_name = "%s-close" % table
        form = self.form(form_name)
        form["_action"] = r.url(representation="", vars=select_vars)

        output = None
        if r.ajax or r.representation == "json":
            # Dialog request
            # => generate a JSON object with form and control script
            script = '''
(function() {
  const c = $('input[name="checkout_confirm"]'),
        f = $('input[name="close_confirm"]'),
        s = $('select[name="status_id"]'),
        b = $('.bulk-action-submit'),
        toggle = function() {
            var cc = f.prop('checked');
                sm = cc && !s.val();
            b.prop('disabled', !c.prop('checked') || sm);
            if (sm) { s.addClass('invalidinput'); } else { s.removeClass('invalidinput'); }
            if (!cc) { s.val(''); }
        };
    c.off('.close').on('click.close', toggle);
    f.off('.close').on('click.close', toggle);
    s.off('.close').on('change.close', toggle);
    }
)();'''
            dialog = TAG[""](form, SCRIPT(script, _type='text/javascript'))

            current.response.headers["Content-Type"] = "application/json"
            output = json.dumps({"dialog": s3_str(dialog.xml())})

        elif form.accepts(r.vars, current.session, formname=form_name):
            # Dialog submission
            # => process the form, set up, authorize and perform the action

            T = current.T
            pkey = table._id.name
            post_vars = r.post_vars

            try:
                record_ids = self.selected_set(resource, post_vars)
            except SyntaxError:
                r.error(400, "Invalid select mode", next=select_url)
            total_selected = len(record_ids)

            # Verify permission for all selected record
            query = (table._id.belongs(record_ids)) & \
                    (table._id.belongs(self.permitted_set(table, record_ids)))
            permitted = current.db(query).select(table._id)
            denied = len(record_ids) - len(permitted)
            if denied > 0:
                record_ids = {row[pkey] for row in permitted}

            # Check-out the clients
            checked_out, checkout_failed = self.checkout_residents(record_ids)
            success = checked_out

            # Build confirmation/error message
            msg = T("%(number)s residents checked-out") % {"number": checked_out}
            failures = []

            failed = checkout_failed + denied
            already_checked_out = total_selected - checked_out - failed
            if already_checked_out:
                failures.append(T("%(number)s already done") % {"number": already_checked_out})
            if failed:
                failures.append(T("%(number)s failed") % {"number": failed})
            if failures:
                failures = "(%s)" % (", ".join(str(f) for f in failures))
                msg = "%s %s" % (msg, failures)

            form_vars = form.vars
            if form_vars.get("close_confirm") == "on":

                # Get closure status from form and validate it
                status_id = form_vars.get("status_id")
                if not self.valid_status(status_id):
                    r.error(400, "Invalid closure status", next=select_url)

                # Close the cases
                closed, closure_failed = self.close_cases(record_ids, status_id)
                success += closed

                # Append to confirmation/error message
                msg_ = T("%(number)s cases closed") % {"number": closed}
                failures = []
                failed = closure_failed + denied
                already_closed = total_selected - closed - failed
                if already_closed:
                    failures.append(T("%(number)s already done") % {"number": already_closed})
                if failed:
                    failures.append(T("%(number)s failed") % {"number": failed})
                if failures:
                    failures = "(%s)" % (", ".join(str(f) for f in failures))
                    msg_ = "%s %s" % (msg_, failures)
                msg = "%s, %s" % (msg, msg_)

            if success:
                current.session.confirmation = msg
            else:
                current.session.warning = msg
            redirect(select_url)
        else:
            r.error(400, current.ERROR.BAD_REQUEST, next=select_url)

        return output

    # -------------------------------------------------------------------------
    @classmethod
    def form(cls, form_name):
        """
            Produces the form to select closure status and confirm the action

            Args:
                form_name: the form name (for CSRF protection)

            Returns:
                the FORM
        """

        T = current.T
        db = current.db
        s3db = current.s3db

        # Dialog and Form
        INFO = T("The selected residents will be checked-out from their shelter.")
        CONFIRM = T("Are you sure you want to check-out the selected residents?")

        # Closure statuses
        stable = s3db.dvr_case_status
        dbset = db((stable.is_closed == True) & (stable.deleted == False))

        # Selector for closure status
        ctable = s3db.dvr_case
        field = ctable.status_id
        field.requires = IS_EMPTY_OR(IS_ONE_OF(dbset, "dvr_case_status.id",
                                               field.represent,
                                               orderby = stable.workflow_position,
                                               sort = False,
                                               ))
        status_selector = OptionsWidget.widget(field, None)

        # Confirmation dialog
        form = FORM(P(INFO, _class="bulk-action-info"),
                    LABEL(INPUT(value = "close_confirm",
                                _name = "close_confirm",
                                _type = "checkbox",
                                ),
                          T("Close cases"),
                          _class="label-inline",
                          ),
                    LABEL(T("Closure Status"),
                          status_selector,
                          _class="label-above",
                          ),
                    P(CONFIRM, _class="bulk-action-question"),
                    LABEL(INPUT(value = "checkout_confirm",
                                _name = "checkout_confirm",
                                _type = "checkbox",
                                ),
                          T("Yes, check-out the selected residents"),
                          _class = "checkout-confirm label-inline",
                          ),
                    DIV(BUTTON(T("Submit"),
                               _class = "small alert button bulk-action-submit",
                               _disabled = "disabled",
                               _type = "submit",
                               ),
                        A(T("Cancel"),
                          _class = "cancel-form-btn action-lnk bulk-action-cancel",
                          _href = "javascript:void(0)",
                          ),
                        _class = "bulk-action-buttons",
                        ),
                    hidden = {"_formkey": FormKey(form_name).generate(),
                              "_formname": form_name,
                              },
                    _class = "bulk-action-form",
                    )

        return form

    # -------------------------------------------------------------------------
    @staticmethod
    def selected_set(resource, post_vars):
        """
            Determine the selected persons from select-parameters

            Args:
                resource: the pre-filtered CRUDResource (pr_person)
                post_vars: the POST vars containing the select-parameters

            Returns:
                set of pr_person.id
        """

        pkey = resource.table._id.name

        # Selected records
        selected_ids = post_vars.get("selected", [])
        if isinstance(selected_ids, str):
            selected_ids = {item for item in selected_ids.split(",") if item.strip()}
        query = FS(pkey).belongs(selected_ids)

        # Selection mode
        mode = post_vars.get("mode")
        if mode == "Exclusive":
            query = ~query if selected_ids else None
        elif mode != "Inclusive":
            raise SyntaxError

        # Get all matching record IDs
        if query is not None:
            resource.add_filter(query)
        rows = resource.select([pkey], as_rows=True)

        return {row[pkey] for row in rows}

    # -------------------------------------------------------------------------
    @staticmethod
    def permitted_set(table, selected_set):
        """
            Produces a sub-select of clients the user is permitted to
            check-out.

            Args:
                table: the target table (pr_person)
                selected_set: set of person IDs of the selected clients

            Returns:
                SQL
        """

        db = current.db
        s3db = current.s3db

        rtable = s3db.cr_shelter_registration
        left = rtable.on((rtable.person_id == table.id) & \
                         (rtable.deleted == False))

        writable = current.auth.s3_accessible_query("update", rtable)
        query = table.id.belongs(selected_set) & \
                ((rtable.id == None) | (rtable.registration_status == 3) | writable)

        return db(query)._select(table.id, left=left)

    # -------------------------------------------------------------------------
    @staticmethod
    def valid_status(status_id):
        """
            Verify if status_id references a valid closure status

            Args:
                status_id: the case status record ID

            Returns:
                boolean
        """

        table = current.s3db.dvr_case_status
        query = (table.id == status_id) & \
                (table.is_closed == True) & \
                (table.deleted == False)
        status = current.db(query).select(table.id, limitby=(0, 1)).first()

        return bool(status)

    # -------------------------------------------------------------------------
    @staticmethod
    def checkout_residents(person_ids):
        """
            Checks out the selected clients from their shelters

            Args:
                person_ids: person IDs of the selected clients

            Returns:
                a tuple (number successful, number failed)
        """

        db = current.db
        s3db = current.s3db

        # Count relevant shelter registrations
        table = s3db.cr_shelter_registration
        query = (table.person_id.belongs(person_ids)) & \
                (table.registration_status != 3) & \
                (table.deleted == False)
        cnt = table.id.count()
        row = db(query).select(cnt).first()
        total = row[cnt]

        if total > 0:
            # Get the permitted shelter registrations
            query = current.auth.s3_accessible_query("update", table) & query
            rows = db(query).select(table.id,
                                    table.person_id,
                                    table.registration_status,
                                    )

            # Perform the checkout
            now = current.request.utcnow
            onaccept = lambda record: s3db.onaccept(table, record, method="update")
            for registration in rows:
                registration.update_record(registration_status = 3,
                                           check_out_date = now,
                                           )
                onaccept(registration)

            updated = len(rows)
        else:
            updated = 0

        return updated, total - updated

    # -------------------------------------------------------------------------
    @staticmethod
    def close_cases(person_ids, status_id):
        """
            Closes the relevant cases with the selected closure status

            Args:
                person_ids: the person IDs of the cases to close
                status_id: the ID of the closure status

            Returns:
                a tuple (number successful, number failed)
        """

        db = current.db
        s3db = current.s3db

        # Count relevant cases
        table = s3db.dvr_case
        query = (table.person_id.belongs(person_ids)) & \
                (table.status_id != status_id) & \
                (table.deleted == False)
        cnt = table.id.count()
        row = db(query).select(cnt).first()
        total = row[cnt]

        if total > 0:
            # Exclude cases where the client is still checked-in to a shelter
            rtable = s3db.cr_shelter_registration
            q = (rtable.person_id.belongs(person_ids)) & \
                (rtable.registration_status == 2) & \
                (rtable.deleted == False)
            checked_in = db(q)._select(rtable.person_id)

            # Get the permitted cases
            query = current.auth.s3_accessible_query("update", table) & \
                    (~(table.person_id.belongs(checked_in))) & \
                    query
            rows = db(query).select(table.id,
                                    table.person_id,
                                    table.status_id,
                                    )

            # Perform the closure
            now = current.request.utcnow
            onaccept = lambda record: s3db.onaccept(table, record, method="update")
            for case in rows:
                case.update_record(status_id=status_id, closed_on=now)
                onaccept(case)

            updated = len(rows)
        else:
            updated = 0

        return updated, total - updated

# =============================================================================
class CreateAppointment(CRUDMethod):
    """ Bulk method to register appointments for multiple clients at once """

    # -------------------------------------------------------------------------
    def apply_method(self, r, **attr):
        """
            Entry point for CRUD controller

            Args:
                r: the CRUDRequest instance
                attr: controller parameters

            Returns:
                output data (JSON)
        """

        output = {}

        if r.http == "POST":
            if r.ajax or r.representation in ("json", "html"):
                output = self.register(r, **attr)
            else:
                r.error(415, current.ERROR.BAD_FORMAT)
        else:
            r.error(405, current.ERROR.BAD_METHOD)

        return output

    # -------------------------------------------------------------------------
    def register(self, r, **attr):
        """
            Provide a dialog to provide the appointment details and confirm
            the action.

            Args:
                r: the CRUDRequest
                table: the target table

            Returns:
                a JSON object with the dialog HTML as string

            Note:
                redirects to /select upon completion
        """

        T = current.T
        db = current.db
        s3db = current.s3db

        resource = self.resource
        table = resource.table

        # Select-URL for redirections (retain closed/archived flags)
        get_vars = r.get_vars
        select_vars = {"$search": "session"}
        select_vars.update({k:get_vars[k] for k in get_vars.keys() & {"closed", "archived"}})
        select_url = r.url(method="select", representation="", vars=select_vars)

        # Check selection parameters
        post_vars = r.post_vars
        if any(key not in post_vars for key in ("selected", "mode")):
            r.error(400, "Missing selection parameters", next=select_url)

        # Determine the case organisation of the selected set
        person_ids = self.selected_set(resource, post_vars)
        ctable = s3db.dvr_case
        query = (ctable.person_id.belongs(person_ids)) & \
                (ctable.deleted == False)
        rows = db(query).select(ctable.organisation_id, distinct=True)
        if len(rows) != 1:
            r.error(400, T("Cannot create appointment for cases from multiple organisations"), next=select_url)
        organisation_id = rows.first().organisation_id

        # Check permission to create appointments for this organisation
        if not self.permitted(organisation_id):
            r.unauthorised()

        # Save ready-scripts
        s3 = current.response.s3
        jquery_ready = s3.jquery_ready
        s3.jquery_ready = []

        # Form to enter appointment details
        form_name = "%s-create-appointment" % table
        form = self.form(form_name, organisation_id=organisation_id)
        form["_action"] = r.url(representation="", vars=select_vars)

        # Capture injected JS, and restore ready-scripts
        injected = s3.jquery_ready
        s3.jquery_ready = jquery_ready

        output = None
        if r.ajax or r.representation == "json":
            # Dialog request
            # => generate a JSON object with form and control script
            script = '''
(function() {
  $(function() {
      %s
  });
  const t = $('select[name="type_id"]'),
        d = $('input[name="start_date"]'),
        b = $('.bulk-action-submit'),
        toggle = function() {
            var tm = !(t.val()),
                dm = !(d.val());
            if (tm) { t.addClass('invalidinput'); } else { t.removeClass('invalidinput'); }
            if (dm) { d.addClass('invalidinput'); } else { d.removeClass('invalidinput'); }
            b.prop('disabled', tm | dm);
        };
  toggle();
  t.off('.ca').on('change.ca', toggle);
  d.off('.ca').on('change.ca', toggle);
  }
)();''' % ("\n".join(injected))

            dialog = TAG[""](form, SCRIPT(script, _type='text/javascript'))

            current.response.headers["Content-Type"] = "application/json"
            output = json.dumps({"dialog": s3_str(dialog.xml())})

        elif form.accepts(r.vars, current.session, formname=form_name):

            # Dialog submission
            form_vars = form.vars

            # Verify that the selected appointment type is valid
            # (i.e. belongs to the organisation_id)
            appointment_type_id = form_vars.type_id
            if not self.valid_type(appointment_type_id, organisation_id):
                r.error(400, T("Invalid appointment type"), next=select_url)

            # Create the appointment for the selected persons
            created, updated = self.create_appointment(person_ids,
                                                       appointment_type_id,
                                                       form_vars.start_date,
                                                       form_vars.end_date,
                                                       )

            # Generate confirmation message
            msg = T("%(number)s appointments created") % {"number": created}
            if updated:
                msg = "%s (%s)" % (msg, (T("%(number)s already planned") % {"number": updated}))
            current.session.confirmation = msg

            redirect(select_url)
        else:
            r.error(400, current.ERROR.BAD_REQUEST, next=select_url)

        return output

    # -------------------------------------------------------------------------
    @classmethod
    def form(cls, form_name, organisation_id=None):
        """
            Produces the form to select appointment type and date/time

            Args:
                form_name: the form name (for CSRF protection)
                organisation_id: the organisation to create appointment for

            Returns:
                the FORM
        """

        T = current.T
        db = current.db
        s3db = current.s3db

        # Dialog and Form
        atable = s3db.dvr_case_appointment
        ttable = s3db.dvr_case_appointment_type

        # Selector for appointment type
        field = atable.type_id
        dbset = db(ttable.organisation_id == organisation_id)
        field.requires = IS_EMPTY_OR(
                            IS_ONE_OF(dbset, "dvr_case_appointment_type.id",
                                      field.represent,
                                      ))
        type_selector = OptionsWidget.widget(field, None)

        # Default values for date/time interval
        now = current.request.utcnow.replace(microsecond=0)
        start = S3DateTime.datetime_represent(now, utc=True)

        # Date/time interval inputs
        field = atable.start_date
        requires = field.requires
        if isinstance(requires, IS_EMPTY_OR):
            requires = requires.other
        field.requires = requires
        field.default = now
        start_date_input = field.widget(field, start)

        # No default end date
        field = atable.end_date
        end_date_input = field.widget(field, None)

        # Appointment dialog
        components = [LABEL(T("Appointment Type"),
                            DIV(type_selector, _class="controls"),
                            _class="label-above",
                            ),
                      LABEL(T("Start Date"),
                            DIV(start_date_input, _class="controls"),
                            _class="label-above",
                            ),
                      LABEL(T("End Date"),
                            DIV(end_date_input, _class="controls"),
                            _class="label-above",
                            ),
                      DIV(BUTTON(T("Submit"),
                                 _class = "small alert button bulk-action-submit",
                                 _disabled = "disabled",
                                 _type = "submit",
                                 ),
                          A(T("Cancel"),
                            _class = "cancel-form-btn action-lnk bulk-action-cancel",
                            _href = "javascript:void(0)",
                            ),
                          _class = "bulk-action-buttons",
                          ),
                      ]

        form = FORM(*[DIV(c, _class="form-row row") for c in components],
                    hidden = {"_formkey": FormKey(form_name).generate(),
                              "_formname": form_name,
                              },
                    _class = "bulk-action-form",
                    )

        return form

    # -----------------------------------------------------------------------------
    @staticmethod
    def permitted(organisation_id):
        """
            Determines whether the user is permitted to create case appointments
            for the given organisation

            Args:
                organisation_id: the organisation ID

            Returns:
                boolean
        """

        if not organisation_id:
            return False

        permissions = current.auth.permission
        permitted_realms = permissions.permitted_realms("dvr_case_appointment", "create")

        if permitted_realms:
            otable = current.s3db.org_organisation
            query = (otable.id == organisation_id) & \
                    (otable.pe_id.belongs(permitted_realms)) & \
                    (otable.deleted == False)
            row = current.db(query).select(otable.id, limitby=(0, 1)).first()
            return bool(row)

        elif permitted_realms is None:
            return True

        return False

    # -------------------------------------------------------------------------
    @staticmethod
    def selected_set(resource, post_vars):
        """
            Determines the selected persons from select-parameters

            Args:
                resource: the pre-filtered CRUDResource (pr_person)
                post_vars: the POST vars containing the select-parameters

            Returns:
                set of pr_person.id
        """

        pkey = resource.table._id.name

        # Selected records
        selected_ids = post_vars.get("selected", [])
        if isinstance(selected_ids, str):
            selected_ids = {item for item in selected_ids.split(",") if item.strip()}
        query = FS(pkey).belongs(selected_ids)

        # Selection mode
        mode = post_vars.get("mode")
        if mode == "Exclusive":
            query = ~query if selected_ids else None
        elif mode != "Inclusive":
            raise SyntaxError

        # Get all matching record IDs
        if query is not None:
            resource.add_filter(query)
        rows = resource.select([pkey], as_rows=True)

        return {row[pkey] for row in rows}

    # -------------------------------------------------------------------------
    @staticmethod
    def valid_type(type_id, organisation_id=None):
        """
            Verifies that the selected appointment type is valid for the
            given organisation

            Args:
                type_id: the appointment type ID
                organisation_id: the organisation ID

            Returns:
                boolean
        """

        table = current.s3db.dvr_case_appointment_type

        query = (table.id == type_id)
        if organisation_id:
            query &= (table.organisation_id == organisation_id)
        query &= (table.deleted == False)

        row = current.db(query).select(table.id, limitby=(0, 1)).first()
        return bool(row)

    # -------------------------------------------------------------------------
    @staticmethod
    def create_appointment(person_ids, appointment_type_id, start_date, end_date):
        """
            Creates the appointment for each of the selected persons

            Args:
                person_ids: list|set of the selected person's IDs
                appointment_type_id: the appointment type ID
                start_date: the start date/time for the appointment
                end_date: the end date/time for the appointment,
                          defaults to one hour after start

            Returns:
                tuple (num_created, num_updated)

            Notes:
                - overlapping, non-completed appointments of the same type
                  would be updated with new status and date/times rather
                  than duplicated
                - bulk-creation of appointments needs to be handled
                  with extra care as it could be costly to undo
        """

        created = updated = 0

        if person_ids:

            db = current.db
            s3db = current.s3db
            auth = current.auth

            now = current.request.utcnow
            if not start_date:
                start_date = now.replace(minute=0, second=0, microsecond=0) + \
                             datetime.timedelta(hours=1)
            if not end_date:
                end_date = start_date + datetime.timedelta(hours=1)
            if start_date > end_date:
                start_date, end_date = end_date, start_date

            daystart = start_date.replace(hour=0,
                                          minute=0,
                                          second=0,
                                          microsecond=0,
                                          )

            # Look up any overlapping appointments of the same type
            table = s3db.dvr_case_appointment
            query = (table.person_id.belongs(person_ids)) & \
                    (table.status != 4) & \
                    (table.start_date != None) & \
                    (table.end_date != None) & \
                    (table.start_date <= end_date) & \
                    (table.start_date >= daystart) & \
                    (table.end_date >= start_date) & \
                    (table.deleted == False)
            overlapping = db(query).select(table.id,
                                           table.person_id,
                                           table.start_date,
                                           table.end_date,
                                           )
            fixed = set()
            for row in overlapping:
                # Update status
                update = {"status": 2} # planned
                # Update dates if required
                if row.start_date > start_date:
                    update["start_date"] = start_date
                    update["date"] = start_date.date()
                if row.end_date < end_date:
                    update["end_date"] = end_date
                row.update_record(**update)
                fixed.add(row.person_id)
                updated += 1

            remaining = set(person_ids) - fixed
            for person_id in remaining:
                # Create new appointment
                appointment = {"person_id": person_id,
                               "type_id": appointment_type_id,
                               "start_date": start_date,
                               "end_date": end_date,
                               "date": start_date.date,
                               "status": 2, # planned
                               }
                appointment["id"] = appointment_id = table.insert(**appointment)
                s3db.update_super(table, appointment)
                auth.s3_set_record_owner(table, appointment_id)
                s3db.onaccept(table, appointment, method="create")
                created += 1

        return created, updated

# =============================================================================
class CompleteAppointments(CRUDMethod):
    """ Method to complete appointments in-bulk """

    # -------------------------------------------------------------------------
    def apply_method(self, r, **attr):
        """
            Entry point for CRUD controller

            Args:
                r: the CRUDRequest instance
                attr: controller parameters

            Returns:
                output data (JSON)
        """

        output = {}

        if r.http == "POST":
            if r.ajax or r.representation in ("json", "html"):
                output = self.complete(r, **attr)
            else:
                r.error(415, current.ERROR.BAD_FORMAT)
        else:
            r.error(405, current.ERROR.BAD_METHOD)

        return output

    # -------------------------------------------------------------------------
    def complete(self, r, **attr):
        """
            Provide a dialog to enter the actual date interval and confirm
            completion, and upon submission, mark the appointments as completed

            Args:
                r: the CRUDRequest
                table: the target table

            Returns:
                a JSON object with the dialog HTML as string

            Note:
                redirects to /select upon completion
        """

        s3 = current.response.s3

        resource = self.resource
        table = resource.table

        get_vars = r.get_vars

        # Select-URL for redirections
        select_vars = {"$search": "session"}
        select_url = r.url(method="select", representation="", vars=select_vars)

        if any(key not in r.post_vars for key in ("selected", "mode")):
            r.error(400, "Missing selection parameters", next=select_url)

        # Save ready-scripts
        jquery_ready = s3.jquery_ready
        s3.jquery_ready = []

        # Form to choose dates of completion
        form_name = "%s-complete" % table
        form = self.form(form_name)
        form["_action"] = r.url(representation="", vars=get_vars)

        # Capture injected JS, and restore ready-scripts
        injected = s3.jquery_ready
        s3.jquery_ready = jquery_ready

        output = None
        if r.ajax or r.representation == "json":
            # Dialog request
            # => generate a JSON object with form and control script

            # Form control script
            script = '''
(function() {
    $(function() {
        %s
    });
    const s = $('input[name="start_date"]'),
          e = $('input[name="end_date"]'),
          c = $('input[name="complete_confirm"]'),
          b = $('.bulk-action-submit'),
          toggle = function() {
              b.prop('disabled', !c.prop('checked') || !s.val() || !e.val());
          };
    s.add(e).off('.complete').on('change.complete', toggle);
    c.off('.complete').on('click.complete', toggle);
    }
)();''' % ("\n".join(injected))

            dialog = TAG[""](form, SCRIPT(script, _type='text/javascript'))

            current.response.headers["Content-Type"] = "application/json"
            output = json.dumps({"dialog": s3_str(dialog.xml())})

        elif form.accepts(r.vars, current.session, formname=form_name):
            # Dialog submission
            # => process the form, set up, authorize and perform the action

            T = current.T
            pkey = table._id.name
            post_vars = r.post_vars

            try:
                record_ids = self.selected_set(resource, post_vars)
            except SyntaxError:
                r.error(400, "Invalid select mode", next=select_url)
            total_selected = len(record_ids)

            # Verify permission for all selected record
            query = (table._id.belongs(record_ids)) & \
                    (table._id.belongs(self.permitted_set(table, record_ids)))
            permitted = current.db(query).select(table._id)
            denied = len(record_ids) - len(permitted)
            if denied > 0:
                record_ids = {row[pkey] for row in permitted}

            # Read the selected date/time interval
            form_vars = form.vars
            start = form_vars.get("start_date")
            end = form_vars.get("end_date")

            # Mark the appointments as completed
            completed, failed = self.mark_completed(record_ids, start, end)
            success = bool(completed)

            # Build confirmation/error message
            msg = T("%(number)s appointments closed") % {"number": completed}
            failures = []

            failed += denied
            already_closed = total_selected - completed - failed
            if already_closed:
                failures.append(T("%(number)s already closed") % {"number": already_closed})
            if failed:
                failures.append(T("%(number)s failed") % {"number": failed})
            if failures:
                failures = "(%s)" % (", ".join(str(f) for f in failures))
                msg = "%s %s" % (msg, failures)

            if success:
                current.session.confirmation = msg
            else:
                current.session.warning = msg
            redirect(select_url)
        else:
            r.error(400, current.ERROR.BAD_REQUEST, next=select_url)

        return output

    # -------------------------------------------------------------------------
    @classmethod
    def form(cls, form_name):
        """
            Produces the form to select closure status and confirm the action

            Args:
                form_name: the form name (for CSRF protection)

            Returns:
                the FORM
        """

        T = current.T
        tablename = "dvr_case_appointment"

        # Info text and confirmation question
        INFO = T("The selected appointments will be marked as completed.")
        CONFIRM = T("Are you sure you want to mark these appointments as completed?")

        # Default values for date/time interval
        now = current.request.utcnow.replace(microsecond=0)
        start = S3DateTime.datetime_represent(now - datetime.timedelta(hours=1), utc=True)
        end = S3DateTime.datetime_represent(now, utc=True)

        # Date/time interval inputs
        field = Field("start_date", "datetime",
                      requires = IS_UTC_DATETIME(maximum=now),
                      )
        field.tablename = tablename
        widget = S3CalendarWidget(set_min = "#dvr_case_appointment_end_date",
                                  timepicker = True,
                                  future = 0,
                                  )
        start_date_input = widget(field, start)

        field = Field("end_date", "datetime",
                      requires = IS_UTC_DATETIME(maximum=now),
                      )
        field.tablename = tablename
        widget = S3CalendarWidget(set_max = "#dvr_case_appointment_start_date",
                                  timepicker = True,
                                  future = 0,
                                  )
        end_date_input = widget(field, end)

        # Build the form
        components = [P(INFO, _class="bulk-action-info"),
                      LABEL("%s:" % T("Start Date"),
                            DIV(start_date_input, _class="controls"),
                            _class="label-above",
                            ),
                      LABEL("%s:" % T("End Date"),
                            DIV(end_date_input, _class="controls"),
                            _class="label-above",
                            ),
                      P(CONFIRM, _class="bulk-action-question"),
                      LABEL(INPUT(value = "complete_confirm",
                                  _name = "complete_confirm",
                                  _type = "checkbox",
                                  ),
                            T("Yes, mark the selected appointments as completed"),
                            _class = "complete-confirm label-inline",
                            ),
                      DIV(BUTTON(T("Submit"),
                                 _class = "small alert button bulk-action-submit",
                                 _disabled = "disabled",
                                 _type = "submit",
                                 ),
                          A(T("Cancel"),
                            _class = "cancel-form-btn action-lnk bulk-action-cancel",
                            _href = "javascript:void(0)",
                            ),
                          _class = "bulk-action-buttons",
                          ),
                      ]

        form = FORM(*[DIV(c, _class="form-row row") for c in components],
                    hidden = {"_formkey": FormKey(form_name).generate(),
                              "_formname": form_name,
                              },
                    _class = "bulk-action-form",
                    )

        return form

    # -------------------------------------------------------------------------
    @staticmethod
    def selected_set(resource, post_vars):
        """
            Determine the selected persons from select-parameters

            Args:
                resource: the pre-filtered CRUDResource (dvr_case_appointment)
                post_vars: the POST vars containing the select-parameters

            Returns:
                set of dvr_case_appointment.id
        """

        pkey = resource.table._id.name

        # Selected records
        selected_ids = post_vars.get("selected", [])
        if isinstance(selected_ids, str):
            selected_ids = {item for item in selected_ids.split(",") if item.strip()}
        query = FS(pkey).belongs(selected_ids)

        # Selection mode
        mode = post_vars.get("mode")
        if mode == "Exclusive":
            query = ~query if selected_ids else None
        elif mode != "Inclusive":
            raise SyntaxError

        # Get all matching record IDs
        if query is not None:
            resource.add_filter(query)
        rows = resource.select([pkey], as_rows=True)

        return {row[pkey] for row in rows}

    # -------------------------------------------------------------------------
    @staticmethod
    def permitted_set(table, selected_set):
        """
            Produces a sub-query of appointments the user is permitted to
            mark as completed.

            Args:
                table: the target table (dvr_case_appointment)
                selected_set: sub-query for permitted appointments

            Returns:
                SQL
        """

        db = current.db

        # All records in the selected set the user can update
        query = (table._id.belongs(selected_set)) & \
                current.auth.s3_accessible_query("update", table)

        return db(query)._select(table.id)

    # -------------------------------------------------------------------------
    @staticmethod
    def mark_completed(appointment_ids, start_date, end_date):
        """
            Sets the status of the selected appointments to completed (4)

            Args:
                appointment_ids: the record IDs of the selected appointments
                start_date: the start date/time of the appointments
                end_date: the end date/time of the appointments

            Returns:
                tuple (number_completed, number_failed)
        """

        db = current.db
        s3db = current.s3db

        table = s3db.dvr_case_appointment

        if end_date < start_date:
            start_date, end_date = end_date, start_date

        # Determine which appointments should be marked completed
        # - only one appointment per type and client
        query = (table.id.belongs(appointment_ids)) & \
                (table.status.belongs((1, 2, 3))) & \
                (table.deleted == False)
        last = table.id.max()
        rows = db(query).select(last,
                                table.person_id,
                                table.type_id,
                                groupby = (table.person_id, table.type_id),
                                )
        actionable = {row[last] for row in rows}

        # Look up duplicates within the selected set
        # - those will be marked as "not required" and undated instead
        query = (table.id.belongs(appointment_ids)) & \
                (~(table.id.belongs(actionable))) & \
                (table.status.belongs((1, 2, 3))) & \
                (table.deleted == False)
        rows = db(query).select(table.id)
        duplicates = {row.id for row in rows}

        audit = current.audit
        onaccept = s3db.onaccept

        # Mark duplicates as "not required"
        data = Storage(start_date=None, end_date=None, status=7)
        completed = db(table.id.belongs(duplicates)).update(**data)
        for appointment_id in duplicates:
            audit("update", "dvr", "case_appointment",
                  form = Storage(vars=data),
                  record = appointment_id,
                  representation = "html",
                  )

        # Mark actionables as "completed"
        data = Storage(start_date=start_date, end_date=end_date, status=4)
        completed += db(table.id.belongs(actionable)).update(**data)
        for appointment_id in actionable:
            # Onaccept to update last_seen_on
            record = Storage(data)
            record["id"] = appointment_id
            onaccept(table, record, method="update")
            audit("update", "dvr", "case_appointment",
                  form = Storage(vars=data),
                  record = appointment_id,
                  representation = "html",
                  )

        # Calculate failed (should be 0)
        failed = len(actionable) + len(duplicates) - completed

        return completed, failed

# END =========================================================================
