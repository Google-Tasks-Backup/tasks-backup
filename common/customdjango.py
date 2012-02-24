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

"""Contains custom Django template filters."""

from django import template
from django.utils import html
from django.utils import safestring
from google.appengine.ext import webapp

import logging

register = webapp.template.create_template_register()


@register.filter
def replace(str_to_replace, args):
  """Performs arbitrary string transformations on template fields.

  If you need to perform a transformation which contains a control character
  or a set of quotes, you will need to create a custom filter below, because
  Django does not support escape characters in their filter parameters.

  Args:
    str_to_replace: the string to be transformed.
    args: "/old/new" replaces old with new.

  Returns:
    The string with the specified replacement.
  """
  if str_to_replace is None:
    return None
  search_str = args.split(args[0])[1]
  replace_str = args.split(args[0])[2]
  return str_to_replace.replace(search_str, replace_str)


@register.filter
def replacenewline(str_to_replace):
  """Escapes newline characters with backslashes.

  Args:
    str_to_replace: the string to be escaped.

  Returns:
    The string with newlines escaped.
  """
  if str_to_replace is None:
    return None
  return str_to_replace.replace(
      "\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")


@register.filter
def replacenewlinebr(str_to_replace, autoescape=None):
  """Turns newline characters into <br/> tags.

  Args:
    str_to_replace: the string to be converted.
    autoescape: True if autoescape is enabled, False otherwise.

  Returns:
    The string with newlines converted to <br/> tags.
  """
  if str_to_replace is None:
    return None
  if autoescape:
    esc = html.conditional_escape
  else:
    esc = lambda x: x
  escaped_str = esc(str_to_replace)
  return safestring.mark_safe(escaped_str.replace("\n", "<br/>"))

replacenewlinebr.needs_autoescape = True


@register.filter
def replacecsv(str_to_replace):
  """Performs string transformations for CSV files.

  Escapes quotes by doubling them and converts unix linebreaks to
  Windows linebreaks.

  Args:
    str_to_replace: the string to be transformed.

  Returns:
    The string escaped for Windows CSV.
  """
  if str_to_replace is None:
    return None
  return str_to_replace.replace("\"", "\"\"").replace("\n", "\r\n")


@register.tag
def recurse(parser, token):
  """Generates a recursive tree structure from a python iterable.

  Usage: {% recurse item <PARAMS> %}
           {% if haschildren %}
             {% children %}
           {% endif %}
         {% endrecurse %}
    item: the name of the variable to create for each loop iteration.
    Parameters:
      root: the list of root-level items to loop through.
      children: the name of the attribute which returns the children of each
        item.
      parent: the name of an attribute which returns None if the item is a root
        item.
      sort: the name of the attribute which returns the sort order of each
        item.

  This tag sets the haschildren variable to a boolean of whether or not the
  current loop iteration has children.  This value can be used or not as
  desired.  In order to render the children of the specified node, it is
  necessary to place a children tag somewhere inside the body of the recurse
  tag.  A children node outside of a recurse tag is invalid.

  Args:
    parser: the django object for parsing template files
    token: the django object containing the template tag data

  Returns:
    A RecurseNode with its arguments populated from token.
  """
  args = token.split_contents()
  item_name = args[1]
  kwargs = {}
  for arg in args[2:]:
    arg_parts = arg.split(":")
    key = arg_parts[0]
    value = ":".join(arg_parts[1:])
    if value[0] == '"' and value[-1] == '"':
      kwargs[key] = value[1:-1]
    else:
      kwargs[key] = value

  nodes = parser.parse(("endrecurse",))
  parser.delete_first_token()
  return RecurseNode(item_name, kwargs, nodes)


class RecurseNode(template.Node):
  """Represents a django template node for a recurse tag."""

  def __init__(self, item_name, kwargs, nodes):
    self.item_name = item_name
    self.root = template.Variable(kwargs["root"])
    self.parent = kwargs["parent"]
    self.children = kwargs["children"]
    self.sort = kwargs["sort"]
    self.nodes = nodes
    for children_node in nodes.get_nodes_by_type(ChildrenNode):
      children_node.recurse_node = self

  def cmp(self, x, y):
    """Compares two objects based on the specified sort parameter.

    Args:
      x: first object to compare.
      y: second object to compare.

    Returns:
      the result of calling cmp on x and y's sort values.
    """
    x_sort = getattr(x, self.sort)
    y_sort = getattr(y, self.sort)
    return cmp(x_sort, y_sort)

  def render(self, context):
    """Renders the current node in the specified context.

    If this method is called from a ChildrenNode then it will push a new
    level of context.

    Args:
      context: the Django context dictionary.

    Returns:
      A string of rendered template text.
    """
    if "children" in context:
      item_list = sorted(context["children"], self.cmp)
      context.push()
    else:
      item_list = sorted(self.root.resolve(context), self.cmp)
      item_list = [item for item in item_list
                   if self.getParent(item) is None]

    return self.RenderList(context, item_list)

  def getParent(self, item):
    try:
      return getattr(item, self.parent)
    except BaseException, e:
      logging.warning(e)
      return None

  def RenderList(self, context, item_list):
    """Renders a single recursion level in the specified context.

    This method pushes a new level of context with the variables specific
    to each iteration of the loop.

    Args:
      context: the Django context dictionary.
      item_list: an iterable representing the sorted data for this level of
        recursion.

    Returns:
      A string of rendered template text.
    """
    result = ""
    for item in item_list:
      context.push()
      context[self.item_name] = item
      try:
        children_items = list(getattr(item, self.children))
        context["haschildren"] = bool(children_items)
      except template.VariableDoesNotExist:
        children_items = None
        context["haschildren"] = False
      context["children"] = children_items
      result += self.RenderItem(context)
      context.pop()
    return result

  def RenderItem(self, context):
    """Renders a single loop iteration in the specified context.

    This method simply calls render on each node that is a child of the
    RecurseNode.

    Args:
      context: the Django context dictionary.

    Returns:
      A string of rendered template text.
    """
    result = ""
    for node in self.nodes:
      result += node.render(context)
    return result


@register.tag
def children(parser, token):
  """Renders the child nodes of a recurse tag.

  For more information on the children tag see the docstring for the recurse
  tag.

  Args:
    parser: the django object for parsing template files
    token: the django object containing the template tag data

  Returns:
    a new ChildrenNode.
  """
  return ChildrenNode()


class ChildrenNode(template.Node):
  """Represents a django template node for a children tag."""

  def render(self, context):
    """Recurses a recurse tag one level using the specified context.

    This method implicitly causes a context push and explicitly pops it after
    the node has been rendered.

    Args:
      context: the Django context dictionary.

    Returns:
      A string of rendered template text.
    """
    result = self.recurse_node.render(context)
    context.pop()
    return result
