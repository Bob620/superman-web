from __future__ import absolute_import
import itertools

from .baseline_handlers import routes as baseline_routes
from .dataset_handlers import routes as dataset_routes
from .explorer_handlers import routes as explorer_routes
from .handlers import routes as generic_routes
from .page_handlers import routes as page_routes
from .peak_handlers import routes as peak_routes
from .search_handlers import routes as search_routes
from .composition_handlers import routes as composition_routes

all_routes = list(itertools.chain(
	page_routes, dataset_routes, baseline_routes, search_routes, generic_routes,
	explorer_routes, peak_routes, composition_routes))
