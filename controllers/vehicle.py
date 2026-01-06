"""
    Vehicle Management Functionality
"""

module = request.controller

if not settings.has_module(module):
    raise HTTP(404, body="Module disabled: %s" % module)

# Vehicle Module depends on Assets
if not settings.has_module("asset"):
    raise HTTP(404, body="Module disabled: %s" % "asset")

# -----------------------------------------------------------------------------
def index():
    """ Module's Home Page """

    return s3db.cms_index(module, alt_function="index_alt")

# -----------------------------------------------------------------------------
def index_alt():
    """
        Module homepage for non-Admin users when no CMS content found
    """

    # Just redirect to the list of Assets
    s3_redirect_default(URL(f="vehicle"))

# -----------------------------------------------------------------------------
def create():
    """ Redirect to vehicle/create """
    redirect(URL(f="vehicle", args="create"))

# -----------------------------------------------------------------------------
def vehicle():
    """
        Vehicles - filtered proxy CRUD controller for assets
    """

    table = s3db.asset_asset

    # Configure custom methods for assets
    set_method = s3db.set_method
    set_method("asset_asset", method="assign",
               action = s3db.hrm_AssignMethod(component="human_resource"))
    set_method("asset_asset", method="check-in",
               action = s3base.S3CheckInMethod())
    set_method("asset_asset", method="check-out",
               action = s3base.S3CheckOutMethod())

    # Filter by asset type VEHICLE
    VEHICLE = s3db.asset_types["VEHICLE"]
    s3.filter = FS("type") == VEHICLE

    # Default to asset type VEHICLE
    field = table.type
    field.default = VEHICLE
    field.readable = False
    field.writable = False

    # Configure list fields for vehicle context
    list_fields = ["item_id$item_category_id",
                   "item_id",
                   "number",
                   "sn",
                   "organisation_id",
                   "site_id",
                   (T("Assigned To"), "assigned_to_id"),
                   "cond",
                   "comments",
                   ]
    # Adapt CRUD form for vehicle context
    from core import CustomForm
    crud_form = CustomForm("organisation_id",
                           "site_id",
                           "item_id",
                           "number",
                           "sn",
                           "supply_org_id",
                           "purchase_date",
                           "purchase_price",
                           "purchase_currency",
                           )
    subheadings = {"organisation_id": T("Owner / Base"),
                   "item_id": T("Vehicle Details"),
                   "supply_org_id": T("Purchase Details"),
                   }

    # Adapt redirections
    create_next = URL(c="vehicle", f="vehicle", args=["[id]"])

    s3db.configure("asset_asset",
                   crud_form = crud_form,
                   subheadings = subheadings,
                   create_next = create_next,
                   list_fields = list_fields,
                   )

    # Limit item categories to vehicle types
    field = table.item_id
    field.label = T("Asset Type")
    ctable = s3db.supply_item_category
    itable = s3db.supply_item
    dbset = db((ctable.id == itable.item_category_id) & \
               (ctable.is_vehicle == True))
    field.requires = IS_ONE_OF(dbset, "supply_item.id", field.represent, sort=True)
    field.widget = None # use simple dropdown

    # Adapt other field labels to vehicle context
    field = table.sn
    field.label = T("License Plate")
    s3db.asset_log.room_id.label = T("Parking Area")

    # Adapt CRUD strings to vehicle context
    s3.crud_strings["asset_asset"] = Storage(
        label_create = T("Add Vehicle"),
        title_display = T("Vehicle Details"),
        title_list = T("Vehicles"),
        title_update = T("Edit Vehicle"),
        title_map = T("Map of Vehicles"),
        label_list_button = T("List Vehicles"),
        label_delete_button = T("Delete Vehicle"),
        msg_record_created = T("Vehicle added"),
        msg_record_modified = T("Vehicle updated"),
        msg_record_deleted = T("Vehicle deleted"),
        msg_list_empty = T("No Vehicles currently registered"))

    return s3db.asset_controller()

# =============================================================================
def vehicle_type():
    """ RESTful CRUD controller """

    return crud_controller()

# =============================================================================
def item():
    """ RESTful CRUD controller """

    # Filter to just Vehicles
    table = s3db.supply_item
    ctable = s3db.supply_item_category
    s3.filter = (table.item_category_id == ctable.id) & \
                (ctable.is_vehicle == True)

    # Limit the Categories to just those with vehicles in
    # - make category mandatory so that filter works
    field = s3db.supply_item.item_category_id
    field.requires = IS_ONE_OF(db,
                               "supply_item_category.id",
                               s3db.supply_item_category_represent,
                               sort=True,
                               filterby = "is_vehicle",
                               filter_opts = [True]
                               )

    field.label = T("Vehicle Categories")
    field.comment = PopupLink(f="item_category",
                              label=T("Add Vehicle Category"),
                              info=T("Add a new vehicle category"),
                              title=T("Vehicle Category"),
                              tooltip=T("Only Categories of type 'Vehicle' will be seen in the dropdown."))

    # CRUD strings
    s3.crud_strings["supply_item"] = Storage(
        label_create = T("Add New Vehicle Type"),
        title_display = T("Vehicle Type Details"),
        title_list = T("Vehicle Types"),
        title_update = T("Edit Vehicle Type"),
        label_list_button = T("List Vehicle Types"),
        label_delete_button = T("Delete Vehicle Type"),
        msg_record_created = T("Vehicle Type added"),
        msg_record_modified = T("Vehicle Type updated"),
        msg_record_deleted = T("Vehicle Type deleted"),
        msg_list_empty = T("No Vehicle Types currently registered"),
        msg_match = T("Matching Vehicle Types"),
        msg_no_match = T("No Matching Vehicle Types")
        )

    # Defined in the Model for use from Multiple Controllers for unified menus
    return s3db.supply_item_controller()

# =============================================================================
def item_category():
    """ RESTful CRUD controller """

    table = s3db.supply_item_category

    # Filter to just Vehicles
    s3.filter = (table.is_vehicle == True)

    # Default to Vehicles
    field = table.can_be_asset
    field.readable = field.writable = False
    field.default = True
    field = table.is_vehicle
    field.readable = field.writable = False
    field.default = True

    return crud_controller("supply", "item_category")

# END =========================================================================
