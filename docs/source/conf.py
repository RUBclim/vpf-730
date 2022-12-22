project = 'vpf-730'
copyright = '2022, Jonas Kittner'
author = 'Jonas Kittner'
release = '0.7.1'

extensions = [
    'myst_parser',
    'sphinx.ext.autodoc',
    'sphinx.ext.intersphinx',
    'sphinx.ext.viewcode',
    'sphinx_autodoc_typehints',
    'sphinx_copybutton',
    'sphinxarg.ext',
]
autodoc_typehints = 'both'
typehints_fully_qualified = True

intersphinx_mapping = {'python': ('https://docs.python.org/3', None)}

html_theme = 'furo'

source_suffix = {
    '.rst': 'restructuredtext',
    '.txt': 'markdown',
    '.md': 'markdown',
}
