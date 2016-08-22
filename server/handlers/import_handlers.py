from __future__ import absolute_import
import logging
import numpy as np
from io import BytesIO
from tornado.escape import url_escape

from .base import BaseHandler
from ..web_datasets import (
    WebVectorDataset, DATASETS, PrimaryKeyMetadata, NumericMetadata,
    BooleanMetadata, LookupMetadata)


class DatasetImportHandler(BaseHandler):
  def post(self):
    ds_name = self.get_argument('ds_name')
    ds_kind = self.get_argument('ds_kind')

    if ds_kind not in DATASETS:
      logging.error('Invalid ds_kind: %r', ds_kind)
      self.set_status(415)
      return self.finish('Invalid dataset kind.')

    if not self.request.files:
      logging.error('DatasetImportHandler: no files uploaded')
      self.set_status(403)
      return self.finish('No file uploaded.')

    f, = self.request.files['spectra']
    fh = BytesIO(f['body'])
    try:
      data = np.genfromtxt(fh, dtype=np.float32, delimiter=',', names=True)
      wave = data[data.dtype.names[0]]
      spectra = data.view((np.float32, len(data.dtype.names))).T[1:]
    except Exception as e:
      logging.error('DatasetImportHandler: bad spectra file: %s', e)
      self.set_status(415)
      return self.finish('Unable to parse spectrum data CSV.')

    pkey = np.array(data.dtype.names[1:])

    # metadata is optional
    meta_kwargs = {}
    if 'metadata' in self.request.files:
      f, = self.request.files['metadata']
      fh = BytesIO(f['body'])
      try:
        meta = np.genfromtxt(fh, dtype=None, delimiter=',', names=True)
        meta_pkeys = np.array(meta[meta.dtype.names[0]])
      except Exception as e:
        logging.error('DatasetImportHandler: bad metadata file: %s', e)
        self.set_status(415)
        return self.finish('Unable to parse metadata CSV.')

      if (meta_pkeys != pkey).any():
        logging.error('DatasetImportHandler: mismatching meta_pkeys')
        self.set_status(415)
        return self.finish('Spectrum and metadata names mismatch.')

      for meta_name in meta.dtype.names[1:]:
        x = meta[meta_name]
        if np.issubdtype(x.dtype, np.bool_):
          m = BooleanMetadata(x)
        elif np.issubdtype(x.dtype, np.number):
          m = NumericMetadata(x)
        else:
          m = LookupMetadata(x)
        meta_kwargs[meta_name] = m

    def _load(ds):
      ds.set_data(wave, spectra, pkey=PrimaryKeyMetadata(pkey), **meta_kwargs)
      return True

    # async loading machinery automatically registers us with DATASETS
    WebVectorDataset(ds_name, ds_kind, _load)

    return self.write('/explorer?ds_kind=%s&ds_name=%s' % (
        ds_kind, url_escape(ds_name, plus=False)))


routes = [
    (r'/_import', DatasetImportHandler),
]
