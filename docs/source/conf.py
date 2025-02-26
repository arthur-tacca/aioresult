#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Documentation build configuration file, created by
# sphinx-quickstart on Sat Jan 21 19:11:14 2017.
#
# This file is execfile()d with the current directory set to its
# containing dir.
#
# Note that not all possible configuration values are present in this
# autogenerated file.
#
# All configuration values have a default; values that are commented out
# serve to show the default.

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
import os
import sys
# So autodoc can import our package
sys.path.insert(0, os.path.abspath('../..'))

# Warn about all references to unknown targets
nitpicky = True
# Except for these ones, which we expect to point to unknown targets:
nitpick_ignore = [
    ("py:obj", "aioresult._src.ResultT"),
    ("py:obj", "aioresult._src.ResultT_co"),
    ("py:class", "ResultT"),
    ("py:class", "ResultT_co"),
    ("py:class", "ResultBaseT"),
    ("py:class", "*ArgsT"),
]
autodoc_inherit_docstrings = False
autodoc_typehints = "none"
default_role = "obj"

# -- General configuration ------------------------------------------------

# If your documentation needs a minimal Sphinx version, state it here.
#
# needs_sphinx = '1.0'

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.intersphinx',
    'sphinxcontrib_trio',
]

intersphinx_mapping = {
    "python": ('https://docs.python.org/3', None),
    "trio": ('https://trio.readthedocs.io/en/stable', None),
    "anyio": ('https://anyio.readthedocs.io/en/stable', None)
}

autodoc_member_order = "bysource"

# Add any paths that contain templates here, relative to this directory.
templates_path = []

# The master toctree document.
master_doc = 'index'

# General information about the project.
project = 'aioresult'
copyright = 'Arthur Tacca'
author = 'Arthur Tacca'

# The version info for the project you're documenting, acts as replacement for
# |version| and |release|, also used in various other places throughout the
# built documents.
#
# The short X.Y version.
import aioresult
version = aioresult.__version__
# The full version, including alpha/beta/rc tags.
release = version

# The language for content autogenerated by Sphinx. Refer to documentation
# for a list of supported languages.
#
# This is also used if you do content translation via gettext catalogs.
# Usually you set "language" from the command line for these cases.
language = "en"

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This patterns also effect to html_static_path and html_extra_path
exclude_patterns = []

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = 'sphinx'

# The default language for :: blocks
highlight_language = 'python3'


# -- Options for HTML output ----------------------------------------------

# The theme to use for HTML and HTML Help pages.
html_theme = 'sphinx_rtd_theme'

# Theme options are theme-specific and customize the look and feel of a theme
# further.  For a list of options available for each theme, see the
# documentation.
#
html_theme_options = {
    "navigation_depth": 3
}

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']

# Custom style sheet to lay out function parameters better on mobile. See:
# https://stackoverflow.com/questions/79114648/
html_css_files = [
    'custom.css',
]


# Print the type parameters for generic functions and classes. This is a workaround for lack of
# support in autodoc that requires listing every specific class and function.
# https://github.com/sphinx-doc/sphinx/issues/10568#issuecomment-2413039360
type_parameters = {
    "aioresult.Future": "ResultT",
    "aioresult.ResultBase": "ResultT_co",
    "aioresult.ResultCapture": "ResultT_co",
    # Probably too confusing to include type parameters in function signatures
    # "aioresult.ResultCapture.start_soon": "ResultT, *ArgsT",
    # "aioresult.ResultCapture.capture_start_and_done_results": "ResultT",
    # "aioresult.wait_any": "ResultBaseT: ResultBase",
    # "aioresult.results_to_channel": "ResultBaseT: ResultBase",
}

def process_signature(app, what, name, obj, options, signature, return_annotation):
    if name in type_parameters:
        signature = "[" + type_parameters[name] + "]" + (signature or "")
    return signature, return_annotation

def setup(app):
    app.connect("autodoc-process-signature", process_signature)


# Allow using `:return TypeName: Description` with type name on same line of output
# https://github.com/orgs/sphinx-doc/discussions/13125#discussioncomment-11219198
from sphinx.domains.python import PyObject, PyGroupedField
for i, f in enumerate(PyObject.doc_field_types):
    if f.name == "returnvalue":
        PyObject.doc_field_types[i] = PyGroupedField(
            f.name, label=f.label, names=f.names, rolename="class", can_collapse=True
        )


# Also allow documenting type parameters.
PyObject.doc_field_types.append(PyGroupedField(
    "typeparam", label="Type Parameters", names=("typeparam",), rolename="class", can_collapse=True
))
