# Supply Unit Tests
#
# To run this script use:
# python web2py.py -S eden -M -R applications/eden/modules/unit_tests/s3db/supply.py
#
import datetime
import unittest

from gluon import current
from gluon.storage import Storage

from s3db.supply import (SupplyCatalogModel,
                         SupplyItemModel,
                         SupplyItemPackQuantity,
                         item_um_from_name,
                         supply_ItemCategoryRepresent,
                         supply_ItemPackRepresent,
                         supply_ItemRepresent,
                         supply_get_shipping_code,
                         supply_item_entity_category,
                         supply_item_entity_contacts,
                         supply_item_entity_controller,
                         supply_item_entity_country,
                         supply_item_entity_organisation,
                         supply_item_entity_status,
                         supply_item_autocomplete_filter,
                         supply_item_pack_quantities,
                         )
from unit_tests import run_suite
from unit_tests.s3db.helpers import SupplyChainTestCase


# =============================================================================
class SupplyHelpersTests(SupplyChainTestCase):
    """Tests for pure supply helpers"""

    # -------------------------------------------------------------------------
    def testItemUmFromName(self):
        """item_um_from_name extracts units of measure from labels"""

        name, um = item_um_from_name("Chocolate per 100g")
        self.assertEqual(name, "Chocolate")
        self.assertEqual(um, "100g")

        name, um = item_um_from_name("Mineral Water bottle")
        self.assertEqual(name, "Mineral Water")
        self.assertEqual(um, "bottle")

        name, um = item_um_from_name("Plain Blanket")
        self.assertEqual(name, "Plain Blanket")
        self.assertEqual(um, None)

    # -------------------------------------------------------------------------
    def testSupplyItemPackQuantity(self):
        """SupplyItemPackQuantity returns nested pack quantities"""

        method = SupplyItemPackQuantity("req_req_item")

        row = type("Row", (), {})()
        row.req_req_item = Storage(item_pack_id=Storage(quantity=12))
        self.assertEqual(method(row), 12)

        row = type("Row", (), {})()
        row.req_req_item = Storage(item_pack_id=None)
        self.assertEqual(method(row), 0)

        row = type("Row", (), {})()
        self.assertEqual(method(row), 0)

    # -------------------------------------------------------------------------
    def testSupplyItemPackQuantities(self):
        """supply_item_pack_quantities bulk-loads known pack quantities"""

        # Create two different packs for the same item
        item_id = self.create_supply_item()
        pack_a = self.create_item_pack(item_id, name="box", quantity=4)
        pack_b = self.create_item_pack(item_id, name="crate", quantity=10)

        quantities = supply_item_pack_quantities([pack_a, pack_a, pack_b, 99999999])

        # Existing packs must be resolved once, unknown IDs ignored
        self.assertEqual(quantities[pack_a], 4)
        self.assertEqual(quantities[pack_b], 10)
        self.assertNotIn(99999999, quantities)

    # -------------------------------------------------------------------------
    def testSupplyGetShippingCode(self):
        """supply_get_shipping_code increments references by site code"""

        db = current.db
        s3db = current.s3db

        # Seed the last used reference for this site
        office = self.create_office(code="WH1")

        send_table = s3db.inv_send
        send_table.insert(send_ref="WB-WH1-000003")

        code = supply_get_shipping_code("WB", office.site_id, send_table.send_ref)
        self.assertEqual(code, "WB-WH1-000004")

        code = supply_get_shipping_code("GRN", None, None)
        self.assertEqual(code, "GRN-###-000001")

        # Custom generators must override the default sequence logic
        settings = current.deployment_settings
        original = settings.supply.get("shipping_code")
        try:
            settings.supply.shipping_code = lambda doctype, site_id, field: "CUSTOM-CODE"
            self.assertEqual(supply_get_shipping_code("WB", office.site_id, send_table.send_ref),
                             "CUSTOM-CODE")
        finally:
            settings.supply.shipping_code = original


