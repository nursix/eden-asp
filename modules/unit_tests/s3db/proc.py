# PROC Unit Tests
#
# To run this script use:
# python web2py.py -S eden -M -R applications/eden/modules/unit_tests/s3db/proc.py
#
import datetime
import unittest

from gluon import HTTP, URL, current
from gluon.storage import Storage

from s3db.proc import PROCProcurementPlansModel, PROCPurchaseOrdersModel, proc_rheader
from unit_tests import run_suite
from unit_tests.s3db.helpers import SupplyChainTestCase


# =============================================================================
class ProcLazyLoadTests(SupplyChainTestCase):
    """Tests for procurement model registration and lazy loading"""

    # -------------------------------------------------------------------------
    def setUp(self):

        super().setUp()

        # Enable the module in the harness even if the template disables it
        settings = current.deployment_settings
        response = current.response
        self.proc_module = settings.modules.get("proc")
        if self.proc_module is None:
            settings.modules["proc"] = Storage(name_nice="Procurement")
            self.proc_module_added = True
        else:
            self.proc_module_added = False

        self.loaded = response.get("eden_model_load")
        if self.loaded:
            for name in ("PROCProcurementPlansModel", "PROCPurchaseOrdersModel"):
                while name in self.loaded:
                    self.loaded.remove(name)

    # -------------------------------------------------------------------------
    def tearDown(self):

        if self.proc_module_added:
            del current.deployment_settings.modules["proc"]

        super().tearDown()

    # -------------------------------------------------------------------------
    def testProcPurchaseOrderModelNamesAndLazyLoad(self):
        """Purchase order model exposes both component tables and lazy-loads them"""

        # Verify the model now registers both component tables separately
        self.assertEqual(PROCPurchaseOrdersModel.names,
                         ("proc_order", "proc_order_item", "proc_order_tag"))

        # Accessing the tables through the model loader must succeed
        self.assertIsNotNone(current.s3db.proc_order)
        self.assertIsNotNone(current.s3db.table("proc_order_item"))
        self.assertIsNotNone(current.s3db.table("proc_order_tag"))


# =============================================================================
class ProcTestCase(SupplyChainTestCase):
    """Base class that enables and loads the procurement module"""

    # -------------------------------------------------------------------------
    def setUp(self):

        super().setUp()

        # Enable and reload procurement models for every isolated test
        settings = current.deployment_settings
        response = current.response
        self.proc_module = settings.modules.get("proc")
        if self.proc_module is None:
            settings.modules["proc"] = Storage(name_nice="Procurement")
            self.proc_module_added = True
        else:
            self.proc_module_added = False

        loaded = response.get("eden_model_load")
        if loaded:
            for name in ("PROCProcurementPlansModel", "PROCPurchaseOrdersModel"):
                while name in loaded:
                    loaded.remove(name)

        PROCProcurementPlansModel("proc")
        PROCPurchaseOrdersModel("proc")

    # -------------------------------------------------------------------------
    def tearDown(self):

        settings = current.deployment_settings
        if self.proc_module_added:
            del settings.modules["proc"]

        super().tearDown()


# =============================================================================
class ProcurementPlanModelTests(ProcTestCase):
    """Tests for procurement plan configuration and representation"""

    # -------------------------------------------------------------------------
    def testProcPlanConfiguration(self):
        """proc_plan redirects to plan items after create and update"""

        s3db = current.s3db

        expected = URL(f="plan", args=["[id]", "plan_item"])
        self.assertEqual(s3db.get_config("proc_plan", "create_next"), expected)
        self.assertEqual(s3db.get_config("proc_plan", "update_next"), expected)

    # -------------------------------------------------------------------------
    def testProcPlanRepresent(self):
        """proc_plan representation includes site and order date"""

        db = current.db

        # Create one procurement plan with a deterministic order date
        office = self.create_office(name="Proc Plan Office")
        order_date = datetime.date(2026, 3, 6)
        plan_table = db.proc_plan
        plan_id = plan_table.insert(site_id=office.site_id,
                                    order_date=order_date,
                                    )

        representation = PROCProcurementPlansModel.proc_plan_represent(plan_id)
        expected = "%s (%s)" % (plan_table.site_id.represent(office.site_id),
                                plan_table.order_date.represent(order_date),
                                )

        # Representation must combine site and planned order date
        self.assertEqual(representation, expected)

    # -------------------------------------------------------------------------
    def testProcPlanRepresentHandlesRowsAndMissingValues(self):
        """proc_plan representation handles inline rows, empty values and unknown IDs"""

        db = current.db

        office = self.create_office(name="Proc Plan Fallback Office")
        order_date = datetime.date(2026, 3, 8)
        plan_table = db.proc_plan

        row = Storage(site_id=office.site_id,
                      order_date=order_date,
                      )
        inline = PROCProcurementPlansModel.proc_plan_represent(1, row=row)
        expected = "%s (%s)" % (plan_table.site_id.represent(office.site_id),
                                plan_table.order_date.represent(order_date),
                                )

        self.assertEqual(inline, expected)
        self.assertEqual(PROCProcurementPlansModel.proc_plan_represent(None),
                         current.messages["NONE"])
        self.assertEqual(PROCProcurementPlansModel.proc_plan_represent(99999999),
                         current.messages.UNKNOWN_OPT)

    # -------------------------------------------------------------------------
    def testProcPlanModelDoesNotExposeDisabledDefaults(self):
        """Procurement-plan model does not define extra defaults helpers"""

        self.assertIsNone(PROCProcurementPlansModel("proc").defaults())


