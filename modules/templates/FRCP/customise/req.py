"""
    REQ module customisations for RLPPTM

    License: MIT
"""

from gluon import current, A, TAG, URL

from core import IS_FLOAT_AMOUNT, IS_ONE_OF, JSONERRORS, BasicCRUD, s3_str

from .org import add_org_tags

# -------------------------------------------------------------------------
def req_onvalidation(form):
    """
        Onvalidation of req:
            - prevent the situation that the site is changed in an
                existing request while it contains items not orderable
                by the new site
    """

    T = current.T
    form_vars = form.vars

    # Read form data
    form_vars = form.vars
    if "id" in form_vars:
        record_id = form_vars.id
    elif hasattr(form, "record_id"):
        record_id = form.record_id
    else:
        record_id = None

    db = current.db
    s3db = current.s3db

    if "site_id" in form_vars: # if site is selectable
        site_id = form_vars.site_id

        if "sub_defaultreq_item" in form_vars:
            # Items inline
            import json
            try:
                items = json.loads(form_vars.sub_defaultreq_item)
            except JSONERRORS:
                item_ids = []
            else:
                item_ids = [item["item_id"]["value"]
                            for item in items["data"] if not item.get("_delete")
                            ]
        elif record_id:
            # Items in database
            ritable = s3db.req_req_item
            query = (ritable.req_id == record_id) & \
                    (ritable.deleted == False)
            rows = db(query).select(ritable.item_id)
            item_ids = [row.item_id for row in rows]
        else:
            item_ids = []

        if item_ids:
            # Check if there are any items not in orderable categories
            from ..requests import get_orderable_item_categories
            categories = get_orderable_item_categories(site=site_id)

            itable = s3db.supply_item
            query = (itable.id.belongs(item_ids)) & \
                    (~(itable.item_category_id.belongs(categories)))
            row = db(query).select(itable.id, limitby = (0, 1)).first()
            if row:
                form.errors.site_id = T("Request contains items that cannot be ordered for this site")

# -------------------------------------------------------------------------
def req_req_resource(r, tablename):

    T = current.T
    s3db = current.s3db

    table = s3db.req_req

    field = table.req_ref
    field.label = T("Order No.")
    #field.represent = lambda v, row=None: v if v else "-"

    # Don't show facility type
    field = table.site_id
    field.represent = s3db.org_SiteRepresent(show_link = True,
                                             show_type = False,
                                             )

    if current.auth.s3_has_role("SUPPLY_COORDINATOR"):
        # Custom method to register a shipment
        from ..requests import RegisterShipment
        s3db.set_method("req_req",
                        method = "ship",
                        action = RegisterShipment,
                        )
        # Show contact details for requester
        field = table.requester_id
        field.represent = s3db.pr_PersonRepresentContact(show_email = True,
                                                         show_phone = True,
                                                         show_link = False,
                                                         styleable = True,
                                                         )
    else:
        # Simpler represent of requester, no link
        field = table.requester_id
        field.represent = s3db.pr_PersonRepresent(show_link = False)

    # Filter out obsolete items
    ritable = s3db.req_req_item
    sitable = s3db.supply_item
    field = ritable.item_id
    dbset = current.db((sitable.obsolete == False) | (sitable.obsolete == None))
    field.requires = IS_ONE_OF(dbset, "supply_item.id",
                               field.represent,
                               sort = True,
                               )

    # Customise error message for ordered quantity
    field = ritable.quantity
    field.requires = IS_FLOAT_AMOUNT(minimum = 1.0,
                                     error_message = T("Minimum quantity is %(min)s"),
                                     )

    # Custom label for Pack
    field = ritable.item_pack_id
    field.label = T("Order Unit")

