from __future__ import absolute_import
import logging
import numpy as np
from itertools import repeat
from sklearn.cross_decomposition import PLSRegression
from sklearn.externals.joblib.numpy_pickle import (
    load as load_pickle, dump as dump_pickle)
from sklearn.metrics import r2_score, mean_squared_error
from sklearn.model_selection import GridSearchCV, KFold, GroupKFold
from sklearn.linear_model import LassoLars, LassoLarsCV, Lars


class RegressionModel(object):
  def __init__(self, k, ds_kind, wave):
    self.parameter = k
    self.ds_kind = ds_kind
    self.wave = wave
    self.var_names = []
    self.var_keys = []

  @staticmethod
  def load(fh):
    return load_pickle(fh)

  def save(self, fname):
    dump_pickle(self, fname, compress=3)

  def predict(self, X, variables):
    preds, stats = {}, []
    for key, p in self._predict(X, variables):
      y, name = variables[key]
      preds[key] = p
      if y is not None and np.isfinite(y).all():
        stats.append(dict(r2=r2_score(y, p),
                          rmse=np.sqrt(mean_squared_error(y, p)),
                          name=name, key=key))
      else:
        stats.append(dict(name=name, key=key, r2=np.nan, rmse=np.nan))
    stats.sort(key=lambda s: s['key'])
    return preds, stats

  def info_html(self):
    return '%s &mdash; %s' % (self, self.ds_kind)

  def __str__(self):
    return '%s(%g)' % (self.__class__.__name__, self.parameter)


class _UnivariateRegression(RegressionModel):
  def train(self, X, variables):
    self.models = {}
    for key in variables:
      clf = self._construct()
      y, name = variables[key]
      self.models[key] = clf.fit(X, y)
      self.var_keys.append(key)
      self.var_names.append(name)

  def _predict(self, X, variables):
    for key in variables:
      if key not in self.models:
        logging.warning('No trained model for variable: %r', key)
        continue
      clf = self.models[key]
      yield key, clf.predict(X)

  @classmethod
  def _run_cv(cls, X, variables, grid, num_folds, labels=None):
    if labels is None:
      cv = KFold(n_splits=num_folds)
    else:
      cv = GroupKFold(n_splits=num_folds)

    for key in sorted(variables):
      y, name = variables[key]
      model = GridSearchCV(cls._cv_construct(), grid, cv=cv,
                           scoring='neg_mean_squared_error',
                           return_train_score=False, n_jobs=1)
      model.fit(X, y=y, groups=labels)
      mse_mean = -model.cv_results_['mean_test_score']
      mse_stdv = model.cv_results_['std_test_score']
      yield name, mse_mean, mse_stdv


class _MultivariateRegression(RegressionModel):
  def train(self, X, variables):
    self.clf = self._construct()
    self.var_keys = variables.keys()
    y_cols = []
    for key in self.var_keys:
      y, name = variables[key]
      y_cols.append(y)
      self.var_names.append(name)
    self.clf.fit(X, np.column_stack(y_cols))

  def _predict(self, X, variables):
    P = self.clf.predict(X)
    for i, key in enumerate(self.var_keys):
      if key not in variables:
        logging.warning('No input variable for predicted: %r', key)
        continue
      yield key, P[:,i]

  @classmethod
  def _run_cv(cls, X, variables, grid, num_folds, labels=None):
    if labels is None:
      cv = KFold(n_splits=num_folds)
    else:
      cv = GroupKFold(n_splits=num_folds)

    pls = GridSearchCV(cls._cv_construct(), grid, cv=cv,
                       scoring='neg_mean_squared_error',
                       return_train_score=False, n_jobs=1)
    Y, names = zip(*variables.values())
    pls.fit(X, y=np.column_stack(Y), groups=labels)
    mse_mean = -pls.cv_results_['mean_test_score']
    mse_stdv = pls.cv_results_['std_test_score']
    return '/'.join(names), mse_mean, mse_stdv


class _PLS(object):
  def _construct(self):
    return PLSRegression(scale=False, n_components=self.parameter)

  @classmethod
  def _cv_construct(cls):
    return PLSRegression(scale=False)


class _Lasso(object):
  def _construct(self):
    return LassoLars(alpha=self.parameter, fit_intercept=False)


class _Lars(object):
  def _construct(self):
    return Lars(n_nonzero_coefs=self.parameter, fit_intercept=False)

  @classmethod
  def _cv_construct(cls):
    return Lars(fit_intercept=False, fit_path=False)


