# REQ Unit Tests
#
# To run this script use:
# python web2py.py -S eden -M -R applications/eden/modules/unit_tests/s3db/req.py
#
import unittest

from gluon import A, B, current
from gluon.storage import Storage

import s3db.req as req_module
from s3db.req import (CommitItemModel,
                      CommitModel,
                      REQ_STATUS_COMPLETE,
                      REQ_STATUS_NONE,
                      REQ_STATUS_PARTIAL,
                      RequestItemModel,
                      RequestModel,
                      req_CommitRepresent,
                      req_RequesterRepresent,
                      req_ReqItemRepresent,
                      req_add_from_template,
                      req_approvers,
                      req_create_form_mods,
                      req_hide_quantities,
                      req_inline_form,
                      req_is_approver,
                      req_req_details,
                      req_req_drivers,
                      req_ref_represent,
                      req_send_commit,
                      req_tabs,
                      req_update_commit_quantities_and_status,
                      req_update_status,
                      )
from unit_tests import run_suite
from unit_tests.s3db.helpers import SupplyChainTestCase


class RedirectIntercept(Exception):
    """Raised to intercept web2py redirects in unit tests"""

    def __init__(self, url):

        super().__init__(url)
        self.url = url


# =============================================================================
class ReqRepresentationTests(SupplyChainTestCase):
    """Tests for request reference representation helpers"""

    # -------------------------------------------------------------------------
    def testReqRefRepresent(self):
        """req_ref representation supports link, no-link and pdf variants"""

        office = self.create_office()
        request_id = self.create_request(office.site_id,
                                         req_ref="REQ-REP-001",
                                         )

        link = req_ref_represent("REQ-REP-001")
        self.assertTrue(isinstance(link, A))
        self.assertEqual(link.attributes["_href"],
                         "/%s/req/req/%s" % (current.request.application, request_id))
        self.assertEqual(link.components[0], "REQ-REP-001")

        pdf_link = req_ref_represent("REQ-REP-001", pdf=True)
        self.assertTrue(isinstance(pdf_link, A))
        self.assertEqual(pdf_link.attributes["_href"],
                         "/%s/req/req/%s/form" % (current.request.application, request_id))

        plain = req_ref_represent("REQ-REP-001", show_link=False)
        self.assertTrue(isinstance(plain, B))
        self.assertEqual(plain.components[0], "REQ-REP-001")

        self.assertEqual(req_ref_represent(None), current.messages["NONE"])

    # -------------------------------------------------------------------------
    def testReqRefFieldCallback(self):
        """req_req.req_ref field callback accepts show_link and pdf"""

        office = self.create_office()
        request_id = self.create_request(office.site_id,
                                         req_ref="REQ-FIELD-001",
                                         )

        field = current.s3db.req_req.req_ref

        result = field.represent("REQ-FIELD-001", show_link=True, pdf=True)
        self.assertTrue(isinstance(result, A))
        self.assertEqual(result.attributes["_href"],
                         "/%s/req/req/%s/form" % (current.request.application, request_id))

        result = field.represent("REQ-FIELD-001", show_link=False, pdf=True)
        self.assertTrue(isinstance(result, B))
        self.assertEqual(result.components[0], "REQ-FIELD-001")

    # -------------------------------------------------------------------------
    def testReqRepresentSupportsReferenceAndFallbackText(self):
        """Request representation uses req_ref or falls back to site/date"""

        db = current.db
        s3db = current.s3db

        office = self.create_office(name="Req Represent Office")
        dated = self.create_request(office.site_id,
                                    req_ref="REQ-MODEL-001",
                                    )
        undated = self.create_request(office.site_id,
                                      req_ref=None,
                                      )

        represented = RequestModel.req_represent(dated, show_link=False)
        self.assertEqual(represented, "REQ-MODEL-001")

        fallback = RequestModel.req_represent(undated, show_link=False)
        row = db(s3db.req_req.id == undated).select(s3db.req_req.date,
                                                    s3db.req_req.site_id,
                                                    limitby=(0, 1),
                                                    ).first()
        expected = "%s - %s" % (s3db.req_req.site_id.represent(row.site_id, show_link=False),
                                 s3db.req_req.date.represent(row.date),
                                 )
        self.assertEqual(str(fallback), str(expected))
        self.assertNotEqual(fallback, current.messages["UNKNOWN_OPT"])

        self.assertEqual(RequestModel.req_represent(999999, show_link=False),
                         current.messages.UNKNOWN_OPT)

    # -------------------------------------------------------------------------
    def testRequesterReqItemAndCommitRepresentations(self):
        """Custom S3Represent helpers render requester, item and commit data"""

        db = current.db
        s3db = current.s3db

        office = self.create_office(name="Commit Office")
        requester_id = self.create_person(last_name="Approver")
        self.create_contact(requester_id, "+48123456789")

        item_id = self.create_supply_item(name="Water Bottle")
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(office.site_id)
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=4,
                                               )
        commit_id = self.create_commit(req_id,
                                       site_id=office.site_id,
                                       organisation_id=office.organisation_id,
                                       )
        db(s3db.req_commit.id == commit_id).update(type=1)

        requester_repr = req_RequesterRepresent(show_link=False)
        requester_repr.table = s3db.pr_person
        rows = requester_repr.lookup_rows(None, [requester_id])
        self.assertEqual(len(rows), 1)
        self.assertIn("+48123456789", requester_repr.represent_row(rows.first()))

        link = requester_repr.link(requester_id,
                                   "Requester",
                                   row=Storage(hrm_human_resource=Storage(type=1)),
                                   )
        self.assertEqual(link.attributes["_href"],
                         "/%s/hrm/person/%s/contacts" % (current.request.application,
                                                          requester_id,
                                                          ))

        item_repr = req_ReqItemRepresent()
        item_repr.table = s3db.req_req_item
        rows = item_repr.lookup_rows(None, [req_item_id])
        self.assertEqual(item_repr.represent_row(rows.first()), "Water Bottle")

        commit_repr = req_CommitRepresent()
        commit_repr.table = s3db.req_commit
        rows = commit_repr.lookup_rows(None, [commit_id])
        row = rows.first()
        commit_text = str(commit_repr.represent_row(row))
        expected_site = str(s3db.req_commit.site_id.represent(office.site_id))
        self.assertIn(expected_site, commit_text)
        expected_date = str(s3db.req_commit.date.represent(row.date))
        self.assertIn(expected_date, commit_text)


