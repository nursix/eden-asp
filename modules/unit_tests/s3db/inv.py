# INV Unit Tests
#
# To run this script use:
# python web2py.py -S eden -M -R applications/eden/modules/unit_tests/s3db/inv.py
#
import datetime
import unittest

from gluon import A, B, current
from gluon.storage import Storage

from s3db.inv import (inv_item_total_volume,
                      inv_item_total_weight,
                      inv_stock_movements,
                      inv_track_item_quantity_needed,
                      InventoryTrackingModel,
                      inv_InvItemRepresent,
                      )
from unit_tests import run_suite
from unit_tests.s3db.helpers import SupplyChainTestCase


# =============================================================================
class InventoryRepresentationTests(SupplyChainTestCase):
    """Tests for inventory representations and reference helpers"""

    # -------------------------------------------------------------------------
    def testSendAndReceiveRepresentations(self):
        """Shipment representers include site, date and PDF links"""

        # Create matching send/receive documents between two sites
        office = self.create_office(name="Origin")
        destination = self.create_office(name="Destination")

        send_id = self.create_send(office.site_id,
                                   to_site_id=destination.site_id,
                                   send_ref="WB-001",
                                   date=datetime.date(2026, 3, 6),
                                   )
        recv_id = self.create_recv(destination.site_id,
                                   from_site_id=office.site_id,
                                   recv_ref="GRN-001",
                                   date=datetime.date(2026, 3, 7),
                                   )

        # Verify the rich send/receive representations
        send_repr = InventoryTrackingModel.inv_send_represent(send_id)
        self.assertTrue(isinstance(send_repr, A))
        self.assertEqual(send_repr.attributes["_href"],
                         "/%s/inv/send/%s" % (current.request.application, send_id))
        self.assertIn("WB-001", str(send_repr))
        expected_destination = str(current.s3db.inv_send.to_site_id.represent(destination.site_id,
                                                                              show_link=False,
                                                                              ))
        self.assertIn(expected_destination, str(send_repr))

        recv_repr = InventoryTrackingModel.inv_recv_represent(recv_id)
        self.assertTrue(isinstance(recv_repr, A))
        self.assertEqual(recv_repr.attributes["_href"],
                         "/%s/inv/recv/%s" % (current.request.application, recv_id))
        self.assertIn("GRN-001", str(recv_repr))
        expected_origin = str(current.s3db.inv_recv.from_site_id.represent(office.site_id,
                                                                           show_link=False,
                                                                           ))
        self.assertIn(expected_origin, str(recv_repr))

        send_ref = InventoryTrackingModel.inv_send_ref_represent("WB-001", show_link=True)
        self.assertTrue(isinstance(send_ref, A))
        self.assertEqual(send_ref.attributes["_href"],
                         "/%s/inv/send/%s/form" % (current.request.application, send_id))
        self.assertEqual(InventoryTrackingModel.inv_send_ref_represent("WB-001", show_link=False),
                         "WB-001")

        recv_ref = InventoryTrackingModel.inv_recv_ref_represent("GRN-001", show_link=True)
        self.assertTrue(isinstance(recv_ref, A))
        self.assertEqual(recv_ref.attributes["_href"],
                         "/%s/inv/recv/%s/form" % (current.request.application, recv_id))
        recv_ref_plain = InventoryTrackingModel.inv_recv_ref_represent("GRN-001", show_link=False)
        self.assertTrue(isinstance(recv_ref_plain, B))
        self.assertEqual(recv_ref_plain.components[0], "GRN-001")

    # -------------------------------------------------------------------------
    def testInventoryItemRepresentIncludesSourceOwnerAndBin(self):
        """Inventory item representation includes joined item context"""

        # Create one inventory record with all optional context fields
        office = self.create_office()
        item_id = self.create_supply_item(name="Medical Kit")
        pack_id = self.create_item_pack(item_id, quantity=1)
        inv_item_id = self.create_inventory_item(office.site_id,
                                                 item_id,
                                                 pack_id,
                                                 quantity=5,
                                                 item_source_no="SRC-1",
                                                 bin="A1",
                                                 owner_org_id=office.organisation_id,
                                                 )

        renderer = inv_InvItemRepresent()
        renderer.table = current.s3db.inv_inv_item
        rows = renderer.lookup_rows(renderer.table.id, [inv_item_id])
        representation = str(renderer.represent_row(rows.first()))

        # Verify the representation includes the joined stock context
        self.assertIn("Medical Kit", representation)
        self.assertIn("SRC-1", representation)
        self.assertIn("A1", representation)


