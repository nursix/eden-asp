"""
    INV module customisations for RLPPTM

    License: MIT
"""

from gluon import current, DIV

from core import ICON, IS_FLOAT_AMOUNT, IS_ONE_OF, S3Represent

from .org import add_org_tags

# -------------------------------------------------------------------------
def inv_recv_resource(r, tablename):

    T = current.T
    s3db = current.s3db

    table = s3db.inv_recv

    # Custom label for req_ref
    from ..requests import ShipmentCodeRepresent
    field = table.req_ref
    field.label = T("Order No.")
    field.represent = ShipmentCodeRepresent("req_req", "req_ref")

    # We don't use send_ref
    #field = table.send_ref
    #field.represent = lambda v, row=None: B(v if v else "-")

    # Don't show type in site representation
    field = table.site_id
    field.represent = s3db.org_SiteRepresent(show_link = True,
                                             show_type = False,
                                             )

    # Custom label for from_site_id, don't show link or type
    field = table.from_site_id
    field.label = T("Distribution Center")
    field.readable = True
    field.writable = False
    field.represent = s3db.org_SiteRepresent(show_link = False,
                                             show_type = False,
                                             )

    # Color-coded status representation
    from core import S3PriorityRepresent
    field = table.status
    status_opts = s3db.inv_ship_status
    from s3db.inv import inv_shipment_status_labels
    status_labels = inv_shipment_status_labels()
    field.represent = S3PriorityRepresent(status_labels,
                                          {status_opts["IN_PROCESS"]: "lightblue",
                                           status_opts["RECEIVED"]: "green",
                                           status_opts["SENT"]: "amber",
                                           status_opts["CANCEL"]: "black",
                                           status_opts["RETURNING"]: "red",
                                           }).represent

    if r.tablename == "inv_recv" and not r.component:
        if r.interactive:
            from core import CustomForm
            crud_fields = ["req_ref",
                           #"send_ref",
                           "site_id",
                           "from_site_id",
                           "status",
                           "recipient_id",
                           "date",
                           "comments",
                           ]
            s3db.configure("inv_recv",
                           crud_form = CustomForm(*crud_fields),
                           )

        list_fields = ["req_ref",
                       #"send_ref",
                       "site_id",
                       "from_site_id",
                       "date",
                       "status",
                       ]

        s3db.configure("inv_recv",
                       list_fields = list_fields,
                       )

# -------------------------------------------------------------------------
def inv_recv_controller(**attr):

    db = current.db

    auth = current.auth
    s3db = current.s3db

    s3 = current.response.s3

    # Custom prep
    standard_prep = s3.prep
    def prep(r):
        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        resource = r.resource
        table = resource.table

        component = r.component

        if not component:
            # Hide unused fields
            unused = ("type",
                      "organisation_id",
                      "purchase_ref",
                      "recv_ref",
                      )
            for fn in unused:
                field = table[fn]
                field.readable = field.writable = False

            field = table.recipient_id
            field.widget = None
            record = r.record
            if record and record.recipient_id:
                accepted_recipients = {record.recipient_id}
            else:
                accepted_recipients = set()
            user_person_id = auth.s3_logged_in_person()
            if user_person_id:
                field.default = user_person_id
                accepted_recipients.add(user_person_id)
            dbset = db(s3db.pr_person.id.belongs(accepted_recipients))
            field.requires = IS_ONE_OF(dbset, "pr_person.id", field.represent)

            if r.interactive:
                from ..requests import recv_filter_widgets
                resource.configure(filter_widgets = recv_filter_widgets())

        elif component.tablename == "inv_track_item":

            itable = component.table

            field = itable.item_id
            field.writable = False

            # Use custom form
            from core import CustomForm
            crud_fields = ["item_id",
                           "item_pack_id",
                           "quantity",
                           "recv_quantity"
                           ]

            # Custom list fields
            list_fields = ["item_id",
                           "item_pack_id",
                           "quantity",
                           "recv_quantity",
                           "status",
                           ]

            component.configure(crud_form = CustomForm(*crud_fields),
                                list_fields = list_fields,
                                )
        return result
    s3.prep = prep

    from ..rheaders import rlpptm_inv_rheader
    attr["rheader"] = rlpptm_inv_rheader

    return attr

