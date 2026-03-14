# INV Unit Tests
#
# To run this script use:
# python web2py.py -S eden -M -R applications/eden/modules/unit_tests/s3db/inv.py
#
import datetime
import json
import unittest

from contextlib import contextmanager

import core

from gluon import A, B, HTTP, URL, current
from gluon.storage import Storage

from s3db.inv import (SHIP_STATUS_IN_PROCESS,
                      SHIP_STATUS_RETURNING,
                      SHIP_STATUS_SENT,
                      TRACK_STATUS_RETURNING,
                      TRACK_STATUS_ARRIVED,
                      TRACK_STATUS_UNLOADING,
                      InventoryAdjustModel,
                      inv_item_total_volume,
                      inv_item_total_weight,
                      inv_adj_rheader,
                      inv_expiry_date_represent,
                      inv_rfooter,
                      inv_rheader,
                      inv_recv_crud_strings,
                      inv_recv_pdf_footer,
                      inv_recv_rheader,
                      inv_send_pdf_footer,
                      inv_send_rheader,
                      inv_stock_movements,
                      inv_tabs,
                      inv_track_item_quantity_needed,
                      InventoryModel,
                      InventoryTrackingModel,
                      inv_InvItemRepresent,
                      )
from unit_tests import run_suite
from unit_tests.s3db.helpers import ControllerRedirect, SupplyChainTestCase


# =============================================================================
@contextmanager
def capture_redirect(function):
    """Intercept redirects from model helpers outside controller harnesses"""

    saved_redirect = function.__globals__["redirect"]
    function.__globals__["redirect"] = lambda url, *args, **kwargs: \
        (_ for _ in ()).throw(ControllerRedirect(url))

    try:
        yield
    finally:
        function.__globals__["redirect"] = saved_redirect


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
    def testShipmentReferenceHelpersHandleEmptyValuesAndReceivedQuantities(self):
        """Shipment reference helpers and received-quantity representation degrade cleanly"""

        none_send_ref = InventoryTrackingModel.inv_send_ref_represent(None)
        none_recv_ref = InventoryTrackingModel.inv_recv_ref_represent(None)
        unknown_send_ref = InventoryTrackingModel.inv_send_ref_represent("UNKNOWN", show_link=True)
        none_qnty = InventoryTrackingModel.qnty_recv_repr(None)
        zero_qnty = InventoryTrackingModel.qnty_recv_repr(0)
        full_qnty = InventoryTrackingModel.qnty_recv_repr(7)

        self.assertEqual(none_send_ref, current.messages["NONE"])
        self.assertEqual(none_recv_ref, current.messages["NONE"])
        self.assertEqual(unknown_send_ref, "UNKNOWN")
        self.assertTrue(isinstance(none_qnty, B))
        self.assertTrue(isinstance(zero_qnty, B))
        self.assertEqual(full_qnty, 7)

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
    def testInvSendFormAddsRequestCommentsAndPackValues(self):
        """Waybill export includes request comments and pack values when configured"""

        settings = current.deployment_settings

        office = self.create_office()
        destination = self.create_office()
        send_id = self.create_send(office.site_id,
                                   to_site_id=destination.site_id,
                                   req_ref="REQ-SEND-FORM",
                                   send_ref="WB-FORM-001",
                                   )

        saved_pdf = core.DataExporter.pdf
        saved_track_pack_values = settings.supply.get("track_pack_values")
        captured = {}

        try:
            # Capture the exporter call to inspect the generated list_fields
            settings.supply.track_pack_values = True
            core.DataExporter.pdf = lambda resource, **kwargs: captured.update(kwargs) or kwargs

            r = Storage(id=send_id,
                        record=Storage(req_ref="REQ-SEND-FORM"),
                        resource="inv_send",
                        )
            result = InventoryTrackingModel.inv_send_form(r)
        finally:
            core.DataExporter.pdf = saved_pdf
            settings.supply.track_pack_values = saved_track_pack_values

        self.assertEqual(result, captured)
        self.assertEqual(result["pdf_filename"], "WB-FORM-001")
        self.assertEqual(result["pdf_componentname"], "track_item")
        self.assertIn("req_item_id$comments", result["list_fields"])
        self.assertIn("currency", result["list_fields"])
        self.assertIn("pack_value", result["list_fields"])
        self.assertEqual(result["pdf_footer"], inv_send_pdf_footer)
        self.assertEqual(result["pdf_orientation"], "Landscape")

    # -------------------------------------------------------------------------
    def testInvRecvExportsConfigureFormAndDonationCertificate(self):
        """Receive export helpers build the expected GRN and donation certificate payloads"""

        destination = self.create_office(name="Receive Export Destination")
        recv_id = self.create_recv(destination.site_id,
                                   recv_ref="GRN-EXPORT-001",
                                   )

        saved_pdf = core.DataExporter.pdf
        captured = []

        try:
            # Capture both exporter calls to inspect their PDF configuration
            core.DataExporter.pdf = lambda resource, **kwargs: \
                captured.append(Storage(resource=resource, kwargs=kwargs)) or kwargs

            r = Storage(id=recv_id,
                        resource="inv_recv",
                        )
            form_result = InventoryTrackingModel.inv_recv_form(r)
            cert_result = InventoryTrackingModel.inv_recv_donation_cert(r)
        finally:
            core.DataExporter.pdf = saved_pdf

        self.assertEqual(form_result["pdf_filename"], "GRN-EXPORT-001")
        self.assertEqual(form_result["pdf_componentname"], "track_item")
        self.assertIn("recv_quantity", form_result["list_fields"])
        self.assertEqual(form_result["pdf_footer"], inv_recv_pdf_footer)
        self.assertEqual(form_result["pdf_orientation"], "Landscape")

        self.assertEqual(cert_result["pdf_title"], "Donation Certificate")
        self.assertTrue(cert_result["pdf_filename"].startswith("DC-"))
        self.assertEqual(cert_result["pdf_componentname"], "track_item")

        self.assertEqual(len(captured), 2)
        self.assertEqual(captured[0].resource, "inv_recv")
        self.assertEqual(captured[1].resource, "inv_recv")

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
    def testInvSendProcessRequiresSendId(self):
        """Send processing redirects to the shipment list when the record ID is missing"""

        with self.controller("inv", function="send_process") as controller:
            # Use a mapping-like args object so the helper hits its KeyError branch
            current.request.args = {}
            with capture_redirect(current.s3db.inv_send_process):
                with self.assertRaises(ControllerRedirect) as redirect:
                    current.s3db.inv_send_process()

        self.assertIn("/inv/send", str(redirect.exception.url))

    # -------------------------------------------------------------------------
    def testInvSendProcessRejectsUnauthorisedShipments(self):
        """Send processing refuses users without update permission on the shipment"""

        auth = current.auth
        session = current.session
        s3db = current.s3db

        origin = self.create_office(name="Process Origin")
        destination = self.create_office(name="Process Destination")
        item_id = self.create_supply_item(name="Rice")
        pack_id = self.create_item_pack(item_id, quantity=1)
        send_id = self.create_send(origin.site_id,
                                   to_site_id=destination.site_id,
                                   status=SHIP_STATUS_IN_PROCESS,
                                   )
        self.create_track_item(item_id,
                               pack_id,
                               quantity=1,
                               send_id=send_id,
                               status=s3db.inv_tracking_status["IN_PROCESS"],
                               )

        saved_permission = auth.s3_has_permission
        saved_error = session.error
        auth.s3_has_permission = lambda *args, **kwargs: False

        try:
            with self.controller("inv",
                                 function="send_process",
                                 args=[str(send_id)],
                                 ) as controller:
                session.error = None
                with capture_redirect(current.s3db.inv_send_process):
                    with self.assertRaises(ControllerRedirect) as redirect:
                        current.s3db.inv_send_process()
                error = session.error
        finally:
            auth.s3_has_permission = saved_permission
            session.error = saved_error

        self.assertIn("/inv/send/%s" % send_id, str(redirect.exception.url))
        self.assertEqual(str(error),
                         "You do not have permission to send this shipment.")

    # -------------------------------------------------------------------------
    def testInvSendProcessRejectsAlreadySentShipments(self):
        """Send processing refuses shipments that are no longer editable"""

        auth = current.auth
        session = current.session
        s3db = current.s3db

        origin = self.create_office(name="Locked Origin")
        destination = self.create_office(name="Locked Destination")
        item_id = self.create_supply_item(name="Maize")
        pack_id = self.create_item_pack(item_id, quantity=1)
        send_id = self.create_send(origin.site_id,
                                   to_site_id=destination.site_id,
                                   status=SHIP_STATUS_SENT,
                                   )
        self.create_track_item(item_id,
                               pack_id,
                               quantity=1,
                               send_id=send_id,
                               status=s3db.inv_tracking_status["SENT"],
                               )

        saved_permission = auth.s3_has_permission
        saved_error = session.error
        auth.s3_has_permission = lambda *args, **kwargs: True

        try:
            with self.controller("inv",
                                 function="send_process",
                                 args=[str(send_id)],
                                 ) as controller:
                session.error = None
                with capture_redirect(current.s3db.inv_send_process):
                    with self.assertRaises(ControllerRedirect) as redirect:
                        current.s3db.inv_send_process()
                error = session.error
        finally:
            auth.s3_has_permission = saved_permission
            session.error = saved_error

        self.assertIn("/inv/send/%s" % send_id, str(redirect.exception.url))
        self.assertEqual(str(error), "This shipment has already been sent.")

    # -------------------------------------------------------------------------
    def testInvSendProcessRejectsShipmentsWithoutItems(self):
        """Send processing refuses shipments that do not contain any track items"""

        auth = current.auth
        session = current.session

        origin = self.create_office(name="Empty Origin")
        destination = self.create_office(name="Empty Destination")
        send_id = self.create_send(origin.site_id,
                                   to_site_id=destination.site_id,
                                   status=SHIP_STATUS_IN_PROCESS,
                                   )

        saved_permission = auth.s3_has_permission
        saved_error = session.error
        auth.s3_has_permission = lambda *args, **kwargs: True

        try:
            with self.controller("inv",
                                 function="send_process",
                                 args=[str(send_id)],
                                 ) as controller:
                session.error = None
                with capture_redirect(current.s3db.inv_send_process):
                    with self.assertRaises(ControllerRedirect) as redirect:
                        current.s3db.inv_send_process()
                error = session.error
        finally:
            auth.s3_has_permission = saved_permission
            session.error = saved_error

        self.assertIn("/inv/send/%s" % send_id, str(redirect.exception.url))
        self.assertEqual(str(error), "No items have been selected for shipping.")

    # -------------------------------------------------------------------------
    def testInvSendProcessCreatesReceiveAndUpdatesTransitQuantities(self):
        """Send processing locks the shipment, creates a receive note and updates request transit"""

        auth = current.auth
        db = current.db
        s3db = current.s3db
        session = current.session

        # Use different request and shipment pack sizes to exercise unit conversion
        origin = self.create_office(name="Transit Origin")
        destination = self.create_office(name="Transit Destination")
        sender_id = self.create_person(last_name="Sender")
        recipient_id = self.create_person(last_name="Recipient")
        item_id = self.create_supply_item(name="Noodles")
        ship_pack_id = self.create_item_pack(item_id, name="piece", quantity=1)
        req_pack_id = self.create_item_pack(item_id, name="box", quantity=2)

        req_id = self.create_request(destination.site_id,
                                     req_type=1,
                                     req_ref="REQ-SEND-PROCESS",
                                     )
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               req_pack_id,
                                               quantity=5,
                                               quantity_transit=1,
                                               )
        send_id = self.create_send(origin.site_id,
                                   to_site_id=destination.site_id,
                                   req_ref="REQ-SEND-PROCESS",
                                   send_ref="WB-PROCESS-001",
                                   sender_id=sender_id,
                                   recipient_id=recipient_id,
                                   transport_type=1,
                                   delivery_date=current.request.utcnow.date() + \
                                                 datetime.timedelta(days=2),
                                   comments="Urgent delivery",
                                   status=SHIP_STATUS_IN_PROCESS,
                                   )
        track_id = self.create_track_item(item_id,
                                          ship_pack_id,
                                          quantity=4,
                                          req_item_id=req_item_id,
                                          send_id=send_id,
                                          status=s3db.inv_tracking_status["IN_PROCESS"],
                                          )

        saved_permission = auth.s3_has_permission
        saved_error = session.error
        saved_confirmation = session.confirmation
        auth.s3_has_permission = lambda *args, **kwargs: True

        try:
            with self.controller("inv",
                                 function="send_process",
                                 args=[str(send_id)],
                                 ) as controller:
                session.error = None
                session.confirmation = None
                with capture_redirect(current.s3db.inv_send_process):
                    with self.assertRaises(ControllerRedirect) as redirect:
                        current.s3db.inv_send_process()
                confirmation = session.confirmation
        finally:
            auth.s3_has_permission = saved_permission
            session.error = saved_error
            session.confirmation = saved_confirmation

        send = db(s3db.inv_send.id == send_id).select(s3db.inv_send.status,
                                                      limitby=(0, 1),
                                                      ).first()
        track = db(s3db.inv_track_item.id == track_id).select(s3db.inv_track_item.status,
                                                              s3db.inv_track_item.recv_id,
                                                              limitby=(0, 1),
                                                              ).first()
        req_item = db(s3db.req_req_item.id == req_item_id).select(s3db.req_req_item.quantity_transit,
                                                                  limitby=(0, 1),
                                                                  ).first()
        req = db(s3db.req_req.id == req_id).select(s3db.req_req.transit_status,
                                                   limitby=(0, 1),
                                                   ).first()
        recv = db(s3db.inv_recv.send_ref == "WB-PROCESS-001").select(s3db.inv_recv.id,
                                                                     s3db.inv_recv.status,
                                                                     s3db.inv_recv.req_ref,
                                                                     s3db.inv_recv.from_site_id,
                                                                     s3db.inv_recv.site_id,
                                                                     s3db.inv_recv.sender_id,
                                                                     s3db.inv_recv.recipient_id,
                                                                     s3db.inv_recv.transport_type,
                                                                     s3db.inv_recv.comments,
                                                                     limitby=(0, 1),
                                                                     ).first()

        self.assertIn("/inv/send/%s/track_item" % send_id,
                      str(redirect.exception.url))
        self.assertEqual(send.status, SHIP_STATUS_SENT)
        self.assertIsNotNone(recv)
        self.assertEqual(recv.status, SHIP_STATUS_SENT)
        self.assertEqual(recv.req_ref, "REQ-SEND-PROCESS")
        self.assertEqual(recv.from_site_id, origin.site_id)
        self.assertEqual(recv.site_id, destination.site_id)
        self.assertEqual(recv.sender_id, sender_id)
        self.assertEqual(recv.recipient_id, recipient_id)
        self.assertEqual(int(recv.transport_type), 1)
        self.assertEqual(recv.comments, "Urgent delivery")
        self.assertEqual(track.status, s3db.inv_tracking_status["SENT"])
        self.assertEqual(track.recv_id, recv.id)
        self.assertEqual(req_item.quantity_transit, 3)
        self.assertEqual(req.transit_status, 1)
        self.assertEqual(str(confirmation), "Request Status updated")

    # -------------------------------------------------------------------------
    def testInvSendProcessWithoutMatchingRequestUsesGenericShipmentConfirmation(self):
        """Send processing uses the generic confirmation when no matching request exists"""

        auth = current.auth
        db = current.db
        s3db = current.s3db
        session = current.session

        # Build a plain warehouse-to-warehouse shipment without req_ref
        origin = self.create_office(name="Generic Origin")
        destination = self.create_office(name="Generic Destination")
        sender_id = self.create_person(last_name="GenericSender")
        recipient_id = self.create_person(last_name="GenericRecipient")
        item_id = self.create_supply_item(name="Blankets")
        pack_id = self.create_item_pack(item_id, quantity=1)

        send_id = self.create_send(origin.site_id,
                                   to_site_id=destination.site_id,
                                   req_ref="REQ-NO-MATCH",
                                   send_ref="WB-GENERIC",
                                   sender_id=sender_id,
                                   recipient_id=recipient_id,
                                   status=SHIP_STATUS_IN_PROCESS,
                                   )
        track_id = self.create_track_item(item_id,
                                          pack_id,
                                          quantity=4,
                                          send_id=send_id,
                                          status=s3db.inv_tracking_status["IN_PROCESS"],
                                          )

        saved_permission = auth.s3_has_permission
        saved_error = session.error
        saved_confirmation = session.confirmation
        auth.s3_has_permission = lambda *args, **kwargs: True

        try:
            with self.controller("inv",
                                 function="send_process",
                                 args=[str(send_id)],
                                 ) as controller:
                session.error = None
                session.confirmation = None
                with capture_redirect(current.s3db.inv_send_process):
                    with self.assertRaises(ControllerRedirect) as redirect:
                        current.s3db.inv_send_process()
                confirmation = session.confirmation
        finally:
            auth.s3_has_permission = saved_permission
            session.error = saved_error
            session.confirmation = saved_confirmation

        send = db(s3db.inv_send.id == send_id).select(s3db.inv_send.status,
                                                      limitby=(0, 1),
                                                      ).first()
        track = db(s3db.inv_track_item.id == track_id).select(s3db.inv_track_item.status,
                                                              s3db.inv_track_item.recv_id,
                                                              limitby=(0, 1),
                                                              ).first()
        recv = db(s3db.inv_recv.send_ref == "WB-GENERIC").select(s3db.inv_recv.id,
                                                                 s3db.inv_recv.status,
                                                                 s3db.inv_recv.site_id,
                                                                 limitby=(0, 1),
                                                                 orderby=~s3db.inv_recv.id,
                                                                 ).first()

        self.assertIn("/inv/send/%s/track_item" % send_id,
                      str(redirect.exception.url))
        self.assertEqual(send.status, SHIP_STATUS_SENT)
        self.assertIsNotNone(recv)
        self.assertEqual(recv.status, SHIP_STATUS_SENT)
        self.assertEqual(recv.site_id, destination.site_id)
        self.assertEqual(track.status, s3db.inv_tracking_status["SENT"])
        self.assertEqual(track.recv_id, recv.id)
        self.assertEqual(str(confirmation), "Shipment Items sent from Warehouse")

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
        """Track item validation defaults recv_quantity for plain and widget-style bins"""

        form = self.make_form(quantity=7,
                              recv_quantity=None,
                              recv_bin=["BIN-A", "BIN-B"],
                              send_inv_item_id=None,
                              )
        InventoryTrackingModel.inv_track_item_onvalidate(form)

        fallback_form = self.make_form(quantity=5,
                                       recv_quantity=None,
                                       recv_bin=["BIN-A", ""],
                                       send_inv_item_id=None,
                                       )
        InventoryTrackingModel.inv_track_item_onvalidate(fallback_form)

        # Direct receipts without a linked send record default to full receipt
        self.assertEqual(form.vars.recv_quantity, 7)
        self.assertEqual(fallback_form.vars.recv_quantity, 5)

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

    # -------------------------------------------------------------------------
    def testInvKittingOnvalidateRequiresDefinedKitComponents(self):
        """Kitting validation rejects kits that have no component definition"""

        # Build a kit item without any supply_kit_item rows
        office = self.create_office()
        kit_id = self.create_supply_item(name="Family Kit")
        current.db(current.s3db.supply_item.id == kit_id).update(kit=True)
        kit_pack_id = self.create_item_pack(kit_id, quantity=1)

        form = self.make_form(item_id=kit_id,
                              item_pack_id=kit_pack_id,
                              quantity=1,
                              site_id=office.site_id,
                              )
        InventoryTrackingModel.inv_kitting_onvalidate(form)

        # The callback should reject kits that do not define any components
        self.assertIn("item_id", form.errors)

    # -------------------------------------------------------------------------
    def testInvKittingOnvalidateRejectsInsufficientStock(self):
        """Kitting validation reports how many kits can be built from current stock"""

        db = current.db
        s3db = current.s3db

        # Define one kit that requires more component stock than is available
        office = self.create_office()
        component_id = self.create_supply_item(name="Component")
        component_pack_id = self.create_item_pack(component_id, quantity=1)
        self.create_inventory_item(office.site_id,
                                   component_id,
                                   component_pack_id,
                                   quantity=1,
                                   )

        kit_id = self.create_supply_item(name="Emergency Kit")
        db(s3db.supply_item.id == kit_id).update(kit=True)
        kit_pack_id = self.create_item_pack(kit_id, quantity=1)
        s3db.supply_kit_item.insert(parent_item_id=kit_id,
                                    item_id=component_id,
                                    item_pack_id=component_pack_id,
                                    quantity=2,
                                    )

        form = self.make_form(item_id=kit_id,
                              item_pack_id=kit_pack_id,
                              quantity=2,
                              site_id=office.site_id,
                              )
        InventoryTrackingModel.inv_kitting_onvalidate(form)

        # Only zero full kits can be built from one available component unit
        self.assertIn("quantity", form.errors)
        self.assertIn("0 kit(s)", str(form.errors.quantity))

    # -------------------------------------------------------------------------
    def testInvKittingOnacceptConsumesComponentsAndCreatesKitStock(self):
        """Kitting onaccept consumes components, records the pick list and adds finished kits to stock"""

        db = current.db
        s3db = current.s3db

        # Assemble one kit from a single component item kept in stock
        office = self.create_office()
        component_id = self.create_supply_item(name="Bandage")
        component_pack_id = self.create_item_pack(component_id, quantity=1)
        expiry = current.request.now.date() + datetime.timedelta(days=10)
        component_stock_id = self.create_inventory_item(office.site_id,
                                                        component_id,
                                                        component_pack_id,
                                                        quantity=5,
                                                        expiry_date=expiry,
                                                        bin="A-1",
                                                        item_source_no="SRC-BANDAGE",
                                                        )

        kit_id = self.create_supply_item(name="First Aid Kit")
        db(s3db.supply_item.id == kit_id).update(kit=True)
        kit_pack_id = self.create_item_pack(kit_id, quantity=1)
        s3db.supply_kit_item.insert(parent_item_id=kit_id,
                                    item_id=component_id,
                                    item_pack_id=component_pack_id,
                                    quantity=2,
                                    )

        ktable = s3db.inv_kitting
        kitting_id = ktable.insert(site_id=office.site_id,
                                   item_id=kit_id,
                                   item_pack_id=kit_pack_id,
                                   quantity=2,
                                   )

        InventoryTrackingModel.inv_kitting_onaccept(self.make_form(id=kitting_id,
                                                                   item_id=kit_id,
                                                                   item_pack_id=kit_pack_id,
                                                                   quantity=2,
                                                                   site_id=office.site_id,
                                                                   ))

        # Verify the consumed component quantity, generated pick list and new kit stock
        component_stock = db(s3db.inv_inv_item.id == component_stock_id).select(s3db.inv_inv_item.quantity,
                                                                                limitby=(0, 1),
                                                                                ).first()
        self.assertEqual(component_stock.quantity, 1)

        pick = db(s3db.inv_kitting_item.kitting_id == kitting_id).select(s3db.inv_kitting_item.ALL,
                                                                         limitby=(0, 1),
                                                                         ).first()
        self.assertIsNotNone(pick)
        self.assertEqual(pick.item_id, component_id)
        self.assertEqual(pick.inv_item_id, component_stock_id)
        self.assertEqual(pick.quantity, 4)

        kit_stock = db((s3db.inv_inv_item.site_id == office.site_id) &
                       (s3db.inv_inv_item.item_id == kit_id)).select(s3db.inv_inv_item.quantity,
                                                                      s3db.inv_inv_item.expiry_date,
                                                                      orderby=~s3db.inv_inv_item.id,
                                                                      limitby=(0, 1),
                                                                      ).first()
        self.assertIsNotNone(kit_stock)
        self.assertEqual(kit_stock.quantity, 2)
        self.assertEqual(kit_stock.expiry_date, expiry)

    # -------------------------------------------------------------------------
    def testInvTrackItemOnacceptUpdatesStockAndDocumentReferences(self):
        """Track item onaccept rebalances stock and copies send/request references to linked documents"""

        db = current.db
        s3db = current.s3db

        # Start from an existing shipment line linked to stock, send, receive and request rows
        origin = self.create_office(name="Origin")
        destination = self.create_office(name="Destination")
        item_id = self.create_supply_item(name="Water")
        pack_id = self.create_item_pack(item_id, quantity=1)
        inv_item_id = self.create_inventory_item(origin.site_id,
                                                 item_id,
                                                 pack_id,
                                                 quantity=8,
                                                 )
        send_id = self.create_send(origin.site_id,
                                   to_site_id=destination.site_id,
                                   send_ref="WB-TRACK-001",
                                   )
        recv_id = self.create_recv(destination.site_id,
                                   from_site_id=origin.site_id,
                                   recv_ref="GRN-TRACK-001",
                                   )
        req_id = self.create_request(destination.site_id,
                                     req_ref="REQ-TRACK-001",
                                     )
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=5,
                                               )
        track_item_id = self.create_track_item(item_id,
                                               pack_id,
                                               quantity=2,
                                               req_item_id=req_item_id,
                                               send_id=send_id,
                                               recv_id=recv_id,
                                               send_inv_item_id=inv_item_id,
                                               status=1,
                                               )
        record = db(s3db.inv_track_item.id == track_item_id).select(s3db.inv_track_item.ALL,
                                                                    limitby=(0, 1),
                                                                    ).first()

        InventoryTrackingModel.inv_track_item_onaccept(self.make_form(record=record,
                                                                      id=track_item_id,
                                                                      send_inv_item_id=inv_item_id,
                                                                      item_pack_id=pack_id,
                                                                      quantity=3,
                                                                      send_id=send_id,
                                                                      recv_id=recv_id,
                                                                      ))

        # Verify the edited shipment line reduced stock by the new quantity
        inv_item = db(s3db.inv_inv_item.id == inv_item_id).select(s3db.inv_inv_item.quantity,
                                                                  limitby=(0, 1),
                                                                  ).first()
        send = db(s3db.inv_send.id == send_id).select(s3db.inv_send.req_ref,
                                                      limitby=(0, 1),
                                                      ).first()
        recv = db(s3db.inv_recv.id == recv_id).select(s3db.inv_recv.send_ref,
                                                      s3db.inv_recv.req_ref,
                                                      limitby=(0, 1),
                                                      ).first()
        self.assertEqual(inv_item.quantity, 7)
        self.assertEqual(send.req_ref, "REQ-TRACK-001")
        self.assertEqual(recv.send_ref, "WB-TRACK-001")
        self.assertEqual(recv.req_ref, "REQ-TRACK-001")

    # -------------------------------------------------------------------------
    def testInvTrackItemOnacceptReceivesUnloadingItemsAndCreatesAdjustment(self):
        """Track item onaccept moves unloading items into stock, fulfils requests and creates adjustments"""

        db = current.db
        s3db = current.s3db

        # Prepare one unloading shipment line with a short receipt
        origin = self.create_office(name="Unload Origin")
        destination = self.create_office(name="Unload Destination")
        recipient_id = self.create_person(last_name="Receiver")
        item_id = self.create_supply_item(name="Blanket")
        pack_id = self.create_item_pack(item_id, quantity=1)
        source_inv_item_id = self.create_inventory_item(origin.site_id,
                                                        item_id,
                                                        pack_id,
                                                        quantity=10,
                                                        source_type=2,
                                                        )
        recv_id = self.create_recv(destination.site_id,
                                   from_site_id=origin.site_id,
                                   recipient_id=recipient_id,
                                   comments="Damaged in transit",
                                   )
        req_id = self.create_request(destination.site_id,
                                     req_ref="REQ-UNLOAD-001",
                                     )
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=3,
                                               quantity_fulfil=0,
                                               )
        track_item_id = self.create_track_item(item_id,
                                               pack_id,
                                               quantity=5,
                                               recv_quantity=3,
                                               req_item_id=req_item_id,
                                               recv_id=recv_id,
                                               send_inv_item_id=source_inv_item_id,
                                               status=TRACK_STATUS_UNLOADING,
                                               currency="USD",
                                               pack_value=4.0,
                                               expiry_date=current.request.now.date() + datetime.timedelta(days=30),
                                               recv_bin="B-2",
                                               owner_org_id=destination.organisation_id,
                                               supply_org_id=origin.organisation_id,
                                               item_source_no="SRC-UNLOAD-1",
                                               comments="Short receipt",
                                               )
        record = db(s3db.inv_track_item.id == track_item_id).select(s3db.inv_track_item.ALL,
                                                                    limitby=(0, 1),
                                                                    ).first()

        InventoryTrackingModel.inv_track_item_onaccept(self.make_form(record=record,
                                                                      id=track_item_id,
                                                                      send_inv_item_id=source_inv_item_id,
                                                                      ))

        # Verify destination stock, request fulfilment and adjustment bookkeeping
        recv_inv_item = db((s3db.inv_inv_item.site_id == destination.site_id) &
                           (s3db.inv_inv_item.item_id == item_id)).select(s3db.inv_inv_item.id,
                                                                           s3db.inv_inv_item.quantity,
                                                                           s3db.inv_inv_item.source_type,
                                                                           limitby=(0, 1),
                                                                           ).first()
        self.assertIsNotNone(recv_inv_item)
        self.assertEqual(recv_inv_item.quantity, 3)
        self.assertEqual(recv_inv_item.source_type, 2)

        req_item = db(s3db.req_req_item.id == req_item_id).select(s3db.req_req_item.quantity_fulfil,
                                                                  limitby=(0, 1),
                                                                  ).first()
        track_item = db(s3db.inv_track_item.id == track_item_id).select(s3db.inv_track_item.recv_inv_item_id,
                                                                        s3db.inv_track_item.status,
                                                                        s3db.inv_track_item.adj_item_id,
                                                                        limitby=(0, 1),
                                                                        ).first()
        adj_item = db(s3db.inv_adj_item.id == track_item.adj_item_id).select(s3db.inv_adj_item.old_quantity,
                                                                             s3db.inv_adj_item.new_quantity,
                                                                             s3db.inv_adj_item.inv_item_id,
                                                                             limitby=(0, 1),
                                                                             ).first()
        self.assertEqual(req_item.quantity_fulfil, 3)
        self.assertEqual(track_item.recv_inv_item_id, recv_inv_item.id)
        self.assertEqual(track_item.status, TRACK_STATUS_ARRIVED)
        self.assertIsNotNone(adj_item)
        self.assertEqual(adj_item.inv_item_id, source_inv_item_id)
        self.assertEqual(adj_item.old_quantity, 5)
        self.assertEqual(adj_item.new_quantity, 3)


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
class InventoryModelHelperTests(SupplyChainTestCase):
    """Tests for inventory model helpers used by controllers/imports"""

    # -------------------------------------------------------------------------
    def testInvPrepFiltersExistingInventoryItems(self):
        """inv_prep excludes items already stocked at the current site"""

        office = self.create_office()
        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id, quantity=1)
        self.create_inventory_item(office.site_id,
                                   item_id,
                                   pack_id,
                                   quantity=2,
                                   )

        requires = current.db.inv_inv_item.item_id.requires
        saved = requires.set_filter
        calls = []
        requires.set_filter = lambda **kwargs: calls.append(kwargs)

        try:
            r = Storage(component=Storage(name="inv_item"),
                        record=Storage(site_id=office.site_id),
                        method="create",
                        args=[],
                        )
            InventoryModel.inv_prep(r)
        finally:
            requires.set_filter = saved

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["not_filterby"], "id")
        self.assertIn(item_id, calls[0]["not_filter_opts"])

    # -------------------------------------------------------------------------
    def testInvPrepDefaultsSendComponentToSearchTab(self):
        """inv_prep switches the GIS selector to the search tab for sends"""

        s3 = current.response.s3
        saved = s3.gis.tab

        try:
            r = Storage(component=Storage(name="send"))
            InventoryModel.inv_prep(r)
            tab = s3.gis.tab
        finally:
            s3.gis.tab = saved

        self.assertEqual(tab, "search")

    # -------------------------------------------------------------------------
    def testInvItemDuplicateMatchesStockAndPreservesQuantity(self):
        """inv_item_duplicate updates matching stock rows and keeps stock quantity"""

        office = self.create_office()
        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id, quantity=1)
        inv_item_id = self.create_inventory_item(office.site_id,
                                                 item_id,
                                                 pack_id,
                                                 quantity=9,
                                                 owner_org_id=office.organisation_id,
                                                 bin="A-01",
                                                 )
        row = current.db(current.s3db.inv_inv_item.id == inv_item_id).select(
                        current.s3db.inv_inv_item.site_id,
                        current.s3db.inv_inv_item.item_id,
                        current.s3db.inv_inv_item.item_pack_id,
                        current.s3db.inv_inv_item.owner_org_id,
                        current.s3db.inv_inv_item.supply_org_id,
                        current.s3db.inv_inv_item.pack_value,
                        current.s3db.inv_inv_item.currency,
                        current.s3db.inv_inv_item.bin,
                        limitby=(0, 1),
                        ).first()

        update = Storage(UPDATE="update")
        item = Storage(data=Storage(site_id=row.site_id,
                                    item_id=row.item_id,
                                    item_pack_id=row.item_pack_id,
                                    owner_org_id=row.owner_org_id,
                                    supply_org_id=row.supply_org_id,
                                    pack_value=row.pack_value,
                                    currency=row.currency,
                                    bin=row.bin,
                                    quantity=0,
                                    ),
                       table=current.s3db.inv_inv_item,
                       METHOD=update,
                       method=None,
                       id=None,
                       )

        InventoryModel.inv_item_duplicate(item)

        self.assertEqual(item.id, inv_item_id)
        self.assertEqual(item.method, update.UPDATE)
        self.assertEqual(item.data.quantity, 9)