# =============================================================================
class PurchaseOrderModelTests(ProcTestCase):
    """Tests for purchase order configuration and numbering"""

    # -------------------------------------------------------------------------
    def testProcOrderConfiguration(self):
        """proc_order redirects to order items after create and update"""

        s3db = current.s3db

        expected = URL(f="order", args=["[id]", "order_item"])
        self.assertEqual(s3db.get_config("proc_order", "create_next"), expected)
        self.assertEqual(s3db.get_config("proc_order", "update_next"), expected)

    # -------------------------------------------------------------------------
    def testProcOrderOnacceptGeneratesPurchaseRef(self):
        """proc_order_onaccept generates sequential purchase references"""

        db = current.db

        # Create an order without a purchase reference
        office = self.create_office(code="PO1")
        order_table = db.proc_order
        order_id = order_table.insert(site_id=office.site_id)

        PROCPurchaseOrdersModel.proc_order_onaccept(Storage(vars=Storage(id=order_id)))

        order = db(order_table.id == order_id).select(order_table.purchase_ref,
                                                      limitby=(0, 1),
                                                      ).first()
        shortname = current.deployment_settings.get_proc_shortname()

        # The callback must generate the next site-specific purchase reference
        self.assertTrue(order.purchase_ref.startswith("%s-PO1-" % shortname))
        self.assertTrue(order.purchase_ref.endswith("000001"))

    # -------------------------------------------------------------------------
    def testProcOrderOnacceptDoesNotOverwriteExistingRef(self):
        """proc_order_onaccept is idempotent once a purchase_ref exists"""

        db = current.db

        office = self.create_office(code="PO2")
        order_table = db.proc_order
        order_id = order_table.insert(site_id=office.site_id,
                                      purchase_ref="PRESET-REF",
                                      )

        PROCPurchaseOrdersModel.proc_order_onaccept(Storage(vars=Storage(id=order_id)))

        order = db(order_table.id == order_id).select(order_table.purchase_ref,
                                                      limitby=(0, 1),
                                                      ).first()
        self.assertEqual(order.purchase_ref, "PRESET-REF")

    # -------------------------------------------------------------------------
    def testProcOrderDefaultsExposeDummyField(self):
        """Disabled procurement-order defaults expose the dummy field template"""

        defaults = PROCPurchaseOrdersModel("proc").defaults()

        self.assertEqual(defaults["proc_order_id"]().name, "order_id")