# -------------------------------------------------------------------------
def inv_send_resource(r, tablename):

    T = current.T
    db = current.db
    s3db = current.s3db

    table = s3db.inv_send

    from ..requests import ShipmentCodeRepresent

    # Custom representation of req_ref
    field = table.req_ref
    field.label = T("Order No.")
    if r.representation == "wws":
        field.represent = lambda v, row=None: v if v else "-"
    else:
        field.represent = ShipmentCodeRepresent("req_req", "req_ref")

    # Sending site is required, must not be obsolete, +custom label
    field = table.site_id
    field.label = T("Distribution Center")
    field.requires = IS_ONE_OF(db, "org_site.site_id",
                               field.represent,
                               instance_types = ("inv_warehouse",),
                               not_filterby = "obsolete",
                               not_filter_opts = (True,),
                               )
    field.represent = s3db.org_SiteRepresent(show_link = False,
                                             show_type = False,
                                             )

    # Recipient site is required, must be org_facility
    field = table.to_site_id
    field.requires = IS_ONE_OF(db, "org_site.site_id",
                               field.represent,
                               instance_types = ("org_facility",),
                               sort = True,
                               )
    field.represent = s3db.org_SiteRepresent(show_link = True,
                                             show_type = False,
                                             )

    # Color-coded status representation
    from core import S3PriorityRepresent
    field = table.status
    status_opts = s3db.inv_ship_status
    from s3db.inv import inv_shipment_status_labels
    status_labels = inv_shipment_status_labels()
    field.represent = S3PriorityRepresent(status_labels,
                                          {status_opts["IN_PROCESS"]: "lightblue",
                                           status_opts["RECEIVED"]: "green",
                                           status_opts["SENT"]: "amber",
                                           status_opts["CANCEL"]: "black",
                                           status_opts["RETURNING"]: "red",
                                           }).represent

    # We don't use send_ref
    field = table.send_ref
    field.readable = field.writable = False
    #field.represent = ShipmentCodeRepresent("inv_send", "send_ref",
    #                                        show_link = False,
    #                                        )

    list_fields = ["id",
                   "req_ref",
                   #"send_ref",
                   "date",
                   "site_id",
                   "to_site_id",
                   "status",
                   ]

    s3db.configure("inv_send",
                   list_fields = list_fields,
                   )

    # Do not check for site_id (unused)
    s3db.clear_config("inv_send", "onvalidation")