# =============================================================================
class InventoryHeaderTests(SupplyChainTestCase):
    """Tests for inventory tabs, headers and footers"""

    # -------------------------------------------------------------------------
    def testInvTabsHonourCollapseStateAndPlannedProcurements(self):
        """inv_tabs switches between collapsed and expanded warehouse views"""

        settings = current.deployment_settings
        auth = current.auth
        session = current.session

        saved_has_tabs = settings.get_org_site_inv_req_tabs
        saved_has_module = settings.has_module
        saved_collapse = settings.get_inv_collapse_tabs
        saved_recv_label = settings.get_inv_recv_tab_label
        saved_send_label = settings.get_inv_send_tab_label
        saved_permission = auth.s3_has_permission
        saved_show_inv = getattr(session.s3, "show_inv", None)
        saved_rheader_resource = inv_tabs.__globals__["s3_rheader_resource"]

        settings.get_org_site_inv_req_tabs = lambda: True
        settings.has_module = lambda module: module in ("inv", "proc")
        settings.get_inv_collapse_tabs = lambda: True
        settings.get_inv_recv_tab_label = lambda: "Incoming"
        settings.get_inv_send_tab_label = lambda: "Outgoing"
        auth.s3_has_permission = lambda *args, **kwargs: True
        inv_tabs.__globals__["s3_rheader_resource"] = lambda r: ("org_office", None)

        try:
            session.s3.show_inv = None
            collapsed = inv_tabs(Storage(name="office",
                                         id=1,
                                         get_vars=Storage(),
                                         ))

            session.s3.show_inv = None
            expanded = inv_tabs(Storage(name="office",
                                        id=1,
                                        get_vars=Storage(show_inv="True"),
                                        ))
        finally:
            settings.get_org_site_inv_req_tabs = saved_has_tabs
            settings.has_module = saved_has_module
            settings.get_inv_collapse_tabs = saved_collapse
            settings.get_inv_recv_tab_label = saved_recv_label
            settings.get_inv_send_tab_label = saved_send_label
            auth.s3_has_permission = saved_permission
            session.s3.show_inv = saved_show_inv
            inv_tabs.__globals__["s3_rheader_resource"] = saved_rheader_resource

        self.assertEqual(collapsed, [("+ Warehouse", "inv_item", {"show_inv": "True"})])
        self.assertEqual([tab[1] for tab in expanded[:4]],
                         ["inv_item", "recv", "send", "plan"])

    # -------------------------------------------------------------------------
    def testInvRfooterAddsAdjustmentAndTrackingActions(self):
        """inv_rfooter exposes stock adjustment and tracking actions for warehouse stock"""

        settings = current.deployment_settings
        auth = current.auth
        response_s3 = current.response.s3

        office = self.create_office()
        saved_direct_stock = settings.get_inv_direct_stock_edits
        saved_permission = auth.s3_has_permission
        saved_footer = response_s3.rfooter

        settings.get_inv_direct_stock_edits = lambda: False
        auth.s3_has_permission = lambda *args, **kwargs: True
        response_s3.rfooter = None

        try:
            inv_rfooter(Storage(component=Storage(name="inv_item"),
                               component_id=17,
                               id=office.id,
                               ),
                        Storage(site_id=office.site_id))
            footer = str(response_s3.rfooter)
        finally:
            settings.get_inv_direct_stock_edits = saved_direct_stock
            auth.s3_has_permission = saved_permission
            response_s3.rfooter = saved_footer

        self.assertIn("Adjust Stock Item", footer)
        self.assertIn("Track Shipment", footer)
        self.assertIn("/inv/adj/create", footer)
        self.assertIn("/inv/track_movement", footer)

    # -------------------------------------------------------------------------
    def testSendAndReceiveRheadersExposeWorkflowActions(self):
        """Shipment rheaders include item tabs and the expected workflow actions"""

        db = current.db
        s3db = current.s3db
        auth = current.auth
        response_s3 = current.response.s3

        origin_location = self.create_location(name="Origin City", L0="Poland")
        destination_location = self.create_location(name="Destination City", L0="Germany")
        origin = self.create_office(name="Origin Warehouse",
                                    location_id=origin_location,
                                    phone1="111",
                                    phone2="222",
                                    )
        destination = self.create_office(name="Destination Warehouse",
                                         location_id=destination_location,
                                         )
        item_id = self.create_supply_item(name="Ready Meal")
        pack_id = self.create_item_pack(item_id, quantity=1)
        inv_item_id = self.create_inventory_item(origin.site_id,
                                                 item_id,
                                                 pack_id,
                                                 quantity=6,
                                                 )
        send_id = self.create_send(origin.site_id,
                                   to_site_id=destination.site_id,
                                   send_ref="WB-HDR-001",
                                   status=SHIP_STATUS_IN_PROCESS,
                                   )
        self.create_track_item(item_id,
                               pack_id,
                               quantity=2,
                               send_id=send_id,
                               send_inv_item_id=inv_item_id,
                               )
        recv_id = self.create_recv(destination.site_id,
                                   from_site_id=origin.site_id,
                                   recv_ref="GRN-HDR-001",
                                   send_ref="WB-HDR-001",
                                   status=SHIP_STATUS_SENT,
                                   )
        self.create_track_item(item_id,
                               pack_id,
                               quantity=2,
                               recv_id=recv_id,
                               )

        sendtable = s3db.inv_send
        recvtable = s3db.inv_recv
        send_record = db(sendtable.id == send_id).select(sendtable.ALL,
                                                         limitby=(0, 1),
                                                         ).first()
        recv_record = db(recvtable.id == recv_id).select(recvtable.ALL,
                                                         limitby=(0, 1),
                                                         ).first()

        saved_send_tabs = inv_send_rheader.__globals__["s3_rheader_tabs"]
        saved_permission = auth.s3_has_permission
        saved_footer = response_s3.rfooter
        auth.s3_has_permission = lambda *args, **kwargs: True
        response_s3.rfooter = None

        try:
            inv_send_rheader.__globals__["s3_rheader_tabs"] = lambda r, tabs: "SEND-TABS"
            send_rheader = inv_send_rheader(Storage(representation="html",
                                                    name="send",
                                                    record=send_record,
                                                    table=sendtable,
                                                    method=None,
                                                    ))
            inv_send_rheader.__globals__["s3_rheader_tabs"] = lambda r, tabs: "RECV-TABS"
            recv_rheader = inv_recv_rheader(Storage(representation="html",
                                                    name="recv",
                                                    record=recv_record,
                                                    table=recvtable,
                                                    ))
        finally:
            inv_send_rheader.__globals__["s3_rheader_tabs"] = saved_send_tabs
            auth.s3_has_permission = saved_permission
            response_s3.rfooter = saved_footer

        self.assertIn("WB-HDR-001", str(send_rheader))
        self.assertIn("SEND-TABS", str(send_rheader))
        self.assertIn("Send Shipment", str(send_rheader))
        self.assertIn("GRN-HDR-001", str(recv_rheader))
        self.assertIn("RECV-TABS", str(recv_rheader))
        self.assertIn("Receive Shipment", str(recv_rheader))

    # -------------------------------------------------------------------------
    def testSendRheaderForSentShipmentExposesReturnReceiveAndCancelActions(self):
        """Sent shipments expose return, remote receive and cancel actions"""

        db = current.db
        s3db = current.s3db
        auth = current.auth
        response_s3 = current.response.s3

        origin = self.create_office(name="Sent Origin")
        destination = self.create_office(name="Sent Destination")
        item_id = self.create_supply_item(name="Rice")
        pack_id = self.create_item_pack(item_id, quantity=1)
        inv_item_id = self.create_inventory_item(origin.site_id,
                                                 item_id,
                                                 pack_id,
                                                 quantity=4,
                                                 )
        send_id = self.create_send(origin.site_id,
                                   to_site_id=destination.site_id,
                                   send_ref="WB-SENT-001",
                                   status=SHIP_STATUS_SENT,
                                   )
        self.create_track_item(item_id,
                               pack_id,
                               quantity=1,
                               send_id=send_id,
                               send_inv_item_id=inv_item_id,
                               )
        sendtable = s3db.inv_send
        send_record = db(sendtable.id == send_id).select(sendtable.ALL,
                                                         limitby=(0, 1),
                                                         ).first()

        saved_tabs = inv_send_rheader.__globals__["s3_rheader_tabs"]
        saved_permission = auth.s3_has_permission
        saved_footer = response_s3.rfooter
        saved_ready = list(response_s3.jquery_ready)
        auth.s3_has_permission = lambda *args, **kwargs: True
        response_s3.rfooter = None
        response_s3.jquery_ready = []

        try:
            inv_send_rheader.__globals__["s3_rheader_tabs"] = lambda r, tabs: "SEND-TABS"
            rheader = inv_send_rheader(Storage(representation="html",
                                               name="send",
                                               record=send_record,
                                               table=sendtable,
                                               method=None,
                                               ))
            ready = list(response_s3.jquery_ready)
        finally:
            inv_send_rheader.__globals__["s3_rheader_tabs"] = saved_tabs
            auth.s3_has_permission = saved_permission
            response_s3.rfooter = saved_footer
            response_s3.jquery_ready = saved_ready

        rendered = str(rheader)
        self.assertIn("Manage Returns", rendered)
        self.assertIn("Confirm Shipment Received", rendered)
        self.assertIn("Cancel Shipment", rendered)
        self.assertTrue(any("send-return" in script for script in ready))
        self.assertTrue(any("send-receive" in script for script in ready))
        self.assertTrue(any("send-cancel" in script for script in ready))

    # -------------------------------------------------------------------------
    def testSendRheaderForReturningShipmentsHandlesItemAndNoItemCases(self):
        """Returning shipments expose completion only when return lines exist"""

        db = current.db
        s3db = current.s3db
        response_s3 = current.response.s3

        origin = self.create_office(name="Returning Origin")
        destination = self.create_office(name="Returning Destination")
        item_id = self.create_supply_item(name="Biscuits")
        pack_id = self.create_item_pack(item_id, quantity=1)
        inv_item_id = self.create_inventory_item(origin.site_id,
                                                 item_id,
                                                 pack_id,
                                                 quantity=3,
                                                 )
        sendtable = s3db.inv_send

        returning_with_items = self.create_send(origin.site_id,
                                                to_site_id=destination.site_id,
                                                send_ref="WB-RETURN-1",
                                                status=SHIP_STATUS_RETURNING,
                                                )
        self.create_track_item(item_id,
                               pack_id,
                               quantity=1,
                               send_id=returning_with_items,
                               send_inv_item_id=inv_item_id,
                               )
        returning_without_items = self.create_send(origin.site_id,
                                                   to_site_id=destination.site_id,
                                                   send_ref="WB-RETURN-2",
                                                   status=SHIP_STATUS_RETURNING,
                                                   )

        saved_tabs = inv_send_rheader.__globals__["s3_rheader_tabs"]
        saved_footer = response_s3.rfooter
        saved_ready = list(response_s3.jquery_ready)
        response_s3.jquery_ready = []

        try:
            inv_send_rheader.__globals__["s3_rheader_tabs"] = lambda r, tabs: "SEND-TABS"

            with_items = db(sendtable.id == returning_with_items).select(sendtable.ALL,
                                                                         limitby=(0, 1),
                                                                         ).first()
            without_items = db(sendtable.id == returning_without_items).select(sendtable.ALL,
                                                                               limitby=(0, 1),
                                                                               ).first()

            response_s3.rfooter = None
            rheader = inv_send_rheader(Storage(representation="html",
                                               name="send",
                                               record=with_items,
                                               table=sendtable,
                                               method=None,
                                               ))
            ready = list(response_s3.jquery_ready)

            response_s3.jquery_ready = []
            response_s3.rfooter = None
            inv_send_rheader(Storage(representation="html",
                                     name="send",
                                     record=without_items,
                                     table=sendtable,
                                     method=None,
                                     ))
            warning = str(response_s3.rfooter)
        finally:
            inv_send_rheader.__globals__["s3_rheader_tabs"] = saved_tabs
            response_s3.rfooter = saved_footer
            response_s3.jquery_ready = saved_ready

        self.assertIn("Complete Returns", str(rheader))
        self.assertTrue(any("return_process" in script for script in ready))
        self.assertIn("complete the return process", warning)

    # -------------------------------------------------------------------------
    def testRecvRheaderWarnsWithoutItemsAndCountsSingleItem(self):
        """Receive headers warn for empty shipments and summarise a single line item"""

        db = current.db
        s3db = current.s3db
        auth = current.auth
        response_s3 = current.response.s3

        origin = self.create_office(name="Recv Origin")
        destination = self.create_office(name="Recv Destination")
        item_id = self.create_supply_item(name="Beans")
        pack_id = self.create_item_pack(item_id, quantity=1)

        recv_empty_id = self.create_recv(destination.site_id,
                                         from_site_id=origin.site_id,
                                         recv_ref="GRN-EMPTY",
                                         status=SHIP_STATUS_IN_PROCESS,
                                         )
        recv_one_id = self.create_recv(destination.site_id,
                                       from_site_id=origin.site_id,
                                       recv_ref="GRN-ONE",
                                       status=SHIP_STATUS_SENT,
                                       )
        self.create_track_item(item_id,
                               pack_id,
                               quantity=1,
                               recv_id=recv_one_id,
                               )

        recvtable = s3db.inv_recv
        saved_tabs = inv_recv_rheader.__globals__["s3_rheader_tabs"]
        saved_permission = auth.s3_has_permission
        saved_footer = response_s3.rfooter
        auth.s3_has_permission = lambda *args, **kwargs: True

        try:
            inv_recv_rheader.__globals__["s3_rheader_tabs"] = lambda r, tabs: "RECV-TABS"

            empty_record = db(recvtable.id == recv_empty_id).select(recvtable.ALL,
                                                                    limitby=(0, 1),
                                                                    ).first()
            response_s3.rfooter = None
            empty_header = inv_recv_rheader(Storage(representation="html",
                                                    name="recv",
                                                    record=empty_record,
                                                    table=recvtable,
                                                    ))
            empty_footer = str(response_s3.rfooter)

            one_record = db(recvtable.id == recv_one_id).select(recvtable.ALL,
                                                                limitby=(0, 1),
                                                                ).first()
            response_s3.rfooter = None
            one_header = inv_recv_rheader(Storage(representation="html",
                                                  name="recv",
                                                  record=one_record,
                                                  table=recvtable,
                                                  ))
        finally:
            inv_recv_rheader.__globals__["s3_rheader_tabs"] = saved_tabs
            auth.s3_has_permission = saved_permission
            response_s3.rfooter = saved_footer

        self.assertIn("allocate to bins", empty_footer)
        self.assertIn("This shipment contains one line item", str(one_header))
        self.assertIn("Receive Shipment", str(one_header))

    # -------------------------------------------------------------------------
    def testInvRheaderAndRecvCrudStringsUseConfiguredLabels(self):
        """Warehouse/item rheaders and receive CRUD strings follow deployment options"""

        db = current.db
        s3db = current.s3db
        settings = current.deployment_settings
        auth = current.auth
        response_s3 = current.response.s3

        office = self.create_warehouse(code="RWH-1")
        warehouse = db(s3db.inv_warehouse.id == office).select(s3db.inv_warehouse.ALL,
                                                               limitby=(0, 1),
                                                               ).first()
        supply_office = self.create_office()
        item_id = self.create_supply_item(name="Soap")
        pack_id = self.create_item_pack(item_id, quantity=1)
        inv_item_id = self.create_inventory_item(supply_office.site_id,
                                                 item_id,
                                                 pack_id,
                                                 quantity=3,
                                                 )
        inv_item = db(s3db.inv_inv_item.id == inv_item_id).select(s3db.inv_inv_item.ALL,
                                                                  limitby=(0, 1),
                                                                  ).first()

        saved_site_tabs = settings.get_org_site_inv_req_tabs
        saved_has_module = settings.has_module
        saved_permission = auth.s3_has_permission
        saved_direct_stock = settings.get_inv_direct_stock_edits
        saved_logo = s3db.org_organisation_logo
        saved_req_tabs = s3db.req_tabs
        saved_inv_tabs = inv_rheader.__globals__["inv_tabs"]
        saved_resource = inv_rheader.__globals__["s3_rheader_resource"]
        saved_header = inv_rheader.__globals__["S3ResourceHeader"]
        saved_tabs = inv_rheader.__globals__["s3_rheader_tabs"]
        saved_shipment_name = settings.inv.get("shipment_name")
        saved_footer = response_s3.rfooter

        settings.get_org_site_inv_req_tabs = lambda: True
        settings.has_module = lambda module: module in ("hrm", "asset", "req")
        settings.inv.shipment_name = "order"
        settings.get_inv_direct_stock_edits = lambda: False
        auth.s3_has_permission = lambda *args, **kwargs: True
        s3db.org_organisation_logo = lambda organisation_id: "LOGO"
        s3db.req_tabs = lambda r: [("Requests", "req")]
        inv_rheader.__globals__["inv_tabs"] = lambda r: [("Stock", "inv_item")]
        inv_rheader.__globals__["s3_rheader_resource"] = lambda r: ("inv_warehouse", warehouse)
        inv_rheader.__globals__["S3ResourceHeader"] = lambda fields, tabs: \
            (lambda r, table=None, record=None: ("WAREHOUSE-FIELDS", "WAREHOUSE-TABS:%s" %
                                                 ",".join(tab[1] or "" for tab in tabs)))
        inv_rheader.__globals__["s3_rheader_tabs"] = lambda r, tabs: "ITEM-TABS"
        response_s3.rfooter = None

        try:
            warehouse_rheader = inv_rheader(Storage(representation="html",
                                                    method=None,
                                                    component=Storage(name="inv_item"),
                                                    component_id=inv_item_id,
                                                    id=warehouse.id,
                                                    get_vars=Storage(),
                                                    ))
            warehouse_footer = str(response_s3.rfooter)
            inv_rheader.__globals__["s3_rheader_resource"] = lambda r: ("inv_inv_item", inv_item)
            response_s3.rfooter = None
            stock_rheader = inv_rheader(Storage(representation="html",
                                                method=None,
                                                component=None,
                                                component_id=None,
                                                id=inv_item_id,
                                                get_vars=Storage(),
                                                ))
            inv_recv_crud_strings()
            recv_strings = response_s3.crud_strings["inv_recv"]
        finally:
            settings.get_org_site_inv_req_tabs = saved_site_tabs
            settings.has_module = saved_has_module
            settings.inv.shipment_name = saved_shipment_name
            settings.get_inv_direct_stock_edits = saved_direct_stock
            auth.s3_has_permission = saved_permission
            s3db.org_organisation_logo = saved_logo
            s3db.req_tabs = saved_req_tabs
            inv_rheader.__globals__["inv_tabs"] = saved_inv_tabs
            inv_rheader.__globals__["s3_rheader_resource"] = saved_resource
            inv_rheader.__globals__["S3ResourceHeader"] = saved_header
            inv_rheader.__globals__["s3_rheader_tabs"] = saved_tabs
            response_s3.rfooter = saved_footer

        self.assertIn("WAREHOUSE-FIELDS", str(warehouse_rheader))
        self.assertIn("WAREHOUSE-TABS", str(warehouse_rheader))
        self.assertIn("Adjust Stock Item", warehouse_footer)
        self.assertIn("ITEM-TABS", str(stock_rheader))
        self.assertIn("Soap", str(stock_rheader))
        self.assertEqual(recv_strings.label_create, "Add Order")

    # -------------------------------------------------------------------------
    def testInvRheaderSupportsKittingAndTrackItemVariants(self):
        """inv_rheader renders dedicated kitting and track-item headers"""

        db = current.db
        s3db = current.s3db

        office = self.create_office(name="Header Office")
        repacked_id = self.create_person(last_name="Repacker")
        item_id = self.create_supply_item(name="Kit Item")
        pack_id = self.create_item_pack(item_id, quantity=1)
        inv_item_id = self.create_inventory_item(office.site_id,
                                                 item_id,
                                                 pack_id,
                                                 quantity=4,
                                                 )
        kitting_id = s3db.inv_kitting.insert(site_id=office.site_id,
                                             item_id=item_id,
                                             item_pack_id=pack_id,
                                             quantity=2,
                                             req_ref="KIT-REQ-1",
                                             repacked_id=repacked_id,
                                             date=current.request.utcnow.date(),
                                             )
        track_with_site_id = self.create_track_item(item_id,
                                                    pack_id,
                                                    quantity=1,
                                                    send_inv_item_id=inv_item_id,
                                                    )
        track_without_site_id = self.create_track_item(item_id,
                                                       pack_id,
                                                       quantity=1,
                                                       send_inv_item_id=None,
                                                       )

        kitting = db(s3db.inv_kitting.id == kitting_id).select(s3db.inv_kitting.ALL,
                                                               limitby=(0, 1),
                                                               ).first()
        tracktable = s3db.inv_track_item
        track_with_site = db(tracktable.id == track_with_site_id).select(tracktable.ALL,
                                                                         limitby=(0, 1),
                                                                         ).first()
        track_without_site = db(tracktable.id == track_without_site_id).select(tracktable.ALL,
                                                                               limitby=(0, 1),
                                                                               ).first()

        saved_resource = inv_rheader.__globals__["s3_rheader_resource"]
        saved_tabs = inv_rheader.__globals__["s3_rheader_tabs"]
        saved_footer = inv_rheader.__globals__["inv_rfooter"]
        inv_rheader.__globals__["s3_rheader_tabs"] = lambda r, tabs: "TRACK-TABS"
        inv_rheader.__globals__["inv_rfooter"] = lambda r, record: None

        try:
            # Representation caches can outlive rolled-back rows across tests
            self._clear_represent_caches()
            inv_rheader.__globals__["s3_rheader_resource"] = lambda r: ("inv_kitting", kitting)
            kitting_rheader = inv_rheader(Storage(representation="html",
                                                  method=None,
                                                  ))

            inv_rheader.__globals__["s3_rheader_resource"] = lambda r: ("inv_track_item", track_with_site)
            track_with_site_rheader = inv_rheader(Storage(representation="html",
                                                          method=None,
                                                          ))

            inv_rheader.__globals__["s3_rheader_resource"] = lambda r: ("inv_track_item", track_without_site)
            track_without_site_rheader = inv_rheader(Storage(representation="html",
                                                             method=None,
                                                             ))
        finally:
            inv_rheader.__globals__["s3_rheader_resource"] = saved_resource
            inv_rheader.__globals__["s3_rheader_tabs"] = saved_tabs
            inv_rheader.__globals__["inv_rfooter"] = saved_footer

        expected_site = str(s3db.inv_inv_item.site_id.represent(office.site_id))
        expected_item = str(s3db.inv_inv_item.item_id.represent(item_id))
        self.assertIn("KIT-REQ-1", str(kitting_rheader))
        self.assertIn("TRACK-TABS", str(kitting_rheader))
        self.assertIn(expected_site, str(track_with_site_rheader))
        self.assertIn(expected_item, str(track_with_site_rheader))
        self.assertIn("TRACK-TABS", str(track_with_site_rheader))
        self.assertIn(expected_item, str(track_without_site_rheader))
        self.assertIn("TRACK-TABS", str(track_without_site_rheader))

    # -------------------------------------------------------------------------
    def testSendRheaderHandlesDocumentsAndMissingDestinationDetails(self):
        """Send rheaders add the document tab and fall back cleanly without destination details"""

        db = current.db
        s3db = current.s3db
        settings = current.deployment_settings
        response_s3 = current.response.s3

        warehouse_id = self.create_warehouse(code="HDR-WH-2")
        warehouse = db(s3db.inv_warehouse.id == warehouse_id).select(s3db.inv_warehouse.site_id,
                                                                     limitby=(0, 1),
                                                                     ).first()
        send_id = self.create_send(warehouse.site_id,
                                   to_site_id=None,
                                   send_ref="WB-DOCS-1",
                                   status=SHIP_STATUS_IN_PROCESS,
                                   )
        sendtable = s3db.inv_send
        send_record = db(sendtable.id == send_id).select(sendtable.ALL,
                                                         limitby=(0, 1),
                                                         ).first()

        captured_tabs = []
        saved_tabs = inv_send_rheader.__globals__["s3_rheader_tabs"]
        saved_docs = settings.inv.get("document_filing")
        saved_footer = response_s3.rfooter
        settings.inv.document_filing = True
        response_s3.rfooter = None

        try:
            inv_send_rheader.__globals__["s3_rheader_tabs"] = lambda r, tabs: captured_tabs.extend(tabs) or "SEND-TABS"
            rheader = inv_send_rheader(Storage(representation="html",
                                               name="send",
                                               record=send_record,
                                               table=sendtable,
                                               method=None,
                                               ))
        finally:
            inv_send_rheader.__globals__["s3_rheader_tabs"] = saved_tabs
            settings.inv.document_filing = saved_docs
            response_s3.rfooter = saved_footer

        self.assertIn(("Documents", "document"), [(str(label), component) for label, component in captured_tabs])
        self.assertIn(str(current.messages["NONE"]), str(rheader))
        self.assertIn("SEND-TABS", str(rheader))