# -------------------------------------------------------------------------
def req_req_controller(**attr):

    T = current.T
    db = current.db
    s3db = current.s3db
    auth = current.auth

    has_role = auth.s3_has_role

    s3 = current.response.s3

    # Custom prep
    standard_prep = s3.prep
    def prep(r):

        add_org_tags()

        r.get_vars["type"] = "1"

        is_supply_coordinator = has_role("SUPPLY_COORDINATOR")

        from ..requests import get_managed_requester_orgs, \
                               get_orderable_item_categories, \
                               req_filter_widgets

        # User must be either SUPPLY_COORDINATOR or ORG_ADMIN of a
        # requester organisation to access this controller
        if not is_supply_coordinator:
            requester_orgs = get_managed_requester_orgs(cache=False)
            if not requester_orgs:
                r.unauthorised()
        else:
            requester_orgs = None

        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        resource = r.resource
        table = resource.table

        ritable = s3db.req_req_item
        sitable = s3db.supply_item

        # Date is only writable for ADMIN
        field = table.date
        field.default = current.request.utcnow
        field.writable = has_role("AMDIN")

        record = r.record
        if record:
            # Check if there is any shipment for this request
            titable = s3db.inv_track_item
            join = titable.on((titable.req_item_id == ritable.id) & \
                              (titable.deleted == False))
            query = (ritable.req_id == r.id) & \
                    (ritable.deleted == False)
            item = db(query).select(titable.id, join=join, limitby=(0, 1)).first()

            if item:
                # Cannot edit the request
                resource.configure(editable=False, deletable=False)
                if r.component_name == "req_item":
                    # ...nor its items
                    r.component.configure(insertable = False,
                                          editable = False,
                                          deletable = False,
                                          )
        if not r.component:
            # Hide priority, date_required and date_recv
            field = table.priority
            field.readable = field.writable = False
            field = table.date_required
            field.readable = field.writable = False
            field = table.date_recv
            field.readable = field.writable = False

            if is_supply_coordinator:
                # Coordinators do not make requests
                resource.configure(insertable = False)

            else:
                # Limit to sites of managed requester organisations
                stable = s3db.org_site
                dbset = db((stable.organisation_id.belongs(requester_orgs)) & \
                           (stable.obsolete == False))
                field = table.site_id
                field.requires = IS_ONE_OF(dbset, "org_site.site_id",
                                           field.represent,
                                           )
                # If only one site selectable, set default and make r/o
                sites = dbset.select(stable.site_id, limitby=(0, 2))
                if len(sites) == 1:
                    field.default = sites.first().site_id
                    field.writable = False
                elif not sites:
                    resource.configure(insertable = False)
                else:
                    # User can order for more than one site
                    # => add custom callback to make sure all items in the request
                    #    are orderable for the site selected
                    s3db.add_custom_callback("req_req",
                                             "onvalidation",
                                             req_onvalidation,
                                             )

                # Filter selectable items to orderable categories
                categories = get_orderable_item_categories(orgs=requester_orgs)
                item_query = (sitable.item_category_id.belongs(categories)) & \
                              ((sitable.obsolete == False) | \
                               (sitable.obsolete == None))
                field = ritable.item_id
                field.requires = IS_ONE_OF(db(item_query), "supply_item.id",
                                           field.represent,
                                           sort = True,
                                           )

            # Requester is always the current user
            # => set as default and make r/o
            user_person_id = auth.s3_logged_in_person()
            if user_person_id:
                field = table.requester_id
                field.default = user_person_id
                field.writable = False

            if r.interactive:
                resource.configure(filter_widgets = req_filter_widgets(),
                                   )

            # Custom list fields
            list_fields = ["id",
                           "req_ref",
                           "date",
                           "site_id",
                           (T("Details"), "details"),
                           "transit_status",
                           "fulfil_status",
                           ]

            # Reconfigure table
            resource.configure(list_fields = list_fields,
                               )

            # Custom callback for inline items
            s3db.add_custom_callback("req_req_item",
                                     "onaccept",
                                     req_req_item_create_onaccept,
                                     method = "create",
                                     )

        elif r.component_name == "req_item" and record:

            # Filter selectable items to orderable categories
            categories = get_orderable_item_categories(site = record.site_id)
            item_query = (sitable.item_category_id.belongs(categories)) & \
                          ((sitable.obsolete == False) | \
                           (sitable.obsolete == None))
            field = ritable.item_id
            field.requires = IS_ONE_OF(db(item_query), "supply_item.id",
                                       field.represent,
                                       sort = True,
                                       )
        return result
    s3.prep = prep

    standard_postp = s3.postp
    def postp(r, output):

        # Call standard postp if on component tab
        if r.component and callable(standard_postp):
            output = standard_postp(r, output)

        resource = r.resource

        table = resource.table
        from s3db.req import REQ_STATUS_COMPLETE, REQ_STATUS_CANCEL
        request_complete = (REQ_STATUS_COMPLETE, REQ_STATUS_CANCEL)

        istable = s3db.inv_send

        from s3db.inv import SHIP_STATUS_IN_PROCESS, SHIP_STATUS_SENT
        shipment_in_process = (SHIP_STATUS_IN_PROCESS, SHIP_STATUS_SENT)

        record = r.record
        if r.interactive and isinstance(output, dict):

            # Add register-shipment action button(s)
            ritable = s3db.req_req_item

            ship_btn_label = s3_str(T("Register Shipment"))
            inject_script = False
            if record:
                # Single record view
                if not r.component and has_role("SUPPLY_COORDINATOR"):
                    query = (ritable.req_id == record.id) & \
                            (ritable.deleted == False)
                    item = db(query).select(ritable.id, limitby=(0, 1)).first()
                    if item and record.fulfil_status not in request_complete:
                        query = (istable.req_ref == record.req_ref) & \
                                (istable.status.belongs(shipment_in_process)) & \
                                (istable.deleted == False)
                        shipment = db(query).select(istable.id, limitby=(0, 1)).first()
                    else:
                        shipment = None
                    if item and not shipment:
                        from ..requests import is_active
                        site_active = is_active(record.site_id)
                    else:
                        site_active = True
                    if item and not shipment and site_active:
                        ship_btn = A(T("Register Shipment"),
                                     _class = "action-btn ship-btn",
                                     _db_id = str(record.id),
                                     )
                        inject_script = True
                    else:
                        warn = None
                        if not item:
                            warn = reason = T("Requests contains no items")
                        elif not site_active:
                            warn = reason = T("Requesting site no longer active")
                        else:
                            reason = T("Shipment already in process")
                        if warn:
                            current.response.warning = warn
                        ship_btn = A(T("Register Shipment"),
                                     _class = "action-btn",
                                     _disabled = "disabled",
                                     _title = reason,
                                     )
                    if "buttons" not in output:
                        buttons = output["buttons"] = {}
                    else:
                        buttons = output["buttons"]
                    delete_btn = buttons.get("delete_btn")

                    b = [delete_btn, ship_btn] if delete_btn else [ship_btn]
                    buttons["delete_btn"] = TAG[""](*b)

            elif not r.component and not r.method:
                # Datatable
                stable = s3db.org_site

                # Default action buttons (except delete)
                BasicCRUD.action_buttons(r, deletable =False)

                if has_role("SUPPLY_COORDINATOR"):
                    # Can only register shipments for unfulfilled requests with
                    # no shipment currently in process or in transit, and the
                    # requesting site still active, and at least one requested item
                    left = istable.on((istable.req_ref == table.req_ref) & \
                                      (istable.status.belongs(shipment_in_process)) & \
                                      (istable.deleted == False))
                    join = [stable.on((stable.site_id == table.site_id) & \
                                      (stable.obsolete == False)),
                            ritable.on((ritable.req_id == table.id) & \
                                       (ritable.deleted == False)),
                            ]
                    query = (table.fulfil_status != REQ_STATUS_COMPLETE) & \
                            (table.fulfil_status != REQ_STATUS_CANCEL) & \
                            (istable.id == None)
                    rows = db(query).select(table.id, groupby=table.id, join=join, left=left)
                    restrict = [str(row.id) for row in rows]

                    # Register-shipment button
                    enabled = {"label": ship_btn_label,
                               "_class": "action-btn ship-btn",
                               "restrict": restrict,
                               }
                    s3.actions.append(enabled)

                    # Disabled shipment-button to indicate why the action
                    # is currently disabled
                    disabled = {"label": ship_btn_label,
                                "_class": "action-btn",
                                "_title": s3_str(T("Shipment already in process, or not possible")),
                                "_disabled": "disabled",
                                "exclude": restrict,
                                }
                    s3.actions.append(disabled)

                    # Do inject script
                    inject_script = True

                if auth.s3_has_permission("delete", table):
                    # Requests can only be deleted while no shipment for them
                    # has been registered yet:
                    left = istable.on((istable.req_ref == table.req_ref) & \
                                      (istable.deleted == False))
                    query = auth.s3_accessible_query("delete", table) & \
                            (istable.id == None)
                    rows = db(query).select(table.id, left=left)

                    # Delete-button
                    if rows:
                        delete = {"label": s3_str(s3.crud_labels.DELETE),
                                  "url": URL(c="req", f="req", args=["[id]", "delete"]),
                                  "_class": "delete-btn",
                                  "restrict": [str(row.id) for row in rows],
                                  }
                        s3.actions.append(delete)

            if inject_script:
                # Confirmation question
                confirm = '''i18n.req_register_shipment="%s"''' % \
                            T("Do you want to register a shipment for this request?")
                s3.js_global.append(confirm)

                # Inject script for action
                script = "/%s/static/themes/RLP/js/ship.js" % r.application
                if script not in s3.scripts:
                    s3.scripts.append(script)

        return output
    s3.postp = postp

    from ..rheaders import rlpptm_req_rheader
    attr["rheader"] = rlpptm_req_rheader

    return attr

