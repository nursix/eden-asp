# PROC Unit Tests
#
# To run this script use:
# python web2py.py -S eden -M -R applications/eden/modules/unit_tests/s3db/proc.py
#
import datetime
import unittest

from gluon import URL, current
from gluon.storage import Storage

from s3db.proc import PROCProcurementPlansModel, PROCPurchaseOrdersModel
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


# =============================================================================
if __name__ == "__main__":

    run_suite(
        ProcLazyLoadTests,
        ProcurementPlanModelTests,
        PurchaseOrderModelTests,
    )

# END ========================================================================
