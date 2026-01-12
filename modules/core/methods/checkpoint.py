"""
    Checkpoint UI (DVR)

    Copyright: 2023-2023 (c) Sahana Software Foundation

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

__all__ = ("Checkpoint",
           )

import datetime
import json

from gluon import current, URL, \
                  A, DIV, H4, INPUT, SPAN, \
                  SQLFORM, IS_LENGTH, IS_NOT_EMPTY

from s3dal import Field

from .base import CRUDMethod
from .presence import SitePresence
from ..tools import s3_fullname, s3_str, S3DateTime, FormKey
from ..resource import FS
from ..ui import S3QRInput, ICON

# =============================================================================
class Checkpoint(CRUDMethod):
    """ User interface for checkpoints to register DVR case events """

    # Action to look up flag instructions for
    # TODO modify to show instructions per event class
    # TODO extend with option to restrict event types per flag
    ACTION = "id-check"

    # Event class this method is intended for
    EVENT_CLASS = "C" # Checkpoint

    # -------------------------------------------------------------------------
    def apply_method(self, r, **attr):
        """
            Entry point for CRUD controller

            Args:
                r: the CRUDRequest instance
                attr: controller parameters
        """

        output = {}

        representation = r.representation
        http = r.http

        if representation == "html":

            if http == "GET":
                output = self.registration_form(r, **attr)
            else:
                r.error(405, current.ERROR.BAD_METHOD)

        elif representation == "json":

            if http == "GET":
                output = self.event_types(r, **attr)
            elif http == "POST":
                output = self.check_or_register(r, **attr)
            else:
                r.error(405, current.ERROR.BAD_METHOD)

        else:
            r.error(415, current.ERROR.BAD_FORMAT)

        return output

    # -------------------------------------------------------------------------
    # Response methods
    # -------------------------------------------------------------------------
    def registration_form(self, r, **attr):
        """
            Delivers the event registration form

            Args:
                r: the CRUDRequest instance
                attr: controller parameters

            Returns:
                dict with view elements
        """

        if not current.auth.s3_has_permission("create", "dvr_case_event"):
            r.unauthorised()

        T = current.T
        #s3db = current.s3db

        response = current.response
        settings = current.deployment_settings

        output = {}
        widget_id = "case-event-form"

        # Add organisation selector
        organisations = self.get_organisations() # {id: Row(id, name), _default: id}
        selector = self.organisation_selector(organisations, widget_id=widget_id)
        output.update(selector)

        # Default organisation_id
        organisation_id = organisations.get("_default") # Could be None

        # Add event type selector
        event_types = self.get_event_types(organisation_id) # {id: Row(id, code, name), _default: id}, or None
        selector = self.event_type_selector(event_types, widget_id=widget_id)
        output.update(selector)

        # Default event type
        default = event_types.get("_default")
        if default:
            event_type = event_types.get(default)
            event_code = event_type.code if event_type else None
        else:
            event_type = None
            event_code = None

        label_input = self.label_input
        use_qr_code = settings.get_org_site_presence_qrcode()
        if use_qr_code:
            if use_qr_code is True:
                label_input = S3QRInput()
            elif isinstance(use_qr_code, tuple):
                pattern, index = use_qr_code[:2]
                label_input = S3QRInput(pattern=pattern, index=index)

        # Standard form fields and data
        formfields = [Field("label",
                            label = T("ID"),
                            requires = [IS_NOT_EMPTY(error_message=T("Enter or scan an ID")),
                                        IS_LENGTH(512, minsize=1),
                                        ],
                            widget = label_input,
                            ),
                      Field("person",
                            label = "",
                            writable = False,
                            default = "",
                            ),
                      Field("flaginfo",
                            label = "",
                            writable = False,
                            ),
                      Field("details",
                            label = "",
                            writable = False,
                            ),
                      Field("family",
                            label = T("Family"),
                            writable = False,
                            ),
                      ]

        data = {"id": "",
                "label": "",
                "person": "",
                "flaginfo": "",
                "family": "",
                "details": "",
                }

        # Hidden fields to store event type, scanner, flag info and permission
        hidden = {"event": event_code,
                  "actionable": None,
                  "permitted": None,
                  "flags": [],
                  "familyinfo": None,
                  "intervals": None,
                  "image": None,
                  "_formkey": FormKey("case-event-registration").generate(),
                  }

        # TODO Additional form data
        #widget_id, submit = self.get_form_data(person,
                                               #formfields,
                                               #data,
                                               #hidden,
                                               #permitted = permitted,
                                               #)

        # Form buttons
        check_btn = INPUT(_class = "small secondary button check-btn",
                          _name = "check",
                          _type = "submit",
                          _value = T("Check ID"),
                          )
        submit_btn = INPUT(_class = "small primary button submit-btn hide",
                           _disabled = "disabled",
                           _name = "submit",
                           _type = "submit",
                           _value = T("Register"),
                           )
        buttons = [check_btn, submit_btn]

        # Add the cancel-action
        buttons.append(A(T("Cancel"), _class = "cancel-action cancel-form-btn action-lnk"))

        resourcename = r.resource.name

        # Generate the form and add it to the output
        formstyle = settings.get_ui_formstyle()
        form = SQLFORM.factory(record = data,
                               showid = False,
                               formstyle = formstyle,
                               table_name = resourcename,
                               buttons = buttons,
                               hidden = hidden,
                               _id = widget_id,
                               _class = "event-registration-form",
                               *formfields)
        output["form"] = form
        output["picture"] = DIV(_class = "panel profile-picture",
                                _id = "%s-picture" % widget_id,
                                )

        # Custom view
        response.view = self._view(r, "dvr/register_case_event.html")

        # Show profile picture by default or only on demand?
        show_picture = settings.get_ui_checkpoint_show_picture()
        multi_preselect_all = settings.get_ui_checkpoint_multi_preselect_all()

        # Inject JS
        options = {"tablename": resourcename,
                   "ajaxURL": self.ajax_url(r),
                   "multiPreselectAll": multi_preselect_all,
                   "showPicture": show_picture,
                   "showPictureText": s3_str(T("Show Picture")),
                   "hidePictureText": s3_str(T("Hide Picture")),
                   "selectAllText": s3_str(T("Select All")),
                   "noEventsLabel": s3_str(T("No event types available")),
                   "selectEventLabel": s3_str(T("Please select an event type")),
                   }
        self.inject_js(widget_id, options)

        return output

    # -------------------------------------------------------------------------
    @classmethod
    def event_types(cls, r, **attr):
        """
            Returns the event types for the organisation specified by the
            URL query parameter "org" (=the organisation ID)

            Args:
                r: the CRUDRequest instance
                attr: controller parameters

            Returns:
                - a JSON object {"types": [[code, name, multiple], ...],
                                 "default": [code, name, multiple],
                                 }
        """

        T = current.T

        organisation_id = r.get_vars.get("org")
        if organisation_id:
            # Get the event types for the organisation
            event_types = cls.get_event_types(organisation_id)

            # Build the type list
            types, default = [], None
            encode = lambda t: [t.code, s3_str(T(t.name)), t.register_multiple]
            for k, v in event_types.items():
                if k == "_default":
                    default = encode(event_types[v])
                else:
                    types.append(encode(v))

            # Sort types alphabetically by label
            output = {"types": sorted(types, key=lambda i: i[1])}
            if default:
                output["default"] = default
        else:
            output = {"types": [], "default": None}

        current.response.headers["Content-Type"] = "application/json"
        return json.dumps(output)

    # -------------------------------------------------------------------------
    def check_or_register(self, r, **attr):
        """
            Check the ID label or register an event for the person

            Args:
                r: the CRUDRequest
                **attr: controller parameters

            Returns:
                a JSON object like:
                    {// Person details
                     "l": the actual PE label (to update the input field),
                     "p": the person details (HTML),
                     "f": flags instructions
                          [{"n": the flag name, "i": flag instructions},...],
                     "b": profile picture URL,  # TODO Change into i(mage)
                     "x": the family details,

                     // Transaction details
                     "d": action details,       # TODO proper explanation
                     "i": blocked events        # TODO Change into "r" (=rules)
                          {<event_code>: [<msg>, <blocked_until_datetime>]},
                     "u": actionable info (e.g. which payment to pay out)
                     "s": whether the action is permitted or not

                     // Messages
                     "a": form error (for label field)
                     "e": error message
                     "w": warning message
                     "c": success message
                     }

            Note:
                Request body is expected to contain a JSON-object like:
                    {"a": the action ("check"|"register")
                     "k": XSRF token
                     "l": the PE label(s)
                     "o": the organisation ID
                     "t": the event type code
                     }
        """

        # Load JSON data from request body
        s = r.body
        s.seek(0)
        try:
            json_data = json.load(s)
        except (ValueError, TypeError):
            r.error(400, current.ERROR.BAD_REQUEST)

        # XSRF protection
        formkey = FormKey("case-event-registration")
        if not formkey.verify(json_data, variable="k", invalidate=False):
            r.unauthorised()

        # Dispatch by action
        action = json_data.get("a")
        if action == "check":
            output = self.check(r, json_data)
        elif action == "register":
            output = self.register(r, json_data)
        else:
            r.error(400, current.ERROR.BAD_REQUEST)

        current.response.headers["Content-Type"] = "application/json"
        return json.dumps(output)

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------
    def check(self, r, json_data):
        """
            Checks the ID label against the selected organisation, and
            returns the relevant details to register events for the person

            Args:
                r: the CRUDRequest
                json_data: the input JSON, see check_or_register

            Returns:
                a JSON-serializable dict, format see check_or_register
        """

        organisation_id = json_data.get("o")
        if not organisation_id:
            r.error(400, current.ERROR.BAD_REQUEST)

        # NOTE Permission to read person record implied by get_person()

        # Identify the person
        label = json_data.get("l")
        validate = current.deployment_settings.get_org_site_presence_validate_id()
        if callable(validate):
            label, advice, error = validate(label)
            person = self.get_person(label, organisation_id) if label else None
            if error:
                # TODO show as advice
                # TODO disable action
                pass
        else:
            advice, error = None, None
            person = self.get_person(label, organisation_id)
        if not person:
            if not error:
                advice = current.T("No person found with this ID number")
            else:
                advice = None

        output = {"l": label,
                  "a": s3_str(advice) if advice else None,
                  "e": s3_str(error) if error else None,
                  }

        if person:
            output["l"] = person.pe_label
            output["p"] = s3_str(self.person_details(person).xml())
            output["b"] = self.profile_picture(person)

            # Check if resident
            is_resident, site_id = self.is_resident(person.id, organisation_id)
            if is_resident and site_id:
                # Absence warning
                from .presence import SitePresence
                status = SitePresence.status(person.id, site_id=site_id)[0]
                if status == "OUT":
                    warning = current.T("Person currently reported as absent")
                    output["w"] = s3_str(warning)

            # Flag instructions
            output["f"] = self.flag_instructions(person.id,
                                                 organisation_id = organisation_id,
                                                 )

            # Family members
            family = self.get_family_members(person.id, organisation_id)
            if family:
                output["x"] = family

            # Blocked events
            blocked = self.get_blocked_events(person.id,
                                              organisation_id,
                                              is_resident = is_resident,
                                              serializable = True,
                                              )
            if blocked:
                # TODO format as r: {event_code: {m: message, e: earliest}}
                output["i"] = blocked

            output["s"] = True
        else:
            output["p"] = None
            output["s"] = False

        return output

    # -------------------------------------------------------------------------
    def register(self, r, json_data):
        """
            Registers a case event for a person with the specified organisation

            Args:
                r: the CRUDRequest
                json_data: the input JSON, see check_or_register

            Returns:
                a JSON-serializable dict, format see check_or_register
        """

        T = current.T

        organisation_id = json_data.get("o")
        if not organisation_id:
            r.error(400, current.ERROR.BAD_REQUEST)

        # Check permission
        # NOTE Permission to read person record implied by get_person()
        if not self.permitted("create", "dvr_case_event", organisation_id=organisation_id):
            r.unauthorised()

        persons = []
        error = None

        # Identify the event type
        code = json_data.get("t")
        event_type = self.get_event_type(code, organisation_id)
        if event_type:
            # Identify the person(s)
            labels = json_data.get("l")
            if not labels:
                labels = []
            elif not isinstance(labels, list):
                labels = [labels]
            elif not event_type.register_multiple:
                # GUI should prevent this, but need to catch forged requests
                labels = []
                event_type = None
                error = T("Multiple-registration not permitted")

            validate = current.deployment_settings.get_org_site_presence_validate_id()
            for i, label in enumerate(labels):
                if i > 1:
                    validate = None
                if callable(validate):
                    label, advice, error = validate(label)
                    person = self.get_person(label, organisation_id) if label else None
                    #if advice:
                        #output["e"] = s3_str(advice)
                else:
                    advice, error = None, None
                    person = self.get_person(label, organisation_id)
                if person:
                    persons.append(person)
                else:
                    # TODO Error: person not found
                    break

        if persons and event_type:
            for person in persons:
                # TODO Check event type not blocked for that person
                #      - GUI should prevent this, but need to catch forged requests
                success = self.register_case_event(person, event_type.id)
                if not success:
                    error = T("Event registration failed")
                    break
        elif not event_type:
            if not error:
                error = T("Invalid event type")
        elif not error:
            error = T("Person not found")

        if error:
            output = {"e": s3_str(error)}
        else:
            output = {"c": s3_str(T("Event registered"))}

        return output

    # -------------------------------------------------------------------------
    @staticmethod
    def register_case_event(person, event_type_id):
        """
            Registers an event for a person (low-level method)

            Args:
                person: the pr_person Row
                event_type_id: the event type record ID

            Returns:
                True if successful, otherwise False
        """

        s3db = current.s3db

        etable = s3db.dvr_case_event

        # Customise event resource
        from ..controller import CRUDRequest
        r = CRUDRequest("dvr", "case_event", current.request, args=[], get_vars={})
        r.customise_resource("dvr_case_event")

        data = {"person_id": person.id,
                "type_id": event_type_id,
                "date": current.request.utcnow,
                }
        record_id = etable.insert(**data)
        if record_id:
            # Set record owner
            auth = current.auth
            auth.s3_set_record_owner(etable, record_id)
            auth.s3_make_session_owner(etable, record_id)
            # Execute onaccept
            data["id"] = record_id
            s3db.onaccept(etable, data, method="create")

        return bool(record_id)

    # -------------------------------------------------------------------------
    # UI Widgets
    # -------------------------------------------------------------------------
    @staticmethod
    def organisation_selector(organisations, widget_id=None):
        """
            Args:
                organisations: all permitted organisations (dict as produced
                               by get_organisations())
                widget_id: the node ID of the registration form

            Returns:
                dict of view elements
        """

        #organisations = {id: Row(id, name), _default: id}

        T = current.T

        # Organisation selection buttons
        buttons = []
        default = None
        for k, v in organisations.items():
            if k == "_default":
                default = v
            else:
                button = A(T(v.name),
                           _class = "secondary button org-select",
                           data = {"id": s3_str(k), "name": s3_str(v.name)},
                           )
                buttons.append(button)

        # Organisation name
        classes = ["org-header"]
        data = {}
        if buttons:
            if default:
                organisation = organisations[default]
                data["selected"] = organisation.id
                org_name = organisation.name
                classes.append("selected")
                if len(buttons) == 1:
                    classes.append("disabled")
            else:
                org_name = T("Please select an organization")
        else:
            # No organisations selectable
            org_name = T("No organization")
            classes.append("empty")
            classes.append("disabled")

        # Organisation header
        header = DIV(H4(org_name, _class="org-name"),
                     _class = " ".join(classes),
                     _id = "%s-org-header" % widget_id,
                     data = data,
                     )

        # Organisation selector
        if buttons:
            select = DIV(buttons,
                         _class="button-group stacked hide org-select",
                         _id = "%s-org-select" % widget_id,
                         )
        else:
            select = ""

        return {"org_header": header,
                "org_select": select,
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def event_type_selector(event_types, widget_id=None):
        """
            Args:
                event_types: all permitted event types (dict as produced
                             by get_event_types())
                widget_id: the node ID of the registration form

            Returns:
                dict of view elements
        """

        T = current.T

        # Organisation selection buttons
        buttons = []
        default = None
        for k, v in event_types.items():
            if k == "_default":
                default = v
            else:
                name = T(v.name)
                button = A(name,
                           _class = "secondary button event-type-select",
                           data = {"code": s3_str(v.code),
                                   "name": s3_str(name),
                                   "multiple": "T" if v.register_multiple else "F",
                                   },
                           )
                buttons.append(button)

        data = {}
        classes = ["event-type-header"]
        if buttons:
            if default:
                event_type = event_types.get(default)
                name = T(event_type.name)
                data["code"] = event_type.code
                if len(buttons) == 1:
                    classes.append("disabled")
            else:
                name = T("Please select an event type")
        else:
            name = T("No event types available")
            classes.append("empty")
            classes.append("disabled")

        header = DIV(H4(name, _class="event-type-name"),
                     data = data,
                     _class = " ".join(classes),
                     _id = "%s-event-type-header" % widget_id,
                     )

        select = DIV(buttons,
                     _class="button-group stacked hide event-type-select",
                     _id="%s-event-type-select" % widget_id,
                     )

        return {"event_type_header": header,
                "event_type_select": select,
                }

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
    @staticmethod
    def ajax_url(r):
        """
            The Ajax URL for check/register requests; for subclasses

            Args:
                r: the CRUDRequest
            Returns:
                URL
        """

        return r.url(None, method="register", representation="json")

    # -------------------------------------------------------------------------
    @staticmethod
    def get_form_data(person, formfields, data, hidden, permitted=False):
        # TODO deprecate?
        """
            Helper function to extend the form

            Args:
                person: the person (Row)
                formfields: list of form fields (Field)
                data: the form data (dict)
                hidden: hidden form fields (dict)
                permitted: whether the action is permitted

            Returns:
                tuple (widget_id, submit_label)
        """

        T = current.T
        s3db = current.s3db

        # Extend form with household size info
        if person:
            details = s3db.dvr_get_household_size(person.id,
                                                  dob = person.date_of_birth,
                                                  )
        else:
            details = ""
        formfields.extend([Field("details",
                                 label = T("Family"),
                                 writable = False,
                                 ),
                           ])
        data["details"] = details

        widget_id = "case-event-form"
        submit = current.T("Register")

        return widget_id, submit

    # -------------------------------------------------------------------------
    # Lookup methods
    # -------------------------------------------------------------------------
    @staticmethod
    def get_person(label, organisation_id=None):
        """
            Returns the person record for a label

            Args:
                label: the PE label
                organisation_id: the organisation ID

            Returns:
                the person record (pr_person Row)
        """

        if not label or not organisation_id:
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
                  ]

        query = (FS("pe_label").upper() == label.upper()) & \
                (FS("dvr_case.organisation_id") == organisation_id) & \
                (FS("dvr_case.archived") == False) & \
                (FS("dvr_case.status_id$is_closed") == False)

        presource = current.s3db.resource("pr_person",
                                          components = [],
                                          filter = query,
                                          )
        rows = presource.select(fields, limit=1, as_rows=True)

        return rows[0] if rows else None

    # -------------------------------------------------------------------------
    @staticmethod
    def person_details(person):
        """
            Formats person details

            Args:
                person: the person record (Row)

            Returns:
                HTML with formatted details
        """

        T = current.T

        name = s3_fullname(person)
        dob = person.date_of_birth
        if dob:
            dob = S3DateTime.date_represent(dob)
            details = "%s (%s %s)" % (name, T("DoB"), dob)
        else:
            details = name

        return SPAN(details, _class="person-details")

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
        row = current.db(query).select(table.image, limitby=(0, 1)).first()

        return URL(c="default", f="download", args=row.image) if row else None

    # -------------------------------------------------------------------------
    @staticmethod
    def is_resident(person_id, organisation_id):
        """
            Check if a person is a current resident of a shelter of
            the organisation

            Args:
                person_id: the person ID
                organisation_id: the organisation ID

            Returns:
                tuple (is_resident, site_id)
        """

        db = current.db
        s3db = current.s3db

        is_resident, site_id = None, None

        stable = s3db.cr_shelter
        query = (stable.organisation_id == organisation_id) & \
                (stable.deleted == False)
        has_shelters = db(query).select(stable.id, limitby=(0, 1)).first()
        if has_shelters:
            rtable = s3db.cr_shelter_registration
            join = rtable.on((rtable.shelter_id == stable.id) & \
                             (rtable.person_id == person_id) & \
                             (rtable.registration_status == 2) & \
                             (rtable.deleted == False))
            row = db(query).select(stable.site_id, join=join, limitby=(0, 1)).first()
            if row:
                is_resident, site_id = True, row.site_id
            else:
                is_resident = False

        return is_resident, site_id

    # -------------------------------------------------------------------------
    @staticmethod
    def flag_instructions(person_id, organisation_id=None):
        """
            Returns any flag instructions of an organisation for a client

            Args:
                person_id: the client person record ID
                organisation_id: the organisation record ID

            Returns:
                a JSON-serializable dict {flagname: instructions}
        """

        T = current.T
        s3db = current.s3db

        flag_info = s3db.dvr_get_flag_instructions(person_id,
                                                   organisation_id = organisation_id,
                                                   )
        info = flag_info["info"]

        flags = []
        for flagname, instructions in info:
            flags.append({"n": s3_str(T(flagname)),
                          "i": s3_str(T(instructions)),
                          })
        return flags

    # -------------------------------------------------------------------------
    def get_family_members(self, person_id, organisation_id):
        """
            Extracts and formats family details for a client

            Args:
                person_id: the client person record ID
                organisation_id: the organisation record ID

            Returns:
                array with family member infos, format:
                    [{l: pe_label,
                      n: fullname,
                      d: dob_formatted,
                      p: picture_URL,
                      r: {
                        # blocked events for this family member
                        event_code: {m: message, e: earliest_date_ISO}
                      }, ...
                     ]
        """

        db = current.db
        s3db = current.s3db

        # Case groups this person belongs to
        gtable = s3db.pr_group
        mtable = s3db.pr_group_membership
        join = gtable.on((gtable.id == mtable.group_id) & \
                         (gtable.group_type == 7))
        query = ((mtable.person_id == person_id) & \
                 (mtable.deleted != True))
        groups = db(query)._select(mtable.group_id, join=join)

        members = {}

        # Open case statuses
        stable = s3db.dvr_case_status
        open_status = db(stable.is_closed == False)._select(stable.id)

        # Other group members with open cases with the same organisation
        ptable = s3db.pr_person
        itable = s3db.pr_image
        ctable = s3db.dvr_case
        join = [ptable.on(ptable.id == mtable.person_id),
                ctable.on((ctable.person_id == ptable.id) & \
                          (ctable.organisation_id == organisation_id) & \
                          (ctable.status_id.belongs(open_status)) & \
                          (ctable.archived == False) & \
                          (ctable.deleted == False)),
                ]
        left = [itable.on((itable.pe_id == ptable.pe_id) & \
                          (itable.profile == True) & \
                          (itable.deleted == False)),
                ]

        query = (mtable.group_id.belongs(groups)) & \
                (mtable.deleted ==False)
        rows = db(query).select(ptable.id,
                                ptable.pe_label,
                                ptable.first_name,
                                ptable.last_name,
                                ptable.date_of_birth,
                                itable.image,
                                join = join,
                                left = left,
                                )
        for row in rows:
            member_id = row.pr_person.id
            if member_id not in members:
                members[member_id] = row

        output = []
        for member_id, row in members.items():
            # Person data
            member = row.pr_person
            data = {"l": member.pe_label,
                    "n": s3_fullname(member),
                    "d": S3DateTime.date_represent(member.date_of_birth),
                    }
            if str(member.id) == str(person_id):
                data["s"] = True

            # Profile picture URL
            picture = row.pr_image
            if picture.image:
                data["p"] = URL(c = "default",
                                f = "download",
                                args = picture.image,
                                )
            # Blocking rules
            is_resident = self.is_resident(member_id, organisation_id)[0]
            event_rules = self.get_blocked_events(member_id,
                                                  organisation_id,
                                                  is_resident = is_resident,
                                                  serializable = True,
                                                  )
            if event_rules:
                data["r"] = event_rules

            output.append(data)

        return output

    # -------------------------------------------------------------------------
    @classmethod
    def get_blocked_events(cls,
                           person_id,
                           organisation_id,
                           is_resident = True,
                           event_type_id = None,
                           serializable = True,
                           ):
        """
            Returns currently excluded events for a person including reasons
            for their exclusion

            Args:
                person_id: the person record ID
                organisation_id: the organisation record ID
                is_resident: whether the person is currently a checked-in
                             resident at a shelter of the organisation
                event_type_id: check only this event type (rather than all
                               event types defined by the organisation)
                serializable: return JSON-serializable data

            Returns:
                a dict with exclusion details
                {event_type_id: (error_message, blocked_until_datetime, permit_others)}

            Note:
                - permit_others flag indicates that the registration for other
                  family members is still permitted even when it is blocked for
                  the person whose ID is being used for the registration
        """

        now = current.request.utcnow.replace(microsecond=0)
        day_start = now.replace(hour=0, minute=0, second=0)

        # Get event types for organisation
        event_types = cls.get_event_types(organisation_id)

        # Get event types to check
        event_type_ids = set(event_types.keys())
        event_type_ids.discard("_default")
        if event_type_id and event_type_id in event_type_ids:
            check = {event_type_id}
        else:
            check = event_type_ids

        excluded = {}

        # Exclude residents-only event types if the person is not currently
        # a resident at a shelter of the organisation
        if not is_resident:
            not_applicable = cls.check_residents_only(check, event_types)
            excluded.update(not_applicable)
            check -= set(not_applicable.keys())

        # Exclude event types that are not combinable with other events
        # registered today
        non_combinable = cls.check_non_combinable(person_id, check, day_start, event_types)
        excluded.update(non_combinable)
        check -= set(non_combinable.keys())

        # Exclude event types for which maximum number of occurences per
        # day have been reached
        max_per_day = cls.check_max_per_day(person_id, check, day_start, event_types)
        excluded.update(max_per_day)
        check -= set(max_per_day.keys())

        # Exclude event types for which minimum interval between consecutive
        # occurences has not yet been reached
        min_interval = cls.check_min_interval(person_id, check, now, event_types)
        excluded.update(min_interval)
        check -= set(min_interval.keys())

        if serializable:
            formatted = {}
            for type_id, reason in excluded.items():
                msg, earliest, permit_others = reason
                earliest = earliest.isoformat() + "Z" if earliest else None
                event_type = event_types[type_id]
                formatted[event_type.code] = [s3_str(msg), earliest, permit_others]
            excluded = formatted

        return excluded

    # -------------------------------------------------------------------------
    # Helper functions
    # -------------------------------------------------------------------------
    @classmethod
    def get_organisations(cls, tablename="dvr_case_event"):
        """
            Looks up all organisations the user is permitted to register
            case events for

            Returns:
                Rows (org_organisation)
        """

        db = current.db
        s3db = current.s3db

        otable = s3db.org_organisation

        permissions = current.auth.permission
        permitted_realms = permissions.permitted_realms(tablename, "create")
        if permitted_realms is not None:
            query = (otable.pe_id.belongs(permitted_realms)) & \
                    (otable.deleted == False)
        else:
            query = (otable.deleted == False)

        rows = db(query).select(otable.id, otable.name)

        organisations = {row.id: row for row in rows}

        if len(rows) > 1:
            default = cls.get_default_organisation()
            if default and default in organisations:
                organisations["_default"] = default
        elif rows:
            organisations["_default"] = rows.first().id

        return organisations

    # -------------------------------------------------------------------------
    @classmethod
    def get_default_organisation(cls):
        """
            Determines the default organisation for the current user
                1) the organisation operating the site where the user is
                   currently reported present
                2) the organisation employing the user
                3) no default organisation (must choose)

            Returns:
                organisation record ID
        """

        person_id = current.auth.s3_logged_in_person()
        if not person_id:
            return None

        organisation_id = cls.get_current_site_org(person_id)
        if not organisation_id:
            organisation_id = cls.get_employer_org(person_id)

        return organisation_id

    # -------------------------------------------------------------------------
    @staticmethod
    def get_current_site_org(person_id):
        """
            Returns the organisation operating the site where the user
            is currently reported present

            Args:
                person_id: the person record ID

            Returns:
                organisation record ID
        """

        site_id = SitePresence.get_current_site(person_id)

        table = current.s3db.org_site
        query = (table.site_id == site_id)
        row = current.db(query).select(table.organisation_id,
                                       limitby = (0, 1),
                                       ).first()

        return row.organisation_id if row else None

    # -------------------------------------------------------------------------
    @staticmethod
    def get_employer_org(person_id):
        """
            Returns the organisation by which the user is currently employed

            Args:
                person_id: the person record ID

            Returns:
                organisation record ID
        """

        htable = current.s3db.hrm_human_resource

        query = (htable.person_id == person_id) & \
                (htable.status == 1) & \
                (htable.deleted == False)
        row = current.db(query).select(htable.organisation_id,
                                       orderby = ~htable.created_on,
                                       limitby = (0, 1),
                                       ).first()

        return row.organisation_id if row else None

    # -------------------------------------------------------------------------
    @classmethod
    def get_event_type(cls, code, organisation_id):
        """
            Looks up the event type during registration, enforces event class,
            active event types and required role; returns the default event
            type if no code is specified (i.e. None or "")

            Args:
                code: the event code
                organisation_id: the organisation ID

            Returns:
                Row
        """

        db = current.db
        s3db = current.s3db

        table = s3db.dvr_case_event_type
        if code:
            query = (table.code == code)
        else:
            query = (table.is_default == True)

        query &= (table.organisation_id == organisation_id) & \
                 (table.event_class == cls.EVENT_CLASS) & \
                 (table.is_inactive == False)

        # Roles required
        sr = current.auth.get_system_roles()
        roles = current.session.s3.roles
        if sr.ADMIN not in roles:
            query &= (table.role_required == None) | \
                     (table.role_required.belongs(roles))

        query &= (table.deleted == False)
        return db(query).select(table.id,
                                #table.name,
                                table.register_multiple,
                                limitby = (0, 1),
                                ).first()

    # -------------------------------------------------------------------------
    @classmethod
    def get_event_types(cls, organisation_id=None, type_filter=None):
        """
            Looks up all available event types for the organisation

            Args:
                organisation_id: the organisation record ID
                type_filter: a filter query for event type selection

            Returns:
                a dict {event_type_id: event_type_row}
        """

        db = current.db
        s3db = current.s3db

        table = s3db.dvr_case_event_type
        query = current.auth.s3_accessible_query("read", "dvr_case_event_type") & \
                (table.organisation_id == organisation_id) & \
                (table.is_inactive == False) & \
                (table.event_class == cls.EVENT_CLASS)
        if type_filter is not None:
            query &= type_filter

        # Roles required
        sr = current.auth.get_system_roles()
        roles = current.session.s3.roles
        if sr.ADMIN not in roles:
            query &= (table.role_required == None) | \
                     (table.role_required.belongs(roles))

        query &= (table.deleted == False)

        rows = db(query).select(table.id,
                                table.code,
                                table.name,
                                table.is_default,
                                table.min_interval,
                                table.max_per_day,
                                table.register_multiple,
                                table.residents_only,
                                #table.comments,
                                )
        event_types = {row.id: row for row in rows}
        for row in rows:
            if row.is_default or len(rows) == 1:
                event_types["_default"] = row.id
                break

        return event_types

    # -------------------------------------------------------------------------
    @staticmethod
    def check_residents_only(check, event_types):
        """
            Returns exclusion details for event types that can only be
            registered if the person is currently a resident of a shelter

            Args:
                check: the event types to check
                event_types: all event types to consider

            Returns: a dict with exclusion details
                     {event_type_id: (error_message, blocked_until_datetime, permit_others)}

            Note:
                When an event is blocked because the person whose ID is being used
                to register the event is not a resident, then it cannot be registered
                for any family member (that is, permit_others=False in this case)
        """

        msg = current.T("Not currently a resident")

        exclude = {}
        for type_id in check:
            event_type = event_types.get(type_id)
            if event_type and event_type.residents_only:
                exclude[type_id] = (msg, None, False)

        return exclude

    # -------------------------------------------------------------------------
    @staticmethod
    def check_non_combinable(person_id, check, day_start, event_types):
        """
            Returns exclusion details for event types that are not combinable
            with events already registered for the person on the given day

            Args:
                person_id: the person record ID
                check: the event types to check
                day_start: the start of the 24h persion to check
                event_types: all event types to consider

            Returns: a dict with exclusion details
                     {event_type_id: (error_message, blocked_until_datetime, permit_others)}
        """

        T = current.T
        db = current.db
        s3db = current.s3db

        etable = s3db.dvr_case_event
        xtable = s3db.dvr_case_event_exclusion

        event_type_ids = set(event_types.keys())
        event_type_ids.discard("_default")

        # Event type IDs that have been registered for the person today
        query = (etable.person_id == person_id) & \
                (etable.type_id.belongs(event_type_ids)) & \
                (etable.date >= day_start) & \
                (etable.deleted == False)
        registered_today = db(query)._select(etable.type_id, distinct=True)

        query = (xtable.type_id.belongs(check)) & \
                (xtable.excluded_by_id.belongs(registered_today)) & \
                (xtable.deleted == False)
        rows = db(query).select(xtable.type_id,
                                xtable.excluded_by_id,
                                )

        exclusions = {}
        for row in rows:
            type_id = row.type_id
            if type_id in exclusions:
                exclusions[type_id].add(row.excluded_by_id)
            else:
                exclusions[type_id] = {row.excluded_by_id}

        exclude = {}
        next_day = day_start + datetime.timedelta(days=1)
        for type_id, excluded_by in exclusions.items():
            names = ", ".join(s3_str(T(event_types[i].name)) for i in excluded_by)
            msg = T("%(event)s already registered today, not combinable") % \
                   {"event": names}
            exclude[type_id] = (msg, next_day, True)

        return exclude

    # -------------------------------------------------------------------------
    @staticmethod
    def check_max_per_day(person_id, check, day_start, event_types):
        """
            Returns exclusion details for event types for which the maximum
            number of registrations for a person has been reached on the
            given day

            Args:
                person_id: the person record ID
                check: the event types to check
                day_start: the start of the 24h persion to check
                event_types: all event types to consider

            Returns: a dict with exclusion details
                     {event_type_id: (error_message, blocked_until_datetime, permit_others)}
        """

        T = current.T
        db = current.db
        s3db = current.s3db

        etable = s3db.dvr_case_event
        ttable = s3db.dvr_case_event_type

        # Number of registrations for each event type where the
        # of registrations for the person is greater than max_per_day
        join = ttable.on((ttable.id == etable.type_id) & \
                         (ttable.max_per_day != None))
        query = (etable.person_id == person_id) & \
                (etable.type_id.belongs(check)) & \
                (etable.date >= day_start) & \
                (etable.deleted == False)
        count = etable.id.count()
        rows = db(query).select(ttable.id,
                                ttable.max_per_day,
                                count,
                                groupby = ttable.id,
                                having = (count >= ttable.max_per_day),
                                join = join,
                                )
        exclude = {}
        next_day = day_start + datetime.timedelta(days=1)
        for row in rows:
            number = row[count]
            type_id = row.dvr_case_event_type.id
            event_type = event_types[type_id]
            if number > 1:
                msg = T("%(event)s already registered %(number)s times today") % \
                       {"event": T(event_type.name), "number": number}
            else:
                msg = T("%(event)s already registered today") % \
                       {"event": T(event_type.name)}
            exclude[type_id] = (msg, next_day, True)

        return exclude

    # -------------------------------------------------------------------------
    @staticmethod
    def check_min_interval(person_id, check, now, event_types):
        """
            Returns exclusion details for event types for which the minimum
            interval between consecutive registrations for the same person
            has not been reached yet

            Args:
                person_id: the person record ID
                check: the event types to check
                now: the current date/time
                event_types: all event types to consider

            Returns: a dict with exclusion details
                     {event_type_id: (error_message, blocked_until_datetime, permit_others)}
        """

        T = current.T
        db = current.db
        s3db = current.s3db

        etable = s3db.dvr_case_event
        ttable = s3db.dvr_case_event_type

        # Last registration of types with a minimum interval
        join = ttable.on((ttable.id == etable.type_id) & \
                         (ttable.min_interval != None))
        query = (etable.person_id == person_id) & \
                (etable.type_id.belongs(check)) & \
                (etable.deleted == False)
        interval = ttable.min_interval.max()
        last_reg = etable.date.max()
        rows = db(query).select(ttable.id,
                                interval,
                                last_reg,
                                groupby = ttable.id,
                                join = join,
                                )

        exclude = {}
        represent = etable.date.represent
        for row in rows:
            type_id = row.dvr_case_event_type.id
            event_type = event_types[type_id]
            latest, hours = row[last_reg], row[interval]

            # Compute the earliest next registration time
            if latest and hours:
                earliest = latest + datetime.timedelta(hours=hours)
            else:
                # Either no previous registration or no waiting interval
                continue

            if earliest > now:
                msg = T("%(event)s already registered on %(timestamp)s") % \
                      {"event": T(event_type.name), "timestamp": represent(latest)}
                exclude[type_id] = (msg, earliest, True)

        return exclude

    # -------------------------------------------------------------------------
    @staticmethod
    def permitted(method, tablename, organisation_id=None):
        """
            Helper function to check permissions

            Returns:
                True if permitted to use this method, else False
        """

        auth = current.auth

        permitted = False

        if organisation_id:
            realms = auth.permission.permitted_realms(tablename, method=method)
            if realms:
                otable = current.s3db.org_organisation
                query = (otable.id == organisation_id) & \
                        (otable.pe_id.belongs(realms))
                if current.db(query).select(otable.id, limitby=(0, 1)).first():
                    return True
            elif realms is None:
                permitted = True
        else:
            permitted = auth.s3_has_permission(method, tablename)

        return permitted

    # -------------------------------------------------------------------------
    @staticmethod
    def inject_js(widget_id, options):
        """
            Injects required static JS and the instantiation if the
            eventRegistration widget

            Args:
                widget_id: the node ID of the <form> to instantiate
                           the eventRegistration widget on
                options: dict of widget options (JSON-serializable)
        """

        s3 = current.response.s3
        appname = current.request.application

        # Static JS
        scripts = s3.scripts
        if s3.debug:
            script = "/%s/static/scripts/S3/s3.ui.checkpoint.js" % appname
        else:
            script = "/%s/static/scripts/S3/s3.ui.checkpoint.min.js" % appname
        scripts.append(script)

        # Instantiate widget
        scripts = s3.jquery_ready
        script = '''$('#%(id)s').checkPoint(%(options)s)''' % \
                 {"id": widget_id, "options": json.dumps(options)}
        if script not in scripts:
            scripts.append(script)

# END =========================================================================