# -------------------------------------------------------------------------
def req_req_item_create_onaccept(form):
    """
        Custom callback to prevent duplicate request items:
        - if the same request contains another req_item with the same
            item_id and item_pack_id that is not yet referenced by a
            shipment item, then merge the quantities and delete this
            one
    """

    # Get record ID
    form_vars = form.vars
    if "id" in form_vars:
        record_id = form_vars.id
    elif hasattr(form, "record_id"):
        record_id = form.record_id
    else:
        return

    db = current.db
    s3db = current.s3db

    table = s3db.req_req_item
    titable = s3db.inv_track_item

    left = titable.on((titable.req_item_id == table.id) & \
                      (titable.deleted == False))

    query = (table.id == record_id)
    record = db(query).select(table.id,
                              table.req_id,
                              table.item_id,
                              table.item_pack_id,
                              table.quantity,
                              titable.id,
                              left = left,
                              limitby = (0, 1),
                              ).first()
    if record and not record.inv_track_item.id:
        this = record.req_req_item
        query = (table.req_id == this.req_id) & \
                (table.id != this.id) & \
                (table.item_id == this.item_id) & \
                (table.item_pack_id == this.item_pack_id) & \
                (titable.id == None)
        other = db(query).select(table.id,
                                 table.quantity,
                                 left = left,
                                 limitby = (0, 1),
                                 ).first()
        if other:
            resource = s3db.resource("req_req_item", id=this.id)
            deleted = resource.delete()
            if deleted:
                other.update_record(quantity = other.quantity + this.quantity)