# =============================================================================
class ReqStatusTests(SupplyChainTestCase):
    """Tests for request status calculations"""

    # -------------------------------------------------------------------------
    def testReqUpdateStatus(self):
        """req_update_status computes NONE, PARTIAL and COMPLETE correctly"""

        db = current.db
        s3db = current.s3db

        office = self.create_office()
        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id, quantity=2)

        req_id = self.create_request(office.site_id)
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=10,
                                               )

        rtable = s3db.req_req
        ritable = s3db.req_req_item

        req_update_status(req_id)
        req = db(rtable.id == req_id).select(rtable.commit_status,
                                             rtable.transit_status,
                                             rtable.fulfil_status,
                                             limitby=(0, 1),
                                             ).first()
        self.assertEqual(req.commit_status, REQ_STATUS_NONE)
        self.assertEqual(req.transit_status, REQ_STATUS_NONE)
        self.assertEqual(req.fulfil_status, REQ_STATUS_NONE)

        db(ritable.id == req_item_id).update(quantity_commit=10,
                                             quantity_transit=5,
                                             quantity_fulfil=0,
                                             )
        req_update_status(req_id)
        req = db(rtable.id == req_id).select(rtable.commit_status,
                                             rtable.transit_status,
                                             rtable.fulfil_status,
                                             limitby=(0, 1),
                                             ).first()
        self.assertEqual(req.commit_status, REQ_STATUS_COMPLETE)
        self.assertEqual(req.transit_status, REQ_STATUS_PARTIAL)
        self.assertEqual(req.fulfil_status, REQ_STATUS_NONE)

        db(ritable.id == req_item_id).update(quantity_transit=10,
                                             quantity_fulfil=10,
                                             )
        req_update_status(req_id)
        req = db(rtable.id == req_id).select(rtable.commit_status,
                                             rtable.transit_status,
                                             rtable.fulfil_status,
                                             limitby=(0, 1),
                                             ).first()
        self.assertEqual(req.commit_status, REQ_STATUS_COMPLETE)
        self.assertEqual(req.transit_status, REQ_STATUS_COMPLETE)
        self.assertEqual(req.fulfil_status, REQ_STATUS_COMPLETE)

    # -------------------------------------------------------------------------
    def testReqUpdateCommitQuantitiesAndStatusForItems(self):
        """req_update_commit_quantities_and_status updates item commitments"""

        db = current.db
        s3db = current.s3db

        office = self.create_office()
        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id, quantity=2)

        req_id = self.create_request(office.site_id,
                                     req_type=1,
                                     commit_status=REQ_STATUS_NONE,
                                     )
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=6,
                                               )
        commit_id = self.create_commit(req_id,
                                       site_id=office.site_id,
                                       organisation_id=office.organisation_id,
                                       )
        self.create_commit_item(commit_id, req_item_id, pack_id, quantity=5)

        rtable = s3db.req_req
        ritable = s3db.req_req_item

        req = db(rtable.id == req_id).select(rtable.id,
                                             rtable.type,
                                             rtable.commit_status,
                                             limitby=(0, 1),
                                             ).first()
        req_update_commit_quantities_and_status(req)

        req_item = db(ritable.id == req_item_id).select(ritable.quantity_commit,
                                                        limitby=(0, 1),
                                                        ).first()
        self.assertEqual(req_item.quantity_commit, 10)

        req = db(rtable.id == req_id).select(rtable.commit_status,
                                             limitby=(0, 1),
                                             ).first()
        self.assertEqual(req.commit_status, REQ_STATUS_PARTIAL)

        self.create_commit_item(commit_id, req_item_id, pack_id, quantity=1)
        req = db(rtable.id == req_id).select(rtable.id,
                                             rtable.type,
                                             rtable.commit_status,
                                             limitby=(0, 1),
                                             ).first()
        req_update_commit_quantities_and_status(req)

        req_item = db(ritable.id == req_item_id).select(ritable.quantity_commit,
                                                        limitby=(0, 1),
                                                        ).first()
        self.assertEqual(req_item.quantity_commit, 12)

        req = db(rtable.id == req_id).select(rtable.commit_status,
                                             limitby=(0, 1),
                                             ).first()
        self.assertEqual(req.commit_status, REQ_STATUS_COMPLETE)

    # -------------------------------------------------------------------------
    def testReqUpdateCommitQuantitiesAndStatusForSkills(self):
        """Committed skill quantities are matched against requested skill sets"""

        db = current.db
        s3db = current.s3db

        office = self.create_office()
        skill_id = self.create_skill("Logistics")

        req_id = self.create_request(office.site_id,
                                     req_type=3,
                                     commit_status=REQ_STATUS_NONE,
                                     )
        req_skill_id = self.create_request_skill(req_id,
                                                 skill_ids=[skill_id],
                                                 quantity=2,
                                                 )
        commit_id = self.create_commit(req_id,
                                       site_id=office.site_id,
                                       organisation_id=office.organisation_id,
                                       )
        self.create_commit_skill(commit_id, skill_ids=[skill_id], quantity=1)

        rtable = s3db.req_req
        stable = s3db.req_req_skill

        req = db(rtable.id == req_id).select(rtable.id,
                                             rtable.type,
                                             rtable.commit_status,
                                             limitby=(0, 1),
                                             ).first()
        req_update_commit_quantities_and_status(req)

        row = db(stable.id == req_skill_id).select(stable.quantity_commit,
                                                   limitby=(0, 1),
                                                   ).first()
        self.assertEqual(row.quantity_commit, 1)

        req = db(rtable.id == req_id).select(rtable.commit_status,
                                             limitby=(0, 1),
                                             ).first()
        self.assertEqual(req.commit_status, REQ_STATUS_PARTIAL)

        self.create_commit_skill(commit_id, skill_ids=[skill_id], quantity=1)
        req = db(rtable.id == req_id).select(rtable.id,
                                             rtable.type,
                                             rtable.commit_status,
                                             limitby=(0, 1),
                                             ).first()
        req_update_commit_quantities_and_status(req)

        row = db(stable.id == req_skill_id).select(stable.quantity_commit,
                                                   limitby=(0, 1),
                                                   ).first()
        self.assertEqual(row.quantity_commit, 2)

        req = db(rtable.id == req_id).select(rtable.commit_status,
                                             limitby=(0, 1),
                                             ).first()
        self.assertEqual(req.commit_status, REQ_STATUS_COMPLETE)

    # -------------------------------------------------------------------------
    def testReqUpdateCommitQuantitiesAndStatusForOtherRequests(self):
        """Other request types transition from NONE to PARTIAL when committed"""

        db = current.db
        s3db = current.s3db

        office = self.create_office()
        req_id = self.create_request(office.site_id,
                                     req_type=9,
                                     req_status=REQ_STATUS_NONE,
                                     commit_status=REQ_STATUS_NONE,
                                     )
        commit_id = self.create_commit(req_id,
                                       site_id=office.site_id,
                                       organisation_id=office.organisation_id,
                                       )
        db(s3db.req_commit.id == commit_id).update(type=9)

        rtable = s3db.req_req
        req = db(rtable.id == req_id).select(rtable.id,
                                             rtable.type,
                                             rtable.req_status,
                                             rtable.commit_status,
                                             limitby=(0, 1),
                                             ).first()
        req_update_commit_quantities_and_status(req)

        req = db(rtable.id == req_id).select(rtable.req_status,
                                             rtable.commit_status,
                                             limitby=(0, 1),
                                             ).first()
        self.assertEqual(req.commit_status, REQ_STATUS_PARTIAL)
        self.assertEqual(req.req_status, REQ_STATUS_PARTIAL)


