"""
    Anonymizer rules for DRKCM

    License: MIT
"""

from core import anonymous_address, obscure_dob

# =============================================================================
def drk_person_anonymize():
    """ Rules to anonymize a case file """

    ANONYMOUS = "-"

    # Helper to produce an anonymous ID (pe_label)
    anonymous_id = lambda record_id, f, v: "NN%06d" % int(record_id)

    # General rule for attachments
    documents = ("doc_document", {"key": "doc_id",
                                  "match": "doc_id",
                                  "fields": {"name": ("set", ANONYMOUS),
                                             "file": "remove",
                                             "comments": "remove",
                                             },
                                  "delete": True,
                                  })

    # Cascade rule for case activities
    activity_details = [("dvr_case_activity_update", {"key": "case_activity_id",
                                                      "match": "id",
                                                      "fields": {"comments": ("set", ANONYMOUS),
                                                                 },
                                                      }),
                        ]

    # Cascade rule for response actions
    response_details = [("dvr_response_action_theme", {"key": "action_id",
                                                       "match": "id",
                                                       "fields": {"comments": ("set", ANONYMOUS),
                                                                  },
                                                       }),
                        ]

    rules = [# Remove identity of beneficiary
             {"name": "default",
              "title": "Names, IDs, Reference Numbers, Contact Information, Addresses",
              "fields": {"first_name": ("set", ANONYMOUS),
                         "last_name": ("set", ANONYMOUS),
                         "pe_label": anonymous_id,
                         "date_of_birth": obscure_dob,
                         "comments": "remove",
                         },
              "cascade": [("dvr_case", {"key": "person_id",
                                        "match": "id",
                                        "fields": {"comments": "remove",
                                                   },
                                        }),
                          ("dvr_case_details", {"key": "person_id",
                                                "match": "id",
                                                "fields": {"lodging": "remove",
                                                           },
                                                }),
                          ("pr_contact", {"key": "pe_id",
                                          "match": "pe_id",
                                          "fields": {"contact_description": "remove",
                                                     "value": ("set", ""),
                                                     "comments": "remove",
                                                     },
                                          "delete": True,
                                          }),
                          ("pr_contact_emergency", {"key": "pe_id",
                                                    "match": "pe_id",
                                                    "fields": {"name": ("set", ANONYMOUS),
                                                               "relationship": "remove",
                                                               "phone": "remove",
                                                               "comments": "remove",
                                                               },
                                                    "delete": True,
                                                    }),
                          ("pr_address", {"key": "pe_id",
                                          "match": "pe_id",
                                          "fields": {"location_id": anonymous_address,
                                                     "comments": "remove",
                                                     },
                                          }),
                          ("pr_person_details", {"key": "person_id",
                                                 "match": "id",
                                                 "fields": {"education": "remove",
                                                            "occupation": "remove",
                                                            },
                                                 }),
                          ("pr_person_tag", {"key": "person_id",
                                             "match": "id",
                                             "fields": {"value": ("set", ANONYMOUS),
                                                        },
                                             "delete": True,
                                             }),
                          ("dvr_residence_status", {"key": "person_id",
                                                    "match": "id",
                                                    "fields": {"reference": ("set", ANONYMOUS),
                                                               "comments": "remove",
                                                               },
                                                    }),
                          ("dvr_service_contact", {"key": "person_id",
                                                   "match": "id",
                                                   "fields": {"reference": "remove",
                                                              "contact": "remove",
                                                              "phone": "remove",
                                                              "email": "remove",
                                                              "comments": "remove",
                                                              },
                                                   }),
                          ],
              },

             # Remove activity details, appointments and notes
             {"name": "activities",
              "title": "Activity Details, Appointments, Notes",
              "cascade": [("dvr_case_language", {"key": "person_id",
                                                 "match": "id",
                                                 "fields": {"comments": "remove",
                                                            },
                                                 }),
                          ("dvr_case_appointment", {"key": "person_id",
                                                    "match": "id",
                                                    "fields": {"comments": "remove",
                                                               },
                                                    }),
                          ("dvr_case_activity", {"key": "person_id",
                                                 "match": "id",
                                                 "fields": {"subject": ("set", ANONYMOUS),
                                                            "need_details": "remove",
                                                            "outcome": "remove",
                                                            "comments": "remove",
                                                            },
                                                 "cascade": activity_details,
                                                 }),
                          ("dvr_response_action", {"key": "person_id",
                                                   "match": "id",
                                                   "fields": {"comments": "remove",
                                                              },
                                                   "cascade": response_details,
                                                   }),
                          ("dvr_vulnerability", {"key": "person_id",
                                                 "match": "id",
                                                 "fields": {"comments": "remove",
                                                            "description": ("set", ANONYMOUS),
                                                            },
                                                 }),
                          ("dvr_note", {"key": "person_id",
                                        "match": "id",
                                        "fields": {"note": "remove",
                                                   },
                                        "delete": True,
                                        }),
                          ],
              },

             # Remove photos and attachments
             {"name": "documents",
              "title": "Photos and Documents",
              "cascade": [("dvr_case", {"key": "person_id",
                                        "match": "id",
                                        "cascade": [documents,
                                                    ],
                                        }),
                          ("dvr_case_activity", {"key": "person_id",
                                                 "match": "id",
                                                 "cascade": [documents,
                                                             ],
                                                 }),
                          ("pr_image", {"key": "pe_id",
                                        "match": "pe_id",
                                        "fields": {"image": "remove",
                                                   "url": "remove",
                                                   "description": "remove",
                                                   },
                                        "delete": True,
                                        }),
                          ],
              },

              # TODO family membership

             ]

    return rules

# END =========================================================================
