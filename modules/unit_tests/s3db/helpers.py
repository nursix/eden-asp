# S3DB Supply Chain Unit Test Helpers
#
# Shared test fixtures for logistics-related unit tests.
#
import datetime
import os
import runpy
import unittest

from contextlib import contextmanager

from gluon import current
from gluon.storage import Storage


class ControllerRedirect(Exception):
    """Raised to intercept web2py redirects in controller unit tests"""

    def __init__(self, url):

        super().__init__(url)
        self.url = url


class SupplyChainTestCase(unittest.TestCase):
    """Shared helpers for supply chain unit tests"""

    _sequence = 0

    # -------------------------------------------------------------------------
    def setUp(self):

        current.auth.override = True

    # -------------------------------------------------------------------------
    def tearDown(self):

        current.db.rollback()
        current.auth.override = False

    # -------------------------------------------------------------------------
    @classmethod
    def unique_name(cls, prefix):
        """Generate a deterministic unique label for test records"""

        cls._sequence += 1
        return "%s%s" % (prefix, cls._sequence)

    # -------------------------------------------------------------------------
    @staticmethod
    def make_form(record=None, **vars):
        """Construct a minimal FORM-like object for callbacks"""

        return Storage(vars=Storage(vars),
                       errors=Storage(),
                       record=record,
                       )

    # -------------------------------------------------------------------------
    def create_organisation(self, name=None):
        """Create an organisation record"""

        s3db = current.s3db
        otable = s3db.org_organisation

        organisation = Storage(name=name or self.unique_name("Test Org "))
        organisation_id = otable.insert(**organisation)
        organisation.update(id=organisation_id)
        s3db.update_super(otable, organisation)

        return organisation_id

    # -------------------------------------------------------------------------
    def create_office(self,
                      organisation_id=None,
                      name=None,
                      code=None,
                      comments=None,
                      location_id=None,
                      phone1=None,
                      phone2=None):
        """Create an office and return both office_id and site_id"""

        db = current.db
        s3db = current.s3db

        # Create a parent organisation unless the test wants to control it
        if organisation_id is None:
            organisation_id = self.create_organisation()

        ftable = s3db.org_office
        office = Storage(name=name or self.unique_name("Test Office "),
                         organisation_id=organisation_id,
                         )
        office_id = ftable.insert(**office)
        office.update(id=office_id)
        s3db.update_super(ftable, office)

        # Read back the generated site/pe linkage from the super-entity update
        row = db(ftable.id == office_id).select(ftable.site_id,
                                                ftable.pe_id,
                                                limitby=(0, 1),
                                                ).first()
        site_id = row.site_id

        updates = {}
        if comments is not None:
            updates["comments"] = comments
        if location_id is not None:
            updates["location_id"] = location_id
        if phone1 is not None:
            updates["phone1"] = phone1
        if phone2 is not None:
            updates["phone2"] = phone2
        if updates:
            db(ftable.id == office_id).update(**updates)

        stable = s3db.org_site
        site_updates = {}
        if code:
            site_updates["code"] = code
        if location_id is not None:
            site_updates["location_id"] = location_id
        if site_updates:
            db(stable.site_id == site_id).update(**site_updates)

        return Storage(id=office_id,
                       pe_id=row.pe_id,
                       site_id=site_id,
                       organisation_id=organisation_id,
                       )

    # -------------------------------------------------------------------------
    def create_location(self, name=None, level=None, parent=None, L0=None):
        """Create a location record"""

        table = current.s3db.gis_location

        return table.insert(name=name or self.unique_name("Location "),
                            level=level,
                            parent=parent,
                            L0=L0,
                            )

    # -------------------------------------------------------------------------
    def create_person(self, first_name="Test", last_name=None):
        """Create a person record"""

        s3db = current.s3db
        ptable = s3db.pr_person

        person = Storage(first_name=first_name,
                         last_name=last_name or self.unique_name("Person"),
                         )
        person_id = ptable.insert(**person)
        person.update(id=person_id)
        s3db.update_super(ptable, person)

        return person_id

    # -------------------------------------------------------------------------
    def create_contact(self, person_id, value, contact_method="SMS"):
        """Create a contact detail for a person"""

        db = current.db
        s3db = current.s3db

        ptable = s3db.pr_person
        person = db(ptable.id == person_id).select(ptable.pe_id,
                                                   limitby=(0, 1),
                                                   ).first()
        self.assertIsNotNone(person)

        ctable = s3db.pr_contact
        return ctable.insert(pe_id=person.pe_id,
                             contact_method=contact_method,
                             value=value,
                             )

    # -------------------------------------------------------------------------
    def create_user_for_person(self,
                               person_id,
                               email=None,
                               language="en",
                               first_name="Test",
                               last_name=None):
        """Create an auth_user linked to a person"""

        db = current.db
        auth = current.auth
        s3db = current.s3db

        ptable = s3db.pr_person
        person = db(ptable.id == person_id).select(ptable.pe_id,
                                                   limitby=(0, 1),
                                                   ).first()
        self.assertIsNotNone(person)

        utable = auth.settings.table_user
        user_id = utable.insert(first_name=first_name,
                                last_name=last_name or self.unique_name("User"),
                                email=email or "%s@example.com" % self.unique_name("user").lower(),
                                password="test",
                                language=language,
                                )

        ltable = s3db.pr_person_user
        ltable.insert(user_id=user_id,
                      pe_id=person.pe_id,
                      )

        return user_id

    # -------------------------------------------------------------------------
    def create_catalog(self, organisation_id=None, name=None):
        """Create a supply catalog"""

        ctable = current.s3db.supply_catalog

        return ctable.insert(organisation_id=organisation_id,
                             name=name or self.unique_name("Catalog "),
                             )

    # -------------------------------------------------------------------------
    def create_item_category(self, catalog_id, name=None, code=None):
        """Create a supply item category"""

        table = current.s3db.supply_item_category

        return table.insert(catalog_id=catalog_id,
                            name=name or self.unique_name("Category "),
                            code=code,
                            )

    # -------------------------------------------------------------------------
    def create_catalog_item(self,
                            catalog_id,
                            item_id,
                            item_category_id=None,
                            comments=None):
        """Create a supply catalog item"""

        table = current.s3db.supply_catalog_item

        return table.insert(catalog_id=catalog_id,
                            item_id=item_id,
                            item_category_id=item_category_id,
                            comments=comments,
                            )

    # -------------------------------------------------------------------------
    def create_supply_item(self,
                           catalog_id=None,
                           item_category_id=None,
                           name=None,
                           code=None,
                           um="pc"):
        """Create a supply item"""

        if catalog_id is None:
            catalog_id = self.create_catalog()
        if item_category_id is None:
            item_category_id = self.create_item_category(catalog_id)

        table = current.s3db.supply_item

        return table.insert(catalog_id=catalog_id,
                            item_category_id=item_category_id,
                            code=code,
                            name=name or self.unique_name("Item "),
                            um=um,
                            )

    # -------------------------------------------------------------------------
    def create_item_pack(self,
                         item_id,
                         name="piece",
                         quantity=1.0,
                         weight=None,
                         volume=None):
        """Create a supply item pack"""

        table = current.s3db.supply_item_pack

        return table.insert(item_id=item_id,
                            name=name,
                            quantity=quantity,
                            weight=weight,
                            volume=volume,
                            )

    # -------------------------------------------------------------------------
    def create_request(self,
                       site_id,
                       req_type=1,
                       req_ref=None,
                       requester_id=None,
                       req_status=0,
                       commit_status=0,
                       transit_status=0,
                       fulfil_status=0,
                       **fields):
        """Create a request record"""

        table = current.s3db.req_req

        data = Storage(type=req_type,
                       site_id=site_id,
                       req_ref=req_ref,
                       requester_id=requester_id,
                       req_status=req_status,
                       commit_status=commit_status,
                       transit_status=transit_status,
                       fulfil_status=fulfil_status,
                       date_required=current.request.utcnow + datetime.timedelta(days=1),
                       )
        data.update(fields)

        return table.insert(**data)

    # -------------------------------------------------------------------------
    def create_request_item(self,
                            req_id,
                            item_id,
                            item_pack_id,
                            quantity,
                            quantity_commit=0,
                            quantity_transit=0,
                            quantity_fulfil=0):
        """Create a requested item"""

        table = current.s3db.req_req_item

        return table.insert(req_id=req_id,
                            item_id=item_id,
                            item_pack_id=item_pack_id,
                            quantity=quantity,
                            quantity_commit=quantity_commit,
                            quantity_transit=quantity_transit,
                            quantity_fulfil=quantity_fulfil,
                            )

    # -------------------------------------------------------------------------
    def create_commit(self,
                      req_id,
                      site_id=None,
                      organisation_id=None,
                      committer_id=None):
        """Create a commitment record"""

        table = current.s3db.req_commit

        return table.insert(req_id=req_id,
                            site_id=site_id,
                            organisation_id=organisation_id,
                            committer_id=committer_id,
                            )

    # -------------------------------------------------------------------------
    def create_commit_item(self,
                           commit_id,
                           req_item_id,
                           item_pack_id,
                           quantity):
        """Create a committed item"""

        table = current.s3db.req_commit_item

        return table.insert(commit_id=commit_id,
                            req_item_id=req_item_id,
                            item_pack_id=item_pack_id,
                            quantity=quantity,
                            )

    # -------------------------------------------------------------------------
    def create_inventory_item(self,
                              site_id,
                              item_id,
                              item_pack_id,
                              quantity,
                              **fields):
        """Create an inventory item"""

        table = current.s3db.inv_inv_item

        # Start from the minimal stock record and let callers override extras
        data = Storage(site_id=site_id,
                       item_id=item_id,
                       item_pack_id=item_pack_id,
                       quantity=quantity,
                       )
        data.update(fields)

        item_id = table.insert(**data)
        data.update(id=item_id)
        current.s3db.update_super(table, data)

        return item_id

    # -------------------------------------------------------------------------
    def create_track_item(self,
                          item_id,
                          item_pack_id,
                          quantity,
                          recv_quantity=None,
                          req_item_id=None,
                          send_id=None,
                          recv_id=None,
                          **fields):
        """Create a shipment tracking item"""

        table = current.s3db.inv_track_item

        # Mirror the common workflow default: full receipt unless specified otherwise
        if recv_quantity is None:
            recv_quantity = quantity

        data = Storage(item_id=item_id,
                       item_pack_id=item_pack_id,
                       quantity=quantity,
                       recv_quantity=recv_quantity,
                       req_item_id=req_item_id,
                       send_id=send_id,
                       recv_id=recv_id,
                       )
        data.update(fields)

        track_item_id = table.insert(**data)
        data.update(id=track_item_id)
        current.s3db.update_super(table, data)

        return track_item_id

    # -------------------------------------------------------------------------
    def create_warehouse(self, name=None, code=None, organisation_id=None):
        """Create a warehouse record"""

        s3db = current.s3db
        table = s3db.inv_warehouse

        warehouse = Storage(name=name or self.unique_name("Warehouse "),
                            code=code,
                            organisation_id=organisation_id,
                            )
        warehouse_id = table.insert(**warehouse)
        warehouse.update(id=warehouse_id)
        s3db.update_super(table, warehouse)

        return warehouse_id

    # -------------------------------------------------------------------------
    def create_send(self,
                    site_id,
                    to_site_id=None,
                    req_ref=None,
                    send_ref=None,
                    sender_id=None,
                    recipient_id=None,
                    organisation_id=None,
                    date=None,
                    **fields):
        """Create an outgoing shipment"""

        table = current.s3db.inv_send

        data = Storage(site_id=site_id,
                       to_site_id=to_site_id,
                       req_ref=req_ref,
                       send_ref=send_ref,
                       sender_id=sender_id,
                       recipient_id=recipient_id,
                       organisation_id=organisation_id,
                       date=date or current.request.utcnow.date(),
                       )
        data.update(fields)

        return table.insert(**data)

    # -------------------------------------------------------------------------
    def create_recv(self,
                    site_id,
                    from_site_id=None,
                    organisation_id=None,
                    send_ref=None,
                    recv_ref=None,
                    sender_id=None,
                    recipient_id=None,
                    date=None,
                    **fields):
        """Create an incoming shipment"""

        table = current.s3db.inv_recv

        data = Storage(site_id=site_id,
                       from_site_id=from_site_id,
                       organisation_id=organisation_id,
                       send_ref=send_ref,
                       recv_ref=recv_ref,
                       sender_id=sender_id,
                       recipient_id=recipient_id,
                       date=date or current.request.utcnow.date(),
                       )
        data.update(fields)

        return table.insert(**data)

    # -------------------------------------------------------------------------
    def create_proc_plan(self, site_id, order_date=None, eta=None, **fields):
        """Create a procurement plan"""

        table = current.s3db.proc_plan

        data = Storage(site_id=site_id,
                       order_date=order_date or current.request.utcnow.date(),
                       eta=eta,
                       )
        data.update(fields)

        return table.insert(**data)

    # -------------------------------------------------------------------------
    def create_proc_plan_item(self,
                              plan_id,
                              item_id,
                              item_pack_id,
                              quantity=1,
                              **fields):
        """Create a procurement plan item"""

        table = current.s3db.proc_plan_item

        data = Storage(plan_id=plan_id,
                       item_id=item_id,
                       item_pack_id=item_pack_id,
                       quantity=quantity,
                       )
        data.update(fields)

        plan_item_id = table.insert(**data)
        data.update(id=plan_item_id)
        current.s3db.update_super(table, data)

        return plan_item_id

    # -------------------------------------------------------------------------
    def create_skill(self, name=None):
        """Create an HR skill"""

        table = current.s3db.hrm_skill

        return table.insert(name=name or self.unique_name("Skill "))

    # -------------------------------------------------------------------------
    def create_request_skill(self,
                             req_id,
                             skill_ids=None,
                             quantity=1,
                             quantity_commit=0,
                             quantity_transit=0,
                             quantity_fulfil=0,
                             site_id=None):
        """Create a requested skill row"""

        table = current.s3db.req_req_skill

        return table.insert(req_id=req_id,
                            skill_id=skill_ids or [],
                            quantity=quantity,
                            quantity_commit=quantity_commit,
                            quantity_transit=quantity_transit,
                            quantity_fulfil=quantity_fulfil,
                            site_id=site_id,
                            )

    # -------------------------------------------------------------------------
    def create_commit_skill(self, commit_id, skill_ids=None, quantity=1):
        """Create a committed skill row"""

        table = current.s3db.req_commit_skill

        return table.insert(commit_id=commit_id,
                            skill_id=skill_ids or [],
                            quantity=quantity,
                            )

    # -------------------------------------------------------------------------
    def create_approver(self, pe_id, person_id, title=None, matcher=False):
        """Create a request approver"""

        table = current.s3db.req_approver

        return table.insert(pe_id=pe_id,
                            person_id=person_id,
                            title=title,
                            matcher=matcher,
                            )

    # -------------------------------------------------------------------------
    @staticmethod
    def _capture_controller_state():
        """Capture request/response state before loading a controller"""

        request = current.request
        response = current.response
        s3 = response.s3

        return Storage(controller=request.controller,
                       function=request.function,
                       args_class=request.args.__class__,
                       args=list(request.args),
                       vars=Storage(request.vars),
                       get_vars=Storage(request.get_vars),
                       post_vars=Storage(request.post_vars),
                       headers=dict(response.headers),
                       title=response.title,
                       prep=getattr(s3, "prep", None),
                       postp=getattr(s3, "postp", None),
                       filter=getattr(s3, "filter", None),
                       )

    # -------------------------------------------------------------------------
    @staticmethod
    def _restore_controller_state(state):
        """Restore request/response state after a controller test"""

        request = current.request
        response = current.response
        s3 = response.s3

        request.controller = state.controller
        request.function = state.function
        request.args = state.args_class(state.args)
        vars_ = Storage(state.vars)
        get_vars = Storage(state.get_vars)
        post_vars = Storage(state.post_vars)
        request._vars = vars_
        request._get_vars = get_vars
        request._post_vars = post_vars
        request.vars = vars_
        request.get_vars = get_vars
        request.post_vars = post_vars

        response.headers.clear()
        response.headers.update(state.headers)
        response.title = state.title
        s3.prep = state.prep
        s3.postp = state.postp
        s3.filter = state.filter

    # -------------------------------------------------------------------------
    @contextmanager
    def controller(self,
                   name,
                   function=None,
                   args=None,
                   query_vars=None,
                   vars=None,
                   overrides=None):
        """
            Load a controller module with a stubbed CRUD cycle

            Returns:
                Storage with:
                    module: controller globals
                    calls: captured crud_controller calls
        """

        request = current.request
        response = current.response

        state = self._capture_controller_state()

        if query_vars is None:
            query_vars = vars

        request.controller = name
        request.function = function or name
        request.args = state.args_class(list(args) if args else [])
        query = Storage(query_vars or {})
        post = Storage()
        request._vars = query
        request._get_vars = query
        request._post_vars = post
        request.vars = query
        request.get_vars = query
        request.post_vars = post

        response.s3.prep = None
        response.s3.postp = None
        response.s3.filter = None

        calls = []

        def crud_controller(*cargs, **ckwargs):
            """Capture CRUD controller invocations for assertions"""

            call = Storage(args=cargs,
                           kwargs=ckwargs,
                           prep=response.s3.prep,
                           postp=response.s3.postp,
                           filter=getattr(response.s3, "filter", None),
                           )
            calls.append(call)
            return call

        def redirect(url, *args, **kwargs):
            """Intercept controller redirects"""

            raise ControllerRedirect(url)

        env = current.globalenv.copy()
        env.update({"request": request,
                    "response": response,
                    "session": current.session,
                    "db": current.db,
                    "s3db": current.s3db,
                    "settings": current.deployment_settings,
                    "auth": current.auth,
                    "s3": response.s3,
                    "get_vars": request.get_vars,
                    "crud_controller": crud_controller,
                    "redirect": redirect,
                    "s3_redirect_default": redirect,
                    })
        if overrides:
            env.update(overrides)

        path = os.path.join(current.request.folder, "controllers", "%s.py" % name)

        try:
            module = runpy.run_path(path, init_globals=env)
            yield Storage(module=module, calls=calls)
        finally:
            self._restore_controller_state(state)