# =============================================================================
class SupplyValidationTests(SupplyChainTestCase):
    """Tests for supply validators and duplicate detection"""

    # -------------------------------------------------------------------------
    def testCatalogAndCategoryValidation(self):
        """Catalog and category validators enforce uniqueness and required labels"""

        organisation_id = self.create_organisation()
        catalog_id = self.create_catalog(organisation_id=organisation_id,
                                         name="Main Catalog",
                                         )
        form = self.make_form(organisation_id=organisation_id,
                              name="Main Catalog",
                              )
        SupplyCatalogModel.catalog_onvalidation(form)
        self.assertIn("name", form.errors)

        form = self.make_form(catalog_id=catalog_id,
                              name=None,
                              code=None,
                              )
        SupplyCatalogModel.item_category_onvalidation(form)
        self.assertIn("name", form.errors)
        self.assertIn("code", form.errors)

        self.create_item_category(catalog_id, name="Shelter", code="SHEL")
        form = self.make_form(catalog_id=catalog_id,
                              name="Shelter",
                              code="SHEL",
                              )
        SupplyCatalogModel.item_category_onvalidation(form)
        self.assertIn("name", form.errors)
        self.assertIn("code", form.errors)

    # -------------------------------------------------------------------------
    def testSupplyItemAndCatalogItemValidation(self):
        """Item and catalog item validation reject duplicates in relevant catalogs"""

        organisation_id = self.create_organisation()
        catalog_a = self.create_catalog(organisation_id=organisation_id,
                                        name="Catalog A",
                                        )
        catalog_b = self.create_catalog(organisation_id=organisation_id,
                                        name="Catalog B",
                                        )
        category_a = self.create_item_category(catalog_a, name="Food", code="FOOD")
        category_b = self.create_item_category(catalog_b, name="Food", code="FOOD2")

        item_id = self.create_supply_item(catalog_id=catalog_a,
                                          item_category_id=category_a,
                                          code="ITM-1",
                                          name="Rice",
                                          um="kg",
                                          )
        self.create_catalog_item(catalog_a, item_id, item_category_id=category_a)

        form = self.make_form(catalog_id=catalog_b,
                              code="ITM-1",
                              name="Rice",
                              )
        SupplyItemModel.supply_item_onvalidation(form)
        self.assertIn("code", form.errors)
        self.assertIn("name", form.errors)

        form = self.make_form(catalog_id=catalog_a,
                              item_id=item_id,
                              )
        SupplyItemModel.catalog_item_onvalidation(form)
        self.assertIn("item_id", form.errors)

    # -------------------------------------------------------------------------
    def testDuplicateCallbacksDetectExistingRecords(self):
        """Import deduplication callbacks identify existing rows"""

        # Build one full catalog/item/pack structure to match against
        organisation_id = self.create_organisation()
        catalog_id = self.create_catalog(organisation_id=organisation_id,
                                         name="Import Catalog",
                                         )
        category_id = self.create_item_category(catalog_id, name="Relief", code="REL")
        item_id = self.create_supply_item(catalog_id=catalog_id,
                                          item_category_id=category_id,
                                          name="Blanket",
                                          um="pc",
                                          )
        pack_id = self.create_item_pack(item_id, name="bundle", quantity=5)
        catalog_item_id = self.create_catalog_item(catalog_id,
                                                   item_id,
                                                   item_category_id=category_id,
                                                   )

        update = Storage(UPDATE="update")

        item = Storage(data={"catalog_id": catalog_id,
                             "name": "Blanket",
                             "um": "pc",
                             },
                       table=current.s3db.supply_item,
                       METHOD=update,
                       method=None,
                       id=None,
                       )
        SupplyItemModel.supply_item_duplicate(item)
        self.assertEqual(item.id, item_id)
        self.assertEqual(item.method, update.UPDATE)

        pack = Storage(data={"item_id": item_id,
                             "name": "bundle",
                             "quantity": 5,
                             },
                       table=current.s3db.supply_item_pack,
                       METHOD=update,
                       method=None,
                       id=None,
                       )
        SupplyItemModel.supply_item_pack_duplicate(pack)
        self.assertEqual(pack.id, pack_id)
        self.assertEqual(pack.method, update.UPDATE)

        citem = Storage(data={"catalog_id": catalog_id,
                              "item_id": item_id,
                              "item_category_id": category_id,
                              },
                        table=current.s3db.supply_catalog_item,
                        METHOD=update,
                        method=None,
                        id=None,
                        )
        SupplyItemModel.catalog_item_deduplicate(citem)
        self.assertEqual(citem.id, catalog_item_id)
        self.assertEqual(citem.method, update.UPDATE)

        category = Storage(data={"catalog_id": catalog_id,
                                 "name": "Relief",
                                 "code": "REL",
                                 },
                           table=current.s3db.supply_item_category,
                           METHOD=update,
                           method=None,
                           id=None,
                           )
        SupplyCatalogModel.item_category_duplicate(category)
        self.assertEqual(category.id, category_id)
        self.assertEqual(category.method, update.UPDATE)