# =============================================================================
class WarehouseValidationTests(SupplyChainTestCase):
    """Tests for warehouse validators"""

    # -------------------------------------------------------------------------
    def testWarehouseCodeValidationUsesWarehouseTable(self):
        """Warehouse code validation ignores warehouse types and rejects duplicates"""

        s3db = current.s3db

        # A warehouse type with the same name must not block the warehouse code
        wt_table = s3db.inv_warehouse_type
        wt_table.insert(name="WH001")

        code_field = s3db.inv_warehouse.code

        value, error = code_field.validate("WH001")
        self.assertEqual(value, "WH001")
        self.assertEqual(error, None)

        # A real warehouse with the same code must be rejected
        self.create_warehouse(code="WH001")

        value, error = code_field.validate("WH001")
        self.assertEqual(value, "WH001")
        self.assertNotEqual(error, None)


# =============================================================================
class InventoryMeasureComputationTests(SupplyChainTestCase):
    """Tests for inventory quantity, weight and volume helpers"""

    # -------------------------------------------------------------------------
    def testInvItemTotalsUsePackMetrics(self):
        """Inventory item totals use weight and volume from item packs"""

        # Build one inventory row with explicit pack metrics
        office = self.create_office()
        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id,
                                        quantity=10,
                                        weight=2.5,
                                        volume=0.75,
                                        )
        inv_item_id = self.create_inventory_item(office.site_id,
                                                 item_id,
                                                 pack_id,
                                                 quantity=4,
                                                 )

        row = Storage(inv_inv_item=Storage(id=inv_item_id, quantity=4),
                      supply_item_pack=Storage(weight=2.5, volume=0.75),
                      )

        # Weight and volume must be derived from the pack, not the item
        self.assertEqual(inv_item_total_weight(row), 10.0)
        self.assertEqual(inv_item_total_volume(row), 3.0)

    # -------------------------------------------------------------------------
    def testInvItemTotalsFallbackToPackLookup(self):
        """Inventory item totals can reload pack metrics from the database"""

        office = self.create_office()
        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id,
                                        quantity=6,
                                        weight=1.25,
                                        volume=0.5,
                                        )
        inv_item_id = self.create_inventory_item(office.site_id,
                                                 item_id,
                                                 pack_id,
                                                 quantity=3,
                                                 )

        row = Storage(inv_inv_item=Storage(id=inv_item_id, quantity=3))

        self.assertEqual(inv_item_total_weight(row), 3.75)
        self.assertEqual(inv_item_total_volume(row), 1.5)

    # -------------------------------------------------------------------------
    def testTrackItemTotalsUsePackMetrics(self):
        """Track item totals use pack metrics for sent and received quantities"""

        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id,
                                        quantity=8,
                                        weight=2.0,
                                        volume=1.2,
                                        )
        track_item_id = self.create_track_item(item_id,
                                               pack_id,
                                               quantity=3,
                                               recv_quantity=2,
                                               )

        row = Storage(inv_track_item=Storage(id=track_item_id,
                                             quantity=3,
                                             recv_quantity=2,
                                             ),
                      supply_item_pack=Storage(weight=2.0, volume=1.2),
                      )

        self.assertEqual(InventoryTrackingModel.inv_track_item_total_weight(row), 6.0)
        self.assertEqual(InventoryTrackingModel.inv_track_item_total_volume(row), 3.6)
        self.assertEqual(InventoryTrackingModel.inv_track_item_total_weight(row, received=True), 4.0)
        self.assertEqual(InventoryTrackingModel.inv_track_item_total_volume(row, received=True), 2.4)

    # -------------------------------------------------------------------------
    def testTrackItemTotalsFallbackToPackLookup(self):
        """Track item totals can reload pack metrics from the database"""

        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id,
                                        quantity=5,
                                        weight=1.5,
                                        volume=0.4,
                                        )
        track_item_id = self.create_track_item(item_id,
                                               pack_id,
                                               quantity=4,
                                               recv_quantity=1,
                                               )

        row = Storage(inv_track_item=Storage(id=track_item_id,
                                             quantity=4,
                                             recv_quantity=1,
                                             ))

        self.assertEqual(InventoryTrackingModel.inv_track_item_total_weight(row), 6.0)
        self.assertEqual(InventoryTrackingModel.inv_track_item_total_volume(row), 1.6)

    # -------------------------------------------------------------------------
    def testTrackItemTotalsFallbackToTrackItemLookupForReceivedQuantities(self):
        """Received totals reload recv_quantity from inv_track_item, not inv_inv_item"""

        # Pass a row shape that forces the fallback branch for recv_quantity
        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id,
                                        quantity=5,
                                        weight=1.25,
                                        volume=0.5,
                                        )
        track_item_id = self.create_track_item(item_id,
                                               pack_id,
                                               quantity=4,
                                               recv_quantity=3,
                                               )

        class KeyErrorRow(dict):

            __getattr__ = dict.__getitem__

        row = Storage(inv_track_item=KeyErrorRow(id=track_item_id))

        # The helper must read recv_quantity from inv_track_item
        self.assertEqual(InventoryTrackingModel.inv_track_item_total_weight(row, received=True), 3.75)
        self.assertEqual(InventoryTrackingModel.inv_track_item_total_volume(row, received=True), 1.5)

    # -------------------------------------------------------------------------
    def testTrackItemTotalValueUsesPackValue(self):
        """Track item total value multiplies quantity with pack value"""

        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id, quantity=1)
        track_item_id = self.create_track_item(item_id,
                                               pack_id,
                                               quantity=4,
                                               pack_value=2.25,
                                               )

        row = Storage(inv_track_item=Storage(id=track_item_id,
                                             quantity=4,
                                             pack_value=2.25,
                                             ))
        self.assertEqual(InventoryTrackingModel.inv_track_item_total_value(row), 9.0)