# =============================================================================
class ReqCallbackTests(SupplyChainTestCase):
    """Tests for req/commit onaccept and ondelete callbacks"""

    # -------------------------------------------------------------------------
    def testReqItemOnacceptAddsCategoryLink(self):
        """Requested item onaccept adds request-category link entries"""

        db = current.db
        s3db = current.s3db

        office = self.create_office()
        catalog_id = self.create_catalog()
        category_id = self.create_item_category(catalog_id, name="Food")
        item_id = self.create_supply_item(catalog_id=catalog_id,
                                          item_category_id=category_id,
                                          )
        self.create_catalog_item(catalog_id, item_id, item_category_id=category_id)

        req_id = self.create_request(office.site_id)
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               self.create_item_pack(item_id, quantity=1),
                                               quantity=5,
                                               )

        form = self.make_form(id=req_item_id,
                              req_id=req_id,
                              item_id=item_id,
                              )
        RequestItemModel.req_item_onaccept(form)

        ltable = s3db.req_req_item_category
        row = db((ltable.req_id == req_id) &
                 (ltable.item_category_id == category_id),
                 ).select(ltable.id,
                          limitby=(0, 1),
                          ).first()
        self.assertIsNotNone(row)

    # -------------------------------------------------------------------------
    def testReqItemOndeleteRemovesCategoryLinkWhenLastItemDeleted(self):
        """Requested item ondelete removes obsolete request-category links"""

        db = current.db
        s3db = current.s3db

        office = self.create_office()
        catalog_id = self.create_catalog()
        category_id = self.create_item_category(catalog_id, name="Shelter")
        item_id = self.create_supply_item(catalog_id=catalog_id,
                                          item_category_id=category_id,
                                          )
        pack_id = self.create_item_pack(item_id, quantity=1)
        self.create_catalog_item(catalog_id, item_id, item_category_id=category_id)

        req_id = self.create_request(office.site_id)
        req_item_id = self.create_request_item(req_id, item_id, pack_id, quantity=2)
        RequestItemModel.req_item_onaccept(self.make_form(id=req_item_id,
                                                          req_id=req_id,
                                                          item_id=item_id,
                                                          ))

        ritable = s3db.req_req_item
        db(ritable.id == req_item_id).update(deleted=True,
                                             deleted_fk='{"req_id": %s, "item_id": %s}' % (req_id,
                                                                                            item_id,
                                                                                            ),
                                             )
        RequestItemModel.req_item_ondelete(Storage(id=req_item_id))

        ltable = s3db.req_req_item_category
        row = db((ltable.req_id == req_id) &
                 (ltable.item_category_id == category_id),
                 ).select(ltable.id,
                          limitby=(0, 1),
                          ).first()
        self.assertIsNone(row)

    # -------------------------------------------------------------------------
    def testCommitOnacceptSetsTypeAndUpdatesRequest(self):
        """Commit onaccept derives commit type from the linked request"""

        db = current.db
        s3db = current.s3db

        office = self.create_office()
        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id, quantity=2)

        req_id = self.create_request(office.site_id,
                                     req_type=1,
                                     commit_status=REQ_STATUS_NONE,
                                     )
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=3,
                                               )
        commit_id = self.create_commit(req_id,
                                       site_id=office.site_id,
                                       organisation_id=office.organisation_id,
                                       )
        self.create_commit_item(commit_id, req_item_id, pack_id, quantity=1)

        CommitModel.commit_onaccept(self.make_form(id=commit_id,
                                                   site_id=office.site_id,
                                                   ))

        commit = db(s3db.req_commit.id == commit_id).select(s3db.req_commit.type,
                                                            limitby=(0, 1),
                                                            ).first()
        self.assertEqual(commit.type, 1)

        req = db(s3db.req_req.id == req_id).select(s3db.req_req.commit_status,
                                                   limitby=(0, 1),
                                                   ).first()
        self.assertEqual(req.commit_status, REQ_STATUS_PARTIAL)

    # -------------------------------------------------------------------------
    def testCommitOndeleteRecalculatesRequestWithoutDeletedCommit(self):
        """Deleted commits must no longer count towards committed quantities"""

        db = current.db
        s3db = current.s3db

        office = self.create_office()
        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id, quantity=1)

        req_id = self.create_request(office.site_id,
                                     req_type=1,
                                     commit_status=REQ_STATUS_NONE,
                                     )
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=2,
                                               )
        commit_id = self.create_commit(req_id,
                                       site_id=office.site_id,
                                       organisation_id=office.organisation_id,
                                       )
        self.create_commit_item(commit_id, req_item_id, pack_id, quantity=2)

        rtable = s3db.req_req
        req = db(rtable.id == req_id).select(rtable.id,
                                             rtable.type,
                                             rtable.commit_status,
                                             limitby=(0, 1),
                                             ).first()
        req_update_commit_quantities_and_status(req)

        req_item = db(s3db.req_req_item.id == req_item_id).select(s3db.req_req_item.quantity_commit,
                                                                  limitby=(0, 1),
                                                                  ).first()
        self.assertEqual(req_item.quantity_commit, 2)

        db(s3db.req_commit.id == commit_id).update(deleted=True,
                                                   deleted_fk='{"req_id": %s}' % req_id,
                                                   )
        CommitModel.commit_ondelete(Storage(id=commit_id))

        req_item = db(s3db.req_req_item.id == req_item_id).select(s3db.req_req_item.quantity_commit,
                                                                  limitby=(0, 1),
                                                                  ).first()
        self.assertEqual(req_item.quantity_commit, 0)

        req = db(rtable.id == req_id).select(rtable.commit_status,
                                             limitby=(0, 1),
                                             ).first()
        self.assertEqual(req.commit_status, REQ_STATUS_NONE)

    # -------------------------------------------------------------------------
    def testCommitItemCallbacksUpdateCommitStatus(self):
        """Commit item callbacks update request quantities on add and delete"""

        db = current.db
        s3db = current.s3db

        office = self.create_office()
        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id, quantity=1)

        req_id = self.create_request(office.site_id,
                                     req_type=1,
                                     commit_status=REQ_STATUS_NONE,
                                     )
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=1,
                                               )
        commit_id = self.create_commit(req_id,
                                       site_id=office.site_id,
                                       organisation_id=office.organisation_id,
                                       )
        commit_item_id = self.create_commit_item(commit_id,
                                                 req_item_id,
                                                 pack_id,
                                                 quantity=1,
                                                 )

        CommitItemModel.commit_item_onaccept(self.make_form(id=commit_item_id))

        req_item = db(s3db.req_req_item.id == req_item_id).select(s3db.req_req_item.quantity_commit,
                                                                  limitby=(0, 1),
                                                                  ).first()
        self.assertEqual(req_item.quantity_commit, 1)

        db(s3db.req_commit_item.id == commit_item_id).update(deleted=True,
                                                             deleted_fk='{"commit_id": %s}' % commit_id,
                                                             )
        CommitItemModel.commit_item_ondelete(Storage(id=commit_item_id))

        req_item = db(s3db.req_req_item.id == req_item_id).select(s3db.req_req_item.quantity_commit,
                                                                  limitby=(0, 1),
                                                                  ).first()
        self.assertEqual(req_item.quantity_commit, 0)