# =============================================================================
class ProcurementControllerTests(ProcTestCase):
    """Tests for procurement controller wrappers"""

    # -------------------------------------------------------------------------
    def testProcIndexUsesCmsIndex(self):
        """Module home controller delegates to cms_index with the proc module"""

        s3db = current.s3db
        saved = s3db.cms_index
        s3db.cms_index = lambda module: Storage(module=module)

        try:
            with self.controller("proc", function="index") as controller:
                output = controller.module["index"]()
        finally:
            s3db.cms_index = saved

        self.assertEqual(output.module, "proc")

    # -------------------------------------------------------------------------
    def testProcControllerRaises404WhenModuleDisabled(self):
        """Controller import fails with HTTP 404 when the procurement module is disabled"""

        fake_settings = Storage(has_module=lambda module: False)

        with self.assertRaises(HTTP) as error:
            with self.controller("proc",
                                 function="index",
                                 overrides={"settings": fake_settings},
                                 ):
                pass

        self.assertEqual(error.exception.status, 404)

    # -------------------------------------------------------------------------
    def testProcOrderControllerUsesProcRheader(self):
        """order controller configures rheader and hides filters"""

        with self.controller("proc", function="order") as controller:
            output = controller.module["order"]()

        self.assertEqual(output.kwargs["rheader"], current.s3db.proc_rheader)
        self.assertTrue(output.kwargs["hide_filter"])

    # -------------------------------------------------------------------------
    def testProcRheaderRendersOrderAndPlanSummaries(self):
        """proc_rheader renders the expected summary blocks for orders and plans"""

        db = current.db
        s3db = current.s3db

        office = self.create_office(name="Proc Rheader Office")
        order_table = s3db.proc_order
        order_id = order_table.insert(site_id=office.site_id,
                                      purchase_ref="PO-RHDR-001",
                                      )
        order_record = db(order_table.id == order_id).select(order_table.ALL,
                                                             limitby=(0, 1),
                                                             ).first()

        plan_table = s3db.proc_plan
        plan_id = plan_table.insert(site_id=office.site_id,
                                    order_date=datetime.date(2026, 3, 7),
                                    eta=datetime.date(2026, 3, 20),
                                    )
        plan_record = db(plan_table.id == plan_id).select(plan_table.ALL,
                                                          limitby=(0, 1),
                                                          ).first()

        saved_tabs = proc_rheader.__globals__["s3_rheader_tabs"]
        proc_rheader.__globals__["s3_rheader_tabs"] = lambda r, tabs: \
            "PROC-TABS:%s" % ",".join(tab[1] or "" for tab in tabs)
        try:
            order_rheader = proc_rheader(Storage(representation="html",
                                                 record=order_record,
                                                 tablename="proc_order",
                                                 table=order_table,
                                                 ))
            plan_rheader = proc_rheader(Storage(representation="html",
                                                record=plan_record,
                                                tablename="proc_plan",
                                                table=plan_table,
                                                ))
        finally:
            proc_rheader.__globals__["s3_rheader_tabs"] = saved_tabs

        self.assertIn("PO-RHDR-001", str(order_rheader))
        self.assertIn("PROC-TABS:,order_item", str(order_rheader))
        self.assertIn("PROC-TABS:,plan_item", str(plan_rheader))
        self.assertIn(str(plan_table.eta.represent(plan_record.eta)), str(plan_rheader))

    # -------------------------------------------------------------------------
    def testProcRheaderReturnsNoneWithoutHtmlOrRecord(self):
        """proc_rheader ignores non-HTML views and missing records"""

        self.assertIsNone(proc_rheader(Storage(representation="pdf",
                                               record=Storage(id=1),
                                               tablename="proc_order",
                                               )))
        self.assertIsNone(proc_rheader(Storage(representation="html",
                                               record=None,
                                               tablename="proc_plan",
                                               )))

    # -------------------------------------------------------------------------
    def testProcRheaderIgnoresUnknownTables(self):
        """proc_rheader ignores HTML records from unrelated resources"""

        rheader = proc_rheader(Storage(representation="html",
                                       record=Storage(id=1),
                                       tablename="proc_unknown",
                                       table=Storage(),
                                       ))

        self.assertIsNone(rheader)

    # -------------------------------------------------------------------------
    def testProcPlanControllerUsesProcRheader(self):
        """plan controller configures rheader and hides filters"""

        with self.controller("proc", function="plan") as controller:
            output = controller.module["plan"]()

        self.assertEqual(output.kwargs["rheader"], current.s3db.proc_rheader)
        self.assertTrue(output.kwargs["hide_filter"])

    # -------------------------------------------------------------------------
    def testProcSupplierControllerDelegatesToOrganisationCrud(self):
        """supplier controller exposes the supplier CRUD view on organisations"""

        with self.controller("proc", function="supplier") as controller:
            output = controller.module["supplier"]()

        self.assertEqual(output.args, ("org", "organisation"))


# =============================================================================
if __name__ == "__main__":

    run_suite(
        ProcLazyLoadTests,
        ProcurementPlanModelTests,
        PurchaseOrderModelTests,
        ProcurementControllerTests,
    )

# END ========================================================================
