#!/usr/bin/python2.5
#
# Copyright 2011 Google Inc.  All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Generic Uploader for Apiary API data.

This module contains code to take an arbitrary set of datastore objects and
upload them to an Apiary API
"""

__author__ = "dwightguth@google.com (Dwight Guth)"

from google.appengine.ext import db

PREVIOUS_ARGUMENT = object()


class Uploader(object):
  """Uploads data to an Apiary API."""

  _RESERVED_WORDS = ("parent_")

  def __init__(self, insert_method, **args):
    """Creates a new Uploader object.

    If you want each item uploaded to have a query parameter set to the value
    of the id of the previous item uploaded, please specify this parameter
    in args by setting its value to apiupload.PREVIOUS_ARGUMENT.

    Args:
      insert_method: the method which is called to invoke the API.
      args: keyword parameters to pass to the method that invokes the API.
    """
    self.insert_method = insert_method
    self.args = args
    self.previous = None

  def Upload(self, entities):
    """Uploads the provided entities to the Apiary API.

    Args:
      entities: a Python list of model instances to upload.

    Returns:
      The list of API keys assigned by the API to the entities uploaded
    """
    keys = []

    for entity in entities:
      ret_id = self.UploadEntity(entity)
      self.previous = ret_id
      entity.id = ret_id
      entity.put()
      keys.append(ret_id)
    return keys

  def UploadEntity(self, entity):
    """Uploads the provided entity to the Apiary API.

    Args:
      entity: a model instance to upload.

    Returns:
      The API key assigned by the API to the entity uploaded
    """
    args = self.args.copy()
    for key, value in args.items():
      # for another example of this sort of design pattern, see
      # google.appengine.ext.db.SelfReferenceProperty.
      if value is PREVIOUS_ARGUMENT:
        # user has specified that this parameter needs to be generated on the
        # fly by populating it with the previous ID uploaded.  We therefore need
        # to fill in this value on each API request.
        if self.previous is None:
          del args[key]
        else:
          args[key] = self.previous
    args["body"] = self.BuildBody(entity)
    api_data = self.insert_method(**args).execute()
    return api_data["id"]

  def BuildBody(self, entity):
    """Computes the POST body of an insert invocation.

    Args:
      entity: the model instance to parametrize.

    Raises:
      ValueError: if an entity property cannot be converted to POST data.

    Returns:
      A dict of POST data for the API request.
    """
    result = {}

    for prop_name, prop in entity.properties().items():
      data = getattr(entity, prop_name)
      api_name = Uploader.ModelToApi(prop_name)
      if data is None:
        continue
      if (isinstance(prop, db.StringProperty) or
          isinstance(prop, db.TextProperty) or
          isinstance(prop, db.BooleanProperty) or
          isinstance(prop, db.IntegerProperty) or
          isinstance(prop, db.FloatProperty)):
        result[api_name] = data
      elif isinstance(prop, db.LinkProperty):
        result[api_name] = str(data)
      elif isinstance(prop, db.DateProperty):
        # The elif clause for DateProperty must come ABOVE the elif clause for
        # DateTimeProperty because DateProperty is a subclass of
        # DateTimeProperty. If we ever add a TimeProperty we will need it
        # to be above DateTimeProperty as well.
        result[api_name] = data.strftime("%Y-%m-%dT%H:%M:%S.000Z")
      elif isinstance(prop, db.DateTimeProperty):
        result[api_name] = data.strftime("%Y-%m-%dT%H:%M:%S.")
        result[api_name] += str(data.microsecond / 1000)
        result[api_name] += "Z"
      elif isinstance(prop, db.ReferenceProperty):
        result[api_name] = data.id
      elif isinstance(prop, db.ListProperty):
        prop_value = getattr(entity, prop_name)
        result[api_name] = [key.name() for key in prop_value]
      else:
        raise ValueError("Could not convert property %s to POST data.\n"
                         "Value: %s" % (prop_name, data))
    return result

  @staticmethod
  def ModelToApi(prop_name):
    """Converts a Model property name to an API property name.

    Args:
      prop_name: the name of the property in the datastore model.

    Returns:
      The name of the same prooperty in the Apiary API.
    """
    if prop_name in Uploader._RESERVED_WORDS:
      return prop_name[:-1]
    return prop_name
