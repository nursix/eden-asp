# REQ Unit Tests
#
# To run this script use:
# python web2py.py -S eden -M -R applications/eden/modules/unit_tests/s3db/req.py
#
import json
import unittest

import core
import datetime

from gluon import A, B, DIV, HTTP, TABLE, current
from gluon.storage import Storage

import s3db.req as req_module
from s3db.req import (CommitItemModel,
                      CommitModel,
                      CommitSkillModel,
                      REQ_STATUS_CANCEL,
                      REQ_STATUS_COMPLETE,
                      REQ_STATUS_NONE,
                      REQ_STATUS_PARTIAL,
                      RequestNeedsContactModel,
                      RequestNeedsModel,
                      RequestNeedsTagModel,
                      RequestItemModel,
                      RequestModel,
                      RequestSkillModel,
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
    def testReqRepresentAcceptsInlineRows(self):
        """Request representation accepts inline rows without querying the database again"""

        s3db = current.s3db

        office = self.create_office(name="Inline Row Office")
        row = Storage(req_ref=None,
                      site_id=office.site_id,
                      date=datetime.date(2026, 3, 8),
                      )

        representation = RequestModel.req_represent(1, row=row, show_link=False)
        expected = "%s - %s" % (s3db.req_req.site_id.represent(office.site_id, show_link=False),
                                 s3db.req_req.date.represent(row.date),
                                 )

        self.assertEqual(str(representation), str(expected))

    # -------------------------------------------------------------------------
    def testReqRepresentLinksAndCommitStatusFormatting(self):
        """Request representation supports PDF links and complete-commit status styling"""

        office = self.create_office(name="Req Link Office")
        req_id = self.create_request(office.site_id,
                                     req_ref="REQ-LINK-001",
                                     )

        link = RequestModel.req_represent(req_id, pdf=True)
        status = RequestModel.req_commit_status_represent(REQ_STATUS_COMPLETE)
        unknown = RequestModel.req_commit_status_represent(-1)

        self.assertTrue(isinstance(link, A))
        self.assertEqual(link.attributes["_href"],
                         "/%s/req/req/%s/form" % (current.request.application, req_id))
        self.assertEqual(link.attributes["_title"], "Open PDF")
        self.assertEqual(RequestModel.req_represent(None, show_link=False),
                         current.messages["NONE"])
        self.assertEqual(status.attributes["_class"], "req_status_complete")
        self.assertEqual(status.components[0], "Complete")
        self.assertEqual(unknown, current.messages.UNKNOWN_OPT)

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
    def testCustomRepresentersHandleBulkLookupsAndFallbackRows(self):
        """Custom representers cover bulk lookups, fallback rows and alternate links"""

        settings = current.deployment_settings
        s3db = current.s3db
        db = current.db

        office = self.create_office(name="Bulk Represent Office")
        person_a = self.create_person(first_name="Anna", last_name="Bulk")
        person_b = self.create_person(first_name="Bob", last_name="Bulk")
        self.create_contact(person_a, "+48111222333")

        item_a = self.create_supply_item(name="Bulk Item A")
        item_b = self.create_supply_item(name="Bulk Item B")
        pack_a = self.create_item_pack(item_a, quantity=1)
        pack_b = self.create_item_pack(item_b, quantity=1)
        req_id = self.create_request(office.site_id)
        req_item_a = self.create_request_item(req_id, item_a, pack_a, quantity=1)
        req_item_b = self.create_request_item(req_id, item_b, pack_b, quantity=2)

        item_commit_id = self.create_commit(req_id,
                                            site_id=office.site_id,
                                            )
        org_commit_id = self.create_commit(req_id,
                                           organisation_id=office.organisation_id,
                                           )
        db(s3db.req_commit.id == item_commit_id).update(type=1)
        db(s3db.req_commit.id == org_commit_id).update(type=9)

        requester_repr = req_RequesterRepresent(show_link=False)
        requester_repr.table = s3db.pr_person
        item_repr = req_ReqItemRepresent()
        item_repr.table = s3db.req_req_item
        commit_repr = req_CommitRepresent()
        commit_repr.table = s3db.req_commit

        saved_has_module = settings.has_module
        saved_site_represent = s3db.req_commit.site_id.represent
        saved_org_represent = s3db.req_commit.organisation_id.represent

        class BulkRepresent:
            """Minimal bulk-capable representer for lookup assertions"""

            def __init__(self, prefix):

                self.prefix = prefix
                self.calls = []

            def bulk(self, values):

                self.calls.append(sorted(values))

            def __call__(self, value):

                return "%s-%s" % (self.prefix, value)

        site_represent = BulkRepresent("SITE")
        org_represent = BulkRepresent("ORG")

        settings.has_module = lambda module: False
        s3db.req_commit.site_id.represent = site_represent
        s3db.req_commit.organisation_id.represent = org_represent

        try:
            rows = requester_repr.lookup_rows(None, [person_a, person_b])
            req_items = item_repr.lookup_rows(None, [req_item_a, req_item_b])
            commits = commit_repr.lookup_rows(None, [item_commit_id, org_commit_id])

            fallback_row = db(s3db.pr_person.id == person_b).select(s3db.pr_person.first_name,
                                                                    s3db.pr_person.middle_name,
                                                                    s3db.pr_person.last_name,
                                                                    limitby=(0, 1),
                                                                    ).first()
            fallback_person = requester_repr.represent_row(fallback_row)
            volunteer_link = requester_repr.link(person_a,
                                                 "Volunteer",
                                                 row=Storage(hrm_human_resource=Storage(type=2)),
                                                 )
            fallback_item = item_repr.represent_row(type("Row", (), {"id": req_item_a})())
            undated_commit = commit_repr.represent_row(Storage(organisation_id=None,
                                                               date=None,
                                                               ))
        finally:
            settings.has_module = saved_has_module
            s3db.req_commit.site_id.represent = saved_site_represent
            s3db.req_commit.organisation_id.represent = saved_org_represent

        self.assertEqual(len(rows), 2)
        self.assertEqual(len(req_items), 2)
        self.assertEqual(len(commits), 2)
        self.assertEqual(site_represent.calls, [[office.site_id]])
        self.assertEqual(org_represent.calls, [[office.organisation_id]])
        self.assertIn("Bob Bulk", str(fallback_person))
        self.assertEqual(volunteer_link.attributes["_href"],
                         "/%s/vol/person/%s/contacts" % (current.request.application,
                                                          person_a,
                                                          ))
        self.assertEqual(fallback_item, str(req_item_a))
        self.assertEqual(str(undated_commit), "undated")

    # -------------------------------------------------------------------------
    def testRepresentersHandleSparseContactsAndUnknownCommitTypes(self):
        """Custom representers degrade cleanly for sparse rows and unknown commit types"""

        s3db = current.s3db

        requester_repr = req_RequesterRepresent(show_link=False)
        requester_repr.table = s3db.pr_person
        commit_repr = req_CommitRepresent()
        commit_repr.table = s3db.req_commit

        person = Storage(first_name="No",
                         middle_name=None,
                         last_name="Contact",
                         )
        requester = requester_repr.represent_row(Storage(pr_person=person,
                                                         pr_contact=Storage(),
                                                         ))
        fallback_link = requester_repr.link(1,
                                            "Person",
                                            row=Storage(hrm_human_resource=Storage()),
                                            )
        unknown_commit = commit_repr.represent_row(Storage(date=datetime.date(2026, 3, 8),
                                                           organisation_id=1,
                                                           ))

        self.assertIn("No Contact", str(requester))
        self.assertEqual(fallback_link.attributes["_href"],
                         "/%s/pr/person/1/contacts" % current.request.application)
        self.assertIn("organization1", str(unknown_commit))
        self.assertTrue("2026-03-08" in str(unknown_commit) or
                        "08:00" in str(unknown_commit))

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
class ReqConfigurationTests(SupplyChainTestCase):
    """Tests for req model configuration branches"""

    # -------------------------------------------------------------------------
    @staticmethod
    def _reload_model(model_class, name, *tablenames):
        """Reload a req DataModel after changing deployment settings"""

        s3db = current.s3db

        for tablename in tablenames:
            s3db.clear_config(tablename)

        loaded = current.response.get("eden_model_load")
        if loaded:
            while name in loaded:
                loaded.remove(name)

        model_class("req")

    # -------------------------------------------------------------------------
    def testNeedModelsConfigureDefaultsAndGenerateReferences(self):
        """Need models expose defaults and generate assessment references onaccept"""

        db = current.db
        s3db = current.s3db

        self._reload_model(RequestNeedsModel,
                           "RequestNeedsModel",
                           "req_need",
                           "req_need_site_type",
                           )
        self._reload_model(RequestNeedsContactModel,
                           "RequestNeedsContactModel",
                           "req_need_contact",
                           )
        self._reload_model(RequestNeedsTagModel,
                           "RequestNeedsTagModel",
                           "req_need_tag",
                           )

        defaults = RequestNeedsModel("req").defaults()
        self.assertEqual(defaults["req_need_id"]().name, "need_id")

        need_id = s3db.req_need.insert(site_name="Test Need Site")
        RequestNeedsModel.need_onaccept(self.make_form(id=need_id))

        need = db(s3db.req_need.id == need_id).select(s3db.req_need.refno,
                                                      limitby=(0, 1),
                                                      ).first()
        self.assertEqual(need.refno, "NE%05d" % need_id)

        # Missing or unknown record IDs must be ignored cleanly
        RequestNeedsModel.need_onaccept(self.make_form())
        RequestNeedsModel.need_onaccept(self.make_form(id=99999999))

        self.assertIsNotNone(s3db.get_config("req_need_contact", "deduplicate"))
        self.assertIsNotNone(s3db.get_config("req_need_tag", "deduplicate"))

    # -------------------------------------------------------------------------
    def testRequestModelConfiguresItemWorkflowAuthorDefaultsAndFilters(self):
        """Request model reloads cleanly under item-workflow settings and still exposes core configs"""

        settings = current.deployment_settings
        auth = current.auth
        request = current.request

        office = self.create_office(name="Request Defaults Office")
        person_id = self.create_person(last_name="Requester")

        saved_has_module = settings.has_module
        saved_req_types = settings.get_req_req_type
        saved_inv_label = settings.get_req_type_inv_label
        saved_hrm_label = settings.get_req_type_hrm_label
        saved_requester_author = settings.get_req_requester_is_author
        saved_site_autocomplete = settings.get_org_site_autocomplete
        saved_workflow = settings.get_req_workflow
        saved_use_req_number = settings.get_req_use_req_number
        saved_use_commit = settings.get_req_use_commit
        saved_transit_status = settings.get_req_show_quantity_transit
        saved_logged_in = auth.s3_logged_in
        saved_logged_in_person = auth.s3_logged_in_person
        saved_user = auth.user
        saved_get_vars = request.get_vars

        try:
            settings.has_module = lambda module: module in ("inv", "hrm")
            settings.get_req_req_type = lambda: ["Stock", "People", "Other"]
            settings.get_req_type_inv_label = lambda: "Stock"
            settings.get_req_type_hrm_label = lambda: "People"
            settings.get_req_requester_is_author = lambda: True
            settings.get_org_site_autocomplete = lambda: True
            settings.get_req_workflow = lambda: True
            settings.get_req_use_req_number = lambda: True
            settings.get_req_use_commit = lambda: True
            settings.get_req_show_quantity_transit = lambda: True
            auth.s3_logged_in = lambda: True
            auth.s3_logged_in_person = lambda: person_id
            auth.user = Storage(site_id=office.site_id)
            request.get_vars = Storage(type="1")

            self._reload_model(RequestModel,
                               "RequestModel",
                               "req_req",
                               )

            filter_widgets = current.s3db.get_config("req_req", "filter_widgets")
            list_fields = current.s3db.get_config("req_req", "list_fields")
            report_options = current.s3db.get_config("req_req", "report_options")

            self.assertTrue(filter_widgets)
            self.assertTrue(list_fields)
            self.assertIsNotNone(report_options)
            self.assertIn("fulfil_status", list_fields)

            defaults = RequestModel("req").defaults()
            self.assertEqual(defaults["req_req_id"]().name, "req_id")
            self.assertEqual(defaults["req_req_ref"]().name, "req_ref")
        finally:
            settings.has_module = saved_has_module
            settings.get_req_req_type = saved_req_types
            settings.get_req_type_inv_label = saved_inv_label
            settings.get_req_type_hrm_label = saved_hrm_label
            settings.get_req_requester_is_author = saved_requester_author
            settings.get_org_site_autocomplete = saved_site_autocomplete
            settings.get_req_workflow = saved_workflow
            settings.get_req_use_req_number = saved_use_req_number
            settings.get_req_use_commit = saved_use_commit
            settings.get_req_show_quantity_transit = saved_transit_status
            auth.s3_logged_in = saved_logged_in
            auth.s3_logged_in_person = saved_logged_in_person
            auth.user = saved_user
            request.get_vars = saved_get_vars
            self._reload_model(RequestModel,
                               "RequestModel",
                               "req_req",
                               )

    # -------------------------------------------------------------------------
    def testRequestModelConfiguresPeopleOnlyWorkflowWithoutCommit(self):
        """Request model reloads cleanly when only people requests are deployed"""

        settings = current.deployment_settings
        auth = current.auth
        request = current.request

        saved_has_module = settings.has_module
        saved_req_types = settings.get_req_req_type
        saved_requester_author = settings.get_req_requester_is_author
        saved_site_autocomplete = settings.get_org_site_autocomplete
        saved_workflow = settings.get_req_workflow
        saved_use_req_number = settings.get_req_use_req_number
        saved_use_commit = settings.get_req_use_commit
        saved_transit_status = settings.get_req_show_quantity_transit
        saved_logged_in = auth.s3_logged_in
        saved_logged_in_person = auth.s3_logged_in_person
        saved_user = auth.user
        saved_get_vars = request.get_vars

        try:
            settings.has_module = lambda module: module == "hrm"
            settings.get_req_req_type = lambda: ["People"]
            settings.get_req_requester_is_author = lambda: False
            settings.get_org_site_autocomplete = lambda: False
            settings.get_req_workflow = lambda: False
            settings.get_req_use_req_number = lambda: False
            settings.get_req_use_commit = lambda: False
            settings.get_req_show_quantity_transit = lambda: False
            auth.s3_logged_in = lambda: False
            auth.s3_logged_in_person = lambda: None
            auth.user = None
            request.get_vars = Storage()

            self._reload_model(RequestModel,
                               "RequestModel",
                               "req_req",
                               )
            filter_widgets = current.s3db.get_config("req_req", "filter_widgets")
            list_fields = current.s3db.get_config("req_req", "list_fields")
            report_options = current.s3db.get_config("req_req", "report_options")

            self.assertTrue(filter_widgets)
            self.assertTrue(list_fields)
            self.assertIsNotNone(report_options)
            self.assertIn("fulfil_status", list_fields)
        finally:
            settings.has_module = saved_has_module
            settings.get_req_req_type = saved_req_types
            settings.get_req_requester_is_author = saved_requester_author
            settings.get_org_site_autocomplete = saved_site_autocomplete
            settings.get_req_workflow = saved_workflow
            settings.get_req_use_req_number = saved_use_req_number
            settings.get_req_use_commit = saved_use_commit
            settings.get_req_show_quantity_transit = saved_transit_status
            auth.s3_logged_in = saved_logged_in
            auth.s3_logged_in_person = saved_logged_in_person
            auth.user = saved_user
            request.get_vars = saved_get_vars
            self._reload_model(RequestModel,
                               "RequestModel",
                               "req_req",
                               )

    # -------------------------------------------------------------------------
    def testRequestModelConfiguresSingleTypeDefaultsAndAutocomplete(self):
        """Single-type deployments with site autocomplete reload cleanly"""

        settings = current.deployment_settings
        auth = current.auth
        request = current.request
        s3db = current.s3db

        office = self.create_office(name="Single Type Office")
        person_id = self.create_person(last_name="Single Type Requester")

        saved_has_module = settings.has_module
        saved_req_types = settings.get_req_req_type
        saved_inv_label = settings.get_req_type_inv_label
        saved_requester_author = settings.get_req_requester_is_author
        saved_site_autocomplete = settings.get_org_site_autocomplete
        saved_workflow = settings.get_req_workflow
        saved_logged_in = auth.s3_logged_in
        saved_logged_in_person = auth.s3_logged_in_person
        saved_user = auth.user
        saved_get_vars = request.get_vars

        try:
            settings.has_module = lambda module: module == "inv"
            settings.get_req_req_type = lambda: ["Stock"]
            settings.get_req_type_inv_label = lambda: "Stock"
            settings.get_req_requester_is_author = lambda: True
            settings.get_org_site_autocomplete = lambda: True
            settings.get_req_workflow = lambda: True
            auth.s3_logged_in = lambda: True
            auth.s3_logged_in_person = lambda: person_id
            auth.user = Storage(site_id=office.site_id)
            request.get_vars = Storage()

            self._reload_model(RequestModel,
                               "RequestModel",
                               "req_req",
                               )

            table = s3db.req_req
            self.assertEqual(table._tablename, "req_req")
            self.assertIsNotNone(s3db.get_config("req_req", "list_fields"))
        finally:
            settings.has_module = saved_has_module
            settings.get_req_req_type = saved_req_types
            settings.get_req_type_inv_label = saved_inv_label
            settings.get_req_requester_is_author = saved_requester_author
            settings.get_org_site_autocomplete = saved_site_autocomplete
            settings.get_req_workflow = saved_workflow
            auth.s3_logged_in = saved_logged_in
            auth.s3_logged_in_person = saved_logged_in_person
            auth.user = saved_user
            request.get_vars = saved_get_vars
            self._reload_model(RequestModel,
                               "RequestModel",
                               "req_req",
                               )


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

    # -------------------------------------------------------------------------
    def testReqUpdateCommitQuantitiesAndStatusPreservesUnchangedRows(self):
        """Status recalculation leaves unchanged item and skill commitments untouched"""

        db = current.db
        s3db = current.s3db

        office = self.create_office()
        item_id = self.create_supply_item(name="Stable Item")
        pack_id = self.create_item_pack(item_id, quantity=2)

        # Item requests should not update rows or request status when nothing changed
        item_req_id = self.create_request(office.site_id,
                                          req_type=1,
                                          commit_status=REQ_STATUS_COMPLETE,
                                          )
        req_item_id = self.create_request_item(item_req_id,
                                               item_id,
                                               pack_id,
                                               quantity=3,
                                               quantity_commit=6,
                                               )
        item_commit_id = self.create_commit(item_req_id,
                                            site_id=office.site_id,
                                            organisation_id=office.organisation_id,
                                            )
        self.create_commit_item(item_commit_id, req_item_id, pack_id, quantity=3)

        rtable = s3db.req_req
        ritable = s3db.req_req_item

        req = db(rtable.id == item_req_id).select(rtable.id,
                                                  rtable.type,
                                                  rtable.commit_status,
                                                  limitby=(0, 1),
                                                  ).first()
        req_update_commit_quantities_and_status(req)

        row = db(ritable.id == req_item_id).select(ritable.quantity_commit,
                                                   limitby=(0, 1),
                                                   ).first()
        status = db(rtable.id == item_req_id).select(rtable.commit_status,
                                                     limitby=(0, 1),
                                                     ).first()

        self.assertEqual(row.quantity_commit, 6)
        self.assertEqual(status.commit_status, REQ_STATUS_COMPLETE)

        # Skill requests should remain NONE when available skills never match
        request_skill = self.create_skill("Requested Skill")
        other_skill = self.create_skill("Other Skill")
        skill_req_id = self.create_request(office.site_id,
                                           req_type=3,
                                           commit_status=REQ_STATUS_NONE,
                                           )
        req_skill_id = self.create_request_skill(skill_req_id,
                                                 skill_ids=[request_skill],
                                                 quantity=1,
                                                 quantity_commit=0,
                                                 )
        skill_commit_id = self.create_commit(skill_req_id,
                                             site_id=office.site_id,
                                             organisation_id=office.organisation_id,
                                             )
        self.create_commit_skill(skill_commit_id,
                                 skill_ids=[other_skill],
                                 quantity=1,
                                 )
        self.create_commit_skill(skill_commit_id,
                                 skill_ids=[request_skill],
                                 quantity=0,
                                 )

        req = db(rtable.id == skill_req_id).select(rtable.id,
                                                   rtable.type,
                                                   rtable.commit_status,
                                                   limitby=(0, 1),
                                                   ).first()
        req_update_commit_quantities_and_status(req)

        stable = s3db.req_req_skill
        row = db(stable.id == req_skill_id).select(stable.quantity_commit,
                                                   limitby=(0, 1),
                                                   ).first()
        status = db(rtable.id == skill_req_id).select(rtable.commit_status,
                                                      limitby=(0, 1),
                                                      ).first()

        self.assertEqual(row.quantity_commit, 0)
        self.assertEqual(status.commit_status, REQ_STATUS_NONE)


# =============================================================================
class ReqCallbackTests(SupplyChainTestCase):
    """Tests for req/commit onaccept and ondelete callbacks"""

    # -------------------------------------------------------------------------
    def testReqOnacceptGeneratesRequestNumberUpdatesStatusesAndLinksRequester(self):
        """Request onaccept generates req_ref, translates simple status and links the requester to the site"""

        db = current.db
        s3db = current.s3db
        settings = current.deployment_settings
        # Build one item request that needs a generated reference and site-contact creation
        office = self.create_office(code="REQ1")
        requester_id = self.create_person(last_name="Site Contact")
        req_id = self.create_request(office.site_id,
                                     req_type=1,
                                     req_ref=None,
                                     requester_id=requester_id,
                                     req_status=REQ_STATUS_PARTIAL,
                                     commit_status=REQ_STATUS_NONE,
                                     fulfil_status=REQ_STATUS_COMPLETE,
                                     )

        saved_use_number = settings.req.get("use_req_number")
        saved_shortname = settings.req.get("shortname")
        saved_requester_to_site = settings.req.get("requester_to_site")
        saved_inline_forms = settings.req.get("inline_forms")
        saved_has_module = settings.has_module
        saved_hrm_onaccept = s3db.hrm_human_resource_onaccept
        saved_create_next = s3db.get_config("req_req", "create_next")
        saved_update_next = s3db.get_config("req_req", "update_next")
        hrm_onaccept_calls = []

        try:
            # Force the callback through the request-number and requester-to-site branches
            settings.req.use_req_number = True
            settings.req.shortname = "REQ"
            settings.req.requester_to_site = True
            settings.req.inline_forms = False
            settings.has_module = lambda module: module == "inv"
            s3db.hrm_human_resource_onaccept = lambda row: hrm_onaccept_calls.append(row.id)

            RequestModel.req_onaccept(self.make_form(id=req_id))
        finally:
            settings.req.use_req_number = saved_use_number
            settings.req.shortname = saved_shortname
            settings.req.requester_to_site = saved_requester_to_site
            settings.req.inline_forms = saved_inline_forms
            settings.has_module = saved_has_module
            s3db.hrm_human_resource_onaccept = saved_hrm_onaccept

        try:
            # Verify the generated reference, translated statuses and site-contact linkage
            req = db(s3db.req_req.id == req_id).select(s3db.req_req.req_ref,
                                                       s3db.req_req.commit_status,
                                                       s3db.req_req.fulfil_status,
                                                       limitby=(0, 1),
                                                       ).first()
            hr = db(s3db.hrm_human_resource.person_id == requester_id).select(
                        s3db.hrm_human_resource.id,
                        s3db.hrm_human_resource.site_id,
                        s3db.hrm_human_resource.organisation_id,
                        s3db.hrm_human_resource.site_contact,
                        limitby=(0, 1),
                        ).first()
            create_next = s3db.get_config("req_req", "create_next")
            update_next = s3db.get_config("req_req", "update_next")

            self.assertEqual(req.req_ref, "REQ-REQ1-000001")
            self.assertEqual(req.commit_status, REQ_STATUS_PARTIAL)
            self.assertEqual(req.fulfil_status, REQ_STATUS_PARTIAL)
            self.assertIsNotNone(hr)
            self.assertEqual(hr.site_id, office.site_id)
            self.assertEqual(hr.organisation_id, office.organisation_id)
            self.assertTrue(hr.site_contact)
            self.assertEqual(hrm_onaccept_calls, [hr.id])
            self.assertIn("/req/req/%5Bid%5D/req_item", str(create_next))
            self.assertIn("/req/req/%5Bid%5D/req_item", str(update_next))
        finally:
            s3db.configure("req_req",
                           create_next=saved_create_next,
                           update_next=saved_update_next,
                           )

    # -------------------------------------------------------------------------
    def testReqOnacceptCancelsRequestsForCancelledSimpleStatus(self):
        """Request onaccept translates cancelled simple status into the workflow cancel state"""

        db = current.db
        s3db = current.s3db
        settings = current.deployment_settings

        # Build one request using the simple status selector with a cancelled status
        office = self.create_office()
        req_id = self.create_request(office.site_id,
                                     req_status=REQ_STATUS_CANCEL,
                                     cancel=False,
                                     )

        saved_use_number = settings.req.get("use_req_number")
        saved_requester_to_site = settings.req.get("requester_to_site")
        saved_inline_forms = settings.req.get("inline_forms")

        try:
            settings.req.use_req_number = False
            settings.req.requester_to_site = False
            settings.req.inline_forms = True

            RequestModel.req_onaccept(self.make_form(id=req_id))
        finally:
            settings.req.use_req_number = saved_use_number
            settings.req.requester_to_site = saved_requester_to_site
            settings.req.inline_forms = saved_inline_forms

        req = db(s3db.req_req.id == req_id).select(s3db.req_req.cancel,
                                                   s3db.req_req.workflow_status,
                                                   limitby=(0, 1),
                                                   ).first()
        self.assertTrue(req.cancel)
        self.assertEqual(req.workflow_status, 5)

    # -------------------------------------------------------------------------
    def testReqOnacceptAssignsExistingRequesterHrRecordToTheRequestSite(self):
        """Request onaccept assigns an existing HR record to the request site when the organisation matches"""

        db = current.db
        s3db = current.s3db
        settings = current.deployment_settings

        # Create one requester with an HR record in the same organisation but without a site assignment
        office = self.create_office()
        requester_id = self.create_person(last_name="Existing HR")
        hr_id = s3db.hrm_human_resource.insert(person_id=requester_id,
                                               organisation_id=office.organisation_id,
                                               site_id=None,
                                               site_contact=False,
                                               )
        req_id = self.create_request(office.site_id,
                                     requester_id=requester_id,
                                     )

        saved_use_number = settings.req.get("use_req_number")
        saved_requester_to_site = settings.req.get("requester_to_site")
        saved_inline_forms = settings.req.get("inline_forms")
        saved_hrm_onaccept = s3db.hrm_human_resource_onaccept
        onaccept_calls = []

        try:
            # Drive the branch that updates an existing HR record instead of inserting a new one
            settings.req.use_req_number = False
            settings.req.requester_to_site = True
            settings.req.inline_forms = True
            s3db.hrm_human_resource_onaccept = lambda row: onaccept_calls.append(row.id)

            RequestModel.req_onaccept(self.make_form(id=req_id))
        finally:
            settings.req.use_req_number = saved_use_number
            settings.req.requester_to_site = saved_requester_to_site
            settings.req.inline_forms = saved_inline_forms
            s3db.hrm_human_resource_onaccept = saved_hrm_onaccept

        hr = db(s3db.hrm_human_resource.id == hr_id).select(s3db.hrm_human_resource.site_id,
                                                            limitby=(0, 1),
                                                            ).first()
        self.assertEqual(hr.site_id, office.site_id)
        self.assertEqual(onaccept_calls, [hr_id])

    # -------------------------------------------------------------------------
    def testReqOnacceptAvoidsDuplicatePrimarySiteContacts(self):
        """Request onaccept creates non-primary HR contacts when the site already has a primary contact"""

        db = current.db
        s3db = current.s3db
        settings = current.deployment_settings

        office = self.create_office(name="Primary Contact Site")
        primary_person = self.create_person(last_name="Primary Contact")
        requester_id = self.create_person(last_name="Secondary Contact")

        hrtable = s3db.hrm_human_resource
        primary_hr_id = hrtable.insert(person_id=primary_person,
                                       organisation_id=office.organisation_id,
                                       site_id=office.site_id,
                                       site_contact=True,
                                       )
        s3db.hrm_human_resource_onaccept(Storage(id=primary_hr_id))

        req_id = self.create_request(office.site_id,
                                     requester_id=requester_id,
                                     )

        saved_use_number = settings.req.get("use_req_number")
        saved_requester_to_site = settings.req.get("requester_to_site")
        saved_inline_forms = settings.req.get("inline_forms")

        try:
            settings.req.use_req_number = False
            settings.req.requester_to_site = True
            settings.req.inline_forms = True

            RequestModel.req_onaccept(self.make_form(id=req_id))
        finally:
            settings.req.use_req_number = saved_use_number
            settings.req.requester_to_site = saved_requester_to_site
            settings.req.inline_forms = saved_inline_forms

        hr = db(hrtable.person_id == requester_id).select(hrtable.site_id,
                                                          hrtable.site_contact,
                                                          limitby=(0, 1),
                                                          ).first()
        self.assertIsNotNone(hr)
        self.assertEqual(hr.site_id, office.site_id)
        self.assertFalse(hr.site_contact)

    # -------------------------------------------------------------------------
    def testReqOnacceptLeavesForeignOrganisationHrRecordsUnchanged(self):
        """Request onaccept does not assign existing HR records to sites in other organisations"""

        db = current.db
        s3db = current.s3db
        settings = current.deployment_settings

        office = self.create_office(name="Target Site")
        foreign_org = self.create_organisation(name="Foreign Org")
        requester_id = self.create_person(last_name="Foreign HR")
        hr_id = s3db.hrm_human_resource.insert(person_id=requester_id,
                                               organisation_id=foreign_org,
                                               site_id=None,
                                               site_contact=False,
                                               )
        req_id = self.create_request(office.site_id,
                                     requester_id=requester_id,
                                     )

        saved_use_number = settings.req.get("use_req_number")
        saved_requester_to_site = settings.req.get("requester_to_site")
        saved_inline_forms = settings.req.get("inline_forms")
        saved_hrm_onaccept = s3db.hrm_human_resource_onaccept
        onaccept_calls = []

        try:
            settings.req.use_req_number = False
            settings.req.requester_to_site = True
            settings.req.inline_forms = True
            s3db.hrm_human_resource_onaccept = lambda row: onaccept_calls.append(row.id)

            RequestModel.req_onaccept(self.make_form(id=req_id))
        finally:
            settings.req.use_req_number = saved_use_number
            settings.req.requester_to_site = saved_requester_to_site
            settings.req.inline_forms = saved_inline_forms
            s3db.hrm_human_resource_onaccept = saved_hrm_onaccept

        hr = db(s3db.hrm_human_resource.id == hr_id).select(s3db.hrm_human_resource.site_id,
                                                            limitby=(0, 1),
                                                            ).first()
        self.assertIsNone(hr.site_id)
        self.assertEqual(onaccept_calls, [])

    # -------------------------------------------------------------------------
    def testReqOnacceptUsesWorkflowCancelForExplicitCancelFlag(self):
        """Request onaccept translates explicit cancel flags into workflow cancel state"""

        db = current.db
        s3db = current.s3db
        settings = current.deployment_settings

        office = self.create_office(name="Cancel Site")
        req_id = self.create_request(office.site_id,
                                     req_status=None,
                                     cancel=True,
                                     workflow_status=2,
                                     )

        saved_use_number = settings.req.get("use_req_number")
        saved_requester_to_site = settings.req.get("requester_to_site")
        saved_inline_forms = settings.req.get("inline_forms")

        try:
            settings.req.use_req_number = False
            settings.req.requester_to_site = False
            settings.req.inline_forms = True

            RequestModel.req_onaccept(self.make_form(id=req_id))
        finally:
            settings.req.use_req_number = saved_use_number
            settings.req.requester_to_site = saved_requester_to_site
            settings.req.inline_forms = saved_inline_forms

        req = db(s3db.req_req.id == req_id).select(s3db.req_req.workflow_status,
                                                   limitby=(0, 1),
                                                   ).first()
        self.assertEqual(req.workflow_status, 5)

    # -------------------------------------------------------------------------
    def testReqOnacceptHandlesCompleteStatusAndExplicitCancelWithoutSimpleCancelOption(self):
        """Request onaccept completes requests and falls back to workflow cancel when needed"""

        db = current.db
        s3db = current.s3db
        settings = current.deployment_settings

        office = self.create_office(name="Completion Site")
        complete_id = self.create_request(office.site_id,
                                          req_status=REQ_STATUS_COMPLETE,
                                          fulfil_status=REQ_STATUS_NONE,
                                          )
        cancel_id = self.create_request(office.site_id,
                                        req_status=REQ_STATUS_PARTIAL,
                                        cancel=True,
                                        workflow_status=2,
                                        )

        table = s3db.req_req
        saved_requires = table.req_status.requires
        saved_use_number = settings.req.get("use_req_number")
        saved_requester_to_site = settings.req.get("requester_to_site")
        saved_inline_forms = settings.req.get("inline_forms")

        class FakeRequires:
            @staticmethod
            def options():
                return [("0", "None"),
                        ("1", "Partial"),
                        ("2", "Complete"),
                        ]

        try:
            settings.req.use_req_number = False
            settings.req.requester_to_site = False
            settings.req.inline_forms = True
            table.req_status.requires = Storage(other=FakeRequires())

            RequestModel.req_onaccept(self.make_form(id=complete_id))
            RequestModel.req_onaccept(self.make_form(id=cancel_id))
        finally:
            table.req_status.requires = saved_requires
            settings.req.use_req_number = saved_use_number
            settings.req.requester_to_site = saved_requester_to_site
            settings.req.inline_forms = saved_inline_forms

        complete = db(table.id == complete_id).select(table.fulfil_status,
                                                      limitby=(0, 1),
                                                      ).first()
        cancelled = db(table.id == cancel_id).select(table.workflow_status,
                                                     limitby=(0, 1),
                                                     ).first()

        self.assertEqual(complete.fulfil_status, REQ_STATUS_COMPLETE)
        self.assertEqual(cancelled.workflow_status, 5)

    # -------------------------------------------------------------------------
    def testReqOnacceptConfiguresTemplateInlineFormsForScheduleTab(self):
        """Template requests with inline forms return to the schedule tab after save"""

        db = current.db
        s3db = current.s3db
        settings = current.deployment_settings

        office = self.create_office(name="Template Inline Site")
        req_id = self.create_request(office.site_id,
                                     req_type=1,
                                     is_template=True,
                                     )

        saved_use_number = settings.req.get("use_req_number")
        saved_requester_to_site = settings.req.get("requester_to_site")
        saved_inline_forms = settings.req.get("inline_forms")
        saved_create_next = s3db.get_config("req_req", "create_next")
        saved_update_next = s3db.get_config("req_req", "update_next")

        try:
            settings.req.use_req_number = False
            settings.req.requester_to_site = False
            settings.req.inline_forms = True

            RequestModel.req_onaccept(self.make_form(id=req_id))

            create_next = s3db.get_config("req_req", "create_next")
            update_next = s3db.get_config("req_req", "update_next")
        finally:
            settings.req.use_req_number = saved_use_number
            settings.req.requester_to_site = saved_requester_to_site
            settings.req.inline_forms = saved_inline_forms
            s3db.configure("req_req",
                           create_next=saved_create_next,
                           update_next=saved_update_next,
                           )

        self.assertIn("/req/req_template/%5Bid%5D/job", str(create_next))
        self.assertIn("/req/req_template/%5Bid%5D/job", str(update_next))

    # -------------------------------------------------------------------------
    def testReqOnacceptConfiguresSkillNextPageWhenInlineFormsAreDisabled(self):
        """Skill requests without inline forms return to the requested-skills component tab"""

        db = current.db
        s3db = current.s3db
        settings = current.deployment_settings

        office = self.create_office(name="Skill Redirect Site")
        req_id = self.create_request(office.site_id,
                                     req_type=3,
                                     is_template=False,
                                     )

        saved_use_number = settings.req.get("use_req_number")
        saved_requester_to_site = settings.req.get("requester_to_site")
        saved_inline_forms = settings.req.get("inline_forms")
        saved_has_module = settings.has_module
        saved_create_next = s3db.get_config("req_req", "create_next")
        saved_update_next = s3db.get_config("req_req", "update_next")

        try:
            settings.req.use_req_number = False
            settings.req.requester_to_site = False
            settings.req.inline_forms = False
            settings.has_module = lambda module: module == "hrm"

            RequestModel.req_onaccept(self.make_form(id=req_id))

            create_next = s3db.get_config("req_req", "create_next")
            update_next = s3db.get_config("req_req", "update_next")
        finally:
            settings.req.use_req_number = saved_use_number
            settings.req.requester_to_site = saved_requester_to_site
            settings.req.inline_forms = saved_inline_forms
            settings.has_module = saved_has_module
            s3db.configure("req_req",
                           create_next=saved_create_next,
                           update_next=saved_update_next,
                           )

        self.assertIn("/req/req/%5Bid%5D/req_skill", str(create_next))
        self.assertIn("/req/req/%5Bid%5D/req_skill", str(update_next))

    # -------------------------------------------------------------------------
    def testReqReqOndeleteRemovesScheduledTemplateTasks(self):
        """Deleting recurring templates removes only the matching scheduler job"""

        db = current.db

        office = self.create_office(name="Delete Template Site")
        req_id = self.create_request(office.site_id,
                                     is_template=True,
                                     )

        table = db.scheduler_task
        delete_id = table.insert(function_name="req_add_from_template",
                                 args="[%s]" % req_id,
                                 )
        keep_id = table.insert(function_name="req_add_from_template",
                               args="[999999]",
                               )

        RequestModel.req_req_ondelete(Storage(id=req_id))

        self.assertFalse(db(table.id == delete_id).count())
        self.assertTrue(db(table.id == keep_id).count())

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
    def testReqItemOnacceptReloadsReqContextFromRecordId(self):
        """Requested item onaccept reloads req_id from the row when the form only provides the record ID"""

        db = current.db
        s3db = current.s3db

        office = self.create_office(name="Reload Req Context")
        catalog_id = self.create_catalog()
        category_id = self.create_item_category(catalog_id,
                                                name="Reload Category",
                                                code="REL",
                                                )
        item_id = self.create_supply_item(catalog_id=catalog_id,
                                          item_category_id=category_id,
                                          )
        self.create_catalog_item(catalog_id, item_id, item_category_id=category_id)

        req_id = self.create_request(office.site_id)
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               self.create_item_pack(item_id, quantity=1),
                                               quantity=2,
                                               )

        RequestItemModel.req_item_onaccept(self.make_form(id=req_item_id,
                                                          item_id=item_id,
                                                          ))

        ltable = s3db.req_req_item_category
        row = db((ltable.req_id == req_id) &
                 (ltable.item_category_id == category_id),
                 ).select(ltable.id,
                          limitby=(0, 1),
                          ).first()
        self.assertIsNotNone(row)

    # -------------------------------------------------------------------------
    def testReqItemOnacceptReturnsWithoutRequestContext(self):
        """Requested item onaccept exits without side effects when the item has no request context"""

        db = current.db
        ltable = current.s3db.req_req_item_category

        before = db(ltable.id > 0).count()

        RequestItemModel.req_item_onaccept(self.make_form(id=999999,
                                                          item_id=999999,
                                                          ))

        after = db(ltable.id > 0).count()
        self.assertEqual(after, before)

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
    def testReqSkillOnacceptUpdatesStatusesAndCreatesProjectTask(self):
        """Requested skill onaccept updates request statuses and creates a linked project task"""

        db = current.db
        s3db = current.s3db

        location_id = self.create_location(name="Skill Site Location")
        office = self.create_office(location_id=location_id)
        skill_id = self.create_skill("Forklift")
        req_id = self.create_request(office.site_id,
                                     req_type=3,
                                     req_ref="REQ-SKILL-001",
                                     purpose="Unload incoming stock",
                                     priority=3,
                                     )
        req_skill_id = self.create_request_skill(req_id,
                                                 skill_ids=[skill_id],
                                                 quantity=1,
                                                 quantity_commit=1,
                                                 )

        RequestSkillModel.req_skill_onaccept(self.make_form(id=req_skill_id,
                                                            req_id=req_id,
                                                            ))

        req = db(s3db.req_req.id == req_id).select(s3db.req_req.commit_status,
                                                   s3db.req_req.transit_status,
                                                   s3db.req_req.fulfil_status,
                                                   limitby=(0, 1),
                                                   ).first()
        task = db(s3db.project_task.site_id == office.site_id).select(s3db.project_task.id,
                                                                      s3db.project_task.name,
                                                                      s3db.project_task.description,
                                                                      s3db.project_task.priority,
                                                                      s3db.project_task.location_id,
                                                                      limitby=(0, 1),
                                                                      orderby=~s3db.project_task.id,
                                                                      ).first()
        link = db((s3db.req_task_req.req_id == req_id) &
                  (s3db.req_task_req.task_id == task.id)
                  ).select(s3db.req_task_req.id,
                           limitby=(0, 1),
                           ).first()

        self.assertEqual(req.commit_status, REQ_STATUS_COMPLETE)
        self.assertEqual(req.transit_status, REQ_STATUS_NONE)
        self.assertEqual(req.fulfil_status, REQ_STATUS_NONE)
        self.assertEqual(task.name, "REQ-SKILL-001")
        self.assertEqual(task.description, "Unload incoming stock")
        self.assertEqual(task.priority, 3)
        self.assertEqual(task.location_id, location_id)
        self.assertIsNotNone(link)

    # -------------------------------------------------------------------------
    def testReqSkillOnacceptResolvesRequestContextFromSkillRecordId(self):
        """Requested skill onaccept reloads req_id from req_req_skill when the form only provides the record ID"""

        db = current.db
        s3db = current.s3db

        office = self.create_office()
        skill_id = self.create_skill("Driver")
        req_id = self.create_request(office.site_id,
                                     req_type=3,
                                     )
        req_skill_id = self.create_request_skill(req_id,
                                                 skill_ids=[skill_id],
                                                 quantity=2,
                                                 quantity_commit=1,
                                                 )

        RequestSkillModel.req_skill_onaccept(self.make_form(id=req_skill_id))

        req = db(s3db.req_req.id == req_id).select(s3db.req_req.commit_status,
                                                   limitby=(0, 1),
                                                   ).first()
        self.assertEqual(req.commit_status, REQ_STATUS_PARTIAL)

    # -------------------------------------------------------------------------
    def testReqSkillRepresentReturnsSkillNamesAndFallbacks(self):
        """Requested skill representation resolves skill names and cleanly falls back for empty or unknown values"""

        office = self.create_office()
        skill_id = self.create_skill("Radio Operator")
        req_id = self.create_request(office.site_id,
                                     req_type=3,
                                     )
        req_skill_id = self.create_request_skill(req_id,
                                                 skill_ids=[skill_id],
                                                 quantity=1,
                                                 )

        self.assertEqual(RequestSkillModel.req_skill_represent(req_skill_id), "Radio Operator")
        self.assertEqual(RequestSkillModel.req_skill_represent(None), current.messages["NONE"])
        self.assertEqual(RequestSkillModel.req_skill_represent(999999), current.messages.UNKNOWN_OPT)

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
    def testCommitSkillCallbacksUpdateSkillRequestStatus(self):
        """Commit skill callbacks update anonymous skill commitments on add and delete"""

        db = current.db
        s3db = current.s3db

        office = self.create_office()
        skill_id = self.create_skill("Forklift Driver")

        req_id = self.create_request(office.site_id,
                                     req_type=3,
                                     commit_status=REQ_STATUS_NONE,
                                     )
        self.create_request_skill(req_id,
                                  skill_ids=[skill_id],
                                  quantity=2,
                                  )
        commit_id = self.create_commit(req_id,
                                       site_id=office.site_id,
                                       organisation_id=office.organisation_id,
                                       )
        commit_skill_id = self.create_commit_skill(commit_id,
                                                   skill_ids=[skill_id],
                                                   quantity=1,
                                                   )

        CommitSkillModel.commit_skill_onaccept(self.make_form(id=commit_skill_id))

        req_skill = db(s3db.req_req_skill.req_id == req_id).select(s3db.req_req_skill.quantity_commit,
                                                                   limitby=(0, 1),
                                                                   ).first()
        req = db(s3db.req_req.id == req_id).select(s3db.req_req.commit_status,
                                                   limitby=(0, 1),
                                                   ).first()
        self.assertEqual(req_skill.quantity_commit, 1)
        self.assertEqual(req.commit_status, REQ_STATUS_PARTIAL)

        db(s3db.req_commit_skill.id == commit_skill_id).update(deleted=True,
                                                               deleted_fk=json.dumps({"commit_id": commit_id}),
                                                               )
        CommitSkillModel.commit_skill_ondelete(Storage(id=commit_skill_id))

        req_skill = db(s3db.req_req_skill.req_id == req_id).select(s3db.req_req_skill.quantity_commit,
                                                                   limitby=(0, 1),
                                                                   ).first()
        req = db(s3db.req_req.id == req_id).select(s3db.req_req.commit_status,
                                                   limitby=(0, 1),
                                                   ).first()
        self.assertEqual(req_skill.quantity_commit, 0)
        self.assertEqual(req.commit_status, REQ_STATUS_NONE)

    # -------------------------------------------------------------------------
    def testCommitSkillCallbacksIgnoreMissingRowsAndInvalidDeletePayloads(self):
        """Commit skill callbacks return cleanly for malformed forms, missing rows and bad delete payloads"""

        db = current.db
        s3db = current.s3db

        office = self.create_office(name="Skill Callback Site")
        skill_id = self.create_skill("Responder")
        req_id = self.create_request(office.site_id,
                                     req_type=3,
                                     commit_status=REQ_STATUS_NONE,
                                     )
        self.create_request_skill(req_id,
                                  skill_ids=[skill_id],
                                  quantity=1,
                                  )
        commit_id = self.create_commit(req_id,
                                       site_id=office.site_id,
                                       organisation_id=office.organisation_id,
                                       )
        commit_skill_id = self.create_commit_skill(commit_id,
                                                   skill_ids=[skill_id],
                                                   quantity=1,
                                                   )

        # Missing form vars and unknown IDs must not raise
        CommitSkillModel.commit_skill_onaccept(Storage())
        CommitSkillModel.commit_skill_onaccept(self.make_form(id=999999))

        # Invalid delete payloads and missing commits must be ignored
        db(s3db.req_commit_skill.id == commit_skill_id).update(deleted=True,
                                                               deleted_fk="not-json",
                                                               )
        CommitSkillModel.commit_skill_ondelete(Storage(id=commit_skill_id))

        db(s3db.req_commit_skill.id == commit_skill_id).update(deleted_fk=json.dumps({"commit_id": 999999}),
                                                               )
        CommitSkillModel.commit_skill_ondelete(Storage(id=commit_skill_id))

        req = db(s3db.req_req.id == req_id).select(s3db.req_req.commit_status,
                                                   limitby=(0, 1),
                                                   ).first()
        self.assertEqual(req.commit_status, REQ_STATUS_NONE)

    # -------------------------------------------------------------------------
    def testCommitCallbacksIgnoreMalformedFormsAndMissingRequests(self):
        """Commit callbacks return cleanly for malformed forms and missing request records"""

        s3db = current.s3db

        CommitModel.commit_onaccept(Storage(vars=Storage()))
        CommitModel.commit_onaccept(self.make_form(id=None))
        CommitModel.commit_onaccept(self.make_form(id=99999999, site_id=None))

        CommitItemModel.commit_item_onaccept(Storage(vars=Storage()))
        CommitItemModel.commit_item_onaccept(self.make_form(id=99999999))

        item_id = s3db.req_commit_item.insert(commit_id=None,
                                              req_item_id=None,
                                              item_pack_id=None,
                                              quantity=1,
                                              )
        current.db(s3db.req_commit_item.id == item_id).update(deleted_fk="not-json",
                                                              deleted=True,
                                                              )
        CommitItemModel.commit_item_ondelete(Storage(id=item_id))

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

    # -------------------------------------------------------------------------
    def testReqItemDefaultsAndDuplicateFallbacks(self):
        """Request-item defaults and duplicate checks handle incomplete references"""

        defaults = RequestItemModel("req").defaults()
        self.assertEqual(defaults["req_item_id"]().name, "req_item_id")

        update = Storage(UPDATE="update")
        item = Storage(table=current.s3db.req_req_item,
                       references=[Storage(entry=Storage(tablename="req_req",
                                                         id=None,
                                                         item_id="REQREF",
                                                         )),
                                   Storage(entry=Storage(tablename="supply_item",
                                                         id=None,
                                                         item_id="ITEMREF",
                                                         )),
                                   ],
                       job=type("Job", (), {"items": {"REQREF": Storage(id=None),
                                                      "ITEMREF": Storage(id=None),
                                                      }})(),
                       METHOD=update,
                       method=None,
                       id=None,
                       )

        RequestItemModel.req_item_duplicate(item)

        self.assertIsNone(item.id)
        self.assertIsNone(item.method)

    # -------------------------------------------------------------------------
    def testReqSkillOnacceptReturnsWithoutContextOrMatchingRequest(self):
        """Requested-skill callbacks tolerate missing request context and orphaned requests"""

        db = current.db

        RequestSkillModel.req_skill_onaccept(self.make_form(id=99999999))
        RequestSkillModel.req_skill_onaccept(self.make_form(req_id=99999999))

        task = db(current.s3db.project_task.id > 0).select(current.s3db.project_task.id,
                                                   limitby=(0, 1),
                                                   ).first()
        self.assertIsNone(task)

    # -------------------------------------------------------------------------
    def testCommitCallbacksHandleMissingVarsObjectsAndSiteLocations(self):
        """Commit callbacks tolerate missing vars objects and copy site locations when present"""

        db = current.db
        s3db = current.s3db

        location_id = self.create_location(name="Commit Source")
        office = self.create_office(location_id=location_id)
        req_id = self.create_request(office.site_id)
        commit_id = self.create_commit(req_id)

        CommitModel.commit_onaccept(Storage(vars=object()))
        CommitModel.commit_onaccept(self.make_form(id=commit_id,
                                                   site_id=office.site_id,
                                                   ))

        db(s3db.req_commit.id == commit_id).update(deleted_fk='{"req_id": 99999999}')
        CommitModel.commit_ondelete(Storage(id=commit_id))

        CommitItemModel.commit_item_onaccept(Storage(vars=object()))

        commit = db(s3db.req_commit.id == commit_id).select(s3db.req_commit.location_id,
                                                            limitby=(0, 1),
                                                            ).first()
        self.assertEqual(commit.location_id, location_id)


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
        saved_use_commit = settings.req.get("use_commit")
        saved_permission = auth.s3_has_permission

        settings.get_org_site_inv_req_tabs = lambda: True
        settings.has_module = lambda module: module == "req"
        settings.req.use_commit = True
        auth.s3_has_permission = lambda *args, **kwargs: True

        try:
            tabs = req_tabs(Storage(controller="req"), match=True)
        finally:
            settings.get_org_site_inv_req_tabs = saved_inv_tabs
            settings.has_module = saved_has_module
            settings.req.use_commit = saved_use_commit
            auth.s3_has_permission = saved_permission

        # Verify the visible tab order
        self.assertEqual([item[1] for item in tabs],
                         ["req", "req_match/", "commit"])

    # -------------------------------------------------------------------------
    def testReqTabsReturnEmptyWithoutRequestAccess(self):
        """Request tabs disappear when the user cannot read requests"""

        settings = current.deployment_settings
        auth = current.auth

        saved_has_module = settings.has_module
        saved_permission = auth.s3_has_permission

        try:
            settings.has_module = lambda module: False
            auth.s3_has_permission = lambda *args, **kwargs: False
            self.assertEqual(req_tabs(Storage(controller="req"), match=True), [])
        finally:
            settings.has_module = saved_has_module
            auth.s3_has_permission = saved_permission

    # -------------------------------------------------------------------------
    def testReqTabsOmitMatchAndCommitWhenDisabled(self):
        """Request tabs reduce to the plain request tab when matching and commits are disabled"""

        settings = current.deployment_settings
        auth = current.auth

        saved_inv_tabs = settings.get_org_site_inv_req_tabs
        saved_has_module = settings.has_module
        saved_permission = auth.s3_has_permission
        saved_settings = self._capture_req_settings("use_commit")

        settings.get_org_site_inv_req_tabs = lambda: True
        settings.has_module = lambda module: module == "req"
        settings.req.use_commit = False
        auth.s3_has_permission = lambda *args, **kwargs: True

        try:
            tabs = req_tabs(Storage(controller="req"), match=False)
        finally:
            settings.get_org_site_inv_req_tabs = saved_inv_tabs
            settings.has_module = saved_has_module
            auth.s3_has_permission = saved_permission
            self._restore_req_settings(saved_settings)

        self.assertEqual([item[1] for item in tabs], ["req"])

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
    def testReqDetailsRepresentSkillRequestsAndDriverFallback(self):
        """Request detail helpers render requested skills and non-item driver fallback"""

        office = self.create_office(name="Skill Detail Site")
        req_id = self.create_request(office.site_id,
                                     req_type=3,
                                     req_ref="REQ-SKILL-DETAIL",
                                     )
        skill_id = self.create_skill("Paramedic")
        self.create_request_skill(req_id,
                                  skill_ids=[skill_id],
                                  quantity=2,
                                  )

        row = Storage(req_req=Storage(id=req_id,
                                      type=3,
                                      req_ref="REQ-SKILL-DETAIL",
                                      ))

        details = req_req_details(row)

        self.assertIn("2", details)
        self.assertIn("Paramedic", details)
        self.assertEqual(req_req_drivers(row), current.messages["NONE"])

    # -------------------------------------------------------------------------
    def testReqDetailsAndDriversHandleMalformedRowsAndOtherRequests(self):
        """Request detail helpers return safe fallbacks for malformed rows and unsupported request types"""

        office = self.create_office(name="Other Request Site")
        req_id = self.create_request(office.site_id,
                                     req_type=9,
                                     req_ref="REQ-OTHER-DETAIL",
                                     )

        malformed = Storage()
        other = Storage(req_req=Storage(id=req_id,
                                        type=9,
                                        req_ref="REQ-OTHER-DETAIL",
                                        ))

        self.assertIsNone(req_req_details(malformed))
        self.assertIsNone(req_req_drivers(malformed))
        self.assertEqual(req_req_details(other), current.messages["NONE"])
        self.assertEqual(req_req_drivers(other), current.messages["NONE"])

    # -------------------------------------------------------------------------
    def testReqDetailsReturnNoneWhenRequestsHaveNoLines(self):
        """Request detail helpers fall back to NONE when requests have no item or skill rows"""

        office = self.create_office(name="Empty Detail Site")
        item_req_id = self.create_request(office.site_id,
                                          req_type=1,
                                          req_ref="REQ-EMPTY-ITEM",
                                          )
        skill_req_id = self.create_request(office.site_id,
                                           req_type=3,
                                           req_ref="REQ-EMPTY-SKILL",
                                           )

        item_row = Storage(req_req=Storage(id=item_req_id,
                                           type=1,
                                           req_ref="REQ-EMPTY-ITEM",
                                           ))
        skill_row = Storage(req_req=Storage(id=skill_req_id,
                                            type=3,
                                            req_ref="REQ-EMPTY-SKILL",
                                            ))

        self.assertEqual(req_req_details(item_row), current.messages["NONE"])
        self.assertEqual(req_req_details(skill_row), current.messages["NONE"])

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
    def testReqAddFromTemplateCopiesSkillsAndGeneratedRequestNumbers(self):
        """Recurring request helper copies skills and generates request references when enabled"""

        db = current.db
        s3db = current.s3db
        settings = current.deployment_settings

        office = self.create_office(name="Template Skill Office")
        requester_id = self.create_person(last_name="Skill Template")
        template_id = self.create_request(office.site_id,
                                          req_type=3,
                                          requester_id=requester_id,
                                          )
        skill_id = self.create_skill("Template Skill")
        skill_row_id = self.create_request_skill(template_id,
                                                 skill_ids=[skill_id],
                                                 quantity=3,
                                                 )
        db(s3db.req_req_skill.id == skill_row_id).update(task="Cover the night shift",
                                                         comments="Bring certificates",
                                                         )

        saved_settings = self._capture_req_settings("use_req_number")
        saved_shortname = settings.get_req_shortname
        saved_shipping_code = s3db.supply_get_shipping_code

        settings.req.use_req_number = True
        settings.get_req_shortname = lambda: "REQ"
        s3db.supply_get_shipping_code = lambda prefix, site_id, field: "REQ-TPL-0001"

        try:
            new_req_id = req_add_from_template(template_id)
        finally:
            self._restore_req_settings(saved_settings)
            settings.get_req_shortname = saved_shortname
            s3db.supply_get_shipping_code = saved_shipping_code

        req_row = db(s3db.req_req.id == new_req_id).select(s3db.req_req.req_ref,
                                                           limitby=(0, 1),
                                                           ).first()
        fields = [s3db.req_req_skill.skill_id,
                  s3db.req_req_skill.quantity,
                  s3db.req_req_skill.comments,
                  ]
        if "task" in s3db.req_req_skill.fields:
            fields.append(s3db.req_req_skill.task)
        skills = db(s3db.req_req_skill.req_id == new_req_id).select(*fields)

        self.assertEqual(req_row.req_ref, "REQ-TPL-0001")
        self.assertEqual(len(skills), 1)
        self.assertEqual(skills.first().skill_id, [skill_id])
        self.assertEqual(skills.first().quantity, 3)
        self.assertEqual(skills.first().comments, "Bring certificates")
        if "task" in s3db.req_req_skill.fields:
            self.assertEqual(skills.first().task, "Cover the night shift")

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
    def testReqApproverHelpersResolveInheritedApprovers(self):
        """Approver lookup recognises inherited organisation approvers"""

        db = current.db
        s3db = current.s3db
        auth = current.auth

        organisation_id = self.create_organisation()
        office = self.create_office(organisation_id=organisation_id)
        person_id = self.create_person(last_name="Inherited Approver")

        otable = s3db.org_organisation
        organisation = db(otable.id == organisation_id).select(otable.pe_id,
                                                               limitby=(0, 1),
                                                               ).first()
        self.create_approver(organisation.pe_id,
                             person_id,
                             title="Regional Approver",
                             matcher=False,
                             )

        saved_person = auth.s3_logged_in_person
        saved_desc = s3db.pr_get_descendants
        saved_anc = s3db.pr_get_ancestors

        auth.s3_logged_in_person = lambda: person_id
        s3db.pr_get_descendants = lambda pe_ids, entity_types=None: [office.pe_id]
        s3db.pr_get_ancestors = lambda pe_id: [organisation.pe_id]

        try:
            self.assertTrue(req_is_approver(office.site_id))
            approvers = req_approvers(office.site_id)
        finally:
            auth.s3_logged_in_person = saved_person
            s3db.pr_get_descendants = saved_desc
            s3db.pr_get_ancestors = saved_anc

        self.assertIn(person_id, approvers)
        self.assertEqual(approvers[person_id]["title"], "Regional Approver")
        self.assertFalse(approvers[person_id]["matcher"])

    # -------------------------------------------------------------------------
    def testReqApproverHelpersReturnFalseWithoutAssignments(self):
        """Approver lookup returns False when the user has no approver records"""

        auth = current.auth

        office = self.create_office(name="No Approver Office")
        person_id = self.create_person(last_name="Not Approver")

        saved_person = auth.s3_logged_in_person
        auth.s3_logged_in_person = lambda: person_id

        try:
            permitted = req_is_approver(office.site_id)
        finally:
            auth.s3_logged_in_person = saved_person

        self.assertFalse(permitted)

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
    def testReqHideQuantitiesLeavesWritableFieldsUntouched(self):
        """Quantity fields stay writable when the deployment allows editing them"""

        settings = current.deployment_settings
        saved_settings = self._capture_req_settings("item_quantities_writable")
        settings.req.item_quantities_writable = True

        table = Storage(quantity_commit=Storage(readable=True, writable=True),
                        quantity_transit=Storage(readable=True, writable=True),
                        quantity_fulfil=Storage(readable=True, writable=True),
                        )
        try:
            req_hide_quantities(table)
        finally:
            self._restore_req_settings(saved_settings)

        self.assertTrue(table.quantity_commit.readable)
        self.assertTrue(table.quantity_commit.writable)
        self.assertTrue(table.quantity_transit.readable)
        self.assertTrue(table.quantity_transit.writable)
        self.assertTrue(table.quantity_fulfil.readable)
        self.assertTrue(table.quantity_fulfil.writable)

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
    def testReqInlineFormConfiguresItemReadFormWithGeneratedNumbers(self):
        """Inline item read forms expose request numbers and readonly status fields"""

        settings = current.deployment_settings
        s3 = current.response.s3
        s3db = current.s3db
        _ = s3db.req_req
        table = current.db.req_req

        state = self._capture_req_form_state()
        saved_settings = self._capture_req_settings("status_writable",
                                                    "show_quantity_transit",
                                                    "use_commit",
                                                    "requester_from_site",
                                                    "use_req_number",
                                                    "generate_req_number",
                                                    "items_ask_purpose",
                                                    )
        saved_postprocess = getattr(s3, "req_req_postprocess", None)

        settings.req.status_writable = True
        settings.req.show_quantity_transit = False
        settings.req.use_commit = False
        settings.req.requester_from_site = False
        settings.req.use_req_number = True
        settings.req.generate_req_number = True
        settings.req.items_ask_purpose = False
        s3.req_req_postprocess = lambda form: form

        try:
            req_inline_form(1, "read")

            crud_form = s3db.get_config("req_req", "crud_form")
            selectors = [element.selector for element in crud_form.elements]

            self.assertEqual(selectors,
                             ["req_ref",
                              "site_id",
                              "requester_id",
                              "date",
                              "priority",
                              "date_required",
                              "req_item",
                              "comments",
                              "fulfil_status",
                              "date_recv",
                              ])
            self.assertFalse(table.req_ref.writable)
            self.assertEqual(str(s3.crud.submit_button), str(current.T("Save")))
        finally:
            self._restore_req_settings(saved_settings)
            self._restore_req_form_state(state)
            s3.req_req_postprocess = saved_postprocess

    # -------------------------------------------------------------------------
    def testReqInlineFormConfiguresItemUpdateFormWithoutOptionalStatusFields(self):
        """Inline item update forms omit optional request-number and status branches when disabled"""

        settings = current.deployment_settings
        s3 = current.response.s3
        s3db = current.s3db
        _ = s3db.req_req

        state = self._capture_req_form_state()
        saved_settings = self._capture_req_settings("status_writable",
                                                    "show_quantity_transit",
                                                    "use_commit",
                                                    "requester_from_site",
                                                    "use_req_number",
                                                    "items_ask_purpose",
                                                    )
        saved_postprocess = getattr(s3, "req_req_postprocess", None)

        settings.req.status_writable = False
        settings.req.show_quantity_transit = False
        settings.req.use_commit = False
        settings.req.requester_from_site = False
        settings.req.use_req_number = False
        settings.req.items_ask_purpose = False
        s3.req_req_postprocess = None

        try:
            req_inline_form(1, "update")

            crud_form = s3db.get_config("req_req", "crud_form")
            selectors = [element.selector for element in crud_form.elements]

            self.assertEqual(selectors,
                             ["site_id",
                              "requester_id",
                              "date",
                              "priority",
                              "date_required",
                              "req_item",
                              "comments",
                              "date_recv",
                              ])
            self.assertEqual(str(s3.crud.submit_button), str(current.T("Save")))
        finally:
            self._restore_req_settings(saved_settings)
            self._restore_req_form_state(state)
            s3.req_req_postprocess = saved_postprocess

    # -------------------------------------------------------------------------
    def testReqInlineFormConfiguresSkillCreateFormWithManualNumbers(self):
        """Inline skill create forms expose explicit request numbers when auto-generation is off"""

        settings = current.deployment_settings
        s3 = current.response.s3
        s3db = current.s3db
        _ = s3db.req_req

        state = self._capture_req_form_state()
        saved_settings = self._capture_req_settings("use_req_number",
                                                    "generate_req_number",
                                                    "requester_from_site",
                                                    )
        saved_postprocess = getattr(s3, "req_req_postprocess", None)

        settings.req.use_req_number = True
        settings.req.generate_req_number = False
        settings.req.requester_from_site = False
        s3.req_req_postprocess = None

        try:
            req_inline_form(3, "create")

            crud_form = s3db.get_config("req_req", "crud_form")
            selectors = [element.selector for element in crud_form.elements]

            self.assertEqual(selectors,
                             ["req_ref",
                              "site_id",
                              "is_template",
                              "requester_id",
                              "date",
                              "priority",
                              "date_required",
                              "date_required_until",
                              "purpose",
                              "req_skill",
                              "comments",
                              ])
            self.assertEqual(str(s3.crud.submit_button), str(current.T("Save")))
        finally:
            self._restore_req_settings(saved_settings)
            self._restore_req_form_state(state)
            s3.req_req_postprocess = saved_postprocess

    # -------------------------------------------------------------------------
    def testReqInlineFormConfiguresSkillUpdateWithoutStatusAndSiteRequesterWidgets(self):
        """Inline skill update forms keep the minimal status-free layout when optional branches are off"""

        settings = current.deployment_settings
        s3 = current.response.s3
        s3db = current.s3db
        _ = s3db.req_req

        state = self._capture_req_form_state()
        saved_settings = self._capture_req_settings("status_writable",
                                                    "show_quantity_transit",
                                                    "use_commit",
                                                    "requester_from_site",
                                                    "use_req_number",
                                                    "generate_req_number",
                                                    )
        saved_postprocess = getattr(s3, "req_req_postprocess", None)

        settings.req.status_writable = False
        settings.req.show_quantity_transit = False
        settings.req.use_commit = False
        settings.req.requester_from_site = False
        settings.req.use_req_number = False
        settings.req.generate_req_number = True
        s3.req_req_postprocess = None

        try:
            req_inline_form(3, "update")

            crud_form = s3db.get_config("req_req", "crud_form")
            selectors = [element.selector for element in crud_form.elements]

            self.assertEqual(selectors,
                             ["site_id",
                              "requester_id",
                              "date",
                              "priority",
                              "date_required",
                              "date_required_until",
                              "purpose",
                              "req_skill",
                              "date_recv",
                              "comments",
                              ])
        finally:
            self._restore_req_settings(saved_settings)
            self._restore_req_form_state(state)
            s3.req_req_postprocess = saved_postprocess

    # -------------------------------------------------------------------------
    def testReqInlineFormConfiguresItemUpdateFormWithAllStatuses(self):
        """Inline item update forms include all status fields when the workflow exposes them"""

        settings = current.deployment_settings
        s3 = current.response.s3
        s3db = current.s3db
        _ = s3db.req_req
        _ = s3db.req_req_item

        state = self._capture_req_form_state()
        saved_settings = self._capture_req_settings("status_writable",
                                                    "show_quantity_transit",
                                                    "use_commit",
                                                    "requester_from_site",
                                                    "use_req_number",
                                                    "generate_req_number",
                                                    "items_ask_purpose",
                                                    )

        settings.req.status_writable = True
        settings.req.show_quantity_transit = True
        settings.req.use_commit = True
        settings.req.requester_from_site = False
        settings.req.use_req_number = False
        settings.req.generate_req_number = True
        settings.req.items_ask_purpose = False

        try:
            req_inline_form(1, "update")

            crud_form = s3db.get_config("req_req", "crud_form")
            selectors = [element.selector for element in crud_form.elements]

            self.assertEqual(selectors,
                             ["site_id",
                              "requester_id",
                              "date",
                              "priority",
                              "date_required",
                              "req_item",
                              "comments",
                              "commit_status",
                              "transit_status",
                              "fulfil_status",
                              "date_recv",
                              ])
        finally:
            self._restore_req_settings(saved_settings)
            self._restore_req_form_state(state)

    # -------------------------------------------------------------------------
    def testReqInlineFormConfiguresSkillUpdateFormWithPostprocess(self):
        """Inline skill update forms honour postprocess callbacks on the assembled CustomForm"""

        settings = current.deployment_settings
        s3 = current.response.s3
        s3db = current.s3db
        _ = s3db.req_req

        state = self._capture_req_form_state()
        saved_settings = self._capture_req_settings("status_writable",
                                                    "show_quantity_transit",
                                                    "use_commit",
                                                    "requester_from_site",
                                                    "use_req_number",
                                                    "generate_req_number",
                                                    )
        saved_postprocess = getattr(s3, "req_req_postprocess", None)

        settings.req.status_writable = True
        settings.req.show_quantity_transit = False
        settings.req.use_commit = True
        settings.req.requester_from_site = False
        settings.req.use_req_number = False
        settings.req.generate_req_number = True
        s3.req_req_postprocess = lambda form: form

        try:
            req_inline_form(3, "update")

            crud_form = s3db.get_config("req_req", "crud_form")
            selectors = [element.selector for element in crud_form.elements]

            self.assertEqual(selectors,
                             ["site_id",
                              "requester_id",
                              "date",
                              "priority",
                              "date_required",
                              "date_required_until",
                              "purpose",
                              "req_skill",
                              "date_recv",
                              "commit_status",
                              "fulfil_status",
                              "comments",
                              ])
        finally:
            self._restore_req_settings(saved_settings)
            self._restore_req_form_state(state)
            s3.req_req_postprocess = saved_postprocess

    # -------------------------------------------------------------------------
    def testReqJobHelpersResetAndRunTasks(self):
        """Recurring-request helpers reset jobs and run templates on demand"""

        auth = current.auth
        session = current.session
        s3task = current.s3task

        saved_redirect = req_module.redirect
        saved_reset = req_module.S3Task.reset
        saved_run_async = s3task.run_async
        saved_confirmation = session.confirmation
        saved_user = auth.user

        calls = Storage(reset=None, run=None)

        req_module.redirect = lambda url, *args, **kwargs: (_ for _ in ()).throw(RedirectIntercept(url))
        req_module.S3Task.reset = lambda job_id: setattr(calls, "reset", job_id)
        s3task.run_async = lambda task, args, vars: setattr(calls, "run", (task, args, vars))
        auth.user = Storage(id=42)
        session.confirmation = None

        try:
            reset_request = Storage(interactive=True,
                                    component=Storage(alias="job"),
                                    component_id=7,
                                    url=lambda **kwargs: "/req/req_template/1/job",
                                    )
            with self.assertRaises(RedirectIntercept) as redirect:
                req_module.req_job_reset(reset_request)
            self.assertEqual(calls.reset, 7)
            self.assertEqual(str(session.confirmation), "Job reactivated")
            self.assertEqual(str(redirect.exception.url), "/req/req_template/1/job")

            session.confirmation = None
            run_request = Storage(interactive=True,
                                  id=11,
                                  url=lambda **kwargs: "/req/req_template/11/job",
                                  )
            with self.assertRaises(RedirectIntercept) as redirect:
                req_module.req_job_run(run_request)
            self.assertEqual(calls.run,
                             ("req_add_from_template",
                              [11],
                              {"user_id": 42},
                              ))
            self.assertEqual(str(session.confirmation), "Request added")
            self.assertEqual(str(redirect.exception.url), "/req/req_template/11/job")
        finally:
            req_module.redirect = saved_redirect
            req_module.S3Task.reset = saved_reset
            s3task.run_async = saved_run_async
            session.confirmation = saved_confirmation
            auth.user = saved_user

    # -------------------------------------------------------------------------
    def testReqJobHelpersIgnoreNonInteractiveRequests(self):
        """Recurring-request helpers do not invoke tasks for non-interactive requests"""

        session = current.session
        s3task = current.s3task

        saved_redirect = req_module.redirect
        saved_reset = req_module.S3Task.reset
        saved_run_async = s3task.run_async
        saved_confirmation = session.confirmation

        calls = Storage(reset=None, run=None)

        req_module.redirect = lambda url, *args, **kwargs: (_ for _ in ()).throw(RedirectIntercept(url))
        req_module.S3Task.reset = lambda job_id: setattr(calls, "reset", job_id)
        s3task.run_async = lambda task, args, vars: setattr(calls, "run", (task, args, vars))
        session.confirmation = None

        try:
            with self.assertRaises(RedirectIntercept) as reset_redirect:
                req_module.req_job_reset(Storage(interactive=False,
                                                component=Storage(alias="job"),
                                                component_id=7,
                                                url=lambda **kwargs: "/req/req_template/7/job",
                                                ))
            with self.assertRaises(RedirectIntercept) as run_redirect:
                req_module.req_job_run(Storage(interactive=False,
                                              id=9,
                                              url=lambda **kwargs: "/req/req_template/9/job",
                                              ))
        finally:
            req_module.redirect = saved_redirect
            req_module.S3Task.reset = saved_reset
            s3task.run_async = saved_run_async
            session.confirmation = saved_confirmation

        self.assertIsNone(calls.reset)
        self.assertIsNone(calls.run)
        self.assertEqual(str(reset_redirect.exception.url), "/req/req_template/7/job")
        self.assertEqual(str(run_redirect.exception.url), "/req/req_template/9/job")

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

    # -------------------------------------------------------------------------
    def testReqRheaderAddsScheduleTabForTemplates(self):
        """Request rheaders include the schedule tab for recurring templates"""

        db = current.db
        s3db = current.s3db
        settings = current.deployment_settings

        office = self.create_office(name="Template Schedule Site")
        item_id = self.create_supply_item(name="Schedule Kit")
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(office.site_id,
                                     req_type=1,
                                     req_ref="REQ-TPL-SCHED",
                                     is_template=True,
                                     )
        self.create_request_item(req_id,
                                 item_id,
                                 pack_id,
                                 quantity=1,
                                 )
        record = db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                      limitby=(0, 1),
                                                      ).first()

        captured_tabs = []
        saved_tabs = req_rheader.__globals__["s3_rheader_tabs"]
        saved_settings = self._capture_req_settings("use_commit",
                                                    "workflow",
                                                    "multiple_req_items",
                                                    )
        saved_has_module = settings.has_module

        req_rheader.__globals__["s3_rheader_tabs"] = lambda r, tabs: \
            captured_tabs.append(tabs) or DIV("REQ-TABS")
        settings.has_module = lambda module: module in ("inv", "req")
        settings.req.use_commit = True
        settings.req.workflow = True
        settings.req.multiple_req_items = True

        try:
            rheader = req_rheader(Storage(representation="html",
                                          record=record,
                                          name="req",
                                          table=s3db.req_req,
                                          component=None,
                                          ))
        finally:
            req_rheader.__globals__["s3_rheader_tabs"] = saved_tabs
            self._restore_req_settings(saved_settings)
            settings.has_module = saved_has_module

        self.assertIn("REQ-TABS", str(rheader))
        self.assertTrue(any(tab[1] == "job" for tab in captured_tabs[0]))

    # -------------------------------------------------------------------------
    def testReqRheaderReturnsNoneOutsideInteractiveViews(self):
        """Request rheaders are only built for HTML record views"""

        s3db = current.s3db

        self.assertIsNone(req_rheader(Storage(representation="pdf",
                                              record=Storage(id=1),
                                              name="req",
                                              table=s3db.req_req,
                                              )))
        self.assertIsNone(req_rheader(Storage(representation="html",
                                              record=None,
                                              name="req",
                                              table=s3db.req_req,
                                              )))

    # -------------------------------------------------------------------------
    def testReqRheaderPeopleRequestsExposeSkillCheckTab(self):
        """People requests expose the skills tab and matcher check action when commit-people is enabled"""

        db = current.db
        s3db = current.s3db
        auth = current.auth
        settings = current.deployment_settings

        office = self.create_office(name="People Request Site")
        skill_id = self.create_skill("Medic")
        req_id = self.create_request(office.site_id,
                                     req_type=3,
                                     req_ref="REQ-PEOPLE-HDR",
                                     workflow_status=1,
                                     is_template=False,
                                     )
        self.create_request_skill(req_id,
                                  skill_ids=[skill_id],
                                  quantity=2,
                                  )
        record = db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                      limitby=(0, 1),
                                                      ).first()

        captured_tabs = []
        saved_user = auth.user
        saved_tabs = req_rheader.__globals__["s3_rheader_tabs"]
        saved_settings = self._capture_req_settings("use_commit",
                                                    "workflow",
                                                    "commit_people",
                                                    )
        saved_has_module = settings.has_module

        auth.user = Storage(organisation_id=office.organisation_id,
                            site_id=None,
                            )
        req_rheader.__globals__["s3_rheader_tabs"] = lambda r, tabs: \
            captured_tabs.append(tabs) or DIV("REQ-TABS")
        settings.req.use_commit = True
        settings.req.workflow = False
        settings.req.commit_people = True
        settings.has_module = lambda module: module == "hrm"

        try:
            rheader = req_rheader(Storage(representation="html",
                                          record=record,
                                          name="req",
                                          table=s3db.req_req,
                                          component=None,
                                          component_name=None,
                                          component_id=None,
                                          ))
        finally:
            auth.user = saved_user
            req_rheader.__globals__["s3_rheader_tabs"] = saved_tabs
            self._restore_req_settings(saved_settings)
            settings.has_module = saved_has_module

        self.assertIn("REQ-TABS", str(rheader))
        self.assertEqual([tab[1] for tab in captured_tabs[0]],
                         [None, "req_skill", "document", "commit", "check"],
                         )

    # -------------------------------------------------------------------------
    def testReqRheaderSkipsApproveButtonForApprovedApproversAndCheckPage(self):
        """Approved approvers do not see another approve button, and check pages omit header tabs"""

        db = current.db
        s3db = current.s3db
        auth = current.auth
        response_s3 = current.response.s3
        settings = current.deployment_settings

        office = self.create_office(name="Approved Request Site")
        approver_id = self.create_person(last_name="Approved Approver")
        self.create_approver(office.pe_id,
                             approver_id,
                             title="Approver",
                             )
        item_id = self.create_supply_item(name="Solar Lamp")
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(office.site_id,
                                     req_type=1,
                                     req_ref="REQ-HDR-APPROVED",
                                     workflow_status=2,
                                     is_template=False,
                                     )
        self.create_request_item(req_id,
                                 item_id,
                                 pack_id,
                                 quantity=1,
                                 )
        s3db.req_approver_req.insert(req_id=req_id,
                                     person_id=approver_id,
                                     )
        record = db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                      limitby=(0, 1),
                                                      ).first()

        saved_user = auth.user
        saved_logged_in = auth.s3_logged_in_person
        saved_settings = self._capture_req_settings("use_commit",
                                                    "workflow",
                                                    "multiple_req_items",
                                                    )
        saved_has_module = settings.has_module
        saved_descendants = s3db.pr_get_descendants
        saved_ancestors = s3db.pr_get_ancestors
        saved_footer = response_s3.rfooter

        auth.user = Storage(organisation_id=office.organisation_id,
                            site_id=office.site_id,
                            )
        auth.s3_logged_in_person = lambda: approver_id
        settings.req.use_commit = True
        settings.req.workflow = True
        settings.req.multiple_req_items = True
        settings.has_module = lambda module: module == "inv"
        s3db.pr_get_descendants = lambda pe_ids, entity_types=None: []
        s3db.pr_get_ancestors = lambda pe_id: []
        response_s3.rfooter = None

        try:
            rheader = req_rheader(Storage(representation="html",
                                          record=record,
                                          name="req",
                                          table=s3db.req_req,
                                          component=None,
                                          component_name=None,
                                          component_id=None,
                                          ),
                                  check_page=True,
                                  )
            footer = response_s3.rfooter
        finally:
            auth.user = saved_user
            auth.s3_logged_in_person = saved_logged_in
            self._restore_req_settings(saved_settings)
            settings.has_module = saved_has_module
            s3db.pr_get_descendants = saved_descendants
            s3db.pr_get_ancestors = saved_ancestors
            response_s3.rfooter = saved_footer

        self.assertIn("<div", str(rheader).lower())
        self.assertIsNone(footer)

    # -------------------------------------------------------------------------
    def testReqRheaderOtherRequestsExposeDocumentAndCommitTabs(self):
        """Other request types skip item/skill tabs but still expose document and commitment tabs"""

        db = current.db
        s3db = current.s3db
        settings = current.deployment_settings

        office = self.create_office(name="Other Header Site")
        req_id = self.create_request(office.site_id,
                                     req_type=9,
                                     req_ref="REQ-HDR-OTHER",
                                     workflow_status=3,
                                     is_template=False,
                                     )
        record = db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                      limitby=(0, 1),
                                                      ).first()

        captured_tabs = []
        saved_tabs = req_rheader.__globals__["s3_rheader_tabs"]
        saved_settings = self._capture_req_settings("use_commit",
                                                    "workflow",
                                                    )

        req_rheader.__globals__["s3_rheader_tabs"] = lambda r, tabs: \
            captured_tabs.append(tabs) or DIV("REQ-TABS")
        settings.req.use_commit = True
        settings.req.workflow = False

        try:
            rheader = req_rheader(Storage(representation="html",
                                          record=record,
                                          name="req",
                                          table=s3db.req_req,
                                          component=None,
                                          component_name=None,
                                          component_id=None,
                                          ))
        finally:
            req_rheader.__globals__["s3_rheader_tabs"] = saved_tabs
            self._restore_req_settings(saved_settings)

        self.assertIn("REQ-TABS", str(rheader))
        self.assertEqual([tab[1] for tab in captured_tabs[0]],
                         [None, "document", "commit"],
                         )

    # -------------------------------------------------------------------------
    def testReqRheaderUsesSingularItemTabAndNoCommitStatusWhenCommitWorkflowIsOff(self):
        """Request rheaders use the singular item tab and omit commit status without commit workflow"""

        db = current.db
        s3db = current.s3db
        settings = current.deployment_settings

        office = self.create_office(name="Singular Header Site")
        item_id = self.create_supply_item(name="Single Header Item")
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(office.site_id,
                                     req_type=1,
                                     req_ref="REQ-HDR-SINGLE",
                                     workflow_status=3,
                                     commit_status=REQ_STATUS_COMPLETE,
                                     fulfil_status=REQ_STATUS_PARTIAL,
                                     )
        self.create_request_item(req_id,
                                 item_id,
                                 pack_id,
                                 quantity=1,
                                 )
        record = db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                      limitby=(0, 1),
                                                      ).first()

        captured_tabs = []
        saved_tabs = req_rheader.__globals__["s3_rheader_tabs"]
        saved_settings = self._capture_req_settings("use_commit",
                                                    "workflow",
                                                    "multiple_req_items",
                                                    "show_quantity_transit",
                                                    )

        req_rheader.__globals__["s3_rheader_tabs"] = lambda r, tabs: \
            captured_tabs.append(tabs) or DIV("REQ-TABS")
        settings.req.use_commit = False
        settings.req.workflow = True
        settings.req.multiple_req_items = False
        settings.req.show_quantity_transit = False

        try:
            rheader = req_rheader(Storage(representation="html",
                                          record=record,
                                          name="req",
                                          table=s3db.req_req,
                                          component=None,
                                          component_name=None,
                                          component_id=None,
                                          ))
        finally:
            req_rheader.__globals__["s3_rheader_tabs"] = saved_tabs
            self._restore_req_settings(saved_settings)

        self.assertIn("REQ-TABS", str(rheader))
        tab_names = [tab[1] for tab in captured_tabs[0]]
        self.assertEqual(tab_names[:3], [None, "req_item", "document"])
        self.assertNotIn("Committed", str(rheader))


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
        saved_use_number = settings.req.get("use_req_number")
        saved_shipping_code = s3db.supply_get_shipping_code

        try:
            # Generate a deterministic new request reference and intercept the redirect
            settings.req.use_req_number = True
            s3db.supply_get_shipping_code = lambda *args, **kwargs: "REQ-COPY-NEW"
            req_module.redirect = lambda url: (_ for _ in ()).throw(RedirectIntercept(url))

            with self.assertRaises(RedirectIntercept) as redirect:
                RequestModel.req_copy_all(Storage(record=record))
        finally:
            req_module.redirect = saved_redirect
            settings.req.use_req_number = saved_use_number
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
        saved_use_number = settings.req.get("use_req_number")

        try:
            # Skills requests should still duplicate cleanly without request numbers
            settings.req.use_req_number = False
            req_module.redirect = lambda url: (_ for _ in ()).throw(RedirectIntercept(url))

            with self.assertRaises(RedirectIntercept):
                RequestModel.req_copy_all(Storage(record=record))
        finally:
            req_module.redirect = saved_redirect
            settings.req.use_req_number = saved_use_number

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
    def testReqCopyAllCopiesSkillTasksWhenPresent(self):
        """req_copy_all preserves req_req_skill.task when the deployment exposes the field"""

        db = current.db
        s3db = current.s3db

        office = self.create_office(name="Task Copy Site")
        skill_id = self.create_skill(name="Logistics")
        req_id = self.create_request(office.site_id,
                                     req_type=3,
                                     purpose="Need task copy",
                                     )
        req_skill_id = self.create_request_skill(req_id,
                                                 skill_ids=[skill_id],
                                                 quantity=1,
                                                 site_id=office.site_id,
                                                 )
        if "task" not in s3db.req_req_skill.fields:
            self.skipTest("req_req_skill.task not available in this deployment")

        db(s3db.req_req_skill.id == req_skill_id).update(task="Night shift")
        record = db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                      limitby=(0, 1),
                                                      ).first()

        saved_redirect = req_module.redirect
        try:
            req_module.redirect = lambda url: (_ for _ in ()).throw(RedirectIntercept(url))
            with self.assertRaises(RedirectIntercept):
                RequestModel.req_copy_all(Storage(record=record))
        finally:
            req_module.redirect = saved_redirect

        new_req = db((s3db.req_req.id != req_id) &
                     (s3db.req_req.type == 3)).select(s3db.req_req.id,
                                                      orderby=~s3db.req_req.id,
                                                      limitby=(0, 1),
                                                      ).first()
        new_skill = db(s3db.req_req_skill.req_id == new_req.id).select(s3db.req_req_skill.task,
                                                                       limitby=(0, 1),
                                                                       ).first()
        self.assertEqual(new_skill.task, "Night shift")

    # -------------------------------------------------------------------------
    def testReqCopyAllDuplicatesOtherRequestTypesWithoutComponents(self):
        """req_copy_all still duplicates non-item, non-skill requests and preserves the header fields"""

        db = current.db
        s3db = current.s3db
        settings = current.deployment_settings

        office = self.create_office(name="Other Copy Site")
        requester_id = self.create_person(last_name="Other Requester")
        req_id = self.create_request(office.site_id,
                                     req_type=9,
                                     req_ref="REQ-OTHER-COPY",
                                     requester_id=requester_id,
                                     purpose="Other workflow",
                                     comments="Header only",
                                     )
        record = db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                      limitby=(0, 1),
                                                      ).first()

        saved_redirect = req_module.redirect
        saved_use_number = settings.req.get("use_req_number")

        try:
            settings.req.use_req_number = False
            req_module.redirect = lambda url: (_ for _ in ()).throw(RedirectIntercept(url))

            with self.assertRaises(RedirectIntercept):
                RequestModel.req_copy_all(Storage(record=record))
        finally:
            req_module.redirect = saved_redirect
            settings.req.use_req_number = saved_use_number

        new_req = db((s3db.req_req.id != req_id) &
                     (s3db.req_req.type == 9)).select(s3db.req_req.ALL,
                                                      orderby=~s3db.req_req.id,
                                                      limitby=(0, 1),
                                                      ).first()
        self.assertIsNotNone(new_req)
        self.assertEqual(new_req.requester_id, requester_id)
        self.assertEqual(new_req.purpose, "Other workflow")
        self.assertEqual(new_req.comments, "Header only")
        self.assertEqual(db(s3db.req_req_item.req_id == new_req.id).count(), 0)
        self.assertEqual(db(s3db.req_req_skill.req_id == new_req.id).count(), 0)

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
    def testReqCommitAllHandlesOtherRequestTypes(self):
        """req_commit_all still completes non-item, non-skill requests and redirects to the commitment"""

        db = current.db
        s3db = current.s3db
        session = current.session

        office = self.create_office(name="Other Commit Site")
        req_id = self.create_request(office.site_id,
                                     req_type=9,
                                     commit_status=REQ_STATUS_NONE,
                                     )
        record = db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                      limitby=(0, 1),
                                                      ).first()

        saved_redirect = req_module.redirect
        saved_confirmation = session.confirmation

        try:
            session.confirmation = None
            req_module.redirect = lambda url: (_ for _ in ()).throw(RedirectIntercept(url))
            with self.assertRaises(RedirectIntercept) as redirect:
                RequestModel.req_commit_all(Storage(record=record,
                                                   id=req_id,
                                                   args=[],
                                                   ))
        finally:
            req_module.redirect = saved_redirect

        try:
            commit = db(s3db.req_commit.req_id == req_id).select(s3db.req_commit.id,
                                                                 s3db.req_commit.type,
                                                                 limitby=(0, 1),
                                                                 ).first()
            req = db(s3db.req_req.id == req_id).select(s3db.req_req.commit_status,
                                                       limitby=(0, 1),
                                                       ).first()

            self.assertIsNotNone(commit)
            self.assertEqual(commit.type, 9)
            self.assertEqual(req.commit_status, REQ_STATUS_COMPLETE)
            self.assertIn("/req/commit/%s" % commit.id, str(redirect.exception.url))
            self.assertEqual(session.confirmation,
                             "You have committed to this Request. Please check that all details are correct and update as-required.")
        finally:
            session.confirmation = saved_confirmation

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
        settings = current.deployment_settings
        saved_exporter = core.DataExporter.pdf
        saved_use_number = settings.req.get("use_req_number")

        try:
            # Capture the PDF export options without generating a real document
            settings.req.use_req_number = True
            core.DataExporter.pdf = lambda resource, **kwargs: captured.update(resource=resource,
                                                                               kwargs=kwargs,
                                                                               ) or "PDF"
            result = RequestModel.req_form(Storage(record=record,
                                                  resource="RESOURCE",
                                                  ))
        finally:
            settings.req.use_req_number = saved_use_number
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
    def testReqFormBuildsPdfExportForSkillRequestsWithoutRequestNumbers(self):
        """req_form exports skill requests and omits filenames when request numbers are disabled"""

        s3db = current.s3db
        settings = current.deployment_settings

        # Prepare one skills request for PDF export
        office = self.create_office()
        req_id = self.create_request(office.site_id,
                                     req_type=3,
                                     req_ref="REQ-SKILL-001",
                                     )
        record = current.db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                              limitby=(0, 1),
                                                              ).first()

        captured = {}
        saved_use_number = settings.req.get("use_req_number")
        saved_exporter = core.DataExporter.pdf

        try:
            # Capture the PDF exporter call for the skills branch
            settings.req.use_req_number = False
            core.DataExporter.pdf = lambda resource, **kwargs: captured.update(kwargs=kwargs) or "PDF"
            result = RequestModel.req_form(Storage(record=record,
                                                  resource="RESOURCE",
                                                  ))
        finally:
            settings.req.use_req_number = saved_use_number
            core.DataExporter.pdf = saved_exporter

        self.assertEqual(result, "PDF")
        self.assertEqual(captured["kwargs"]["pdf_componentname"], "req_skill")
        self.assertEqual(captured["kwargs"]["pdf_filename"], None)
        self.assertEqual(captured["kwargs"]["list_fields"],
                         ["skill_id",
                          "quantity",
                          "quantity_commit",
                          "quantity_transit",
                          "quantity_fulfil",
                          ])

    # -------------------------------------------------------------------------
    def testReqFormRedirectsUnsupportedRequestTypesToNativePdf(self):
        """req_form redirects unsupported request types to the regular PDF export"""

        s3db = current.s3db

        # Unsupported request types should fall back to the generic PDF handler
        office = self.create_office()
        req_id = self.create_request(office.site_id,
                                     req_type=9,
                                     )
        record = current.db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                              limitby=(0, 1),
                                                              ).first()

        saved_args = list(current.request.args)
        saved_redirect = req_module.redirect

        current.request.args = [str(req_id)]
        try:
            req_module.redirect = lambda url: (_ for _ in ()).throw(RedirectIntercept(url))
            with self.assertRaises(RedirectIntercept) as redirect:
                RequestModel.req_form(Storage(record=record,
                                              resource="RESOURCE",
                                              ))
        finally:
            current.request.args = saved_args
            req_module.redirect = saved_redirect

        url = str(redirect.exception.url)
        self.assertIn(".pdf", url)
        self.assertIn("/%s" % req_id, url)

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
    def testReqSubmitRejectsNonDraftRequests(self):
        """req_submit only accepts draft requests in workflow status 1"""

        s3db = current.s3db

        # Submitted or approved requests must not be submitted again
        office = self.create_office()
        req_id = self.create_request(office.site_id,
                                     workflow_status=2,
                                     )
        record = current.db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                              limitby=(0, 1),
                                                              ).first()

        saved_redirect = req_module.redirect
        current.session.error = None

        try:
            req_module.redirect = lambda url: (_ for _ in ()).throw(RedirectIntercept(url))
            with self.assertRaises(RedirectIntercept) as redirect:
                RequestModel.req_submit(Storage(record=record,
                                               id=req_id,
                                               unauthorised=lambda: self.fail("submit unauthorised"),
                                               ))
        finally:
            req_module.redirect = saved_redirect

        self.assertEqual(current.session.error, "Can only Submit Draft Requests")
        self.assertTrue(str(redirect.exception.url).endswith("/%s" % req_id))

    # -------------------------------------------------------------------------
    def testReqSubmitRejectsUnauthorisedUpdates(self):
        """req_submit refuses users without update permission on the request"""

        s3db = current.s3db
        auth = current.auth

        # Permission denial should call the unauthorised hook before any lookup work
        office = self.create_office()
        req_id = self.create_request(office.site_id,
                                     workflow_status=1,
                                     )
        record = current.db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                              limitby=(0, 1),
                                                              ).first()

        saved_permission = auth.s3_has_permission
        try:
            auth.s3_has_permission = lambda *args, **kwargs: False
            with self.assertRaises(PermissionError):
                RequestModel.req_submit(Storage(record=record,
                                               id=req_id,
                                               unauthorised=lambda: (_ for _ in ()).throw(PermissionError("unauthorised")),
                                               ))
        finally:
            auth.s3_has_permission = saved_permission

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
    def testReqApproveRejectsNonSubmittedRequests(self):
        """req_approve only accepts requests in submitted workflow status"""

        s3db = current.s3db

        # Draft requests must not enter the approval workflow
        office = self.create_office()
        req_id = self.create_request(office.site_id,
                                     workflow_status=1,
                                     )
        record = current.db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                              limitby=(0, 1),
                                                              ).first()

        saved_redirect = req_module.redirect
        current.session.error = None

        try:
            req_module.redirect = lambda url: (_ for _ in ()).throw(RedirectIntercept(url))
            with self.assertRaises(RedirectIntercept) as redirect:
                RequestModel.req_approve(Storage(record=record,
                                                id=req_id,
                                                unauthorised=lambda: self.fail("approve unauthorised"),
                                                ))
        finally:
            req_module.redirect = saved_redirect

        self.assertEqual(current.session.error, "Can only Approve Submitted Requests")
        self.assertTrue(str(redirect.exception.url).endswith("/%s" % req_id))

    # -------------------------------------------------------------------------
    def testReqApproveRejectsUnauthorisedApprovers(self):
        """req_approve refuses users who are not configured as approvers for the request site"""

        s3db = current.s3db
        auth = current.auth

        # A logged-in person outside the approver map must be rejected
        office = self.create_office()
        person_id = self.create_person(last_name="Unapproved")
        req_id = self.create_request(office.site_id,
                                     workflow_status=2,
                                     )
        record = current.db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                              limitby=(0, 1),
                                                              ).first()

        saved_approvers = req_module.req_approvers
        saved_logged_in = auth.s3_logged_in_person
        try:
            req_module.req_approvers = lambda site_id: {}
            auth.s3_logged_in_person = lambda: person_id
            with self.assertRaises(PermissionError):
                RequestModel.req_approve(Storage(record=record,
                                                id=req_id,
                                                unauthorised=lambda: (_ for _ in ()).throw(PermissionError("unauthorised")),
                                                ))
        finally:
            req_module.req_approvers = saved_approvers
            auth.s3_logged_in_person = saved_logged_in

    # -------------------------------------------------------------------------
    def testReqApproveWarnsIfAlreadyApproved(self):
        """req_approve warns and redirects if the current approver has already approved the request"""

        s3db = current.s3db
        auth = current.auth

        # Repeated approvals by the same person should not create duplicate rows
        office = self.create_office()
        person_id = self.create_person(last_name="Repeat Approver")
        req_id = self.create_request(office.site_id,
                                     workflow_status=2,
                                     )
        s3db.req_approver_req.insert(req_id=req_id,
                                     person_id=person_id,
                                     title="Lead",
                                     )
        record = current.db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                              limitby=(0, 1),
                                                              ).first()

        saved_approvers = req_module.req_approvers
        saved_logged_in = auth.s3_logged_in_person
        saved_redirect = req_module.redirect
        current.session.warning = None

        try:
            req_module.req_approvers = lambda site_id: {
                person_id: {"matcher": False, "title": "Lead"},
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

        self.assertEqual(current.session.warning, "You have already Approved this Request")
        self.assertTrue(str(redirect.exception.url).endswith("/%s" % req_id))
        self.assertEqual(current.db(s3db.req_approver_req.req_id == req_id).count(), 1)

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
    def testReqApproveFinalApprovalNotifiesWarehouseOperators(self):
        """req_approve notifies warehouse operators once the final approver signs off"""

        db = current.db
        s3db = current.s3db
        auth = current.auth

        # Create a submitted request whose item has already been matched to a warehouse
        requester = self.create_office(name="Requester Site")
        warehouse = self.create_office(name="Approved Warehouse")
        approver_id = self.create_person(last_name="Approver Final")
        operator_id = self.create_person(last_name="Warehouse Operator")
        operator_user_id = self.create_user_for_person(operator_id, language="pl")
        self.create_group_membership(operator_user_id,
                                     "wh_operator",
                                     role="Warehouse Operator",
                                     pe_id=warehouse.pe_id,
                                     )

        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(requester.site_id,
                                     req_type=1,
                                     req_ref="REQ-APPROVE-001",
                                     workflow_status=2,
                                     )
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=2,
                                               )
        db(s3db.req_req_item.id == req_item_id).update(site_id=warehouse.site_id)
        record = db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                      limitby=(0, 1),
                                                      ).first()
        operator_pe_id = db(s3db.pr_person.id == operator_id).select(s3db.pr_person.pe_id,
                                                                     limitby=(0, 1),
                                                                     ).first().pe_id

        sent = []
        saved_approvers = req_module.req_approvers
        saved_logged_in = auth.s3_logged_in_person
        saved_ancestors = s3db.pr_get_ancestors
        saved_sender = current.msg.send_by_pe_id
        saved_redirect = req_module.redirect
        current.session.confirmation = None

        try:
            # Drive the workflow through the final-approval branch and capture operator notifications
            req_module.req_approvers = lambda site_id: {
                approver_id: {"matcher": False, "title": "Approver"},
            }
            auth.s3_logged_in_person = lambda: approver_id
            s3db.pr_get_ancestors = lambda pe_id: []
            current.msg.send_by_pe_id = lambda pe_id, **kwargs: sent.append((pe_id, kwargs))
            req_module.redirect = lambda url: (_ for _ in ()).throw(RedirectIntercept(url))

            with self.assertRaises(RedirectIntercept) as redirect:
                RequestModel.req_approve(Storage(record=record,
                                                id=req_id,
                                                unauthorised=lambda: self.fail("approve unauthorised"),
                                                ))
        finally:
            req_module.req_approvers = saved_approvers
            auth.s3_logged_in_person = saved_logged_in
            s3db.pr_get_ancestors = saved_ancestors
            current.msg.send_by_pe_id = saved_sender
            req_module.redirect = saved_redirect

        approval = db(s3db.req_approver_req.req_id == req_id).select(s3db.req_approver_req.person_id,
                                                                     limitby=(0, 1),
                                                                     ).first()
        status = db(s3db.req_req.id == req_id).select(s3db.req_req.workflow_status,
                                                      limitby=(0, 1),
                                                      ).first()
        self.assertIsNotNone(approval)
        self.assertEqual(approval.person_id, approver_id)
        self.assertEqual(status.workflow_status, 3)
        self.assertEqual(current.session.confirmation, "Request Approved")
        self.assertTrue(str(redirect.exception.url).endswith("/%s" % req_id))
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][0], operator_pe_id)
        self.assertIn("REQ-APPROVE-001", sent[0][1]["subject"])
        self.assertIn("Approved Warehouse", sent[0][1]["message"])
        self.assertIn("/req/req/%s/req_item" % req_id, sent[0][1]["message"])

    # -------------------------------------------------------------------------
    def testReqApproveFallsBackToLogsManagerWithDefaultRealm(self):
        """req_approve falls back to logs_manager users with matching default realms"""

        db = current.db
        s3db = current.s3db
        auth = current.auth

        requester = self.create_office(name="Fallback Requester")
        warehouse = self.create_office(name="Fallback Warehouse")
        approver_id = self.create_person(last_name="Fallback Approver")
        logs_manager_id = self.create_person(last_name="Fallback Logs")
        logs_user_id = self.create_user_for_person(logs_manager_id, language="pl")
        self.create_group_membership(logs_user_id,
                                     "logs_manager",
                                     role="Logs Manager",
                                     pe_id=None,
                                     )
        logs_pe_id = db(s3db.pr_person.id == logs_manager_id).select(s3db.pr_person.pe_id,
                                                                     limitby=(0, 1),
                                                                     ).first().pe_id
        s3db.pr_add_affiliation(warehouse.pe_id,
                                logs_pe_id,
                                role="Warehouse Realm",
                                role_type=req_module.OU,
                                )

        item_id = self.create_supply_item(name="Fallback Item")
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(requester.site_id,
                                     req_type=1,
                                     req_ref="REQ-LOGS-001",
                                     workflow_status=2,
                                     )
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=1,
                                               )
        db(s3db.req_req_item.id == req_item_id).update(site_id=warehouse.site_id)
        record = db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                      limitby=(0, 1),
                                                      ).first()

        sent = []
        saved_approvers = req_module.req_approvers
        saved_logged_in = auth.s3_logged_in_person
        saved_ancestors = s3db.pr_get_ancestors
        saved_sender = current.msg.send_by_pe_id
        saved_redirect = req_module.redirect

        try:
            req_module.req_approvers = lambda site_id: {
                approver_id: {"matcher": False, "title": "Approver"},
            }
            auth.s3_logged_in_person = lambda: approver_id
            s3db.pr_get_ancestors = lambda pe_id: []
            current.msg.send_by_pe_id = lambda pe_id, **kwargs: sent.append((pe_id, kwargs))
            req_module.redirect = lambda url: (_ for _ in ()).throw(RedirectIntercept(url))

            with self.assertRaises(RedirectIntercept):
                RequestModel.req_approve(Storage(record=record,
                                                id=req_id,
                                                unauthorised=lambda: self.fail("approve unauthorised"),
                                                ))
        finally:
            req_module.req_approvers = saved_approvers
            auth.s3_logged_in_person = saved_logged_in
            s3db.pr_get_ancestors = saved_ancestors
            current.msg.send_by_pe_id = saved_sender
            req_module.redirect = saved_redirect

        recipients = [pe_id for pe_id, _ in sent]
        self.assertIn(logs_pe_id, recipients)
        message = next(kwargs for pe_id, kwargs in sent if pe_id == logs_pe_id)
        self.assertIn("REQ-LOGS-001", message["subject"])

    # -------------------------------------------------------------------------
    def testReqApproveFallsBackToAdminWithoutWarehouseOrLogsManagers(self):
        """req_approve falls back to ADMIN when no warehouse or logs-manager users match"""

        db = current.db
        s3db = current.s3db
        auth = current.auth

        requester = self.create_office(name="Admin Fallback Requester")
        warehouse = self.create_office(name="Admin Fallback Warehouse")
        approver_id = self.create_person(last_name="Admin Fallback Approver")
        admin_id = self.create_person(last_name="Admin Fallback User")
        admin_user_id = self.create_user_for_person(admin_id, language="en")
        self.create_group_membership(admin_user_id,
                                     "ADMIN",
                                     role="Administrator",
                                     pe_id=None,
                                     )
        admin_pe_id = db(s3db.pr_person.id == admin_id).select(s3db.pr_person.pe_id,
                                                               limitby=(0, 1),
                                                               ).first().pe_id

        item_id = self.create_supply_item(name="Admin Fallback Item")
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(requester.site_id,
                                     req_type=1,
                                     req_ref="REQ-ADMIN-001",
                                     workflow_status=2,
                                     )
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=1,
                                               )
        db(s3db.req_req_item.id == req_item_id).update(site_id=warehouse.site_id)
        record = db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                      limitby=(0, 1),
                                                      ).first()

        sent = []
        saved_approvers = req_module.req_approvers
        saved_logged_in = auth.s3_logged_in_person
        saved_ancestors = s3db.pr_get_ancestors
        saved_sender = current.msg.send_by_pe_id
        saved_redirect = req_module.redirect

        try:
            req_module.req_approvers = lambda site_id: {
                approver_id: {"matcher": False, "title": "Approver"},
            }
            auth.s3_logged_in_person = lambda: approver_id
            s3db.pr_get_ancestors = lambda pe_id: []
            current.msg.send_by_pe_id = lambda pe_id, **kwargs: sent.append((pe_id, kwargs))
            req_module.redirect = lambda url: (_ for _ in ()).throw(RedirectIntercept(url))

            with self.assertRaises(RedirectIntercept):
                RequestModel.req_approve(Storage(record=record,
                                                id=req_id,
                                                unauthorised=lambda: self.fail("approve unauthorised"),
                                                ))
        finally:
            req_module.req_approvers = saved_approvers
            auth.s3_logged_in_person = saved_logged_in
            s3db.pr_get_ancestors = saved_ancestors
            current.msg.send_by_pe_id = saved_sender
            req_module.redirect = saved_redirect

        recipients = [pe_id for pe_id, _ in sent]
        self.assertIn(admin_pe_id, recipients)
        message = next(kwargs for pe_id, kwargs in sent if pe_id == admin_pe_id)
        self.assertIn("REQ-ADMIN-001", message["subject"])

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

    # -------------------------------------------------------------------------
    def testReqApproveAllowsMatchersWhenOutstandingItemsAreAlreadyOrdered(self):
        """req_approve lets matchers continue once every unmatched item already has an order entry"""

        db = current.db
        s3db = current.s3db
        auth = current.auth

        # Create one unmatched request item that has already been moved into purchasing
        office = self.create_office()
        person_id = self.create_person(last_name="Matcher")
        other_id = self.create_person(last_name="Reviewer")
        item_id = self.create_supply_item()
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(office.site_id,
                                     workflow_status=2,
                                     )
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=2,
                                               )
        s3db.req_order_item.insert(req_item_id=req_item_id,
                                   req_id=req_id,
                                   item_id=item_id,
                                   item_pack_id=pack_id,
                                   quantity=2,
                                   )
        record = db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                      limitby=(0, 1),
                                                      ).first()

        saved_approvers = req_module.req_approvers
        saved_logged_in = auth.s3_logged_in_person
        saved_sender = current.msg.send_by_pe_id
        saved_redirect = req_module.redirect
        current.session.confirmation = None
        current.session.warning = None

        try:
            # Keep this as a non-final approval while exercising the matcher/order branch
            req_module.req_approvers = lambda site_id: {
                person_id: {"matcher": True, "title": "Matcher"},
                other_id: {"matcher": False, "title": "Reviewer"},
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

        approval = db(s3db.req_approver_req.req_id == req_id).select(s3db.req_approver_req.person_id,
                                                                     s3db.req_approver_req.title,
                                                                     limitby=(0, 1),
                                                                     ).first()
        status = db(s3db.req_req.id == req_id).select(s3db.req_req.workflow_status,
                                                      limitby=(0, 1),
                                                      ).first()
        self.assertIsNotNone(approval)
        self.assertEqual(approval.person_id, person_id)
        self.assertEqual(approval.title, "Matcher")
        self.assertEqual(status.workflow_status, 2)
        self.assertEqual(current.session.confirmation, "Request Approved")
        self.assertTrue(str(redirect.exception.url).endswith("/%s" % req_id))
        self.assertEqual(current.session.warning, None)


# =============================================================================
class ReqMatchingTests(SupplyChainTestCase):
    """Tests for request matching helpers and methods"""

    # -------------------------------------------------------------------------
    def testCheckMethodRoutesByRequestType(self):
        """req_CheckMethod dispatches item and skill requests to the correct matcher"""

        method = req_module.req_CheckMethod()

        saved_inv_match = req_module.req_CheckMethod.inv_match
        saved_skills_match = req_module.req_CheckMethod.skills_match

        try:
            req_module.req_CheckMethod.inv_match = staticmethod(lambda r, **attr: "INV")
            req_module.req_CheckMethod.skills_match = staticmethod(lambda r, **attr: "SKILLS")

            item = method.apply_method(Storage(record=Storage(type=1)))
            people = method.apply_method(Storage(record=Storage(type=3)))

            errors = []
            other = method.apply_method(Storage(record=Storage(type=9),
                                                error=lambda code, message: errors.append((code, message)),
                                                ))
        finally:
            req_module.req_CheckMethod.inv_match = saved_inv_match
            req_module.req_CheckMethod.skills_match = saved_skills_match

        self.assertEqual(item, "INV")
        self.assertEqual(people, "SKILLS")
        self.assertIsNone(other)
        self.assertEqual(errors, [(405, current.ERROR.BAD_METHOD)])

    # -------------------------------------------------------------------------
    def testReqMatchReturnsEmptyOutputWithoutValidViewing(self):
        """req_match returns an empty payload without a valid viewing context"""

        request = current.request

        saved_vars = request.vars
        saved_get_vars = request.get_vars
        saved__vars = request._vars
        saved__get_vars = request._get_vars

        try:
            # Missing viewing means there is nothing to match against
            query = Storage()
            request.vars = request.get_vars = request._vars = request._get_vars = query
            self.assertEqual(req_module.req_match(), {})

            # Malformed viewing syntax must also short-circuit cleanly
            query = Storage(viewing="warehouse")
            request.vars = request.get_vars = request._vars = request._get_vars = query
            self.assertEqual(req_module.req_match(), {})
        finally:
            request.vars = saved_vars
            request.get_vars = saved_get_vars
            request._vars = saved__vars
            request._get_vars = saved__get_vars

    # -------------------------------------------------------------------------
    def testReqMatchConfiguresActionsFiltersAndCrudHooks(self):
        """req_match configures request actions, filters and CRUD hooks for a viewed site"""

        request = current.request
        response_s3 = current.response.s3
        settings = current.deployment_settings
        auth = current.auth

        office = self.create_office(name="Viewed Site")

        saved_vars = request.vars
        saved_get_vars = request.get_vars
        saved__vars = request._vars
        saved__get_vars = request._get_vars
        saved_actions = getattr(response_s3, "actions", None)
        saved_prep = getattr(response_s3, "prep", None)
        saved_postp = getattr(response_s3, "postp", None)
        saved_filter = getattr(response_s3, "filter", None)
        saved_crud_controller = current.crud_controller
        saved_permission = auth.s3_has_permission
        saved_use_commit = settings.req.get("use_commit")
        saved_workflow = settings.req.get("workflow")
        labels = []
        filters = []
        postp_output = None

        try:
            # Drive the full branch for a viewed site with commit actions enabled
            query = Storage(viewing="org_office.%s" % office.id)
            request.vars = request.get_vars = request._vars = request._get_vars = query
            response_s3.actions = []
            auth.s3_has_permission = lambda *args, **kwargs: True
            settings.req.use_commit = True
            settings.req.workflow = True
            current.crud_controller = lambda *args, **kwargs: Storage(args=args,
                                                                      kwargs=kwargs,
                                                                      prep=response_s3.prep,
                                                                      postp=response_s3.postp,
                                                                      filter=response_s3.filter,
                                                                      actions=list(response_s3.actions),
                                                                      )

            output = req_module.req_match(rheader="RHEADER")
            labels = [str(action["label"]) for action in output.actions]
            self.assertEqual(output.args, ("req", "req"))
            self.assertEqual(output.kwargs["rheader"], "RHEADER")
            self.assertIn("Check", labels)
            self.assertIn("Commit", labels)
            self.assertIsNotNone(output.filter)

            self.assertTrue(output.prep(Storage(resource=Storage(add_filter=lambda query: filters.append(query)))))
            self.assertEqual(len(filters), 1)

            postp_output = output.postp(Storage(representation="html"), {})
        finally:
            request.vars = saved_vars
            request.get_vars = saved_get_vars
            request._vars = saved__vars
            request._get_vars = saved__get_vars
            response_s3.actions = saved_actions
            response_s3.prep = saved_prep
            response_s3.postp = saved_postp
            response_s3.filter = saved_filter
            current.crud_controller = saved_crud_controller
            auth.s3_has_permission = saved_permission
            settings.req.use_commit = saved_use_commit
            settings.req.workflow = saved_workflow

        self.assertEqual(postp_output["title"],
                         current.response.s3.crud_strings["org_office"].title_display)

    # -------------------------------------------------------------------------
    def testReqMatchHandlesCustomisationErrorsAndImplicitOfficeHeaders(self):
        """req_match logs customisation failures and falls back to the office rheader"""

        request = current.request
        response_s3 = current.response.s3
        settings = current.deployment_settings
        auth = current.auth

        office = self.create_office(name="Customised Office")

        saved_vars = request.vars
        saved_get_vars = request.get_vars
        saved__vars = request._vars
        saved__get_vars = request._get_vars
        saved_actions = getattr(response_s3, "actions", None)
        saved_prep = getattr(response_s3, "prep", None)
        saved_postp = getattr(response_s3, "postp", None)
        saved_filter = getattr(response_s3, "filter", None)
        saved_crud_controller = current.crud_controller
        saved_permission = auth.s3_has_permission
        saved_customise = settings.get("customise_org_office_resource")
        saved_log_error = current.log.error

        errors = []

        def broken_customise(request, tablename):
            raise AttributeError("broken")

        try:
            query = Storage(viewing="org_office.%s" % office.id)
            request.vars = request.get_vars = request._vars = request._get_vars = query
            response_s3.actions = []
            auth.s3_has_permission = lambda *args, **kwargs: False
            settings["customise_org_office_resource"] = broken_customise
            current.log.error = lambda message: errors.append(message)
            current.crud_controller = lambda *args, **kwargs: Storage(args=args,
                                                                      kwargs=kwargs,
                                                                      prep=response_s3.prep,
                                                                      postp=response_s3.postp,
                                                                      actions=list(response_s3.actions),
                                                                      )

            output = req_module.req_match()
            labels = [str(action["label"]) for action in output.actions]
            non_html = output.postp(Storage(representation="json"),
                                    {"keep": "value"},
                                    )
        finally:
            request.vars = saved_vars
            request.get_vars = saved_get_vars
            request._vars = saved__vars
            request._get_vars = saved__get_vars
            response_s3.actions = saved_actions
            response_s3.prep = saved_prep
            response_s3.postp = saved_postp
            response_s3.filter = saved_filter
            current.crud_controller = saved_crud_controller
            auth.s3_has_permission = saved_permission
            if saved_customise is None:
                settings.pop("customise_org_office_resource", None)
            else:
                settings["customise_org_office_resource"] = saved_customise
            current.log.error = saved_log_error

        self.assertEqual(output.kwargs["rheader"], current.s3db.org_rheader)
        self.assertEqual(labels, ["Check"])
        self.assertEqual(non_html, {"keep": "value"})
        self.assertTrue(any("customise_org_office_resource" in error for error in errors))

    # -------------------------------------------------------------------------
    def testReqMatchSelectsFacilitySpecificRheaders(self):
        """req_match selects facility-specific fallback rheaders from the viewing resource"""

        request = current.request
        response_s3 = current.response.s3
        auth = current.auth
        s3db = current.s3db

        organisation_id = self.create_organisation(name="Facility Match Org")
        ftable = s3db.org_facility
        facility = Storage(name="Facility Match Site",
                           organisation_id=organisation_id,
                           )
        facility_id = ftable.insert(**facility)
        facility.update(id=facility_id)
        s3db.update_super(ftable, facility)
        warehouse_id = self.create_warehouse(name="Warehouse Match Site")

        saved_vars = request.vars
        saved_get_vars = request.get_vars
        saved__vars = request._vars
        saved__get_vars = request._get_vars
        saved_actions = getattr(response_s3, "actions", None)
        saved_prep = getattr(response_s3, "prep", None)
        saved_postp = getattr(response_s3, "postp", None)
        saved_filter = getattr(response_s3, "filter", None)
        saved_crud_controller = current.crud_controller
        saved_permission = auth.s3_has_permission
        saved_facility_rheader = s3db.org_facility_rheader
        saved_inv_rheader = s3db.inv_rheader

        try:
            response_s3.actions = []
            auth.s3_has_permission = lambda *args, **kwargs: False
            current.crud_controller = lambda *args, **kwargs: Storage(args=args,
                                                                      kwargs=kwargs,
                                                                      prep=response_s3.prep,
                                                                      postp=response_s3.postp,
                                                                      actions=list(response_s3.actions),
                                                                      )
            s3db.org_facility_rheader = "FACILITY-RHEADER"
            s3db.inv_rheader = "INV-RHEADER"

            query = Storage(viewing="org_facility.%s" % facility_id)
            request.vars = request.get_vars = request._vars = request._get_vars = query
            facility_output = req_module.req_match()

            query = Storage(viewing="inv_warehouse.%s" % warehouse_id)
            request.vars = request.get_vars = request._vars = request._get_vars = query
            warehouse_output = req_module.req_match()
        finally:
            request.vars = saved_vars
            request.get_vars = saved_get_vars
            request._vars = saved__vars
            request._get_vars = saved__get_vars
            response_s3.actions = saved_actions
            response_s3.prep = saved_prep
            response_s3.postp = saved_postp
            response_s3.filter = saved_filter
            current.crud_controller = saved_crud_controller
            auth.s3_has_permission = saved_permission
            s3db.org_facility_rheader = saved_facility_rheader
            s3db.inv_rheader = saved_inv_rheader

        self.assertEqual(facility_output.kwargs["rheader"], "FACILITY-RHEADER")
        self.assertEqual(warehouse_output.kwargs["rheader"], "INV-RHEADER")

    # -------------------------------------------------------------------------
    def testInvMatchShowsAvailableStockAndSendAction(self):
        """inv_match renders stock matches and exposes the send action when stock exists"""

        response = current.response
        response_s3 = response.s3

        requester = self.create_office(name="Requester")
        sender = self.create_office(name="Sender")
        item_id = self.create_supply_item(name="Matched Item")
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(requester.site_id, req_type=1)
        self.create_request_item(req_id,
                                 item_id,
                                 pack_id,
                                 quantity=3,
                                 )
        self.create_inventory_item(sender.site_id,
                                   item_id,
                                   pack_id,
                                   quantity=5,
                                   status=0,
                                   )

        saved_rheader = req_module.req_rheader
        saved_view = response.view
        saved_warning = response.warning
        saved_rfooter = getattr(response_s3, "rfooter", None)

        try:
            # Supply a minimal rheader container and inspect the rendered stock comparison
            req_module.req_rheader = lambda r, check_page=False: DIV(TABLE())
            response.warning = None
            response_s3.rfooter = None

            r = Storage(id=req_id,
                        record=Storage(site_id=requester.site_id),
                        get_vars=Storage(site_id=str(sender.site_id)),
                        now=current.request.now,
                        )
            output = req_module.req_CheckMethod.inv_match(r)
            rfooter = response_s3.rfooter
        finally:
            req_module.req_rheader = saved_rheader
            response.view = saved_view
            response.warning = saved_warning
            response_s3.rfooter = saved_rfooter

        items = str(output["items"])
        self.assertEqual(output["title"], "Check Request")
        self.assertEqual(output["subtitle"], "Requested Items")
        self.assertIn("5.0", items)
        self.assertIn("YES", items)
        self.assertIn("Send from", str(rfooter))
        self.assertIn("site_id=%s" % sender.site_id, str(rfooter))
        self.assertEqual(current.response.view, "list.html")

    # -------------------------------------------------------------------------
    def testInvMatchWarnsWhenNoExactStockMatchExists(self):
        """inv_match warns when the warehouse has no exact stock match for the request"""

        response = current.response

        requester = self.create_office(name="Requester")
        sender = self.create_office(name="Sender")
        item_id = self.create_supply_item(name="Requested Item")
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(requester.site_id, req_type=1)
        self.create_request_item(req_id,
                                 item_id,
                                 pack_id,
                                 quantity=2,
                                 )

        saved_rheader = req_module.req_rheader
        saved_warning = response.warning

        try:
            # No stock rows should keep the comparison view but raise a warning
            req_module.req_rheader = lambda r, check_page=False: DIV(TABLE())
            response.warning = None

            r = Storage(id=req_id,
                        record=Storage(site_id=requester.site_id),
                        get_vars=Storage(site_id=str(sender.site_id)),
                        now=current.request.now,
                        )
            output = req_module.req_CheckMethod.inv_match(r)
            warning = response.warning
        finally:
            req_module.req_rheader = saved_rheader
            response.warning = saved_warning

        self.assertIn("NO", str(output["items"]))
        self.assertIn("has no items exactly matching this request", str(warning))

    # -------------------------------------------------------------------------
    def testInvMatchShowsDistancePartialAndNotApplicableRows(self):
        """inv_match renders distance, partial matches and fully-covered items as N/A"""

        db = current.db
        ltable = current.s3db.gis_location
        response = current.response
        response_s3 = response.s3

        requester_location = ltable.insert(name="Requester Match Location",
                                           lat=52.2297,
                                           lon=21.0122,
                                           )
        sender_location = ltable.insert(name="Sender Match Location",
                                        lat=50.0647,
                                        lon=19.9450,
                                        )
        requester = self.create_office(name="Distance Requester",
                                       location_id=requester_location,
                                       )
        sender = self.create_office(name="Distance Sender",
                                    location_id=sender_location,
                                    )
        matched_item = self.create_supply_item(name="Partially Matched Item")
        matched_pack = self.create_item_pack(matched_item, quantity=1)
        covered_item = self.create_supply_item(name="Already Covered Item")
        covered_pack = self.create_item_pack(covered_item, quantity=1)
        req_id = self.create_request(requester.site_id, req_type=1)
        self.create_request_item(req_id,
                                 matched_item,
                                 matched_pack,
                                 quantity=5,
                                 )
        self.create_request_item(req_id,
                                 covered_item,
                                 covered_pack,
                                 quantity=2,
                                 quantity_fulfil=2,
                                 )
        self.create_inventory_item(sender.site_id,
                                   matched_item,
                                   matched_pack,
                                   quantity=1,
                                   status=0,
                                   )
        self.create_inventory_item(sender.site_id,
                                   matched_item,
                                   matched_pack,
                                   quantity=2,
                                   status=0,
                                   )

        saved_rheader = req_module.req_rheader
        saved_view = response.view
        saved_warning = response.warning
        saved_rfooter = getattr(response_s3, "rfooter", None)

        try:
            req_module.req_rheader = lambda r, check_page=False: DIV(TABLE())
            response.warning = None
            response_s3.rfooter = None

            r = Storage(id=req_id,
                        record=Storage(site_id=requester.site_id),
                        get_vars=Storage(site_id=str(sender.site_id)),
                        now=current.request.now,
                        )
            output = req_module.req_CheckMethod.inv_match(r)
            rfooter = response_s3.rfooter
        finally:
            req_module.req_rheader = saved_rheader
            response.view = saved_view
            response.warning = saved_warning
            response_s3.rfooter = saved_rfooter

        items = str(output["items"])
        self.assertIn("Partial", items)
        self.assertIn("N/A", items)
        self.assertIn("Distance from", str(output["rheader"]))
        self.assertIn("Send from", str(rfooter))

    # -------------------------------------------------------------------------
    def testInvMatchRejectsMissingWarehouseContext(self):
        """inv_match reports a missing site when neither the URL nor the user provide one"""

        auth = current.auth
        response = current.response

        requester = self.create_office(name="Requester")
        item_id = self.create_supply_item(name="Unmatched Item")
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(requester.site_id, req_type=1)
        self.create_request_item(req_id,
                                 item_id,
                                 pack_id,
                                 quantity=1,
                                 )

        saved_rheader = req_module.req_rheader
        saved_error = response.error
        saved_user = auth.user

        try:
            # Without a sender site the matcher can only render an explanatory error
            req_module.req_rheader = lambda r, check_page=False: DIV(TABLE())
            response.error = None
            auth.user = Storage(site_id=None)

            r = Storage(id=req_id,
                        record=Storage(site_id=requester.site_id),
                        get_vars=Storage(),
                        now=current.request.now,
                        )
            req_module.req_CheckMethod.inv_match(r)
            error = response.error
        finally:
            req_module.req_rheader = saved_rheader
            response.error = saved_error
            auth.user = saved_user

        self.assertEqual(str(error), "User has no Site to check against!")

    # -------------------------------------------------------------------------
    def testInvMatchReturnsEmptyMessageForRequestsWithoutItems(self):
        """inv_match falls back to the CRUD empty-message when the request has no item rows"""

        response = current.response

        requester = self.create_office(name="Requester")
        req_id = self.create_request(requester.site_id, req_type=1)

        saved_rheader = req_module.req_rheader
        saved_view = response.view

        try:
            # Empty requests should use the configured CRUD empty-message instead of a table
            req_module.req_rheader = lambda r, check_page=False: DIV(TABLE())
            r = Storage(id=req_id,
                        record=Storage(site_id=requester.site_id),
                        get_vars=Storage(site_id=str(requester.site_id)),
                        now=current.request.now,
                        )
            output = req_module.req_CheckMethod.inv_match(r)
        finally:
            req_module.req_rheader = saved_rheader
            response.view = saved_view

        self.assertEqual(output["items"],
                         current.response.s3.crud_strings.req_req_item.msg_list_empty)
        self.assertEqual(current.response.view, "list.html")

    # -------------------------------------------------------------------------
    def testSkillsMatchShowsMatchingPeopleAndAssignAction(self):
        """skills_match renders matching people counts and exposes the assign action"""

        s3db = current.s3db
        response = current.response
        response_s3 = response.s3

        office = self.create_office(name="Skills Requester")
        req_id = self.create_request(office.site_id, req_type=3)
        skill_id = self.create_skill("Forklift")
        self.create_request_skill(req_id,
                                  skill_ids=[skill_id],
                                  quantity=1,
                                  )

        person_id = self.create_person(last_name="Matcher")
        s3db.hrm_human_resource.insert(person_id=person_id,
                                       organisation_id=office.organisation_id,
                                       )
        s3db.hrm_competency.insert(person_id=person_id,
                                   skill_id=skill_id,
                                   )

        saved_rheader = req_module.req_rheader
        saved_rfooter = getattr(response_s3, "rfooter", None)
        saved_view = response.view

        try:
            # Matching competencies in the selected organisation should expose the assign action
            req_module.req_rheader = lambda r, check_page=False: DIV(TABLE())
            response_s3.rfooter = None

            r = Storage(id=req_id,
                        record=Storage(site_id=office.site_id),
                        get_vars=Storage(organisation_id=str(office.organisation_id)),
                        )
            output = req_module.req_CheckMethod.skills_match(r)
            rfooter = response_s3.rfooter
        finally:
            req_module.req_rheader = saved_rheader
            response_s3.rfooter = saved_rfooter
            response.view = saved_view

        items = str(output["items"])
        self.assertEqual(output["title"], "Check Request")
        self.assertEqual(output["subtitle"], "Requested Skills")
        # Skill-name rendering is covered separately in req_skill_represent;
        # here we only verify the matching summary and follow-up action.
        self.assertIn("YES", items)
        self.assertIn("Assign People to this Request", str(rfooter))
        self.assertEqual(current.response.view, "list.html")

    # -------------------------------------------------------------------------
    def testSkillsMatchRejectsMissingOrganisationContext(self):
        """skills_match reports a missing organisation when no context is available"""

        auth = current.auth
        response = current.response

        office = self.create_office(name="Skills Requester")
        req_id = self.create_request(office.site_id, req_type=3)
        skill_id = self.create_skill("Driver")
        self.create_request_skill(req_id,
                                  skill_ids=[skill_id],
                                  quantity=1,
                                  )

        saved_rheader = req_module.req_rheader
        saved_error = response.error
        saved_user = auth.user

        try:
            # Without an organisation context the matcher should stop with an explanatory error
            req_module.req_rheader = lambda r, check_page=False: DIV(TABLE())
            response.error = None
            auth.user = Storage(organisation_id=None)

            r = Storage(id=req_id,
                        record=Storage(site_id=office.site_id),
                        get_vars=Storage(),
                        )
            req_module.req_CheckMethod.skills_match(r)
            error = response.error
        finally:
            req_module.req_rheader = saved_rheader
            response.error = saved_error
            auth.user = saved_user

        self.assertEqual(str(error), "User has no Organization to check against!")

    # -------------------------------------------------------------------------
    def testSkillsMatchReturnsEmptyMessageForRequestsWithoutSkills(self):
        """skills_match falls back to the CRUD empty-message when the request has no skill rows"""

        response = current.response

        office = self.create_office(name="Skills Requester")
        req_id = self.create_request(office.site_id, req_type=3)

        saved_rheader = req_module.req_rheader
        saved_view = response.view

        try:
            # Empty skill requests should use the configured CRUD empty-message instead of a table
            req_module.req_rheader = lambda r, check_page=False: DIV(TABLE())
            r = Storage(id=req_id,
                        record=Storage(site_id=office.site_id),
                        get_vars=Storage(organisation_id=str(office.organisation_id)),
                        )
            output = req_module.req_CheckMethod.skills_match(r)
        finally:
            req_module.req_rheader = saved_rheader
            response.view = saved_view

        self.assertEqual(output["items"],
                         current.response.s3.crud_strings.req_req_skill.msg_list_empty)
        self.assertEqual(current.response.view, "list.html")

    # -------------------------------------------------------------------------
    def testSkillsMatchShowsPartialAndNoMatchesInOneResponse(self):
        """skills_match distinguishes partial and missing matches across skill rows"""

        s3db = current.s3db
        response = current.response
        response_s3 = response.s3

        office = self.create_office(name="Partial Skills Requester")
        req_id = self.create_request(office.site_id, req_type=3)
        skill_a = self.create_skill("Driver")
        skill_b = self.create_skill("Mechanic")
        skill_c = self.create_skill("Medic")
        self.create_request_skill(req_id,
                                  skill_ids=[skill_a],
                                  quantity=3,
                                  )
        self.create_request_skill(req_id,
                                  skill_ids=[skill_b, skill_c],
                                  quantity=1,
                                  )

        person_1 = self.create_person(last_name="Multi Skilled")
        person_2 = self.create_person(last_name="Single Skilled")
        s3db.hrm_human_resource.insert(person_id=person_1,
                                       organisation_id=office.organisation_id,
                                       )
        s3db.hrm_human_resource.insert(person_id=person_2,
                                       organisation_id=office.organisation_id,
                                       )
        s3db.hrm_competency.insert(person_id=person_1,
                                   skill_id=skill_a,
                                   )
        s3db.hrm_competency.insert(person_id=person_1,
                                   skill_id=skill_b,
                                   )
        s3db.hrm_competency.insert(person_id=person_2,
                                   skill_id=skill_a,
                                   )

        saved_rheader = req_module.req_rheader
        saved_rfooter = getattr(response_s3, "rfooter", None)
        saved_view = response.view

        try:
            req_module.req_rheader = lambda r, check_page=False: DIV(TABLE())
            response_s3.rfooter = None

            r = Storage(id=req_id,
                        record=Storage(site_id=office.site_id),
                        get_vars=Storage(organisation_id=str(office.organisation_id)),
                        )
            output = req_module.req_CheckMethod.skills_match(r)
            rfooter = response_s3.rfooter
        finally:
            req_module.req_rheader = saved_rheader
            response_s3.rfooter = saved_rfooter
            response.view = saved_view

        items = str(output["items"])
        self.assertIn("Partial", items)
        self.assertIn("NO", items)
        self.assertIn("Assign People to this Request", str(rfooter))

    # -------------------------------------------------------------------------
    def testSkillsMatchMarksAlreadyFulfilledSkillsAsNotApplicable(self):
        """skills_match marks already fulfilled skill rows as not applicable instead of missing"""

        response = current.response
        response_s3 = response.s3

        office = self.create_office(name="Satisfied Skills Requester")
        req_id = self.create_request(office.site_id, req_type=3)
        skill_id = self.create_skill("Satisfied Skill")
        self.create_request_skill(req_id,
                                  skill_ids=[skill_id],
                                  quantity=1,
                                  quantity_fulfil=1,
                                  )

        saved_rheader = req_module.req_rheader
        saved_rfooter = getattr(response_s3, "rfooter", None)
        saved_view = response.view

        try:
            req_module.req_rheader = lambda r, check_page=False: DIV(TABLE())
            response_s3.rfooter = None

            r = Storage(id=req_id,
                        record=Storage(site_id=office.site_id),
                        get_vars=Storage(organisation_id=str(office.organisation_id)),
                        )
            output = req_module.req_CheckMethod.skills_match(r)
        finally:
            req_module.req_rheader = saved_rheader
            response_s3.rfooter = saved_rfooter
            response.view = saved_view

        items = str(output["items"])
        self.assertIn("N/A", items)
        self.assertNotIn("Assign People to this Request", str(response_s3.rfooter))

    # -------------------------------------------------------------------------
    def testAddFromTemplateRaisesRuntimeErrorForMissingTemplate(self):
        """req_add_from_template raises a clear runtime error for a missing template"""

        with self.assertRaises(RuntimeError) as error:
            req_add_from_template(999999)

        self.assertIn("Template not found", str(error.exception))


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
    def testReqControllerRaises404WhenModuleDisabled(self):
        """Controller import fails with HTTP 404 when the request module is disabled"""

        fake_settings = Storage(has_module=lambda module: False)

        with self.assertRaises(HTTP) as error:
            with self.controller("req",
                                 function="index",
                                 overrides={"settings": fake_settings},
                                 ):
                pass

        self.assertEqual(error.exception.status, 404)

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
    def testIsAffiliatedRequiresOrganisationForRegularUsers(self):
        """is_affiliated only returns true for regular logged-in users with an organisation"""

        auth = current.auth
        utable = auth.settings.table_user

        without_org = utable.insert(first_name="No",
                                    last_name="Org",
                                    email="%s@example.com" % self.unique_name("noorg").lower(),
                                    password="test",
                                    organisation_id=None,
                                    )
        with_org = utable.insert(first_name="With",
                                 last_name="Org",
                                 email="%s@example.com" % self.unique_name("withorg").lower(),
                                 password="test",
                                 organisation_id=self.create_organisation(),
                                 )

        saved_logged_in = auth.is_logged_in
        saved_has_role = auth.s3_has_role
        saved_user = auth.user

        try:
            with self.controller("req", function="is_affiliated") as controller:
                auth.is_logged_in = lambda: True
                auth.s3_has_role = lambda role: False

                auth.user = Storage(id=without_org)
                self.assertFalse(controller.module["is_affiliated"]())

                auth.user = Storage(id=with_org)
                self.assertTrue(controller.module["is_affiliated"]())
        finally:
            auth.is_logged_in = saved_logged_in
            auth.s3_has_role = saved_has_role
            auth.user = saved_user

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
    def testReqTemplateReqSkillBranchConfiguresSkillListFields(self):
        """req_template configures compact skill list fields inside the req_skill tab"""

        s3db = current.s3db
        saved_prompt = current.deployment_settings.req.prompt_match
        saved_list_fields = s3db.get_config("req_req_skill", "list_fields")

        try:
            with self.controller("req",
                                 function="req_template",
                                 args=["req_skill"],
                                 ) as controller:
                controller.module["req_template"].__globals__["req_controller"] = \
                    lambda template=False: \
                    Storage(template=template,
                            list_fields=s3db.get_config("req_req_skill", "list_fields"),
                            )
                output = controller.module["req_template"]()
                self.assertTrue(output.template)
                self.assertEqual(output.list_fields,
                                 ["skill_id", "quantity", "comments"])
        finally:
            current.deployment_settings.req.prompt_match = saved_prompt
            s3db.configure("req_req_skill", list_fields=saved_list_fields)

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
    def testReqControllerCreatePrepConfiguresTypedPeopleRequests(self):
        """req_controller prep configures people-request forms and labels"""

        auth = current.auth
        s3db = current.s3db
        table = s3db.req_req

        office = self.create_office()
        filters = []

        fake_settings = Storage(has_module=current.deployment_settings.has_module,
                                get_req_workflow=lambda: False,
                                get_req_req_crud_strings=lambda req_type: None,
                                get_req_items_ask_purpose=lambda: False,
                                get_req_inline_forms=lambda: False,
                                get_ui_auto_keyvalue=lambda: False,
                                )

        saved_logged_in = auth.is_logged_in
        saved_user = auth.user
        saved_default = table.type.default
        saved_readable = table.type.readable
        saved_writable = table.type.writable
        saved_date_until_readable = table.date_required_until.readable
        saved_date_until_writable = table.date_required_until.writable
        saved_purpose_label = table.purpose.label
        saved_site_label = table.site_id.label
        saved_requester_label = table.requester_id.label
        saved_request_for_label = table.request_for_id.label
        saved_recv_by_label = table.recv_by_id.label
        saved_create_label = current.response.s3.crud_strings["req_req"].label_create
        results = Storage()

        auth.is_logged_in = lambda: True
        auth.user = Storage(site_id=office.site_id)

        try:
            with self.controller("req",
                                 function="req",
                                 query_vars={"type": "3"},
                                 overrides={"settings": fake_settings},
                                 ) as controller:
                output = controller.module["req_controller"]()
                prep = output.prep
                r = Storage(table=table,
                            record=Storage(type=3,
                                           workflow_status=None,
                                           ),
                            component=None,
                            interactive=True,
                            id=None,
                            method=None,
                            http="GET",
                            resource=Storage(add_filter=lambda query: filters.append(query)),
                            representation="html",
                            )
                self.assertTrue(prep(r))
                results.type_readable = table.type.readable
                results.type_writable = table.type.writable
                results.date_until_readable = table.date_required_until.readable
                results.date_until_writable = table.date_required_until.writable
                results.purpose_label = str(table.purpose.label)
                results.site_label = str(table.site_id.label)
                results.requester_label = str(table.requester_id.label)
                results.request_for_label = str(table.request_for_id.label)
                results.recv_by_label = str(table.recv_by_id.label)
                results.create_label = str(current.response.s3.crud_strings["req_req"].label_create)
        finally:
            auth.is_logged_in = saved_logged_in
            auth.user = saved_user
            table.type.default = saved_default
            table.type.readable = saved_readable
            table.type.writable = saved_writable
            table.date_required_until.readable = saved_date_until_readable
            table.date_required_until.writable = saved_date_until_writable
            table.purpose.label = saved_purpose_label
            table.site_id.label = saved_site_label
            table.requester_id.label = saved_requester_label
            table.request_for_id.label = saved_request_for_label
            table.recv_by_id.label = saved_recv_by_label
            current.response.s3.crud_strings["req_req"].label_create = saved_create_label

        self.assertFalse(results.type_readable)
        self.assertFalse(results.type_writable)
        self.assertTrue(results.date_until_readable)
        self.assertTrue(results.date_until_writable)
        self.assertEqual(results.purpose_label, "Task Details")
        self.assertEqual(results.site_label, "Report To")
        self.assertEqual(results.requester_label, "Volunteer Contact")
        self.assertEqual(results.request_for_label, "Report To")
        self.assertEqual(results.recv_by_label, "Reported To")
        self.assertEqual(results.create_label, "Make People Request")
        self.assertEqual(len(filters), 1)

    # -------------------------------------------------------------------------
    def testReqControllerInvItemShortcutAssignsSenderSiteAndRunsOnaccept(self):
        """req_controller handles inv-item shortcuts by fixing req_item.site_id and firing onaccept"""

        auth = current.auth
        db = current.db
        s3db = current.s3db
        table = s3db.req_req

        requester = self.create_office(name="Shortcut Requester")
        sender = self.create_office(name="Shortcut Sender")
        item_id = self.create_supply_item(name="Shortcut Item")
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(requester.site_id, req_type=1)
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=2,
                                               )
        inv_item_id = self.create_inventory_item(sender.site_id,
                                                 item_id,
                                                 pack_id,
                                                 quantity=5,
                                                 )
        record = db(table.id == req_id).select(table.ALL,
                                               limitby=(0, 1),
                                               ).first()

        fake_settings = Storage(has_module=current.deployment_settings.has_module,
                                get_req_workflow=lambda: False,
                                get_req_req_crud_strings=lambda req_type: None,
                                get_req_items_ask_purpose=lambda: False,
                                get_req_inline_forms=lambda: False,
                                get_ui_auto_keyvalue=lambda: False,
                                )

        saved_permission = auth.s3_has_permission
        saved_onaccept = s3db.get_config("req_req_item", "onaccept")
        seen = []

        auth.s3_has_permission = lambda *args, **kwargs: True
        s3db.configure("req_req_item",
                       onaccept=lambda form: seen.append((form.vars.id, form.vars.site_id)),
                       )

        try:
            with self.controller("req",
                                 function="req",
                                 query_vars={"type": "1",
                                             "inv_item_id": str(inv_item_id),
                                             "req_item_id": str(req_item_id),
                                             },
                                 overrides={"settings": fake_settings},
                                 ) as controller:
                output = controller.module["req_controller"]()
                prep = output.prep
                r = Storage(table=table,
                            record=record,
                            component=None,
                            interactive=True,
                            id=req_id,
                            method=None,
                            http="GET",
                            resource=Storage(add_filter=lambda query: None),
                            representation="html",
                            unauthorised=lambda: (_ for _ in ()).throw(AssertionError("unexpected unauthorised")),
                            )
                self.assertTrue(prep(r))
                confirmation = str(current.response.confirmation)
        finally:
            auth.s3_has_permission = saved_permission
            s3db.configure("req_req_item", onaccept=saved_onaccept)

        req_item = db(s3db.req_req_item.id == req_item_id).select(s3db.req_req_item.site_id,
                                                                  limitby=(0, 1),
                                                                  ).first()
        self.assertEqual(req_item.site_id, sender.site_id)
        self.assertEqual(seen, [(str(req_item_id), sender.site_id)])
        self.assertIn("requested from", confirmation)

    # -------------------------------------------------------------------------
    def testReqControllerInvItemShortcutRejectsUnauthorisedUpdates(self):
        """req_controller rejects inventory shortcuts without req_item update permission"""

        auth = current.auth
        db = current.db
        s3db = current.s3db
        table = s3db.req_req

        requester = self.create_office(name="Denied Requester")
        sender = self.create_office(name="Denied Sender")
        item_id = self.create_supply_item(name="Denied Item")
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(requester.site_id, req_type=1)
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=1,
                                               )
        inv_item_id = self.create_inventory_item(sender.site_id,
                                                 item_id,
                                                 pack_id,
                                                 quantity=2,
                                                 )
        record = db(table.id == req_id).select(table.ALL,
                                               limitby=(0, 1),
                                               ).first()

        saved_permission = auth.s3_has_permission
        auth.s3_has_permission = lambda *args, **kwargs: False

        try:
            with self.controller("req",
                                 function="req",
                                 query_vars={"type": "1",
                                             "inv_item_id": str(inv_item_id),
                                             "req_item_id": str(req_item_id),
                                             },
                                 ) as controller:
                prep = controller.module["req_controller"]().prep
                r = Storage(table=table,
                            record=record,
                            component=None,
                            interactive=True,
                            id=req_id,
                            method=None,
                            http="GET",
                            resource=Storage(add_filter=lambda query: None),
                            representation="html",
                            unauthorised=lambda: (_ for _ in ()).throw(RuntimeError("DENIED")),
                            )
                with self.assertRaisesRegex(RuntimeError, "DENIED"):
                    prep(r)
        finally:
            auth.s3_has_permission = saved_permission

    # -------------------------------------------------------------------------
    def testReqControllerPrepAppliesCustomCrudStringsAndPlainViews(self):
        """req_controller prep applies custom CRUD strings and tolerates plain representations"""

        settings = current.deployment_settings
        s3db = current.s3db
        table = s3db.req_req

        saved_req_crud_strings = settings.req.get("req_crud_strings")
        saved_req_types = settings.req.get("req_type")
        saved_label = current.response.s3.crud_strings["req_req"].label_create

        try:
            settings.req.req_crud_strings = {1: Storage(label_create="Custom Stock Request",
                                                        marker="custom",
                                                        )}
            settings.req.req_type = ["Stock"]
            with self.controller("req",
                                 function="req",
                                 query_vars={"type": "1"},
                                 ) as controller:
                prep = controller.module["req_controller"]().prep
                interactive_r = Storage(table=table,
                                        record=None,
                                        component=None,
                                        interactive=True,
                                        method=None,
                                        http="GET",
                                        resource=Storage(add_filter=lambda query: None),
                                        representation="html",
                                        )
                self.assertTrue(prep(interactive_r))

                plain_r = Storage(table=table,
                                  record=None,
                                  component=None,
                                  interactive=False,
                                  method=None,
                                  http="GET",
                                  resource=Storage(add_filter=lambda query: None),
                                  representation="plain",
                                  )
                self.assertTrue(prep(plain_r))
        finally:
            settings.req.req_crud_strings = saved_req_crud_strings
            settings.req.req_type = saved_req_types

        self.assertEqual(getattr(current.response.s3.crud_strings["req_req"],
                                 "marker",
                                 None,
                                 ),
                         "custom")
        current.response.s3.crud_strings["req_req"].label_create = saved_label

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
    def testReqControllerCommitPrepHandlesDisabledPeopleAndLockedRequests(self):
        """req_controller commit prep disables people commits and completed requests"""

        auth = current.auth
        db = current.db
        s3db = current.s3db
        settings = current.deployment_settings
        ctable = s3db.req_commit
        rtable = s3db.req_req

        site = self.create_office(name="Commit Branch Site")
        people_req_id = self.create_request(site.site_id,
                                            req_type=3,
                                            commit_status=REQ_STATUS_NONE,
                                            )
        item_req_id = self.create_request(site.site_id,
                                          req_type=1,
                                          commit_status=REQ_STATUS_COMPLETE,
                                          )

        people_record = db(rtable.id == people_req_id).select(rtable.ALL,
                                                              limitby=(0, 1),
                                                              ).first()
        item_record = db(rtable.id == item_req_id).select(rtable.ALL,
                                                          limitby=(0, 1),
                                                          ).first()

        saved_allowed = auth.permitted_facilities
        saved_commit_people = settings.req.get("commit_people")
        saved_restrict = settings.req.get("req_restrict_on_complete")
        saved_insertable = s3db.get_config("req_commit", "insertable")

        try:
            auth.permitted_facilities = lambda *args, **kwargs: [site.site_id]
            settings.req.commit_people = True
            settings.req.req_restrict_on_complete = True

            with self.controller("req", function="req") as controller:
                prep = controller.module["req_controller"]().prep

                people_r = Storage(table=rtable,
                                   record=people_record,
                                   component=Storage(name="commit",
                                                     table=ctable,
                                                     ),
                                   component_id=None,
                                   interactive=True,
                                   id=people_req_id,
                                   method="create",
                                   http="GET",
                                   resource=Storage(add_filter=lambda query: None),
                                   representation="html",
                                   )
                self.assertTrue(prep(people_r))
                people_insertable = s3db.get_config("req_commit", "insertable")

                item_r = Storage(table=rtable,
                                 record=item_record,
                                 component=Storage(name="commit",
                                                   table=ctable,
                                                   ),
                                 component_id=None,
                                 interactive=True,
                                 id=item_req_id,
                                 method="create",
                                 http="GET",
                                 resource=Storage(add_filter=lambda query: None),
                                 representation="html",
                                 )
                self.assertTrue(prep(item_r))
                item_insertable = s3db.get_config("req_commit", "insertable")
        finally:
            auth.permitted_facilities = saved_allowed
            settings.req.commit_people = saved_commit_people
            settings.req.req_restrict_on_complete = saved_restrict
            s3db.configure("req_commit", insertable=saved_insertable)

        self.assertFalse(people_insertable)
        self.assertFalse(item_insertable)

    # -------------------------------------------------------------------------
    def testReqControllerCommitPrepHandlesRemainingSiteSelectionBranches(self):
        """req_controller commit prep handles current-site reuse and non-create fallbacks"""

        auth = current.auth
        db = current.db
        s3db = current.s3db
        settings = current.deployment_settings
        ctable = s3db.req_commit
        rtable = s3db.req_req

        requester = self.create_office(name="Commit Target")
        reusable_site = self.create_office(name="Reusable Commit Site")
        other_site = self.create_office(name="Other Commit Site")

        req_id = self.create_request(requester.site_id,
                                     req_type=1,
                                     commit_status=REQ_STATUS_NONE,
                                     )
        record = db(rtable.id == req_id).select(rtable.ALL,
                                                limitby=(0, 1),
                                                ).first()
        commit_id = self.create_commit(req_id, site_id=reusable_site.site_id)

        saved_allowed = auth.permitted_facilities
        saved_commit_people = settings.get_req_commit_people
        saved_restrict = settings.get_req_restrict_on_complete
        saved_requires = ctable.site_id.requires
        saved_insertable = s3db.get_config("req_commit", "insertable")

        try:
            settings.get_req_commit_people = lambda: False
            settings.get_req_restrict_on_complete = lambda: False

            with self.controller("req", function="req") as controller:
                prep = controller.module["req_controller"]().prep

                auth.permitted_facilities = lambda redirect_on_error=False: [reusable_site.site_id,
                                                                             other_site.site_id,
                                                                             ]
                reusable_r = Storage(table=rtable,
                                     record=record,
                                     component=Storage(name="commit",
                                                       table=ctable,
                                                       ),
                                     component_id=commit_id,
                                     interactive=True,
                                     id=req_id,
                                     method="update",
                                     http="GET",
                                     resource=Storage(add_filter=lambda query: None),
                                     representation="html",
                                     )
                self.assertTrue(prep(reusable_r))
                requires = ctable.site_id.requires

                auth.permitted_facilities = lambda redirect_on_error=False: []
                fallback_r = Storage(table=rtable,
                                     record=record,
                                     component=Storage(name="commit",
                                                       table=ctable,
                                                       ),
                                     component_id=None,
                                     interactive=True,
                                     id=req_id,
                                     method="update",
                                     http="GET",
                                     resource=Storage(add_filter=lambda query: None),
                                     representation="html",
                                     )
                self.assertTrue(prep(fallback_r))
                insertable = s3db.get_config("req_commit", "insertable")
        finally:
            auth.permitted_facilities = saved_allowed
            settings.get_req_commit_people = saved_commit_people
            settings.get_req_restrict_on_complete = saved_restrict
            ctable.site_id.requires = saved_requires
            s3db.configure("req_commit", insertable=saved_insertable)

        self.assertIsNotNone(requires)
        self.assertFalse(insertable)

    # -------------------------------------------------------------------------
    def testReqControllerComponentPrepsLockWorkflowManagedItemsAndSkills(self):
        """req_controller locks request components once workflow reaches final states"""

        s3db = current.s3db

        fake_settings = Storage(has_module=current.deployment_settings.has_module,
                                get_req_workflow=lambda: True,
                                get_req_req_crud_strings=lambda req_type: None,
                                get_req_items_ask_purpose=lambda: False,
                                get_req_inline_forms=lambda: False,
                                get_ui_auto_keyvalue=lambda: False,
                                )

        saved_item_config = {k: s3db.get_config("req_req_item", k)
                             for k in ("deletable", "editable", "insertable")}
        saved_skill_config = {k: s3db.get_config("req_req_skill", k)
                              for k in ("deletable", "editable", "insertable")}
        results = Storage()

        try:
            with self.controller("req",
                                 function="req",
                                 overrides={"settings": fake_settings},
                                 ) as controller:
                output = controller.module["req_controller"]()
                prep = output.prep

                item_r = Storage(table=s3db.req_req,
                                 record=Storage(type=1,
                                                workflow_status=3,
                                                ),
                                 component=Storage(name="req_item",
                                                   table=s3db.req_req_item,
                                                   alias="req_item",
                                                   ),
                                 component_name="req_item",
                                 interactive=True,
                                 representation="html",
                                 resource=Storage(add_filter=lambda query: None),
                                 )
                self.assertTrue(prep(item_r))

                skill_r = Storage(table=s3db.req_req,
                                  record=Storage(type=3,
                                                 workflow_status=4,
                                                 ),
                                  component=Storage(name="req_skill",
                                                    table=s3db.req_req_skill,
                                                    alias="req_skill",
                                                    ),
                                  component_name="req_skill",
                                  interactive=True,
                                  representation="html",
                                  resource=Storage(add_filter=lambda query: None),
                                  )
                self.assertTrue(prep(skill_r))
                results.item_deletable = s3db.get_config("req_req_item", "deletable")
                results.item_editable = s3db.get_config("req_req_item", "editable")
                results.item_insertable = s3db.get_config("req_req_item", "insertable")
                results.skill_deletable = s3db.get_config("req_req_skill", "deletable")
                results.skill_editable = s3db.get_config("req_req_skill", "editable")
                results.skill_insertable = s3db.get_config("req_req_skill", "insertable")
        finally:
            s3db.configure("req_req_item", **saved_item_config)
            s3db.configure("req_req_skill", **saved_skill_config)

        self.assertFalse(results.item_deletable)
        self.assertFalse(results.item_editable)
        self.assertFalse(results.item_insertable)
        self.assertFalse(results.skill_deletable)
        self.assertFalse(results.skill_editable)
        self.assertFalse(results.skill_insertable)

    # -------------------------------------------------------------------------
    def testReqControllerJobComponentConfiguresRecurringTaskCrud(self):
        """req_controller configures the scheduler task helper for template jobs"""

        auth = current.auth
        db = current.db

        fake_settings = Storage(has_module=current.deployment_settings.has_module,
                                get_req_workflow=lambda: False,
                                get_req_req_crud_strings=lambda req_type: None,
                                get_req_items_ask_purpose=lambda: False,
                                get_req_inline_forms=lambda: False,
                                get_ui_auto_keyvalue=lambda: False,
                                )

        saved_user = auth.user
        saved_writable = db.scheduler_task.timeout.writable
        captured = {}
        timeout_writable = None

        auth.user = Storage(id=42)

        try:
            with self.controller("req",
                                 function="req",
                                 overrides={"settings": fake_settings},
                                 ) as controller:
                output = controller.module["req_controller"]()
                prep = output.prep
                s3task = prep.__globals__["s3task"]
                saved_configure = s3task.configure_tasktable_crud
                s3task.configure_tasktable_crud = lambda **kwargs: captured.update(kwargs)
                try:
                    r = Storage(table=current.s3db.req_req,
                                record=Storage(type=1,
                                               workflow_status=None,
                                               ),
                                component=Storage(alias="job"),
                                component_name="job",
                                interactive=True,
                                representation="html",
                                id=17,
                                resource=Storage(add_filter=lambda query: None),
                                )
                    self.assertTrue(prep(r))
                    timeout_writable = db.scheduler_task.timeout.writable
                finally:
                    s3task.configure_tasktable_crud = saved_configure
        finally:
            auth.user = saved_user
            db.scheduler_task.timeout.writable = saved_writable

        self.assertEqual(captured["function"], "req_add_from_template")
        self.assertEqual(captured["args"], [17])
        self.assertEqual(captured["vars"], {"user_id": 42})
        self.assertEqual(captured["period"], 86400)
        self.assertFalse(timeout_writable)

    # -------------------------------------------------------------------------
    def testReqControllerAutoKeyvalueAddsDynamicTagFields(self):
        """req_controller adds inline tag fields when auto-keyvalue is enabled"""

        db = current.db
        s3db = current.s3db

        site = self.create_office(name="Tagged Request Site")
        req_id = self.create_request(site.site_id, req_type=1)
        ttable = s3db.req_req_tag
        ttable.insert(req_id=req_id, tag="donor", value="ACME")
        ttable.insert(req_id=req_id, tag="reference", value="R-1")

        fake_settings = Storage(has_module=current.deployment_settings.has_module,
                                get_req_workflow=lambda: False,
                                get_req_req_crud_strings=lambda req_type: None,
                                get_req_items_ask_purpose=lambda: False,
                                get_req_inline_forms=lambda: False,
                                get_ui_auto_keyvalue=lambda: True,
                                )

        saved_form = s3db.get_config("req_req", "crud_form")
        saved_list_fields = list(s3db.get_config("req_req", "list_fields"))
        captured = []

        try:
            with self.controller("req",
                                 function="req",
                                 overrides={"settings": fake_settings},
                                 ) as controller:
                output = controller.module["req_controller"]()
                prep = output.prep
                saved_add_components = s3db.add_components
                s3db.add_components = lambda tablename, **links: captured.append((tablename, links))
                try:
                    r = Storage(table=s3db.req_req,
                                record=None,
                                component=None,
                                interactive=True,
                                id=None,
                                method="create",
                                http="GET",
                                representation="html",
                                resource=Storage(add_filter=lambda query: None),
                                )
                    self.assertTrue(prep(r))
                    crud_form = s3db.get_config("req_req", "crud_form")
                    list_fields = list(s3db.get_config("req_req", "list_fields"))
                finally:
                    s3db.add_components = saved_add_components
        finally:
            s3db.configure("req_req",
                           crud_form=saved_form,
                           list_fields=saved_list_fields,
                           )

        self.assertIsNotNone(crud_form)
        dynamic_fields = [(str(entry[0]), entry[1])
                          for entry in list_fields
                          if isinstance(entry, (tuple, list)) and len(entry) == 2
                          ]
        self.assertIn(("Donor", "donor.value"), dynamic_fields)
        self.assertIn(("Reference", "reference.value"), dynamic_fields)
        self.assertEqual(captured[0][0], "req_req")
        self.assertEqual(captured[0][1]["org_organisation_tag"]["name"], "donor")
        self.assertEqual(captured[1][1]["org_organisation_tag"]["name"], "reference")

    # -------------------------------------------------------------------------
    def testReqControllerUpdatePrepHidesStatusesAndLocksApprovedRequests(self):
        """req_controller update prep hides statuses for submitted requests and locks approved ones"""

        response_s3 = current.response.s3
        s3db = current.s3db
        table = s3db.req_req

        fake_settings = Storage(has_module=current.deployment_settings.has_module,
                                get_req_workflow=lambda: True,
                                get_req_req_crud_strings=lambda req_type: None,
                                get_req_items_ask_purpose=lambda: False,
                                get_req_inline_forms=lambda: True,
                                get_ui_auto_keyvalue=lambda: False,
                                )

        saved_inline = s3db.req_inline_form
        saved_scripts = list(response_s3.scripts)
        saved_status_visibility = {name: (getattr(table, name).readable,
                                          getattr(table, name).writable)
                                   for name in ("commit_status", "transit_status", "fulfil_status")}
        saved_editable = s3db.get_config("req_req", "editable")
        saved_deletable = s3db.get_config("req_req", "deletable")
        inline_calls = []

        s3db.req_inline_form = lambda req_type, method: inline_calls.append((req_type, method))

        try:
            with self.controller("req",
                                 function="req",
                                 overrides={"settings": fake_settings},
                                 ) as controller:
                output = controller.module["req_controller"]()
                prep = output.prep

                submitted = Storage(table=table,
                                    record=Storage(type=1,
                                                   workflow_status=2,
                                                   ),
                                    component=None,
                                    interactive=True,
                                    id=1,
                                    method="update",
                                    http="GET",
                                    representation="html",
                                    resource=Storage(add_filter=lambda query: None),
                                    )
                self.assertTrue(prep(submitted))
                status_visibility = {name: (getattr(table, name).readable,
                                            getattr(table, name).writable)
                                     for name in ("commit_status", "transit_status", "fulfil_status")}

                approved = Storage(table=table,
                                   record=Storage(type=1,
                                                  workflow_status=3,
                                                  ),
                                   component=None,
                                   interactive=True,
                                   id=2,
                                   method="update",
                                   http="GET",
                                   representation="html",
                                   resource=Storage(add_filter=lambda query: None),
                                   )
                self.assertTrue(prep(approved))
                editable = s3db.get_config("req_req", "editable")
                deletable = s3db.get_config("req_req", "deletable")
                scripts = list(response_s3.scripts)
        finally:
            s3db.req_inline_form = saved_inline
            response_s3.scripts = saved_scripts
            for name, (readable, writable) in saved_status_visibility.items():
                getattr(table, name).readable = readable
                getattr(table, name).writable = writable
            s3db.configure("req_req",
                           editable=saved_editable,
                           deletable=saved_deletable,
                           )

        self.assertEqual(inline_calls, [(1, "update"), (1, "update")])
        self.assertEqual(status_visibility["commit_status"], (False, False))
        self.assertEqual(status_visibility["transit_status"], (False, False))
        self.assertEqual(status_visibility["fulfil_status"], (False, False))
        self.assertIn("/eden/static/scripts/S3/s3.req_update.js", scripts)
        self.assertFalse(editable)
        self.assertFalse(deletable)

    # -------------------------------------------------------------------------
    def testReqControllerReqItemComponentDisablesEditingForPartialRequests(self):
        """req_controller blocks req_item changes once the request is already in flight"""

        s3db = current.s3db

        fake_settings = Storage(has_module=current.deployment_settings.has_module,
                                get_req_workflow=lambda: False,
                                get_req_req_crud_strings=lambda req_type: None,
                                get_req_items_ask_purpose=lambda: False,
                                get_req_inline_forms=lambda: False,
                                get_ui_auto_keyvalue=lambda: False,
                                )

        saved_config = {k: s3db.get_config("req_req_item", k)
                        for k in ("deletable", "insertable")}
        results = Storage()

        try:
            with self.controller("req",
                                 function="req",
                                 overrides={"settings": fake_settings},
                                 ) as controller:
                output = controller.module["req_controller"]()
                prep = output.prep
                r = Storage(table=s3db.req_req,
                            record=Storage(fulfil_status=1,
                                           transit_status=0,
                                           req_status=0,
                                           closed=False,
                                           cancel=False,
                                           ),
                            component=Storage(name="req_item"),
                            interactive=False,
                            component_name="req_item",
                            representation="html",
                            resource=Storage(add_filter=lambda query: None),
                            )
                self.assertTrue(prep(r))
                results.deletable = s3db.get_config("req_req_item", "deletable")
                results.insertable = s3db.get_config("req_req_item", "insertable")
        finally:
            s3db.configure("req_req_item", **saved_config)

        self.assertFalse(results.deletable)
        self.assertFalse(results.insertable)

    # -------------------------------------------------------------------------
    def testReqControllerPostpCreateRedirectsToTypeSpecificComponents(self):
        """req_controller create postp redirects new requests to their detail component tabs"""

        response_s3 = current.response.s3

        fake_settings = Storage(has_module=current.deployment_settings.has_module,
                                get_req_use_commit=lambda: True,
                                get_req_copyable=lambda: True,
                                get_req_req_type=lambda: ["Stock", "People"],
                                get_req_commit_people=lambda: True,
                                get_req_inline_forms=lambda: False,
                                )

        saved_actions = response_s3.actions
        saved_ready = response_s3.jquery_ready
        saved_rfooter = response_s3.rfooter

        try:
            with self.controller("req",
                                 function="req",
                                 overrides={"settings": fake_settings},
                                 ) as controller:
                output = controller.module["req_controller"]()
                postp = output.postp

                item_r = Storage(interactive=True,
                                 method=None,
                                 http="POST",
                                 component=None,
                                 table=current.s3db.req_req,
                                 next=None,
                                 )
                postp(item_r, {"form": Storage(vars=Storage(id=11, type="1"))})

                people_r = Storage(interactive=True,
                                   method=None,
                                   http="POST",
                                   component=None,
                                   table=current.s3db.req_req,
                                   next=None,
                                   )
                postp(people_r, {"form": Storage(vars=Storage(id=12, type="3"))})
        finally:
            response_s3.actions = saved_actions
            response_s3.jquery_ready = saved_ready
            response_s3.rfooter = saved_rfooter

        self.assertTrue(item_r.next.endswith("/11/req_item"))
        self.assertTrue(people_r.next.endswith("/12/req_skill"))

    # -------------------------------------------------------------------------
    def testReqControllerPostpHandlesPromptMatchAndCreateMethodRedirects(self):
        """req_controller postp appends prompt-match actions and create-method redirects"""

        response_s3 = current.response.s3
        settings = current.deployment_settings

        saved_actions = response_s3.actions
        saved_ready = response_s3.jquery_ready
        saved_prompt_match = settings.req.get("prompt_match")
        saved_inline_forms = settings.req.get("inline_forms")

        try:
            settings.req.prompt_match = True
            settings.req.inline_forms = False

            with self.controller("req", function="req") as controller:
                output = controller.module["req_controller"]()
                postp = output.postp
                globals_ = postp.__globals__
                saved_buttons = globals_["s3_action_buttons"]
                globals_["s3_action_buttons"] = lambda *args, **kwargs: None

                try:
                    response_s3.actions = []
                    response_s3.jquery_ready = []

                    component_r = Storage(interactive=True,
                                          method=None,
                                          http="GET",
                                          component=Storage(name="req_item",
                                                            tablename="req_req_item",
                                                            alias="req_item",
                                                            ),
                                          record=Storage(id=1),
                                          table=current.s3db.req_req,
                                          )
                    postp(component_r, {})
                    labels = [str(action["label"]) for action in response_s3.actions]

                    item_r = Storage(interactive=True,
                                     method="create",
                                     http="POST",
                                     component=None,
                                     table=current.s3db.req_req,
                                     next=None,
                                     )
                    postp(item_r, {"form": Storage(vars=Storage(id=21, type="1"))})

                    people_r = Storage(interactive=True,
                                       method="create",
                                       http="POST",
                                       component=None,
                                       table=current.s3db.req_req,
                                       next=None,
                                       )
                    postp(people_r, {"form": Storage(vars=Storage(id=22, type="3"))})
                finally:
                    globals_["s3_action_buttons"] = saved_buttons
        finally:
            response_s3.actions = saved_actions
            response_s3.jquery_ready = saved_ready
            settings.req.prompt_match = saved_prompt_match
            settings.req.inline_forms = saved_inline_forms

        self.assertIn("Request from Facility", labels)
        self.assertTrue(item_r.next.endswith("/21/req_item"))
        self.assertTrue(people_r.next.endswith("/22/req_skill"))

    # -------------------------------------------------------------------------
    def testReqControllerPostpAddsRecurringJobActions(self):
        """req_controller postp exposes open/reset/run actions for recurring jobs"""

        response_s3 = current.response.s3

        saved_actions = response_s3.actions

        try:
            with self.controller("req", function="req") as controller:
                output = controller.module["req_controller"]()
                postp = output.postp
                globals_ = postp.__globals__
                saved_buttons = globals_["s3_action_buttons"]
                globals_["s3_action_buttons"] = lambda *args, **kwargs: None

                try:
                    response_s3.actions = []
                    r = Storage(interactive=True,
                                method=None,
                                component=Storage(alias="job",
                                                  tablename="scheduler_task",
                                                  table=current.db.scheduler_task,
                                                  ),
                                id=7,
                                )
                    postp(r, {})
                    labels = [str(action["label"]) for action in response_s3.actions]
                finally:
                    globals_["s3_action_buttons"] = saved_buttons
        finally:
            response_s3.actions = saved_actions

        self.assertEqual(labels, ["Open", "Reset", "Run Now"])

    # -------------------------------------------------------------------------
    def testReqControllerCommitComponentRejectsCreateWithoutAcceptableSites(self):
        """req_controller redirects out of commit creation when no sites remain available"""

        auth = current.auth
        s3db = current.s3db

        requester = self.create_office(name="No Site Requester")
        sender = self.create_office(name="Committed Site")
        item_id = self.create_supply_item(name="Committed Item")
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(requester.site_id, req_type=1)
        self.create_request_item(req_id, item_id, pack_id, quantity=1)
        self.create_commit(req_id, site_id=sender.site_id)

        record = current.db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
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
        saved_error = current.session.error

        auth.permitted_facilities = lambda **kwargs: [sender.site_id]

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
                                              table=s3db.req_commit,
                                              alias="commit",
                                              ),
                            component_name="commit",
                            component_id=None,
                            interactive=True,
                            method="create",
                            id=req_id,
                            representation="html",
                            url=lambda **kwargs: "/eden/req/req/%s" % req_id,
                            )
                with self.assertRaises(ControllerRedirect):
                    prep(r)
        finally:
            auth.permitted_facilities = saved_facilities
            current.session.error = saved_error

        self.assertIn("permission", str(current.session.error).lower())

    # -------------------------------------------------------------------------
    def testReqControllerCommitComponentConfiguresPeopleCommitForms(self):
        """req_controller configures people commitments from the request component view"""

        auth = current.auth
        s3db = current.s3db

        office = self.create_office(name="People Commit Site")
        req_id = self.create_request(office.site_id, req_type=3)
        skill_id = self.create_skill("People Commit Skill")
        self.create_request_skill(req_id,
                                  skill_ids=[skill_id],
                                  quantity=2,
                                  )
        record = current.db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
                                                              limitby=(0, 1),
                                                              ).first()

        fake_settings = Storage(has_module=current.deployment_settings.has_module,
                                get_req_workflow=lambda: False,
                                get_req_req_crud_strings=lambda req_type: None,
                                get_req_items_ask_purpose=lambda: False,
                                get_req_commit_people=lambda: False,
                                get_req_restrict_on_complete=lambda: True,
                                get_ui_auto_keyvalue=lambda: False,
                                )

        saved_facilities = auth.permitted_facilities
        saved_form = s3db.get_config("req_commit", "crud_form")
        saved_insertable = s3db.get_config("req_commit", "insertable")
        captured = Storage(facility_tables=[],
                           skill_filters=[],
                           )

        auth.permitted_facilities = lambda *args, **kwargs: \
            captured.facility_tables.append(kwargs.get("table")) or [office.site_id]

        try:
            with self.controller("req",
                                 function="req",
                                 overrides={"settings": fake_settings},
                                 ) as controller:
                output = controller.module["req_controller"]()
                prep = output.prep
                globals_ = prep.__globals__
                saved_skills_filter = globals_["skills_filter"]
                globals_["skills_filter"] = lambda record_id: captured.skill_filters.append(record_id)
                try:
                    r = Storage(table=s3db.req_req,
                                record=record,
                                resource=Storage(add_filter=lambda query: None),
                                component=Storage(name="commit",
                                                  table=s3db.req_commit,
                                                  alias="commit",
                                                  ),
                                component_name="commit",
                                component_id=None,
                                interactive=True,
                                method="create",
                                id=req_id,
                                representation="html",
                                url=lambda **kwargs: "/eden/req/req/%s" % req_id,
                                )
                    self.assertTrue(prep(r))
                    crud_form = s3db.get_config("req_commit", "crud_form")
                    insertable = s3db.get_config("req_commit", "insertable")
                finally:
                    globals_["skills_filter"] = saved_skills_filter
        finally:
            auth.permitted_facilities = saved_facilities
            s3db.configure("req_commit",
                           crud_form=saved_form,
                           insertable=saved_insertable,
                           )

        self.assertTrue(insertable)
        self.assertIsNotNone(crud_form)
        self.assertTrue(captured.facility_tables)
        self.assertEqual(captured.skill_filters, [req_id])

    # -------------------------------------------------------------------------
    def testReqControllerCommitComponentSupportsAffiliatedOtherRequests(self):
        """req_controller exposes organisation fields for affiliated commitments to other requests"""

        auth = current.auth
        s3db = current.s3db
        table = s3db.req_commit

        office = self.create_office(name="Affiliated Other Request Site")
        req_id = self.create_request(office.site_id, req_type=9)
        record = current.db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
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

        saved_orgs = auth.permitted_organisations
        saved_readable = table.organisation_id.readable
        saved_writable = table.organisation_id.writable
        called = []

        auth.permitted_organisations = lambda *args, **kwargs: called.append(kwargs.get("table"))

        try:
            with self.controller("req",
                                 function="req",
                                 overrides={"settings": fake_settings},
                                 ) as controller:
                output = controller.module["req_controller"]()
                prep = output.prep
                globals_ = prep.__globals__
                saved_is_affiliated = globals_["is_affiliated"]
                globals_["is_affiliated"] = lambda: True
                try:
                    r = Storage(table=s3db.req_req,
                                record=record,
                                resource=Storage(add_filter=lambda query: None),
                                component=Storage(name="commit",
                                                  table=table,
                                                  alias="commit",
                                                  ),
                                component_name="commit",
                                component_id=None,
                                interactive=True,
                                method="create",
                                id=req_id,
                                representation="html",
                                url=lambda **kwargs: "/eden/req/req/%s" % req_id,
                                )
                    self.assertTrue(prep(r))
                    readable = table.organisation_id.readable
                    writable = table.organisation_id.writable
                finally:
                    globals_["is_affiliated"] = saved_is_affiliated
        finally:
            auth.permitted_organisations = saved_orgs
            table.organisation_id.readable = saved_readable
            table.organisation_id.writable = saved_writable

        self.assertTrue(readable)
        self.assertTrue(writable)
        self.assertEqual(called, [s3db.req_req])

    # -------------------------------------------------------------------------
    def testReqControllerCommitComponentRestrictsUnaffiliatedOtherRequests(self):
        """req_controller hides sender fields for unaffiliated commitments to other requests"""

        s3db = current.s3db
        table = s3db.req_commit

        office = self.create_office(name="Other Request Site")
        req_id = self.create_request(office.site_id, req_type=9)
        record = current.db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
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

        saved_committer_writable = table.committer_id.writable
        saved_committer_comment = table.committer_id.comment
        saved_site_readable = table.site_id.readable
        saved_site_writable = table.site_id.writable

        try:
            with self.controller("req",
                                 function="req",
                                 overrides={"settings": fake_settings},
                                 ) as controller:
                output = controller.module["req_controller"]()
                prep = output.prep
                globals_ = prep.__globals__
                saved_is_affiliated = globals_["is_affiliated"]
                globals_["is_affiliated"] = lambda: False
                try:
                    r = Storage(table=s3db.req_req,
                                record=record,
                                resource=Storage(add_filter=lambda query: None),
                                component=Storage(name="commit",
                                                  table=table,
                                                  alias="commit",
                                                  ),
                                component_name="commit",
                                component_id=None,
                                interactive=True,
                                method="create",
                                id=req_id,
                                representation="html",
                                url=lambda **kwargs: "/eden/req/req/%s" % req_id,
                                )
                    self.assertTrue(prep(r))
                    committer_writable = table.committer_id.writable
                    committer_comment = table.committer_id.comment
                    site_readable = table.site_id.readable
                    site_writable = table.site_id.writable
                finally:
                    globals_["is_affiliated"] = saved_is_affiliated
        finally:
            table.committer_id.writable = saved_committer_writable
            table.committer_id.comment = saved_committer_comment
            table.site_id.readable = saved_site_readable
            table.site_id.writable = saved_site_writable

        self.assertFalse(committer_writable)
        self.assertIsNone(committer_comment)
        self.assertFalse(site_readable)
        self.assertFalse(site_writable)

    # -------------------------------------------------------------------------
    def testReqControllerPrepDisablesDeletingClosedOrInFlightRequests(self):
        """req_controller marks partial or closed requests as non-deletable"""

        s3db = current.s3db
        saved_deletable = s3db.get_config("req_req", "deletable")

        try:
            with self.controller("req", function="req") as controller:
                output = controller.module["req_controller"]()
                prep = output.prep
                r = Storage(table=s3db.req_req,
                            id=1,
                            record=Storage(fulfil_status=REQ_STATUS_PARTIAL,
                                           transit_status=REQ_STATUS_NONE,
                                           req_status=REQ_STATUS_NONE,
                                           closed=False,
                                           ),
                            component=None,
                            interactive=True,
                            representation="html",
                            resource=Storage(add_filter=lambda query: None),
                            )
                self.assertTrue(prep(r))
                deletable = s3db.get_config("req_req", "deletable")
        finally:
            s3db.configure("req_req", deletable=saved_deletable)

        self.assertFalse(deletable)

    # -------------------------------------------------------------------------
    def testReqControllerCommitComponentKeepsExistingUnpermittedSiteReadOnly(self):
        """req_controller keeps an existing committing site read-only when the user cannot choose it"""

        auth = current.auth
        s3db = current.s3db
        table = s3db.req_commit

        requester = self.create_office(name="Existing Commit Requester")
        sender = self.create_office(name="Existing Commit Sender")
        other = self.create_office(name="Existing Commit Other")
        item_id = self.create_supply_item(name="Existing Commit Item")
        pack_id = self.create_item_pack(item_id, quantity=1)
        req_id = self.create_request(requester.site_id, req_type=1)
        self.create_request_item(req_id, item_id, pack_id, quantity=1)
        commit_id = self.create_commit(req_id, site_id=sender.site_id)
        record = current.db(s3db.req_req.id == req_id).select(s3db.req_req.ALL,
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
        saved_site_writable = table.site_id.writable

        auth.permitted_facilities = lambda **kwargs: [other.site_id]

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
                                              table=table,
                                              alias="commit",
                                              ),
                            component_name="commit",
                            component_id=commit_id,
                            interactive=True,
                            method="update",
                            id=req_id,
                            representation="html",
                            url=lambda **kwargs: "/eden/req/req/%s" % req_id,
                            )
                self.assertTrue(prep(r))
                site_writable = table.site_id.writable
        finally:
            auth.permitted_facilities = saved_facilities
            table.site_id.writable = saved_site_writable

        self.assertFalse(site_writable)

    # -------------------------------------------------------------------------
    def testReqControllerPostpUsesCheckActionsWithoutCommitWorkflow(self):
        """req_controller postp falls back to check actions when direct commits are disabled"""

        auth = current.auth
        response_s3 = current.response.s3
        s3db = current.s3db

        office = self.create_office(name="Check Action Site")
        self.create_request(office.site_id, req_type=1)
        self.create_request(office.site_id, req_type=3)

        fake_settings = Storage(has_module=current.deployment_settings.has_module,
                                get_req_use_commit=lambda: False,
                                get_req_copyable=lambda: False,
                                get_req_req_type=lambda: ["Stock", "People"],
                                get_req_commit_people=lambda: True,
                                )

        saved_actions = response_s3.actions
        saved_ready = response_s3.jquery_ready
        saved_user = auth.user
        results = Storage()

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
                auth.user = Storage(site_id=office.site_id,
                                    organisation_id=office.organisation_id,
                                    )

                try:
                    r = Storage(interactive=True,
                                method=None,
                                component=None,
                                http="GET",
                                table=s3db.req_req,
                                )
                    postp(r, {})
                    results.labels = [str(action["label"]) for action in response_s3.actions]
                    results.restricts = [action.get("restrict") for action in response_s3.actions
                                         if str(action["label"]) == "Check"]
                finally:
                    globals_["s3_action_buttons"] = saved_buttons
        finally:
            auth.user = saved_user
            response_s3.actions = saved_actions
            response_s3.jquery_ready = saved_ready

        self.assertEqual(results.labels.count("Check"), 2)
        self.assertTrue(all(restrict is not None for restrict in results.restricts))

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
    def testReqControllerPostpBuildsSingleTypeActionsWithoutRestrictions(self):
        """req_controller postp omits restrict lists when only one request type is deployed"""

        auth = current.auth
        response_s3 = current.response.s3

        saved_actions = response_s3.actions
        saved_ready = response_s3.jquery_ready
        saved_user = auth.user
        settings = current.deployment_settings
        saved_use_commit = settings.req.get("use_commit")
        saved_copyable = settings.req.get("copyable")
        saved_req_types = settings.req.get("req_type")
        saved_commit_people = settings.req.get("commit_people")

        try:
            settings.req.use_commit = True
            settings.req.copyable = False
            settings.req.req_type = ["Stock"]
            settings.req.commit_people = False

            with self.controller("req", function="req", query_vars={"type": "1"}) as controller:
                output = controller.module["req_controller"]()
                postp = output.postp
                globals_ = postp.__globals__
                saved_buttons = globals_["s3_action_buttons"]
                globals_["s3_action_buttons"] = lambda *args, **kwargs: None

                try:
                    auth.user = Storage(site_id=1, organisation_id=None)
                    response_s3.actions = []
                    response_s3.jquery_ready = []
                    stock_r = Storage(interactive=True,
                                      method=None,
                                      http="GET",
                                      component=None,
                                      table=current.s3db.req_req,
                                      record=None,
                                      )
                    postp(stock_r, {})
                    stock_actions = list(response_s3.actions)
                finally:
                    globals_["s3_action_buttons"] = saved_buttons

            settings.req.use_commit = False
            settings.req.copyable = False
            settings.req.req_type = ["People"]
            settings.req.commit_people = True

            with self.controller("req", function="req", query_vars={"type": "3"}) as controller:
                output = controller.module["req_controller"]()
                postp = output.postp
                globals_ = postp.__globals__
                saved_buttons = globals_["s3_action_buttons"]
                globals_["s3_action_buttons"] = lambda *args, **kwargs: None

                try:
                    auth.user = Storage(site_id=None, organisation_id=1)
                    response_s3.actions = []
                    response_s3.jquery_ready = []
                    people_r = Storage(interactive=True,
                                       method=None,
                                       http="GET",
                                       component=None,
                                       table=current.s3db.req_req,
                                       record=None,
                                       )
                    postp(people_r, {})
                    people_actions = list(response_s3.actions)
                finally:
                    globals_["s3_action_buttons"] = saved_buttons
        finally:
            settings.req.use_commit = saved_use_commit
            settings.req.copyable = saved_copyable
            settings.req.req_type = saved_req_types
            settings.req.commit_people = saved_commit_people
            response_s3.actions = saved_actions
            response_s3.jquery_ready = saved_ready
            auth.user = saved_user

        stock_check = [action for action in stock_actions
                       if str(action["label"]) in ("Check", "Send")]
        people_check = [action for action in people_actions
                        if str(action["label"]) == "Check"]
        self.assertTrue(stock_check)
        self.assertTrue(people_check)
        self.assertTrue(all("restrict" not in action for action in stock_check))
        self.assertTrue(all("restrict" not in action for action in people_check))

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
    def testReqItemControllerAppendsPromptMatchActionToExistingActions(self):
        """req_item appends the prompt-match action when actions already exist"""

        response_s3 = current.response.s3

        fake_settings = Storage(has_module=current.deployment_settings.has_module,
                                get_req_prompt_match=lambda: True,
                                )

        saved_actions = response_s3.actions

        try:
            with self.controller("req",
                                 function="req_item",
                                 overrides={"settings": fake_settings},
                                 ) as controller:
                response_s3.actions = [{"label": "Existing"}]
                controller.module["req_item"]()
                labels = [str(action["label"]) for action in response_s3.actions]
        finally:
            response_s3.actions = saved_actions

        self.assertEqual(labels, ["Existing", "Request from Facility"])

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
    def testReqItemInvItemOmitsAlternativesAndOrderActionWhenDisabled(self):
        """req_item_inv_item suppresses optional alternative stock and ordering branches when disabled"""

        requester = self.create_office(name="Requester Without Options")
        warehouse = self.create_office(name="Primary Warehouse")
        requester_person = self.create_person(last_name="Requester Without Options")

        item_id = self.create_supply_item(name="Only Item")
        pack_id = self.create_item_pack(item_id, quantity=1)
        self.create_inventory_item(warehouse.site_id, item_id, pack_id, quantity=2)

        req_id = self.create_request(requester.site_id,
                                     requester_id=requester_person,
                                     req_type=1,
                                     )
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=1,
                                               )

        fake_settings = Storage(has_module=current.deployment_settings.has_module,
                                get_supply_use_alt_name=lambda: False,
                                get_req_order_item=lambda: False,
                                )
        calls = []

        def fake_crud_controller(*args, **kwargs):
            """Return a deterministic stock list for the main inventory only"""

            calls.append((args, kwargs))
            return {"items": "PRIMARY"}

        saved_actions = current.response.s3.actions
        saved_filter = current.response.s3.filter
        saved_view = current.response.view

        try:
            with self.controller("req",
                                 function="req_item_inv_item",
                                 args=[str(req_item_id)],
                                 overrides={"crud_controller": fake_crud_controller,
                                            "settings": fake_settings,
                                            },
                                 ) as controller:
                current.response.s3.actions = []
                output = controller.module["req_item_inv_item"]()
        finally:
            current.response.s3.actions = saved_actions
            current.response.s3.filter = saved_filter
            current.response.view = saved_view

        self.assertEqual(output["items"], "PRIMARY")
        self.assertIsNone(output["items_alt"])
        self.assertIsNone(output["order_btn"])
        self.assertEqual(len(calls), 1)

    # -------------------------------------------------------------------------
    def testReqItemInvItemReportsMissingAlternativeItems(self):
        """req_item_inv_item shows the fallback message when no alternative items are configured"""

        requester = self.create_office(name="Requester With Empty Alternatives")
        warehouse = self.create_office(name="Primary Warehouse Only")
        requester_person = self.create_person(last_name="Requester With Alternatives")

        item_id = self.create_supply_item(name="Primary Only Item")
        pack_id = self.create_item_pack(item_id, quantity=1)
        self.create_inventory_item(warehouse.site_id, item_id, pack_id, quantity=3)

        req_id = self.create_request(requester.site_id,
                                     requester_id=requester_person,
                                     req_type=1,
                                     )
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=1,
                                               )

        fake_settings = Storage(has_module=current.deployment_settings.has_module,
                                get_supply_use_alt_name=lambda: True,
                                get_req_order_item=lambda: False,
                                )

        def fake_crud_controller(*args, **kwargs):
            """Return only the primary inventory listing"""

            return {"items": "PRIMARY"}

        saved_actions = current.response.s3.actions
        saved_filter = current.response.s3.filter
        saved_view = current.response.view

        try:
            with self.controller("req",
                                 function="req_item_inv_item",
                                 args=[str(req_item_id)],
                                 overrides={"crud_controller": fake_crud_controller,
                                            "settings": fake_settings,
                                            },
                                 ) as controller:
                current.response.s3.actions = []
                output = controller.module["req_item_inv_item"]()
        finally:
            current.response.s3.actions = saved_actions
            current.response.s3.filter = saved_filter
            current.response.view = saved_view

        self.assertEqual(output["items"], "PRIMARY")
        self.assertEqual(str(output["items_alt"]),
                         "No Inventories currently have suitable alternative items in stock")
        self.assertIsNone(output["order_btn"])

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
    def testReqSkillControllerSkipsCreateOnlyHidingForUpdateAndRead(self):
        """req_skill leaves quantity fields alone for update/read requests and non-interactive postp"""

        response_s3 = current.response.s3
        s3db = current.s3db

        saved_actions = response_s3.actions
        saved_filter = response_s3.filter
        saved_list_fields = s3db.get_config("req_req_skill", "list_fields")
        saved_insertable = s3db.get_config("req_req_skill", "insertable")
        saved_hide = s3db.req_hide_quantities
        hide_calls = []

        s3db.req_hide_quantities = lambda table: hide_calls.append(table._tablename)

        try:
            with self.controller("req", function="req_skill") as controller:
                response_s3.actions = []
                output = controller.module["req_skill"]()
                prep = output.prep
                postp = output.postp

                self.assertTrue(prep(Storage(interactive=True,
                                             representation="html",
                                             method="update",
                                             table=s3db.req_req_skill,
                                             )))
                self.assertTrue(prep(Storage(interactive=False,
                                             representation="aadata",
                                             method="read",
                                             table=s3db.req_req_skill,
                                             )))
                result = postp(Storage(interactive=False), {"ok": True})
        finally:
            response_s3.actions = saved_actions
            response_s3.filter = saved_filter
            s3db.configure("req_req_skill",
                           list_fields=saved_list_fields,
                           insertable=saved_insertable,
                           )
            s3db.req_hide_quantities = saved_hide

        self.assertEqual(hide_calls, [])
        self.assertEqual(result, {"ok": True})

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
    def testCommitReqCreatesPartialCommitWhenStockIsScarce(self):
        """commit_req commits only the stock currently available in the sender warehouse"""

        auth = current.auth
        db = current.db
        s3db = current.s3db

        requester = self.create_office(name="Partial Commit Requester")
        sender = self.create_office(name="Partial Commit Sender")
        item_id = self.create_supply_item(name="Scarce Item")
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
                                   quantity=2,
                                   )

        saved_permission = auth.s3_has_permission
        auth.s3_has_permission = lambda *args, **kwargs: True

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

        ctable = s3db.req_commit
        itable = s3db.req_commit_item
        commit = db((ctable.req_id == req_id) &
                    (ctable.site_id == sender.site_id)).select(ctable.id,
                                                               limitby=(0, 1),
                                                               orderby=~ctable.id,
                                                               ).first()
        commit_item = db(itable.commit_id == commit.id).select(itable.req_item_id,
                                                               itable.quantity,
                                                               limitby=(0, 1),
                                                               ).first()

        self.assertEqual(commit_item.req_item_id, req_item_id)
        self.assertEqual(commit_item.quantity, 2)
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
    def testSendReqAddsPlaceholderRowsForAmbiguousInventory(self):
        """send_req leaves zero-quantity placeholders for ambiguous warehouse matches"""

        auth = current.auth
        db = current.db
        s3db = current.s3db

        requester = self.create_office(name="Ambiguous Requester")
        sender = self.create_office(name="Ambiguous Sender")
        person_id = self.create_person(last_name="Shipment Sender")

        item_id = self.create_supply_item(name="Ambiguous Item")
        pack_id = self.create_item_pack(item_id, quantity=1)
        unmatched_item_id = self.create_supply_item(name="Unmatched Item")
        unmatched_pack_id = self.create_item_pack(unmatched_item_id, quantity=1)

        req_id = self.create_request(requester.site_id,
                                     req_ref="REQ-SEND-AMB",
                                     requester_id=person_id,
                                     )
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=10,
                                               )
        self.create_request_item(req_id,
                                 unmatched_item_id,
                                 unmatched_pack_id,
                                 quantity=1,
                                 )

        expiring = self.create_inventory_item(sender.site_id,
                                              item_id,
                                              pack_id,
                                              quantity=2,
                                              status=0,
                                              expiry_date=current.request.now + datetime.timedelta(days=30),
                                              )
        second = self.create_inventory_item(sender.site_id,
                                            item_id,
                                            pack_id,
                                            quantity=3,
                                            status=0,
                                            )
        third = self.create_inventory_item(sender.site_id,
                                           item_id,
                                           pack_id,
                                           quantity=6,
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

        send = db((s3db.inv_send.req_ref == "REQ-SEND-AMB") &
                  (s3db.inv_send.site_id == sender.site_id)).select(s3db.inv_send.id,
                                                                    limitby=(0, 1),
                                                                    orderby=~s3db.inv_send.id,
                                                                    ).first()
        tracks = db(s3db.inv_track_item.send_id == send.id).select(s3db.inv_track_item.req_item_id,
                                                                   s3db.inv_track_item.send_inv_item_id,
                                                                   s3db.inv_track_item.quantity,
                                                                   orderby=s3db.inv_track_item.id,
                                                                   )

        quantities = [row.quantity for row in tracks if row.req_item_id == req_item_id]
        send_inv_item_ids = {row.send_inv_item_id for row in tracks if row.req_item_id == req_item_id}
        self.assertIn("/inv/send/%s/track_item" % send.id, url)
        self.assertEqual(sorted(quantities), [0, 0, 2])
        self.assertEqual(send_inv_item_ids, {expiring, second, third})

    # -------------------------------------------------------------------------
    def testSendReqUsesPurchaseDateBeforeUndatedStock(self):
        """send_req prefers purchase-dated stock before falling back to undated stock"""

        auth = current.auth
        db = current.db
        s3db = current.s3db

        requester = self.create_office(name="Purchase Requester")
        sender = self.create_office(name="Purchase Sender")
        person_id = self.create_person(last_name="Purchase Sender")

        item_id = self.create_supply_item(name="Purchase-Date Item")
        pack_id = self.create_item_pack(item_id, quantity=1)

        req_id = self.create_request(requester.site_id,
                                     req_ref="REQ-SEND-PURCHASE",
                                     requester_id=person_id,
                                     )
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=5,
                                               )

        expiring_row = self.create_inventory_item(sender.site_id,
                                                  item_id,
                                                  pack_id,
                                                  quantity=2,
                                                  status=0,
                                                  expiry_date=current.request.now + datetime.timedelta(days=5),
                                                  )
        purchase_row = self.create_inventory_item(sender.site_id,
                                                  item_id,
                                                  pack_id,
                                                  quantity=3,
                                                  status=0,
                                                  purchase_date=current.request.now.date() - datetime.timedelta(days=10),
                                                  )
        spare_row = self.create_inventory_item(sender.site_id,
                                               item_id,
                                               pack_id,
                                               quantity=1,
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

        send = db((s3db.inv_send.req_ref == "REQ-SEND-PURCHASE") &
                  (s3db.inv_send.site_id == sender.site_id)).select(s3db.inv_send.id,
                                                                    limitby=(0, 1),
                                                                    orderby=~s3db.inv_send.id,
                                                                    ).first()
        tracks = db((s3db.inv_track_item.send_id == send.id) &
                    (s3db.inv_track_item.req_item_id == req_item_id)).select(s3db.inv_track_item.send_inv_item_id,
                                                                             s3db.inv_track_item.quantity,
                                                                             orderby=s3db.inv_track_item.id,
                                                                             )

        self.assertIn("/inv/send/%s/track_item" % send.id, url)
        used = [(row.send_inv_item_id, row.quantity) for row in tracks]
        self.assertEqual(used,
                         [(purchase_row, 3),
                          (expiring_row, 2),
                          ])
        self.assertEqual(db(s3db.inv_inv_item.id == spare_row).select(s3db.inv_inv_item.quantity,
                                                                      limitby=(0, 1),
                                                                      ).first().quantity,
                         1)

    # -------------------------------------------------------------------------
    def testSendReqAssignsWholeBatchWhenUndatedStockFitsExactly(self):
        """send_req assigns a whole undated batch when it exactly matches the outstanding quantity"""

        auth = current.auth
        db = current.db
        s3db = current.s3db

        requester = self.create_office(name="Batch Requester")
        sender = self.create_office(name="Batch Sender")
        person_id = self.create_person(last_name="Batch Sender")

        item_id = self.create_supply_item(name="Whole Batch Item")
        pack_id = self.create_item_pack(item_id, quantity=1)

        req_id = self.create_request(requester.site_id,
                                     req_ref="REQ-SEND-BATCH",
                                     requester_id=person_id,
                                     )
        req_item_id = self.create_request_item(req_id,
                                               item_id,
                                               pack_id,
                                               quantity=3,
                                               )

        batch_row = self.create_inventory_item(sender.site_id,
                                               item_id,
                                               pack_id,
                                               quantity=3,
                                               status=0,
                                               )
        spare_row = self.create_inventory_item(sender.site_id,
                                               item_id,
                                               pack_id,
                                               quantity=5,
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
                with self.assertRaises(ControllerRedirect):
                    controller.module["send_req"]()
        finally:
            auth.s3_has_permission = saved_permission
            auth.s3_logged_in_person = saved_logged_in_person

        send = db((s3db.inv_send.req_ref == "REQ-SEND-BATCH") &
                  (s3db.inv_send.site_id == sender.site_id)).select(s3db.inv_send.id,
                                                                    limitby=(0, 1),
                                                                    orderby=~s3db.inv_send.id,
                                                                    ).first()
        tracks = db((s3db.inv_track_item.send_id == send.id) &
                    (s3db.inv_track_item.req_item_id == req_item_id)).select(s3db.inv_track_item.send_inv_item_id,
                                                                             s3db.inv_track_item.quantity,
                                                                             orderby=s3db.inv_track_item.id,
                                                                             )

        self.assertEqual([(row.send_inv_item_id, row.quantity) for row in tracks],
                         [(batch_row, 3)])
        self.assertEqual(db(s3db.inv_inv_item.id == spare_row).select(s3db.inv_inv_item.quantity,
                                                                      limitby=(0, 1),
                                                                      ).first().quantity,
                         5)

    # -------------------------------------------------------------------------
    def testSendReqWarnsWhenNoExactStockMatchesExist(self):
        """send_req warns when the sender has stock but nothing exactly matching the request item"""

        auth = current.auth
        session = current.session
        db = current.db
        s3db = current.s3db

        requester = self.create_office(name="No Match Requester")
        sender = self.create_office(name="No Match Sender")
        person_id = self.create_person(last_name="No Match Sender")

        req_item_id = self.create_supply_item(name="Requested Match Item")
        req_pack_id = self.create_item_pack(req_item_id, quantity=1)
        other_item_id = self.create_supply_item(name="Different Stock Item")
        other_pack_id = self.create_item_pack(other_item_id, quantity=1)

        req_id = self.create_request(requester.site_id,
                                     req_ref="REQ-SEND-NOMATCH",
                                     requester_id=person_id,
                                     )
        self.create_request_item(req_id,
                                 req_item_id,
                                 req_pack_id,
                                 quantity=3,
                                 )
        self.create_inventory_item(sender.site_id,
                                   other_item_id,
                                   other_pack_id,
                                   quantity=10,
                                   status=0,
                                   )

        saved_permission = auth.s3_has_permission
        saved_logged_in_person = auth.s3_logged_in_person
        saved_warning = session.warning
        auth.s3_has_permission = lambda *args, **kwargs: True
        auth.s3_logged_in_person = lambda: person_id

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
            auth.s3_logged_in_person = saved_logged_in_person
            session.warning = saved_warning

        send = db((s3db.inv_send.req_ref == "REQ-SEND-NOMATCH") &
                  (s3db.inv_send.site_id == sender.site_id)).select(s3db.inv_send.id,
                                                                    limitby=(0, 1),
                                                                    orderby=~s3db.inv_send.id,
                                                                    ).first()

        self.assertIn("/inv/send/%s/track_item" % send.id, url)
        self.assertIn("no items exactly matching", str(warning).lower())
        self.assertEqual(db(s3db.inv_track_item.send_id == send.id).count(), 0)

    # -------------------------------------------------------------------------
    def testShipmentProxyControllersDelegateToUnderlyingMethods(self):
        """Shipment proxy controllers delegate to the inventory and request helpers"""

        s3db = current.s3db

        saved_send = s3db.inv_send_controller
        saved_send_commit = s3db.req_send_commit
        saved_send_process = s3db.inv_send_process

        s3db.inv_send_controller = lambda: "SEND"
        s3db.req_send_commit = lambda: "SEND-COMMIT"
        s3db.inv_send_process = lambda: "SEND-PROCESS"

        try:
            with self.controller("req", function="send") as controller:
                send_output = controller.module["send"]()
                listadd = s3db.get_config("inv_send", "listadd")

            with self.controller("req", function="send_commit") as controller:
                send_commit_output = controller.module["send_commit"]()

            with self.controller("req", function="send_process") as controller:
                send_process_output = controller.module["send_process"]()
        finally:
            s3db.inv_send_controller = saved_send
            s3db.req_send_commit = saved_send_commit
            s3db.inv_send_process = saved_send_process

        self.assertFalse(listadd)
        self.assertEqual(send_output, "SEND")
        self.assertEqual(send_commit_output, "SEND-COMMIT")
        self.assertEqual(send_process_output, "SEND-PROCESS")

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
    def testCommitControllerDisablesCommitPeopleForUnaffiliatedUsers(self):
        """commit disables person-assignment records for unaffiliated users outside assign mode"""

        s3db = current.s3db
        field = s3db.req_commit_person.human_resource_id

        saved_insertable = s3db.get_config("req_commit_person", "insertable")
        saved_writable = field.writable

        try:
            with self.controller("req", function="commit") as controller:
                controller.module["commit"].__globals__["is_affiliated"] = lambda: False
                output = controller.module["commit"]()
                insertable = s3db.get_config("req_commit_person", "insertable")
                writable = field.writable
        finally:
            s3db.configure("req_commit_person", insertable=saved_insertable)
            field.writable = saved_writable

        self.assertEqual(output.kwargs["rheader"], controller.module["commit_rheader"])
        self.assertFalse(insertable)
        self.assertFalse(writable)

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
    def testCommitControllerPostpLeavesPrepareShipmentUnrestrictedForStockOnly(self):
        """commit postp omits action restrictions when all commitments are stock commitments"""

        response_s3 = current.response.s3
        s3db = current.s3db

        office = self.create_office(name="Stock Only Commit Site")
        item_req_id = self.create_request(office.site_id, req_type=1)
        item_commit_id = self.create_commit(item_req_id, site_id=office.site_id)
        current.db(s3db.req_commit.id == item_commit_id).update(type=1)

        saved_actions = response_s3.actions
        saved_ready = response_s3.jquery_ready

        try:
            with self.controller("req",
                                 function="commit",
                                 overrides={"settings": Storage(has_module=current.deployment_settings.has_module,
                                                                get_req_req_type=lambda: ["Stock"])},
                                 ) as controller:
                output = controller.module["commit"]()
                postp = output.postp
                globals_ = postp.__globals__
                saved_buttons = globals_["s3_action_buttons"]
                globals_["s3_action_buttons"] = lambda *args, **kwargs: None

                try:
                    response_s3.actions = []
                    response_s3.jquery_ready = []
                    postp(Storage(interactive=True,
                                  method=None,
                                  component=None,
                                  table=s3db.req_commit,
                                  function="commit",
                                  get_vars=Storage(),
                                  ),
                          {})
                    action = [a for a in response_s3.actions if str(a["label"]) == "Prepare Shipment"][0]
                finally:
                    globals_["s3_action_buttons"] = saved_buttons
        finally:
            response_s3.actions = saved_actions
            response_s3.jquery_ready = saved_ready

        self.assertNotIn("restrict", action)

    # -------------------------------------------------------------------------
    def testCommitControllerComponentPrepFiltersItemsAndSkills(self):
        """commit prep filters commit_item and commit_skill components to the linked request"""

        s3db = current.s3db

        office = self.create_office(name="Commit Component Site")
        item_id = self.create_supply_item(name="Commit Component Item")
        pack_id = self.create_item_pack(item_id, quantity=1)

        item_req_id = self.create_request(office.site_id, req_type=1)
        self.create_request_item(item_req_id, item_id, pack_id, quantity=2)
        item_commit_id = self.create_commit(item_req_id, site_id=office.site_id)
        current.db(s3db.req_commit.id == item_commit_id).update(type=1)

        skill_req_id = self.create_request(office.site_id, req_type=3)
        skill_id = self.create_skill("Component Skill")
        self.create_request_skill(skill_req_id,
                                  skill_ids=[skill_id],
                                  quantity=1,
                                  )
        skill_commit_id = self.create_commit(skill_req_id, site_id=office.site_id)
        current.db(s3db.req_commit.id == skill_commit_id).update(type=3)

        saved_widget = s3db.req_commit_item.req_item_id.widget
        saved_requires = s3db.req_commit_item.req_item_id.requires
        captured = []

        try:
            with self.controller("req", function="commit") as controller:
                output = controller.module["commit"]()
                prep = output.prep
                globals_ = prep.__globals__
                saved_skills_filter = globals_["skills_filter"]
                globals_["skills_filter"] = lambda req_id: captured.append(req_id)

                try:
                    item_record = current.db(s3db.req_commit.id == item_commit_id).select(s3db.req_commit.ALL,
                                                                                          limitby=(0, 1),
                                                                                          ).first()
                    item_r = Storage(interactive=True,
                                     record=item_record,
                                     component=Storage(name="commit_item"),
                                     component_name="commit_item",
                                     )
                    self.assertTrue(prep(item_r))
                    widget = s3db.req_commit_item.req_item_id.widget
                    requires = s3db.req_commit_item.req_item_id.requires

                    skill_record = current.db(s3db.req_commit.id == skill_commit_id).select(s3db.req_commit.ALL,
                                                                                            limitby=(0, 1),
                                                                                            ).first()
                    skill_r = Storage(interactive=True,
                                      record=skill_record,
                                      component=Storage(name="commit_skill"),
                                      component_name="commit_skill",
                                      )
                    self.assertTrue(prep(skill_r))
                finally:
                    globals_["skills_filter"] = saved_skills_filter
        finally:
            s3db.req_commit_item.req_item_id.widget = saved_widget
            s3db.req_commit_item.req_item_id.requires = saved_requires

        self.assertIsNone(widget)
        self.assertIsNotNone(requires)
        self.assertEqual(captured, [skill_req_id])

    # -------------------------------------------------------------------------
    def testCommitRheaderShowsSkillsTabWhenCommitPeopleIsDisabled(self):
        """commit_rheader uses the skills tab for people commitments when person assignments are disabled"""
        s3db = current.s3db

        office = self.create_office(name="Skills RHeader Site")
        req_id = self.create_request(office.site_id, req_type=3)
        commit_id = self.create_commit(req_id,
                                       organisation_id=office.organisation_id,
                                       )
        current.db(s3db.req_commit.id == commit_id).update(type=3)
        record = current.db(s3db.req_commit.id == commit_id).select(s3db.req_commit.ALL,
                                                                    limitby=(0, 1),
                                                                    ).first()

        try:
            with self.controller("req", function="commit") as controller:
                globals_ = controller.module["commit_rheader"].__globals__
                saved_tabs = globals_["s3_rheader_tabs"]
                saved_settings = globals_["settings"]
                globals_["s3_rheader_tabs"] = lambda r, tabs: "TABS:%s" % ",".join(str(t[0]) for t in tabs)
                globals_["settings"] = Storage(get_req_commit_people=lambda: False)
                try:
                    header = controller.module["commit_rheader"](Storage(representation="html",
                                                                         name="commit",
                                                                         record=record,
                                                                         table=s3db.req_commit,
                                                                         id=commit_id,
                                                                         resource=Storage(get_config=lambda key: False),
                                                                         get_vars=Storage(),
                                                                         ))
                finally:
                    globals_["s3_rheader_tabs"] = saved_tabs
                    globals_["settings"] = saved_settings
        finally:
            pass

        self.assertIn("Skills", str(header))

    # -------------------------------------------------------------------------
    def testCommitControllerPostpRestrictsPrepareShipmentToItemCommitments(self):
        """commit postp restricts prepare-shipment to item commitments when multiple types exist"""

        response_s3 = current.response.s3
        s3db = current.s3db

        office = self.create_office(name="Commit Action Site")
        item_req_id = self.create_request(office.site_id, req_type=1)
        item_commit_id = self.create_commit(item_req_id, site_id=office.site_id)
        current.db(s3db.req_commit.id == item_commit_id).update(type=1)

        people_req_id = self.create_request(office.site_id, req_type=3)
        people_commit_id = self.create_commit(people_req_id,
                                              organisation_id=office.organisation_id,
                                              )
        current.db(s3db.req_commit.id == people_commit_id).update(type=3)

        saved_types = current.deployment_settings.get_req_req_type
        saved_actions = response_s3.actions
        saved_ready = response_s3.jquery_ready

        current.deployment_settings.get_req_req_type = lambda: ["Stock", "People"]

        try:
            with self.controller("req", function="commit") as controller:
                output = controller.module["commit"]()
                postp = output.postp
                globals_ = postp.__globals__
                saved_buttons = globals_["s3_action_buttons"]
                globals_["s3_action_buttons"] = lambda *args, **kwargs: None

                try:
                    response_s3.actions = []
                    response_s3.jquery_ready = []
                    postp(Storage(interactive=True,
                                  method=None,
                                  component=None,
                                  table=s3db.req_commit,
                                  function="commit",
                                  get_vars=Storage(),
                                  ),
                          {})
                    action = [a for a in response_s3.actions if str(a["label"]) == "Prepare Shipment"][0]
                finally:
                    globals_["s3_action_buttons"] = saved_buttons
        finally:
            current.deployment_settings.get_req_req_type = saved_types
            response_s3.actions = saved_actions
            response_s3.jquery_ready = saved_ready

        self.assertIn(str(item_commit_id), action["restrict"])
        self.assertNotIn(str(people_commit_id), action["restrict"])

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

    # -------------------------------------------------------------------------
    def testCommitRheaderHandlesOtherCommitTypesAndNonHtmlViews(self):
        """commit_rheader falls back to other-type headers and ignores non-HTML views"""

        response_s3 = current.response.s3
        s3db = current.s3db

        office = self.create_office(name="Other Commit Header")
        req_id = self.create_request(office.site_id, req_type=9)
        commit_id = self.create_commit(req_id,
                                       organisation_id=office.organisation_id,
                                       committer_id=self.create_person(last_name="Committer"),
                                       )
        current.db(s3db.req_commit.id == commit_id).update(type=9,
                                                           comments="Other commitment",
                                                           )

        saved_footer = response_s3.rfooter

        try:
            with self.controller("req", function="commit_rheader") as controller:
                record = current.db(s3db.req_commit.id == commit_id).select(s3db.req_commit.ALL,
                                                                            limitby=(0, 1),
                                                                            ).first()
                other_rheader = controller.module["commit_rheader"](Storage(representation="html",
                                                                            record=record,
                                                                            name="commit",
                                                                            table=s3db.req_commit,
                                                                            id=commit_id,
                                                                            resource=Storage(get_config=lambda key: False),
                                                                            get_vars=Storage(),
                                                                            ))
                non_html = controller.module["commit_rheader"](Storage(representation="json",
                                                                       record=record,
                                                                       name="commit",
                                                                       table=s3db.req_commit,
                                                                       id=commit_id,
                                                                       resource=Storage(get_config=lambda key: False),
                                                                       get_vars=Storage(),
                                                                       ))
        finally:
            response_s3.rfooter = saved_footer

        self.assertIn("Committing Person", str(other_rheader))
        self.assertIn("Other commitment", str(other_rheader))
        self.assertIsNone(non_html)


# =============================================================================
if __name__ == "__main__":

    run_suite(
        ReqRepresentationTests,
        ReqConfigurationTests,
        ReqStatusTests,
        ReqCallbackTests,
        ReqHelperTests,
        ReqSendCommitTests,
        ReqWorkflowMethodTests,
        ReqMatchingTests,
        ReqControllerTests,
    )

# END ========================================================================