# -------------------------------------------------------------------------
def inv_send_controller(**attr):

    T = current.T
    db = current.db

    auth = current.auth
    s3db = current.s3db

    s3 = current.response.s3

    # Custom prep
    standard_prep = s3.prep
    def prep(r):
        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        add_org_tags()

        resource = r.resource
        table = resource.table

        record = r.record
        component = r.component

        if r.method == "report":
            s3.crud_strings[resource.tablename].title_report = T("Shipments Statistics")

        if not component:

            # Hide unused fields
            unused = (#"site_id",
                      "organisation_id",
                      "type",
                      "driver_name",
                      "driver_phone",
                      "vehicle_plate_no",
                      "time_out",
                      "delivery_date",
                      )
            for fn in unused:
                field = table[fn]
                field.readable = field.writable = False

            # Shipment reference must be editable while the shipment
            # is still editable (but we don't use send_ref at all currently)
            field.readable = field.writable = False
            #field = table.send_ref
            #field.readable = field.writable = True
            #field.requires = IS_NOT_ONE_OF(db, "inv_send.send_ref",
            #                               error_message = T("Specify a unique reference number"),
            #                               )

            # Request number, on the other hand, should not be editable
            field = table.req_ref
            field.readable = bool(record)
            field.writable = False

            # Sender is always the current user
            # => allow editing only if sender_id is missing
            field = table.sender_id
            field.widget = None
            record = r.record
            if record and record.sender_id:
                accepted_senders = {record.sender_id}
            else:
                accepted_senders = set()
            user_person_id = auth.s3_logged_in_person()
            if user_person_id:
                field.default = user_person_id
                accepted_senders.add(user_person_id)
            dbset = db(s3db.pr_person.id.belongs(accepted_senders))
            field.requires = IS_ONE_OF(dbset, "pr_person.id", field.represent)

            # Recipient should already have been set from request
            # => allow editing only that hasn't happened yet
            field = table.recipient_id
            # TODO allow editing but look up acceptable recipients
            #      from organisation of the receiving site
            field.writable = False
            field.readable = record and record.recipient_id
            field.widget = None

            if r.interactive:
                from ..requests import send_filter_widgets
                resource.configure(filter_widgets = send_filter_widgets())

        elif component.tablename == "inv_track_item":

            itable = component.table

            field = itable.item_id
            field.readable = field.writable = True

            if r.component_id:
                # If this item is linked to a request item, don't allow
                # to switch to another supply item
                query = (itable.id == r.component_id)
                item = db(query).select(itable.req_item_id,
                                        limitby = (0, 1),
                                        ).first()
                if item and item.req_item_id:
                    field.writable = False

                # ...however, the item quantity can still be adjusted
                # => override IS_AVAILABLE_QUANTITY here as we don't
                #    have an inventory item to check against
                field = itable.quantity
                field.requires = IS_FLOAT_AMOUNT(0)

            # Use custom form
            from core import CustomForm
            crud_fields = ["item_id",
                           "item_pack_id",
                           "quantity",
                           ]

            # Custom list fields
            list_fields = ["item_id",
                           "item_pack_id",
                           "quantity",
                           "recv_quantity",
                           "status",
                           ]

            component.configure(crud_form = CustomForm(*crud_fields),
                                list_fields = list_fields,
                                )

        if r.interactive and not record and auth.s3_has_role("SUPPLY_COORDINATOR"):
            # Configure WWS export format
            settings = current.deployment_settings
            export_formats = list(settings.get_ui_export_formats())
            export_formats.append(("wws", "fa fa-shopping-cart", T("CoronaWWS")))
            s3.formats["wws"] = r.url(method="", vars={"mcomponents": "track_item"})
            settings.ui.export_formats = export_formats

        return result
    s3.prep = prep

    standard_postp = s3.postp
    def postp(r, output):

        # Call standard postp if on component tab
        if r.component and callable(standard_postp):
            output = standard_postp(r, output)

        if r.representation == "wws":
            # Deliver as attachment rather than as page content
            from gluon.contenttype import contenttype

            now = current.request.utcnow.strftime("%Y%m%d%H%M%S")
            filename = "ship%s.wws" % now
            disposition = "attachment; filename=\"%s\"" % filename

            response = current.response
            response.headers["Content-Type"] = contenttype(".xml")
            response.headers["Content-disposition"] = disposition

        return output
    s3.postp = postp

    from ..rheaders import rlpptm_inv_rheader
    attr["rheader"] = rlpptm_inv_rheader

    return attr