# =============================================================================
class SupplyModelTests(SupplyChainTestCase):
    """Tests for supply callbacks, representers and filters"""

    # -------------------------------------------------------------------------
    def testSupplyItemOnacceptCreatesCatalogItemAndDefaultPack(self):
        """Item onaccept creates the catalog link and the default unit pack"""

        db = current.db
        s3db = current.s3db

        # Create an item without any pre-existing default pack
        catalog_id = self.create_catalog()
        category_id = self.create_item_category(catalog_id, name="Medical")
        item_id = self.create_supply_item(catalog_id=catalog_id,
                                          item_category_id=category_id,
                                          name="Bandage",
                                          um="kg",
                                          )

        SupplyItemModel.supply_item_onaccept(self.make_form(id=item_id,
                                                            catalog_id=catalog_id,
                                                            item_category_id=category_id,
                                                            um="kg",
                                                            kit=False,
                                                            ))

        # The callback must create both the catalog link and the unit pack
        citable = s3db.supply_catalog_item
        citem = db(citable.item_id == item_id).select(citable.catalog_id,
                                                      citable.item_category_id,
                                                      limitby=(0, 1),
                                                      ).first()
        self.assertIsNotNone(citem)
        self.assertEqual(citem.catalog_id, catalog_id)
        self.assertEqual(citem.item_category_id, category_id)

        ptable = s3db.supply_item_pack
        pack = db((ptable.item_id == item_id) &
                  (ptable.quantity == 1.0),
                  ).select(ptable.name,
                           limitby=(0, 1),
                           ).first()
        self.assertIsNotNone(pack)
        self.assertEqual(pack.name, s3db.supply_item.um.represent("kg"))

    # -------------------------------------------------------------------------
    def testSupplyRepresentersAndAutocompleteFilter(self):
        """Representers format item data and autocomplete respects catalog scope"""

        db = current.db
        s3db = current.s3db

        # Create local, global and foreign catalog items for filter testing
        organisation_id = self.create_organisation()
        other_organisation = self.create_organisation()

        local_catalog = self.create_catalog(organisation_id=organisation_id, name="Local")
        global_catalog = self.create_catalog(organisation_id=None, name="Global")
        foreign_catalog = self.create_catalog(organisation_id=other_organisation, name="Foreign")

        local_category = self.create_item_category(local_catalog, name="Water", code="WAT")
        global_category = self.create_item_category(global_catalog, name="Shelter", code="SHE")

        local_item = self.create_supply_item(catalog_id=local_catalog,
                                             item_category_id=local_category,
                                             name="Water Bottle",
                                             um="L",
                                             )
        global_item = self.create_supply_item(catalog_id=global_catalog,
                                              item_category_id=global_category,
                                              name="Tent",
                                              um="pc",
                                              )
        foreign_item = self.create_supply_item(catalog_id=foreign_catalog,
                                               item_category_id=self.create_item_category(foreign_catalog,
                                                                                         name="Other",
                                                                                         code="OTH",
                                                                                         ),
                                               name="Generator",
                                               um="pc",
                                               )

        local_pack = self.create_item_pack(local_item, name="crate", quantity=6)
        self.create_catalog_item(local_catalog, local_item, item_category_id=local_category)
        self.create_catalog_item(global_catalog, global_item, item_category_id=global_category)
        self.create_catalog_item(foreign_catalog, foreign_item)

        item_repr = supply_ItemRepresent(show_um=True, truncate=False)
        rows = item_repr.lookup_rows(None, [local_item])
        expected_um = s3db.supply_item.um.represent("L")
        self.assertEqual(item_repr.represent_row(rows.first()),
                         "Water Bottle (%s)" % expected_um)

        pack_repr = supply_ItemPackRepresent()
        pack_repr.table = s3db.supply_item_pack
        rows = pack_repr.lookup_rows(pack_repr.table.id, [local_pack])
        self.assertEqual(pack_repr.represent_row(rows.first()),
                         "crate (6 %s)" % expected_um)

        category_repr = supply_ItemCategoryRepresent(show_catalog=False,
                                                     use_code=False,
                                                     )
        rows = category_repr.lookup_rows(None, [global_category])
        self.assertEqual(category_repr.represent_row(rows.first()), "Shelter")

        query = supply_item_autocomplete_filter(organisation_id)
        rows = db(query).select(s3db.supply_item.id)
        item_ids = {row.id for row in rows}

        # The filter should expose local and global items, but not foreign ones
        self.assertIn(local_item, item_ids)
        self.assertIn(global_item, item_ids)
        self.assertNotIn(foreign_item, item_ids)

    # -------------------------------------------------------------------------
    def testSupplyItemEntityVirtualFieldsRepresentInventoryContext(self):
        """Item entity virtual fields derive category, country, org, contacts and status"""

        db = current.db
        s3db = current.s3db
        request = current.request

        # Build one stocked item with enough site context for all virtual fields
        location_id = self.create_location(name="Warsaw", L0="Poland")
        office = self.create_office(name="Warehouse Office",
                                    comments="Call the warehouse",
                                    location_id=location_id,
                                    )
        organisation_row = db(s3db.org_organisation.id == office.organisation_id).select(
                               s3db.org_organisation.name,
                               limitby=(0, 1),
                               ).first()
        catalog_id = self.create_catalog(organisation_id=office.organisation_id,
                                         name="Warehouse Catalog",
                                         )
        category_id = self.create_item_category(catalog_id,
                                                name="Medical Supplies",
                                                code="MED",
                                                )
        item_id = self.create_supply_item(catalog_id=catalog_id,
                                          item_category_id=category_id,
                                          name="Thermal Blanket",
                                          )
        pack_id = self.create_item_pack(item_id, quantity=1)
        expiry = datetime.date(2026, 4, 1)
        inv_item_id = self.create_inventory_item(office.site_id,
                                                 item_id,
                                                 pack_id,
                                                 quantity=5,
                                                 expiry_date=expiry,
                                                 )

        entity_id = db(s3db.inv_inv_item.id == inv_item_id).select(s3db.inv_inv_item.item_entity_id,
                                                                   limitby=(0, 1),
                                                                   ).first().item_entity_id
        row = Storage(supply_item_entity=Storage(item_id=item_id,
                                                 item_entity_id=entity_id,
                                                 instance_type="inv_inv_item",
                                                 ))

        category = str(supply_item_entity_category(row))
        organisation = str(supply_item_entity_organisation(row))
        status = str(supply_item_entity_status(row))

        saved_extension = request.extension
        try:
            request.extension = "html"
            contacts = supply_item_entity_contacts(row)
            request.extension = "xls"
            export_contacts = supply_item_entity_contacts(row)
        finally:
            request.extension = saved_extension

        # Virtual fields must resolve all visible site/item context
        self.assertIn("Medical Supplies", category)
        self.assertEqual(supply_item_entity_country(row), "Poland")
        self.assertIn(organisation_row.name, organisation)
        self.assertIn("Call the warehouse", str(contacts))
        self.assertIn("/office/%s" % office.id, contacts.attributes["_href"])
        self.assertEqual(export_contacts, "Call the warehouse")
        self.assertIn("Stock Expires", status)
        self.assertIn(str(expiry), status)

    # -------------------------------------------------------------------------
    def testSupplyItemEntityVirtualFieldsHandleUnsupportedOrMissingRows(self):
        """Item entity virtual fields degrade cleanly for incomplete row shapes"""

        none = current.messages["NONE"]

        self.assertEqual(supply_item_entity_category(Storage()), None)
        self.assertEqual(supply_item_entity_country(Storage()), None)
        self.assertEqual(supply_item_entity_organisation(Storage()), None)
        self.assertEqual(supply_item_entity_contacts(Storage()), None)
        self.assertEqual(supply_item_entity_status(Storage()), None)

        row = Storage(supply_item_entity=Storage(item_entity_id=1,
                                                 instance_type="asset_asset",
                                                 ))
        self.assertEqual(supply_item_entity_country(row), none)
        self.assertEqual(supply_item_entity_organisation(row), none)
        self.assertEqual(supply_item_entity_contacts(row), none)
        self.assertEqual(supply_item_entity_status(row), none)


