from __future__ import absolute_import
import itertools

from .baseline_handlers import routes as baseline_routes
from .classify_handlers import routes as classify_routes
from .composition_handlers import routes as composition_routes
from .dataset_handlers import routes as dataset_routes
from .generic import routes as generic_routes
from .import_handlers import routes as import_routes
from .model_handlers import routes as generic_model_routes
from .page_handlers import routes as page_routes
from .peak_handlers import routes as peak_routes
from .plotting_handlers import routes as plotting_routes
from .predict_handlers import routes as predict_routes
from .search_handlers import routes as search_routes

all_routes = list(itertools.chain(
    page_routes, dataset_routes, baseline_routes, search_routes,
    generic_routes, plotting_routes, peak_routes, composition_routes,
    predict_routes, import_routes, generic_model_routes, classify_routes))