# -------------------------------------------------------------------------
def inv_track_item_onaccept(form):
    """
        Custom-onaccept for inv_track_item
        - based on standard inv_track_item_onaccept, but without the
            stock item updates and adjustments
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

    # Look up the track item record if not in form
    ttable = s3db.inv_track_item
    try:
        record = form.record
    except AttributeError:
        record = None
    if not record:
        record = db(ttable.id == record_id).select(ttable.id,
                                                   ttable.status,
                                                   ttable.req_item_id,
                                                   ttable.recv_quantity,
                                                   ttable.item_pack_id,
                                                   limitby = (0, 1),
                                                   ).first()
    if not record:
        return

    # Set send_ref in recv_record
    send_id = form_vars.get("send_id")
    recv_id = form_vars.get("recv_id")
    recv_update = {}

    if send_id and recv_id:
        # Get the send_ref
        stable = s3db.inv_send
        send = db(stable.id == send_id).select(stable.send_ref,
                                               limitby = (0, 1)
                                               ).first().send_ref
        # Note the send_ref for recv-update (we do that later)
        recv_update["send_ref"] = send.send_ref

    # Update the request
    rrtable = s3db.req_req
    ritable = s3db.req_req_item
    iptable = db.supply_item_pack

    # If this item is linked to a request, then copy the req_ref to the send item
    req_item_id = record.req_item_id
    req = req_item = None
    if req_item_id:

        # Look up the request item
        left = rrtable.on(rrtable.id == ritable.req_id)
        row = db(ritable.id == req_item_id).select(ritable.id,
                                                   ritable.quantity_fulfil,
                                                   ritable.item_pack_id,
                                                   rrtable.id,
                                                   rrtable.req_ref,
                                                   left = left,
                                                   limitby = (0, 1),
                                                   ).first()
        if row:
            req = row.req_req
            req_item = row.req_req_item
            recv_update["req_ref"] = req.req_ref

    # Update the recv-record with send and req references
    if recv_id and recv_update:
        rtable = s3db.inv_recv
        db(rtable.id == recv_id).update(**recv_update)

    # When item status is UNLOADING, update the request
    from s3db.inv import TRACK_STATUS_UNLOADING, TRACK_STATUS_ARRIVED
    recv_quantity = record.recv_quantity
    if record.status == TRACK_STATUS_UNLOADING:

        if req_item and recv_quantity:
            # Update the fulfilled quantity of the req item
            req_pack_id = req_item.item_pack_id
            rcv_pack_id = record.item_pack_id
            query = iptable.id.belongs((req_pack_id, rcv_pack_id))
            packs = db(query).select(iptable.id,
                                     iptable.quantity,
                                     limitby = (0, 2),
                                     ).as_dict(key="id")
            req_pack_quantity = packs.get(req_pack_id)
            rcv_pack_quantity = packs.get(rcv_pack_id)

            if req_pack_quantity and rcv_pack_quantity:
                quantity_fulfil = s3db.supply_item_add(req_item.quantity_fulfil,
                                                       req_pack_quantity,
                                                       recv_quantity,
                                                       rcv_pack_quantity,
                                                       )
                req_item.update_record(quantity_fulfil = quantity_fulfil)

            # Update the request status
            s3db.req_update_status(req.id)

        # Update the track item status to ARRIVED
        db(ttable.id == record_id).update(status = TRACK_STATUS_ARRIVED)

# -------------------------------------------------------------------------
def inv_track_item_resource(r, tablename):

    T = current.T
    s3db = current.s3db

    table = s3db.inv_track_item

    # Item selector using dropdown not autocomplete
    field = table.item_id
    field.widget = None
    field.comment = None

    field = table.send_id
    field.label = T("Shipment")
    field.represent = S3Represent(lookup = "inv_send",
                                  fields = ["req_ref"],
                                  #fields = ["send_ref"], # we don't use send_ref
                                  show_link = True,
                                  )

    # Custom label for Pack
    field = table.item_pack_id
    field.label = T("Order Unit")

    # Custom list fields
    resource = r.resource
    if resource.tablename == "supply_item":

        # Custom form for record view (read-only)
        field = table.recv_quantity
        field.readable = True
        from core import CustomForm
        crud_form = CustomForm("item_id",
                               "send_id",
                               "item_pack_id",
                               "quantity",
                               "recv_quantity",
                               "status",
                               )

        # List fields
        list_fields = ["item_id",
                       "send_id",
                       "send_id$date",
                       "send_id$to_site_id",
                       "item_pack_id",
                       "quantity",
                       "recv_quantity",
                       "status",
                       ]

        # Reconfigure - always r/o in this view
        s3db.configure("inv_track_item",
                       crud_form = crud_form,
                       list_fields = list_fields,
                       insertable = False,
                       editable = False,
                       deletable = False,
                       )

    if r.method == "report":
        axes = [(T("Orderer"), "send_id$to_site_id"),
                "send_id$to_site_id$location_id$L3",
                "send_id$to_site_id$location_id$L2",
                "send_id$to_site_id$location_id$L1",
                (T("Shipment Items"), "item_id"),
                (T("Distribution Center"), "send_id$site_id"),
                "send_id$status",
                ]

        report_options = {
            "rows": axes,
            "cols": axes,
            "fact": [(T("Number of Shipments"), "count(send_id)"),
                     (T("Number of Items"), "count(id)"),
                     (T("Sent Quantity"), "sum(quantity)"),
                     ],
            "defaults": {"rows": "item_id",
                         "cols": "send_id$status",
                         "fact": "sum(quantity)",
                         "totals": True,
                         },
            }
        s3db.configure("inv_track_item",
                       report_options = report_options,
                       )

    # Override standard-onaccept to prevent inventory updates
    s3db.configure("inv_track_item",
                   onaccept = inv_track_item_onaccept,
                   )

# -------------------------------------------------------------------------
def warehouse_tag_onaccept(form):
    """
        Onaccept of site tags for warehouses:
            - make sure only one warehouse has the CENTRAL=Y tag
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
    table = current.s3db.org_site_tag

    tag = form_vars.get("tag")
    if not tag and record_id:
        record = db(table.id == record_id).select(table.id,
                                                  table.tag,
                                                  limitby = (0, 1),
                                                  ).first()
        tag = record.tag if record else None

    value = form_vars.get("value")
    site_id = form_vars.get("site_id")

    if site_id and tag == "CENTRAL" and value == "Y":
        query = (table.site_id != site_id) & \
                (table.tag == "CENTRAL") & \
                (table.value == "Y")
        db(query).update(value = "N")