# =============================================================================
class SupplyControllerTests(SupplyChainTestCase):
    """Tests for supply controller wrappers and prep hooks"""

    # -------------------------------------------------------------------------
    def testSupplyIndexUsesConfiguredModuleName(self):
        """supply index exposes the configured module name"""

        expected = current.deployment_settings.modules["supply"].get("name_nice")

        with self.controller("supply", function="index") as controller:
            output = controller.module["index"]()
            title = current.response.title

        self.assertEqual(output["module_name"], expected)
        self.assertEqual(title, expected)

    # -------------------------------------------------------------------------
    def testCatalogControllerPrepFiltersCategoryAndItemFields(self):
        """catalog prep limits categories and item widgets to the catalog organisation"""

        s3db = current.s3db

        organisation_id = self.create_organisation()
        catalog_id = self.create_catalog(organisation_id=organisation_id,
                                         name="Controller Catalog",
                                         )

        table = s3db.supply_catalog_item
        category_field = table.item_category_id
        item_field = table.item_id
        original_requires = category_field.requires
        original_widget = item_field.widget

        try:
            with self.controller("supply", function="catalog") as controller:
                output = controller.module["catalog"]()

                prep = output.prep
                record = Storage(id=catalog_id, organisation_id=organisation_id)
                r = Storage(record=record,
                            component_name="catalog_item",
                            component=Storage(table=table),
                            )

                self.assertTrue(prep(r))
                widget_filter = item_field.widget.filter
        finally:
            category_field.requires = original_requires
            item_field.widget = original_widget

        self.assertEqual(output.kwargs["rheader"], s3db.supply_catalog_rheader)
        self.assertIsNotNone(category_field.requires)
        self.assertEqual(widget_filter, "org=%s" % organisation_id)

    # -------------------------------------------------------------------------
    def testItemCategoryControllerPrepSupportsAssetsAndParentFilter(self):
        """item_category prep hides the asset flag and excludes the current parent"""

        s3db = current.s3db

        catalog_id = self.create_catalog()
        category_a = self.create_item_category(catalog_id,
                                               name="Parent",
                                               code="PAR",
                                               )
        self.create_item_category(catalog_id,
                                  name="Child",
                                  code="CHI",
                                  )

        table = s3db.supply_item_category
        field = table.can_be_asset
        parent_field = table.parent_item_category_id
        original_readable = field.readable
        original_writable = field.writable
        original_requires = parent_field.requires

        try:
            with self.controller("supply", function="item_category") as controller:
                output = controller.module["item_category"]()

                prep = output.prep
                r = Storage(id=category_a,
                            get_vars=Storage(assets="1"),
                            table=table,
                            )
                self.assertTrue(prep(r))
                readable = field.readable
                writable = field.writable
                requires = parent_field.requires
        finally:
            field.readable = original_readable
            field.writable = original_writable
            parent_field.requires = original_requires

        self.assertFalse(readable)
        self.assertFalse(writable)
        self.assertIsNotNone(requires)

    # -------------------------------------------------------------------------
    def testDistributionControllersScopeItemAutocompleteToOrganisation(self):
        """distribution controllers limit item autocomplete to the distribution organisation"""

        s3db = current.s3db

        organisation_id = self.create_organisation()
        record = Storage(organisation_id=organisation_id)

        set_table = s3db.supply_distribution_set_item
        item_table = s3db.supply_distribution_item
        original_set_widget = set_table.item_id.widget
        original_item_widget = item_table.item_id.widget

        try:
            with self.controller("supply", function="distribution_set") as controller:
                output = controller.module["distribution_set"]()
                prep = output.prep
                r = Storage(record=record,
                            component_name="distribution_set_item",
                            component=Storage(table=set_table),
                            )
                self.assertTrue(prep(r))
                self.assertEqual(set_table.item_id.widget.filter,
                                 "org=%s" % organisation_id)

            with self.controller("supply", function="distribution") as controller:
                output = controller.module["distribution"]()
                prep = output.prep
                r = Storage(record=record,
                            component_name="distribution_item",
                            component=Storage(table=item_table),
                            )
                self.assertTrue(prep(r))
                self.assertEqual(item_table.item_id.widget.filter,
                                 "org=%s" % organisation_id)
        finally:
            set_table.item_id.widget = original_set_widget
            item_table.item_id.widget = original_item_widget

    # -------------------------------------------------------------------------
    def testItemAndItemEntityControllersDelegateToModelControllers(self):
        """item and item_entity controllers delegate to model controller helpers"""

        s3db = current.s3db
        saved_item = s3db.supply_item_controller
        saved_entity = s3db.supply_item_entity_controller
        s3db.supply_item_controller = lambda: "ITEM-CONTROLLER"
        s3db.supply_item_entity_controller = lambda: "ENTITY-CONTROLLER"

        try:
            with self.controller("supply", function="item") as controller:
                item_output = controller.module["item"]()

            with self.controller("supply", function="item_entity") as controller:
                entity_output = controller.module["item_entity"]()
        finally:
            s3db.supply_item_controller = saved_item
            s3db.supply_item_entity_controller = saved_entity

        self.assertEqual(item_output, "ITEM-CONTROLLER")
        self.assertEqual(entity_output, "ENTITY-CONTROLLER")

    # -------------------------------------------------------------------------
    def testItemPackControllerDisablesListAdd(self):
        """item_pack controller disables inline list-adds"""

        s3db = current.s3db
        saved = s3db.get_config("supply_item_pack", "listadd")

        try:
            with self.controller("supply", function="item_pack") as controller:
                output = controller.module["item_pack"]()
                listadd = s3db.get_config("supply_item_pack", "listadd")
        finally:
            s3db.configure("supply_item_pack", listadd=saved)

        self.assertEqual(listadd, False)
        self.assertEqual(output.args, ())

    # -------------------------------------------------------------------------
    def testItemEntityControllerConfiguresVirtualFieldsAndManualFilters(self):
        """item_entity controller exposes virtual report fields and manual list filters"""

        current.db.rollback()

        # Create one inventory entity so the controller can build filter choices
        location_id = self.create_location(name="Berlin", L0="Germany")
        office = self.create_office(name="Entity Office",
                                    comments="entity contact",
                                    location_id=location_id,
                                    )
        catalog_id = self.create_catalog(organisation_id=office.organisation_id)
        category_id = self.create_item_category(catalog_id,
                                                name="Shelter",
                                                code="SHE",
                                                )
        item_id = self.create_supply_item(catalog_id=catalog_id,
                                          item_category_id=category_id,
                                          name="Family Tent",
                                          )
        pack_id = self.create_item_pack(item_id, quantity=1)
        self.create_inventory_item(office.site_id,
                                   item_id,
                                   pack_id,
                                   quantity=7,
                                   )

        response_s3 = current.response.s3
        saved_crud_controller = current.crud_controller
        saved_postp = response_s3.postp
        saved_no_sspag = response_s3.no_sspag
        saved_ready = list(response_s3.jquery_ready)
        captured = {}

        def crud_controller(*args, **kwargs):
            """Capture controller setup for assertions"""

            captured["args"] = args
            captured["kwargs"] = kwargs
            captured["postp"] = response_s3.postp
            return Storage(args=args, kwargs=kwargs)

        current.crud_controller = crud_controller
        response_s3.jquery_ready = []
        try:
            output = supply_item_entity_controller()
            postp = captured["postp"]
            rendered = postp(Storage(interactive=True, record=None), {})
            no_sspag = response_s3.no_sspag
            jquery_ready = list(response_s3.jquery_ready)
        finally:
            current.crud_controller = saved_crud_controller
            response_s3.postp = saved_postp
            response_s3.no_sspag = saved_no_sspag
            response_s3.jquery_ready = saved_ready

        rheader = str(rendered["rheader"])
        list_fields = current.s3db.get_config("supply_item_entity", "list_fields")

        # The report controller must expose the virtual columns and manual filters
        self.assertEqual(output.args, ("supply", "item_entity"))
        self.assertTrue(captured["kwargs"]["hide_filter"])
        self.assertTrue(no_sspag)
        self.assertEqual([field[1] if isinstance(field, tuple) else field
                          for field in list_fields],
                         ["category",
                          "item_id",
                          "quantity",
                          "item_pack_id",
                          "status",
                          "country",
                          "organisation",
                          "contacts",
                          ])
        self.assertIn("Filter by Category", rheader)
        self.assertIn("Filter by Status", rheader)
        self.assertIn("Filter by Country", rheader)
        self.assertIn("Filter by Organization", rheader)
        self.assertIn("filterColumns", "".join(jquery_ready))


# =============================================================================
if __name__ == "__main__":

    run_suite(
        SupplyHelpersTests,
        SupplyValidationTests,
        SupplyModelTests,
        SupplyControllerTests,
    )

# END ========================================================================
