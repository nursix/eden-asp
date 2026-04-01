# =============================================================================
#   Tasks to be callable async &/or on a Schedule
#   @ToDo: Rewrite a lot of these to use s3db_task or settings_task instead of
#          having a lot of separate tasks defined here
# =============================================================================

has_module = settings.has_module

# -----------------------------------------------------------------------------
def dummy():
    """
        Dummy Task
        - can be used to populate a table with a task_id
    """
    return

# -----------------------------------------------------------------------------
def s3db_task(function, user_id=None, **kwargs):
    """
        Generic Task
        - can be used to call any s3db.function(**kwargs)
        - saves having to create separate Tasks for many cases
    """
    if user_id:
        # Authenticate
        auth.s3_impersonate(user_id)
    # Run the Task & return the result
    result = s3db[function](**kwargs)
    db.commit()
    return result

# -----------------------------------------------------------------------------
def settings_task(taskname, user_id=None, **kwargs):
    """
        Generic Task
        - can be used to call any settings.tasks.taskname(**kwargs)
        - saves having to create separate Tasks for many cases
    """
    if user_id:
        # Authenticate
        auth.s3_impersonate(user_id)
    task = settings.get_task(taskname)
    if task:
        # Run the Task & return the result
        result = task(**kwargs)
        db.commit()
        return result

# -----------------------------------------------------------------------------
def maintenance(period = "daily"):
    """
        Run all maintenance tasks which should be done daily
        - instantiates and calls the Daily() class defined in the template's
          maintenance.py file - if it exists
        - falls back to the default template's maintenancy.py
    """

    maintenance = None
    result = "NotImplementedError"

    templates = settings.get_template()
    if templates != "default":
        # Try to import maintenance routine from template
        if not isinstance(templates, (tuple, list)):
            templates = (templates,)
        for template in templates[::-1]:
            package = "templates.%s" % template
            name = "maintenance"
            try:
                maintenance = getattr(__import__(package, fromlist=[name]), name)
            except (ImportError, AttributeError):
                pass
            else:
                break

    if maintenance is None:
        try:
            # Fallback to default maintenance routine
            from templates.default import maintenance
        except ImportError:
            pass

    if maintenance is not None:
        if period == "daily":
            result = maintenance.Daily()()
        db.commit()

    return result

# -----------------------------------------------------------------------------
# GIS: always-enabled
# -----------------------------------------------------------------------------
def gis_download_kml(record_id, filename, session_id_name, session_id,
                     user_id=None):
    """
        Download a KML file
            - will normally be done Asynchronously if there is a worker alive

        @param record_id: id of the record in db.gis_layer_kml
        @param filename: name to save the file as
        @param session_id_name: name of the session
        @param session_id: id of the session
        @param user_id: calling request's auth.user.id or None
    """
    if user_id:
        # Authenticate
        auth.s3_impersonate(user_id)
    # Run the Task & return the result
    result = gis.download_kml(record_id, filename, session_id_name, session_id)
    db.commit()
    return result

# -----------------------------------------------------------------------------
def gis_update_location_tree(feature, user_id=None):
    """
        Update the Location Tree for a feature
            - will normally be done Asynchronously if there is a worker alive

        @param feature: the feature (in JSON format)
        @param user_id: calling request's auth.user.id or None
    """
    if user_id:
        # Authenticate
        auth.s3_impersonate(user_id)
    # Run the Task & return the result
    feature = json.loads(feature)
    path = gis.update_location_tree(feature)
    db.commit()
    return path

# -----------------------------------------------------------------------------
# Org: always-enabled
# -----------------------------------------------------------------------------
def org_site_check(site_id, user_id=None):
    """ Check the Status for Sites """

    if user_id:
        # Authenticate
        auth.s3_impersonate(user_id)

    # Check for Template-specific processing
    customise = settings.get_org_site_check()
    if customise:
        customise(site_id)
        db.commit()