# =============================================================================
class InventoryWorkflowTests(SupplyChainTestCase):
    """Tests for inventory workflow callbacks"""

    # -------------------------------------------------------------------------
    def testInvSendOnacceptCreatesReferenceAndTypedTrackItems(self):
        """Send onaccept generates a reference and includes typed stock items"""

        db = current.db
        s3db = current.s3db

        # Create stock to be pulled into a typed shipment
        office = self.create_office()
        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id, quantity=1)
        inv_item_id = self.create_inventory_item(office.site_id,
                                                 item_id,
                                                 pack_id,
                                                 quantity=5,
                                                 status=7,
                                                 currency="USD",
                                                 pack_value=4.5,
                                                 )
        send_id = self.create_send(office.site_id,
                                   type=7,
                                   send_ref=None,
                                   )

        saved = s3db.inv_track_item_onaccept
        s3db.inv_track_item_onaccept = lambda form: None
        try:
            # Prevent the nested onaccept from mutating unrelated stock state
            InventoryTrackingModel.inv_send_onaccept(self.make_form(id=send_id,
                                                                    site_id=office.site_id,
                                                                    type=7,
                                                                    ))
        finally:
            s3db.inv_track_item_onaccept = saved

        # Verify the generated shipment header and copied track item
        send = db(s3db.inv_send.id == send_id).select(s3db.inv_send.send_ref,
                                                      limitby=(0, 1),
                                                      ).first()
        self.assertTrue(send.send_ref)

        rows = db(s3db.inv_track_item.send_id == send_id).select(s3db.inv_track_item.send_inv_item_id,
                                                                 s3db.inv_track_item.quantity,
                                                                 limitby=(0, 1),
                                                                 )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.first().send_inv_item_id, inv_item_id)
        self.assertEqual(rows.first().quantity, 5)

    # -------------------------------------------------------------------------
    def testInvRecvOnacceptAndOnvalidation(self):
        """Receive callbacks generate refs and validate shipment sources"""

        db = current.db
        s3db = current.s3db

        # Generate a receive reference for a new inbound shipment
        office = self.create_office()
        recv_id = self.create_recv(office.site_id, recv_ref=None)
        InventoryTrackingModel.inv_recv_onaccept(self.make_form(id=recv_id))

        recv = db(s3db.inv_recv.id == recv_id).select(s3db.inv_recv.recv_ref,
                                                      limitby=(0, 1),
                                                      ).first()
        self.assertTrue(recv.recv_ref)

        # Internal shipments require a source site
        form = self.make_form(type=11)
        InventoryTrackingModel.inv_recv_onvalidation(form)
        self.assertIn("from_site_id", form.errors)

        # External supplier shipments require an organisation
        form = self.make_form(type=32)
        InventoryTrackingModel.inv_recv_onvalidation(form)
        self.assertIn("organisation_id", form.errors)

    # -------------------------------------------------------------------------
    def testInvSendOnvalidationRequiresDestinationSiteOrOrganisation(self):
        """Send validation rejects shipments without any destination entity"""

        form = self.make_form(to_site_id=None, organisation_id=None)
        InventoryTrackingModel.inv_send_onvalidation(form)

        # Both destination fields should receive the same validation error
        self.assertIn("to_site_id", form.errors)
        self.assertIn("organisation_id", form.errors)

    # -------------------------------------------------------------------------
    def testInvTrackItemOnvalidateCopiesFieldsFromInventory(self):
        """Track item validation copies immutable stock item details"""

        # Use an inventory row with context fields that must be copied to tracking
        office = self.create_office()
        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id, quantity=1)
        inv_item_id = self.create_inventory_item(office.site_id,
                                                 item_id,
                                                 pack_id,
                                                 quantity=5,
                                                 item_source_no="SRC-42",
                                                 bin="B-7",
                                                 owner_org_id=office.organisation_id,
                                                 )

        form = self.make_form(send_inv_item_id=inv_item_id)
        InventoryTrackingModel.inv_track_item_onvalidate(form)

        self.assertEqual(form.vars.item_id, item_id)
        self.assertEqual(form.vars.item_source_no, "SRC-42")
        self.assertEqual(form.vars.bin, "B-7")
        self.assertEqual(form.vars.owner_org_id, office.organisation_id)

    # -------------------------------------------------------------------------
    def testInvTrackItemOnvalidateDefaultsReceivedQuantity(self):
        """Track item validation defaults recv_quantity to the shipped quantity"""

        form = self.make_form(quantity=7,
                              recv_quantity=None,
                              recv_bin=None,
                              send_inv_item_id=None,
                              )
        InventoryTrackingModel.inv_track_item_onvalidate(form)

        # Direct receipts without a linked send record default to full receipt
        self.assertEqual(form.vars.recv_quantity, 7)

    # -------------------------------------------------------------------------
    def testInvTrackItemDeletingRestoresStockAndTransit(self):
        """Deleting a preparing track item restores stock and request transit quantity"""

        db = current.db
        s3db = current.s3db

        # Create a preparing shipment line linked to both stock and request
        office = self.create_office()
        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id, quantity=1)
        inv_item_id = self.create_inventory_item(office.site_id,
                                                 item_id,
                                                 pack_id,
                                                 quantity=10,
                                                 comments="Stock comment",
                                                 )
        req_id = self.create_request(office.site_id)
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=6,
                                               quantity_transit=5,
                                               )
        track_item_id = self.create_track_item(item_id,
                                               pack_id,
                                               quantity=3,
                                               req_item_id=req_item_id,
                                               send_inv_item_id=inv_item_id,
                                               status=1,
                                               )

        self.assertTrue(InventoryTrackingModel.inv_track_item_deleting(track_item_id))

        # Verify stock, transit quantity and tracking row were rolled back
        inv_item = db(s3db.inv_inv_item.id == inv_item_id).select(s3db.inv_inv_item.quantity,
                                                                  limitby=(0, 1),
                                                                  ).first()
        self.assertEqual(inv_item.quantity, 13)

        req_item = db(s3db.req_req_item.id == req_item_id).select(s3db.req_req_item.quantity_transit,
                                                                  limitby=(0, 1),
                                                                  ).first()
        self.assertEqual(req_item.quantity_transit, 2)

        track_item = db(s3db.inv_track_item.id == track_item_id).select(s3db.inv_track_item.quantity,
                                                                        limitby=(0, 1),
                                                                        ).first()
        self.assertEqual(track_item.quantity, 0)


