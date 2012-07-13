import argparse
import numpy as np
import urllib, urllib2
import cStringIO
import sys
import h5py
import tempfile

def main():

  parser = argparse.ArgumentParser(description='Request a list of ids that match specified type and status values')
  parser.add_argument('--status', type=int, action="store", default=None )
  parser.add_argument('--type', type=int, action="store", default=None )
  parser.add_argument('baseurl', action="store" )
  parser.add_argument('token', action="store" )

  result = parser.parse_args()

  url = 'http://%s/annotate/%s/ids/' % ( result.baseurl, result.token )
  if result.type != None:
    url += 'type/%s/' % ( result.type )
  if result.status != None:
    url += 'status/%s/' % ( result.status )

  # Get cube in question
  try:
    f = urllib2.urlopen ( url )
  except urllib2.URLError:
    print "Failed to open url ", url
    sys.exit(-1)

  tmpfile = tempfile.NamedTemporaryFile ( )
  tmpfile.write ( f.read() )
  tmpfile.tell()
  h5f = h5py.File ( tmpfile.name, driver='core', backing_store=False )

  if len(h5f['ANNOIDS']) == 0:
    print "Found no annotations matching type and status"
  else:
    print "Matching annotations at %s" % ( np.array(h5f['ANNOIDS'][:]) )

if __name__ == "__main__":
  main()