class _LassoOrLars1(_UnivariateRegression):
  def train(self, X, variables):
    _UnivariateRegression.train(self, X, variables)
    for clf in self.models.values():
      # XXX: work around a bug in sklearn
      # see https://github.com/scikit-learn/scikit-learn/pull/8160
      clf.coef_ = np.array(clf.coef_)

  def coefficients(self):
    all_bands = []
    all_coefs = []
    for key in self.var_keys:
      clf = self.models[key]
      all_bands.append(self.wave[clf.active_])
      all_coefs.append(clf.coef_[clf.active_])
    return all_bands, all_coefs


class _LassoOrLars2(_MultivariateRegression):
  def train(self, X, variables):
    _MultivariateRegression.train(self, X, variables)
    for clf in self.models.values():
      # XXX: work around a bug in sklearn
      # see https://github.com/scikit-learn/scikit-learn/pull/8160
      clf.coef_ = np.array(clf.coef_)

  def coefficients(self):
    coef = self.clf.coef_
    active = self.clf.active_
    if coef.ndim == 1:
      all_bands = [self.wave[active]]
      all_coefs = [coef[active]]
    else:
      all_bands = [self.wave[idx] for idx in active]
      all_coefs = [cc[idx] for idx,cc in zip(active, coef)]
    return all_bands, all_coefs


class PLS1(_UnivariateRegression, _PLS):
  def coefficients(self):
    all_bands = repeat(self.wave)
    all_coefs = [self.models[key].coef_.ravel() for key in self.var_keys]
    return all_bands, all_coefs

  @classmethod
  def cross_validate(cls, X, variables, comps=None, num_folds=5, labels=None):
    grid = dict(n_components=comps)
    for name, mse_mean, mse_stdv in cls._run_cv(X, variables, grid, num_folds,
                                                labels=labels):
      yield name, comps, mse_mean, mse_stdv


class PLS2(_MultivariateRegression, _PLS):
  def coefficients(self):
    return repeat(self.wave), self.clf.coef_.T

  @classmethod
  def cross_validate(cls, X, variables, comps=None, num_folds=5, labels=None):
    grid = dict(n_components=comps)
    name, mse_mean, mse_stdv = cls._run_cv(X, variables, grid, num_folds,
                                           labels=labels)
    yield name, comps, mse_mean, mse_stdv


class Lars1(_LassoOrLars1, _Lars):
  @classmethod
  def cross_validate(cls, X, variables, chans=None, num_folds=5, labels=None):
    grid = dict(n_nonzero_coefs=chans)
    for name, mse_mean, mse_stdv in cls._run_cv(X, variables, grid, num_folds,
                                                labels=labels):
      yield name, chans, mse_mean, mse_stdv


class Lars2(_LassoOrLars2, _Lars):
  @classmethod
  def cross_validate(cls, X, variables, chans=None, num_folds=5, labels=None):
    grid = dict(n_nonzero_coefs=chans)
    name, mse_mean, mse_stdv = cls._run_cv(X, variables, grid, num_folds,
                                           labels=labels)
    yield name, chans, mse_mean, mse_stdv


class Lasso1(_LassoOrLars1, _Lasso):
  @classmethod
  def cross_validate(cls, X, variables, num_folds=5, labels=None):
    if labels is None:
      cv = KFold(n_splits=num_folds)
    else:
      cv = HackAroundSklearnCV(n_splits=num_folds, groups=labels)

    for key in sorted(variables):
      y, name = variables[key]
      lasso = LassoLarsCV(fit_intercept=False, max_iter=2000, cv=cv, n_jobs=1)
      lasso.fit(X, y)
      cv_mse = lasso.mse_path_
      mse_mean = cv_mse.mean(axis=1)
      mse_stdv = cv_mse.std(axis=1)
      yield name, lasso.cv_alphas_, mse_mean, mse_stdv


class Lasso2(_LassoOrLars2, _Lasso):
  @classmethod
  def cross_validate(cls, X, variables, num_folds=5, labels=None):
    raise NotImplementedError("Multivariate Lasso doesn't yet support CV.")


class HackAroundSklearnCV(GroupKFold):
  """LassoLarsCV doesn't pass along `groups`, so we have to hack it in here."""
  def __init__(self, groups=None, **kwargs):
    GroupKFold.__init__(self, **kwargs)
    self.groups = groups

  def split(self, X, y):
    return GroupKFold.split(self, X, y=y, groups=self.groups)


REGRESSION_MODELS = dict(
    pls=dict(uni=PLS1, multi=PLS2),
    lasso=dict(uni=Lasso1, multi=Lasso2),
    lars=dict(uni=Lars1, multi=Lars2),
)