# -----------------------------------------------------------------------------
tasks = {"dummy": dummy,
         "s3db_task": s3db_task,
         "settings_task": settings_task,
         "maintenance": maintenance,
         "gis_download_kml": gis_download_kml,
         "gis_update_location_tree": gis_update_location_tree,
         "org_site_check": org_site_check,
         }

# -----------------------------------------------------------------------------
# Optional Modules
# -----------------------------------------------------------------------------
if has_module("cap"):

    # -------------------------------------------------------------------------
    def cap_ftp_sync(user_id=None):
        """ Get all the FTP repositories and synchronize them """

        if user_id:
            # Authenticate
            auth.s3_impersonate(user_id)

        rows = db(s3db.sync_repository.apitype == "ftp").select()

        if rows:
            sync = current.sync
            for row in rows:
                sync.synchronize(row)

    tasks["cap_ftp_sync"] = cap_ftp_sync

# -----------------------------------------------------------------------------
if has_module("msg"):

    # -------------------------------------------------------------------------
    def msg_process_outbox(contact_method, user_id=None):
        """
            Process Outbox
            - will normally be done Asynchronously if there is a worker alive

            @param contact_method: one from S3Msg.MSG_CONTACT_OPTS
            @param user_id: calling request's auth.user.id or None
        """
        if user_id:
            # Authenticate
            auth.s3_impersonate(user_id)

        # Run the Task & return the result
        result = msg.process_outbox(contact_method)
        db.commit()
        return result

    tasks["msg_process_outbox"] = msg_process_outbox

    # -------------------------------------------------------------------------
    def msg_poll(tablename, channel_id, user_id=None):
        """
            Poll an inbound channel
        """
        if user_id:
            auth.s3_impersonate(user_id)

        # Run the Task & return the result
        result = msg.poll(tablename, channel_id)
        db.commit()
        return result

    tasks["msg_poll"] = msg_poll

    # -----------------------------------------------------------------------------
    def msg_parse(channel_id, function_name, user_id=None):
        """
            Parse Messages coming in from a Source Channel
        """
        if user_id:
            auth.s3_impersonate(user_id)

        # Run the Task & return the result
        result = msg.parse(channel_id, function_name)
        db.commit()
        return result

    tasks["msg_parse"] = msg_parse

    # -------------------------------------------------------------------------
    def msg_gcm(title, uri, message, registration_ids, user_id=None):
        """ Push the data relating to google cloud messaging server """

        if user_id:
            # Authenticate
            auth.s3_impersonate(user_id)

        msg.gcm_push(title, uri, message, eval(registration_ids))

    tasks["msg_gcm"] = msg_gcm

# -----------------------------------------------------------------------------
if has_module("req"):

    def req_add_from_template(req_id, user_id=None):
        """
            Add a Request from template
        """
        if user_id:
            # Authenticate
            auth.s3_impersonate(user_id)

        # Run the Task & return the result
        result = s3db.req_add_from_template(req_id)
        db.commit()
        return result

    tasks["req_add_from_template"] = req_add_from_template