# =============================================================================
class InventoryReportTests(SupplyChainTestCase):
    """Tests for stock movement report extraction"""

    # -------------------------------------------------------------------------
    def testInvStockMovementsComputesOriginalAndFinalQuantities(self):
        """Stock movement report combines in-range and post-range movements correctly"""

        # Assemble report data with both in-range and post-range movements
        incoming_site = self.create_office(name="Incoming Site")
        outgoing_site = self.create_office(name="Outgoing Site")

        inv_item_id = 101
        latest = current.request.utcnow
        initial_rows = [{"_row": {"inv_inv_item.id": inv_item_id,
                                  "inv_inv_item.quantity": 10,
                                  },
                         "inv_inv_item.quantity": 10,
                         }]
        incoming_rows = [{"_row": {"inv_track_item.recv_inv_item_id": inv_item_id,
                                   "inv_track_item.recv_quantity": 4,
                                   "inv_recv.date": latest - datetime.timedelta(days=1),
                                   "inv_recv.from_site_id": incoming_site.site_id,
                                   "inv_recv.recv_ref": "GRN-1",
                                   }},
                         {"_row": {"inv_track_item.recv_inv_item_id": inv_item_id,
                                   "inv_track_item.recv_quantity": 1,
                                   "inv_recv.date": latest + datetime.timedelta(days=1),
                                   "inv_recv.from_site_id": incoming_site.site_id,
                                   "inv_recv.recv_ref": "GRN-2",
                                   }},
                         ]
        outgoing_rows = [{"_row": {"inv_track_item.send_inv_item_id": inv_item_id,
                                   "inv_track_item.quantity": 2,
                                   "inv_send.date": latest - datetime.timedelta(days=1),
                                   "inv_send.to_site_id": outgoing_site.site_id,
                                   "inv_send.send_ref": "WB-1",
                                   }},
                         {"_row": {"inv_track_item.send_inv_item_id": inv_item_id,
                                   "inv_track_item.quantity": 3,
                                   "inv_send.date": latest + datetime.timedelta(days=1),
                                   "inv_send.to_site_id": outgoing_site.site_id,
                                   "inv_send.send_ref": "WB-2",
                                   }},
                         ]

        class FakeResource:

            def __init__(self, rows):
                self._rows = rows

            def select(self, *fields, **kwargs):
                return Storage(rows=list(self._rows))

        s3db = current.s3db
        request = current.request
        saved_resource = s3db.resource
        saved_get_vars = request.get_vars

        resources = [FakeResource(incoming_rows), FakeResource(outgoing_rows)]
        s3db.resource = lambda *args, **kwargs: resources.pop(0)
        request.get_vars = Storage()

        try:
            rows = inv_stock_movements(FakeResource(initial_rows), [], None)
        finally:
            s3db.resource = saved_resource
            request.get_vars = saved_get_vars

        # Only in-range movements must affect the report totals
        self.assertEqual(len(rows), 1)
        row = rows[0]

        self.assertEqual(row["inv_inv_item.original_quantity"], 10)
        self.assertEqual(row["inv_inv_item.quantity_in"], 4)
        self.assertEqual(row["inv_inv_item.quantity_out"], 2)
        self.assertEqual(row["inv_inv_item.quantity"], 12)
        self.assertIn("GRN-1", row["inv_inv_item.documents"])
        self.assertIn("WB-1", row["inv_inv_item.documents"])
        self.assertNotIn("GRN-2", row["inv_inv_item.documents"])
        self.assertNotIn("WB-2", row["inv_inv_item.documents"])