# =============================================================================
class ReqHelperTests(SupplyChainTestCase):
    """Tests for miscellaneous request helper functions"""

    MISSING = object()

    # -------------------------------------------------------------------------
    def _capture_req_form_state(self):
        """Capture mutable request form state for restoration"""

        s3db = current.s3db
        # Ensure the request models are loaded before we inspect mutable fields
        _ = s3db.req_req
        _ = s3db.req_req_item
        table = current.db.req_req
        item_table = s3db.req_req_item
        s3 = current.response.s3

        field_state = {}
        for fieldname in ("req_ref",
                          "commit_status",
                          "transit_status",
                          "fulfil_status",
                          "workflow_status",
                          "cancel",
                          "closed",
                          "date_recv",
                          "recv_by_id",
                          "requester_id",
                          "site_id",
                          "date_required_until",
                          ):
            field = table[fieldname]
            field_state[fieldname] = Storage(readable=getattr(field, "readable", None),
                                             writable=getattr(field, "writable", None),
                                             widget=getattr(field, "widget", None),
                                             comment=getattr(field, "comment", None),
                                             )

        return Storage(field_state=field_state,
                       item_widget=item_table.item_id.widget,
                       type_default=table.type.default,
                       submit_button=s3.crud.submit_button,
                       jquery_ready=list(s3.jquery_ready),
                       js_global=list(s3.js_global),
                       scripts=list(s3.scripts),
                       crud_form=s3db.get_config("req_req", "crud_form"),
                       )

    # -------------------------------------------------------------------------
    def _restore_req_form_state(self, state):
        """Restore mutable request form state after form helper tests"""

        s3db = current.s3db
        table = current.db.req_req
        item_table = s3db.req_req_item
        s3 = current.response.s3

        for fieldname, attributes in state.field_state.items():
            field = table[fieldname]
            field.readable = attributes.readable
            field.writable = attributes.writable
            field.widget = attributes.widget
            field.comment = attributes.comment

        item_table.item_id.widget = state.item_widget
        table.type.default = state.type_default

        s3.crud.submit_button = state.submit_button
        s3.jquery_ready = state.jquery_ready
        s3.js_global = state.js_global
        s3.scripts = state.scripts

        s3db.configure("req_req", crud_form=state.crud_form)

    # -------------------------------------------------------------------------
    def _capture_req_settings(self, *keys):
        """Capture request deployment settings for temporary overrides"""

        req_settings = current.deployment_settings.req
        missing = self.MISSING

        return {key: req_settings[key] if key in req_settings else missing
                for key in keys}

    # -------------------------------------------------------------------------
    def _restore_req_settings(self, saved):
        """Restore request deployment settings after temporary overrides"""

        req_settings = current.deployment_settings.req
        missing = self.MISSING

        for key, value in saved.items():
            if value is missing:
                req_settings.pop(key, None)
            else:
                req_settings[key] = value

    # -------------------------------------------------------------------------
    def testReqTabsHonoursPermissionsAndSettings(self):
        """Request tabs include requests, match and commit where permitted"""

        settings = current.deployment_settings
        auth = current.auth

        # Expose all optional tabs for this scenario
        saved_inv_tabs = settings.get_org_site_inv_req_tabs
        saved_has_module = settings.has_module
        saved_use_commit = settings.get_req_use_commit
        saved_permission = auth.s3_has_permission

        settings.get_org_site_inv_req_tabs = lambda: True
        settings.has_module = lambda module: module == "req"
        settings.get_req_use_commit = lambda: True
        auth.s3_has_permission = lambda *args, **kwargs: True

        try:
            tabs = req_tabs(Storage(controller="req"), match=True)
        finally:
            settings.get_org_site_inv_req_tabs = saved_inv_tabs
            settings.has_module = saved_has_module
            settings.get_req_use_commit = saved_use_commit
            auth.s3_has_permission = saved_permission

        # Verify the visible tab order
        self.assertEqual([item[1] for item in tabs],
                         ["req", "req_match/", "commit"])

    # -------------------------------------------------------------------------
    def testReqDetailsAndDriversRepresentJoinedRows(self):
        """Request detail helpers aggregate item lines and shipment drivers"""

        # Create a request with one item line and one outbound shipment
        office = self.create_office()
        item_id = self.create_supply_item(name="Family Tent")
        pack_id = self.create_item_pack(item_id, quantity=1)

        req_id = self.create_request(office.site_id,
                                     req_type=1,
                                     req_ref="REQ-DETAIL-001",
                                     )
        self.create_request_item(req_id,
                                 item_id,
                                 pack_id,
                                 quantity=3,
                                 )
        self.create_send(office.site_id,
                         req_ref="REQ-DETAIL-001",
                         driver_name="Jan",
                         driver_phone="123",
                         vehicle_plate_no="WX1234",
                         )

        row = Storage(req_req=Storage(id=req_id,
                                      type=1,
                                      req_ref="REQ-DETAIL-001",
                                      ))

        # Verify both helper representations use the joined data
        self.assertEqual(req_req_details(row), "3 Family Tent")
        self.assertEqual(req_req_drivers(row), "Jan 123 WX1234")

    # -------------------------------------------------------------------------
    def testReqAddFromTemplateCopiesItemLines(self):
        """Recurring request helper copies request items from the template"""

        db = current.db
        s3db = current.s3db
        settings = current.deployment_settings

        # Build a template request with one item line
        office = self.create_office()
        item_id = self.create_supply_item(name="Blanket")
        pack_id = self.create_item_pack(item_id, quantity=1)

        template_id = self.create_request(office.site_id,
                                          req_type=1,
                                          requester_id=self.create_person(last_name="Template"),
                                          )
        self.create_request_item(template_id,
                                 item_id,
                                 pack_id,
                                 quantity=6,
                                 )

        saved = settings.get_req_use_req_number
        settings.get_req_use_req_number = lambda: False
        try:
            new_req_id = req_add_from_template(template_id)
        finally:
            settings.get_req_use_req_number = saved

        self.assertNotEqual(new_req_id, template_id)

        # Verify the template item line has been copied to the new request
        ritable = s3db.req_req_item
        items = db(ritable.req_id == new_req_id).select(ritable.item_id,
                                                        ritable.item_pack_id,
                                                        ritable.quantity,
                                                        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items.first().item_id, item_id)
        self.assertEqual(items.first().item_pack_id, pack_id)
        self.assertEqual(items.first().quantity, 6)

    # -------------------------------------------------------------------------
    def testReqApproverHelpersResolveDirectApprovers(self):
        """Approver lookup recognises direct site approvers"""

        # Create one direct approver for the office entity
        person_id = self.create_person(last_name="Matcher")
        office = self.create_office()
        self.create_approver(office.pe_id,
                             person_id,
                             title="Warehouse Lead",
                             matcher=True,
                             )

        auth = current.auth
        s3db = current.s3db

        saved_person = auth.s3_logged_in_person
        saved_desc = s3db.pr_get_descendants
        saved_anc = s3db.pr_get_ancestors

        auth.s3_logged_in_person = lambda: person_id
        s3db.pr_get_descendants = lambda pe_ids, entity_types=None: []
        s3db.pr_get_ancestors = lambda pe_id: []

        try:
            self.assertTrue(req_is_approver(office.site_id))
            approvers = req_approvers(office.site_id)
        finally:
            auth.s3_logged_in_person = saved_person
            s3db.pr_get_descendants = saved_desc
            s3db.pr_get_ancestors = saved_anc

        # Verify both the boolean helper and the detailed lookup
        self.assertIn(person_id, approvers)
        self.assertEqual(approvers[person_id]["title"], "Warehouse Lead")
        self.assertTrue(approvers[person_id]["matcher"])

    # -------------------------------------------------------------------------
    def testReqHideQuantitiesHonoursDeploymentSetting(self):
        """Quantity status fields are hidden when item quantities are read-only"""

        settings = current.deployment_settings
        saved = settings.get_req_item_quantities_writable
        settings.get_req_item_quantities_writable = lambda: False

        table = Storage(quantity_commit=Storage(readable=True, writable=True),
                        quantity_transit=Storage(readable=True, writable=True),
                        quantity_fulfil=Storage(readable=True, writable=True),
                        )
        try:
            req_hide_quantities(table)
        finally:
            settings.get_req_item_quantities_writable = saved

        self.assertFalse(table.quantity_commit.readable)
        self.assertFalse(table.quantity_commit.writable)
        self.assertFalse(table.quantity_transit.readable)
        self.assertFalse(table.quantity_transit.writable)
        self.assertFalse(table.quantity_fulfil.readable)
        self.assertFalse(table.quantity_fulfil.writable)

    # -------------------------------------------------------------------------
    def testReqCreateFormModsConfiguresCreatePageHelpers(self):
        """Create-form setup hides status fields and injects the request helper JS"""

        settings = current.deployment_settings
        request = current.request
        s3 = current.response.s3
        s3db = current.s3db
        _ = s3db.req_req
        table = current.db.req_req

        # Preserve mutable form state before the helper mutates shared objects
        state = self._capture_req_form_state()
        saved_settings = self._capture_req_settings("inline_forms",
                                                    "requester_from_site",
                                                    "req_type",
                                                    )
        saved_get_vars = request._get_vars

        settings.req.inline_forms = False
        settings.req.requester_from_site = True
        settings.req.req_type = ["Items", "People"]
        request._get_vars = Storage()
        s3.crud.submit_button = None
        table.type.default = 1
        s3.jquery_ready = []
        s3.js_global = []
        s3.scripts = []

        try:
            req_create_form_mods()
        finally:
            self._restore_req_settings(saved_settings)
            request._get_vars = saved_get_vars

        try:
            # Verify the create page hides status-only fields and customises the UI
            self.assertEqual(str(s3.crud.submit_button), str(current.T("Save and add Items")))
            self.assertFalse(table.req_ref.readable)
            self.assertFalse(table.commit_status.readable)
            self.assertFalse(table.transit_status.readable)
            self.assertFalse(table.fulfil_status.readable)
            self.assertFalse(table.workflow_status.readable)
            self.assertFalse(table.cancel.readable)
            self.assertFalse(table.closed.readable)
            self.assertFalse(table.date_recv.readable)
            self.assertFalse(table.recv_by_id.readable)
            self.assertTrue(table.date_required_until.writable)
            self.assertIsNone(table.requester_id.widget)
            self.assertIsNotNone(table.requester_id.comment)

            # Check the client-side helpers added by the prep function
            self.assertTrue(any("staff_for_site" in script for script in s3.jquery_ready))
            self.assertTrue(any("req_details_mandatory" in script for script in s3.js_global))
            self.assertEqual(s3.scripts,
                             ["/%s/static/scripts/S3/s3.req_create_variable.js" %
                              request.application])
        finally:
            self._restore_req_form_state(state)

    # -------------------------------------------------------------------------
    def testReqCreateFormModsUsesTypedCreateScript(self):
        """Typed create requests use the simplified create script"""

        settings = current.deployment_settings
        request = current.request
        s3 = current.response.s3

        # Preserve the mutable response/request state
        state = self._capture_req_form_state()
        saved_settings = self._capture_req_settings("inline_forms",
                                                    "requester_from_site",
                                                    "req_type",
                                                    )
        saved_get_vars = request._get_vars

        settings.req.inline_forms = False
        settings.req.requester_from_site = False
        settings.req.req_type = ["Items"]
        request._get_vars = Storage(type="1")
        s3.scripts = []

        try:
            req_create_form_mods()
            self.assertEqual(s3.scripts,
                             ["/%s/static/scripts/S3/s3.req_create.js" %
                             request.application])
        finally:
            self._restore_req_settings(saved_settings)
            request._get_vars = saved_get_vars
            self._restore_req_form_state(state)

    # -------------------------------------------------------------------------
    def testReqInlineFormConfiguresItemCreateForm(self):
        """Inline item requests configure the expected fields and client-side filters"""

        settings = current.deployment_settings
        s3 = current.response.s3
        s3db = current.s3db
        _ = s3db.req_req
        _ = s3db.req_req_item
        table = current.db.req_req

        # Preserve mutable config because req_inline_form rewrites it in-place
        state = self._capture_req_form_state()
        saved_settings = self._capture_req_settings("requester_from_site",
                                                    "items_ask_purpose",
                                                    )

        settings.req.requester_from_site = True
        settings.req.items_ask_purpose = True
        s3.jquery_ready = []
        s3.crud.submit_button = "Temporary"

        try:
            req_inline_form(1, "create")

            crud_form = s3db.get_config("req_req", "crud_form")
            selectors = [element.selector for element in crud_form.elements]

            # Verify the create form layout for item requests
            self.assertEqual(selectors,
                             ["site_id",
                              "is_template",
                              "requester_id",
                              "date",
                              "priority",
                              "date_required",
                              "req_item",
                              "purpose",
                              "comments",
                              ])
            self.assertIsNone(s3db.req_req_item.item_id.widget)
            self.assertIsNotNone(table.requester_id.comment)
            self.assertIsNotNone(table.site_id.comment)

            # Verify both dynamic filter widgets are attached
            self.assertTrue(any("lookupResource':'item_pack" in script for script in s3.jquery_ready))
            self.assertTrue(any("staff_for_site" in script for script in s3.jquery_ready))
            self.assertEqual(str(s3.crud.submit_button), str(current.T("Save")))
        finally:
            self._restore_req_settings(saved_settings)
            self._restore_req_form_state(state)

    # -------------------------------------------------------------------------
    def testReqInlineFormConfiguresSkillUpdateForm(self):
        """Inline skill requests add status fields and request numbers on update"""

        settings = current.deployment_settings
        s3 = current.response.s3
        s3db = current.s3db
        _ = s3db.req_req
        table = current.db.req_req

        # Preserve mutable config because this branch rewrites several fields
        state = self._capture_req_form_state()
        saved_settings = self._capture_req_settings("status_writable",
                                                    "show_quantity_transit",
                                                    "use_commit",
                                                    "requester_from_site",
                                                    "use_req_number",
                                                    "generate_req_number",
                                                    )

        settings.req.status_writable = True
        settings.req.show_quantity_transit = True
        settings.req.use_commit = True
        settings.req.requester_from_site = True
        settings.req.use_req_number = True
        settings.req.generate_req_number = False
        s3.jquery_ready = []
        s3.crud.submit_button = "Temporary"

        try:
            req_inline_form(3, "update")

            crud_form = s3db.get_config("req_req", "crud_form")
            selectors = [element.selector for element in crud_form.elements]

            # Verify the update form includes request number and status tracking
            self.assertEqual(selectors,
                             ["req_ref",
                              "site_id",
                              "requester_id",
                              "date",
                              "priority",
                              "date_required",
                              "date_required_until",
                              "purpose",
                              "req_skill",
                              "date_recv",
                              "commit_status",
                              "transit_status",
                              "fulfil_status",
                              "comments",
                              ])
            self.assertIsNotNone(table.requester_id.comment)
            self.assertIsNotNone(table.site_id.comment)
            self.assertTrue(any("staff_for_site" in script for script in s3.jquery_ready))
            self.assertEqual(str(s3.crud.submit_button), str(current.T("Save")))
        finally:
            self._restore_req_settings(saved_settings)
            self._restore_req_form_state(state)


