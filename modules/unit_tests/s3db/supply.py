# Supply Unit Tests
#
# To run this script use:
# python web2py.py -S eden -M -R applications/eden/modules/unit_tests/s3db/supply.py
#
import datetime
import unittest

from gluon import HTTP, URL, current
from gluon.storage import Storage

from s3db.supply import (SupplyCatalogModel,
                         SupplyDistributionModel,
                         SupplyItemModel,
                         SupplyItemBrandModel,
                         SupplyItemEntityModel,
                         SupplyItemPackQuantity,
                         item_um_from_name,
                         supply_catalog_rheader,
                         supply_distribution_rheader,
                         supply_ItemCategoryRepresent,
                         supply_ItemPackRepresent,
                         supply_ItemRepresent,
                         supply_get_shipping_code,
                         supply_item_rheader,
                         supply_item_controller,
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

    # -------------------------------------------------------------------------
    def testSupplyGetShippingCodeFallsBackToUnknownSiteCode(self):
        """Shipping codes fall back to ### when the site code cannot be resolved"""

        send_table = current.s3db.inv_send
        send_table.insert(send_ref="WB-###-000009")

        code = supply_get_shipping_code("WB", 99999999, send_table.send_ref)

        self.assertEqual(code, "WB-###-000010")

    # -------------------------------------------------------------------------
    def testSupplyItemAddHandlesDifferentPackQuantities(self):
        """supply_item_add normalises quantities into the first pack size"""

        self.assertEqual(SupplyItemModel.supply_item_add(2, 1, 3, 1), 5)
        self.assertEqual(SupplyItemModel.supply_item_add(2, 5, 3, 2), 3.2)


# =============================================================================
class SupplyConfigurationTests(SupplyChainTestCase):
    """Tests for supply model configuration branches"""

    # -------------------------------------------------------------------------
    @staticmethod
    def _reload_model(model_class, name, *tablenames):
        """Reload a supply DataModel after changing deployment settings"""

        s3db = current.s3db

        for tablename in tablenames:
            s3db.clear_config(tablename)

        loaded = current.response.get("eden_model_load")
        if loaded:
            while name in loaded:
                loaded.remove(name)

        model_class("supply")

    # -------------------------------------------------------------------------
    def testSupplyCatalogModelSupportsTranslationHierarchyAndXlsxParents(self):
        """Catalog/category model honours translation, hierarchy and xlsx parent representations"""

        settings = current.deployment_settings
        globals_ = SupplyCatalogModel.model.__globals__

        saved_translate = settings.get_L10n_translate_supply_item
        saved_hierarchy = settings.get_supply_item_category_hierarchy
        sentinel = object()
        saved_format = globals_.get("format", sentinel)

        try:
            settings.get_L10n_translate_supply_item = lambda: True
            settings.get_supply_item_category_hierarchy = lambda: True
            globals_["format"] = "xlsx"

            self._reload_model(SupplyCatalogModel,
                               "SupplyCatalogModel",
                               "supply_catalog",
                               "supply_item_category",
                               )

            catalog_id = self.create_catalog(name="Translated Catalog")
            table = current.s3db.supply_item_category
            parent_id = table.insert(catalog_id=catalog_id,
                                     name="Parent Category",
                                     code="PARENT",
                                     )
            child_id = table.insert(catalog_id=catalog_id,
                                    parent_item_category_id=parent_id,
                                    name="Child Category",
                                    code="CHILD",
                                    )

            row = current.db(table.id == child_id).select(table.parent_item_category_id,
                                                          limitby=(0, 1),
                                                          ).first()
            self.assertEqual(row.parent_item_category_id, parent_id)
            self.assertIsNotNone(current.s3db.get_config("supply_item_category", "deduplicate"))
        finally:
            settings.get_L10n_translate_supply_item = saved_translate
            settings.get_supply_item_category_hierarchy = saved_hierarchy
            if saved_format is sentinel:
                globals_.pop("format", None)
            else:
                globals_["format"] = saved_format
            self._reload_model(SupplyCatalogModel,
                               "SupplyCatalogModel",
                               "supply_catalog",
                               "supply_item_category",
                               )

    # -------------------------------------------------------------------------
    def testSupplyItemModelSupportsLocalUnitsAltNamesAndPackTracking(self):
        """Item model configuration exposes alt names, local units and tracking columns"""

        settings = current.deployment_settings

        saved_translate = settings.get_L10n_translate_supply_item
        saved_units = settings.get_L10n_units_of_measure
        saved_alt_name = settings.get_supply_use_alt_name
        saved_generic_items = settings.get_supply_generic_items
        saved_kits = settings.get_supply_kits
        saved_pack_values = settings.get_supply_track_pack_values
        saved_pack_dimensions = settings.get_supply_track_pack_dimensions

        try:
            settings.get_L10n_translate_supply_item = lambda: True
            settings.get_L10n_units_of_measure = lambda: {"bag": "bag"}
            settings.get_supply_use_alt_name = lambda: True
            settings.get_supply_generic_items = lambda: False
            settings.get_supply_kits = lambda: True
            settings.get_supply_track_pack_values = lambda: True
            settings.get_supply_track_pack_dimensions = lambda: True

            self._reload_model(SupplyItemModel,
                               "SupplyItemModel",
                               "supply_item",
                               "supply_item_pack",
                               "supply_catalog_item",
                               )

            list_fields = current.s3db.get_config("supply_item", "list_fields")
            self.assertIn("brand_id", list_fields)
            self.assertIn("model", list_fields)
            self.assertIn("year", list_fields)

            filter_widgets = current.s3db.get_config("supply_item", "filter_widgets")
            widget_fields = [getattr(widget, "field", None) for widget in filter_widgets]
            self.assertIn("brand_id", widget_fields)
            self.assertIn("year", widget_fields)
        finally:
            settings.get_L10n_translate_supply_item = saved_translate
            settings.get_L10n_units_of_measure = saved_units
            settings.get_supply_use_alt_name = saved_alt_name
            settings.get_supply_generic_items = saved_generic_items
            settings.get_supply_kits = saved_kits
            settings.get_supply_track_pack_values = saved_pack_values
            settings.get_supply_track_pack_dimensions = saved_pack_dimensions
            self._reload_model(SupplyItemModel,
                               "SupplyItemModel",
                               "supply_item",
                               "supply_item_pack",
                               "supply_catalog_item",
                               )

    # -------------------------------------------------------------------------
    def testSupplyModelDefaultsProvideHiddenDummyFields(self):
        """Disabled-model defaults expose hidden dummy field templates"""

        catalog_defaults = SupplyCatalogModel("supply").defaults()
        self.assertEqual(catalog_defaults["supply_catalog_id"]().name, "catalog_id")
        self.assertEqual(catalog_defaults["supply_item_category_id"]().name, "item_category_id")

        item_defaults = SupplyItemModel("supply").defaults()
        self.assertEqual(item_defaults["supply_item_id"]().name, "item_id")
        self.assertEqual(item_defaults["supply_item_pack_id"]().name, "item_pack_id")
        self.assertEqual(item_defaults["supply_item_pack_quantity"]("req_req_item")(Storage()), 0)

    # -------------------------------------------------------------------------
    def testAdditionalSupplyDefaultsExposeDummyFields(self):
        """Other disabled supply models expose their dummy field templates"""

        item_entity_defaults = SupplyItemEntityModel("supply").defaults()
        brand_defaults = SupplyItemBrandModel("supply").defaults()
        distribution_defaults = SupplyDistributionModel("supply").defaults()

        self.assertEqual(item_entity_defaults["supply_item_entity_id"]().name, "item_entity_id")
        self.assertEqual(brand_defaults["supply_brand_id"]().name, "brand_id")
        self.assertEqual(distribution_defaults["supply_distribution_set_id"]().name, "distribution_set_id")


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
    def testCatalogAndCategoryValidationIgnoreCurrentRowsAndSingleLabels(self):
        """Catalog and category validators ignore the current row and accept forms with only one label"""

        organisation_id = self.create_organisation()
        catalog_id = self.create_catalog(organisation_id=organisation_id,
                                         name="Validation Catalog",
                                         )
        category_id = self.create_item_category(catalog_id,
                                                name="Shelter",
                                                code="SHEL",
                                                )

        form = self.make_form(id=catalog_id,
                              organisation_id=organisation_id,
                              name="Validation Catalog",
                              )
        SupplyCatalogModel.catalog_onvalidation(form)
        self.assertEqual(form.errors, {})

        form = self.make_form(id=category_id,
                              catalog_id=catalog_id,
                              name="Shelter",
                              code="SHEL",
                              )
        SupplyCatalogModel.item_category_onvalidation(form)
        self.assertEqual(form.errors, {})

        name_only = self.make_form(catalog_id=catalog_id,
                                   name="Water",
                                   code=None,
                                   )
        SupplyCatalogModel.item_category_onvalidation(name_only)
        self.assertEqual(name_only.errors, {})

        code_only = self.make_form(catalog_id=catalog_id,
                                   name=None,
                                   code="WATR",
                                   )
        SupplyCatalogModel.item_category_onvalidation(code_only)
        self.assertEqual(code_only.errors, {})

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

        duplicate_code_item = self.create_supply_item(catalog_id=catalog_b,
                                                      item_category_id=category_b,
                                                      code="ITM-1",
                                                      name="Rice Extra",
                                                      um="kg",
                                                      )
        form = self.make_form(catalog_id=catalog_a,
                              item_id=duplicate_code_item,
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

    # -------------------------------------------------------------------------
    def testSupplyItemDuplicateSupportsCodeAndExtractedUnitMatching(self):
        """Item deduplication can match by exact code or by UM extracted from the imported name"""

        s3db = current.s3db
        update = Storage(UPDATE="update")

        catalog_id = self.create_catalog(name="Dedup Catalog")
        category_id = self.create_item_category(catalog_id,
                                                name="Food",
                                                code="FOOD",
                                                )

        coded_item_id = self.create_supply_item(catalog_id=catalog_id,
                                                item_category_id=category_id,
                                                code="BLK-001",
                                                name="Blanket",
                                                um="pc",
                                                )
        extracted_item_id = self.create_supply_item(catalog_id=catalog_id,
                                                    item_category_id=category_id,
                                                    name="Chocolate",
                                                    um="100g",
                                                    )

        coded = Storage(data={"code": "BLK-001"},
                        table=s3db.supply_item,
                        METHOD=update,
                        method=None,
                        id=None,
                        )
        SupplyItemModel.supply_item_duplicate(coded)

        extracted = Storage(data={"catalog_id": catalog_id,
                                  "name": "Chocolate per 100g",
                                  },
                            table=s3db.supply_item,
                            METHOD=update,
                            method=None,
                            id=None,
                            )
        SupplyItemModel.supply_item_duplicate(extracted)

        unnamed = Storage(data={},
                          table=s3db.supply_item,
                          METHOD=update,
                          method=None,
                          id=None,
                          )
        SupplyItemModel.supply_item_duplicate(unnamed)

        self.assertEqual(coded.id, coded_item_id)
        self.assertEqual(coded.method, update.UPDATE)
        self.assertEqual(extracted.id, extracted_item_id)
        self.assertEqual(extracted.method, update.UPDATE)
        self.assertIsNone(unnamed.id)
        self.assertIsNone(unnamed.method)

    # -------------------------------------------------------------------------
    def testPackAndCatalogDeduplicationWorkWithoutOptionalFilters(self):
        """Pack and catalog-item deduplication still matches when optional quantity/category filters are absent"""

        s3db = current.s3db
        update = Storage(UPDATE="update")

        catalog_id = self.create_catalog(name="Optional Filter Catalog")
        category_id = self.create_item_category(catalog_id,
                                                name="Shelter",
                                                code="SHEL",
                                                )
        item_id = self.create_supply_item(catalog_id=catalog_id,
                                          item_category_id=category_id,
                                          name="Tent",
                                          )
        pack_id = self.create_item_pack(item_id,
                                        name="bundle",
                                        quantity=5,
                                        )
        catalog_item_id = self.create_catalog_item(catalog_id,
                                                   item_id,
                                                   item_category_id=category_id,
                                                   )

        pack = Storage(data={"item_id": item_id,
                             "name": "bundle",
                             },
                       table=s3db.supply_item_pack,
                       METHOD=update,
                       method=None,
                       id=None,
                       )
        SupplyItemModel.supply_item_pack_duplicate(pack)

        citem = Storage(data={"catalog_id": catalog_id,
                              "item_id": item_id,
                              },
                        table=s3db.supply_catalog_item,
                        METHOD=update,
                        method=None,
                        id=None,
                        )
        SupplyItemModel.catalog_item_deduplicate(citem)

        self.assertEqual(pack.id, pack_id)
        self.assertEqual(pack.method, update.UPDATE)
        self.assertEqual(citem.id, catalog_item_id)
        self.assertEqual(citem.method, update.UPDATE)

    # -------------------------------------------------------------------------
    def testItemCategoryDuplicateRespectsParentCategoryId(self):
        """Category deduplication must distinguish equal labels under different parents"""

        catalog_id = self.create_catalog(name="Hierarchy Catalog")
        table = current.s3db.supply_item_category

        parent_a = table.insert(catalog_id=catalog_id,
                                name="Parent A",
                                code="PA",
                                )
        parent_b = table.insert(catalog_id=catalog_id,
                                name="Parent B",
                                code="PB",
                                )
        table.insert(catalog_id=catalog_id,
                     parent_item_category_id=parent_a,
                     name="Shelter",
                     )

        update = Storage(UPDATE="update")
        item = Storage(data={"catalog_id": catalog_id,
                             "name": "Shelter",
                             "parent_item_category_id": parent_b,
                             },
                       table=table,
                       METHOD=update,
                       method=None,
                       id=None,
                       )

        SupplyCatalogModel.item_category_duplicate(item)

        self.assertIsNone(item.id)
        self.assertIsNone(item.method)

    # -------------------------------------------------------------------------
    def testCatalogItemOnvalidationIgnoresCurrentRecordAcrossCatalogs(self):
        """Catalog-item validation must ignore the current row when matching codes in other catalogs"""

        catalog_a = self.create_catalog(name="Catalog A")
        category_a = self.create_item_category(catalog_a, name="Food", code="FOOD-A")
        item_a = self.create_supply_item(catalog_id=catalog_a,
                                         item_category_id=category_a,
                                         code="WAT-1",
                                         name="Water",
                                         )
        self.create_catalog_item(catalog_a,
                                 item_a,
                                 item_category_id=category_a,
                                 )

        catalog_b = self.create_catalog(name="Catalog B")
        category_b = self.create_item_category(catalog_b, name="Food", code="FOOD-B")
        item_b = self.create_supply_item(catalog_id=catalog_b,
                                         item_category_id=category_b,
                                         code="WAT-1",
                                         name="Water",
                                         )
        catalog_item_id = self.create_catalog_item(catalog_b,
                                                   item_b,
                                                   item_category_id=category_b,
                                                   )

        form = self.make_form(id=catalog_item_id,
                              catalog_id=catalog_b,
                              item_id=item_b,
                              )

        SupplyItemModel.catalog_item_onvalidation(form)

        self.assertNotIn("item_id", form.errors)

    # -------------------------------------------------------------------------
    def testDistributionSetValidationRejectsDuplicateTitles(self):
        """Distribution set validation enforces title uniqueness per organisation"""

        organisation_id = self.create_organisation()
        table = current.s3db.supply_distribution_set

        table.insert(organisation_id=organisation_id,
                     name="Daily Kits",
                     )

        form = self.make_form(organisation_id=organisation_id,
                              name="Daily Kits",
                              )
        SupplyDistributionModel.distribution_set_onvalidation(form)

        self.assertIn("name", form.errors)

    # -------------------------------------------------------------------------
    def testDistributionSetItemValidationRejectsDuplicatesAndBadQuantities(self):
        """Distribution set item validation blocks duplicate rows and invalid quantity ranges"""

        s3db = current.s3db

        set_id = s3db.supply_distribution_set.insert(name="Shelter Kits")
        item_id = self.create_supply_item(name="Family Tent")

        s3db.supply_distribution_set_item.insert(distribution_set_id=set_id,
                                                 mode="GRA",
                                                 item_id=item_id,
                                                 quantity=1,
                                                 quantity_max=2,
                                                 )

        form = self.make_form(distribution_set_id=set_id,
                              mode="GRA",
                              item_id=item_id,
                              quantity=3,
                              quantity_max=2,
                              )
        SupplyDistributionModel.distribution_set_item_onvalidation(form)

        self.assertIn("item_id", form.errors)
        self.assertIn("quantity", form.errors)

    # -------------------------------------------------------------------------
    def testDistributionValidatorsIgnoreCurrentRowsAndMissingIds(self):
        """Distribution validators ignore the current row and no-op without a record ID"""

        db = current.db
        s3db = current.s3db

        organisation_id = self.create_organisation()
        set_id = s3db.supply_distribution_set.insert(name="Starter Kit",
                                                     organisation_id=organisation_id,
                                                     )
        item_id = self.create_supply_item(name="Starter Blanket")
        row_id = s3db.supply_distribution_set_item.insert(distribution_set_id=set_id,
                                                          mode="GRA",
                                                          item_id=item_id,
                                                          quantity=1,
                                                          quantity_max=2,
                                                          )

        form = self.make_form(id=set_id,
                              organisation_id=organisation_id,
                              name="Starter Kit",
                              )
        SupplyDistributionModel.distribution_set_onvalidation(form)
        self.assertNotIn("name", form.errors)

        form = self.make_form(id=row_id,
                              distribution_set_id=set_id,
                              mode="GRA",
                              item_id=item_id,
                              quantity=1,
                              quantity_max=2,
                              )
        SupplyDistributionModel.distribution_set_item_onvalidation(form)
        self.assertEqual(dict(form.errors), {})

        SupplyDistributionModel.distribution_item_onaccept(self.make_form())
        self.assertEqual(db(s3db.supply_distribution_set_item.id == row_id).count(), 1)


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
    def testSupplyItemOnacceptUpdatesSingleCatalogLinkAndUnitPack(self):
        """Item onaccept updates the single surviving catalog link and the unit-pack label"""

        db = current.db
        s3db = current.s3db

        catalog_id = self.create_catalog()
        category_a = self.create_item_category(catalog_id,
                                               name="Food",
                                               code="FOOD",
                                               )
        category_b = self.create_item_category(catalog_id,
                                               name="Shelter",
                                               code="SHEL",
                                               )
        item_id = self.create_supply_item(catalog_id=catalog_id,
                                          item_category_id=category_a,
                                          name="Tarpaulin",
                                          um="pc",
                                          )
        self.create_catalog_item(catalog_id,
                                 item_id,
                                 item_category_id=category_a,
                                 )
        self.create_item_pack(item_id,
                              name="piece",
                              quantity=1.0,
                              )

        saved_create_next = s3db.get_config("supply_item", "create_next")
        saved_update_next = s3db.get_config("supply_item", "update_next")

        try:
            SupplyItemModel.supply_item_onaccept(self.make_form(id=item_id,
                                                                item_category_id=category_b,
                                                                um="box",
                                                                kit=True,
                                                                ))

            citem = db(s3db.supply_catalog_item.item_id == item_id).select(s3db.supply_catalog_item.catalog_id,
                                                                           s3db.supply_catalog_item.item_category_id,
                                                                           limitby=(0, 1),
                                                                           ).first()
            pack = db((s3db.supply_item_pack.item_id == item_id) &
                      (s3db.supply_item_pack.quantity == 1.0)).select(s3db.supply_item_pack.name,
                                                                      limitby=(0, 1),
                                                                      ).first()
            create_next = s3db.get_config("supply_item", "create_next")
            update_next = s3db.get_config("supply_item", "update_next")

            self.assertEqual(citem.catalog_id, catalog_id)
            self.assertEqual(citem.item_category_id, category_b)
            self.assertEqual(pack.name, s3db.supply_item.um.represent("box"))
            self.assertTrue(str(create_next).endswith("/%5Bid%5D/kit_item"))
            self.assertTrue(str(update_next).endswith("/%5Bid%5D/kit_item"))
        finally:
            s3db.configure("supply_item",
                           create_next=saved_create_next,
                           update_next=saved_update_next,
                           )

    # -------------------------------------------------------------------------
    def testSupplyItemOnacceptInfersCatalogFromCategoryAndConfiguresKitRedirect(self):
        """Item onaccept looks up the catalog via category and redirects kits to their components"""

        db = current.db
        s3db = current.s3db

        saved_create_next = s3db.get_config("supply_item", "create_next")
        saved_update_next = s3db.get_config("supply_item", "update_next")

        try:
            catalog_id = self.create_catalog(name="Kit Catalog")
            category_id = self.create_item_category(catalog_id, name="Kits", code="KIT")
            item_id = self.create_supply_item(catalog_id=catalog_id,
                                              item_category_id=category_id,
                                              name="Emergency Kit",
                                              um="set",
                                              )

            SupplyItemModel.supply_item_onaccept(self.make_form(id=item_id,
                                                                item_category_id=category_id,
                                                                um="set",
                                                                kit=True,
                                                                ))

            ctable = s3db.supply_catalog_item
            link = db(ctable.item_id == item_id).select(ctable.catalog_id,
                                                        ctable.item_category_id,
                                                        limitby=(0, 1),
                                                        ).first()
            self.assertIsNotNone(link)
            self.assertEqual(link.catalog_id, catalog_id)
            self.assertEqual(link.item_category_id, category_id)

            url = URL(args=["[id]", "kit_item"])
            self.assertEqual(s3db.get_config("supply_item", "create_next"), url)
            self.assertEqual(s3db.get_config("supply_item", "update_next"), url)
        finally:
            s3db.configure("supply_item",
                           create_next=saved_create_next,
                           update_next=saved_update_next,
                           )

    # -------------------------------------------------------------------------
    def testDistributionItemOnacceptInheritsRecipientFromDistribution(self):
        """Distribution items inherit the recipient person from the parent distribution"""

        db = current.db
        s3db = current.s3db

        site_id = self.create_office().site_id
        person_id = self.create_person(last_name="Beneficiary")
        item_id = self.create_supply_item(name="Blanket")
        pack_id = self.create_item_pack(item_id, quantity=1)

        distribution_id = s3db.supply_distribution.insert(site_id=site_id,
                                                          person_id=person_id,
                                                          )
        distribution_item_id = s3db.supply_distribution_item.insert(distribution_id=distribution_id,
                                                                    item_id=item_id,
                                                                    item_pack_id=pack_id,
                                                                    quantity=2,
                                                                    )

        SupplyDistributionModel.distribution_item_onaccept(self.make_form(id=distribution_item_id))

        row = db(s3db.supply_distribution_item.id == distribution_item_id).select(s3db.supply_distribution_item.person_id,
                                                                                   limitby=(0, 1),
                                                                                   ).first()
        self.assertEqual(row.person_id, person_id)

    # -------------------------------------------------------------------------
    def testSupplyItemOnacceptFallsBackToDefaultCatalog(self):
        """Item onaccept falls back to the default catalog when no catalog can be inferred"""

        db = current.db
        s3db = current.s3db

        catalog_id = self.create_catalog(name="Fallback Catalog")
        item_id = self.create_supply_item(catalog_id=None,
                                          item_category_id=None,
                                          name="Fallback Item",
                                          um="pc",
                                          )

        table = s3db.supply_item
        saved_default = table.catalog_id.default

        try:
            table.catalog_id.default = catalog_id
            SupplyItemModel.supply_item_onaccept(self.make_form(id=item_id,
                                                                item_category_id=None,
                                                                catalog_id=None,
                                                                um="pc",
                                                                ))
        finally:
            table.catalog_id.default = saved_default

        link = db((s3db.supply_catalog_item.item_id == item_id) &
                  (s3db.supply_catalog_item.catalog_id == catalog_id) &
                  (s3db.supply_catalog_item.deleted == False)).select(s3db.supply_catalog_item.id,
                                                                      limitby=(0, 1),
                                                                      ).first()
        self.assertIsNotNone(link)

    # -------------------------------------------------------------------------
    def testCatalogItemOnacceptAdoptsReplacementCatalogLink(self):
        """Catalog-item onaccept updates the item's home catalog when the original link is gone"""

        db = current.db
        s3db = current.s3db

        # Build one item whose original catalog item has been replaced by another same-org link
        organisation_id = self.create_organisation()
        original_catalog = self.create_catalog(organisation_id=organisation_id,
                                               name="Original Catalog",
                                               )
        replacement_catalog = self.create_catalog(organisation_id=organisation_id,
                                                  name="Replacement Catalog",
                                                  )
        original_category = self.create_item_category(original_catalog,
                                                      name="Original Category",
                                                      code="ORIG",
                                                      )
        replacement_category = self.create_item_category(replacement_catalog,
                                                         name="Replacement Category",
                                                         code="REPL",
                                                         )
        item_id = self.create_supply_item(catalog_id=original_catalog,
                                          item_category_id=original_category,
                                          name="Replacement Candidate",
                                          )
        original_link = self.create_catalog_item(original_catalog,
                                                 item_id,
                                                 item_category_id=original_category,
                                                 )
        replacement_link = self.create_catalog_item(replacement_catalog,
                                                    item_id,
                                                    item_category_id=replacement_category,
                                                    )

        db(s3db.supply_catalog_item.id == original_link).update(deleted=True)

        SupplyItemModel.catalog_item_onaccept(self.make_form(id=replacement_link,
                                                             item_id=item_id,
                                                             ))

        # The supply item must now point at the surviving replacement link
        item = db(s3db.supply_item.id == item_id).select(s3db.supply_item.catalog_id,
                                                         s3db.supply_item.item_category_id,
                                                         limitby=(0, 1),
                                                         ).first()
        self.assertEqual(item.catalog_id, replacement_catalog)
        self.assertEqual(item.item_category_id, replacement_category)

    # -------------------------------------------------------------------------
    def testCatalogItemOndeleteRestoresOriginalCatalogLinkWhenLastLinkIsRemoved(self):
        """Catalog-item ondelete recreates the original catalog link if the last same-org link disappears"""

        db = current.db
        s3db = current.s3db

        # Build one item whose only original catalog link has just been deleted
        organisation_id = self.create_organisation()
        catalog_id = self.create_catalog(organisation_id=organisation_id,
                                         name="Restored Catalog",
                                         )
        category_id = self.create_item_category(catalog_id,
                                                name="Restored Category",
                                                code="RESTORE",
                                                )
        item_id = self.create_supply_item(catalog_id=catalog_id,
                                          item_category_id=category_id,
                                          name="Restore Candidate",
                                          )
        link_id = self.create_catalog_item(catalog_id,
                                           item_id,
                                           item_category_id=category_id,
                                           )

        current.response.warning = None
        db(s3db.supply_catalog_item.id == link_id).update(deleted=True)

        SupplyItemModel.catalog_item_ondelete(Storage(item_id=item_id))

        # The callback must recreate the original catalog link and warn the user
        restored = db((s3db.supply_catalog_item.item_id == item_id) &
                      (s3db.supply_catalog_item.deleted == False),
                      ).select(s3db.supply_catalog_item.catalog_id,
                               s3db.supply_catalog_item.item_category_id,
                               limitby=(0, 1),
                               orderby=~s3db.supply_catalog_item.id,
                               ).first()
        self.assertIsNotNone(restored)
        self.assertEqual(restored.catalog_id, catalog_id)
        self.assertEqual(restored.item_category_id, category_id)
        self.assertEqual(current.response.warning, "Catalog Item restored")

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
    def testSupplyCategoryRepresentBuildsDeepHierarchyAndCatalogPrefix(self):
        """Category representations include deep parent chains and optional catalog prefixes"""

        db = current.db
        s3db = current.s3db

        catalog_id = self.create_catalog(name="Hierarchy Catalog")
        great3 = self.create_item_category(catalog_id,
                                           name="Level 6",
                                           code="L6",
                                           )
        great2 = self.create_item_category(catalog_id,
                                           name="Level 5",
                                           code="L5",
                                           )
        db(s3db.supply_item_category.id == great2).update(parent_item_category_id=great3)
        great1 = self.create_item_category(catalog_id,
                                           name="Level 4",
                                           code="L4",
                                           )
        db(s3db.supply_item_category.id == great1).update(parent_item_category_id=great2)
        grandparent = self.create_item_category(catalog_id,
                                                name="Level 3",
                                                code="L3",
                                                )
        db(s3db.supply_item_category.id == grandparent).update(parent_item_category_id=great1)
        parent = self.create_item_category(catalog_id,
                                           name="Level 2",
                                           code="L2",
                                           )
        db(s3db.supply_item_category.id == parent).update(parent_item_category_id=grandparent)
        child = self.create_item_category(catalog_id,
                                          name="Level 1",
                                          code="L1",
                                          )
        db(s3db.supply_item_category.id == child).update(parent_item_category_id=parent)

        name_repr = supply_ItemCategoryRepresent(show_catalog=True,
                                                 use_code=False,
                                                 )
        code_repr = supply_ItemCategoryRepresent(show_catalog=True,
                                                 use_code=True,
                                                 )

        row = {"supply_item_category.name": "Level 1",
               "supply_item_category.code": "L1",
               "supply_parent_item_category.name": "Level 2",
               "supply_parent_item_category.code": "L2",
               "supply_grandparent_item_category.name": "Level 3",
               "supply_grandparent_item_category.code": "L3",
               "supply_grandparent_item_category.parent_item_category_id": great1,
               "supply_catalog.name": "Hierarchy Catalog",
               }

        name_text = name_repr.represent_row(row)
        code_text = code_repr.represent_row(row)

        self.assertEqual(name_text,
                         "Hierarchy Catalog > Level 1 - Level 2 - Level 3 - Level 4 - Level 5 - Level 6")
        self.assertEqual(code_text,
                         "Hierarchy Catalog > L1-L2-L3-L4-L5-L6")

        catalog_row = dict(row)
        catalog_row["supply_grandparent_item_category.parent_item_category_id"] = None

        self.assertEqual(name_repr.represent_row(catalog_row),
                         "Hierarchy Catalog > Level 1 - Level 2 - Level 3")
        self.assertEqual(code_repr.represent_row(catalog_row),
                         "Hierarchy Catalog > L1-L2-L3")

    # -------------------------------------------------------------------------
    def testSupplyCategoryRepresentTranslatesCatalogAndAncestorFallbacks(self):
        """Category representations translate catalog and ancestor labels while falling back to codes where needed"""

        category_repr = supply_ItemCategoryRepresent(show_catalog=True,
                                                     use_code=False,
                                                     translate=True,
                                                     )

        row = {"supply_item_category.name": "Child",
               "supply_item_category.code": "CH",
               "supply_parent_item_category.name": None,
               "supply_parent_item_category.code": "PARENT",
               "supply_grandparent_item_category.name": "Grand",
               "supply_grandparent_item_category.code": "GRAND",
               "supply_grandparent_item_category.parent_item_category_id": None,
               "supply_catalog.name": "Translated Catalog",
               }

        self.assertEqual(category_repr.represent_row(row),
                         "Translated Catalog > Child - PARENT - Grand")

    # -------------------------------------------------------------------------
    def testSupplyCategoryRepresentHandlesTranslatedDeepFallbackRows(self):
        """Category representations cover translated deep fallback branches and empty deep lookups"""

        real_db = current.db

        class FakeSet:
            """Minimal DAL set stub for deep hierarchy lookups"""

            def __init__(self, row):
                self.row = row

            def select(self, *fields, **kwargs):
                return Storage(first=lambda: self.row)

        class FakeDB:
            """DAL wrapper that returns a predefined row for one select"""

            def __init__(self, db, row):
                self.supply_item_category = db.supply_item_category
                self._row = row

            def __call__(self, query):
                return FakeSet(self._row)

        category_repr = supply_ItemCategoryRepresent(show_catalog=False,
                                                     use_code=False,
                                                     translate=True,
                                                     )

        row = {"supply_item_category.name": "Child",
               "supply_item_category.code": "CH",
               "supply_parent_item_category.name": "Parent",
               "supply_parent_item_category.code": "PAR",
               "supply_grandparent_item_category.name": None,
               "supply_grandparent_item_category.code": "GRAND",
               "supply_grandparent_item_category.parent_item_category_id": 999,
               }

        current.db = FakeDB(real_db,
                            {"supply_item_category.name": "Great",
                             "supply_item_category.code": "GREAT-CODE",
                             "supply_parent_item_category.name": "Great Great",
                             "supply_parent_item_category.code": "GG-CODE",
                             "supply_grandparent_item_category.name": "Great Great Great",
                             "supply_grandparent_item_category.code": "GGG-CODE",
                             },
                            )
        try:
            translated = category_repr.represent_row(dict(row))
        finally:
            current.db = real_db

        current.db = FakeDB(real_db,
                            {"supply_item_category.name": None,
                             "supply_item_category.code": "FALLBACK-1",
                             "supply_parent_item_category.name": None,
                             "supply_parent_item_category.code": "FALLBACK-2",
                             "supply_grandparent_item_category.name": None,
                             "supply_grandparent_item_category.code": None,
                             },
                            )
        try:
            fallback = category_repr.represent_row(dict(row))
        finally:
            current.db = real_db

        current.db = FakeDB(real_db, None)
        try:
            empty_lookup = category_repr.represent_row(dict(row))
        finally:
            current.db = real_db

        self.assertEqual(translated,
                         "Child - Parent - GRAND - Great - Great Great - Great Great Great")
        self.assertEqual(fallback,
                         "Child - Parent - GRAND - FALLBACK-1 - FALLBACK-2")
        self.assertEqual(empty_lookup,
                         "Child - Parent - GRAND")

    # -------------------------------------------------------------------------
    def testSupplyRepresentersHandleFallbackRowsAndMissingNames(self):
        """Supply representers fall back cleanly when joins or names are missing"""

        s3db = current.s3db

        pack_repr = supply_ItemPackRepresent()
        pack_repr.table = s3db.supply_item_pack

        expected_um = s3db.supply_item.um.represent("pc")
        fallback = pack_repr.represent_row({"name": "box",
                                            "quantity": 2.0,
                                            })
        missing = pack_repr.represent_row({})

        category_repr = supply_ItemCategoryRepresent(show_catalog=False,
                                                     use_code=False,
                                                     translate=True,
                                                     )
        category = category_repr.represent_row({"supply_item_category.name": None,
                                                "supply_item_category.code": "GEN",
                                                "supply_parent_item_category.name": None,
                                                "supply_parent_item_category.code": None,
                                                "supply_grandparent_item_category.name": None,
                                                "supply_grandparent_item_category.code": None,
                                                "supply_grandparent_item_category.parent_item_category_id": None,
                                                })

        self.assertEqual(fallback, "box (2 %s)" % expected_um)
        self.assertEqual(missing, current.messages.UNKNOWN_OPT)
        self.assertEqual(category, "GEN")

    # -------------------------------------------------------------------------
    def testSupplyRepresentersHandleBulkLookupsAndUnitPacks(self):
        """Supply representers handle multi-row lookups and unit packs without pack suffixes"""

        s3db = current.s3db

        catalog_id = self.create_catalog(name="Lookup Catalog")
        category_a = self.create_item_category(catalog_id,
                                               name="Medical",
                                               code="MED",
                                               )
        category_b = self.create_item_category(catalog_id,
                                               name="Shelter",
                                               code="SHEL",
                                               )
        item_a = self.create_supply_item(catalog_id=catalog_id,
                                         item_category_id=category_a,
                                         name="Bandage",
                                         )
        item_b = self.create_supply_item(catalog_id=catalog_id,
                                         item_category_id=category_b,
                                         name="Tent",
                                         )
        pack_a = self.create_item_pack(item_a,
                                       name="piece",
                                       quantity=1.0,
                                       )
        self.create_item_pack(item_b,
                              name="box",
                              quantity=3.0,
                              )

        item_repr = supply_ItemRepresent(show_um=False, truncate=False)
        item_rows = item_repr.lookup_rows(None, [item_a, item_b])

        pack_repr = supply_ItemPackRepresent()
        pack_repr.table = s3db.supply_item_pack
        pack_rows = pack_repr.lookup_rows(pack_repr.table.id, [pack_a])

        category_repr = supply_ItemCategoryRepresent(show_catalog=True,
                                                     use_code=False,
                                                     )
        category_rows = category_repr.lookup_rows(None, [category_a, category_b])

        self.assertEqual(len(item_rows), 2)
        self.assertEqual(len(category_rows), 2)
        self.assertEqual(pack_repr.represent_row(pack_rows.first()), "piece")

    # -------------------------------------------------------------------------
    def testSupplyRepresentersHandleSparseRowsAndBulkPackLookups(self):
        """Supply representers handle sparse rows and multi-value pack lookups"""

        s3db = current.s3db

        item_id = self.create_supply_item(name="Sparse Item")
        current.db(s3db.supply_item.id == item_id).update(model="M1")
        pack_a = self.create_item_pack(item_id, name="box", quantity=2)
        pack_b = self.create_item_pack(item_id, name="crate", quantity=5)

        item_repr = supply_ItemRepresent()
        item_repr.table = s3db.supply_item
        pack_repr = supply_ItemPackRepresent()
        pack_repr.table = s3db.supply_item_pack

        model_only = item_repr.represent_row({"supply_item.name": "Sparse Item",
                                              "supply_item.model": "M1",
                                              "supply_brand.name": None,
                                              "supply_item.um": None,
                                              })
        brand_only = item_repr.represent_row({"supply_item.name": "Sparse Item",
                                              "supply_item.model": None,
                                              "supply_brand.name": "BrandX",
                                              "supply_item.um": None,
                                              })
        rows = pack_repr.lookup_rows(pack_repr.table.id, [pack_a, pack_b])

        self.assertIn("M1", str(model_only))
        self.assertIn("BrandX", str(brand_only))
        self.assertEqual(len(rows), 2)

    # -------------------------------------------------------------------------
    def testSupplyAutocompleteFilterSupportsGlobalInactiveCatalogScope(self):
        """Autocomplete filter can be restricted to inactive global catalogs only"""

        db = current.db
        s3db = current.s3db

        global_catalog = self.create_catalog(organisation_id=None,
                                             name="Global Inactive",
                                             )
        local_organisation = self.create_organisation()
        local_catalog = self.create_catalog(organisation_id=local_organisation,
                                            name="Local Active",
                                            )
        db(s3db.supply_catalog.id == global_catalog).update(active=False)

        global_category = self.create_item_category(global_catalog,
                                                    name="Global",
                                                    code="GLOB",
                                                    )
        local_category = self.create_item_category(local_catalog,
                                                   name="Local",
                                                   code="LOC",
                                                   )
        global_item = self.create_supply_item(catalog_id=global_catalog,
                                              item_category_id=global_category,
                                              name="Global Item",
                                              )
        local_item = self.create_supply_item(catalog_id=local_catalog,
                                             item_category_id=local_category,
                                             name="Local Item",
                                             )
        self.create_catalog_item(global_catalog,
                                 global_item,
                                 item_category_id=global_category,
                                 )
        self.create_catalog_item(local_catalog,
                                 local_item,
                                 item_category_id=local_category,
                                 )

        query = supply_item_autocomplete_filter(0, inactive=True)
        rows = db(query).select(s3db.supply_item.id)
        item_ids = {row.id for row in rows}

        self.assertIn(global_item, item_ids)
        self.assertNotIn(local_item, item_ids)

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
        expected_category = str(s3db.supply_item.item_category_id.represent(category_id))
        self.assertEqual(category, expected_category)
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

    # -------------------------------------------------------------------------
    def testSupplyItemEntityVirtualFieldsHandleMissingRecordsAndUnknownValues(self):
        """Item entity virtual fields handle missing joins, missing IDs and unknown countries"""

        db = current.db
        s3db = current.s3db
        request = current.request
        none = current.messages["NONE"]

        office = self.create_office(name="Unknown Country Office",
                                    comments=None,
                                    location_id=self.create_location(name="Unknown Country"),
                                    )
        catalog_id = self.create_catalog(organisation_id=office.organisation_id)
        category_id = self.create_item_category(catalog_id,
                                                name="Fallback Category",
                                                code="FALL",
                                                )
        item_id = self.create_supply_item(catalog_id=catalog_id,
                                          item_category_id=category_id,
                                          name="Fallback Item",
                                          )
        pack_id = self.create_item_pack(item_id, quantity=1)
        inv_item_id = self.create_inventory_item(office.site_id,
                                                 item_id,
                                                 pack_id,
                                                 quantity=1,
                                                 )

        entity_id = db(s3db.inv_inv_item.id == inv_item_id).select(s3db.inv_inv_item.item_entity_id,
                                                                   limitby=(0, 1),
                                                                   ).first().item_entity_id

        missing_item_row = Storage(supply_item_entity=Storage(item_id=999999,
                                                              item_entity_id=entity_id,
                                                              instance_type="inv_inv_item",
                                                              ))
        class MissingEntityID:
            """Row stub whose entity ID lookup raises AttributeError"""

            instance_type = "inv_inv_item"

            def __getitem__(self, key):
                raise AttributeError

        missing_entity_row = Storage(supply_item_entity=MissingEntityID())
        missing_record_row = Storage(supply_item_entity=Storage(item_id=item_id,
                                                                item_entity_id=999999,
                                                                instance_type="inv_inv_item",
                                                                ))
        unknown_country_row = Storage(supply_item_entity=Storage(item_id=item_id,
                                                                 item_entity_id=entity_id,
                                                                 instance_type="inv_inv_item",
                                                                 ))

        saved_extension = request.extension
        try:
            request.extension = "pdf"
            export_contacts = supply_item_entity_contacts(Storage(supply_item_entity=Storage(item_id=item_id,
                                                                                            item_entity_id=entity_id,
                                                                                            instance_type="inv_inv_item",
                                                                                            )))
            request.extension = "html"
            html_contacts = supply_item_entity_contacts(Storage(supply_item_entity=Storage(item_id=item_id,
                                                                                          item_entity_id=entity_id,
                                                                                          instance_type="inv_inv_item",
                                                                                          )))
        finally:
            request.extension = saved_extension

        self.assertEqual(supply_item_entity_category(Storage(supply_item_entity=Storage())), none)
        self.assertEqual(supply_item_entity_category(missing_item_row), none)
        self.assertEqual(supply_item_entity_country(missing_entity_row), None)
        self.assertEqual(supply_item_entity_organisation(missing_entity_row), None)
        self.assertEqual(supply_item_entity_contacts(missing_entity_row), None)
        self.assertEqual(supply_item_entity_status(missing_entity_row), None)
        self.assertEqual(supply_item_entity_country(unknown_country_row), current.T("Unknown"))
        self.assertEqual(supply_item_entity_organisation(missing_record_row), none)
        self.assertEqual(export_contacts, none)
        self.assertIn(none, str(html_contacts))
        self.assertIn("/office/%s" % office.id, html_contacts.attributes["_href"])
        self.assertEqual(supply_item_entity_status(missing_record_row), none)

    # -------------------------------------------------------------------------
    def testSupplyItemEntityVirtualFieldsReturnNoneForPlainObjects(self):
        """Virtual fields return None when called without a row wrapper"""

        bare = object()

        self.assertIsNone(supply_item_entity_category(bare))
        self.assertIsNone(supply_item_entity_country(bare))
        self.assertIsNone(supply_item_entity_organisation(bare))
        self.assertIsNone(supply_item_entity_contacts(bare))
        self.assertIsNone(supply_item_entity_status(bare))

    # -------------------------------------------------------------------------
    def testSupplyItemEntityVirtualFieldsRepresentProcurementContext(self):
        """Item entity virtual fields resolve procurement-plan context for planned stock"""

        db = current.db
        s3db = current.s3db
        request = current.request

        # Build one planned procurement item tied to a site with location and contacts
        location_id = self.create_location(name="Krakow", L0="Poland")
        office = self.create_office(name="Procurement Office",
                                    comments="Call procurement",
                                    location_id=location_id,
                                    )
        organisation_row = db(s3db.org_organisation.id == office.organisation_id).select(
                               s3db.org_organisation.name,
                               limitby=(0, 1),
                               ).first()
        catalog_id = self.create_catalog(organisation_id=office.organisation_id,
                                         name="Proc Catalog",
                                         )
        category_id = self.create_item_category(catalog_id,
                                                name="Shelter Kits",
                                                code="SHELTER",
                                                )
        item_id = self.create_supply_item(catalog_id=catalog_id,
                                          item_category_id=category_id,
                                          name="Family Tent",
                                          )
        pack_id = self.create_item_pack(item_id, quantity=1)
        plan_id = self.create_proc_plan(office.site_id,
                                        eta=datetime.date(2026, 5, 1),
                                        )
        plan_item_id = self.create_proc_plan_item(plan_id,
                                                  item_id,
                                                  pack_id,
                                                  quantity=10,
                                                  )

        entity_id = db(s3db.proc_plan_item.id == plan_item_id).select(s3db.proc_plan_item.item_entity_id,
                                                                       limitby=(0, 1),
                                                                       ).first().item_entity_id
        row = Storage(supply_item_entity=Storage(item_id=item_id,
                                                 item_entity_id=entity_id,
                                                 instance_type="proc_plan_item",
                                                 ))

        saved_extension = request.extension
        try:
            request.extension = "html"
            contacts = supply_item_entity_contacts(row)
        finally:
            request.extension = saved_extension

        # Planned procurement items must resolve via their procurement site context
        expected_category = str(s3db.supply_item.item_category_id.represent(category_id))
        self.assertEqual(str(supply_item_entity_category(row)), expected_category)
        self.assertEqual(supply_item_entity_country(row), "Poland")
        self.assertIn(organisation_row.name, str(supply_item_entity_organisation(row)))
        self.assertIn("Call procurement", str(contacts))
        self.assertIn("/office/%s" % office.id, contacts.attributes["_href"])
        self.assertIn("Planned", str(supply_item_entity_status(row)))
        self.assertIn("2026-05-01", str(supply_item_entity_status(row)))

    # -------------------------------------------------------------------------
    def testSupplyItemEntityVirtualFieldsRepresentIncomingTrackingContext(self):
        """Item entity virtual fields resolve incoming tracking rows through the receive site"""

        db = current.db
        s3db = current.s3db
        request = current.request

        # Build one inbound tracking item for a site with location and contacts
        location_id = self.create_location(name="Lublin", L0="Poland")
        office = self.create_office(name="Inbound Office",
                                    comments="Receive at dock 3",
                                    location_id=location_id,
                                    )
        organisation_row = db(s3db.org_organisation.id == office.organisation_id).select(
                               s3db.org_organisation.name,
                               limitby=(0, 1),
                               ).first()
        catalog_id = self.create_catalog(organisation_id=office.organisation_id,
                                         name="Inbound Catalog",
                                         )
        category_id = self.create_item_category(catalog_id,
                                                name="Food",
                                                code="FOOD",
                                                )
        item_id = self.create_supply_item(catalog_id=catalog_id,
                                          item_category_id=category_id,
                                          name="Rice",
                                          )
        pack_id = self.create_item_pack(item_id, quantity=1)
        recv_id = self.create_recv(office.site_id)
        track_item_id = self.create_track_item(item_id,
                                               pack_id,
                                               quantity=5,
                                               recv_quantity=5,
                                               recv_id=recv_id,
                                               )

        row = Storage(supply_item_entity=Storage(item_id=item_id,
                                                 item_entity_id=track_item_id,
                                                 instance_type="inv_track_item",
                                                 ))

        saved_extension = request.extension
        try:
            request.extension = "html"
            contacts = supply_item_entity_contacts(row)
        finally:
            request.extension = saved_extension

        # Incoming tracking items must resolve via the receiving site
        expected_category = str(s3db.supply_item.item_category_id.represent(category_id))
        self.assertEqual(str(supply_item_entity_category(row)), expected_category)
        self.assertEqual(supply_item_entity_country(row), "Poland")
        self.assertIn(organisation_row.name, str(supply_item_entity_organisation(row)))
        self.assertIn("Receive at dock 3", str(contacts))
        self.assertIn("/office/%s" % office.id, contacts.attributes["_href"])
        self.assertIn("On Order", str(supply_item_entity_status(row)))

    # -------------------------------------------------------------------------
    def testSupplyItemEntityStatusUsesReceiveEtaForIncomingTracking(self):
        """Incoming tracking status uses the receive record ETA rather than unrelated shipment item IDs"""

        db = current.db
        s3db = current.s3db

        # Build one inbound tracking item with an ETA on the receive record
        office = self.create_office(name="ETA Office")
        catalog_id = self.create_catalog(organisation_id=office.organisation_id)
        category_id = self.create_item_category(catalog_id,
                                                name="Medical",
                                                code="MEDICAL",
                                                )
        item_id = self.create_supply_item(catalog_id=catalog_id,
                                          item_category_id=category_id,
                                          name="IV Fluids",
                                          )
        pack_id = self.create_item_pack(item_id, quantity=1)
        recv_id = self.create_recv(office.site_id,
                                   eta=datetime.date(2026, 6, 2),
                                   )
        track_item_id = self.create_track_item(item_id,
                                               pack_id,
                                               quantity=3,
                                               recv_quantity=3,
                                               recv_id=recv_id,
                                               )

        row = Storage(supply_item_entity=Storage(item_id=item_id,
                                                 item_entity_id=track_item_id,
                                                 instance_type="inv_track_item",
                                                 ))

        # The status label must be derived from inv_recv.eta for the receiving shipment
        status = str(supply_item_entity_status(row))
        self.assertIn("Order Due", status)
        self.assertIn("2026-06-02", status)

    # -------------------------------------------------------------------------
    def testSupplyItemEntityStatusUsesGenericLabelsWithoutDates(self):
        """Item entity status falls back to generic labels when no ETA or expiry is available"""

        db = current.db
        s3db = current.s3db

        # Build one stocked item and one planned procurement without date markers
        office = self.create_office(name="Generic Status Office")
        catalog_id = self.create_catalog(organisation_id=office.organisation_id)
        category_id = self.create_item_category(catalog_id,
                                                name="Generic",
                                                code="GEN",
                                                )
        item_id = self.create_supply_item(catalog_id=catalog_id,
                                          item_category_id=category_id,
                                          name="Soap",
                                          )
        pack_id = self.create_item_pack(item_id, quantity=1)
        inv_item_id = self.create_inventory_item(office.site_id,
                                                 item_id,
                                                 pack_id,
                                                 quantity=4,
                                                 expiry_date=None,
                                                 )
        plan_id = self.create_proc_plan(office.site_id,
                                        eta=None,
                                        )
        plan_item_id = self.create_proc_plan_item(plan_id,
                                                  item_id,
                                                  pack_id,
                                                  quantity=6,
                                                  )

        stock_entity_id = db(s3db.inv_inv_item.id == inv_item_id).select(s3db.inv_inv_item.item_entity_id,
                                                                         limitby=(0, 1),
                                                                         ).first().item_entity_id
        plan_entity_id = db(s3db.proc_plan_item.id == plan_item_id).select(s3db.proc_plan_item.item_entity_id,
                                                                           limitby=(0, 1),
                                                                           ).first().item_entity_id

        stock_row = Storage(supply_item_entity=Storage(item_id=item_id,
                                                       item_entity_id=stock_entity_id,
                                                       instance_type="inv_inv_item",
                                                       ))
        plan_row = Storage(supply_item_entity=Storage(item_id=item_id,
                                                      item_entity_id=plan_entity_id,
                                                      instance_type="proc_plan_item",
                                                      ))

        self.assertEqual(str(supply_item_entity_status(stock_row)), "In Stock")
        self.assertEqual(str(supply_item_entity_status(plan_row)), "Planned Procurement")


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
    def testSupplyControllerRaises404WhenModuleDisabled(self):
        """Controller import fails with HTTP 404 when the supply module is disabled"""

        fake_settings = Storage(has_module=lambda module: False)

        with self.assertRaises(HTTP) as error:
            with self.controller("supply",
                                 function="index",
                                 overrides={"settings": fake_settings},
                                 ):
                pass

        self.assertEqual(error.exception.status, 404)

    # -------------------------------------------------------------------------
    def testSimpleCrudWrappersDelegateToCrudController(self):
        """Simple supply CRUD wrappers delegate unchanged to crud_controller"""

        with self.controller("supply", function="brand") as controller:
            brand_output = controller.module["brand"]()

        with self.controller("supply", function="catalog_item") as controller:
            catalog_item_output = controller.module["catalog_item"]()

        with self.controller("supply", function="kit_item") as controller:
            kit_item_output = controller.module["kit_item"]()

        with self.controller("supply", function="person_item") as controller:
            person_item_output = controller.module["person_item"]()

        with self.controller("supply", function="person_item_status") as controller:
            status_output = controller.module["person_item_status"]()

        with self.controller("supply", function="distribution_item") as controller:
            distribution_item_output = controller.module["distribution_item"]()

        self.assertEqual(brand_output.args, ())
        self.assertEqual(catalog_item_output.args, ())
        self.assertEqual(kit_item_output.args, ())
        self.assertEqual(person_item_output.args, ())
        self.assertEqual(status_output.args, ())
        self.assertEqual(distribution_item_output.args, ())
        self.assertEqual(distribution_item_output.kwargs["rheader"],
                         current.s3db.supply_distribution_rheader)

    # -------------------------------------------------------------------------
    def testSupplyRheadersRenderExpectedTabsAndRespectFormat(self):
        """Supply rheaders expose the expected tabs and skip non-HTML requests"""

        db = current.db
        s3db = current.s3db
        settings = current.deployment_settings

        catalog_id = self.create_catalog(name="RHeader Catalog")
        category_id = self.create_item_category(catalog_id,
                                                name="RHeader Category",
                                                code="RHC",
                                                )
        site_id = self.create_office().site_id
        item_id = self.create_supply_item(catalog_id=catalog_id,
                                          item_category_id=category_id,
                                          name="RHeader Item",
                                          )
        db(s3db.supply_item.id == item_id).update(kit=True)
        set_id = s3db.supply_distribution_set.insert(name="RHeader Set")
        distribution_id = s3db.supply_distribution.insert(site_id=site_id,
                                                          distribution_set_id=set_id,
                                                          )

        catalog = db(s3db.supply_catalog.id == catalog_id).select(s3db.supply_catalog.ALL,
                                                                  limitby=(0, 1),
                                                                  ).first()
        item = db(s3db.supply_item.id == item_id).select(s3db.supply_item.ALL,
                                                         limitby=(0, 1),
                                                         ).first()
        distribution_set = db(s3db.supply_distribution_set.id == set_id).select(s3db.supply_distribution_set.ALL,
                                                                                limitby=(0, 1),
                                                                                ).first()
        distribution = db(s3db.supply_distribution.id == distribution_id).select(s3db.supply_distribution.ALL,
                                                                                 limitby=(0, 1),
                                                                                 ).first()

        saved_catalog_header = supply_catalog_rheader.__globals__["S3ResourceHeader"]
        saved_item_header = supply_item_rheader.__globals__["S3ResourceHeader"]
        saved_distribution_header = supply_distribution_rheader.__globals__["S3ResourceHeader"]
        saved_use_alt_name = settings.supply.get("use_alt_name")
        saved_kits = settings.supply.get("kits")

        def fake_header(fields, tabs, title=None):
            """Capture rheader tabs without invoking the full UI renderer"""

            return lambda r, table=None, record=None: \
                "TABS:%s|TITLE:%s" % (",".join(str(tab[0]) for tab in tabs), title)

        supply_catalog_rheader.__globals__["S3ResourceHeader"] = fake_header
        supply_item_rheader.__globals__["S3ResourceHeader"] = fake_header
        supply_distribution_rheader.__globals__["S3ResourceHeader"] = fake_header
        settings.supply.use_alt_name = True
        settings.supply.kits = True

        try:
            catalog_header = supply_catalog_rheader(Storage(representation="html",
                                                            tablename="supply_catalog",
                                                            record=catalog,
                                                            get_vars=Storage(),
                                                            resource=Storage(table=s3db.supply_catalog),
                                                            ))
            item_header = supply_item_rheader(Storage(representation="html",
                                                      tablename="supply_item",
                                                      record=item,
                                                      get_vars=Storage(),
                                                      resource=Storage(table=s3db.supply_item),
                                                      ))
            distribution_set_header = supply_distribution_rheader(Storage(representation="html",
                                                                          tablename="supply_distribution_set",
                                                                          record=distribution_set,
                                                                          get_vars=Storage(),
                                                                          resource=Storage(table=s3db.supply_distribution_set),
                                                                          ))
            distribution_header = supply_distribution_rheader(Storage(representation="html",
                                                                      tablename="supply_distribution",
                                                                      record=distribution,
                                                                      get_vars=Storage(),
                                                                      resource=Storage(table=s3db.supply_distribution),
                                                                      ))
            distribution_item_header = supply_distribution_rheader(Storage(representation="html",
                                                                           tablename="supply_distribution_item",
                                                                           record=Storage(id=1),
                                                                           get_vars=Storage(),
                                                                           resource=Storage(table=s3db.supply_distribution_item,
                                                                                            select=lambda *args, **kwargs: Storage(rows=[{
                                                                                                "supply_distribution.person_id": "Beneficiary",
                                                                                                "supply_distribution.organisation_id": "Org",
                                                                                                "supply_distribution.site_id": "Site",
                                                                                                "supply_distribution.distribution_set_id": "Set",
                                                                                                "supply_distribution.date": "2026-03-08",
                                                                                                "supply_distribution.human_resource_id": "Staff",
                                                                                                }]),
                                                                                            ),
                                                                           ))
            catalog_pdf = supply_catalog_rheader(Storage(representation="pdf",
                                                         tablename="supply_catalog",
                                                         record=catalog,
                                                         get_vars=Storage(),
                                                         resource=Storage(table=s3db.supply_catalog),
                                                         ))
            item_pdf = supply_item_rheader(Storage(representation="pdf",
                                                   tablename="supply_item",
                                                   record=item,
                                                   get_vars=Storage(),
                                                   resource=Storage(table=s3db.supply_item),
                                                   ))
            distribution_pdf = supply_distribution_rheader(Storage(representation="pdf",
                                                                   tablename="supply_distribution_set",
                                                                   record=Storage(id=1),
                                                                   get_vars=Storage(),
                                                                   resource=Storage(table=s3db.supply_distribution_set),
                                                                   ))
        finally:
            supply_catalog_rheader.__globals__["S3ResourceHeader"] = saved_catalog_header
            supply_item_rheader.__globals__["S3ResourceHeader"] = saved_item_header
            supply_distribution_rheader.__globals__["S3ResourceHeader"] = saved_distribution_header
            settings.supply.use_alt_name = saved_use_alt_name
            settings.supply.kits = saved_kits

        self.assertIn("Edit Details", catalog_header)
        self.assertIn("Categories", catalog_header)
        self.assertIn("Catalog Items", catalog_header)
        self.assertIn("Alternative Items", item_header)
        self.assertIn("Kit Items", item_header)
        self.assertIn("In Inventories", item_header)
        self.assertIn("Basic Details", distribution_set_header)
        self.assertIn("Items", distribution_set_header)
        self.assertIn("Basic Details", distribution_header)
        self.assertIn("Item Details", distribution_item_header)
        self.assertIsNone(catalog_pdf)
        self.assertIsNone(item_pdf)
        self.assertIsNone(distribution_pdf)

    # -------------------------------------------------------------------------
    def testSupplyRheadersResolveAliasedResourcesAndEmptyDistributionRows(self):
        """Supply rheaders can resolve aliased resources and ignore empty distribution-item contexts"""

        s3db = current.s3db

        calls = []
        saved_catalog_resource = supply_catalog_rheader.__globals__["s3_rheader_resource"]
        saved_item_resource = supply_item_rheader.__globals__["s3_rheader_resource"]
        saved_distribution_resource = supply_distribution_rheader.__globals__["s3_rheader_resource"]
        saved_catalog_header = supply_catalog_rheader.__globals__["S3ResourceHeader"]
        saved_item_header = supply_item_rheader.__globals__["S3ResourceHeader"]
        saved_distribution_header = supply_distribution_rheader.__globals__["S3ResourceHeader"]
        saved_resource = s3db.resource

        def fake_resource(tablename, id=None):
            """Capture aliased resource lookups"""

            calls.append((tablename, id))
            table = s3db[tablename]
            if tablename == "supply_distribution_item":
                return Storage(table=table,
                               select=lambda *args, **kwargs: Storage(rows=[]),
                               )
            return Storage(table=table)

        def fake_header(fields, tabs, title=None):
            """Render a simple marker instead of the full UI header"""

            return lambda r, table=None, record=None: \
                "RHEADER:%s:%s" % (table._tablename, title)

        resolver = lambda r: (r.expected_tablename, r.record)

        supply_catalog_rheader.__globals__["s3_rheader_resource"] = resolver
        supply_item_rheader.__globals__["s3_rheader_resource"] = resolver
        supply_distribution_rheader.__globals__["s3_rheader_resource"] = resolver
        supply_catalog_rheader.__globals__["S3ResourceHeader"] = fake_header
        supply_item_rheader.__globals__["S3ResourceHeader"] = fake_header
        supply_distribution_rheader.__globals__["S3ResourceHeader"] = fake_header
        s3db.resource = fake_resource

        try:
            catalog = supply_catalog_rheader(Storage(representation="html",
                                                     tablename="alias_catalog",
                                                     expected_tablename="supply_catalog",
                                                     record=Storage(id=1),
                                                     resource=Storage(table=s3db.supply_catalog),
                                                     ))
            item = supply_item_rheader(Storage(representation="html",
                                               tablename="alias_item",
                                               expected_tablename="supply_item",
                                               record=Storage(id=2, kit=False),
                                               resource=Storage(table=s3db.supply_item),
                                               ))
            distribution = supply_distribution_rheader(Storage(representation="html",
                                                               tablename="alias_distribution",
                                                               expected_tablename="supply_distribution",
                                                               record=Storage(id=3),
                                                               resource=Storage(table=s3db.supply_distribution),
                                                               ))
            distribution_item = supply_distribution_rheader(Storage(representation="html",
                                                                    tablename="alias_distribution_item",
                                                                    expected_tablename="supply_distribution_item",
                                                                    record=Storage(id=4),
                                                                    resource=Storage(table=s3db.supply_distribution_item),
                                                                    ))
        finally:
            supply_catalog_rheader.__globals__["s3_rheader_resource"] = saved_catalog_resource
            supply_item_rheader.__globals__["s3_rheader_resource"] = saved_item_resource
            supply_distribution_rheader.__globals__["s3_rheader_resource"] = saved_distribution_resource
            supply_catalog_rheader.__globals__["S3ResourceHeader"] = saved_catalog_header
            supply_item_rheader.__globals__["S3ResourceHeader"] = saved_item_header
            supply_distribution_rheader.__globals__["S3ResourceHeader"] = saved_distribution_header
            s3db.resource = saved_resource

        self.assertEqual(calls,
                         [("supply_catalog", 1),
                          ("supply_item", 2),
                          ("supply_distribution", 3),
                          ("supply_distribution_item", 4),
                          ],
                         )
        self.assertEqual(catalog, "RHEADER:supply_catalog:name")
        self.assertEqual(item, "RHEADER:supply_item:name")
        self.assertEqual(distribution, "RHEADER:supply_distribution:None")
        self.assertIsNone(distribution_item)

    # -------------------------------------------------------------------------
    def testSupplyRheadersSupportExplicitTabsAndMissingRecords(self):
        """Supply rheaders honor explicit tabs and return None for missing records"""

        s3db = current.s3db

        saved_catalog_header = supply_catalog_rheader.__globals__["S3ResourceHeader"]
        saved_item_header = supply_item_rheader.__globals__["S3ResourceHeader"]
        saved_distribution_header = supply_distribution_rheader.__globals__["S3ResourceHeader"]

        def fake_header(fields, tabs, title=None):
            """Render a minimal marker for explicit tab assertions"""

            return lambda r, table=None, record=None: \
                "TABS:%s|TITLE:%s" % (",".join(str(tab[0]) for tab in tabs), title)

        supply_catalog_rheader.__globals__["S3ResourceHeader"] = fake_header
        supply_item_rheader.__globals__["S3ResourceHeader"] = fake_header
        supply_distribution_rheader.__globals__["S3ResourceHeader"] = fake_header

        try:
            missing_catalog = supply_catalog_rheader(Storage(representation="html",
                                                             tablename="supply_catalog",
                                                             record=None,
                                                             get_vars=Storage(),
                                                             resource=Storage(table=s3db.supply_catalog),
                                                             ))
            missing_item = supply_item_rheader(Storage(representation="html",
                                                       tablename="supply_item",
                                                       record=None,
                                                       get_vars=Storage(),
                                                       resource=Storage(table=s3db.supply_item),
                                                       ))
            missing_distribution = supply_distribution_rheader(Storage(representation="html",
                                                                       tablename="supply_distribution",
                                                                       record=None,
                                                                       get_vars=Storage(),
                                                                       resource=Storage(table=s3db.supply_distribution),
                                                                       ))

            catalog = supply_catalog_rheader(Storage(representation="html",
                                                     tablename="supply_catalog",
                                                     record=Storage(id=1),
                                                     get_vars=Storage(),
                                                     resource=Storage(table=s3db.supply_catalog),
                                                     ),
                                             tabs=[("Custom Catalog", None)])
            item = supply_item_rheader(Storage(representation="html",
                                               tablename="supply_item",
                                               record=Storage(id=2, kit=False),
                                               get_vars=Storage(),
                                               resource=Storage(table=s3db.supply_item),
                                               ),
                                       tabs=[("Custom Item", None)])
            distribution = supply_distribution_rheader(Storage(representation="html",
                                                               tablename="supply_distribution",
                                                               record=Storage(id=3),
                                                               get_vars=Storage(),
                                                               resource=Storage(table=s3db.supply_distribution),
                                                               ),
                                                       tabs=[("Custom Distribution", None)])
            distribution_item = supply_distribution_rheader(Storage(representation="html",
                                                                    tablename="supply_distribution_item",
                                                                    record=Storage(id=4),
                                                                    get_vars=Storage(),
                                                                    resource=Storage(table=s3db.supply_distribution_item,
                                                                                     select=lambda *args, **kwargs: Storage(rows=[{
                                                                                         "supply_distribution.person_id": "Beneficiary",
                                                                                         "supply_distribution.organisation_id": "Org",
                                                                                         "supply_distribution.site_id": "Site",
                                                                                         "supply_distribution.distribution_set_id": "Set",
                                                                                         "supply_distribution.date": "2026-03-08",
                                                                                         "supply_distribution.human_resource_id": "Staff",
                                                                                         }]),
                                                                                     ),
                                                                    ),
                                                            tabs=[("Custom Distribution Item", None)])
        finally:
            supply_catalog_rheader.__globals__["S3ResourceHeader"] = saved_catalog_header
            supply_item_rheader.__globals__["S3ResourceHeader"] = saved_item_header
            supply_distribution_rheader.__globals__["S3ResourceHeader"] = saved_distribution_header

        self.assertIsNone(missing_catalog)
        self.assertIsNone(missing_item)
        self.assertIsNone(missing_distribution)
        self.assertIn("Custom Catalog", catalog)
        self.assertIn("Custom Item", item)
        self.assertIn("Custom Distribution", distribution)
        self.assertIn("Custom Distribution Item", distribution_item)

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
    def testSupplyControllerPrepsHandleMissingOrganisationBranches(self):
        """Controller prep hooks leave widgets unchanged without organisation context"""

        s3db = current.s3db

        item_table = s3db.supply_catalog_item
        category_requires = item_table.item_category_id.requires
        item_widget = item_table.item_id.widget

        set_table = s3db.supply_distribution_set_item
        dist_table = s3db.supply_distribution_item
        saved_set_widget = set_table.item_id.widget
        saved_dist_widget = dist_table.item_id.widget

        category_table = s3db.supply_item_category
        asset_readable = category_table.can_be_asset.readable
        asset_writable = category_table.can_be_asset.writable
        parent_requires = category_table.parent_item_category_id.requires

        try:
            with self.controller("supply", function="catalog") as controller:
                prep = controller.module["catalog"]().prep
                self.assertTrue(prep(Storage(record=Storage(id=1, organisation_id=None),
                                             component_name="catalog_item",
                                             component=Storage(table=item_table),
                                             )))

            with self.controller("supply", function="distribution_set") as controller:
                prep = controller.module["distribution_set"]().prep
                self.assertTrue(prep(Storage(record=Storage(organisation_id=None),
                                             component_name="distribution_set_item",
                                             component=Storage(table=set_table),
                                             )))

            with self.controller("supply", function="distribution") as controller:
                prep = controller.module["distribution"]().prep
                self.assertTrue(prep(Storage(record=Storage(organisation_id=None),
                                             component_name="distribution_item",
                                             component=Storage(table=dist_table),
                                             )))

            with self.controller("supply", function="item_category") as controller:
                prep = controller.module["item_category"]().prep
                self.assertTrue(prep(Storage(id=None,
                                             get_vars=Storage(),
                                             table=category_table,
                                             )))
        finally:
            item_table.item_category_id.requires = category_requires
            item_table.item_id.widget = item_widget
            set_table.item_id.widget = saved_set_widget
            dist_table.item_id.widget = saved_dist_widget
            category_table.can_be_asset.readable = asset_readable
            category_table.can_be_asset.writable = asset_writable
            category_table.parent_item_category_id.requires = parent_requires

        self.assertIs(item_table.item_category_id.requires, category_requires)
        self.assertIs(item_table.item_id.widget, item_widget)
        self.assertIs(set_table.item_id.widget, saved_set_widget)
        self.assertIs(dist_table.item_id.widget, saved_dist_widget)

    # -------------------------------------------------------------------------
    def testSupplyControllerPrepsIgnoreUnrelatedComponents(self):
        """Controller prep hooks no-op outside their item subcomponents"""

        s3db = current.s3db

        catalog_table = s3db.supply_catalog_item
        set_table = s3db.supply_distribution_set_item
        dist_table = s3db.supply_distribution_item

        saved_catalog_widget = catalog_table.item_id.widget
        saved_set_widget = set_table.item_id.widget
        saved_dist_widget = dist_table.item_id.widget

        try:
            with self.controller("supply", function="catalog") as controller:
                prep = controller.module["catalog"]().prep
                self.assertTrue(prep(Storage(record=Storage(id=1, organisation_id=1),
                                             component_name="document",
                                             component=Storage(table=catalog_table),
                                             )))

            with self.controller("supply", function="distribution_set") as controller:
                prep = controller.module["distribution_set"]().prep
                self.assertTrue(prep(Storage(record=Storage(organisation_id=1),
                                             component_name="document",
                                             component=Storage(table=set_table),
                                             )))

            with self.controller("supply", function="distribution") as controller:
                prep = controller.module["distribution"]().prep
                self.assertTrue(prep(Storage(record=Storage(organisation_id=1),
                                             component_name="document",
                                             component=Storage(table=dist_table),
                                             )))
        finally:
            catalog_table.item_id.widget = saved_catalog_widget
            set_table.item_id.widget = saved_set_widget
            dist_table.item_id.widget = saved_dist_widget

        self.assertIs(catalog_table.item_id.widget, saved_catalog_widget)
        self.assertIs(set_table.item_id.widget, saved_set_widget)
        self.assertIs(dist_table.item_id.widget, saved_dist_widget)

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
    def testSupplyItemControllerPrepRejectsInvalidSearchOrg(self):
        """Item controller prep rejects invalid organisation filters for autocomplete lookups"""

        response_s3 = current.response.s3
        saved_crud_controller = current.crud_controller
        captured = {}

        def crud_controller(*args, **kwargs):
            """Capture the configured prep hook"""

            captured["prep"] = response_s3.prep
            return Storage(args=args, kwargs=kwargs)

        current.crud_controller = crud_controller
        try:
            supply_item_controller()
            prep = captured["prep"]

            with self.assertRaises(RuntimeError):
                prep(Storage(component=None,
                             method="search_ac",
                             get_vars=Storage(org="not-a-number"),
                             representation="html",
                             resource=Storage(add_filter=lambda query: None),
                             error=lambda code, message: (_ for _ in ()).throw(RuntimeError((code, message))),
                             ))
        finally:
            current.crud_controller = saved_crud_controller

    # -------------------------------------------------------------------------
    def testSupplyItemControllerPrepSupportsAssetCallersAndXlsOutput(self):
        """Item controller prep adapts category handling for asset callers and XLS exports"""

        s3db = current.s3db
        response_s3 = current.response.s3
        saved_crud_controller = current.crud_controller
        captured = {}

        field = s3db.supply_item.item_category_id
        original_requires = field.requires
        original_comment = field.comment
        original_represent = field.represent

        def crud_controller(*args, **kwargs):
            """Capture the configured prep hook"""

            captured["prep"] = response_s3.prep
            return Storage(args=args, kwargs=kwargs)

        current.crud_controller = crud_controller
        try:
            supply_item_controller()
            prep = captured["prep"]

            r = Storage(component=None,
                        method=None,
                        get_vars=Storage(caller="event_asset_item_id"),
                        representation="xlsx",
                        resource=Storage(add_filter=lambda query: None),
                        error=lambda code, message: None,
                        )
            self.assertTrue(prep(r))
        finally:
            current.crud_controller = saved_crud_controller

        try:
            self.assertIs(field.requires, original_requires.other)
            self.assertIn("assets=1", field.comment.url(format="popup"))
            self.assertIsInstance(field.represent, supply_ItemCategoryRepresent)
            self.assertFalse(field.represent.use_code)
        finally:
            field.requires = original_requires
            field.comment = original_comment
            field.represent = original_represent

    # -------------------------------------------------------------------------
    def testSupplyItemControllerPrepAddsAutocompleteFiltersWithoutOrgContext(self):
        """Item controller prep adds inactive and obsolete filters even without an organisation context"""

        response_s3 = current.response.s3
        saved_crud_controller = current.crud_controller
        captured = {}
        added_filters = []

        def crud_controller(*args, **kwargs):
            """Capture the configured prep hook"""

            captured["prep"] = response_s3.prep
            return Storage(args=args, kwargs=kwargs)

        current.crud_controller = crud_controller
        try:
            supply_item_controller()
            prep = captured["prep"]

            r = Storage(component=None,
                        method="search_ac",
                        get_vars=Storage(inactive="1"),
                        representation="html",
                        resource=Storage(add_filter=lambda query: added_filters.append(query)),
                        error=lambda code, message: None,
                        )
            self.assertTrue(prep(r))
        finally:
            current.crud_controller = saved_crud_controller

        self.assertEqual(len(added_filters), 2)
        self.assertNotEqual(str(added_filters[0]), str(added_filters[1]))

    # -------------------------------------------------------------------------
    def testSupplyItemControllerPrepConfiguresInventoryAndRequestComponents(self):
        """Item controller prep locks inventory and request components into read-only report modes"""

        s3db = current.s3db
        response_s3 = current.response.s3
        saved_crud_controller = current.crud_controller
        captured = {}

        original_inv_requires = s3db.inv_inv_item.item_pack_id.requires

        def crud_controller(*args, **kwargs):
            """Capture the configured prep hook"""

            captured["prep"] = response_s3.prep
            return Storage(args=args, kwargs=kwargs)

        current.crud_controller = crud_controller
        try:
            supply_item_controller()
            prep = captured["prep"]

            inv_record = Storage(id=42)
            self.assertTrue(prep(Storage(component=Storage(),
                                         get_vars=Storage(),
                                         component_name="inv_item",
                                         record=inv_record,
                                         )))
            self.assertTrue(prep(Storage(component=Storage(),
                                         get_vars=Storage(),
                                         component_name="req_item",
                                         record=inv_record,
                                         )))
        finally:
            current.crud_controller = saved_crud_controller

        try:
            self.assertEqual(s3db.inv_inv_item.item_pack_id.requires.ktable,
                             "supply_item_pack",
                             )
            self.assertIsInstance(s3db.inv_inv_item.item_pack_id.requires.label,
                                  type(s3db.supply_item_pack_represent),
                                  )
        finally:
            s3db.inv_inv_item.item_pack_id.requires = original_inv_requires

    # -------------------------------------------------------------------------
    def testSupplyItemControllerPrepHandlesComponentContexts(self):
        """Item controller prep configures non-empty inventory and request components"""

        s3db = current.s3db
        response_s3 = current.response.s3
        saved_crud_controller = current.crud_controller
        captured = {}

        original_inv_listadd = s3db.get_config("inv_inv_item", "listadd")
        original_inv_deletable = s3db.get_config("inv_inv_item", "deletable")
        original_req_listadd = s3db.get_config("req_req_item", "listadd")
        original_req_deletable = s3db.get_config("req_req_item", "deletable")
        original_inv_requires = s3db.inv_inv_item.item_pack_id.requires

        def crud_controller(*args, **kwargs):
            """Capture the configured prep hook"""

            captured["prep"] = response_s3.prep
            return Storage(args=args, kwargs=kwargs)

        current.crud_controller = crud_controller
        try:
            supply_item_controller()
            prep = captured["prep"]

            inv_component = Storage(name="inv-item-component")
            req_component = Storage(name="req-item-component")

            self.assertTrue(prep(Storage(component=inv_component,
                                         component_name="inv_item",
                                         record=Storage(id=42),
                                         get_vars=Storage(),
                                         )))
            self.assertTrue(prep(Storage(component=req_component,
                                         component_name="req_item",
                                         record=Storage(id=42),
                                         get_vars=Storage(),
                                         )))
        finally:
            current.crud_controller = saved_crud_controller

        try:
            self.assertFalse(s3db.get_config("inv_inv_item", "listadd"))
            self.assertFalse(s3db.get_config("inv_inv_item", "deletable"))
            self.assertFalse(s3db.get_config("req_req_item", "listadd"))
            self.assertFalse(s3db.get_config("req_req_item", "deletable"))
            self.assertEqual(s3db.inv_inv_item.item_pack_id.requires.filter_opts, (42,))
        finally:
            s3db.configure("inv_inv_item",
                           listadd=original_inv_listadd,
                           deletable=original_inv_deletable,
                           )
            s3db.configure("req_req_item",
                           listadd=original_req_listadd,
                           deletable=original_req_deletable,
                           )
            s3db.inv_inv_item.item_pack_id.requires = original_inv_requires

    # -------------------------------------------------------------------------
    def testItemEntityControllerConfiguresVirtualFieldsAndManualFilters(self):
        """item_entity controller exposes virtual report fields and manual list filters"""

        current.db.rollback()

        # Create one inventory, one incoming order and one procurement plan
        stock_location = self.create_location(name="Berlin", L0="Germany")
        stock_office = self.create_office(name="Entity Office",
                                          comments="entity contact",
                                          location_id=stock_location,
                                          )
        stock_catalog = self.create_catalog(organisation_id=stock_office.organisation_id)
        stock_category = self.create_item_category(stock_catalog,
                                                   name="Shelter",
                                                   code="SHE",
                                                   )
        stock_item = self.create_supply_item(catalog_id=stock_catalog,
                                             item_category_id=stock_category,
                                             name="Family Tent",
                                             )
        stock_pack = self.create_item_pack(stock_item, quantity=1)
        self.create_inventory_item(stock_office.site_id,
                                   stock_item,
                                   stock_pack,
                                   quantity=7,
                                   )

        recv_location = self.create_location(name="Warsaw", L0="Poland")
        recv_office = self.create_office(name="Receive Office",
                                         location_id=recv_location,
                                         )
        recv_catalog = self.create_catalog(organisation_id=recv_office.organisation_id)
        recv_category = self.create_item_category(recv_catalog,
                                                  name="Receive",
                                                  code="RECV",
                                                  )
        recv_item = self.create_supply_item(catalog_id=recv_catalog,
                                            item_category_id=recv_category,
                                            name="Water",
                                            )
        recv_pack = self.create_item_pack(recv_item, quantity=1)
        recv_id = self.create_recv(recv_office.site_id)
        self.create_track_item(recv_item,
                               recv_pack,
                               quantity=3,
                               recv_quantity=3,
                               recv_id=recv_id,
                               )

        plan_location = self.create_location(name="Prague", L0="Czechia")
        plan_office = self.create_office(name="Plan Office",
                                         location_id=plan_location,
                                         )
        plan_catalog = self.create_catalog(organisation_id=plan_office.organisation_id)
        plan_category = self.create_item_category(plan_catalog,
                                                  name="Plan",
                                                  code="PLAN",
                                                  )
        plan_item = self.create_supply_item(catalog_id=plan_catalog,
                                            item_category_id=plan_category,
                                            name="Tent",
                                            )
        plan_pack = self.create_item_pack(plan_item, quantity=1)
        plan_id = self.create_proc_plan(plan_office.site_id)
        self.create_proc_plan_item(plan_id,
                                   plan_item,
                                   plan_pack,
                                   quantity=8,
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
        self.assertIn("Germany", rheader)
        self.assertIn("Poland", rheader)
        self.assertIn("Czechia", rheader)
        self.assertIn("filterColumns", "".join(jquery_ready))

    # -------------------------------------------------------------------------
    def testItemEntityControllerPostpHandlesSelectiveModulesAndNonListViews(self):
        """item_entity postp handles module-specific filters and skips non-list views"""

        current.db.rollback()

        location_id = self.create_location(name="Unknown Country")
        office = self.create_office(name="Proc Only Office",
                                    location_id=location_id,
                                    )
        catalog_id = self.create_catalog(organisation_id=office.organisation_id)
        category_id = self.create_item_category(catalog_id,
                                                name="Proc Only Category",
                                                code="PROC-ONLY",
                                                )
        item_id = self.create_supply_item(catalog_id=catalog_id,
                                          item_category_id=category_id,
                                          name="Proc Only Item",
                                          )
        pack_id = self.create_item_pack(item_id, quantity=1)
        plan_id = self.create_proc_plan(office.site_id)
        self.create_proc_plan_item(plan_id,
                                   item_id,
                                   pack_id,
                                   quantity=2,
                                   )

        response_s3 = current.response.s3
        settings = current.deployment_settings
        saved_crud_controller = current.crud_controller
        saved_postp = response_s3.postp
        saved_no_sspag = response_s3.no_sspag
        saved_ready = list(response_s3.jquery_ready)
        saved_inv = settings.modules.pop("inv", None)
        captured = {}

        def crud_controller(*args, **kwargs):
            """Capture controller setup for assertions"""

            captured["postp"] = response_s3.postp
            return Storage(args=args, kwargs=kwargs)

        current.crud_controller = crud_controller
        response_s3.jquery_ready = []
        try:
            supply_item_entity_controller()
            postp = captured["postp"]

            passive = {"marker": "keep"}
            unchanged = postp(Storage(interactive=False, record=None), dict(passive))
            with_record = postp(Storage(interactive=True, record=Storage(id=1)), dict(passive))
            rendered = postp(Storage(interactive=True, record=None), {})
            jquery_ready = list(response_s3.jquery_ready)
        finally:
            current.crud_controller = saved_crud_controller
            response_s3.postp = saved_postp
            response_s3.no_sspag = saved_no_sspag
            response_s3.jquery_ready = saved_ready
            if saved_inv is not None:
                settings.modules["inv"] = saved_inv

        rheader = str(rendered["rheader"])

        self.assertEqual(unchanged, {"marker": "keep"})
        self.assertEqual(with_record, {"marker": "keep"})
        self.assertIn("Planned Procurement", rheader)
        self.assertNotIn("In Stock", rheader)
        self.assertIn("Unknown", rheader)
        self.assertIn("filterColumns", "".join(jquery_ready))


# =============================================================================
if __name__ == "__main__":

    run_suite(
        SupplyConfigurationTests,
        SupplyHelpersTests,
        SupplyValidationTests,
        SupplyModelTests,
        SupplyControllerTests,
    )

# END ========================================================================
