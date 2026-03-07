# REQ Unit Tests
#
# To run this script use:
# python web2py.py -S eden -M -R applications/eden/modules/unit_tests/s3db/req.py
#
import json
import unittest

import core
import datetime

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
                      req_rheader,
                      req_ref_represent,
                      req_send_commit,
                      req_tabs,
                      req_update_commit_quantities_and_status,
                      req_update_status,
                      )
from unit_tests import run_suite
from unit_tests.s3db.helpers import ControllerRedirect, SupplyChainTestCase


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

    # -------------------------------------------------------------------------
    def testQuantityRepresentersExposeAjaxExpanderForReadOnlyQuantities(self):
        """Quantity representers add AJAX expanders while request item quantities are read-only"""

        settings = current.deployment_settings
        saved_settings = settings.req.get("item_quantities_writable")

        settings.req.item_quantities_writable = False
        try:
            commit = RequestItemModel.req_qnty_commit_represent(4)
            transit = RequestItemModel.req_qnty_transit_represent(2)
            fulfil = RequestItemModel.req_qnty_fulfil_represent(1, show_link=False)
        finally:
            settings.req.item_quantities_writable = saved_settings

        self.assertIn("ajax_more", str(commit))
        self.assertIn("ajax_more", str(transit))
        self.assertEqual(fulfil, 1)

        settings.req.item_quantities_writable = True
        try:
            plain = RequestItemModel.req_qnty_commit_represent(3)
        finally:
            settings.req.item_quantities_writable = saved_settings

        self.assertEqual(plain, 3)


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

    # -------------------------------------------------------------------------
    def testReqItemDuplicateMatchesDirectAndDeferredReferences(self):
        """Request item deduplication resolves both direct and deferred import references"""

        office = self.create_office()
        item_id = self.create_supply_item(name="Hygiene Kit")
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(office.site_id)
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=2,
                                               )

        update = Storage(UPDATE="update")
        direct = Storage(table=current.s3db.req_req_item,
                         references=[Storage(entry=Storage(tablename="req_req",
                                                           id=req_id,
                                                           )),
                                     Storage(entry=Storage(tablename="supply_item",
                                                           id=item_id,
                                                           )),
                                     ],
                         METHOD=update,
                         method=None,
                         id=None,
                         )
        RequestItemModel.req_item_duplicate(direct)

        deferred = Storage(table=current.s3db.req_req_item,
                           references=[Storage(entry=Storage(tablename="req_req",
                                                             id=None,
                                                             item_id="REQREF",
                                                             )),
                                       Storage(entry=Storage(tablename="supply_item",
                                                             id=None,
                                                             item_id="ITEMREF",
                                                             )),
                                       ],
                           job=type("Job", (), {"items": {"REQREF": Storage(id=req_id),
                                                          "ITEMREF": Storage(id=item_id),
                                                          }})(),
                           METHOD=update,
                           method=None,
                           id=None,
                           )
        RequestItemModel.req_item_duplicate(deferred)

        self.assertEqual(direct.id, req_item_id)
        self.assertEqual(direct.method, update.UPDATE)
        self.assertEqual(deferred.id, req_item_id)
        self.assertEqual(deferred.method, update.UPDATE)


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

    # -------------------------------------------------------------------------
    def testReqRheaderShowsDraftWorkflowTabsAndSubmitAction(self):
        """Request rheader exposes item tabs and submit action for draft workflows"""

        db = current.db
        s3db = current.s3db
        auth = current.auth
        response_s3 = current.response.s3
        settings = current.deployment_settings

        office = self.create_office()
        requester_id = self.create_person(last_name="Requester")
        item_id = self.create_supply_item(name="Cooking Set")
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(office.site_id,
                                     req_ref="REQ-HDR-001",
                                     requester_id=requester_id,
                                     transit_status=REQ_STATUS_PARTIAL,
                                     workflow_status=1,
                                     purpose="Shelter support",
                                     comments="Urgent",
                                     is_template=False,
                                     )
        self.create_request_item(req_id,
                                 item_id,
                                 pack_id,
                                 quantity=2,
                                 )
        record = db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                      limitby=(0, 1),
                                                      ).first()

        saved_user = auth.user
        saved_settings = self._capture_req_settings("use_commit",
                                                    "workflow",
                                                    "multiple_req_items",
                                                    "commit_people",
                                                    "show_quantity_transit",
                                                    "use_req_number",
                                                    )
        saved_has_module = settings.has_module
        saved_logo = s3db.org_organisation_logo
        saved_tabs = req_rheader.__globals__["s3_rheader_tabs"]
        saved_footer = response_s3.rfooter
        saved_ready = list(response_s3.jquery_ready)

        auth.user = Storage(organisation_id=office.organisation_id,
                            site_id=office.site_id,
                            )
        settings.req.use_commit = True
        settings.req.workflow = True
        settings.req.multiple_req_items = True
        settings.req.commit_people = False
        settings.req.show_quantity_transit = True
        settings.req.use_req_number = True
        settings.has_module = lambda module: module == "inv"
        s3db.org_organisation_logo = lambda organisation_id: "LOGO"
        req_rheader.__globals__["s3_rheader_tabs"] = lambda r, tabs: \
            "REQ-TABS:%s" % ",".join(tab[1] or "" for tab in tabs)
        response_s3.rfooter = None
        response_s3.jquery_ready = []

        try:
            rheader = req_rheader(Storage(representation="html",
                                          record=record,
                                          name="req",
                                          table=s3db.req_req,
                                          component=None,
                                          component_name=None,
                                          component_id=None,
                                          ))
            footer = str(response_s3.rfooter)
            ready = list(response_s3.jquery_ready)
        finally:
            auth.user = saved_user
            self._restore_req_settings(saved_settings)
            settings.has_module = saved_has_module
            s3db.org_organisation_logo = saved_logo
            req_rheader.__globals__["s3_rheader_tabs"] = saved_tabs
            response_s3.rfooter = saved_footer
            response_s3.jquery_ready = saved_ready

        self.assertIn("req_item,document,commit,check", str(rheader))
        self.assertIn("Submit for Approval", footer)
        self.assertTrue(any("req-submit" in script for script in ready))
        self.assertIn("REQ-HDR-001", str(rheader))

    # -------------------------------------------------------------------------
    def testReqRheaderShowsApproveAndPrepareShipmentActions(self):
        """Request rheader exposes approve and prepare-shipment actions in the right states"""

        db = current.db
        s3db = current.s3db
        auth = current.auth
        response_s3 = current.response.s3
        settings = current.deployment_settings

        office = self.create_office()
        approver_id = self.create_person(last_name="Approver")
        self.create_approver(office.pe_id,
                             approver_id,
                             title="Request Approver",
                             )
        item_id = self.create_supply_item(name="Water Purifier")
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(office.site_id,
                                     req_ref="REQ-HDR-002",
                                     requester_id=approver_id,
                                     workflow_status=2,
                                     is_template=False,
                                     )
        self.create_request_item(req_id,
                                 item_id,
                                 pack_id,
                                 quantity=1,
                                 )
        record = db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                      limitby=(0, 1),
                                                      ).first()

        saved_user = auth.user
        saved_logged_in = auth.s3_logged_in_person
        saved_settings = self._capture_req_settings("use_commit",
                                                    "workflow",
                                                    "multiple_req_items",
                                                    "commit_people",
                                                    "use_req_number",
                                                    )
        saved_has_module = settings.has_module
        saved_descendants = s3db.pr_get_descendants
        saved_ancestors = s3db.pr_get_ancestors
        saved_tabs = req_rheader.__globals__["s3_rheader_tabs"]
        saved_footer = response_s3.rfooter
        saved_ready = list(response_s3.jquery_ready)

        auth.user = Storage(organisation_id=office.organisation_id,
                            site_id=office.site_id,
                            )
        auth.s3_logged_in_person = lambda: approver_id
        settings.req.use_commit = True
        settings.req.workflow = True
        settings.req.multiple_req_items = True
        settings.req.commit_people = False
        settings.req.use_req_number = True
        settings.has_module = lambda module: module == "inv"
        s3db.pr_get_descendants = lambda pe_ids, entity_types=None: []
        s3db.pr_get_ancestors = lambda pe_id: []
        req_rheader.__globals__["s3_rheader_tabs"] = lambda r, tabs: \
            "REQ-TABS:%s" % ",".join(tab[1] or "" for tab in tabs)
        response_s3.rfooter = None
        response_s3.jquery_ready = []

        try:
            req_rheader(Storage(representation="html",
                                record=record,
                                name="req",
                                table=s3db.req_req,
                                component=None,
                                component_name=None,
                                component_id=None,
                                ))
            approve_footer = str(response_s3.rfooter)

            response_s3.rfooter = None
            req_rheader(Storage(representation="html",
                                record=record,
                                name="req",
                                table=s3db.req_req,
                                component=Storage(name="commit"),
                                component_name="commit",
                                component_id=77,
                                ))
            prepare_footer = str(response_s3.rfooter)
        finally:
            auth.user = saved_user
            auth.s3_logged_in_person = saved_logged_in
            self._restore_req_settings(saved_settings)
            settings.has_module = saved_has_module
            s3db.pr_get_descendants = saved_descendants
            s3db.pr_get_ancestors = saved_ancestors
            req_rheader.__globals__["s3_rheader_tabs"] = saved_tabs
            response_s3.rfooter = saved_footer
            response_s3.jquery_ready = saved_ready

        self.assertIn("Approve", approve_footer)
        self.assertIn("Prepare Shipment", prepare_footer)

    # -------------------------------------------------------------------------
    def testReqRheaderBuildsNeedHeader(self):
        """Need rheaders expose the expected summary tabs"""

        table = Storage(location_id=Storage(label="Location",
                                            represent=lambda value: "Need Location",
                                            ))
        record = Storage(location_id=1)

        saved_tabs = req_rheader.__globals__["s3_rheader_tabs"]
        req_rheader.__globals__["s3_rheader_tabs"] = lambda r, tabs: \
            "NEED-TABS:%s" % ",".join(tab[1] or "" for tab in tabs)
        try:
            rheader = req_rheader(Storage(representation="html",
                                          record=record,
                                          name="need",
                                          table=table,
                                          ))
        finally:
            req_rheader.__globals__["s3_rheader_tabs"] = saved_tabs

        self.assertIn("Need Location", str(rheader))
        self.assertIn("NEED-TABS:,demographic,need_item,need_skill,tag", str(rheader))


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
class ReqWorkflowMethodTests(SupplyChainTestCase):
    """Tests for request workflow helper methods"""

    # -------------------------------------------------------------------------
    def testReqCopyAllDuplicatesItemRequests(self):
        """req_copy_all duplicates item requests and refreshes expired due dates"""

        db = current.db
        s3db = current.s3db
        settings = current.deployment_settings

        # Build an item request with one line and an overdue required date
        office = self.create_office()
        requester_id = self.create_person(last_name="Copy Requester")
        item_id = self.create_supply_item(name="Copy Item")
        pack_id = self.create_item_pack(item_id, quantity=2)
        req_id = self.create_request(office.site_id,
                                     req_ref="REQ-COPY-OLD",
                                     requester_id=requester_id,
                                     priority=3,
                                     purpose="Restock",
                                     transport_req=True,
                                     security_req=True,
                                     comments="Copy me",
                                     date_required=current.request.now - datetime.timedelta(days=2),
                                     )
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=4,
                                               )
        db(s3db.req_req_item.id == req_item_id).update(pack_value=7.5,
                                                       currency="USD",
                                                       site_id=office.site_id,
                                                       comments="Line note",
                                                       )

        record = db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                      limitby=(0, 1),
                                                      ).first()

        saved_redirect = req_module.redirect
        saved_use_number = settings.get_req_use_req_number
        saved_shipping_code = s3db.supply_get_shipping_code

        try:
            # Generate a deterministic new request reference and intercept the redirect
            settings.get_req_use_req_number = lambda: True
            s3db.supply_get_shipping_code = lambda *args, **kwargs: "REQ-COPY-NEW"
            req_module.redirect = lambda url: (_ for _ in ()).throw(RedirectIntercept(url))

            with self.assertRaises(RedirectIntercept) as redirect:
                RequestModel.req_copy_all(Storage(record=record))
        finally:
            req_module.redirect = saved_redirect
            settings.get_req_use_req_number = saved_use_number
            s3db.supply_get_shipping_code = saved_shipping_code

        # Verify the copied request header and its duplicated item line
        new_req = db((s3db.req_req.id != req_id) &
                     (s3db.req_req.req_ref == "REQ-COPY-NEW")).select(s3db.req_req.ALL,
                                                                      limitby=(0, 1),
                                                                      ).first()
        self.assertIsNotNone(new_req)
        self.assertIn("/req/%s/update" % new_req.id, str(redirect.exception.url))
        self.assertEqual(new_req.site_id, office.site_id)
        self.assertEqual(new_req.requester_id, requester_id)
        self.assertEqual(new_req.comments, "Copy me")
        self.assertEqual(new_req.date_required.date(),
                         (current.request.now + datetime.timedelta(days=14)).date())

        new_item = db(s3db.req_req_item.req_id == new_req.id).select(s3db.req_req_item.ALL,
                                                                     limitby=(0, 1),
                                                                     ).first()
        self.assertIsNotNone(new_item)
        self.assertEqual(new_item.item_id, item_id)
        self.assertEqual(new_item.item_pack_id, pack_id)
        self.assertEqual(new_item.quantity, 4)
        self.assertEqual(new_item.pack_value, 7.5)
        self.assertEqual(new_item.currency, "USD")
        self.assertEqual(new_item.site_id, office.site_id)
        self.assertEqual(new_item.comments, "Line note")

    # -------------------------------------------------------------------------
    def testReqCopyAllDuplicatesSkillRequests(self):
        """req_copy_all duplicates people/skill requests and their requested skills"""

        db = current.db
        s3db = current.s3db
        settings = current.deployment_settings

        # Build a skills request with one requested skill
        office = self.create_office()
        skill_id = self.create_skill(name="Nurse")
        req_id = self.create_request(office.site_id,
                                     req_type=3,
                                     purpose="Need a nurse",
                                     )
        req_skill_id = self.create_request_skill(req_id,
                                                 skill_ids=[skill_id],
                                                 quantity=2,
                                                 site_id=office.site_id,
                                                 )
        db(s3db.req_req_skill.id == req_skill_id).update(comments="Skill note")

        record = db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                      limitby=(0, 1),
                                                      ).first()

        saved_redirect = req_module.redirect
        saved_use_number = settings.get_req_use_req_number

        try:
            # Skills requests should still duplicate cleanly without request numbers
            settings.get_req_use_req_number = lambda: False
            req_module.redirect = lambda url: (_ for _ in ()).throw(RedirectIntercept(url))

            with self.assertRaises(RedirectIntercept):
                RequestModel.req_copy_all(Storage(record=record))
        finally:
            req_module.redirect = saved_redirect
            settings.get_req_use_req_number = saved_use_number

        new_req = db((s3db.req_req.id != req_id) &
                     (s3db.req_req.type == 3)).select(s3db.req_req.ALL,
                                                      orderby=~s3db.req_req.id,
                                                      limitby=(0, 1),
                                                      ).first()
        self.assertIsNotNone(new_req)

        new_skill = db(s3db.req_req_skill.req_id == new_req.id).select(s3db.req_req_skill.ALL,
                                                                       limitby=(0, 1),
                                                                       ).first()
        self.assertIsNotNone(new_skill)
        self.assertEqual(new_skill.skill_id, [skill_id])
        self.assertEqual(new_skill.quantity, 2)
        self.assertEqual(new_skill.site_id, office.site_id)
        self.assertEqual(new_skill.comments, "Skill note")

    # -------------------------------------------------------------------------
    def testReqCommitAllCreatesItemCommitAndAssignRedirect(self):
        """req_commit_all creates item commitments and can redirect into assign workflow"""

        db = current.db
        s3db = current.s3db

        # Create one outstanding item request
        office = self.create_office()
        item_id = self.create_supply_item(name="Commit Item")
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(office.site_id,
                                     req_type=1,
                                     commit_status=REQ_STATUS_NONE,
                                     )
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=3,
                                               )
        db(s3db.req_req_item.id == req_item_id).update(comments="Commit note")

        record = db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                      limitby=(0, 1),
                                                      ).first()

        saved_redirect = req_module.redirect
        try:
            # Commit all requested items and branch into the assignment workflow
            req_module.redirect = lambda url: (_ for _ in ()).throw(RedirectIntercept(url))
            with self.assertRaises(RedirectIntercept) as redirect:
                RequestModel.req_commit_all(Storage(record=record,
                                                   id=req_id,
                                                   args=["assign"],
                                                   ))
        finally:
            req_module.redirect = saved_redirect

        commit = db(s3db.req_commit.req_id == req_id).select(s3db.req_commit.id,
                                                             s3db.req_commit.type,
                                                             limitby=(0, 1),
                                                             ).first()
        self.assertIsNotNone(commit)
        self.assertEqual(commit.type, 1)
        self.assertIn("/commit/%s/assign" % commit.id, str(redirect.exception.url))

        commit_item = db(s3db.req_commit_item.commit_id == commit.id).select(s3db.req_commit_item.ALL,
                                                                             limitby=(0, 1),
                                                                             ).first()
        self.assertIsNotNone(commit_item)
        self.assertEqual(commit_item.req_item_id, req_item_id)
        self.assertEqual(commit_item.quantity, 3)
        self.assertEqual(commit_item.comments, "Commit note")

        req_item = db(s3db.req_req_item.id == req_item_id).select(s3db.req_req_item.quantity_commit,
                                                                  limitby=(0, 1),
                                                                  ).first()
        req = db(s3db.req_req.id == req_id).select(s3db.req_req.commit_status,
                                                   limitby=(0, 1),
                                                   ).first()
        self.assertEqual(req_item.quantity_commit, 3)
        self.assertEqual(req.commit_status, REQ_STATUS_COMPLETE)

    # -------------------------------------------------------------------------
    def testReqCommitAllCreatesSkillCommitAndSendRedirect(self):
        """req_commit_all creates skill commitments and can redirect to shipment creation"""

        db = current.db
        s3db = current.s3db

        # Create one requested skill set
        office = self.create_office()
        skill_id = self.create_skill(name="Paramedic")
        req_id = self.create_request(office.site_id,
                                     req_type=3,
                                     commit_status=REQ_STATUS_NONE,
                                     )
        req_skill_id = self.create_request_skill(req_id,
                                                 skill_ids=[skill_id],
                                                 quantity=2,
                                                 )
        db(s3db.req_req_skill.id == req_skill_id).update(comments="Skill commit")

        record = db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                      limitby=(0, 1),
                                                      ).first()

        saved_redirect = req_module.redirect
        try:
            # People commitments can continue directly into the send workflow
            req_module.redirect = lambda url: (_ for _ in ()).throw(RedirectIntercept(url))
            with self.assertRaises(RedirectIntercept) as redirect:
                RequestModel.req_commit_all(Storage(record=record,
                                                   id=req_id,
                                                   args=["send"],
                                                   ))
        finally:
            req_module.redirect = saved_redirect

        commit = db(s3db.req_commit.req_id == req_id).select(s3db.req_commit.id,
                                                             s3db.req_commit.type,
                                                             limitby=(0, 1),
                                                             ).first()
        self.assertIsNotNone(commit)
        self.assertEqual(commit.type, 3)
        self.assertIn("/send_commit/%s" % commit.id, str(redirect.exception.url))

        commit_skill = db(s3db.req_commit_skill.commit_id == commit.id).select(s3db.req_commit_skill.ALL,
                                                                               limitby=(0, 1),
                                                                               ).first()
        self.assertIsNotNone(commit_skill)
        self.assertEqual(commit_skill.skill_id, [skill_id])
        self.assertEqual(commit_skill.quantity, 2)
        self.assertEqual(commit_skill.comments, "Skill commit")

        req_skill = db(s3db.req_req_skill.id == req_skill_id).select(s3db.req_req_skill.quantity_commit,
                                                                     limitby=(0, 1),
                                                                     ).first()
        req = db(s3db.req_req.id == req_id).select(s3db.req_req.commit_status,
                                                   limitby=(0, 1),
                                                   ).first()
        self.assertEqual(req_skill.quantity_commit, 2)
        self.assertEqual(req.commit_status, REQ_STATUS_COMPLETE)

    # -------------------------------------------------------------------------
    def testReqCommitAllRedirectsToExistingCommit(self):
        """req_commit_all redirects to an existing commitment instead of creating another one"""

        db = current.db
        s3db = current.s3db

        # Existing commitments must be reused rather than duplicated
        office = self.create_office()
        req_id = self.create_request(office.site_id)
        self.create_commit(req_id,
                           site_id=office.site_id,
                           organisation_id=office.organisation_id,
                           )
        record = db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                      limitby=(0, 1),
                                                      ).first()

        saved_redirect = req_module.redirect
        try:
            req_module.redirect = lambda url: (_ for _ in ()).throw(RedirectIntercept(url))
            with self.assertRaises(RedirectIntercept) as redirect:
                RequestModel.req_commit_all(Storage(record=record,
                                                   id=req_id,
                                                   args=[],
                                                   ))
        finally:
            req_module.redirect = saved_redirect

        self.assertIn("/req/%s/commit" % req_id, str(redirect.exception.url))
        self.assertEqual(db(s3db.req_commit.req_id == req_id).count(), 1)

    # -------------------------------------------------------------------------
    def testReqFormBuildsPdfExportForItemRequests(self):
        """req_form delegates supported request types to the PDF exporter with typed list fields"""

        s3db = current.s3db

        # Prepare one item request for PDF export
        office = self.create_office()
        req_id = self.create_request(office.site_id,
                                     req_type=1,
                                     req_ref="REQ-FORM-001",
                                     )
        record = current.db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                              limitby=(0, 1),
                                                              ).first()

        captured = {}
        saved_exporter = core.DataExporter.pdf

        try:
            # Capture the PDF export options without generating a real document
            core.DataExporter.pdf = lambda resource, **kwargs: captured.update(resource=resource,
                                                                               kwargs=kwargs,
                                                                               ) or "PDF"
            result = RequestModel.req_form(Storage(record=record,
                                                  resource="RESOURCE",
                                                  ))
        finally:
            core.DataExporter.pdf = saved_exporter

        self.assertEqual(result, "PDF")
        self.assertEqual(captured["resource"], "RESOURCE")
        self.assertEqual(captured["kwargs"]["pdf_componentname"], "req_item")
        self.assertEqual(captured["kwargs"]["pdf_filename"], "REQ-FORM-001")
        self.assertEqual(captured["kwargs"]["list_fields"],
                         ["item_id",
                          "item_pack_id",
                          "quantity",
                          "quantity_commit",
                          "quantity_transit",
                          "quantity_fulfil",
                          ])

    # -------------------------------------------------------------------------
    def testReqSubmitNotifiesApproversAndMarksRequestSubmitted(self):
        """req_submit looks up approvers, sends notifications and moves workflow to Submitted"""

        db = current.db
        s3db = current.s3db
        auth = current.auth

        # Create one draft request with one approver reachable by PE ID
        office = self.create_office(name="Submit Office")
        requester_id = self.create_person(last_name="Submit Requester")
        approver_id = self.create_person(last_name="Submit Approver")
        self.create_approver(office.pe_id, approver_id)
        self.create_user_for_person(approver_id, language="pl")

        req_id = self.create_request(office.site_id,
                                     req_ref="REQ-SUBMIT-001",
                                     requester_id=requester_id,
                                     workflow_status=1,
                                     )
        record = db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                      limitby=(0, 1),
                                                      ).first()

        sent = []
        saved_permission = auth.s3_has_permission
        saved_ancestors = s3db.pr_get_ancestors
        saved_sender = current.msg.send_by_pe_id
        saved_redirect = req_module.redirect

        current.session.error = None
        current.session.confirmation = None

        try:
            # Stub the permission, ancestor lookup and mail sender around the workflow
            auth.s3_has_permission = lambda *args, **kwargs: True
            s3db.pr_get_ancestors = lambda pe_id: []
            current.msg.send_by_pe_id = lambda pe_id, **kwargs: sent.append((pe_id, kwargs))
            req_module.redirect = lambda url: (_ for _ in ()).throw(RedirectIntercept(url))

            with self.assertRaises(RedirectIntercept) as redirect:
                RequestModel.req_submit(Storage(record=record,
                                               id=req_id,
                                               unauthorised=lambda: self.fail("submit unauthorised"),
                                               ))
        finally:
            auth.s3_has_permission = saved_permission
            s3db.pr_get_ancestors = saved_ancestors
            current.msg.send_by_pe_id = saved_sender
            req_module.redirect = saved_redirect

        # Verify the workflow state and the generated approval notification
        updated = db(s3db.req_req.id == req_id).select(s3db.req_req.workflow_status,
                                                       limitby=(0, 1),
                                                       ).first()
        approver_pe_id = db(s3db.pr_person.id == approver_id).select(s3db.pr_person.pe_id,
                                                                     limitby=(0, 1),
                                                                     ).first().pe_id
        self.assertEqual(updated.workflow_status, 2)
        self.assertEqual(current.session.error, None)
        self.assertEqual(current.session.confirmation, "Request submitted for Approval")
        self.assertTrue(str(redirect.exception.url).endswith("/%s" % req_id))
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][0], approver_pe_id)
        self.assertIn("REQ-SUBMIT-001", sent[0][1]["subject"])
        self.assertIn("/req/req/%s" % req_id, sent[0][1]["message"])

    # -------------------------------------------------------------------------
    def testReqSubmitRedirectsWhenNoApproverExists(self):
        """req_submit redirects with an error if no approver is configured for the site"""

        db = current.db
        s3db = current.s3db
        auth = current.auth

        # Create a draft request at a site without any req_approver rows
        office = self.create_office()
        req_id = self.create_request(office.site_id,
                                     workflow_status=1,
                                     )
        record = db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                      limitby=(0, 1),
                                                      ).first()

        saved_permission = auth.s3_has_permission
        saved_ancestors = s3db.pr_get_ancestors
        saved_redirect = req_module.redirect

        current.session.error = None

        try:
            auth.s3_has_permission = lambda *args, **kwargs: True
            s3db.pr_get_ancestors = lambda pe_id: []
            req_module.redirect = lambda url: (_ for _ in ()).throw(RedirectIntercept(url))

            with self.assertRaises(RedirectIntercept) as redirect:
                RequestModel.req_submit(Storage(record=record,
                                               id=req_id,
                                               unauthorised=lambda: self.fail("submit unauthorised"),
                                               ))
        finally:
            auth.s3_has_permission = saved_permission
            s3db.pr_get_ancestors = saved_ancestors
            req_module.redirect = saved_redirect

        self.assertEqual(current.session.error, "No Request Approver defined")
        self.assertTrue(str(redirect.exception.url).endswith("/%s" % req_id))

    # -------------------------------------------------------------------------
    def testReqApproveRecordsNonFinalApproval(self):
        """req_approve records an approver without notifying warehouses until all approvals are present"""

        db = current.db
        s3db = current.s3db
        auth = current.auth

        # Create a submitted request with two possible approvers
        office = self.create_office()
        person_id = self.create_person(last_name="Approver One")
        other_id = self.create_person(last_name="Approver Two")
        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(office.site_id,
                                     workflow_status=2,
                                     )
        self.create_request_item(req_id,
                                 item_id,
                                 pack_id,
                                 quantity=1,
                                 )
        record = db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                      limitby=(0, 1),
                                                      ).first()

        saved_approvers = req_module.req_approvers
        saved_logged_in = auth.s3_logged_in_person
        saved_sender = current.msg.send_by_pe_id
        saved_redirect = req_module.redirect

        current.session.confirmation = None

        try:
            # Keep this as a non-final approval so the warehouse notification block stays untouched
            req_module.req_approvers = lambda site_id: {
                person_id: {"matcher": False, "title": "Logistics"},
                other_id: {"matcher": False, "title": "Operations"},
            }
            auth.s3_logged_in_person = lambda: person_id
            current.msg.send_by_pe_id = lambda *args, **kwargs: self.fail("unexpected warehouse notification")
            req_module.redirect = lambda url: (_ for _ in ()).throw(RedirectIntercept(url))

            with self.assertRaises(RedirectIntercept) as redirect:
                RequestModel.req_approve(Storage(record=record,
                                                id=req_id,
                                                unauthorised=lambda: self.fail("approve unauthorised"),
                                                ))
        finally:
            req_module.req_approvers = saved_approvers
            auth.s3_logged_in_person = saved_logged_in
            current.msg.send_by_pe_id = saved_sender
            req_module.redirect = saved_redirect

        artable = s3db.req_approver_req
        approval = db(artable.req_id == req_id).select(artable.person_id,
                                                       artable.title,
                                                       limitby=(0, 1),
                                                       ).first()
        status = db(s3db.req_req.id == req_id).select(s3db.req_req.workflow_status,
                                                      limitby=(0, 1),
                                                      ).first()
        self.assertIsNotNone(approval)
        self.assertEqual(approval.person_id, person_id)
        self.assertEqual(approval.title, "Logistics")
        self.assertEqual(status.workflow_status, 2)
        self.assertEqual(current.session.confirmation, "Request Approved")
        self.assertTrue(str(redirect.exception.url).endswith("/%s" % req_id))

    # -------------------------------------------------------------------------
    def testReqApproveRedirectsMatchersToOutstandingMatches(self):
        """req_approve redirects matchers to unassigned items before recording approval"""

        db = current.db
        s3db = current.s3db
        auth = current.auth

        # Create one submitted request item without a source site
        office = self.create_office()
        person_id = self.create_person(last_name="Matcher")
        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(office.site_id,
                                     workflow_status=2,
                                     )
        self.create_request_item(req_id,
                                 item_id,
                                 pack_id,
                                 quantity=2,
                                 )
        record = db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                      limitby=(0, 1),
                                                      ).first()

        saved_approvers = req_module.req_approvers
        saved_logged_in = auth.s3_logged_in_person
        saved_redirect = req_module.redirect

        try:
            # Matchers must complete source matching before the approval is stored
            req_module.req_approvers = lambda site_id: {
                person_id: {"matcher": True, "title": "Matcher"},
            }
            auth.s3_logged_in_person = lambda: person_id
            req_module.redirect = lambda url: (_ for _ in ()).throw(RedirectIntercept(url))

            with self.assertRaises(RedirectIntercept) as redirect:
                RequestModel.req_approve(Storage(record=record,
                                                id=req_id,
                                                unauthorised=lambda: self.fail("approve unauthorised"),
                                                ))
        finally:
            req_module.req_approvers = saved_approvers
            auth.s3_logged_in_person = saved_logged_in
            req_module.redirect = saved_redirect

        self.assertEqual(db(s3db.req_approver_req.req_id == req_id).count(), 0)
        self.assertEqual(current.session.warning, "You need to Match Items in this Request")
        self.assertIn("/%s/req_item" % req_id, str(redirect.exception.url))