# -------------------------------------------------------------------------
def inv_warehouse_resource(r, tablename):

    T = current.T

    s3db = current.s3db

    table = s3db.inv_warehouse

    # Remove Add-links for organisation and warehouse type
    field = table.organisation_id
    field.comment = None
    field = table.warehouse_type_id
    field.comment = None

    # Add CENTRAL-tag as component
    s3db.add_components("org_site",
                        org_site_tag = ({"name": "central",
                                         "joinby": "site_id",
                                         "filterby": {"tag": "CENTRAL"},
                                         "multiple": False,
                                         },
                                        ),
                        )

    # Custom callback to ensure that there is only one with CENTRAL=Y
    s3db.add_custom_callback("org_site_tag",
                             "onaccept",
                             warehouse_tag_onaccept,
                             )

    # Custom label, represent and tooltip for obsolete-flag
    field = table.obsolete
    field.readable = field.writable = True
    field.label = T("Defunct")
    field.represent = lambda v, row=None: ICON("remove") if v else ""
    field.comment = DIV(_class="tooltip",
                        _title="%s|%s" % (T("Defunct"),
                                          T("Please mark this field when the facility is no longer in operation"),
                                          ),
                        )

    if r.interactive:

        # Configure location selector and geocoder
        from core import LocationSelector
        field = table.location_id
        field.widget = LocationSelector(levels = ("L1", "L2", "L3", "L4"),
                                        required_levels = ("L1", "L2", "L3"),
                                        show_address = True,
                                        show_postcode = True,
                                        show_map = True,
                                        )
        current.response.s3.scripts.append("/%s/static/themes/RLP/js/geocoderPlugin.js" % r.application)

        # Custom CRUD-Form
        from core import CustomForm
        crud_fields = ["organisation_id",
                       "name",
                       "code",
                       "warehouse_type_id",
                       (T("Central Warehouse"), "central.value"),
                       "location_id",
                       "email",
                       "phone1",
                       "phone2",
                       "comments",
                       "obsolete",
                       ]

        s3db.configure("inv_warehouse",
                       crud_form = CustomForm(*crud_fields),
                       )

    # Custom list fields
    list_fields = ["organisation_id",
                   "name",
                   "code",
                   "warehouse_type_id",
                   (T("Central Warehouse"), "central.value"),
                   "location_id",
                   "email",
                   "phone1",
                   "obsolete",
                   ]
    s3db.configure("inv_warehouse",
                   list_fields = list_fields,
                   deletable = False,
                   )

# -------------------------------------------------------------------------
def inv_warehouse_controller(**attr):

    s3 = current.response.s3

    # Custom prep
    standard_prep = s3.prep
    def prep(r):
        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        # Configure central-tag
        from ..helpers import configure_binary_tags
        configure_binary_tags(r.resource, ("central",))

        return result
    s3.prep = prep

    #standard_postp = s3.postp
    #def postp(r, output):
    #    if callable(standard_postp):
    #        output = standard_postp(r, output)
    #    return output
    #s3.postp = postp

    # Override standard postp
    s3.postp = None

    from ..rheaders import rlpptm_inv_rheader
    attr["rheader"] = rlpptm_inv_rheader

    return attr

# END =========================================================================