# =============================================================================
class InventoryAdjustmentTests(SupplyChainTestCase):
    """Tests for adjustment representers and document helpers"""

    # -------------------------------------------------------------------------
    def testAdjustmentRepresentersAndExpiryDates(self):
        """Adjustment representers summarise quantity changes and highlight expired stock"""

        db = current.db
        s3db = current.s3db

        office = self.create_office()
        adjuster_id = self.create_person(last_name="Adjuster")
        item_id = self.create_supply_item(name="Cleaning Set")
        pack_id = self.create_item_pack(item_id, quantity=1)

        adj_table = s3db.inv_adj
        adj_id = adj_table.insert(site_id=office.site_id,
                                  adjuster_id=adjuster_id,
                                  adjustment_date=current.request.utcnow.date(),
                                  category=1,
                                  status=0,
                                  )
        adj_item_table = s3db.inv_adj_item
        adj_item_id = adj_item_table.insert(adj_id=adj_id,
                                            item_id=item_id,
                                            item_pack_id=pack_id,
                                            old_quantity=10,
                                            new_quantity=7,
                                            )
        saved_item_represent = adj_item_table.item_id.represent
        adj_item_table.item_id.represent = lambda value, show_link=True: "Cleaning Set"
        try:
            # Clear cached person/item representations before rendering
            self._clear_represent_caches()
            adj_repr = InventoryAdjustModel.inv_adj_represent(adj_id, show_link=False)
            adj_item_repr = InventoryAdjustModel.inv_adj_item_represent(adj_item_id,
                                                                        show_link=False,
                                                                        )
        finally:
            adj_item_table.item_id.represent = saved_item_represent
        expired = inv_expiry_date_represent(datetime.date(2020, 1, 1))
        future = inv_expiry_date_represent(datetime.date(2099, 1, 1))

        self.assertIn(" - ", str(adj_repr))
        self.assertIn("Cleaning Set", str(adj_item_repr))
        self.assertIn("-3", str(adj_item_repr))
        self.assertEqual(InventoryAdjustModel.inv_adj_represent(None), current.messages["NONE"])
        self.assertEqual(InventoryAdjustModel.inv_adj_item_represent(None), current.messages["NONE"])
        self.assertIn("expired", str(expired))
        self.assertNotIn("expired", str(future))

    # -------------------------------------------------------------------------
    def testAdjustmentOnacceptBuildsItemsForPositiveStockAndFormatsNoneQuantity(self):
        """Adjustment onaccept expands stocktake lines from positive stock and preserves None quantities"""

        db = current.db
        s3db = current.s3db

        office = self.create_office()
        adjuster_id = self.create_person(last_name="Stocktaker")
        item_a = self.create_supply_item(name="Positive Stock")
        item_b = self.create_supply_item(name="Zero Stock")
        pack_a = self.create_item_pack(item_a, quantity=1)
        pack_b = self.create_item_pack(item_b, quantity=1)
        self.create_inventory_item(office.site_id,
                                   item_a,
                                   pack_a,
                                   quantity=5,
                                   )
        self.create_inventory_item(office.site_id,
                                   item_b,
                                   pack_b,
                                   quantity=0,
                                   )

        adj_id = s3db.inv_adj.insert(site_id=office.site_id,
                                     adjuster_id=adjuster_id,
                                     adjustment_date=current.request.utcnow.date(),
                                     category=1,
                                     status=0,
                                     )

        form = self.make_form(id=adj_id, site_id=office.site_id)
        InventoryAdjustModel.inv_adj_onaccept(form)

        rows = db(s3db.inv_adj_item.adj_id == adj_id).select(s3db.inv_adj_item.item_id)

        self.assertEqual({row.item_id for row in rows}, {item_a})
        self.assertTrue(isinstance(InventoryAdjustModel.qnty_adj_repr(None), B))
        self.assertNotEqual(InventoryAdjustModel.qnty_adj_repr(2), current.messages["NONE"])

    # -------------------------------------------------------------------------
    def testAdjustmentRheaderAndPdfFootersRenderExpectedSections(self):
        """Adjustment headers and shipment PDF footers render their workflow sections"""

        db = current.db
        s3db = current.s3db
        auth = current.auth

        office = self.create_office()
        adjuster_id = self.create_person(last_name="Counter")
        adj_table = s3db.inv_adj
        adj_id = adj_table.insert(site_id=office.site_id,
                                  adjuster_id=adjuster_id,
                                  adjustment_date=current.request.utcnow.date(),
                                  category=1,
                                  status=0,
                                  )
        record = db(adj_table.id == adj_id).select(adj_table.ALL,
                                                   limitby=(0, 1),
                                                   ).first()

        saved_tabs = inv_adj_rheader.__globals__["s3_rheader_tabs"]
        saved_permission = auth.s3_has_permission
        auth.s3_has_permission = lambda *args, **kwargs: True
        inv_adj_rheader.__globals__["s3_rheader_tabs"] = lambda r, tabs: "ADJ-TABS"
        try:
            rheader = inv_adj_rheader(Storage(representation="html",
                                             name="adj",
                                             record=record,
                                             table=adj_table,
                                             ))
        finally:
            inv_adj_rheader.__globals__["s3_rheader_tabs"] = saved_tabs
            auth.s3_has_permission = saved_permission

        send_footer = inv_send_pdf_footer(Storage(record=Storage(id=1)))
        recv_footer = inv_recv_pdf_footer(Storage(record=Storage(id=1)))

        self.assertIn("Complete Adjustment", str(rheader))
        self.assertIn("ADJ-TABS", str(rheader))
        self.assertIn("Commodities Loaded", str(send_footer))
        self.assertIn("Delivered By", str(recv_footer))
        self.assertIsNone(inv_send_pdf_footer(Storage(record=None)))
        self.assertIsNone(inv_recv_pdf_footer(Storage(record=None)))

    # -------------------------------------------------------------------------
    def testAdjustmentRheaderOmitsCloseActionWhenUnauthorizedOrAlreadyClosed(self):
        """Adjustment rheaders do not expose the close button when it must not be used"""

        db = current.db
        s3db = current.s3db
        auth = current.auth

        office = self.create_office()
        adjuster_id = self.create_person(last_name="Closer")
        adj_table = s3db.inv_adj
        open_id = adj_table.insert(site_id=office.site_id,
                                   adjuster_id=adjuster_id,
                                   adjustment_date=current.request.utcnow.date(),
                                   category=1,
                                   status=0,
                                   )
        closed_id = adj_table.insert(site_id=office.site_id,
                                     adjuster_id=adjuster_id,
                                     adjustment_date=current.request.utcnow.date(),
                                     category=1,
                                     status=1,
                                     )
        open_record = db(adj_table.id == open_id).select(adj_table.ALL,
                                                         limitby=(0, 1),
                                                         ).first()
        closed_record = db(adj_table.id == closed_id).select(adj_table.ALL,
                                                             limitby=(0, 1),
                                                             ).first()

        saved_tabs = inv_adj_rheader.__globals__["s3_rheader_tabs"]
        saved_permission = auth.s3_has_permission
        inv_adj_rheader.__globals__["s3_rheader_tabs"] = lambda r, tabs: "ADJ-TABS"

        try:
            auth.s3_has_permission = lambda *args, **kwargs: False
            unauthorized = inv_adj_rheader(Storage(representation="html",
                                                   name="adj",
                                                   record=open_record,
                                                   table=adj_table,
                                                   ))

            auth.s3_has_permission = lambda *args, **kwargs: True
            closed = inv_adj_rheader(Storage(representation="html",
                                             name="adj",
                                             record=closed_record,
                                             table=adj_table,
                                             ))
        finally:
            inv_adj_rheader.__globals__["s3_rheader_tabs"] = saved_tabs
            auth.s3_has_permission = saved_permission

        self.assertNotIn("Complete Adjustment", str(unauthorized))
        self.assertIn("ADJ-TABS", str(unauthorized))
        self.assertNotIn("Complete Adjustment", str(closed))
        self.assertIn("ADJ-TABS", str(closed))