# =============================================================================
class ReqSendCommitTests(SupplyChainTestCase):
    """Tests for commitment-to-shipment conversion"""

    # -------------------------------------------------------------------------
    def testReqSendCommitCreatesShipmentAndTrackItems(self):
        """req_send_commit creates a shipment from all committed items"""

        db = current.db
        s3db = current.s3db

        # Create a committed request with one line item
        office = self.create_office()
        requester_id = self.create_person(last_name="Requester")
        committer_id = self.create_person(last_name="Committer")
        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id, quantity=5)

        req_id = self.create_request(office.site_id,
                                     req_ref="REQ-SEND-001",
                                     requester_id=requester_id,
                                     )
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=3,
                                               )
        commit_id = self.create_commit(req_id,
                                       site_id=office.site_id,
                                       organisation_id=office.organisation_id,
                                       committer_id=committer_id,
                                       )
        self.create_commit_item(commit_id, req_item_id, pack_id, quantity=2)

        saved_args = list(current.request.args)
        saved_redirect = req_module.redirect
        saved_onaccept = s3db.inv_send_onaccept

        current.request.args = [commit_id]

        try:
            # Intercept the redirect because the workflow finishes in the controller
            req_module.redirect = lambda url: (_ for _ in ()).throw(RedirectIntercept(url))
            s3db.inv_send_onaccept = lambda form: None

            with self.assertRaises(RedirectIntercept):
                req_send_commit()
        finally:
            current.request.args = saved_args
            req_module.redirect = saved_redirect
            s3db.inv_send_onaccept = saved_onaccept

        # Verify the generated shipment header
        send_table = s3db.inv_send
        send = db(send_table.req_ref == "REQ-SEND-001").select(send_table.id,
                                                               send_table.site_id,
                                                               send_table.to_site_id,
                                                               send_table.sender_id,
                                                               send_table.recipient_id,
                                                               limitby=(0, 1),
                                                               ).first()
        self.assertIsNotNone(send)
        self.assertEqual(send.site_id, office.site_id)
        self.assertEqual(send.to_site_id, office.site_id)
        self.assertEqual(send.sender_id, committer_id)
        self.assertEqual(send.recipient_id, requester_id)

        # Verify the committed line became one shipment tracking item
        track_table = s3db.inv_track_item
        rows = db(track_table.send_id == send.id).select(track_table.req_item_id,
                                                         track_table.item_id,
                                                         track_table.item_pack_id,
                                                         track_table.quantity,
                                                         track_table.recv_quantity,
                                                         )
        self.assertEqual(len(rows), 1)

        row = rows.first()
        self.assertEqual(row.req_item_id, req_item_id)
        self.assertEqual(row.item_id, item_id)
        self.assertEqual(row.item_pack_id, pack_id)
        self.assertEqual(row.quantity, 2)
        self.assertEqual(row.recv_quantity, 2)

    # -------------------------------------------------------------------------
    def testReqSendCommitRedirectsWithoutCommitId(self):
        """Missing commit IDs trigger a controlled redirect"""

        saved_args = list(current.request.args)
        saved_redirect = req_module.redirect
        current.request.args = []

        try:
            req_module.redirect = lambda url: (_ for _ in ()).throw(RedirectIntercept(url))
            with self.assertRaises(RedirectIntercept) as redirect:
                req_send_commit()
        finally:
            current.request.args = saved_args
            req_module.redirect = saved_redirect

        self.assertTrue(str(redirect.exception.url).endswith("/req/commit"))

    # -------------------------------------------------------------------------
    def testReqSendCommitRedirectsWhenCommitDoesNotExist(self):
        """Unknown commit IDs must not crash with AttributeError"""

        saved_args = list(current.request.args)
        saved_redirect = req_module.redirect
        current.request.args = ["999999"]

        try:
            req_module.redirect = lambda url: (_ for _ in ()).throw(RedirectIntercept(url))
            with self.assertRaises(RedirectIntercept) as redirect:
                req_send_commit()
        finally:
            current.request.args = saved_args
            req_module.redirect = saved_redirect

        self.assertTrue(str(redirect.exception.url).endswith("/req/commit"))

    # -------------------------------------------------------------------------
    def testReqSendCommitRedirectsWhenCommitIsDeleted(self):
        """Deleted commits are treated as unavailable and redirect cleanly"""

        # Mark the commit deleted to exercise the unavailable-record branch
        office = self.create_office()
        req_id = self.create_request(office.site_id)
        commit_id = self.create_commit(req_id,
                                       site_id=office.site_id,
                                       organisation_id=office.organisation_id,
                                       )
        current.db(current.s3db.req_commit.id == commit_id).update(deleted=True)

        saved_args = list(current.request.args)
        saved_redirect = req_module.redirect
        current.request.args = [commit_id]

        try:
            req_module.redirect = lambda url: (_ for _ in ()).throw(RedirectIntercept(url))
            with self.assertRaises(RedirectIntercept) as redirect:
                req_send_commit()
        finally:
            current.request.args = saved_args
            req_module.redirect = saved_redirect

        self.assertTrue(str(redirect.exception.url).endswith("/req/commit"))

    # -------------------------------------------------------------------------
    def testReqSendCommitCreatesShipmentWithoutTrackItemsForEmptyCommit(self):
        """Commits without items still redirect cleanly after creating a shipment"""

        db = current.db
        s3db = current.s3db

        # Create an empty commit to cover the no-items branch
        office = self.create_office()
        requester_id = self.create_person(last_name="Requester")
        committer_id = self.create_person(last_name="Committer")
        req_id = self.create_request(office.site_id,
                                     req_ref="REQ-EMPTY-001",
                                     requester_id=requester_id,
                                     )
        commit_id = self.create_commit(req_id,
                                       site_id=office.site_id,
                                       organisation_id=office.organisation_id,
                                       committer_id=committer_id,
                                       )

        saved_args = list(current.request.args)
        saved_redirect = req_module.redirect
        saved_onaccept = s3db.inv_send_onaccept
        current.request.args = [commit_id]

        try:
            req_module.redirect = lambda url: (_ for _ in ()).throw(RedirectIntercept(url))
            s3db.inv_send_onaccept = lambda form: None
            with self.assertRaises(RedirectIntercept):
                req_send_commit()
        finally:
            current.request.args = saved_args
            req_module.redirect = saved_redirect
            s3db.inv_send_onaccept = saved_onaccept

        # The shipment should exist, but without tracking items
        send = db(s3db.inv_send.req_ref == "REQ-EMPTY-001").select(s3db.inv_send.id,
                                                                    limitby=(0, 1),
                                                                    ).first()
        self.assertIsNotNone(send)

        rows = db(s3db.inv_track_item.send_id == send.id).select(s3db.inv_track_item.id)
        self.assertEqual(len(rows), 0)


# =============================================================================
if __name__ == "__main__":

    run_suite(
        ReqRepresentationTests,
        ReqStatusTests,
        ReqCallbackTests,
        ReqHelperTests,
        ReqSendCommitTests,
    )

# END ========================================================================
