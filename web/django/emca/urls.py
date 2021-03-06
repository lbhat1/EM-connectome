from django.conf.urls import patterns, include, url

# Uncomment the next two lines to enable the admin:
#from django.contrib import admin
#admin.autodiscover()

urlpatterns = patterns('emca.views',
  # catmaid
  url(r'^catmaid/(?P<webargs>\w+/.*)$', 'catmaid'),
  # fetch ids (with predicates)
  url(r'(?P<webargs>^\w+/list/[\w,/]*)$', 'listObjects'),
  # batch fetch RAMON 
  url(r'(?P<webargs>^\w+/objects/[\w,/]*)$', 'getObjects'),
  # get project information
  url(r'(?P<webargs>^\w+/projinfo/[\w,/]*)$', 'projinfo'),
  # get services
  url(r'(?P<webargs>^\w+/(xy|xz|yz|hdf5|npz|zip|id|ids|xyanno||xzanno|yzanno|xytiff|xztiff|yztiff)/[\w,/]+)$', 'emcaget'),
  # the post services
  url(r'(?P<webargs>^\w+/(npvoxels|npdense)/[\w,/]+)$', 'annopost'),
  # csv metadata read
  url(r'(?P<webargs>^\w+/(csv)[\d+/]?[\w,/]*)$', 'csv'),
  # multi-channel false color 
  url(r'(?P<webargs>^\w+/mcfc/[\w,/]+)$', 'mcFalseColor'),
  # HDF5 interfaces
  url(r'(?P<webargs>^\w+/[\d+/]?[\w,/]*)$', 'annotation'),
)