# -----------------------------------------------------------------------------
if has_module("stats"):

    def stats_demographic_update_aggregates(records = None,
                                            user_id = None,
                                            ):
        """
            Update the stats_demographic_aggregate table for the given
            stats_demographic_data record(s)

            @param records: JSON of Rows of stats_demographic_data records to
                            update aggregates for
            @param user_id: calling request's auth.user.id or None
        """
        if user_id:
            # Authenticate
            auth.s3_impersonate(user_id)

        # Run the Task & return the result
        result = s3db.stats_demographic_update_aggregates(records)
        db.commit()
        return result

    tasks["stats_demographic_update_aggregates"] = stats_demographic_update_aggregates

    # -------------------------------------------------------------------------
    def stats_demographic_update_location_aggregate(location_level,
                                                    root_location_id,
                                                    parameter_id,
                                                    start_date,
                                                    end_date,
                                                    user_id = None,
                                                    ):
        """
            Update the stats_demographic_aggregate table for the given location and parameter
            - called from within stats_demographic_update_aggregates

            @param location_level: gis level at which the data needs to be accumulated
            @param root_location_id: id of the location
            @param parameter_id: parameter for which the stats are being updated
            @param start_date: start date of the period in question
            @param end_date: end date of the period in question
            @param user_id: calling request's auth.user.id or None
        """
        if user_id:
            # Authenticate
            auth.s3_impersonate(user_id)

        # Run the Task & return the result
        result = s3db.stats_demographic_update_location_aggregate(location_level,
                                                                  root_location_id,
                                                                  parameter_id,
                                                                  start_date,
                                                                  end_date,
                                                                  )
        db.commit()
        return result

    tasks["stats_demographic_update_location_aggregate"] = stats_demographic_update_location_aggregate

    # --------------------e----------------------------------------------------
    # Disease: Depends on Stats
    # --------------------e----------------------------------------------------
    if has_module("disease"):

        def disease_stats_update_aggregates(records = None,
                                            all = False,
                                            user_id = None,
                                            ):
            """
                Update the disease_stats_aggregate table for the given
                disease_stats_data record(s)

                @param records: JSON of Rows of disease_stats_data records to
                                update aggregates for
                @param user_id: calling request's auth.user.id or None
            """
            if user_id:
                # Authenticate
                auth.s3_impersonate(user_id)

            # Run the Task & return the result
            result = s3db.disease_stats_update_aggregates(records, all)
            db.commit()
            return result

        tasks["disease_stats_update_aggregates"] = disease_stats_update_aggregates

        # ---------------------------------------------------------------------
        def disease_stats_update_location_aggregates(location_id,
                                                     children,
                                                     parameter_id,
                                                     dates,
                                                     user_id = None,
                                                     ):
            """
                Update the disease_stats_aggregate table for the given location and parameter
                - called from within disease_stats_update_aggregates

                @param location_id: location to aggregate at
                @param children: locations to aggregate from
                @param parameter_id: parameter to aggregate
                @param dates: dates to aggregate for
                @param user_id: calling request's auth.user.id or None
            """
            if user_id:
                # Authenticate
                auth.s3_impersonate(user_id)

            # Run the Task & return the result
            result = s3db.disease_stats_update_location_aggregates(location_id,
                                                                   children,
                                                                   parameter_id,
                                                                   dates,
                                                                   )
            db.commit()
            return result

        tasks["disease_stats_update_location_aggregates"] = disease_stats_update_location_aggregates

# -----------------------------------------------------------------------------
if has_module("sync"):

    def sync_synchronize(repository_id, user_id=None, manual=False):
        """
            Run all tasks for a repository, to be called from scheduler
        """
        if user_id:
            # Authenticate
            auth.s3_impersonate(user_id)

        rtable = s3db.sync_repository
        query = (rtable.deleted != True) & \
                (rtable.id == repository_id)
        repository = db(query).select(limitby=(0, 1)).first()
        if repository:
            sync = s3base.S3Sync()
            status = sync.get_status()
            if status.running:
                message = "Synchronization already active - skipping run"
                sync.log.write(repository_id=repository.id,
                               resource_name=None,
                               transmission=None,
                               mode=None,
                               action="check",
                               remote=False,
                               result=sync.log.ERROR,
                               message=message)
                db.commit()
                return sync.log.ERROR
            sync.set_status(running=True, manual=manual)
            try:
                sync.synchronize(repository)
            finally:
                sync.set_status(running=False, manual=False)
        db.commit()
        return s3base.S3SyncLog.SUCCESS

    tasks["sync_synchronize"] = sync_synchronize

# -----------------------------------------------------------------------------
# Instantiate Scheduler instance with the list of tasks
s3.tasks = tasks
s3task = s3base.S3Task()
current.s3task = s3task

# -----------------------------------------------------------------------------
# Field template for scheduler task links
scheduler_task_id = FieldTemplate("scheduler_task_id",
                                  "reference %s" % s3base.S3Task.TASK_TABLENAME,
                                  ondelete = "CASCADE",
                                  )
s3.scheduler_task_id = scheduler_task_id

# END =========================================================================