# -------------------------------------------------------------------------
def req_req_item_resource(r, tablename):

    T = current.T
    s3db = current.s3db

    table = s3db.req_req_item

    quantities = ("quantity_transit",
                  "quantity_fulfil",
                  )
    for fn in quantities:
        field = table[fn]
        field.represent = lambda v: v if v is not None else "-"

    resource = r.resource
    if resource.tablename == "supply_item":
        from ..requests import ShipmentCodeRepresent
        rtable = s3db.req_req
        field = rtable.req_ref
        field.represent = ShipmentCodeRepresent("req_req", "req_ref")

        list_fields = ["item_id",
                       "req_id$req_ref",
                       "req_id$site_id",
                       "item_pack_id",
                       "quantity",
                       "quantity_transit",
                       "quantity_fulfil",
                       ]
        s3db.configure("req_req_item",
                       list_fields = list_fields,
                       insertable = False,
                       editable = False,
                       deletable = False,
                       )

    # Use drop-down for supply item, not autocomplete
    field = table.item_id
    field.widget = None

    # Custom label for Pack
    field = table.item_pack_id
    field.label = T("Order Unit")

    s3db.add_custom_callback("req_req_item",
                             "onaccept",
                             req_req_item_create_onaccept,
                             method = "create",
                             )

    if r.method == "report":
        axes = [(T("Orderer"), "req_id$site_id"),
                "req_id$site_id$location_id$L3",
                "req_id$site_id$location_id$L2",
                "req_id$site_id$location_id$L1",
                (T("Requested Items"), "item_id"),
                "req_id$transit_status",
                "req_id$fulfil_status",
                ]

        report_options = {
            "rows": axes,
            "cols": axes,
            "fact": [(T("Number of Requests"), "count(req_id)"),
                     (T("Number of Items"), "count(id)"),
                     (T("Requested Quantity"), "sum(quantity)"),
                     ],
            "defaults": {"rows": "req_id$site_id$location_id$L2",
                         "cols": None,
                         "fact": "count(req_id)",
                         "totals": True,
                         },
            }

        s3db.configure(tablename,
                       report_options = report_options,
                       )

# END =========================================================================
