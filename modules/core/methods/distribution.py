"""
    Distribution UI (SUPPLY)

    Copyright: 2024 (c) Sahana Software Foundation

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

__all__ = ("Distribution",
           )

import datetime
import json

from gluon import current, \
                  A, BUTTON, DIV, H4, \
                  SQLFORM, IS_LENGTH, IS_NOT_EMPTY

from s3dal import Field

from ..tools import FormKey, s3_str
from ..ui import S3QRInput

from .checkpoint import Checkpoint

# =============================================================================
class Distribution(Checkpoint):

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

        if representation == "json":
            if http == "GET":
                output = self.distribution_sets(r, **attr)
            elif http == "POST":
                output = self.check_or_register(r, **attr)
            else:
                r.error(405, current.ERROR.BAD_METHOD)
        elif representation == "html":
            if http == "GET":
                output = self.registration_form(r, **attr)
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
            Delivers the registration form

            Args:
                r: the CRUDRequest instance
                attr: controller parameters

            Returns:
                dict with view elements
        """

        if not current.auth.s3_has_permission("create", "supply_distribution"):
            r.unauthorised()

        T = current.T

        response = current.response
        settings = current.deployment_settings

        output = {}
        widget_id = "distribution-registration-form"

        # Add organisation selector
        organisations = self.get_organisations(tablename="supply_distribution") # {id: Row(id, name), _default: id}
        selector = self.organisation_selector(organisations, widget_id=widget_id)
        output.update(selector)

        # Default organisation_id
        organisation_id = organisations.get("_default") # Could be None

        # Distribution set selector
        distribution_sets = self.get_distribution_sets(organisation_id) # {id: Row(id, code, name), _default: id}, or None
        selector = self.distribution_set_selector(distribution_sets, widget_id=widget_id)
        output.update(selector)

        # Default distribution set
        default = distribution_sets.get("_default")
        if default:
            distribution_set = distribution_sets.get(default)
            #distribution_code = distribution_set.code if distribution_set else None
        else:
            distribution_set = None
            #distribution_code = None

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
                      ]

        data = {"id": "",
                "label": "",
                "person": "",
                "flaginfo": "",
                "details": "",
                }

        # Hidden fields to store distribution set, flag info and permission
        hidden = {"distset": distribution_set.id if distribution_set else None,
                  "actionable": None,
                  "permitted": None,
                  "flags": [],
                  "actions": None,
                  "image": None,
                  "_formkey": FormKey("distribution-registration").generate(),
                  }

        # Form buttons
        check_btn = BUTTON(T("Check ID"),
                           _class = "small secondary button check-btn",
                           _type = "button",
                           )
        submit_btn = BUTTON(T("Register"),
                            _class = "small primary button submit-btn hide",
                            _disabled = "disabled",
                            _type = "button",
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
        response.view = self._view(r, "supply/register_distribution.html")

        # Show profile picture by default or only on demand?
        show_picture = settings.get_ui_checkpoint_show_picture()

        # Inject JS
        options = {"ajaxURL": self.ajax_url(r),
                   "tablename": resourcename,
                   "showPicture": show_picture,
                   "showPictureLabel": s3_str(T("Show Picture")),
                   "hidePictureLabel": s3_str(T("Hide Picture")),
                   "selectDistributionSetLabel": s3_str(T("Please select a distribution item set")),
                   "noDistributionSetsLabel": s3_str(T("No distribution item sets available")),
                   "noItemsLabel": s3_str(T("Currently no items to process for this beneficiary")),
                   "distributeLabel": s3_str(T("Distribution")),
                   "returnLabel": s3_str(T("Return##distribution")),
                   "itemLabel": s3_str(T("Item")),
                   "quantityLabel": s3_str(T("Quantity")),
                   "packLabel": s3_str(T("Pack")),
                   "lossLabel": s3_str(T("Loss##distribution")),
                   "loanLabel": s3_str(T("Loan##distribution")),
                   }

        self.inject_js(widget_id, options)

        return output

    # -------------------------------------------------------------------------
    @classmethod
    def distribution_sets(cls, r, **attr):
        """
            Returns the distribution sets for the organisation specified
            by the URL query parameter "org" (=the organisation ID)

            Args:
                r: the CRUDRequest instance
                attr: controller parameters

            Returns:
                - a JSON object {"sets": [[id, name], ...],
                                 "default": [id, name],
                                 }
        """

        T = current.T

        organisation_id = r.get_vars.get("org")
        if organisation_id:
            # Get the event sets for the organisation
            distribution_sets = cls.get_distribution_sets(organisation_id)

            # Build the set list
            sets, default = [], None
            encode = lambda t: [t.id, s3_str(T(t.name))]
            for k, v in distribution_sets.items():
                if k == "_default":
                    default = encode(distribution_sets[v])
                else:
                    sets.append(encode(v))

            # Sort sets alphabetically by label
            output = {"sets": sorted(sets, key=lambda i: i[1])}
            if default:
                output["default"] = default
        else:
            output = {"sets": [], "default": None}

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

                     // Transaction details
                     "u": actionable info (e.g. which items to distribute/return)
                     "s": whether the action is permitted or not

                     // messages
                     "a": advice (for label field)
                     "e": error message
                     "w": warning message
                     "c": confirmation message
                     }

            Note:
                Request body is expected to contain a JSON-object like:
                    {"a": the action ("check"|"register")
                     "k": XSRF token
                     "l": the PE label
                     "o": the organisation ID
                     "t": the distribution set ID
                     "d": the distribution details (registration only):
                          => an object
                          {"d": [[item_id, pack_id, mode, quantity], ...],
                           "r": [[item_id, pack_id, mode, itemq, lostq], ...]
                           }
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
        formkey = FormKey("distribution-registration")
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

        # Identify the client
        label = json_data.get("l")
        person, label, advice, error = self.identify_client(label, organisation_id)
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
            if current.deployment_settings.get_supply_distribution_check_resident():
                is_resident, site_id = self.is_resident(person.id, organisation_id)
                if is_resident and site_id:
                    # Absence warning
                    from .presence import SitePresence
                    status = SitePresence.status(person.id, site_id=site_id)[0]
                    if status == "OUT":
                        warning = current.T("Person currently reported as absent")
                        output["w"] = s3_str(warning)
            else:
                is_resident = None

            # Flag instructions
            output["f"] = self.flag_instructions(person.id,
                                                 organisation_id = organisation_id,
                                                 )

            # Actionable items
            set_id = json_data.get("t")
            if set_id:
                distribution_sets = self.get_distribution_sets(organisation_id)
                distribution_set = distribution_sets.get(set_id)
                output["u"] = self.get_items(person.id,
                                             distribution_set,
                                             is_resident = is_resident,
                                             )

            output["s"] = True
        else:
            output["p"] = None
            output["s"] = False

        return output

    # -------------------------------------------------------------------------
    @classmethod
    def identify_client(cls, label, organisation_id):
        """
            Identifies the client from the ID label

            Args:
                label: the ID label
                organisation_id: the organisation ID

            Returns:
                a tuple (person Row, label, advice, error message)
        """

        validate = current.deployment_settings.get_org_site_presence_validate_id()
        if callable(validate):
            label, advice, error = validate(label)
            person = cls.get_person(label, organisation_id) if label else None
        else:
            advice, error = None, None
            person = cls.get_person(label, organisation_id)

        return person, label, advice, error

    # -------------------------------------------------------------------------
    def register(self, r, json_data):
        """
            Registers a distribution

            Args:
                r: the CRUDRequest
                json_data: the JSON data for the distribution, a dict:
                    {a: 'register',
                     k: formKey,
                     l: beneficiary ID label,
                     o: organisation ID,
                     t: distribution set ID,
                     d: {d: [distributed items],
                         r: [returned items]
                         },
                     }
                     ...with items being arrays of:
                     [item_id, pack_id, mode, item-quantity(, lost-quantity)]

            Returns:
                a dict {m: confirmation message}

            Raises:
                - HTTP404 for invalid IDs
                - HTTP400 for other syntax errors or invalid data
        """

        T = current.T

        # Determine the organisation
        organisation_id = json_data.get("o")
        if not organisation_id:
            r.error(400, current.ERROR.BAD_REQUEST)

        # Authorize the request
        if not self.permitted("create", "supply_distribution", organisation_id=organisation_id):
            r.unauthorised()
        try:
            # Note: staff_id could be None (for ADMINs)
            staff_id = self.get_staff_id(organisation_id)
        except ValueError:
            r.unauthorised()

        # Determine and verify the distribution set
        set_id = json_data.get("t")
        distribution_set = self.get_distribution_set(set_id, organisation_id=organisation_id)
        if not distribution_set:
            r.error(404, T("Invalid Distribution Item Set"))
        organisation_id = distribution_set.organisation_id

        # Identify the client
        label = json_data.get("l")
        person, label, _, error = self.identify_client(label, organisation_id)
        if not person:
            r.error(404, error or T("Invalid Beneficiary ID"))
        person_id = person.id

        # Get resident status and site of the client
        if current.deployment_settings.get_supply_distribution_check_resident():
            is_resident, site_id = self.is_resident(person.id, organisation_id)
        else:
            is_resident, site_id = None, None

        # Verify transaction details
        details = json_data.get("d")
        if not details:
            r.error(400, current.ERROR.BAD_REQUEST)
        items = []

        # Verify distributed items
        # - must be distributable, and of permitted quantity
        distributed = details.get("d")
        if distributed:
            distributable, msg = self.get_distributable_items(person_id,
                                                              distribution_set,
                                                              is_resident = is_resident,
                                                              )
            if not distributable:
                r.error(400, msg or current.ERROR.BAD_REQUEST)
            item_dict = {(i["id"], i["pack_id"], i["mode"]): i for i in distributable}
            for item in distributed:
                item, error = self.validate_item(item_dict, item)
                if error:
                    r.error(400, error)
                item_id, pack_id, mode, quantity = item
                items.append((item_id, pack_id, mode, quantity))

        # Verify returned items
        # - must be returnable, and of plausible quantity
        returned = details.get("r")
        if returned:
            returnable = self.get_returnable_items(person_id, distribution_set)
            if not returnable:
                r.error(400, current.ERROR.BAD_REQUEST)
            item_dict = {(i["id"], i["pack_id"], "RET"): i for i in returnable}
            for item in returned:
                item, error = self.validate_item(item_dict, item)
                if error:
                    r.error(400, error)
                item_id, pack_id, mode, itemq, lostq = item
                if itemq:
                    items.append((item_id, pack_id, mode, itemq))
                if lostq:
                    items.append((item_id, pack_id, "LOS", lostq))

        # Must not create empty distributions
        if not distributed and not returned:
            r.error(400, current.ERROR.BAD_REQUEST)

        # Create the distribution record
        self.register_distribution(person_id,
                                   distribution_set,
                                   items,
                                   site_id = site_id,
                                   staff_id = staff_id,
                                   )

        # Confirmation message
        return {"c": s3_str(T("Distribution registered"))}

    # -------------------------------------------------------------------------
    @staticmethod
    def register_distribution(person_id, distribution_set, items, site_id=None, staff_id=None):
        """
            Creates and post-processes distribution and distribution item
            records

            Args:
                person_id: the beneficiary person ID
                distribution_set: the suppyl_distribution_set Row
                items: list of distributed/returned items
                       [(item_id, pack_id, mode, quantity)]
                site_id: the site_id of the distribution site
                staff_id: the human_resource_id of the person in charge

            Returns:
                the record ID of the newly registered distribution

        """

        if not items:
            return None

        s3db = current.s3db
        auth = current.auth

        # Postprocess functions
        update_super = s3db.update_super
        set_record_owner = auth.s3_set_record_owner
        onaccept = s3db.onaccept
        audit = current.audit

        organisation_id = distribution_set.organisation_id
        set_id = distribution_set.id
        now = current.request.utcnow

        # Create distribution
        dtable = s3db.supply_distribution
        distribution = {"organisation_id": organisation_id,
                        "distribution_set_id": set_id,
                        "site_id": site_id,
                        "date": now,
                        "person_id": person_id,
                        "human_resource_id": staff_id,
                        }
        distribution["id"] = distribution_id = dtable.insert(**distribution)

        # Post-process create
        update_super(dtable, distribution)
        set_record_owner(dtable, distribution_id)
        onaccept(dtable, distribution, method="create")
        audit("create", "supply", "distribution",
              record = distribution_id,
              representation = "json"
              )

        # Add distributed/returned/lost items
        ditable = s3db.supply_distribution_item
        for item in items:
            item_id, pack_id, mode, quantity = item
            if not quantity:
                continue

            # Create item
            ditem = {"distribution_id": distribution_id,
                     "person_id": person_id,
                     "mode": mode,
                     "item_id": item_id,
                     "item_pack_id": pack_id,
                     "quantity": quantity,
                     }
            ditem["id"] = ditem_id = ditable.insert(**ditem)

            # Post-process create
            update_super(ditable, ditem)
            set_record_owner(ditable, ditem_id)
            onaccept(ditable, ditem, method="create")
            audit("create", "supply", "distribution_item",
                  record = ditem_id,
                  representation = "json",
                  )

        return distribution_id

    # -------------------------------------------------------------------------
    @staticmethod
    def validate_item(item_dict, item):
        """
            Validates a distributed/returned item against a distribution subset

            Args:
                item_dict: the distribution subset, a dict
                           {(item_id, pack_id, mode): {max: max-quantity}}
                item: a tuple (item_id, pack_id, mode, itemq, lostq)

            Returns:
                a tuple (item, error)
        """

        T = current.T
        INVALID_ITEM = T("Invalid Item")
        INVALID_QUANTITY = T("Invalid Quantity")

        # Verify Item
        try:
            item_id, pack_id, mode, itemq, lostq = (list(item) + [0])[:5]
        except (ValueError, TypeError):
            return None, INVALID_ITEM

        set_item = item_dict.get((item_id, pack_id, mode))
        if not set_item:
            return None, INVALID_ITEM

        # Verify Quantity
        if itemq is None:
            itemq = 0
        if lostq is None:
            lostq = 0
        try:
            itemq = int(itemq)
            lostq = int(lostq)
        except (ValueError, TypeError):
            return None, INVALID_QUANTITY

        max_quantity = set_item.get("max")
        if max_quantity is not None and itemq + lostq > max_quantity:
            return None, INVALID_QUANTITY

        return item, None

    # -------------------------------------------------------------------------
    # Widgets
    # - organisation_selector
    # - label_input
    # - ajax_url
    # -------------------------------------------------------------------------
    @staticmethod
    def distribution_set_selector(distribution_sets, widget_id=None):
        """
            Builds the distribution set selector

            Args:
                distribution_sets: all permitted distribution sets (dict as produced
                                    by get_distribution_sets())
                widget_id: the node ID of the registration form

            Returns:
                dict of view elements
        """

        T = current.T

        # Organisation selection buttons
        buttons = []
        default = None
        for k, v in distribution_sets.items():
            if k == "_default":
                default = v
            else:
                name = T(v.name)
                button = A(name,
                           _class = "secondary button event-type-select",
                           data = {"id": s3_str(v.id), "name": s3_str(name)},
                           )
                buttons.append(button)

        data = {}
        classes = ["event-type-header"]
        if buttons:
            if default:
                distribution_set = distribution_sets.get(default)
                name = T(distribution_set.name)
                data["id"] = distribution_set.id
                if len(buttons) == 1:
                    classes.append("disabled")
            else:
                name = T("Please select a distribution item set")
        else:
            name = T("No distribution item sets available")
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

        return {"distribution_set_header": header,
                "distribution_set_select": select,
                }

    # -------------------------------------------------------------------------
    # Lookup methods
    # - get_organisations
    # - get_default_organisation
    # - get_current_site_org
    # - get_employer_org
    # -------------------------------------------------------------------------
    @staticmethod
    def get_distribution_set(set_id, organisation_id):
        """
            Looks up the distribution set by its ID; as input verification
            during register().

            Args:
                set_id: the distribution set ID
                organisation_id: the organisation ID

            Returns:
                the distribution set Row
        """

        db = current.db
        s3db = current.s3db

        table = s3db.supply_distribution_set
        query = (table.id == set_id) & \
                (table.organisation_id == organisation_id) & \
                (table.active == True) & \
                (table.deleted == False)
        row = db(query).select(table.id,
                               table.organisation_id,
                               table.name,
                               table.max_per_day,
                               table.min_interval,
                               table.residents_only,
                               limitby = (0, 1),
                               ).first()
        return row

    # -------------------------------------------------------------------------
    @classmethod
    def get_distribution_sets(cls, organisation_id=None, set_filter=None):
        """
            Looks up all available distribution sets for the organisation

            Args:
                organisation_id: the organisation record ID
                set_filter: a filter query for distribution set selection

            Returns:
                a dict {id: row, ..., _default: id}
        """

        db = current.db
        s3db = current.s3db

        table = s3db.supply_distribution_set
        query = current.auth.s3_accessible_query("read", "supply_distribution_set") & \
                (table.organisation_id == organisation_id) & \
                (table.active == True)
        if set_filter is not None:
            query &= set_filter

        query &= (table.deleted == False)

        rows = db(query).select(table.id,
                                table.organisation_id,
                                table.name,
                                table.min_interval,
                                table.max_per_day,
                                table.residents_only,
                                )
        distribution_sets = {row.id: row for row in rows}
        if len(rows) == 1:
            distribution_sets["_default"] = rows.first().id

        return distribution_sets

    # -------------------------------------------------------------------------
    @classmethod
    def get_items(cls, person_id, distribution_set, is_resident=None):
        """
            Looks up all actionable items of the distribution set

            Args:
                person_id: the beneficiary person ID
                distribution_set: the supply_distribution_set Row
                is_resident: whether the client is a shelter resident (if known)

            Returns:
                a JSON-serializable dict like:
                    {"distribute": {"items": [{"mode": LOA|GRA,
                                               "id": item_id,
                                               "pack_id": pack_id,
                                               "name": item name,
                                               "pack": pack name,
                                               "quantity": default quantity,
                                               "max": maximum quantity,
                                               }, ...],
                                    "msg": error message (if not applicable),
                                    },
                     "return": [{"id": item_id,
                                 "pack_id": pack_id,
                                 "name": item name,
                                 "pack": pack name,
                                 "max": returnable quantity,
                                 }, ...]
                     }
        """

        output = {}

        # Look up distributable items
        items, msg = cls.get_distributable_items(person_id,
                                                 distribution_set,
                                                 is_resident = is_resident,
                                                 )
        output["distribute"] = {"items": items, "msg": s3_str(msg) if msg else None}

        # Look up returnable items
        items = cls.get_returnable_items(person_id, distribution_set)
        output["return"] = items

        return output

    # -------------------------------------------------------------------------
    @classmethod
    def get_distributable_items(cls, person_id, distribution_set, is_resident=None):
        """
            Returns the items and respective permissible quantities that
            can be distributed to the client at this point

            Args:
                person_id: the client person ID
                distribution_set: the distribution set Row
                is_resident: whether the client is a shelter resident (if known)

            Returns:
                a JSON-serializable list of dicts:
                [{"mode": the distribution mode GRA|LOA,
                  "id": supply_item ID,
                  "pack_id": supply_item_pack ID,
                  "name": item name,
                  "pack": pack name,
                  "quantity": default quantity,
                  "max": maximum permissible quantity,
                  }, ...]
        """

        db = current.db
        s3db = current.s3db

        # Determine the organisation_id of the distribution set
        set_id = distribution_set.id
        organisation_id = distribution_set.organisation_id

        # Check whether distribution is actionable for the client
        actionable, msg = cls.verify_actionable(person_id,
                                                distribution_set,
                                                is_resident = is_resident,
                                                )
        if actionable:
            itable = s3db.supply_item
            sitable = s3db.supply_distribution_set_item

            # Applicable catalogs
            ctable = s3db.supply_catalog
            query = (ctable.organisation_id == None)
            if organisation_id:
                query |= (ctable.organisation_id == organisation_id)
            query &= (ctable.active == True) & (ctable.deleted == False)
            catalogs = db(query)._select(ctable.id)

            # Items in applicable catalogs
            citable = s3db.supply_catalog_item
            query = (citable.catalog_id.belongs(catalogs)) & \
                    (citable.deleted == False)
            active_items = db(query)._select(citable.item_id, distinct=True)

            # Look up selectable items
            join = itable.on((itable.id == sitable.item_id) & \
                             (itable.obsolete == False))
            query = (sitable.distribution_set_id == set_id) & \
                    (sitable.item_id.belongs(active_items)) & \
                    (sitable.mode.belongs(("GRA", "LOA"))) & \
                    (sitable.deleted == False)
            rows = db(query).select(sitable.mode,
                                    sitable.item_id,
                                    sitable.item_pack_id,
                                    sitable.quantity,
                                    sitable.quantity_max,
                                    join = join,
                                    orderby = itable.name,
                                    )

            represent = sitable.item_id.represent
            item_repr = represent.bulk([row.item_id for row in rows], show_link=False)
            represent = sitable.item_pack_id.represent
            pack_repr = represent.bulk([row.item_pack_id for row in rows], show_link=False)

            distributable = []
            for row in rows:
                distributable.append({"mode": row.mode,
                                      "id": row.item_id,
                                      "pack_id": row.item_pack_id,
                                      "name": item_repr.get(row.item_id),
                                      "pack": pack_repr.get(row.item_pack_id),
                                      "quantity": row.quantity,
                                      "max": row.quantity_max
                                      })

            result = distributable, None

        else:
            # Not actionable at this time
            result = None, msg

        return result

    # -------------------------------------------------------------------------
    @staticmethod
    def get_returnable_items(person_id, distribution_set):
        """
            Returns the quantities of all items on loan which the client
            can return at this point

            Args:
                person_id: the client person ID
                distribution_set: the distribution set Row

            Returns:
                a JSON-serializable list of dicts:
                [{"id": supply_item ID,
                  "pack_id": supply_item_pack ID,
                  "name": item name,
                  "pack": pack name,
                  "max": returnable quantity,
                  }, ...]
        """

        db = current.db
        s3db = current.s3db

        set_id = distribution_set.id

        # Lookup returnable items for the distribution set
        itable = s3db.supply_item
        sitable = s3db.supply_distribution_set_item
        join = itable.on(itable.id == sitable.item_id)
        query = (sitable.distribution_set_id == set_id) & \
                (sitable.mode == "RET") & \
                (sitable.deleted == False)
        items = db(query).select(sitable.item_id,
                                 sitable.item_pack_id,
                                 join = join,
                                 orderby = itable.name,
                                 )
        item_ids = {i.item_id for i in items}

        # All distributions to this client by the organisation defining the set
        dtable = s3db.supply_distribution
        query = (dtable.person_id == person_id) & \
                (dtable.organisation_id == distribution_set.organisation_id) & \
                (dtable.deleted == False)
        distributions = db(query)._select(dtable.id)

        # Total quantities of these items loaned/returned by the client
        ditable = s3db.supply_distribution_item
        query = (ditable.distribution_id.belongs(distributions)) & \
                (ditable.item_id.belongs(item_ids)) & \
                (ditable.mode.belongs(("LOA", "RET", "LOS"))) & \
                (ditable.deleted == False)
        total_quantity = ditable.quantity.sum()
        rows = db(query).select(ditable.item_id,
                                ditable.item_pack_id,
                                ditable.mode,
                                total_quantity,
                                groupby = (ditable.item_id, ditable.item_pack_id, ditable.mode),
                                )

        # Calculate the total quantities remaining with the client
        totals = {}
        for row in rows:
            ditem = row.supply_distribution_item
            quantity = row[total_quantity]
            if ditem.mode != "LOA":
                quantity = quantity * -1
            key = (ditem.item_id, ditem.item_pack_id)
            totals[key] = totals.get(key, 0) + quantity

        # Build list of items+quantities the client could return
        represent = sitable.item_id.represent
        item_repr = represent.bulk([row.item_id for row in items], show_link=False)
        represent = sitable.item_pack_id.represent
        pack_repr = represent.bulk([row.item_pack_id for row in items], show_link=False)

        returnable = []
        for row in items:
            item_id, pack_id = row.item_id, row.item_pack_id
            remaining = totals.get((item_id, pack_id), 0)
            if remaining > 0:
                returnable.append({"id": item_id,
                                   "pack_id": pack_id,
                                   "name": item_repr.get(item_id),
                                   "pack": pack_repr.get(pack_id),
                                   "max": remaining
                                   })

        return returnable

    # -------------------------------------------------------------------------
    @staticmethod
    def get_staff_id(organisation_id):
        """
            Verifies that the current user is an active staff member of
            the organisation, and returns the staff record ID

            Args:
                organisation_id: the organisation record ID

            Returns:
                human_resource_id

            Raises:
                ValueError if the current user is not an active staff member
        """

        auth = current.auth

        person_id = auth.s3_logged_in_person()
        if person_id:
            hrtable = current.s3db.hrm_human_resource
            query = (hrtable.person_id == person_id) & \
                    (hrtable.organisation_id == organisation_id) & \
                    (hrtable.status == 1) & \
                    (hrtable.deleted == False)
            row = current.db(query).select(hrtable.id, limitby=(0, 1)).first()
        else:
            row = None

        if not row:
            if auth.s3_has_role("ADMIN"):
                return None
            raise ValueError("not an active staff member")

        return row.id

    # -------------------------------------------------------------------------
    # Helper functions
    # -------------------------------------------------------------------------
    @classmethod
    def verify_actionable(cls, person_id, distribution_set, is_resident=None):

        settings = current.deployment_settings
        now = current.request.utcnow

        actionable = True

        # Check whether the client is currently a resident
        check_resident = settings.get_supply_distribution_check_resident()
        if check_resident and distribution_set.residents_only:
            if is_resident is None:
                is_resident = cls.is_resident(person_id, distribution_set.organisation_id)[0]
            if not is_resident:
                actionable, msg = False, current.T("Not currently a resident")

        # Check whether distribution is permissible for the client
        if actionable:
            check_flags = settings.get_supply_distribution_check_case_flags()
            if check_flags:
                actionable, msg = cls.verify_flags(person_id, distribution_set)
        if actionable:
            actionable, msg = cls.verify_min_interval(person_id, distribution_set, now)
        if actionable:
            actionable, msg = cls.verify_max_per_day(person_id, distribution_set, now)

        return actionable, msg

    # -------------------------------------------------------------------------
    @staticmethod
    def verify_flags(person_id, distribution_set):
        """
            Checks whether the given distribution set is currently
            blocked due to case flags

            Args:
                person_id: the client person ID
                distribution_set: the distribution set Row

            Returns:
                tuple (actionable, message)
        """

        db = current.db
        s3db = current.s3db

        set_id = distribution_set.id
        actionable = True

        # All current case flags for the client
        ftable = s3db.dvr_case_flag_case
        query = (ftable.person_id == person_id) & \
                (ftable.deleted == False)
        current_flags = db(query)._select(ftable.flag_id)

        # Check for debarring flags
        if actionable:
            dftable = s3db.dvr_distribution_flag_debarring
            query = (dftable.distribution_set_id == set_id) & \
                    (dftable.flag_id.belongs(current_flags)) & \
                    (dftable.deleted == False)
            row = db(query).select(dftable.flag_id, limitby=(0, 1)).first()
            if row:
                actionable = False

        # Check for required flags
        if actionable:
            rftable = s3db.dvr_distribution_flag_required
            query = (rftable.distribution_set_id == set_id) & \
                    (~(rftable.flag_id.belongs(current_flags))) & \
                    (rftable.deleted == False)
            row = db(query).select(rftable.flag_id, limitby=(0, 1)).first()
            if row:
                actionable = False

        if not actionable:
            msg = current.T('Distribution of "%(set)s" currently not permitted for this beneficiary') % \
                  {"set": distribution_set.name}
        else:
            msg = None

        return (actionable, msg)

    # -------------------------------------------------------------------------
    @staticmethod
    def verify_min_interval(person_id, distribution_set, now):
        """
            Checks whether the given distribution set is currently blocked
            due to a mandatory waiting interval

            Args:
                person_id: the client person ID
                distribution_set: the distribution set Row
                now: the current date/time

            Returns:
                tuple (actionable, message)
        """

        T = current.T

        db = current.db
        s3db = current.s3db

        set_id = distribution_set.id
        min_interval = distribution_set.min_interval

        result = (True, None)

        if min_interval:

            dtable = s3db.supply_distribution

            # Get the date/time of the last distribution of this set
            # that is less than min_interval hours past
            start = now - datetime.timedelta(hours=min_interval)
            query = (dtable.distribution_set_id == set_id) & \
                    (dtable.person_id == person_id) & \
                    (dtable.date > start) & \
                    (dtable.date <= now) & \
                    (dtable.deleted == False)
            maxdate = dtable.date.max()
            row = db(query).select(maxdate).first()

            # If there was a distribution within that interval,
            # report as not actionable
            latest = row[maxdate]
            if latest:
                represent = dtable.date.represent
                msg = T('Distribution of "%(set)s" already registered on %(timestamp)s') % \
                      {"set": T(distribution_set.name), "timestamp": represent(latest)}
                result = (False, msg)

        return result

    # -------------------------------------------------------------------------
    @staticmethod
    def verify_max_per_day(person_id, distribution_set, now):
        """
            Checks whether the given distribution set is currently blocked
            because a maximum number of distributions per day has been reached

            Args:
                person_id: the client person ID
                distribution_set: the distribution set Row
                now: the current date/time

            Returns:
                tuple (actionable, message)
        """

        T = current.T

        db = current.db
        s3db = current.s3db

        set_id = distribution_set.id
        max_per_day = distribution_set.max_per_day

        result = (True, None)

        if max_per_day:

            dtable = s3db.supply_distribution
            ditable = s3db.supply_distribution_item

            # Only count distributions with distributed items
            join = ditable.on((ditable.distribution_id == dtable.id) & \
                              (ditable.mode.belongs(("LOA", "GRA"))) & \
                              (ditable.deleted == False))

            # Get the number of distributions of this set today
            start = now.replace(hour=0, minute=0, second=0)
            end = start + datetime.timedelta(days=1)
            query = (dtable.distribution_set_id == set_id) & \
                    (dtable.person_id == person_id) & \
                    (dtable.date >= start) & \
                    (dtable.date < end) & \
                    (dtable.deleted == False)
            cnt = dtable.id.count(distinct=True)
            number = db(query).select(cnt, join=join).first()[cnt]

            # If maximum has been reached, report as not actionable
            if number >= max_per_day:
                if number > 1:
                    msg = T('Distribution of "%(set)s" already registered %(number)s times today') % \
                          {"set": T(distribution_set.name), "number": number}
                else:
                    msg = T('Distribution of "%(set)s" already registered today') % \
                          {"set": T(distribution_set.name)}
                result = (False, msg)

        return result

    # -------------------------------------------------------------------------
    @staticmethod
    def inject_js(widget_id, options):
        """
            Injects required static JS and the instantiation if the
            registerDistribution widget

            Args:
                widget_id: the node ID of the <form> to instantiate
                           the registerDistribution widget on
                options: dict of widget options (JSON-serializable)
        """

        s3 = current.response.s3
        appname = current.request.application

        # Static JS
        scripts = s3.scripts
        if s3.debug:
            script = "/%s/static/scripts/S3/s3.ui.distribution.js" % appname
        else:
            script = "/%s/static/scripts/S3/s3.ui.distribution.min.js" % appname
        scripts.append(script)

        # Instantiate widget
        scripts = s3.jquery_ready
        script = '''$('#%(id)s').registerDistribution(%(options)s)''' % \
                 {"id": widget_id, "options": json.dumps(options)}
        if script not in scripts:
            scripts.append(script)

# END =========================================================================
