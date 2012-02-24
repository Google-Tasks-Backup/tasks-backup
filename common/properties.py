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

"""Custom model properties for the App Engine datastore."""

__author__ = "dwightguth@google.com (Dwight Guth)"

import datetime
import pickle

from google.appengine.ext import db


class TimeDeltaProperty(db.Property):
  """A datastore property for a datetime.timedelta object."""
  data_type = datetime.timedelta

  def get_value_for_datastore(self, model_instance):
    dt = db.Property.get_value_for_datastore(self, model_instance)
    if not dt:
      return None
    return [dt.days, dt.seconds, dt.microseconds]

  def make_value_from_datastore(self, value):
    if value is None:
      return None
    days = value[0]
    seconds = value[1]
    microseconds = value[2]
    return datetime.timedelta(days, seconds, microseconds)

  def validate(self, value):
    if value and not isinstance(value, datetime.timedelta):
      raise BadValueError("Property %s must be convertible to a timedelta "
                          "instance (%s)" % (self.name, value))
    return db.Property.validate(self, value)

  def empty(self, value):
    return not value


class DictProperty(db.Property):
  """A datastore property for a dict object."""
  data_type = dict

  def get_value_for_datastore(self, model_instance):
    d = db.Property.get_value_for_datastore(self, model_instance)
    if not d:
      return None
    return db.Blob(pickle.dumps(d))

  def make_value_from_datastore(self, value):
    if value is None:
      return None
    return pickle.loads(value)

  def validate(self, value):
    if value and not isinstance(value, dict):
      raise BadValueError("Property %s must be convertible to a dict "
                          "instance (%s)" % (self.name, value))
    return db.Property.validate(self, value)

  def empty(self, value):
    return not value