# =============================================================================
class TrackItemQuantityNeededTests(SupplyChainTestCase):
    """Tests for quantity-needed computation of shipment items"""

    # -------------------------------------------------------------------------
    def testTrackItemQuantityNeeded(self):
        """Quantity needed uses the request item quantity and pack quantity"""

        # Create a request line that is already partly in transit and fulfilled
        office = self.create_office()
        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id, quantity=2)

        req_id = self.create_request(office.site_id)
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=10,
                                               quantity_transit=4,
                                               quantity_fulfil=3,
                                               )
        track_item_id = self.create_track_item(item_id,
                                               pack_id,
                                               quantity=2,
                                               req_item_id=req_item_id,
                                               )

        row = Storage(inv_track_item=Storage(id=track_item_id,
                                             req_item_id=req_item_id,
                                             ))

        # Needed quantity is expressed in the shipment pack of the track item
        self.assertEqual(inv_track_item_quantity_needed(row), 12)

    # -------------------------------------------------------------------------
    def testTrackItemQuantityNeededWithoutRequest(self):
        """Quantity needed returns NONE when the track item has no request item"""

        row = Storage(inv_track_item=Storage(req_item_id=None))
        self.assertEqual(inv_track_item_quantity_needed(row), current.messages["NONE"])


# =============================================================================
if __name__ == "__main__":

    run_suite(
        InventoryRepresentationTests,
        WarehouseValidationTests,
        InventoryMeasureComputationTests,
        InventoryWorkflowTests,
        InventoryReportTests,
        TrackItemQuantityNeededTests,
    )

# END ========================================================================