# =============================================================================
class InventoryControllerTests(SupplyChainTestCase):
    """Tests for inventory controller wrappers and hooks"""

    # -------------------------------------------------------------------------
    def testInvIndexUsesCustomHome(self):
        """index delegates to the deployment home customisation"""

        fake_settings = Storage(has_module=current.deployment_settings.has_module,
                                customise_home=lambda module, alt_function=None: \
                                    {"module": module,
                                     "alt_function": alt_function,
                                     },
                                )

        with self.controller("inv",
                             function="index",
                             overrides={"settings": fake_settings},
                             ) as controller:
            output = controller.module["index"]()

        self.assertEqual(output["module"], "inv")
        self.assertEqual(output["alt_function"], "index_alt")

    # -------------------------------------------------------------------------
    def testInvIndexAltRedirectsToWarehouseSummary(self):
        """index_alt redirects non-admin users to the warehouse summary"""

        with self.controller("inv", function="index_alt") as controller:
            with self.assertRaises(ControllerRedirect) as redirect:
                controller.module["index_alt"]()

        self.assertIn("/inv/warehouse/summary", str(redirect.exception.url))

    # -------------------------------------------------------------------------
    def testWarehouseControllerSupportsExtraDataAndNativeTabs(self):
        """warehouse controller adapts resource name and native mode to the request"""

        with self.controller("inv",
                             function="warehouse",
                             query_vars={"extra_data": "1"},
                             ) as controller:
            output = controller.module["warehouse"]()

        self.assertEqual(output.args, ("inv", "inv_item"))
        self.assertEqual(output.kwargs["csv_stylesheet"], "inv_item.xsl")
        self.assertEqual(output.kwargs["csv_template"], "inv_item")
        self.assertFalse(output.kwargs["native"])

        with self.controller("inv",
                             function="warehouse",
                             args=["1", "send"],
                             ) as controller:
            output = controller.module["warehouse"]()

        self.assertEqual(output.args, ("inv", "warehouse"))
        self.assertTrue(output.kwargs["native"])

    # -------------------------------------------------------------------------
    def testWarehouseTypeUsesCrudController(self):
        """warehouse_type delegates to the generic CRUD controller"""

        with self.controller("inv", function="warehouse_type") as controller:
            output = controller.module["warehouse_type"]()

        self.assertEqual(output.args, ())

    # -------------------------------------------------------------------------
    def testWarehousePrepAdjustsInvItemListFields(self):
        """warehouse prep configures inventory items without the site field"""

        s3db = current.s3db
        saved_list_fields = s3db.get_config("inv_inv_item", "list_fields")
        saved_prep = s3db.inv_prep
        inv_prep_calls = []

        s3db.configure("inv_inv_item",
                       list_fields=["site_id", "item_id", "quantity"],
                       )
        s3db.inv_prep = lambda r: inv_prep_calls.append(r.component_name)

        try:
            with self.controller("inv", function="warehouse") as controller:
                output = controller.module["warehouse"]()
                prep = output.prep
                filters = []
                r = Storage(component=Storage(name="inv_item"),
                            component_name="inv_item",
                            record=Storage(site_id=1),
                            method=None,
                            vars=Storage(),
                            representation="html",
                            resource=Storage(add_filter=lambda query: filters.append(query),
                                             get_config=lambda key: None,
                                             ),
                            )
                self.assertTrue(prep(r))
                configured = s3db.get_config("inv_inv_item", "list_fields")
        finally:
            s3db.inv_prep = saved_prep
            s3db.configure("inv_inv_item", list_fields=saved_list_fields)

        self.assertEqual(inv_prep_calls, ["inv_item"])
        self.assertEqual(configured, ["item_id", "quantity"])
        self.assertGreaterEqual(len(filters), 1)

    # -------------------------------------------------------------------------
    def testWarehousePrepAndPostpCoverRemainingComponentBranches(self):
        """warehouse prep/postp handle recv, send, staff, req, asset and export branches"""

        db = current.db
        s3db = current.s3db
        auth = current.auth

        office = self.create_office(name="Warehouse Branch Office")
        warehouse_id = self.create_warehouse(code="WH-BRANCH")
        item_id = self.create_supply_item(name="Branch Item")
        pack_id = self.create_item_pack(item_id, quantity=1)
        recv_id = self.create_recv(office.site_id,
                                   from_site_id=office.site_id,
                                   status=s3db.inv_ship_status["SENT"],
                                   )

        warehouse = db(s3db.inv_warehouse.id == warehouse_id).select(s3db.inv_warehouse.ALL,
                                                                     limitby=(0, 1),
                                                                     ).first()
        recv_record = db(s3db.inv_recv.id == recv_id).select(s3db.inv_recv.ALL,
                                                             limitby=(0, 1),
                                                             ).first()

        saved_prep = s3db.inv_prep
        saved_staff_config = s3db.org_site_staff_config
        saved_req_mods = s3db.req_create_form_mods
        saved_asset_create_next = s3db.get_config("asset_asset", "create_next")
        saved_asset_org = Storage(default=s3db.asset_asset.organisation_id.default,
                                  readable=s3db.asset_asset.organisation_id.readable,
                                  writable=s3db.asset_asset.organisation_id.writable,
                                  )
        saved_asset_site = Storage(default=s3db.asset_asset.site_id.default,
                                   readable=s3db.asset_asset.site_id.readable,
                                   writable=s3db.asset_asset.site_id.writable,
                                   )
        saved_recv_ref = s3db.inv_recv.recv_ref.readable
        saved_recv_status = s3db.inv_recv.status.readable
        saved_obsolete = Storage(readable=s3db.inv_warehouse.obsolete.readable,
                                 writable=s3db.inv_warehouse.obsolete.writable,
                                 )
        inv_prep_calls = []
        staff_calls = []
        req_mods_calls = []
        postp_calls = []

        s3db.inv_prep = lambda r: inv_prep_calls.append(r.component_name)
        s3db.org_site_staff_config = lambda r: staff_calls.append(r.component_name)
        s3db.req_create_form_mods = lambda: req_mods_calls.append("req")

        try:
            with self.controller("inv", function="warehouse") as controller:
                output = controller.module["warehouse"]()
                prep = output.prep
                postp = output.postp
                globals_ = prep.__globals__
                saved_set_recv_attr = globals_["set_recv_attr"]
                saved_action_buttons = postp.__globals__["s3_action_buttons"]
                set_recv_calls = []
                xlsx_fields = ["name"]
                filters = []
                globals_["set_recv_attr"] = lambda status: set_recv_calls.append(status)
                postp.__globals__["s3_action_buttons"] = lambda r, **kwargs: postp_calls.append(kwargs)
                try:
                    self.assertTrue(prep(Storage(component=Storage(name="recv"),
                                                 component_name="recv",
                                                 component_id=recv_id,
                                                 method="update",
                                                 record=recv_record,
                                                 vars=Storage(),
                                                 representation="html",
                                                 resource=Storage(add_filter=lambda query: filters.append(query),
                                                                  get_config=lambda key: None,
                                                                  ),
                                                 )))
                    self.assertTrue(prep(Storage(component=Storage(name="recv"),
                                                 component_name="recv",
                                                 component_id=None,
                                                 method="create",
                                                 record=recv_record,
                                                 vars=Storage(),
                                                 representation="html",
                                                 resource=Storage(add_filter=lambda query: filters.append(query),
                                                                  get_config=lambda key: None,
                                                                  ),
                                                 )))
                    recv_ref_readable = s3db.inv_recv.recv_ref.readable
                    recv_status_readable = s3db.inv_recv.status.readable
                    self.assertTrue(prep(Storage(component=Storage(name="send"),
                                                 component_name="send",
                                                 component_id=None,
                                                 method=None,
                                                 record=warehouse,
                                                 vars=Storage(),
                                                 representation="html",
                                                 resource=Storage(add_filter=lambda query: filters.append(query),
                                                                  get_config=lambda key: None,
                                                                  ),
                                                 )))
                    self.assertTrue(prep(Storage(component=Storage(name="human_resource"),
                                                 component_name="human_resource",
                                                 component_id=None,
                                                 method=None,
                                                 record=warehouse,
                                                 vars=Storage(),
                                                 representation="html",
                                                 resource=Storage(add_filter=lambda query: filters.append(query),
                                                                  get_config=lambda key: None,
                                                                  ),
                                                 )))
                    self.assertTrue(prep(Storage(component=Storage(name="req"),
                                                 component_name="req",
                                                 component_id=None,
                                                 method="create",
                                                 record=warehouse,
                                                 vars=Storage(),
                                                 representation="html",
                                                 resource=Storage(add_filter=lambda query: filters.append(query),
                                                                  get_config=lambda key: None,
                                                                  ),
                                                 )))
                    self.assertTrue(prep(Storage(component=Storage(name="asset"),
                                                 component_name="asset",
                                                 component_id=None,
                                                 method="create",
                                                 record=Storage(organisation_id=office.organisation_id,
                                                                site_id=office.site_id,
                                                                ),
                                                 vars=Storage(),
                                                 representation="html",
                                                 resource=Storage(add_filter=lambda query: filters.append(query),
                                                                  get_config=lambda key: None,
                                                                  ),
                                                 )))
                    asset_org_default = s3db.asset_asset.organisation_id.default
                    asset_org_readable = s3db.asset_asset.organisation_id.readable
                    asset_org_writable = s3db.asset_asset.organisation_id.writable
                    asset_site_default = s3db.asset_asset.site_id.default
                    asset_site_readable = s3db.asset_asset.site_id.readable
                    asset_site_writable = s3db.asset_asset.site_id.writable
                    asset_create_next = s3db.get_config("asset_asset", "create_next")
                    self.assertTrue(prep(Storage(component=None,
                                                 id=warehouse_id,
                                                 table=s3db.inv_warehouse,
                                                 method="list",
                                                 vars=Storage(),
                                                 representation="xlsx",
                                                 resource=Storage(add_filter=lambda query: filters.append(query),
                                                                  get_config=lambda key: xlsx_fields if key == "list_fields" else None,
                                                                  ),
                                                 )))
                    obsolete_readable = s3db.inv_warehouse.obsolete.readable
                    obsolete_writable = s3db.inv_warehouse.obsolete.writable

                    saved_permission = auth.s3_has_permission
                    auth.s3_has_permission = lambda *args, **kwargs: True
                    try:
                        result = postp(Storage(interactive=False,
                                               component=Storage(name="human_resource"),
                                               component_name="human_resource",
                                               method=None,
                                               get_vars=Storage(),
                                               ),
                                       {"add_btn": "Add"})
                    finally:
                        auth.s3_has_permission = saved_permission
                finally:
                    globals_["set_recv_attr"] = saved_set_recv_attr
                    postp.__globals__["s3_action_buttons"] = saved_action_buttons
        finally:
            s3db.inv_prep = saved_prep
            s3db.org_site_staff_config = saved_staff_config
            s3db.req_create_form_mods = saved_req_mods
            s3db.configure("asset_asset", create_next=saved_asset_create_next)
            s3db.asset_asset.organisation_id.default = saved_asset_org.default
            s3db.asset_asset.organisation_id.readable = saved_asset_org.readable
            s3db.asset_asset.organisation_id.writable = saved_asset_org.writable
            s3db.asset_asset.site_id.default = saved_asset_site.default
            s3db.asset_asset.site_id.readable = saved_asset_site.readable
            s3db.asset_asset.site_id.writable = saved_asset_site.writable
            s3db.inv_recv.recv_ref.readable = saved_recv_ref
            s3db.inv_recv.status.readable = saved_recv_status
            s3db.inv_warehouse.obsolete.readable = saved_obsolete.readable
            s3db.inv_warehouse.obsolete.writable = saved_obsolete.writable

        self.assertEqual(inv_prep_calls.count("recv"), 2)
        self.assertIn("send", inv_prep_calls)
        self.assertEqual(staff_calls, ["human_resource"])
        self.assertEqual(req_mods_calls, ["req"])
        self.assertEqual(set_recv_calls,
                         [s3db.inv_ship_status["SENT"],
                          s3db.inv_ship_status["IN_PROCESS"]])
        self.assertFalse(recv_ref_readable)
        self.assertFalse(recv_status_readable)
        self.assertEqual(asset_org_default, office.organisation_id)
        self.assertFalse(asset_org_readable)
        self.assertFalse(asset_org_writable)
        self.assertEqual(asset_site_default, office.site_id)
        self.assertFalse(asset_site_readable)
        self.assertFalse(asset_site_writable)
        self.assertIsNone(asset_create_next)
        self.assertTrue(obsolete_readable)
        self.assertTrue(obsolete_writable)
        self.assertEqual(xlsx_fields[-3:],
                         ["location_id$lat", "location_id$lon", "location_id$inherited"])
        self.assertGreaterEqual(len(filters), 1)
        self.assertNotIn("add_btn", result)
        self.assertIn("/hrm/staff/", str(postp_calls[0]["read_url"]))
        self.assertIn("/hrm/staff/", str(postp_calls[0]["update_url"]))

    # -------------------------------------------------------------------------
    def testWarehousePostpRemovesAddButtonAndOpensStockTab(self):
        """warehouse postp removes add_btn and rewrites read/update buttons"""

        auth = current.auth

        with self.controller("inv", function="warehouse") as controller:
            output = controller.module["warehouse"]()
            postp = output.postp
            calls = []
            globals_ = postp.__globals__
            saved = globals_["s3_action_buttons"]
            saved_permission = auth.s3_has_permission

            globals_["s3_action_buttons"] = lambda r, **kwargs: calls.append(kwargs)
            auth.s3_has_permission = lambda *args, **kwargs: True
            try:
                r = Storage(interactive=True,
                            component=None,
                            method=None,
                            get_vars=Storage(),
                            )
                result = postp(r, {"add_btn": "Add"})
            finally:
                globals_["s3_action_buttons"] = saved
                auth.s3_has_permission = saved_permission

        self.assertNotIn("add_btn", result)
        self.assertEqual(len(calls), 1)
        self.assertIn("/inv/warehouse/", str(calls[0]["read_url"]))
        self.assertIn("/inv_item", str(calls[0]["read_url"]))
        self.assertIn("/inv/warehouse/", str(calls[0]["update_url"]))
        self.assertIn("/inv_item", str(calls[0]["update_url"]))

    # -------------------------------------------------------------------------
    def testSupplierControllerFiltersOrganisationTypeAndDelegates(self):
        """supplier controller filters to suppliers and delegates to org controller"""

        s3db = current.s3db
        saved = s3db.org_organisation_controller
        saved_next = s3db.get_config("org_organisation", "create_next")
        s3db.org_organisation_controller = lambda: "ORG-CONTROLLER"

        try:
            with self.controller("inv", function="supplier") as controller:
                output = controller.module["supplier"]()
                organisation_type = current.request.get_vars["organisation_type.name"]
                create_next = s3db.get_config("org_organisation", "create_next")
        finally:
            s3db.org_organisation_controller = saved
            s3db.configure("org_organisation", create_next=saved_next)

        self.assertEqual(output, "ORG-CONTROLLER")
        self.assertEqual(organisation_type, "Supplier")
        expected = URL(c="inv", f="supplier", args=["[id]", "read"])
        self.assertEqual(create_next, expected)

    # -------------------------------------------------------------------------
    def testTrackMovementPrepFiltersViewedInventoryItem(self):
        """track_movement filters tracking rows to the viewed inventory item"""

        s3db = current.s3db
        saved_config = Storage(create=s3db.get_config("inv_track_item", "create"),
                               deletable=s3db.get_config("inv_track_item", "deletable"),
                               editable=s3db.get_config("inv_track_item", "editable"),
                               listadd=s3db.get_config("inv_track_item", "listadd"),
                               )
        inv_item_id = 42

        try:
            with self.controller("inv",
                                 function="track_movement",
                                 query_vars={"viewing": "inv_inv_item.%s" % inv_item_id},
                                 ) as controller:
                output = controller.module["track_movement"]()
                prep = output.prep
                filters = []
                r = Storage(interactive=True,
                            resource=Storage(add_filter=lambda query: filters.append(query)),
                            )
                self.assertTrue(prep(r))
                create = s3db.get_config("inv_track_item", "create")
                listadd = s3db.get_config("inv_track_item", "listadd")
        finally:
            s3db.configure("inv_track_item",
                           create=saved_config.create,
                           deletable=saved_config.deletable,
                           editable=saved_config.editable,
                           listadd=saved_config.listadd,
                           )

        self.assertEqual(output.args, ("inv", "track_item"))
        self.assertFalse(create)
        self.assertFalse(listadd)
        self.assertEqual(len(filters), 1)

    # -------------------------------------------------------------------------
    def testInvItemQuantityEndpointReturnsJson(self):
        """inv_item_quantity returns stock and pack quantities as JSON"""

        office = self.create_office()
        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id, quantity=6)
        inv_item_id = self.create_inventory_item(office.site_id,
                                                 item_id,
                                                 pack_id,
                                                 quantity=4,
                                                 )

        with self.controller("inv",
                             function="inv_item_quantity",
                             args=[str(inv_item_id)],
                             ) as controller:
            output = controller.module["inv_item_quantity"]()
            content_type = current.response.headers["Content-Type"]

        payload = json.loads(output)
        self.assertEqual(content_type, "application/json")
        self.assertEqual(payload["iquantity"], 4)
        self.assertEqual(payload["pquantity"], 6)

    # -------------------------------------------------------------------------
    def testInvItemPacksEndpointReturnsPackOptionsAsJson(self):
        """inv_item_packs returns all packs for the stock item's supply item"""

        office = self.create_office()
        item_id = self.create_supply_item()
        pack_a = self.create_item_pack(item_id, name="one", quantity=1)
        pack_b = self.create_item_pack(item_id, name="ten", quantity=10)
        inv_item_id = self.create_inventory_item(office.site_id,
                                                 item_id,
                                                 pack_a,
                                                 quantity=4,
                                                 )

        with self.controller("inv",
                             function="inv_item_packs",
                             args=[str(inv_item_id)],
                             ) as controller:
            output = controller.module["inv_item_packs"]()
            content_type = current.response.headers["Content-Type"]

        payload = json.loads(output)
        pack_ids = {row["id"] for row in payload}
        self.assertEqual(content_type, "application/json")
        self.assertIn(pack_a, pack_ids)
        self.assertIn(pack_b, pack_ids)

    # -------------------------------------------------------------------------
    def testInvItemRedirectsTrackItemViewsToTrackMovement(self):
        """inv_item redirects viewing inv_track_item rows to track_movement"""

        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id, quantity=1)
        track_item_id = self.create_track_item(item_id,
                                               pack_id,
                                               quantity=1,
                                               )

        with self.controller("inv",
                             function="inv_item",
                             query_vars={"viewing": "inv_track_item.%s" % track_item_id},
                             ) as controller:
            with self.assertRaises(ControllerRedirect) as redirect:
                controller.module["inv_item"]()

        url = str(redirect.exception.url)
        self.assertIn("/inv/track_movement", url)
        self.assertIn("viewing=inv_inv_item.%s" % item_id, url)

    # -------------------------------------------------------------------------
    def testInvItemMonetizationReportAndImportReplace(self):
        """inv_item configures monetization reports and import replacement cleanup"""

        s3db = current.s3db
        response_s3 = current.response.s3

        saved_list_fields = s3db.get_config("inv_inv_item", "list_fields")
        saved_strings = response_s3.crud_strings["inv_inv_item"]
        saved_import_prep = getattr(response_s3, "import_prep", None)
        saved_import_replace = getattr(response_s3, "import_replace", None)
        saved_resource = s3db.resource
        deleted = []

        class FakeOrgNode:
            def __init__(self, value):
                self.text = None
                self.value = value

            def get(self, key, default=None):
                return self.value if key == "value" else default

        class FakeRoot:
            @staticmethod
            def xpath(expr):
                return [FakeOrgNode("Import Org")]

        class FakeTree:
            @staticmethod
            def getroot():
                return FakeRoot()

        s3db.resource = lambda tablename, filter=None: \
            Storage(delete=lambda **kwargs: deleted.append((tablename, kwargs)))

        try:
            response_s3.import_replace = True
            with self.controller("inv",
                                 function="inv_item",
                                 query_vars={"report": "mon"},
                                 ) as controller:
                output = controller.module["inv_item"]()
                list_fields = s3db.get_config("inv_inv_item", "list_fields")
                title = response_s3.crud_strings["inv_inv_item"].title_list
                import_prep = response_s3.import_prep
                import_prep(FakeTree())
        finally:
            s3db.resource = saved_resource
            s3db.configure("inv_inv_item", list_fields=saved_list_fields)
            response_s3.crud_strings["inv_inv_item"] = saved_strings
            response_s3.import_prep = saved_import_prep
            response_s3.import_replace = saved_import_replace

        self.assertEqual(output.kwargs["pdf_orientation"], "Landscape")
        self.assertTrue(any("total_value" in str(field) for field in list_fields))
        self.assertEqual(str(title), "Monetization Report")
        self.assertEqual(deleted,
                         [("inv_inv_item",
                           {"format": "xml", "cascade": True})])

    # -------------------------------------------------------------------------
    def testInvItemDefaultBranchFiltersZeroStockAndRemovesAddButton(self):
        """inv_item default branch filters zero stock and hides add button without direct edits"""

        s3db = current.s3db
        response_s3 = current.response.s3

        fake_settings = Storage(has_module=current.deployment_settings.has_module,
                                get_inv_direct_stock_edits=lambda: False,
                                )
        saved_filter = response_s3.filter
        saved_list_fields = s3db.get_config("inv_inv_item", "list_fields")
        saved_insertable = s3db.get_config("inv_inv_item", "insertable")

        try:
            with self.controller("inv",
                                 function="inv_item",
                                 overrides={"settings": fake_settings,
                                            "crud_controller": lambda **kwargs: {"add_btn": "Add"},
                                            },
                                 ) as controller:
                output = controller.module["inv_item"]()
                list_fields = s3db.get_config("inv_inv_item", "list_fields")
                insertable = s3db.get_config("inv_inv_item", "insertable")
                filter_ = response_s3.filter
        finally:
            response_s3.filter = saved_filter
            s3db.configure("inv_inv_item",
                           list_fields=saved_list_fields,
                           insertable=saved_insertable,
                           )

        self.assertNotIn("add_btn", output)
        self.assertEqual(list_fields,
                         ["id",
                          "site_id",
                          "item_id",
                          "item_id$code",
                          "item_id$item_category_id",
                          "quantity",
                          "pack_value",
                          ])
        self.assertFalse(insertable)
        self.assertIsNotNone(filter_)

    # -------------------------------------------------------------------------
    def testSendWrappersDelegateToModelMethods(self):
        """send wrappers delegate to the corresponding model methods"""

        s3db = current.s3db
        saved_send = s3db.inv_send_controller
        saved_commit = s3db.req_send_commit
        saved_process = s3db.inv_send_process
        s3db.inv_send_controller = lambda: "SEND"
        s3db.req_send_commit = lambda: "SEND-COMMIT"
        s3db.inv_send_process = lambda: "SEND-PROCESS"

        try:
            with self.controller("inv", function="send") as controller:
                send_output = controller.module["send"]()

            with self.controller("inv", function="send_commit") as controller:
                commit_output = controller.module["send_commit"]()

            with self.controller("inv", function="send_process") as controller:
                process_output = controller.module["send_process"]()
        finally:
            s3db.inv_send_controller = saved_send
            s3db.req_send_commit = saved_commit
            s3db.inv_send_process = saved_process

        self.assertEqual(send_output, "SEND")
        self.assertEqual(commit_output, "SEND-COMMIT")
        self.assertEqual(process_output, "SEND-PROCESS")

    # -------------------------------------------------------------------------
    def testShipmentWorkflowControllersRedirectWithoutIds(self):
        """Shipment workflow controllers fall back to list views when record IDs are missing"""

        with self.controller("inv", function="send_returns") as controller:
            globals_ = controller.module["send_returns"].__globals__
            saved_redirect = globals_["redirect"]
            globals_["redirect"] = lambda *args, **kwargs: \
                (_ for _ in ()).throw(ControllerRedirect(kwargs.get("f") or args[0]))
            with self.assertRaises(ControllerRedirect) as redirect:
                try:
                    controller.module["send_returns"]()
                finally:
                    globals_["redirect"] = saved_redirect
            send_returns_url = str(redirect.exception.url)

        with self.controller("inv", function="return_process") as controller:
            globals_ = controller.module["return_process"].__globals__
            saved_redirect = globals_["redirect"]
            globals_["redirect"] = lambda *args, **kwargs: \
                (_ for _ in ()).throw(ControllerRedirect(kwargs.get("f") or args[0]))
            with self.assertRaises(ControllerRedirect) as redirect:
                try:
                    controller.module["return_process"]()
                finally:
                    globals_["redirect"] = saved_redirect
            return_process_url = str(redirect.exception.url)

        with self.controller("inv", function="send_cancel") as controller:
            globals_ = controller.module["send_cancel"].__globals__
            saved_redirect = globals_["redirect"]
            globals_["redirect"] = lambda *args, **kwargs: \
                (_ for _ in ()).throw(ControllerRedirect(kwargs.get("f") or args[0]))
            with self.assertRaises(ControllerRedirect) as redirect:
                try:
                    controller.module["send_cancel"]()
                finally:
                    globals_["redirect"] = saved_redirect
            send_cancel_url = str(redirect.exception.url)

        with self.controller("inv", function="recv_process") as controller:
            with self.assertRaises(ControllerRedirect) as redirect:
                controller.module["recv_process"]()
            recv_process_url = str(redirect.exception.url)

        with self.controller("inv", function="recv_cancel") as controller:
            globals_ = controller.module["recv_cancel"].__globals__
            saved_redirect = globals_["redirect"]
            globals_["redirect"] = lambda *args, **kwargs: \
                (_ for _ in ()).throw(ControllerRedirect(kwargs.get("f") or args[0]))
            with self.assertRaises(ControllerRedirect) as redirect:
                try:
                    controller.module["recv_cancel"]()
                finally:
                    globals_["redirect"] = saved_redirect
            recv_cancel_url = str(redirect.exception.url)

        self.assertEqual(send_returns_url, "send")
        self.assertEqual(return_process_url, "send")
        self.assertEqual(send_cancel_url, "send")
        self.assertIn("/inv/recv", recv_process_url)
        self.assertIn("/inv/recv", recv_cancel_url)

    # -------------------------------------------------------------------------
    def testShipmentWorkflowControllersRejectPermissionFailures(self):
        """Shipment workflow controllers reject users without the required permissions"""

        auth = current.auth
        session = current.session
        s3db = current.s3db

        origin = self.create_office(name="Permission Origin")
        destination = self.create_office(name="Permission Destination")

        send_returns_id = self.create_send(origin.site_id,
                                           to_site_id=destination.site_id,
                                           status=s3db.inv_ship_status["SENT"],
                                           )
        return_process_id = self.create_send(origin.site_id,
                                             to_site_id=destination.site_id,
                                             status=s3db.inv_ship_status["RETURNING"],
                                             )
        send_cancel_id = self.create_send(origin.site_id,
                                          to_site_id=destination.site_id,
                                          status=s3db.inv_ship_status["SENT"],
                                          )
        recv_process_id = self.create_recv(destination.site_id,
                                           from_site_id=origin.site_id,
                                           status=s3db.inv_ship_status["SENT"],
                                           )
        recv_cancel_id = self.create_recv(destination.site_id,
                                          from_site_id=origin.site_id,
                                          status=s3db.inv_ship_status["RECEIVED"],
                                          )

        saved_permission = auth.s3_has_permission
        saved_error = session.error
        auth.s3_has_permission = lambda *args, **kwargs: False

        try:
            session.error = None
            with self.controller("inv",
                                 function="send_returns",
                                 args=[str(send_returns_id)],
                                 ) as controller:
                with self.assertRaises(ControllerRedirect) as redirect:
                    controller.module["send_returns"]()
                send_returns_url = str(redirect.exception.url)
                send_returns_error = session.error

            session.error = None
            with self.controller("inv",
                                 function="return_process",
                                 args=[str(return_process_id)],
                                 ) as controller:
                with self.assertRaises(ControllerRedirect) as redirect:
                    controller.module["return_process"]()
                return_process_url = str(redirect.exception.url)
                return_process_error = session.error

            session.error = None
            with self.controller("inv",
                                 function="send_cancel",
                                 args=[str(send_cancel_id)],
                                 ) as controller:
                with self.assertRaises(ControllerRedirect) as redirect:
                    controller.module["send_cancel"]()
                send_cancel_url = str(redirect.exception.url)
                send_cancel_error = session.error

            session.error = None
            with self.controller("inv",
                                 function="recv_process",
                                 args=[str(recv_process_id)],
                                 ) as controller:
                with self.assertRaises(ControllerRedirect) as redirect:
                    controller.module["recv_process"]()
                recv_process_url = str(redirect.exception.url)
                recv_process_error = session.error

            session.error = None
            with self.controller("inv",
                                 function="recv_cancel",
                                 args=[str(recv_cancel_id)],
                                 ) as controller:
                with self.assertRaises(ControllerRedirect) as redirect:
                    controller.module["recv_cancel"]()
                recv_cancel_url = str(redirect.exception.url)
                recv_cancel_error = session.error
        finally:
            auth.s3_has_permission = saved_permission
            session.error = saved_error

        self.assertIn("/inv/send/%s" % send_returns_id, send_returns_url)
        self.assertEqual(str(send_returns_error),
                         "You do not have permission to return this sent shipment.")
        self.assertIn("/inv/send/%s" % return_process_id, return_process_url)
        self.assertEqual(str(return_process_error),
                         "You do not have permission to return this sent shipment.")
        self.assertIn("/inv/send/%s" % send_cancel_id, send_cancel_url)
        self.assertEqual(str(send_cancel_error),
                         "You do not have permission to cancel this sent shipment.")
        self.assertIn("/inv/recv/%s" % recv_process_id, recv_process_url)
        self.assertEqual(str(recv_process_error),
                         "You do not have permission to receive this shipment.")
        self.assertIn("/inv/recv/%s" % recv_cancel_id, recv_cancel_url)
        self.assertEqual(str(recv_cancel_error),
                         "You do not have permission to cancel this received shipment.")

    # -------------------------------------------------------------------------
    def testSendControllerInitialisesQuantityValidatorAndSimplifiesDocuments(self):
        """send initialises stock quantity validation and document components"""

        db = current.db
        s3db = current.s3db
        tracktable = s3db.inv_track_item
        doctable = s3db.doc_document

        origin = self.create_office(name="Validator Origin")
        destination = self.create_office(name="Validator Destination")
        item_id = self.create_supply_item(name="Soap")
        pack_id = self.create_item_pack(item_id, quantity=6)
        inv_item_id = self.create_inventory_item(origin.site_id,
                                                 item_id,
                                                 pack_id,
                                                 quantity=4,
                                                 status=0,
                                                 )
        send_id = self.create_send(origin.site_id,
                                   to_site_id=destination.site_id,
                                   status=SHIP_STATUS_IN_PROCESS,
                                   )

        saved_crud = current.crud_controller
        saved_requires = tracktable.quantity.requires
        saved_item_pack = current.request.vars.get("item_pack_id")
        saved_file_required = doctable.file.required
        saved_url_readable = doctable.url.readable
        saved_url_writable = doctable.url.writable
        saved_date_readable = doctable.date.readable
        saved_date_writable = doctable.date.writable

        try:
            with self.controller("inv",
                                 function="send",
                                 args=[str(send_id), "document"],
                                 query_vars={"send_inv_item_id": str(inv_item_id)},
                                 ) as controller:
                current.crud_controller = lambda *args, **kwargs: Storage(prep=current.response.s3.prep,
                                                                          args=args,
                                                                          kwargs=kwargs,
                                                                          )
                output = controller.module["send"]()
                prep = output.prep
                record = db(s3db.inv_send.id == send_id).select(s3db.inv_send.ALL,
                                                                limitby=(0, 1),
                                                                ).first()
                self.assertTrue(prep(Storage(id=send_id,
                                             record=record,
                                             component=Storage(name="document"),
                                             component_name="document",
                                             component_id=None,
                                             method=None,
                                             interactive=True,
                                             )))
                item_pack_id = current.request.vars.item_pack_id
                requires = tracktable.quantity.requires
                file_required = doctable.file.required
                url_readable = doctable.url.readable
                url_writable = doctable.url.writable
                date_readable = doctable.date.readable
                date_writable = doctable.date.writable
        finally:
            current.crud_controller = saved_crud
            tracktable.quantity.requires = saved_requires
            current.request.vars.item_pack_id = saved_item_pack
            doctable.file.required = saved_file_required
            doctable.url.readable = saved_url_readable
            doctable.url.writable = saved_url_writable
            doctable.date.readable = saved_date_readable
            doctable.date.writable = saved_date_writable

        self.assertEqual(int(item_pack_id), pack_id)
        self.assertEqual(requires.__class__.__name__, "IS_AVAILABLE_QUANTITY")
        self.assertTrue(file_required)
        self.assertFalse(url_readable)
        self.assertFalse(url_writable)
        self.assertFalse(date_readable)
        self.assertFalse(date_writable)

    # -------------------------------------------------------------------------
    def testSendControllerIgnoresUnknownTrackItemParentIds(self):
        """send tolerates track-item tabs opened with unknown parent shipment IDs"""

        s3db = current.s3db
        saved_crud = current.crud_controller
        saved_editable = s3db.get_config("inv_track_item", "editable")
        saved_create = s3db.get_config("inv_track_item", "create")

        try:
            with self.controller("inv",
                                 function="send",
                                 args=["999999", "track_item"],
                                 ) as controller:
                current.crud_controller = lambda *args, **kwargs: Storage(args=args,
                                                                          kwargs=kwargs,
                                                                          )
                output = controller.module["send"]()
                editable = s3db.get_config("inv_track_item", "editable")
                create = s3db.get_config("inv_track_item", "create")
        finally:
            current.crud_controller = saved_crud
            s3db.configure("inv_track_item",
                           editable=saved_editable,
                           create=saved_create,
                           )

        self.assertEqual(output.args, ("inv", "send"))
        self.assertEqual(editable, saved_editable)
        self.assertEqual(create, saved_create)

    # -------------------------------------------------------------------------
    def testSendPrepConfiguresDraftAndLockedShipments(self):
        """send prep hides draft references and locks sent shipment headers"""

        db = current.db
        s3db = current.s3db
        sendtable = s3db.inv_send

        origin = self.create_office(name="Header Origin")
        destination = self.create_office(name="Header Destination")
        send_id = self.create_send(origin.site_id,
                                   to_site_id=destination.site_id,
                                   status=SHIP_STATUS_SENT,
                                   )

        saved_crud = current.crud_controller
        saved_send_ref_readable = sendtable.send_ref.readable
        saved_send_ref_writable = sendtable.send_ref.writable
        saved_comments_writable = sendtable.comments.writable

        try:
            with self.controller("inv",
                                 function="send",
                                 args=[str(send_id)],
                                 ) as controller:
                current.crud_controller = lambda *args, **kwargs: Storage(prep=current.response.s3.prep,
                                                                          args=args,
                                                                          kwargs=kwargs,
                                                                          )
                output = controller.module["send"]()
                prep = output.prep
                self.assertTrue(prep(Storage(id=send_id, component=None)))
                locked_send_ref_writable = sendtable.send_ref.writable
                locked_comments_writable = sendtable.comments.writable

            with self.controller("inv", function="send") as controller:
                current.crud_controller = lambda *args, **kwargs: Storage(prep=current.response.s3.prep,
                                                                          args=args,
                                                                          kwargs=kwargs,
                                                                          )
                output = controller.module["send"]()
                prep = output.prep
                self.assertTrue(prep(Storage(id=None, component=None, method="create")))
                draft_send_ref_readable = sendtable.send_ref.readable
                draft_send_ref_writable = sendtable.send_ref.writable
        finally:
            current.crud_controller = saved_crud
            sendtable.send_ref.readable = saved_send_ref_readable
            sendtable.send_ref.writable = saved_send_ref_writable
            sendtable.comments.writable = saved_comments_writable

        self.assertFalse(locked_send_ref_writable)
        self.assertFalse(locked_comments_writable)
        self.assertFalse(draft_send_ref_readable)
        self.assertFalse(draft_send_ref_writable)

    # -------------------------------------------------------------------------
    def testSendPrepDeletesTrackItemsOnlyWhilePreparing(self):
        """send prep blocks track-item changes after dispatch and delegates draft deletions"""

        db = current.db
        s3db = current.s3db
        tracktable = s3db.inv_track_item

        origin = self.create_office(name="Delete Origin")
        destination = self.create_office(name="Delete Destination")
        item_id = self.create_supply_item(name="Salt")
        pack_id = self.create_item_pack(item_id, quantity=1)
        inv_item_id = self.create_inventory_item(origin.site_id,
                                                 item_id,
                                                 pack_id,
                                                 quantity=4,
                                                 status=0,
                                                 )
        locked_send_id = self.create_send(origin.site_id,
                                          to_site_id=destination.site_id,
                                          status=SHIP_STATUS_SENT,
                                          )
        draft_send_id = self.create_send(origin.site_id,
                                         to_site_id=destination.site_id,
                                         status=SHIP_STATUS_IN_PROCESS,
                                         )
        track_id = self.create_track_item(item_id,
                                          pack_id,
                                          quantity=2,
                                          send_id=draft_send_id,
                                          send_inv_item_id=inv_item_id,
                                          status=s3db.inv_tracking_status["IN_PROCESS"],
                                          )

        deleted = []
        saved_crud = current.crud_controller
        saved_delete = s3db.inv_track_item_deleting
        saved_requires = tracktable.send_inv_item_id.requires

        s3db.inv_track_item_deleting = lambda record_id: deleted.append(record_id) or "DELETED"

        try:
            with self.controller("inv",
                                 function="send",
                                 args=[str(locked_send_id), "track_item"],
                                 ) as controller:
                current.crud_controller = lambda *args, **kwargs: Storage(prep=current.response.s3.prep,
                                                                          args=args,
                                                                          kwargs=kwargs,
                                                                          )
                output = controller.module["send"]()
                prep = output.prep
                record = db(s3db.inv_send.id == locked_send_id).select(s3db.inv_send.ALL,
                                                                       limitby=(0, 1),
                                                                       ).first()
                locked = prep(Storage(id=locked_send_id,
                                      record=record,
                                      component=Storage(name="track_item"),
                                      component_name="track_item",
                                      component_id=track_id,
                                      method="delete",
                                      interactive=True,
                                      now=current.request.utcnow.date(),
                                      ))

            with self.controller("inv",
                                 function="send",
                                 args=[str(draft_send_id), "track_item"],
                                 ) as controller:
                current.crud_controller = lambda *args, **kwargs: Storage(prep=current.response.s3.prep,
                                                                          args=args,
                                                                          kwargs=kwargs,
                                                                          )
                output = controller.module["send"]()
                prep = output.prep
                record = db(s3db.inv_send.id == draft_send_id).select(s3db.inv_send.ALL,
                                                                      limitby=(0, 1),
                                                                      ).first()
                deleted_result = prep(Storage(id=draft_send_id,
                                              record=record,
                                              component=Storage(name="track_item"),
                                              component_name="track_item",
                                              component_id=track_id,
                                              method="delete",
                                              interactive=True,
                                              now=current.request.utcnow.date(),
                                              ))
        finally:
            current.crud_controller = saved_crud
            s3db.inv_track_item_deleting = saved_delete
            tracktable.send_inv_item_id.requires = saved_requires

        self.assertFalse(locked)
        self.assertEqual(deleted_result, "DELETED")
        self.assertEqual(deleted, [track_id])

    # -------------------------------------------------------------------------
    def testSendPrepShowsArrivalFieldsForReceivedTrackItems(self):
        """send prep exposes received quantities and valuation fields for arrived items"""

        db = current.db
        s3db = current.s3db
        tracktable = s3db.inv_track_item

        origin = self.create_office(name="Arrived Origin")
        destination = self.create_office(name="Arrived Destination")
        item_id = self.create_supply_item(name="Sugar")
        pack_id = self.create_item_pack(item_id, quantity=1)
        send_id = self.create_send(origin.site_id,
                                   to_site_id=destination.site_id,
                                   status=s3db.inv_ship_status["RECEIVED"],
                                   )
        track_id = self.create_track_item(item_id,
                                          pack_id,
                                          quantity=3,
                                          send_id=send_id,
                                          status=TRACK_STATUS_ARRIVED,
                                          )

        saved_crud = current.crud_controller
        saved_recv_quantity = tracktable.recv_quantity.readable
        saved_return_quantity = tracktable.return_quantity.readable
        saved_recv_bin = tracktable.recv_bin.readable
        saved_currency = tracktable.currency.readable
        saved_pack_value = tracktable.pack_value.readable
        saved_item_source = tracktable.item_source_no.readable
        saved_requires = tracktable.send_inv_item_id.requires

        try:
            with self.controller("inv",
                                 function="send",
                                 args=[str(send_id), "track_item"],
                                 ) as controller:
                current.crud_controller = lambda *args, **kwargs: Storage(prep=current.response.s3.prep,
                                                                          args=args,
                                                                          kwargs=kwargs,
                                                                          )
                output = controller.module["send"]()
                prep = output.prep
                record = db(s3db.inv_send.id == send_id).select(s3db.inv_send.ALL,
                                                                limitby=(0, 1),
                                                                ).first()
                self.assertTrue(prep(Storage(id=send_id,
                                             record=record,
                                             component=Storage(name="track_item"),
                                             component_name="track_item",
                                             component_id=track_id,
                                             method="update",
                                             interactive=True,
                                             now=current.request.utcnow.date(),
                                             )))
                recv_quantity = tracktable.recv_quantity.readable
                return_quantity = tracktable.return_quantity.readable
                recv_bin = tracktable.recv_bin.readable
                currency = tracktable.currency.readable
                pack_value = tracktable.pack_value.readable
                item_source = tracktable.item_source_no.readable
        finally:
            current.crud_controller = saved_crud
            tracktable.recv_quantity.readable = saved_recv_quantity
            tracktable.return_quantity.readable = saved_return_quantity
            tracktable.recv_bin.readable = saved_recv_bin
            tracktable.currency.readable = saved_currency
            tracktable.pack_value.readable = saved_pack_value
            tracktable.item_source_no.readable = saved_item_source
            tracktable.send_inv_item_id.requires = saved_requires

        self.assertTrue(item_source)
        self.assertTrue(recv_quantity)
        self.assertTrue(return_quantity)
        self.assertTrue(recv_bin)
        self.assertTrue(currency)
        self.assertTrue(pack_value)

    # -------------------------------------------------------------------------
    def testSendPrepAddsQuantityNeededForRequestShipments(self):
        """send prep exposes quantity-needed for track items linked to requests"""

        db = current.db
        s3db = current.s3db
        tracktable = s3db.inv_track_item

        origin = self.create_office(name="Send Origin")
        destination = self.create_office(name="Send Destination")
        item_id = self.create_supply_item(name="Beans")
        pack_id = self.create_item_pack(item_id, quantity=1)
        self.create_inventory_item(origin.site_id,
                                   item_id,
                                   pack_id,
                                   quantity=5,
                                   status=0,
                                   )
        send_id = self.create_send(origin.site_id,
                                   to_site_id=destination.site_id,
                                   req_ref="REQ-SEND-QTY",
                                   status=SHIP_STATUS_IN_PROCESS,
                                   )

        saved_crud = current.crud_controller
        saved_list_fields = s3db.get_config("inv_track_item", "list_fields")
        saved_extra_fields = s3db.get_config("inv_track_item", "extra_fields")
        saved_requires = tracktable.send_inv_item_id.requires

        try:
            with self.controller("inv",
                                 function="send",
                                 args=[str(send_id), "track_item"],
                                 ) as controller:
                current.crud_controller = lambda *args, **kwargs: Storage(prep=current.response.s3.prep,
                                                                          args=args,
                                                                          kwargs=kwargs,
                                                                          )
                output = controller.module["send"]()
                editable_before_prep = s3db.get_config("inv_track_item", "editable")
                prep = output.prep
                record = db(s3db.inv_send.id == send_id).select(s3db.inv_send.ALL,
                                                                limitby=(0, 1),
                                                                ).first()
                r = Storage(record=record,
                            component=Storage(name="track_item"),
                            component_name="track_item",
                            component_id=None,
                            method=None,
                            interactive=True,
                            id=send_id,
                            now=current.request.utcnow.date(),
                            )
                self.assertTrue(prep(r))
                list_fields = s3db.get_config("inv_track_item", "list_fields")
                extra_fields = s3db.get_config("inv_track_item", "extra_fields")
        finally:
            current.crud_controller = saved_crud
            s3db.configure("inv_track_item",
                           list_fields=saved_list_fields,
                           extra_fields=saved_extra_fields,
                           )
            tracktable.send_inv_item_id.requires = saved_requires

        self.assertTrue(any("quantity_needed" in str(field) for field in list_fields))
        self.assertEqual(extra_fields, ["req_item_id"])

    # -------------------------------------------------------------------------
    def testSendPrepReturningTrackItemsAllowReturnEditing(self):
        """send prep makes returning track items editable for return quantities"""

        db = current.db
        s3db = current.s3db
        tracktable = s3db.inv_track_item

        origin = self.create_office(name="Returning Origin")
        destination = self.create_office(name="Returning Destination")
        item_id = self.create_supply_item(name="Oil")
        pack_id = self.create_item_pack(item_id, quantity=1)
        inv_item_id = self.create_inventory_item(origin.site_id,
                                                 item_id,
                                                 pack_id,
                                                 quantity=4,
                                                 status=0,
                                                 )
        send_id = self.create_send(origin.site_id,
                                   to_site_id=destination.site_id,
                                   status=SHIP_STATUS_RETURNING,
                                   )
        track_id = self.create_track_item(item_id,
                                          pack_id,
                                          quantity=2,
                                          send_id=send_id,
                                          send_inv_item_id=inv_item_id,
                                          status=TRACK_STATUS_RETURNING,
                                          )

        saved_crud = current.crud_controller
        saved_editable = s3db.get_config("inv_track_item", "editable")
        saved_list_fields = s3db.get_config("inv_track_item", "list_fields")
        saved_requires = tracktable.send_inv_item_id.requires
        saved_return_readable = tracktable.return_quantity.readable
        saved_return_writable = tracktable.return_quantity.writable
        saved_currency_readable = tracktable.currency.readable
        saved_pack_value_readable = tracktable.pack_value.readable

        try:
            with self.controller("inv",
                                 function="send",
                                 args=[str(send_id), "track_item"],
                                 ) as controller:
                current.crud_controller = lambda *args, **kwargs: Storage(prep=current.response.s3.prep,
                                                                          args=args,
                                                                          kwargs=kwargs,
                                                                          )
                output = controller.module["send"]()
                editable_before_prep = s3db.get_config("inv_track_item", "editable")
                prep = output.prep
                record = db(s3db.inv_send.id == send_id).select(s3db.inv_send.ALL,
                                                                limitby=(0, 1),
                                                                ).first()
                r = Storage(record=record,
                            component=Storage(name="track_item"),
                            component_name="track_item",
                            component_id=track_id,
                            method="update",
                            interactive=True,
                            id=send_id,
                            now=current.request.utcnow.date(),
                            )
                self.assertTrue(prep(r))
                editable = s3db.get_config("inv_track_item", "editable")
                list_fields = s3db.get_config("inv_track_item", "list_fields")
                return_readable = tracktable.return_quantity.readable
                return_writable = tracktable.return_quantity.writable
                currency_readable = tracktable.currency.readable
                pack_value_readable = tracktable.pack_value.readable
        finally:
            current.crud_controller = saved_crud
            s3db.configure("inv_track_item",
                           editable=saved_editable,
                           list_fields=saved_list_fields,
                           )
            tracktable.send_inv_item_id.requires = saved_requires
            tracktable.return_quantity.readable = saved_return_readable
            tracktable.return_quantity.writable = saved_return_writable
            tracktable.currency.readable = saved_currency_readable
            tracktable.pack_value.readable = saved_pack_value_readable

        self.assertTrue(editable_before_prep)
        self.assertFalse(editable)
        self.assertIn("return_quantity", list_fields)
        self.assertTrue(return_readable)
        self.assertTrue(return_writable)
        self.assertFalse(currency_readable)
        self.assertFalse(pack_value_readable)

    # -------------------------------------------------------------------------
    def testSendPrepAddsPackValueColumnsForReceivedAndReturningShipments(self):
        """send prep includes valuation columns for received and returning shipment tabs"""

        db = current.db
        s3db = current.s3db

        ship_status = s3db.inv_ship_status
        origin = self.create_office(name="PackValue Origin")
        destination = self.create_office(name="PackValue Destination")
        received_id = self.create_send(origin.site_id,
                                       to_site_id=destination.site_id,
                                       status=ship_status["RECEIVED"],
                                       )
        returning_id = self.create_send(origin.site_id,
                                        to_site_id=destination.site_id,
                                        status=ship_status["RETURNING"],
                                        )

        saved_crud = current.crud_controller
        saved_list_fields = s3db.get_config("inv_track_item", "list_fields")
        settings = current.deployment_settings
        saved_values = settings.supply.get("track_pack_values")

        settings.supply.track_pack_values = True

        try:
            with self.controller("inv",
                                 function="send",
                                 args=[str(received_id), "track_item"],
                                 ) as controller:
                current.crud_controller = lambda *args, **kwargs: Storage(prep=current.response.s3.prep,
                                                                          args=args,
                                                                          kwargs=kwargs,
                                                                          )
                output = controller.module["send"]()
                prep = output.prep
                record = db(s3db.inv_send.id == received_id).select(s3db.inv_send.ALL,
                                                                    limitby=(0, 1),
                                                                    ).first()
                self.assertTrue(prep(Storage(record=record,
                                             component=Storage(name="track_item"),
                                             component_name="track_item",
                                             component_id=None,
                                             method=None,
                                             interactive=True,
                                             id=received_id,
                                             now=current.request.utcnow.date(),
                                             )))
                received_fields = s3db.get_config("inv_track_item", "list_fields")

            with self.controller("inv",
                                 function="send",
                                 args=[str(returning_id), "track_item"],
                                 ) as controller:
                current.crud_controller = lambda *args, **kwargs: Storage(prep=current.response.s3.prep,
                                                                          args=args,
                                                                          kwargs=kwargs,
                                                                          )
                output = controller.module["send"]()
                prep = output.prep
                record = db(s3db.inv_send.id == returning_id).select(s3db.inv_send.ALL,
                                                                     limitby=(0, 1),
                                                                     ).first()
                self.assertTrue(prep(Storage(record=record,
                                             component=Storage(name="track_item"),
                                             component_name="track_item",
                                             component_id=None,
                                             method=None,
                                             interactive=True,
                                             id=returning_id,
                                             now=current.request.utcnow.date(),
                                             )))
                returning_fields = s3db.get_config("inv_track_item", "list_fields")
        finally:
            current.crud_controller = saved_crud
            s3db.configure("inv_track_item", list_fields=saved_list_fields)
            settings.supply.track_pack_values = saved_values

        self.assertIn("currency", received_fields)
        self.assertIn("pack_value", received_fields)
        self.assertIn("currency", returning_fields)
        self.assertIn("pack_value", returning_fields)

    # -------------------------------------------------------------------------
    def testSendPrepLocksRequestBoundTrackItemsToTheirChosenStockRow(self):
        """send prep keeps request-bound track items tied to the already selected stock row"""

        db = current.db
        s3db = current.s3db
        tracktable = s3db.inv_track_item

        origin = self.create_office(name="Requested Origin")
        destination = self.create_office(name="Requested Destination")
        item_id = self.create_supply_item(name="Rice")
        pack_id = self.create_item_pack(item_id, quantity=1)
        inv_item_id = self.create_inventory_item(origin.site_id,
                                                 item_id,
                                                 pack_id,
                                                 quantity=9,
                                                 status=0,
                                                 )
        req_id = self.create_request(destination.site_id, req_type=1)
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=4,
                                               )
        send_id = self.create_send(origin.site_id,
                                   to_site_id=destination.site_id,
                                   status=SHIP_STATUS_IN_PROCESS,
                                   )
        track_id = self.create_track_item(item_id,
                                          pack_id,
                                          quantity=2,
                                          req_item_id=req_item_id,
                                          send_id=send_id,
                                          send_inv_item_id=inv_item_id,
                                          status=s3db.inv_tracking_status["IN_PROCESS"],
                                          )

        saved_crud = current.crud_controller
        saved_send_inv_writable = tracktable.send_inv_item_id.writable
        saved_pack_writable = tracktable.item_pack_id.writable
        saved_comment = tracktable.quantity.comment
        saved_requires = tracktable.quantity.requires

        try:
            with self.controller("inv",
                                 function="send",
                                 args=[str(send_id), "track_item"],
                                 ) as controller:
                current.crud_controller = lambda *args, **kwargs: Storage(prep=current.response.s3.prep,
                                                                          args=args,
                                                                          kwargs=kwargs,
                                                                          )
                output = controller.module["send"]()
                prep = output.prep
                record = db(s3db.inv_send.id == send_id).select(s3db.inv_send.ALL,
                                                                limitby=(0, 1),
                                                                ).first()
                self.assertTrue(prep(Storage(record=record,
                                             component=Storage(name="track_item"),
                                             component_name="track_item",
                                             component_id=track_id,
                                             method="update",
                                             interactive=True,
                                             id=send_id,
                                             now=current.request.utcnow.date(),
                                             )))
                send_inv_writable = tracktable.send_inv_item_id.writable
                pack_writable = tracktable.item_pack_id.writable
                quantity_comment = str(tracktable.quantity.comment)
                quantity_requires = tracktable.quantity.requires
        finally:
            current.crud_controller = saved_crud
            tracktable.send_inv_item_id.writable = saved_send_inv_writable
            tracktable.item_pack_id.writable = saved_pack_writable
            tracktable.quantity.comment = saved_comment
            tracktable.quantity.requires = saved_requires

        self.assertFalse(send_inv_writable)
        self.assertFalse(pack_writable)
        self.assertIn("in stock", quantity_comment)
        self.assertEqual(quantity_requires.__class__.__name__, "IS_AVAILABLE_QUANTITY")

    # -------------------------------------------------------------------------
    def testSendPrepReceivedFlagUpdatesShipmentAndRequestFulfilment(self):
        """send prep marks shipments received and updates linked request fulfilment"""

        auth = current.auth
        db = current.db
        s3db = current.s3db
        response = current.response
        sendtable = s3db.inv_send
        tracktable = s3db.inv_track_item

        origin = self.create_office(name="Received Origin")
        destination = self.create_office(name="Received Destination")
        item_id = self.create_supply_item(name="Water")
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(destination.site_id,
                                     req_type=1,
                                     req_ref="REQ-REMOTE-RECV",
                                     fulfil_status=0,
                                     )
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=2,
                                               quantity_fulfil=0,
                                               )
        send_id = self.create_send(origin.site_id,
                                   to_site_id=destination.site_id,
                                   req_ref="REQ-REMOTE-RECV",
                                   status=SHIP_STATUS_SENT,
                                   )
        track_id = self.create_track_item(item_id,
                                          pack_id,
                                          quantity=3,
                                          req_item_id=req_item_id,
                                          send_id=send_id,
                                          status=s3db.inv_tracking_status["SENT"],
                                          )

        saved_crud = current.crud_controller
        saved_permission = auth.s3_has_permission
        saved_confirmation = response.confirmation
        saved_send_ref_readable = sendtable.send_ref.readable
        saved_send_ref_writable = sendtable.send_ref.writable
        saved_send_field_writable = {field: sendtable[field].writable for field in sendtable.fields}
        saved_track_field_writable = {field: tracktable[field].writable for field in tracktable.fields}

        auth.s3_has_permission = lambda *args, **kwargs: True

        try:
            with self.controller("inv",
                                 function="send",
                                 args=[str(send_id)],
                                 query_vars={"received": "1"},
                                 ) as controller:
                current.crud_controller = lambda *args, **kwargs: Storage(prep=current.response.s3.prep,
                                                                          args=args,
                                                                          kwargs=kwargs,
                                                                          )
                output = controller.module["send"]()
                prep = output.prep
                response.confirmation = None
                self.assertTrue(prep(Storage(id=send_id,
                                             component=None,
                                             )))
                confirmation = response.confirmation
        finally:
            current.crud_controller = saved_crud
            auth.s3_has_permission = saved_permission
            response.confirmation = saved_confirmation
            sendtable.send_ref.readable = saved_send_ref_readable
            sendtable.send_ref.writable = saved_send_ref_writable
            for field, writable in saved_send_field_writable.items():
                sendtable[field].writable = writable
            for field, writable in saved_track_field_writable.items():
                tracktable[field].writable = writable

        send = db(sendtable.id == send_id).select(sendtable.status,
                                                  limitby=(0, 1),
                                                  ).first()
        track = db(tracktable.id == track_id).select(tracktable.status,
                                                     limitby=(0, 1),
                                                     ).first()
        req_item = db(s3db.req_req_item.id == req_item_id).select(s3db.req_req_item.quantity_fulfil,
                                                                  limitby=(0, 1),
                                                                  ).first()
        req = db(s3db.req_req.id == req_id).select(s3db.req_req.fulfil_status,
                                                   limitby=(0, 1),
                                                   ).first()

        self.assertEqual(send.status, s3db.inv_ship_status["RECEIVED"])
        self.assertEqual(track.status, TRACK_STATUS_ARRIVED)
        self.assertEqual(req_item.quantity_fulfil, 3)
        self.assertEqual(req.fulfil_status, 2)
        self.assertEqual(str(confirmation), "Shipment received")

    # -------------------------------------------------------------------------
    def testSendPrepReceivedFlagLeavesPartiallyFulfilledRequestsOpen(self):
        """send prep marks linked requests as partial when received quantities remain outstanding"""

        auth = current.auth
        db = current.db
        s3db = current.s3db
        response = current.response
        sendtable = s3db.inv_send
        tracktable = s3db.inv_track_item

        origin = self.create_office(name="Partial Origin")
        destination = self.create_office(name="Partial Destination")
        item_id = self.create_supply_item(name="Soap")
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(destination.site_id,
                                     req_type=1,
                                     req_ref="REQ-REMOTE-PARTIAL",
                                     fulfil_status=0,
                                     )
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=5,
                                               quantity_fulfil=0,
                                               )
        send_id = self.create_send(origin.site_id,
                                   to_site_id=destination.site_id,
                                   req_ref="REQ-REMOTE-PARTIAL",
                                   status=SHIP_STATUS_SENT,
                                   )
        track_id = self.create_track_item(item_id,
                                          pack_id,
                                          quantity=2,
                                          req_item_id=req_item_id,
                                          send_id=send_id,
                                          status=s3db.inv_tracking_status["SENT"],
                                          )

        saved_crud = current.crud_controller
        saved_permission = auth.s3_has_permission
        saved_confirmation = response.confirmation
        saved_send_ref_readable = sendtable.send_ref.readable
        saved_send_ref_writable = sendtable.send_ref.writable
        saved_send_field_writable = {field: sendtable[field].writable for field in sendtable.fields}
        saved_track_field_writable = {field: tracktable[field].writable for field in tracktable.fields}

        auth.s3_has_permission = lambda *args, **kwargs: True

        try:
            with self.controller("inv",
                                 function="send",
                                 args=[str(send_id)],
                                 query_vars={"received": "1"},
                                 ) as controller:
                current.crud_controller = lambda *args, **kwargs: Storage(prep=current.response.s3.prep,
                                                                          args=args,
                                                                          kwargs=kwargs,
                                                                          )
                output = controller.module["send"]()
                prep = output.prep
                response.confirmation = None
                self.assertTrue(prep(Storage(id=send_id,
                                             component=None,
                                             )))
                confirmation = response.confirmation
        finally:
            current.crud_controller = saved_crud
            auth.s3_has_permission = saved_permission
            response.confirmation = saved_confirmation
            sendtable.send_ref.readable = saved_send_ref_readable
            sendtable.send_ref.writable = saved_send_ref_writable
            for field, writable in saved_send_field_writable.items():
                sendtable[field].writable = writable
            for field, writable in saved_track_field_writable.items():
                tracktable[field].writable = writable

        track = db(tracktable.id == track_id).select(tracktable.status,
                                                     limitby=(0, 1),
                                                     ).first()
        req_item = db(s3db.req_req_item.id == req_item_id).select(s3db.req_req_item.quantity_fulfil,
                                                                  limitby=(0, 1),
                                                                  ).first()
        req = db(s3db.req_req.id == req_id).select(s3db.req_req.fulfil_status,
                                                   limitby=(0, 1),
                                                   ).first()

        self.assertEqual(track.status, TRACK_STATUS_ARRIVED)
        self.assertEqual(req_item.quantity_fulfil, 2)
        self.assertEqual(req.fulfil_status, 1)
        self.assertEqual(str(confirmation), "Shipment received")

    # -------------------------------------------------------------------------
    def testIncomingAndReqMatchDelegateToModelHelpers(self):
        """incoming and req_match delegate to the model helper methods"""

        fake_s3db = Storage(inv_incoming=lambda: "INCOMING",
                            req_match=lambda: "MATCH",
                            )

        with self.controller("inv", function="incoming") as controller:
            controller.module["incoming"].__globals__["s3db"] = fake_s3db
            incoming_output = controller.module["incoming"]()

        with self.controller("inv", function="req_match") as controller:
            controller.module["req_match"].__globals__["s3db"] = fake_s3db
            match_output = controller.module["req_match"]()

        self.assertEqual(incoming_output, "INCOMING")
        self.assertEqual(match_output, "MATCH")

    # -------------------------------------------------------------------------
    def testReqItemsForInvReturnsEarliestOutstandingItem(self):
        """req_items_for_inv keeps the earliest outstanding request per item"""

        db = current.db
        s3db = current.s3db

        office = self.create_office()
        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id, quantity=1)

        first_req = self.create_request(office.site_id)
        second_req = self.create_request(office.site_id)
        db(s3db.req_req.id == first_req).update(date_required=datetime.date(2026, 3, 10))
        db(s3db.req_req.id == second_req).update(date_required=datetime.date(2026, 3, 12))

        self.create_request_item(first_req,
                                 item_id,
                                 pack_id,
                                 quantity=5,
                                 quantity_commit=1,
                                 )
        self.create_request_item(second_req,
                                 item_id,
                                 pack_id,
                                 quantity=6,
                                 quantity_commit=0,
                                 )

        with self.controller("inv", function="req_items_for_inv") as controller:
            req_items = controller.module["req_items_for_inv"](office.site_id, "commit")

        self.assertIn(item_id, req_items)
        self.assertEqual(req_items[item_id].req_id, first_req)

    # -------------------------------------------------------------------------
    def testReqItemInShipmentUpdatesMatchingRequestsAndHandlesFallbackRows(self):
        """req_item_in_shipment updates matching requests and falls back to inv_inv_item rows"""

        class FakeTable(dict):
            """Minimal table stub that records row updates by record ID"""

        fake_req_req_item = FakeTable()
        fake_send_item = FakeTable()
        fake_s3db = Storage(req_req_item=fake_req_req_item,
                            inv_send_item=fake_send_item,
                            )

        shipment_item = Storage(inv_send_item=Storage(id=7,
                                                      item_id=3,
                                                      pack_quantity=2,
                                                      quantity=4,
                                                      ))
        req_items = Storage({3: Storage(id=11,
                                        req_id=21,
                                        quantity=10,
                                        pack_quantity=4,
                                        quantity_transit=1,
                                        )})

        with self.controller("inv", function="req_item_in_shipment") as controller:
            globals_ = controller.module["req_item_in_shipment"].__globals__
            saved_s3db = globals_["s3db"]
            globals_["s3db"] = fake_s3db
            try:
                req_id, req_item_id = controller.module["req_item_in_shipment"](shipment_item,
                                                                                "send",
                                                                                req_items,
                                                                                )
                fallback = controller.module["req_item_in_shipment"](Storage(inv_inv_item=Storage(item_id=99)),
                                                                     "recv",
                                                                     Storage(),
                                                                     )
            finally:
                globals_["s3db"] = saved_s3db

        self.assertEqual((req_id, req_item_id), (21, 11))
        self.assertEqual(fake_req_req_item[11], {"quantity_transit": 3})
        self.assertEqual(fake_send_item[7], {"req_item_id": 11})
        self.assertEqual(fallback, (None, None))

    # -------------------------------------------------------------------------
    def testSendReturnsValidatesStatusAndMarksShipmentReturning(self):
        """send_returns rejects editable shipments and marks sent ones as returning"""

        auth = current.auth
        db = current.db
        s3db = current.s3db
        session = current.session

        ship_status = s3db.inv_ship_status
        tracking_status = s3db.inv_tracking_status
        origin = self.create_office(name="Origin")
        destination = self.create_office(name="Destination")
        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id, quantity=1)

        draft_send = self.create_send(origin.site_id,
                                      to_site_id=destination.site_id,
                                      status=ship_status["IN_PROCESS"],
                                      )

        send_id = self.create_send(origin.site_id,
                                   to_site_id=destination.site_id,
                                   status=ship_status["SENT"],
                                   )
        recv_id = self.create_recv(destination.site_id,
                                   from_site_id=origin.site_id,
                                   status=ship_status["SENT"],
                                   )
        track_id = self.create_track_item(item_id,
                                          pack_id,
                                          quantity=4,
                                          send_id=send_id,
                                          recv_id=recv_id,
                                          status=tracking_status["SENT"],
                                          )

        saved_permission = auth.s3_has_permission
        saved_error = session.error
        saved_confirmation = session.confirmation
        auth.s3_has_permission = lambda *args, **kwargs: True

        try:
            session.error = None
            with self.controller("inv",
                                 function="send_returns",
                                 args=[str(draft_send)],
                                 ) as controller:
                with self.assertRaises(ControllerRedirect) as redirect:
                    controller.module["send_returns"]()
                draft_url = str(redirect.exception.url)
                draft_error = session.error

            session.error = None
            session.confirmation = None
            with self.controller("inv",
                                 function="send_returns",
                                 args=[str(send_id)],
                                 ) as controller:
                with self.assertRaises(ControllerRedirect) as redirect:
                    controller.module["send_returns"]()
                success_url = str(redirect.exception.url)
                confirmation = session.confirmation
        finally:
            auth.s3_has_permission = saved_permission
            session.error = saved_error
            session.confirmation = saved_confirmation

        send = db(s3db.inv_send.id == send_id).select(s3db.inv_send.status,
                                                      limitby=(0, 1),
                                                      ).first()
        recv = db(s3db.inv_recv.id == recv_id).select(s3db.inv_recv.status,
                                                      limitby=(0, 1),
                                                      ).first()
        track = db(s3db.inv_track_item.id == track_id).select(s3db.inv_track_item.status,
                                                              limitby=(0, 1),
                                                              ).first()

        self.assertIn("/inv/send/%s" % draft_send, draft_url)
        self.assertIsNotNone(draft_error)
        self.assertIn("/inv/send/%s/track_item" % send_id, success_url)
        self.assertEqual(send.status, ship_status["RETURNING"])
        self.assertEqual(recv.status, ship_status["RETURNING"])
        self.assertEqual(track.status, tracking_status["RETURNING"])
        self.assertEqual(str(confirmation),
                         "Sent Shipment has returned, indicate how many items will be returned to Warehouse.")

    # -------------------------------------------------------------------------
    def testReturnProcessRestoresWarehouseStock(self):
        """return_process restores returned quantities and closes the shipment"""

        auth = current.auth
        db = current.db
        s3db = current.s3db
        session = current.session

        ship_status = s3db.inv_ship_status
        tracking_status = s3db.inv_tracking_status
        origin = self.create_office(name="Origin")
        destination = self.create_office(name="Destination")
        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id, quantity=1)

        send_id = self.create_send(origin.site_id,
                                   to_site_id=destination.site_id,
                                   status=ship_status["RETURNING"],
                                   )
        recv_id = self.create_recv(destination.site_id,
                                   from_site_id=origin.site_id,
                                   status=ship_status["RETURNING"],
                                   )
        inv_item_id = self.create_inventory_item(origin.site_id,
                                                 item_id,
                                                 pack_id,
                                                 quantity=2,
                                                 )
        track_id = self.create_track_item(item_id,
                                          pack_id,
                                          quantity=5,
                                          recv_quantity=0,
                                          send_id=send_id,
                                          recv_id=recv_id,
                                          send_inv_item_id=inv_item_id,
                                          return_quantity=2,
                                          status=tracking_status["RETURNING"],
                                          )

        saved_permission = auth.s3_has_permission
        saved_error = session.error
        auth.s3_has_permission = lambda *args, **kwargs: True

        try:
            session.error = None
            with self.controller("inv",
                                 function="return_process",
                                 args=[str(send_id)],
                                 ) as controller:
                with self.assertRaises(ControllerRedirect) as redirect:
                    controller.module["return_process"]()
                url = str(redirect.exception.url)
        finally:
            auth.s3_has_permission = saved_permission
            session.error = saved_error

        send = db(s3db.inv_send.id == send_id).select(s3db.inv_send.status,
                                                      limitby=(0, 1),
                                                      ).first()
        recv = db(s3db.inv_recv.id == recv_id).select(s3db.inv_recv.status,
                                                      limitby=(0, 1),
                                                      ).first()
        track = db(s3db.inv_track_item.id == track_id).select(s3db.inv_track_item.recv_quantity,
                                                              s3db.inv_track_item.status,
                                                              limitby=(0, 1),
                                                              ).first()
        inv_item = db(s3db.inv_inv_item.id == inv_item_id).select(s3db.inv_inv_item.quantity,
                                                                  limitby=(0, 1),
                                                                  ).first()

        self.assertIn("/inv/send/%s" % send_id, url)
        self.assertEqual(send.status, ship_status["RECEIVED"])
        self.assertEqual(recv.status, ship_status["RECEIVED"])
        self.assertEqual(track.recv_quantity, 3)
        self.assertEqual(track.status, tracking_status["RECEIVED"])
        self.assertEqual(inv_item.quantity, 4)

    # -------------------------------------------------------------------------
    def testSendCancelCancelsShipmentAndMarksTrackItems(self):
        """send_cancel cancels the shipment and invokes track-item deletion hooks"""

        auth = current.auth
        db = current.db
        s3db = current.s3db
        session = current.session

        ship_status = s3db.inv_ship_status
        tracking_status = s3db.inv_tracking_status
        origin = self.create_office(name="Origin")
        destination = self.create_office(name="Destination")
        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id, quantity=1)

        send_id = self.create_send(origin.site_id,
                                   to_site_id=destination.site_id,
                                   status=ship_status["SENT"],
                                   )
        recv_id = self.create_recv(destination.site_id,
                                   from_site_id=origin.site_id,
                                   status=ship_status["SENT"],
                                   )
        track_id = self.create_track_item(item_id,
                                          pack_id,
                                          quantity=2,
                                          send_id=send_id,
                                          recv_id=recv_id,
                                          status=tracking_status["SENT"],
                                          )

        deleted = []
        saved_permission = auth.s3_has_permission
        saved_delete = s3db.inv_track_item_deleting
        saved_error = session.error
        saved_confirmation = session.confirmation

        auth.s3_has_permission = lambda *args, **kwargs: True
        s3db.inv_track_item_deleting = lambda record_id: deleted.append(record_id)

        try:
            session.error = None
            session.confirmation = None
            with self.controller("inv",
                                 function="send_cancel",
                                 args=[str(send_id)],
                                 ) as controller:
                with self.assertRaises(ControllerRedirect) as redirect:
                    controller.module["send_cancel"]()
                url = str(redirect.exception.url)
                confirmation = session.confirmation
        finally:
            auth.s3_has_permission = saved_permission
            s3db.inv_track_item_deleting = saved_delete
            session.error = saved_error
            session.confirmation = saved_confirmation

        send = db(s3db.inv_send.id == send_id).select(s3db.inv_send.status,
                                                      limitby=(0, 1),
                                                      ).first()
        recv = db(s3db.inv_recv.id == recv_id).select(s3db.inv_recv.status,
                                                      limitby=(0, 1),
                                                      ).first()
        track = db(s3db.inv_track_item.id == track_id).select(s3db.inv_track_item.status,
                                                              limitby=(0, 1),
                                                              ).first()

        self.assertIn("/inv/send/%s" % send_id, url)
        self.assertEqual(send.status, ship_status["CANCEL"])
        self.assertEqual(recv.status, ship_status["CANCEL"])
        self.assertEqual(track.status, tracking_status["CANCEL"])
        self.assertEqual(deleted, [track_id])
        self.assertEqual(str(confirmation),
                         "Sent Shipment canceled and items returned to Warehouse")

    # -------------------------------------------------------------------------
    def testRecvControllerConfiguresTrackItemsForTransit(self):
        """recv configures track items to capture received quantities in transit"""

        s3db = current.s3db

        ship_status = s3db.inv_ship_status
        origin = self.create_office(name="Origin")
        destination = self.create_office(name="Destination")
        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id, quantity=1)
        recv_id = self.create_recv(destination.site_id,
                                   from_site_id=origin.site_id,
                                   status=ship_status["SENT"],
                                   )
        track_id = self.create_track_item(item_id,
                                          pack_id,
                                          quantity=3,
                                          recv_id=recv_id,
                                          status=s3db.inv_tracking_status["SENT"],
                                          )

        saved_editable = s3db.get_config("inv_track_item", "editable")
        saved_list_fields = s3db.get_config("inv_track_item", "list_fields")
        saved_recv_quantity_writable = s3db.inv_track_item.recv_quantity.writable
        saved_recv_bin_readable = s3db.inv_track_item.recv_bin.readable
        saved_recv_bin_writable = s3db.inv_track_item.recv_bin.writable

        try:
            with self.controller("inv",
                                 function="recv",
                                 args=[str(recv_id), "track_item"],
                                 ) as controller:
                output = controller.module["recv"]()
                prep = output.prep
                record = current.db(s3db.inv_recv.id == recv_id).select(s3db.inv_recv.ALL,
                                                                        limitby=(0, 1),
                                                                        ).first()
                r = Storage(record=record,
                            component=Storage(name="track_item"),
                            component_name="track_item",
                            component_id=track_id,
                            method="update",
                            id=recv_id,
                            )
                self.assertTrue(prep(r))
                editable = s3db.get_config("inv_track_item", "editable")
                list_fields = s3db.get_config("inv_track_item", "list_fields")
                recv_quantity_writable = s3db.inv_track_item.recv_quantity.writable
                recv_bin_readable = s3db.inv_track_item.recv_bin.readable
                recv_bin_writable = s3db.inv_track_item.recv_bin.writable
        finally:
            s3db.configure("inv_track_item",
                           editable=saved_editable,
                           list_fields=saved_list_fields,
                           )
            s3db.inv_track_item.recv_quantity.writable = saved_recv_quantity_writable
            s3db.inv_track_item.recv_bin.readable = saved_recv_bin_readable
            s3db.inv_track_item.recv_bin.writable = saved_recv_bin_writable

        self.assertTrue(editable)
        self.assertIn("recv_quantity", list_fields)
        self.assertTrue(recv_quantity_writable)
        self.assertTrue(recv_bin_readable)
        self.assertTrue(recv_bin_writable)

    # -------------------------------------------------------------------------
    def testRecvControllerUsesOrderPermissionMessageWhenConfigured(self):
        """recv switches the facility-permission message when the deployment uses orders"""

        auth = current.auth
        captured = []
        saved_permitted = auth.permitted_facilities
        saved_name = current.deployment_settings.inv.get("shipment_name")

        auth.permitted_facilities = lambda table=None, error_msg=None: captured.append(str(error_msg))
        current.deployment_settings.inv.shipment_name = "order"

        try:
            with self.controller("inv", function="recv") as controller:
                controller.module["recv"]()
        finally:
            auth.permitted_facilities = saved_permitted
            current.deployment_settings.inv.shipment_name = saved_name

        self.assertEqual(captured, ["You do not have permission for any facility to add an order."])

    # -------------------------------------------------------------------------
    def testRecvControllerCanPopulateMissingRecipientForExistingReceipts(self):
        """recv can backfill a missing recipient when the legacy branch is reached"""

        db = current.db
        auth = current.auth
        s3db = current.s3db

        origin = self.create_office(name="Recipient Origin")
        destination = self.create_office(name="Recipient Destination")
        recipient_id = self.create_person(last_name="Receiver")
        recv_id = self.create_recv(destination.site_id,
                                   from_site_id=origin.site_id,
                                   recipient_id=None,
                                   )

        saved_logged_in_person = auth.s3_logged_in_person

        try:
            with self.controller("inv",
                                 function="recv",
                                 args=[str(recv_id)],
                                 ) as controller:
                auth.s3_logged_in_person = lambda: recipient_id
                globals_ = controller.module["recv"].__globals__
                sentinel = object()
                saved_id = globals_.get("id", sentinel)
                globals_["id"] = 1
                try:
                    controller.module["recv"]()
                finally:
                    if saved_id is sentinel:
                        del globals_["id"]
                    else:
                        globals_["id"] = saved_id
        finally:
            auth.s3_logged_in_person = saved_logged_in_person

        recv = db(s3db.inv_recv.id == recv_id).select(s3db.inv_recv.recipient_id,
                                                      limitby=(0, 1),
                                                      ).first()
        self.assertEqual(recv.recipient_id, recipient_id)

    # -------------------------------------------------------------------------
    def testRecvControllerConfiguresPreparingTrackItemsForManualEntry(self):
        """recv prep exposes manual item-entry fields while a receipt is still in draft"""

        db = current.db
        s3db = current.s3db
        tracktable = s3db.inv_track_item

        origin = self.create_office(name="Draft Origin")
        destination = self.create_office(name="Draft Destination")
        recv_id = self.create_recv(destination.site_id,
                                   from_site_id=origin.site_id,
                                   organisation_id=origin.organisation_id,
                                   status=s3db.inv_ship_status["IN_PROCESS"],
                                   )

        saved_item_source_writable = tracktable.item_source_no.writable
        saved_item_id_writable = tracktable.item_id.writable
        saved_item_pack_writable = tracktable.item_pack_id.writable
        saved_quantity_writable = tracktable.quantity.writable
        saved_currency_writable = tracktable.currency.writable
        saved_pack_value_writable = tracktable.pack_value.writable
        saved_expiry_writable = tracktable.expiry_date.writable
        saved_recv_bin_writable = tracktable.recv_bin.writable
        saved_owner_writable = tracktable.owner_org_id.writable
        saved_supply_writable = tracktable.supply_org_id.writable
        saved_supply_default = tracktable.supply_org_id.default
        saved_status_writable = tracktable.inv_item_status.writable
        saved_comments_writable = tracktable.comments.writable
        saved_recv_quantity_readable = tracktable.recv_quantity.readable
        saved_send_inv_readable = tracktable.send_inv_item_id.readable
        saved_status_readable = tracktable.status.readable
        saved_recv_bin_label = tracktable.recv_bin.label

        try:
            with self.controller("inv",
                                 function="recv",
                                 args=[str(recv_id), "track_item"],
                                 ) as controller:
                output = controller.module["recv"]()
                prep = output.prep
                record = db(s3db.inv_recv.id == recv_id).select(s3db.inv_recv.ALL,
                                                                limitby=(0, 1),
                                                                ).first()
                self.assertTrue(prep(Storage(record=record,
                                             component=Storage(name="track_item"),
                                             component_name="track_item",
                                             component_id=None,
                                             method=None,
                                             id=recv_id,
                                             )))
                item_source_writable = tracktable.item_source_no.writable
                item_id_writable = tracktable.item_id.writable
                item_pack_writable = tracktable.item_pack_id.writable
                quantity_writable = tracktable.quantity.writable
                currency_writable = tracktable.currency.writable
                pack_value_writable = tracktable.pack_value.writable
                expiry_writable = tracktable.expiry_date.writable
                recv_bin_writable = tracktable.recv_bin.writable
                owner_writable = tracktable.owner_org_id.writable
                supply_writable = tracktable.supply_org_id.writable
                supply_default = tracktable.supply_org_id.default
                status_writable = tracktable.inv_item_status.writable
                comments_writable = tracktable.comments.writable
                recv_quantity_readable = tracktable.recv_quantity.readable
                send_inv_readable = tracktable.send_inv_item_id.readable
                status_readable = tracktable.status.readable
                recv_bin_label = str(tracktable.recv_bin.label)
        finally:
            tracktable.item_source_no.writable = saved_item_source_writable
            tracktable.item_id.writable = saved_item_id_writable
            tracktable.item_pack_id.writable = saved_item_pack_writable
            tracktable.quantity.writable = saved_quantity_writable
            tracktable.currency.writable = saved_currency_writable
            tracktable.pack_value.writable = saved_pack_value_writable
            tracktable.expiry_date.writable = saved_expiry_writable
            tracktable.recv_bin.writable = saved_recv_bin_writable
            tracktable.owner_org_id.writable = saved_owner_writable
            tracktable.supply_org_id.writable = saved_supply_writable
            tracktable.supply_org_id.default = saved_supply_default
            tracktable.inv_item_status.writable = saved_status_writable
            tracktable.comments.writable = saved_comments_writable
            tracktable.recv_quantity.readable = saved_recv_quantity_readable
            tracktable.send_inv_item_id.readable = saved_send_inv_readable
            tracktable.status.readable = saved_status_readable
            tracktable.recv_bin.label = saved_recv_bin_label

        self.assertTrue(item_source_writable)
        self.assertTrue(item_id_writable)
        self.assertTrue(item_pack_writable)
        self.assertTrue(quantity_writable)
        self.assertTrue(currency_writable)
        self.assertTrue(pack_value_writable)
        self.assertTrue(expiry_writable)
        self.assertTrue(recv_bin_writable)
        self.assertTrue(owner_writable)
        self.assertTrue(supply_writable)
        self.assertEqual(supply_default, origin.organisation_id)
        self.assertTrue(status_writable)
        self.assertTrue(comments_writable)
        self.assertFalse(recv_quantity_readable)
        self.assertFalse(send_inv_readable)
        self.assertFalse(status_readable)
        self.assertEqual(recv_bin_label, "Bin")

    # -------------------------------------------------------------------------
    def testRecvControllerConfiguresArrivedTrackItemsAsReadOnly(self):
        """recv prep keeps arrived items read-only except for the destination bin"""

        db = current.db
        s3db = current.s3db
        tracktable = s3db.inv_track_item

        origin = self.create_office(name="Arrived Origin")
        destination = self.create_office(name="Arrived Destination")
        item_id = self.create_supply_item(name="Arrived Item")
        pack_id = self.create_item_pack(item_id, quantity=1)
        recv_id = self.create_recv(destination.site_id,
                                   from_site_id=origin.site_id,
                                   status=s3db.inv_ship_status["RECEIVED"],
                                   )
        track_id = self.create_track_item(item_id,
                                          pack_id,
                                          quantity=2,
                                          recv_id=recv_id,
                                          status=s3db.inv_tracking_status["RECEIVED"],
                                          )

        saved_item_source_readable = tracktable.item_source_no.readable
        saved_item_source_writable = tracktable.item_source_no.writable
        saved_item_id_writable = tracktable.item_id.writable
        saved_send_inv_writable = tracktable.send_inv_item_id.writable
        saved_item_pack_writable = tracktable.item_pack_id.writable
        saved_quantity_writable = tracktable.quantity.writable
        saved_currency_writable = tracktable.currency.writable
        saved_pack_value_writable = tracktable.pack_value.writable
        saved_expiry_writable = tracktable.expiry_date.writable
        saved_owner_writable = tracktable.owner_org_id.writable
        saved_supply_writable = tracktable.supply_org_id.writable
        saved_recv_bin_readable = tracktable.recv_bin.readable
        saved_recv_bin_writable = tracktable.recv_bin.writable

        try:
            with self.controller("inv",
                                 function="recv",
                                 args=[str(recv_id), "track_item"],
                                 ) as controller:
                output = controller.module["recv"]()
                prep = output.prep
                record = db(s3db.inv_recv.id == recv_id).select(s3db.inv_recv.ALL,
                                                                limitby=(0, 1),
                                                                ).first()
                self.assertTrue(prep(Storage(record=record,
                                             component=Storage(name="track_item"),
                                             component_name="track_item",
                                             component_id=track_id,
                                             method="update",
                                             id=recv_id,
                                             )))
                item_source_readable = tracktable.item_source_no.readable
                item_source_writable = tracktable.item_source_no.writable
                item_id_writable = tracktable.item_id.writable
                send_inv_writable = tracktable.send_inv_item_id.writable
                item_pack_writable = tracktable.item_pack_id.writable
                quantity_writable = tracktable.quantity.writable
                currency_writable = tracktable.currency.writable
                pack_value_writable = tracktable.pack_value.writable
                expiry_writable = tracktable.expiry_date.writable
                owner_writable = tracktable.owner_org_id.writable
                supply_writable = tracktable.supply_org_id.writable
                recv_bin_readable = tracktable.recv_bin.readable
                recv_bin_writable = tracktable.recv_bin.writable
        finally:
            tracktable.item_source_no.readable = saved_item_source_readable
            tracktable.item_source_no.writable = saved_item_source_writable
            tracktable.item_id.writable = saved_item_id_writable
            tracktable.send_inv_item_id.writable = saved_send_inv_writable
            tracktable.item_pack_id.writable = saved_item_pack_writable
            tracktable.quantity.writable = saved_quantity_writable
            tracktable.currency.writable = saved_currency_writable
            tracktable.pack_value.writable = saved_pack_value_writable
            tracktable.expiry_date.writable = saved_expiry_writable
            tracktable.owner_org_id.writable = saved_owner_writable
            tracktable.supply_org_id.writable = saved_supply_writable
            tracktable.recv_bin.readable = saved_recv_bin_readable
            tracktable.recv_bin.writable = saved_recv_bin_writable

        self.assertTrue(item_source_readable)
        self.assertFalse(item_source_writable)
        self.assertFalse(item_id_writable)
        self.assertFalse(send_inv_writable)
        self.assertFalse(item_pack_writable)
        self.assertFalse(quantity_writable)
        self.assertFalse(currency_writable)
        self.assertFalse(pack_value_writable)
        self.assertFalse(expiry_writable)
        self.assertFalse(owner_writable)
        self.assertFalse(supply_writable)
        self.assertTrue(recv_bin_readable)
        self.assertTrue(recv_bin_writable)

    # -------------------------------------------------------------------------
    def testRecvControllerCreateFormHidesReferencesAndStatus(self):
        """recv create forms hide generated references and workflow status fields"""

        s3db = current.s3db
        recvtable = s3db.inv_recv

        saved_recv_ref_readable = recvtable.recv_ref.readable
        saved_status_readable = recvtable.status.readable
        saved_send_ref_writable = recvtable.send_ref.writable

        try:
            with self.controller("inv", function="recv") as controller:
                output = controller.module["recv"]()
                prep = output.prep
                self.assertTrue(prep(Storage(id=None,
                                             component=None,
                                             method="create",
                                             )))
                recv_ref_readable = recvtable.recv_ref.readable
                status_readable = recvtable.status.readable
                send_ref_writable = recvtable.send_ref.writable
        finally:
            recvtable.recv_ref.readable = saved_recv_ref_readable
            recvtable.status.readable = saved_status_readable
            recvtable.send_ref.writable = saved_send_ref_writable

        self.assertFalse(recv_ref_readable)
        self.assertFalse(status_readable)
        self.assertTrue(send_ref_writable)

    # -------------------------------------------------------------------------
    def testRecvControllerLocksTrackItemsAfterReceipt(self):
        """recv disables inline CRUD buttons for track items once the receipt is closed"""

        s3db = current.s3db

        origin = self.create_office(name="Locked Origin")
        destination = self.create_office(name="Locked Destination")
        recv_id = self.create_recv(destination.site_id,
                                   from_site_id=origin.site_id,
                                   status=s3db.inv_ship_status["RECEIVED"],
                                   )

        saved_create = s3db.get_config("inv_track_item", "create")
        saved_deletable = s3db.get_config("inv_track_item", "deletable")
        saved_editable = s3db.get_config("inv_track_item", "editable")
        saved_listadd = s3db.get_config("inv_track_item", "listadd")

        try:
            with self.controller("inv",
                                 function="recv",
                                 args=[str(recv_id), "track_item"],
                                 ) as controller:
                controller.module["recv"]()
                create = s3db.get_config("inv_track_item", "create")
                deletable = s3db.get_config("inv_track_item", "deletable")
                editable = s3db.get_config("inv_track_item", "editable")
                listadd = s3db.get_config("inv_track_item", "listadd")
        finally:
            s3db.configure("inv_track_item",
                           create=saved_create,
                           deletable=saved_deletable,
                           editable=saved_editable,
                           listadd=saved_listadd,
                           )

        self.assertFalse(create)
        self.assertFalse(deletable)
        self.assertFalse(editable)
        self.assertFalse(listadd)

    # -------------------------------------------------------------------------
    def testRecvProcessReceivesShipmentAndInvokesTrackOnaccept(self):
        """recv_process completes the shipment and calls track-item onaccept"""

        auth = current.auth
        db = current.db
        s3db = current.s3db
        session = current.session

        ship_status = s3db.inv_ship_status
        origin = self.create_office(name="Origin")
        destination = self.create_office(name="Destination")
        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id, quantity=1)

        send_id = self.create_send(origin.site_id,
                                   to_site_id=destination.site_id,
                                   status=ship_status["SENT"],
                                   )
        recv_id = self.create_recv(destination.site_id,
                                   from_site_id=origin.site_id,
                                   status=ship_status["SENT"],
                                   recv_ref="",
                                   )
        db(s3db.inv_recv.id == recv_id).update(date=None,
                                               recv_ref=None,
                                               )
        track_id = self.create_track_item(item_id,
                                          pack_id,
                                          quantity=3,
                                          recv_quantity=3,
                                          send_id=send_id,
                                          recv_id=recv_id,
                                          status=s3db.inv_tracking_status["SENT"],
                                          )

        onaccept_calls = []
        customise_calls = []
        saved_permission = auth.s3_has_permission
        saved_onaccept = s3db.get_config("inv_track_item", "onaccept")
        saved_confirmation = session.confirmation

        auth.s3_has_permission = lambda *args, **kwargs: True
        s3db.configure("inv_track_item",
                       onaccept=lambda form: onaccept_calls.append(form.vars.id),
                       )

        try:
            with self.controller("inv",
                                 function="recv_process",
                                 args=[str(recv_id)],
                                 ) as controller:
                globals_ = controller.module["recv_process"].__globals__
                saved_crud_request = globals_["crud_request"]
                globals_["crud_request"] = lambda *args, **kwargs: \
                    Storage(customise_resource=lambda tablename: customise_calls.append(tablename))
                try:
                    session.confirmation = None
                    with self.assertRaises(ControllerRedirect) as redirect:
                        controller.module["recv_process"]()
                    url = str(redirect.exception.url)
                    confirmation = session.confirmation
                finally:
                    globals_["crud_request"] = saved_crud_request
        finally:
            auth.s3_has_permission = saved_permission
            s3db.configure("inv_track_item", onaccept=saved_onaccept)
            session.confirmation = saved_confirmation

        recv = db(s3db.inv_recv.id == recv_id).select(s3db.inv_recv.status,
                                                      s3db.inv_recv.recv_ref,
                                                      s3db.inv_recv.date,
                                                      limitby=(0, 1),
                                                      ).first()
        send = db(s3db.inv_send.id == send_id).select(s3db.inv_send.status,
                                                      limitby=(0, 1),
                                                      ).first()
        track = db(s3db.inv_track_item.id == track_id).select(s3db.inv_track_item.status,
                                                              limitby=(0, 1),
                                                              ).first()

        self.assertIn("/inv/recv/%s" % recv_id, url)
        self.assertEqual(recv.status, ship_status["RECEIVED"])
        self.assertEqual(send.status, ship_status["RECEIVED"])
        self.assertIsNotNone(recv.recv_ref)
        self.assertIsNotNone(recv.date)
        self.assertEqual(track.status, 3)
        self.assertEqual(onaccept_calls, [track_id])
        self.assertEqual(customise_calls, ["inv_track_item"])
        self.assertEqual(str(confirmation), "Shipment Items Received")

    # -------------------------------------------------------------------------
    def testRecvProcessRejectsAlreadyClosedShipments(self):
        """recv_process refuses shipments that are already received or canceled"""

        auth = current.auth
        session = current.session
        s3db = current.s3db

        origin = self.create_office(name="Closed Origin")
        destination = self.create_office(name="Closed Destination")
        received_id = self.create_recv(destination.site_id,
                                       from_site_id=origin.site_id,
                                       status=s3db.inv_ship_status["RECEIVED"],
                                       )
        canceled_id = self.create_recv(destination.site_id,
                                       from_site_id=origin.site_id,
                                       status=s3db.inv_ship_status["CANCEL"],
                                       )

        saved_permission = auth.s3_has_permission
        saved_error = session.error
        auth.s3_has_permission = lambda *args, **kwargs: True

        try:
            session.error = None
            with self.controller("inv",
                                 function="recv_process",
                                 args=[str(received_id)],
                                 ) as controller:
                with self.assertRaises(ControllerRedirect) as redirect:
                    controller.module["recv_process"]()
                received_url = str(redirect.exception.url)
                received_error = session.error

            session.error = None
            with self.controller("inv",
                                 function="recv_process",
                                 args=[str(canceled_id)],
                                 ) as controller:
                with self.assertRaises(ControllerRedirect) as redirect:
                    controller.module["recv_process"]()
                canceled_url = str(redirect.exception.url)
                canceled_error = session.error
        finally:
            auth.s3_has_permission = saved_permission
            session.error = saved_error

        self.assertIn("/inv/recv/%s" % received_id, received_url)
        self.assertEqual(str(received_error),
                         "This shipment has already been received.")
        self.assertIn("/inv/recv/%s" % canceled_id, canceled_url)
        self.assertEqual(str(canceled_error),
                         "This shipment has already been received & subsequently canceled.")

    # -------------------------------------------------------------------------
    def testRecvCancelRejectsUnreceivedShipments(self):
        """recv_cancel refuses shipments that have not yet been received"""

        auth = current.auth
        s3db = current.s3db
        session = current.session

        ship_status = s3db.inv_ship_status
        origin = self.create_office(name="Origin")
        destination = self.create_office(name="Destination")
        recv_id = self.create_recv(destination.site_id,
                                   from_site_id=origin.site_id,
                                   status=ship_status["SENT"],
                                   )

        saved_permission = auth.s3_has_permission
        saved_error = session.error
        auth.s3_has_permission = lambda *args, **kwargs: True

        try:
            session.error = None
            with self.controller("inv",
                                 function="recv_cancel",
                                 args=[str(recv_id)],
                                 ) as controller:
                with self.assertRaises(ControllerRedirect) as redirect:
                    controller.module["recv_cancel"]()
                url = str(redirect.exception.url)
                error = session.error
        finally:
            auth.s3_has_permission = saved_permission
            session.error = saved_error

        self.assertIn("/inv/recv/%s" % recv_id, url)
        self.assertIsNotNone(error)

    # -------------------------------------------------------------------------
    def testRecvCancelRevertsReceivedShipmentsAndRequestQuantities(self):
        """recv_cancel restores stock to transit and rolls back request fulfilment"""

        auth = current.auth
        db = current.db
        s3db = current.s3db
        session = current.session

        ship_status = s3db.inv_ship_status
        origin = self.create_office(name="Origin")
        destination = self.create_office(name="Destination")
        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id, quantity=1)

        req_id = self.create_request(destination.site_id, req_type=1)
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=2,
                                               quantity_fulfil=2,
                                               )
        send_id = self.create_send(origin.site_id,
                                   to_site_id=destination.site_id,
                                   status=ship_status["RECEIVED"],
                                   )
        recv_id = self.create_recv(destination.site_id,
                                   from_site_id=origin.site_id,
                                   status=ship_status["RECEIVED"],
                                   )
        recv_inv_item_id = self.create_inventory_item(destination.site_id,
                                                      item_id,
                                                      pack_id,
                                                      quantity=3,
                                                      )
        track_id = self.create_track_item(item_id,
                                          pack_id,
                                          quantity=2,
                                          recv_quantity=2,
                                          req_item_id=req_item_id,
                                          send_id=send_id,
                                          recv_id=recv_id,
                                          recv_inv_item_id=recv_inv_item_id,
                                          status=s3db.inv_tracking_status["RECEIVED"],
                                          )

        saved_permission = auth.s3_has_permission
        saved_error = session.error
        auth.s3_has_permission = lambda *args, **kwargs: True

        try:
            session.error = None
            with self.controller("inv",
                                 function="recv_cancel",
                                 args=[str(recv_id)],
                                 ) as controller:
                with self.assertRaises(ControllerRedirect) as redirect:
                    controller.module["recv_cancel"]()
                url = str(redirect.exception.url)
        finally:
            auth.s3_has_permission = saved_permission
            session.error = saved_error

        recv = db(s3db.inv_recv.id == recv_id).select(s3db.inv_recv.status,
                                                      limitby=(0, 1),
                                                      ).first()
        send = db(s3db.inv_send.id == send_id).select(s3db.inv_send.status,
                                                      limitby=(0, 1),
                                                      ).first()
        track = db(s3db.inv_track_item.id == track_id).select(s3db.inv_track_item.status,
                                                              limitby=(0, 1),
                                                              ).first()
        req_item = db(s3db.req_req_item.id == req_item_id).select(s3db.req_req_item.quantity_fulfil,
                                                                  limitby=(0, 1),
                                                                  ).first()
        inv_item = db(s3db.inv_inv_item.id == recv_inv_item_id).select(s3db.inv_inv_item.quantity,
                                                                       limitby=(0, 1),
                                                                       ).first()

        self.assertIn("/inv/recv/%s" % recv_id, url)
        self.assertEqual(recv.status, ship_status["CANCEL"])
        self.assertEqual(send.status, ship_status["SENT"])
        self.assertEqual(track.status, s3db.inv_tracking_status["SENT"])
        self.assertEqual(req_item.quantity_fulfil, 0)
        self.assertEqual(inv_item.quantity, 1)

    # -------------------------------------------------------------------------
    def testSetRecvAttrConfiguresWritableFieldsByShipmentStatus(self):
        """set_recv_attr toggles receive-field editability by shipment status"""

        s3db = current.s3db
        recvtable = s3db.inv_recv
        ship_status = s3db.inv_ship_status

        saved = Storage(send_ref_writable=recvtable.send_ref.writable,
                        recv_ref_readable=recvtable.recv_ref.readable,
                        date_writable=recvtable.date.writable,
                        recipient_readable=recvtable.recipient_id.readable,
                        recipient_writable=recvtable.recipient_id.writable,
                        comments_writable=recvtable.comments.writable,
                        )

        try:
            with self.controller("inv", function="set_recv_attr") as controller:
                set_recv_attr = controller.module["set_recv_attr"]

                set_recv_attr(ship_status["IN_PROCESS"])
                in_process = Storage(send_ref_writable=recvtable.send_ref.writable,
                                     recv_ref_readable=recvtable.recv_ref.readable,
                                     )

                set_recv_attr(ship_status["SENT"])
                sent = Storage(date_writable=recvtable.date.writable,
                               recipient_readable=recvtable.recipient_id.readable,
                               recipient_writable=recvtable.recipient_id.writable,
                               comments_writable=recvtable.comments.writable,
                               )

                set_recv_attr(ship_status["RECEIVED"])
                received = Storage(send_ref_writable=recvtable.send_ref.writable,
                                   date_writable=recvtable.date.writable,
                                   comments_writable=recvtable.comments.writable,
                                   )
        finally:
            recvtable.send_ref.writable = saved.send_ref_writable
            recvtable.recv_ref.readable = saved.recv_ref_readable
            recvtable.date.writable = saved.date_writable
            recvtable.recipient_id.readable = saved.recipient_readable
            recvtable.recipient_id.writable = saved.recipient_writable
            recvtable.comments.writable = saved.comments_writable

        self.assertTrue(in_process.send_ref_writable)
        self.assertFalse(in_process.recv_ref_readable)
        self.assertTrue(sent.date_writable)
        self.assertTrue(sent.recipient_readable)
        self.assertTrue(sent.recipient_writable)
        self.assertTrue(sent.comments_writable)
        self.assertFalse(received.send_ref_writable)
        self.assertFalse(received.date_writable)
        self.assertFalse(received.comments_writable)

    # -------------------------------------------------------------------------
    def testRecvPrepRejectsTrackItemCreateOutsidePreparing(self):
        """recv prep blocks creating track rows once the shipment has left draft"""

        s3db = current.s3db
        ship_status = s3db.inv_ship_status
        origin = self.create_office(name="Origin")
        destination = self.create_office(name="Destination")
        recv_id = self.create_recv(destination.site_id,
                                   from_site_id=origin.site_id,
                                   status=ship_status["SENT"],
                                   )

        with self.controller("inv",
                             function="recv",
                             args=[str(recv_id), "track_item"],
                             ) as controller:
            output = controller.module["recv"]()
            prep = output.prep
            record = current.db(s3db.inv_recv.id == recv_id).select(s3db.inv_recv.ALL,
                                                                    limitby=(0, 1),
                                                                    ).first()
            r = Storage(record=record,
                        component=Storage(name="track_item"),
                        component_name="track_item",
                        component_id=None,
                        method="create",
                        id=recv_id,
                        )
            allowed = prep(r)

        self.assertFalse(allowed)

    # -------------------------------------------------------------------------
    def testRecvPrepSimplifiesDocumentUploads(self):
        """recv prep simplifies document components to mandatory file uploads"""

        s3db = current.s3db
        ship_status = s3db.inv_ship_status
        origin = self.create_office(name="Origin")
        destination = self.create_office(name="Destination")
        recv_id = self.create_recv(destination.site_id,
                                   from_site_id=origin.site_id,
                                   status=ship_status["IN_PROCESS"],
                                   )

        dtable = s3db.doc_document
        saved = Storage(file_required=dtable.file.required,
                        url_readable=dtable.url.readable,
                        url_writable=dtable.url.writable,
                        date_readable=dtable.date.readable,
                        date_writable=dtable.date.writable,
                        )

        try:
            with self.controller("inv",
                                 function="recv",
                                 args=[str(recv_id), "document"],
                                 ) as controller:
                output = controller.module["recv"]()
                prep = output.prep
                record = current.db(s3db.inv_recv.id == recv_id).select(s3db.inv_recv.ALL,
                                                                        limitby=(0, 1),
                                                                        ).first()
                r = Storage(record=record,
                            component=Storage(name="document"),
                            component_name="document",
                            component_id=None,
                            method="create",
                            id=recv_id,
                            )
                self.assertTrue(prep(r))
                file_required = dtable.file.required
                url_readable = dtable.url.readable
                url_writable = dtable.url.writable
                date_readable = dtable.date.readable
                date_writable = dtable.date.writable
        finally:
            dtable.file.required = saved.file_required
            dtable.url.readable = saved.url_readable
            dtable.url.writable = saved.url_writable
            dtable.date.readable = saved.date_readable
            dtable.date.writable = saved.date_writable

        self.assertTrue(file_required)
        self.assertFalse(url_readable)
        self.assertFalse(url_writable)
        self.assertFalse(date_readable)
        self.assertFalse(date_writable)

    # -------------------------------------------------------------------------
    def testTrackItemReportsConfigureListFieldsAndFilters(self):
        """track_item report variants select report-specific fields and filters"""

        s3db = current.s3db
        saved_list_fields = s3db.get_config("inv_track_item", "list_fields")
        saved_orderby = s3db.get_config("inv_track_item", "orderby")
        saved_filter = current.response.s3.filter
        saved_strings = current.response.s3.crud_strings["inv_track_item"]

        try:
            expectations = {"rel": "send_id$date",
                            "inc": "recv_id$date",
                            "util": "send_id$site_id",
                            "exp": "expiry_date",
                            }
            for report, expected in expectations.items():
                with self.subTest(report=report):
                    with self.controller("inv",
                                         function="track_item",
                                         query_vars={"report": report},
                                         ) as controller:
                        output = controller.module["track_item"]()
                        list_fields = s3db.get_config("inv_track_item", "list_fields")
                        title = current.response.s3.crud_strings["inv_track_item"].title_list
                        self.assertEqual(output.args, ())
                        self.assertTrue(any(expected in str(field) for field in list_fields))
                        self.assertIsNotNone(current.response.s3.filter)
                        self.assertIsNotNone(title)
        finally:
            s3db.configure("inv_track_item",
                           list_fields=saved_list_fields,
                           orderby=saved_orderby,
                           )
            current.response.s3.filter = saved_filter
            current.response.s3.crud_strings["inv_track_item"] = saved_strings

    # -------------------------------------------------------------------------
    def testAdjPrepCreatesSingleItemAdjustmentAndRedirects(self):
        """adj prep creates one-line adjustments from stock shortcuts"""

        db = current.db
        s3db = current.s3db

        office = self.create_office(name="Adjustable Site")
        item_id = self.create_supply_item(name="Adjustable Item")
        pack_id = self.create_item_pack(item_id, quantity=1)
        inv_item_id = self.create_inventory_item(office.site_id,
                                                 item_id,
                                                 pack_id,
                                                 quantity=6,
                                                 status=0,
                                                 )

        with self.controller("inv",
                             function="adj",
                             query_vars={"item": str(inv_item_id),
                                         "site": str(office.site_id),
                                         },
                             ) as controller:
            output = controller.module["adj"]()
            prep = output.prep
            r = Storage(interactive=True,
                        component=None,
                        record=None,
                        )
            with self.assertRaises(ControllerRedirect) as redirect:
                prep(r)

        adj = db(s3db.inv_adj.comments == "Single item adjustment").select(s3db.inv_adj.id,
                                                                           limitby=(0, 1),
                                                                           orderby=~s3db.inv_adj.id,
                                                                           ).first()
        self.assertIsNotNone(adj)
        adj_item = db(s3db.inv_adj_item.adj_id == adj.id).select(s3db.inv_adj_item.id,
                                                                 s3db.inv_adj_item.inv_item_id,
                                                                 limitby=(0, 1),
                                                                 ).first()
        self.assertEqual(adj_item.inv_item_id, inv_item_id)
        self.assertIn("/inv/adj/%s/adj_item/%s/update" % (adj.id, adj_item.id),
                      str(redirect.exception.url))

    # -------------------------------------------------------------------------
    def testAdjPrepDefaultsCompleteStockAdjustment(self):
        """adj prep defaults site and comments for complete stock adjustments"""

        s3db = current.s3db
        table = s3db.inv_adj
        office = self.create_office(name="Stocktake Site")

        saved_comments = table.comments.default
        saved_site_default = table.site_id.default
        saved_site_writable = table.site_id.writable

        try:
            with self.controller("inv",
                                 function="adj",
                                 query_vars={"site": str(office.site_id)},
                                 ) as controller:
                output = controller.module["adj"]()
                prep = output.prep
                r = Storage(interactive=True,
                            component=None,
                            record=None,
                            )
                self.assertTrue(prep(r))
                comments_default = table.comments.default
                site_default = table.site_id.default
                site_writable = table.site_id.writable
        finally:
            table.comments.default = saved_comments
            table.site_id.default = saved_site_default
            table.site_id.writable = saved_site_writable

        self.assertEqual(comments_default, "Complete Stock Adjustment")
        self.assertEqual(site_default, str(office.site_id))
        self.assertTrue(site_writable)

    # -------------------------------------------------------------------------
    def testAdjPrepConfiguresExistingItemsImagesAndClosedAdjustments(self):
        """adj prep handles existing items, linked images and closed adjustments correctly"""

        db = current.db
        s3db = current.s3db
        table = s3db.inv_adj
        aitable = s3db.inv_adj_item
        doc_table = s3db.doc_image

        office = self.create_office(name="Adjustment Office")
        item_id = self.create_supply_item(name="Adjustment Item")
        pack_id = self.create_item_pack(item_id, quantity=1)
        inv_item_id = self.create_inventory_item(office.site_id,
                                                 item_id,
                                                 pack_id,
                                                 quantity=8,
                                                 )
        open_id = table.insert(site_id=office.site_id,
                               adjuster_id=self.create_person(last_name="OpenAdjuster"),
                               adjustment_date=current.request.utcnow,
                               status=0,
                               category=1,
                               )
        adj_item_id = aitable.insert(adj_id=open_id,
                                     inv_item_id=inv_item_id,
                                     item_id=item_id,
                                     item_pack_id=pack_id,
                                     old_quantity=8,
                                     new_quantity=7,
                                     reason=0,
                                     )
        closed_id = table.insert(site_id=office.site_id,
                                 adjuster_id=self.create_person(last_name="ClosedAdjuster"),
                                 adjustment_date=current.request.utcnow,
                                 status=1,
                                 category=1,
                                 )

        saved_reason_writable = aitable.reason.writable
        saved_item_writable = aitable.item_id.writable
        saved_item_comment = aitable.item_id.comment
        saved_pack_writable = aitable.item_pack_id.writable
        saved_org_readable = doc_table.organisation_id.readable
        saved_org_writable = doc_table.organisation_id.writable
        saved_person_readable = doc_table.person_id.readable
        saved_person_writable = doc_table.person_id.writable
        saved_location_readable = doc_table.location_id.readable
        saved_location_writable = doc_table.location_id.writable
        saved_adjuster_writable = table.adjuster_id.writable
        saved_site_writable = table.site_id.writable
        saved_comments_writable = table.comments.writable
        saved_create = s3db.get_config("inv_adj_item", "create")
        saved_deletable = s3db.get_config("inv_adj_item", "deletable")
        saved_editable = s3db.get_config("inv_adj_item", "editable")
        saved_listadd = s3db.get_config("inv_adj_item", "listadd")

        try:
            with self.controller("inv",
                                 function="adj",
                                 args=[str(open_id), "adj_item"],
                                 ) as controller:
                output = controller.module["adj"]()
                prep = output.prep
                record = db(table.id == open_id).select(table.ALL,
                                                        limitby=(0, 1),
                                                        ).first()
                self.assertTrue(prep(Storage(interactive=True,
                                             component=Storage(name="adj_item"),
                                             component_name="adj_item",
                                             component_id=adj_item_id,
                                             record=record,
                                             )))
                reason_writable = aitable.reason.writable
                item_writable = aitable.item_id.writable
                item_comment = aitable.item_id.comment
                pack_writable = aitable.item_pack_id.writable

            with self.controller("inv",
                                 function="adj",
                                 args=[str(open_id), "image"],
                                 ) as controller:
                output = controller.module["adj"]()
                prep = output.prep
                record = db(table.id == open_id).select(table.ALL,
                                                        limitby=(0, 1),
                                                        ).first()
                self.assertTrue(prep(Storage(interactive=True,
                                             component=Storage(name="image"),
                                             component_name="image",
                                             component_id=None,
                                             record=record,
                                             )))
                org_readable = doc_table.organisation_id.readable
                org_writable = doc_table.organisation_id.writable
                person_readable = doc_table.person_id.readable
                person_writable = doc_table.person_id.writable
                location_readable = doc_table.location_id.readable
                location_writable = doc_table.location_id.writable

            with self.controller("inv",
                                 function="adj",
                                 args=[str(closed_id), "adj_item"],
                                 ) as controller:
                output = controller.module["adj"]()
                prep = output.prep
                record = db(table.id == closed_id).select(table.ALL,
                                                          limitby=(0, 1),
                                                          ).first()
                self.assertTrue(prep(Storage(interactive=True,
                                             component=None,
                                             record=record,
                                             )))
                adjuster_writable = table.adjuster_id.writable
                site_writable = table.site_id.writable
                comments_writable = table.comments.writable
                create = s3db.get_config("inv_adj_item", "create")
                deletable = s3db.get_config("inv_adj_item", "deletable")
                editable = s3db.get_config("inv_adj_item", "editable")
                listadd = s3db.get_config("inv_adj_item", "listadd")
        finally:
            aitable.reason.writable = saved_reason_writable
            aitable.item_id.writable = saved_item_writable
            aitable.item_id.comment = saved_item_comment
            aitable.item_pack_id.writable = saved_pack_writable
            doc_table.organisation_id.readable = saved_org_readable
            doc_table.organisation_id.writable = saved_org_writable
            doc_table.person_id.readable = saved_person_readable
            doc_table.person_id.writable = saved_person_writable
            doc_table.location_id.readable = saved_location_readable
            doc_table.location_id.writable = saved_location_writable
            table.adjuster_id.writable = saved_adjuster_writable
            table.site_id.writable = saved_site_writable
            table.comments.writable = saved_comments_writable
            s3db.configure("inv_adj_item",
                           create=saved_create,
                           deletable=saved_deletable,
                           editable=saved_editable,
                           listadd=saved_listadd,
                           )

        self.assertTrue(reason_writable)
        self.assertFalse(item_writable)
        self.assertIsNone(item_comment)
        self.assertFalse(pack_writable)
        self.assertFalse(org_readable)
        self.assertFalse(org_writable)
        self.assertFalse(person_readable)
        self.assertFalse(person_writable)
        self.assertFalse(location_readable)
        self.assertFalse(location_writable)
        self.assertFalse(adjuster_writable)
        self.assertFalse(site_writable)
        self.assertFalse(comments_writable)
        self.assertFalse(create)
        self.assertFalse(deletable)
        self.assertFalse(editable)
        self.assertFalse(listadd)

    # -------------------------------------------------------------------------
    def testAdjCloseRejectsMissingAndClosedAdjustments(self):
        """adj_close redirects missing requests and refuses already closed adjustments"""

        db = current.db
        s3db = current.s3db
        session = current.session

        office = self.create_office(name="Adj Close Office")
        adj_id = s3db.inv_adj.insert(site_id=office.site_id,
                                     adjuster_id=self.create_person(last_name="Closer"),
                                     adjustment_date=current.request.utcnow,
                                     status=1,
                                     category=1,
                                     )

        saved_error = session.error

        try:
            with self.controller("inv", function="adj_close") as controller:
                with self.assertRaises(ControllerRedirect) as redirect:
                    controller.module["adj_close"]()
                missing_url = str(redirect.exception.url)

            session.error = None
            with self.controller("inv",
                                 function="adj_close",
                                 args=[str(adj_id)],
                                 ) as controller:
                with self.assertRaises(ControllerRedirect) as redirect:
                    controller.module["adj_close"]()
                closed_url = str(redirect.exception.url)
                closed_error = session.error
        finally:
            session.error = saved_error

        self.assertIn("/inv/adj", missing_url)
        self.assertIn("/inv/adj/%s" % adj_id, closed_url)
        self.assertEqual(str(closed_error), "This adjustment has already been closed.")

    # -------------------------------------------------------------------------
    def testAdjCloseAppliesInventoryChangesAndRedirectsToSiteStock(self):
        """adj_close creates missing stock, updates existing stock and closes the record"""

        auth = current.auth
        db = current.db
        s3db = current.s3db
        session = current.session

        office = self.create_office(name="Adjustment Site")
        item_a = self.create_supply_item(name="New Stock Item")
        item_b = self.create_supply_item(name="Existing Stock Item")
        pack_a = self.create_item_pack(item_a, quantity=1)
        pack_b = self.create_item_pack(item_b, quantity=1)
        existing_inv_item_id = self.create_inventory_item(office.site_id,
                                                          item_b,
                                                          pack_b,
                                                          quantity=8,
                                                          status=0,
                                                          )

        atable = s3db.inv_adj
        aitable = s3db.inv_adj_item
        adj_id = atable.insert(site_id=office.site_id,
                               status=0,
                               )
        aitable.insert(adj_id=adj_id,
                       inv_item_id=None,
                       item_id=item_a,
                       item_pack_id=pack_a,
                       currency="USD",
                       bin="A1",
                       old_pack_value=3,
                       expiry_date=None,
                       new_quantity=4,
                       old_owner_org_id=office.organisation_id,
                       )
        aitable.insert(adj_id=adj_id,
                       inv_item_id=existing_inv_item_id,
                       item_id=item_b,
                       item_pack_id=pack_b,
                       currency="USD",
                       bin="B2",
                       old_pack_value=5,
                       expiry_date=None,
                       new_quantity=2,
                       new_owner_org_id=office.organisation_id,
                       new_status=1,
                       )

        saved_realm = auth.get_realm_entity
        saved_error = session.error
        auth.get_realm_entity = lambda table, record: 99

        try:
            session.error = None
            with self.controller("inv",
                                 function="adj_close",
                                 args=[str(adj_id)],
                                 ) as controller:
                with self.assertRaises(ControllerRedirect) as redirect:
                    controller.module["adj_close"]()
                url = str(redirect.exception.url)
        finally:
            auth.get_realm_entity = saved_realm
            session.error = saved_error

        adj = db(atable.id == adj_id).select(atable.status,
                                             limitby=(0, 1),
                                             ).first()
        new_item = db((s3db.inv_inv_item.site_id == office.site_id) &
                      (s3db.inv_inv_item.item_id == item_a)).select(s3db.inv_inv_item.quantity,
                                                                    s3db.inv_inv_item.realm_entity,
                                                                    limitby=(0, 1),
                                                                    ).first()
        existing = db(s3db.inv_inv_item.id == existing_inv_item_id).select(s3db.inv_inv_item.quantity,
                                                                           s3db.inv_inv_item.status,
                                                                           limitby=(0, 1),
                                                                           ).first()

        self.assertEqual(adj.status, 1)
        self.assertEqual(new_item.quantity, 4)
        self.assertEqual(new_item.realm_entity, 99)
        self.assertEqual(existing.quantity, 2)
        self.assertEqual(existing.status, 1)
        self.assertIn("/org/office/%s/inv_item" % office.id, url)

    # -------------------------------------------------------------------------
    def testReceiveAndSendItemJsonEndpointsReturnShipmentSummaries(self):
        """recv_item_json and send_item_json prepend summary rows to JSON payloads"""

        db = current.db
        s3db = current.s3db
        recvtable = s3db.inv_recv
        sendtable = s3db.inv_send

        origin = self.create_office(name="Sender")
        destination = self.create_office(name="Receiver")
        item_id = self.create_supply_item(name="JSON Item")
        pack_id = self.create_item_pack(item_id, quantity=1)

        req_id = self.create_request(destination.site_id)
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=2,
                                               )

        send_id = self.create_send(origin.site_id,
                                   to_site_id=destination.site_id,
                                   status=s3db.inv_ship_status["SENT"],
                                   date=datetime.date(2026, 3, 7),
                                   )
        recv_id = self.create_recv(destination.site_id,
                                   from_site_id=origin.site_id,
                                   status=s3db.inv_ship_status["RECEIVED"],
                                   date=datetime.date(2026, 3, 8),
                                   )
        track_id = self.create_track_item(item_id,
                                          pack_id,
                                          quantity=2,
                                          req_item_id=req_item_id,
                                          send_id=send_id,
                                          recv_id=recv_id,
                                          status=s3db.inv_tracking_status["RECEIVED"],
                                          )
        db(s3db.inv_track_item.id == track_id).update(deleted=False)

        saved_recv_represent = recvtable.date.represent
        saved_send_represent = sendtable.date.represent

        try:
            with self.controller("inv",
                                 function="recv_item_json",
                                 args=[str(req_item_id)],
                                 ) as controller:
                recv_payload = json.loads(controller.module["recv_item_json"]())

            with self.controller("inv",
                                 function="send_item_json",
                                 args=[str(req_item_id)],
                                 ) as controller:
                send_payload = json.loads(controller.module["send_item_json"]())
        finally:
            recvtable.date.represent = saved_recv_represent
            sendtable.date.represent = saved_send_represent

        self.assertEqual(recv_payload[0]["id"], "Received")
        self.assertEqual(send_payload[0]["id"], "Sent")
        self.assertGreaterEqual(len(recv_payload), 2)
        self.assertGreaterEqual(len(send_payload), 2)
        self.assertIn("'id': %s" % recv_id, str(recv_payload[1]))
        self.assertIn("'id': %s" % send_id, str(send_payload[1]))

    # -------------------------------------------------------------------------
    def testReceiveAndSendItemJsonEndpointsRejectMissingIds(self):
        """recv_item_json and send_item_json reject requests that omit the request item ID"""

        with self.controller("inv", function="recv_item_json") as controller:
            with self.assertRaises(HTTP) as recv_error:
                controller.module["recv_item_json"]()

        with self.controller("inv", function="send_item_json") as controller:
            with self.assertRaises(HTTP) as send_error:
                controller.module["send_item_json"]()

        self.assertEqual(recv_error.exception.status, 400)
        self.assertEqual(send_error.exception.status, 400)

    # -------------------------------------------------------------------------
    def testKittingFacilityAndProjectControllersDelegateWithExpectedConfig(self):
        """kitting, facility, facility_type and project expose the expected CRUD setup"""

        s3db = current.s3db
        saved_facility = s3db.org_facility_controller
        saved_create_next = s3db.get_config("org_facility", "create_next")
        saved_form = s3db.get_config("project_project", "crud_form")
        saved_filters = s3db.get_config("project_project", "filter_widgets")
        saved_list_fields = s3db.get_config("project_project", "list_fields")
        s3db.org_facility_controller = lambda: "FACILITY"

        try:
            with self.controller("inv", function="kitting") as controller:
                kitting_output = controller.module["kitting"]()

            with self.controller("inv", function="facility") as controller:
                facility_output = controller.module["facility"]()
                create_next = s3db.get_config("org_facility", "create_next")

            with self.controller("inv", function="facility_type") as controller:
                facility_type_output = controller.module["facility_type"]()

            with self.controller("inv", function="project") as controller:
                project_output = controller.module["project"]()
                configured_fields = s3db.get_config("project_project", "list_fields")
        finally:
            s3db.org_facility_controller = saved_facility
            s3db.configure("org_facility", create_next=saved_create_next)
            s3db.configure("project_project",
                           crud_form=saved_form,
                           filter_widgets=saved_filters,
                           list_fields=saved_list_fields,
                           )

        self.assertEqual(kitting_output.args, ())
        self.assertEqual(kitting_output.kwargs["rheader"], s3db.inv_rheader)
        self.assertEqual(facility_output, "FACILITY")
        self.assertEqual(create_next, URL(c="inv", f="facility", args=["[id]", "read"]))
        self.assertEqual(facility_type_output.args, ("org",))
        self.assertEqual(project_output.args, ("project",))
        self.assertEqual(configured_fields,
                         ["organisation_id", "code", "name", "end_date"])


# =============================================================================
if __name__ == "__main__":

    run_suite(
        InventoryRepresentationTests,
        WarehouseValidationTests,
        InventoryMeasureComputationTests,
        InventoryWorkflowTests,
        InventoryReportTests,
        TrackItemQuantityNeededTests,
        InventoryModelHelperTests,
        InventoryHeaderTests,
        InventoryAdjustmentTests,
        InventoryControllerTests,
    )

# END ========================================================================
