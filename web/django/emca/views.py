import django.http
from django.views.decorators.cache import cache_control
import MySQLdb
import cStringIO

import empaths
import zindex
import emcarest
import emcaproj
import dbconfig

# Errors we are going to catch
from emcaerror import ANNError

import logging
logger=logging.getLogger("emca")


def emcaget (request, webargs):
  """Restful URL for all read services to annotation projects"""

  [ token , sym, cutoutargs ] = webargs.partition ('/')
  [ service, sym, rest ] = cutoutargs.partition ('/')

  try:
    # add a tiff service for cutouts?
    if service=='xy' or service=='yz' or service=='xz':
      return django.http.HttpResponse(emcarest.emcaget(webargs), mimetype="image/png" )
    elif service=='xytiff' or service=='yztiff' or service=='xztiff':
      return django.http.HttpResponse(emcarest.emcaget(webargs), mimetype="image/tiff" )
    elif service=='hdf5':
      return django.http.HttpResponse(emcarest.emcaget(webargs), mimetype="product/hdf5" )
    elif service=='npz':
      return django.http.HttpResponse(emcarest.emcaget(webargs), mimetype="product/npz" )
    elif service=='zip':
      return django.http.HttpResponse(emcarest.emcaget(webargs), mimetype="product/zip" )
    elif service=='xyanno' or service=='yzanno' or service=='xzanno':
      return django.http.HttpResponse(emcarest.emcaget(webargs), mimetype="image/png" )
    elif service=='id':
      return django.http.HttpResponse(emcarest.emcaget(webargs))
    elif service=='ids':
      return django.http.HttpResponse(emcarest.emcaget(webargs))
    else:
      logger.warning ("HTTP Bad request. Could not find service %s" % dataset )
      return django.http.HttpResponseBadRequest ("Could not find service %s" % dataset )
  except (ANNError,MySQLdb.Error), e:
    return django.http.HttpResponseNotFound(e.value)
  except:
    logger.exception("Unknown exception in emcaget.")
    raise

@cache_control(no_cache=True)
def annopost (request, webargs):
  """Restful URL for all write/post services to annotation projects"""

  # All handling done by emcarest
  try:
    return django.http.HttpResponse(emcarest.annopost(webargs,request.body))
  except ANNError, e:
    return django.http.HttpResponseNotFound(e.value)
  except:
    logger.exception("Unknown exception in annopost.")
    raise

@cache_control(no_cache=True)
def annotation (request, webargs):
  """Get put object interface for RAMON objects"""

  try:
    if request.method == 'GET':
      return django.http.HttpResponse(emcarest.getAnnotation(webargs), mimetype="product/hdf5" )
    elif request.method == 'POST':
      return django.http.HttpResponse(emcarest.putAnnotation(webargs,request.body))
    elif request.method == 'DELETE':
      emcarest.deleteAnnotation(webargs)
      return django.http.HttpResponse ("Success", mimetype='text/html')
  except ANNError, e:
    if hasattr(e,'value'):
      return django.http.HttpResponseNotFound(e.value)
    else: 
      return django.http.HttpResponseNotFound(e)
  except:
    logger.exception("Unknown exception in annotation.")
    raise


@cache_control(no_cache=True)
def csv (request, webargs):
  """Get (not yet put) csv interface for RAMON objects"""

  try:
    if request.method == 'GET':
      return django.http.HttpResponse(emcarest.getCSV(webargs), mimetype="text/html" )
  except ANNError, e:
    if hasattr(e,'value'):
      return django.http.HttpResponseNotFound(e.value)
    else: 
      return django.http.HttpResponseNotFound(e)
  except:
    logger.exception("Unknown exception in csv.")
    raise
      
@cache_control(no_cache=True)
def getObjects ( request, webargs ):
  """Batch fetch of RAMON objects"""

  try:
    if request.method == 'GET':
      raise ANNError ( "GET requested. objects Web service requires a POST of a list of identifiers.")
    elif request.method == 'POST':
      return django.http.HttpResponse(emcarest.getAnnotations(webargs,request.body), mimetype="product/hdf5") 
    
  except ANNError, e:
    return django.http.HttpResponseNotFound(e.value)
  except:
    logger.exception("Unknown exception in getObjects.")
    raise

@cache_control(no_cache=True)
def listObjects ( request, webargs ):
  """Return a list of objects matching predicates and cutout"""

  try:
    if request.method == 'GET':
      return django.http.HttpResponse(emcarest.listAnnoObjects(webargs), mimetype="product/hdf5") 
    elif request.method == 'POST':
      return django.http.HttpResponse(emcarest.listAnnoObjects(webargs,request.body), mimetype="product/hdf5") 
    
  except ANNError, e:
    return django.http.HttpResponseNotFound(e.value)
  except:
    logger.exception("Unknown exception in listObjects.")
    raise


def catmaid (request, webargs):
  """Convert a CATMAID request into an cutout."""

  try:
    catmaidimg = emcarest.emcacatmaid(webargs)

    fobj = cStringIO.StringIO ( )
    catmaidimg.save ( fobj, "PNG" )
    fobj.seek(0)
    return django.http.HttpResponse(fobj.read(), mimetype="image/png")

  except ANNError, e:
    return django.http.HttpResponseNotFound(e)
  except:
    logger.exception("Unknown exception in annopost.")
    raise


def projinfo (request, webargs):
  """Return project and dataset configuration information"""

  try:  
    return django.http.HttpResponse(emcarest.projInfo(webargs), mimetype="product/hdf5" )
  except ANNError, e:
    return django.http.HttpResponseNotFound(e)
  except:
    logger.exception("Unknown exception in projInfo.")
    raise


def mcFalseColor (request, webargs):
  """Cutout of multiple channels with false color rendering"""

  try:
    return django.http.HttpResponse(emcarest.mcFalseColor(webargs), mimetype="image/png" )
  except ANNError, e:
    return django.http.HttpResponseNotFound(e)
  except:
    logger.exception("Unknown exception in mcFalseColor.")
    raise