# =============================================================================
class ReqControllerTests(SupplyChainTestCase):
    """Tests for request controller wrappers and helper endpoints"""

    # -------------------------------------------------------------------------
    def testReqIndexUsesCustomHome(self):
        """req index delegates to the deployment home customisation"""

        fake_settings = Storage(has_module=current.deployment_settings.has_module,
                                customise_home=lambda module, alt_function=None: \
                                    {"module": module,
                                     "alt_function": alt_function,
                                     },
                                )

        with self.controller("req",
                             function="index",
                             overrides={"settings": fake_settings},
                             ) as controller:
            output = controller.module["index"]()

        self.assertEqual(output["module"], "req")
        self.assertEqual(output["alt_function"], "index_alt")

    # -------------------------------------------------------------------------
    def testReqIndexAltAndCreateRedirects(self):
        """index_alt and create redirect to the expected request views"""

        with self.controller("req", function="index_alt") as controller:
            with self.assertRaises(ControllerRedirect) as redirect:
                controller.module["index_alt"]()
            self.assertIn("/req/req", str(redirect.exception.url))

        with self.controller("req", function="create") as controller:
            with self.assertRaises(ControllerRedirect) as redirect:
                controller.module["create"]()
            self.assertIn("/req/req/create", str(redirect.exception.url))

    # -------------------------------------------------------------------------
    def testNeedControllersConfigurePrepHooks(self):
        """need and need_service configure their prep hooks for interactive views"""

        s3db = current.s3db

        stats_field = s3db.stats_impact.location_id
        saved_default = stats_field.default
        saved_list_fields = s3db.get_config("req_need_service", "list_fields")
        saved_insertable = s3db.get_config("req_need_service", "insertable")
        saved_deletable = s3db.get_config("req_need_service", "deletable")

        try:
            with self.controller("req", function="need") as controller:
                output = controller.module["need"]()
                prep = output.prep
                r = Storage(component_name="impact",
                            record=Storage(location_id=123),
                            )
                self.assertTrue(prep(r))
                self.assertEqual(stats_field.default, 123)

            with self.controller("req", function="need_service") as controller:
                output = controller.module["need_service"]()
                prep = output.prep
                configured = {}
                r = Storage(component=None,
                            resource=Storage(configure=lambda **kwargs: configured.update(kwargs)),
                            )
                self.assertTrue(prep(r))
        finally:
            stats_field.default = saved_default
            s3db.configure("req_need_service",
                           list_fields=saved_list_fields,
                           insertable=saved_insertable,
                           deletable=saved_deletable,
                           )

        self.assertEqual(output.kwargs["rheader"], s3db.req_rheader)
        self.assertEqual(configured["list_fields"],
                         ["priority",
                          "need_id$date",
                          "need_id$location_id",
                          "service_id",
                          "details",
                          "status",
                          "need_id",
                          ])
        self.assertFalse(configured["insertable"])
        self.assertFalse(configured["deletable"])

    # -------------------------------------------------------------------------
    def testNeedSiteTypeAndOrderItemUseCrudController(self):
        """need_site_type and order_item delegate to the generic CRUD controller"""

        with self.controller("req", function="need_site_type") as controller:
            output = controller.module["need_site_type"]()
            self.assertEqual(output.args, ())

        with self.controller("req", function="order_item") as controller:
            output = controller.module["order_item"]()
            self.assertEqual(output.args, ())

    # -------------------------------------------------------------------------
    def testIsAffiliatedHandlesAnonymousAndAdminUsers(self):
        """is_affiliated handles anonymous and admin users without DB lookups"""

        auth = current.auth
        saved_logged_in = auth.is_logged_in
        saved_has_role = auth.s3_has_role

        try:
            with self.controller("req", function="is_affiliated") as controller:
                auth.is_logged_in = lambda: False
                self.assertFalse(controller.module["is_affiliated"]())

                auth.is_logged_in = lambda: True
                auth.s3_has_role = lambda role: role == "ADMIN"
                self.assertTrue(controller.module["is_affiliated"]())
        finally:
            auth.is_logged_in = saved_logged_in
            auth.s3_has_role = saved_has_role

    # -------------------------------------------------------------------------
    def testMarkerFnUsesTypeAndPrioritySpecificMarker(self):
        """marker_fn selects the correct marker for the request type/priority"""

        db = current.db

        mtable = db.gis_marker
        for name, image in (("asset_red", "asset_red.png"),
                            ("staff_yellow", "staff_yellow.png"),
                            ("request", "request.png"),
                            ):
            if not db(mtable.name == name).select(mtable.id, limitby=(0, 1)).first():
                mtable.insert(name=name,
                              image=image,
                              height=32,
                              width=32,
                              )

        with self.controller("req", function="marker_fn") as controller:
            marker_fn = controller.module["marker_fn"]

            item_marker = marker_fn(Storage(type=1, priority=3))
            people_marker = marker_fn(Storage(type=3, priority=2))
            default_marker = marker_fn(Storage(type=9, priority=1))

        self.assertIn("red", item_marker.image)
        self.assertIn("yellow", people_marker.image)
        self.assertIsNotNone(default_marker.image)

    # -------------------------------------------------------------------------
    def testReqAndReqTemplateDelegateToReqController(self):
        """req and req_template set their filters and delegate to req_controller"""

        table = current.s3db.req_req
        saved_filter = current.response.s3.filter
        saved_prompt = current.deployment_settings.req.prompt_match
        saved_default = table.is_template.default
        saved_readable = table.is_template.readable
        saved_writable = table.is_template.writable
        saved_list_fields = current.s3db.get_config("req_req", "list_fields")

        try:
            with self.controller("req", function="req") as controller:
                controller.module["req"].__globals__["req_controller"] = \
                    lambda template=False: Storage(template=template,
                                                   filter=current.response.s3.filter,
                                                   )
                output = controller.module["req"]()
                self.assertFalse(output.template)
                self.assertIsNotNone(output.filter)

            with self.controller("req", function="req_template") as controller:
                controller.module["req_template"].__globals__["req_controller"] = \
                    lambda template=False: Storage(template=template,
                                                   filter=current.response.s3.filter,
                                                   list_fields=current.s3db.get_config("req_req", "list_fields"),
                                                   )
                output = controller.module["req_template"]()
                self.assertTrue(output.template)
                self.assertIsNotNone(output.filter)
                self.assertTrue(table.is_template.default)
                self.assertFalse(table.is_template.readable)
                self.assertFalse(table.is_template.writable)
                self.assertIn("site_id", output.list_fields)
                self.assertIn("purpose", output.list_fields)
                self.assertFalse(current.deployment_settings.req.prompt_match)
        finally:
            current.response.s3.filter = saved_filter
            current.deployment_settings.req.prompt_match = saved_prompt
            table.is_template.default = saved_default
            table.is_template.readable = saved_readable
            table.is_template.writable = saved_writable
            current.s3db.configure("req_req", list_fields=saved_list_fields)

    # -------------------------------------------------------------------------
    def testReqTemplateReqItemBranchConfiguresItemListFields(self):
        """req_template configures compact item list fields inside the req_item tab"""

        s3db = current.s3db
        saved_prompt = current.deployment_settings.req.prompt_match
        saved_list_fields = s3db.get_config("req_req_item", "list_fields")

        try:
            with self.controller("req",
                                 function="req_template",
                                 args=["req_item"],
                                 ) as controller:
                controller.module["req_template"].__globals__["req_controller"] = \
                    lambda template=False: \
                    Storage(template=template,
                            list_fields=s3db.get_config("req_req_item", "list_fields"),
                            )
                output = controller.module["req_template"]()
                self.assertTrue(output.template)
                self.assertEqual(output.list_fields,
                                 ["item_id", "item_pack_id", "quantity", "comments"])
        finally:
            current.deployment_settings.req.prompt_match = saved_prompt
            s3db.configure("req_req_item", list_fields=saved_list_fields)

    # -------------------------------------------------------------------------
    def testReqControllerCreatePrepConfiguresTypedItemRequests(self):
        """req_controller prep configures item request create forms"""

        auth = current.auth
        s3db = current.s3db
        table = s3db.req_req

        office = self.create_office()
        filters = []
        form_mods = []
        inline_forms = []

        fake_settings = Storage(has_module=current.deployment_settings.has_module,
                                get_req_workflow=lambda: False,
                                get_req_req_crud_strings=lambda req_type: None,
                                get_req_items_ask_purpose=lambda: False,
                                get_req_inline_forms=lambda: True,
                                get_ui_auto_keyvalue=lambda: False,
                                )

        saved_logged_in = auth.is_logged_in
        saved_user = auth.user
        saved_form_mods = s3db.req_create_form_mods
        saved_inline_form = s3db.req_inline_form
        saved_default = table.type.default
        saved_readable = table.type.readable
        saved_writable = table.type.writable
        saved_date_recv_readable = table.date_recv.readable
        saved_date_recv_writable = table.date_recv.writable
        saved_site_default = table.site_id.default
        saved_site_label = table.site_id.label
        saved_request_for_label = table.request_for_id.label
        saved_recv_by_label = table.recv_by_id.label

        auth.is_logged_in = lambda: True
        auth.user = Storage(site_id=office.site_id)
        s3db.req_create_form_mods = lambda: form_mods.append(True)
        s3db.req_inline_form = lambda req_type, method: inline_forms.append((req_type, method))
        results = Storage()

        try:
            with self.controller("req",
                                 function="req",
                                 query_vars={"type": "1"},
                                 overrides={"settings": fake_settings},
                                 ) as controller:
                output = controller.module["req_controller"]()
                prep = output.prep
                r = Storage(table=table,
                            record=None,
                            component=None,
                            interactive=True,
                            id=None,
                            method=None,
                            http="GET",
                            resource=Storage(add_filter=lambda query: filters.append(query)),
                            representation="html",
                            )
                self.assertTrue(prep(r))
                results.type_default = table.type.default
                results.type_readable = table.type.readable
                results.type_writable = table.type.writable
                results.date_recv_readable = table.date_recv.readable
                results.date_recv_writable = table.date_recv.writable
                results.site_default = table.site_id.default
                results.site_label = str(table.site_id.label)
                results.request_for_label = str(table.request_for_id.label)
                results.recv_by_label = str(table.recv_by_id.label)
        finally:
            auth.is_logged_in = saved_logged_in
            auth.user = saved_user
            s3db.req_create_form_mods = saved_form_mods
            s3db.req_inline_form = saved_inline_form
            table.type.default = saved_default
            table.type.readable = saved_readable
            table.type.writable = saved_writable
            table.date_recv.readable = saved_date_recv_readable
            table.date_recv.writable = saved_date_recv_writable
            table.site_id.default = saved_site_default
            table.site_id.label = saved_site_label
            table.request_for_id.label = saved_request_for_label
            table.recv_by_id.label = saved_recv_by_label

        self.assertEqual(results.type_default, 1)
        self.assertFalse(results.type_readable)
        self.assertFalse(results.type_writable)
        self.assertTrue(results.date_recv_readable)
        self.assertTrue(results.date_recv_writable)
        self.assertEqual(results.site_default, office.site_id)
        self.assertEqual(results.site_label, "Deliver To")
        self.assertEqual(results.request_for_label, "Deliver To")
        self.assertEqual(results.recv_by_label, "Delivered To")
        self.assertEqual(len(filters), 1)
        self.assertEqual(form_mods, [True])
        self.assertEqual(inline_forms, [(1, "create")])

    # -------------------------------------------------------------------------
    def testReqControllerCommitPrepConfiguresCommitForms(self):
        """req_controller prep configures item commitments with site options"""

        auth = current.auth
        s3db = current.s3db

        requester = self.create_office()
        sender = self.create_office()
        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(requester.site_id, req_type=1)
        self.create_request_item(req_id, item_id, pack_id, quantity=4)

        rtable = s3db.req_req
        ctable = s3db.req_commit
        record = current.db(rtable.id == req_id).select(rtable.ALL,
                                                        limitby=(0, 1),
                                                        ).first()

        fake_settings = Storage(has_module=current.deployment_settings.has_module,
                                get_req_workflow=lambda: False,
                                get_req_req_crud_strings=lambda req_type: None,
                                get_req_items_ask_purpose=lambda: False,
                                get_req_commit_people=lambda: True,
                                get_req_restrict_on_complete=lambda: True,
                                get_ui_auto_keyvalue=lambda: False,
                                )

        saved_facilities = auth.permitted_facilities
        saved_filter_widgets = s3db.get_config("req_commit", "filter_widgets")
        saved_insertable = s3db.get_config("req_commit", "insertable")
        saved_crud_form = s3db.get_config("req_commit", "crud_form")
        saved_widget = s3db.req_commit_item.req_item_id.widget
        saved_requires = s3db.req_commit.site_id.requires
        results = Storage()

        auth.permitted_facilities = lambda *args, **kwargs: [sender.site_id]

        try:
            with self.controller("req",
                                 function="req",
                                 overrides={"settings": fake_settings},
                                 ) as controller:
                output = controller.module["req_controller"]()
                prep = output.prep
                r = Storage(table=s3db.req_req,
                            record=record,
                            resource=Storage(add_filter=lambda query: None),
                            component=Storage(name="commit",
                                              table=ctable,
                                              alias="commit",
                                              tablename="req_commit",
                                              ),
                            component_name="commit",
                            interactive=True,
                            component_id=None,
                            method="create",
                            id=req_id,
                            url=lambda **kwargs: "/eden/req/req/%s" % req_id,
                            )
                self.assertTrue(prep(r))
                results.insertable = s3db.get_config("req_commit", "insertable")
                results.filter_widgets = s3db.get_config("req_commit", "filter_widgets")
                results.crud_form = s3db.get_config("req_commit", "crud_form")
                results.widget = s3db.req_commit_item.req_item_id.widget
                results.site_options = dict(ctable.site_id.requires.options())
        finally:
            auth.permitted_facilities = saved_facilities
            s3db.configure("req_commit",
                           filter_widgets=saved_filter_widgets,
                           insertable=saved_insertable,
                           crud_form=saved_crud_form,
                           )
            s3db.req_commit_item.req_item_id.widget = saved_widget
            ctable.site_id.requires = saved_requires

        self.assertTrue(results.insertable)
        self.assertIsNone(results.filter_widgets)
        self.assertIsNone(results.widget)
        self.assertIsNotNone(results.crud_form)
        self.assertIn(str(sender.site_id), results.site_options)

    # -------------------------------------------------------------------------
    def testReqControllerPostpAddsRequestActions(self):
        """req_controller postp adds list actions for requests and commits"""

        auth = current.auth
        response_s3 = current.response.s3
        s3db = current.s3db
        table = s3db.req_req

        office = self.create_office()
        self.create_request(office.site_id, req_type=1)
        self.create_request(office.site_id, req_type=3)

        fake_settings = Storage(has_module=current.deployment_settings.has_module,
                                get_req_use_commit=lambda: True,
                                get_req_copyable=lambda: True,
                                get_req_req_type=lambda: ["Stock", "People"],
                                get_req_commit_people=lambda: True,
                                )

        saved_actions = response_s3.actions
        saved_ready = response_s3.jquery_ready
        saved_rfooter = response_s3.rfooter
        saved_user = auth.user
        labels = []

        try:
            with self.controller("req",
                                 function="req",
                                 overrides={"settings": fake_settings},
                                 ) as controller:
                output = controller.module["req_controller"]()
                postp = output.postp
                globals_ = postp.__globals__
                saved_buttons = globals_["s3_action_buttons"]
                globals_["s3_action_buttons"] = lambda *args, **kwargs: None

                response_s3.actions = []
                response_s3.jquery_ready = []
                response_s3.rfooter = None
                auth.user = Storage(site_id=office.site_id,
                                    organisation_id=office.organisation_id,
                                    )

                try:
                    r = Storage(interactive=True,
                                method=None,
                                component=None,
                                http="GET",
                                table=table,
                                )
                    postp(r, {})
                    labels = [str(action["label"]) for action in response_s3.actions]
                finally:
                    globals_["s3_action_buttons"] = saved_buttons
        finally:
            auth.user = saved_user
            response_s3.actions = saved_actions
            response_s3.jquery_ready = saved_ready
            response_s3.rfooter = saved_rfooter

        self.assertIn("Commit", labels)
        self.assertIn("Send", labels)
        self.assertIn("Check", labels)
        self.assertIn("Copy", labels)
        self.assertIn("Delete", labels)

    # -------------------------------------------------------------------------
    def testReqControllerCommitPostpAddsFooterAndShipmentAction(self):
        """req_controller postp exposes commit-all and prepare shipment actions"""

        response_s3 = current.response.s3
        s3db = current.s3db
        requester = self.create_office()
        sender = self.create_office()
        req_id = self.create_request(requester.site_id, req_type=1)
        record = current.db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                              limitby=(0, 1),
                                                              ).first()

        saved_actions = response_s3.actions
        saved_ready = response_s3.jquery_ready
        saved_rfooter = response_s3.rfooter
        rfooter = None
        labels = []

        try:
            with self.controller("req", function="req") as controller:
                output = controller.module["req_controller"]()
                postp = output.postp
                globals_ = postp.__globals__
                saved_buttons = globals_["s3_action_buttons"]
                globals_["s3_action_buttons"] = lambda *args, **kwargs: None

                try:
                    response_s3.actions = []
                    response_s3.jquery_ready = []
                    response_s3.rfooter = None
                    r = Storage(interactive=True,
                                method=None,
                                component=Storage(name="commit",
                                                  tablename="req_commit",
                                                  ),
                                record=record,
                                id=req_id,
                                )
                    postp(r, {"form": object()})
                    rfooter = str(response_s3.rfooter)

                    response_s3.actions = []
                    response_s3.jquery_ready = []
                    response_s3.rfooter = None
                    self.create_commit(req_id, site_id=sender.site_id)
                    postp(r, {"form": object()})
                    labels = [str(action["label"]) for action in response_s3.actions]
                finally:
                    globals_["s3_action_buttons"] = saved_buttons
        finally:
            response_s3.actions = saved_actions
            response_s3.jquery_ready = saved_ready
            response_s3.rfooter = saved_rfooter

        self.assertIn("Commit All", rfooter)
        self.assertIn("Prepare Shipment", labels)

    # -------------------------------------------------------------------------
    def testReqItemControllerConfiguresHierarchyFieldsAndAction(self):
        """req_item configures hierarchy list fields and prompt-match action"""

        response_s3 = current.response.s3
        s3db = current.s3db

        fake_settings = Storage(has_module=current.deployment_settings.has_module,
                                get_req_prompt_match=lambda: True,
                                )
        fake_gis = Storage(get_relevant_hierarchy_levels=lambda: ["L1", "L2"])

        saved_actions = response_s3.actions
        saved_filter = response_s3.filter
        saved_list_fields = s3db.get_config("req_req_item", "list_fields")
        saved_insertable = s3db.get_config("req_req_item", "insertable")
        saved_hide = s3db.req_hide_quantities
        hide_calls = []
        configured = None
        insertable = None
        labels = []

        s3db.req_hide_quantities = lambda table: hide_calls.append(table._tablename)

        try:
            with self.controller("req",
                                 function="req_item",
                                 overrides={"settings": fake_settings,
                                            "gis": fake_gis,
                                            },
                                 ) as controller:
                response_s3.actions = []
                output = controller.module["req_item"]()
                prep = output.prep
                r = Storage(interactive=True,
                            representation="html",
                            method="create",
                            table=s3db.req_req_item,
                            )
                self.assertTrue(prep(r))
                configured = s3db.get_config("req_req_item", "list_fields")
                insertable = s3db.get_config("req_req_item", "insertable")
                labels = [str(action["label"]) for action in response_s3.actions]
        finally:
            response_s3.actions = saved_actions
            response_s3.filter = saved_filter
            s3db.configure("req_req_item",
                           list_fields=saved_list_fields,
                           insertable=saved_insertable,
                           )
            s3db.req_hide_quantities = saved_hide

        self.assertEqual(output.args, ("req", "req_item"))
        self.assertIn("req_id$site_id", configured)
        self.assertIn("req_id$site_id$location_id$L1", configured)
        self.assertIn("req_id$site_id$location_id$L2", configured)
        self.assertFalse(insertable)
        self.assertEqual(hide_calls, ["req_req_item"])
        self.assertIn("Request from Facility", labels)

    # -------------------------------------------------------------------------
    def testReqItemPacksSupportsVariableLookup(self):
        """req_item_packs resolves the request item from filter variable names"""

        office = self.create_office()
        item_id = self.create_supply_item(name="Packable Variable Item")
        pack_a = self.create_item_pack(item_id, name="small", quantity=1)
        pack_b = self.create_item_pack(item_id, name="large", quantity=10)
        req_id = self.create_request(office.site_id)
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_a,
                                               quantity=1,
                                               )

        with self.controller("req",
                             function="req_item_packs",
                             query_vars={"commit_item.req_item_id": str(req_item_id)},
                             ) as controller:
            output = controller.module["req_item_packs"]()

        payload = json.loads(output)
        pack_ids = {row["id"] for row in payload}
        self.assertIn(pack_a, pack_ids)
        self.assertIn(pack_b, pack_ids)

    # -------------------------------------------------------------------------
    def testReqItemInvItemShowsMatchesAlternativesAndOrderAction(self):
        """req_item_inv_item renders stock matches, alternatives and order action"""

        s3db = current.s3db
        response_s3 = current.response.s3

        requester = self.create_office(name="Requester")
        warehouse = self.create_office(name="Warehouse")
        alt_warehouse = self.create_office(name="Alt Warehouse")
        requester_person = self.create_person()

        item_id = self.create_supply_item(name="Main Item")
        pack_id = self.create_item_pack(item_id, quantity=1)
        alt_item_id = self.create_supply_item(name="Alt Item")
        alt_pack_id = self.create_item_pack(alt_item_id, quantity=1)
        s3db.supply_item_alt.insert(item_id=item_id, alt_item_id=alt_item_id)

        self.create_inventory_item(warehouse.site_id, item_id, pack_id, quantity=8)
        self.create_inventory_item(alt_warehouse.site_id, alt_item_id, alt_pack_id, quantity=5)

        req_id = self.create_request(requester.site_id,
                                     requester_id=requester_person,
                                     req_type=1,
                                     )
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=4,
                                               )

        fake_settings = Storage(has_module=current.deployment_settings.has_module,
                                get_supply_use_alt_name=lambda: True,
                                get_req_order_item=lambda: True,
                                )
        calls = []
        items = iter(("PRIMARY", "ALTERNATIVE"))

        def fake_crud_controller(*args, **kwargs):
            """Return deterministic inventory lists for the request stock view"""

            calls.append((args, kwargs, response_s3.filter))
            return {"items": next(items)}

        saved_actions = response_s3.actions
        saved_filter = response_s3.filter
        saved_view = current.response.view
        labels = []

        try:
            with self.controller("req",
                                 function="req_item_inv_item",
                                 args=[str(req_item_id)],
                                 overrides={"crud_controller": fake_crud_controller,
                                            "settings": fake_settings,
                                            },
                                 ) as controller:
                response_s3.actions = []
                output = controller.module["req_item_inv_item"]()
                view = current.response.view
                labels = [str(action["label"]) for action in response_s3.actions]
        finally:
            response_s3.actions = saved_actions
            response_s3.filter = saved_filter
            current.response.view = saved_view

        self.assertEqual(output["items"], "PRIMARY")
        self.assertEqual(output["items_alt"], "ALTERNATIVE")
        self.assertIsNotNone(output["order_btn"])
        self.assertEqual(view, "req/req_item_inv_item.html")
        self.assertEqual(len(calls), 2)
        self.assertIn("Request From", labels)

    # -------------------------------------------------------------------------
    def testReqSkillControllerConfiguresListFieldsAndReadAction(self):
        """req_skill configures hierarchy fields and opens linked requests"""

        response_s3 = current.response.s3
        s3db = current.s3db

        saved_actions = response_s3.actions
        saved_filter = response_s3.filter
        saved_list_fields = s3db.get_config("req_req_skill", "list_fields")
        saved_insertable = s3db.get_config("req_req_skill", "insertable")
        saved_hide = s3db.req_hide_quantities
        configured = None
        labels = []
        hide_calls = []

        s3db.req_hide_quantities = lambda table: hide_calls.append(table._tablename)

        try:
            with self.controller("req", function="req_skill") as controller:
                response_s3.actions = []
                output = controller.module["req_skill"]()
                prep = output.prep
                postp = output.postp
                r = Storage(interactive=True,
                            representation="html",
                            method="create",
                            table=s3db.req_req_skill,
                            )
                self.assertTrue(prep(r))
                configured = s3db.get_config("req_req_skill", "list_fields")
                postp(Storage(interactive=True), {})
                labels = [str(action["label"]) for action in response_s3.actions]
        finally:
            response_s3.actions = saved_actions
            response_s3.filter = saved_filter
            s3db.configure("req_req_skill",
                           list_fields=saved_list_fields,
                           insertable=saved_insertable,
                           )
            s3db.req_hide_quantities = saved_hide

        self.assertEqual(output.args, ("req", "req_skill"))
        self.assertIn("req_id$site_id", configured)
        self.assertIn("req_id$site_id$location_id$L3", configured)
        self.assertIn("req_id$site_id$location_id$L4", configured)
        self.assertEqual(hide_calls, ["req_req_skill"])
        self.assertIn("Open", labels)

    # -------------------------------------------------------------------------
    def testSkillsFilterHandlesSingleAndMultipleSkills(self):
        """skills_filter defaults single skills and constrains multiple choices"""

        db = current.db
        s3db = current.s3db
        field = s3db.req_commit_skill.skill_id

        office = self.create_office()
        req_single = self.create_request(office.site_id, req_type=3)
        skill_a = self.create_skill("Skill A")
        self.create_request_skill(req_single,
                                  skill_ids=[skill_a],
                                  quantity=1,
                                  )

        req_multi = self.create_request(office.site_id, req_type=3)
        skill_b = self.create_skill("Skill B")
        self.create_request_skill(req_multi,
                                  skill_ids=[skill_a, skill_b],
                                  quantity=2,
                                  )

        saved_default = field.default
        saved_writable = field.writable
        saved_requires = field.requires

        try:
            with self.controller("req", function="skills_filter") as controller:
                controller.module["skills_filter"](req_single)
                single_default = field.default
                single_writable = field.writable

            field.default = None
            field.writable = True
            field.requires = saved_requires

            with self.controller("req", function="skills_filter") as controller:
                controller.module["skills_filter"](req_multi)
                multiple_options = dict(field.requires.options())
        finally:
            field.default = saved_default
            field.writable = saved_writable
            field.requires = saved_requires

        self.assertEqual(single_default, skill_a)
        self.assertFalse(single_writable)
        self.assertIn(str(skill_a), multiple_options)
        self.assertIn(str(skill_b), multiple_options)

    # -------------------------------------------------------------------------
    def testCommitItemControllerRestrictsToItemCommitments(self):
        """commit_item only offers item commitments in the commit selector"""

        db = current.db
        s3db = current.s3db
        office = self.create_office()

        item_req = self.create_request(office.site_id, req_type=1)
        people_req = self.create_request(office.site_id, req_type=3)
        item_commit = self.create_commit(item_req, site_id=office.site_id)
        people_commit = self.create_commit(people_req, site_id=office.site_id)
        db(s3db.req_commit.id == item_commit).update(type=1)
        db(s3db.req_commit.id == people_commit).update(type=3)

        field = s3db.req_commit_item.commit_id
        saved_requires = field.requires

        try:
            with self.controller("req", function="commit_item") as controller:
                output = controller.module["commit_item"]()
                prep = output.prep
                r = Storage(table=s3db.req_commit_item)
                self.assertTrue(prep(r))
                options = dict(field.requires.other.options())
        finally:
            field.requires = saved_requires

        self.assertEqual(output.args, ())
        self.assertIn(str(item_commit), options)
        self.assertNotIn(str(people_commit), options)

    # -------------------------------------------------------------------------
    def testProjectReqAllowsOnlyS3JsonOptionsRequests(self):
        """project_req only exposes the options method in s3json format"""

        auth = current.auth
        saved_format = auth.permission.format

        try:
            auth.permission.format = "html"
            with self.controller("req", function="project_req") as controller:
                self.assertEqual(controller.module["project_req"](), "")

            auth.permission.format = "s3json"
            with self.controller("req", function="project_req") as controller:
                output = controller.module["project_req"]()
                prep = output.prep
                self.assertTrue(prep(Storage(method="options")))
                self.assertFalse(prep(Storage(method="read")))
        finally:
            auth.permission.format = saved_format

    # -------------------------------------------------------------------------
    def testReqItemPacksReturnsItemPackOptionsAsJson(self):
        """req_item_packs returns all packs for the requested item as JSON"""

        office = self.create_office()
        item_id = self.create_supply_item(name="Packable Item")
        pack_a = self.create_item_pack(item_id, name="small", quantity=1)
        pack_b = self.create_item_pack(item_id, name="large", quantity=10)
        req_id = self.create_request(office.site_id)
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_a,
                                               quantity=2,
                                               )

        with self.controller("req",
                             function="req_item_packs",
                             args=[str(req_item_id)],
                             ) as controller:
            output = controller.module["req_item_packs"]()
            content_type = current.response.headers["Content-Type"]

        payload = json.loads(output)
        pack_ids = {row["id"] for row in payload}
        self.assertEqual(content_type, "application/json")
        self.assertIn(pack_a, pack_ids)
        self.assertIn(pack_b, pack_ids)

    # -------------------------------------------------------------------------
    def testCommitItemJsonReturnsCommitRowsAsJson(self):
        """commit_item_json returns commitment rows for a request item as JSON"""

        office = self.create_office()
        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(office.site_id)
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=3,
                                               )
        commit_id = self.create_commit(req_id,
                                       site_id=office.site_id,
                                       organisation_id=office.organisation_id,
                                       )
        self.create_commit_item(commit_id, req_item_id, pack_id, quantity=2)

        with self.controller("req",
                             function="commit_item_json",
                             args=[str(req_item_id)],
                             ) as controller:
            output = controller.module["commit_item_json"]()
            content_type = current.response.headers["Content-Type"]

        payload = json.loads(output)
        self.assertEqual(content_type, "application/json")
        self.assertGreaterEqual(len(payload), 2)
        self.assertEqual(payload[0]["quantity"], "#")

    # -------------------------------------------------------------------------
    def testCommitReqRedirectsWithoutPermission(self):
        """commit_req denies access when the user cannot update the sending site"""

        auth = current.auth
        session = current.session

        office = self.create_office()
        req_id = self.create_request(office.site_id)

        saved = auth.s3_has_permission
        auth.s3_has_permission = lambda *args, **kwargs: False
        session.error = None

        try:
            with self.controller("req",
                                 function="commit_req",
                                 args=[str(req_id)],
                                 query_vars={"site_id": str(office.site_id)},
                                 ) as controller:
                with self.assertRaises(ControllerRedirect) as redirect:
                    controller.module["commit_req"]()
                self.assertIn("/req/req/%s" % req_id, str(redirect.exception.url))
        finally:
            auth.s3_has_permission = saved

        self.assertIsNotNone(session.error)

    # -------------------------------------------------------------------------
    def testCommitReqCreatesCommitFromAvailableStock(self):
        """commit_req creates a commitment using the available warehouse stock"""

        auth = current.auth
        s3db = current.s3db

        requester = self.create_office(name="Requester Site")
        sender = self.create_office(name="Sender Site")
        item_id = self.create_supply_item(name="Committed Item")
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(requester.site_id, req_type=1)
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=5,
                                               )
        self.create_inventory_item(sender.site_id,
                                   item_id,
                                   pack_id,
                                   quantity=8,
                                   )

        onaccept_calls = []
        saved_permission = auth.s3_has_permission
        saved_onaccept = s3db.onaccept

        auth.s3_has_permission = lambda *args, **kwargs: True
        s3db.onaccept = lambda tablename, record: onaccept_calls.append((tablename,
                                                                         record["req_item_id"],
                                                                         record["quantity"],
                                                                         ))

        try:
            with self.controller("req",
                                 function="commit_req",
                                 args=[str(req_id)],
                                 query_vars={"site_id": str(sender.site_id)},
                                 ) as controller:
                with self.assertRaises(ControllerRedirect) as redirect:
                    controller.module["commit_req"]()
        finally:
            auth.s3_has_permission = saved_permission
            s3db.onaccept = saved_onaccept

        db = current.db
        ctable = s3db.req_commit
        itable = s3db.req_commit_item

        commit = db((ctable.req_id == req_id) &
                    (ctable.site_id == sender.site_id)).select(ctable.id,
                                                               limitby=(0, 1),
                                                               ).first()
        self.assertIsNotNone(commit)

        commit_item = db(itable.commit_id == commit.id).select(itable.req_item_id,
                                                               itable.quantity,
                                                               limitby=(0, 1),
                                                               ).first()
        self.assertEqual(commit_item.req_item_id, req_item_id)
        self.assertEqual(commit_item.quantity, 5)
        self.assertEqual(onaccept_calls,
                         [("req_commit_item", req_item_id, 5)])
        self.assertIn("/req/commit/%s/commit_item" % commit.id,
                      str(redirect.exception.url))

    # -------------------------------------------------------------------------
    def testSendReqRedirectsWithoutPermission(self):
        """send_req refuses to prepare shipments without update permission on the sender site"""

        auth = current.auth
        session = current.session

        requester = self.create_office(name="Requester")
        sender = self.create_office(name="Sender")
        req_id = self.create_request(requester.site_id)

        saved_permission = auth.s3_has_permission
        saved_error = session.error
        auth.s3_has_permission = lambda *args, **kwargs: False

        try:
            session.error = None
            with self.controller("req",
                                 function="send_req",
                                 args=[str(req_id)],
                                 query_vars={"site_id": str(sender.site_id)},
                                 ) as controller:
                with self.assertRaises(ControllerRedirect) as redirect:
                    controller.module["send_req"]()
                url = str(redirect.exception.url)
                error = session.error
        finally:
            auth.s3_has_permission = saved_permission
            session.error = saved_error

        self.assertIn("/req/req/%s" % req_id, url)
        self.assertIsNotNone(error)

    # -------------------------------------------------------------------------
    def testSendReqRedirectsWhenNoItemsRemainOutstanding(self):
        """send_req redirects back to the request when all requested items are already in transit"""

        auth = current.auth
        session = current.session

        requester = self.create_office(name="Requester")
        sender = self.create_office(name="Sender")
        item_id = self.create_supply_item(name="Already Covered Item")
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(requester.site_id)
        self.create_request_item(req_id,
                                 item_id,
                                 pack_id,
                                 quantity=4,
                                 quantity_transit=4,
                                 )

        saved_permission = auth.s3_has_permission
        saved_warning = session.warning
        auth.s3_has_permission = lambda *args, **kwargs: True

        try:
            session.warning = None
            with self.controller("req",
                                 function="send_req",
                                 args=[str(req_id)],
                                 query_vars={"site_id": str(sender.site_id)},
                                 ) as controller:
                with self.assertRaises(ControllerRedirect) as redirect:
                    controller.module["send_req"]()
                url = str(redirect.exception.url)
                warning = session.warning
        finally:
            auth.s3_has_permission = saved_permission
            session.warning = saved_warning

        self.assertIn("/req/req/%s/req_item" % req_id, url)
        self.assertEqual(str(warning), "This request has no items outstanding!")

    # -------------------------------------------------------------------------
    def testSendReqCreatesShipmentFromAvailableStock(self):
        """send_req creates a draft shipment and track rows from matching stock items"""

        auth = current.auth
        db = current.db
        s3db = current.s3db

        requester = self.create_office(name="Requester")
        sender = self.create_office(name="Sender")
        person_id = self.create_person(last_name="Sender")
        item_id = self.create_supply_item(name="Shippable Item")
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(requester.site_id,
                                     req_ref="REQ-SEND-001",
                                     requester_id=person_id,
                                     )
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=5,
                                               )
        inv_item_id = self.create_inventory_item(sender.site_id,
                                                 item_id,
                                                 pack_id,
                                                 quantity=8,
                                                 status=0,
                                                 )

        saved_permission = auth.s3_has_permission
        saved_logged_in_person = auth.s3_logged_in_person
        auth.s3_has_permission = lambda *args, **kwargs: True
        auth.s3_logged_in_person = lambda: person_id

        try:
            with self.controller("req",
                                 function="send_req",
                                 args=[str(req_id)],
                                 query_vars={"site_id": str(sender.site_id)},
                                 ) as controller:
                with self.assertRaises(ControllerRedirect) as redirect:
                    controller.module["send_req"]()
                url = str(redirect.exception.url)
        finally:
            auth.s3_has_permission = saved_permission
            auth.s3_logged_in_person = saved_logged_in_person

        send = db((s3db.inv_send.req_ref == "REQ-SEND-001") &
                  (s3db.inv_send.site_id == sender.site_id)).select(s3db.inv_send.id,
                                                                    s3db.inv_send.sender_id,
                                                                    s3db.inv_send.to_site_id,
                                                                    limitby=(0, 1),
                                                                    orderby=~s3db.inv_send.id,
                                                                    ).first()
        track = db(s3db.inv_track_item.send_id == send.id).select(s3db.inv_track_item.req_item_id,
                                                                  s3db.inv_track_item.send_inv_item_id,
                                                                  s3db.inv_track_item.quantity,
                                                                  limitby=(0, 1),
                                                                  ).first()
        inv_item = db(s3db.inv_inv_item.id == inv_item_id).select(s3db.inv_inv_item.quantity,
                                                                  limitby=(0, 1),
                                                                  ).first()

        self.assertIn("/inv/send/%s/track_item" % send.id, url)
        self.assertEqual(send.sender_id, person_id)
        self.assertEqual(send.to_site_id, requester.site_id)
        self.assertEqual(track.req_item_id, req_item_id)
        self.assertEqual(track.send_inv_item_id, inv_item_id)
        self.assertEqual(track.quantity, 5)
        self.assertEqual(inv_item.quantity, 3)

    # -------------------------------------------------------------------------
    def testFacilityControllerDelegatesToOrgFacilityController(self):
        """facility configures create_next and delegates to the org facility controller"""

        s3db = current.s3db
        saved = s3db.org_facility_controller
        saved_next = s3db.get_config("org_facility", "create_next")
        s3db.org_facility_controller = lambda: "FACILITY"

        try:
            with self.controller("req", function="facility") as controller:
                output = controller.module["facility"]()
                create_next = s3db.get_config("org_facility", "create_next")
        finally:
            s3db.org_facility_controller = saved
            s3db.configure("org_facility", create_next=saved_next)

        self.assertEqual(output, "FACILITY")
        self.assertEqual(create_next, "/eden/req/facility/%5Bid%5D/read")

    # -------------------------------------------------------------------------
    def testApproverUsesCrudController(self):
        """approver delegates to the generic CRUD controller"""

        with self.controller("req", function="approver") as controller:
            output = controller.module["approver"]()

        self.assertEqual(output.args, ())

    # -------------------------------------------------------------------------
    def testReqControllerMapAndGeojsonConfigureMarkerHandling(self):
        """req_controller configures request markers for map and geojson output"""

        s3db = current.s3db
        table = s3db.req_req
        office = self.create_office(name="GeoJSON Site")
        req_id = self.create_request(office.site_id,
                                     req_ref="REQ-GEO-001",
                                     )

        saved_marker = s3db.get_config("req_req", "marker_fn")
        saved_represent = table.req_ref.represent

        try:
            with self.controller("req", function="req") as controller:
                output = controller.module["req_controller"]()
                prep = output.prep

                map_r = Storage(table=table,
                                record=None,
                                component=None,
                                interactive=True,
                                method="map",
                                resource=Storage(add_filter=lambda query: None),
                                representation="html",
                                )
                self.assertTrue(prep(map_r))
                marker_fn = s3db.get_config("req_req", "marker_fn")

            with self.controller("req", function="req") as controller:
                output = controller.module["req_controller"]()
                prep = output.prep

                geojson_r = Storage(table=table,
                                    record=None,
                                    component=None,
                                    interactive=False,
                                    method=None,
                                    resource=Storage(add_filter=lambda query: None),
                                    representation="geojson",
                                    )
                self.assertTrue(prep(geojson_r))
                geojson_repr = table.req_ref.represent("REQ-GEO-001", pdf=True)
        finally:
            s3db.configure("req_req", marker_fn=saved_marker)
            table.req_ref.represent = saved_represent

        self.assertTrue(callable(marker_fn))
        self.assertTrue(isinstance(geojson_repr, B))
        self.assertEqual(geojson_repr.components[0], "REQ-GEO-001")

    # -------------------------------------------------------------------------
    def testReqControllerDocumentAndPrefilledSiteBranches(self):
        """req_controller simplifies document uploads and honours req.site_id defaults"""

        s3db = current.s3db
        table = s3db.req_req
        dtable = s3db.doc_document

        office = self.create_office(name="Request Site")
        req_id = self.create_request(office.site_id, req_type=1)

        saved_submit = current.response.s3.crud.submit_button
        saved_url_readable = dtable.url.readable
        saved_url_writable = dtable.url.writable
        saved_date_readable = dtable.date.readable
        saved_date_writable = dtable.date.writable
        saved_site_default = table.site_id.default
        saved_site_writable = table.site_id.writable
        results = Storage()

        try:
            with self.controller("req",
                                 function="req",
                                 query_vars={"req.site_id": str(office.site_id)},
                                 ) as controller:
                output = controller.module["req_controller"]()
                prep = output.prep
                record = current.db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                                      limitby=(0, 1),
                                                                      ).first()

                document_r = Storage(table=table,
                                     record=record,
                                     component=Storage(name="document"),
                                     component_name="document",
                                     interactive=True,
                                     id=req_id,
                                     method="create",
                                     http="GET",
                                     resource=Storage(add_filter=lambda query: None),
                                     representation="html",
                                     )
                self.assertTrue(prep(document_r))
                results.submit_button = current.response.s3.crud.submit_button
                results.url_readable = dtable.url.readable
                results.url_writable = dtable.url.writable
                results.date_readable = dtable.date.readable
                results.date_writable = dtable.date.writable

                prefilled_r = Storage(table=table,
                                      record=None,
                                      component=None,
                                      interactive=True,
                                      id=None,
                                      method=None,
                                      http="POST",
                                      get_vars=current.request.get_vars,
                                      resource=Storage(add_filter=lambda query: None),
                                      representation="html",
                                      )
                self.assertTrue(prep(prefilled_r))
                results.site_default = table.site_id.default
                results.site_writable = table.site_id.writable
                results.has_query_var = "req.site_id" in prefilled_r.get_vars
        finally:
            current.response.s3.crud.submit_button = saved_submit
            dtable.url.readable = saved_url_readable
            dtable.url.writable = saved_url_writable
            dtable.date.readable = saved_date_readable
            dtable.date.writable = saved_date_writable
            table.site_id.default = saved_site_default
            table.site_id.writable = saved_site_writable

        self.assertEqual(results.submit_button, "Add")
        self.assertFalse(results.url_readable)
        self.assertFalse(results.url_writable)
        self.assertFalse(results.date_readable)
        self.assertFalse(results.date_writable)
        self.assertEqual(results.site_default, str(office.site_id))
        self.assertFalse(results.site_writable)
        self.assertFalse(results.has_query_var)

    # -------------------------------------------------------------------------
    def testReqItemOrderActionCreatesPurchaseRows(self):
        """req_item exposes an order action that copies request items into purchases"""

        s3db = current.s3db
        session = current.session
        db = current.db

        office = self.create_office(name="Order Site")
        item_id = self.create_supply_item(name="Ordered Item")
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(office.site_id)
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=7,
                                               )

        captured = {}
        saved_method = s3db.set_method
        saved_confirmation = session.confirmation

        s3db.set_method = lambda tablename, method=None, action=None: \
            captured.update(tablename=tablename,
                            method=method,
                            action=action,
                            )

        try:
            with self.controller("req", function="req_item") as controller:
                controller.module["req_item"]()
                order_item = captured["action"]
                record = db(s3db.req_req_item.id == req_item_id).select(s3db.req_req_item.ALL,
                                                                        limitby=(0, 1),
                                                                        ).first()
                with self.assertRaises(ControllerRedirect) as redirect:
                    order_item(Storage(record=record))
                url = str(redirect.exception.url)
                confirmation = session.confirmation
        finally:
            s3db.set_method = saved_method
            session.confirmation = saved_confirmation

        row = db(s3db.req_order_item.req_item_id == req_item_id).select(s3db.req_order_item.req_id,
                                                                        s3db.req_order_item.quantity,
                                                                        limitby=(0, 1),
                                                                        ).first()
        self.assertEqual(captured["tablename"], "req_req_item")
        self.assertEqual(captured["method"], "order")
        self.assertEqual(row.req_id, req_id)
        self.assertEqual(row.quantity, 7)
        self.assertEqual(str(confirmation), "Item added to your list of Purchases")
        self.assertIn("/req/req/%s/req_item" % req_id, url)

    # -------------------------------------------------------------------------
    def testCommitControllerConfiguresAssignFilterForUnaffiliatedUsers(self):
        """commit configures assignment filtering and single-person commits for outsiders"""

        s3db = current.s3db
        field = s3db.req_commit_person.human_resource_id

        office = self.create_office(name="Skills Site")
        req_id = self.create_request(office.site_id, req_type=3)
        skill_a = self.create_skill("Commit Skill A")
        skill_b = self.create_skill("Commit Skill B")
        self.create_request_skill(req_id,
                                  skill_ids=[skill_a, skill_b],
                                  quantity=2,
                                  )
        commit_id = self.create_commit(req_id,
                                       site_id=office.site_id,
                                       )
        current.db(s3db.req_commit.id == commit_id).update(type=3)

        saved_insertable = s3db.get_config("req_commit_person", "insertable")
        saved_writable = field.writable
        captured = {}
        human_resource_writable = None

        try:
            with self.controller("req",
                                 function="commit",
                                 args=[str(commit_id), "assign"],
                                 ) as controller:
                controller.module["commit"].__globals__["is_affiliated"] = lambda: False
                s3base = controller.module["commit"].__globals__["s3base"]
                saved_default_filter = s3base.set_default_filter
                s3base.set_default_filter = lambda selector, fn, tablename=None: \
                    captured.update(selector=selector,
                                    fn=fn,
                                    tablename=tablename,
                                    )
                try:
                    output = controller.module["commit"]()
                    skills = captured["fn"](None)
                    human_resource_writable = field.writable
                finally:
                    s3base.set_default_filter = saved_default_filter
        finally:
            s3db.configure("req_commit_person", insertable=saved_insertable)
            field.writable = saved_writable

        insertable = s3db.get_config("req_commit_person", "insertable")
        self.assertEqual(output.kwargs["rheader"], controller.module["commit_rheader"])
        self.assertFalse(insertable)
        self.assertFalse(human_resource_writable)
        self.assertEqual(captured["selector"], "competency.skill_id")
        self.assertEqual(captured["tablename"], "hrm_human_resource")
        self.assertEqual(skills, [skill_a, skill_b])

    # -------------------------------------------------------------------------
    def testCommitControllerPrepAndPostpConfigureTypeSpecificCommitForms(self):
        """commit prep/postp configure stock, people and other commitment flows"""

        auth = current.auth
        s3db = current.s3db
        response_s3 = current.response.s3

        site = self.create_office(name="Commit Site")
        other_site = self.create_office(name="Other Commit Site")
        item_id = self.create_supply_item(name="Committed Stock")
        pack_id = self.create_item_pack(item_id, quantity=1)

        item_req_id = self.create_request(site.site_id, req_type=1)
        self.create_request_item(item_req_id, item_id, pack_id, quantity=2)
        item_commit_id = self.create_commit(item_req_id, site_id=site.site_id)
        current.db(s3db.req_commit.id == item_commit_id).update(type=1)

        people_req_id = self.create_request(site.site_id, req_type=3)
        skill_id = self.create_skill("Committed Skill")
        self.create_request_skill(people_req_id,
                                  skill_ids=[skill_id],
                                  quantity=1,
                                  )
        people_commit_id = self.create_commit(people_req_id, site_id=site.site_id)
        current.db(s3db.req_commit.id == people_commit_id).update(type=3)

        other_req_id = self.create_request(site.site_id, req_type=9)
        other_commit_id = self.create_commit(other_req_id,
                                             organisation_id=site.organisation_id,
                                             )
        current.db(s3db.req_commit.id == other_commit_id).update(type=9)

        saved_facilities = auth.permitted_facilities
        saved_orgs = auth.permitted_organisations
        saved_types = current.deployment_settings.get_req_req_type
        saved_actions = response_s3.actions
        saved_jquery = list(response_s3.jquery_ready)
        saved_form = s3db.get_config("req_commit", "crud_form")
        captured = Storage(facilities=[],
                           organisations=[],
                           )

        auth.permitted_facilities = lambda *args, **kwargs: captured.facilities.append(kwargs.get("table"))
        auth.permitted_organisations = lambda *args, **kwargs: captured.organisations.append(kwargs.get("table"))
        current.deployment_settings.get_req_req_type = lambda: ["Stock", "People"]

        try:
            with self.controller("req", function="commit") as controller:
                output = controller.module["commit"]()
                prep = output.prep
                postp = output.postp

                item_record = current.db(s3db.req_commit.id == item_commit_id).select(s3db.req_commit.ALL,
                                                                                      limitby=(0, 1),
                                                                                      ).first()
                item_r = Storage(interactive=True,
                                 record=item_record,
                                 component=None,
                                 table=s3db.req_commit,
                                 )
                self.assertTrue(prep(item_r))
                item_comment = s3db.req_commit.site_id.comment
                item_form = s3db.get_config("req_commit", "crud_form")

                people_record = current.db(s3db.req_commit.id == people_commit_id).select(s3db.req_commit.ALL,
                                                                                          limitby=(0, 1),
                                                                                          ).first()
                people_r = Storage(interactive=True,
                                   record=people_record,
                                   component=None,
                                   table=s3db.req_commit,
                                   )
                self.assertTrue(prep(people_r))
                people_form = s3db.get_config("req_commit", "crud_form")

                other_record = current.db(s3db.req_commit.id == other_commit_id).select(s3db.req_commit.ALL,
                                                                                        limitby=(0, 1),
                                                                                        ).first()
                other_r = Storage(interactive=True,
                                  record=other_record,
                                  component=None,
                                  table=s3db.req_commit,
                                  )
                self.assertTrue(prep(other_r))
                organisation_readable = s3db.req_commit.organisation_id.readable
                site_readable = s3db.req_commit.site_id.readable

                response_s3.actions = []
                globals_ = postp.__globals__
                saved_buttons = globals_["s3_action_buttons"]
                globals_["s3_action_buttons"] = lambda r, **kwargs: None
                try:
                    postp(Storage(interactive=True,
                                  method=None,
                                  component=None,
                                  table=s3db.req_commit,
                                  function="commit",
                                  get_vars=Storage(),
                                  ),
                          {})
                finally:
                    globals_["s3_action_buttons"] = saved_buttons
                labels = [str(action["label"]) for action in response_s3.actions]
        finally:
            auth.permitted_facilities = saved_facilities
            auth.permitted_organisations = saved_orgs
            current.deployment_settings.get_req_req_type = saved_types
            response_s3.actions = saved_actions
            response_s3.jquery_ready = saved_jquery
            s3db.configure("req_commit", crud_form=saved_form)

        self.assertIsNotNone(item_comment)
        self.assertIsNotNone(item_form)
        self.assertIsNotNone(people_form)
        self.assertTrue(organisation_readable)
        self.assertFalse(site_readable)
        self.assertTrue(captured.facilities)
        self.assertTrue(captured.organisations)
        self.assertIn("Prepare Shipment", labels)

    # -------------------------------------------------------------------------
    def testCommitRheaderBuildsTypeSpecificTabsAndFooter(self):
        """commit_rheader exposes item and people tabs according to commitment type"""

        auth = current.auth
        response_s3 = current.response.s3
        s3db = current.s3db

        office = self.create_office(name="Header Site")
        item_req_id = self.create_request(office.site_id, req_type=1)
        item_commit_id = self.create_commit(item_req_id, site_id=office.site_id)
        current.db(s3db.req_commit.id == item_commit_id).update(type=1)

        people_req_id = self.create_request(office.site_id, req_type=3)
        people_commit_id = self.create_commit(people_req_id,
                                              organisation_id=office.organisation_id,
                                              )
        current.db(s3db.req_commit.id == people_commit_id).update(type=3)

        saved_commit_people = current.deployment_settings.get_req_commit_people
        saved_permission = auth.s3_has_permission
        saved_footer = response_s3.rfooter

        current.deployment_settings.get_req_commit_people = lambda: True
        auth.s3_has_permission = lambda *args, **kwargs: True

        try:
            with self.controller("req", function="commit_rheader") as controller:
                globals_ = controller.module["commit_rheader"].__globals__
                saved_tabs = globals_["s3_rheader_tabs"]
                saved_settings = globals_["settings"]
                globals_["s3_rheader_tabs"] = lambda r, tabs: "TABS:%s" % ",".join(str(t[0]) for t in tabs)
                globals_["settings"] = Storage(get_req_commit_people=lambda: True)
                item_record = current.db(s3db.req_commit.id == item_commit_id).select(s3db.req_commit.ALL,
                                                                                      limitby=(0, 1),
                                                                                      ).first()
                try:
                    item_rheader = controller.module["commit_rheader"](Storage(representation="html",
                                                                               record=item_record,
                                                                               name="commit",
                                                                               table=s3db.req_commit,
                                                                               id=item_commit_id,
                                                                               resource=Storage(get_config=lambda key: False),
                                                                               get_vars=Storage(),
                                                                               ))
                    item_footer = response_s3.rfooter

                    people_record = current.db(s3db.req_commit.id == people_commit_id).select(s3db.req_commit.ALL,
                                                                                              limitby=(0, 1),
                                                                                              ).first()
                    response_s3.rfooter = None
                    people_rheader = controller.module["commit_rheader"](Storage(representation="html",
                                                                                 record=people_record,
                                                                                 name="commit",
                                                                                 table=s3db.req_commit,
                                                                                 id=people_commit_id,
                                                                                 resource=Storage(get_config=lambda key: False),
                                                                                 get_vars=Storage(),
                                                                                 ))
                finally:
                    globals_["s3_rheader_tabs"] = saved_tabs
                    globals_["settings"] = saved_settings
        finally:
            current.deployment_settings.get_req_commit_people = saved_commit_people
            auth.s3_has_permission = saved_permission
            response_s3.rfooter = saved_footer

        self.assertIn("Prepare Shipment", str(item_footer))
        self.assertIn("Items", str(item_rheader))
        self.assertIn("People", str(people_rheader))
        self.assertIn("Assign", str(people_rheader))


# =============================================================================
if __name__ == "__main__":

    run_suite(
        ReqRepresentationTests,
        ReqStatusTests,
        ReqCallbackTests,
        ReqHelperTests,
        ReqSendCommitTests,
        ReqWorkflowMethodTests,
        ReqControllerTests,
    )

# END ========================================================================
