"""
    Messaging Model

    Copyright: 2009-2022 (c) Sahana Software Foundation

    Permission is hereby granted, free of charge, to any person
    obtaining a copy of this software and associated documentation
    files (the "Software"), to deal in the Software without
    restriction, including without limitation the rights to use,
    copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the
    Software is furnished to do so, subject to the following
    conditions:

    The above copyright notice and this permission notice shall be
    included in all copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
    EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
    OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
    NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
    HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
    WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
    FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
    OTHER DEALINGS IN THE SOFTWARE.
"""

__all__ = ("MsgChannelModel",
           "MsgMessageModel",
           "MsgMessageAttachmentModel",
           "MsgMessageContactModel",
           "MsgMessageTagModel",
           "MsgEmailModel",
           "MsgFacebookModel",
           "MsgMCommonsModel",
           "MsgGCMModel",
           "MsgParsingModel",
           "MsgRSSModel",
           "MsgSMSModel",
           "MsgSMSOutboundModel",
           "MsgTropoModel",
           "MsgTwilioModel",
           "MsgXFormsModel",
           "MsgBaseStationModel",
           )

from gluon import *
from gluon.storage import Storage
from ..core import *

# Compact JSON encoding
SEPARATORS = (",", ":")

# =============================================================================
class MsgChannelModel(DataModel):
    """
        Messaging Channels
        - all Inbound & Outbound channels for messages are instances of this
          super-entity
    """

    names = ("msg_channel",
             "msg_channel_limit",
             "msg_channel_status",
             "msg_channel_id",
             "msg_channel_enable",
             "msg_channel_disable",
             "msg_channel_enable_interactive",
             "msg_channel_disable_interactive",
             "msg_channel_onaccept",
             )

    def model(self):

        T = current.T
        db = current.db

        define_table = self.define_table

        #----------------------------------------------------------------------
        # Super entity: msg_channel
        #
        channel_types = Storage(msg_email_channel = T("Email (Inbound)"),
                                msg_facebook_channel = T("Facebook"),
                                msg_gcm_channel = T("Google Cloud Messaging"),
                                msg_mcommons_channel = T("Mobile Commons (Inbound)"),
                                msg_rss_channel = T("RSS Feed"),
                                msg_sms_modem_channel = T("SMS Modem"),
                                msg_sms_webapi_channel = T("SMS WebAPI (Outbound)"),
                                msg_sms_smtp_channel = T("SMS via SMTP (Outbound)"),
                                msg_tropo_channel = T("Tropo"),
                                msg_twilio_channel = T("Twilio (Inbound)"),
                                )

        tablename = "msg_channel"
        self.super_entity(tablename, "channel_id",
                          channel_types,
                          Field("name",
                                #label = T("Name"),
                                ),
                          Field("description",
                                #label = T("Description"),
                                ),
                          Field("enabled", "boolean",
                                default = True,
                                #label = T("Enabled?")
                                #represent = s3_yes_no_represent,
                                ),
                          # @ToDo: Indicate whether channel can be used for Inbound or Outbound
                          #Field("inbound", "boolean",
                          #      label = T("Inbound?")),
                          #Field("outbound", "boolean",
                          #      label = T("Outbound?")),
                          on_define = lambda table: \
                            [table.instance_type.set_attributes(readable = True),
                             ],
                          )

        # Foreign Key Template
        channel_id = FieldTemplate("channel_id", "reference %s" % tablename,
                                   label = T("Channel"),
                                   ondelete = "SET NULL",
                                   represent = S3Represent(lookup = tablename),
                                   requires = IS_EMPTY_OR(
                                                IS_ONE_OF_EMPTY(db, "msg_channel.channel_id")),
                                   )

        self.add_components(tablename,
                            msg_channel_status = "channel_id",
                            )

        # ---------------------------------------------------------------------
        # Channel Limit
        #  Used to limit the number of emails sent from the system
        #  - works by simply recording an entry for the timestamp to be checked against
        #
        # - currently just used by msg.send_email()
        #
        tablename = "msg_channel_limit"
        define_table(tablename,
                     # @ToDo: Make it per-channel
                     #channel_id(),
                     *MetaFields.timestamps(),
                     meta = False,
                     )

        # ---------------------------------------------------------------------
        # Channel Status
        #  Used to record errors encountered in the Channel
        #
        tablename = "msg_channel_status"
        define_table(tablename,
                     channel_id(),
                     Field("status",
                           #label = T("Status"),
                           #represent = s3_yes_no_represent,
                           represent = lambda v: v or current.messages["NONE"],
                           ),
                     )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        return {"msg_channel_id": channel_id,
                "msg_channel_enable": self.channel_enable,
                "msg_channel_disable": self.channel_disable,
                "msg_channel_enable_interactive": self.channel_enable_interactive,
                "msg_channel_disable_interactive": self.channel_disable_interactive,
                "msg_channel_onaccept": self.channel_onaccept,
                "msg_channel_poll": self.channel_poll,
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def channel_enable(tablename, channel_id):
        """
            Enable a Channel
            - Schedule a Poll for new messages
            - Enable all associated Parsers

            CLI API for shell scripts & to be called by CRUDMethod
        """

        db = current.db
        s3db = current.s3db
        table = s3db.table(tablename)
        record = db(table.channel_id == channel_id).select(table.id, # needed for update_record
                                                           table.enabled,
                                                           limitby=(0, 1),
                                                           ).first()
        if not record.enabled:
            # Flag it as enabled
            # Update Instance
            record.update_record(enabled = True)
            # Update Super
            s3db.update_super(table, record)

        # Enable all Parser tasks on this channel
        ptable = s3db.msg_parser
        query = (ptable.channel_id == channel_id) & \
                (ptable.deleted == False)
        parsers = db(query).select(ptable.id)
        for parser in parsers:
            s3db.msg_parser_enable(parser.id)

        # Do we have an existing Task?
        ttable = db.scheduler_task
        args = '["%s", %s]' % (tablename, channel_id)
        query = ((ttable.function_name == "msg_poll") & \
                 (ttable.args == args) & \
                 (ttable.status.belongs(["RUNNING", "QUEUED", "ALLOCATED"])))
        exists = db(query).select(ttable.id,
                                  limitby=(0, 1)).first()
        if exists:
            return "Channel already enabled"
        else:
            current.s3task.schedule_task("msg_poll",
                                         args = [tablename, channel_id],
                                         period = 300,  # seconds
                                         timeout = 300, # seconds
                                         repeats = 0    # unlimited
                                         )
            return "Channel enabled"

    # -------------------------------------------------------------------------
    @staticmethod
    def channel_enable_interactive(r, **attr):
        """
            Enable a Channel
            - Schedule a Poll for new messages

            CRUD m´ethod for interactive requests
        """

        tablename = r.tablename
        result = current.s3db.msg_channel_enable(tablename, r.record.channel_id)
        current.session.confirmation = result
        fn = tablename.split("_", 1)[1]
        redirect(URL(f=fn))

    # -------------------------------------------------------------------------
    @staticmethod
    def channel_disable(tablename, channel_id):
        """
            Disable a Channel
            - Remove schedule for Polling for new messages
            - Disable all associated Parsers

            CLI API for shell scripts & to be called by CRUDMethod
        """

        db = current.db
        s3db = current.s3db
        table = s3db.table(tablename)
        record = db(table.channel_id == channel_id).select(table.id, # needed for update_record
                                                           table.enabled,
                                                           limitby=(0, 1),
                                                           ).first()
        if record.enabled:
            # Flag it as disabled
            # Update Instance
            record.update_record(enabled = False)
            # Update Super
            s3db.update_super(table, record)

        # Disable all Parser tasks on this channel
        ptable = s3db.msg_parser
        parsers = db(ptable.channel_id == channel_id).select(ptable.id)
        for parser in parsers:
            s3db.msg_parser_disable(parser.id)

        # Do we have an existing Task?
        ttable = db.scheduler_task
        args = '["%s", %s]' % (tablename, channel_id)
        query = ((ttable.function_name == "msg_poll") & \
                 (ttable.args == args) & \
                 (ttable.status.belongs(["RUNNING", "QUEUED", "ALLOCATED"])))
        exists = db(query).select(ttable.id,
                                  limitby=(0, 1)).first()
        if exists:
            # Disable all
            db(query).update(status="STOPPED")
            return "Channel disabled"
        else:
            return "Channel already disabled"

    # --------------------------------------------------------------------------
    @staticmethod
    def channel_disable_interactive(r, **attr):
        """
            Disable a Channel
            - Remove schedule for Polling for new messages

            CRUD method for interactive requests
        """

        tablename = r.tablename
        result = current.s3db.msg_channel_disable(tablename, r.record.channel_id)
        current.session.confirmation = result
        fn = tablename.split("_", 1)[1]
        redirect(URL(f=fn))

    # -------------------------------------------------------------------------
    @staticmethod
    def channel_onaccept(form):
        """
            Process the Enabled Flag
        """

        form_vars = form.vars
        if form.record:
            # Update form
            # Process if changed
            if form.record.enabled and not form_vars.enabled:
                current.s3db.msg_channel_disable(form.table._tablename,
                                                 form_vars.channel_id)
            elif form_vars.enabled and not form.record.enabled:
                current.s3db.msg_channel_enable(form.table._tablename,
                                                form_vars.channel_id)
        else:
            # Create form
            # Process only if enabled
            if form_vars.enabled:
                current.s3db.msg_channel_enable(form.table._tablename,
                                                form_vars.channel_id)

    # -------------------------------------------------------------------------
    @staticmethod
    def channel_poll(r, **attr):
        """
            Poll a Channel for new messages

            CRUD method for interactive requests
        """

        tablename = r.tablename
        current.s3task.run_async("msg_poll",
                                 args = [tablename, r.record.channel_id])
        current.session.confirmation = \
            current.T("The poll request has been submitted, so new messages should appear shortly - refresh to see them")
        if tablename == "msg_email_channel":
            fn = "email_inbox"
        elif tablename == "msg_mcommons_channel":
            fn = "sms_inbox"
        elif tablename == "msg_rss_channel":
            fn = "rss"
        elif tablename == "msg_twilio_channel":
            fn = "sms_inbox"
        else:
            return "Unsupported channel: %s" % tablename

        redirect(URL(f=fn))

# =============================================================================
class MsgMessageModel(DataModel):
    """
        Messages
    """

    names = ("msg_message",
             "msg_message_id",
             "msg_message_represent",
             "msg_outbox",
             )

    def model(self):

        T = current.T
        db = current.db

        UNKNOWN_OPT = current.messages.UNKNOWN_OPT

        configure = self.configure

        # Message priority
        msg_priority_opts = {3 : T("High"),
                             2 : T("Medium"),
                             1 : T("Low"),
                             }

        # ---------------------------------------------------------------------
        # Message Super Entity - all Inbound & Outbound Messages
        #

        message_types = Storage(msg_contact = T("Contact"),
                                msg_email = T("Email"),
                                msg_facebook = T("Facebook"),
                                msg_rss = T("RSS"),
                                msg_sms = T("SMS"),
                                )

        tablename = "msg_message"
        self.super_entity(tablename, "message_id",
                          message_types,
                          # Knowing which Channel Incoming Messages
                          # came in on allows correlation to Outbound
                          # messages (campaign_message, deployment_alert, etc)
                          self.msg_channel_id(),
                          DateTimeField(default="now"),
                          Field("body", "text",
                                label = T("Message"),
                                ),
                          Field("from_address",
                                label = T("From"),
                                ),
                          Field("to_address",
                                label = T("To"),
                                ),
                          Field("inbound", "boolean",
                                default = False,
                                label = T("Direction"),
                                represent = lambda direction: \
                                            (direction and [T("In")] or \
                                                           [T("Out")])[0],
                                ),
                          on_define = lambda table: \
                            [table.instance_type.set_attributes(readable = True,
                                                                writable = True,
                                                                ),

                             ],
                          )

        configure(tablename,
                  list_fields = ["instance_type",
                                 "from_address",
                                 "to_address",
                                 "body",
                                 "inbound",
                                 ],
                  )

        # Foreign Key Template
        message_represent = S3Represent(lookup = tablename, fields = ["body"])
        message_id = FieldTemplate("message_id", "reference %s" % tablename,
                                   ondelete = "RESTRICT",
                                   represent = message_represent,
                                   requires = IS_EMPTY_OR(
                                                IS_ONE_OF_EMPTY(db, "msg_message.message_id")),
                                   )

        self.add_components(tablename,
                            msg_attachment = "message_id",
                            msg_tag = "message_id",
                            deploy_response = "message_id",
                            )

        # ---------------------------------------------------------------------
        # Outbound Messages
        #

        # Show only the supported messaging methods
        MSG_CONTACT_OPTS = current.msg.MSG_CONTACT_OPTS

        # Maximum number of retries to send a message
        MAX_SEND_RETRIES = current.deployment_settings.get_msg_max_send_retries()

        # Valid message outbox statuses
        MSG_STATUS_OPTS = {1 : T("Unsent"),
                           2 : T("Sent"),
                           3 : T("Draft"),
                           4 : T("Invalid"),
                           5 : T("Failed"),
                           }

        opt_msg_status = FieldTemplate("status", "integer",
                                       notnull=True,
                                       requires = IS_IN_SET(MSG_STATUS_OPTS,
                                                            zero = None,
                                                            ),
                                       default = 1,
                                       label = T("Status"),
                                       represent = lambda opt: \
                                                   MSG_STATUS_OPTS.get(opt, UNKNOWN_OPT)
                                       )

        # Outbox - needs to be separate to Message since a single message
        # sent needs different outbox entries for each recipient
        tablename = "msg_outbox"
        self.define_table(tablename,
                          # FK not instance
                          message_id(),
                          # Person/Group to send the message out to:
                          self.super_link("pe_id", "pr_pentity"),
                          # If set used instead of picking up from pe_id:
                          Field("address"),
                          Field("contact_method", length=32,
                                default = "EMAIL",
                                label = T("Contact Method"),
                                represent = lambda opt: \
                                            MSG_CONTACT_OPTS.get(opt, UNKNOWN_OPT),
                                requires = IS_IN_SET(MSG_CONTACT_OPTS,
                                                     zero=None),
                                ),
                          opt_msg_status(),
                          # Used to loop through a PE to get it's members
                          Field("system_generated", "boolean",
                                default = False,
                                ),
                          # Give up if we can't send after MAX_RETRIES
                          Field("retries", "integer",
                                default = MAX_SEND_RETRIES,
                                readable = False,
                                writable = False,
                                ),
                          )

        configure(tablename,
                  list_fields = ["id",
                                 "message_id",
                                 "pe_id",
                                 "status",
                                 ],
                  orderby = "msg_outbox.created_on desc",
                  )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        return {"msg_message_id": message_id,
                "msg_message_represent": message_represent,
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def defaults():
        """
            Return safe defaults in case the model has been deactivated.
        """

        return {"msg_message_id": FieldTemplate.dummy("message_id"),
                }

# =============================================================================
class MsgMessageAttachmentModel(DataModel):
    """
        Message Attachments
        - link table between msg_message & doc_document
    """

    names = ("msg_attachment",)

    def model(self):

        # ---------------------------------------------------------------------
        #
        tablename = "msg_attachment"
        self.define_table(tablename,
                          # FK not instance
                          self.msg_message_id(ondelete = "CASCADE"),
                          # document_id not doc_id
                          self.doc_document_id(),
                          )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        return None

# =============================================================================
class MsgMessageContactModel(DataModel):
    """
        Contact Form
    """

    names = ("msg_contact",
             )

    def model(self):

        T = current.T

        # ---------------------------------------------------------------------
        # Contact Messages: InBox
        #
        # Should probably use project_task if this kind of functionality is desired:
        #priority_opts = {1: T("Low"),
        #                 2: T("Medium"),
        #                 3: T("High"),
        #                 }

        #status_opts = {1: T("New"),
        #               2: T("In-Progress"),
        #               3: T("Closed"),
        #               }

        tablename = "msg_contact"
        self.define_table(tablename,
                          # Instance
                          self.super_link("message_id", "msg_message"),
                          self.msg_channel_id(), # Unused
                          DateTimeField(default = "now"),
                          Field("subject", length=78,    # RFC 2822
                                label = T("Subject"),
                                requires = IS_LENGTH(78),
                                ),
                          Field("name",
                                label = T("Name"),
                                ),
                          Field("body", "text",
                                label = T("Message"),
                                ),
                          Field("phone",
                                label = T("Phone"),
                                requires = IS_EMPTY_OR(IS_PHONE_NUMBER_MULTI()),
                                ),
                          Field("from_address",
                                label = T("Email"),
                                requires = IS_EMPTY_OR(IS_EMAIL()),
                                ),
                          #Field("priority", "integer",
                          #      default = 1,
                          #      label = T("Priority"),
                          #      represent = represent_option(priority_opts),
                          #      requires = IS_IN_SET(priority_opts,
                          #                           zero = None),
                          #      ),
                          #Field("status", "integer",
                          #      default = 3,
                          #      label = T("Status"),
                          #      represent = represent_option(status_opts),
                          #      requires = IS_IN_SET(status_opts,
                          #                           zero = None),
                          #      ),
                          Field("inbound", "boolean",
                                default = True,
                                label = T("Direction"),
                                represent = lambda direction: \
                                            (direction and [T("In")] or [T("Out")])[0],
                                readable = False,
                                writable = False,
                                ),
                          )

        self.configure(tablename,
                       orderby = "msg_contact.date desc",
                       super_entity = "msg_message",
                       )

        # CRUD strings
        current.response.s3.crud_strings[tablename] = Storage(
            label_create=T("Contact Form"),
            title_display=T("Contact Details"),
            title_list=T("Contacts"),
            title_update=T("Edit Contact"),
            label_list_button=T("List Contacts"),
            label_delete_button=T("Delete Contact"),
            msg_record_created=T("Contact added"),
            msg_record_modified=T("Contact updated"),
            msg_record_deleted=T("Contact deleted"),
            msg_list_empty=T("No Contacts currently registered"))

        # ---------------------------------------------------------------------
        return None

# =============================================================================
class MsgMessageTagModel(DataModel):
    """
        Message Tags
    """

    names = ("msg_tag",)

    def model(self):

        T = current.T

        # ---------------------------------------------------------------------
        # Message Tags
        # - Key-Value extensions
        # - can be used to provide conversions to external systems, such as:
        #   * HXL, FTS
        # - can be a Triple Store for Semantic Web support
        # - can be used to add custom fields
        #
        tablename = "msg_tag"
        self.define_table(tablename,
                          # FK not instance
                          self.msg_message_id(ondelete="CASCADE"),
                          # key is a reserved word in MySQL
                          Field("tag",
                                label = T("Key"),
                                ),
                          Field("value",
                                label = T("Value"),
                                ),
                          CommentsField(),
                          )

        self.configure(tablename,
                       deduplicate = S3Duplicate(primary = ("message_id",
                                                            "tag",
                                                            ),
                                                 ),
                       )

        # Pass names back to global scope (s3.*)
        return None

# =============================================================================
class MsgEmailModel(MsgChannelModel):
    """
        Email
            InBound Channels
                Outbound Email is currently handled via deployment_settings
            InBox/OutBox
    """

    names = ("msg_email_channel",
             "msg_email",
             )

    def model(self):

        T = current.T

        configure = self.configure
        define_table = self.define_table
        set_method = self.set_method
        super_link = self.super_link

        # ---------------------------------------------------------------------
        # Email Inbound Channels
        #
        tablename = "msg_email_channel"
        define_table(tablename,
                     # Instance
                     super_link("channel_id", "msg_channel"),
                     Field("name"),
                     Field("description"),
                     # Allows using different Inboxes for different Orgs/Branches
                     self.org_organisation_id(),
                     Field("enabled", "boolean",
                           default = True,
                           label = T("Enabled?"),
                           represent = s3_yes_no_represent,
                           ),
                     Field("server"),
                     Field("protocol",
                           requires = IS_IN_SET(["imap", "pop3"],
                                                zero=None),
                           ),
                     Field("use_ssl", "boolean"),
                     Field("port", "integer"),
                     Field("username"),
                     Field("password", "password", length=64,
                           readable = False,
                           requires = [IS_NOT_EMPTY(),
                                       IS_LENGTH(64),
                                       ],
                           widget = S3PasswordWidget.widget,
                           ),
                     # Set true to delete messages from the remote
                     # inbox after fetching them.
                     Field("delete_from_server", "boolean"),
                     )

        configure(tablename,
                  onaccept = self.msg_channel_onaccept,
                  super_entity = "msg_channel",
                  )

        set_method("msg_email_channel",
                   method = "enable",
                   action = self.msg_channel_enable_interactive)

        set_method("msg_email_channel",
                   method = "disable",
                   action = self.msg_channel_disable_interactive)

        set_method("msg_email_channel",
                   method = "poll",
                   action = self.msg_channel_poll)

        # ---------------------------------------------------------------------
        # Email Messages: InBox & Outbox
        #
        sender = current.deployment_settings.get_mail_sender()

        tablename = "msg_email"
        define_table(tablename,
                     # Instance
                     super_link("message_id", "msg_message"),
                     self.msg_channel_id(),
                     DateTimeField(default = "now"),
                     Field("subject", length=78,    # RFC 2822
                           label = T("Subject"),
                           requires = IS_LENGTH(78),
                           ),
                     Field("body", "text",
                           label = T("Message"),
                           ),
                     Field("from_address", #notnull=True,
                           default = sender,
                           label = T("Sender"),
                           requires = IS_EMAIL(),
                           ),
                     Field("to_address",
                           label = T("To"),
                           requires = IS_EMAIL(),
                           ),
                     Field("raw", "text",
                           label = T("Message Source"),
                           readable = False,
                           writable = False,
                           ),
                     Field("inbound", "boolean",
                           default = False,
                           label = T("Direction"),
                           represent = lambda direction: \
                                       (direction and [T("In")] or [T("Out")])[0],
                           ),
                     )

        configure(tablename,
                  orderby = "msg_email.date desc",
                  super_entity = "msg_message",
                  )

        # Components
        self.add_components(tablename,
                            # Used to link to custom tab deploy_response_select_mission:
                            deploy_mission = {"name": "select",
                                              "link": "deploy_response",
                                              "joinby": "message_id",
                                              "key": "mission_id",
                                              "autodelete": False,
                                              },
                            )

        # ---------------------------------------------------------------------
        return None

# =============================================================================
class MsgFacebookModel(MsgChannelModel):
    """
        Facebook
            Channels
            InBox/OutBox

        https://developers.facebook.com/docs/graph-api
    """

    names = ("msg_facebook_channel",
             "msg_facebook",
             "msg_facebook_login",
             )

    def model(self):

        T = current.T

        configure = self.configure
        define_table = self.define_table
        set_method = self.set_method
        super_link = self.super_link

        # ---------------------------------------------------------------------
        # Facebook Channels
        #
        tablename = "msg_facebook_channel"
        define_table(tablename,
                     # Instance
                     super_link("channel_id", "msg_channel"),
                     Field("name"),
                     Field("description"),
                     Field("enabled", "boolean",
                           default = True,
                           label = T("Enabled?"),
                           represent = s3_yes_no_represent,
                           ),
                     Field("login", "boolean",
                           default = False,
                           label = T("Use for Login?"),
                           represent = s3_yes_no_represent,
                           ),
                     Field("app_id", "bigint",
                           requires = IS_INT_IN_RANGE(0, +1e16)
                           ),
                     Field("app_secret", "password", length=64,
                           readable = False,
                           requires = [IS_NOT_EMPTY(),
                                       IS_LENGTH(64),
                                       ],
                           widget = S3PasswordWidget.widget,
                           ),
                     # Optional
                     Field("page_id", "bigint",
                           requires = IS_INT_IN_RANGE(0, +1e16)
                           ),
                     Field("page_access_token"),
                     )

        configure(tablename,
                  onaccept = self.msg_facebook_channel_onaccept,
                  super_entity = "msg_channel",
                  )

        set_method("msg_facebook_channel",
                   method = "enable",
                   action = self.msg_channel_enable_interactive)

        set_method("msg_facebook_channel",
                   method = "disable",
                   action = self.msg_channel_disable_interactive)

        #set_method("msg_facebook_channel",
        #           method = "poll",
        #           action = self.msg_channel_poll)

        # ---------------------------------------------------------------------
        # Facebook Messages: InBox & Outbox
        #

        tablename = "msg_facebook"
        define_table(tablename,
                     # Instance
                     super_link("message_id", "msg_message"),
                     self.msg_channel_id(),
                     DateTimeField(default = "now"),
                     Field("body", "text",
                           label = T("Message"),
                           ),
                     # @ToDo: Are from_address / to_address relevant in Facebook?
                     Field("from_address", #notnull=True,
                           #default = sender,
                           label = T("Sender"),
                           ),
                     Field("to_address",
                           label = T("To"),
                           ),
                     Field("inbound", "boolean",
                           default = False,
                           label = T("Direction"),
                           represent = lambda direction: \
                                       (direction and [T("In")] or [T("Out")])[0],
                           ),
                     )

        configure(tablename,
                  orderby = "msg_facebook.date desc",
                  super_entity = "msg_message",
                  )

        # ---------------------------------------------------------------------
        return {"msg_facebook_login": self.msg_facebook_login,
                }

    # -------------------------------------------------------------------------
    @staticmethod
    def defaults():
        """ Safe defaults for model-global names if module is disabled """

        return {"msg_facebook_login": lambda: False,
                }

    # -------------------------------------------------------------------------
    @classmethod
    def msg_facebook_channel_onaccept(cls, form):

        if form.vars.login:
            # Ensure only a single account used for Login
            current.db(current.s3db.msg_facebook_channel.id != form.vars.id).update(login = False)

        # Normal onaccept processing
        cls.channel_onaccept(form)

    # -------------------------------------------------------------------------
    @staticmethod
    def msg_facebook_login():

        table = current.s3db.msg_facebook_channel
        query = (table.login == True) & \
                (table.deleted == False)
        c = current.db(query).select(table.app_id,
                                     table.app_secret,
                                     limitby=(0, 1)
                                     ).first()
        return c

# =============================================================================
class MsgMCommonsModel(MsgChannelModel):
    """
        Mobile Commons Inbound SMS Settings
        - Outbound can use Web API
    """

    names = ("msg_mcommons_channel",)

    def model(self):

        #T = current.T

        set_method = self.set_method

        # ---------------------------------------------------------------------
        tablename = "msg_mcommons_channel"
        self.define_table(tablename,
                          self.super_link("channel_id", "msg_channel"),
                          Field("name"),
                          Field("description"),
                          Field("enabled", "boolean",
                                default = True,
                                #label = T("Enabled?"),
                                represent = s3_yes_no_represent,
                                ),
                          Field("campaign_id", length=128, unique=True,
                                requires = [IS_NOT_EMPTY(),
                                            IS_LENGTH(128),
                                            ],
                                ),
                          Field("url",
                                default = \
                                    "https://secure.mcommons.com/api/messages",
                                requires = IS_URL()
                                ),
                          Field("username",
                                requires = IS_NOT_EMPTY(),
                                ),
                          Field("password", "password",
                                readable = False,
                                requires = IS_NOT_EMPTY(),
                                widget = S3PasswordWidget.widget,
                                ),
                          Field("query"),
                          Field("timestmp", "datetime",
                                writable = False,
                                ),
                          )

        self.configure(tablename,
                       onaccept = self.msg_channel_onaccept,
                       super_entity = "msg_channel",
                       )

        set_method("msg_mcommons_channel",
                   method = "enable",
                   action = self.msg_channel_enable_interactive)

        set_method("msg_mcommons_channel",
                   method = "disable",
                   action = self.msg_channel_disable_interactive)

        set_method("msg_mcommons_channel",
                   method = "poll",
                   action = self.msg_channel_poll)

        # ---------------------------------------------------------------------
        return None

# =============================================================================
class MsgGCMModel(MsgChannelModel):
    """
        Google Cloud Messaging
            Channels

        https://developers.google.com/cloud-messaging/
    """

    names = ("msg_gcm_channel",
             )

    def model(self):

        T = current.T

        set_method = self.set_method

        # ---------------------------------------------------------------------
        # GCM Channels
        #
        tablename = "msg_gcm_channel"
        self.define_table(tablename,
                          # Instance
                          self.super_link("channel_id", "msg_channel"),
                          Field("name"),
                          Field("description"),
                          Field("enabled", "boolean",
                                default = True,
                                label = T("Enabled?"),
                                represent = s3_yes_no_represent,
                                ),
                          #Field("login", "boolean",
                          #      default = False,
                          #      label = T("Use for Login?"),
                          #      represent = s3_yes_no_represent,
                          #      ),
                          Field("api_key",
                                notnull = True,
                                ),
                          )

        self.configure(tablename,
                       onaccept = self.msg_gcm_channel_onaccept,
                       super_entity = "msg_channel",
                       )

        set_method("msg_gcm_channel",
                   method = "enable",
                   action = self.msg_channel_enable_interactive)

        set_method("msg_gcm_channel",
                   method = "disable",
                   action = self.msg_channel_disable_interactive)

        #set_method("msg_gcm_channel",
        #           method = "poll",
        #           action = self.msg_channel_poll)

        # ---------------------------------------------------------------------
        return None

    # -------------------------------------------------------------------------
    @classmethod
    def msg_gcm_channel_onaccept(cls, form):

        if form.vars.enabled:
            # Ensure only a single account enabled
            current.db(current.s3db.msg_gcm_channel.id != form.vars.id).update(enabled = False)

        # Normal onaccept processing
        cls.channel_onaccept(form)

# =============================================================================
class MsgParsingModel(DataModel):
    """
        Message Parsing Model
    """

    names = ("msg_parser",
             "msg_parsing_status",
             "msg_session",
             "msg_keyword",
             "msg_sender",
             "msg_parser_enabled",
             "msg_parser_enable",
             "msg_parser_disable",
             "msg_parser_enable_interactive",
             "msg_parser_disable_interactive",
             )

    def model(self):

        T = current.T

        define_table = self.define_table
        set_method = self.set_method

        channel_id = self.msg_channel_id
        message_id = self.msg_message_id

        # ---------------------------------------------------------------------
        # Link between Message Channels and Parsers in parser.py
        #
        tablename = "msg_parser"
        define_table(tablename,
                     # Source
                     channel_id(ondelete = "CASCADE"),
                     Field("function_name",
                           label = T("Parser"),
                           ),
                     Field("enabled", "boolean",
                           default = True,
                           label = T("Enabled?"),
                           represent = s3_yes_no_represent,
                           ),
                     )

        self.configure(tablename,
                       onaccept = self.msg_parser_onaccept,
                       )

        set_method("msg_parser",
                   method = "enable",
                   action = self.parser_enable_interactive)

        set_method("msg_parser",
                   method = "disable",
                   action = self.parser_disable_interactive)

        set_method("msg_parser",
                   method = "parse",
                   action = self.parser_parse)

        # ---------------------------------------------------------------------
        # Message parsing status
        # - component to core msg_message table
        # - messages which need parsing are placed here & updated when parsed
        #
        tablename = "msg_parsing_status"
        define_table(tablename,
                     # Component, not Instance
                     message_id(ondelete = "CASCADE"),
                     # Source
                     channel_id(ondelete = "CASCADE"),
                     Field("is_parsed", "boolean",
                           default = False,
                           label = T("Parsing Status"),
                           represent = lambda parsed: \
                                       (parsed and [T("Parsed")] or \
                                                   [T("Not Parsed")])[0],
                           ),
                     message_id("reply_id",
                                label = T("Reply"),
                                ondelete = "CASCADE",
                                ),
                     )

        # ---------------------------------------------------------------------
        # Login sessions for Message Parsing
        # - links a from_address with a login until expiry
        #
        tablename = "msg_session"
        define_table(tablename,
                     Field("from_address"),
                     Field("email"),
                     Field("created_datetime", "datetime",
                           default = current.request.utcnow,
                           ),
                     Field("expiration_time", "integer"),
                     Field("is_expired", "boolean",
                           default = False,
                           ),
                     )

        # ---------------------------------------------------------------------
        # Keywords for Message Parsing
        #
        tablename = "msg_keyword"
        define_table(tablename,
                     Field("keyword",
                           label = T("Keyword"),
                           ),
                     # @ToDo: Move this to a link table
                     self.event_incident_type_id(),
                     )

        # ---------------------------------------------------------------------
        # Senders for Message Parsing
        # - whitelist / blacklist / prioritise
        #
        tablename = "msg_sender"
        define_table(tablename,
                     Field("sender",
                           label = T("Sender"),
                           ),
                     # @ToDo: Make pe_id work for this
                     #self.super_link("pe_id", "pr_pentity"),
                     Field("priority", "integer",
                           label = T("Priority"),
                           ),
                     )

        # ---------------------------------------------------------------------
        return {"msg_parser_enabled": self.parser_enabled,
                "msg_parser_enable": self.parser_enable,
                "msg_parser_disable": self.parser_disable,
                }

    # -----------------------------------------------------------------------------
    @staticmethod
    def parser_parse(r, **attr):
        """
            Parse unparsed messages

            CRUD method for interactive requests
        """

        record = r.record
        current.s3task.run_async("msg_parse",
                                 args = [record.channel_id,
                                         record.function_name])
        current.session.confirmation = \
            current.T("The parse request has been submitted")
        redirect(URL(f="parser"))

    # -------------------------------------------------------------------------
    @staticmethod
    def parser_enabled(channel_id):
        """
            Helper function to see if there is a Parser connected to a Channel
            - used to determine whether to populate the msg_parsing_status table
        """

        table = current.s3db.msg_parser
        record = current.db(table.channel_id == channel_id).select(table.enabled,
                                                                   limitby=(0, 1),
                                                                   ).first()
        if record and record.enabled:
            return True
        else:
            return False

    # -------------------------------------------------------------------------
    @staticmethod
    def parser_enable(id):
        """
            Enable a Parser
            - Connect a Parser to a Channel

            CLI API for shell scripts & to be called by CRUDMethod

            @ToDo: Ensure only 1 Parser is connected to any Channel at a time
        """

        db = current.db
        s3db = current.s3db
        table = s3db.msg_parser
        record = db(table.id == id).select(table.id, # needed for update_record
                                           table.enabled,
                                           table.channel_id,
                                           table.function_name,
                                           limitby=(0, 1),
                                           ).first()
        if not record.enabled:
            # Flag it as enabled
            record.update_record(enabled = True)

        channel_id = record.channel_id
        function_name = record.function_name

        # Do we have an existing Task?
        ttable = db.scheduler_task
        args = '[%s, "%s"]' % (channel_id, function_name)
        query = ((ttable.function_name == "msg_parse") & \
                 (ttable.args == args) & \
                 (ttable.status.belongs(["RUNNING", "QUEUED", "ALLOCATED"])))
        exists = db(query).select(ttable.id,
                                  limitby=(0, 1)).first()
        if exists:
            return "Parser already enabled"
        else:
            current.s3task.schedule_task("msg_parse",
                                         args = [channel_id, function_name],
                                         period = 300,  # seconds
                                         timeout = 300, # seconds
                                         repeats = 0    # unlimited
                                         )
            return "Parser enabled"

    # -------------------------------------------------------------------------
    @staticmethod
    def parser_enable_interactive(r, **attr):
        """
            Enable a Parser
            - Connect a Parser to a Channel

            CRUD method for interactive requests
        """

        result = current.s3db.msg_parser_enable(r.id)
        current.session.confirmation = result
        redirect(URL(f="parser"))

    # -------------------------------------------------------------------------
    @staticmethod
    def parser_disable(id):
        """
            Disable a Parser
            - Disconnect a Parser from a Channel

            CLI API for shell scripts & to be called by CRUDMethod
        """

        db = current.db
        s3db = current.s3db
        table = s3db.msg_parser
        record = db(table.id == id).select(table.id, # needed for update_record
                                           table.enabled,
                                           table.channel_id,
                                           table.function_name,
                                           limitby=(0, 1),
                                           ).first()
        if record.enabled:
            # Flag it as disabled
            record.update_record(enabled = False)

        # Do we have an existing Task?
        ttable = db.scheduler_task
        args = '[%s, "%s"]' % (record.channel_id, record.function_name)
        query = ((ttable.function_name == "msg_parse") & \
                 (ttable.args == args) & \
                 (ttable.status.belongs(["RUNNING", "QUEUED", "ALLOCATED"])))
        exists = db(query).select(ttable.id,
                                  limitby=(0, 1)).first()
        if exists:
            # Disable all
            db(query).update(status="STOPPED")
            return "Parser disabled"
        else:
            return "Parser already disabled"

    # -------------------------------------------------------------------------
    @staticmethod
    def parser_disable_interactive(r, **attr):
        """
            Disable a Parser
            - Disconnect a Parser from a Channel

            CRUD method for interactive requests
        """

        result = current.s3db.msg_parser_disable(r.id)
        current.session.confirmation = result
        redirect(URL(f="parser"))

    # -------------------------------------------------------------------------
    @staticmethod
    def msg_parser_onaccept(form):
        """
            Process the Enabled Flag
        """

        if form.record:
            # Update form
            # process of changed
            if form.record.enabled and not form.vars.enabled:
                current.s3db.msg_parser_disable(form.vars.id)
            elif form.vars.enabled and not form.record.enabled:
                current.s3db.msg_parser_enable(form.vars.id)
        else:
            # Create form
            # Process only if enabled
            if form.vars.enabled:
                current.s3db.msg_parser_enable(form.vars.id)

# =============================================================================
class MsgRSSModel(MsgChannelModel):
    """
        RSS channel
    """

    names = ("msg_rss_channel",
             "msg_rss",
             "msg_rss_link",
             )

    def model(self):

        T = current.T

        define_table = self.define_table
        set_method = self.set_method
        super_link = self.super_link

        # ---------------------------------------------------------------------
        # RSS Settings for an account
        #
        tablename = "msg_rss_channel"
        define_table(tablename,
                     # Instance
                     super_link("channel_id", "msg_channel"),
                     Field("name", length=255, unique=True,
                           label = T("Name"),
                           requires = IS_LENGTH(255),
                           ),
                     Field("description",
                           label = T("Description"),
                           ),
                     Field("enabled", "boolean",
                           default = True,
                           label = T("Enabled?"),
                           represent = s3_yes_no_represent,
                           ),
                     Field("url",
                           label = T("URL"),
                           requires = IS_URL(),
                           ),
                     Field("content_type", "boolean",
                           default = False,
                           label = T("Content-Type Override"),
                           represent = s3_yes_no_represent,
                           # Some feeds have text/html set which feedparser refuses to parse
                           comment = T("Force content-type to application/xml"),
                           ),
                     DateTimeField(label = T("Last Polled"),
                                   writable = False,
                                   ),
                     Field("etag",
                           label = T("ETag"),
                           writable = False
                           ),
                     # Enable this when required in the template
                     # Used by SAMBRO to separate the RSS for cap or cms
                     Field("type",
                           readable = False,
                           writable = False,
                           ),
                     Field("username",
                           label = T("Username"),
                           comment = DIV(_class="tooltip",
                                         _title="%s|%s" % (T("Username"),
                                                           T("Optional username for HTTP Basic Authentication."))),
                           ),
                     Field("password", "password",
                           label = T("Password"),
                           readable = False,
                           widget = S3PasswordWidget.widget,
                           comment = DIV(_class="tooltip",
                                         _title="%s|%s" % (T("Password"),
                                                           T("Optional password for HTTP Basic Authentication."))),
                           ),
                     )

        self.configure(tablename,
                       list_fields = ["name",
                                      "description",
                                      "enabled",
                                      "url",
                                      "date",
                                      "channel_status.status",
                                      ],
                       onaccept = self.msg_channel_onaccept,
                       super_entity = "msg_channel",
                       )

        set_method("msg_rss_channel",
                   method = "enable",
                   action = self.msg_channel_enable_interactive)

        set_method("msg_rss_channel",
                   method = "disable",
                   action = self.msg_channel_disable_interactive)

        set_method("msg_rss_channel",
                   method = "poll",
                   action = self.msg_channel_poll)

        # ---------------------------------------------------------------------
        # RSS Feed Posts
        #
        tablename = "msg_rss"
        define_table(tablename,
                     # Instance
                     super_link("message_id", "msg_message"),
                     self.msg_channel_id(),
                     DateTimeField(default="now",
                                   label = T("Published on"),
                                   ),
                     Field("title",
                           label = T("Title"),
                           ),
                     Field("body", "text",
                           label = T("Content"),
                           ),
                     Field("from_address",
                           label = T("Link"),
                           ),
                     # http://pythonhosted.org/feedparser/reference-feed-author_detail.html
                     Field("author",
                           label = T("Author"),
                           ),
                     # http://pythonhosted.org/feedparser/reference-entry-tags.html
                     Field("tags", "list:string",
                           label = T("Tags"),
                           ),
                     self.gis_location_id(),
                     # Just present for Super Entity
                     Field("inbound", "boolean",
                           default = True,
                           readable = False,
                           writable = False,
                           ),
                     )

        self.configure(tablename,
                       deduplicate = S3Duplicate(primary = ("from_address",),
                                                 ignore_case = False,
                                                 ),
                       list_fields = ["channel_id",
                                      "title",
                                      "from_address",
                                      "date",
                                      "body"
                                      ],
                       super_entity = current.s3db.msg_message,
                       )
        # Components
        self.add_components(tablename,
                            msg_rss_link = "rss_id",
                            )

        rss_represent = S3Represent(lookup = tablename,
                                    fields = ["title", "from_address",],
                                    field_sep = " - ")

        rss_id = FieldTemplate("rss_id", "reference %s" % tablename,
                               label = T("RSS Link"),
                               ondelete = "CASCADE",
                               represent = rss_represent,
                               requires = IS_EMPTY_OR(
                                            IS_ONE_OF(current.db, "msg_rss.id",
                                                      rss_represent,
                                                      )),
                               )

        # ---------------------------------------------------------------------
        # Links for RSS Feed
        #
        tablename = "msg_rss_link"
        define_table(tablename,
                     rss_id(),
                     Field("url",
                           requires = IS_EMPTY_OR(IS_URL()),
                           ),
                     Field("type",
                           ),
                     )

        self.configure(tablename,
                       deduplicate = S3Duplicate(primary = ("rss_id", "url"),
                                                 ),
                       )

        # ---------------------------------------------------------------------
        return None

# =============================================================================
class MsgSMSModel(DataModel):
    """
        SMS: Short Message Service

        These can be received through a number of different gateways
        - MCommons
        - Modem (@ToDo: Restore this)
        - Tropo
        - Twilio
    """

    names = ("msg_sms",)

    def model(self):

        #T = current.T
        user = current.auth.user
        if user and user.organisation_id:
            # SMS Messages need to be tagged to their org so that they can be sent through the correct gateway
            default = user.organisation_id
        else:
            default = None

        # ---------------------------------------------------------------------
        # SMS Messages: InBox & Outbox
        #
        tablename = "msg_sms"
        self.define_table(tablename,
                          # Instance
                          self.super_link("message_id", "msg_message"),
                          self.msg_channel_id(),
                          self.org_organisation_id(default = default),
                          DateTimeField(default="now"),
                          Field("body", "text",
                                # Allow multi-part SMS
                                #length = 160,
                                #label = T("Message"),
                                ),
                          Field("from_address",
                                #label = T("Sender"),
                                ),
                          Field("to_address",
                                #label = T("To"),
                                ),
                          Field("inbound", "boolean",
                                default = False,
                                #represent = lambda direction: \
                                # (direction and [T("In")] or \
                                #                [T("Out")])[0],
                                #label = T("Direction")),
                                ),
                          # Used e.g. for Clickatell
                          Field("remote_id",
                                #label = T("Remote ID"),
                                ),
                          )

        self.configure(tablename,
                       super_entity = "msg_message",
                       )

        # ---------------------------------------------------------------------
        return None

# =============================================================================
class MsgSMSOutboundModel(DataModel):
    """
        SMS: Short Message Service
        - Outbound Channels

        These can be sent through a number of different gateways
        - Modem
        - SMTP
        - Tropo
        - Web API (inc Clickatell, MCommons, mVaayoo)
    """

    names = ("msg_sms_outbound_gateway",
             "msg_sms_modem_channel",
             "msg_sms_smtp_channel",
             "msg_sms_webapi_channel",
             )

    def model(self):

        #T = current.T

        configure = self.configure
        define_table = self.define_table
        settings = current.deployment_settings

        # ---------------------------------------------------------------------
        # SMS Outbound Gateway
        # - select which gateway is in active use for which Organisation/Branch
        #

        country_code = settings.get_L10n_default_country_code()

        tablename = "msg_sms_outbound_gateway"
        define_table(tablename,
                     self.msg_channel_id(
                        requires = IS_ONE_OF(current.db, "msg_channel.channel_id",
                                             S3Represent(lookup="msg_channel"),
                                             instance_types = ("msg_sms_modem_channel",
                                                               "msg_sms_webapi_channel",
                                                               "msg_sms_smtp_channel",
                                                               ),
                                             sort = True,
                                             ),
                                         ),
                     #Field("outgoing_sms_handler", length=32,
                     #      requires = IS_IN_SET(current.msg.GATEWAY_OPTS,
                     #                           zero = None),
                     #      ),
                     # Allow selection of different gateways based on Organisation/Branch
                     self.org_organisation_id(),
                     # @ToDo: Allow selection of different gateways based on destination Location
                     #self.gis_location_id(),
                     Field("default_country_code", "integer",
                           default = country_code,
                           ),
                     )

        # ---------------------------------------------------------------------
        # SMS Modem Channel
        #
        tablename = "msg_sms_modem_channel"
        define_table(tablename,
                     self.super_link("channel_id", "msg_channel"),
                     Field("name"),
                     Field("description"),
                     Field("modem_port"),
                     Field("modem_baud", "integer",
                           default = 115200,
                           ),
                     Field("enabled", "boolean",
                           default = True,
                           ),
                     Field("max_length", "integer",
                           default = 160,
                           ),
                     )

        configure(tablename,
                  super_entity = "msg_channel",
                  )

        # ---------------------------------------------------------------------
        # SMS via SMTP Channel
        #
        tablename = "msg_sms_smtp_channel"
        define_table(tablename,
                     self.super_link("channel_id", "msg_channel"),
                     Field("name"),
                     Field("description"),
                     Field("address", length=64,
                           requires = IS_LENGTH(64),
                           ),
                     Field("subject", length=64,
                           requires = IS_LENGTH(64),
                           ),
                     Field("enabled", "boolean",
                           default = True,
                           ),
                     Field("max_length", "integer",
                           default = 160,
                           ),
                     )

        configure(tablename,
                  super_entity = "msg_channel",
                  )

        # ---------------------------------------------------------------------
        # Settings for Web API services
        #
        # @ToDo: Simplified dropdown of services which prepopulates entries & provides nice prompts for the config options
        #        + Advanced mode for raw access to real fields
        #
        # https://www.twilio.com/docs/api/rest/sending-messages
        #
        tablename = "msg_sms_webapi_channel"
        define_table(tablename,
                     self.super_link("channel_id", "msg_channel"),
                     Field("name"),
                     Field("description"),
                     Field("url",
                           #default = "http://sms1.cardboardfish.com:9001/HTTPSMS?", # Cardboardfish
                           default = "https://api.clickatell.com/http/sendmsg", # Clickatell
                           #default = "https://secure.mcommons.com/api/send_message", # Mobile Commons
                           #default = "https://www.textmagic.com/app/api", # Text Magic
                           #default = "http://bulkmessage-api.dhiraagu.com.mv/jsp/receiveSMS.jsp", # Dhiraagu (Maldives local provider)
                           #default = "https://api.twilio.com/2010-04-01/Accounts/{AccountSid}/Messages", # Twilio (Untested)
                           requires = IS_URL(),
                           ),
                     Field("parameters",
                           #default = "S=H&UN=yourusername&P=yourpassword&SA=Sahana", # Cardboardfish
                           default = "user=yourusername&password=yourpassword&api_id=yourapiid", # Clickatell
                           #default = "campaign_id=yourid", # Mobile Commons
                           #default = "username=yourusername&password=yourpassword&cmd=send&unicode=1", # Text Magic
                           #default = "userid=yourusername&password=yourpassword", # Dhiraagu
                           #default = "From={RegisteredTelNumber}", # Twilio (Untested)
                           ),
                     Field("message_variable", "string",
                           #default = "M", # Cardboardfish
                           default = "text", # Clickatell, Text Magic, Dhiraagu
                           #default = "body", # Mobile Commons
                           #default = "Body", # Twilio (Untested)
                           requires = IS_NOT_EMPTY(),
                           ),
                     Field("to_variable", "string",
                           #default = "DA", # Cardboardfish
                           default = "to", # Clickatell, Dhiraagu
                           #default = "phone_number", # Mobile Commons
                           #default = "phone", # Text Magic
                           #default = "To", # Twilio (Untested)
                           requires = IS_NOT_EMPTY(),
                           ),
                     Field("max_length", "integer",
                           default = 480, # Clickatell concat 3
                           ),
                     # If using HTTP Auth (e.g. Mobile Commons)
                     Field("username"),
                     Field("password", "password",
                           readable = False,
                           widget = S3PasswordWidget.widget,
                           ),
                     Field("enabled", "boolean",
                           default = True,
                           ),
                     )

        configure(tablename,
                  super_entity = "msg_channel",
                  )

        # ---------------------------------------------------------------------
        return None

# =============================================================================
class MsgTropoModel(DataModel):
    """
        Tropo can be used to send & receive SMS & XMPP

        https://www.tropo.com
    """

    names = ("msg_tropo_channel",
             "msg_tropo_scratch",
             )

    def model(self):

        #T = current.T

        define_table = self.define_table
        set_method = self.set_method

        # ---------------------------------------------------------------------
        # Tropo Channels
        #
        tablename = "msg_tropo_channel"
        define_table(tablename,
                     self.super_link("channel_id", "msg_channel"),
                     Field("name"),
                     Field("description"),
                     Field("enabled", "boolean",
                           default = True,
                           #label = T("Enabled?"),
                           represent = s3_yes_no_represent,
                           ),
                     Field("token_messaging"),
                     #Field("token_voice"),
                     )

        self.configure(tablename,
                       super_entity = "msg_channel",
                       )

        set_method("msg_tropo_channel",
                   method = "enable",
                   action = self.msg_channel_enable_interactive)

        set_method("msg_tropo_channel",
                   method = "disable",
                   action = self.msg_channel_disable_interactive)

        set_method("msg_tropo_channel",
                   method = "poll",
                   action = self.msg_channel_poll)

        # ---------------------------------------------------------------------
        # Tropo Scratch pad for outbound messaging
        #
        tablename = "msg_tropo_scratch"
        define_table(tablename,
                     Field("row_id", "integer"),
                     Field("message_id", "integer"),
                     Field("recipient"),
                     Field("message"),
                     Field("network"),
                     meta = False,
                     )

        # ---------------------------------------------------------------------
        return None

# =============================================================================
class MsgTwilioModel(MsgChannelModel):
    """
        Twilio Inbound SMS channel
        - for Outbound, use Web API
    """

    names = ("msg_twilio_channel",
             "msg_twilio_sid",
             )

    def model(self):

        #T = current.T

        define_table = self.define_table
        set_method = self.set_method

        # ---------------------------------------------------------------------
        # Twilio Channels
        #
        tablename = "msg_twilio_channel"
        define_table(tablename,
                     # Instance
                     self.super_link("channel_id", "msg_channel"),
                     Field("name"),
                     Field("description"),
                     Field("enabled", "boolean",
                           default = True,
                           #label = T("Enabled?"),
                           represent = s3_yes_no_represent,
                           ),
                     Field("account_name", length=255, unique=True),
                     Field("url",
                           default = \
                               "https://api.twilio.com/2010-04-01/Accounts"
                           ),
                     Field("account_sid", length=64,
                           requires = [IS_NOT_EMPTY(),
                                       IS_LENGTH(64),
                                       ],
                           ),
                     Field("auth_token", "password", length=64,
                           readable = False,
                           requires = [IS_NOT_EMPTY(),
                                       IS_LENGTH(64),
                                       ],
                           widget = S3PasswordWidget.widget,
                           ),
                     )

        self.configure(tablename,
                       onaccept = self.msg_channel_onaccept,
                       super_entity = "msg_channel",
                       )

        set_method("msg_twilio_channel",
                   method = "enable",
                   action = self.msg_channel_enable_interactive)

        set_method("msg_twilio_channel",
                   method = "disable",
                   action = self.msg_channel_disable_interactive)

        set_method("msg_twilio_channel",
                   method = "poll",
                   action = self.msg_channel_poll)

        # ---------------------------------------------------------------------
        # Twilio Message extensions
        # - store message sid to know which ones we've already downloaded
        #
        tablename = "msg_twilio_sid"
        define_table(tablename,
                     # Component not Instance
                     self.msg_message_id(ondelete = "CASCADE"),
                     Field("sid"),
                     )

        # ---------------------------------------------------------------------
        return None

# =============================================================================
class MsgXFormsModel(DataModel):
    """
        XForms are used by the ODK Collect mobile client

        http://eden.sahanafoundation.org/wiki/BluePrint/Mobile#Android
    """

    names = ("msg_xforms_store",)

    def model(self):

        #T = current.T

        # ---------------------------------------------------------------------
        # SMS store for persistence and scratch pad for combining incoming xform chunks
        tablename = "msg_xforms_store"
        self.define_table(tablename,
                          Field("sender", length=20),
                          Field("fileno", "integer"),
                          Field("totalno", "integer"),
                          Field("partno", "integer"),
                          Field("message", length=160),
                          meta = False,
                          )

        # ---------------------------------------------------------------------
        return None

# =============================================================================
class MsgBaseStationModel(DataModel):
    """
        Base Stations (Cell Towers) are a type of Site

        @ToDo: Calculate Coverage from Antenna Height, Radio Power and Terrain
               - see RadioMobile
    """

    names = ("msg_basestation",)

    def model(self):

        T = current.T

        # ---------------------------------------------------------------------
        # Base Stations (Cell Towers)
        #

        if current.deployment_settings.get_msg_basestation_code_unique():
            db = current.db
            code_requires = IS_EMPTY_OR([IS_LENGTH(10),
                                         IS_NOT_IN_DB(db, "msg_basestation.code")
                                         ])
        else:
            code_requires = IS_LENGTH(10)

        tablename = "msg_basestation"
        self.define_table(tablename,
                          self.super_link("site_id", "org_site"),
                          Field("name", notnull=True,
                                length=64, # Mayon Compatibility
                                label = T("Name"),
                                requires = [IS_NOT_EMPTY(),
                                            IS_LENGTH(64),
                                            ],
                                ),
                          Field("code", length=10, # Mayon compatibility
                                label = T("Code"),
                                requires = code_requires,
                                ),
                          self.org_organisation_id(
                                 label = T("Operator"),
                                 requires = self.org_organisation_requires(required=True,
                                                                           updateable=True),
                                 #widget=S3OrganisationAutocompleteWidget(default_from_profile=True),
                                 ),
                          self.gis_location_id(),
                          CommentsField(),
                          )

        # CRUD strings
        current.response.s3.crud_strings[tablename] = Storage(
            label_create=T("Create Base Station"),
            title_display=T("Base Station Details"),
            title_list=T("Base Stations"),
            title_update=T("Edit Base Station"),
            title_upload=T("Import Base Stations"),
            title_map=T("Map of Base Stations"),
            label_list_button=T("List Base Stations"),
            label_delete_button=T("Delete Base Station"),
            msg_record_created=T("Base Station added"),
            msg_record_modified=T("Base Station updated"),
            msg_record_deleted=T("Base Station deleted"),
            msg_list_empty=T("No Base Stations currently registered"))

        self.configure(tablename,
                       deduplicate = S3Duplicate(),
                       super_entity = "org_site",
                       )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return None

# END =========================================================================
