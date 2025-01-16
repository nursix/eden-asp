"""
    Presence Registration UI (ORG)

    Copyright: 2021-2023 (c) Sahana Software Foundation

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

__all__ = ("PresenceRegistration",
           "SitePresence",
           )

import datetime
import json

from gluon import current, redirect, URL, \
                  A, BUTTON, DIV, I, INPUT, SPAN, \
                  Field, IS_NOT_EMPTY, SQLFORM

from ..resource import FS
from ..tools import s3_fullname, s3_str, FormKey, S3DateTime, S3Trackable
from ..ui import S3QRInput, ICON

from .base import CRUDMethod

# =============================================================================
class PresenceRegistration(CRUDMethod):
    """ Interactive registration of presence events at sites """

    # -------------------------------------------------------------------------
    def apply_method(self, r, **attr):
        """
            Entry point for the REST API

            Args:
                r: the CRUDRequest
                attr: controller parameters
        """

        output = {}

        representation = r.representation
        if representation == "html":
            if r.http == "GET":
                output = self.registration_form(r, **attr)
            else:
                r.error(405, current.ERROR.BAD_METHOD)
        elif representation == "json":
            if r.http == "POST":
                output = self.submit_ajax(r, **attr)
            else:
                r.error(405, current.ERROR.BAD_METHOD)
        else:
            r.error(415, current.ERROR.BAD_FORMAT)

        return output

    # -------------------------------------------------------------------------
    def registration_form(self, r, **attr):
        """
            Render the check-in page

            Args:
                r: the CRUDRequest
                attr: controller parameters
        """

        T = current.T
        s3db = current.s3db

        response = current.response
        settings = current.deployment_settings

        resource = r.resource
        table = resource.table

        # User must be logged-in
        logged_in_person_id = current.auth.s3_logged_in_person()
        if not logged_in_person_id:
            r.unauthorised()

        record = r.record
        if record:
            if "site_id" in record:
                site_id = record.site_id
            else:
                # Not a site
                r.error(400, current.ERROR.BAD_REQUEST)
            #if not self.present(site_id):
            #    # TODO offer self-registration at this site
            #    r.unauthorised()
        else:
            site_id = SitePresence.get_current_site(logged_in_person_id, table)
            if site_id:
                record_id = s3db.get_instance("org_site", site_id)[-1]
                redirect(r.url(id=record_id))
            # TODO offer self-registration at a site of this type
            r.unauthorised()

        # Check that user is permitted to register presence at this site
        if not self.permitted(resource.tablename, site_id=site_id, record=record):
            r.unauthorised()

        # Title and site name
        output = {"title": T("Presence Registration"),
                  "sitename": record.name if "name" in table.fields else None,
                  }

        request_vars = r.get_vars
        label = request_vars.get("label")

        # Identify the person
        person = None
        pe_label = None
        if label is not None:
            person = self.get_person(label)
            if person is None:
                response.error = T("No person found with this ID number")

        # Get the person data
        person_data = None
        if person:
            status = self.status(resource.tablename, site_id, person)
            if not status.get("valid"):
                person = None
                response.error = status.get("error", T("Person not allowed to register at this site"))
            else:
                pe_label = person.pe_label
                person_data = self.ajax_data(person, status)

        # Configure label input
        validate_serverside = bool(settings.get_org_site_presence_validate_id())
        label_input = self.label_input
        use_qr_code = settings.get_org_site_presence_qrcode()
        if use_qr_code:
            if use_qr_code is True:
                label_input = S3QRInput()
            elif isinstance(use_qr_code, tuple):
                pattern, index = use_qr_code[:2]
                label_input = S3QRInput(placeholder = T("Enter or scan ID"),
                                        pattern = pattern,
                                        index = index,
                                        keep_original = validate_serverside,
                                        )

        # Standard form fields and data
        formfields = [Field("label",
                            label = T("ID"),
                            requires = IS_NOT_EMPTY(error_message=T("Enter or scan an ID")),
                            widget = label_input,
                            ),
                      Field("person",
                            label = "",
                            readable = True,
                            writable = False,
                            default = "",
                            ),
                      Field("status",
                            label = "",
                            writable = False,
                            default = "",
                            ),
                      Field("info",
                            label = "",
                            writable = False,
                            default = "",
                            ),
                      ]

        # Initial data
        data = {"id": "",
                "label": "", #pe_label,
                "person": "",
                "status": "",
                "info": "",
                }
        if person:
            data["label"] = pe_label

        # Hidden inputs
        hidden = {"data": json.dumps(person_data),
                  "formkey": FormKey("presence-registration/%s" % site_id).generate(),
                  }

        # Form buttons
        check_btn = BUTTON(ICON("id-check"), T("Check"),
                           _class = "small secondary button check-btn",
                           _type = "button",
                           )
        check_in_btn = BUTTON(ICON("entering"), T("Entering"),
                              _class = "small primary button check-in-btn",
                              _type = "button",
                             )
        check_out_btn = BUTTON(ICON("leaving"), T("Leaving"),
                               _class = "small primary button check-out-btn",
                               _type = "button",
                               )

        buttons = [check_btn, check_in_btn, check_out_btn]
        buttons.append(A(T("Cancel"),
                         _class="cancel-action action-lnk",
                         _href=r.url(vars={}),
                         ))

        # Generate the form and add it to the output
        formstyle = settings.get_ui_formstyle()
        widget_id = "presence-form"
        table_name = "site_presence"
        form = SQLFORM.factory(*formfields,
                               record = data, # if person else None,
                               showid = False,
                               formstyle = formstyle,
                               table_name = table_name,
                               buttons = buttons,
                               hidden = hidden,
                               _id = widget_id,
                               _class = "presence-registration",
                               )
        output["form"] = form

        # Status labels
        label_in = SPAN(I(_class = "fa fa-check"),
                        T("Present##presence"),
                        _class = "site-presence-in",
                        )
        label_out = SPAN(I(_class="fa fa-times"),
                         T("Not Present##presence"),
                         _class = "site-presence-out"
                         )

        # Inject JS
        options = {"tableName": table_name,
                   "ajaxURL": r.url(None,
                                    representation = "json",
                                    ),
                   "noPictureAvailable": s3_str(T("No picture available")),
                   "statusIn": s3_str(label_in),
                   "statusOut": s3_str(label_out),
                   "statusNone": "-",
                   "statusLabel": s3_str(T("Status")),
                   "sendOriginalQRInput": validate_serverside,
                   }
        self.inject_js(widget_id, options)

        response.view = "org/site_presence.html"

        return output

    # -------------------------------------------------------------------------
    @staticmethod
    def label_input(field, value, **attributes):
        """
            Custom widget for label input, providing a clear-button
            (for ease of use on mobile devices where no ESC exists)

            Args:
                field: the Field
                value: the current value
                attributes: HTML attributes

            Note:
                expects Foundation theme
        """

        from gluon.sqlhtml import StringWidget

        default = {"value": (value is not None and str(value)) or ""}
        attr = StringWidget._attributes(field, default, **attributes)

        placeholder = current.T("Enter or scan ID")
        attr["_placeholder"] = placeholder

        postfix = ICON("fa fa-close")

        widget = DIV(DIV(INPUT(**attr),
                         _class="small-11 columns",
                         ),
                     DIV(SPAN(postfix, _class="postfix clear-btn"),
                         _class="small-1 columns",
                         ),
                     _class="row collapse",
                     )

        return widget

    # -------------------------------------------------------------------------
    def submit_ajax(self, r, **attr):
        """
            Perform ajax actions, accepts a JSON object as input:
                {m: the method (STATUS|IN|OUT)
                 l: the PE label
                 k: the form key
                 }

            Args:
                r: the CRUDRequest
                attr: controller parameters
        """

        T = current.T

        resource = r.resource

        # Must have a record
        record = r.record
        if not record:
            r.error(400, current.ERROR.BAD_REQUEST)

        # Must be permitted
        permitted = self.permitted(resource.tablename, record=record)
        if not permitted:
            r.unauthorised()

        site_id = record.site_id

        # Load JSON data from request body
        s = r.body
        s.seek(0)
        try:
            data = json.load(s)
        except (ValueError, TypeError):
            r.error(400, current.ERROR.BAD_REQUEST)

        # XSRF protection
        formkey = FormKey("presence-registration/%s" % site_id)
        if not formkey.verify(data, variable="k", invalidate=False):
            r.unauthorised()

        # Initialize
        output = {}
        error = None
        alert = None
        alert_type = "success"

        # Identify the person
        label = data.get("l")
        validate = current.deployment_settings.get_org_site_presence_validate_id()
        if callable(validate):
            label, advice, error = validate(label)
            person = self.get_person(label) if label else None
            if advice:
                output["q"] = s3_str(advice)
        else:
            person = self.get_person(label)

        if person is None:
            if not error:
                error = T("No person found with this ID number")
        else:
            status = self.status(resource.tablename, site_id, person)
            if not status.get("valid"):
                person = None
                error = status.get("error", T("Person not allowed to enter this site"))

        if person:
            method = data.get("m")

            if method == "STATUS":
                ajax_data = self.ajax_data(person, status)
                output.update(ajax_data)

            elif method == "IN":
                current_status = status.get("status")
                check_in_allowed = status.get("allowed_in")

                if not check_in_allowed or status.get("info") is not None:
                    ajax_data = self.ajax_data(person, status)
                    output.update(ajax_data)

                success = False
                if check_in_allowed:
                    success = SitePresence.register(person.id, site_id, "IN")
                if success:
                    output["s"] = "IN"
                    if current_status == "IN":
                        alert = T("Person was already registered as present")
                        alert_type = "warning"
                    else:
                        alert = T("Presence registered")
                elif check_in_allowed is False:
                    alert = T("Person not permitted to enter premises!")
                    alert_type = "error"
                else:
                    alert = T("Registration failed!")
                    alert_type = "error"

            elif method == "OUT":
                current_status = status.get("status")
                check_out_allowed = status.get("allowed_out")

                if not check_out_allowed or status.get("info") is not None:
                    ajax_data = self.ajax_data(person, status)
                    output.update(ajax_data)

                success = False
                if check_out_allowed:
                    success = SitePresence.register(person.id, site_id, "OUT")
                if success:
                    output["s"] = "OUT"
                    if current_status == "OUT":
                        alert = T("Person was already registered as absent")
                        alert_type = "warning"
                    else:
                        alert = T("Absence registered")
                elif check_out_allowed is False:
                    alert = T("Person not permitted to leave premises!")
                    alert_type = "error"
                else:
                    alert = T("Registration failed!")
                    alert_type = "error"
            else:
                r.error(405, current.ERROR.BAD_METHOD)

        # Input-field error
        if error:
            output["e"] = s3_str(error)

        # Page alert
        if alert:
            output["m"] = (s3_str(alert), alert_type)

        current.response.headers["Content-Type"] = "application/json"
        return json.dumps(output)

    # -------------------------------------------------------------------------
    @classmethod
    def ajax_data(cls, person, status):
        """
            Convert person details and current presence status into
            a JSON-serializable dict for Ajax-actions

            Args:
                person: the person record
                status: the status dict (from status())
        """

        person_details = cls.person_details(person)
        output = {"d": s3_str(person_details),
                  "i": True if status.get("allowed_in") else False,
                  "o": True if status.get("allowed_out") else False,
                  "s": status.get("status"),
                  "t": status.get("date"),
                  }

        profile_picture = cls.profile_picture(person)
        if profile_picture:
            output["p"] = profile_picture

        info = status.get("info")
        if info:
            output["a"] = s3_str(info)

        return output

    # -------------------------------------------------------------------------
    @staticmethod
    def get_person(label):
        """
            Returns the person record for a PE label

            Args:
                label: the PE label

            Returns:
                the pr_person Row
        """

        if not label:
            return None

        # Fields to extract
        fields = ["id",
                  "pe_id",
                  "pe_label",
                  "first_name",
                  "middle_name",
                  "last_name",
                  "date_of_birth",
                  "gender",
                  "location_id",
                  ]

        presource = current.s3db.resource("pr_person",
                                          components = [],
                                          filter = (FS("pe_label").upper() == label.upper()),
                                          )
        rows = presource.select(fields, limit=1, as_rows=True)

        return rows[0] if rows else None

    # -------------------------------------------------------------------------
    @staticmethod
    def status(tablename, site_id, person):
        """
            Check the presence status for a person at a site, invokes the
            site_presence_status callback for the site resource to obtain
            additional status information.

            Args:
                r: the CRUDRequest
                site_id: the site ID
                person: the person record

            Returns:
                a dict like:
                     {valid: True|False, whether the person record is valid
                             for check-in/out at this site
                      status: "IN" = currently present at this site
                              "OUT" = currently absent from this site
                              None = no previous status available
                      date: the status date/time
                      info: string or XML to render in info-field
                      allowed_in: True|False
                      allowed_out: True|False
                      error: error message to display in registration form
                      }
        """

        status, _, date = SitePresence.status(person.id,
                                              site_id = site_id,
                                              site_type = tablename,
                                              )

        # Default result
        result =  {"valid": True,
                   "status": status,
                   "date": date.isoformat() if date else None,
                   "info": None,
                   "allowed_in": True,
                   "allowed_out": True,
                   "error": None,
                   }

        # Call site-specific status check
        status_check = current.s3db.get_config(tablename, "site_presence_status")
        if callable(status_check):
            update = status_check(site_id, person)
            if isinstance(update, dict):
                result.update(update)
            elif update:
                result["status"] = update

        return result

    # -------------------------------------------------------------------------
    @staticmethod
    def person_details(person):
        """
            Format the person details

            Args:
                person: the person record (Row)
        """

        T = current.T

        name = s3_fullname(person)
        dob = person.date_of_birth
        if dob:
            dob = S3DateTime.date_represent(dob)
            details = "%s (%s %s)" % (name, T("Date of Birth"), dob)
        else:
            details = name

        return SPAN(details, _class = "person-details")

    # -------------------------------------------------------------------------
    @staticmethod
    def profile_picture(person):
        """
            Get the profile picture URL for a person

            Args:
                person: the person record (Row)

            Returns:
                the profile picture URL (relative URL), or None if
                no profile picture is available for that person
        """

        try:
            pe_id = person.pe_id
        except AttributeError:
            return None

        table = current.s3db.pr_image
        query = (table.pe_id == pe_id) & \
                (table.profile == True) & \
                (table.deleted != True)
        row = current.db(query).select(table.image,
                                       limitby = (0, 1)
                                       ).first()

        if row:
            return URL(c="default", f="download", args=row.image)
        else:
            return None

    # -------------------------------------------------------------------------
    @staticmethod
    def permitted(site_type, site_id=None, record=None):
        """
            Verifies that the user is permitted to register presence at a site

            Args:
                site_type: tablename of the target site
                site_id: the site_id of the target site
                record: alternatively, the site instance record
            Returns:
                boolean

            Note:
                Does not verify whether the user is present at the site,
                this must be checked independently if required
        """

        if not site_id and not record:
            return False

        db = current.db
        s3db = current.s3db
        auth = current.auth
        permissions = auth.permission

        settings = current.deployment_settings

        table = site = None

        # Verify that site_type is valid
        supertables = s3db.get_config(site_type, "super_entity") or []
        if not isinstance(supertables, (tuple, list)):
            supertables = [supertables]
        if "org_site" in supertables:
            valid_types = settings.get_org_site_presence_site_types()
            if valid_types is True or \
               isinstance(valid_types, (tuple, list)) and site_type in valid_types:
                table = s3db[site_type]
        if not table:
            # Not a valid site type
            return False

        # Look up the site (instance)
        check_realm = "realm_entity" in table.fields
        if record:
            query = (table.site_id == record.site_id) & \
                    (table.deleted == False)
            if db(query).select(table.id, limitby=(0, 1)).first():
                site = record
        else:
            query = (table.site_id == site_id) & \
                    (table.deleted == False)
            fields = [table.id, table.site_id]
            if check_realm:
                fields.append(table.realm_entity)
            site = db(query).select(*fields, limitby=(0, 1)).first()
        if not site:
            # Specified site does not exist
            return False

        # Check that the user is permitted to register presence
        permitted = auth.s3_has_permission("create", "org_site_presence_event")
        if permitted and permissions.entity_realm and check_realm:
            # ...at this site?
            permitted_realms = permissions.permitted_realms("org_site_presence_event", "create")
            if permitted_realms:
                realm = site.realm_entity
                if realm and realm not in permitted_realms:
                    # Not permitted for this realm
                    permitted = False
            elif permitted_realms is not None:
                # Not permitted for any realms
                permitted = False

        return permitted

    # -------------------------------------------------------------------------
    @staticmethod
    def present(site_id, check_expired=True):
        """
            Checks if the current user is registered as present at a site

            Args:
                site_id: the site ID
                check_expired: check whether IN-registration has expired
            Returns:
                boolean

            Note:
                Use settings.org.site_presence_expires to configure expiry interval
        """

        db = current.db
        s3db = current.s3db

        settings = current.deployment_settings

        person_id = current.auth.s3_logged_in_person()
        if not person_id:
            return False

        ptable = s3db.org_site_presence
        query = (ptable.person_id == person_id) & \
                (ptable.site_id == site_id) & \
                (ptable.status == "IN") & \
                (ptable.deleted == False)
        row = db(query).select(ptable.id,
                               ptable.modified_on,
                               limitby = (0, 1),
                               ).first()
        if row:
            expires = settings.get_org_site_presence_expires() if check_expired else False
            if expires and isinstance(expires, int):
                date = ptable.modified_on
                earliest = datetime.datetime.utcnow() - datetime.timedelta(hours=expires)
                present = False if date < earliest else True
            else:
                present = True
        else:
            present = False

        return present

    # -------------------------------------------------------------------------
    @staticmethod
    def inject_js(widget_id, options):
        """
            Helper function to inject static JS and instantiate the
            client-side widget

            Args:
                widget_id: the node ID where to instantiate the widget
                options: dict of widget options (JSON-serializable)
        """

        s3 = current.response.s3
        appname = current.request.application

        # Static JS
        scripts = s3.scripts
        if s3.debug:
            script = "/%s/static/scripts/S3/s3.ui.presence.js" % appname
        else:
            script = "/%s/static/scripts/S3/s3.ui.presence.min.js" % appname
        scripts.append(script)

        # Instantiate widget
        scripts = s3.jquery_ready
        script = '''$('#%(id)s').registerPresence(%(options)s)''' % \
                 {"id": widget_id, "options": json.dumps(options)}
        if script not in scripts:
            scripts.append(script)

# =============================================================================
class SitePresence:
    """ Toolkit to query and manage site presence """

    # -------------------------------------------------------------------------
    @staticmethod
    def get_current_site(person_id, table=None, site_id=None):
        """
            Get the site where a person is currently registered as present

            Args:
                person_id: the person record ID
                table: a site instance table, to limit the query to a
                       certain type of sites
                site_id: the site ID, to check the person's presence at
                         that particular site

            Returns:
                the site ID where the person is currently registered
                as present, or None
        """

        ptable = current.s3db.org_site_presence
        query = (ptable.person_id == person_id) & \
                (ptable.status == "IN")
        if table:
            query &= (ptable.site_id == table.site_id)
        if site_id:
            query &= (ptable.site_id == site_id)
        query &= (ptable.deleted == False)

        row = current.db(query).select(ptable.site_id,
                                       limitby = (0, 1),
                                       ).first()

        return row.site_id if row else None

    # -------------------------------------------------------------------------
    @staticmethod
    def register(person_id, site_id, event_type):
        """
            Register a presence event

            Args:
                person_id: the person ID
                site_id: the site ID
                event_type: the event type "IN"|"OUT"|"SEEN"

            Returns:
                True if successful, else False
        """

        db = current.db
        s3db = current.s3db

        # Customise site_presence_event (to allow custom onaccept callbacks)
        from ..controller import CRUDRequest
        r = CRUDRequest("org", "site_presence_event", args=[], get_vars={})
        r.customise_resource("org_site_presence_event")

        # Create a new event
        event = {"person_id": person_id,
                 "site_id": site_id,
                 "event_type": event_type,
                 "date": datetime.datetime.utcnow().replace(microsecond=0),
                 }
        etable = s3db.org_site_presence_event
        event["id"] = record_id = etable.insert(**event)

        if record_id:
            s3db.update_super(etable, event)
            current.auth.s3_set_record_owner(etable, record_id)
            s3db.onaccept(etable, event)

            # Add an entry to the Site Event Log
            # TODO deprecate since redundant?
            if event_type in ("IN", "OUT"):
                s3db.org_site_event.insert(person_id = person_id,
                                           site_id = site_id,
                                           event = 3 if event_type == "IN" else 4,
                                           date = event["date"],
                                           )

            # Determine the site type
            stable = s3db.org_site
            row = db(stable.site_id == site_id).select(stable.instance_type,
                                                       limitby = (0, 1),
                                                       ).first()
            if row:
                site_type = row.instance_type
                itable = s3db.table(site_type)
            else:
                site_type = itable = None

            if itable and "location_id" in itable.fields:
                # Look up the location_id and update the track location of the person
                # ...this applies for any event type, since the person must be there?
                site = db(itable.site_id == site_id).select(itable.location_id,
                                                            limitby = (0, 1),
                                                            ).first()
                if site:
                    tracker = S3Trackable(s3db.pr_person, record_id=person_id)
                    tracker.set_location(site.location_id)

            if site_type:
                # Invoke the site-type-specific callback for the event
                setting = "site_presence_%s" % event_type.lower()
                cb = s3db.get_config(site_type, setting)
                if cb:
                    cb(site_id, person_id)

        return bool(record_id)

    # -------------------------------------------------------------------------
    @staticmethod
    def status(person_id, site_id=None, site_type=None):
        """
            Returns a person's current presence status

            Args:
                person_id: the person record ID
                site_id: a site ID
                site_type: a tablename to filter by site type

            Returns:
                Tuple (status, site, date/time) with the current presence
                status of the person; either at the specified site, or any
                site (of the specified type)
        """

        db = current.db
        s3db = current.s3db

        stable = s3db.org_site
        ptable = s3db.org_site_presence
        etable = s3db.org_site_presence_event

        if site_type:
            join = stable.on((stable.site_id == ptable.site_id) & \
                             (stable.instance_type == site_type))
        else:
            join = None

        result = (None, None, None)

        if site_id:
            # Check the person's presence at this site
            query = (ptable.person_id == person_id) & \
                    (ptable.site_id == site_id) & \
                    (ptable.deleted == False)
            row = db(query).select(ptable.status,
                                   ptable.site_id,
                                   ptable.date,
                                   join = join,
                                   limitby = (0, 1),
                                   ).first()
            if row:
                result = (row.status, row.site_id, row.date)
            return result

        # Check if the person is reported "IN" at any site
        query = (ptable.person_id == person_id) & \
                (ptable.status == "IN") & \
                (ptable.site_id != None) & \
                (ptable.deleted == False)
        row = db(query).select(ptable.site_id,
                               ptable.date,
                               join = join,
                               limitby = (0, 1),
                               orderby = ~ptable.modified_on,
                               ).first()
        if row:
            result = ("IN", row.site_id, row.date)
        else:
            # Get the lastest "OUT" event for the person
            if site_type:
                join = stable.on((stable.site_id == etable.site_id) & \
                                 (stable.instance_type == site_type))
            else:
                join = None
            query = (etable.person_id == person_id) & \
                    (etable.event_type == "OUT") & \
                    (etable.site_id != None) & \
                    (etable.deleted == False)
            row = db(query).select(etable.site_id,
                                   etable.date,
                                   join = join,
                                   limitby = (0, 1),
                                   orderby = (~etable.date, ~etable.id),
                                   ).first()
            if row:
                result = ("OUT", row.site_id, row.date)

        return result

# END =========================================================================
